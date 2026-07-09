"""Flash publish (V8 / N10): act on the flash seam Slice 2 only stored.

An event crossing into Red on an hourly poll re-renders the dashboard early with
the flash banner and sets ``flash_published`` (once per Red spell). The gate
computes the trigger; the poll acts on it. Also covers the flash edition content.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from hadr.__main__ import _run_poll
from scripts import edition, gate
from scripts.state import empty_state

NOW = datetime(2026, 7, 9, 5, 0, 0, tzinfo=UTC)


def _event(**over):
    base = {
        "hazard": "EQ",
        "name": "M 7.1 - Banda Sea",
        "aliases": ["usgs:usR"],
        "location": {"lat": -6.1, "lon": 129.9, "place": "Banda Sea"},
        "origin_time": "2026-07-09T04:30:00Z",
        "magnitude": {"value": 7.1, "type": "mww", "depth_km": 20},
        "gdacs_alert": None,
        "pager_alert": None,
        "reported": False,
        "flash_published": False,
        "status": "active",
        "first_seen": "2026-07-09T04:31:00Z",
        "last_changed": "2026-07-09T04:59:00Z",
        "source_refs": {"usgs": "https://example/usR"},
    }
    base.update(over)
    return base


def _state(events):
    st = empty_state()
    st["events"] = events
    return st


# --- flash edition content -------------------------------------------------


def test_build_flash_edition_names_the_red_events_and_carries_no_changelog():
    st = _state({"evt-1": _event(gdacs_alert="Red")})
    content = edition.build_flash_edition(st, ["evt-1"], now=NOW, title="HADR Monitor")
    assert content["type"] == "flash"
    assert content["flash"]["events"][0]["id"] == "evt-1"
    assert content["flash"]["events"][0]["name"] == "M 7.1 - Banda Sea"
    # Flash bypasses the edition builder + model: no changelog entries.
    assert all(not v for v in content["changelog"].values())


# --- poll acts on the flash (N10) ------------------------------------------


def _island(html: str) -> dict:
    m = re.search(
        r'<script type="application/json" id="hadr-state">(.*?)</script>', html, re.DOTALL
    )
    return json.loads(m.group(1))


def test_poll_publishes_flash_sets_guard_and_renders_banner(tmp_path):
    st = _state({"evt-1": _event(gdacs_alert="Red")})
    reportables, flash = gate.gate([], st, empty_state())
    assert flash == ["evt-1"]  # escalation/first-sight into Red triggers a flash

    events = [{"id": "evt-1", **st["events"]["evt-1"]}]
    out = tmp_path / "dashboard.html"
    state_path = tmp_path / "state.json"
    rc = _run_poll(
        st, flash, events, {"feeds": [], "stale": [], "banner": None}, NOW, out, state_path, []
    )

    assert rc == 0
    # Guard set on publish -> fires once per Red spell.
    assert st["events"]["evt-1"]["flash_published"] is True
    # Dashboard re-rendered with the flash banner in the island.
    island = _island(out.read_text(encoding="utf-8"))
    assert island["edition"]["type"] == "flash"
    assert island["edition"]["flash"]["events"][0]["id"] == "evt-1"
    # State persisted.
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["events"]["evt-1"]["flash_published"] is True


def test_sustained_red_does_not_reflash_after_publish():
    # After a flash is published, a later poll with the event still at Red does
    # not re-flash (guard held; prior already Red).
    published = _state({"evt-1": _event(gdacs_alert="Red", flash_published=True)})
    still_red = _state({"evt-1": _event(gdacs_alert="Red", flash_published=True)})
    _, flash = gate.gate([], still_red, published)
    assert flash == []


def test_poll_without_flash_persists_state_but_does_not_render(tmp_path):
    st = _state({"evt-1": _event(gdacs_alert="Orange")})  # reportable but not Red
    reportables, flash = gate.gate([], st, empty_state())
    assert flash == []
    events = [{"id": "evt-1", **st["events"]["evt-1"]}]
    out = tmp_path / "dashboard.html"
    state_path = tmp_path / "state.json"
    rc = _run_poll(
        st, flash, events, {"feeds": [], "stale": [], "banner": None}, NOW, out, state_path, []
    )
    assert rc == 0
    assert state_path.exists()  # state persisted
    assert not out.exists()  # last published dashboard stands; no re-render
