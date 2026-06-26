"""Tool: run_multiples — thin wrapper over ValuationService."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.valuation import run_multiples as _svc_run_multiples


async def run_multiples(
    symbol: str,
    peers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch P/E, EV/EBITDA, P/B for subject vs peers from yfinance (read-only)."""
    return await _svc_run_multiples(symbol, peers or [])
