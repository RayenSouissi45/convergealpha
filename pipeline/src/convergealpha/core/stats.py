"""Core formulas from the specification (Sections 4, 5 and 7).

Every function here is pure and has a reference-value unit test in tests/test_stats.py.
Rates and returns are fractions (0.0029 = 0.29%), never percentages.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

MAD_TO_SIGMA = 1.4826
Z_CLIP = 3.0
# A sector needs at least this many valid values for its own median/MAD; otherwise the
# universe-wide median/MAD is used so tiny sectors don't produce extreme z-scores.
MIN_SECTOR_COUNT = 5


def norm_cdf(z: float) -> float:
    """Standard normal CDF, Φ(z)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _robust_center_scale(x: NDArray[np.float64]) -> tuple[float, float]:
    median = float(np.median(x))
    mad = float(np.median(np.abs(x - median)))
    return median, MAD_TO_SIGMA * mad


def robust_sector_scores(
    values: ArrayLike,
    sectors: ArrayLike,
    lower_pct: float = 1.0,
    upper_pct: float = 99.0,
) -> NDArray[np.float64]:
    """Normalize one raw signal across the universe into 0-100 scores.

    1. Winsorize at the universe 1st/99th percentile.
    2. Robust z inside the sector: (x - median_sector) / (1.4826 * MAD_sector), clipped to [-3, 3].
    3. score = 100 * Φ(z).

    Missing values (NaN) stay NaN. A sector with fewer than MIN_SECTOR_COUNT values or zero MAD
    falls back to the universe median/MAD; if that MAD is also zero, z = 0 (score 50).
    """
    x = np.asarray(values, dtype=np.float64)
    groups = np.asarray(sectors, dtype=object)
    if x.shape != groups.shape:
        raise ValueError("values and sectors must have the same shape")

    scores = np.full(x.shape, np.nan)
    valid = ~np.isnan(x)
    if not valid.any():
        return scores

    lo, hi = np.percentile(x[valid], [lower_pct, upper_pct])
    w = np.clip(x, lo, hi)
    universe_center, universe_scale = _robust_center_scale(w[valid])

    for sector in np.unique(groups[valid]):
        mask = valid & (groups == sector)
        center, scale = _robust_center_scale(w[mask])
        if mask.sum() < MIN_SECTOR_COUNT or scale == 0.0:
            center, scale = universe_center, universe_scale
        if scale == 0.0:
            z = np.zeros(int(mask.sum()))
        else:
            z = np.clip((w[mask] - center) / scale, -Z_CLIP, Z_CLIP)
        scores[mask] = [100.0 * norm_cdf(float(v)) for v in z]
    return scores


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center - half, center + half


def n_eff(weights: ArrayLike, corr: ArrayLike) -> float:
    """Effective number of independent sources: (Σw)² / ΣΣ w_i w_j ρ_ij."""
    w = np.asarray(weights, dtype=np.float64)
    rho = np.asarray(corr, dtype=np.float64)
    if rho.shape != (w.size, w.size):
        raise ValueError("corr must be a square matrix matching weights")
    denom = float(w @ rho @ w)
    if denom <= 0.0:
        raise ValueError("weights and correlations give a non-positive variance")
    return float(w.sum() ** 2 / denom)


def uniform_corr(n: int, rho: float) -> NDArray[np.float64]:
    """An n×n correlation matrix with every off-diagonal entry equal to rho."""
    m = np.full((n, n), rho, dtype=np.float64)
    np.fill_diagonal(m, 1.0)
    return m


def trading_cost(
    spread: float, commission: float, sigma_daily: float, order_to_adv: float
) -> float:
    """Round-trip cost C = spread + 2·commission + 2·impact, impact = 0.5·σ_daily·√(order/ADV)."""
    impact = 0.5 * sigma_daily * math.sqrt(order_to_adv)
    return spread + 2 * commission + 2 * impact


def expected_value(p: float, avg_win: float, avg_loss: float, cost: float) -> float:
    """EV = p·W̄ − (1−p)·L̄ − C, with W̄ and L̄ as positive magnitudes."""
    return p * avg_win - (1 - p) * avg_loss - cost


def kelly_fraction(p: float, b: float) -> float:
    """Full Kelly fraction f* = p − (1−p)/b for win probability p and payoff ratio b."""
    if b <= 0:
        raise ValueError("payoff ratio must be positive")
    return p - (1 - p) / b


def planned_exit(entry: float, atr: float) -> float:
    """Planned exit level X = max(E − 2·ATR, 0.92·E). Never call it a 'maximum loss'."""
    return max(entry - 2 * atr, 0.92 * entry)


def gap_stress(entry: float, overnight_returns: ArrayLike, worst_frac: float = 0.02) -> float:
    """G = E · |mean of the worst 2% overnight returns| (spec: over the last 500 days)."""
    r = np.sort(np.asarray(overnight_returns, dtype=np.float64))
    r = r[~np.isnan(r)]
    if r.size == 0:
        raise ValueError("no overnight returns")
    k = max(1, math.ceil(worst_frac * r.size))
    return entry * abs(float(r[:k].mean()))


def position_shares(
    equity: float,
    entry: float,
    exit_level: float,
    gap: float,
    p_lower: float,
    payoff_b: float,
    tier_multiplier: float = 1.0,
    risk_per_trade: float = 0.0075,
    kelly_multiplier: float = 0.25,
    max_position_frac: float = 0.10,
    adv_shares: float | None = None,
    max_adv_frac: float = 0.01,
) -> int:
    """Whole shares to buy (Section 7).

    shares = 0.75%·equity·tier / r with r = max(E − X, G), capped by ¼-Kelly on the Wilson lower
    bound (as a fraction of equity invested), 10% of equity per stock, and 1% of ADV.
    Tier 1 uses tier_multiplier 1.0; Tier 2 is half size (0.5).
    """
    risk_per_share = max(entry - exit_level, gap)
    if risk_per_share <= 0 or entry <= 0 or equity <= 0:
        return 0
    caps = [
        risk_per_trade * equity * tier_multiplier / risk_per_share,
        max_position_frac * equity / entry,
    ]
    kelly = kelly_multiplier * kelly_fraction(p_lower, payoff_b)
    if kelly <= 0:
        return 0
    caps.append(kelly * equity / entry)
    if adv_shares is not None:
        caps.append(max_adv_frac * adv_shares)
    return max(0, math.floor(min(caps)))


def p_up_fallback(mu_annual: float, sigma_annual: float, horizon_days: int) -> float:
    """Uncalibrated P(up) ≈ Φ(((μ − σ²/2)·T) / (σ·√T)), T in years (252 trading days).

    Label anything produced by this as "estimate — not calibrated".
    """
    if sigma_annual <= 0 or horizon_days <= 0:
        raise ValueError("sigma and horizon must be positive")
    t = horizon_days / 252
    return norm_cdf((mu_annual - sigma_annual**2 / 2) * t / (sigma_annual * math.sqrt(t)))
