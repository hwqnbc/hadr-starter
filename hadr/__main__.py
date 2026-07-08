"""CLI entry point: ``python -m hadr run [--now | --fixture DIR]``.

V1 wiring: fetch USGS -> render dashboard. Later slices insert reconcile/state
and additional feeds between the fetch and the render without changing this
surface.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import fetch_usgs
from scripts.feeds import FeedSnapshot, SourceRecord
from scripts.render import DEFAULT_OUTPUT, render


def iso_utc(dt: datetime) -> str:
    """UTC datetime -> ISO string with a trailing ``Z`` (state.json convention)."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_to_event(record: SourceRecord) -> dict[str, Any]:
    """Project a source record into a render-ready event dict (V1: one feed)."""
    return {
        "id": record.aliases[0] if record.aliases else record.name,
        "hazard": record.hazard,
        "name": record.name,
        "magnitude": record.magnitude,
        "location": {"lat": record.lat, "lon": record.lon, "place": record.place},
        "origin_time": iso_utc(record.origin_time),
        "gdacs_alert": record.gdacs_alert,
        "pager_alert": record.pager_alert,
        "status": "active",
        "source_refs": {"usgs": record.source_ref},
    }


def run(*, fixture: str | None, output: str | Path) -> int:
    """Fetch USGS (live or fixture), render the dashboard, report a summary."""
    usgs_fixture = str(Path(fixture) / "usgs_all_day.json") if fixture else None
    snapshot: FeedSnapshot = fetch_usgs.snapshot(fixture=usgs_fixture)

    events = [_record_to_event(r) for r in snapshot.records]
    # Most recent origin first.
    events.sort(key=lambda e: e["origin_time"], reverse=True)

    edition_content = {
        "title": "HADR Monitor — Earthquakes",
        "generated_at": iso_utc(datetime.now(tz=UTC)),
    }
    render(events, edition_content, output=output)
    print(f"Rendered {len(events)} event(s) to {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hadr", description="HADR Monitor pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="fetch feeds and render the dashboard")
    mode = run_p.add_mutually_exclusive_group()
    mode.add_argument("--now", action="store_true", help="fetch live feeds (default)")
    mode.add_argument("--fixture", metavar="DIR", help="read recorded fixtures from DIR")
    run_p.add_argument("--output", default=DEFAULT_OUTPUT, help="dashboard output path")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(fixture=args.fixture, output=args.output)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
