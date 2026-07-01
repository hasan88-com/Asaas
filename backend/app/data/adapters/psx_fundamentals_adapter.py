"""
Asaasa — PSX Fundamentals Adapter (dps.psx.com.pk, official)

Scrapes the PSX official company page for a ticker's fundamentals — P/E (TTM),
EPS, last price (LDCP), market cap, shares. This is the authoritative source and
works for ANY listed symbol (including ones yfinance/DuckDuckGo can't serve, e.g.
BBFL), so valuation no longer depends on Yahoo being reachable.

Returns an ``info``-style dict (yfinance key names) so it merges straight into the
fundamentals bundle. Sanity-banded; returns {} on failure — never fabricates.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("asaas.psx_fundamentals_adapter")

_URL = "https://dps.psx.com.pk/company/{sym}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}


def _to_float(s: str) -> Optional[float]:
    try:
        v = s.replace(",", "").strip()
        neg = v.startswith("(") and v.endswith(")")  # accounting negatives
        v = v.strip("()")
        f = float(v)
        return -f if neg else f
    except (InvalidOperation, AttributeError, ValueError):
        return None


def _grab_stat(text: str, label_pat: str) -> Optional[float]:
    """First stats_value after a label (labels can carry ** / <span> markup)."""
    m = re.search(label_pat + r'.{0,80}?stats_value">\s*\(?([0-9][0-9,]*\.?[0-9]*)', text, re.S)
    return _to_float(m.group(1)) if m else None


async def fetch_psx_fundamentals(symbol: str) -> Dict[str, Any]:
    """P/E, EPS, price, market cap, shares for `symbol` from dps.psx.com.pk.
    Keyed with yfinance names so it merges into the fundamentals `info`."""
    import asyncio

    base = symbol.upper().replace(".KA", "").strip()
    t = None
    for attempt in range(2):  # dps rate-limits rapid hits — one gentle retry
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=_HEADERS, follow_redirects=True) as c:
                r = await c.get(_URL.format(sym=base))
                r.raise_for_status()
                t = r.text
                break
        except Exception as exc:
            logger.warning("dps fundamentals fetch failed for %s (attempt %d): %s", symbol, attempt + 1, exc)
            await asyncio.sleep(1.5)
    if not t:
        return {}

    pe = _grab_stat(t, r"P/E Ratio")
    price = _grab_stat(t, r">LDCP<")           # last day close (regular market, first hit)
    mcap_k = _grab_stat(t, r"Market Cap")       # in thousands
    shares = _grab_stat(t, r">Shares<")
    # EPS: price / P/E is exact & robust (P/E ≡ price / EPS_TTM). Prefer the
    # precise financials-table value when it agrees within 2x, else use price/PE.
    pe_eps = (price / pe) if (price and pe) else None
    m = re.search(r">EPS<.*?(-?[0-9][0-9,]*\.[0-9]+)", t, re.S)  # require a decimal
    table_eps = _to_float(m.group(1)) if m else None
    if table_eps is not None and pe_eps and 0.5 <= (table_eps / pe_eps) <= 2:
        eps = table_eps
    else:
        eps = pe_eps if pe_eps is not None else table_eps

    out: Dict[str, Any] = {}
    # Accept any positive P/E — near-zero-earnings stocks (holding cos etc.) can
    # legitimately show P/E in the hundreds/thousands (e.g. ENGROH ~2238, KEL ~836).
    # dps shows "N/A" for loss-makers, which simply doesn't parse (correctly None).
    if pe is not None and 0 < pe < 100000:
        out["trailingPE"] = pe
    if eps is not None:
        out["trailingEps"] = eps
    if price is not None and price > 0:
        out["regularMarketPrice"] = price
    if mcap_k is not None and mcap_k > 0:
        out["marketCap"] = mcap_k * 1000.0     # page shows 000's
    if shares is not None and shares > 0:
        out["sharesOutstanding"] = shares

    if out:
        logger.info("dps fundamentals %s: pe=%s eps=%s price=%s", symbol, out.get("trailingPE"), out.get("trailingEps"), out.get("regularMarketPrice"))
    return out
