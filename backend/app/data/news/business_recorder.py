"""
Business Recorder / Pakistan Financial News Scraper

Uses Google News RSS for Pakistan financial/business news.
Falls back to BR homepage scraping if Google News fails.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from xml.etree import ElementTree

import httpx

logger = logging.getLogger("asaas.data.news.business_recorder")

_GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?"
    "q=pakistan+stock+exchange+OR+SBP+OR+PSX+OR+karachi+business+economy"
    "&hl=en-PK&gl=PK&ceid=PK:en"
)
_HOME_URL = "https://www.brecorder.com"
_SOURCE = "business_recorder"
_TIMEOUT = 15


class BusinessRecorderScraper:
    """Fetches Pakistan financial news via Google News RSS."""

    async def fetch(self) -> List[Dict[str, Any]]:
        items = await self._fetch_google_news()
        if items:
            return items
        logger.warning("Google News RSS empty — falling back to BR homepage")
        return await self._fetch_homepage()

    async def _fetch_google_news(self) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_GOOGLE_NEWS_URL)
                if resp.status_code != 200:
                    return []
                resp.raise_for_status()

            root = ElementTree.fromstring(resp.text.encode("utf-8"))
            items: List[Dict[str, Any]] = []

            for item_el in root.iter("item"):
                title = (item_el.findtext("title") or "").strip()
                link = (item_el.findtext("link") or "").strip()
                pub_date = (item_el.findtext("pubDate") or "").strip()
                source_el = item_el.find("source")
                source_name = (source_el.text or _SOURCE).strip() if source_el is not None else _SOURCE

                if not title:
                    continue

                items.append({
                    "source": source_name,
                    "headline": title,
                    "url": link or None,
                    "published_at": pub_date or None,
                    "raw": {"title": title, "link": link, "pubDate": pub_date, "source": source_name},
                })

            return items[:50]
        except Exception as exc:
            logger.error("Google News RSS failed: %s", exc)
            return []

    async def _fetch_homepage(self) -> List[Dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_HOME_URL, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                    "Accept": "text/html,application/xhtml+xml",
                })
                if resp.status_code != 200:
                    return []
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            items: List[Dict[str, Any]] = []

            for tag in soup.select("h2 a, h3 a, .article-title a, a[href*='/news/']"):
                headline = tag.get_text(strip=True)
                href = tag.get("href")
                if not headline or len(headline) < 5:
                    continue
                url = None
                if href:
                    url = href if href.startswith("http") else f"https://www.brecorder.com{href}"
                items.append({
                    "source": _SOURCE,
                    "headline": headline[:200],
                    "url": url,
                    "published_at": None,
                    "raw": {"headline": headline},
                })

            return items[:50]
        except Exception as exc:
            logger.error("Business Recorder homepage scrape failed: %s", exc)
            return []
