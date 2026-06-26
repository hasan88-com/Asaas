"""
PSX Announcements Scraper

Scrapes PSX company announcements from the main page announcements section.
All errors are caught; returns [] on failure.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("asaas.data.news.psx")

_HTML_URL = "https://www.psx.com.pk"
_SOURCE = "psx"
_TIMEOUT = 15


class PSXScraper:
    """Fetches PSX company announcements."""

    async def fetch(self) -> List[Dict[str, Any]]:
        """Return a list of raw announcement dicts."""
        return await self._fetch_html()

    async def _fetch_html(self) -> List[Dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(_HTML_URL, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                    "Accept": "text/html,application/xhtml+xml",
                })
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            items: List[Dict[str, Any]] = []

            # PSX main page has announcement sections with date + headline in divs
            for section in soup.select(".news-item, .announcement-item, [class*='announce'], [class*='news']"):
                date_el = section.select_one(".date, .news-date, time, [class*='date']")
                headline_el = section.select_one(".title, .headline, h3, h4, a")
                if headline_el:
                    headline = headline_el.get_text(strip=True)
                    link_tag = headline_el if headline_el.name == "a" else headline_el.find("a")
                    url = None
                    if link_tag and link_tag.get("href"):
                        href = link_tag["href"]
                        url = href if href.startswith("http") else f"https://www.psx.com.pk{href}"
                    date_text = date_el.get_text(strip=True) if date_el else None
                    if headline and len(headline) > 5:
                        items.append({
                            "source": _SOURCE,
                            "headline": headline[:200],
                            "url": url,
                            "published_at": date_text,
                            "raw": {"headline": headline},
                        })

            # Fallback: parse exchange announcements from headings
            if not items:
                for tag in soup.find_all(["h3", "h4", "a"]):
                    text = tag.get_text(strip=True)
                    if not text or len(text) < 15:
                        continue
                    upper = text.upper()
                    if not any(kw in upper for kw in ("EXCHANGE", "UNUSUAL", "LISTING OF",
                                                       "DIVIDEND", "NON-COMPLIANCE",
                                                       "FINANCIAL RESULTS", "BOARD MEETING")):
                        continue
                    # Skip navigation/menu items
                    if tag.find_parent(["nav", "header", "footer"]):
                        continue
                    # Skip generic navigation text
                    if text in ("Listing with PSX", "The Exchange", "Market Data",
                                "Products", "Services", "Indices"):
                        continue
                    url = None
                    if tag.name == "a" and tag.get("href"):
                        href = tag["href"]
                        url = href if href.startswith("http") else f"https://www.psx.com.pk{href}"
                    items.append({
                        "source": _SOURCE,
                        "headline": text[:200],
                        "url": url,
                        "published_at": None,
                        "raw": {"headline": text},
                    })

            return items[:30]
        except Exception as exc:
            logger.error("PSX HTML scrape failed: %s", exc)
            return []
