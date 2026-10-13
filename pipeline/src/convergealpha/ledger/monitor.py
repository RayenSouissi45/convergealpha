"""Scorecard, live baseline race, kill switch, drift (PSI) and Actions usage (spec section 10)."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES, SPY
from convergealpha.util import http
from convergealpha.util.log import get
from convergealpha.validate import metrics as V

log = get(__name__)


# --------------------------------------------------------------------------- scorecard


def scorecard(outcomes: list[dict[str, Any]], backtest: dict[str, Any] | None) -> dict[str, Any]:
    df = pd.DataFrame(outcomes)
    out: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "labels": {},
        "backtest": backtest,
    }
    if df.empty:
        out["note"] = (
            "No outcomes yet: predictions are recorded before the outcome, and the first ones mature 5 trading days after the first signals."
        )
        return out
    for label, g in df.groupby("label"):
        per = {}
        for name in HORIZON_NAMES.values():
            h = g[g["horizon"] == name]
            if h.empty:
                continue
            ex = h["excess"].astype(float)
            win, loss = ex[ex > 0], -ex[ex <= 0]
            p = h["predicted_p_up"].astype(float)
            ok = p.notna()
            per[name] = {
                "n": len(h),
                "hit_rate_up": float(h["up"].mean()),
                "hit_rate_beat": float(h["beat"].mean()),
                "mean_return": float(h["return"].mean()),
                "mean_excess": float(ex.mean()),
                "payoff": float(win.mean() / loss.mean())
                if len(win) and len(loss) and loss.mean() > 0
                else None,
                "brier_up": V.brier(p[ok].to_numpy(), h.loc[ok, "up"].astype(float).to_numpy())
                if ok.any()
                else None,
                "reliability": _reliability(
                    p[ok].to_numpy(), h.loc[ok, "up"].astype(float).to_numpy()
                )
                if ok.sum() >= 20
                else [],
            }
        out["labels"][str(label)] = per
    return out


def _reliability(p: np.ndarray, y: np.ndarray, bins: int = 5) -> list[dict[str, float]]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p >= lo) & (p <= hi)
        if m.sum() >= 5:
            out.append(
                {"predicted": float(p[m].mean()), "actual": float(y[m].mean()), "n": int(m.sum())}
            )
    return out


# --------------------------------------------------------------------------- live baseline race


PICKS_STRATEGY = "Picks – Balanced top 25"
PICKS_TOP = 25


def race(data_dir: Path, tr: pd.DataFrame) -> dict[str, Any]:
    """Each month's first snapshot: top-2% picks by strategy, held 21 trading days, excess vs SPY.

    "Picks – Balanced top 25" holds the Picks page's 25 balanced picks equally weighted, from the
    first snapshot of each month that has them: it is a live-only strategy (no backtest), so it
    starts on the first day the Picks page ran.
    """
    import pyarrow.parquet as pq

    files = sorted((data_dir / "snapshots").glob("*/*/scores.parquet"))
    if not files or SPY not in tr:
        return {"months": 0, "strategies": {}, "picks_since": None}
    by_month: dict[str, Path] = {}
    picks_month: dict[str, Path] = {}
    for f in files:
        d = f.parent.name
        by_month.setdefault(d[:6], f)
        if d[:6] not in picks_month and "pick_rank" in pq.read_schema(f).names:
            picks_month[d[:6]] = f
    idx = tr.index
    series: dict[str, list[tuple[str, float]]] = {}

    def forward(f: Path) -> tuple[pd.Timestamp, pd.Series, float] | None:
        d = pd.Timestamp(f.parent.name)
        if d not in idx:
            return None
        i = idx.get_loc(d)
        if i + 21 >= len(idx):
            return None
        fwd = tr.iloc[i + 21] / tr.iloc[i] - 1
        return d, fwd, float(fwd[SPY])

    for _, f in sorted(by_month.items()):
        got = forward(f)
        if got is None:
            continue
        d, fwd, spy = got
        s = pd.read_parquet(f).set_index("ticker")
        el = s[s["label"] != "SELL / RISK WARNING"] if "label" in s else s
        for name, col in (
            ("App (model rank)", "l1"),
            ("Equal-weight family average", "composite"),
            ("Momentum (6 months)", "ret_6m"),
        ):
            if col not in el:
                continue
            k = max(1, int(len(el) * 0.02))
            pick = el[col].dropna().sort_values(ascending=False).index[:k]
            r = fwd.reindex(pick).dropna()
            if len(r):
                series.setdefault(name, []).append(
                    (d.strftime("%Y-%m-%d"), float(r.mean()) - spy - 0.002)
                )
        series.setdefault("S&P 500", []).append((d.strftime("%Y-%m-%d"), 0.0))
    for _, f in sorted(picks_month.items()):
        got = forward(f)
        if got is None:
            continue
        d, fwd, spy = got
        ranks = pd.read_parquet(f, columns=["ticker", "pick_rank"]).set_index("ticker")
        pick = ranks["pick_rank"].dropna().sort_values().index[:PICKS_TOP]
        r = fwd.reindex(pick).dropna()
        if len(r):
            series.setdefault(PICKS_STRATEGY, []).append(
                (d.strftime("%Y-%m-%d"), float(r.mean()) - spy - 0.002)
            )
    out = {}
    for name, pts in series.items():
        m = np.array([v for _, v in pts])
        out[name] = {
            "points": [{"date": d, "excess": v} for d, v in pts],
            "cumulative": float(np.prod(1 + m) - 1) if len(m) else 0.0,
            "months": len(m),
            "max_drawdown": V.max_drawdown(m),
        }
    first_picks = min(picks_month) if picks_month else None
    return {
        "months": len(series.get("S&P 500", [])),
        "strategies": out,
        "picks_since": picks_month[first_picks].parent.name if first_picks else None,
    }


# --------------------------------------------------------------------------- kill switch


def kill_switch(race_live: dict[str, Any], data_ok: bool) -> dict[str, Any]:
    reasons = []
    app = race_live.get("strategies", {}).get("App (model rank)")
    if app and app["months"]:
        if app["max_drawdown"] <= -0.15:
            reasons.append(f"Live drawdown {app['max_drawdown']:.0%} (limit −15%)")
        pts = app["points"][-12:]
        if len(pts) >= 12:
            r12 = float(np.prod([1 + p["excess"] for p in pts]) - 1)
            if r12 < -0.05:
                reasons.append(f"Rolling 12-month net excess {r12:.1%} (limit −5%)")
    if not data_ok:
        reasons.append("Data-health failure (prices or universe not updated)")
    return {"implemented": True, "active": bool(reasons), "reasons": reasons}


# --------------------------------------------------------------------------- drift


def psi(expected: np.ndarray, actual: np.ndarray, edges: np.ndarray) -> float:
    e = np.histogram(expected, edges)[0].astype(float)
    a = np.histogram(actual, edges)[0].astype(float)
    e = np.clip(e / max(e.sum(), 1), 1e-4, None)
    a = np.clip(a / max(a.sum(), 1), 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def drift(reference: pd.DataFrame, today: pd.DataFrame, features: list[str]) -> dict[str, float]:
    out = {}
    for f in features:
        if f not in reference or f not in today:
            continue
        ref = reference[f].dropna().to_numpy()
        cur = today[f].dropna().to_numpy()
        if len(ref) < 100 or len(cur) < 100:
            continue
        edges = np.unique(np.quantile(ref, np.linspace(0, 1, 11)))
        if len(edges) < 3:
            continue
        edges[0], edges[-1] = -np.inf, np.inf
        out[f] = round(psi(ref, cur, edges), 4)
    return out


# --------------------------------------------------------------------------- Actions usage


def actions_usage() -> dict[str, Any] | None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None
    s = http.make_session(
        {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    )
    month = datetime.now(UTC).strftime("%Y-%m-01")
    total, runs, page = 0.0, 0, 1
    try:
        while page <= 10:
            r = http.get(
                s,
                f"https://api.github.com/repos/{repo}/actions/runs",
                params={"created": f">={month}", "per_page": 100, "page": page},
                timeout=30,
            )
            items = (r.json() if r is not None else {}).get("workflow_runs", [])
            for w in items:
                if w.get("run_started_at") and w.get("updated_at"):
                    total += (
                        pd.Timestamp(w["updated_at"]) - pd.Timestamp(w["run_started_at"])
                    ).total_seconds()
                    runs += 1
            if len(items) < 100:
                break
            page += 1
    except Exception as e:
        log.warning("actions usage unavailable: %s", e)
        return None
    return {
        "month": month[:7],
        "runs": runs,
        "wall_minutes": round(total / 60),
        "billing": "Standard GitHub-hosted runners are free for public repositories.",
    }


def _f(v: Any) -> float | None:
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None
