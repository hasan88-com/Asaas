"""
Asaas (اثاثہ) — News Sentiment Service (Stage 2: ENRICH)

Per-item directional sentiment + magnitude from a built-in curated finance
lexicon (Loughran–McDonald style). Pure, deterministic, no network, no
dependency, no LLM. Strictly an additive *signal*: nothing here touches the
optimizer, MPT math, portfolio weights, P&L, or the Decimal money pipeline.

`classify_sentiment(text) -> (label, magnitude)`:
  label     ∈ {"positive", "negative", "neutral"}
  magnitude ∈ Decimal 0.000–1.000 (how strong the directional cue is)
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Tuple

# Weak cues (weight 1) and strong cues (weight 2). Finance-oriented; lowercase.
_POSITIVE = {
    "gain", "gains", "rise", "rises", "rose", "rising", "higher", "grow", "grows",
    "growth", "profit", "profits", "profitable", "beat", "beats", "strong", "strength",
    "boost", "boosted", "recovery", "rebound", "rebounds", "improve", "improved",
    "improvement", "upgrade", "upgraded", "approval", "approved", "positive",
    "optimistic", "bullish", "outperform", "expansion", "inflow", "inflows", "dividend",
    "surplus", "ease", "eased", "easing", "disbursement", "stable", "stability", "gainer",
    "gainers", "advance", "advances", "wins", "win", "robust", "resilient", "uptick",
}
_POSITIVE_STRONG = {
    "surge", "surged", "surges", "soar", "soared", "soars", "rally", "rallied", "rallies",
    "record", "jump", "jumped", "jumps", "skyrocket", "breakthrough", "upbeat", "boom",
    "outperformed", "all-time", "高",  # (defensive: stray non-ascii never matches token regex)
}
_NEGATIVE = {
    "fall", "falls", "fell", "falling", "drop", "drops", "dropped", "decline", "declines",
    "declined", "lower", "loss", "losses", "weak", "weaker", "miss", "missed", "cut", "cuts",
    "downgrade", "downgraded", "negative", "bearish", "deficit", "concern", "concerns",
    "concerned", "risk", "risks", "fear", "fears", "outflow", "outflows", "selloff",
    "pressure", "slowdown", "slow", "loser", "losers", "decline", "shortfall", "worsen",
    "worsened", "drag", "drags", "subdued", "sluggish",
}
_NEGATIVE_STRONG = {
    "crash", "crashed", "crashes", "plunge", "plunged", "plunges", "plummet", "plummeted",
    "collapse", "collapsed", "crisis", "slump", "slumped", "tumble", "tumbled", "tumbles",
    "default", "defaulted", "defaults", "sink", "sank", "freefall", "rout", "panic", "crackdown",
}

_TOKEN_RE = re.compile(r"[a-z]+")
# Scale: weight at which magnitude saturates to 1.0. A single strong cue (2) →
# 0.5; "record surge in profits" (2+2+1=5) → 1.0. Tuned so a lone weak cue reads
# as a modest 0.25 signal, not a dominant one.
_MAGNITUDE_SCALE = Decimal("4")


def classify_sentiment(text: str) -> Tuple[str, Decimal]:
    """Return (label, magnitude) for a headline / summary string.

    Deterministic lexicon scoring: sum weighted positive vs negative cues, take
    the net sign for direction and the dominant side's weight for magnitude.
    Empty / cue-free text → ("neutral", 0.000).
    """
    tokens = _TOKEN_RE.findall((text or "").lower())
    pos = sum(2 if t in _POSITIVE_STRONG else 1 if t in _POSITIVE else 0 for t in tokens)
    neg = sum(2 if t in _NEGATIVE_STRONG else 1 if t in _NEGATIVE else 0 for t in tokens)

    if pos == 0 and neg == 0:
        return "neutral", Decimal("0.000")

    net = pos - neg
    if net > 0:
        label = "positive"
    elif net < 0:
        label = "negative"
    else:
        # Balanced cues (e.g. "profit warning") → genuinely mixed → neutral.
        label = "neutral"

    dominant = Decimal(max(pos, neg))
    magnitude = min(Decimal("1.000"), (dominant / _MAGNITUDE_SCALE)).quantize(Decimal("0.001"))
    return label, magnitude
