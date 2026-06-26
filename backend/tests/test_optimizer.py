"""
Asaas (اثاثہ) — Optimizer Unit Tests

Verifies that:
- Weights sum precisely to 1.0 (RULES.md D2.3).
- Bounds and sector caps are respected (RULES.md A1.5).
- Stable heuristics are generated on fallback (RULES.md A3.5).
"""

from __future__ import annotations

import numpy as np
import pytest
from decimal import Decimal
from app.services.optimizer import (
    PortfolioOptimizer,
    aligned_returns,
    mean_historical_return,
    ledoit_wolf_cov,
    max_sharpe,
    min_vol,
    risk_parity,
    hrp,
)


def _synth_returns(n: int = 4, T: int = 300, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    common = rng.normal(0.0005, 0.008, size=(T, 1))      # shared market factor
    return common + rng.normal(0.0, 0.012, size=(T, n))   # idiosyncratic


def test_heuristic_allocation_sums_to_one():
    """Verify heuristic optimizer weights sum precisely to 1.0."""
    optimizer = PortfolioOptimizer(risk_free_rate=Decimal("0.20"))

    # Include a symbol from EVERY asset class the heuristic targets, so each
    # target bucket gets allocated and _normalize_weights has no missing-class
    # gap to redistribute (which would otherwise rescale the crypto cap).
    symbols = ["HBL.KA", "SPY", "BTC", "TBILL-3M", "GC=F"]
    asset_classes = {
        "HBL.KA": "psx_stock",
        "SPY": "global_stock",
        "BTC": "crypto",
        "TBILL-3M": "tbill",
        "GC=F": "commodity",
    }

    # Conservative profile
    weights = optimizer._generate_heuristic_allocation(symbols, asset_classes, "conservative")
    assert sum(weights.values()) == Decimal("1.0")
    assert weights["BTC"] == Decimal("0.0"), "conservative must cap crypto at 0%"

    # Moderate profile — crypto cap is 5% of the total, preserved when every
    # asset class is represented (no renormalization gap).
    weights_mod = optimizer._generate_heuristic_allocation(symbols, asset_classes, "moderate")
    assert sum(weights_mod.values()) == Decimal("1.0")
    assert weights_mod["BTC"] == Decimal("0.05"), "moderate must cap crypto at 5%"

    # Aggressive profile
    weights_agg = optimizer._generate_heuristic_allocation(symbols, asset_classes, "aggressive")
    assert sum(weights_agg.values()) == Decimal("1.0")
    assert weights_agg["BTC"] == Decimal("0.15"), "aggressive must cap crypto at 15%"

    # Risk ordering across profiles: more risk tolerance ⇒ more crypto.
    assert weights_agg["BTC"] > weights_mod["BTC"] >= weights["BTC"]


def test_optimizer_normalization_safeguard():
    """Verify weight normalization handles precision issues gracefully."""
    optimizer = PortfolioOptimizer(risk_free_rate=Decimal("0.20"))
    
    # Weights that sum slightly above/below 1.0 due to rounding
    imperfect_weights = {
        "A": Decimal("0.3333"),
        "B": Decimal("0.3333"),
        "C": Decimal("0.3333"),
    }
    
    normalized = optimizer._normalize_weights(imperfect_weights)
    assert sum(normalized.values()) == Decimal("1.0000")


# --------------------------------------------------------------------------- #
# Phase B — numpy/scipy optimizer math
# --------------------------------------------------------------------------- #

def test_ledoit_wolf_is_symmetric_psd():
    cov = ledoit_wolf_cov(_synth_returns(n=5))
    assert np.allclose(cov, cov.T), "covariance must be symmetric"
    assert np.min(np.linalg.eigvalsh(cov)) >= -1e-10, "shrunk covariance must be PSD"


def test_methods_weights_sum_to_one_and_respect_caps():
    rets = _synth_returns(n=4)
    mu, cov = mean_historical_return(rets), ledoit_wolf_cov(rets)
    bounds = [(0.0, 0.40)] * 4
    for w in (max_sharpe(mu, cov, 0.11, bounds), min_vol(mu, cov, bounds), risk_parity(cov, bounds)):
        assert w is not None
        assert abs(w.sum() - 1.0) < 1e-6
        assert (w <= 0.40 + 1e-6).all() and (w >= -1e-9).all()


def test_min_vol_not_riskier_than_max_sharpe():
    rets = _synth_returns(n=4)
    mu, cov = mean_historical_return(rets), ledoit_wolf_cov(rets)
    bounds = [(0.0, 1.0)] * 4
    wv, ws = min_vol(mu, cov, bounds), max_sharpe(mu, cov, 0.11, bounds)
    vol = lambda w: float(np.sqrt(w @ cov @ w))
    assert vol(wv) <= vol(ws) + 1e-8


def test_hrp_runs_on_thin_fixture():
    cov = ledoit_wolf_cov(_synth_returns(n=5, T=40))  # thin window
    w = hrp(cov, np.array([1.0] * 5))
    assert w is not None and abs(w.sum() - 1.0) < 1e-6 and (w >= 0).all()


def test_risk_parity_equalizes_contributions():
    cov = ledoit_wolf_cov(_synth_returns(n=4))
    w = risk_parity(cov, [(0.0, 1.0)] * 4)
    vol = float(np.sqrt(w @ cov @ w))
    rc = w * (cov @ w) / vol
    assert rc.std() / rc.mean() < 0.30, "risk contributions should be ~equal"


def test_optimize_uses_math_when_history_present():
    rng = np.random.default_rng(1)
    prices = {}
    for s in ("A", "B", "C"):
        p = 100 + np.cumsum(rng.normal(0, 1, size=200))
        prices[s] = [Decimal(str(round(float(x), 4))) for x in p[::-1]]  # DESC like the DB
    w = PortfolioOptimizer(Decimal("0.11")).optimize(
        prices, {s: "psx_stock" for s in prices}, {}, "moderate"
    )
    assert abs(sum(w.values()) - Decimal("1.0")) < Decimal("0.001")
    assert all(v >= 0 for v in w.values())
