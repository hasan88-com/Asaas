"""
Tool: reoptimize

Creates a new DRAFT portfolio by re-running the optimizer against current prices.
The existing confirmed portfolio is NEVER touched (RULES.md A1.1).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Portfolio
from app.agent.tools.suggest_portfolio import suggest_portfolio

logger = logging.getLogger("asaas.agent.tools.reoptimize")


async def reoptimize(
    db: AsyncSession,
    user_id: UUID,
    portfolio_id: Optional[UUID] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Re-run the portfolio optimizer and return a new DRAFT.

    The currently confirmed portfolio (portfolio_id) is NEVER mutated.
    The new draft is a separate DB record that the user must confirm separately.
    Pending flags for the confirmed portfolio are preserved.
    """
    # Verify the confirmed portfolio belongs to this user (ownership check)
    if portfolio_id:
        res = await db.execute(
            select(Portfolio).where(Portfolio.id == portfolio_id)
        )
        existing = res.scalar_one_or_none()
        if not existing:
            return {"error": f"Portfolio {portfolio_id} not found."}
        if str(existing.user_id) != str(user_id):
            return {"error": "Unauthorised: portfolio does not belong to this user."}
        if existing.status not in ("confirmed", "tracked"):
            return {"error": "Referenced portfolio is not in confirmed or tracked status."}

    # Delegate to suggest_portfolio (always creates a new draft)
    result = await suggest_portfolio(db=db, user_id=user_id, overrides=overrides)
    if "error" in result:
        return result

    result["reoptimised"] = True
    result["source_portfolio_id"] = str(portfolio_id) if portfolio_id else None
    return result
