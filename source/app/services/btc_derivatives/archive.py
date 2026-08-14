from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

RETENTION_DAYS = {
    "option_chain_15m": 7,
    "option_chain_1h": 90,
    "perp_snapshot_15m": 7,
    "perp_snapshot_1h": 90,
    "daily_metrics": 400,
}
PROTECTED_TYPES = {"daily_metrics"}


@dataclass(frozen=True)
class ArchiveWriteResult:
    path: Path
    content_hash: str
    created: bool


@dataclass(frozen=True)
class ArchiveMaintenanceReport:
    deleted_expired: int = 0
    deleted_for_quota: int = 0
    bytes_after: int = 0


class DerivativesArchive:
    def __init__(self, root: Path, *, quota_bytes: int = 5 * 1024**3) -> None:
        self.root = Path(root)
        self.quota_bytes = quota_bytes
        self.index_path = self.root / "archive_index.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS partitions (
                    content_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    data_type TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    row_count INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_partitions_captured "
                "ON partitions(data_type, captured_at)"
            )

    @staticmethod
    def _canonical(records: list[dict[str, Any]]) -> bytes:
        return json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

    def append(
        self,
        *,
        provider: str,
        underlying: str,
        data_type: str,
        captured_at: datetime,
        records: list[dict[str, Any]],
    ) -> ArchiveWriteResult:
        captured_at = captured_at.astimezone(timezone.utc)
        canonical = self._canonical(records)
        hash_context = json.dumps(
            {
                "provider": provider,
                "underlying": underlying.upper(),
                "data_type": data_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        content_hash = hashlib.sha256(hash_context + b"\n" + canonical).hexdigest()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT relative_path FROM partitions WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if existing:
                return ArchiveWriteResult(
                    self.root / existing["relative_path"],
                    content_hash,
                    False,
                )
        directory = (
            self.root
            / provider
            / underlying.upper()
            / data_type
            / f"{captured_at:%Y}"
            / f"{captured_at:%m}"
            / f"{captured_at:%d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{captured_at:%H%M%S}-{content_hash[:12]}.jsonl.gz"
        destination = directory / filename
        temporary = destination.with_suffix(".gz.tmp")
        envelope = {
            "schema_version": "derivatives-archive-v1",
            "provider": provider,
            "underlying": underlying.upper(),
            "data_type": data_type,
            "captured_at": captured_at.isoformat(),
            "records": records,
        }
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
            handle.write(json.dumps(envelope, ensure_ascii=False, default=str))
            handle.write("\n")
        os.replace(temporary, destination)
        relative_path = destination.relative_to(self.root).as_posix()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO partitions (
                        content_hash, provider, underlying, data_type,
                        captured_at, relative_path, row_count, size_bytes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        content_hash,
                        provider,
                        underlying.upper(),
                        data_type,
                        captured_at.isoformat(),
                        relative_path,
                        len(records),
                        destination.stat().st_size,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return ArchiveWriteResult(destination, content_hash, True)

    def list_partitions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM partitions ORDER BY captured_at"
                )
            ]

    def read_records(
        self,
        *,
        data_type: str,
        underlying: str = "BTC",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Read persisted records in capture order.

        Portable updates intentionally clear the transient cache while preserving
        this archive. Historical charts therefore use the archive as their source
        of truth and merge the cache only as a recent acceleration layer.
        """
        clauses = ["data_type = ?", "underlying = ?"]
        params: list[Any] = [data_type, underlying.upper()]
        if start is not None:
            clauses.append("captured_at >= ?")
            params.append(start.astimezone(timezone.utc).isoformat())
        if end is not None:
            clauses.append("captured_at <= ?")
            params.append(end.astimezone(timezone.utc).isoformat())
        query = (
            "SELECT captured_at, relative_path FROM partitions WHERE "
            + " AND ".join(clauses)
            + " ORDER BY captured_at"
        )
        with self._connect() as connection:
            rows = list(connection.execute(query, params))
        records: list[dict[str, Any]] = []
        for row in rows:
            path = self.root / row["relative_path"]
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    envelope = json.loads(handle.readline())
            except (OSError, json.JSONDecodeError):
                continue
            captured_at = str(envelope.get("captured_at") or row["captured_at"])
            for item in envelope.get("records") or []:
                if not isinstance(item, dict):
                    continue
                payload = dict(item)
                payload.setdefault("timestamp", captured_at)
                payload.setdefault("archive_captured_at", captured_at)
                records.append(payload)
        return records

    @staticmethod
    def _parse_timestamp(value: object) -> datetime:
        """Parse a legacy timestamp string into an offset-aware datetime.

        `daily_history.json` records are produced by multiple writers over
        the project's history; some emit offset-aware ISO strings, others
        emit naive ones. Mixing them in `max()` raised TypeError on
        Python 3.11+. We normalize naive datetimes to UTC so comparison
        always works.
        """
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def migrate_legacy(self, legacy_root: Path) -> int:
        legacy_root = Path(legacy_root)
        created = 0
        snapshot_path = legacy_root / "normalized_snapshot.json"
        if snapshot_path.exists():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                snapshot = {}
            options = snapshot.get("options") or []
            provider = snapshot.get("primary_option_provider")
            if (
                snapshot.get("snapshot_state") in {"live", "stale"}
                and provider
                and provider != "fixture"
                and options
            ):
                captured_at = datetime.fromisoformat(
                    str(snapshot["data_timestamp"]).replace("Z", "+00:00")
                )
                result = self.append(
                    provider=str(provider),
                    underlying="BTC",
                    data_type="option_chain_15m",
                    captured_at=captured_at,
                    records=options,
                )
                created += int(result.created)
        history_path = legacy_root / "daily_history.json"
        if history_path.exists():
            try:
                history = json.loads(history_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                history = []
            real_history = [
                item
                for item in history
                if isinstance(item, dict)
                and item.get("timestamp")
                and item.get("source_provider") != "fixture"
            ]
            if real_history:
                captured_at = max(
                    self._parse_timestamp(item["timestamp"])
                    for item in real_history
                )
                result = self.append(
                    provider="derived",
                    underlying="BTC",
                    data_type="daily_metrics",
                    captured_at=captured_at,
                    records=real_history,
                )
                created += int(result.created)
        return created

    def _delete(self, content_hash: str, relative_path: str) -> bool:
        path = self.root / relative_path
        path.unlink(missing_ok=True)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM partitions WHERE content_hash = ?",
                (content_hash,),
            )
        return True

    def maintain(
        self,
        *,
        now: datetime | None = None,
    ) -> ArchiveMaintenanceReport:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expired = 0
        quota_deleted = 0
        rows = self.list_partitions()
        for row in rows:
            retention = RETENTION_DAYS.get(row["data_type"], 90)
            captured = datetime.fromisoformat(row["captured_at"])
            if captured < now - timedelta(days=retention):
                self._delete(row["content_hash"], row["relative_path"])
                expired += 1
        rows = self.list_partitions()
        total = sum(int(row["size_bytes"]) for row in rows)
        newest_by_type: dict[str, str] = {}
        for row in rows:
            newest_by_type[row["data_type"]] = row["content_hash"]
        for row in rows:
            if total <= self.quota_bytes:
                break
            if row["data_type"] in PROTECTED_TYPES:
                continue
            if newest_by_type.get(row["data_type"]) == row["content_hash"]:
                continue
            total -= int(row["size_bytes"])
            self._delete(row["content_hash"], row["relative_path"])
            quota_deleted += 1
        return ArchiveMaintenanceReport(expired, quota_deleted, max(total, 0))
