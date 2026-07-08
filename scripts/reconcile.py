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
from datetime import datetime, timedelta
from typing import Any

from scripts.feeds import FeedSnapshot, SourceRecord, iso_utc
from scripts.geo import haversine_km
from scripts.state import next_canonical_id

# A magnitude change below this is instrument noise, not a revision worth telling.
MAG_NOISE = 0.1

# Last-resort proximity join tolerances (ADR-0001): same hazard within this
# window of time and distance may be the same occurrence seen by two feeds.
HEURISTIC_TIME = timedelta(minutes=30)
HEURISTIC_KM = 250.0

# When two candidates both qualify, the nearer in combined (normalised) time-and-
# space wins (ADR-0001). Only a near-tie within this margin is "genuinely
# ambiguous" and left unmerged — a false merge hides a disaster, a missed one is
# visible and recoverable.
HEURISTIC_TIE_MARGIN = 0.15

# For a merged earthquake, USGS owns the descriptive fields (precise magnitude,
# location, title); GDACS contributes its alert level. A lower-priority source
# never overwrites these — it only adds aliases, its alert, and its source link.
DESCRIPTIVE_OWNER = "usgs"

# Change kinds emitted into the change set.
NEW = "new"
REVISION = "revision"
RETRACTION = "retraction"
AGED_OUT = "aged_out"


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
    owns_description = record.source == DESCRIPTIVE_OWNER or not event.get("name")

    # Magnitude: the descriptive owner (USGS) sets it; a lower-priority source may
    # only fill a value we don't yet have, and must never wipe the owner's value
    # (GDACS EQ magnitudes are coarse and often absent). A change beyond noise is
    # a revision.
    new_mag = record.magnitude
    has_new_mag = bool(new_mag) and new_mag.get("value") is not None
    old_mag = event.get("magnitude")
    event_has_mag = bool(old_mag) and old_mag.get("value") is not None
    if has_new_mag and (owns_description or not event_has_mag):
        if _magnitude_revised(old_mag, new_mag):
            kind = REVISION
        event["magnitude"] = new_mag

    # Descriptive fields follow source precedence; alerts are per-model, kept apart.
    if owns_description:
        event["name"] = record.name or event["name"]
        event["location"] = {"lat": record.lat, "lon": record.lon, "place": record.place}
    if record.pager_alert is not None:
        event["pager_alert"] = record.pager_alert
    if record.gdacs_alert is not None:
        event["gdacs_alert"] = record.gdacs_alert

    # A previously aged-out/retracted event reappearing in the window is active again.
    if event["status"] != "active":
        event["status"] = "active"
        kind = kind or REVISION

    if kind:
        event["last_changed"] = iso_utc(now)
    return kind


def _same_source_conflict(record: SourceRecord, event: dict[str, Any]) -> bool:
    """True if the event carries a *different* id in a source the record also uses.

    Two USGS ids (a mainshock and its aftershock) or two GDACS eventids are, by
    definition, distinct events — the heuristic must never merge them.
    """
    rec_sources = {a.split(":", 1)[0] for a in record.aliases}
    for alias in event["aliases"]:
        src = alias.split(":", 1)[0]
        if src in rec_sources and alias not in record.aliases:
            return True
    return False


def _heuristic_match(record: SourceRecord, state: dict[str, Any]) -> str | None:
    """Last-resort join: the nearest active same-hazard event within tolerance.

    Scores each candidate by combined normalised time-and-space distance and takes
    the closest (ADR-0001). Two candidates that score within ``HEURISTIC_TIE_MARGIN``
    of each other are genuinely ambiguous and stay separate rather than risk a false
    merge.
    """
    scored: list[tuple[float, str]] = []
    for eid, event in state["events"].items():
        if event["status"] == "retracted" or event["hazard"] != record.hazard:
            continue
        if _same_source_conflict(record, event):
            continue
        dt = abs(_parse_iso(event["origin_time"]) - record.origin_time)
        if dt > HEURISTIC_TIME:
            continue
        loc = event["location"]
        dist = haversine_km(loc["lat"], loc["lon"], record.lat, record.lon)
        if dist > HEURISTIC_KM:
            continue
        score = dt / HEURISTIC_TIME + dist / HEURISTIC_KM
        scored.append((score, eid))

    if not scored:
        return None
    scored.sort()
    if len(scored) >= 2 and scored[1][0] - scored[0][0] <= HEURISTIC_TIE_MARGIN:
        return None  # nearest two are indistinguishable -> ambiguous, stay separate
    return scored[0][1]


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
            # Join order (ADR-0001): shared alias (GLIDE or the GDACS sourceid
            # folded into the USGS alias set) first, then the proximity heuristic.
            eid = _match(record, index) or _heuristic_match(record, state)
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
