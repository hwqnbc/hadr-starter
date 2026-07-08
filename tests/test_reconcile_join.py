"""Cross-source dedup: the join order and its guardrails (V3)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from hadr.__main__ import _enrich_gdacs
from scripts import fetch_gdacs, fetch_usgs, reconcile
from scripts.feeds import FeedSnapshot, SourceRecord
from scripts.state import empty_state

NOW = datetime(2026, 7, 8, 4, 0, 0, tzinfo=UTC)
T0 = datetime(2026, 7, 8, 2, 0, 0, tzinfo=UTC)


def usgs_rec(uid, *, mag=5.0, lat=0.0, lon=0.0, at=T0, aliases_extra=()):
    return SourceRecord(
        source="usgs",
        hazard="EQ",
        aliases=[f"usgs:{uid}", *aliases_extra],
        name=f"M {mag} - {uid}",
        origin_time=at,
        lat=lat,
        lon=lon,
        place=uid,
        source_ref=f"https://earthquake.usgs.gov/earthquakes/eventpage/{uid}",
        magnitude={"value": mag, "type": "mww", "depth_km": 10},
    )


def gdacs_rec(eid, *, lat=0.0, lon=0.0, at=T0, alert="Green", sourceid=None, glide=None):
    aliases = [f"gdacs:{eid}"]
    if glide:
        aliases.append(f"glide:{glide}")
    if sourceid:
        aliases.append(f"usgs:{sourceid}")
    return SourceRecord(
        source="gdacs",
        hazard="EQ",
        aliases=aliases,
        name=f"Earthquake {eid}",
        origin_time=at,
        lat=lat,
        lon=lon,
        place=f"country-{eid}",
        source_ref=f"https://www.gdacs.org/report.aspx?eventid={eid}",
        gdacs_alert=alert,
        glide=glide,
        extra={"eventid": eid},
    )


def _snap(source, records):
    return FeedSnapshot(source=source, records=records, fetched_at=NOW, ok=True)


def _reconcile(usgs_records, gdacs_records):
    snaps = [_snap("usgs", usgs_records), _snap("gdacs", gdacs_records)]
    return reconcile.reconcile(snaps, empty_state(), now=NOW)


def test_sourceid_join_makes_one_event_with_both_sources():
    usgs = [usgs_rec("us6000taui", mag=5.0, lat=28.58, lon=104.75)]
    gdacs = [gdacs_rec(1550709, lat=28.58, lon=104.75, alert="Green", sourceid="us6000taui")]
    state, _ = _reconcile(usgs, gdacs)

    assert len(state["events"]) == 1
    ev = next(iter(state["events"].values()))
    assert {"usgs:us6000taui", "gdacs:1550709"} <= set(ev["aliases"])
    assert ev["magnitude"]["value"] == 5.0  # USGS magnitude retained
    assert ev["gdacs_alert"] == "Green"
    assert set(ev["source_refs"]) == {"usgs", "gdacs"}


def test_glide_join_beats_distance():
    # A GLIDE match must join even when the epicentres are nowhere near each other.
    usgs = [
        replace(
            usgs_rec("us6000aaaa", lat=1.0, lon=1.0),
            aliases=["usgs:us6000aaaa", "glide:EQ-2026-000093-CHN"],
        )
    ]
    gdacs = [gdacs_rec(1551000, lat=80.0, lon=170.0, glide="EQ-2026-000093-CHN")]
    state, _ = _reconcile(usgs, gdacs)
    assert len(state["events"]) == 1


def test_heuristic_join_when_no_shared_id():
    usgs = [usgs_rec("us7000abcd", mag=6.2, lat=-6.51, lon=126.42, at=T0)]
    gdacs = [gdacs_rec(1550800, lat=-6.60, lon=126.50, at=T0.replace(minute=5), alert="Orange")]
    state, _ = _reconcile(usgs, gdacs)

    assert len(state["events"]) == 1
    ev = next(iter(state["events"].values()))
    assert ev["magnitude"]["value"] == 6.2 and ev["gdacs_alert"] == "Orange"


def test_mainshock_and_aftershock_stay_distinct():
    # Distinct USGS ids within the heuristic window are never merged.
    usgs = [
        usgs_rec("us7000main", lat=-6.51, lon=126.42, at=T0),
        usgs_rec("us7000after", lat=-6.55, lon=126.45, at=T0.replace(minute=20)),
    ]
    state, _ = _reconcile(usgs, [])
    assert len(state["events"]) == 2


def test_ambiguous_heuristic_stays_separate():
    # Two nearby USGS quakes, one GDACS quake with no id link near both -> ambiguous.
    usgs = [
        usgs_rec("us7000one", lat=-6.50, lon=126.40, at=T0),
        usgs_rec("us7000two", lat=-6.60, lon=126.50, at=T0.replace(minute=10)),
    ]
    gdacs = [gdacs_rec(1550801, lat=-6.55, lon=126.45, at=T0.replace(minute=5))]
    state, _ = _reconcile(usgs, gdacs)
    assert len(state["events"]) == 3  # the GDACS record stays on its own


def test_full_scenario_through_fetchers(scenario_a):
    """Integration: real fixtures + pipeline enrichment -> deduped state."""
    usgs_snap = fetch_usgs.snapshot(fixture=scenario_a / "usgs_all_day.json")
    gdacs_snap = _enrich_gdacs(
        fetch_gdacs.snapshot(fixture=scenario_a / "gdacs_events4app.json"),
        empty_state(),
        str(scenario_a),
    )
    state, _ = reconcile.reconcile([usgs_snap, gdacs_snap], empty_state(), now=NOW)

    # 3 USGS quakes; GDACS adds Xunchang (sourceid join) + Banda (heuristic) onto
    # existing events, and one GDACS-only Iceland quake. => 4 canonical events.
    assert len(state["events"]) == 4

    banda = next(e for e in state["events"].values() if "usgs:us7000abcd" in e["aliases"])
    assert banda["pager_alert"] == "yellow"  # USGS PAGER kept...
    assert banda["gdacs_alert"] == "Orange"  # ...separate from GDACS alert
    assert "gdacs:1550800" in banda["aliases"] and banda["magnitude"]["value"] == 6.2

    iceland = next(e for e in state["events"].values() if "gdacs:1550900" in e["aliases"])
    assert set(iceland["source_refs"]) == {"gdacs"}
