"""
Tool: analyze_rate_impact

Delegates to RateImpactService to reprice T-bill holdings and create flags
when the SBP policy rate changes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rate_impact import RateImpactService


async def analyze_rate_impact(
    db: AsyncSession,
    old_rate: Decimal,
    new_rate: Decimal,
) -> Dict[str, Any]:
    """
    Apply a SBP policy rate change: reprice T-bills and flag exposed portfolios.
    Returns abstracted summary (delta in bps, severity).
    """
    delta = new_rate - old_rate
    delta_bps = int(delta * 1000)  # basis points (0.01 = 100 bps × 10?)
    # Standard: 1% = 100 bps
    delta_bps_std = int(delta * 100)

    svc = RateImpactService(db)
    await svc.apply_policy_rate_change(old_rate, new_rate)

    severity = "high" if abs(delta) >= Decimal("0.01") else "medium"

    return {
        "old_rate": str(old_rate),
        "new_rate": str(new_rate),
        "delta_bps": delta_bps_std,
        "severity": severity,
        "direction": "hike" if delta > 0 else "cut",
    }
