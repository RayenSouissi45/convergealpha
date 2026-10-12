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


def test_holdout_touched_at_most_once() -> None:
    """The data repo keeps a log of every holdout evaluation; more than one means the holdout
    was reused after a configuration change and its results are contaminated."""
    log = Path(__file__).resolve().parents[2] / "data" / "validation" / "holdout_log.json"
    if not log.is_file():
        return  # CI has no data repo checkout; the weekly job checks the same rule itself
    entries = json.loads(log.read_text(encoding="utf-8"))
    assert len(entries) <= 1, f"holdout evaluated {len(entries)} times"
