"""CLI entry point for the HADR Monitor pipeline.

Subcommands:

- ``run [--now | --fixture DIR] [--mode poll|edition]`` — fetch USGS + GDACS,
  reconcile against committed state, record coverage, gate, persist state, and
  render. In ``edition`` mode it also builds the changelog edition and emits the
  reportables payload for the guarded model step; in ``poll`` mode it re-renders
  only when a flash fires (N10), otherwise it just persists state.
- ``assess --input FILE`` — the guarded model step (N14): read the reportables
  payload, phrase it via the ``/sitrep`` seam, fold the prose in and re-render.
  This is the only step the workflow gives ``ANTHROPIC_API_KEY``.
- ``mode --event NAME [--cron CRON]`` — print the pipeline mode for a trigger
  (N3), the single source of truth the workflow branches on.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts import assess as assessor
from scripts import edition as edition_builder
from scripts import fetch_gdacs, fetch_usgs, gate, reconcile, schedule, staleness
from scripts import state as state_store
from scripts.feeds import HAZARD_EQ, FeedSnapshot
from scripts.render import DEFAULT_OUTPUT, render
from scripts.retry import fetch_with_retry

# Render newest origin first; a stable sort keyed on origin_time.
_RENDER_ORDER = "origin_time"

_TITLE = "HADR Monitor — Earthquakes"

# Transient sidecar the deterministic run writes and the guarded model step reads.
# Gitignored: it is regenerated every edition, never committed.
DEFAULT_ASSESSMENT_INPUT = "data/assessment_input.json"


def _events_for_render(state: dict[str, Any], reportable_ids: list[str]) -> list[dict[str, Any]]:
    """Project the reportable events into render-ready dicts (id folded in).

    Only events that cleared the impact gate (V4) reach the board; sub-threshold
    events stay tracked in state (``reported: false``) but hidden. Changes to
    events that dropped off the board are surfaced in the changelog (V5).
    """
    events = [{"id": eid, **state["events"][eid]} for eid in reportable_ids]
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


def _enrich_gdacs(
    snap: FeedSnapshot,
    prior: dict[str, Any],
    fixture: str | None,
    *,
    client: httpx.Client | None = None,
) -> FeedSnapshot:
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
                None
                if missing
                else fetch_gdacs.event_detail(eventid, client=client, fixture=detail_fixture)
            )
            if sourceid:
                record = replace(record, aliases=[*record.aliases, f"usgs:{sourceid}"])
        records.append(record)
    return replace(snap, records=records)


def run(
    *,
    fixture: str | None,
    output: str | Path,
    state_path: str | Path,
    mode: str = schedule.EDITION,
    assessment_input: str | Path | None = DEFAULT_ASSESSMENT_INPUT,
) -> int:
    """Fetch USGS + GDACS (live or fixture), reconcile into state, persist, render.

    ``mode`` selects the trigger behaviour (N3):

    - ``edition`` (08:30 SGT / dispatch): build the changelog edition, render, and
      — when there are reportables — write the ``assessment_input`` payload for the
      guarded model step (N14) to phrase.
    - ``poll`` (hourly): persist reconciled state and re-render *only* when a flash
      fires (N10, an event crossing into Red); otherwise the last published
      dashboard stands. No edition build, no model call.
    """
    now = datetime.now(tz=UTC)
    prior = state_store.load(state_path)

    usgs_fixture = str(Path(fixture) / "usgs_all_day.json") if fixture else None
    gdacs_fixture = str(Path(fixture) / "gdacs_events4app.json") if fixture else None

    # One pooled client for the whole live run (list + per-EQ detail calls); the
    # fixture path makes no requests, so no client is created.
    client = None if fixture else httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        # Polite retry-with-backoff within the run (B7.4); a fixture read never
        # fails, so live runs are the only ones that actually back off.
        usgs_snap = fetch_with_retry(
            lambda: fetch_usgs.snapshot(client=client, fixture=usgs_fixture)
        )
        gdacs_snap = _enrich_gdacs(
            fetch_with_retry(lambda: fetch_gdacs.snapshot(client=client, fixture=gdacs_fixture)),
            prior,
            fixture,
            client=client,
        )
    finally:
        if client is not None:
            client.close()

    # USGS first so a GDACS earthquake joins onto the existing USGS event.
    snapshots: list[FeedSnapshot] = [usgs_snap, gdacs_snap]
    new_state, change_set = reconcile.reconcile(snapshots, prior, now=now)

    # Record per-feed success/failure into state (S2); a failed fetch keeps the
    # last known success — staleness is not retraction (V7).
    for snap in snapshots:
        staleness.record(
            new_state["feed_status"],
            snap.source,
            ok=snap.ok,
            now=now,
            feed_generated_at=snap.feed_generated_at,
        )
    coverage = staleness.coverage(new_state["feed_status"], now)

    # Impact gate (V4): decide reportables + flash trigger, annotate state.
    reportable_ids, flash_trigger = gate.gate(change_set, new_state, prior)
    events = _events_for_render(new_state, reportable_ids)

    if mode == schedule.POLL:
        return _run_poll(
            new_state, flash_trigger, events, coverage, now, output, state_path, change_set
        )

    # Edition mode (V5): changelog since the marker, quiet/regular, advance marker.
    edition_content = edition_builder.build_edition(
        new_state,
        new_state["edition_marker"],
        change_set,
        prior,
        now=now,
        reportable_ids=reportable_ids,
        title=_TITLE,
    )
    state_store.save(new_state, state_path)
    render(events, edition_content, coverage=coverage, output=output)

    # Emit the reportables payload for the guarded model step (N14). Written only
    # when there is something to assess, so a quiet morning never triggers it.
    if reportable_ids and assessment_input:
        _write_assessment_input(assessment_input, events, edition_content, coverage)

    counts = Counter(c["kind"] for c in change_set)
    summary = ", ".join(f"{kind}×{n}" for kind, n in counts.items()) or "no changes"
    print(
        f"Rendered {len(events)} reportable event(s) to {output} "
        f"[{edition_content['type']}] ({summary})"
    )
    return 0


def _run_poll(
    state: dict[str, Any],
    flash_trigger: list[str],
    events: list[dict[str, Any]],
    coverage: dict[str, Any],
    now: datetime,
    output: str | Path,
    state_path: str | Path,
    change_set: list[dict[str, str]],
) -> int:
    """Hourly poll (N3 hourly branch): persist state; re-render only on a flash (N10)."""
    if flash_trigger:
        # Act on the flash seam Slice 2 only stored: mark it published (once per Red
        # spell — the gate clears the guard on a drop below Red) and re-render the
        # dashboard early with the flash banner, bypassing the edition + model steps.
        for eid in flash_trigger:
            state["events"][eid]["flash_published"] = True
        edition_content = edition_builder.build_flash_edition(
            state, flash_trigger, now=now, title=_TITLE
        )
        state_store.save(state, state_path)
        render(events, edition_content, coverage=coverage, output=output)
        print(f"FLASH re-render: {len(flash_trigger)} event(s) crossed into Red -> {output}")
        return 0

    # No flash: persist the reconciled state; the last published dashboard stands.
    state_store.save(state, state_path)
    counts = Counter(c["kind"] for c in change_set)
    summary = ", ".join(f"{kind}×{n}" for kind, n in counts.items()) or "no changes"
    print(f"Poll: state updated ({summary}); dashboard unchanged")
    return 0


def _write_assessment_input(
    path: str | Path,
    events: list[dict[str, Any]],
    edition_content: dict[str, Any],
    coverage: dict[str, Any] | None,
) -> None:
    """Write the {events, edition, coverage} payload the model step re-renders from."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"events": events, "edition": edition_content, "coverage": coverage}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assess(
    *,
    input_path: str | Path,
    output: str | Path,
    client: assessor.AssessClient | None = None,
) -> int:
    """Guarded model step (N14): phrase reportables via ``/sitrep`` and re-render.

    Reads the payload the edition run wrote, hands the reportables + changelog to
    the assessment seam (``client`` is injectable; production shells out to
    ``claude -p``), folds the prose onto the event cards + edition summary, and
    re-renders the dashboard in place. The model never sees a feed (SKILL.md).
    """
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    events = data["events"]
    edition_content = data["edition"]
    coverage = data.get("coverage")

    # Reportables are exactly the rendered events; the changelog is the edition's.
    prose = assessor.assess(events, edition_content.get("changelog"), client=client)
    if prose:
        assessments = prose["event_assessments"]
        for ev in events:
            if ev.get("id") in assessments:
                ev["assessment"] = assessments[ev["id"]]
        edition_content["summary"] = prose["edition_summary"]

    render(events, edition_content, coverage=coverage, output=output)
    print(f"Assessed {len(events)} reportable event(s); re-rendered {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hadr", description="HADR Monitor pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="fetch feeds, reconcile, and render the dashboard")
    source = run_p.add_mutually_exclusive_group()
    source.add_argument("--now", action="store_true", help="fetch live feeds (default)")
    source.add_argument("--fixture", metavar="DIR", help="read recorded fixtures from DIR")
    run_p.add_argument(
        "--mode",
        choices=(schedule.POLL, schedule.EDITION),
        default=schedule.EDITION,
        help="poll (hourly, flash-only re-render) or edition (full changelog build)",
    )
    run_p.add_argument("--output", default=DEFAULT_OUTPUT, help="dashboard output path")
    run_p.add_argument("--state", default=state_store.DEFAULT_PATH, help="path to state.json")
    run_p.add_argument(
        "--assessment-input",
        default=DEFAULT_ASSESSMENT_INPUT,
        help="where to write the reportables payload for the guarded model step",
    )

    assess_p = sub.add_parser("assess", help="guarded model step: phrase reportables, re-render")
    assess_p.add_argument(
        "--input", default=DEFAULT_ASSESSMENT_INPUT, help="reportables payload from `run`"
    )
    assess_p.add_argument("--output", default=DEFAULT_OUTPUT, help="dashboard output path")

    mode_p = sub.add_parser("mode", help="print the pipeline mode for a GitHub trigger (N3)")
    mode_p.add_argument("--event", required=True, help="github.event_name")
    mode_p.add_argument("--cron", default=None, help="github.event.schedule (for scheduled runs)")

    args = parser.parse_args(argv)
    if args.command == "run":
        return run(
            fixture=args.fixture,
            output=args.output,
            state_path=args.state,
            mode=args.mode,
            assessment_input=args.assessment_input,
        )
    if args.command == "assess":
        return assess(input_path=args.input, output=args.output)
    if args.command == "mode":
        print(schedule.run_mode(args.event, args.cron))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
