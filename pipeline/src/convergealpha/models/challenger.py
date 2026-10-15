"""A challenger model, trained every week next to the champion and judged on the same footing.

The champion is the configuration the app uses (TrainConfig). The challenger is ONE alternative
fixed in advance (below). Every Saturday both are trained walk-forward on 2016-2023 only (the
2024-2026 holdout is never evaluated again, so the validation lab is not run for the challenger),
and compared on the chance of rising over 1 month and 6 months (the validated horizons):

- per half (2016-2019 and 2020-2023): AUC of the raw score, and the Brier score of the chance after
  calibrating on the OTHER half (cross-fitted, so neither model is scored on what it was
  calibrated on);
- the challenger is "ahead on history" if its Brier is lower for both horizons in both halves.

The challenger also forecasts every day in the shadow (stored with the champion's forecasts, never
shown as advice). It may replace the champion only by the rule registered as
challenger-2026-v1: ahead on history AND a lower Brier than the champion on the live report card
for both horizons over at least 6 independent periods of each. Until then the champion stays.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.models import train as T

PROTOCOL_ID = "challenger-2026-v1"
HORIZONS = ("1m", "6m")
HALVES = ((2016, 2019), (2020, 2023))
LIVE_MIN_PERIODS = 6


def config(champion: T.TrainConfig) -> T.TrainConfig:
    """The challenger, fixed in advance: a slower, more regularised version of the champion
    (more, smaller trees and fewer stocks per leaf decision), the usual remedy for noisy targets."""
    return replace(champion, n_estimators=500, learning_rate=0.03, num_leaves=15, min_child_samples=800, subsample=0.7, colsample=0.7)  # fmt: skip


def protocol_digest(champion: T.TrainConfig | None = None) -> str:
    spec = {"id": PROTOCOL_ID, "challenger": asdict(config(champion or T.TrainConfig())), "horizons": HORIZONS, "halves": HALVES, "live_min_periods": LIVE_MIN_PERIODS}  # fmt: skip
    return hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _auc(x: np.ndarray, y: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score

    ok = np.isfinite(x) & np.isfinite(y)
    return (
        float(roc_auc_score(y[ok], x[ok])) if ok.sum() > 10 and len(np.unique(y[ok])) > 1 else None
    )


def _half_scores(oos: pd.DataFrame, h: str, min_bin: int) -> dict[str, dict[str, float | None]]:
    raw, up = f"raw_up_{h}", f"up_{h}"
    d = oos[oos[raw].notna() & oos[up].notna()].copy()
    d["year"] = pd.to_datetime(d["date"]).dt.year
    out: dict[str, dict[str, float | None]] = {}
    for a, b in HALVES:
        test = d[d["year"].between(a, b)]
        other = d[~d["year"].between(a, b)]
        if test.empty or other.empty:
            continue
        iso = T._iso(other[raw].to_numpy(), other[up].to_numpy(), min_bin)
        p = iso.predict(test[raw].to_numpy())
        y = test[up].to_numpy(dtype=float)
        out[f"{a}-{b}"] = {"auc": _auc(test[raw].to_numpy(dtype=float), y), "brier": float(np.mean((p - y) ** 2)), "n": float(len(test))}  # fmt: skip
    return out


def compare(champ_oos: pd.DataFrame, chall_oos: pd.DataFrame, min_bin: int = 200) -> dict[str, Any]:
    res: dict[str, Any] = {"protocol": PROTOCOL_ID, "horizons": {}}
    ahead = True
    for h in HORIZONS:
        c, x = _half_scores(champ_oos, h, min_bin), _half_scores(chall_oos, h, min_bin)
        better = bool(c) and all(k in x and x[k]["brier"] is not None and c[k]["brier"] is not None and x[k]["brier"] < c[k]["brier"] for k in c)  # type: ignore[operator]  # fmt: skip
        ahead = ahead and better
        res["horizons"][h] = {"champion": c, "challenger": x, "challenger_better": better}
    res["ahead_on_history"] = ahead
    return res


def live_compare(df: pd.DataFrame) -> dict[str, Any]:
    """df: report-card outcome rows with both chances (p_up for the champion, p_ch for the
    challenger). Brier per horizon and whether the challenger is lower with enough periods."""
    from convergealpha.config import HORIZON_NAMES

    days_of = {v: k for k, v in HORIZON_NAMES.items()}
    out: dict[str, Any] = {}
    for h in HORIZONS:
        g = df[(df["horizon"] == h) & df["p_ch"].notna()] if not df.empty and "p_ch" in df else pd.DataFrame()  # fmt: skip
        if g.empty:
            out[h] = {"n": 0, "periods": 0.0}
            continue
        y = (g["ret"] > 0).to_numpy(dtype=float)
        periods = g["day"].nunique() / days_of[h]
        bc = float(np.mean((g["p_up"].to_numpy() - y) ** 2))
        bx = float(np.mean((g["p_ch"].to_numpy() - y) ** 2))
        out[h] = {"n": len(g), "periods": round(periods, 2), "brier_champion": bc, "brier_challenger": bx, "challenger_better": bx < bc, "enough": periods >= LIVE_MIN_PERIODS}  # fmt: skip
    return out


def register(data_dir: Any) -> dict[str, Any] | None:
    """Seal the challenger and its replacement rule in the experiment log (once)."""
    from convergealpha.ledger import experiments as X

    digest = protocol_digest()
    if any(e.get("protocol_id") == PROTOCOL_ID and e.get("protocol_digest") == digest for e in X.entries(data_dir)):  # fmt: skip
        return None
    return X.record(
        data_dir,
        {
            "experiment": "challenger model (registered in advance)",
            "question": "Does a more regularised model forecast better than the champion, on history and live?",
            "protocol_id": PROTOCOL_ID,
            "protocol_digest": digest,
            "period": "weekly on 2016-2023 (walk-forward) and daily live in the shadow",
            "status": "registered",
            "decision": {
                "replace_if": "lower Brier for 1m and 6m in both halves of 2016-2023 AND live over 6+ independent periods of each"
            },
        },
    )


def run_weekly(df: pd.DataFrame, years: list[int], champion_cfg: T.TrainConfig, champ_oos: pd.DataFrame, trading: pd.DatetimeIndex, out_dir: Any) -> dict[str, Any]:  # fmt: skip
    """Train the challenger like the champion (walk-forward on the pre-holdout years, then on
    all data for the daily shadow forecasts) and compare them. Writes challenger_*.pkl/json."""
    from convergealpha.util.io import write_json

    cfg = config(champion_cfg)
    oos = T.walk_forward(df[df["date"] < T.HOLDOUT[0]], years, cfg, trading)
    cal = T.calibrate(oos, cfg)
    res = {**compare(champ_oos, oos, cfg.calibration_min_bin), "protocol_digest": protocol_digest(champion_cfg), "config": asdict(cfg)}  # fmt: skip
    final = T.fit_models(df, cfg, trading)
    T.save(out_dir / "challenger_fitted.pkl", final)
    T.save(out_dir / "challenger_calibration.pkl", cal)
    write_json(res, out_dir / "challenger.json")
    return res


__all__ = [
    "HORIZONS",
    "PROTOCOL_ID",
    "compare",
    "config",
    "live_compare",
    "protocol_digest",
    "register",
    "run_weekly",
]
