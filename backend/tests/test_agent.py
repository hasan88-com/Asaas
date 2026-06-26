"""
Tests for PII abstraction, intent classification, and no-auto-action guard.
RULES.md Part D gates: D2.4 (PII), D2.5 (no-auto-action).
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.agent.prompts.pii_abstraction import ABSTRACTION_GUARDRAIL, _assert_no_pii, abstract_context


# ---------------------------------------------------------------------------
# Helpers: build minimal mock ORM objects
# ---------------------------------------------------------------------------


def _make_profile(**kwargs):
    p = MagicMock()
    p.risk_tolerance = kwargs.get("risk_tolerance", "moderate")
    p.horizon = kwargs.get("horizon", "medium")
    p.investor_mode = kwargs.get("investor_mode", "long_term")
    p.goal = kwargs.get("goal", "growth")
    p.constraints = kwargs.get("constraints", {})
    p.initial_capital = kwargs.get("initial_capital", Decimal("5000000"))
    return p


def _make_portfolio(**kwargs):
    pf = MagicMock()
    pf.id = kwargs.get("id", uuid4())
    pf.name = kwargs.get("name", "Test Portfolio")
    pf.status = kwargs.get("status", "confirmed")
    pf.expected_return = kwargs.get("expected_return", Decimal("0.15"))
    pf.expected_risk = kwargs.get("expected_risk", Decimal("0.10"))
    pf.sharpe = kwargs.get("sharpe", Decimal("1.5"))
    pf.risk_free_rate = kwargs.get("risk_free_rate", Decimal("0.20"))
    pf.rationale = kwargs.get("rationale", "Test rationale")
    return pf


def _make_holding(instrument_id=None):
    h = MagicMock()
    h.instrument_id = instrument_id or uuid4()
    h.target_weight = Decimal("0.25")
    h.actual_weight = Decimal("0.26")
    h.quantity = Decimal("100")
    h.entry_price = Decimal("120.50")
    return h


def _make_instrument(symbol="HBL.KA", asset_class="psx_stock", sector="Banking"):
    i = MagicMock()
    i.id = uuid4()
    i.symbol = symbol
    i.asset_class = asset_class
    i.sector = sector
    return i


# ---------------------------------------------------------------------------
# PII Abstraction Tests (RULES.md D2.4)
# ---------------------------------------------------------------------------


def test_abstract_context_strips_initial_capital():
    """initial_capital must NEVER appear in the abstracted context."""
    profile = _make_profile(initial_capital=Decimal("5000000"))
    ctx = abstract_context(profile=profile, portfolio=None, holdings=[])

    serialized = json.dumps(ctx, default=str)
    assert "initial_capital" not in serialized
    assert "5000000" not in serialized


def test_abstract_context_strips_user_identity():
    """user_id and email must not appear in abstract_context output."""
    profile = _make_profile()
    portfolio = _make_portfolio()
    ctx = abstract_context(profile=profile, portfolio=portfolio, holdings=[])

    serialized = json.dumps(ctx, default=str)
    assert "email" not in serialized
    assert "user_id" not in serialized


def test_abstract_context_strips_holding_pii():
    """entry_price and quantity must not appear in abstracted holdings."""
    inst = _make_instrument()
    holding = _make_holding(instrument_id=inst.id)
    instruments = {str(inst.id): inst}

    profile = _make_profile()
    portfolio = _make_portfolio()
    ctx = abstract_context(
        profile=profile,
        portfolio=portfolio,
        holdings=[holding],
        instruments=instruments,
    )

    serialized = json.dumps(ctx, default=str)
    assert "entry_price" not in serialized
    assert "120.50" not in serialized  # actual entry price value


def test_abstract_context_includes_risk_profile():
    """Risk profile metadata should be present."""
    profile = _make_profile(risk_tolerance="aggressive", goal="growth")
    ctx = abstract_context(profile=profile, portfolio=None, holdings=[])

    assert ctx["has_profile"] is True
    assert ctx["risk_profile"]["risk_tolerance"] == "aggressive"
    assert ctx["risk_profile"]["goal"] == "growth"
    # initial_capital must not be present
    assert "initial_capital" not in ctx["risk_profile"]


def test_abstract_context_includes_holdings_by_symbol():
    """Holdings should be present by symbol/weight only."""
    inst = _make_instrument(symbol="HBL.KA")
    holding = _make_holding(instrument_id=inst.id)
    instruments = {str(inst.id): inst}

    profile = _make_profile()
    portfolio = _make_portfolio()
    ctx = abstract_context(
        profile=profile, portfolio=portfolio, holdings=[holding], instruments=instruments
    )

    assert len(ctx["holdings"]) == 1
    h = ctx["holdings"][0]
    assert h["symbol"] == "HBL.KA"
    assert "target_weight" in h
    assert "entry_price" not in h
    assert "quantity" not in h


def test_assert_no_pii_raises_on_leak():
    """_assert_no_pii should raise if a forbidden key is present."""
    bad_payload = {"risk_profile": {"initial_capital": "5000000", "goal": "growth"}}
    with pytest.raises(AssertionError, match="initial_capital"):
        _assert_no_pii(bad_payload)


def test_assert_no_pii_passes_clean_payload():
    """_assert_no_pii should not raise for a clean abstracted payload."""
    clean = {
        "risk_profile": {"risk_tolerance": "moderate", "goal": "growth"},
        "portfolio": {"sharpe": "1.5"},
        "holdings": [{"symbol": "HBL.KA", "target_weight": "0.25"}],
    }
    _assert_no_pii(clean)  # should not raise


def test_abstraction_guardrail_contains_key_instructions():
    """ABSTRACTION_GUARDRAIL must mention identity and balance prohibition."""
    assert "identity" in ABSTRACTION_GUARDRAIL.lower() or "email" in ABSTRACTION_GUARDRAIL.lower()
    assert "pkr" in ABSTRACTION_GUARDRAIL.lower() or "balance" in ABSTRACTION_GUARDRAIL.lower()


# ---------------------------------------------------------------------------
# No-Auto-Action Test (RULES.md D2.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_auto_action_on_confirm_message(db_session):
    """
    Sending a 'confirm my portfolio' message through the orchestrator must NOT
    transition any portfolio to 'confirmed' status — only explicit confirm_holdings
    tool call (via the API) can do that.
    """
    from sqlalchemy import select

    from app.agent.orchestrator import AgentOrchestrator
    from app.models.portfolio import Portfolio
    from app.models.user import User

    # Create a test user with a draft portfolio.
    # id is explicit — Supabase Auth owns it; the model has no local default.
    user = User(
        id=uuid4(),
        email="test_noauto@asaas.test",
        full_name="Test User",
    )
    db_session.add(user)
    await db_session.flush()

    draft = Portfolio(
        user_id=user.id,
        name="Test Draft",
        status="draft",
    )
    db_session.add(draft)
    await db_session.commit()

    # Mock the LLM at its use-site (orchestrator imports call_llm directly).
    with patch("app.agent.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "general"  # intent classification
        orchestrator = AgentOrchestrator(db_session)
        await orchestrator.process_message(user.id, "please confirm my portfolio")

    # Verify draft portfolio is STILL draft (no auto-confirm)
    res = await db_session.execute(
        select(Portfolio).where(Portfolio.id == draft.id)
    )
    portfolio = res.scalar_one()
    assert portfolio.status == "draft", (
        "Portfolio must NOT be auto-confirmed from a chat message alone."
    )


# ---------------------------------------------------------------------------
# Conversation memory (Part A)
# ---------------------------------------------------------------------------


def test_format_history():
    """format_history renders labeled turns and no-ops on empty/blank input."""
    from app.agent.memory import format_history

    # Empty / unusable input → "" so roles can append unconditionally.
    assert format_history([]) == ""
    assert format_history([{"role": "user"}]) == ""              # missing content
    assert format_history([{"role": "user", "content": "   "}]) == ""  # blank content
    assert format_history(["not a dict"]) == ""                  # tolerates junk

    # Mixed turns → labeled block, "assistant" rendered as "Asaas", in order.
    out = format_history(
        [
            {"role": "user", "content": "what about gold?"},
            {"role": "assistant", "content": "Gold sits at ~8% of your mix."},
        ]
    )
    assert out.startswith("Recent conversation:")
    assert "User: what about gold?" in out
    assert "Asaas: Gold sits at ~8% of your mix." in out
    # Order preserved (user turn before assistant turn).
    assert out.index("User: what about gold?") < out.index("Asaas: Gold sits")


# ---------------------------------------------------------------------------
# Optimizer intent wiring (Part B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimizer_track_intent_calls_track_value(db_session):
    """
    A 'track' intent must call track_value on the existing portfolio and must
    NOT create a new portfolio (no fall-through to suggest_portfolio/reoptimize).
    """
    from sqlalchemy import func, select

    from app.agent.roles import optimizer as opt_mod
    from app.models.portfolio import Portfolio
    from app.models.user import User

    user = User(id=uuid4(), email="track@asaas.test", full_name="Track User")
    db_session.add(user)
    await db_session.flush()

    confirmed = Portfolio(user_id=user.id, name="My Portfolio", status="confirmed")
    db_session.add(confirmed)
    await db_session.commit()

    count_q = select(func.count()).select_from(Portfolio)
    before = (await db_session.execute(count_q)).scalar_one()

    state = {
        "user_id": str(user.id),
        "user_message": "how is my portfolio doing?",
        "intent": "track",
        "context": {},
        "portfolio_id": str(confirmed.id),
        "response": "",
        "history": [],
    }

    with patch.object(opt_mod, "track_value", new_callable=AsyncMock) as mock_track, \
         patch.object(opt_mod, "suggest_portfolio", new_callable=AsyncMock) as mock_suggest, \
         patch.object(opt_mod, "reoptimize", new_callable=AsyncMock) as mock_reopt, \
         patch.object(opt_mod, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_track.return_value = {
            "pnl_percent": "5.20",
            "pnl_direction": "up",
            "snapshot_date": "2026-06-21",
        }
        mock_llm.return_value = "Your portfolio is up 5.2% since inception."
        result = await opt_mod.run_optimizer(state, db_session)

    # track branch taken; no portfolio-creating tool invoked.
    mock_track.assert_awaited_once()
    mock_suggest.assert_not_awaited()
    mock_reopt.assert_not_awaited()

    after = (await db_session.execute(count_q)).scalar_one()
    assert after == before, "track intent must NOT create a new portfolio"
    assert result["response"] == "Your portfolio is up 5.2% since inception."


@pytest.mark.asyncio
async def test_optimizer_suggest_with_existing_portfolio_uses_reoptimize(db_session):
    """
    A 'suggest' intent with an existing confirmed portfolio must route through
    reoptimize (ownership-checked) — not raw suggest_portfolio — and must leave
    the confirmed portfolio untouched while surfacing the new draft.
    """
    from sqlalchemy import select

    from app.agent.roles import optimizer as opt_mod
    from app.models.portfolio import Portfolio
    from app.models.user import User

    user = User(id=uuid4(), email="reopt@asaas.test", full_name="Reopt User")
    db_session.add(user)
    await db_session.flush()

    confirmed = Portfolio(user_id=user.id, name="Confirmed Portfolio", status="confirmed")
    db_session.add(confirmed)
    await db_session.flush()

    # Stand-in for the fresh draft reoptimize would create (kept distinct so we
    # can prove the confirmed portfolio is never the one surfaced/mutated).
    new_draft = Portfolio(user_id=user.id, name="Reoptimised Draft", status="draft")
    db_session.add(new_draft)
    await db_session.commit()

    state = {
        "user_id": str(user.id),
        "user_message": "rebalance my portfolio",
        "intent": "suggest",
        "context": {},
        "portfolio_id": str(confirmed.id),
        "response": "",
        "history": [],
    }

    with patch.object(opt_mod, "reoptimize", new_callable=AsyncMock) as mock_reopt, \
         patch.object(opt_mod, "suggest_portfolio", new_callable=AsyncMock) as mock_suggest, \
         patch.object(opt_mod, "check_diversification", new_callable=AsyncMock) as mock_div, \
         patch.object(opt_mod, "call_llm", new_callable=AsyncMock) as mock_llm:
        mock_reopt.return_value = {
            "portfolio_id": str(new_draft.id),
            "reoptimised": True,
            "source_portfolio_id": str(confirmed.id),
            "target_weights": {"HBL.KA": 0.5, "OGDC.KA": 0.5},
            "expected_return": "0.16",
            "expected_risk": "0.11",
            "sharpe": "1.4",
            "risk_free_rate": "0.20",
            "sector_breakdown": {},
            "rationale": "Rebalanced for better diversification.",
        }
        mock_div.return_value = {"asset_class_breakdown": {}, "warnings": []}
        mock_llm.return_value = "Here's a rebalanced draft for your review."
        result = await opt_mod.run_optimizer(state, db_session)

    # reoptimize used (ownership-checked), not raw suggest.
    mock_reopt.assert_awaited_once()
    mock_suggest.assert_not_awaited()
    assert mock_reopt.await_args.kwargs["portfolio_id"] == confirmed.id
    assert mock_reopt.await_args.kwargs["user_id"] == user.id

    # The confirmed portfolio is untouched.
    refetched = (
        await db_session.execute(select(Portfolio).where(Portfolio.id == confirmed.id))
    ).scalar_one()
    assert refetched.status == "confirmed"
    assert refetched.name == "Confirmed Portfolio"

    # The new draft is surfaced, distinct from the confirmed portfolio.
    assert result["portfolio_id"] == str(new_draft.id)
    assert result["portfolio_id"] != str(confirmed.id)
    assert result["response"] == "Here's a rebalanced draft for your review."
