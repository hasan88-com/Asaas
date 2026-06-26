"""
Asaas (اثاثہ) — Questionnaire Schemas

Request/response models for the lean 8-question onboarding flow.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    value: str
    label: str


class QuestionDefinition(BaseModel):
    id: str
    question: str
    category: str = "general"
    multiple: bool = False
    options: List[QuestionOption]
    conditional_on: Optional[Dict[str, str]] = None


class QuestionnaireAnswer(BaseModel):
    question_id: str
    answer: Union[str, List[str], int, float]


class QuestionnaireRequest(BaseModel):
    """POST /profile/questionnaire"""
    answers: List[QuestionnaireAnswer]
    initial_capital: Decimal = Field(..., gt=0, description="Investable capital in PKR")
    monthly_contribution: Decimal = Field(default=Decimal("0"), ge=0, description="Monthly top-up in PKR")
    investment_frequency: str = Field(default="one_time", description="one_time/monthly/quarterly/annually")
    investment_preferences: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Asset class selections from the optional preferences screen",
    )


class QuestionnaireResponse(BaseModel):
    """Returned after evaluation — lean profile for the frontend onboarding flow."""
    profile_id: UUID
    risk_score: int
    investor_persona: str
    risk_tolerance: str
    horizon: str
    investor_mode: str
    goal: str
    constraints: Dict[str, Any]
    investment_preferences: Optional[Dict[str, Any]] = None
    monthly_contribution: Optional[Decimal] = None
    investment_frequency: Optional[str] = None
    agent_remarks: Optional[Dict[str, Any]] = None
    recommendations: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class DeclareHoldingInput(BaseModel):
    """One existing position the user already owns."""
    instrument_id: UUID
    quantity: Decimal = Field(..., gt=0)
    entry_price: Decimal = Field(..., gt=0, description="Actual buy price in PKR (NUMERIC)")
    entry_date: str | None = None


class DeclareHoldingsRequest(BaseModel):
    """POST /portfolio/declare-holdings"""
    holdings: List[DeclareHoldingInput] = Field(
        ..., min_length=1, description="Existing positions the user already holds"
    )
