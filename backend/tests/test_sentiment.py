"""
Tests for the lexicon sentiment service (Stage 2) and the precision matcher
(Stage 3). Pure/offline — no DB, no network, no LLM.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.instrument import Instrument
from app.services.materiality import _match_instrument
from app.services.sentiment import classify_sentiment


# --------------------------------------------------------------------------- #
# Stage 2 — lexicon sentiment
# --------------------------------------------------------------------------- #

def test_sentiment_positive():
    label, mag = classify_sentiment("Bank profits surge to record high")
    assert label == "positive"
    assert mag > Decimal("0")


def test_sentiment_negative():
    label, mag = classify_sentiment("Rupee plunges as market crashes amid default fears")
    assert label == "negative"
    assert mag > Decimal("0")


def test_sentiment_neutral_no_cues():
    label, mag = classify_sentiment("SBP announces next monetary policy meeting schedule")
    assert label == "neutral"
    assert mag == Decimal("0.000")


def test_sentiment_magnitude_strong_beats_weak():
    _, weak = classify_sentiment("shares rise")
    _, strong = classify_sentiment("shares surge to record")
    assert strong > weak


def test_sentiment_balanced_is_neutral():
    # Equal positive ("profit") and negative ("warning"/"miss") cues → mixed.
    label, _ = classify_sentiment("profit warning: earnings miss")
    assert label == "neutral"


# --------------------------------------------------------------------------- #
# Stage 3 — precision matching (no DB; ORM objects unpersisted)
# --------------------------------------------------------------------------- #

def _inst(symbol, name, asset_class, sector=None):
    return Instrument(symbol=symbol, name=name, asset_class=asset_class, sector=sector)


SOL = _inst("SOL", "Solana", "crypto")
HBL = _inst("HBL.KA", "Habib Bank Limited", "psx_stock", sector="Commercial Banks")


def test_solar_does_not_match_sol():
    """The headline class bug: 'solar' must NOT match the SOL crypto ticker."""
    assert _match_instrument(SOL, "pakistan solar panel prices fall sharply") is None


def test_solana_name_matches_sol():
    """Full coin name is unambiguous direct evidence."""
    m = _match_instrument(SOL, "solana rallies 20% as altcoins recover")
    assert m is not None and m[1] == "direct"


def test_bare_ticker_with_crypto_cue_matches():
    """Bare SOL ticker confirmed by a crypto topic cue → direct.

    (The matcher's contract is a lowercased headline — the pipeline lowercases
    via `news_item.headline.lower()` before calling.)
    """
    m = _match_instrument(SOL, "sol jumps as the crypto market rebounds")
    assert m is not None and m[1] == "direct"


def test_bare_crypto_ticker_without_cue_dropped():
    """Bare SOL with no name and no crypto cue is too fragile → dropped."""
    assert _match_instrument(SOL, "sol set to host a conference") is None


def test_equity_ticker_word_boundary_matches():
    """A standalone PSX equity ticker matches without needing the full name."""
    m = _match_instrument(HBL, "hbl posts record quarterly numbers")
    assert m is not None and m[1] == "direct"


def test_equity_ticker_not_substring():
    """Word boundary: the equity ticker must not match inside another word."""
    assert _match_instrument(HBL, "the shbloon index is irrelevant") is None
