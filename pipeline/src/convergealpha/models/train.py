"""Model training (spec section 5): walk-forward with yearly refit, purge + embargo, calibration.

L1  ridge on family scores + LightGBM on all features (monotone where theory is clear), averaged;
    target: the 63-day excess return vs the S&P 500, ranked within each month.
p̂   LightGBM classifier of the triple-barrier "correct" outcome, isotonic-calibrated per regime
    on walk-forward predictions only; calibration buckets give Wilson bounds, average win/loss.
H   per horizon (1w, 1m, 3m, 6m): calibrated classifiers for "up" and "beat", and quantile models
    (10/25/50/90) widened by split-conformal so 80% ranges cover 80% on held-out data.
L2  meta-model (logistic) trained only on L1's top 5%: "will this specific trade work?".

The holdout (2024 to mid-2026) is never used here; the validation lab evaluates it exactly once.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES, HORIZONS
from convergealpha.core import stats
from convergealpha.models.dataset import FAMILY_FEATURES, FEATURES
from convergealpha.util.log import get

log = get(__name__)

DEV_YEARS = list(range(2016, 2021))
VAL_YEARS = [2021, 2022, 2023]
HOLDOUT = (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-06-30"))
EMBARGO = 10
QUANTILES = (0.1, 0.25, 0.5, 0.9)
POSITIVE = {
    "f3h",
    "f4h",
    "f5h",
    "f6h",
    "resid_mom",
    "sue_srw",
    "insider_value",
    "roic",
    "gp_assets",
    "fcf_yield",
    "industry_mom",
    "mom_12_2",
}
NEGATIVE = {"accruals", "debt_ebitda", "short_pct"}
META_FEATURES = [
    "l1_rank_pct",
    "disagreement_h",
    "n_fam",
    "regime_code",
    "atr_pct",
    "days_since_report",
    "log_adv",
    "short_pct",
    "dist_52w",
]


@dataclass
class TrainConfig:
    n_estimators: int = 250
    learning_rate: float = 0.05
    num_leaves: int = 31
    min_child_samples: int = 400
    subsample: float = 0.8
    colsample: float = 0.8
    ridge_alpha: float = 10.0
    seed: int = 7
    features: list[str] = field(default_factory=lambda: list(FEATURES))

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:10]


def _lgbm(cfg: TrainConfig, kind: str, alpha: float | None = None, monotone: bool = False) -> Any:
    import lightgbm as lgb

    params: dict[str, Any] = dict(
        n_estimators=cfg.n_estimators, learning_rate=cfg.learning_rate, num_leaves=cfg.num_leaves,
        min_child_samples=cfg.min_child_samples, subsample=cfg.subsample, subsample_freq=1,
        colsample_bytree=cfg.colsample, random_state=cfg.seed, n_jobs=-1, verbose=-1,
    )  # fmt: skip
    if monotone:
        params["monotone_constraints"] = [
            1 if f in POSITIVE else (-1 if f in NEGATIVE else 0) for f in cfg.features
        ]
    if kind == "clf":
        return lgb.LGBMClassifier(**params)
    if kind == "quantile":
        return lgb.LGBMRegressor(objective="quantile", alpha=alpha, **params)
    return lgb.LGBMRegressor(**params)


def _rank_target(df: pd.DataFrame, col: str) -> pd.Series:
    return df.groupby("date")[col].rank(pct=True) - 0.5


def _purge(
    train: pd.DataFrame, test_start: pd.Timestamp, horizon: int, trading_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Keep rows whose label window (+ embargo) ends before the test period starts."""
    pos = trading_dates.searchsorted(test_start) - (horizon + EMBARGO)
    cutoff = trading_dates[max(pos, 0)]
    return train[train["date"] < cutoff]


@dataclass
class Fitted:
    cfg: TrainConfig
    ridge: Any = None
    l1_lgbm: Any = None
    clf_correct: Any = None
    clf_up: dict[str, Any] = field(default_factory=dict)
    clf_beat: dict[str, Any] = field(default_factory=dict)
    quant: dict[str, dict[float, Any]] = field(default_factory=dict)
    medians: dict[str, float] = field(default_factory=dict)


def fit_models(
    train: pd.DataFrame,
    cfg: TrainConfig,
    trading_dates: pd.DatetimeIndex,
    test_start: pd.Timestamp | None = None,
) -> Fitted:
    """Fit every model on `train` (purged against `test_start` when given)."""
    from sklearn.linear_model import Ridge

    m = Fitted(cfg)
    X_cols = cfg.features

    def subset(target: str, horizon: int) -> pd.DataFrame:
        d = train if test_start is None else _purge(train, test_start, horizon, trading_dates)
        return d[d[target].notna()]

    d = subset("exc_3m", 63)
    y = _rank_target(d, "exc_3m")
    fam = d[FAMILY_FEATURES].fillna(50.0)
    m.medians = {c: float(train[c].median()) for c in X_cols}
    m.ridge = Ridge(alpha=cfg.ridge_alpha).fit(fam, y)
    m.l1_lgbm = _lgbm(cfg, "reg", monotone=True).fit(d[X_cols], y)
    d = subset("tb_correct", 61)
    m.clf_correct = _lgbm(cfg, "clf", monotone=True).fit(d[X_cols], d["tb_correct"].astype(int))
    for h in HORIZONS:
        name = HORIZON_NAMES[h]
        d = subset(f"ret_{name}", h)
        if len(d) < 1000:
            continue
        m.clf_up[name] = _lgbm(cfg, "clf").fit(d[X_cols], d[f"up_{name}"].astype(int))
        m.clf_beat[name] = _lgbm(cfg, "clf", monotone=True).fit(
            d[X_cols], d[f"beat_{name}"].astype(int)
        )
        m.quant[name] = {
            q: _lgbm(cfg, "quantile", alpha=q).fit(d[X_cols], d[f"ret_{name}"]) for q in QUANTILES
        }
    return m


def predict(m: Fitted, X: pd.DataFrame) -> pd.DataFrame:
    cols = m.cfg.features
    Xf = X[cols]
    out = pd.DataFrame(index=X.index)
    fam = X[FAMILY_FEATURES].fillna(50.0)
    r = pd.Series(m.ridge.predict(fam), index=X.index)
    g = pd.Series(m.l1_lgbm.predict(Xf), index=X.index)
    out["l1_ridge"] = r
    out["l1_lgbm"] = g
    out["raw_correct"] = m.clf_correct.predict_proba(Xf)[:, 1]
    for name, mdl in m.clf_up.items():
        out[f"raw_up_{name}"] = mdl.predict_proba(Xf)[:, 1]
        out[f"raw_beat_{name}"] = m.clf_beat[name].predict_proba(Xf)[:, 1]
        for q, qm in m.quant[name].items():
            out[f"q{int(q * 100)}_{name}"] = qm.predict(Xf)
    return out


def l1_score(pred: pd.DataFrame, dates: pd.Series) -> pd.Series:
    """Average of the ridge and LightGBM scores, each ranked within its month."""
    r = pred["l1_ridge"].groupby(dates).rank(pct=True)
    g = pred["l1_lgbm"].groupby(dates).rank(pct=True)
    return (r + g) / 2


def walk_forward(
    df: pd.DataFrame, years: list[int], cfg: TrainConfig, trading_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Out-of-sample predictions: for each test year, models trained only on earlier, purged data."""
    outs = []
    for y in years:
        t0 = time.time()
        start = pd.Timestamp(f"{y}-01-01")
        test = df[(df["date"] >= start) & (df["date"] < pd.Timestamp(f"{y + 1}-01-01"))]
        if test.empty:
            continue
        train = df[df["date"] < start]
        m = fit_models(train, cfg, trading_dates, test_start=start)
        p = predict(m, test)
        p["l1"] = l1_score(p, test["date"])
        outs.append(
            pd.concat(
                [
                    test[
                        [
                            "date",
                            "ticker",
                            "regime",
                            "sector",
                            *[
                                c
                                for c in df.columns
                                if c.startswith(("tb_", "ret_", "up_", "beat_", "exc_"))
                            ],
                            *META_FEATURES[1:],
                        ]
                    ],
                    p,
                ],
                axis=1,
            )
        )
        log.info(
            "walk-forward %d: trained on %d rows, predicted %d (%.0fs)",
            y,
            len(train),
            len(test),
            time.time() - t0,
        )
    return pd.concat(outs, ignore_index=True) if outs else pd.DataFrame()


# --------------------------------------------------------------------------- calibration


@dataclass
class Calibration:
    correct: dict[str, Any]  # regime -> IsotonicRegression (plus "all")
    up: dict[str, Any]
    beat: dict[str, Any]
    conformal: dict[str, float]  # horizon -> widening Q for the 10-90 interval
    buckets: list[dict[str, float]]  # calibrated p-hat buckets with n, wins, wilson, avg win/loss
    meta: Any = None
    meta_medians: dict[str, float] = field(default_factory=dict)
    meta_sectors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)  # horizon -> held-out rows used


def _iso(x: np.ndarray, y: np.ndarray) -> Any:
    from sklearn.isotonic import IsotonicRegression

    return IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(x, y)


def calibrate(oos: pd.DataFrame) -> Calibration:
    """Fit calibration on walk-forward predictions (dev + validation years only)."""
    d = oos[oos["tb_correct"].notna()]
    correct = {"all": _iso(d["raw_correct"].to_numpy(), d["tb_correct"].to_numpy())}
    for reg, g in d.groupby("regime"):
        if len(g) >= 2000:
            correct[str(reg)] = _iso(g["raw_correct"].to_numpy(), g["tb_correct"].to_numpy())
    up, beat, conf = {}, {}, {}
    conf_counts: dict[str, int] = {}
    for name in HORIZON_NAMES.values():
        if f"raw_up_{name}" not in oos:
            continue
        g = oos[oos[f"up_{name}"].notna()]
        conf_counts[name] = len(g)
        up[name] = _iso(g[f"raw_up_{name}"].to_numpy(), g[f"up_{name}"].to_numpy())
        beat[name] = _iso(g[f"raw_beat_{name}"].to_numpy(), g[f"beat_{name}"].to_numpy())
        # Split-conformal (CQR): widen [q10, q90] so 80% of held-out outcomes fall inside.
        e = np.maximum(
            g[f"q10_{name}"] - g[f"ret_{name}"], g[f"ret_{name}"] - g[f"q90_{name}"]
        ).to_numpy()
        n = len(e)
        level = min(1.0, np.ceil((n + 1) * 0.8) / n)
        conf[name] = float(np.quantile(e, level)) if n else 0.0
    cal = Calibration(correct, up, beat, conf, [], counts={**conf_counts, "p_hat": len(d)})
    p = apply_correct(cal, d["raw_correct"].to_numpy(), d["regime"].astype(str).to_numpy())
    cal.buckets = buckets(p, d["tb_correct"].to_numpy(), d["tb_excess"].to_numpy())
    return cal


def apply_correct(cal: Calibration, raw: np.ndarray, regimes: np.ndarray) -> np.ndarray:
    out = cal.correct["all"].predict(raw)
    for reg, iso in cal.correct.items():
        if reg == "all":
            continue
        mask = regimes == reg
        if mask.any():
            out[mask] = iso.predict(raw[mask])
    return np.asarray(out)


def buckets(
    p: np.ndarray,
    correct: np.ndarray,
    excess: np.ndarray,
    edges: tuple[float, ...] = (
        0.0,
        0.35,
        0.40,
        0.45,
        0.48,
        0.50,
        0.52,
        0.55,
        0.58,
        0.62,
        0.66,
        1.01,
    ),
) -> list[dict[str, float]]:
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n == 0:
            continue
        wins = int(correct[m].sum())
        wl, wh = stats.wilson_interval(wins, n)
        ex = excess[m]
        win = ex[ex > 0]
        loss = -ex[ex <= 0]
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "n": n,
                "wins": wins,
                "rate": wins / n,
                "wilson_lo": wl,
                "wilson_hi": wh,
                "avg_win": float(win.mean()) if len(win) else 0.0,
                "avg_loss": float(loss.mean()) if len(loss) else 0.0,
                "mean_p": float(p[m].mean()),
            }
        )
    return out


def bucket_for(cal: Calibration, p: float) -> dict[str, float] | None:
    for b in cal.buckets:
        if b["lo"] <= p < b["hi"]:
            return b
    return None


def fit_meta(oos: pd.DataFrame, cal: Calibration) -> None:
    """L2: logistic regression on L1's top 5% (walk-forward predictions)."""
    from sklearn.linear_model import LogisticRegression

    d = oos[oos["tb_correct"].notna()].copy()
    d["l1_rank_pct"] = d.groupby("date")["l1"].rank(pct=True)
    top = d[d["l1_rank_pct"] >= 0.95]
    if len(top) < 500:
        return
    X, med, sectors = meta_matrix(top, None, None)
    cal.meta = LogisticRegression(C=0.5, max_iter=500).fit(X, top["tb_correct"].astype(int))
    cal.meta_medians = med
    cal.meta_sectors = sectors


def meta_matrix(
    d: pd.DataFrame, medians: dict[str, float] | None, sectors: list[str] | None
) -> tuple[np.ndarray, dict[str, float], list[str]]:
    num = d[META_FEATURES].astype("float64")
    med = medians or {c: float(num[c].median()) for c in META_FEATURES}
    num = num.fillna(pd.Series(med))
    mu = num.mean()
    sd = num.std().replace(0, 1)
    if medians is None:
        med = {
            **med,
            **{f"__mu_{c}": float(mu[c]) for c in META_FEATURES},
            **{f"__sd_{c}": float(sd[c]) for c in META_FEATURES},
        }
    z = np.column_stack([(num[c] - med[f"__mu_{c}"]) / med[f"__sd_{c}"] for c in META_FEATURES])
    secs = sectors or sorted(d["sector"].dropna().astype(str).unique().tolist())
    oh = (
        np.column_stack([(d["sector"].astype(str) == s).astype(float) for s in secs])
        if secs
        else np.zeros((len(d), 0))
    )
    return np.column_stack([z, oh]), med, secs


# --------------------------------------------------------------------------- persistence


def save(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)


def load(path: Path) -> Any:
    with open(path, "rb") as f:
        return pickle.load(f)
