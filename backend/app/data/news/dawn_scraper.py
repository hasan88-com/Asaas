"""
Dawn Business News Scraper

Primary:  Dawn business RSS feed.
No HTML fallback needed — Dawn RSS is reliable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from xml.etree import ElementTree

import httpx

logger = logging.getLogger("asaas.data.news.dawn")

_RSS_URL = "https://www.dawn.com/feeds/business"
_SOURCE = "dawn"
_TIMEOUT = 15


class DawnScraper:
    """Fetches Dawn business section news via RSS."""

    async def fetch(self) -> List[Dict[str, Any]]:
        return await self._fetch_rss()

    async def _fetch_rss(self) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_RSS_URL)
                resp.raise_for_status()

            root = ElementTree.fromstring(resp.content)
            items = []
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                description = (item.findtext("description") or "").strip()
                if title:
                    items.append({
                        "source": _SOURCE,
                        "headline": title,
                        "url": link or None,
                        "published_at": pub_date or None,
                        "raw": {
                            "title": title,
                            "link": link,
                            "pubDate": pub_date,
                            "description": description,
                        },
                    })
            return items
        except Exception as exc:
            logger.error("Dawn RSS fetch failed: %s", exc)
            return []
