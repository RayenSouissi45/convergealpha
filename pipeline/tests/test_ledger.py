import json
from pathlib import Path

import numpy as np
import pandas as pd

from convergealpha.ledger import ledger as L


def test_hash_chain_and_tamper_detection(tmp_path: Path) -> None:
    p = tmp_path / "ledger.jsonl"
    L.append(
        p,
        [
            {"ticker": "AAA", "label": "BUY", "p_hat": 0.61},
            {"ticker": "BBB", "label": "BUY", "p_hat": 0.58},
        ],
    )
    L.append(p, [{"ticker": "CCC", "label": "SELL / RISK WARNING", "p_hat": None}])
    entries = L.read(p)
    assert [e["seq"] for e in entries] == [1, 2, 3]
    assert entries[0]["prev_hash"] == L.GENESIS
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    assert L.verify(p) == (True, "ok")

    # Editing a past prediction breaks the chain: the tamper test must fail.
    lines = p.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["p_hat"] = 0.99
    lines[0] = json.dumps(first, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, why = L.verify(p)
    assert not ok and "line 1" in why

    # Recomputing the edited line's own hash still breaks the next line's link.
    lines = p.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[0])
    e["hash"] = L.hashlib.sha256((L.GENESIS + L._canonical(e)).encode()).hexdigest()
    lines[0] = json.dumps(e, sort_keys=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, why = L.verify(p)
    assert not ok and "line 2" in why


def test_only_new_signals_are_recorded() -> None:
    today = pd.DataFrame(
        {
            "label": ["BUY", "BUY", "NO TRADE", "SELL / RISK WARNING"],
            "price": [10.0, 20.0, 30.0, 40.0],
        },
        index=["NEW", "OLD", "NONE", "RISK"],
    )
    sig = L.new_signals(today, {"OLD": "BUY", "RISK": "NO TRADE"})
    assert sorted(sig.index) == ["NEW", "RISK"]


def test_outcomes_after_the_horizon_only(tmp_path: Path) -> None:
    idx = pd.bdate_range("2026-01-02", periods=200)
    tr = pd.DataFrame({"X": np.linspace(100, 120, 200)}, index=idx)
    spy = pd.Series(np.linspace(100, 110, 200), index=idx)
    p = tmp_path / "l.jsonl"
    entries = L.append(
        p,
        [
            {
                "ticker": "X",
                "label": "BUY",
                "date": idx[10].strftime("%Y-%m-%d"),
                "forecast": {"1w": {"p_up": 0.6}},
            }
        ],
    )
    outs = L.due_outcomes(entries, [], tr, spy, idx[40])
    assert sorted(o["horizon"] for o in outs) == ["1m", "1w"]  # 3m and 6m not elapsed yet
    one_week = next(o for o in outs if o["horizon"] == "1w")
    assert one_week["up"] is True and one_week["predicted_p_up"] == 0.6
    # Already recorded outcomes are not recorded again.
    assert L.due_outcomes(entries, outs, tr, spy, idx[40]) == []
