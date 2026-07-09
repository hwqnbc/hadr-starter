"""Renderer embeds the expected event state as a JSON island (N15 tests).

Per the testing seam (PRD): assert on the embedded state JSON, not on markup.
"""

from __future__ import annotations

import json
import re

from scripts.render import build_html

EVENTS = [
    {
        "id": "usgs:us6000taui",
        "hazard": "EQ",
        "name": "M 5.0 - 15 km NNE of Xunchang, China",
        "magnitude": {"value": 5.0, "type": "mww", "depth_km": 10},
        "location": {"lat": 28.5871, "lon": 104.7549, "place": "15 km NNE of Xunchang, China"},
        "origin_time": "2026-07-08T02:08:48Z",
        "gdacs_alert": None,
        "pager_alert": None,
        "status": "active",
        "source_refs": {"usgs": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000taui"},
    }
]
EDITION = {"title": "HADR Monitor — Earthquakes", "generated_at": "2026-07-08T02:49:03Z"}


def _extract_island(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="hadr-state">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "JSON island not found in rendered HTML"
    return json.loads(match.group(1))


def test_island_carries_events_and_edition():
    island = _extract_island(build_html(EVENTS, EDITION))
    assert island["events"] == EVENTS
    assert island["edition"] == EDITION


def test_page_is_self_contained_no_external_refs():
    html = build_html(EVENTS, EDITION)
    # ADR-0005: one self-contained file — no external scripts/styles/fetches.
    assert "src=" not in html
    assert 'href="http' not in html.replace("target=", "")  # source links live in the island
    assert "<style>" in html and "<script>" in html


def test_empty_state_still_renders():
    html = build_html([], {"title": "HADR Monitor", "generated_at": "2026-07-08T02:49:03Z"})
    island = _extract_island(html)
    assert island["events"] == []


def test_island_carries_edition_type_and_changelog():
    # V5: edition type badge (U1), quiet line (U4) and changelog (U9/U10/U11)
    # travel in the island; assertions are on the JSON, not the markup.
    edition = {
        "title": "HADR Monitor",
        "generated_at": "2026-07-09T00:30:00Z",
        "type": "regular",
        "changelog": {
            "escalations": [{"id": "evt-1", "kind": "escalation", "from": "Orange", "to": "Red"}],
            "downgrades": [],
            "revisions": [],
            "retractions": [],
        },
    }
    island = _extract_island(build_html(EVENTS, edition))
    assert island["edition"]["type"] == "regular"
    assert island["edition"]["changelog"]["escalations"][0]["to"] == "Red"


def test_quiet_edition_line_travels_in_island():
    edition = {
        "title": "HADR Monitor",
        "generated_at": "2026-07-09T00:30:00Z",
        "type": "quiet",
        "quiet_line": "No significant events — all feeds healthy",
        "changelog": {"escalations": [], "downgrades": [], "revisions": [], "retractions": []},
    }
    island = _extract_island(build_html([], edition))
    assert island["edition"]["quiet_line"].startswith("No significant events")


def test_page_has_filter_and_changelog_anchors():
    # U8 filter chips (N20 applyFilter) and the changelog container are present.
    html = build_html(EVENTS, EDITION)
    assert 'id="hazard-filter"' in html
    assert 'id="changelog"' in html
    assert "function applyFilter" in html


def test_assessment_prose_and_summary_travel_in_island():
    # V6: model prose rides on the event (U6) and a summary on the edition; both
    # travel in the JSON island without breaking it, and the bootstrap reads them.
    events = [{**EVENTS[0], "assessment": "A moderate quake struck offshore."}]
    edition = {**EDITION, "type": "regular", "summary": "One reportable event."}
    html = build_html(events, edition)
    island = _extract_island(html)
    assert island["events"][0]["assessment"].startswith("A moderate")
    assert island["edition"]["summary"] == "One reportable event."
    assert 'id="edition-summary"' in html
    assert "ev.assessment" in html  # the bootstrap places prose on the card


def test_coverage_rows_and_banner_travel_in_island():
    # V7: per-feed rows (U12) + a warning banner (U13) ride in the island; the
    # bootstrap renders them (converting last-success to SGT at display).
    coverage = {
        "feeds": [
            {
                "feed": "usgs",
                "label": "USGS",
                "last_success": "2026-07-09T05:50:00Z",
                "consecutive_failures": 0,
                "stale": False,
            },
            {
                "feed": "gdacs",
                "label": "GDACS",
                "last_success": "2026-07-09T03:10:00Z",
                "consecutive_failures": 3,
                "stale": True,
            },
        ],
        "stale": ["gdacs"],
        "banner": {
            "items": [{"feed": "gdacs", "label": "GDACS", "last_success": "2026-07-09T03:10:00Z"}],
            "note": "EQ coverage via USGS only",
        },
    }
    html = build_html(EVENTS, EDITION, coverage=coverage)
    island = _extract_island(html)
    assert island["coverage"]["stale"] == ["gdacs"]
    assert island["coverage"]["banner"]["items"][0]["label"] == "GDACS"
    assert 'id="coverage-banner"' in html and 'id="coverage-rows"' in html
    assert "function renderCoverage" in html
