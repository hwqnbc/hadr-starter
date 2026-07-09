"""Edition builder (B5 edition logic / N12, N13) + marker S3.

Pure, deterministic, no model call (ADR-0003): every run produces a dated
edition and an honest changelog of what changed since the last edition. The
model (V6) only ever phrases already-decided reportable material; the decision
to publish, the quiet/regular split, and the changelog are all computed here.

``build_edition`` returns the edition content the renderer embeds:

- a **changelog** of changes since the marker S3 — escalations first (US7),
  then downgrades/revisions as one-liners, then retractions (US6, US8);
- a **quiet vs regular** decision — the deterministic quiet edition (N13) is
  chosen iff there is nothing reportable *and* nothing changed;
- and it **advances the marker** (S3) monotonically so a change is told once.

"Since the marker" is watermarked on ``last_changed``: reconcile bumps an
event's ``last_changed`` whenever its alert level, magnitude or status changes,
so any event changed after ``marker["last_edition_at"]`` is post-marker. The
kind of each change is classified from the before/after (prior vs reconciled)
state, not from feed wording.
"""

from __future__ import annotations

from typing import Any

from scripts.feeds import iso_utc
from scripts.gate import LEVEL_NAME, event_level

# Changelog change kinds (distinct from reconcile's NEW/REVISION/… change_set:
# these describe how a *previously tracked* event changed, for the reader).
ESCALATION = "escalation"
DOWNGRADE = "downgrade"
REVISION = "revision"
RETRACTION = "retraction"

QUIET_LINE = "No significant events — all feeds healthy"

# Section order is the render order: escalations lead (US7), retractions close.
_SECTIONS = ("escalations", "downgrades", "revisions", "retractions")
_SECTION_OF = {
    ESCALATION: "escalations",
    DOWNGRADE: "downgrades",
    REVISION: "revisions",
    RETRACTION: "retractions",
}


def _post_marker(event: dict[str, Any], last_edition_at: str | None) -> bool:
    """True if the event changed after the last edition (fixed-width UTC ISO sorts)."""
    if last_edition_at is None:
        return True
    return event.get("last_changed", "") > last_edition_at


def _classify(
    prior_event: dict[str, Any] | None,
    event: dict[str, Any],
    revised: bool,
) -> str | None:
    """How did a tracked event change? A brand-new event is a board card, not news."""
    was_retracted = bool(prior_event) and prior_event.get("status") == "retracted"
    if event.get("status") == "retracted" and not was_retracted:
        return RETRACTION
    if prior_event is None:
        return None  # first sight -> a card on the board, not a changelog line
    new_level = event_level(event)
    old_level = event_level(prior_event)
    if new_level > old_level:
        return ESCALATION
    if new_level < old_level:
        return DOWNGRADE
    if revised:
        return REVISION
    return None


def _entry(eid: str, event: dict[str, Any], prior_event: dict[str, Any] | None, kind: str) -> dict:
    """A structured, render-ready changelog line (the renderer asserts on this)."""
    entry: dict[str, Any] = {
        "id": eid,
        "kind": kind,
        "name": event.get("name", ""),
        "hazard": event.get("hazard", ""),
    }
    if kind in (ESCALATION, DOWNGRADE):
        entry["from"] = LEVEL_NAME[event_level(prior_event)]
        entry["to"] = LEVEL_NAME[event_level(event)]
    elif kind == REVISION:
        mag = (event.get("magnitude") or {}).get("value")
        entry["magnitude"] = mag
    return entry


def build_edition(
    state: dict[str, Any],
    marker: dict[str, Any],
    change_set: list[dict[str, str]] | None = None,
    prior: dict[str, Any] | None = None,
    *,
    now,
    reportable_ids: list[str] | None = None,
    title: str = "HADR Monitor",
) -> dict[str, Any]:
    """Build the edition content, advance the marker in place, and return it.

    Pure aside from advancing ``marker`` (S3): fills the changelog from
    post-marker changes, picks quiet vs regular, and moves ``last_edition_at``
    forward monotonically. No model is consulted on any path.
    """
    change_set = change_set or []
    prior_events = (prior or {}).get("events", {})
    reportable_ids = reportable_ids or []
    last_edition_at = marker.get("last_edition_at")
    revised_ids = {c["id"] for c in change_set if c["kind"] == "revision"}

    sections: dict[str, list[dict]] = {name: [] for name in _SECTIONS}
    acknowledged: list[str] = []
    for eid, event in state["events"].items():
        if not _post_marker(event, last_edition_at):
            continue
        kind = _classify(prior_events.get(eid), event, eid in revised_ids)
        if kind is None:
            continue
        sections[_SECTION_OF[kind]].append(_entry(eid, event, prior_events.get(eid), kind))
        acknowledged.append(eid)

    for name in _SECTIONS:
        sections[name].sort(key=lambda e: e["id"])
    has_changes = any(sections[name] for name in _SECTIONS)

    quiet = not reportable_ids and not has_changes
    edition: dict[str, Any] = {
        "title": title,
        "generated_at": iso_utc(now),
        "type": "quiet" if quiet else "regular",
        "changelog": sections,
    }
    if quiet:
        edition["quiet_line"] = QUIET_LINE

    # Advance the marker monotonically — a change is told to the reader once.
    stamp = iso_utc(now)
    if last_edition_at is None or stamp >= last_edition_at:
        marker["last_edition_at"] = stamp
    marker["acknowledged_changes"] = acknowledged
    return edition
