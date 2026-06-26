"""
Role: Optimizer

Three intent-aware branches, all respecting RULES.md A1.1 (no portfolio change
without an explicit user confirm):

  intent == "track"            → track_value: refresh metrics + snapshot on the
                                 EXISTING confirmed portfolio. No new portfolio
                                 is created. Falls back to a graceful message
                                 when the user has nothing tracked yet.
  intent in (suggest,          → if the user already has a confirmed portfolio,
  diversification)               call reoptimize (ownership-checked; the confirmed
                                 portfolio is NEVER mutated — a new tagged draft is
                                 produced for the user to confirm). Otherwise run
                                 suggest_portfolio to produce a first draft.

Then check_diversification runs on the resulting portfolio_id and the LLM
produces a plain-language rationale. Returns to orchestrator after one round —
no self-chaining (AGENT_RULES.md §3).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.optimizer_prompt import SYSTEM_PROMPT
from app.agent.tools.check_diversification import check_diversification
from app.agent.tools.reoptimize import reoptimize
from app.agent.tools.suggest_portfolio import suggest_portfolio
from app.agent.tools.track_value import track_value
from app.agent.types import AgentState
from app.models.holding import Holding
from app.models.portfolio import Portfolio

logger = logging.getLogger("asaas.agent.roles.optimizer")


async def _existing_draft_id(db: AsyncSession, user_id: UUID) -> UUID | None:
    """Return the most recent draft portfolio id for the user, if any."""
    res = await db.execute(
        select(Portfolio.id)
        .where(Portfolio.user_id == user_id, Portfolio.status == "draft")
        .order_by(Portfolio.created_at.desc())
        .limit(1)
    )
    row = res.first()
    return row[0] if row else None


async def _draft_snapshot(db: AsyncSession, portfolio_id: UUID) -> Dict[str, Any]:
    """Read-only view of an existing draft for the LLM payload (no absolute PKR)."""
    pf_res = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id)
    )
    portfolio = pf_res.scalar_one_or_none()
    if not portfolio:
        return {"error": "Draft not found."}

    hold_res = await db.execute(
        select(Holding).where(Holding.portfolio_id == portfolio_id)
    )
    holdings = hold_res.scalars().all()

    def _d(v: Any) -> str:
        return str(v) if v is not None else ""

    target_weights = {
        str(h.target_weight): _d(h.target_weight) for h in holdings if h.target_weight
    }
    return {
        "status": portfolio.status,
        "target_weights": {},
        "expected_return": _d(portfolio.expected_return),
        "expected_risk": _d(portfolio.expected_risk),
        "sharpe": _d(portfolio.sharpe),
        "risk_free_rate": _d(portfolio.risk_free_rate),
        "sector_breakdown": {},
        "rationale": portfolio.rationale or "Your previously suggested (unconfirmed) draft.",
    }


async def run_optimizer(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Run the appropriate portfolio tool based on intent and produce an explanation.
    All data passed to the LLM is abstracted (no absolute PKR, no identity).
    """
    user_id = UUID(state["user_id"])
    intent = state.get("intent", "suggest")
    portfolio_id_str = state.get("portfolio_id")

    # ------------------------------------------------------------------
    # Branch 1 — track: report on the existing portfolio, do NOT create one.
    # ------------------------------------------------------------------
    if intent == "track":
        if not portfolio_id_str:
            state["response"] = (
                "You don't have a tracked portfolio yet. Complete your profile and "
                "confirm a portfolio first, then I can report on its performance."
            )
            return state

        portfolio_id = UUID(portfolio_id_str)
        try:
            track_result = await track_value(db=db, portfolio_id=portfolio_id)
        except Exception as exc:
            # track_value touches live prices via PerformanceService; if market
            # data is empty/down it can raise rather than return an error dict.
            # Surface a calm message — never a raw traceback.
            logger.error("track_value tool raised for portfolio %s: %s", portfolio_id, exc)
            track_result = {"error": "data_unavailable"}
        if "error" in track_result:
            state["response"] = (
                "I can't refresh your portfolio's performance right now — live price "
                "data may still be loading. Your holdings are safe; try again shortly."
            )
            return state

        # Relative metrics only — no absolute PKR (RULES.md A1.2).
        track_payload = {
            "pnl_percent": track_result.get("pnl_percent"),
            "pnl_direction": track_result.get("pnl_direction"),
            "snapshot_date": track_result.get("snapshot_date"),
        }
        user_content = "\n\n".join(p for p in [
            f"Portfolio performance (current snapshot):\n{json.dumps(track_payload, default=str)}",
            format_history(state.get("history", [])),
            f"User question: {state['user_message']}",
        ] if p)

        try:
            explanation = await call_llm(
                task="reasoning",
                system_prompt=SYSTEM_PROMPT,
                user_message=user_content,
            )
        except Exception as exc:
            logger.error("Optimizer (track) LLM call failed: %s", exc)
            direction = track_payload.get("pnl_direction", "unchanged")
            pct = track_payload.get("pnl_percent", "0")
            explanation = (
                f"Your portfolio is currently {direction} by {pct}% (as of "
                f"{track_payload.get('snapshot_date', 'today')}). "
                "ASAAS provides suggestions only — not financial advice."
            )

        state["response"] = explanation
        # track_value operates on the existing portfolio; no new id to surface.
        return state

    # ------------------------------------------------------------------
    # Branches 2 & 3 — produce a draft (reoptimize if a portfolio already
    # exists, otherwise suggest from scratch).
    # ------------------------------------------------------------------
    portfolio_result = None
    if portfolio_id_str:
        # Ownership + status checks live inside reoptimize; on failure it
        # returns {"error": ...} and we fall back to a fresh suggestion.
        portfolio_result = await reoptimize(
            db=db,
            user_id=user_id,
            portfolio_id=UUID(portfolio_id_str),
        )
        if "error" in portfolio_result:
            logger.info(
                "reoptimize declined (will suggest instead): %s",
                portfolio_result["error"],
            )
            portfolio_result = None

    if portfolio_result is None:
        # reoptimize declined (e.g. the user's only portfolio is itself a draft).
        # Avoid stacking duplicates: if a draft already exists for this user,
        # reuse it rather than creating yet another. Only suggest from scratch
        # when there's truly nothing pending.
        existing_draft_id = await _existing_draft_id(db, user_id)
        if existing_draft_id:
            portfolio_result = {
                "portfolio_id": str(existing_draft_id),
                "reused_draft": True,
                **(await _draft_snapshot(db, existing_draft_id)),
            }
        else:
            portfolio_result = await suggest_portfolio(db=db, user_id=user_id)

    if "error" in portfolio_result:
        state["response"] = (
            f"I wasn't able to generate a portfolio suggestion: {portfolio_result['error']}\n\n"
            "Please make sure your investor profile is complete and market data "
            "has been loaded."
        )
        return state

    # Check diversification on the resulting draft.
    portfolio_id = UUID(portfolio_result["portfolio_id"])
    diversification = await check_diversification(db=db, portfolio_id=portfolio_id)

    # Build abstracted LLM payload (no user identity, no absolute PKR).
    llm_payload = {
        "reoptimised": portfolio_result.get("reoptimised", False),
        "target_weights": portfolio_result.get("target_weights", {}),
        "expected_return": portfolio_result.get("expected_return"),
        "expected_risk": portfolio_result.get("expected_risk"),
        "sharpe": portfolio_result.get("sharpe"),
        "risk_free_rate": portfolio_result.get("risk_free_rate"),
        "sector_breakdown": portfolio_result.get("sector_breakdown", {}),
        "asset_class_breakdown": diversification.get("asset_class_breakdown", {}),
        "diversification_notes": diversification.get("warnings", []),
        "rationale": portfolio_result.get("rationale"),
    }

    user_content = "\n\n".join(p for p in [
        f"Portfolio optimization result:\n{json.dumps(llm_payload, default=str)}",
        format_history(state.get("history", [])),
        f"User question: {state['user_message']}",
    ] if p)

    try:
        explanation = await call_llm(
            task="reasoning",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Optimizer LLM call failed: %s", exc)
        explanation = portfolio_result.get("rationale", "Portfolio optimization complete.")

    state["response"] = explanation
    state["portfolio_id"] = portfolio_result["portfolio_id"]
    return state
