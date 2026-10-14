"""The experiment log: every research question the app tested, when, under which fixed protocol,
with which code, and what came out, failures included. Append-only and hash-chained like the
signal ledger (ledger/experiments.jsonl in the private data repo).

Why: when many ideas are tried, some look good by luck. Counting every try (and never deleting the
failed ones) is what keeps "it worked in the past" honest, and a protocol can only be run once.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from convergealpha.ledger import ledger as LG

PATH = Path("ledger") / "experiments.jsonl"


def path(data_dir: Path) -> Path:
    return data_dir / PATH


def code_commit() -> str | None:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def entries(data_dir: Path) -> list[dict[str, Any]]:
    p = path(data_dir)
    return LG.read(p) if p.is_file() else []


def already_run(data_dir: Path, protocol_id: str, digest: str) -> bool:
    return any(
        e.get("protocol_id") == protocol_id
        and e.get("protocol_digest") == digest
        and e.get("status") == "done"
        for e in entries(data_dir)
    )


def record(data_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Append one experiment (status 'done' or 'failed')."""
    e = {
        "kind": "experiment",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_commit": code_commit(),
        **entry,
    }
    return LG.append(path(data_dir), [e])[-1]


def verify(data_dir: Path) -> tuple[bool, str]:
    p = path(data_dir)
    return LG.verify(p) if p.is_file() else (True, "empty")


def export(data_dir: Path) -> dict[str, Any]:
    """experiments.json for the site: every try, newest first, without internal details."""
    ok, detail = verify(data_dir)
    keep = ("recorded_at", "experiment", "question", "protocol_id", "protocol_digest", "period", "status", "summary", "decision", "code_commit")  # fmt: skip
    rows = [{k: e.get(k) for k in keep} for e in reversed(entries(data_dir))]
    return {"verified": ok, "detail": detail, "count": len(rows), "experiments": rows}
