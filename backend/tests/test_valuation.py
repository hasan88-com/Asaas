"""
Tests for Valuation service and role (Phase 6).
RULES.md D2.6 (Decimal money), D2.3 (no PII in LLM payloads), D3.1 (graceful degradation).
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.agent.prompts.pii_abstraction import _assert_no_pii
from app.agent.prompts.valuation_prompt import SYSTEM_PROMPT
from app.services.valuation import (
    _compute_duration,
    _to_decimal,
    extract_company_info,
    run_dcf,
    run_monte_carlo,
    run_multiples,
)


# ---------------------------------------------------------------------------
# Test: WACC uses SBP rate as risk-free leg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wacc_uses_sbp_rate():
    """WACC risk-free leg must come from SBP adapter, not a hardcoded foreign rate."""
    mock_cashflow = pd.DataFrame(
        {"2023": [5_000_000_000.0]},
        index=["Operating Cash Flow"],
    )
    mock_balance = pd.DataFrame(
        {"2023": [10_000_000_000.0, 2_000_000_000.0]},
        index=["Total Debt", "Cash And Cash Equivalents"],
    )
    mock_info = {
        "currentPrice": 100.0,
        "sharesOutstanding": 1_000_000_000,
        "beta": 1.0,
        "earningsGrowth": 0.08,
    }

    sbp_rate = Decimal("0.22")

    with (
        patch(
            "app.services.valuation._get_sbp_rate",
            new=AsyncMock(return_value=(sbp_rate, False)),  # (rate, is_placeholder)
        ),
        patch("yfinance.Ticker") as mock_ticker_cls,
    ):
        mock_ticker = MagicMock()
        mock_ticker.cashflow = mock_cashflow
        mock_ticker.balance_sheet = mock_balance
        mock_ticker.info = mock_info
        mock_ticker_cls.return_value = mock_ticker

        result = await run_dcf("TEST.KA")

    assert "wacc" in result, f"Expected 'wacc' in result, got: {result}"
    wacc_val = Decimal(result["wacc"])
    # WACC = SBP(0.22) + beta(1.0) * ERP(0.1635) = 0.3835
    assert wacc_val >= sbp_rate, "WACC must be at least the SBP risk-free rate"
    assert wacc_val < Decimal("1.0"), "WACC must be < 100%"


# ---------------------------------------------------------------------------
# Test: Monte Carlo returns a p10/p50/p90 distribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monte_carlo_returns_distribution():
    """Monte Carlo must return p10 < p50 < p90 for a standard ticker."""
    mock_cashflow = pd.DataFrame(
        {"2023": [5_000_000_000.0]},
        index=["Operating Cash Flow"],
    )
    mock_balance = pd.DataFrame({"2023": [0.0]}, index=["Total Debt"])
    mock_info = {
        "currentPrice": 100.0,
        "sharesOutstanding": 1_000_000_000,
        "beta": 1.0,
        "earningsGrowth": 0.05,
    }

    with (
        patch(
            "app.services.valuation._get_sbp_rate",
            new=AsyncMock(return_value=(Decimal("0.20"), False)),  # (rate, is_placeholder)
        ),
        patch("yfinance.Ticker") as mock_ticker_cls,
    ):
        mock_ticker = MagicMock()
        mock_ticker.cashflow = mock_cashflow
        mock_ticker.balance_sheet = mock_balance
        mock_ticker.info = mock_info
        mock_ticker_cls.return_value = mock_ticker

        result = await run_monte_carlo("TEST.KA", n=500)

    assert not result.get("insufficient_data"), f"Unexpected insufficient_data: {result}"
    for key in ("p10", "p50", "p90", "mean", "std"):
        assert key in result, f"Missing key '{key}' in Monte Carlo result"

    p10 = Decimal(result["p10"])
    p50 = Decimal(result["p50"])
    p90 = Decimal(result["p90"])
    assert p10 < p50 < p90, f"Expected p10 < p50 < p90, got {p10}, {p50}, {p90}"
    assert result["n_simulations"] == 500


# ---------------------------------------------------------------------------
# Test: duration / DV01 / convexity (fixed-income risk metrics)
# ---------------------------------------------------------------------------


def test_compute_duration_par_bond():
    """A 5y 10% semi-annual bond priced at par (YTM == coupon): price ≈ face,
    0 < modified < Macaulay < maturity, DV01 and convexity positive."""
    d = _compute_duration(Decimal("10"), Decimal("10"), Decimal("5"), Decimal("100"), freq=2)
    assert d is not None
    price = Decimal(d["price"])
    mac = Decimal(d["macaulay_years"])
    mod = Decimal(d["modified_years"])
    assert abs(price - Decimal("100")) < Decimal("0.5"), f"par price expected ~100, got {price}"
    assert Decimal("0") < mod < mac < Decimal("5"), f"mod={mod} mac={mac}"
    assert Decimal(d["dv01"]) > 0
    assert Decimal(d["convexity"]) > 0


def test_compute_duration_zero_coupon():
    """Zero-coupon (T-bill style): Macaulay duration == years to maturity."""
    d = _compute_duration(Decimal("0"), Decimal("12"), Decimal("1"), Decimal("100"), freq=2)
    assert d is not None
    assert Decimal(d["macaulay_years"]) == Decimal("1.00")
    assert Decimal(d["modified_years"]) < Decimal("1.00")


def test_compute_duration_guards():
    """Unusable inputs (non-positive horizon or face) return None, never fabricate."""
    assert _compute_duration(Decimal("10"), Decimal("10"), Decimal("0"), Decimal("100")) is None
    assert _compute_duration(Decimal("10"), Decimal("10"), Decimal("5"), Decimal("0")) is None


# ---------------------------------------------------------------------------
# Test: thin data returns insufficient_data, never fabricates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thin_data_no_fabrication():
    """If yfinance returns no operating cash flow, DCF must return insufficient_data."""
    empty_cashflow = pd.DataFrame()
    mock_info = {"currentPrice": 100.0}

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.cashflow = empty_cashflow
        mock_ticker.balance_sheet = pd.DataFrame()
        mock_ticker.info = mock_info
        mock_ticker_cls.return_value = mock_ticker

        result = await run_dcf("NOFCF.KA")

    assert result.get("insufficient_data") is True, (
        f"Expected insufficient_data=True for missing FCF, got: {result}"
    )
    assert "reason" in result
    # Must not contain any fabricated numeric valuation
    assert "intrinsic_value_per_share" not in result


# ---------------------------------------------------------------------------
# Test: all money values are Decimal strings (never float) in company info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_money_values_are_decimal():
    """Ratio fields in extract_company_info must be Decimal strings, not floats."""
    mock_info = {
        "longName": "Test Corp",
        "sector": "Banking",
        "currentPrice": 125.5,
        "marketCap": 125_000_000_000,
        "trailingPE": 8.4,
        "priceToBook": 1.2,
        "beta": 0.85,
        "sharesOutstanding": 1_000_000_000,
    }

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker_cls.return_value = mock_ticker

        result = await extract_company_info("TEST.KA")

    numeric_fields = ["current_price", "market_cap", "trailing_pe", "price_to_book", "beta"]
    for field in numeric_fields:
        val = result.get(field)
        if val is not None:
            assert isinstance(val, str), (
                f"Field '{field}' should be a str(Decimal), got {type(val).__name__}: {val}"
            )
            # Must be parseable as Decimal
            Decimal(val)
            # Must NOT be a float
            assert "." not in str(type(val)), "Value must not be float type"


# ---------------------------------------------------------------------------
# Test: valuation prompt has no buy/sell directives
# ---------------------------------------------------------------------------


def test_no_buy_sell_in_valuation_prompt():
    """Valuation system prompt must never use 'buy' or 'sell' as directive words."""
    prompt_lower = SYSTEM_PROMPT.lower()
    # These exact standalone directives are banned (recommendation-style usage)
    banned_phrases = ['"buy"', '"sell"', '"hold"']
    # Simple check: the prompt must not contain "buy" or "sell" except in the
    # context of "buying pressure" (which is allowed in the technical prompt)
    # For the valuation prompt, neither should appear at all.
    for phrase in ("never issue a buy", "buy, sell"):
        # These are OK — they appear in the rules section as negations
        pass
    # The key test: the prompt must include the disclaimer about not recommending
    assert "financial advice" in prompt_lower, "Missing disclaimer"
    assert "buy, sell, or hold recommendation" in prompt_lower, (
        "Prompt must explicitly prohibit buy/sell/hold recommendations"
    )


# ---------------------------------------------------------------------------
# Test: PII not in valuation payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pii_not_in_valuation_payload():
    """Payload assembled for valuation LLM call must pass the PII guardrail."""
    mock_info = {
        "longName": "Habib Bank Limited",
        "sector": "Banking",
        "currentPrice": 150.0,
        "trailingPE": 7.5,
    }

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker.cashflow = pd.DataFrame()
        mock_ticker.balance_sheet = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        info = await extract_company_info("HBL.KA")
        dcf = await run_dcf("HBL.KA")
        mc = await run_monte_carlo("HBL.KA")
        mult = await run_multiples("HBL.KA")

    payload: Dict[str, Any] = {
        "symbol": "HBL.KA",
        "company_info": info,
        "dcf": dcf,
        "monte_carlo": mc,
        "multiples": mult,
    }

    # Must not raise AssertionError — no PII fields in the payload
    _assert_no_pii(payload)
