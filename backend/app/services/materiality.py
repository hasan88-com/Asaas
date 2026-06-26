"""
Asaas (اثاثہ) — News Materiality Service (Stage 3: MATCH)

Links enriched news items to portfolio holdings and scores impact.
Relevance levels: direct > sector > macro (TECH.md §2, §4).

Precision-first matching (no substring false positives):
  • word-boundary ticker matching ("sol" never matches "solar")
  • name-confirmation for short / crypto tickers (SOL needs "solana" or a crypto cue)
  • asset-class topic guard (a crypto symbol in an energy headline is dropped)

Materiality combines the Stage-2 signals: relevance × magnitude × directional,
so only genuinely material events flag. Sentiment is additive signal — this
never touches the optimizer, weights, or the Decimal money pipeline.
`flag_event`/Flag remains the only write path and is now *more* conservative.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsItem, NewsHoldingLink
from app.models.portfolio import Portfolio
from app.models.holding import Holding
from app.models.instrument import Instrument
from app.models.flag import Flag
from app.services.sentiment import classify_sentiment

logger = logging.getLogger("asaas.services.materiality")

# Only flag holdings when the per-instrument materiality clears this bar AND the
# instrument is actually held. Stops minor/neutral items from flagging.
_FLAG_THRESHOLD = Decimal("0.4")

# Macro keywords that make a sovereign-debt instrument relevant.
_MACRO_KEYWORDS = ("sbp", "policy rate", "interest rate", "kibor", "monetary policy")

# Positive topic clusters per asset class — used to *confirm* a fragile ticker
# match (short or crypto). A bare short ticker with no topical support is dropped.
_CLASS_TOPICS = {
    "crypto": {
        "crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "blockchain",
        "token", "coin", "binance", "defi", "stablecoin", "web3", "altcoin", "digital currency",
    },
    "commodity": {
        "gold", "silver", "oil", "crude", "brent", "commodity", "commodities",
        "bullion", "metal", "petroleum", "wti", "tola", "ounce", "opec",
    },
    "tbill": {*_MACRO_KEYWORDS, "bond", "t-bill", "tbill", "treasury", "pib", "sukuk",
              "yield", "auction", "debt", "government securities", "gilt"},
    "bond": {*_MACRO_KEYWORDS, "bond", "tfc", "sukuk", "yield", "coupon", "debt", "credit", "default"},
    "psx_stock": {
        "psx", "kse", "kse-100", "share", "shares", "stock", "stocks", "equity",
        "equities", "index", "listed", "earnings", "dividend", "ipo", "bourse",
    },
    "global_stock": {"stock", "stocks", "equity", "equities", "shares", "nasdaq", "nyse", "earnings"},
}


def _class_topic_present(asset_class: str, headline: str) -> bool:
    """True if any topic keyword for the asset class appears in the headline."""
    return any(topic in headline for topic in _CLASS_TOPICS.get(asset_class, set()))


def _match_instrument(inst: Instrument, headline: str) -> Optional[Tuple[Decimal, str]]:
    """Return (relevance, level) if `inst` is relevant to `headline`, else None.

    `headline` must be lowercased. Precision-first: full-name OR word-boundary
    ticker for `direct`; sector word-boundary for `sector`; macro keywords for
    sovereign debt. Fragile (short / crypto) tickers require a topical/name cue.
    """
    symbol = inst.symbol.split(".")[0].lower()  # drop the .KA suffix
    name = (inst.name or "").lower()
    asset_class = inst.asset_class

    # Direct — full instrument/coin name is strong, unambiguous evidence.
    if len(name) > 3 and name in headline:
        return Decimal("1.000"), "direct"

    # Direct — word-boundary ticker match (NOT substring → "sol" ≠ "solar").
    if symbol and re.search(rf"\b{re.escape(symbol)}\b", headline):
        # Crypto tickers are short common-word collisions (SOL/GAS/ETH); the bare
        # ticker alone is fragile, so confirm with a crypto topic cue (the full
        # coin name was already checked above). PSX equity tickers (HBL, OGDC…)
        # are alphanumeric and rarely English words, so word-boundary alone is
        # sufficient precision for them — gating those on a topic cue would wrongly
        # drop legitimate direct hits.
        if asset_class == "crypto" and not _class_topic_present(asset_class, headline):
            return None  # bare crypto ticker, no topical support → drop
        return Decimal("1.000"), "direct"

    # Sector — word-boundary sector match.
    sector = (inst.sector or "").lower()
    if sector and len(sector) > 3 and re.search(rf"\b{re.escape(sector)}\b", headline):
        return Decimal("0.500"), "sector"

    # Macro — sovereign debt reacts to policy-rate / SBP news.
    if asset_class in ("tbill", "bond") and any(k in headline for k in _MACRO_KEYWORDS):
        return Decimal("0.300"), "macro"

    return None


class MaterialityService:
    """Matches enriched news items to active positions and scores impact."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_news_item(self, news_item_id: UUID):
        """
        Match a news item to all active instruments, score materiality from the
        Stage-2 sentiment signals, create links, and selectively create flags.
        """
        news_res = await self.db.execute(select(NewsItem).where(NewsItem.id == news_item_id))
        news_item = news_res.scalar_one_or_none()
        if not news_item:
            return

        # Stage 2 normally tags sentiment/magnitude at ingest. The agent tool path
        # may reach here untagged → classify on the fly so materiality is correct.
        if news_item.sentiment is None or news_item.magnitude is None:
            label, mag = classify_sentiment(f"{news_item.headline} {news_item.summary or ''}")
            if news_item.sentiment is None:
                news_item.sentiment = label
            if news_item.magnitude is None:
                news_item.magnitude = mag

        magnitude = news_item.magnitude or Decimal("0")
        # Directional factor: a neutral item is informational, not material.
        directional = Decimal("1.0") if (news_item.sentiment and news_item.sentiment != "neutral") else Decimal("0.4")

        inst_res = await self.db.execute(select(Instrument).where(Instrument.is_active == True))  # noqa: E712
        instruments = inst_res.scalars().all()

        headline = news_item.headline.lower()

        matched: List[Tuple[Instrument, Decimal, str]] = []
        for inst in instruments:
            m = _match_instrument(inst, headline)
            if m is not None:
                matched.append((inst, m[0], m[1]))

        if not matched:
            news_item.level = news_item.level or "macro"
            # No holding link → not flag-worthy; keep a small informational score.
            news_item.materiality_score = (magnitude * directional * Decimal("0.1")).quantize(Decimal("0.001"))
            return

        logger.info("News %s matched %d instruments.", news_item_id, len(matched))

        # Item-level classification uses the strongest match.
        best_relevance, best_level = max(((r, lvl) for _, r, lvl in matched), key=lambda t: t[0])
        news_item.level = best_level
        news_item.materiality_score = (best_relevance * magnitude * directional).quantize(Decimal("0.001"))

        for inst, relevance, level in matched:
            # 1. Link (dedup).
            link_res = await self.db.execute(
                select(NewsHoldingLink).where(
                    NewsHoldingLink.news_id == news_item.id,
                    NewsHoldingLink.instrument_id == inst.id,
                )
            )
            if link_res.scalar_one_or_none() is None:
                self.db.add(NewsHoldingLink(
                    news_id=news_item.id,
                    instrument_id=inst.id,
                    relevance=float(relevance),
                ))

            # 2. Selective flagging — only material, directional, HELD events.
            inst_materiality = relevance * magnitude * directional
            if level in ("direct", "sector") and inst_materiality > _FLAG_THRESHOLD:
                await self._flag_holders(news_item, inst, level)

    async def _flag_holders(self, news_item: NewsItem, inst: Instrument, level: str):
        """Create a pending flag for every active portfolio holding `inst`."""
        portfolios_res = await self.db.execute(
            select(Portfolio)
            .join(Holding, Holding.portfolio_id == Portfolio.id)
            .where(
                Holding.instrument_id == inst.id,
                Portfolio.status.in_(["confirmed", "tracked"]),
            )
        )
        for port in portfolios_res.scalars().all():
            flag_res = await self.db.execute(
                select(Flag).where(
                    Flag.portfolio_id == port.id,
                    Flag.news_id == news_item.id,
                    Flag.status == "pending",
                )
            )
            if flag_res.scalar_one_or_none() is not None:
                continue
            severity = "high" if level == "direct" else "medium"
            self.db.add(Flag(
                portfolio_id=port.id,
                news_id=news_item.id,
                type="news",
                severity=severity,
                message=f"Material {level} event: '{news_item.headline}' impacts your holding in {inst.symbol}.",
                status="pending",
            ))
            logger.info("Created %s news flag for portfolio %s re %s", severity, port.id, inst.symbol)
