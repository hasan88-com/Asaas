"""Tool: run_monte_carlo — thin wrapper over ValuationService."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.valuation import run_monte_carlo as _svc_run_monte_carlo


async def run_monte_carlo(
    symbol: str,
    ranges: Optional[Dict[str, Any]] = None,
    n: int = 1000,
) -> Dict[str, Any]:
    """Run Monte Carlo DCF simulation; returns p10/p50/p90 fair-value distribution (read-only)."""
    return await _svc_run_monte_carlo(symbol, ranges or {}, n)
