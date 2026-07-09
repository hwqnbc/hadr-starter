"""Event state store (S1 / ADR-0004).

Canonical event state is a single schema-versioned JSON file, committed by the
workflow and never hand-edited. This module is the only reader/writer; the
reconciler works on the in-memory dict and hands it back here to persist.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_PATH = "data/state.json"

_ID_RE = re.compile(r"^evt-(\d{4})-(\d+)$")


def empty_state() -> dict[str, Any]:
    """A fresh schema-v1 state with no events yet."""
    return {
        "version": SCHEMA_VERSION,
        "events": {},
        "feed_status": {},
        # ``baseline`` snapshots each event's alert level/magnitude/status as of the
        # last edition, so the next edition's changelog reflects changes accumulated
        # across the intervening hourly polls (S3 / V8), not just the last run.
        "edition_marker": {
            "last_edition_at": None,
            "acknowledged_changes": [],
            "baseline": {},
        },
        # Events crossing into Red this run, computed by the gate and consumed by
        # V8's flash branch. Stored, not acted on, in this slice (ADR-0003).
        "flash_pending": [],
    }


def load(path: str | Path = DEFAULT_PATH) -> dict[str, Any]:
    """Load state, or return a fresh one if the file does not exist yet."""
    p = Path(path)
    if not p.exists():
        return empty_state()
    state = json.loads(p.read_text(encoding="utf-8"))
    if state.get("version") != SCHEMA_VERSION:
        raise ValueError(
            f"state.json schema version {state.get('version')} != expected {SCHEMA_VERSION}"
        )
    return state


def save(state: dict[str, Any], path: str | Path = DEFAULT_PATH) -> None:
    """Persist state atomically (write to a temp file, then replace)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, p)


def next_canonical_id(state: dict[str, Any], origin_year: int) -> str:
    """Mint the next ``evt-YYYY-NNNN`` id deterministically from existing ids.

    The sequence is global (max over all events, any year) so ids never collide;
    the year segment records the event's origin year. Deterministic given state.
    """
    max_seq = 0
    for key in state["events"]:
        m = _ID_RE.match(key)
        if m:
            max_seq = max(max_seq, int(m.group(2)))
    return f"evt-{origin_year}-{max_seq + 1:04d}"
