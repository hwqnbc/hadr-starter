"""CLI entry point: ``python -m hadr run [--now | --fixture DIR]``.

Pipeline: fetch USGS -> reconcile against committed state -> persist state ->
render the dashboard from the current best-known event state. Later slices add
feeds and a gated model step between reconcile and render without changing this
surface.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import fetch_gdacs, fetch_usgs, reconcile
from scripts import state as state_store
from scripts.feeds import HAZARD_EQ, FeedSnapshot, iso_utc
from scripts.render import DEFAULT_OUTPUT, render

# Render newest origin first; a stable sort keyed on origin_time.
_RENDER_ORDER = "origin_time"


def _events_for_render(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Project committed events into render-ready dicts (id folded in)."""
    events = [{"id": eid, **event} for eid, event in state["events"].items()]
    events.sort(key=lambda e: e[_RENDER_ORDER], reverse=True)
    return events


def _already_joined(prior: dict[str, Any], eventid: object) -> bool:
    """True if a prior canonical event already carries this GDACS id + a USGS alias.

    When so, the sourceid is cached on the event and the detail call is skipped
    (SPIKE-1: re-fetch only when the episode changes).
    """
    gdacs_alias = f"gdacs:{eventid}"
    for event in prior["events"].values():
        aliases = event["aliases"]
        if gdacs_alias in aliases and any(a.startswith("usgs:") for a in aliases):
            return True
    return False


def _enrich_gdacs(snap: FeedSnapshot, prior: dict[str, Any], fixture: str | None) -> FeedSnapshot:
    """Fold each new/changed GDACS earthquake's USGS sourceid in as an alias (N8)."""
    records = []
    for record in snap.records:
        eventid = record.extra.get("eventid")
        needs_detail = (
            record.hazard == HAZARD_EQ
            and eventid is not None
            and not _already_joined(prior, eventid)
        )
        if needs_detail:
            detail_fixture = (
                str(Path(fixture) / f"gdacs_detail_{eventid}.json") if fixture else None
            )
            missing = detail_fixture is not None and not Path(detail_fixture).exists()
            sourceid = (
                None if missing else fetch_gdacs.event_detail(eventid, fixture=detail_fixture)
            )
            if sourceid:
                record = replace(record, aliases=[*record.aliases, f"usgs:{sourceid}"])
        records.append(record)
    return replace(snap, records=records)


def run(*, fixture: str | None, output: str | Path, state_path: str | Path) -> int:
    """Fetch USGS + GDACS (live or fixture), reconcile into state, persist, render."""
    now = datetime.now(tz=UTC)
    prior = state_store.load(state_path)

    usgs_fixture = str(Path(fixture) / "usgs_all_day.json") if fixture else None
    gdacs_fixture = str(Path(fixture) / "gdacs_events4app.json") if fixture else None

    usgs_snap = fetch_usgs.snapshot(fixture=usgs_fixture)
    gdacs_snap = _enrich_gdacs(fetch_gdacs.snapshot(fixture=gdacs_fixture), prior, fixture)
    # USGS first so a GDACS earthquake joins onto the existing USGS event.
    snapshots: list[FeedSnapshot] = [usgs_snap, gdacs_snap]
    new_state, change_set = reconcile.reconcile(snapshots, prior, now=now)
    state_store.save(new_state, state_path)

    edition_content = {
        "title": "HADR Monitor — Earthquakes",
        "generated_at": iso_utc(now),
    }
    events = _events_for_render(new_state)
    render(events, edition_content, output=output)

    counts = Counter(c["kind"] for c in change_set)
    summary = ", ".join(f"{kind}×{n}" for kind, n in counts.items()) or "no changes"
    print(f"Rendered {len(events)} event(s) to {output} ({summary})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hadr", description="HADR Monitor pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="fetch feeds, reconcile, and render the dashboard")
    mode = run_p.add_mutually_exclusive_group()
    mode.add_argument("--now", action="store_true", help="fetch live feeds (default)")
    mode.add_argument("--fixture", metavar="DIR", help="read recorded fixtures from DIR")
    run_p.add_argument("--output", default=DEFAULT_OUTPUT, help="dashboard output path")
    run_p.add_argument("--state", default=state_store.DEFAULT_PATH, help="path to state.json")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(fixture=args.fixture, output=args.output, state_path=args.state)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
