"""
Asaas (اثاثہ) — News and Flags API Router

Endpoints for fetching personalized news feeds and managing material event flags.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.response_cache import (
    NEWS_FEED_KEY, flags_key, get_cached, invalidate, set_cached,
)
from app.core.security import get_current_user
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.news import NewsHoldingLink, NewsItem
from app.models.market_sentiment import MarketSentimentSnapshot
from app.models.user import User
from app.models.flag import Flag
from app.models.portfolio import Portfolio
from app.schemas.news import FlagResponse, NewsItemResponse

logger = logging.getLogger("asaas.api.news")
router = APIRouter(tags=["news"])

MOCK_NEWS = [
    {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "headline": "SBP keeps policy rate unchanged at 11% — supports equity rally and bond valuations",
        "source": "SBP / Dawn",
        "url": "https://www.sbp.org.pk",
        "impact": "positive",
        "impact_level": "macro",
        "affected_symbols": [],
        "materiality_score": 0.8,
        "summary": "State Bank of Pakistan maintained the policy rate at 11%, signalling confidence in the inflation trajectory and supporting the ongoing equity market rally.",
    },
    {
        "id": UUID("00000000-0000-0000-0000-000000000002"),
        "headline": "PSX100 crosses 120,000 — banking and oil sectors lead gains",
        "source": "PSX / Business Recorder",
        "url": "https://www.psx.com.pk",
        "impact": "positive",
        "impact_level": "sector",
        "affected_symbols": ["HBL", "UBL", "OGDC"],
        "materiality_score": 0.7,
        "summary": "Karachi stock exchange hits new all-time high as banking sector reports record profits and oil prices remain firm.",
    },
    {
        "id": UUID("00000000-0000-0000-0000-000000000003"),
        "headline": "Pakistan T-bill yields drop to 10.8% as inflation expectations ease",
        "source": "SBP / Profit",
        "url": "https://www.sbp.org.pk",
        "impact": "neutral",
        "impact_level": "direct",
        "affected_symbols": [],
        "materiality_score": 0.5,
        "summary": "Latest T-bill auction saw yields decline across all tenors as market prices in further disinflation.",
    },
    {
        "id": UUID("00000000-0000-0000-0000-000000000004"),
        "headline": "Gold hits record $2,450/oz globally — Pakistan gold price crosses ₨240,000/tola",
        "source": "Reuters / Jewellers Assoc",
        "url": "https://www.reuters.com",
        "impact": "positive",
        "impact_level": "sector",
        "affected_symbols": [],
        "materiality_score": 0.6,
        "summary": "Global gold surge driven by geopolitical tensions and central bank buying. Pakistan gold prices hit all-time high.",
    },
    {
        "id": UUID("00000000-0000-0000-0000-000000000005"),
        "headline": "Bitcoin ETF inflows hit $1B this week — crypto market caps surpass $3T",
        "source": "CoinDesk / Bloomberg",
        "url": "https://www.coindesk.com",
        "impact": "positive",
        "impact_level": "macro",
        "affected_symbols": ["BTC", "ETH"],
        "materiality_score": 0.4,
        "summary": "Institutional crypto demand surges as US Bitcoin ETFs see record weekly inflows.",
    },
    {
        "id": UUID("00000000-0000-0000-0000-000000000006"),
        "headline": "Pakistan IMF review on track — $1.1B tranche expected by month end",
        "source": "The News / Geo",
        "url": "https://www.thenews.com.pk",
        "impact": "positive",
        "impact_level": "macro",
        "affected_symbols": [],
        "materiality_score": 0.9,
        "summary": "IMF confirms Pakistan meeting all structural benchmarks. Foreign reserves expected to cross $10B after tranche disbursement.",
    },
]


@router.get("/news/feed", response_model=List[NewsItemResponse])
async def get_news_feed(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch personalized news feed matched to holdings in user's portfolio.
    Returns Pakistan-focused market news with impact analysis.
    """
    cached = await get_cached(NEWS_FEED_KEY)
    if cached is not None:
        return JSONResponse(content=cached)

    # Recent window so stale items drop off automatically; fall back to the
    # latest 20 regardless of date if too few recent items exist (never empty).
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    result = await db.execute(
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(NewsItem.published_at.desc())
        .limit(50)
    )
    db_items = result.scalars().all()

    if len(db_items) < 5:
        result = await db.execute(
            select(NewsItem).order_by(NewsItem.published_at.desc()).limit(20)
        )
        db_items = result.scalars().all()

    if db_items:
        news_items = []
        for item in db_items:
            link_result = await db.execute(
                select(Instrument.symbol)
                .join(NewsHoldingLink, NewsHoldingLink.instrument_id == Instrument.id)
                .where(NewsHoldingLink.news_id == item.id)
            )
            affected = [row[0] for row in link_result.all()]

            news_items.append(NewsItemResponse(
                id=item.id,
                source=item.source,
                headline=item.headline,
                url=item.url,
                published_at=item.published_at,
                impact_level=item.level or "macro",
                impact=item.sentiment or "neutral",
                affected_symbols=affected,
                materiality_score=float(item.materiality_score) if item.materiality_score else None,
                summary=item.summary,
            ))
        payload = jsonable_encoder(news_items)
        await set_cached(NEWS_FEED_KEY, payload, 60)  # feed changes slowly
        return JSONResponse(content=payload)

    now = datetime.now(timezone.utc)
    return [
        NewsItemResponse(
            id=m["id"],
            headline=m["headline"],
            source=m["source"],
            url=m["url"],
            published_at=now,
            impact=m["impact"],
            impact_level=m["impact_level"],
            affected_symbols=m["affected_symbols"],
            materiality_score=m["materiality_score"],
            summary=m["summary"],
        )
        for m in MOCK_NEWS
    ]


@router.post("/news/scrape")
async def trigger_news_scrape(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a news scrape. Runs async, returns immediately.

    Dedupes concurrent triggers: if a scrape is already running, returns
    'in_progress' instead of kicking off a second parallel job.
    """
    import json as _json
    from app.core.redis import redis_client
    from app.workers.news_monitor import SCRAPE_STATUS_KEY, run_news_monitor

    try:
        raw = await redis_client.get(SCRAPE_STATUS_KEY)
        if raw and _json.loads(raw).get("state") == "running":
            return {"status": "in_progress"}
    except Exception:
        pass

    async def _safe_scrape():
        try:
            await run_news_monitor()
            await invalidate(NEWS_FEED_KEY, "market_sentiment")  # surface fresh items + sentiment
        except Exception as exc:
            logger.error("Manual scrape failed: %s", exc)

    asyncio.create_task(_safe_scrape())
    return {"status": "scrape triggered"}


@router.get("/news/scrape/status")
async def get_scrape_status(
    current_user: User = Depends(get_current_user),
):
    """Current scrape progress so the frontend can poll instead of blind-waiting.

    Returns {state, sources_total, sources_done, started_at, ingested}; state is
    'idle' when nothing has run (or the status key expired).
    """
    import json as _json
    from app.core.redis import redis_client
    from app.workers.news_monitor import SCRAPE_STATUS_KEY

    try:
        raw = await redis_client.get(SCRAPE_STATUS_KEY)
        if raw:
            return _json.loads(raw)
    except Exception:
        pass
    return {"state": "idle"}


@router.get("/news/sentiment")
async def get_market_sentiment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Latest market-sentiment snapshot (overall + per sector + per asset class).

    Reads precomputed rows (Stage 4) — additive signal only, never portfolio math.
    """
    cached = await get_cached("market_sentiment")
    if cached is not None:
        return JSONResponse(content=cached)

    # Latest snapshot date present, then all rows for it.
    latest_date = await db.scalar(select(func.max(MarketSentimentSnapshot.snapshot_date)))
    if latest_date is None:
        return JSONResponse(content={"as_of": None, "market": None, "sectors": [], "asset_classes": []})

    rows = (await db.execute(
        select(MarketSentimentSnapshot).where(MarketSentimentSnapshot.snapshot_date == latest_date)
    )).scalars().all()

    def _row(r: MarketSentimentSnapshot) -> dict:
        return {
            "scope": r.scope, "label": r.label, "score": float(r.score),
            "item_count": r.item_count, "bullish_count": r.bullish_count,
            "bearish_count": r.bearish_count,
        }

    market = next((_row(r) for r in rows if r.scope == "market"), None)
    payload = {
        "as_of": str(latest_date),
        "market": market,
        "sectors": [_row(r) for r in rows if r.scope == "sector"],
        "asset_classes": [_row(r) for r in rows if r.scope == "asset_class"],
    }
    await set_cached("market_sentiment", payload, 120)
    return JSONResponse(content=payload)


@router.get("/flags", response_model=List[FlagResponse])
async def get_flags(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all pending material-event flags for the user's active portfolio."""
    port_result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.id, Portfolio.status != "draft")
        .order_by(Portfolio.confirmed_at.desc())
    )
    portfolio = port_result.scalars().first()

    if not portfolio:
        return JSONResponse(content=[])

    key = flags_key(current_user.id)
    cached = await get_cached(key)
    if cached is not None:
        return JSONResponse(content=cached)

    flag_result = await db.execute(
        select(Flag)
        .where(Flag.portfolio_id == portfolio.id, Flag.status == "pending")
        .order_by(Flag.created_at.desc())
    )
    flags = flag_result.scalars().all()
    payload = jsonable_encoder([FlagResponse.model_validate(f) for f in flags])
    await set_cached(key, payload, 30)
    return JSONResponse(content=payload)


@router.post("/flags/{id}/dismiss", response_model=FlagResponse)
async def dismiss_flag(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a pending flag (RULES.md C1.5 check user ownership)."""
    result = await db.execute(
        select(Flag)
        .join(Portfolio, Flag.portfolio_id == Portfolio.id)
        .where(Flag.id == id, Portfolio.user_id == current_user.id)
    )
    flag = result.scalar_one_or_none()

    if not flag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Flag not found or access denied.",
        )

    flag.status = "acknowledged"
    flag.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(flag)
    await invalidate(flags_key(current_user.id))

    return flag
