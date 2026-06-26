"""
Asaas (اثاثہ) — Questionnaire Evaluation Service

Lean 8-question onboarding: goal, horizon, risk behaviour, loss tolerance,
experience, capital, monthly contribution, investment frequency.
Asset preferences (asset classes + sub-selections) are collected on a
separate optional screen and folded into investment_preferences JSONB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional


# ── Question Definitions ────────────────────────────────────────────────────

QUESTIONS: List[Dict[str, Any]] = [
    # ── Core 8 ──
    {
        "id": "goal",
        "question": "What is your primary investment goal?",
        "category": "goals",
        "options": [
            {"value": "preserve", "label": "Capital Preservation"},
            {"value": "income",   "label": "Income Generation"},
            {"value": "growth",   "label": "Balanced Growth"},
            {"value": "appreciation", "label": "Aggressive Growth"},
            {"value": "target",   "label": "Target Amount (house, education, retirement)"},
        ],
    },
    {
        "id": "horizon",
        "question": "When will you likely need most of this money?",
        "category": "goals",
        "options": [
            {"value": "1y",       "label": "Less than 1 year"},
            {"value": "1_3y",     "label": "1–3 years"},
            {"value": "3_5y",     "label": "3–5 years"},
            {"value": "5_10y",    "label": "5–10 years"},
            {"value": "10y_plus", "label": "10+ years"},
        ],
    },
    {
        "id": "risk_willingness",
        "question": "If your portfolio dropped 15% in a month, what would you do?",
        "category": "risk",
        "options": [
            {"value": "sell_all",  "label": "Sell Everything"},
            {"value": "sell_some", "label": "Sell Some"},
            {"value": "hold",      "label": "Hold"},
            {"value": "buy_more",  "label": "Buy More"},
        ],
    },
    {
        "id": "loss_tolerance",
        "question": "What maximum annual loss could you tolerate?",
        "category": "risk",
        "options": [
            {"value": "5pct",      "label": "5%"},
            {"value": "10pct",     "label": "10%"},
            {"value": "15pct",     "label": "15%"},
            {"value": "25pct_plus","label": "25%+"},
        ],
    },
    {
        "id": "experience",
        "question": "What best describes your investment experience?",
        "category": "behavioral",
        "options": [
            {"value": "none",      "label": "Beginner — first time investing"},
            {"value": "limited",   "label": "Some Experience — savings / fixed deposits"},
            {"value": "moderate",  "label": "Experienced — mutual funds or PSX stocks"},
            {"value": "extensive", "label": "Advanced — active diversified investor"},
        ],
    },
    {
        "id": "initial_capital",
        "question": "How much are you investing today? (PKR)",
        "category": "capital",
        "options": [],
    },
    {
        "id": "monthly_contribution",
        "question": "How much can you invest every month? (PKR, enter 0 if one-time)",
        "category": "capital",
        "options": [],
    },
    {
        "id": "investment_frequency",
        "question": "How frequently do you plan to invest?",
        "category": "capital",
        "options": [
            {"value": "one_time",  "label": "One Time Only"},
            {"value": "monthly",   "label": "Monthly"},
            {"value": "quarterly", "label": "Quarterly"},
            {"value": "annually",  "label": "Annually"},
        ],
    },
    # ── Asset Preferences (conditional screen) ──
    {
        "id": "asset_classes",
        "question": "Which investments are you comfortable owning?",
        "category": "preferences",
        "multiple": True,
        "options": [
            {"value": "psx",          "label": "Pakistan Stocks (PSX)"},
            {"value": "fixed_income", "label": "Fixed Income (T-Bills, Sukuk, Bonds)"},
            {"value": "gold",         "label": "Gold & Commodities"},
            {"value": "crypto",       "label": "Crypto"},
            {"value": "shariah",      "label": "Shariah-Compliant Only"},
        ],
    },
    {
        "id": "crypto_assets",
        "question": "Which crypto assets interest you?",
        "category": "preferences",
        "multiple": True,
        "conditional_on": {"asset_classes": "crypto"},
        "options": [
            {"value": "btc",         "label": "Bitcoin (BTC)"},
            {"value": "eth",         "label": "Ethereum (ETH)"},
            {"value": "sol",         "label": "Solana (SOL)"},
            {"value": "stablecoins", "label": "Stablecoins (USDT/USDC)"},
        ],
    },
    {
        "id": "fixed_income_products",
        "question": "Which fixed income products interest you?",
        "category": "preferences",
        "multiple": True,
        "conditional_on": {"asset_classes": "fixed_income"},
        "options": [
            {"value": "tbills",     "label": "T-Bills (3/6/12 month)"},
            {"value": "pibs",       "label": "PIBs (3–10 year)"},
            {"value": "sukuk",      "label": "Sukuk (Shariah-compliant)"},
            {"value": "corp_bonds", "label": "Corporate Bonds/TFCs"},
        ],
    },
    {
        "id": "psx_sectors",
        "question": "Which PSX sectors interest you?",
        "category": "preferences",
        "multiple": True,
        "conditional_on": {"asset_classes": "psx"},
        "options": [
            {"value": "banking",    "label": "Banking (HBL, UBL, MCB)"},
            {"value": "oil_gas",    "label": "Oil & Gas (OGDC, PPL)"},
            {"value": "cement",     "label": "Cement (LUCK, DGKC)"},
            {"value": "fertilizer", "label": "Fertilizer (EFERT, FFC)"},
            {"value": "tech",       "label": "Technology (TRG, NETSOL)"},
            {"value": "pharma",     "label": "Pharmaceuticals (GLAXO)"},
            {"value": "power",      "label": "Power (KEL, HUBCO)"},
            {"value": "textile",    "label": "Textile & Export (NML)"},
        ],
    },
]


# ── Scoring ─────────────────────────────────────────────────────────────────

SCORING_WEIGHTS = {
    "risk_willingness": 35,
    "loss_tolerance":   25,
    "horizon":          15,
    "experience":       10,
    "goal":              5,
    # contribution_consistency scored inline below
}

SCORE_MAPS = {
    "goal":            {"preserve": 0, "income": 10, "growth": 50, "appreciation": 85, "target": 40},
    "horizon":         {"1y": 0, "1_3y": 20, "3_5y": 45, "5_10y": 75, "10y_plus": 100},
    "risk_willingness":{"sell_all": 0, "sell_some": 30, "hold": 65, "buy_more": 100},
    "loss_tolerance":  {"5pct": 0, "10pct": 33, "15pct": 66, "25pct_plus": 100},
    "experience":      {"none": 0, "limited": 25, "moderate": 55, "extensive": 80},
}

PERSONA_THRESHOLDS = [
    (0,  20, "Conservative Saver",  "conservative"),
    (21, 40, "Cautious Investor",   "moderately_conservative"),
    (41, 60, "Balanced Investor",   "moderate"),
    (61, 80, "Growth Seeker",       "aggressive"),
    (81, 100,"Aggressive Trader",   "very_aggressive"),
]


def _contribution_consistency_score(answers: Dict[str, Any]) -> int:
    """10% weight: rewards regular monthly investing habits."""
    freq = answers.get("investment_frequency", "one_time")
    if freq == "one_time":
        return 0
    if freq == "annually":
        return 25
    if freq == "quarterly":
        return 50

    # monthly — scale by contribution-to-capital ratio
    try:
        capital = Decimal(str(answers.get("initial_capital", 0) or 0))
        contrib = Decimal(str(answers.get("monthly_contribution", 0) or 0))
        if capital > 0 and contrib > 0:
            ratio = float(contrib / capital)
            return min(100, int(ratio * 600))  # 5% monthly → score ≈ 30; 10% → 60; 16% → 100
    except Exception:
        pass
    return 40  # monthly with unknown amount → moderate


def _compute_score(answers: Dict[str, Any]) -> int:
    total = 0
    max_possible = sum(SCORING_WEIGHTS.values()) + 10  # +10 for contribution_consistency

    for q_id, weight in SCORING_WEIGHTS.items():
        smap = SCORE_MAPS.get(q_id, {})
        val = answers.get(q_id, "")
        if isinstance(val, str) and val in smap:
            total += int((smap[val] / 100) * weight)

    # Contribution consistency (10%)
    total += int((_contribution_consistency_score(answers) / 100) * 10)

    return round((total / max_possible) * 100) if max_possible else 50


def _classify_persona(score: int) -> tuple[str, str]:
    for lo, hi, persona, risk in PERSONA_THRESHOLDS:
        if lo <= score <= hi:
            return persona, risk
    return "Balanced Investor", "moderate"


def _build_investment_preferences(answers: Dict[str, Any]) -> Dict[str, Any]:
    asset_classes = answers.get("asset_classes", [])
    if not isinstance(asset_classes, list):
        asset_classes = []

    shariah = "shariah" in asset_classes
    classes = [c for c in asset_classes if c != "shariah"]

    return {
        "shariah": shariah,
        "asset_classes": classes,
        "psx_sectors": answers.get("psx_sectors", []) if "psx" in classes else [],
        "crypto_assets": answers.get("crypto_assets", []) if "crypto" in classes else [],
        "fixed_income_products": answers.get("fixed_income_products", []) if "fixed_income" in classes else [],
    }


def _generate_agent_remarks(
    persona: str,
    risk_score: int,
    answers: Dict[str, Any],
    prefs: Dict[str, Any],
) -> Dict[str, str]:
    remarks: Dict[str, str] = {}

    if risk_score < 25:
        remarks["risk"] = f"Score {risk_score}/100 — conservative. Focus on T-bills and blue-chip PSX stocks for capital preservation."
    elif risk_score < 55:
        remarks["risk"] = f"Score {risk_score}/100 — balanced. A mix of equities, fixed income, and gold suits your profile."
    else:
        remarks["risk"] = f"Score {risk_score}/100 — growth-oriented. You can accept higher volatility for long-term returns."

    asset_classes = prefs.get("asset_classes", [])

    if "crypto" in asset_classes and risk_score < 30:
        remarks["warning"] = "Your conservative risk score conflicts with crypto exposure. Consider capping crypto at 1–2%."

    if "fixed_income" in asset_classes:
        remarks["fixed_income"] = "T-bills and Sukuk provide stable, Shariah-compliant yields anchored to the SBP policy rate."

    if prefs.get("shariah"):
        remarks["shariah"] = "Shariah-compliant filter applied. Only KMI-30 index and Sukuk instruments will be eligible."

    freq = answers.get("investment_frequency", "one_time")
    if freq in ("monthly", "quarterly"):
        remarks["contribution"] = "Regular contributions enable rupee-cost averaging — a key advantage in volatile markets."

    return remarks


def _generate_recommendations(
    risk_score: int,
    answers: Dict[str, Any],
    prefs: Dict[str, Any],
) -> Dict[str, Any]:
    asset_classes = prefs.get("asset_classes", [])
    has_crypto = "crypto" in asset_classes
    has_fi = "fixed_income" in asset_classes
    has_gold = "gold" in asset_classes
    has_psx = "psx" in asset_classes or not asset_classes  # default to psx if nothing selected

    crypto_pct = 0
    if has_crypto:
        if risk_score >= 70:
            crypto_pct = 15
        elif risk_score >= 50:
            crypto_pct = 7
        else:
            crypto_pct = 2

    gold_pct = 0
    if has_gold:
        gold_pct = 5 if risk_score >= 50 else 10

    fi_pct = 0
    if has_fi:
        fi_pct = max(10, min(50, 80 - risk_score))

    equity_pct = max(10, 100 - crypto_pct - gold_pct - fi_pct)

    total = equity_pct + fi_pct + gold_pct + crypto_pct
    if total > 0:
        equity_pct = round(equity_pct / total * 100)
        fi_pct = round(fi_pct / total * 100)
        gold_pct = round(gold_pct / total * 100)
        crypto_pct = 100 - equity_pct - fi_pct - gold_pct  # absorb rounding

    action_items = [
        f"Start with {'T-bills' if fi_pct > equity_pct else 'PSX index funds or ETFs'} as your first investment.",
        "Set up automatic contributions to build your portfolio systematically.",
        "Review and rebalance quarterly based on market conditions and SBP rate decisions.",
    ]

    return {
        "suggested_allocation": {
            "pakistan_equity": equity_pct,
            "fixed_income": fi_pct,
            "commodities": gold_pct,
            "crypto": crypto_pct,
        },
        "action_items": action_items,
    }


def evaluate_questionnaire(answers: Dict[str, Any]) -> Dict[str, Any]:
    risk_score = _compute_score(answers)
    persona, risk_tolerance = _classify_persona(risk_score)

    horizon_raw = answers.get("horizon", "3_5y")
    horizon_map = {"1y": "short", "1_3y": "short", "3_5y": "medium", "5_10y": "long", "10y_plus": "long"}
    horizon_val = horizon_map.get(horizon_raw, "medium")

    goal_raw = answers.get("goal", "growth")
    goal_map = {"preserve": "preservation", "income": "income", "growth": "growth", "appreciation": "growth", "target": "growth"}
    goal_val = goal_map.get(goal_raw, "growth")

    if horizon_val == "long" and goal_val == "growth":
        mode_val = "long_term"
    elif risk_score < 30:
        mode_val = "capital_preservation"
    elif risk_score < 60:
        mode_val = "balanced"
    else:
        mode_val = "maximum_growth"

    prefs = _build_investment_preferences(answers)
    recs = _generate_recommendations(risk_score, answers, prefs)
    remarks = _generate_agent_remarks(persona, risk_score, answers, prefs)

    constraints: Dict[str, Any] = {}
    excluded = answers.get("excluded_sectors", [])
    if isinstance(excluded, list):
        # Drop the "none" sentinel, then only record constraints if anything
        # real remains — ["none"] (or all-None) must yield no constraint key
        # at all, not an empty list.
        filtered = [s for s in excluded if s and s != "none"]
        if filtered:
            constraints["excluded_sectors"] = filtered
    liquidity = answers.get("liquidity", "none")
    if liquidity and liquidity != "none":
        constraints["liquidity_needs"] = liquidity

    return {
        "risk_tolerance":        risk_tolerance,
        "horizon":               horizon_val,
        "investor_mode":         mode_val,
        "goal":                  goal_val,
        "constraints":           constraints,
        "investor_persona":      persona,
        "risk_score":            risk_score,
        "investment_preferences": prefs,
        "agent_remarks":         remarks,
        "recommendations":       recs,
    }
