"""Tool: extract_company_info — thin wrapper over ValuationService."""

from __future__ import annotations

from typing import Any, Dict

from app.services.valuation import extract_company_info as _svc_extract


async def extract_company_info(symbol: str) -> Dict[str, Any]:
    """Fetch company profile, ratios, and financials from yfinance (read-only)."""
    return await _svc_extract(symbol)
