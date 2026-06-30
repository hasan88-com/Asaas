"""
Asaasa — FX Search Adapter (DuckDuckGo)

Last-resort USD/PKR rate source: queries DuckDuckGo's currency "spice" endpoint
(no API key) when the primary yfinance source and cache are unavailable. Parses
the converted amount for 1 USD → PKR. Returns None on any failure — never
fabricates a rate.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx

logger = logging.getLogger("asaas.fx_search_adapter")

# DuckDuckGo currency conversion endpoint → JSONP: ddg_spice_currency({...})
_DDG_CURRENCY = "https://duckduckgo.com/js/spice/currency/1/{base}/{quote}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AsaasaBot/1.0)"}
# Sanity band for USD/PKR so we never accept a garbage parse.
_MIN_RATE = Decimal("150")
_MAX_RATE = Decimal("700")


async def fetch_usd_pkr_via_search(base: str = "USD", quote: str = "PKR") -> Optional[Decimal]:
    """Return the 1-unit `base`→`quote` rate from DuckDuckGo, or None."""
    url = _DDG_CURRENCY.format(base=base, quote=quote)
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception as exc:
        logger.warning("DuckDuckGo FX fetch failed: %s", exc)
        return None

    rate = _parse_rate(text)
    if rate is None:
        logger.warning("DuckDuckGo FX parse failed (no rate found).")
        return None
    if not (_MIN_RATE <= rate <= _MAX_RATE):
        logger.warning("DuckDuckGo FX rate %s outside sane band — rejecting.", rate)
        return None
    logger.info("Fetched USD/PKR via DuckDuckGo search: %s", rate)
    return rate


def _parse_rate(text: str) -> Optional[Decimal]:
    """Pull the converted amount out of the JSONP payload."""
    # Strip the `ddg_spice_currency(` … `);` callback wrapper, then JSON-parse.
    m = re.search(r"\(\s*(\{.*\})\s*\)\s*;?\s*$", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            conv = data.get("conversion") or {}
            amt = conv.get("converted-amount")
            if amt is not None:
                return _to_decimal(amt)
            to = data.get("to") or []
            if to and isinstance(to, list):
                return _to_decimal(to[0].get("mid") or to[0].get("price"))
        except (ValueError, TypeError, KeyError, IndexError):
            pass
    # Fallback: regex the converted-amount field directly.
    m2 = re.search(r'"converted-amount"\s*:\s*"?([\d.,]+)"?', text)
    if m2:
        return _to_decimal(m2.group(1))
    return None


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
