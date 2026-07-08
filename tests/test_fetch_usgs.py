"""USGS fetcher parses a recorded fixture correctly (N5 tests)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from scripts import fetch_usgs


def test_parse_ids_splits_comma_wrapped_string():
    assert fetch_usgs.parse_ids(",ci41287863,us6000tafd,") == ["ci41287863", "us6000tafd"]
    assert fetch_usgs.parse_ids("") == []


def test_snapshot_filters_to_earthquakes(scenario_a):
    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    # The quarry-blast feature is dropped; three earthquakes remain.
    assert snap.ok is True
    assert len(snap.records) == 3
    assert all(r.hazard == "EQ" for r in snap.records)


def test_snapshot_keeps_all_aliases_and_preferred_id_first(scenario_a):
    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    avalon = next(r for r in snap.records if "usgs:ci41287863" in r.aliases)
    # Preferred id first, then remaining ids entries, de-duplicated.
    assert avalon.aliases == ["usgs:ci41287863", "usgs:us6000tafd"]


def test_snapshot_parses_magnitude_depth_and_pager(scenario_a):
    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    banda = next(r for r in snap.records if "usgs:us7000abcd" in r.aliases)
    assert banda.magnitude == {"value": 6.2, "type": "mww", "depth_km": 35.0}
    assert banda.pager_alert == "yellow"


def test_snapshot_converts_epoch_ms_to_utc(scenario_a):
    snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    xunchang = next(r for r in snap.records if "usgs:us6000taui" in r.aliases)
    assert xunchang.origin_time == datetime(2026, 7, 8, 2, 8, 48, tzinfo=UTC)
    assert snap.feed_generated_at == datetime(2026, 7, 8, 2, 49, 3, tzinfo=UTC)


def test_snapshot_returns_not_ok_on_http_error():
    # A feed outage degrades gracefully rather than raising out of the run.
    client = httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(503)))
    snap = fetch_usgs.snapshot(client=client)
    assert snap.ok is False and snap.records == [] and snap.error
