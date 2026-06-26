"""
Asaas (اثاثہ) — Asset-Class Capability Map (single source of truth)

Declares, per asset class, which analysis methods are valid. Both the backend
dispatch (refuses to compute disabled methods) and the frontend (hides
irrelevant tabs) read from this map — see ``frontend/src/lib/capabilities.ts``,
which must be kept in sync.

Why this exists: methods are NOT interchangeable across classes. Technical
analysis (RSI/MACD/Bollinger) applies to continuously-priced liquid assets
(equity, crypto, commodity) but is meaningless on fixed income (T-bills, bonds,
sukuk), which are valued by discounting contractual cash flows. Crypto needs a
wider RSI band (80/20) because 24/7 high-volatility markets keep momentum
extended longer than equities (70/30).

Phase 1 scope: this map reflects CURRENTLY-implemented methods only. As later
phases land new math (duration/DV01, on-chain NVT/MVRV, DDM, gold/silver ratio),
flip the relevant flags here and add the corresponding panels — nothing else
needs to change, because every consumer reads this map.

Naming: ``Instrument.asset_class`` uses ``psx_stock``/``global_stock``/``crypto``/
``tbill``/``commodity``/``mutual_fund``; the frontend/valuation routing also uses
``equity``/``bond``. Both spellings are accepted here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# RSI overbought/oversold thresholds. Crypto widens to 80/20 (field guide §3).
_RSI_DEFAULT: Dict[str, int] = {"overbought": 70, "oversold": 30}
_RSI_CRYPTO: Dict[str, int] = {"overbought": 80, "oversold": 20}

# Equity capabilities are shared by psx_stock / global_stock / equity alias.
_EQUITY: Dict[str, Any] = {
    "valuation_methods": ["dcf", "multiples"],
    "technical": {"enabled": True, "rsi": _RSI_DEFAULT},
    "risk_panels": [],
    "onchain": False,
    "shariah": "screenable",
    "warnings": [],
}

_CRYPTO: Dict[str, Any] = {
    "valuation_methods": ["market_comparison"],  # no cash flows → no DCF/DDM
    "technical": {"enabled": True, "rsi": _RSI_CRYPTO},
    "risk_panels": [],
    "onchain": False,  # Phase 2: NVT / MVRV / Fear & Greed
    "shariah": "disputed",
    "warnings": [
        "Crypto's legal status in Pakistan is restrictive and there is no "
        "SBP-sanctioned domestic exchange.",
    ],
}

_COMMODITY: Dict[str, Any] = {
    "valuation_methods": ["market_comparison"],  # Phase 2: GSR / mean-reversion
    "technical": {"enabled": True, "rsi": _RSI_DEFAULT},
    "risk_panels": [],
    "onchain": False,
    "shariah": "compliant",
    "warnings": [],
}

# Fixed income: valued by yield, NOT chart patterns → technical disabled.
# Duration/DV01/convexity ride within the YTM valuation response.
_FIXED_INCOME: Dict[str, Any] = {
    "valuation_methods": ["ytm"],
    "technical": {"enabled": False, "rsi": _RSI_DEFAULT},
    "risk_panels": ["duration"],  # Phase 2 adds: credit spread / real yield
    "onchain": False,
    "shariah": "non_compliant",  # except GIS sukuk → compliant (Phase 2 nuance)
    "warnings": [],
}

CAPABILITIES: Dict[str, Dict[str, Any]] = {
    # equity
    "psx_stock": _EQUITY,
    "global_stock": _EQUITY,
    "equity": _EQUITY,
    "mutual_fund": _EQUITY,
    # crypto
    "crypto": _CRYPTO,
    # commodity
    "commodity": _COMMODITY,
    # fixed income
    "tbill": _FIXED_INCOME,
    "bond": _FIXED_INCOME,
}

# Unknown / unseeded classes fall back to equity behaviour so we never silently
# hide a tab (or block a method) for a class we simply forgot to map.
_DEFAULT: Dict[str, Any] = _EQUITY


def get_capabilities(asset_class: Optional[str]) -> Dict[str, Any]:
    """Return the capability record for an asset class (case-insensitive)."""
    if not asset_class:
        return _DEFAULT
    return CAPABILITIES.get(asset_class.strip().lower(), _DEFAULT)


def technical_enabled(asset_class: Optional[str]) -> bool:
    return bool(get_capabilities(asset_class)["technical"]["enabled"])


def rsi_thresholds(asset_class: Optional[str]) -> Dict[str, int]:
    return dict(get_capabilities(asset_class)["technical"]["rsi"])


def valuation_methods(asset_class: Optional[str]) -> List[str]:
    return list(get_capabilities(asset_class)["valuation_methods"])


# Portfolio optimizer methods (services/optimizer.py) + the default per risk
# profile. Registered here so the capability map stays the single source of truth.
OPTIMIZER_METHODS = ("max_sharpe", "min_vol", "risk_parity", "hrp")
PROFILE_OPTIMIZER_METHOD: Dict[str, str] = {
    "conservative": "min_vol",
    "moderately_conservative": "min_vol",
    "moderate": "max_sharpe",
    "aggressive": "max_sharpe",
    "very_aggressive": "risk_parity",
}


# Portfolio risk-analytics metrics (services/risk.py), surfaced at /portfolio/risk.
RISK_METRICS = (
    "var_95", "var_99", "var_95_parametric", "cvar_95",
    "max_drawdown", "max_drawdown_days", "rolling_vol_30",
    "rolling_sharpe_30", "sortino", "beta_vs_kse_proxy",
)


# Per-class historical-price source for the backfill (workers/backfill_prices.py).
# DB-first: technicals/optimizer/risk read the `prices` table; these are how that
# table gets populated. tbill/bond have no OHLCV price series (yields, not prices).
DATA_SOURCES: Dict[str, str] = {
    "psx_stock": "PSX DPS → psx-data-reader → yfinance .KA",
    "global_stock": "yfinance history",
    "crypto": "CoinGecko market_chart (PKR) → yfinance BTC-USD",
    "commodity": "yfinance =F history",
    "index": "yfinance (^KSE)",
    "tbill": "n/a (SBP yields, not a price series)",
    "bond": "n/a (SBP/PSX yields, not a price series)",
}

