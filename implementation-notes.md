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
