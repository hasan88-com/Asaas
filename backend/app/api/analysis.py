"""
Asaas (اثاثہ) — Analysis API Router

Read-only endpoints for company info, DCF/Monte Carlo/multiples, and technical indicators.
All endpoints require a valid JWT. No DB writes.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import rsi_thresholds, technical_enabled
from app.core.db import get_db
from app.core.security import get_current_user
from app.models.instrument import Instrument
from app.models.user import User
from app.services.technical import compute_indicators
from app.services.valuation import (
    extract_company_info,
    run_dcf,
    run_fixed_income_valuation,
    run_market_comparison,
    run_monte_carlo,
    run_multiples,
)

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger("asaas.api.analysis")


class ValuationRequest(BaseModel):
    assumptions: Optional[Dict[str, Any]] = None
    peers: Optional[List[str]] = None


@router.get("/company/{symbol}")
async def get_company_info(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Fetch company profile and financial ratios from yfinance.
    Returns missing_fields list for any absent data — never fabricates.
    """
    result = await extract_company_info(symbol, db=db)
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"],
        )
    return result


@router.post("/valuation/{symbol}")
async def get_valuation(
    symbol: str,
    payload: ValuationRequest = ValuationRequest(),
    asset_class: Optional[str] = None,
    face_value: Optional[Decimal] = None,
    coupon_rate: Optional[Decimal] = None,
    buy_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Valuation for the given instrument, with the method chosen by asset class:
      • equity (default)   → DCF + Monte Carlo + multiples
      • tbill / bond       → yield-to-maturity (real coupon from holding params
                              or PSX Debt Market; SBP benchmark fallback)
      • crypto / commodity → market-price comparison
    Returns insufficient_data flags rather than fabricating values.
    All numeric values are Decimal strings — never floats.
    """
    import asyncio

    ac = (asset_class or "").lower()
    empty = {"insufficient_data": True}

    if ac in ("crypto", "commodity"):
        info, comp = await asyncio.gather(
            extract_company_info(symbol),
            run_market_comparison(symbol),
        )
        return {
            "symbol": symbol,
            "method": "market_comparison",
            "company_info": info,
            "market_comparison": comp,
            "dcf": empty,
            "monte_carlo": empty,
            "multiples": {},
        }

    if ac in ("tbill", "bond"):
        fi = await run_fixed_income_valuation(
            symbol,
            face_value=face_value,
            coupon_rate=coupon_rate,
            buy_date=buy_date,
        )
        return {
            "symbol": symbol,
            "method": "yield_to_maturity",
            "company_info": {"name": symbol},
            "fixed_income": fi,
            "dcf": empty,
            "monte_carlo": empty,
            "multiples": {},
        }

    # equity / unknown → DCF-based equity valuation (unchanged behaviour).
    # Pass db so beta is computed vs the PSX composite proxy from price history.
    info, dcf, mc, mult = await asyncio.gather(
        extract_company_info(symbol, db=db),
        run_dcf(symbol, payload.assumptions),
        run_monte_carlo(symbol),
        run_multiples(symbol, payload.peers),
    )

    return {
        "symbol": symbol,
        "method": "dcf",
        "company_info": info,
        "dcf": dcf,
        "monte_carlo": mc,
        "multiples": mult,
    }


@router.get("/technical/{symbol}")
async def get_technical(
    symbol: str,
    asset_class: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Compute RSI, MACD, MFI, SMA/EMA, crossover, support/resistance on daily EOD data.
    Data source: prices DB table → yfinance fallback.

    Class-aware (core.capabilities): technical analysis is refused for
    fixed-income instruments (T-bills/bonds) — they are valued by yield, not
    chart patterns — and crypto uses an 80/20 RSI band instead of 70/30.
    Returns insufficient_data flag if fewer than 30 bars available. No DB writes.
    """
    # Resolve the asset class: explicit query param wins; else look it up.
    ac = asset_class
    if ac is None:
        res = await db.execute(
            select(Instrument.asset_class).where(Instrument.symbol == symbol)
        )
        ac = res.scalar_one_or_none()

    if not technical_enabled(ac):
        return {
            "symbol": symbol,
            "asset_class": ac,
            "disabled": True,
            "reason": (
                "Technical analysis does not apply to fixed-income instruments. "
                "Bonds and T-bills are valued by discounting their contractual "
                "cash flows (yield-to-maturity), not by chart patterns — see the "
                "Valuation tab for the yield analysis."
            ),
        }

    result = await compute_indicators(
        symbol=symbol, db=db, rsi_thresholds=rsi_thresholds(ac)
    )
    if result.get("insufficient_data"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.get("reason", "Insufficient price data."),
        )
    return result
