"""Model gate: a new weekly bundle is used only if it is not worse than the one in use."""

from __future__ import annotations

from convergealpha.ledger import incidents as INC
from convergealpha.models import gate as G


def meta(version: str, brier: float = 0.240, auc: float = 0.560, cov: float = 0.80, rows: int = 264_701) -> dict[str, object]:  # fmt: skip
    return {
        "version": version,
        "metrics": {"brier_correct": brier, "auc_correct": auc, "coverage80_1m": cov, "coverage80_6m": cov},
        "dataset": {"rows": rows},
    }  # fmt: skip


def test_a_similar_or_better_model_passes() -> None:
    res = G.check(meta("new", brier=0.2440, auc=0.552), meta("old"))  # 1.7% worse, 0.008 lower
    assert res["passed"] and res["in_use"] == "new"
    assert {c["check"] for c in res["checks"]} == {
        "brier",
        "auc",
        "coverage80_1m",
        "coverage80_6m",
        "rows",
    }


def test_a_worse_model_is_not_used_and_the_previous_one_stays() -> None:
    for bad in (meta("new", brier=0.2460), meta("new", auc=0.548), meta("new", cov=0.62), meta("new", rows=200_000)):  # fmt: skip
        res = G.check(bad, meta("old"))
        assert not res["passed"] and res["in_use"] == "old", res
    # The daily build logs it as an incident, naming what failed.
    found = INC.detect({"model_gate": G.check(meta("new", brier=0.30), meta("old"))})
    assert (
        "model_rollback" in found and "new not used, old kept" in found["model_rollback"]["detail"]
    )


def test_first_bundle_only_needs_the_absolute_checks() -> None:
    assert G.check(meta("first"), None)["passed"]
    assert not G.check({"version": "x", "metrics": {}}, None)["passed"]  # no Brier at all
