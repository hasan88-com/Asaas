"""
Tool: flag_event

Creates a Flag record for a material event against a portfolio.
Returns the flag id, type, and severity.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flag import Flag


async def flag_event(
    db: AsyncSession,
    portfolio_id: UUID,
    event_type: str,
    message: str,
    severity: str,
    news_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """
    Persist a flag for a material event (news / rate_impact / drift).

    event_type: "news" | "rate_impact" | "drift"
    severity:   "high" | "medium"
    news_id:    optional link to the triggering news item
    """
    allowed_types = {"news", "rate_impact", "drift"}
    allowed_severities = {"high", "medium"}

    if event_type not in allowed_types:
        return {"error": f"Invalid event_type '{event_type}'. Must be one of {allowed_types}."}
    if severity not in allowed_severities:
        return {"error": f"Invalid severity '{severity}'. Must be one of {allowed_severities}."}

    flag = Flag(
        portfolio_id=portfolio_id,
        news_id=news_id,
        type=event_type,
        severity=severity,
        message=message,
        status="pending",
    )
    db.add(flag)
    await db.commit()
    await db.refresh(flag)

    return {
        "flag_id": str(flag.id),
        "type": flag.type,
        "severity": flag.severity,
        "status": flag.status,
    }
