from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.db.models.market import MarketEvent, MarketEventInstrument
from app.repositories.market_repository import MarketRepository
from app.services.market_event_sources import (
    MarketEventSource,
    load_market_event_normalization_rules,
    load_market_event_sources,
)
from app.services.translation import MarketEventTranslationService
from app.workers.market_event_translation import market_event_translation_worker

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeedEntry:
    title: str
    summary: str
    link: str
    published_at: datetime
    source: str
    source_id: str
    category: str
    reliability: str
    importance: str
    tags: list[str]


class MarketEventFeedService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.sources = [item for item in load_market_event_sources() if item.enabled]
        self.rules = load_market_event_normalization_rules()
        self.translator = MarketEventTranslationService(enabled=True)

    async def sync_default_feeds(self) -> int:
        total = 0
        translation_queue: list[str] = []
        queued_ids: set[str] = set()
        async with httpx.AsyncClient(
            timeout=settings.gateio_timeout_seconds, follow_redirects=True
        ) as client:
            instruments = await self.repository.list_instruments()
            for source in self.sources:
                if source.access_mode not in {"rss", "atom", "rss_or_atom", "html"}:
                    continue
                try:
                    entries = await self._fetch_feed(client, source)
                except Exception as exc:  # pragma: no cover
                    logger.warning(
                        "market event feed fetch failed for %s: %s", source.source_id, exc
                    )
                    continue
                for entry in entries:
                    instrument_ids = self._match_instruments(entry, instruments)
                    payload_json = self.translator.build_initial_payload(
                        {
                            "link": entry.link,
                            "source_id": entry.source_id,
                            "official_priority": source.official_priority,
                            "access_confidence": source.access_confidence,
                            "importance": entry.importance,
                            "tags": entry.tags,
                            "feed_url": source.entry_url,
                        },
                        entry.title,
                        entry.summary,
                    )
                    saved_event = await self.repository.add_market_event(
                        MarketEvent(
                            event_id=self._event_id(entry),
                            category=entry.category,
                            title=entry.title,
                            summary=entry.summary,
                            source=entry.source,
                            reliability=entry.reliability,
                            ts_event=entry.published_at,
                            payload_json=payload_json,
                        )
                    )
                    await self.repository.add_market_event_links(
                        [
                            MarketEventInstrument(event_id=saved_event.event_id, instrument_id=item)
                            for item in instrument_ids
                        ]
                    )
                    if saved_event.event_id not in queued_ids and self.translator.needs_translation(
                        saved_event.payload_json, saved_event.title, saved_event.summary
                    ):
                        translation_queue.append(saved_event.event_id)
                        queued_ids.add(saved_event.event_id)
                    total += 1
        if translation_queue:
            await market_event_translation_worker.enqueue_event_ids(translation_queue)
        return total

    async def _fetch_feed(
        self, client: httpx.AsyncClient, source: MarketEventSource
    ) -> list[FeedEntry]:
        response = await client.get(source.entry_url)
        response.raise_for_status()
        response_text = response.text
        if source.access_mode == "html" or self._looks_like_html(
            response_text, response.headers.get("content-type", "")
        ):
            return self._parse_html_feed(response_text, source)
        try:
            root = ElementTree.fromstring(response_text)
        except ElementTree.ParseError:
            if self._supports_html_fallback(source):
                fallback_entries = self._parse_html_feed(response_text, source)
                if fallback_entries:
                    return fallback_entries
            if self._looks_like_html(response_text, response.headers.get("content-type", "")):
                return self._parse_html_feed(response_text, source)
            raise
        if root.tag.endswith("feed"):
            return self._parse_atom_feed(root, source)
        return self._parse_rss_feed(root, source)

    @staticmethod
    def _looks_like_html(text: str, content_type: str) -> bool:
        content_type = (content_type or "").lower()
        if "html" in content_type:
            return True
        sample = (text or "").lstrip().lower()
        return sample.startswith("<!doctype html") or sample.startswith("<html")

    def _parse_html_feed(self, text: str, source: MarketEventSource) -> list[FeedEntry]:
        if self._supports_html_fallback(source):
            return self._parse_panews_html(text, source)
        return []

    @staticmethod
    def _supports_html_fallback(source: MarketEventSource) -> bool:
        lowered_source_id = source.source_id.lower()
        lowered_url = source.entry_url.lower()
        return "panews" in lowered_source_id or "panewslab" in lowered_url

    def _parse_panews_html(self, text: str, source: MarketEventSource) -> list[FeedEntry]:
        script_match = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
        if not script_match:
            return []
        try:
            payload = json.loads(script_match.group(1))
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        entries: list[FeedEntry] = []
        for _index, item in enumerate(payload):
            if not isinstance(item, dict):
                continue
            if not {"slug", "title", "desc", "createdAt"} <= set(item.keys()):
                continue
            title = self._resolve_nuxt_ref(payload, item.get("title"))
            summary = self._clean_html(self._resolve_nuxt_ref(payload, item.get("desc")))
            slug = self._resolve_nuxt_ref(payload, item.get("slug"))
            created_at = self._resolve_nuxt_ref(payload, item.get("createdAt"))
            if not title or not slug or not created_at:
                continue
            category = self._infer_category(source, title, summary)
            entries.append(
                FeedEntry(
                    title=title,
                    summary=summary,
                    link=urljoin(source.entry_url, f"/zh/articles/{slug}"),
                    published_at=self._parse_pub_date(created_at),
                    source=source.provider_name,
                    source_id=source.source_id,
                    category=category,
                    reliability=source.reliability,
                    importance=self._infer_importance(title, summary),
                    tags=list(source.tags),
                )
            )
            if len(entries) >= source.item_limit:
                break
        return entries

    @staticmethod
    def _resolve_nuxt_ref(payload: list[Any], value: Any) -> str:
        if isinstance(value, int) and 0 <= value < len(payload):
            resolved = payload[value]
            if isinstance(resolved, str):
                return resolved.strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    def _parse_rss_feed(
        self, root: ElementTree.Element, source: MarketEventSource
    ) -> list[FeedEntry]:
        items = root.findall(".//item")
        return [
            self._build_entry_from_rss_item(item, source) for item in items[: source.item_limit]
        ]

    def _parse_atom_feed(
        self, root: ElementTree.Element, source: MarketEventSource
    ) -> list[FeedEntry]:
        entries = root.findall(".//{*}entry")
        return [
            self._build_entry_from_atom_item(item, source) for item in entries[: source.item_limit]
        ]

    def _build_entry_from_rss_item(
        self, item: ElementTree.Element, source: MarketEventSource
    ) -> FeedEntry:
        title = self._text(item, "title")
        summary = self._clean_html(self._text(item, "description"))
        link = self._text(item, "link")
        published = self._parse_pub_date(self._text(item, "pubDate"))
        category = self._infer_category(source, title, summary)
        return FeedEntry(
            title=title,
            summary=summary,
            link=link,
            published_at=published,
            source=source.provider_name,
            source_id=source.source_id,
            category=category,
            reliability=source.reliability,
            importance=self._infer_importance(title, summary),
            tags=list(source.tags),
        )

    def _build_entry_from_atom_item(
        self, item: ElementTree.Element, source: MarketEventSource
    ) -> FeedEntry:
        title = self._text_ns(item, "title")
        summary = self._clean_html(self._text_ns(item, "summary") or self._text_ns(item, "content"))
        link = self._atom_link(item)
        published = self._parse_pub_date(
            self._text_ns(item, "updated") or self._text_ns(item, "published")
        )
        category = self._infer_category(source, title, summary)
        return FeedEntry(
            title=title,
            summary=summary,
            link=link,
            published_at=published,
            source=source.provider_name,
            source_id=source.source_id,
            category=category,
            reliability=source.reliability,
            importance=self._infer_importance(title, summary),
            tags=list(source.tags),
        )

    @staticmethod
    def _text(node: ElementTree.Element, tag: str) -> str:
        child = node.find(tag)
        return (child.text or "").strip() if child is not None and child.text else ""

    @staticmethod
    def _text_ns(node: ElementTree.Element, tag: str) -> str:
        child = node.find(f".//{{*}}{tag}")
        return (child.text or "").strip() if child is not None and child.text else ""

    @staticmethod
    def _atom_link(node: ElementTree.Element) -> str:
        for child in node.findall(".//{*}link"):
            href = (child.attrib.get("href") or "").strip()
            if href:
                return href
        return ""

    @staticmethod
    def _clean_html(value: str) -> str:
        text = html.unescape(value or "")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _parse_pub_date(value: str) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            parsed = parsedate_to_datetime(value)
        except ValueError:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _infer_category(self, source: MarketEventSource, title: str, summary: str) -> str:
        haystack = f"{title} {summary}".lower()
        for category, keywords in self.rules.get("category_rules", {}).items():
            if any(keyword.lower() in haystack for keyword in keywords or []):
                return category
        if source.category in {"newsflash", "news"}:
            return "news"
        return source.category

    def _infer_importance(self, title: str, summary: str) -> str:
        haystack = f"{title} {summary}".lower()
        importance_rules = self.rules.get("importance_rules", {})
        for level in ("high", "medium"):
            if any(
                keyword.lower() in haystack for keyword in importance_rules.get(level, []) or []
            ):
                return level
        return "low"

    @staticmethod
    def _event_id(entry: FeedEntry) -> str:
        slug = f"{entry.link}|{entry.title}|{entry.published_at.isoformat()}"
        digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:24]
        return f"feed-{digest}"

    def _match_instruments(self, entry: FeedEntry, instruments: list[Any]) -> list[str]:
        text = f"{entry.title} {entry.summary}".upper()
        keyword_map = self.rules.get("symbol_keywords", {})
        matched: list[str] = []
        for instrument in instruments:
            base = str(getattr(instrument, "base_ccy", "")).upper()
            tokens = keyword_map.get(base, [base])
            if any(token and str(token).upper() in text for token in tokens):
                matched.append(instrument.instrument_id)
        return matched
