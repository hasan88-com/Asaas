"""
Tests for all ten agent tools.
RULES.md Part D: D2.3 (weights), D2.5 (no-auto-action), D2.6 (money type).
"""

from __future__ import annotations

import glob
import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agent.tools.analyze_profile import analyze_profile
from app.agent.tools.check_diversification import check_diversification
from app.agent.tools.confirm_holdings import confirm_holdings
from app.agent.tools.fetch_relevant_news import fetch_relevant_news
from app.agent.tools.flag_event import flag_event
from app.agent.tools.track_value import track_value
from app.models.flag import Flag
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.risk_profile import RiskProfile
from app.models.user import User


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


async def _create_user(db, suffix="") -> User:
    user = User(
        id=uuid4(),
        email=f"tooltest{suffix}@asaas.test",
        full_name="Tool Test User",
    )
    db.add(user)
    await db.flush()
    return user


async def _create_instrument(db, symbol="TEST.KA", asset_class="psx_stock") -> Instrument:
    inst = Instrument(
        symbol=symbol,
        name=f"Test Instrument {symbol}",
        asset_class=asset_class,
        sector="Banking",
        currency="PKR",
        is_active=True,
    )
    db.add(inst)
    await db.flush()
    return inst


async def _create_portfolio(db, user_id, status="draft") -> Portfolio:
    port = Portfolio(
        user_id=user_id,
        name="Test Portfolio",
        status=status,
        risk_free_rate=Decimal("0.20"),
    )
    db.add(port)
    await db.flush()
    return port


# ---------------------------------------------------------------------------
# analyze_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_profile_saves_and_returns_abstracted(db_session):
    user = await _create_user(db_session, "profile")
    result = await analyze_profile(
        db=db_session,
        user_id=user.id,
        profile_data={
            "risk_tolerance": "moderate",
            "horizon": "medium",
            "investor_mode": "long_term",
            "goal": "growth",
            "initial_capital": "3000000",
        },
    )
    assert result["saved"] is True
    assert result["risk_tolerance"] == "moderate"
    # initial_capital must NOT be in the return value (RULES.md A1.2)
    assert "initial_capital" not in result


@pytest.mark.asyncio
async def test_analyze_profile_upserts_existing(db_session):
    user = await _create_user(db_session, "profileup")
    await analyze_profile(db=db_session, user_id=user.id, profile_data={"risk_tolerance": "conservative"})
    result = await analyze_profile(db=db_session, user_id=user.id, profile_data={"risk_tolerance": "aggressive"})
    assert result["risk_tolerance"] == "aggressive"
    res = await db_session.execute(select(RiskProfile).where(RiskProfile.user_id == user.id))
    assert res.scalars().all().__len__() == 1  # still only one profile record


# ---------------------------------------------------------------------------
# check_diversification (read-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_diversification_no_writes(db_session):
    user = await _create_user(db_session, "div")
    inst = await _create_instrument(db_session, "DIV.KA")
    port = await _create_portfolio(db_session, user.id)

    holding = Holding(
        portfolio_id=port.id,
        instrument_id=inst.id,
        target_weight=Decimal("1.0"),
    )
    db_session.add(holding)
    await db_session.flush()

    # Snapshot flag count before
    flag_res = await db_session.execute(select(Flag))
    flags_before = len(flag_res.scalars().all())

    result = await check_diversification(db=db_session, portfolio_id=port.id)

    flag_res2 = await db_session.execute(select(Flag))
    flags_after = len(flag_res2.scalars().all())

    assert flags_before == flags_after, "check_diversification must not write flags"
    assert "sector_breakdown" in result
    assert "asset_class_breakdown" in result


# ---------------------------------------------------------------------------
# confirm_holdings — sole path to "confirmed"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_holdings_transitions_to_confirmed(db_session):
    user = await _create_user(db_session, "confirm")
    inst = await _create_instrument(db_session, "CONF.KA")
    port = await _create_portfolio(db_session, user.id, status="draft")

    result = await confirm_holdings(
        db=db_session,
        portfolio_id=port.id,
        user_id=user.id,
        confirmations=[
            {
                "instrument_id": str(inst.id),
                "actual_weight": "1.0",
                "quantity": "100",
                "entry_price": "50.00",
                "entry_date": date.today().isoformat(),
            }
        ],
    )
    assert result["status"] == "confirmed"
    assert result["holdings_count"] == 1


@pytest.mark.asyncio
async def test_confirm_holdings_rejects_wrong_user(db_session):
    user = await _create_user(db_session, "confauth")
    port = await _create_portfolio(db_session, user.id, status="draft")
    other_user_id = uuid4()

    result = await confirm_holdings(
        db=db_session,
        portfolio_id=port.id,
        user_id=other_user_id,
        confirmations=[],
    )
    assert "error" in result
    assert "Unauthorised" in result["error"]


@pytest.mark.asyncio
async def test_confirm_holdings_rejects_non_draft(db_session):
    user = await _create_user(db_session, "confstatus")
    port = await _create_portfolio(db_session, user.id, status="confirmed")

    result = await confirm_holdings(
        db=db_session,
        portfolio_id=port.id,
        user_id=user.id,
        confirmations=[],
    )
    assert "error" in result
    assert "draft" in result["error"]


# ---------------------------------------------------------------------------
# track_value — no absolute PKR in return
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_track_value_no_absolute_pkr(db_session):
    user = await _create_user(db_session, "track")
    port = await _create_portfolio(db_session, user.id, status="confirmed")

    result = await track_value(db=db_session, portfolio_id=port.id)
    assert "total_value_pkr" not in result
    assert "pnl_percent" in result


# ---------------------------------------------------------------------------
# fetch_relevant_news — read-only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_relevant_news_empty_portfolio(db_session):
    user = await _create_user(db_session, "news")
    port = await _create_portfolio(db_session, user.id, status="confirmed")

    result = await fetch_relevant_news(db=db_session, portfolio_id=port.id)
    assert isinstance(result, list)
    # Empty portfolio → empty result, no error
    assert result == []


# ---------------------------------------------------------------------------
# flag_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flag_event_creates_pending_flag(db_session):
    user = await _create_user(db_session, "flag")
    port = await _create_portfolio(db_session, user.id, status="confirmed")

    result = await flag_event(
        db=db_session,
        portfolio_id=port.id,
        event_type="drift",
        message="Test drift flag",
        severity="medium",
    )
    assert result["status"] == "pending"
    assert result["type"] == "drift"

    res = await db_session.execute(select(Flag).where(Flag.portfolio_id == port.id))
    flags = res.scalars().all()
    assert len(flags) == 1
    assert flags[0].status == "pending"


@pytest.mark.asyncio
async def test_flag_event_rejects_invalid_type(db_session):
    user = await _create_user(db_session, "flagbad")
    port = await _create_portfolio(db_session, user.id, status="confirmed")

    result = await flag_event(
        db=db_session,
        portfolio_id=port.id,
        event_type="invalid_type",
        message="Bad flag",
        severity="high",
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# Money type guard (RULES.md D2.6)
# ---------------------------------------------------------------------------


def test_no_float_in_tool_files():
    """Ensure no tool module uses float() for currency calculations."""
    tools_dir = os.path.join(os.path.dirname(__file__), "..", "app", "agent", "tools")
    tool_files = glob.glob(os.path.join(tools_dir, "*.py"))
    assert tool_files, "No tool files found"

    violations = []
    for path in tool_files:
        with open(path) as f:
            for lineno, line in enumerate(f, 1):
                # Allow float() in imports/comments; flag in logic
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                # Specifically flag float() used with currency-like variables
                if "float(" in line and any(
                    kw in line for kw in ["price", "weight", "pkr", "rate", "capital", "amount"]
                ):
                    violations.append(f"{os.path.basename(path)}:{lineno}: {stripped}")

    assert not violations, (
        "float() used for currency in tool files (RULES.md A2.6):\n"
        + "\n".join(violations)
    )
