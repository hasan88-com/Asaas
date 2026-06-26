"""
Tool: confirm_holdings

The sole code path that transitions a portfolio from "draft" to "confirmed".
Writes confirmed holdings and creates the initial performance snapshot.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.snapshot import PortfolioSnapshot
from app.services.performance import PerformanceService


async def confirm_holdings(
    db: AsyncSession,
    portfolio_id: UUID,
    user_id: UUID,
    confirmations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Confirm a draft portfolio.

    confirmations: list of dicts with keys:
      instrument_id (str/UUID), actual_weight (str/Decimal),
      quantity (str/Decimal, optional), entry_price (str/Decimal, optional),
      entry_date (date string, optional)

    Ownership check: portfolio.user_id must match user_id.
    Status must be "draft" — this is the ONLY path to "confirmed".
    """
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = result.scalar_one_or_none()

    if not portfolio:
        return {"error": "Draft portfolio not found."}
    if str(portfolio.user_id) != str(user_id):
        return {"error": "Unauthorised: portfolio does not belong to this user."}
    if portfolio.status != "draft":
        return {"error": f"Portfolio is already '{portfolio.status}', not 'draft'."}

    # Clear existing draft holdings
    await db.execute(
        delete(Holding).where(Holding.portfolio_id == portfolio_id)
    )

    # Insert confirmed holdings
    today = datetime.now(timezone.utc).date()
    for item in confirmations:
        instrument_id = UUID(str(item["instrument_id"]))
        actual_weight = Decimal(str(item.get("actual_weight", "0")))
        quantity = Decimal(str(item["quantity"])) if item.get("quantity") else None
        entry_price = Decimal(str(item["entry_price"])) if item.get("entry_price") else None
        entry_date = item.get("entry_date") or today
        if isinstance(entry_date, str):
            try:
                entry_date = date.fromisoformat(entry_date)
            except ValueError:
                entry_date = today

        holding = Holding(
            portfolio_id=portfolio_id,
            instrument_id=instrument_id,
            target_weight=actual_weight,
            actual_weight=actual_weight,
            quantity=quantity,
            entry_price=entry_price,
            entry_date=entry_date,
        )
        db.add(holding)

    portfolio.status = "confirmed"
    portfolio.confirmed_at = datetime.now(timezone.utc)
    await db.flush()

    # Write initial snapshot
    svc = PerformanceService(db)
    total_value, pnl_abs, pnl_pct = await svc.update_portfolio_metrics(portfolio_id)

    snap_res = await db.execute(
        select(PortfolioSnapshot).where(
            PortfolioSnapshot.portfolio_id == portfolio_id,
            PortfolioSnapshot.snapshot_date == today,
        )
    )
    existing_snap = snap_res.scalar_one_or_none()
    if not existing_snap:
        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio_id,
            snapshot_date=today,
            total_value_pkr=total_value,
            pnl_absolute=pnl_abs,
            pnl_percent=pnl_pct,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(portfolio)

    return {
        "portfolio_id": str(portfolio.id),
        "status": portfolio.status,
        "confirmed_at": portfolio.confirmed_at.isoformat(),
        "holdings_count": len(confirmations),
    }
