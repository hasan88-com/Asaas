"""
Asaas (اثاثہ) — Market Schemas

Pydantic schemas for instruments, prices, and search results (TECH.md §7.2, §4).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InstrumentBase(BaseModel):
    symbol: str = Field(..., description="e.g. HBL.KA, BTC, GC=F, TBILL-3M")
    name: Optional[str] = None
    asset_class: str = Field(..., description="psx_stock / global_stock / crypto / tbill / commodity / mutual_fund")
    sector: Optional[str] = None
    currency: str = "PKR"
    data_source: Optional[str] = None
    metadata_: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="metadata")
    is_active: bool = True


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentResponse(InstrumentBase):
    id: UUID

    class Config:
        from_attributes = True
        populate_by_name = True


class SearchResult(BaseModel):
    id: UUID
    symbol: str
    name: Optional[str] = None
    asset_class: str
    sector: Optional[str] = None
    currency: str
    is_active: bool

    class Config:
        from_attributes = True


class PriceResponse(BaseModel):
    symbol: str
    price: Decimal
    price_date: date
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    volume: Optional[int] = None
    source: Optional[str] = None
    fetched_at: datetime

    class Config:
        from_attributes = True
