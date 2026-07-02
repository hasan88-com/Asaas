"""
Asaas (اثاثہ) — Wallet Schemas

Pydantic I/O for the virtual PKR cash wallet (`CashAccount` / `CashTransaction`).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

MAX_MOVEMENT_PKR = Decimal("1000000000")  # ₨1B per transaction, well inside Numeric(18,2)


class CashMovementRequest(BaseModel):
    amount: Decimal = Field(..., gt=0, le=MAX_MOVEMENT_PKR, description="Amount in PKR")
    note: Optional[str] = Field(None, max_length=280)

    @field_validator("amount")
    @classmethod
    def _quantize_2dp(cls, v: Decimal) -> Decimal:
        return v.quantize(Decimal("0.01"))


class WalletResponse(BaseModel):
    balance: Decimal
    currency: str
    created_at: datetime

    class Config:
        from_attributes = True


class CashTransactionResponse(BaseModel):
    id: uuid.UUID
    type: str
    amount: Decimal
    balance_after: Decimal
    symbol: Optional[str] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    status: str
    note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    items: List[CashTransactionResponse]
    total: int
