from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

INSTRUMENTS = ("btc-usdt-perp", "eth-usdt-perp", "hype-usdt-perp", "bnb-usdt-perp", "okb-usdt-perp")
TIMEFRAMES = ("1h", "4h", "1d", "1w", "1M")


@dataclass
class MatrixResult:
    instrument: str
    timeframe: str
    status: str
    cache_state: str | None = None
    candles: int = 0
    geometry: int = 0
    swing: int = 0
    classic: int = 0
    profile: int = 0
    classic_patterns: int = 0
    has_price_line: bool = False
    has_swing_line: bool = False
    has_degraded_message: bool = False
    message: str = ""
    error: str | None = None


def fetch_json(base_url: str, instrument: str, timeframe: str, timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "instrument_id": instrument,
            "timeframe": timeframe,
            "include_geometry": "true",
            "candles_limit": "180",
        }
    )
    url = f"{base_url.rstrip('/')}/api/v1/structure/tab/bundle?{query}"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - local diagnostic URL
        return json.loads(response.read().decode("utf-8"))


def count_classic_patterns(snapshot: dict[str, Any]) -> int:
    payload = snapshot.get("classic_patterns") or {}
    return sum(1 for item in [payload.get("primary"), *(payload.get("candidates") or [])] if item)


def inspect_payload(instrument: str, timeframe: str, payload: dict[str, Any]) -> MatrixResult:
    snapshot = payload.get("snapshot") or {}
    geometry = snapshot.get("geometry") or []
    candles = payload.get("candles") or []
    status_message = payload.get("status_message") or ""
    swing = [item for item in geometry if item.get("system") == "swing"]
    classic = [item for item in geometry if item.get("system") == "classic"]
    profile = [item for item in geometry if item.get("system") == "profile"]
    has_price_line = bool(candles)
    has_swing_line = any(
        len(item.get("points_json") or item.get("points") or []) >= 2 for item in swing
    )
    has_degraded_message = bool(status_message) or payload.get("cache_state") in {
        "missing",
        "stale",
        "error",
        "degraded",
    }
    status = "ready"
    if candles and swing and not has_swing_line:
        status = "render_failed"
    elif candles and not snapshot:
        status = "degraded"
    elif payload.get("cache_state") == "missing":
        status = "degraded" if candles else "missing"
    elif not candles:
        status = "missing"
    return MatrixResult(
        instrument=instrument,
        timeframe=timeframe,
        status=status,
        cache_state=payload.get("cache_state"),
        candles=len(candles),
        geometry=len(geometry),
        swing=len(swing),
        classic=len(classic),
        profile=len(profile),
        classic_patterns=count_classic_patterns(snapshot),
        has_price_line=has_price_line,
        has_swing_line=has_swing_line,
        has_degraded_message=has_degraded_message,
        message=status_message,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check structure bundle coverage across default instruments/timeframes."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    results: list[MatrixResult] = []
    for instrument in INSTRUMENTS:
        for timeframe in TIMEFRAMES:
            try:
                payload = fetch_json(args.base_url, instrument, timeframe, args.timeout)
                results.append(inspect_payload(instrument, timeframe, payload))
            except Exception as exc:  # pragma: no cover - diagnostic script
                results.append(
                    MatrixResult(
                        instrument=instrument,
                        timeframe=timeframe,
                        status="render_failed",
                        error=str(exc),
                    )
                )

    failures = [
        item
        for item in results
        if item.status == "render_failed"
        or (item.candles > 0 and not item.has_price_line)
        or (item.cache_state == "missing" and not item.has_degraded_message)
    ]

    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(
                f"{item.instrument:14} {item.timeframe:>3} {item.status:13} "
                f"candles={item.candles:3} swing={item.swing} classic={item.classic} "
                f"profile={item.profile} patterns={item.classic_patterns} state={item.cache_state}"
            )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
