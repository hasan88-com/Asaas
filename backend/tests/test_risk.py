"""
Phase C — risk metric unit tests (pure numpy, offline).
Verifies VaR/CVaR/drawdown/rolling/Sortino/beta on known fixtures.
"""

from __future__ import annotations

import numpy as np

from app.services.risk import (
    var_historical, var_parametric, cvar, max_drawdown,
    rolling_vol, rolling_sharpe, sortino, beta,
)


def test_var_historical_is_positive_loss():
    # 5th percentile of a known series → positive loss fraction.
    r = np.array([-0.10, -0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    v = var_historical(r, 95)
    assert v > 0
    # Equals -(5th percentile)
    assert abs(v - (-np.percentile(r, 5))) < 1e-9


def test_var_parametric_formula():
    r = np.random.default_rng(0).normal(0.0, 0.02, size=500)
    expected = 1.645 * r.std(ddof=1) - r.mean()
    assert abs(var_parametric(r, 95) - expected) < 1e-9


def test_cvar_ge_var():
    r = np.random.default_rng(1).normal(0.0, 0.02, size=1000)
    assert cvar(r, 95) >= var_historical(r, 95) - 1e-9  # tail mean ≥ the cutoff


def test_max_drawdown_known_series():
    # Up to 110, down to 88 (−20%), then recover.
    rets = np.array([0.10, -0.20, 0.05, 0.05])
    mdd, dur = max_drawdown(rets)
    assert mdd < 0
    assert abs(mdd - (-0.20)) < 1e-9      # worst single drop here
    assert dur >= 1


def test_rolling_and_sortino_positive_drift():
    rng = np.random.default_rng(2)
    # Strong positive drift (0.5%/day) well above the daily SBP rf → clearly
    # positive Sharpe/Sortino regardless of window noise.
    r = rng.normal(0.005, 0.01, size=300)
    assert rolling_vol(r, 30) > 0
    assert rolling_sharpe(r, 0.11 / 252, 200) > 0
    assert sortino(r, 0.11 / 252) > 0


def test_beta_of_self_is_one():
    r = np.random.default_rng(3).normal(0, 0.02, size=200)
    b = beta(r, r)
    assert b is not None and abs(b - 1.0) < 1e-6


def test_beta_scaled_market():
    rng = np.random.default_rng(4)
    m = rng.normal(0, 0.02, size=200)
    a = 1.5 * m + rng.normal(0, 1e-6, size=200)  # asset ≈ 1.5×market
    b = beta(a, m)
    assert b is not None and abs(b - 1.5) < 0.05


def test_beta_thin_returns_none():
    assert beta(np.zeros(10), np.zeros(10)) is None  # < 30 obs
