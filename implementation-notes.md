# Implementation notes

Kept by the agent, reviewed by you. One entry per working block.

## Decisions

### 2026-07-08 — Planning block (build-plan-product process)

- Ran the full product-planning process: grilling → PRD → shaping →
  breadboarding → consistency pass. Outputs: `REQS.md`, `QUESTIONS.md`,
  `CONTEXT.md`, `docs/adr/0001–0005`, `docs/PRD.md`, `FRAME.md`,
  `SHAPING.md`, `SPIKE-1-gdacs-detail-ids.md`, `BREADBOARD.md`; `CLAUDE.md`
  filled in.
- Shape **B** (hourly reconciler with gated assessor) selected — the only
  shape passing all 9 requirements (Fit Check v2 in `SHAPING.md`).
- SPIKE-1 verified live (8 Jul 2026): GDACS EQ detail `properties.sourceid`
  is a verbatim USGS alias (`us6000taui` found in both feeds for the same
  M5.0 China quake); the list payload carries the key but empty — one
  cached detail call per new/changed GDACS earthquake is required.

### 2026-07-08 — Slicing block

- Sliced Shape B into 8 vertical slices V1–V8 in `SLICES.md`. Renderer is
  built in V1 so every later slice demos by changing the published page.
  Order: page-from-one-feed → state → 3-feed dedup → threshold → editions
  → model assessment → coverage → unattended scheduling+flash.
- `build-plan-specs` skill is not publicly installable (its source repo
  needs auth); slicing was done directly from the breadboarding skill's
  slicing methodology, which is its substance.

### 2026-07-08 — Resolved PRD challenges (GitHub issues #4, #5)

- **#5 flash trigger.** Redefined the intraday flash from "new Red event" to
  "any event crossing into Red since the last edition — newly detected *or* a
  tracked event escalating into Red." Escalation-to-Red is the scenario the
  reconciler (ADR-0001) exists to catch, so deferring it to 08:30 was a bug.
  `flash_published` now means "fired this Red spell" and clears when the event
  drops below Red, so re-escalation flashes again but sustained Red does not
  re-flash each poll. Hourly cadence kept (defended, ADR-0003); US9's "same
  hour" wording corrected to "within the hour of detection" (~2 h from
  occurrence). Updated: `docs/PRD.md` (US9, Cadence, Testing), ADR-0003,
  `SLICES.md` (V4/V8), `prd.html`.
- **#4 dedup.** Headline aftershock false-merge is prevented by the existing
  tiered join (distinct shocks carry distinct USGS ids → join at tier 2, never
  reaching the heuristic) — defended, not re-architected. Added the explicit
  safeguards the spec lacked: the heuristic is last-resort, never merges
  records with distinct same-source IDs, breaks in-window ties by
  nearest-in-time-space, and leaves ambiguous matches separate. Made join
  corrections first-class: split (wrong merge) and merge (later-found link)
  join escalation/downgrade/revision/retraction in the update policy and the
  changelog. Updated: `docs/PRD.md` (Canonical events, Testing), ADR-0001,
  `SLICES.md` (V3).

### 2026-07-08 — Slice 1 build (issue #6, branch `feat/slice-1-skeleton`)

Built the headline Slice 1 (detailed slices V1–V3) as three staged commits:
page-from-USGS + renderer → canonical state + reconcile → GDACS + cross-source
dedup. All 24 tests, `ruff check`, and `ruff format --check` pass.

Deviations / decisions worth recording:

- **Physical layout — `scripts/` is an importable package imported by `hadr/`.**
  CLAUDE.md and the breadboard name modules as `scripts/fetch_usgs.py` etc. and
  the CLI as `python -m hadr`. Resolved by making `scripts/` a package (pure
  deterministic logic) that `hadr/__main__.py` orchestrates. `pyproject.toml`
  declares both packages. No departure from intent, just a layout the docs
  left implicit.
- **Feed scope: USGS + GDACS only; ReliefWeb deferred.** Issue #6's DoD names
  only USGS and GDACS and its one-card demo is USGS+GDACS, but the "composed of
  V1–V3" reference includes ReliefWeb. Scoped to the DoD (confirmed with the
  maintainer). The GLIDE join path is built and unit-tested; ReliefWeb's fetcher
  (N6) lands in a follow-up behind the same `snapshot()` interface — no
  reconciler change needed.
- **GDACS fetcher returns all hazards, not just EQ.** Matches B1.1 and the
  feed's real content; non-EQ events render as their own cards (V1–V3 shows
  everything the feeds return — the impact threshold is V4). Earthquakes are the
  only cross-source dedup case in this slice because USGS is EQ-only.
- **USGS is the descriptive owner for merged earthquakes.** On a merge, USGS
  magnitude/location/title win and GDACS contributes only its alert level; a
  GDACS record never overwrites USGS data (its EQ magnitude is often absent).
  PAGER and GDACS alerts are stored in separate fields, never merged (ADR-0002).
- **`data/state.json` is a runtime artifact, not committed on this branch.** The
  scheduled workflow (V8) commits state + dashboard; committing a
  fixture-derived state now would just be churn the workflow overwrites. The
  committed `dashboard.html` is rendered from the scenario-A fixtures as the
  reviewer's demo surface.

### 2026-07-09 — Slice 2 build (issue #7, branch `feat/slice-2-decision`)

Built Slice 2 (detailed slices V4 + V5): the impact threshold and the
editions/changelog. Two staged commits (`feat(v4)`, `feat(v5)`) plus docs. All
56 tests, `ruff check`, and `ruff format --check` pass.

- **V4 — `scripts/gate.py` (N9).** Pure `gate(change_set, state, prior)` per
  ADR-0002. Reportable when any arm holds: GDACS Orange/Red, PAGER yellow+, an
  already-tracked event escalated (level rose vs `prior`), or a ReliefWeb entry
  for an unreported event. Both alert models are mapped onto one ordinal
  (Green 0 / Yellow 1 / Orange 2 / Red 3) taking the worse of the two; the two
  fields stay separate in state. `flash_trigger` = active event at Red now with
  prior level below Red (covers "newly detected at Red" and "escalating into
  Red" in one predicate), suppressed while `flash_published` is outstanding; the
  guard clears on a drop below Red so re-escalation flashes again. Wired into
  `hadr/__main__.py` after reconcile; only reportables render on the board.
  Renderer gained hazard filter chips (U8) + client-side `applyFilter` (N20).
- **V5 — `scripts/edition.py` (N12/N13) + marker S3.** Pure
  `build_edition(state, marker, change_set, prior, *, now, reportable_ids)`:
  builds the changelog from post-marker changes (escalations first, then
  downgrades/revisions, then retractions), picks quiet vs regular (quiet iff no
  reportables and no changes — deterministic template, no model call), and
  advances `edition_marker.last_edition_at` monotonically. Change kind is
  classified from prior-vs-new alert levels / status, not feed wording.
  Renderer gained the edition type badge (U1), quiet line (U4), and changelog
  sections (U9/U10/U11). Renderer tests assert on the embedded JSON island.

Deviations / decisions worth recording:

- **`gate` takes a third `prior` argument** beyond the breadboard's
  `gate(change_set, state)`. Detecting escalation and "crosses into Red"
  requires the before/after alert levels, and `prior` is already in hand in the
  pipeline (the loaded pre-run state). `change_set` is still accepted (interface
  stability) but the decision is derived from levels, which strictly dominate
  the change kinds. `gate` also *annotates state in place* (`reported`,
  `flash_published`, `flash_pending`) rather than returning a new state, so the
  pipeline persists the decision without a second projection step.
- **`reported` is sticky.** Once an event clears the bar it stays
  `reported=true` (a durable "we have told the reader" fact used by the
  ReliefWeb arm and the changelog). Board membership is the *current* reportable
  set, computed fresh each run; a downgraded event drops off the board and its
  downgrade goes to the changelog.
- **`reconcile` now bumps `last_changed` on an alert-level change** (previously
  only magnitude/status did). This is change *detection*, not the join logic the
  slice was told to leave alone, and it is what makes the edition's post-marker
  watermark (`last_changed > last_edition_at`) honest for escalations/downgrades.
  No new `change_set` kind was added, so existing reconcile tests are unaffected.
- **`flash_pending` added to the state schema** (top-level list, seeded in
  `empty_state`). This is the seam V8's flash branch consumes; adding it is an
  additive, backward-tolerant extension of schema v1 (no version bump — the
  loader tolerates its absence in older files, and no v1 state is committed yet).
- **`flash_trigger` is computed and stored, not acted on** (V4 scope): it is
  returned from `gate`, persisted on `state["flash_pending"]`, and surfaced in
  the run summary. Publishing a flash / off-cycle render is V8.
- **Multi-run accumulation deferred to V8.** Locally each `hadr run` is
  effectively an edition run, so the changelog is this-run's delta gated by the
  marker. Once V8 splits hourly polls from the daily edition, the changelog must
  accumulate changes across the intervening hourly runs (the `last_changed`
  watermark already supports this; classifying against the *last edition's*
  levels rather than the last run's is the remaining V8 work).
- **Committed `dashboard.html` regenerated** from `scenario_a` via the pipeline:
  it now shows only the reportable Banda Sea M6.2 (Orange/PAGER-yellow); the two
  Green quakes and the no-alert Avalon quake are tracked in state but hidden.

### 2026-07-09 — Slice 3 build (issue #8, branch `feat/slice-3-unattended`)

Built Slice 3 (detailed slices V6 + V7 + V8): model assessment, coverage/
staleness, and unattended scheduling + flash. Stacked on Slice 2. Four staged
commits (`feat(v6)`, `feat(v7)`, `feat(v8)`, docs). All 92 tests, `ruff check`
and `ruff format --check` pass.

- **V6 — model assessment + `/sitrep` (N14).** `scripts/assess.py` puts the
  model call behind an injectable `assess(reportables, changelog, *, client)`
  seam: empty reportables short-circuit with `{}` and **no** client call (the
  decision to invoke is deterministic, never the model's — ADR-0003); otherwise
  the reportables + changelog are handed to `client` and the output schema is
  validated. The default client shells out to `claude -p` running the
  `skills/sitrep/SKILL.md` skill (no feed/tool access; data passed in). The
  renderer places per-event prose (U6) and an edition summary in the JSON island.
- **V7 — coverage + staleness (N11 / S2).** `scripts/staleness.py`:
  `coverage(feed_status, now)` marks a feed stale when there is no fresh success
  within 2× the hourly cadence, per feed independently, and emits render-ready
  rows (U12) + a banner (U13) naming the stale feed, its last success and a
  fallback note. `record()` folds each fetch outcome into `state["feed_status"]`;
  a failed fetch keeps the last success (staleness ≠ retraction).
  `scripts/retry.py` adds polite retry-with-backoff within a run (B7.4).
- **V8 — scheduling + flash (N1–N3, N10, N14, N16).** `.github/workflows/
  sitrep.yml` enabled: hourly + edition crons + dispatch, mode routed by
  `scripts/schedule.run_mode`, guarded model step with the secret quarantined,
  `[skip ci]` commit, concurrency group. The entrypoint gained `--mode
  poll|edition`, an `assess` subcommand (the guarded step) and a `mode`
  subcommand. Poll acts on the flash seam: it sets `flash_published` (once per
  Red spell) and re-renders with the banner; otherwise it persists state without
  re-rendering. `goal.md` committed.

Deviations / decisions worth recording:

- **The model runs as a separate `assess` subcommand, not inside `run`.** V6's
  seam is Python-and-tested, but V8's secret isolation (N14: `ANTHROPIC_API_KEY`
  never in fetch/reconcile/gate steps) requires process separation. So the
  deterministic `run` writes a transient `data/assessment_input.json` sidecar
  (gitignored) with the rendered events + edition; the guarded `assess` step
  reads it, phrases via `/sitrep`, folds the prose in and re-renders. The
  committed `dashboard.html` is therefore the *deterministic* render (no prose);
  prose is folded only by the guarded step (in CI with the key, or locally via
  `hadr assess`) — honest with "no live model in CI".
- **Multi-run changelog accumulation resolved via a marker baseline.** Slice 2
  deferred this. The edition now classifies the changelog against a `baseline`
  snapshot (level/magnitude/status per event) stored in `edition_marker` at each
  edition, not against the previous run. Hourly polls never advance the marker or
  baseline, so the daily edition reflects every change since the *last edition*.
  `_baseline_records` falls back to `prior` when no baseline is stored (first
  edition, and the existing V5 unit tests), so no prior test changed. This is an
  additive schema extension (`edition_marker.baseline`), no version bump.
- **Poll runs re-render only on a flash.** A plain hourly poll updates
  `state.json` but leaves the last published `dashboard.html` standing (the
  commit step commits state alone). Editions and flashes re-render. This keeps
  the dashboard the single surface (US10) without churning it every hour.
- **`build_flash_edition` bypasses the edition builder and the model** (breadboard
  N10 → N15, not N12/N14): a flash carries a Red banner and an empty changelog;
  the next 08:30 edition folds the crossing into its changelog via the baseline.
- **Workflow tests are text assertions, not YAML parsing.** `pyyaml` is not a
  dependency; `tests/test_workflow.py` strips comment lines and asserts on the
  real YAML (crons, concurrency, `[skip ci]`, and the secret confined to the one
  guarded step). Avoids adding a dependency just for a test.
- **Default `run` mode is `edition`**, so the existing local `python -m hadr run
  --fixture …` demo still builds an edition exactly as before Slice 3.

## Open questions

- Q16 in `QUESTIONS.md`: backfill strategy after a pipeline outage longer
  than the feeds' rolling windows (candidate: one-shot `4.5_week.geojson`
  fetch). Decide during the relevant build slice.

## Deviations

### 2026-07-08 — Two deliberate deviations from the starter README

- "No change → no report" replaced by always-publish (quiet editions are
  deterministic one-liners, no model call) — ADR-0003.
- Intraday flash alerts for new Red-level events added (REQS.md originally
  excluded intraday alerting; REQS amended) — ADR-0003.

<!-- Anything built that departs from the PRD or CLAUDE.md is recorded here,
     with the reason. An undocumented deviation is a bug. -->
