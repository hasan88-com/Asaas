"""
Tool: track_value

Recalculates portfolio value and writes a daily snapshot.
Returns pnl_percent and status only — no absolute PKR amounts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.models.snapshot import PortfolioSnapshot
from app.services.performance import PerformanceService


async def track_value(
    db: AsyncSession,
    portfolio_id: UUID,
) -> Dict[str, Any]:
    """
    Update portfolio metrics and write today's snapshot.
    Returns relative performance only (RULES.md A1.2: no absolute PKR).
    """
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        return {"error": f"Portfolio {portfolio_id} not found."}

    svc = PerformanceService(db)
    total_value, pnl_abs, pnl_pct = await svc.update_portfolio_metrics(portfolio_id)

    today = datetime.now(timezone.utc).date()

    # Upsert today's snapshot (unique constraint: portfolio_id + snapshot_date)
    snap_res = await db.execute(
        select(PortfolioSnapshot).where(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date == today,
        )
    )
    snapshot = snap_res.scalar_one_or_none()

    if snapshot:
        snapshot.total_value_pkr = total_value
        snapshot.pnl_absolute = pnl_abs
        snapshot.pnl_percent = pnl_pct
    else:
        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio_id,
            snapshot_date=today,
            total_value_pkr=total_value,
            pnl_absolute=pnl_abs,
            pnl_percent=pnl_pct,
        )
        db.add(snapshot)

    await db.commit()

    # Return relative metrics only — no absolute total_value_pkr
    return {
        "portfolio_id": str(portfolio_id),
        "pnl_percent": str(pnl_pct),
        "pnl_direction": "gain" if pnl_pct >= Decimal("0") else "loss",
        "snapshot_date": today.isoformat(),
    }
