"""
Role: Rate-Impact Analyst

Extracts old/new SBP policy rates from context or message, calls
analyze_rate_impact tool, then explains the impact in plain language.
Returns to orchestrator after one round (AGENT_RULES.md §5).
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.rate_impact_prompt import SYSTEM_PROMPT
from app.agent.tools.analyze_rate_impact import analyze_rate_impact
from app.agent.types import AgentState
from app.data.adapters.sbp_adapter import SBPAdapter

logger = logging.getLogger("asaas.agent.roles.rate_impact")


def _extract_rate_from_text(text: str) -> Decimal | None:
    """Parse a percentage rate from message text, e.g. '22%' → Decimal('0.22')."""
    match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", text)
    if match:
        try:
            return Decimal(match.group(1)) / Decimal("100")
        except InvalidOperation:
            pass
    return None


async def run_rate_analyst(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Analyse a SBP rate change and explain the T-bill impact.
    Rates are extracted from message text; identity/balance never reach the LLM.
    """
    message = state["user_message"]
    context = state["context"]

    # 1. Try to get current rate from SBP adapter
    try:
        from app.core.market import get_sbp_rate
        current_rate = await get_sbp_rate()
    except RuntimeError:
        try:
            sbp = SBPAdapter()
            current_rate = await sbp.fetch_policy_rate()
        except Exception:
            logger.warning("SBP rate unavailable — cannot run rate impact analysis")
            state["response"] = "I couldn't fetch the current SBP policy rate. Please try again later."
            return state

    # 2. Extract the new rate from the user message (if mentioned)
    new_rate = _extract_rate_from_text(message)
    old_rate = current_rate

    if new_rate is None:
        # No explicit rate mentioned — explain the current rate's impact
        new_rate = current_rate
        old_rate = current_rate - Decimal("0.01")  # synthetic 100bps prior

    # 3. Call the rate impact tool
    impact_result = await analyze_rate_impact(db=db, old_rate=old_rate, new_rate=new_rate)

    # 4. Build abstracted LLM payload
    portfolio_context = context.get("portfolio", {})
    llm_payload = {
        "old_rate_pct": f"{float(old_rate) * 100:.2f}%",
        "new_rate_pct": f"{float(new_rate) * 100:.2f}%",
        "delta_bps": impact_result.get("delta_bps", 0),
        "direction": impact_result.get("direction", "unchanged"),
        "severity": impact_result.get("severity", "medium"),
        "portfolio_sharpe": portfolio_context.get("sharpe"),
        "portfolio_risk_free_rate": portfolio_context.get("risk_free_rate"),
    }

    user_content = "\n\n".join(p for p in [
        f"Rate change details:\n{json.dumps(llm_payload, default=str)}",
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
        logger.error("Rate impact LLM call failed: %s", exc)
        direction = impact_result.get("direction", "changed")
        delta = impact_result.get("delta_bps", 0)
        explanation = (
            f"The SBP policy rate has {direction}d by {abs(delta)} bps "
            f"(from {llm_payload['old_rate_pct']} to {llm_payload['new_rate_pct']}). "
            "This affects your T-bill holdings — no changes have been made to your portfolio."
        )

    state["response"] = explanation
    return state
