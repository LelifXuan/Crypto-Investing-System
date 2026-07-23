from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.btc_derivatives.archive import DerivativesArchive


def test_archive_writes_gzip_jsonl_partition_and_dedupes_content(
    tmp_path: Path,
) -> None:
    archive = DerivativesArchive(tmp_path, quota_bytes=10_000_000)
    captured_at = datetime(2026, 6, 25, 1, 15, tzinfo=timezone.utc)
    records = [{"instrument": "BTC-25SEP26-65000-C", "open_interest": 100}]

    first = archive.append(
        provider="deribit",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=captured_at,
        records=records,
    )
    second = archive.append(
        provider="deribit",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=captured_at,
        records=records,
    )

    assert first.created is True
    assert second.created is False
    assert first.path.suffixes[-2:] == [".jsonl", ".gz"]
    with gzip.open(first.path, "rt", encoding="utf-8") as handle:
        payload = json.loads(handle.readline())
    assert payload["records"] == records
    assert archive.list_partitions()[0]["content_hash"] == first.content_hash


def test_archive_retention_keeps_daily_metrics_and_removes_expired_chain(
    tmp_path: Path,
) -> None:
    archive = DerivativesArchive(tmp_path, quota_bytes=10_000_000)
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    archive.append(
        provider="deribit",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=now - timedelta(days=8),
        records=[{"value": 1}],
    )
    daily = archive.append(
        provider="derived",
        underlying="BTC",
        data_type="daily_metrics",
        captured_at=now - timedelta(days=399),
        records=[{"max_pain": 60_000}],
    )

    report = archive.maintain(now=now)

    assert report.deleted_expired == 1
    assert daily.path.exists()


def test_archive_quota_removes_oldest_cold_partition_first(tmp_path: Path) -> None:
    archive = DerivativesArchive(tmp_path, quota_bytes=1)
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    old = archive.append(
        provider="okx",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=now - timedelta(days=2),
        records=[{"payload": "old" * 100}],
    )
    newest = archive.append(
        provider="deribit",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=now,
        records=[{"payload": "new" * 100}],
    )

    report = archive.maintain(now=now)

    assert report.deleted_for_quota >= 1
    assert not old.path.exists()
    assert newest.path.exists()


def test_archive_migrates_real_legacy_files_once_without_fixture(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "normalized_snapshot.json").write_text(
        json.dumps(
            {
                "snapshot_state": "live",
                "data_timestamp": "2026-06-25T00:00:00+00:00",
                "primary_option_provider": "deribit",
                "options": [{"provider": "deribit", "instrument": "BTC-C"}],
                "perps": [],
            }
        ),
        encoding="utf-8",
    )
    (legacy / "daily_history.json").write_text(
        json.dumps(
            [{"timestamp": "2026-06-25T00:00:00+00:00", "max_pain_strike": 60_000}]
        ),
        encoding="utf-8",
    )
    archive = DerivativesArchive(tmp_path / "archive")

    first = archive.migrate_legacy(legacy)
    second = archive.migrate_legacy(legacy)

    assert first == 2
    assert second == 0
    assert {row["data_type"] for row in archive.list_partitions()} == {
        "option_chain_15m",
        "daily_metrics",
    }


def test_archive_dedupe_scope_includes_provider_and_data_type(tmp_path: Path) -> None:
    archive = DerivativesArchive(tmp_path)
    captured_at = datetime(2026, 6, 25, tzinfo=timezone.utc)
    records = [{"value": 1}]

    deribit = archive.append(
        provider="deribit",
        underlying="BTC",
        data_type="option_chain_15m",
        captured_at=captured_at,
        records=records,
    )
    okx = archive.append(
        provider="okx",
        underlying="BTC",
        data_type="option_chain_1h",
        captured_at=captured_at,
        records=records,
    )

    assert deribit.created is True
    assert okx.created is True
    assert deribit.content_hash != okx.content_hash
