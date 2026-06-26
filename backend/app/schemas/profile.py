"""
Asaas (اثاثہ) — Risk Profile Schemas

Pydantic schemas for risk profile endpoints.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileBase(BaseModel):
    goal: str = Field(..., description="preservation / income / growth")
    horizon: str = Field(..., description="short / medium / long")
    risk_tolerance: str = Field(..., description="conservative / moderate / aggressive / very_aggressive / moderately_conservative")
    investor_mode: str = Field(..., description="capital_preservation / balanced / long_term / maximum_growth")
    initial_capital: Decimal = Field(..., gt=0, description="Investable capital in PKR")
    monthly_contribution: Optional[Decimal] = Field(default=None, ge=0)
    investment_frequency: Optional[str] = None
    risk_willingness: Optional[str] = None
    loss_tolerance: Optional[str] = None
    experience: Optional[str] = None
    investment_preferences: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    goal: Optional[str] = None
    horizon: Optional[str] = None
    risk_tolerance: Optional[str] = None
    investor_mode: Optional[str] = None
    initial_capital: Optional[Decimal] = Field(None, gt=0)
    monthly_contribution: Optional[Decimal] = Field(None, ge=0)
    investment_frequency: Optional[str] = None
    risk_willingness: Optional[str] = None
    loss_tolerance: Optional[str] = None
    experience: Optional[str] = None
    investment_preferences: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    investor_persona: Optional[str] = None
    risk_score: Optional[int] = None
    agent_remarks: Optional[Dict[str, Any]] = None
    recommendations: Optional[Dict[str, Any]] = None


class ProfileResponse(ProfileBase):
    id: UUID
    user_id: UUID
    risk_score: Optional[int] = None
    investor_persona: Optional[str] = None
    agent_remarks: Optional[Dict[str, Any]] = None
    recommendations: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
