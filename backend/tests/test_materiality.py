"""
Tests for news materiality scoring and rate-impact flagging.
RULES.md Part D: D2.4 (materiality scoring), D2.5 (no-auto-action).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.flag import Flag
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.news import NewsHoldingLink, NewsItem
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.materiality import MaterialityService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_user_portfolio_instrument(db, symbol="HBL.KA", sector="Banking"):
    import uuid as _uuid
    user = User(
        id=_uuid.uuid4(),
        email=f"mat_{symbol.replace('.','_')}@asaas.test",
        full_name="Materiality Test",
    )
    db.add(user)
    await db.flush()

    inst = Instrument(
        symbol=symbol,
        name=f"Test {symbol}",
        asset_class="psx_stock",
        sector=sector,
        currency="PKR",
        is_active=True,
    )
    db.add(inst)
    await db.flush()

    port = Portfolio(user_id=user.id, name="Test", status="confirmed")
    db.add(port)
    await db.flush()

    holding = Holding(
        portfolio_id=port.id,
        instrument_id=inst.id,
        target_weight=Decimal("0.5"),
    )
    db.add(holding)
    await db.flush()

    return user, inst, port


async def _insert_news(db, headline, source="psx"):
    news = NewsItem(
        source=source,
        headline=headline,
        published_at=datetime.now(timezone.utc),
        raw={},
    )
    db.add(news)
    await db.flush()
    return news


# ---------------------------------------------------------------------------
# Direct match → high severity flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_match_creates_high_flag(db_session):
    """News mentioning the exact symbol → Flag(severity='high')."""
    _, inst, port = await _setup_user_portfolio_instrument(db_session, "HBL.KA")
    news = await _insert_news(db_session, "HBL announces record quarterly profits")

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    res = await db_session.execute(
        select(Flag).where(Flag.portfolio_id == port.id)
    )
    flags = res.scalars().all()
    assert len(flags) >= 1
    assert any(f.severity == "high" for f in flags)
    assert all(f.status == "pending" for f in flags)


# ---------------------------------------------------------------------------
# Sector match → medium severity flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_match_creates_medium_flag(db_session):
    """A MATERIAL sector event (sector match + strong sentiment) → Flag(medium).

    Selective flagging: materiality = relevance(0.5) × magnitude × directional
    must clear the threshold, so the headline needs real directional weight.
    """
    _, inst, port = await _setup_user_portfolio_instrument(db_session, "MCB.KA", "banking")
    # Sector mention (not the symbol) + strong negative cues → high magnitude.
    news = await _insert_news(db_session, "Banking sector collapses as loan defaults plunge profits")

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    res = await db_session.execute(
        select(Flag).where(Flag.portfolio_id == port.id)
    )
    flags = res.scalars().all()
    assert len(flags) >= 1
    assert any(f.severity == "medium" for f in flags)


@pytest.mark.asyncio
async def test_weak_sector_item_links_but_does_not_flag(db_session):
    """A low-materiality sector item is linked (appears in the feed) but does NOT
    flag — the selective-flagging gate stops minor news from piling up alerts."""
    _, inst, port = await _setup_user_portfolio_instrument(db_session, "MCB.KA", "banking")
    # Sector match but only a weak/mixed cue → materiality below threshold.
    news = await _insert_news(db_session, "Banking sector holds routine quarterly review meeting")

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    link = (await db_session.execute(
        select(NewsHoldingLink).where(
            NewsHoldingLink.news_id == news.id,
            NewsHoldingLink.instrument_id == inst.id,
        )
    )).scalar_one_or_none()
    assert link is not None, "sector item should still be linked for the feed"

    flags = (await db_session.execute(
        select(Flag).where(Flag.portfolio_id == port.id)
    )).scalars().all()
    assert len(flags) == 0, "weak sector item must not flag"


# ---------------------------------------------------------------------------
# Macro-only news for T-bill → no portfolio flag (score too low)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_macro_news_no_flag_for_equity_holding(db_session):
    """Pure macro news with no symbol/sector match → no Flag created."""
    _, inst, port = await _setup_user_portfolio_instrument(db_session, "LUCK.KA", "Cement")
    # Headline has no reference to LUCK or Cement
    news = await _insert_news(
        db_session,
        "Global equity markets rally on strong US employment data",
        source="dawn",
    )

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    res = await db_session.execute(
        select(Flag).where(Flag.portfolio_id == port.id)
    )
    flags = res.scalars().all()
    assert len(flags) == 0


# ---------------------------------------------------------------------------
# SBP rate keyword → T-bill macro match (level="macro", no equity flag)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sbp_rate_news_matches_tbill_instrument(db_session):
    """News with 'policy rate' keyword links to T-bill instruments (macro level)."""
    import uuid as _uuid
    user = User(
        id=_uuid.uuid4(),
        email="rate_tbill@asaas.test",
        full_name="Rate Test",
    )
    db_session.add(user)
    await db_session.flush()

    tbill = Instrument(
        symbol="TBILL-3M",
        name="3-Month T-Bill",
        asset_class="tbill",
        sector="Government",
        currency="PKR",
        is_active=True,
    )
    db_session.add(tbill)
    await db_session.flush()

    port = Portfolio(user_id=user.id, name="Fixed Income", status="confirmed")
    db_session.add(port)
    await db_session.flush()

    holding = Holding(
        portfolio_id=port.id,
        instrument_id=tbill.id,
        target_weight=Decimal("1.0"),
    )
    db_session.add(holding)
    await db_session.flush()

    news = await _insert_news(
        db_session,
        "SBP raises policy rate by 100 basis points to combat inflation",
        source="sbp",
    )

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    # Should have created a NewsHoldingLink for the T-bill instrument
    link_res = await db_session.execute(
        select(NewsHoldingLink).where(
            NewsHoldingLink.news_id == news.id,
            NewsHoldingLink.instrument_id == tbill.id,
        )
    )
    link = link_res.scalar_one_or_none()
    assert link is not None, "T-bill should be linked to SBP rate news"
    assert Decimal(str(link.relevance)) == Decimal("0.300")  # macro relevance


# ---------------------------------------------------------------------------
# No-auto-action: flags are "pending", not applied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flags_remain_pending_after_materiality(db_session):
    """Materiality service creates flags but never auto-modifies the portfolio."""
    _, inst, port = await _setup_user_portfolio_instrument(db_session, "ENGRO.KA", "Chemical")
    news = await _insert_news(db_session, "ENGRO reports surge in fertilizer exports")

    svc = MaterialityService(db_session)
    await svc.process_news_item(news.id)

    res = await db_session.execute(
        select(Flag).where(Flag.portfolio_id == port.id)
    )
    flags = res.scalars().all()
    for flag in flags:
        assert flag.status == "pending", "Flags must be pending — no auto-action"

    # Portfolio itself must remain unchanged
    port_res = await db_session.execute(
        select(Portfolio).where(Portfolio.id == port.id)
    )
    port_current = port_res.scalar_one()
    assert port_current.status == "confirmed"
