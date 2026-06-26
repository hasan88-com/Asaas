"""
Role: Technical Analysis

Computes and interprets RSI, MACD, MFI, moving averages, and crossovers for a named
equity on daily EOD data. All data is read-only. One LLM call per turn (AGENT_RULES.md §3).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.technical_prompt import SYSTEM_PROMPT
from app.agent.tools.run_technical_analysis import run_technical_analysis
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.technical")

_PSX_TICKERS = frozenset({
    "HBL", "UBL", "MCB", "ABL", "BAFL", "BAHL",
    "OGDC", "PPL", "PSO", "SNGP", "SSGC",
    "LUCK", "MLCF", "DGKC", "CHCC", "PIOC",
    "ENGRO", "FFC", "FFBL", "EFERT",
    "NESTLE", "UNILEVER", "ICI",
    "KTML", "NML", "GATM",
    "COLG", "SHEL", "PAKT",
    "TRG", "SYS", "NETSOL",
    "POL", "MARI", "APL",
    "PKGS", "CEPB", "PAPB",
})


def _extract_symbol(message: str) -> Optional[str]:
    """Parse equity ticker from natural-language message (same logic as valuation role)."""
    qualified = re.search(r"\b([A-Z]{2,6}\.KA)\b", message)
    if qualified:
        return qualified.group(1)

    bare = re.findall(r"\b([A-Z]{2,6})\b", message)
    for candidate in bare:
        if candidate in _PSX_TICKERS:
            return f"{candidate}.KA"
        if len(candidate) >= 2:
            return candidate
    return None


async def run_technical_analysis_role(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Compute technical indicators for the named ticker and interpret them for the investor.
    Data is daily EOD only — no intraday signals.
    One LLM call — no self-chaining (AGENT_RULES.md §3).
    """
    symbol = _extract_symbol(state["user_message"])
    if not symbol:
        state["response"] = (
            "Please name the company or ticker you'd like to analyse technically "
            "(e.g. 'RSI for HBL' or 'show MACD on OGDC' or 'technicals for AAPL')."
        )
        return state

    logger.info("Running technical analysis for symbol=%s", symbol)

    try:
        indicators = await run_technical_analysis(symbol=symbol, db=db)
    except Exception as exc:
        logger.error("Technical analysis tool failed for %s: %s", symbol, exc)
        state["response"] = (
            f"I was unable to retrieve technical indicator data for **{symbol}** right now. "
            "The analysis service may be temporarily unavailable. Please try again in a moment."
        )
        return state

    if indicators.get("insufficient_data"):
        state["response"] = (
            f"I don't have enough price history for **{symbol}** to compute "
            f"technical indicators yet. {indicators.get('reason', '')} "
            "Try seeding historical prices or check the ticker spelling."
        )
        return state

    user_content = "\n\n".join(p for p in [
        f"Technical indicators:\n{json.dumps(indicators, default=str)}",
        format_history(state.get("history", [])),
        f"User: {state['user_message']}",
    ] if p)

    try:
        response_text = await call_llm(
            task="reasoning",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Technical Analysis LLM call failed: %s", exc)
        response_text = (
            f"I couldn't generate the technical analysis for {symbol} right now. "
            "Please try again in a moment."
        )

    state["response"] = response_text
    return state
