"""Apply the trained model bundle to today's stocks (called by decide/pipeline.py).

Raises if no model bundle is available; the caller then falls back to the transparent estimate.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from convergealpha.config import HORIZON_NAMES
from convergealpha.core import stats
from convergealpha.models import dataset as D
from convergealpha.models import train as T
from convergealpha.util.log import get

if TYPE_CHECKING:
    from convergealpha.features.evidence import Sources
    from convergealpha.run import RunContext

log = get(__name__)


def bundle_dir(ctx: RunContext) -> Path:
    return ctx.paths.cache / "models"


def _history_today(src: Sources, t: pd.DataFrame, fred: pd.DataFrame) -> D.History:
    """History built from the sources the build already loaded (only the latest month of
    residual momentum is needed today)."""
    from convergealpha.config import GSPC
    from convergealpha.features.price_features import wilder_atr
    from convergealpha.features.regime import regime_series

    stocks = t[["sector", "industry_group", "cik"]]
    panel = src.panel
    tail = panel.close.index[-300:]
    sub_panel = type(panel)(
        open=panel.open.loc[tail], high=panel.high.loc[tail], low=panel.low.loc[tail], close=panel.close.loc[tail],
        volume=panel.volume.loc[tail], dividend=panel.dividend.loc[tail], tr=panel.tr.loc[tail], split_events=panel.split_events,
    )  # fmt: skip
    atr = wilder_atr(
        sub_panel.high.astype("float64"),
        sub_panel.low.astype("float64"),
        sub_panel.close.astype("float64"),
    )
    resid = D.residual_momentum_panel(
        type(panel)(
            panel.open,
            panel.high,
            panel.low,
            panel.close,
            panel.volume,
            panel.dividend,
            panel.tr.iloc[-900:],
            panel.split_events,
        ),
        stocks["sector"].fillna("Unknown"),
    )
    spx = panel.close[GSPC].astype("float64").dropna()
    vix = (
        fred["VIXCLS"]
        if "VIXCLS" in fred
        else panel.close.get("^VIX", pd.Series(dtype=float)).astype("float64")
    )
    reg = regime_series(spx, vix, fred.get("BAMLH0A0HYM2"))
    from convergealpha.sources import fundamentals as F

    facts_sue = pd.DataFrame(columns=["cik", "end", "known", "sue"])
    if src.extras.get("eps_sue") is not None:
        facts_sue = src.extras["eps_sue"]  # already computed by the build
    else:
        try:
            facts = (
                F.load_facts(src.extras["data_dir"]) if "data_dir" in src.extras else pd.DataFrame()
            )
            if not facts.empty:
                facts_sue = D.eps_surprise_series(facts)
        except Exception as e:
            log.warning("eps surprise series unavailable: %s", e)
    return D.History(
        sub_panel,
        stocks,
        src.ttm,
        src.instants,
        src.trades,
        src.extras.get("short_all", pd.DataFrame()),
        facts_sue,
        reg,
        atr,
        resid,
    )


def predict(ctx: RunContext, t: pd.DataFrame, src: Sources) -> tuple[pd.DataFrame, dict[str, Any]]:
    from convergealpha.sources import macro as M

    d = bundle_dir(ctx)
    if not (d / "fitted.pkl").is_file():
        raise FileNotFoundError("no model bundle")
    fitted: T.Fitted = T.load(d / "fitted.pkl")
    cal: T.Calibration = T.load(d / "calibration.pkl")
    analogs = T.load(d / "analogs.pkl") if (d / "analogs.pkl").is_file() else None
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    patterns = (
        json.loads((d / "patterns.json").read_text(encoding="utf-8"))
        if (d / "patterns.json").is_file()
        else {}
    )

    fred = M.load_fred(ctx.paths.data)
    h = _history_today(src, t, fred)
    f = D.features_at(h, src.as_of)
    f = f.reindex(t.index)
    X = f[fitted.cfg.features].astype("float64")
    raw = T.predict(fitted, X)
    out = pd.DataFrame(index=t.index)
    elig = t["eligible"].astype(bool)
    r_rank = raw["l1_ridge"].where(elig).rank(pct=True)
    g_rank = raw["l1_lgbm"].where(elig).rank(pct=True)
    out["l1"] = (r_rank + g_rank) / 2
    regimes = f["regime"].astype(str).fillna("Normal").to_numpy()
    p = T.apply_correct(cal, raw["raw_correct"].to_numpy(), regimes)
    out["p_hat"] = p
    lower, win, loss, nb = [], [], [], []
    for v in p:
        b = T.bucket_for(cal, float(v))
        lower.append(b["wilson_lo"] if b else np.nan)
        win.append(b["avg_win"] if b else np.nan)
        loss.append(b["avg_loss"] if b else np.nan)
        nb.append(b["n"] if b else np.nan)
    out["p_lower"], out["avg_win"], out["avg_loss"], out["bucket_n"] = lower, win, loss, nb

    for name in HORIZON_NAMES.values():
        if name not in cal.up:
            continue
        out[f"p_up_{name}"] = cal.up[name].predict(raw[f"raw_up_{name}"].to_numpy())
        out[f"p_beat_{name}"] = cal.beat[name].predict(raw[f"raw_beat_{name}"].to_numpy())
        q = cal.conformal.get(name, 0.0)
        out[f"median_{name}"] = raw[f"q50_{name}"]
        out[f"p10_{name}"] = raw[f"q10_{name}"] - q
        out[f"p90_{name}"] = raw[f"q90_{name}"] + q
        out[f"p25_{name}"] = np.minimum(raw[f"q25_{name}"], raw[f"q50_{name}"])
        # Quantile crossing guard.
        out[f"p10_{name}"] = np.minimum(out[f"p10_{name}"], out[f"median_{name}"])
        out[f"p90_{name}"] = np.maximum(out[f"p90_{name}"], out[f"median_{name}"])

    # The challenger forecasts in the shadow (stored for the live comparison, never shown as advice).
    if (d / "challenger_fitted.pkl").is_file() and (d / "challenger_calibration.pkl").is_file():
        try:
            from convergealpha.models import challenger as CH

            fitted_ch: T.Fitted = T.load(d / "challenger_fitted.pkl")
            cal_ch: T.Calibration = T.load(d / "challenger_calibration.pkl")
            raw_ch = T.predict(fitted_ch, f[fitted_ch.cfg.features].astype("float64"))
            for name in CH.HORIZONS:
                if name in cal_ch.up:
                    out[f"p_up_ch_{name}"] = cal_ch.up[name].predict(raw_ch[f"raw_up_{name}"].to_numpy())  # fmt: skip
        except Exception as e:
            log.warning("challenger shadow forecasts skipped: %s", e)

    # Sector / stock corrections adopted by the one-time research run (corrections-2016-2023-v1).
    corrections = (
        json.loads((d / "corrections.json").read_text(encoding="utf-8"))
        if (d / "corrections.json").is_file()
        else {}
    )
    if corrections:
        from convergealpha.research import corrections as RCX

        sectors = (
            t["sector"].reindex(out.index)
            if "sector" in t
            else pd.Series(None, index=out.index, dtype=object)
        )
        tickers = pd.Series(out.index.astype(str), index=out.index)
        for name, c in corrections.items():
            if f"p_up_{name}" in out and c.get("sector"):
                out[f"p_up_{name}"] = RCX.apply(
                    out[f"p_up_{name}"].to_numpy(), sectors, tickers, c["sector"], c.get("stock")
                )

    # Learning from its own results: the chances corrected by a fixed rule from live outcomes.
    live_cal: dict[str, Any] = {}
    tr = getattr(ctx, "extras_tr", None)
    if tr is not None:
        try:
            from convergealpha.ledger import report_card as RC
            from convergealpha.models import live_calibration as LC

            live_cal = LC.fit(RC.outcomes(ctx.paths.data, tr, pd.Timestamp(src.as_of), raw=True))
            for name, c in live_cal.items():
                if f"p_up_{name}" in out:
                    out[f"p_up_raw_{name}"] = out[f"p_up_{name}"]
                    out[f"p_up_{name}"] = LC.apply(out[f"p_up_{name}"].to_numpy(), c["shift"])
        except Exception as e:  # never stops the forecasts; the correction is simply not applied
            log.warning("live calibration skipped: %s", e)

    # Meta-model on today's top 5% by L1.
    if cal.meta is not None:
        mf = f.copy()
        mf["l1_rank_pct"] = out["l1"]
        top = mf[(out["l1"] >= 0.95) & elig]
        if len(top):
            Xm, _, _ = T.meta_matrix(top, cal.meta_medians, cal.meta_sectors)
            out.loc[top.index, "meta"] = cal.meta.predict_proba(Xm)[:, 1]

    analog_out: dict[str, Any] = {}
    if analogs is not None:
        analog_out = analog_check(analogs, f[elig], out)
        for tk, a in analog_out.items():
            out.loc[tk, "analog_pass"] = bool(a["n"] >= 100 and a["lo"] >= 0.65)
            out.loc[tk, "analog_text"] = a["text"]
    counts = getattr(cal, "counts", {})
    sample_hz: dict[str, dict[str, int]] = {}
    for tk in t.index:
        n = out.at[tk, "bucket_n"]
        sample_hz[str(tk)] = {k: int(counts[k]) for k in HORIZON_NAMES.values() if k in counts} | (
            {"p_hat": int(n)} if pd.notna(n) else {}
        )
    default_patterns = {
        "passed": [],
        "likely_luck": [],
        "tested": int(patterns.get("tested", 0)),
        "method": patterns.get("method", ""),
    }
    validation = (
        json.loads((d / "validation.json").read_text(encoding="utf-8"))
        if (d / "validation.json").is_file()
        else None
    )
    if validation and validation.get("periods"):
        from convergealpha.validate import lab

        # The verdict is a pure function of the report: recompute it so its rules and wording
        # always match the current code, even for a bundle trained by an older version.
        validation["verdict"] = lab.verdict(validation)
    reliability = (
        json.loads((d / "reliability.json").read_text(encoding="utf-8"))
        if (d / "reliability.json").is_file()
        else None
    )
    drift = None
    if (d / "reference.parquet").is_file():
        from convergealpha.ledger import monitor as MON

        ref = pd.read_parquet(d / "reference.parquet")
        drift = MON.drift(ref, f[elig], [c for c in fitted.cfg.features if c in ref])
    model_meta = {
        "validation": validation,
        "validated": ((validation or {}).get("verdict") or {}).get("validated", []),
        "drift": {"psi": drift, "alerts": sorted(k for k, v in (drift or {}).items() if v > 0.25)}
        if drift is not None
        else None,
        "files": {"validation.json": validation} if validation else {},
        "reliability": reliability,
        "analogs": analog_out,
        "sample_sizes": sample_hz,
        "patterns": {
            str(tk): patterns.get("by_ticker", {}).get(str(tk), default_patterns) for tk in t.index
        }
        if patterns
        else {},
        # Every tested (stock or industry, event type, window): the opportunity badge's history.
        "pattern_history": patterns.get("history") or {},
        "health": {
            "model_version": meta["version"],
            "model_trained_at": meta["trained_at"],
            "model_metrics": meta.get("metrics"),
            "live_calibration": live_cal or None,
            "challenger": meta.get("challenger"),
            "corrections": {h: sorted(c) for h, c in corrections.items()} or None,
        },
        "version": meta["version"],
    }
    return out, model_meta


def analog_check(
    ix: dict[str, Any], f: pd.DataFrame, out: pd.DataFrame, k: int = 200
) -> dict[str, dict[str, Any]]:
    """The 200 most similar past setups (independent: at most one per stock per 6 months)."""
    from sklearn.neighbors import NearestNeighbors

    feats = ix["features"]
    mu = pd.Series(ix["mu"])
    sd = pd.Series(ix["sd"])
    q = ((f[feats].astype("float64") - mu[feats]) / sd[feats]).fillna(0.0)
    if q.empty:
        return {}
    nn = NearestNeighbors(n_neighbors=min(k * 3, len(ix["Z"]))).fit(ix["Z"])
    _, idx = nn.kneighbors(q.to_numpy(dtype="float32"))
    res: dict[str, dict[str, Any]] = {}
    for row, tk in zip(idx, q.index, strict=True):
        seen: dict[str, np.datetime64] = {}
        picked = []
        for j in row:
            t, dt = ix["ticker"][j], ix["date"][j]
            if t == tk:
                continue  # never compare a stock with its own past
            last = seen.get(t)
            if last is not None and abs((dt - last).astype("timedelta64[D]").astype(int)) < 182:
                continue
            seen[t] = dt
            picked.append(j)
            if len(picked) >= k:
                break
        n = len(picked)
        if n == 0:
            continue
        ups = int(ix["up"][picked].sum())
        lo, hi = stats.wilson_interval(ups, n)
        rate = ups / n
        model_p = out.at[tk, "p_up_6m"] if "p_up_6m" in out else np.nan
        gap = (
            None
            if model_p is None or (isinstance(model_p, float) and math.isnan(model_p))
            else float(model_p - rate)
        )
        res[str(tk)] = {
            "n": n,
            "up": ups,
            "rate": rate,
            "lo": lo,
            "hi": hi,
            "median_ret": float(np.median(ix["ret"][picked])),
            "model_gap": gap,
            "text": f"Historically {rate:.0%} of {n} similar setups were higher after 6 months ({lo:.0%}–{hi:.0%}).",
        }
    return res
