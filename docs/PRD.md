# PRD — HADR Monitor

Synthesised 8 Jul 2026 from REQS.md, CONTEXT.md, docs/adr/0001–0005, and the
grilling log in QUESTIONS.md. Vocabulary per CONTEXT.md.

## Problem Statement

People who need to stay aware of significant humanitarian disasters — where
they happened, how bad they are, who is affected — must either watch three
noisy, differently-shaped live feeds themselves (GDACS, USGS, ReliefWeb) or
rely on news coverage that is late, selective, and attention-driven. The raw
feeds double-report the same event under different identifiers, revise or
retract events after publication, and emit far more noise (daily Green
alerts, 5–10 low-impact quakes a day) than signal. There is no low-effort way
to get a trustworthy, once-a-day picture that stays honest when a feed is
down and quiet when the world is.

## Solution

An unattended monitoring agent that polls the three feeds hourly, reconciles
what it sees into canonical events with its own identifiers (deduplicated
across sources, tracking escalations, downgrades, revisions and
retractions), applies an impact-based reporting threshold, and publishes one
edition every morning at 08:30 Singapore time to a single self-contained
dashboard page. Quiet mornings still produce a one-line quiet edition —
rendered deterministically, with no model involvement — so a missing report
is unambiguous. A new Red-level event between editions triggers an intraday
flash alert on the same dashboard. Every edition states its data coverage:
a down or stale feed is reported as such, never allowed to read as a calm
world.

## User Stories

1. As a reader, I want one morning edition at 08:30 SGT summarising all
   reportable disaster events, so that I stay informed without watching raw
   feeds.
2. As a reader, I want each reported event to say what happened, where, how
   bad, and who is affected, so that I can judge its significance at a
   glance.
3. As a reader, I want the same physical earthquake reported once — not once
   per feed — so that I don't misread duplicates as separate disasters.
4. As a reader, I want events reported only when they clear an impact-based
   threshold (GDACS Orange/Red, PAGER yellow+, escalation, or ReliefWeb
   curation), so that the edition stays worth opening.
5. As a reader, I want a one-line quiet edition on mornings with nothing
   reportable, so that I can distinguish "calm world" from "broken pipeline".
6. As a reader, I want an Updates/changelog section listing escalations,
   downgrades, revisions and retractions of previously reported events, so
   that I'm never left believing stale claims.
7. As a reader, I want escalations of already-reported events surfaced
   prominently, so that a Green-turned-Red event isn't buried as a footnote.
8. As a reader, I want retractions stated explicitly ("previously reported
   M5.2 was deleted by USGS"), so that corrections are as visible as claims.
9. As a reader, I want a flash alert on the dashboard when any event crosses
   into Red level between editions — whether newly detected at Red or a
   tracked event escalating into Red — so that catastrophic events reach me
   within the hour they are detected, not the next morning.
10. As a reader, I want the dashboard to always show the current best-known
    state of tracked events, so that I'm never acting on superseded data.
11. As a reader, I want an explicit coverage warning when a feed is down or
    stale ("GDACS unreachable since 03:10 SGT"), so that I know what the
    edition could not see.
12. As a reader, I want each event to link to its source records (GDACS
    report page, USGS event page, ReliefWeb disaster page), so that I can
    drill into primary sources.
13. As a reader, I want events timestamped in Singapore time on the
    dashboard, so that I don't do timezone arithmetic at breakfast.
14. As a reader, I want the dashboard to be a single self-contained page,
    so that it loads anywhere, with no backend to be down.
15. As the operator, I want the agent to run unattended on a schedule, so
    that the edition appears without anyone remembering to trigger it.
16. As the operator, I want quiet editions and change detection to be fully
    deterministic (no model call), so that scheduled runs are cheap and
    the model never decides whether to wake up.
17. As the operator, I want all event state in a reviewable JSON file
    committed by the workflow, so that I can audit what the agent believed
    and when, in git history.
18. As the operator, I want every deviation from the PRD/ADRs logged in the
    implementation notes, so that undocumented drift is treated as a bug.
19. As the operator, I want each feed isolated behind its own fetch module,
    so that ReliefWeb RSS can be swapped for the API without touching the
    reconciler.
20. As the operator, I want polite hourly polling with backoff, so that we
    remain good citizens of SLA-free public feeds.
21. As the operator, I want per-feed staleness tracked independently, so
    that one dead feed doesn't silently degrade the whole product.
22. As a reviewer, I want deterministic logic covered by tests against
    recorded fixture payloads, so that I can confirm behaviour without live
    feeds.
23. As a reviewer, I want each vertical slice observable as done in under
    two minutes, so that review keeps pace with the three-day build.

## Implementation Decisions

- **Architecture: event-state reconciler, not a feed reader** (ADR-0001).
  Poll → snapshot → diff against persistent canonical-event state → derive
  reporting from the diff. Never alert directly off raw feed items.
- **Canonical events** carry our own IDs and every source alias (GDACS
  `eventid`, all USGS `ids` entries, GLIDE, ReliefWeb disaster ID). Join
  order: GLIDE → USGS IDs from GDACS per-event detail → heuristic (hazard
  type + origin time ±30 min + distance ≤250 km). GDACS keyed on `eventid`;
  a new `episodeid` is an update. The heuristic is the **last resort**, used
  only when no shared identifier links the records; it **never merges records
  that already carry distinct same-source identifiers** (two different USGS
  `ids`, two different GDACS `eventid`s are distinct events). This is what
  keeps an aftershock sequence separate: each significant aftershock has its
  own USGS id and its own GDACS event, so they join by ID, not by the
  proximity window they happen to share with the mainshock. When several
  candidates *do* fall in the heuristic window, the nearest in combined
  time-and-space wins; a genuinely ambiguous match **stays separate rather
  than merging** — a missed merge is recoverable and visible, a false merge
  hides a disaster.
- **Join corrections are first-class** (resolves issue #4): a join is a
  revisable belief, not a permanent fact. If later evidence shows a merge was
  wrong the canonical event is **split**; if a shared GLIDE or preferred-ID
  flip later links two separate events they are **merged**. Split and merge
  are part of the update policy alongside escalation, downgrade, revision and
  retraction, and each is surfaced in the edition changelog so a correction is
  as visible as the original claim (US6–US8).

- **Threshold** (ADR-0002): reportable = GDACS Orange/Red, or PAGER
  yellow/orange/red, or escalation of a tracked event, or a ReliefWeb
  disaster entry for an unreported event. GDACS alert level and PAGER level
  are kept as separate fields, never merged.
- **Cadence** (ADR-0003): hourly poll; daily edition at 08:30 SGT (00:30
  UTC cron); **any event crossing into Red since the last edition — newly
  detected at Red or a tracked event escalating into Red — triggers an
  intraday flash re-render** (resolves issue #5: escalation-to-Red is the very
  scenario the reconciler exists to catch, so it must flash, not wait for
  morning). A flash fires once per Red spell: the `flash_published` guard is
  set on the flash and cleared when the event drops below Red, so a
  downgrade-then-re-escalation flashes again while sustained Red does not
  re-flash every poll. Detection latency is bounded by the hourly poll and
  best-effort Actions cron — the flash reaches the reader within roughly an
  hour of detection (up to ~2 h from occurrence); the cadence stays hourly
  deliberately (polite to SLA-free feeds; Red impact estimates develop over
  hours anyway). Every morning publishes; quiet editions are template-only
  with no model call. The model is invoked only to assess and phrase
  reportable material.
- **Persistence** (ADR-0004): single schema-versioned JSON state file,
  committed by the workflow, never hand-edited.
- **Stack** (ADR-0005): Python 3.12+/uv/pytest/ruff, httpx; the dashboard
  is one self-contained HTML file (inline JS/CSS, event state embedded as
  JSON at render time); GitHub Actions cron for scheduling.
- **Feeds**: GDACS GeoJSON event list is primary for multi-hazard impact;
  USGS summary feeds (CDN-cached) for earthquake detection/enrichment,
  filtered to real earthquakes (`type`) and stored with `magType` and depth;
  ReliefWeb via public disasters RSS now (GLIDE extraction), API behind the
  same module interface once the appname is approved. ReliefWeb is
  confirmation/curation, never detection.
- **Timestamps** UTC everywhere internally (GDACS naive-UTC parsed
  explicitly; USGS epoch-ms converted); SGT only at render time.
- **Failure behaviour**: per-feed staleness tracked independently; fetch
  failures back off politely; a stale/down feed forces a coverage warning
  in the edition rather than silence.

## Testing Decisions

- Good tests assert external behaviour at the agreed seam, not internals.
- **Primary seam (the only load-bearing one):** a pure pipeline function —
  (feed snapshots, prior state, clock) → (new state, edition/flash
  decision + content data). All dedup, threshold, escalation, retraction,
  staleness and quiet-morning behaviour is tested here with recorded
  fixture payloads and a controlled clock.
- **Fetch modules** are tested against recorded fixture payloads (shape
  parsing, alias extraction, error/staleness signalling) — no live-feed
  tests in CI.
- **Renderer** is tested by asserting on the state JSON embedded in the
  produced dashboard HTML, not on markup details.
- Prior art: none — this repo starts empty; these tests set the pattern.
- Scenario fixtures to cover at minimum: same quake from three feeds
  (dedup), Green→Red escalation, magnitude revision, USGS deletion
  (retraction), preferred-ID flip within `ids`, quiet morning, one feed
  stale, ReliefWeb entry arriving days late for an already-reported event,
  a tracked Orange event escalating to Red between editions (asserts a flash
  re-render is emitted, and that a downgrade-then-re-escalation flashes again
  while sustained Red does not), a mainshock plus an M5+ aftershock inside the
  ±30 min / ≤250 km window each carrying its own USGS id (asserts they remain
  distinct canonical events), and a wrong heuristic merge later split apart
  (asserts the split produces a changelog entry).

## Out of Scope

- Hazards without a source in the stack: conflict, displacement, epidemics,
  tsunami warnings, landslides, heatwaves. Slow-onset anomaly logic beyond
  what GDACS itself raises (drought is in only as GDACS events).
- Feeds beyond GDACS, USGS, ReliefWeb.
- Notification channels beyond the dashboard (no email/Slack/RSS out).
- Intraday alerting below Red level.
- Historical backfill/archive queries; the store tracks the active window,
  not a research archive.
- Region-specific weighting (global scope; severity does the filtering).
- Document-volume-based severity signals (attention bias).

## Further Notes

- Human task, immediately: request the ReliefWeb API appname (approval
  latency is days; RSS is the interim).
- GitHub Actions cron is best-effort; the 08:30 edition may land minutes
  late. Accepted (ADR-0005).
- The starter README's "no change → no report" principle was deliberately
  revised to always-publish (ADR-0003); the README is the starter's voice,
  not this product's spec.
- Not published to an issue tracker: no tracker/triage vocabulary is
  configured for this repo; this file is the canonical PRD location per the
  planning process. `prd.html` (an expected end-of-week artefact) should be
  rendered from this document later.
