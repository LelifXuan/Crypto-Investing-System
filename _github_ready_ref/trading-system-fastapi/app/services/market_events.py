from __future__ import annotations

from app.db.models.market import MarketEvent
from app.integrations.market_events import GateAnnouncementsProvider, RSSMarketEventsProvider, dedupe_events
from app.repositories.market_repository import MarketRepository
from app.services.market import MarketService


class MarketEventIngestionService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_service = MarketService(repository)
        self.gate_provider = GateAnnouncementsProvider()
        self.rss_provider = RSSMarketEventsProvider()

    async def sync(self, limit: int = 50) -> dict[str, int]:
        provider_events = []
        provider_events.extend(await self.gate_provider.fetch_latest(limit=limit))
        provider_events.extend(await self.rss_provider.fetch_latest(limit=limit))
        events = dedupe_events(provider_events)[:limit]
        inserted = 0
        for item in events:
            instrument_ids = await self.repository.match_instrument_ids(item.instrument_tokens)
            persisted = await self.market_service.add_market_event(
                MarketEvent(
                    event_id=item.external_id,
                    category=item.category,
                    title=item.title,
                    summary=item.summary,
                    source=item.source,
                    reliability=item.reliability,
                    ts_event=item.ts_event,
                    payload_json=item.payload_json,
                ),
                instrument_ids=instrument_ids,
            )
            if persisted.event_id == item.external_id:
                inserted += 1
        return {"fetched": len(events), "upserted": inserted}
