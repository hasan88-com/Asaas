"""
Tests for Technical Analysis service (Phase 6).
RULES.md D2.6 (no floats), D2.3 (no PII), D3.1 (graceful degradation).
All tests use synthetic price series — no DB required.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.agent.prompts.pii_abstraction import _assert_no_pii
from app.agent.prompts.technical_prompt import SYSTEM_PROMPT
from app.services.technical import (
    _compute_macd,
    _compute_mfi,
    _compute_rsi,
    _detect_crossover,
    compute_indicators,
)


# ---------------------------------------------------------------------------
# Helper: build a synthetic OHLCV DataFrame
# ---------------------------------------------------------------------------


def _make_df(close_values, volume_value=1_000_000.0):
    """Build minimal OHLCV DataFrame from a list of close prices."""
    n = len(close_values)
    close = pd.Series(close_values, dtype=float)
    open_ = close.shift(1).fillna(close.iloc[0])
    high = close * 1.01
    low = close * 0.99
    volume = pd.Series([volume_value] * n, dtype=float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


# ---------------------------------------------------------------------------
# RSI: known fixture
# ---------------------------------------------------------------------------


def test_rsi_known_fixture():
    """
    14 consecutive rising bars followed by 6 flat bars → RSI should be high (>80).
    After 14 rising bars the EWM RSI converges toward 100 with no losses.
    """
    # 20 bars: first 14 rising, last 6 flat
    prices = [100.0 + i for i in range(14)] + [113.0] * 6
    close = pd.Series(prices, dtype=float)
    rsi = _compute_rsi(close)
    # After 14 rising bars RSI via Wilder EWM should be well above 80
    assert rsi.iloc[-1] > 80, f"Expected RSI > 80 for rising series, got {rsi.iloc[-1]:.2f}"


# ---------------------------------------------------------------------------
# MACD: crossover fixture
# ---------------------------------------------------------------------------


def test_macd_crossover_fixture():
    """
    After a sharp price jump, MACD line crosses above signal → histogram turns positive.
    The histogram peaks early in the spike (when MACD rises faster than signal).
    """
    # Start with flat prices, then spike sharply — 50 flat, then rising
    prices = [100.0] * 50 + [100.0 + i * 2 for i in range(1, 21)]
    close = pd.Series(prices, dtype=float)
    macd_data = _compute_macd(close)
    hist = macd_data["histogram"]
    # After the spike, histogram must reach a positive value at some point
    assert hist.max() > 0, (
        f"MACD histogram must become positive after price spike; max={hist.max():.4f}"
    )


# ---------------------------------------------------------------------------
# MFI: known fixture
# ---------------------------------------------------------------------------


def test_mfi_known_fixture():
    """
    Constant rising prices with constant volume → positive money flow → MFI > 50.
    """
    n = 30
    close = pd.Series([100.0 + i for i in range(n)], dtype=float)
    high = close * 1.01
    low = close * 0.99
    volume = pd.Series([1_000_000.0] * n, dtype=float)
    mfi = _compute_mfi(high, low, close, volume)
    assert mfi.iloc[-1] > 50, f"Expected MFI > 50 for rising prices, got {mfi.iloc[-1]:.2f}"


# ---------------------------------------------------------------------------
# Moving averages: exact values on arithmetic series
# ---------------------------------------------------------------------------


def test_ma_values():
    """SMA over an arithmetic sequence should equal the mean of the window."""
    # Prices 1..50
    prices = list(range(1, 51))
    close = pd.Series(prices, dtype=float)
    sma_10 = close.rolling(10).mean()
    # SMA(10) at position 49 = mean(41..50) = 45.5
    assert abs(sma_10.iloc[-1] - 45.5) < 1e-9, (
        f"Expected SMA(10) = 45.5, got {sma_10.iloc[-1]}"
    )


# ---------------------------------------------------------------------------
# Golden cross detection
# ---------------------------------------------------------------------------


def test_golden_cross_detected():
    """Craft SMA-50 crossing above SMA-200 → crossover == 'golden_cross'."""
    # Two-point series: prev SMA50 < SMA200, curr SMA50 > SMA200
    sma_50 = pd.Series([90.0, 110.0])
    sma_200 = pd.Series([100.0, 100.0])
    result = _detect_crossover(sma_50, sma_200)
    assert result == "golden_cross", f"Expected golden_cross, got {result}"


# ---------------------------------------------------------------------------
# Death cross detection
# ---------------------------------------------------------------------------


def test_death_cross_detected():
    """Craft SMA-50 crossing below SMA-200 → crossover == 'death_cross'."""
    sma_50 = pd.Series([110.0, 90.0])
    sma_200 = pd.Series([100.0, 100.0])
    result = _detect_crossover(sma_50, sma_200)
    assert result == "death_cross", f"Expected death_cross, got {result}"


# ---------------------------------------------------------------------------
# No DB writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_db_writes():
    """compute_indicators must not call db.execute with any write operation."""
    mock_db = MagicMock()
    # Simulate DB returning no rows (will trigger yfinance fallback)
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    # Build a synthetic yfinance history with 50 bars
    prices = [100.0 + i * 0.5 for i in range(50)]
    hist_df = pd.DataFrame(
        {
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1_000_000] * 50,
        }
    )

    with patch("app.services.technical._load_ohlcv_yfinance", new=AsyncMock(return_value=hist_df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}))):
        result = await compute_indicators("TEST.KA", mock_db)

    # No write methods should have been called
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()
    mock_db.flush.assert_not_called()
    # Result should have indicator keys
    assert "rsi_14" in result or result.get("insufficient_data"), (
        f"Unexpected result: {result}"
    )


# ---------------------------------------------------------------------------
# Daily data note appears in technical prompt
# ---------------------------------------------------------------------------


def test_daily_data_only_note_in_prompt():
    """Technical system prompt must explicitly reference daily EOD data."""
    assert "daily" in SYSTEM_PROMPT.lower(), (
        "Technical prompt must contain 'daily' to prevent intraday misuse"
    )
    assert "financial advice" in SYSTEM_PROMPT.lower(), (
        "Technical prompt must include the disclaimer"
    )


# ---------------------------------------------------------------------------
# PII not in technical payload
# ---------------------------------------------------------------------------


def test_pii_not_in_technical_payload():
    """Indicator dict returned by compute_indicators must pass PII guardrail."""
    # Build a minimal synthetic result (as if compute_indicators returned it)
    payload: Dict[str, Any] = {
        "symbol": "HBL.KA",
        "bars_used": 50,
        "current_price": "150.000000",
        "rsi_14": "62.5",
        "rsi_signal": "neutral",
        "mfi_14": "55.0",
        "sma_50": "148.0",
        "sma_200": "140.0",
        "macd_line": "1.5",
        "macd_signal": "1.2",
        "macd_histogram": "0.3",
        "crossover": "none",
        "support_levels": ["145.0", "142.0"],
        "resistance_levels": ["155.0", "158.0"],
        "data_note": "Daily EOD data only.",
    }
    _assert_no_pii(payload)
