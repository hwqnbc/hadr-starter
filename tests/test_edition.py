"""Edition builder (V5 / N12, N13): changelog, quiet decision, marker advance.

Deterministic, no model call on any path (ADR-0003). Asserts on the returned
edition content and the advanced marker.
"""

from __future__ import annotations

from datetime import UTC, datetime

from scripts import edition
from scripts.state import empty_state

NOW = datetime(2026, 7, 9, 0, 30, 0, tzinfo=UTC)  # 08:30 SGT edition
LAST_EDITION = "2026-07-08T00:30:00Z"


def _event(**over):
    base = {
        "hazard": "EQ",
        "name": "test event",
        "aliases": ["usgs:usX"],
        "location": {"lat": 0.0, "lon": 0.0, "place": "somewhere"},
        "origin_time": "2026-07-08T00:00:00Z",
        "magnitude": {"value": 5.0, "type": "mww", "depth_km": 10},
        "gdacs_alert": None,
        "pager_alert": None,
        "reported": False,
        "flash_published": False,
        "status": "active",
        "first_seen": "2026-07-08T00:00:00Z",
        "last_changed": "2026-07-09T00:29:00Z",  # after LAST_EDITION -> post-marker
        "source_refs": {"usgs": "https://example/usX"},
    }
    base.update(over)
    return base


def _state(events, marker=None):
    st = empty_state()
    st["events"] = events
    if marker is not None:
        st["edition_marker"] = marker
    return st


def _marker(last_edition_at=LAST_EDITION):
    return {"last_edition_at": last_edition_at, "acknowledged_changes": []}


# --- Quiet vs regular ------------------------------------------------------


def test_quiet_edition_when_nothing_reportable_and_no_changes():
    st = _state({"evt-1": _event(gdacs_alert="Green", last_changed=LAST_EDITION)})
    marker = _marker()
    content = edition.build_edition(st, marker, [], st, now=NOW, reportable_ids=[])
    assert content["type"] == "quiet"
    assert content["quiet_line"] == edition.QUIET_LINE
    # No model path: quiet content is produced directly by the deterministic builder.
    assert all(not v for v in content["changelog"].values())


def test_regular_edition_when_something_is_reportable():
    st = _state({"evt-1": _event(gdacs_alert="Orange")})
    content = edition.build_edition(st, _marker(), [], st, now=NOW, reportable_ids=["evt-1"])
    assert content["type"] == "regular"
    assert "quiet_line" not in content


def test_regular_edition_when_changes_but_nothing_reportable():
    # A downgrade with no current reportables still makes a regular edition.
    prior = _state({"evt-1": _event(gdacs_alert="Orange")})
    new = _state({"evt-1": _event(gdacs_alert="Green")})
    content = edition.build_edition(new, _marker(), [], prior, now=NOW, reportable_ids=[])
    assert content["type"] == "regular"
    assert len(content["changelog"]["downgrades"]) == 1


# --- Changelog classification + ordering -----------------------------------


def test_escalation_leads_the_changelog_above_downgrades():
    prior = _state(
        {
            "evt-esc": _event(gdacs_alert="Orange", aliases=["usgs:e"]),
            "evt-down": _event(gdacs_alert="Red", aliases=["usgs:d"]),
        }
    )
    new = _state(
        {
            "evt-esc": _event(gdacs_alert="Red", aliases=["usgs:e"]),
            "evt-down": _event(gdacs_alert="Orange", aliases=["usgs:d"]),
        }
    )
    content = edition.build_edition(new, _marker(), [], prior, now=NOW, reportable_ids=["evt-esc"])
    cl = content["changelog"]
    assert [e["id"] for e in cl["escalations"]] == ["evt-esc"]
    assert cl["escalations"][0]["from"] == "Orange" and cl["escalations"][0]["to"] == "Red"
    assert [e["id"] for e in cl["downgrades"]] == ["evt-down"]
    # Render order: escalations section is emitted before downgrades (US7).
    assert list(cl.keys()).index("escalations") < list(cl.keys()).index("downgrades")


def test_retraction_appears_in_changelog():
    prior = _state({"evt-1": _event(gdacs_alert="Orange", status="active")})
    new = _state({"evt-1": _event(gdacs_alert="Orange", status="retracted")})
    content = edition.build_edition(new, _marker(), [], prior, now=NOW, reportable_ids=[])
    assert [e["id"] for e in content["changelog"]["retractions"]] == ["evt-1"]


def test_revision_one_liner_uses_change_set():
    prior = _state({"evt-1": _event(gdacs_alert="Orange", magnitude={"value": 5.0})})
    new = _state({"evt-1": _event(gdacs_alert="Orange", magnitude={"value": 5.4})})
    change_set = [{"id": "evt-1", "kind": "revision"}]
    content = edition.build_edition(
        new, _marker(), change_set, prior, now=NOW, reportable_ids=["evt-1"]
    )
    revs = content["changelog"]["revisions"]
    assert [e["id"] for e in revs] == ["evt-1"] and revs[0]["magnitude"] == 5.4


def test_new_event_is_not_a_changelog_entry():
    # A first-sight event is a board card, not an "update" line.
    new = _state({"evt-1": _event(gdacs_alert="Orange")})
    content = edition.build_edition(
        new, _marker(), [], empty_state(), now=NOW, reportable_ids=["evt-1"]
    )
    assert all(not v for v in content["changelog"].values())


# --- Marker semantics ------------------------------------------------------


def test_changelog_contains_only_post_marker_changes():
    # evt-old changed before the last edition (already told); evt-new changed after.
    prior = _state(
        {
            "evt-old": _event(gdacs_alert="Orange", aliases=["usgs:o"]),
            "evt-new": _event(gdacs_alert="Orange", aliases=["usgs:n"]),
        }
    )
    new = _state(
        {
            "evt-old": _event(
                gdacs_alert="Red", aliases=["usgs:o"], last_changed="2026-07-07T00:00:00Z"
            ),
            "evt-new": _event(
                gdacs_alert="Red", aliases=["usgs:n"], last_changed="2026-07-09T00:29:00Z"
            ),
        }
    )
    content = edition.build_edition(new, _marker(), [], prior, now=NOW, reportable_ids=[])
    assert [e["id"] for e in content["changelog"]["escalations"]] == ["evt-new"]


def test_marker_advances_monotonically():
    st = _state({"evt-1": _event(gdacs_alert="Orange")})
    marker = _marker()
    edition.build_edition(st, marker, [], st, now=NOW, reportable_ids=["evt-1"])
    assert marker["last_edition_at"] == "2026-07-09T00:30:00Z"
    assert marker["last_edition_at"] > LAST_EDITION

    # An earlier "now" must never move the marker backwards.
    earlier = datetime(2026, 7, 8, 12, 0, 0, tzinfo=UTC)
    edition.build_edition(st, marker, [], st, now=earlier, reportable_ids=["evt-1"])
    assert marker["last_edition_at"] == "2026-07-09T00:30:00Z"


def test_first_ever_edition_has_no_prior_marker():
    st = _state({"evt-1": _event(gdacs_alert="Orange")}, marker=empty_state()["edition_marker"])
    content = edition.build_edition(
        st, st["edition_marker"], [], empty_state(), now=NOW, reportable_ids=["evt-1"]
    )
    assert content["type"] == "regular"
    assert st["edition_marker"]["last_edition_at"] == "2026-07-09T00:30:00Z"


# --- V8: changelog accumulates across polls (compares to the last edition) --


def test_changelog_compares_against_baseline_not_the_last_poll():
    # Edition 1 snapshots a baseline at Green. Between editions, hourly polls move
    # the event Green -> Orange -> Red (the *last poll* saw Orange->Red only). The
    # next edition must report the full crossing since edition 1: Green -> Red.
    st = _state({"evt-1": _event(gdacs_alert="Green", last_changed="2026-07-08T00:31:00Z")})
    marker = _marker()
    edition.build_edition(st, marker, [], st, now=NOW, reportable_ids=[])
    assert marker["baseline"]["evt-1"]["level"] == 0  # Green captured at edition 1

    # ... polls advance the event to Red without touching the marker/baseline ...
    st2 = _state({"evt-1": _event(gdacs_alert="Red", last_changed="2026-07-09T12:00:00Z")})
    st2["edition_marker"] = marker  # same persisted marker (carries the baseline)
    later = datetime(2026, 7, 10, 0, 30, 0, tzinfo=UTC)
    content = edition.build_edition(st2, marker, [], st2, now=later, reportable_ids=["evt-1"])
    escs = content["changelog"]["escalations"]
    assert [e["id"] for e in escs] == ["evt-1"]
    assert escs[0]["from"] == "Green" and escs[0]["to"] == "Red"  # full crossing, not Orange->Red
    # Baseline advances to Red for the following edition.
    assert marker["baseline"]["evt-1"]["level"] == 3
