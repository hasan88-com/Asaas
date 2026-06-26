"""
Asaas (اثاثہ) — News and Flag Schemas

Pydantic schemas for news feed and material flags (TECH.md §7.2, §4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NewsHoldingLinkResponse(BaseModel):
    news_id: UUID
    instrument_id: UUID
    relevance: Decimal

    class Config:
        from_attributes = True


class NewsItemResponse(BaseModel):
    id: UUID
    source: str = Field(..., description="psx / sbp / business_recorder / dawn")
    headline: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    impact_level: Optional[str] = Field(None, description="direct / sector / macro")
    impact: Optional[str] = Field(None, description="positive / negative / neutral")
    affected_symbols: Optional[List[str]] = Field(default_factory=list)
    materiality_score: Optional[float] = None
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class FlagResponse(BaseModel):
    id: UUID
    portfolio_id: UUID
    news_id: Optional[UUID] = None
    type: str = Field(..., description="news / rate_impact / drift")
    severity: str = Field(..., description="high / medium")
    message: str
    status: str = Field(..., description="pending / acknowledged / actioned")
    created_at: datetime
    resolved_at: Optional[datetime] = None
    news_item: Optional[NewsItemResponse] = None

    class Config:
        from_attributes = True
