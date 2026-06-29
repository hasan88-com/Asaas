"""
Role: News & Materiality Analyst

Fetches relevant news for the user's portfolio, assesses materiality for any
unscored items, then asks the LLM to explain the impact. Returns to orchestrator
after one round (AGENT_RULES.md §4).
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.news_prompt import SYSTEM_PROMPT
from app.agent.tools.assess_materiality import assess_materiality
from app.agent.tools.fetch_relevant_news import fetch_relevant_news
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.news_materiality")


async def run_news_analyst(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Explain recent news impact on the portfolio.
    Data sent to the LLM is abstracted: headlines, levels, scores, symbols only.
    """
    portfolio_id_str = state.get("portfolio_id")

    if not portfolio_id_str:
        state["response"] = (
            "You don't have an active portfolio yet, so I can't match news to your holdings. "
            "Set up your profile and confirm a portfolio first."
        )
        return state

    portfolio_id = UUID(portfolio_id_str)

    # 1. Fetch matched news
    news_items = await fetch_relevant_news(db=db, portfolio_id=portfolio_id, limit=10)

    # If the user quoted a specific headline (pattern: "…"headline"…"), filter to that item only.
    user_msg = state.get("user_message", "")
    import re as _re
    _quoted = _re.search(r'"([^"]{10,})"', user_msg)
    if _quoted:
        target = _quoted.group(1).lower()
        specific = [i for i in news_items if target[:60] in i.get("headline", "").lower()]
        if specific:
            news_items = specific

    # 2. Assess materiality for any items not yet scored
    for item in news_items:
        if item.get("materiality_score") is None:
            try:
                news_uuid = UUID(item["news_id"])
                await assess_materiality(db=db, news_item_id=news_uuid)
            except Exception as exc:
                logger.warning("Materiality assessment failed for %s: %s", item["news_id"], exc)

    # Drop items confirmed as irrelevant after scoring
    news_items = [
        i for i in news_items
        if i.get("materiality_score") is None or float(i["materiality_score"]) >= 0.1
    ]

    if not news_items:
        state["response"] = (
            "There are no recent news items matched to your current holdings. "
            "I'll check again when new articles are ingested."
        )
        return state

    # 3. Build abstracted LLM payload (no user identity)
    abstracted_news = [
        {
            "headline": item["headline"],
            "source": item["source"],
            "level": item["level"],
            "sentiment": item["sentiment"],
            "materiality_score": item["materiality_score"],
            "matched_symbol": item["matched_symbol"],
            "published_at": item["published_at"],
        }
        for item in news_items
    ]

    user_content = "\n\n".join(p for p in [
        f"Matched news for portfolio:\n{json.dumps(abstracted_news, default=str)}",
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
        logger.error("News analyst LLM call failed: %s", exc)
        explanation = (
            f"I found {len(news_items)} relevant news item(s) for your holdings, "
            "but had trouble generating an explanation. Please try again."
        )

    state["response"] = explanation
    return state
