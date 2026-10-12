"""Leakage guards (spec section 13): fail the build if a model input could see the future."""

import json
from pathlib import Path

from convergealpha.models import dataset as D
from convergealpha.models import train as T
from convergealpha.models.weekly import ANALOG_FEATURES


def test_no_feature_shares_a_name_with_an_outcome_column() -> None:
    for f in [*D.FEATURES, *ANALOG_FEATURES, *T.META_FEATURES, *T.TrainConfig().features]:
        assert not f.startswith(D.LABEL_PREFIXES), f"feature {f} looks like an outcome column"


def test_holdout_is_after_all_training_and_validation_years() -> None:
    assert max(T.DEV_YEARS) < min(T.VAL_YEARS)
    assert max(T.VAL_YEARS) < T.HOLDOUT[0].year


def test_holdout_evaluated_once_per_configuration() -> None:
    """The data repo logs every holdout evaluation. Each configuration may touch it once; more
    than one entry in total is reported on the site as contaminated (the verdict fails)."""
    log = Path(__file__).resolve().parents[2] / "data" / "validation" / "holdout_log.json"
    if not log.is_file():
        return  # CI has no data repo checkout; the weekly job applies the same rule itself
    entries = json.loads(log.read_text(encoding="utf-8"))
    digests = [e["digest"] for e in entries]
    assert len(digests) == len(set(digests)), "a configuration evaluated the holdout twice"
    assert [e["touch"] for e in entries] == list(range(1, len(entries) + 1))
