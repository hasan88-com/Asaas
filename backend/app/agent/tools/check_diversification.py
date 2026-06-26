"""
Tool: check_diversification

Reads portfolio holdings and returns a concentration analysis by sector and
asset class. No DB writes.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio


async def check_diversification(
    db: AsyncSession,
    portfolio_id: UUID,
) -> Dict[str, Any]:
    """
    Analyse portfolio diversification by sector and asset class.
    Returns concentration metrics; does not write to DB.
    """
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        return {"error": f"Portfolio {portfolio_id} not found."}

    holdings_res = await db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    )
    holdings = holdings_res.scalars().all()

    if not holdings:
        return {"warnings": ["Portfolio has no holdings."], "sector_breakdown": {}, "asset_class_breakdown": {}}

    sector_totals: Dict[str, Decimal] = defaultdict(Decimal)
    asset_class_totals: Dict[str, Decimal] = defaultdict(Decimal)
    holding_details = []

    for h in holdings:
        inst_res = await db.execute(
            select(Instrument).where(Instrument.id == h.instrument_id)
        )
        inst = inst_res.scalar_one()

        weight = Decimal(str(h.target_weight or 0))
        sector = inst.sector or "Unclassified"
        asset_class = inst.asset_class or "unknown"

        sector_totals[sector] += weight
        asset_class_totals[asset_class] += weight
        holding_details.append({
            "symbol": inst.symbol,
            "asset_class": asset_class,
            "sector": sector,
            "weight": str(weight),
        })

    warnings = []
    crypto_weight = asset_class_totals.get("crypto", Decimal("0"))
    if crypto_weight > Decimal("0.15"):
        warnings.append(f"Crypto allocation {crypto_weight:.1%} exceeds the 15% aggressive cap.")
    elif crypto_weight > Decimal("0.10"):
        warnings.append(f"Crypto allocation {crypto_weight:.1%} is elevated — ensure this fits your risk profile.")

    for sector, w in sector_totals.items():
        if w > Decimal("0.40"):
            warnings.append(f"Sector '{sector}' concentration {w:.1%} exceeds 40% — consider reducing.")

    return {
        "sector_breakdown": {k: str(v) for k, v in sector_totals.items()},
        "asset_class_breakdown": {k: str(v) for k, v in asset_class_totals.items()},
        "holdings": holding_details,
        "warnings": warnings,
    }
