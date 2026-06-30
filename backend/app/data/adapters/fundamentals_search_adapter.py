"""
Asaasa — Fundamentals Search Adapter (DuckDuckGo)

Last-resort fundamentals source for a ticker when yfinance is throttled (Render
gets 429s) and we have no DB snapshot. Queries DuckDuckGo's HTML endpoint (no API
key) and best-effort-parses P/E, EPS and price from the result snippets.

This is intentionally a *fallback* — the broadened DB seed is the reliable tier.
Returns {} (or partial) on failure; never fabricates a number, and sanity-bands
everything it does parse.
"""

from __future__ import annotations

import html as _html
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("asaas.fundamentals_search_adapter")

_DDG_HTML = "https://html.duckduckgo.com/html/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AsaasaBot/1.0)"}

# Sanity bands (PSX). EPS/price are PKR; P/E unitless.
_PE_MIN, _PE_MAX = Decimal("0.5"), Decimal("80")


def _to_dec(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(",", "").strip())
    except (InvalidOperation, AttributeError, ValueError):
        return None


def _strip_tags(raw: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", " ", raw))


def _first_match(text: str, patterns: list[str]) -> Optional[Decimal]:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = _to_dec(m.group(1))
            if v is not None:
                return v
    return None


async def fetch_fundamentals_via_search(symbol: str) -> Dict[str, Any]:
    """Best-effort {trailingPE, trailingEps, regularMarketPrice} for `symbol`."""
    base = symbol.upper().replace(".KA", "").strip()
    query = f"{base} PSX share P/E ratio EPS"
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(_DDG_HTML, params={"q": query})
            resp.raise_for_status()
            text = _strip_tags(resp.text)
    except Exception as exc:
        logger.warning("DuckDuckGo fundamentals fetch failed for %s: %s", symbol, exc)
        return {}

    out: Dict[str, Any] = {}

    pe = _first_match(text, [
        r"p/?e\s*(?:ttm)?\s*(?:ratio)?\s*(?:of|is|=|:)?\s*([0-9]+(?:\.[0-9]+)?)",
        r"price[- ]to[- ]earnings[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)",
    ])
    if pe is not None and _PE_MIN <= pe <= _PE_MAX:
        out["trailingPE"] = float(pe)

    eps = _first_match(text, [
        r"\beps\s*(?:ttm)?\s*(?:of|is|=|:)?\s*(-?[0-9][0-9,]*(?:\.[0-9]+)?)",
        r"earnings per share[^0-9-]{0,12}(-?[0-9][0-9,]*(?:\.[0-9]+)?)",
    ])
    if eps is not None and Decimal("-10000") <= eps <= Decimal("100000"):
        out["trailingEps"] = float(eps)

    if out:
        logger.info("DuckDuckGo fundamentals for %s: %s", symbol, out)
    else:
        logger.info("DuckDuckGo fundamentals for %s: nothing parseable", symbol)
    return out
