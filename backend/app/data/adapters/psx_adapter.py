"""
Asaas (اثاثہ) — PSX Equity History Adapter

Daily OHLCV history for PSX-listed shares (symbols like ``HBL.KA`` / ``HBL``),
used by the price backfill. Waterfall, each tier fail-open:

  1. PSX DPS timeseries  (dps.psx.com.pk EOD JSON — close + volume)
  2. psx-data-reader     (the `psx` package — full OHLCV)
  3. yfinance .KAR       (last resort, sparse/slow)

Returns ``[{price_date, open, high, low, close, volume}]`` oldest→newest, all
Decimals; empty list when every tier fails (never raises). Money = Decimal.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx

logger = logging.getLogger("asaas.psx_adapter")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _base_symbol(symbol: str) -> str:
    """`HBL.KA` → `HBL` (PSX-native symbol used by DPS / psx-data-reader)."""
    return symbol.strip().upper().replace(".KA", "")


def _dec(v: Any) -> Decimal | None:
    try:
        if v is None:
            return None
        return Decimal(str(round(float(v), 6)))
    except (InvalidOperation, TypeError, ValueError):
        return None


class PSXAdapter:
    """Daily OHLCV history for PSX equities (waterfall sourcing)."""

    async def fetch_history(self, symbol: str, years: int = 2) -> List[Dict[str, Any]]:
        base = _base_symbol(symbol)

        rows = await self._from_dps(base)
        if rows:
            logger.info("PSX history for %s from DPS (%d bars)", base, len(rows))
            return rows

        rows = await self._from_psx_reader(base, years)
        if rows:
            logger.info("PSX history for %s from psx-data-reader (%d bars)", base, len(rows))
            return rows

        # Last resort: yfinance .KAR (Yahoo Finance PSX suffix)
        try:
            from app.data.adapters.yfinance_adapter import YFinanceAdapter
            rows = await YFinanceAdapter().fetch_history(f"{base}.KAR", period=f"{years}y")
            if rows:
                logger.info("PSX history for %s from yfinance .KAR (%d bars)", base, len(rows))
                return rows
        except Exception as exc:
            logger.warning("yfinance .KAR fallback failed for %s: %s", base, exc)

        logger.warning("No PSX history for %s from any source", base)
        return []

    async def _from_dps(self, base: str) -> List[Dict[str, Any]]:
        """PSX DPS EOD timeseries: JSON {data: [[unix_s, close, volume], ...]}.
        Close + volume only (OHL left None; the DB loader fills from close)."""
        url = f"https://dps.psx.com.pk/timeseries/eod/{base}"
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=_HEADERS)
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])
            out: Dict[date, Dict[str, Any]] = {}
            for entry in data:
                if not entry or len(entry) < 2:
                    continue
                ts, close = entry[0], entry[1]
                vol = entry[2] if len(entry) > 2 else None
                d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
                c = _dec(close)
                if c is None:
                    continue
                out[d] = {
                    "price_date": d, "open": None, "high": None, "low": None,
                    "close": c, "volume": int(vol) if vol is not None else None,
                }
            return [out[d] for d in sorted(out)]
        except Exception as exc:
            logger.warning("PSX DPS timeseries failed for %s: %s", base, exc)
            return []

    async def _from_psx_reader(self, base: str, years: int) -> List[Dict[str, Any]]:
        """psx-data-reader (`psx` package). Blocking → executor. Full OHLCV."""
        def _blocking() -> List[Dict[str, Any]]:
            try:
                from psx import stocks  # type: ignore
            except Exception:
                return []
            end = date.today()
            start = end - timedelta(days=365 * years + 5)
            df = stocks(base, start=start, end=end)
            if df is None or df.empty:
                return []
            rows: List[Dict[str, Any]] = []
            for idx, row in df.iterrows():
                d = idx.date() if hasattr(idx, "date") else None
                close = _dec(row.get("Close"))
                if d is None or close is None:
                    continue
                vol = row.get("Volume")
                rows.append({
                    "price_date": d,
                    "open": _dec(row.get("Open")),
                    "high": _dec(row.get("High")),
                    "low": _dec(row.get("Low")),
                    "close": close,
                    "volume": int(vol) if vol is not None and str(vol) != "nan" else None,
                })
            return rows

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _blocking)
        except Exception as exc:
            logger.warning("psx-data-reader failed for %s: %s", base, exc)
            return []
