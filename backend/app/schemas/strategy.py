"""
Asaas (اثاثہ) — Strategy Schemas

Pydantic schemas for the no-code Strategies feature.

config shapes (validated lightly here, fully interpreted by the router):
  • allocation: {risk_tolerance, horizon?, method?,
                 constraints?: {excluded_sectors?: [...], excluded_asset_classes?: [...]}}
  • screener:   {logic?: "AND", conditions: [{field, op, value}, ...]}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

StrategyKind = Literal["allocation", "screener"]

# Optimizer methods the allocation builder may request (mirror OPTIMIZER_METHODS).
_ALLOWED_METHODS = {"max_sharpe", "min_vol", "risk_parity", "hrp"}
# Fields/operators a screener condition may use.
_SCREENER_FIELDS = {"sector", "asset_class", "price"}
_SCREENER_OPS = {"eq", "neq", "in", "gt", "gte", "lt", "lte"}


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: StrategyKind
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _validate_config(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        kind = info.data.get("kind")
        if kind == "allocation":
            method = v.get("method")
            if method is not None and method not in _ALLOWED_METHODS:
                raise ValueError(f"method must be one of {sorted(_ALLOWED_METHODS)}")
        elif kind == "screener":
            conditions = v.get("conditions")
            if not isinstance(conditions, list) or not conditions:
                raise ValueError("screener config requires a non-empty 'conditions' list")
            for c in conditions:
                if not isinstance(c, dict):
                    raise ValueError("each condition must be an object")
                if c.get("field") not in _SCREENER_FIELDS:
                    raise ValueError(f"condition.field must be one of {sorted(_SCREENER_FIELDS)}")
                if c.get("op") not in _SCREENER_OPS:
                    raise ValueError(f"condition.op must be one of {sorted(_SCREENER_OPS)}")
                if "value" not in c:
                    raise ValueError("condition.value is required")
        return v


class StrategyResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    kind: StrategyKind
    config: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScreenerMatch(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    asset_class: Optional[str] = None
    current_price: Optional[str] = None


class StrategyRunResult(BaseModel):
    kind: StrategyKind
    # allocation → the draft-portfolio result from suggest_portfolio
    allocation: Optional[Dict[str, Any]] = None
    # screener → matching instruments
    matches: Optional[List[ScreenerMatch]] = None
    count: Optional[int] = None
    error: Optional[str] = None
