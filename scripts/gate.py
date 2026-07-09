"""Impact-based reporting gate (B3 / N9).

Pure decision step between reconcile and render (ADR-0002): given this run's
``change_set`` and the reconciled ``state`` (plus the ``prior`` state for
before/after alert levels), decide which tracked events clear the reporting bar
and which cross into Red. Sub-threshold events stay tracked in state
(``reported`` stays ``False``) but are hidden from the board — the reader only
sees what matters.

The gate never talks to a model and never fetches; it is a deterministic
threshold check (CLAUDE.md / ADR-0003). It *annotates* the reconciled state in
place — setting ``reported`` on events that clear the bar (sticky: once true,
stays true, so "previously reported" is a durable fact), clearing the
``flash_published`` guard when an event drops below Red, and recording the
pending flash set on ``state["flash_pending"]`` — and returns
``(reportables, flash_trigger)`` as sorted lists of canonical event ids.

``flash_trigger`` is *computed and stored* here; publishing a flash (acting on
it) is V8. A flash fires once per Red spell: an event newly at Red or escalating
into Red triggers unless a flash is already outstanding for that spell
(``flash_published``), and the guard clears when the event drops below Red so a
downgrade-then-re-escalation flashes again (ADR-0003).
"""

from __future__ import annotations

from typing import Any

# Unified impact scale across the two independent alert models (kept as separate
# fields, never merged — ADR-0002). GDACS has no yellow band; PAGER has no red-
# vs-orange distinction beyond its own words. Mapping both onto one ordinal lets
# the gate reason about "crosses into Red" and "escalation" uniformly.
_GDACS_LEVEL = {"green": 0, "orange": 2, "red": 3}
_PAGER_LEVEL = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

# Ordinal -> display name for changelog wording (edition.py). 1 is PAGER-only.
LEVEL_NAME = {0: "Green", 1: "Yellow", 2: "Orange", 3: "Red"}

RED = 3


def _level(value: str | None, table: dict[str, int]) -> int:
    return table.get((value or "").strip().lower(), 0)


def gdacs_level(event: dict[str, Any]) -> int:
    return _level(event.get("gdacs_alert"), _GDACS_LEVEL)


def pager_level(event: dict[str, Any]) -> int:
    return _level(event.get("pager_alert"), _PAGER_LEVEL)


def event_level(event: dict[str, Any] | None) -> int:
    """Combined impact ordinal for an event: the worse of its two alert models."""
    if not event:
        return 0
    return max(gdacs_level(event), pager_level(event))


def _reportable(event: dict[str, Any], prior_event: dict[str, Any] | None) -> bool:
    """Does an active event clear the impact bar (ADR-0002)? Any arm suffices."""
    # GDACS Orange/Red, or PAGER yellow/orange/red.
    if gdacs_level(event) >= 2 or pager_level(event) >= 1:
        return True
    # An already-tracked event that escalated (level rose since the prior state).
    if prior_event is not None and event_level(event) > event_level(prior_event):
        return True
    # A ReliefWeb disaster entry for an unreported event — human curation
    # overrides the model thresholds. ReliefWeb's fetcher is not wired yet (V3
    # deferred it), so nothing sets a reliefweb source_ref today; this arm is a
    # tested, ready code path for when it lands, behind the same interface.
    if not event.get("reported") and "reliefweb" in (event.get("source_refs") or {}):
        return True
    return False


def gate(
    change_set: list[dict[str, str]],
    state: dict[str, Any],
    prior: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Annotate ``state`` with reporting decisions; return (reportables, flash_trigger).

    ``change_set`` is accepted for interface stability (BREADBOARD N9) and future
    use; the reportable/flash decision is derived from before/after alert levels,
    which is strictly more information than the change kinds carry. Mutates
    ``state`` in place (``reported``, ``flash_published``, ``flash_pending``).
    """
    _ = change_set  # decision is derived from prior/new levels, not change kinds
    prior_events = (prior or {}).get("events", {})

    reportables: list[str] = []
    flash_trigger: list[str] = []

    for eid, event in state["events"].items():
        prior_event = prior_events.get(eid)
        active = event.get("status") == "active"

        if active and _reportable(event, prior_event):
            event["reported"] = True  # sticky: durable "we have told the reader"
            reportables.append(eid)

        level = event_level(event)
        prior_level = event_level(prior_event)

        # Crosses into Red = at Red now, below Red before (a brand-new event has
        # prior_level 0, so this covers both "newly detected at Red" and
        # "escalating into Red"). Suppressed while a flash is outstanding.
        if active and level == RED and prior_level < RED and not event.get("flash_published"):
            flash_trigger.append(eid)

        # Guard clears when the event drops below Red, so a later re-escalation
        # flashes again while sustained Red does not re-flash each poll.
        if level < RED and event.get("flash_published"):
            event["flash_published"] = False

    reportables.sort()
    flash_trigger.sort()
    # Stored, not acted on: V8's flash branch consumes this seam.
    state["flash_pending"] = flash_trigger
    return reportables, flash_trigger
