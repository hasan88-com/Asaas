"""
SBP Press Release Scraper

Scrapes State Bank of Pakistan press releases via direct scrape and Google News RSS.
Detects rate-change headlines by keyword matching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List
from xml.etree import ElementTree

import httpx

logger = logging.getLogger("asaas.data.news.sbp")

_URLS = [
    "https://www.sbp.org.pk/press/press_release.asp",
    "https://www.sbp.org.pk/press/index.asp",
    "https://www.sbp.org.pk/press",
]
_GOOGLE_NEWS_URL = (
    "https://news.google.com/rss/search?"
    "q=state+bank+of+pakistan+SBP+monetary+policy+OR+interest+rate+OR+policy+rate"
    "&hl=en-PK&gl=PK&ceid=PK:en"
)
_SOURCE = "sbp"
_TIMEOUT = 15
_RATE_KEYWORDS = frozenset(
    {"policy rate", "monetary policy", "interest rate", "sbp rate", "bps", "repo rate"}
)


class SBPScraper:
    """Fetches SBP press releases and policy announcements."""

    async def fetch(self) -> List[Dict[str, Any]]:
        """Return a list of raw press-release dicts."""
        for url in _URLS:
            items = await self._fetch_html(url)
            if items:
                return items

        # Fallback: Google News RSS for SBP news
        items = await self._fetch_google_news()
        if items:
            return items

        logger.warning("All SBP sources failed — returning empty")
        return []

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

                if not title:
                    continue

                lower_title = title.lower()
                is_rate_event = any(kw in lower_title for kw in _RATE_KEYWORDS)

                items.append({
                    "source": _SOURCE,
                    "headline": title,
                    "url": link or None,
                    "published_at": pub_date or None,
                    "raw": {
                        "headline": title,
                        "is_rate_event": is_rate_event,
                    },
                })

            return items[:30]
        except Exception as exc:
            logger.error("SBP Google News RSS failed: %s", exc)
            return []

    async def _fetch_html(self, url: str) -> List[Dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
                    "Accept": "text/html,application/xhtml+xml",
                })
                if resp.status_code != 200:
                    return []
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            items: List[Dict[str, Any]] = []

            # Try table rows first
            for row in soup.select("table tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue

                date_text = cells[0].get_text(strip=True)
                title_cell = cells[1]
                headline = title_cell.get_text(strip=True)
                link_tag = title_cell.find("a")
                url_found = None
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    url_found = href if href.startswith("http") else f"https://www.sbp.org.pk{href}"

                if not headline or len(headline) < 5:
                    continue

                lower_headline = headline.lower()
                is_rate_event = any(kw in lower_headline for kw in _RATE_KEYWORDS)

                items.append({
                    "source": _SOURCE,
                    "headline": headline,
                    "url": url_found,
                    "published_at": date_text or None,
                    "raw": {
                        "date": date_text,
                        "headline": headline,
                        "is_rate_event": is_rate_event,
                    },
                })

            # Fallback: try link lists
            if not items:
                for a_tag in soup.select("a[href*='press'], a[href*='policy'], a[href*='monetary']"):
                    headline = a_tag.get_text(strip=True)
                    if headline and len(headline) > 10:
                        href = a_tag.get("href", "")
                        url_found = href if href.startswith("http") else f"https://www.sbp.org.pk{href}"
                        items.append({
                            "source": _SOURCE,
                            "headline": headline,
                            "url": url_found,
                            "published_at": None,
                            "raw": {"headline": headline, "is_rate_event": False},
                        })

            return items[:30]
        except Exception as exc:
            logger.error("SBP HTML scrape failed for %s: %s", url, exc)
            return []
