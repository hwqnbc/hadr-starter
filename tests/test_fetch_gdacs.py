"""GDACS fetcher parses the event list and detail payloads (N4, N8 tests)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from scripts import fetch_gdacs


def test_snapshot_parses_earthquakes_with_aliases_and_alert(scenario_a):
    snap = fetch_gdacs.snapshot(fixture=scenario_a / "gdacs_events4app.json")
    assert snap.ok and snap.source == "gdacs"
    xunchang = next(r for r in snap.records if "gdacs:1550709" in r.aliases)
    assert xunchang.hazard == "EQ"
    assert xunchang.gdacs_alert == "Green"
    assert xunchang.origin_time == datetime(2026, 7, 8, 2, 8, 48, tzinfo=UTC)
    assert xunchang.extra["eventid"] == 1550709


def test_snapshot_keeps_all_reported_hazards():
    payload = {
        "features": [
            {
                "geometry": {"coordinates": [0, 0]},
                "properties": {
                    "eventtype": "TC",
                    "eventid": 1,
                    "name": "Cyclone",
                    "fromdate": "2026-07-08T00:00:00",
                    "country": "Fiji",
                    "alertlevel": "Red",
                    "url": {},
                },
            },
            {
                "geometry": {"coordinates": [0, 0]},
                "properties": {
                    "eventtype": "XX",
                    "eventid": 2,
                    "name": "Not a hazard",
                    "fromdate": "2026-07-08T00:00:00",
                    "country": "?",
                    "url": {},
                },
            },
        ]
    }
    snap = fetch_gdacs.parse(payload, fetched_at=datetime(2026, 7, 8, tzinfo=UTC))
    hazards = {r.hazard for r in snap.records}
    assert hazards == {"TC"}  # the unknown eventtype is dropped


def test_sourceid_from_detail(scenario_a):
    sid = fetch_gdacs.event_detail(1550709, fixture=scenario_a / "gdacs_detail_1550709.json")
    assert sid == "us6000taui"


def test_sourceid_from_detail_empty_is_none():
    assert fetch_gdacs.sourceid_from_detail({"properties": {"sourceid": ""}}) is None


def test_snapshot_returns_not_ok_on_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(500)))
    snap = fetch_gdacs.snapshot(client=client)
    assert snap.ok is False and snap.records == []


def test_event_detail_returns_none_on_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda _req: httpx.Response(500)))
    assert fetch_gdacs.event_detail(1550709, client=client) is None
