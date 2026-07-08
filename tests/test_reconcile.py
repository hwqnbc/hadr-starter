"""Single-source reconciliation: identity, revision, retraction, aged-out (V2)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from scripts import fetch_usgs, reconcile
from scripts.state import empty_state

NOW = datetime(2026, 7, 8, 3, 0, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 8, 3, 35, 0, tzinfo=UTC)


def _first_run(scenario_a):
    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    return reconcile.reconcile([snap], empty_state(), now=NOW)


def _find(state, alias):
    return next(e for e in state["events"].values() if alias in e["aliases"])


def test_first_run_creates_one_event_per_earthquake(scenario_a):
    state, changes = _first_run(scenario_a)
    # Three earthquakes; the quarry blast never enters state.
    assert len(state["events"]) == 3
    assert all(c["kind"] == reconcile.NEW for c in changes)
    assert all(k.startswith("evt-2026-") for k in state["events"])


def test_revision_updates_same_event_across_preferred_id_flip(scenario_a):
    state, _ = _first_run(scenario_a)
    xunchang_id = next(k for k, e in state["events"].items() if "usgs:us6000taui" in e["aliases"])

    revised = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day_revised.json")
    state2, changes = reconcile.reconcile([revised], state, now=LATER)

    # Same canonical id despite the preferred id flipping us6000taui -> us7000zzzz.
    event = state2["events"][xunchang_id]
    assert event["magnitude"]["value"] == 5.4
    assert "usgs:us7000zzzz" in event["aliases"] and "usgs:us6000taui" in event["aliases"]
    assert {"id": xunchang_id, "kind": reconcile.REVISION} in changes
    # No second Xunchang event was created.
    assert sum("usgs:us6000taui" in e["aliases"] for e in state2["events"].values()) == 1


def test_deleted_status_retracts_not_duplicates(scenario_a):
    state, _ = _first_run(scenario_a)
    banda_id = next(k for k, e in state["events"].items() if "usgs:us7000abcd" in e["aliases"])

    revised = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day_revised.json")
    state2, changes = reconcile.reconcile([revised], state, now=LATER)

    assert state2["events"][banda_id]["status"] == "retracted"
    assert {"id": banda_id, "kind": reconcile.RETRACTION} in changes


def test_absence_ages_out_never_retracts(scenario_a):
    state, _ = _first_run(scenario_a)
    avalon_id = next(k for k, e in state["events"].items() if "usgs:ci41287863" in e["aliases"])

    # Avalon is gone from the revised window (rolling-window absence, no deletion).
    revised = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day_revised.json")
    state2, changes = reconcile.reconcile([revised], state, now=LATER)

    assert state2["events"][avalon_id]["status"] == "aged_out"
    assert {"id": avalon_id, "kind": reconcile.AGED_OUT} in changes


def test_new_event_in_second_window_is_new(scenario_a):
    state, _ = _first_run(scenario_a)
    revised = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day_revised.json")
    state2, changes = reconcile.reconcile([revised], state, now=LATER)

    talaud = _find(state2, "usgs:us6000tnew")
    new_ids = [c["id"] for c in changes if c["kind"] == reconcile.NEW]
    assert any(state2["events"][i] is talaud for i in new_ids)


def test_failed_fetch_never_ages_out_existing_events(scenario_a):
    state, _ = _first_run(scenario_a)
    counts_before = {k: e["status"] for k, e in state["events"].items()}

    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    failed = replace(snap, ok=False, records=[])
    state2, changes = reconcile.reconcile([failed], state, now=LATER)

    # Staleness is not retraction: nothing changes on a failed fetch.
    assert changes == []
    assert {k: e["status"] for k, e in state2["events"].items()} == counts_before
