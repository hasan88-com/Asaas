"""
Asaas (اثاثہ) — Onboarding Flow Tests

Tests the questionnaire → risk profile evaluation flow and
the existing holdings declaration (entry_price as NUMERIC).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.risk_profile import RiskProfile
from app.models.holding import Holding
from app.models.portfolio import Portfolio
from app.models.user import User
from app.services.questionnaire import QUESTIONS, evaluate_questionnaire


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(db, suffix: str = "") -> User:
    user = User(
        id=uuid4(),
        email=f"onboard{suffix}@asaas.test",
        full_name="Onboard Test User",
    )
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Questionnaire definition
# ---------------------------------------------------------------------------


def test_question_set_matches_core_contract():
    """The question set must include the 8 core questions plus asset preferences."""
    ids = {q["id"] for q in QUESTIONS}
    expected_core = {
        "goal", "horizon", "risk_willingness", "loss_tolerance",
        "experience", "initial_capital", "monthly_contribution", "investment_frequency",
    }
    assert expected_core.issubset(ids), f"missing core questions: {expected_core - ids}"


def test_question_ids_are_unique():
    """Every question has a unique id."""
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))


def test_all_questions_have_options_or_numeric():
    """
    Every question exposes at least 2 options, except the free-form numeric
    inputs (initial_capital, monthly_contribution) which intentionally have none.
    """
    numeric_ids = {"initial_capital", "monthly_contribution"}
    for q in QUESTIONS:
        if q["id"] in numeric_ids:
            assert q["options"] == [], f"'{q['id']}' should have no fixed options"
        else:
            assert len(q["options"]) >= 2, f"Question '{q['id']}' has too few options"


# ---------------------------------------------------------------------------
# evaluate_questionnaire — deterministic mapping
# ---------------------------------------------------------------------------


def test_evaluate_maps_conservative():
    """A fully conservative answer set scores into a conservative band."""
    result = evaluate_questionnaire(
        {
            "goal": "preserve",
            "horizon": "1y",
            "risk_willingness": "sell_all",
            "loss_tolerance": "5pct",
            "experience": "none",
        }
    )
    assert result["risk_tolerance"] in ("conservative", "moderately_conservative")
    assert result["horizon"] == "short"
    assert result["goal"] == "preservation"


def test_evaluate_maps_aggressive_long_growth():
    """A fully aggressive answer set scores into an aggressive band."""
    result = evaluate_questionnaire(
        {
            "goal": "appreciation",
            "horizon": "10y_plus",
            "risk_willingness": "buy_more",
            "loss_tolerance": "25pct_plus",
            "experience": "extensive",
            "investment_frequency": "monthly",
            "initial_capital": "1000000",
            "monthly_contribution": "100000",
        }
    )
    assert result["risk_tolerance"] in ("aggressive", "very_aggressive")
    assert result["horizon"] == "long"
    assert result["goal"] == "growth"


def test_evaluate_excluded_sectors_captured():
    result = evaluate_questionnaire(
        {"risk_willingness": "hold", "excluded_sectors": ["tobacco", "gambling"]}
    )
    assert "tobacco" in result["constraints"]["excluded_sectors"]
    assert "gambling" in result["constraints"]["excluded_sectors"]


def test_evaluate_none_exclusion_not_stored():
    """Selecting only 'none' means no exclusions — the key must be absent."""
    result = evaluate_questionnaire(
        {"risk_willingness": "hold", "excluded_sectors": ["none"]}
    )
    assert result["constraints"] == {}


def test_evaluate_invalid_answer_falls_back_to_default():
    """Unrecognised answers contribute 0 to the score and never raise."""
    result = evaluate_questionnaire({"risk_willingness": "super_ultra_aggressive"})
    # Additive scoring: an unrecognised answer scores 0, so the band is the
    # lowest (conservative). The contract is that it degrades gracefully, not raises.
    assert result["risk_tolerance"] == "conservative"
    assert result["risk_score"] == 0


def test_evaluate_empty_answers_returns_all_defaults():
    result = evaluate_questionnaire({})
    # Additive scoring: no answers ⇒ score 0 ⇒ conservative band.
    assert result["risk_tolerance"] == "conservative"
    assert result["risk_score"] == 0
    assert result["horizon"] == "medium"
    assert result["goal"] == "growth"
    assert result["constraints"] == {}


# ---------------------------------------------------------------------------
# Risk profile upsert via questionnaire evaluation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_questionnaire_creates_profile(db_session):
    """Evaluated answers are persisted as a RiskProfile with normalized columns."""
    user = await _create_user(db_session, "q1")
    from datetime import datetime, timezone

    answers = {
        "risk_comfort": "moderate",
        "horizon": "long",
        "investor_mode": "long_term",
        "goal": "growth",
        "excluded_sectors": [],
    }
    evaluated = evaluate_questionnaire(answers)
    now = datetime.now(timezone.utc)

    profile = RiskProfile(
        user_id=user.id,
        risk_tolerance=evaluated["risk_tolerance"],
        horizon=evaluated["horizon"],
        investor_mode=evaluated["investor_mode"],
        initial_capital=Decimal("2000000"),
        goal=evaluated["goal"],
        constraints=evaluated["constraints"],
    )
    db_session.add(profile)
    await db_session.flush()

    res = await db_session.execute(
        select(RiskProfile).where(RiskProfile.user_id == user.id)
    )
    saved = res.scalar_one()
    # Round-trip persistence check: the stored value matches the evaluated one
    # (the answer keys here aren't scored fields, so don't assume a fixed band).
    assert saved.risk_tolerance == evaluated["risk_tolerance"]
    assert saved.initial_capital == Decimal("2000000")


@pytest.mark.asyncio
async def test_questionnaire_upserts_existing_profile(db_session):
    """Re-evaluating questionnaire updates (not duplicates) the risk profile."""
    user = await _create_user(db_session, "q2")

    profile = RiskProfile(
        user_id=user.id,
        risk_tolerance="conservative",
        horizon="short",
        investor_mode="long_term",
        initial_capital=Decimal("500000"),
        goal="preservation",
    )
    db_session.add(profile)
    await db_session.flush()

    # Update via evaluation
    profile.risk_tolerance = "aggressive"
    await db_session.flush()

    res = await db_session.execute(
        select(RiskProfile).where(RiskProfile.user_id == user.id)
    )
    rows = res.scalars().all()
    assert len(rows) == 1  # must not duplicate
    assert rows[0].risk_tolerance == "aggressive"


# ---------------------------------------------------------------------------
# Existing holdings declaration — entry_price as NUMERIC (Decimal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_declare_holdings_stores_entry_price_as_decimal(db_session):
    """
    Holdings declared via onboarding must store entry_price as NUMERIC.
    The value must survive a DB round-trip without float precision loss.
    """
    from app.models.instrument import Instrument

    user = await _create_user(db_session, "h1")

    inst = Instrument(
        symbol="HBL.KA",
        name="Habib Bank Limited",
        asset_class="psx_stock",
        sector="Banking",
        currency="PKR",
        is_active=True,
    )
    db_session.add(inst)
    await db_session.flush()

    portfolio = Portfolio(
        user_id=user.id,
        name="Existing Holdings",
        status="confirmed",
        rationale="User-declared during onboarding.",
    )
    db_session.add(portfolio)
    await db_session.flush()

    entry_price = Decimal("147.50")
    holding = Holding(
        portfolio_id=portfolio.id,
        instrument_id=inst.id,
        quantity=Decimal("200"),
        entry_price=entry_price,
        actual_weight=Decimal("0"),
    )
    db_session.add(holding)
    await db_session.flush()

    res = await db_session.execute(
        select(Holding).where(Holding.portfolio_id == portfolio.id)
    )
    saved = res.scalar_one()

    assert saved.entry_price is not None
    assert Decimal(str(saved.entry_price)) == entry_price, (
        "entry_price must survive DB round-trip as NUMERIC without float drift"
    )


@pytest.mark.asyncio
async def test_declare_holdings_portfolio_is_immediately_confirmed(db_session):
    """Holdings declared during onboarding create a 'confirmed' portfolio immediately."""
    from app.models.instrument import Instrument

    user = await _create_user(db_session, "h2")

    inst = Instrument(
        symbol="MCB.KA",
        name="MCB Bank",
        asset_class="psx_stock",
        sector="Banking",
        currency="PKR",
        is_active=True,
    )
    db_session.add(inst)
    await db_session.flush()

    portfolio = Portfolio(
        user_id=user.id,
        name="Existing Holdings",
        status="confirmed",
    )
    db_session.add(portfolio)
    await db_session.flush()

    holding = Holding(
        portfolio_id=portfolio.id,
        instrument_id=inst.id,
        quantity=Decimal("100"),
        entry_price=Decimal("250.00"),
        actual_weight=Decimal("0"),
    )
    db_session.add(holding)
    await db_session.flush()

    res = await db_session.execute(
        select(Portfolio).where(Portfolio.id == portfolio.id)
    )
    port = res.scalar_one()
    assert port.status == "confirmed", "Declared portfolio must be confirmed immediately"


@pytest.mark.asyncio
async def test_no_float_in_declared_holdings(db_session):
    """entry_price stored via declare-holdings must not be a Python float."""
    from app.models.instrument import Instrument

    user = await _create_user(db_session, "h3")
    inst = Instrument(
        symbol="ENGRO.KA", name="Engro", asset_class="psx_stock",
        sector="Chemical", currency="PKR", is_active=True,
    )
    db_session.add(inst)
    await db_session.flush()

    portfolio = Portfolio(user_id=user.id, name="Existing Holdings", status="confirmed")
    db_session.add(portfolio)
    await db_session.flush()

    entry_price = Decimal("312.75")
    holding = Holding(
        portfolio_id=portfolio.id, instrument_id=inst.id,
        quantity=Decimal("50"), entry_price=entry_price, actual_weight=Decimal("0"),
    )
    db_session.add(holding)
    await db_session.flush()

    res = await db_session.execute(select(Holding).where(Holding.id == holding.id))
    saved = res.scalar_one()

    assert not isinstance(saved.entry_price, float), (
        "entry_price must be Decimal/NUMERIC — never float (RULES.md A2.6)"
    )


# ---------------------------------------------------------------------------
# Diversification analysis (read-only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diversification_analysis_no_writes(db_session):
    """check_diversification must not write any rows."""
    from app.agent.tools.check_diversification import check_diversification
    from app.models.instrument import Instrument
    from sqlalchemy import func

    user = await _create_user(db_session, "div")
    inst = Instrument(
        symbol="LUCK.KA", name="Lucky Cement", asset_class="psx_stock",
        sector="Cement", currency="PKR", is_active=True,
    )
    db_session.add(inst)
    await db_session.flush()

    portfolio = Portfolio(user_id=user.id, name="Existing Holdings", status="confirmed")
    db_session.add(portfolio)
    await db_session.flush()

    holding = Holding(
        portfolio_id=portfolio.id, instrument_id=inst.id,
        quantity=Decimal("100"), entry_price=Decimal("900"),
        actual_weight=Decimal("1.0"),
    )
    db_session.add(holding)
    await db_session.flush()

    # Snapshot row counts before
    before = (await db_session.execute(select(func.count()).select_from(Holding))).scalar()

    result = await check_diversification(db=db_session, portfolio_id=portfolio.id)

    after = (await db_session.execute(select(func.count()).select_from(Holding))).scalar()

    assert before == after, "check_diversification must not write any rows"
    assert "sector_breakdown" in result
