"""
Asaas (اثاثہ) — Yahoo Finance Adapter

Fetches EOD and live prices for stocks (global + PSX suffix .KA) and commodities.
Uses Decimal for precision, handles errors, retries (RULES.md A1.6, A2.6, A3.5).
"""

from __future__ import annotations

import logging
import asyncio
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from datetime import date, datetime, timezone

import pandas as pd
import yfinance as yf

logger = logging.getLogger("asaas.yfinance_adapter")


class YFinanceAdapter:
    """Adapter for interacting with Yahoo Finance."""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def fetch_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch the current/latest close price of an asset.
        Runs the blocking yfinance calls in an executor.
        """
        for attempt in range(self.max_retries):
            try:
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(None, self._get_ticker_data, symbol)
                if data:
                    return data
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        logger.error(f"Failed to fetch price for {symbol} after {self.max_retries} attempts.")
        return None

    async def fetch_price_with_change(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch current price AND previous day's close for day-over-day change.
        Returns dict with 'price', 'prev_close', 'price_date', 'source'.
        Falls back to single-day data if 2-day fetch fails.
        """
        for attempt in range(self.max_retries):
            try:
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(None, self._get_ticker_data_2d, symbol)
                if data:
                    return data
            except Exception as e:
                logger.warning(f"2d attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        # Fallback: single-day data (no prev_close)
        single = await self.fetch_price(symbol)
        if single:
            single["prev_close"] = None
        return single

    async def fetch_history(self, symbol: str, period: str = "2y") -> List[Dict[str, Any]]:
        """Daily OHLCV history (oldest→newest) for backfill.

        Returns [{price_date, open, high, low, close, volume}] as Decimals;
        empty list on failure (never raises). Used for commodities (=F), global
        stocks, ^KSE, and as the last-resort PSX .KA fallback.
        """
        for attempt in range(self.max_retries):
            try:
                loop = asyncio.get_running_loop()
                rows = await loop.run_in_executor(None, self._get_history, symbol, period)
                if rows:
                    return rows
            except Exception as e:
                logger.warning("history attempt %d failed for %s: %s", attempt + 1, symbol, e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        logger.warning("No yfinance history for %s after %d attempts", symbol, self.max_retries)
        return []

    def _get_history(self, symbol: str, period: str) -> List[Dict[str, Any]]:
        """Blocking call — daily OHLCV bars."""
        hist = yf.Ticker(symbol).history(period=period, interval="1d")
        if hist is None or hist.empty:
            return []

        def _dec(v) -> Optional[Decimal]:
            return None if v is None or pd.isna(v) else Decimal(str(round(float(v), 6)))

        out: List[Dict[str, Any]] = []
        for idx, row in hist.iterrows():
            d = idx.date() if hasattr(idx, "date") else None
            close = _dec(row.get("Close"))
            if d is None or close is None:
                continue
            vol = row.get("Volume")
            out.append({
                "price_date": d,
                "open": _dec(row.get("Open")),
                "high": _dec(row.get("High")),
                "low": _dec(row.get("Low")),
                "close": close,
                "volume": int(vol) if vol is not None and not pd.isna(vol) else None,
            })
        return out

    def _get_ticker_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Blocking call — single day data."""
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        if hist.empty:
            fast_info = ticker.fast_info
            price = fast_info.get("last_price")
            if price is not None:
                return {
                    "price": Decimal(str(round(price, 6))),
                    "open": None,
                    "high": None,
                    "low": None,
                    "volume": None,
                    "price_date": date.today(),
                    "source": "yfinance_fast",
                }
            return None

        last_row = hist.iloc[-1]
        price_date = last_row.name.date() if hasattr(last_row.name, "date") else date.today()

        return {
            "price": Decimal(str(round(last_row["Close"], 6))),
            "open": Decimal(str(round(last_row["Open"], 6))) if "Open" in last_row else None,
            "high": Decimal(str(round(last_row["High"], 6))) if "High" in last_row else None,
            "low": Decimal(str(round(last_row["Low"], 6))) if "Low" in last_row else None,
            "volume": int(last_row["Volume"]) if "Volume" in last_row else None,
            "price_date": price_date,
            "source": "yfinance_hist",
        }

    def _get_ticker_data_2d(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Blocking call — fetch 2 days of history to compute day-over-day change.
        Returns the latest close + the previous day's close.
        """
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")  # fetch 5d to ensure we get 2 trading days

        if hist.empty:
            # Fall back to fast_info (no prev_close available)
            fast_info = ticker.fast_info
            price = fast_info.get("last_price")
            if price is not None:
                return {
                    "price": Decimal(str(round(price, 6))),
                    "prev_close": None,
                    "price_date": date.today(),
                    "source": "yfinance_fast",
                }
            return None

        if len(hist) < 2:
            # Only one trading day available
            last_row = hist.iloc[-1]
            price_date = last_row.name.date() if hasattr(last_row.name, "date") else date.today()
            return {
                "price": Decimal(str(round(last_row["Close"], 6))),
                "prev_close": None,
                "price_date": price_date,
                "source": "yfinance_hist",
            }

        last_row = hist.iloc[-1]
        prev_row = hist.iloc[-2]
        price_date = last_row.name.date() if hasattr(last_row.name, "date") else date.today()

        return {
            "price": Decimal(str(round(last_row["Close"], 6))),
            "prev_close": Decimal(str(round(prev_row["Close"], 6))),
            "price_date": price_date,
            "source": "yfinance_hist",
        }
