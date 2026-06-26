"""
Asaas (اثاثہ) — IPS & Portfolio Recommendation Generation Service

Called automatically after questionnaire evaluation to produce:
  - InvestmentPolicyStatement (IPS)
  - PortfolioRecommendation
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── Helpers ──────────────────────────────────────────────────────────────────

def _objective_from_goal(goal: str) -> str:
    return {
        "preservation": "Preserve capital and protect against inflation with minimal drawdown.",
        "income":       "Generate regular income through dividends, profit-sharing, and bond coupons.",
        "growth":       "Grow wealth steadily over the investment horizon with moderate volatility.",
    }.get(goal, "Grow wealth steadily over the investment horizon.")


def _horizon_label(horizon: str) -> str:
    return {
        "short":  "Short-term (up to 3 years)",
        "medium": "Medium-term (3–7 years)",
        "long":   "Long-term (7+ years)",
    }.get(horizon, "Medium-term (3–7 years)")


def _liquidity_profile(horizon: str, loss_tolerance: Optional[str]) -> str:
    if horizon == "short":
        return "High — funds may be needed within 3 years; maintain liquid T-bill allocation."
    if loss_tolerance in ("5pct", "10pct"):
        return "Moderate — partial liquidity buffer recommended via T-bills or money market."
    return "Low — long investment horizon supports illiquid or less-liquid allocations."


def _restrictions_from_prefs(prefs: Optional[Dict[str, Any]]) -> List[str]:
    if not prefs:
        return []
    restrictions = []
    if prefs.get("shariah"):
        restrictions.append("No interest-bearing instruments (riba). Only Shariah-compliant securities.")
    excluded = prefs.get("excluded_sectors", [])
    if excluded:
        for s in excluded:
            restrictions.append(f"Excluded sector: {s}")
    return restrictions


def _return_range(risk_score: Optional[int]) -> str:
    score = risk_score or 50
    if score < 25:
        return "10–14% annually (predominantly T-bills and investment-grade bonds)"
    if score < 45:
        return "12–18% annually (balanced equity and fixed income)"
    if score < 65:
        return "16–24% annually (equity-tilted with moderate fixed income)"
    if score < 80:
        return "20–30% annually (growth equities with selective fixed income)"
    return "25–40%+ annually (aggressive equities and crypto; high variance)"


def _volatility_label(risk_score: Optional[int]) -> str:
    score = risk_score or 50
    if score < 25:
        return "Low — expected drawdowns < 10%"
    if score < 45:
        return "Low-Moderate — expected drawdowns 10–20%"
    if score < 65:
        return "Moderate — expected drawdowns 15–30%"
    if score < 80:
        return "High — expected drawdowns 25–40%"
    return "Very High — expected drawdowns 35%+"


def _rebalance_frequency(horizon: str) -> str:
    return {
        "short":  "Monthly",
        "medium": "Quarterly",
        "long":   "Semi-annually",
    }.get(horizon, "Quarterly")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_ips(profile: Any) -> Dict[str, Any]:
    """
    Build IPS dict from a RiskProfile ORM object.
    Caller is responsible for persisting the result.
    """
    prefs = profile.investment_preferences or {}
    asset_classes = prefs.get("asset_classes", [])

    return {
        "investment_objective":  _objective_from_goal(profile.goal),
        "time_horizon":          _horizon_label(profile.horizon),
        "risk_tolerance":        profile.risk_tolerance,
        "liquidity_profile":     _liquidity_profile(profile.horizon, profile.loss_tolerance),
        "investment_frequency":  profile.investment_frequency,
        "initial_capital":       float(profile.initial_capital),
        "monthly_contribution":  float(profile.monthly_contribution or 0),
        "eligible_asset_classes": asset_classes,
        "investment_restrictions": _restrictions_from_prefs(prefs),
        "recommended_allocation": (profile.recommendations or {}).get("suggested_allocation", {}),
    }


def generate_portfolio_recommendation(profile: Any) -> Dict[str, Any]:
    """
    Build portfolio recommendation dict from a RiskProfile ORM object.
    Caller is responsible for persisting the result.
    """
    return {
        "risk_score":             profile.risk_score,
        "investor_persona":       profile.investor_persona,
        "recommended_allocation": (profile.recommendations or {}).get("suggested_allocation", {}),
        "expected_return_range":  _return_range(profile.risk_score),
        "expected_volatility":    _volatility_label(profile.risk_score),
        "rebalance_frequency":    _rebalance_frequency(profile.horizon),
    }
