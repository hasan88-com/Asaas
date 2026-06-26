"""
Asaas (اثاثہ) — Portfolio Schemas

Pydantic schemas for portfolio and holding operations (TECH.md §7.2, §4).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# --- Holdings ---

class HoldingBase(BaseModel):
    instrument_id: UUID
    target_weight: Optional[Decimal] = Field(None, ge=0, le=1)
    actual_weight: Optional[Decimal] = Field(None, ge=0, le=1)
    quantity: Optional[Decimal] = Field(None, ge=0)
    entry_price: Optional[Decimal] = Field(None, ge=0)
    entry_date: Optional[date] = None


class HoldingCreate(HoldingBase):
    pass


class HoldingResponse(HoldingBase):
    id: UUID
    portfolio_id: UUID
    symbol: Optional[str] = None
    name: Optional[str] = None
    asset_class: Optional[str] = None

    class Config:
        from_attributes = True


# --- Portfolios ---

class PortfolioBase(BaseModel):
    name: Optional[str] = None
    status: str = Field("draft", description="draft / confirmed / tracked")
    expected_return: Optional[Decimal] = None
    expected_risk: Optional[Decimal] = None
    sharpe: Optional[Decimal] = None
    risk_free_rate: Optional[Decimal] = None
    rationale: Optional[str] = None


class PortfolioResponse(PortfolioBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    holdings: List[HoldingResponse] = []
    concentration_warning: Optional[str] = None
    has_existing_holdings: Optional[bool] = None

    class Config:
        from_attributes = True


# --- Request/Response Payloads ---

class SuggestRequest(BaseModel):
    """Optional overrides for risk profile or constraints when suggesting a portfolio."""
    risk_tolerance: Optional[str] = None
    horizon: Optional[str] = None
    investor_mode: Optional[str] = None
    initial_capital: Optional[Decimal] = Field(None, gt=0)
    goal: Optional[str] = None
    constraints: Optional[Dict[str, Any]] = None


class ConfirmHoldingInput(BaseModel):
    instrument_id: UUID
    actual_weight: Decimal = Field(..., ge=0, le=1)
    quantity: Decimal = Field(..., ge=0)
    entry_price: Decimal = Field(..., ge=0)
    entry_date: Optional[date] = None


class ConfirmRequest(BaseModel):
    holdings: List[ConfirmHoldingInput] = Field(default_factory=list, description="Confirmed holdings list to lock in portfolio")


# --- User portfolio activity (buy / sell / update) ---

class AddHoldingRequest(BaseModel):
    """'I bought' — add a holding to the confirmed portfolio (by symbol)."""
    symbol: str = Field(..., description="Instrument symbol, e.g. HBL.KA / BTC / MTB-12M")
    quantity: Decimal = Field(..., gt=0)
    entry_price: Decimal = Field(..., ge=0, description="Price paid (PKR)")
    entry_date: Optional[date] = None


class SellHoldingRequest(BaseModel):
    """'I sold' — reduce or remove an existing holding."""
    holding_id: UUID
    quantity: Decimal = Field(..., gt=0, description="Quantity sold")
    price: Decimal = Field(..., ge=0, description="Price received (PKR)")
    date: Optional[date] = None


class UpdateHoldingRequest(BaseModel):
    """'Update price' — set a new entry price on an existing holding."""
    entry_price: Decimal = Field(..., ge=0)


# --- Guest Mode ---

class GuestHoldingInput(BaseModel):
    symbol: str = Field(..., description="e.g. HBL.KA, BTC, GC=F")
    qty: Decimal = Field(..., gt=0)
    entry_price: Decimal = Field(..., gt=0, description="Always in PKR")
    asset_class: Literal['equity', 'tbill', 'bond', 'crypto', 'commodity']
    interest_rate_at_buy: Optional[Decimal] = None
    buy_date: Optional[date] = None

    @field_validator('interest_rate_at_buy')
    @classmethod
    def validate_rate(cls, v: Decimal) -> Decimal:
        if not (Decimal('0') <= v <= Decimal('100')):
            raise ValueError('interest_rate_at_buy must be between 0 and 100')
        return v


class GuestAnalyzeRequest(BaseModel):
    holdings: List[GuestHoldingInput] = Field(..., description="Current user holdings to analyze")
    risk_tolerance: str = Field("moderate", description="conservative / moderate / aggressive")
    horizon: str = Field("medium", description="short / medium / long")
    goal: str = Field("growth", description="growth / income / preservation")
    constraints: Optional[Dict[str, Any]] = None


class GuestAnalyzeResponse(BaseModel):
    current_metrics: Dict[str, Any] = Field(..., description="Current portfolio metrics")
    suggested_portfolio: PortfolioResponse = Field(..., description="Suggested optimized portfolio")
    rationale: str = Field(..., description="Explanation of why this is better")
    rebalance_actions: List[str] = Field(..., description="Plain-language rebalancing steps")
