---
shaping: true
---

# HADR Monitor — Shaping

Frame: see `FRAME.md`. Vocabulary per `CONTEXT.md`; decisions per
`docs/adr/`. Requirements distilled from `docs/PRD.md`.

## Requirements (R)

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A reader gets one edition every morning at 08:30 SGT summarising reportable events — what happened, where, how bad, who is affected — produced unattended | Core goal |
| R1 | One real-world event is reported once: source records from GDACS/USGS/ReliefWeb referring to the same occurrence merge into one canonical event | Must-have |
| R2 | Only reportable material is reported: GDACS Orange/Red, PAGER yellow+, escalation of a tracked event, or a ReliefWeb disaster entry for an unreported event | Must-have |
| R3 | Changes to already-reported events (escalation, downgrade, revision, retraction) surface in the edition's changelog, and the dashboard always shows current best-known state | Must-have |
| R4 | Quiet mornings still publish: a one-line quiet edition rendered deterministically; the model is never invoked without reportable material and never decides whether to wake up | Must-have |
| R5 | A new Red-level event between editions reaches the dashboard as a flash alert within about an hour | Must-have |
| R6 | A down or stale feed produces an explicit coverage warning; missing data never reads as a calm world | Must-have |
| R7 | Polling is polite (hourly, with backoff) and the pipeline survives feed outages, rate limits, and ReliefWeb's pending appname (RSS interim) | Must-have |
| R8 | The system is reviewable and operable: event state in a committed schema-versioned JSON file, deterministic logic in tested `scripts/`, one self-contained SPA dashboard, scheduled via GitHub Actions | Must-have |

9 top-level requirements — at the chunking cap; new requirements must merge
or displace.

---

## A: Publish-time daily batch

One scheduled run per day does everything: fetch, reconcile, threshold,
render, commit. No state is touched between editions.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| A1 | Daily GitHub Actions run at 00:15 UTC: fetch all three feeds (GDACS GeoJSON, USGS `all_day` summary, ReliefWeb disasters RSS) into snapshot JSON | |
| A2 | 🟡 Reconciler: diff snapshots against `data/state.json` canonical events; alias matching GLIDE → GDACS detail `properties.sourceid` (one cached call per new/changed EQ, verified in SPIKE-1) → heuristic (type + time ±30 min + ≤250 km); emits change set (new/escalation/downgrade/revision/retraction) | |
| A3 | Threshold gate: pure function change set → reportable set per ADR-0002 | |
| A4 | Edition builder: empty reportable set → template quiet edition; else headless model call phrases assessments; renders SPA `dashboard.html` with embedded state JSON | |
| A5 | Staleness check at fetch time: failed/stale feed → coverage warning block in edition | |
| A6 | Workflow commits `data/state.json` + `dashboard.html` | |

**Character:** minimum moving parts — one cron, one run, one commit per day.

## B: Hourly reconciler with gated assessor

An hourly deterministic loop maintains event state continuously; the 08:30
edition and intraday flash alerts are two consumers of the same
always-fresh state.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| B1 | Fetchers: one module per feed behind a common interface `snapshot() → (source records, fetch metadata)`; ReliefWeb RSS now, API later behind same interface; recorded fixtures for tests | |
| B2 | 🟡 Reconciler: canonical events in `data/state.json` (own IDs, all aliases); matching GLIDE → GDACS detail `properties.sourceid` matched into the USGS `ids` alias set (one cached detail call per new/changed EQ; verified live in SPIKE-1) → heuristic (type + time ±30 min + ≤250 km); GDACS keyed on `eventid`, episodes are updates; USGS alias-set matching survives preferred-ID flips; emits change set | |
| B3 | Threshold gate: pure function change set → reportable set per ADR-0002; also computes "new Red?" flash trigger | |
| B4 | Hourly workflow: fetch → reconcile → gate → commit state; if new Red → render flash (dashboard re-render with flash banner) in the same run | |
| B5 | Edition run at 00:30 UTC: builds changelog from state (changes since last edition marker), quiet edition from template when nothing reportable, else headless model call (`claude -p`) phrases assessments; renders SPA `dashboard.html`, sets new edition marker | |
| B6 | Staleness monitor: per-feed last-success + feed self-timestamps kept in state; stale feed → coverage warning injected into every edition/flash | |
| B7 | Actions plumbing: hourly cron + 00:30 UTC cron in one workflow file; `concurrency` group serialises runs; bot commits state + dashboard | |

**Character:** state is always current; edition and flash are cheap reads
of it. The model sits behind a deterministic gate.

## C: Scheduled agent session

A headless agent session each morning (and hourly for Red-watch) reads the
feeds with tools, compares against its notes, and writes the report —
judgment in the loop, minimal fixed pipeline.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| C1 | Scheduled headless agent run with `goal.md` as standing objective; tools to fetch the three feeds | |
| C2 | Agent compares fetched records against `data/state.json` notes it maintains; judges identity, severity, and changes itself | ⚠ |
| C3 | Agent writes/commits `dashboard.html` and updated state notes | |
| C4 | Hourly slim agent run watching only for new Reds | ⚠ |

**Character:** maximum flexibility, minimum code — the model *is* the
pipeline.

---

## Fit Check v1

| Req | Requirement | Status | A | B | C |
|-----|-------------|--------|---|---|---|
| R0 | A reader gets one edition every morning at 08:30 SGT summarising reportable events — what happened, where, how bad, who is affected — produced unattended | Core goal | ✅ | ✅ | ✅ |
| R1 | One real-world event is reported once: source records from GDACS/USGS/ReliefWeb referring to the same occurrence merge into one canonical event | Must-have | ❌ | ❌ | ❌ |
| R2 | Only reportable material is reported: GDACS Orange/Red, PAGER yellow+, escalation of a tracked event, or a ReliefWeb disaster entry for an unreported event | Must-have | ✅ | ✅ | ❌ |
| R3 | Changes to already-reported events (escalation, downgrade, revision, retraction) surface in the edition's changelog, and the dashboard always shows current best-known state | Must-have | ✅ | ✅ | ❌ |
| R4 | Quiet mornings still publish: a one-line quiet edition rendered deterministically; the model is never invoked without reportable material and never decides whether to wake up | Must-have | ✅ | ✅ | ❌ |
| R5 | A new Red-level event between editions reaches the dashboard as a flash alert within about an hour | Must-have | ❌ | ✅ | ✅ |
| R6 | A down or stale feed produces an explicit coverage warning; missing data never reads as a calm world | Must-have | ❌ | ✅ | ❌ |
| R7 | Polling is polite (hourly, with backoff) and the pipeline survives feed outages, rate limits, and ReliefWeb's pending appname (RSS interim) | Must-have | ✅ | ✅ | ❌ |
| R8 | The system is reviewable and operable: event state in a committed schema-versioned JSON file, deterministic logic in tested `scripts/`, one self-contained SPA dashboard, scheduled via GitHub Actions | Must-have | ✅ | ✅ | ❌ |

**Notes:**

- **All shapes fail R1 (flagged unknown):** every shape's dedup depends on
  extracting USGS/NEIC identifiers from the GDACS per-event detail
  endpoint, whose payload shape we have never seen (A2/B2/C2 ⚠). A flag is
  a ❌ until spiked — we've described *what*, not verified *how*.
- **A fails R5:** one daily run cannot flash within an hour of a Red event
  — structural, not fixable without becoming B.
- **A fails R6:** with no state between daily runs, "stale since when"
  cannot be computed from a single morning's failed fetch; a GDACS rolling-
  window gap after an outage is invisible.
- **C fails R2/R3 (⚠→❌):** identity, thresholds and change detection are
  model judgments, not mechanisms — no concrete *how* exists to trace.
- **C fails R4:** the agent deciding "is anything reportable?" is exactly
  the model deciding whether to wake up; quiet editions would cost a model
  run daily.
- **C fails R6/R7/R8:** staleness bookkeeping, polite backoff and
  deterministic tested logic are unspecified in an agent-judgment loop;
  hourly agent runs also multiply cost for nothing on quiet hours.

**Reading:** B fails only on the shared flagged unknown (GDACS detail
payload). Resolve with a spike, then re-check.

---

## Fit Check v2

After `SPIKE-1-gdacs-detail-ids.md` (live verification, 8 Jul 2026): the
GDACS detail endpoint's `properties.sourceid` is a verbatim USGS alias
(`us6000taui` confirmed in both feeds for the same quake). A2/B2 flags
resolved; C2 remains flagged (identity is still model judgment there).

| Req | Requirement | Status | A | B | C |
|-----|-------------|--------|---|---|---|
| R0 | A reader gets one edition every morning at 08:30 SGT summarising reportable events — what happened, where, how bad, who is affected — produced unattended | Core goal | ✅ | ✅ | ✅ |
| R1 | One real-world event is reported once: source records from GDACS/USGS/ReliefWeb referring to the same occurrence merge into one canonical event | Must-have | 🟡 ✅ | 🟡 ✅ | ❌ |
| R2 | Only reportable material is reported: GDACS Orange/Red, PAGER yellow+, escalation of a tracked event, or a ReliefWeb disaster entry for an unreported event | Must-have | ✅ | ✅ | ❌ |
| R3 | Changes to already-reported events (escalation, downgrade, revision, retraction) surface in the edition's changelog, and the dashboard always shows current best-known state | Must-have | ✅ | ✅ | ❌ |
| R4 | Quiet mornings still publish: a one-line quiet edition rendered deterministically; the model is never invoked without reportable material and never decides whether to wake up | Must-have | ✅ | ✅ | ❌ |
| R5 | A new Red-level event between editions reaches the dashboard as a flash alert within about an hour | Must-have | ❌ | ✅ | ✅ |
| R6 | A down or stale feed produces an explicit coverage warning; missing data never reads as a calm world | Must-have | ❌ | ✅ | ❌ |
| R7 | Polling is polite (hourly, with backoff) and the pipeline survives feed outages, rate limits, and ReliefWeb's pending appname (RSS interim) | Must-have | ✅ | ✅ | ❌ |
| R8 | The system is reviewable and operable: event state in a committed schema-versioned JSON file, deterministic logic in tested `scripts/`, one self-contained SPA dashboard, scheduled via GitHub Actions | Must-have | ✅ | ✅ | ❌ |

**Notes:**

- A still fails R5 (structural: daily-only) and R6 (no inter-run state to
  compute staleness from).
- C unchanged: judgments, not mechanisms.
- **B passes 9/9.**

---

## Selected: B (8 Jul 2026)

## Detail B: Concrete components

No remaining ⚠ flags. The one unknown (GDACS→USGS join) was resolved by
`SPIKE-1-gdacs-detail-ids.md`. The workflow gate shape matches the
scaffold's `.github/workflows/sitrep.yml.disabled` contract: deterministic
check first, model call only behind it.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | **Fetchers** (one module per feed, common interface `snapshot() → FeedSnapshot{records, fetched_at, ok, feed_generated_at}`; recorded fixtures for tests) | |
| B1.1 | GDACS: GET `geteventlist/EVENTS4APP` → source records (eventid, episodeid, eventtype, alertlevel/alertscore + episode variants, glide, coords, fromdate/todate/datemodified parsed as naive-UTC, country, severitydata) | |
| B1.2 | USGS: GET `all_day.geojson` → filter `properties.type == "earthquake"` → records (preferred id + every `ids` alias, mag, magType, depth from coord[2], PAGER `alert`, `status`, `sig`, epoch-ms times → UTC) | |
| B1.3 | ReliefWeb: GET disasters RSS → records (title, link, GLIDE parsed from description `tag glide` div, pubDate, country); API client drops in behind the same interface when appname approved | |
| **B2** | **Reconciler** (canonical events, dedup, change detection) | |
| B2.1 | `data/state.json` schema v1: `{version, events: {canonical_id → aliases[], hazard, gdacs_alert, pager_alert, magnitude, location, origin_time, first_seen, last_changed, reported, flash_published, source_refs}}, feed_status, edition_marker` | |
| B2.2 | Alias join, in order: shared GLIDE → GDACS EQ detail `properties.sourceid` matched into USGS alias set (one cached `geteventdata` call per new/changed GDACS EQ; SPIKE-1) → heuristic (same hazard, origin time ±30 min, haversine ≤250 km) | |
| B2.3 | Diff snapshot vs state → ChangeSet: `new`, `escalation`, `downgrade`, `revision` (magnitude/location beyond noise thresholds), `retraction`; GDACS new `episodeid` = update to same event; USGS preferred-ID flips absorbed by alias-set matching | |
| B2.4 | Retraction guard: absence from a rolling window is NOT deletion (windows scroll). Retract only on USGS `status: "deleted"` or an explicit source invalidation; otherwise mark `aged_out` and keep | |
| **B3** | **Threshold gate** (pure function, no I/O) | |
| B3.1 | `gate(change_set, state) → (reportables, flash_trigger)` per ADR-0002: GDACS Orange/Red ∨ PAGER yellow+ ∨ escalation of tracked ∨ ReliefWeb entry for unreported event | |
| B3.2 | `flash_trigger` = event newly at Red (GDACS or PAGER) with `flash_published == false` | |
| **B4** | **Hourly run** (deterministic, no model) | |
| B4.1 | Steps: fetch all three → reconcile → gate → write state → commit; on `flash_trigger`: re-render dashboard with flash banner + set `flash_published`, same run | |
| **B5** | **Edition run** (00:30 UTC = 08:30 SGT) | |
| B5.1 | Changelog = accumulated changes since `edition_marker`; nothing reportable and no changes → render quiet edition from template (no model call), advance marker | |
| B5.2 | Else: headless `claude -p` runs the `/sitrep` skill with the reportable/changed events as JSON input → returns per-event assessment prose (what/where/how bad/who affected) + edition summary; deterministic renderer composes final page | |
| B5.3 | Renderer: single self-contained `dashboard.html` (inline JS/CSS SPA; full event state + edition content embedded as JSON; SGT timestamps at render; source links per event; changelog + coverage sections) | |
| **B6** | **Staleness monitor** | |
| B6.1 | `feed_status` in state: per feed, last successful fetch, last `feed_generated_at`, consecutive failures; stale = no fresh success within 2× poll cadence | |
| B6.2 | Any stale/down feed → coverage warning block injected into every edition and flash render ("GDACS unreachable since 03:10 SGT; EQ coverage via USGS only") | |
| **B7** | **Actions plumbing** | |
| B7.1 | One workflow (`sitrep.yml`, enabling the scaffold's disabled shell): `schedule: cron "0 * * * *"` (hourly) + `cron "30 0 * * *"` (edition) + `workflow_dispatch`; job branches on which trigger fired | |
| B7.2 | `concurrency: group hadr-pipeline, cancel-in-progress: false` serialises hourly/edition/flash runs against the committed state | |
| B7.3 | Bot commit of `data/state.json` + `dashboard.html` with `[skip ci]`; `ANTHROPIC_API_KEY` secret exposed only to the guarded model step (never the fetch/reconcile steps) | |
| B7.4 | Backoff: fetch failures retried within-run (3 attempts, exponential); persistent failure just records `feed_status` — the next hourly run is the retry | |
