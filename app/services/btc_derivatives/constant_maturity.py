from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from app.services.btc_derivatives.expiry_policy import standard_expiries

BUCKET_DTE = {"30D": 30, "60D": 60, "90D": 90}


def select_constant_maturity_expiry(
    expiries: Sequence[str],
    *,
    as_of: date,
    maturity_bucket: str,
) -> dict[str, Any]:
    target_dte = BUCKET_DTE[maturity_bucket]
    candidates: list[tuple[int, str]] = []
    for expiry in standard_expiries(expiries, as_of=as_of):
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (expiry_date - as_of).days
        if dte > 0:
            candidates.append((dte, expiry))
    if not candidates:
        return {
            "expiry": None,
            "dte": None,
            "target_dte": target_dte,
            "distance": None,
            "interpolation_sources": [],
            "interpolation_status": "data_insufficient",
            "status": "data_insufficient",
        }
    candidates.sort()
    dte, expiry = min(candidates, key=lambda item: (abs(item[0] - target_dte), item[0]))
    lower = max((item for item in candidates if item[0] <= target_dte), default=None)
    upper = min((item for item in candidates if item[0] >= target_dte), default=None)
    interpolation_sources = [
        {"dte": item[0], "expiry": item[1]}
        for item in dict.fromkeys(item for item in (lower, upper) if item is not None)
    ]
    return {
        "expiry": expiry,
        "dte": dte,
        "target_dte": target_dte,
        "distance": abs(dte - target_dte),
        "interpolation_sources": interpolation_sources,
        "interpolation_status": (
            "bracketed" if lower is not None and upper is not None and lower != upper
            else "single_source"
        ),
        "status": "ok",
    }


def annotate_constant_maturity_history(
    points: Sequence[dict[str, Any]],
    *,
    maturity_bucket: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_expiry: str | None = None
    for point in points:
        source_expiry = point.get("source_expiry")
        output.append(
            {
                **point,
                "maturity_bucket": maturity_bucket,
                "rollover": previous_expiry is not None and source_expiry != previous_expiry,
            }
        )
        previous_expiry = source_expiry
    return output
