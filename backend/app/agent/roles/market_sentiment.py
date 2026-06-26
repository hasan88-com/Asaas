"""
Role: Market Sentiment Analyst (Stage 5: EXPLAIN)

Reads the persisted market_sentiment_snapshot (via fetch_market_sentiment) and
explains the market mood for the user's holdings. Consumer of precomputed
signal — it does not compute sentiment, and never touches portfolio math.
One LLM call (reasoning), read-only (AGENT_RULES.md §4, §7).
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.tools.fetch_market_sentiment import fetch_market_sentiment
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.market_sentiment")

_SYSTEM_PROMPT = (
    "You are the Market Sentiment analyst for ASAAS, a Pakistan-focused wealth manager.\n"
    "You are given a precomputed sentiment snapshot: an overall PSX score, and per-sector / "
    "per-asset-class scores for the user's holdings. Scores range -1 (very bearish) to +1 (very "
    "bullish); each carries item_count / bullish_count / bearish_count from the last 7 days.\n"
    "Explain the market mood plainly, grounded ONLY in the numbers provided. Call out where the "
    "user's holdings sit. Be concise. Sentiment is informational only — never recommend buying, "
    "selling, or changing allocation. If the snapshot is empty, say sentiment data isn't available yet."
)


async def run_market_sentiment(state: AgentState, db: AsyncSession) -> AgentState:
    """Explain market/sector sentiment for the user's portfolio."""
    portfolio_id_str = state.get("portfolio_id")
    if not portfolio_id_str:
        state["response"] = (
            "You don't have an active portfolio yet, so I can't tie market sentiment to your holdings. "
            "Set up your profile and confirm a portfolio first."
        )
        return state

    snapshot = await fetch_market_sentiment(db=db, portfolio_id=UUID(portfolio_id_str))

    if not snapshot.get("market") and not snapshot.get("sectors") and not snapshot.get("asset_classes"):
        state["response"] = (
            "I don't have a market-sentiment reading yet — it's computed from recent news. "
            "Try refreshing the news feed, and I'll have a mood snapshot shortly."
        )
        return state

    user_content = "\n\n".join(p for p in [
        f"Sentiment snapshot:\n{json.dumps(snapshot, default=str)}",
        format_history(state.get("history", [])),
        f"User question: {state['user_message']}",
    ] if p)

    try:
        state["response"] = await call_llm(
            task="reasoning",
            system_prompt=_SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Market sentiment LLM call failed: %s", exc)
        mkt = snapshot.get("market") or {}
        score = mkt.get("score")
        state["response"] = (
            f"Overall PSX sentiment is {score:+.2f} over the last week"
            if isinstance(score, (int, float))
            else "I have a sentiment snapshot but couldn't generate an explanation. Please try again."
        )
    return state
