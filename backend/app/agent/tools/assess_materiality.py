"""
Tool: assess_materiality

Delegates to MaterialityService to match a news item to holdings,
score its materiality, create NewsHoldingLink records, and create Flags.
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.materiality import MaterialityService


async def assess_materiality(
    db: AsyncSession,
    news_item_id: UUID,
) -> Dict[str, Any]:
    """
    Match a news item to all active holdings and create links + flags.
    Delegates entirely to MaterialityService (RULES.md A1.1: no auto-action).
    """
    svc = MaterialityService(db)
    await svc.process_news_item(news_item_id)
    return {"processed": True, "news_item_id": str(news_item_id)}
