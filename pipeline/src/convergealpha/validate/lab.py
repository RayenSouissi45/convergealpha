"""Validation lab (spec section 9): decides which horizons/labels may leave RESEARCH MODE.

Periods: development = walk-forward 2016-2020, validation = 2021-2023 (used for thresholds and
calibration), holdout = 2024 to mid-2026, evaluated ONCE: its results are frozen in the data repo
(validation/holdout_log.json) and reused until the model configuration changes, which is logged
as a new trial and flagged as contaminated.

Strategy returns use non-overlapping monthly rebalancing on 21-day excess returns vs the S&P 500,
equal weight, net of costs (turnover x round-trip cost). Trade-level statistics (hit rate, payoff,
EV) use the 60-day triple-barrier outcomes of the same picks.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES
from convergealpha.models import train as T
from convergealpha.models.dataset import FAMILY_FEATURES
from convergealpha.util.io import read_json, write_json
from convergealpha.util.log import get
from convergealpha.validate import metrics as V

if TYPE_CHECKING:
    from convergealpha.run import RunContext

log = get(__name__)

COST = 0.002  # round trip per unit of turnover (2x in the cost stress)
HAIRCUT = 0.5  # spec: halve backtested excess returns (survivorship bias) before using them
TOP = 0.02
PERIODS = {"development": (2016, 2020), "validation": (2021, 2023)}
FAMILY_GROUPS = {
    "F3 earnings": ["f3h", "sue_srw", "days_since_report"],
    "F4 insiders": ["f4h", "insider_value"],
    "F5 trend": [
        "f5h",
        "resid_mom",
        "industry_mom",
        "trend",
        "mom_12_2",
        "mom_1m",
        "mom_3m",
        "mom_6m",
    ],
    "F6 quality": ["f6h", "roic", "gp_assets", "accruals", "fcf_yield", "debt_ebitda"],
}


def _period(df: pd.DataFrame, years: tuple[int, int]) -> pd.DataFrame:
    y = df["date"].dt.year
    return df[(y >= years[0]) & (y <= years[1])]


def portfolio(
    df: pd.DataFrame, score: str, top: float = TOP, cost: float = COST, ascending: bool = False
) -> dict[str, Any]:
    """Monthly top-`top` portfolio by `score`: net excess series, trades and turnover."""
    months: list[pd.Timestamp] = []
    rets: list[float] = []
    prev: set[str] = set()
    turnover = []
    picks_all = []
    for d, g in df.groupby("date"):
        g = g[g[score].notna() & g["exc_1m"].notna()]
        if len(g) < 50:
            continue
        k = max(1, int(round(len(g) * top)))
        pick = g.sort_values(score, ascending=ascending).head(k)
        names = set(pick["ticker"])
        to = 1.0 if not prev else len(names - prev) / len(names)
        turnover.append(to)
        rets.append(float(pick["exc_1m"].mean()) - to * cost)
        months.append(d)
        prev = names
        picks_all.append(pick)
    picks = pd.concat(picks_all) if picks_all else pd.DataFrame()
    return {
        "months": months,
        "monthly": np.array(rets),
        "turnover": float(np.mean(turnover)) if turnover else float("nan"),
        "picks": picks,
    }


def trade_stats(picks: pd.DataFrame) -> dict[str, float | None]:
    if picks.empty or "tb_excess" not in picks:
        return {"trades": 0, "hit_rate": None, "payoff": None, "ev": None}
    ex = picks["tb_excess"].dropna()
    win, loss = ex[ex > 0], -ex[ex <= 0]
    return {
        "trades": len(ex),
        "hit_rate": float((ex > 0).mean()) if len(ex) else None,
        "payoff": float(win.mean() / loss.mean())
        if len(win) and len(loss) and loss.mean() > 0
        else None,
        "ev": float(ex.mean()) if len(ex) else None,
    }


def summarize(p: dict[str, Any]) -> dict[str, Any]:
    m = p["monthly"]
    return {
        "months": len(m),
        "net_excess_annual": V.annualize(float(np.nanmean(m))) if len(m) else None,
        "t_stat": V.t_stat(m),
        "sharpe_annual": V.sharpe(m) * math.sqrt(12),
        "max_drawdown": V.max_drawdown(m),
        "turnover": p["turnover"],
        **trade_stats(p["picks"]),
    }


def breakdown(p: dict[str, Any], by: str) -> dict[str, float]:
    picks = p["picks"]
    if picks.empty or by not in picks:
        return {}
    g = picks.groupby(by)["exc_1m"].mean()
    return {str(k): float(v * 12) for k, v in g.items() if pd.notna(v)}


def strategies(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    out = {
        "app": portfolio(df, "l1"),
        "baseline_momentum": portfolio(df, "mom_12_2") if "mom_12_2" in df else None,
        "baseline_family_average": portfolio(df, "composite_h") if "composite_h" in df else None,
        "baseline_all_eligible": portfolio(df, "l1", top=1.0),
    }
    if "meta" in df:
        out["app_meta"] = portfolio(df[df["meta"].notna()], "meta", top=0.5)
    return {k: v for k, v in out.items() if v is not None}


def variants_matrix(df: pd.DataFrame) -> np.ndarray:
    """Monthly returns of the strategy variants tried (trials for DSR and PBO)."""
    cols = []
    for score, top in (
        ("l1", 0.01),
        ("l1", 0.02),
        ("l1", 0.05),
        ("l1", 0.10),
        ("composite_h", 0.02),
        ("mom_12_2", 0.02),
        ("l1_lgbm", 0.02),
        ("l1_ridge", 0.02),
    ):
        if score in df:
            cols.append(portfolio(df, score, top=top)["monthly"])
    n = min(len(c) for c in cols) if cols else 0
    return np.column_stack([c[:n] for c in cols]) if cols else np.zeros((0, 0))


def calibration(df: pd.DataFrame, cal: T.Calibration) -> dict[str, Any]:
    out: dict[str, Any] = {}
    d = df[df["tb_correct"].notna()]
    if len(d):
        p = T.apply_correct(cal, d["raw_correct"].to_numpy(), d["regime"].astype(str).to_numpy())
        y = d["tb_correct"].to_numpy()
        out["trade"] = {
            "brier": V.brier(p, y),
            "brier_base": V.brier(np.full_like(p, y.mean()), y),
            "slope": V.calibration_slope(p, y),
            "n": len(d),
            "reliability": reliability(p, y),
        }
    for name in HORIZON_NAMES.values():
        if name not in cal.up or f"up_{name}" not in df:
            continue
        g = df[df[f"up_{name}"].notna()]
        if not len(g):
            continue
        pu = cal.up[name].predict(g[f"raw_up_{name}"].to_numpy())
        yu = g[f"up_{name}"].to_numpy()
        pb = cal.beat[name].predict(g[f"raw_beat_{name}"].to_numpy())
        yb = g[f"beat_{name}"].to_numpy()
        lo = g[f"q10_{name}"] - cal.conformal.get(name, 0)
        hi = g[f"q90_{name}"] + cal.conformal.get(name, 0)
        cover = float(((g[f"ret_{name}"] >= lo) & (g[f"ret_{name}"] <= hi)).mean())
        out[name] = {
            "n": len(g),
            "up": {
                "brier": V.brier(pu, yu),
                "brier_base": V.brier(np.full_like(pu, yu.mean()), yu),
                "slope": V.calibration_slope(pu, yu),
                "reliability": reliability(pu, yu),
            },
            "beat": {
                "brier": V.brier(pb, yb),
                "brier_base": V.brier(np.full_like(pb, yb.mean()), yb),
                "slope": V.calibration_slope(pb, yb),
                "reliability": reliability(pb, yb),
            },
            "coverage_80": cover,
        }
    return out


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict[str, float]]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p <= hi)
        if m.sum() >= 20:
            out.append(
                {"predicted": float(p[m].mean()), "actual": float(y[m].mean()), "n": int(m.sum())}
            )
    return out


def ablation(df: pd.DataFrame, cfg: T.TrainConfig, trading: pd.DatetimeIndex) -> dict[str, Any]:
    """Drop one family at a time (L1 only, walk-forward) and compare net excess per period."""
    from sklearn.linear_model import Ridge

    base = {
        name: summarize(portfolio(_period(df, yrs), "l1"))["net_excess_annual"]
        for name, yrs in PERIODS.items()
    }
    out: dict[str, Any] = {"full_model": base, "families": {}}
    years = [
        y
        for y in range(PERIODS["development"][0], PERIODS["validation"][1] + 1)
        if (df["date"].dt.year == y).any()
    ]
    for fam, cols in FAMILY_GROUPS.items():
        feats = [f for f in cfg.features if f not in cols]
        preds = []
        for y in years:
            start = pd.Timestamp(f"{y}-01-01")
            test = df[(df["date"] >= start) & (df["date"].dt.year == y)]
            train = T._purge(df[(df["date"] < start) & df["exc_3m"].notna()], start, 63, trading)
            if train.empty or test.empty:
                continue
            yv = T._rank_target(train, "exc_3m")
            fam_cols = [c for c in FAMILY_FEATURES if c not in cols]
            r = Ridge(alpha=cfg.ridge_alpha).fit(train[fam_cols].fillna(50.0), yv)
            g = T._lgbm(T.TrainConfig(features=feats), "reg").fit(train[feats], yv)
            p = test[["date", "ticker", "exc_1m"]].copy()
            p["s"] = (
                pd.Series(r.predict(test[fam_cols].fillna(50.0)), index=test.index)
                .groupby(test["date"])
                .rank(pct=True)
                + pd.Series(g.predict(test[feats]), index=test.index)
                .groupby(test["date"])
                .rank(pct=True)
            ) / 2
            preds.append(p)
        if not preds:
            continue
        pdf = pd.concat(preds)
        res = {
            name: summarize(portfolio(_period(pdf, yrs), "s"))["net_excess_annual"]
            for name, yrs in PERIODS.items()
        }
        drop = {
            k: (base[k] - res[k]) if base[k] is not None and res[k] is not None else None
            for k in PERIODS
        }
        keep = all(v is not None and v >= 0.005 for v in drop.values())
        out["families"][fam] = {"without": res, "loss_when_removed": drop, "keep": keep}
    return out


def evaluate_holdout(
    df: pd.DataFrame, cfg: T.TrainConfig, trading: pd.DatetimeIndex
) -> tuple[pd.DataFrame, T.Calibration]:
    """Train once on everything before 2024 (purged), predict the holdout period."""
    start, end = T.HOLDOUT
    train = df[df["date"] < start]
    test = df[(df["date"] >= start) & (df["date"] <= end)]
    m = T.fit_models(train, cfg, trading, test_start=start)
    p = T.predict(m, test)
    p["l1"] = T.l1_score(p, test["date"])
    out = pd.concat([test.reset_index(drop=True), p.reset_index(drop=True)], axis=1)
    return out, T.Calibration({}, {}, {}, {}, [])


def run(ctx: RunContext, models_dir: Path, site_dir: Path) -> dict[str, Any]:
    df = pd.read_parquet(models_dir / "dataset.parquet")
    oos = pd.read_parquet(models_dir / "oos_devval.parquet")
    cal: T.Calibration = T.load(models_dir / "calibration.pkl")
    cfg = T.TrainConfig()
    trading = pd.DatetimeIndex(sorted(df["date"].unique()))
    # Trading calendar for purging: use the full price index if available.
    try:
        from convergealpha.sources import prices as P

        trading = P.build_panel(P.load_rows(ctx.paths.data, ["SPY"])).close.index
    except Exception:
        pass
    oos = (
        oos.merge(
            df[["date", "ticker", "mom_12_2", "composite_h", "log_mcap"]],
            on=["date", "ticker"],
            how="left",
        )
        if "mom_12_2" not in oos
        else oos
    )
    # Meta-model scores on the walk-forward top 5% (in-sample for the meta-model: labelled as such).
    if cal.meta is not None:
        o = oos.copy()
        o["l1_rank_pct"] = o.groupby("date")["l1"].rank(pct=True)
        top = o[o["l1_rank_pct"] >= 0.95]
        Xm, _, _ = T.meta_matrix(top, cal.meta_medians, cal.meta_sectors)
        oos.loc[top.index, "meta"] = cal.meta.predict_proba(Xm)[:, 1]

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": cfg.digest(),
        "periods": {},
        "notes": [],
    }
    for name, yrs in PERIODS.items():
        d = _period(oos, yrs)
        strat = strategies(d)
        report["periods"][name] = {
            "years": list(yrs),
            "strategies": {k: summarize(v) for k, v in strat.items()},
            "cost_stress_2x": summarize(portfolio(d, "l1", cost=2 * COST)),
            "by_regime": breakdown(strat["app"], "regime"),
            "by_sector": breakdown(strat["app"], "sector"),
            "by_size": _size_breakdown(strat["app"]),
            "calibration": calibration(d, cal),
            "calibration_note": "in-sample: calibration is fitted on development + validation predictions",
        }
    # Trials (variants) for DSR and PBO, on development + validation.
    mat = variants_matrix(oos)
    srs = [V.sharpe(mat[:, j]) for j in range(mat.shape[1])] if mat.size else []
    app_m = portfolio(oos, "l1")["monthly"]
    report["overfitting"] = {
        "trials": len(srs),
        "deflated_sharpe": V.deflated_sharpe(
            app_m, max(len(srs), 1), float(np.var(srs)) if srs else 0.0
        ),
        "pbo": V.pbo(mat) if mat.size else None,
    }
    report["ablation"] = ablation(
        oos.merge(
            df[[c for c in df.columns if c not in oos.columns] + ["date", "ticker"]],
            on=["date", "ticker"],
            how="left",
        ),
        cfg,
        trading,
    )

    # ---- holdout: exactly once per configuration
    log_path = ctx.paths.data / "validation" / "holdout_log.json"
    hlog = read_json(log_path, [])
    digest = hashlib.sha256(
        json.dumps({"cfg": cfg.digest(), "features": cfg.features}).encode()
    ).hexdigest()[:12]
    prior = next((e for e in hlog if e.get("digest") == digest), None)
    if prior is not None:
        holdout = prior["results"]
        report["notes"].append(
            f"Holdout results reused from {prior['run_at']} (evaluated once for this configuration)."
        )
    else:
        ho, _ = evaluate_holdout(df, cfg, trading)
        strat = strategies(ho)
        holdout = {
            "period": [str(T.HOLDOUT[0].date()), str(T.HOLDOUT[1].date())],
            "strategies": {k: summarize(v) for k, v in strat.items()},
            "cost_stress_2x": summarize(portfolio(ho, "l1", cost=2 * COST)),
            "calibration": calibration(ho, cal),
            "by_regime": breakdown(strat["app"], "regime"),
        }
        hlog.append(
            {
                "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "digest": digest,
                "touch": len(hlog) + 1,
                "results": holdout,
            }
        )
        write_json(hlog, log_path, pretty=True)
        if len(hlog) > 1:
            report["notes"].append(
                f"WARNING: the holdout has now been evaluated {len(hlog)} times (configuration changed). Its results are contaminated."
            )
    report["holdout"] = holdout
    report["holdout_touches"] = len(hlog)
    report["verdict"] = verdict(report)
    write_json(report, models_dir / "validation.json", pretty=True)
    write_json(
        report, ctx.paths.data / "validation" / f"{datetime.now(UTC):%Y%m%d}.json", pretty=True
    )
    write_json(report, site_dir / "validation.json")
    log.info("validation verdict: %s", report["verdict"]["summary"])
    return report


def _size_breakdown(p: dict[str, Any]) -> dict[str, float]:
    picks = p["picks"]
    if picks.empty or "log_mcap" not in picks:
        return {}
    q = pd.qcut(picks["log_mcap"], 3, labels=["small", "mid", "large"], duplicates="drop")
    return {
        str(k): float(v * 12) for k, v in picks.groupby(q, observed=True)["exc_1m"].mean().items()
    }


def verdict(r: dict[str, Any]) -> dict[str, Any]:
    """Apply the pass criteria. Returns per-check results and the list of validated items."""
    dev = r["periods"]["development"]["strategies"]
    val = r["periods"]["validation"]["strategies"]
    ho = r["holdout"]["strategies"] if r.get("holdout") else {}
    app = {
        "development": dev.get("app", {}),
        "validation": val.get("app", {}),
        "holdout": ho.get("app", {}),
    }

    def best_baseline(s: dict[str, Any]) -> float:
        vals = [v.get("net_excess_annual") for k, v in s.items() if k.startswith("baseline")]
        vals = [x for x in vals if x is not None]
        return float(max(vals + [0.0]))

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, value: str) -> None:
        checks.append({"check": name, "passed": ok, "value": value})

    for per, s in app.items():
        ne, t = s.get("net_excess_annual"), s.get("t_stat")
        # Shown halved like every backtested excess; sign and t are unchanged by the haircut.
        add(
            f"Net excess > 0 with t ≥ 2 ({per})",
            None if ne is None else bool(ne > 0 and (t or 0) >= 2),
            "—" if ne is None else f"{HAIRCUT * ne:+.2%}/yr (halved), t = {t:.2f}",
        )
    for per, s in (("development", dev), ("validation", val), ("holdout", ho)):
        a = s.get("app", {}).get("net_excess_annual")
        b = best_baseline(s)
        diff = None if a is None else HAIRCUT * (a - b)
        add(
            f"≥ +1%/yr better than the best baseline ({per}, after the 50% haircut)",
            None if diff is None else bool(diff >= 0.01),
            "—" if diff is None else f"{diff:+.2%}/yr vs best baseline",
        )
    d_ne, h_ne = (
        app["development"].get("net_excess_annual"),
        app["holdout"].get("net_excess_annual"),
    )
    add(
        "Holdout ≥ 50% of the development result",
        None if d_ne is None or h_ne is None else bool(d_ne > 0 and h_ne >= 0.5 * d_ne),
        "—"
        if d_ne is None or h_ne is None
        else f"{HAIRCUT * h_ne:+.2%} vs {HAIRCUT * d_ne:+.2%} (both halved)",
    )
    slope = (r.get("holdout", {}).get("calibration", {}).get("trade") or {}).get("slope")
    add(
        "Calibration slope 0.8–1.2 (holdout, trade label)",
        None
        if slope is None or (isinstance(slope, float) and math.isnan(slope))
        else bool(0.8 <= slope <= 1.2),
        "—" if slope is None else f"{slope:.2f}",
    )
    mdd = min([s.get("max_drawdown") or 0 for s in app.values()])
    add("Max drawdown < 25%", bool(mdd > -0.25), f"{mdd:.1%}")
    dsr = r["overfitting"]["deflated_sharpe"]
    add(
        "Deflated Sharpe ratio ≥ 0.95",
        bool(dsr >= 0.95),
        f"{dsr:.2f} ({r['overfitting']['trials']} trials)",
    )
    pbo_v = r["overfitting"]["pbo"]
    add(
        "Probability of backtest overfitting ≤ 20%",
        None if pbo_v is None else bool(pbo_v <= 0.20),
        "—" if pbo_v is None else f"{pbo_v:.0%}",
    )
    if r.get("holdout_touches", 1) > 1:
        add("Holdout evaluated only once", False, f"{r['holdout_touches']} evaluations")
    label_pass = all(c["passed"] is True for c in checks)

    # Horizon probabilities: leave research mode only if better than the base rate and calibrated on the holdout.
    validated = ["BUY label (60-day trade)"] if label_pass else []
    horizon_checks = {}
    hcal = r.get("holdout", {}).get("calibration", {})
    for name in HORIZON_NAMES.values():
        h = hcal.get(name)
        if not h:
            horizon_checks[name] = {"passed": False, "why": "no holdout data"}
            continue
        ok_up = h["up"]["brier"] < h["up"]["brier_base"] and 0.8 <= (h["up"]["slope"] or 0) <= 1.2
        ok_beat = (
            h["beat"]["brier"] < h["beat"]["brier_base"] and 0.8 <= (h["beat"]["slope"] or 0) <= 1.2
        )
        horizon_checks[name] = {"up": ok_up, "beat": ok_beat, "coverage_80": h.get("coverage_80")}
        if ok_up:
            validated.append(f"P(up) {name}")
        if ok_beat:
            validated.append(f"P(beat) {name}")
    passed = sum(c["passed"] is True for c in checks)
    return {
        "checks": checks,
        "label_pass": label_pass,
        "horizons": horizon_checks,
        "validated": validated,
        "summary": f"{passed} of {len(checks)} checks passed; validated: {', '.join(validated) or 'nothing yet'}",
    }
