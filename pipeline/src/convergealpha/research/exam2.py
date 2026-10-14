"""The second clean exam, registered before any of its data exists.

The first exam (the 2024 - mid-2026 holdout) was run once and is never run again. A new period
starts after it: forecasts published from 1 Jul 2026 onward were made by models that never saw
their outcomes. This module fixes, today, how that period will be judged and when, and seals the
plan in the experiment log; the run itself happens once, on or after the date below.

PROTOCOL exam2-2026h2-v1 (fixed before the first forecast of the period matured):
- Forecasts: every eligible stock's published chances of rising (the daily scores snapshots, first
  file of each day) from 12 Oct 2026, the first day they were stored, to 31 Dec 2026.
- Outcomes: total return over 1 week, 1 month, 3 months and 6 months, so all are known by
  30 Jun 2027. Run on or after 1 Jul 2027, once.
- A horizon passes if, on the period: (a) the Brier score beats the usual up rate of 2016-2023
  (skill > 0) and (b) stocks given 60% or more rose at least 55% of the time, with the lower end of
  a 95% Wilson range, computed on one forecast day per horizon length (non-overlapping), above
  50%. Both must hold; anything else is a fail, shown as such.
- The BUY label is judged by the validation lab's own rules (net excess over the best baseline,
  t >= 2, halved backtest haircut not applicable: live results are shown as they are).
- The result goes to the experiment log next to this registration, pass or fail.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROTOCOL_ID = "exam2-2026h2-v1"
SPEC: dict[str, Any] = {
    "id": PROTOCOL_ID,
    "forecasts_from": "2026-10-12",
    "forecasts_to": "2026-12-31",
    "horizons": ["1w", "1m", "3m", "6m"],
    "run_on_or_after": "2027-07-01",
    "pass": {
        "skill_above": 0.0,
        "confident": 0.60,
        "confident_rose_at_least": 0.55,
        "wilson_low_above": 0.50,
        "non_overlapping": True,
    },
    "buy_label": "validation lab verdict rules (t >= 2 over the best baseline), live results unhalved",
}


def protocol_digest() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:12]


def register(data_dir: Path) -> dict[str, Any] | None:
    """Seal the plan in the experiment log (once). Returns the entry, or None if already there."""
    from convergealpha.ledger import experiments as X

    digest = protocol_digest()
    if any(e.get("protocol_id") == PROTOCOL_ID and e.get("protocol_digest") == digest for e in X.entries(data_dir)):  # fmt: skip
        return None
    return X.record(
        data_dir,
        {
            "experiment": "second clean exam (registered in advance)",
            "question": "Do the published chances of rising stay right on a period no model was trained on?",
            "protocol_id": PROTOCOL_ID,
            "protocol_digest": digest,
            "period": f"forecasts {SPEC['forecasts_from']} to {SPEC['forecasts_to']}, run on or after {SPEC['run_on_or_after']}",
            "status": "registered",
            "decision": SPEC["pass"],
        },
    )


__all__ = ["PROTOCOL_ID", "SPEC", "protocol_digest", "register"]
