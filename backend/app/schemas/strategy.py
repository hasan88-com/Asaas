"""
Asaas (اثاثہ) — Strategy Schemas

Pydantic I/O for the no-code Strategy builder (`Strategy` model).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator

_VALID_KINDS = {"allocation", "screener"}


class StrategyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: str
    config: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        if v not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(_VALID_KINDS)}")
        return v


class StrategyResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StrategyRunResult(BaseModel):
    kind: str
    result: Dict[str, Any]
