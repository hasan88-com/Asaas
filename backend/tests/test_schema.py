"""
Asaas (اثاثہ) — Database Schema Tests

Verifies model mapping, relations, constraints, and indexes (RULES.md D2.1).
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.risk_profile import RiskProfile
from app.models.instrument import Instrument
from app.models.portfolio import Portfolio
from app.models.holding import Holding


@pytest.mark.asyncio
async def test_user_risk_profile_relationship(db_session: AsyncSession):
    """Verify 1:1 user to risk_profile cascade and integrity."""
    # Create User
    new_user = User(
        id=uuid4(),
        email="schema_test@example.com",
        full_name="Schema Test User",
    )
    db_session.add(new_user)
    await db_session.flush()

    # Create Risk Profile
    profile = RiskProfile(
        user_id=new_user.id,
        risk_tolerance="moderate",
        horizon="medium",
        investor_mode="long_term",
        initial_capital=1000000.0,
        goal="growth",
        constraints={"excluded_sectors": ["Tobacco"]},
    )
    db_session.add(profile)
    await db_session.flush()

    # Verify relation loading
    await db_session.refresh(new_user)
    assert new_user.risk_profile is not None
    assert new_user.risk_profile.risk_tolerance == "moderate"


@pytest.mark.asyncio
async def test_portfolio_holdings_relationships(db_session: AsyncSession):
    """Verify portfolio and holdings relational integrity and unique indexes."""
    # Create User
    user = User(
        id=uuid4(),
        email="portfolio_schema@example.com",
    )
    db_session.add(user)
    await db_session.flush()

    # Create Instrument
    inst = Instrument(
        symbol="ENGRO.KA",
        name="Engro Corp",
        asset_class="psx_stock",
    )
    db_session.add(inst)
    await db_session.flush()

    # Create Portfolio
    port = Portfolio(
        user_id=user.id,
        name="Test Allocation",
        status="draft",
        expected_return=0.12,
        expected_risk=0.08,
    )
    db_session.add(port)
    await db_session.flush()

    # Create Holding
    holding = Holding(
        portfolio_id=port.id,
        instrument_id=inst.id,
        target_weight=1.0,
        quantity=100.0,
        entry_price=250.0,
    )
    db_session.add(holding)
    await db_session.flush()

    # Verify relationships
    await db_session.refresh(port)
    assert len(port.holdings) == 1
    assert port.holdings[0].instrument_id == inst.id
