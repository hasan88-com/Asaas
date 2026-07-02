"""
Asaas (اثاثہ) — Watchlist Schemas

Pydantic I/O for the per-user instrument watchlist (`WatchlistItem` model).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32,
                        description="Instrument symbol, e.g. HBL.KA / BTC / GC=F / MTB-12M")
    asset_class: Optional[str] = Field(
        None, description="Picker hint (crypto/commodity/tbill/bond) to register unseeded symbols"
    )
    name: Optional[str] = Field(None, max_length=120, description="Display name for on-demand registration")


class WatchlistItemResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    asset_class: str
    sector: Optional[str] = None
    currency: str
    price: Optional[Decimal] = None  # native quote currency (PKR for PSX, USD for crypto/commodity)
    created_at: datetime


class WatchlistResponse(BaseModel):
    items: List[WatchlistItemResponse]
