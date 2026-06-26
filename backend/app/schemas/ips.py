"""
Asaas (اثاثہ) — IPS & Portfolio Recommendation Schemas
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class IPSResponse(BaseModel):
    id: UUID
    user_id: UUID
    risk_profile_id: UUID
    investment_objective: Optional[str] = None
    time_horizon: Optional[str] = None
    risk_tolerance: Optional[str] = None
    liquidity_profile: Optional[str] = None
    investment_frequency: Optional[str] = None
    initial_capital: Optional[Decimal] = None
    monthly_contribution: Optional[Decimal] = None
    eligible_asset_classes: Optional[List[str]] = None
    investment_restrictions: Optional[List[str]] = None
    recommended_allocation: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PortfolioRecommendationResponse(BaseModel):
    id: UUID
    user_id: UUID
    risk_profile_id: UUID
    risk_score: Optional[int] = None
    investor_persona: Optional[str] = None
    recommended_allocation: Optional[Dict[str, Any]] = None
    expected_return_range: Optional[str] = None
    expected_volatility: Optional[str] = None
    rebalance_frequency: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
