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
