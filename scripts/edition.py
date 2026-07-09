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

# A magnitude change below this is instrument noise, not a revision worth telling
# (mirrors reconcile.MAG_NOISE; kept local to avoid coupling the modules).
MAG_NOISE = 0.1

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


def _baseline_rec(event: dict[str, Any]) -> dict[str, Any]:
    """Snapshot the fields the changelog compares against: level, magnitude, status."""
    return {
        "level": event_level(event),
        "magnitude": (event.get("magnitude") or {}).get("value"),
        "status": event.get("status", "active"),
    }


def _baseline_records(marker: dict[str, Any], prior: dict[str, Any] | None) -> dict[str, Any]:
    """The state to classify *against*: the snapshot stored at the last edition.

    From V8 the daily edition compares the current state to the state *as of the
    last edition* — not to the last hourly run — so changes accumulated across the
    intervening polls all appear (the hourly polls never advance the marker or the
    baseline). When no baseline is stored yet (first edition, or unit tests that
    pass ``prior`` directly), fall back to deriving it from ``prior``.
    """
    stored = marker.get("baseline")
    if stored is not None:
        return stored
    prior_events = (prior or {}).get("events", {})
    return {eid: _baseline_rec(ev) for eid, ev in prior_events.items()}


def _mag_revised(base_mag: float | None, new_mag: float | None) -> bool:
    if base_mag is None or new_mag is None:
        return False
    return abs(new_mag - base_mag) >= MAG_NOISE


def _classify(
    base_rec: dict[str, Any] | None,
    event: dict[str, Any],
    revised: bool,
) -> str | None:
    """How did a tracked event change since the baseline? A first sight is a card."""
    was_retracted = bool(base_rec) and base_rec.get("status") == "retracted"
    if event.get("status") == "retracted" and not was_retracted:
        return RETRACTION
    if base_rec is None:
        return None  # first sight since the last edition -> a card, not a changelog line
    new_level = event_level(event)
    old_level = base_rec.get("level", 0)
    if new_level > old_level:
        return ESCALATION
    if new_level < old_level:
        return DOWNGRADE
    if revised:
        return REVISION
    return None


def _entry(eid: str, event: dict[str, Any], base_rec: dict[str, Any] | None, kind: str) -> dict:
    """A structured, render-ready changelog line (the renderer asserts on this)."""
    entry: dict[str, Any] = {
        "id": eid,
        "kind": kind,
        "name": event.get("name", ""),
        "hazard": event.get("hazard", ""),
    }
    if kind in (ESCALATION, DOWNGRADE):
        entry["from"] = LEVEL_NAME[(base_rec or {}).get("level", 0)]
        entry["to"] = LEVEL_NAME[event_level(event)]
    elif kind == REVISION:
        entry["magnitude"] = (event.get("magnitude") or {}).get("value")
    return entry


def build_flash_edition(
    state: dict[str, Any],
    flash_ids: list[str],
    *,
    now,
    title: str = "HADR Monitor",
) -> dict[str, Any]:
    """Off-cycle flash edition content (N10): a Red banner, no changelog, no model.

    A flash re-render bypasses the edition builder and the model step (it does not
    touch N12/N14): it republishes the dashboard early with the Red event(s)
    flagged (U3). The next 08:30 edition folds the crossing into its changelog.
    """
    banner_events = [
        {
            "id": eid,
            "name": state["events"].get(eid, {}).get("name", ""),
            "hazard": state["events"].get(eid, {}).get("hazard", ""),
        }
        for eid in flash_ids
    ]
    return {
        "title": title,
        "generated_at": iso_utc(now),
        "type": "flash",
        "flash": {"events": banner_events},
        "changelog": {name: [] for name in _SECTIONS},
    }


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
    reportable_ids = reportable_ids or []
    last_edition_at = marker.get("last_edition_at")
    revised_ids = {c["id"] for c in change_set if c["kind"] == "revision"}
    # Classify against the state as of the last edition, not the last poll (V8).
    baseline = _baseline_records(marker, prior)

    sections: dict[str, list[dict]] = {name: [] for name in _SECTIONS}
    acknowledged: list[str] = []
    for eid, event in state["events"].items():
        if not _post_marker(event, last_edition_at):
            continue
        base_rec = baseline.get(eid)
        new_mag = (event.get("magnitude") or {}).get("value")
        revised = eid in revised_ids or (
            base_rec is not None and _mag_revised(base_rec.get("magnitude"), new_mag)
        )
        kind = _classify(base_rec, event, revised)
        if kind is None:
            continue
        sections[_SECTION_OF[kind]].append(_entry(eid, event, base_rec, kind))
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

    # Advance the marker monotonically — a change is told to the reader once — and
    # snapshot the new baseline so the *next* edition compares against this one.
    stamp = iso_utc(now)
    if last_edition_at is None or stamp >= last_edition_at:
        marker["last_edition_at"] = stamp
        marker["baseline"] = {eid: _baseline_rec(ev) for eid, ev in state["events"].items()}
    marker["acknowledged_changes"] = acknowledged
    return edition
