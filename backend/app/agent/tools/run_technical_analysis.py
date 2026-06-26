"""Tool: run_technical_analysis — thin wrapper over TechnicalService."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.technical import compute_indicators


async def run_technical_analysis(
    symbol: str,
    db: AsyncSession,
    requested: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute RSI, MACD, MFI, MA, crossover, support/resistance on daily EOD data (read-only)."""
    return await compute_indicators(symbol, db, requested=requested)
