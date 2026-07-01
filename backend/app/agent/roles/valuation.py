"""
Role: Valuation

Runs DCF + Monte Carlo + multiples for a named equity. All data is read-only.
Returns to orchestrator after one LLM call (AGENT_RULES.md §3).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm_router import call_llm
from app.agent.memory import format_history
from app.agent.prompts.valuation_prompt import SYSTEM_PROMPT
from app.agent.tools.extract_company_info import extract_company_info
from app.agent.tools.run_dcf import run_dcf
from app.agent.tools.run_monte_carlo import run_monte_carlo
from app.agent.tools.run_multiples import run_multiples
from app.agent.types import AgentState

logger = logging.getLogger("asaas.agent.roles.valuation")

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
    """
    Parse equity ticker from natural-language message.
    Regex: 2-6 uppercase letters optionally followed by .KA.
    PSX tickers without .KA get it appended.
    """
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


async def run_valuation(
    state: AgentState,
    db: AsyncSession,
) -> AgentState:
    """
    Gather DCF, Monte Carlo, and multiples data for the named ticker,
    then ask the LLM to interpret results for the investor.
    All 4 tools run concurrently. One LLM call — no self-chaining (AGENT_RULES.md §3).
    """
    symbol = _extract_symbol(state["user_message"])
    if not symbol:
        state["response"] = (
            "Please name the company or ticker you'd like valued "
            "(e.g. 'value HBL' or 'DCF on OGDC' or 'tell me about PSO')."
        )
        return state

    # Normalise to the PSX .KA form so ALL tools (incl. company_info) hit the
    # dps/PSX fundamentals source, not a foreign yfinance ticker.
    from app.services.valuation import _yf_equity_symbol
    symbol = _yf_equity_symbol(symbol)

    logger.info("Running valuation for symbol=%s", symbol)

    info, dcf, mc, mult = await asyncio.gather(
        extract_company_info(symbol),
        run_dcf(symbol),
        run_monte_carlo(symbol),
        run_multiples(symbol),
        return_exceptions=True,
    )

    def _safe(result, name: str) -> object:
        return result if not isinstance(result, Exception) else f"{name}: unavailable ({result})"

    payload = {
        "symbol": symbol,
        "company_info": _safe(info, "company_info"),
        "dcf": _safe(dcf, "dcf"),
        "monte_carlo": _safe(mc, "monte_carlo"),
        "multiples": _safe(mult, "multiples"),
    }

    user_content = "\n\n".join(p for p in [
        f"Valuation data:\n{json.dumps(payload, default=str)}",
        format_history(state.get("history", [])),
        f"User: {state['user_message']}",
    ] if p)

    try:
        response_text = await call_llm(
            task="hard",
            system_prompt=SYSTEM_PROMPT,
            user_message=user_content,
        )
    except Exception as exc:
        logger.error("Valuation LLM call failed: %s", exc)
        response_text = (
            f"I couldn't generate a full valuation for {symbol} right now. "
            "Please try again in a moment."
        )

    state["response"] = response_text
    return state
