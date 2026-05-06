from __future__ import annotations

from app.integrations.market_events import GateAnnouncementsProvider, RSSMarketEventsProvider


def test_gate_announcements_parser_extracts_titles() -> None:
    provider = GateAnnouncementsProvider(urls=[])
    html = '<a href="/announcements/12345">Initial Listing: Gate to List BTC (BTC) Spot Trading</a>'
    events = provider._parse_listing(html, 'https://www.gate.com/announcements/39741')
    assert len(events) == 1
    assert events[0].external_id == 'gate-announcement:12345'
    assert 'BTC' in events[0].instrument_tokens


def test_rss_parser_extracts_item() -> None:
    provider = RSSMarketEventsProvider(urls=[])
    xml = '<rss><channel><item><title>Macro Event (BTC)</title><link>https://example.com/1</link><description>hello</description><pubDate>Sun, 05 Apr 2026 00:00:00 GMT</pubDate></item></channel></rss>'
    events = provider._parse_feed(xml, 'https://example.com/feed')
    assert len(events) == 1
    assert events[0].title == 'Macro Event (BTC)'
