"""Reconciler (B2 / N7): diff feed snapshots against canonical state.

The agent is an event-state reconciler, not a feed reader (ADR-0001): every run
diffs the current snapshots against the persisted canonical events and derives a
change set from the diff. This module is pure — no I/O, no clock of its own — so
it is fully testable: ``(snapshots, state, now) -> (new_state, change_set)``.

V2 exercises a single source (USGS): identity via the alias set, revision, and
retraction. The cross-source join order lands in V3, but the signature already
takes a *list* of snapshots so that slice is an extension, not a rewrite.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any

from scripts.feeds import FeedSnapshot, SourceRecord, iso_utc
from scripts.state import next_canonical_id

# A magnitude change below this is instrument noise, not a revision worth telling.
MAG_NOISE = 0.1

# Change kinds emitted into the change set.
NEW = "new"
REVISION = "revision"
RETRACTION = "retraction"
AGED_OUT = "aged_out"


def _event_from_record(record: SourceRecord, now: datetime) -> dict[str, Any]:
    """Build a fresh canonical event from a source record."""
    stamp = iso_utc(now)
    return {
        "hazard": record.hazard,
        "name": record.name,
        "aliases": list(record.aliases),
        "location": {"lat": record.lat, "lon": record.lon, "place": record.place},
        "origin_time": iso_utc(record.origin_time),
        "magnitude": record.magnitude,
        "gdacs_alert": record.gdacs_alert,
        "pager_alert": record.pager_alert,
        "reported": False,
        "flash_published": False,
        "status": "active",
        "first_seen": stamp,
        "last_changed": stamp,
        "source_refs": {record.source: record.source_ref},
    }


def _alias_index(state: dict[str, Any]) -> dict[str, str]:
    """Map every stored alias -> its canonical event id."""
    index: dict[str, str] = {}
    for eid, event in state["events"].items():
        for alias in event["aliases"]:
            index[alias] = eid
    return index


def _match(record: SourceRecord, index: dict[str, str]) -> str | None:
    """Return the canonical id whose alias set overlaps the record, if any.

    Because a canonical event keeps *every* alias a feed ever used, this survives
    a USGS preferred-ID flip: any shared ``ids`` entry still matches.
    """
    for alias in record.aliases:
        if alias in index:
            return index[alias]
    return None


def _magnitude_revised(old: dict | None, new: dict | None) -> bool:
    if not old or not new or old.get("value") is None or new.get("value") is None:
        return False
    return abs(new["value"] - old["value"]) >= MAG_NOISE


def _apply_update(event: dict[str, Any], record: SourceRecord, now: datetime) -> str | None:
    """Fold a matching record into an existing event; return a change kind or None."""
    # Union aliases (order-stable) and record the source link.
    for alias in record.aliases:
        if alias not in event["aliases"]:
            event["aliases"].append(alias)
    event["source_refs"][record.source] = record.source_ref

    # A positive deletion signal is the only thing that retracts (never absence).
    if record.status == "deleted":
        if event["status"] != "retracted":
            event["status"] = "retracted"
            event["last_changed"] = iso_utc(now)
            return RETRACTION
        return None

    kind: str | None = None
    if _magnitude_revised(event.get("magnitude"), record.magnitude):
        kind = REVISION

    # Latest feed values win; the card always shows current best-known state.
    event["name"] = record.name
    event["magnitude"] = record.magnitude
    event["location"] = {"lat": record.lat, "lon": record.lon, "place": record.place}
    if record.pager_alert is not None:
        event["pager_alert"] = record.pager_alert

    # A previously aged-out/retracted event reappearing in the window is active again.
    if event["status"] != "active":
        event["status"] = "active"
        kind = kind or REVISION

    if kind:
        event["last_changed"] = iso_utc(now)
    return kind


def reconcile(
    snapshots: list[FeedSnapshot],
    state: dict[str, Any],
    *,
    now: datetime,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Diff snapshots against state; return (new_state, change_set). Pure."""
    state = copy.deepcopy(state)
    change_set: list[dict[str, str]] = []
    matched_ids: set[str] = set()
    ok_sources = {snap.source for snap in snapshots if snap.ok}

    for snap in snapshots:
        if not snap.ok:
            continue  # A failed fetch is no news — never a retraction or aging signal.
        for record in snap.records:
            index = _alias_index(state)
            eid = _match(record, index)
            if eid is None:
                origin_year = record.origin_time.year
                eid = next_canonical_id(state, origin_year)
                state["events"][eid] = _event_from_record(record, now)
                change_set.append({"id": eid, "kind": NEW})
            else:
                kind = _apply_update(state["events"][eid], record, now)
                if kind:
                    change_set.append({"id": eid, "kind": kind})
            matched_ids.add(eid)

    # Aged-out guard: an active event absent from a feed that *did* report is aged
    # out (kept in state), never retracted. If its covering feed failed, leave it.
    for eid, event in state["events"].items():
        if eid in matched_ids or event["status"] != "active":
            continue
        event_sources = {alias.split(":", 1)[0] for alias in event["aliases"]}
        if event_sources & ok_sources:
            event["status"] = "aged_out"
            event["last_changed"] = iso_utc(now)
            change_set.append({"id": eid, "kind": AGED_OUT})

    return state, change_set
