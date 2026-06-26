"""
APP (Associated Press of Pakistan) Scraper

Scrapes app.com.pk/business for government/business news.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("asaas.data.news.app")

_URL = "https://www.app.com.pk/business/"
_SOURCE = "app"
_TIMEOUT = 15


class APPScraper:
    """Fetches government/business news from APP."""

    async def fetch(self) -> List[Dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_URL, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                    "Accept": "text/html,application/xhtml+xml",
                })
                if resp.status_code != 200:
                    return []
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            items: List[Dict[str, Any]] = []
            seen = set()

            for a_tag in soup.select("a[href]"):
                headline = a_tag.get_text(strip=True)
                href = a_tag.get("href", "")

                if not headline or len(headline) < 15:
                    continue

                if any(skip in headline.lower() for skip in (
                    "menu", "home", "about", "contact", "privacy",
                    "login", "subscribe", "search", "share",
                    "follow us", "advertisement", "foreign correspondent",
                    "federal budget 2023", "federal budget 2024",
                )):
                    continue

                if headline in seen:
                    continue
                seen.add(headline)

                url = href if href.startswith("http") else f"https://www.app.com.pk{href}"

                items.append({
                    "source": _SOURCE,
                    "headline": headline[:200],
                    "url": url,
                    "published_at": None,
                    "raw": {"headline": headline, "url": url},
                })

            return items[:30]
        except Exception as exc:
            logger.error("APP scrape failed: %s", exc)
            return []
