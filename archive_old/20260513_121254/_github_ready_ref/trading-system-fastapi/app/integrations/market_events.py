from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import httpx

from app.core.config import settings


@dataclass(slots=True)
class ExternalMarketEvent:
    external_id: str
    category: str
    title: str
    summary: str | None
    source: str
    reliability: str
    ts_event: datetime
    payload_json: dict
    instrument_tokens: list[str]


class GateAnnouncementsProvider:
    def __init__(self, urls: list[str] | None = None, timeout: int | None = None) -> None:
        self.urls = urls or settings.market_events_gate_announcements_urls
        self.timeout = timeout or settings.gateio_timeout_seconds

    async def fetch_latest(self, limit: int = 50) -> list[ExternalMarketEvent]:
        if not self.urls:
            return []
        seen: set[str] = set()
        results: list[ExternalMarketEvent] = []
        async with httpx.AsyncClient(timeout=self.timeout, headers={"Accept": "text/html"}) as client:
            for url in self.urls:
                response = await client.get(url)
                response.raise_for_status()
                for item in self._parse_listing(response.text, url):
                    if item.external_id in seen:
                        continue
                    seen.add(item.external_id)
                    results.append(item)
                    if len(results) >= limit:
                        return results
        return results

    def _parse_listing(self, html: str, base_url: str) -> list[ExternalMarketEvent]:
        pattern = re.compile(r'href="(?P<href>/announcements(?:/article)?/\d+)"[^>]*>(?P<title>[^<]{6,220})<', re.I)
        parsed: list[ExternalMarketEvent] = []
        for match in pattern.finditer(html):
            href = match.group("href")
            title = self._clean_text(match.group("title"))
            if not title:
                continue
            article_id = href.rstrip("/").split("/")[-1]
            full_url = urljoin(base_url, href)
            category = self._classify_title(title)
            tokens = self._extract_tokens(title)
            parsed.append(
                ExternalMarketEvent(
                    external_id=f"gate-announcement:{article_id}",
                    category=category,
                    title=title,
                    summary=None,
                    source="gateio:announcements",
                    reliability="HIGH",
                    ts_event=datetime.now(UTC),
                    payload_json={"url": full_url, "provider": "gateio_announcements"},
                    instrument_tokens=tokens,
                )
            )
        return parsed

    @staticmethod
    def _classify_title(title: str) -> str:
        title_l = title.lower()
        if "funding" in title_l:
            return "funding"
        if "delist" in title_l:
            return "delisting"
        if "list" in title_l:
            return "listing"
        if any(key in title_l for key in ["upgrade", "maintenance", "engine", "suspend"]):
            return "maintenance"
        return "announcement"

    @staticmethod
    def _extract_tokens(text: str) -> list[str]:
        matches = re.findall(r'\(([A-Z0-9_]{2,20})\)', text)
        return list(dict.fromkeys(matches))

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r'\s+', ' ', unescape(text)).strip()


class RSSMarketEventsProvider:
    def __init__(self, urls: list[str] | None = None, timeout: int | None = None) -> None:
        self.urls = urls or settings.market_events_rss_urls
        self.timeout = timeout or settings.gateio_timeout_seconds

    async def fetch_latest(self, limit: int = 50) -> list[ExternalMarketEvent]:
        if not self.urls:
            return []
        results: list[ExternalMarketEvent] = []
        async with httpx.AsyncClient(timeout=self.timeout, headers={"Accept": "application/rss+xml, application/xml, text/xml"}) as client:
            for url in self.urls:
                response = await client.get(url)
                response.raise_for_status()
                results.extend(self._parse_feed(response.text, url))
                if len(results) >= limit:
                    return results[:limit]
        return results[:limit]

    def _parse_feed(self, xml_text: str, source_url: str) -> list[ExternalMarketEvent]:
        root = ET.fromstring(xml_text)
        items: list[ExternalMarketEvent] = []
        for item in root.findall('.//item'):
            title = self._child_text(item, 'title')
            if not title:
                continue
            link = self._child_text(item, 'link')
            description = self._child_text(item, 'description')
            pub_date = self._child_text(item, 'pubDate')
            items.append(
                ExternalMarketEvent(
                    external_id=f"rss:{link or title}",
                    category="news",
                    title=title,
                    summary=description,
                    source=f"rss:{source_url}",
                    reliability="MEDIUM",
                    ts_event=self._parse_pub_date(pub_date),
                    payload_json={"url": link, "provider": "rss"},
                    instrument_tokens=GateAnnouncementsProvider._extract_tokens(title),
                )
            )
        return items

    @staticmethod
    def _child_text(node: ET.Element, tag: str) -> str | None:
        child = node.find(tag)
        if child is None or child.text is None:
            return None
        return child.text.strip()

    @staticmethod
    def _parse_pub_date(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            return parsedate_to_datetime(value).astimezone(UTC)
        except Exception:
            return datetime.now(UTC)


def dedupe_events(events: Iterable[ExternalMarketEvent]) -> list[ExternalMarketEvent]:
    seen: set[str] = set()
    unique: list[ExternalMarketEvent] = []
    for item in events:
        if item.external_id in seen:
            continue
        seen.add(item.external_id)
        unique.append(item)
    unique.sort(key=lambda e: e.ts_event, reverse=True)
    return unique
