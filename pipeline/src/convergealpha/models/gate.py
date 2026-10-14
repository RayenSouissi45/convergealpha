"""Model gate: a newly trained weekly bundle replaces the one in use only if it is not worse.

The weekly job retrains on all data so far. Before its bundle is published, it is compared with
the bundle the daily builds use now, on the same out-of-sample years (2016-2023, walk-forward):

- the Brier score of the "will the trade be right" chance may not get worse by more than 2%,
- its AUC may not drop by more than 0.01,
- each horizon's 80% range must still hold between 70% and 90% of outcomes,
- the training data may not shrink by more than 10% (a sign of lost price history).

If any check fails, the new bundle is not published: the weekly run is marked failed and the daily
builds keep downloading the last bundle that passed (an automatic rollback). The result is stored
in the data repo (state/model_gate.json), shown on Health and logged as an incident.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

BRIER_REL = 0.02
AUC_ABS = 0.01
ROWS_REL = 0.10
COVERAGE = (0.70, 0.90)


def _num(d: dict[str, Any], *keys: str) -> float | None:
    v: Any = d
    for k in keys:
        if not isinstance(v, dict):
            return None
        v = v.get(k)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def check(new: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Compare two bundles' meta.json. No previous bundle: only the absolute checks apply."""
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    nb, pb = _num(new, "metrics", "brier_correct"), _num(previous or {}, "metrics", "brier_correct")
    if nb is None:
        add("brier", False, "the new bundle has no Brier score")
    elif pb is not None:
        add("brier", nb <= pb * (1 + BRIER_REL), f"{nb:.4f} vs {pb:.4f} now (at most {BRIER_REL:.0%} worse)")  # fmt: skip
    na, pa = _num(new, "metrics", "auc_correct"), _num(previous or {}, "metrics", "auc_correct")
    if na is not None and pa is not None:
        add("auc", na >= pa - AUC_ABS, f"{na:.3f} vs {pa:.3f} now (at most {AUC_ABS} lower)")
    for k, v in (new.get("metrics") or {}).items():
        if k.startswith("coverage80_") and isinstance(v, (int, float)):
            lo, hi = COVERAGE
            add(k, lo <= v <= hi, f"{v:.1%} of outcomes inside the 80% range (allowed {lo:.0%}–{hi:.0%})")  # fmt: skip
    nr, pr = _num(new, "dataset", "rows"), _num(previous or {}, "dataset", "rows")
    if nr is not None and pr is not None:
        add("rows", nr >= pr * (1 - ROWS_REL), f"{nr:,.0f} training rows vs {pr:,.0f} now")
    passed = all(c["ok"] for c in checks)
    prev_version = (previous or {}).get("version")
    return {
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "new": new.get("version"),
        "previous": prev_version,
        "passed": passed,
        "in_use": new.get("version") if passed else prev_version,
        "checks": checks,
    }


__all__ = ["AUC_ABS", "BRIER_REL", "COVERAGE", "ROWS_REL", "check"]
