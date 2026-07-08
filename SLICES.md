---
shaping: true
---

# HADR Monitor — Slices (Shape B)

Vertical implementation slices for the breadboarded Shape B. Ground truth
for slice scope and order; affordance IDs (U/N/S) reference `BREADBOARD.md`,
mechanism IDs (B1–B7) reference `SHAPING.md`. Each slice ends in something
observable — a rendered `dashboard.html` or a committed artifact a reviewer
can confirm in under two minutes (Operating Principle: thin, verifiable
slices).

## Slicing principle for a pipeline product

This product's "demo-able UI" is the published dashboard. The renderer
(N15 + N21) is therefore built in **V1** so every later slice can prove
itself by changing what appears on the page. Slices layer capability from
the outside in: first a page from one feed, then state, then dedup, then
the reporting decision, then editions, then the model, then resilience,
then unattended scheduling.

## Slice summary

| # | Slice | Mechanisms | Key affordances | Demo |
|---|-------|-----------|-----------------|------|
| V1 | Page from one feed | B1 (USGS), B5-render | N5, N15, S4, N21, U1/U2/U5/U6/U7 | `python -m hadr run` fetches USGS and writes `dashboard.html`; open it → today's earthquakes as cards with source links |
| V2 | Canonical events + persistent state | B2 (single-source), S1 | N7, S1, U (unchanged) | Run twice; `data/state.json` persists events; a revised USGS magnitude updates the same card instead of adding a second |
| V3 | Three feeds + cross-source dedup | B1 (GDACS+RW), B2 (join) | N4, N6, N8, N7 (join) | The same quake from USGS **and** GDACS renders as one card carrying both source links (GLIDE→sourceid→heuristic) |
| V4 | Impact threshold | B3 | N9, U8 filter | A Green M4.6 is tracked in state but absent from the board; an Orange event appears. Hazard filter chips work |
| V5 | Editions + changelog | B5 (edition logic), S3 | N12, N13, S3, U1/U3/U4, U9/U10/U11 | Escalate an event between runs → it appears prominently in the changelog; a run with nothing reportable renders the one-line quiet edition |
| V6 | Model assessment + `/sitrep` skill | B5 (model step) | N14, `skills/sitrep/` | Reportable events carry model-written what/where/how-bad/who prose; quiet editions still make **no** model call |
| V7 | Coverage + staleness | B6, S2 | N11, S2, U12, U13 | Point a fetcher at a dead URL → dashboard shows "GDACS unreachable since HH:MM SGT; EQ coverage via USGS only" |
| V8 | Unattended scheduling + flash | B4, B7 | N1, N2, N3, N10, N16, S5 | Enable `sitrep.yml`; hourly + 08:30 SGT runs commit state and dashboard unattended; a new Red event triggers an off-cycle flash re-render |

Eight slices (≤9 cap). V1–V7 are runnable locally via a `run` entrypoint
with `--now`/`--fixture` flags; V8 wraps that entrypoint in the scheduled
workflow — no new pipeline logic, only orchestration.

---

## V1 — Page from one feed

**Mechanism:** B1 (USGS fetcher only) + the renderer half of B5.
**Goal:** stand up the end-to-end skeleton fetch → render → file, provably.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N5 | scripts/fetch_usgs.py | `snapshot()` — GET `all_day.geojson`, filter `type=="earthquake"`, epoch-ms→UTC, keep all `ids` aliases + magType + depth | call | — | → N15 |
| N15 | scripts/render.py | `render(events, edition_content)` — write self-contained SPA with embedded JSON island | call | → S4 | — |
| S4 | dashboard.html | embedded JSON payload | write | — | → N21 |
| N21 | dashboard inline `<script>` | bootstrap: parse island, render cards, times→SGT | call | — | → U1,U2,U5,U6,U7 |
| U1 | header | edition title + date (SGT) | render | — | — |
| U2 | header | "as of" timestamp | render | — | — |
| U5 | events-board | event cards list | render | → U6 | — |
| U6 | event-card | card: title, magnitude, place, origin time (SGT) | render | → U7 | — |
| U7 | event-card | USGS source link | click | → P4 | — |

**Out of scope this slice:** state persistence, other feeds, dedup,
threshold (everything USGS returns is shown), changelog, model, coverage.
**Demo:** `uv run python -m hadr run --now` → open `dashboard.html` → a card
per earthquake in the USGS day window, each linking to its USGS page.
**Tests:** `fetch_usgs` parses a recorded fixture (aliases, magType, depth,
epoch conversion); `render` embeds the expected events JSON.

## V2 — Canonical events + persistent state

**Mechanism:** B2 restricted to a single source (identity, revision,
retraction within USGS) + store S1.
**Goal:** stop treating each poll as fresh; events live across runs.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N7 | scripts/reconcile.py | `reconcile(snapshot, state)` — match by USGS alias set (survives preferred-ID flip), detect `new`/`revision`/`retraction` (`status:"deleted"` only), aged-out guard | call | → S1 | → N15 |
| S1 | data/state.json › events | canonical events: own id, aliases[], magnitude, location, origin_time, first_seen, last_changed, source_refs | write | — | → N7, N15 |

**Out of scope:** cross-source join (single feed still), threshold, editions.
**Demo:** run against fixture A, then fixture A′ where one quake's magnitude
was revised and one was deleted — `state.json` shows the first updated in
place (same canonical id) and the second marked retracted, not duplicated.
**Tests:** alias-set match across a preferred-ID flip; revision vs new;
`deleted` → retraction; rolling-window absence → aged-out, not retracted.

## V3 — Three feeds + cross-source dedup

**Mechanism:** B1 (GDACS + ReliefWeb fetchers) + B2 join order.
**Goal:** one real-world event, one card, regardless of how many feeds saw it.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N4 | scripts/fetch_gdacs.py | `snapshot()` — GET `EVENTS4APP`; event-level + episode alert fields; glide; key on `eventid`, new `episodeid` = update | call | — | → N7 |
| N8 | scripts/fetch_gdacs.py | `event_detail(eventid)` — GET `geteventdata`, extract `properties.sourceid`; cached per new/changed EQ (SPIKE-1) | call | — | → N7 |
| N6 | scripts/fetch_reliefweb.py | `snapshot()` — GET disasters RSS, parse GLIDE from description; API client behind same interface when appname approved | call | — | → N7 |
| N7 | scripts/reconcile.py | join order: shared GLIDE → GDACS `sourceid` ∈ USGS alias set → heuristic (same hazard, origin ±30 min, ≤250 km haversine) | call | → S1 | → N15 |

**Out of scope:** threshold, editions, model.
**Demo:** fixtures where one M6 quake appears in USGS and GDACS (and a late
ReliefWeb entry) → a single card with GDACS colour chip, magnitude, and all
three source links.
**Tests:** each join path in isolation (GLIDE match; sourceid match;
heuristic when both absent); episode fold; GDACS-ingests-USGS no-double.

## V4 — Impact threshold

**Mechanism:** B3 (pure gate) + hazard filter UI.
**Goal:** show only what clears the bar; track the rest silently.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N9 | scripts/gate.py | `gate(change_set, state) → (reportables, flash_trigger)` per ADR-0002: GDACS Orange/Red ∨ PAGER yellow+ ∨ escalation ∨ ReliefWeb-for-unreported; `flash_trigger` = newly Red & not yet flashed | call | — | → N15 |
| U8 | events-board | hazard-type filter chips (EQ/TC/FL/VO/DR/WF) | click | → N20 | — |
| N20 | dashboard inline `<script>` | `applyFilter(hazard)` — toggle card visibility | call | — | → U5 |

**Out of scope:** editions/changelog wording, model prose, flash publish
(trigger is computed and stored, not yet acted on — wire to future V8).
**Demo:** fixture with a Green M4.6 and an Orange flood → only the flood
card shows; the Green is present in `state.json` with `reported:false`.
Filter chips hide/show by hazard.
**Tests:** each threshold arm true/false; escalation of a tracked event is
reportable; `flash_trigger` set exactly when an event first reaches Red.

## V5 — Editions + changelog

**Mechanism:** B5 edition logic + marker S3.
**Goal:** a dated edition each run, and an honest record of what changed.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N12 | scripts/edition.py | `build_edition(state, marker)` — changelog since S3, regular vs quiet decision, advance marker | call | → N13, → S3 | → N15 |
| N13 | scripts/edition.py | quiet edition template (deterministic, no model) | call | — | → N15 |
| S3 | data/state.json › edition_marker | watermark of changes already told to the reader | write | — | → N12 |
| U1 | header | edition type badge (regular / quiet / flash) | render | — | — |
| U3 | header | flash banner (dormant until V8) | render | — | — |
| U4 | header | quiet edition line | render | — | — |
| U9 | changelog | escalation entries (prominent) | render | — | — |
| U10 | changelog | downgrade / revision one-liners | render | — | — |
| U11 | changelog | retraction notices | render | — | — |

**Out of scope:** model prose (V6), flash publish (V8).
**Demo:** run, escalate a tracked event's alert, run again → the escalation
leads the changelog; a run with an empty reportable set and no changes
renders the one-line quiet edition.
**Tests:** changelog contains only post-marker changes; escalations sort
above downgrades; quiet path chosen iff no reportables and no changes;
marker advances monotonically.

## V6 — Model assessment + `/sitrep` skill

**Mechanism:** B5 model step (the guarded `claude -p` call) + the `/sitrep`
skill (an expected end-of-week artifact).
**Goal:** human-readable assessment for reportable events — and only then.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N14 | sitrep.yml / entrypoint | guarded model step: `claude -p` runs `/sitrep` on reportables JSON → per-event assessment prose + edition summary | call | — | → N15 |
| — | skills/sitrep/SKILL.md | `/sitrep`: input = reportables+changelog JSON; output = assessment prose per event + one-paragraph edition summary; no tool access to feeds (data is passed in) | — | — | — |
| U6 | event-card | assessment prose (what/where/how bad/who affected) | render | — | — |

**Out of scope:** scheduling.
**Demo:** run with reportable events → cards carry model-written
assessments and the edition has a summary paragraph; run a quiet morning →
confirm (log/trace) the model step was **skipped** entirely.
**Tests:** gate result decides invocation (asserted on a stubbed model
client — no live model in CI); `/sitrep` output schema validated; renderer
places prose without breaking the JSON island.

## V7 — Coverage + staleness

**Mechanism:** B6 + store S2.
**Goal:** a down or stale feed is stated, never silent.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N11 | scripts/staleness.py | `coverage(feed_status)` — stale = no fresh success within 2× cadence | call | — | → N15 |
| S2 | data/state.json › feed_status | per feed: last success, last `feed_generated_at`, consecutive failures | write | — | → N11 |
| U12 | coverage | per-feed status rows | render | — | — |
| U13 | coverage | coverage warning banner | render | — | — |

Also this slice: fetchers record success/failure into S2 and retry with
backoff within a run (B7.4).
**Out of scope:** scheduling.
**Demo:** point the GDACS fetcher at an unreachable URL → the run still
publishes, with a coverage banner naming the feed and the time since last
success; earthquake coverage falls back to USGS.
**Tests:** stale computed per feed independently; a failed fetch never
empties existing events (staleness ≠ retraction); banner text includes feed
name and last-success time.

## V8 — Unattended scheduling + flash

**Mechanism:** B4 (hourly run + flash publish) + B7 (Actions plumbing),
enabling the scaffold's `.github/workflows/sitrep.yml.disabled`.
**Goal:** it runs itself, and Red events don't wait for morning.

| # | Component | Affordance | Control | Wires Out | Returns To |
|---|-----------|------------|---------|-----------|------------|
| N1 | sitrep.yml | hourly cron `0 * * * *` | trigger | → N3 | — |
| N2 | sitrep.yml | edition cron `30 0 * * *` (08:30 SGT) + `workflow_dispatch` | trigger | → N3 | — |
| N3 | sitrep.yml | trigger branch: fetch+reconcile+gate always; edition build only on edition/dispatch | conditional | → fetch/reconcile/gate, → N12 | — |
| N10 | sitrep.yml | flash branch: `flash_trigger` on an hourly run → render with flash banner, set `flash_published` | conditional | → N15, → S1 | — |
| N16 | sitrep.yml | commit `data/state.json` + `dashboard.html` `[skip ci]`; `ANTHROPIC_API_KEY` exposed only to N14 | call | → S5 | — |
| S5 | git repository | committed state + dashboard; history = audit log | write | — | — |

Also: `concurrency` group serialises runs (B7.2); rename
`sitrep.yml.disabled` → `sitrep.yml`; `goal.md` (agent's standing
objective, expected artifact) committed.
**Demo:** trigger via `workflow_dispatch` → Action fetches, reconciles,
renders, and commits with no local involvement; feed a fixture with a new
Red event on an hourly run → an off-cycle flash commit re-renders the
dashboard with the banner (U3) before the next 08:30 edition folds it into
the changelog.
**Tests:** trigger routing (hourly vs edition vs dispatch); flash fires once
per event (`flash_published` guard); the model secret is unreferenced in
fetch/reconcile steps.

---

## Wires to future slices (expected stubs)

- V4 computes `flash_trigger` but nothing consumes it until **V8**.
- V5 renders the flash banner U3, dormant until **V8** sets a flash edition.
- V3's ReliefWeb fetcher uses RSS; the API path drops in behind the same
  interface once the appname is approved (no slice; a swap inside N6).

## Not slices (separate doc-rendering artifacts)

`prd.html` and `system-view.html` are expected end-of-week deliverables but
are renderings of `docs/PRD.md` and `BREADBOARD.md`, not pipeline
increments. Produce them once the pipeline stabilises (≈ after V6).
