"""Offline unit tests for the Strategies feature + instrument resolver helpers.

Pure-function coverage (no DB/network): PSX ticker candidate detection,
screener condition evaluation, and strategy config validation.
"""

from decimal import Decimal

import pytest

from app.services.instrument_resolver import _psx_candidate
from app.api.strategy import _matches_condition
from app.schemas.strategy import StrategyCreate


# --- _psx_candidate --------------------------------------------------------

def test_psx_candidate_bare_ticker_gets_ka():
    assert _psx_candidate("LUCK") == "LUCK.KA"
    assert _psx_candidate("hbl") == "HBL.KA"


def test_psx_candidate_keeps_existing_ka():
    assert _psx_candidate("OGDC.KA") == "OGDC.KA"


def test_psx_candidate_rejects_non_psx():
    assert _psx_candidate("BTC-USD") is None
    assert _psx_candidate("GC=F") is None
    assert _psx_candidate("") is None


# --- screener condition evaluation -----------------------------------------

class _Inst:
    def __init__(self, symbol, sector=None, asset_class=None):
        self.symbol = symbol
        self.sector = sector
        self.asset_class = asset_class


def test_matches_sector_eq_case_insensitive():
    inst = _Inst("LUCK.KA", sector="Cement", asset_class="psx_stock")
    assert _matches_condition(inst, None, {"field": "sector", "op": "eq", "value": "cement"})
    assert not _matches_condition(inst, None, {"field": "sector", "op": "eq", "value": "banks"})


def test_matches_asset_class_in():
    inst = _Inst("BTC", asset_class="crypto")
    assert _matches_condition(inst, None, {"field": "asset_class", "op": "in", "value": ["crypto", "commodity"]})
    assert not _matches_condition(inst, None, {"field": "asset_class", "op": "in", "value": ["psx_stock"]})


def test_matches_price_thresholds():
    inst = _Inst("LUCK.KA", asset_class="psx_stock")
    assert _matches_condition(inst, Decimal("900"), {"field": "price", "op": "gt", "value": 500})
    assert not _matches_condition(inst, Decimal("100"), {"field": "price", "op": "gt", "value": 500})
    assert _matches_condition(inst, Decimal("100"), {"field": "price", "op": "lte", "value": 100})


def test_matches_price_missing_returns_false():
    inst = _Inst("X.KA", asset_class="psx_stock")
    assert not _matches_condition(inst, None, {"field": "price", "op": "lt", "value": 100})


# --- config validation -----------------------------------------------------

def test_screener_requires_conditions():
    with pytest.raises(Exception):
        StrategyCreate(name="x", kind="screener", config={})


def test_allocation_rejects_bad_method():
    with pytest.raises(Exception):
        StrategyCreate(name="x", kind="allocation", config={"method": "bogus"})


def test_allocation_accepts_valid():
    s = StrategyCreate(name="x", kind="allocation", config={"risk_tolerance": "moderate", "method": "min_vol"})
    assert s.config["method"] == "min_vol"
