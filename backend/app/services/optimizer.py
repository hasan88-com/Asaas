"""
Asaas (اثاثہ) — Portfolio Optimizer Service

Mean-variance + robust allocation implemented in **numpy + scipy** (no
PyPortfolioOpt / cvxpy / sklearn — they need a C compiler / aren't installed).

Pipeline: DB price history → daily returns → annualized μ + **Ledoit-Wolf
shrunk covariance** → one of {max_sharpe, min_vol, risk_parity, hrp} under
sum=1 + per-asset caps. SBP policy rate is the risk-free rate. Falls back to a
deterministic heuristic when data is too thin (RULES.md A1.4, A2.6, A3.5).
All prices/weights cross the boundary as Decimal.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.optimize import minimize

logger = logging.getLogger("asaas.services.optimizer")

_TRADING_DAYS = 252

# Daily simple returns above this magnitude are treated as corrupt price data
# (unit splices, splits, zeros) and dropped — no liquid PSX/crypto/commodity
# asset moves >100% in a single day.
MAX_DAILY_RETURN = 1.0

# Selectable allocation methods + the default per risk profile.
OPTIMIZER_METHODS = ("max_sharpe", "min_vol", "risk_parity", "hrp")
PROFILE_METHOD_DEFAULT = {
    "conservative": "min_vol",
    "moderately_conservative": "min_vol",
    "moderate": "max_sharpe",
    "aggressive": "max_sharpe",
    "very_aggressive": "risk_parity",
}


def is_valid_candidate(instrument) -> bool:
    """Exclude matured and nominal debt from optimizer candidate sets."""
    if instrument.maturity_date and instrument.maturity_date < date.today():
        return False
    if instrument.face_value is not None and instrument.face_value < 1000:
        return False
    return True


def expected_return_for_class(asset_class: str, sbp_rate: Decimal) -> Decimal:
    """Expected annual return proxy per asset class, relative to SBP policy rate."""
    mapping: Dict[str, Decimal] = {
        "equity": sbp_rate + Decimal("0.06"),
        "psx_stock": sbp_rate + Decimal("0.06"),
        "tbill": sbp_rate - Decimal("0.005"),
        "bond": sbp_rate - Decimal("0.005"),
        "crypto": sbp_rate + Decimal("0.20"),
        "commodity": sbp_rate * Decimal("0.6"),
    }
    return mapping.get(asset_class, sbp_rate)


# ---------------------------------------------------------------------------
# Returns + covariance (module-level, pure numpy — unit-testable)
# ---------------------------------------------------------------------------

def aligned_returns(historical_prices: Dict[str, List[Decimal]]) -> Tuple[List[str], Optional[np.ndarray]]:
    """Build a (T × N) daily simple-returns matrix from per-symbol price lists.

    `historical_prices` values are most-recent-first (the DB query orders
    price_date DESC). Series of differing length are truncated to the common
    most-recent window (positional alignment; exact date-join is a later
    refinement). Returns (symbols, returns) or (symbols, None) if too thin.
    """
    syms = [s for s, v in historical_prices.items() if v and len(v) >= 3]
    if len(syms) < 2:
        return syms, None
    min_len = min(len(historical_prices[s]) for s in syms)
    if min_len < 3:
        return syms, None
    cols = []
    for s in syms:
        px = np.array([float(p) for p in historical_prices[s][:min_len]][::-1])  # oldest→newest
        cols.append(px)
    P = np.column_stack(cols)                       # (min_len, N)
    rets = np.diff(P, axis=0) / P[:-1]              # simple returns
    # Drop rows that are non-finite or contain an implausible daily move (>100%).
    # Such rows are almost always corrupt/spliced prices (e.g. a USD↔PKR unit
    # mismatch, a stock-split artefact, or a zero) — a single one would otherwise
    # dominate μ and Σ and blow up every downstream estimate.
    good = np.isfinite(rets).all(axis=1) & (np.abs(rets) <= MAX_DAILY_RETURN).all(axis=1)
    rets = rets[good]
    if rets.shape[0] < 2:
        return syms, None
    return syms, rets


def mean_historical_return(rets: np.ndarray) -> np.ndarray:
    """Annualized mean return per asset: (1 + mean_daily)^252 − 1."""
    return (1.0 + rets.mean(axis=0)) ** _TRADING_DAYS - 1.0


def ledoit_wolf_cov(rets: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf (2004) shrinkage toward a scaled-identity target, annualized.

    Σ_shrunk = δ·(μ·I) + (1−δ)·S, with δ the closed-form optimal intensity.
    Always returns a well-conditioned PSD matrix even when T ≈ N.
    """
    X = np.asarray(rets, dtype=float)
    X = X - X.mean(axis=0)
    T, N = X.shape
    S = (X.T @ X) / T                              # sample cov (MLE)
    mu = np.trace(S) / N                           # mean variance (identity scale)
    # d² = ||S − μI||²_F / N
    d2 = (np.sum(S ** 2) - N * mu ** 2) / N
    # b̄² = mean_t ||x_t x_tᵀ − S||²_F / N  (variance of the sample cov)
    norm_xt2 = (X ** 2).sum(axis=1)               # ||x_t||²
    term1 = np.sum(norm_xt2 ** 2)
    term2 = np.sum(np.einsum("ti,ij,tj->t", X, S, X))
    b2bar = (term1 - 2.0 * term2 + T * np.sum(S ** 2)) / (T ** 2) / N
    b2 = max(0.0, min(b2bar, d2))                 # cap shrinkage variance at d²
    delta = (b2 / d2) if d2 > 0 else 0.0
    shrunk = delta * mu * np.eye(N) + (1.0 - delta) * S
    return shrunk * _TRADING_DAYS                  # annualize


# ---------------------------------------------------------------------------
# Allocation methods (numpy/scipy)
# ---------------------------------------------------------------------------

def _solve(objective, n: int, bounds, extra_cons=()) -> Optional[np.ndarray]:
    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}, *extra_cons]
    w0 = np.array([1.0 / n] * n)
    res = minimize(objective, w0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"maxiter": 800, "ftol": 1e-10})
    if not res.success:
        return None
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else None


def max_sharpe(mu: np.ndarray, cov: np.ndarray, rf: float, bounds) -> Optional[np.ndarray]:
    def neg_sharpe(w):
        vol = float(np.sqrt(w @ cov @ w))
        return 1e6 if vol <= 0 else -((w @ mu - rf) / vol)
    return _solve(neg_sharpe, len(mu), bounds)


def min_vol(mu: np.ndarray, cov: np.ndarray, bounds) -> Optional[np.ndarray]:
    return _solve(lambda w: float(w @ cov @ w), len(mu), bounds)


def risk_parity(cov: np.ndarray, bounds) -> Optional[np.ndarray]:
    n = cov.shape[0]
    def dispersion(w):
        vol = float(np.sqrt(w @ cov @ w))
        if vol <= 0:
            return 1e6
        rc = w * (cov @ w) / vol                   # risk contributions
        return float(np.sum((rc - rc.mean()) ** 2))
    return _solve(dispersion, n, bounds)


def hrp(cov: np.ndarray, upper_caps: np.ndarray) -> Optional[np.ndarray]:
    """Hierarchical Risk Parity: corr→distance→cluster→quasi-diagonal→recursive
    inverse-variance bisection. Caps applied post-hoc (clip + renormalize)."""
    n = cov.shape[0]
    if n < 2:
        return None
    std = np.sqrt(np.diag(cov))
    denom = np.outer(std, std)
    corr = np.divide(cov, denom, out=np.zeros_like(cov), where=denom > 0)
    np.fill_diagonal(corr, 1.0)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    # condensed distance for scipy
    iu = np.triu_indices(n, 1)
    condensed = dist[iu]
    link = linkage(condensed, method="single")
    # quasi-diagonal leaf order
    order = [int(i) for i in to_tree(link).pre_order()]

    def cluster_var(idx):
        sub = cov[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(sub)
        w = iv / iv.sum()
        return float(w @ sub @ w)

    w = np.ones(n)
    clusters = [order]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) <= 1:
                continue
            half = len(c) // 2
            left, right = c[:half], c[half:]
            vl, vr = cluster_var(left), cluster_var(right)
            alpha = 1.0 - vl / (vl + vr) if (vl + vr) > 0 else 0.5
            for i in left:
                w[i] *= alpha
            for i in right:
                w[i] *= (1.0 - alpha)
            nxt += [left, right]
        clusters = nxt
    w = w / w.sum()
    # Apply upper caps (HRP has no native bounds): clip + renormalize a few times.
    for _ in range(8):
        over = w > upper_caps
        if not over.any():
            break
        w[over] = upper_caps[over]
        free = ~over
        deficit = 1.0 - w.sum()
        if free.any() and abs(deficit) > 1e-9:
            w[free] += deficit * (w[free] / w[free].sum())
        else:
            break
    s = w.sum()
    return w / s if s > 0 else None


def efficient_return(mu, cov, target: float, bounds) -> Optional[np.ndarray]:
    cons = ({"type": "eq", "fun": lambda w: float(w @ mu) - target},)
    return _solve(lambda w: float(w @ cov @ w), len(mu), bounds, extra_cons=cons)


def efficient_risk(mu, cov, target_vol: float, bounds) -> Optional[np.ndarray]:
    cons = ({"type": "eq", "fun": lambda w: float(np.sqrt(w @ cov @ w)) - target_vol},)
    return _solve(lambda w: -float(w @ mu), len(mu), bounds, extra_cons=cons)


def efficient_frontier(mu, cov, bounds, points: int = 12) -> List[Tuple[float, float]]:
    """Sweep target returns → (vol, ret) points along the frontier."""
    out: List[Tuple[float, float]] = []
    for tgt in np.linspace(float(mu.min()), float(mu.max()), points):
        w = efficient_return(mu, cov, float(tgt), bounds)
        if w is not None:
            out.append((float(np.sqrt(w @ cov @ w)), float(w @ mu)))
    return out


class PortfolioOptimizer:
    """Robust portfolio allocation (numpy/scipy) with heuristic fallback."""

    def __init__(self, risk_free_rate: Decimal):
        self.risk_free_rate = float(risk_free_rate)

    def optimize(
        self,
        historical_prices: Dict[str, List[Decimal]],
        asset_classes: Dict[str, str],
        sectors: Dict[str, str],
        risk_tolerance: str,
        constraints: Optional[Dict[str, Any]] = None,
        method: Optional[str] = None,
    ) -> Dict[str, Decimal]:
        """Allocate. `method` ∈ OPTIMIZER_METHODS; defaults from risk profile.
        Falls back to the deterministic heuristic when data is too thin / fails."""
        all_symbols = list(historical_prices.keys())
        if not all_symbols:
            return {}
        constraints = constraints or {}
        chosen = (method or PROFILE_METHOD_DEFAULT.get(risk_tolerance, "max_sharpe")).lower()

        try:
            syms, rets = aligned_returns(historical_prices)
            if rets is not None and len(syms) >= 2:
                mu = mean_historical_return(rets)
                cov = ledoit_wolf_cov(rets)
                bounds = self._bounds(syms, asset_classes, sectors, risk_tolerance, constraints)
                upper = np.array([b[1] for b in bounds])

                if chosen == "min_vol":
                    w = min_vol(mu, cov, bounds)
                elif chosen == "risk_parity":
                    w = risk_parity(cov, bounds)
                elif chosen == "hrp":
                    w = hrp(cov, upper)
                else:
                    chosen = "max_sharpe"
                    w = max_sharpe(mu, cov, self.risk_free_rate, bounds)

                if w is not None and np.isfinite(w).all() and w.sum() > 0:
                    result = {syms[i]: Decimal(str(round(float(w[i]), 4))) for i in range(len(syms))}
                    # symbols with no usable history get 0
                    for s in all_symbols:
                        result.setdefault(s, Decimal("0"))
                    logger.info("Optimized via %s for tolerance=%s (%d assets)", chosen, risk_tolerance, len(syms))
                    return self._normalize_weights(result)
        except Exception as e:
            logger.warning("Optimization (%s) failed: %s — heuristic fallback.", chosen, e)

        return self._generate_heuristic_allocation(all_symbols, asset_classes, risk_tolerance)

    def _bounds(self, symbols, asset_classes, sectors, risk_tolerance, constraints):
        """Per-asset (0, cap) bounds: sector exclusions → 0; crypto caps by risk."""
        excluded = set(constraints.get("excluded_sectors", []))
        bounds = []
        for sym in symbols:
            ac = asset_classes.get(sym, "")
            if sectors.get(sym, "") in excluded:
                bounds.append((0.0, 0.0))
                continue
            cap = 0.40
            if ac == "crypto":
                cap = 0.0 if risk_tolerance == "conservative" else 0.05 if risk_tolerance == "moderate" else 0.15
            elif ac in ("tbill", "bond") and risk_tolerance == "conservative":
                cap = 0.60
            bounds.append((0.0, cap))
        return bounds

    def _generate_heuristic_allocation(self, symbols, asset_classes, risk_tolerance):
        """Deterministic asset-class target weights (stable fallback)."""
        logger.info("Heuristic allocation for tolerance=%s", risk_tolerance)
        if risk_tolerance == "conservative":
            targets = {"tbill": 0.50, "psx_stock": 0.20, "global_stock": 0.10, "commodity": 0.20, "crypto": 0.00}
        elif risk_tolerance == "aggressive":
            targets = {"tbill": 0.10, "psx_stock": 0.40, "global_stock": 0.20, "commodity": 0.15, "crypto": 0.15}
        else:
            targets = {"tbill": 0.30, "psx_stock": 0.30, "global_stock": 0.15, "commodity": 0.20, "crypto": 0.05}

        groups: Dict[str, List[str]] = {}
        for sym in symbols:
            groups.setdefault(asset_classes.get(sym, "tbill"), []).append(sym)

        weights: Dict[str, Decimal] = {}
        for ac, tw in targets.items():
            g = groups.get(ac, [])
            if not g:
                continue
            share = Decimal(str(tw)) / Decimal(len(g))
            for sym in g:
                weights[sym] = share
        for sym in symbols:
            weights.setdefault(sym, Decimal("0"))
        return self._normalize_weights(weights)

    def _normalize_weights(self, weights: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Ensure weights sum exactly to 1.0 (RULES.md D2.3)."""
        total = sum(weights.values())
        if not weights:
            return weights
        if total > 0:
            normalized = {k: v / total for k, v in weights.items()}
        else:
            eq = Decimal("1.0") / Decimal(len(weights))
            normalized = {k: eq for k in weights}
        final = {k: Decimal(str(round(v, 4))) for k, v in normalized.items()}
        diff = Decimal("1.0") - sum(final.values())
        if diff != 0 and final:
            largest = max(final, key=lambda k: final[k])
            final[largest] += diff
        return final
