"""
Asaasa — PSX sector P/E benchmarks (maintained)

Approximate trailing P/E by sector for the Pakistan Stock Exchange, used as the
"industry average P/E" in the relative-valuation method (fair price = industry
P/E x EPS) when we don't have enough same-sector peers seeded to compute a
median. Keyword-matched so it works whether the stored sector is a PSX label
("Commercial Banks", "Oil & Gas Exploration Companies") or a yfinance/GICS label
("Financial Services", "Energy", "Basic Materials").

These are rough, maintained benchmarks — refresh periodically. They are a
fallback; a peer-median computed from seeded same-sector stocks is preferred.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

# KSE-100 long-run average — used when the sector is unknown/unmatched.
DEFAULT_MARKET_PE = Decimal("7.0")

# (keyword tuple, benchmark P/E). First keyword match wins; order most-specific first.
_SECTOR_PE = [
    (("oil & gas marketing", "oil marketing", "refinery", "refining"), Decimal("6.0")),
    (("oil & gas exploration", "exploration", "e&p", "energy"), Decimal("5.0")),
    (("commercial bank", "bank", "financial"), Decimal("6.0")),
    (("cement", "construction material", "construction and material"), Decimal("8.0")),
    (("fertilizer",), Decimal("7.5")),
    (("chemical",), Decimal("9.0")),
    (("power", "utilit", "electric"), Decimal("4.5")),
    (("technology", "software", "communication", "telecom"), Decimal("13.0")),
    (("automobile", "auto ", "industrials", "engineering"), Decimal("8.0")),
    (("textile",), Decimal("6.0")),
    (("food", "consumer defensive", "consumer staples", "personal care"), Decimal("22.0")),
    (("pharma", "health"), Decimal("14.0")),
    (("insurance",), Decimal("8.0")),
    (("real estate", "reit"), Decimal("10.0")),
    (("tobacco",), Decimal("18.0")),
    (("sugar",), Decimal("6.0")),
    (("paper", "board"), Decimal("8.0")),
    (("glass", "ceramic"), Decimal("9.0")),
    (("leather", "tanneries"), Decimal("7.0")),
    (("investment bank", "securities", "brokerage", "inv. cos"), Decimal("8.0")),
    (("transport", "shipping", "airline", "logistics"), Decimal("8.0")),
    (("conglomerate", "holding"), Decimal("8.0")),
    (("engineering", "steel", "iron"), Decimal("9.0")),
    (("cable", "electrical goods"), Decimal("9.0")),
    (("packaging",), Decimal("8.0")),
    (("synthetic", "rayon"), Decimal("7.0")),
    (("vanaspati",), Decimal("8.0")),
    (("miscellaneous",), Decimal("10.0")),
]


def industry_pe_for_sector(sector: Optional[str]) -> Decimal:
    """Maintained PSX P/E benchmark for a sector string (keyword-matched).
    Returns the market default when sector is missing/unmatched."""
    if not sector:
        return DEFAULT_MARKET_PE
    s = sector.lower()
    for keywords, pe in _SECTOR_PE:
        if any(k in s for k in keywords):
            return pe
    return DEFAULT_MARKET_PE
