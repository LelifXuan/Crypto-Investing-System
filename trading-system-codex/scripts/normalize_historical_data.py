from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import delete, desc, select, text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import MarketEvent, MarketEventInstrument, MarkPrice


def market_event_key(event: MarketEvent) -> tuple[str, str, str]:
    payload = event.payload_json or {}
    link = str(payload.get("link") or "").strip()
    timestamp = event.ts_event.isoformat() if event.ts_event else ""
    return (str(event.title or "").strip(), timestamp, link)


def market_event_quality(event: MarketEvent) -> tuple[int, int, int, int]:
    payload = event.payload_json or {}
    translated = int(bool(payload.get("translated_title") or payload.get("translated_summary")))
    link = int(bool(payload.get("link")))
    summary_length = len((event.summary or "").strip())
    source_length = len((event.source or "").strip())
    return (translated, link, summary_length, source_length)


async def dedupe_market_events() -> dict[str, int]:
    async with db_manager.session() as session:
        events = list(
            (
                await session.execute(
                    select(MarketEvent).order_by(
                        desc(MarketEvent.ts_event), desc(MarketEvent.created_at)
                    )
                )
            ).scalars()
        )
        links = list((await session.execute(select(MarketEventInstrument))).scalars())

        links_by_event: dict[str, set[str]] = defaultdict(set)
        for link in links:
            links_by_event[link.event_id].add(link.instrument_id)

        merged_events = 0
        merged_links = 0
        grouped: dict[tuple[str, str, str], list[MarketEvent]] = defaultdict(list)
        for event in events:
            grouped[market_event_key(event)].append(event)

        for group in grouped.values():
            if len(group) < 2:
                continue
            keeper = max(group, key=market_event_quality)
            keeper_links = set(links_by_event.get(keeper.event_id, set()))
            for duplicate in group:
                if duplicate.event_id == keeper.event_id:
                    continue
                for instrument_id in links_by_event.get(duplicate.event_id, set()):
                    if instrument_id in keeper_links:
                        continue
                    session.add(
                        MarketEventInstrument(event_id=keeper.event_id, instrument_id=instrument_id)
                    )
                    keeper_links.add(instrument_id)
                    merged_links += 1
                await session.execute(
                    delete(MarketEventInstrument).where(
                        MarketEventInstrument.event_id == duplicate.event_id
                    )
                )
                await session.delete(duplicate)
                merged_events += 1

        return {"merged_events": merged_events, "merged_links": merged_links}


async def prune_mark_price_history(keep_per_series: int) -> dict[str, int]:
    async with db_manager.session() as session:
        rows = (
            await session.execute(
                select(MarkPrice.mark_id, MarkPrice.instrument_id, MarkPrice.source).order_by(
                    MarkPrice.instrument_id,
                    MarkPrice.source,
                    desc(MarkPrice.ts_event),
                    desc(MarkPrice.mark_id),
                )
            )
        ).all()
        seen_counts: dict[tuple[str, str], int] = defaultdict(int)
        delete_ids: list[int] = []
        for mark_id, instrument_id, source in rows:
            key = (instrument_id, source)
            seen_counts[key] += 1
            if seen_counts[key] > keep_per_series:
                delete_ids.append(mark_id)

        if delete_ids:
            chunk_size = 500
            for index in range(0, len(delete_ids), chunk_size):
                chunk = delete_ids[index : index + chunk_size]
                await session.execute(delete(MarkPrice).where(MarkPrice.mark_id.in_(chunk)))
        return {"deleted_mark_prices": len(delete_ids)}


async def vacuum_sqlite() -> dict[str, str]:
    if not settings.database_url.startswith("sqlite+aiosqlite:"):
        return {"vacuum": "skipped"}
    try:
        async with db_manager.engine.begin() as connection:
            await connection.execute(text("VACUUM"))
            await connection.execute(text("ANALYZE"))
        return {"vacuum": "done"}
    except OperationalError:
        return {"vacuum": "skipped (database in use)"}


async def async_main(keep_per_series: int) -> None:
    await db_manager.connect()
    try:
        event_stats = await dedupe_market_events()
        mark_stats = await prune_mark_price_history(keep_per_series)
        vacuum_stats = await vacuum_sqlite()
        print("Historical data normalized:")
        print(f"- merged duplicate market events: {event_stats['merged_events']}")
        print(f"- merged duplicate instrument links: {event_stats['merged_links']}")
        print(f"- deleted stale mark price rows: {mark_stats['deleted_mark_prices']}")
        print(f"- sqlite maintenance: {vacuum_stats['vacuum']}")
    finally:
        await db_manager.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize stored market history for local use.")
    parser.add_argument(
        "--keep-mark-prices",
        type=int,
        default=settings.history_mark_prices_keep_per_series,
        help="How many latest mark price rows to keep per instrument/source series.",
    )
    args = parser.parse_args()
    asyncio.run(async_main(args.keep_mark_prices))


if __name__ == "__main__":
    main()
