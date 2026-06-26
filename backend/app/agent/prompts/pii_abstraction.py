"""
Asaas (اثاثہ) — PII Abstraction

Shared module imported by every role before any LLM call.
Strips user identity, account numbers, and absolute PKR amounts (RULES.md A1.2).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

# Injected into every role system prompt.
ABSTRACTION_GUARDRAIL = (
    "IMPORTANT — DATA PRIVACY RULE:\n"
    "You receive only abstracted context: asset symbols, portfolio weights, "
    "sectors, and aggregate performance metrics.\n"
    "You NEVER see, and must NEVER ask for:\n"
    "  - User identity, name, email, or account numbers\n"
    "  - Absolute PKR balances or investment amounts\n"
    "  - Individual holding quantities or entry prices\n"
    "Do not reference any of these. If a user mentions them, acknowledge "
    "without repeating the value back."
)


def abstract_context(
    profile: Optional[Any],
    portfolio: Optional[Any],
    holdings: List[Any],
    instruments: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a PII-free context dict safe to pass to any LLM.

    Omits: user_id, email, full_name, initial_capital, entry_price, quantity.
    Includes: risk profile metadata, portfolio aggregate metrics, holdings
              by symbol/weight/sector only.
    """
    ctx: Dict[str, Any] = {
        "has_profile": profile is not None,
        "has_portfolio": portfolio is not None,
    }

    if profile:
        # Sanitise questionnaire_answers before including — strip capital fields
        safe_qa = None
        if getattr(profile, "questionnaire_answers", None):
            safe_qa = {
                k: v for k, v in profile.questionnaire_answers.items()
                if k not in ("initial_capital", "monthly_contribution")
            }
        ctx["risk_profile"] = {
            "risk_tolerance": profile.risk_tolerance,
            "horizon": profile.horizon,
            "investor_mode": profile.investor_mode,
            "goal": profile.goal,
            "constraints": profile.constraints,
            "risk_score": getattr(profile, "risk_score", None),
            "questionnaire_answers": safe_qa,
            # NOT initial_capital — never leaks absolute amount
        }

    if portfolio:
        ctx["portfolio"] = {
            "name": portfolio.name,
            "status": portfolio.status,
            "expected_return": (
                str(portfolio.expected_return) if portfolio.expected_return else None
            ),
            "expected_risk": (
                str(portfolio.expected_risk) if portfolio.expected_risk else None
            ),
            "sharpe": str(portfolio.sharpe) if portfolio.sharpe else None,
            "risk_free_rate": (
                str(portfolio.risk_free_rate) if portfolio.risk_free_rate else None
            ),
            "rationale": portfolio.rationale,
        }

    if holdings:
        instruments = instruments or {}
        abstracted_holdings = []
        for h in holdings:
            # instrument lookup may be pre-loaded dict or ORM object
            inst = instruments.get(str(h.instrument_id))
            symbol = inst.symbol if inst else str(h.instrument_id)
            asset_class = inst.asset_class if inst else None
            sector = inst.sector if inst else None

            abstracted_holdings.append({
                "symbol": symbol,
                "asset_class": asset_class,
                "sector": sector,
                "target_weight": (
                    str(h.target_weight) if h.target_weight else "0"
                ),
                "actual_weight": (
                    str(h.actual_weight) if h.actual_weight else "0"
                ),
                # No entry_price, quantity, or entry_date
            })
        ctx["holdings"] = abstracted_holdings

    return ctx


def _assert_no_pii(payload: Dict[str, Any]) -> None:
    """
    Development-time guard: raises AssertionError if PII keys are found
    anywhere in the serialised payload.  Called by tests (RULES.md D2.4).
    """
    import json

    text = json.dumps(payload, default=str).lower()
    forbidden = ["initial_capital", "entry_price", "quantity", "email", "password"]
    for key in forbidden:
        assert key not in text, f"PII leak detected in LLM payload: key '{key}' found"
