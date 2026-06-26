"""
The Financial Daily Scraper

Scrapes thefinancialdaily.com for Pakistan business/finance news.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("asaas.data.news.financial_daily")

_URL = "https://thefinancialdaily.com/"
_SOURCE = "the_financial_daily"
_TIMEOUT = 15


class FinancialDailyScraper:
    """Fetches Pakistan business news from The Financial Daily."""

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

                # Skip navigation/menu items
                if any(skip in headline.lower() for skip in (
                    "live commodities", "mobile phone", "islamic banking",
                    "menu", "home", "about", "contact", "privacy",
                    "login", "subscribe", "advertise",
                )):
                    continue

                # Skip if already seen (dedup)
                if headline in seen:
                    continue
                seen.add(headline)

                url = href if href.startswith("http") else f"https://thefinancialdaily.com{href}"

                items.append({
                    "source": _SOURCE,
                    "headline": headline[:200],
                    "url": url,
                    "published_at": None,
                    "raw": {"headline": headline, "url": url},
                })

            return items[:30]
        except Exception as exc:
            logger.error("Financial Daily scrape failed: %s", exc)
            return []
