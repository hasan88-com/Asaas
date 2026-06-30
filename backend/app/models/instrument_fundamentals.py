"""
Asaasa — Instrument Fundamentals Cache

Persisted snapshot of yfinance fundamentals (curated `info` fields + the latest
column of each financial statement) per instrument. yfinance rate-limits cloud
IPs (Render gets 429s), so the valuation service reads this DB snapshot when a
live fetch is throttled — turning P/E / EV-EBITDA / P/B / DCF into DB-first reads
with a last-known-good fallback (mirrors how prices already work).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InstrumentFundamentals(Base):
    __tablename__ = "instrument_fundamentals"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    symbol: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {info, income, cashflow, balance}
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
