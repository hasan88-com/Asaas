"""
Asaas (اثاثہ) — News Monitoring Worker (Stage 1: INGEST)

Fetches news from all sources CONCURRENTLY, persists each source's items as it
returns (incremental), enriches with lexicon sentiment (Stage 2), routes to
MaterialityService (Stage 3), and finally rolls up market sentiment (Stage 4).
Publishes scrape progress to Redis so the frontend can poll status instead of
blind-waiting (TECH.md §6).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy import select

from app.core.db import async_session_factory
from app.data.news import (
    PSXScraper,
    SBPScraper,
    BusinessRecorderScraper,
    DawnScraper,
    FinancialDailyScraper,
    ProfitScraper,
    TribuneScraper,
    APPScraper,
    ARYNewsScraper,
    normalize,
)
from app.data.news.normalizer import normalize_headline
from app.models.news import NewsItem
from app.services.materiality import MaterialityService
from app.services.sentiment import classify_sentiment

logger = logging.getLogger("asaas.workers.news_monitor")

SCRAPE_STATUS_KEY = "news:scrape:status"
_STATUS_TTL = 300  # seconds — a crashed run's "running" status self-expires


def _scrapers():
    return [
        PSXScraper(), SBPScraper(), BusinessRecorderScraper(), DawnScraper(),
        FinancialDailyScraper(), ProfitScraper(), TribuneScraper(), APPScraper(),
        ARYNewsScraper(),
    ]


async def _set_status(payload: Dict[str, Any]) -> None:
    """Best-effort publish of scrape progress to Redis (fail-open)."""
    try:
        from app.core.redis import redis_client
        await redis_client.setex(SCRAPE_STATUS_KEY, _STATUS_TTL, json.dumps(payload))
    except Exception:
        pass


async def _fetch_one(scraper) -> Tuple[str, List[Dict[str, Any]]]:
    name = type(scraper).__name__
    try:
        items = await scraper.fetch()
        logger.info("%s fetched %d items", name, len(items))
        return name, items
    except Exception as exc:
        logger.error("%s fetch error: %s", name, exc)
        return name, []


async def _persist_batch(
    raw_items: List[Dict[str, Any]],
    seen_urls: set,
    seen_headlines: set,
) -> int:
    """Normalize, dedup (in-run + DB), enrich, persist, and score one source's
    items. Returns the count of newly ingested items."""
    if not raw_items:
        return 0

    normalized = normalize(raw_items)
    ingested = 0

    async with async_session_factory() as session:
        for article in normalized:
            headline = article["headline"]
            url = article.get("url")
            hkey = normalize_headline(headline)

            # In-run dedup across sources (normalize() only dedups within a batch).
            if url and url in seen_urls:
                continue
            if hkey and hkey in seen_headlines:
                continue

            try:
                # DB dedup: by URL if present, else by exact headline.
                if url:
                    exists_q = select(NewsItem).where(NewsItem.url == url)
                else:
                    exists_q = select(NewsItem).where(NewsItem.headline == headline)
                if (await session.execute(exists_q)).scalar_one_or_none() is not None:
                    if url:
                        seen_urls.add(url)
                    if hkey:
                        seen_headlines.add(hkey)
                    continue

                # Stage 2: enrich with lexicon sentiment + magnitude at ingest.
                desc = (article.get("raw") or {}).get("description") or ""
                label, magnitude = classify_sentiment(f"{headline} {desc}")

                news_item = NewsItem(
                    source=article["source"],
                    headline=headline,
                    url=url,
                    published_at=article.get("published_at") or datetime.now(timezone.utc),
                    sentiment=label,
                    magnitude=magnitude,
                    raw=article.get("raw") or {},
                )
                session.add(news_item)
                await session.flush()  # obtain id for materiality

                # Stage 3: match to holdings + selective flagging.
                await MaterialityService(session).process_news_item(news_item.id)
                ingested += 1

                if url:
                    seen_urls.add(url)
                if hkey:
                    seen_headlines.add(hkey)
            except Exception as exc:
                logger.error("Failed to process '%s': %s", headline, exc)

        await session.commit()

    return ingested


async def run_news_monitor() -> None:
    """Ingest news from all sources concurrently, enrich, score, aggregate."""
    logger.info("Starting News Monitoring Job")

    scrapers = _scrapers()
    total = len(scrapers)
    started_at = datetime.now(timezone.utc).isoformat()
    await _set_status({
        "state": "running", "sources_total": total, "sources_done": 0,
        "started_at": started_at, "ingested": 0,
    })

    seen_urls: set = set()
    seen_headlines: set = set()
    ingested = 0
    done = 0

    # Concurrent fetch + incremental persist: handle each source the moment it
    # returns so the fastest source (Dawn RSS ~2s) lands almost immediately.
    tasks = [asyncio.create_task(_fetch_one(s)) for s in scrapers]
    for coro in asyncio.as_completed(tasks):
        _name, items = await coro
        done += 1
        try:
            ingested += await _persist_batch(items, seen_urls, seen_headlines)
        except Exception as exc:
            logger.error("Persist batch failed: %s", exc)
        await _set_status({
            "state": "running", "sources_total": total, "sources_done": done,
            "started_at": started_at, "ingested": ingested,
        })

    # Stage 4: roll up market sentiment after ingest (best-effort).
    try:
        from app.workers.aggregate_sentiment import run_aggregate_sentiment
        await run_aggregate_sentiment()
    except Exception as exc:
        logger.error("Sentiment aggregation failed: %s", exc)

    await _set_status({
        "state": "done", "sources_total": total, "sources_done": done,
        "started_at": started_at, "ingested": ingested,
    })
    logger.info("News Monitoring Job complete — %d new items ingested", ingested)
