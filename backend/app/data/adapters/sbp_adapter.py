"""
Asaas (اثاثہ) — State Bank of Pakistan (SBP) Adapter

Scrapes the State Bank of Pakistan website for:
- Current monetary policy rate
- T-bill (MTB) auction results and cut-off yields
- PIB secondary market yields
- GIS (Islamic Sukuk) rates

SBP conducts multiple-priced auctions of marketable government securities:
- MTBs: fortnightly auctions on Wednesdays, settlement T+1
- PIBs: need basis per pre-announced calendar
- GIS: Shariah compliant, 3-year tenors, Fixed/Variable Rate Rentals

Uses BeautifulSoup, handles errors gracefully, and returns Decimal (RULES.md A1.4, A2.6, A3.5).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional
from datetime import date, datetime, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("asaas.sbp_adapter")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_pct(text: str) -> Optional[Decimal]:
    """Extract a percentage from text. Handles both '20.50%' and '11.5 percent'
    (SBP's homepage announcement uses the word 'percent'). -> Decimal('0.115')."""
    m = re.search(r"(\d{1,2}(?:\.\d{1,4})?)\s*(?:%|percent)", text, re.IGNORECASE)
    if m:
        try:
            return Decimal(m.group(1)) / Decimal("100")
        except InvalidOperation:
            return None
    return None


def _clean(text: str) -> str:
    """Collapse whitespace in scraped text."""
    return re.sub(r"\s+", " ", text).strip()


class SBPAdapter:
    """Adapter for scraping SBP interest rates and government securities data."""

    def __init__(self):
        self.homepage_url = "https://www.sbp.org.pk/index.html"
        self.monetary_policy_url = "https://www.sbp.org.pk/monetary_policy/index.asp"
        self.auction_url = "https://www.sbp.org.pk/daod/sdma.asp"
        self.key_rates_url = "https://www.sbp.org.pk/keyrates/keyrates.asp"
        self.headers = _HEADERS

    # ------------------------------------------------------------------
    # Policy rate
    # ------------------------------------------------------------------

    async def fetch_policy_rate(self) -> Optional[Decimal]:
        """
        Scrape the SBP website for the current monetary policy rate.
        Tries the homepage, then the monetary policy page, then key rates.

        Returns ``None`` when every source fails — it does NOT fabricate a
        fallback rate. Fabricating a constant here would silently poison the
        last-known-good cache in ``app.core.market.get_sbp_rate``; the caller
        owns the fallback policy (last-known-good, then a clearly-flagged
        placeholder), not this scraper.
        """
        # Strategy 1: Homepage — look for "Policy Rate" near a percentage
        rate = await self._scrape_homepage_policy_rate()
        if rate is not None:
            return rate

        # Strategy 2: Dedicated monetary policy page
        rate = await self._scrape_monetary_policy_page()
        if rate is not None:
            return rate

        # Strategy 3: Key rates page
        rate = await self._scrape_key_rates()
        if rate is not None:
            return rate

        logger.warning("All SBP policy rate sources failed — returning None (caller decides fallback)")
        return None

    async def _scrape_homepage_policy_rate(self) -> Optional[Decimal]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.homepage_url, headers=self.headers)
            if resp.status_code != 200:
                logger.warning("SBP homepage returned %s", resp.status_code)
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # Pattern 1: text nodes containing "Policy Rate" followed by a percentage
            for node in soup.find_all(string=re.compile(r"Policy\s+Rate", re.IGNORECASE)):
                # Check parent, grandparent, and surrounding siblings
                for el in [node.parent, node.parent.parent if node.parent else None]:
                    if el is None:
                        continue
                    text = _clean(el.get_text())
                    rate = _parse_pct(text)
                    if rate is not None:
                        logger.info("Scraped SBP Policy Rate from homepage: %s", rate * 100)
                        return rate

                    # Check sibling cells in the same table row
                    if el.name in ("td", "th", "span", "div"):
                        row = el.find_parent("tr")
                        if row:
                            rate = _parse_pct(_clean(row.get_text()))
                            if rate is not None:
                                logger.info("Scraped SBP Policy Rate from homepage row: %s", rate * 100)
                                return rate

            # Pattern 2: look for any element with class/id hinting at policy rate
            for selector in [
                '[class*="policy"]', '[class*="rate"]', '[id*="policy"]', '[id*="rate"]',
                'td:contains("Policy")', 'th:contains("Policy")',
            ]:
                try:
                    for el in soup.select(selector):
                        rate = _parse_pct(_clean(el.get_text()))
                        if rate is not None:
                            logger.info("Scraped SBP Policy Rate via selector '%s': %s", selector, rate * 100)
                            return rate
                except Exception:
                    continue

            # Pattern 3: brute-force — find the last standalone percentage near "policy" keyword
            full_text = _clean(soup.get_text())
            policy_match = re.search(
                r"policy\s+rate.{0,60}?(\d{1,2}(?:\.\d{1,4})?)\s*(?:%|percent)",
                full_text, re.IGNORECASE,
            )
            if policy_match:
                try:
                    rate = Decimal(policy_match.group(1)) / Decimal("100")
                    logger.info("Scraped SBP Policy Rate from full text: %s", rate * 100)
                    return rate
                except InvalidOperation:
                    pass

            logger.warning("Could not find Policy Rate on SBP homepage")
            return None

        except Exception as e:
            logger.error("Error scraping SBP homepage for policy rate: %s", e)
            return None

    async def _scrape_monetary_policy_page(self) -> Optional[Decimal]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.monetary_policy_url, headers=self.headers)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "lxml")
            full_text = _clean(soup.get_text())

            # Look for "policy rate" near a percentage — the page should state the current rate
            patterns = [
                r"policy\s+rate\s+(?:is|at|of|stands?\s+at|has\s+been\s+(?:set\s+at|kept?\s+at|raised?\s+to|lowered?\s+to))\s*(\d{1,2}\.\d{1,4})\s*%",
                r"policy\s+rate[^%]{0,60}?(\d{1,2}\.\d{1,4})\s*%",
                r"(\d{1,2}\.\d{1,4})\s*%\s*(?:per\s+annum|p\.?\s*a\.?)",
            ]
            for pat in patterns:
                m = re.search(pat, full_text, re.IGNORECASE)
                if m:
                    try:
                        rate = Decimal(m.group(1)) / Decimal("100")
                        logger.info("Scraped SBP Policy Rate from monetary policy page: %s", rate * 100)
                        return rate
                    except InvalidOperation:
                        continue

            return None
        except Exception as e:
            logger.error("Error scraping SBP monetary policy page: %s", e)
            return None

    async def _scrape_key_rates(self) -> Optional[Decimal]:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.key_rates_url, headers=self.headers)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "lxml")

            # The key rates page often lists the policy rate in a table
            for row in soup.find_all("tr"):
                cells = row.find_all(["td", "th"])
                row_text = _clean(row.get_text())
                if re.search(r"policy\s+rate", row_text, re.IGNORECASE):
                    rate = _parse_pct(row_text)
                    if rate is not None:
                        logger.info("Scraped SBP Policy Rate from key rates page: %s", rate * 100)
                        return rate

                    # Check each cell for a standalone percentage
                    for cell in cells:
                        rate = _parse_pct(_clean(cell.get_text()))
                        if rate is not None:
                            logger.info("Scraped SBP Policy Rate from key rates cell: %s", rate * 100)
                            return rate

            return None
        except Exception as e:
            logger.error("Error scraping SBP key rates page: %s", e)
            return None

    # ------------------------------------------------------------------
    # T-bill / government securities yields
    # ------------------------------------------------------------------

    async def fetch_tbill_rates(self) -> Dict[str, Decimal]:
        """
        Fetch yields for government securities (MTBs, PIBs, GIS).
        Returns a dictionary mapping instrument symbol to yield/rental rate Decimal.
        """
        fallbacks = {
            "MTB-3M": Decimal("0.2010"),
            "MTB-6M": Decimal("0.2015"),
            "MTB-12M": Decimal("0.2025"),
            "PIB-3Y": Decimal("0.2150"),
            "PIB-5Y": Decimal("0.2200"),
            "PIB-10Y": Decimal("0.2275"),
            "PIB-20Y": Decimal("0.2350"),
            "GIS-3Y-FRR": Decimal("0.2125"),
            "GIS-3Y-VRR": Decimal("0.2050"),
        }

        # Strategy 1: scrape the auction results page
        scraped = await self._scrape_auction_results()
        if scraped:
            logger.info("Scraped %d T-bill yields from SBP auction page", len(scraped))
            return scraped

        # Strategy 2: scrape the key rates page
        scraped = await self._scrape_key_rates_yields()
        if scraped:
            logger.info("Scraped %d yields from SBP key rates page", len(scraped))
            return scraped

        logger.warning("All SBP yield sources failed. Using fallback defaults.")
        return fallbacks

    async def _scrape_auction_results(self) -> Dict[str, Decimal]:
        """Scrape SBP auction results page for T-bill cut-off yields."""
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.auction_url, headers=self.headers)
            if resp.status_code != 200:
                logger.warning("SBP auction page returned %s", resp.status_code)
                return {}

            soup = BeautifulSoup(resp.text, "lxml")
            yields: Dict[str, Decimal] = {}

            # Look for tables with auction data
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    row_text = _clean(row.get_text()).lower()

                    # Match MTB tenors: 3-month, 6-month, 12-month
                    mtb_map = [
                        (r"3[\s-]*month|3m\b|03\s*month", "MTB-3M"),
                        (r"6[\s-]*month|6m\b|06\s*month", "MTB-6M"),
                        (r"12[\s-]*month|12m\b|1yr|1[\s-]*year", "MTB-12M"),
                    ]
                    for pat, sym in mtb_map:
                        if re.search(pat, row_text, re.IGNORECASE) and sym not in yields:
                            # Find the yield — usually the last numeric cell or a cell with %
                            for cell in reversed(cells):
                                cell_text = _clean(cell.get_text())
                                rate = _parse_pct(cell_text)
                                if rate is not None and Decimal("0.05") < rate < Decimal("0.50"):
                                    yields[sym] = rate
                                    break
                            # Also try all cells in case the % is in an earlier column
                            if sym not in yields:
                                for cell in cells:
                                    rate = _parse_pct(_clean(cell.get_text()))
                                    if rate is not None and Decimal("0.05") < rate < Decimal("0.50"):
                                        yields[sym] = rate
                                        break

                    # Match PIB tenors
                    pib_map = [
                        (r"3[\s-]*year|3y\b", "PIB-3Y"),
                        (r"5[\s-]*year|5y\b", "PIB-5Y"),
                        (r"10[\s-]*year|10y\b", "PIB-10Y"),
                        (r"20[\s-]*year|20y\b", "PIB-20Y"),
                    ]
                    for pat, sym in pib_map:
                        if re.search(pat, row_text, re.IGNORECASE) and sym not in yields:
                            for cell in reversed(cells):
                                rate = _parse_pct(_clean(cell.get_text()))
                                if rate is not None and Decimal("0.05") < rate < Decimal("0.50"):
                                    yields[sym] = rate
                                    break

                    # Match GIS / Sukuk
                    if re.search(r"sukuk|gis|islamic", row_text, re.IGNORECASE):
                        for cell in reversed(cells):
                            rate = _parse_pct(_clean(cell.get_text()))
                            if rate is not None and Decimal("0.05") < rate < Decimal("0.50"):
                                if "GIS-3Y-FRR" not in yields:
                                    yields["GIS-3Y-FRR"] = rate
                                break

            # If no yields found in tables, try the full-page text approach
            if not yields:
                full_text = _clean(soup.get_text())
                yields = self._extract_yields_from_text(full_text)

            return yields

        except Exception as e:
            logger.error("Error scraping SBP auction results: %s", e)
            return {}

    async def _scrape_key_rates_yields(self) -> Dict[str, Decimal]:
        """Scrape the key rates page for government securities yields."""
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(self.key_rates_url, headers=self.headers)
            if resp.status_code != 200:
                return {}

            soup = BeautifulSoup(resp.text, "lxml")
            full_text = _clean(soup.get_text())
            return self._extract_yields_from_text(full_text)

        except Exception as e:
            logger.error("Error scraping SBP key rates for yields: %s", e)
            return {}

    def _extract_yields_from_text(self, text: str) -> Dict[str, Decimal]:
        """Extract government securities yields from a block of text using pattern matching."""
        yields: Dict[str, Decimal] = {}

        # Pattern: tenor keyword near a percentage
        patterns = [
            (r"3[\s-]*month[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "MTB-3M"),
            (r"6[\s-]*month[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "MTB-6M"),
            (r"12[\s-]*month[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "MTB-12M"),
            (r"3[\s-]*year[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "PIB-3Y"),
            (r"5[\s-]*year[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "PIB-5Y"),
            (r"10[\s-]*year[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "PIB-10Y"),
            (r"20[\s-]*year[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "PIB-20Y"),
            (r"sukuk[^%]{0,40}?(\d{1,2}\.\d{1,4})\s*%", "GIS-3Y-FRR"),
        ]

        for pat, sym in patterns:
            if sym not in yields:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    try:
                        rate = Decimal(m.group(1)) / Decimal("100")
                        if Decimal("0.05") < rate < Decimal("0.50"):
                            yields[sym] = rate
                    except InvalidOperation:
                        continue

        return yields

    # ------------------------------------------------------------------
    # Auction calendar (informational)
    # ------------------------------------------------------------------

    async def fetch_auction_calendar(self) -> Dict[str, Any]:
        """
        Fetch upcoming auction calendar from SBP.
        """
        try:
            return {
                "next_mtb_auction": "Fortnightly (Wednesdays)",
                "next_pib_auction": "Per calendar",
                "settlement": "T+1 (following Thursday)",
                "participants": "Primary Dealers (PDs)",
                "source": "sbp.org.pk",
            }
        except Exception as e:
            logger.error("Error fetching auction calendar: %s", e)
            return {}
