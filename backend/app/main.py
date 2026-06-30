"""
Asaas (اثاثہ) — Main API Entry Point

FastAPI setup, CORS, routing, exception handlers, and APScheduler for
background data refresh jobs (TECH.md §6).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import get_settings
from app.core.redis import redis_client
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.portfolio import router as portfolio_router
from app.api.market import router as market_router
from app.api.news import router as news_router
from app.api.chat import router as chat_router
from app.api.strategy import router as strategy_router

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("asaas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Redis connection...")
    try:
        await redis_client.ping()
        logger.info("Redis is connected.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis on startup: {e}")

    # Start APScheduler for background data refresh jobs
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    # Crypto: refresh every 60 s (TECH.md §6)
    from app.workers.crypto_refresh import refresh_crypto_prices
    scheduler.add_job(
        refresh_crypto_prices,
        IntervalTrigger(seconds=60),
        id="crypto_refresh",
        replace_existing=True,
        max_instances=1,
    )

    # Stocks + commodities EOD: daily after market close (17:00 PKT = 12:00 UTC)
    from app.workers.daily_eod import run_daily_eod
    scheduler.add_job(
        run_daily_eod,
        CronTrigger(hour=12, minute=0),
        id="daily_eod",
        replace_existing=True,
        max_instances=1,
    )

    # T-bill / SBP rate watch: every 6 hours (event-driven + periodic fallback)
    from app.workers.tbill_watch import run_tbill_watch
    scheduler.add_job(
        run_tbill_watch,
        IntervalTrigger(hours=6),
        id="tbill_watch",
        replace_existing=True,
        max_instances=1,
    )

    # News monitor: every 3 hours so the feed stays fresh through the day
    # (a daily cron goes stale if the process restarts after it fires).
    from app.workers.news_monitor import run_news_monitor
    scheduler.add_job(
        run_news_monitor,
        IntervalTrigger(hours=3),
        id="news_monitor",
        replace_existing=True,
        max_instances=1,
    )

    # Debt instrument refresh: daily at 00:01 UTC — keep the tenor placeholders
    # backed by the current ACTIVE PSX instrument (real maturity/face_value) and
    # retire any with a past maturity, so the optimizer never suggests matured debt.
    from app.workers.refresh_debt_instruments import run_refresh_debt_instruments
    scheduler.add_job(
        run_refresh_debt_instruments,
        CronTrigger(hour=0, minute=1),
        id="refresh_debt_instruments",
        replace_existing=True,
        max_instances=1,
    )

    # Warm the price cache for held instruments every 2h (under the ~4h stock
    # cache TTL) so dashboard /performance loads hit warm Redis, not the network.
    from app.workers.warm_prices import run_warm_prices
    scheduler.add_job(
        run_warm_prices,
        IntervalTrigger(hours=2),
        id="warm_prices",
        replace_existing=True,
        max_instances=1,
    )

    # Historical price backfill: monthly refresh of the 1–2yr OHLCV window.
    # (daily_eod appends the current day; this keeps the long history complete.)
    from app.workers.backfill_prices import run_backfill_prices
    scheduler.add_job(
        run_backfill_prices,
        CronTrigger(day=1, hour=1, minute=0),
        id="backfill_prices",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "APScheduler started — 7 jobs registered (crypto_refresh, daily_eod, "
        "tbill_watch, news_monitor, refresh_debt_instruments, warm_prices, backfill_prices)"
    )

    # Seed instruments table if empty
    try:
        from sqlalchemy import func, select as sa_select
        from app.core.db import async_session_factory
        from app.models.instrument import Instrument
        from app.data.seed import seed_data

        async with async_session_factory() as _seed_db:
            count = await _seed_db.scalar(sa_select(func.count()).select_from(Instrument))

        if count == 0:
            logger.info("Instruments table is empty — seeding default universe...")
            await seed_data()
            logger.info("Instrument seed complete.")
        else:
            logger.info(f"Instruments table has {count} rows — skipping seed.")
    except Exception as _seed_err:
        logger.error(f"Startup seed failed (non-fatal): {_seed_err}")

    # Populate debt-instrument terms on boot (non-blocking) so matured/nominal
    # debt is excluded immediately, not only after the next 00:01 UTC run.
    try:
        import asyncio as _asyncio
        _asyncio.create_task(run_refresh_debt_instruments())
    except Exception as _refresh_err:
        logger.error(f"Debt refresh kickoff failed (non-fatal): {_refresh_err}")

    # Warm the price cache on boot (non-blocking) so the first dashboard load of
    # a fresh process hits warm Redis instead of paying the cold-fetch tax.
    try:
        import asyncio as _asyncio
        from app.workers.warm_prices import run_warm_prices as _warm
        _asyncio.create_task(_warm())
    except Exception as _warm_err:
        logger.error(f"Price warm kickoff failed (non-fatal): {_warm_err}")

    # Seed the SBP last-known-good rate on boot (non-blocking) so the graceful
    # fallback has a real value from the first request, not only after the next
    # tbill_watch run or first on-demand valuation.
    try:
        import asyncio as _asyncio
        from app.core.market import get_sbp_rate as _get_sbp
        _asyncio.create_task(_get_sbp())
    except Exception as _sbp_err:
        logger.error(f"SBP rate warm kickoff failed (non-fatal): {_sbp_err}")

    # Backfill historical OHLCV on boot if the prices table is cold (non-blocking)
    # so technicals/optimizer/risk read DB-first instead of live-scraping. Idempotent.
    try:
        import asyncio as _asyncio
        from app.workers.backfill_prices import run_backfill_prices, prices_table_is_sparse
        from app.workers.backfill_snapshots import run_backfill_snapshots

        async def _maybe_backfill():
            if await prices_table_is_sparse():
                logger.info("prices table is sparse — kicking off historical backfill")
                await run_backfill_prices()
            # Always backfill snapshots on boot so existing portfolios get chart history
            await run_backfill_snapshots()

        _asyncio.create_task(_maybe_backfill())
    except Exception as _bf_err:
        logger.error(f"Price backfill kickoff failed (non-fatal): {_bf_err}")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("APScheduler shut down.")
    logger.info("Closing Redis connection...")
    await redis_client.close()
    logger.info("Redis connection closed.")


app = FastAPI(
    title=settings.app_name,
    description="Agentic Wealth Management Platform for the Pakistan Market",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware (RULES.md C1.7)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compress JSON/text responses >1KB (news feed, portfolio, etc. shrink ~70-80%).
# Transport-only; response bodies are byte-identical after decompression.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Versioned router
api_router = APIRouter(prefix=settings.api_v1_prefix)

# Mount endpoints
api_router.include_router(auth_router)
api_router.include_router(profile_router)
api_router.include_router(portfolio_router)
api_router.include_router(market_router)
api_router.include_router(news_router)
api_router.include_router(chat_router)
api_router.include_router(analysis_router)
api_router.include_router(strategy_router)


@api_router.get("/health", tags=["system"])
async def health_check():
    """System health check endpoint."""
    redis_status = "healthy"
    try:
        await redis_client.ping()
    except Exception as e:
        logger.error(f"Health check Redis ping failed: {e!r}")
        redis_status = "unhealthy"

    return {
        "status": "healthy" if redis_status == "healthy" else "degraded",
        "services": {
            "database": "healthy",  # Simple ping
            "redis": redis_status,
        }
    }

app.include_router(api_router)
