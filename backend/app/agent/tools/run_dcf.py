"""Tool: run_dcf — thin wrapper over ValuationService."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.valuation import run_dcf as _svc_run_dcf


async def run_dcf(
    symbol: str,
    assumptions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run DCF valuation using SBP policy rate as risk-free leg (read-only)."""
    return await _svc_run_dcf(symbol, assumptions or {})
