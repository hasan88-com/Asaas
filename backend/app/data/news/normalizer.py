"""
News Normalizer

Maps raw scraper output to NewsItem-compatible dicts (TECH.md §7).
Deduplicates by URL. Parses published_at strings to datetime.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("asaas.data.news.normalizer")


def normalize_headline(headline: Optional[str]) -> str:
    """Collapse a headline to a dedup key: lowercase, alphanumerics only.

    So "SBP holds rate at 11.5%!" and "sbp holds rate at 11.5 percent" don't
    both clutter the feed as near-duplicates.
    """
    return re.sub(r"[^a-z0-9]+", " ", (headline or "").lower()).strip()


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        from dateutil import parser as dateutil_parser
        dt = dateutil_parser.parse(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    # Fallback: try common formats
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%b %d, %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert raw scraper dicts to NewsItem-compatible insert dicts.

    Input keys (from scrapers):
      source, headline, url, published_at (str or None), raw (dict)

    Output keys (match news_items schema, TECH.md §7):
      source, headline, url, published_at (datetime|None),
      level, sentiment, materiality_score, summary, raw
    """
    seen_urls: set = set()
    seen_headlines: set = set()
    normalized: List[Dict[str, Any]] = []

    for item in raw_items:
        headline = (item.get("headline") or "").strip()
        if not headline:
            continue

        url = (item.get("url") or "").strip() or None

        # Deduplicate by URL AND by normalized headline (kills near-duplicates
        # that the same story gets across sources / with punctuation variants).
        if url and url in seen_urls:
            continue
        hkey = normalize_headline(headline)
        if hkey and hkey in seen_headlines:
            continue
        if url:
            seen_urls.add(url)
        if hkey:
            seen_headlines.add(hkey)

        published_at = _parse_date(item.get("published_at"))

        normalized.append({
            "source": item.get("source", "unknown"),
            "headline": headline,
            "url": url,
            "published_at": published_at,
            "level": None,           # filled by MaterialityService
            "sentiment": None,       # filled by MaterialityService
            "materiality_score": None,  # filled by MaterialityService
            "summary": None,
            "raw": item.get("raw") or {},
        })

    return normalized
