"""Impact gate (V4 / N9): reportable arms, tracked-but-hidden, flash trigger.

Pure-function seam per the testing decisions: (change_set, state, prior) in,
(reportables, flash_trigger) out, with the state annotated in place.
"""

from __future__ import annotations

from scripts import gate
from scripts.state import empty_state


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
        "last_changed": "2026-07-08T00:00:00Z",
        "source_refs": {"usgs": "https://example/usX"},
    }
    base.update(over)
    return base


def _state(events):
    st = empty_state()
    st["events"] = events
    return st


# --- Reportable arms (ADR-0002), each true/false ---------------------------


def test_gdacs_orange_is_reportable():
    st = _state({"evt-1": _event(gdacs_alert="Orange")})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == ["evt-1"]
    assert st["events"]["evt-1"]["reported"] is True


def test_gdacs_green_is_not_reportable_but_stays_tracked():
    # M4.6-style Green: kept in state, absent from the board (reported stays False).
    st = _state({"evt-1": _event(gdacs_alert="Green")})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == []
    assert st["events"]["evt-1"]["reported"] is False


def test_green_tracked_hidden_while_orange_reported():
    st = _state(
        {
            "evt-green": _event(gdacs_alert="Green", aliases=["usgs:g"]),
            "evt-orange": _event(gdacs_alert="Orange", aliases=["usgs:o"]),
        }
    )
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == ["evt-orange"]
    assert st["events"]["evt-green"]["reported"] is False
    assert st["events"]["evt-orange"]["reported"] is True


def test_pager_yellow_is_reportable():
    st = _state({"evt-1": _event(pager_alert="yellow")})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == ["evt-1"]


def test_pager_green_is_not_reportable():
    st = _state({"evt-1": _event(pager_alert="green")})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == []


def test_escalation_of_tracked_event_is_reportable():
    prior = _state({"evt-1": _event(gdacs_alert="Green", reported=False)})
    new = _state({"evt-1": _event(gdacs_alert="Orange")})
    reportables, _ = gate.gate([], new, prior)
    assert reportables == ["evt-1"]


def test_reliefweb_curation_of_unreported_event_is_reportable():
    # ReliefWeb fetcher not wired yet; this arm is a ready, tested code path.
    st = _state({"evt-1": _event(source_refs={"reliefweb": "https://reliefweb/x"}, reported=False)})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == ["evt-1"]


def test_reliefweb_arm_does_not_refire_once_reported():
    st = _state({"evt-1": _event(source_refs={"reliefweb": "https://reliefweb/x"}, reported=True)})
    # Already reported and otherwise sub-threshold -> not a fresh reportable.
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == []


def test_retracted_event_is_not_on_the_board():
    st = _state({"evt-1": _event(gdacs_alert="Orange", status="retracted")})
    reportables, _ = gate.gate([], st, empty_state())
    assert reportables == []


# --- Flash trigger: crosses into Red, once per spell ------------------------


def test_flash_fires_for_new_event_at_red():
    st = _state({"evt-1": _event(gdacs_alert="Red")})
    _, flash = gate.gate([], st, empty_state())
    assert flash == ["evt-1"]
    assert st["flash_pending"] == ["evt-1"]


def test_flash_fires_for_escalation_into_red():
    prior = _state({"evt-1": _event(gdacs_alert="Orange")})
    new = _state({"evt-1": _event(gdacs_alert="Red")})
    _, flash = gate.gate([], new, prior)
    assert flash == ["evt-1"]


def test_no_flash_while_one_is_outstanding_for_the_spell():
    # Sustained Red with a flash already published -> no re-flash.
    prior = _state({"evt-1": _event(gdacs_alert="Red", flash_published=True)})
    new = _state({"evt-1": _event(gdacs_alert="Red", flash_published=True)})
    _, flash = gate.gate([], new, prior)
    assert flash == []


def test_drop_below_red_clears_the_guard_and_re_escalation_flashes_again():
    # Red (flashed) -> Orange clears flash_published...
    prior = _state({"evt-1": _event(gdacs_alert="Red", flash_published=True)})
    dropped = _state({"evt-1": _event(gdacs_alert="Orange", flash_published=True)})
    _, flash = gate.gate([], dropped, prior)
    assert flash == []
    assert dropped["events"]["evt-1"]["flash_published"] is False
    # ...so a later re-escalation into Red flashes again.
    reesc = _state({"evt-1": _event(gdacs_alert="Red", flash_published=False)})
    _, flash2 = gate.gate([], reesc, dropped)
    assert flash2 == ["evt-1"]


def test_sub_red_event_never_flashes():
    st = _state({"evt-1": _event(gdacs_alert="Orange", pager_alert="orange")})
    _, flash = gate.gate([], st, empty_state())
    assert flash == []
