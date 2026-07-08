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
