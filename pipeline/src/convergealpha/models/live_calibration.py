"""Learning from its own results: the chances of rising are corrected by a fixed rule, using only
the app's own live forecasts and what happened to them (never the 2024-2026 holdout).

For each horizon, once forecasts of at least 4 independent periods have matured (4 weeks for the
1-week chance, 4 months for the 1-month chance...):

    gap    = log-odds(share of stocks that really rose) - log-odds(average chance the app gave)
    weight = periods / (periods + 26)          (half weight after 26 independent periods)
    shift  = weight x gap, at most +/-0.5 in log-odds

and every chance for that horizon becomes sigmoid(log-odds(chance) + shift). The order of stocks
never changes, only how confident the numbers are. The forecasts before the correction are stored
too (p_up_raw_*), so the correction is always measured on the model's own numbers and cannot
feed on itself.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES

K = 26.0
CAP = 0.5
MIN_PERIODS = 4.0
EPS = 0.02


def _logit(p: np.ndarray | float) -> Any:
    q = np.clip(p, EPS, 1 - EPS)
    return np.log(q / (1 - q))


def fit(outcomes: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """outcomes: report_card.outcomes(..., raw=True) rows (day, ticker, horizon, p_up, ret)."""
    out: dict[str, dict[str, Any]] = {}
    for days, name in HORIZON_NAMES.items():
        g = outcomes[outcomes["horizon"] == name] if not outcomes.empty else outcomes
        n_days = int(g["day"].nunique()) if not g.empty else 0
        periods = n_days / days
        if g.empty or periods < MIN_PERIODS:
            out[name] = {"shift": 0.0, "weight": 0.0, "periods": round(periods, 2), "n": len(g), "active": False}  # fmt: skip
            continue
        said = float(g["p_up"].mean())
        rose = float((g["ret"] > 0).mean())
        gap = float(_logit(rose) - _logit(said))
        weight = periods / (periods + K)
        shift = float(np.clip(weight * gap, -CAP, CAP))
        out[name] = {"shift": shift, "weight": weight, "periods": round(periods, 2), "n": len(g), "said": said, "rose": rose, "gap": gap, "active": True}  # fmt: skip
    return out


def apply(p: np.ndarray, shift: float) -> np.ndarray:
    if not shift:
        return p
    x = np.asarray(p, dtype=float)
    ok = np.isfinite(x)
    y = x.copy()
    y[ok] = 1 / (1 + np.exp(-(_logit(x[ok]) + shift)))
    return y


__all__ = ["CAP", "MIN_PERIODS", "K", "apply", "fit"]
