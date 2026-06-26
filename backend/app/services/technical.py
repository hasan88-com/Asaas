"""
Asaas (اثاثہ) — Technical Analysis Service

Computes indicator set on daily EOD OHLCV data (AGENT_RULES.md §6c, §8.3).
Data source: `prices` DB table first; fallback to yfinance history if DB is thin.
All functions are read-only — no DB writes. Daily candles only, no intraday.
All scalar outputs are Decimal; series are list[Decimal] (last 50 values).
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.price import Price

logger = logging.getLogger("asaas.services.technical")

# Crypto symbols are stored bare (BTC) but yfinance needs the USD spot pair
# (BTC-USD) — that pair is the original spot price, not an ETF.
_CRYPTO_YF_TICKER = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
    "BNB": "BNB-USD", "XRP": "XRP-USD", "ADA": "ADA-USD", "DOGE": "DOGE-USD",
}

_MIN_BARS = 30          # minimum bars needed for any computation
_RSI_PERIOD = 14
_MFI_PERIOD = 14
_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9


def _d(value: Any) -> Decimal:
    """Convert float/numpy scalar to Decimal safely."""
    try:
        if pd.isna(value):
            return Decimal("0")
        return Decimal(str(round(float(value), 6)))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _series_to_decimal(s: pd.Series, tail: int = 50) -> List[str]:
    """Return last `tail` values of a series as list of str(Decimal)."""
    return [str(_d(v)) for v in s.tail(tail).tolist()]


# ---------------------------------------------------------------------------
# Indicator computations (pure pandas/numpy — no TA library)
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series, period: int = _RSI_PERIOD) -> pd.Series:
    """Wilder's RSI using EWM (alpha = 1/period)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Pure uptrend (avg_loss == 0, avg_gain > 0) → RSI = 100, not NaN
    rsi = rsi.where((avg_loss != 0) | (avg_gain == 0), 100.0)
    return rsi.fillna(50.0)


def _compute_mfi(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: int = _MFI_PERIOD,
) -> pd.Series:
    """Money Flow Index (volume-weighted RSI)."""
    tp = (high + low + close) / 3.0
    mf = tp * volume.replace(0, float("nan")).fillna(0)
    tp_diff = tp.diff()
    pos_mf = mf.where(tp_diff > 0, 0.0)
    neg_mf = mf.where(tp_diff < 0, 0.0)
    pos_sum = pos_mf.rolling(period).sum()
    neg_sum = neg_mf.rolling(period).sum()
    mfr = pos_sum / neg_sum.replace(0, float("nan"))
    mfi = 100.0 - (100.0 / (1.0 + mfr))
    # Pure positive flow (neg_sum == 0, pos_sum > 0) → MFI = 100, not NaN
    mfi = mfi.where((neg_sum != 0) | (pos_sum == 0), 100.0)
    return mfi.fillna(50.0)


def _compute_macd(
    close: pd.Series,
    fast: int = _MACD_FAST,
    slow: int = _MACD_SLOW,
    signal: int = _MACD_SIGNAL,
) -> Dict[str, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def _compute_support_resistance(
    close: pd.Series,
    window: int = 10,
    top_n: int = 3,
) -> Dict[str, List[str]]:
    """Detect local minima (support) and maxima (resistance)."""
    if len(close) < window * 2 + 1:
        return {"support_levels": [], "resistance_levels": []}
    roll_min = close.rolling(window, center=True).min()
    roll_max = close.rolling(window, center=True).max()
    support = close[close == roll_min].dropna()
    resistance = close[close == roll_max].dropna()
    s_levels = sorted(support.unique(), reverse=False)[-top_n:]
    r_levels = sorted(resistance.unique(), reverse=True)[:top_n]
    return {
        "support_levels": [str(_d(v)) for v in s_levels],
        "resistance_levels": [str(_d(v)) for v in r_levels],
    }


def _detect_crossover(
    sma_50: pd.Series,
    sma_200: pd.Series,
) -> str:
    """
    Detect golden cross (50 crosses above 200) or death cross (50 crosses below 200).
    Requires at least 2 data points after alignment.
    """
    aligned = pd.concat([sma_50, sma_200], axis=1).dropna()
    aligned.columns = ["sma50", "sma200"]
    if len(aligned) < 2:
        return "none"
    prev_diff = aligned["sma50"].iloc[-2] - aligned["sma200"].iloc[-2]
    curr_diff = aligned["sma50"].iloc[-1] - aligned["sma200"].iloc[-1]
    if prev_diff <= 0 and curr_diff > 0:
        return "golden_cross"
    if prev_diff >= 0 and curr_diff < 0:
        return "death_cross"
    return "none"


def _volume_color(close: pd.Series, open_: pd.Series) -> List[str]:
    """'up' if close >= open, else 'down'. Last 50 bars."""
    colors = ["up" if c >= o else "down" for c, o in zip(close.tail(50), open_.tail(50))]
    return colors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def compute_indicators(
    symbol: str,
    db: AsyncSession,
    periods: int = 200,
    requested: Optional[List[str]] = None,
    rsi_thresholds: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Compute technical indicators for `symbol` on daily EOD data.

    Data source: `prices` DB table → fallback to yfinance history.
    Returns {'insufficient_data': True, 'reason': '...'} if < 30 bars available.
    No DB writes.

    `rsi_thresholds` are the per-asset-class overbought/oversold bounds
    (e.g. crypto uses 80/20 vs the 70/30 default) — see core.capabilities.
    """
    df = await _load_ohlcv(symbol, db, periods)

    if df is None or len(df) < _MIN_BARS:
        # Fallback: yfinance history
        df = await _load_ohlcv_yfinance(symbol)

    if df is None or len(df) < _MIN_BARS:
        return {
            "insufficient_data": True,
            "reason": (
                f"Fewer than {_MIN_BARS} daily bars available for {symbol}. "
                "Run the daily data fetch or seed historical prices first."
            ),
        }

    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].fillna(0).astype(float)

    # Core indicators
    rsi_series = _compute_rsi(close)
    mfi_series = _compute_mfi(high, low, close, volume)
    macd_data = _compute_macd(close)
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()

    # Latest scalar values
    rsi_latest = _d(rsi_series.iloc[-1])
    mfi_latest = _d(mfi_series.iloc[-1])
    macd_latest = _d(macd_data["macd"].iloc[-1])
    signal_latest = _d(macd_data["signal"].iloc[-1])
    hist_latest = _d(macd_data["histogram"].iloc[-1])

    _thr = rsi_thresholds or {"overbought": 70, "oversold": 30}
    _ob = _thr.get("overbought", 70)
    _os = _thr.get("oversold", 30)
    rsi_signal = (
        "overbought" if rsi_latest > _ob
        else "oversold" if rsi_latest < _os
        else "neutral"
    )

    sr = _compute_support_resistance(close)
    crossover = _detect_crossover(sma_50, sma_200)

    # Current price and volume
    current_price = _d(close.iloc[-1])
    current_volume = _d(volume.iloc[-1])

    result: Dict[str, Any] = {
        "symbol": symbol,
        "bars_used": len(df),
        "current_price": str(current_price),
        "current_volume": str(current_volume),
        "volume_color": _volume_color(close, open_),
        # RSI
        "rsi_14": str(rsi_latest),
        "rsi_signal": rsi_signal,
        "rsi_overbought": _ob,
        "rsi_oversold": _os,
        "rsi_series": _series_to_decimal(rsi_series),
        # MFI
        "mfi_14": str(mfi_latest),
        # Moving averages (latest values)
        "sma_20": str(_d(sma_20.iloc[-1])) if not pd.isna(sma_20.iloc[-1]) else None,
        "sma_50": str(_d(sma_50.iloc[-1])) if not pd.isna(sma_50.iloc[-1]) else None,
        "sma_200": str(_d(sma_200.iloc[-1])) if not pd.isna(sma_200.iloc[-1]) else None,
        "ema_20": str(_d(ema_20.iloc[-1])),
        "ema_50": str(_d(ema_50.iloc[-1])),
        "sma_50_series": _series_to_decimal(sma_50.dropna()),
        "sma_200_series": _series_to_decimal(sma_200.dropna()),
        # MACD
        "macd_line": str(macd_latest),
        "macd_signal": str(signal_latest),
        "macd_histogram": str(hist_latest),
        "macd_series": _series_to_decimal(macd_data["macd"]),
        # Support / resistance
        "support_levels": sr["support_levels"],
        "resistance_levels": sr["resistance_levels"],
        # Cross signals
        "crossover": crossover,
        "data_note": "Daily EOD data only — not real-time or intraday.",
    }
    return result


async def _load_ohlcv(symbol: str, db: AsyncSession, periods: int) -> Optional[pd.DataFrame]:
    """Load OHLCV from the prices DB table (daily EOD)."""
    try:
        inst_res = await db.execute(
            select(Instrument).where(Instrument.symbol == symbol)
        )
        instrument = inst_res.scalar_one_or_none()
        if not instrument:
            return None

        prices_res = await db.execute(
            select(
                Price.price_date,
                Price.price,
                Price.open,
                Price.high,
                Price.low,
                Price.volume,
            )
            .where(Price.instrument_id == instrument.id)
            .order_by(Price.price_date.asc())
            .limit(periods)
        )
        rows = prices_res.fetchall()
        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["date", "close", "open", "high", "low", "volume"])
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].fillna(df["close"]).astype(float)
        df["high"] = df["high"].fillna(df["close"]).astype(float)
        df["low"] = df["low"].fillna(df["close"]).astype(float)
        df["volume"] = df["volume"].fillna(0).astype(float)
        df = df.set_index("date").sort_index()
        return df
    except Exception as exc:
        logger.warning("DB OHLCV load failed for %s: %s", symbol, exc)
        return None


async def _load_ohlcv_yfinance(symbol: str, period: str = "2y") -> Optional[pd.DataFrame]:
    """Fallback: load OHLCV from yfinance history. Maps bare crypto tickers to
    their USD spot pair (BTC → BTC-USD) so crypto technicals resolve."""
    try:
        import yfinance as yf

        yf_symbol = _CRYPTO_YF_TICKER.get(symbol.strip().upper(), symbol)

        def _fetch():
            return yf.Ticker(yf_symbol).history(period=period)

        hist = await asyncio.to_thread(_fetch)
        if hist is None or hist.empty:
            return None

        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df = df.sort_index()
        return df
    except Exception as exc:
        logger.warning("yfinance history fallback failed for %s: %s", symbol, exc)
        return None
