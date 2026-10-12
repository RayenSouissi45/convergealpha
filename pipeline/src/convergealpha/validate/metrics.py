"""Statistics for the validation lab (spec section 9)."""

from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.stats import kurtosis, norm, skew

EULER = 0.5772156649015329


def annualize(monthly_mean: float) -> float:
    return monthly_mean * 12.0


def t_stat(x: np.ndarray) -> float:
    """Window-level t-statistic of the mean (monthly returns)."""
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))


def sharpe(x: np.ndarray) -> float:
    """Monthly Sharpe ratio (not annualized)."""
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return 0.0
    return float(x.mean() / x.std(ddof=1))


def max_drawdown(monthly: np.ndarray) -> float:
    """Largest peak-to-trough fall of the compounded series (a negative number)."""
    x = np.nan_to_num(monthly)
    wealth = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    return float((wealth / peak - 1.0).min()) if len(x) else 0.0


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """SR0: the Sharpe ratio expected from the best of n unskilled trials."""
    if n_trials <= 1:
        return 0.0
    return float(math.sqrt(max(var_sr, 0.0))) * float(
        (1 - EULER) * norm.ppf(1 - 1 / n_trials) + EULER * norm.ppf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe(x: np.ndarray, n_trials: int, var_sr: float) -> float:
    """Probability that the true Sharpe exceeds what the best of n_trials would show by luck."""
    x = x[np.isfinite(x)]
    t = len(x)
    if t < 6:
        return 0.0
    sr = sharpe(x)
    sr0 = expected_max_sharpe(n_trials, var_sr)
    g3 = float(skew(x))
    g4 = float(kurtosis(x, fisher=False))
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr**2))
    return float(norm.cdf((sr - sr0) * math.sqrt(t - 1) / denom))


def pbo(matrix: np.ndarray, blocks: int = 8) -> float:
    """Probability of backtest overfitting (combinatorially symmetric cross-validation).

    matrix: T periods x N strategies of returns. For every way of picking half the blocks as
    in-sample, take the best in-sample strategy and record its out-of-sample relative rank;
    PBO = share of splits where that rank is below the median (logit <= 0).
    """
    t, n = matrix.shape
    if n < 2 or t < blocks * 2:
        return float("nan")
    parts = np.array_split(np.arange(t), blocks)
    logits = []
    for ins in itertools.combinations(range(blocks), blocks // 2):
        is_idx = np.concatenate([parts[i] for i in ins])
        os_idx = np.concatenate([parts[i] for i in range(blocks) if i not in ins])
        is_perf = np.nanmean(matrix[is_idx], axis=0)
        os_perf = np.nanmean(matrix[os_idx], axis=0)
        best = int(np.nanargmax(is_perf))
        rank = (os_perf < os_perf[best]).sum() + 0.5 * ((os_perf == os_perf[best]).sum() - 1)
        w = (rank + 1) / (n + 1)
        logits.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(logits) <= 0))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def calibration_slope(p: np.ndarray, y: np.ndarray) -> float:
    """Slope of outcome on predicted probability (1 = perfectly calibrated spread)."""
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    if len(p) < 50 or p.std() == 0:
        return float("nan")
    return float(np.polyfit(p, y, 1)[0])
