# REQS.md — Initial idea capture

Rough notes on what I want to build. Handwritten-style capture; details to be
worked out through the planning process.

## The idea

A monitoring agent for humanitarian assistance and disaster response (HADR).
It watches live disaster feeds, decides what actually matters, and publishes a
single morning situation report — unattended, on a schedule, and quiet on
mornings when nothing has changed.

## Who it's for

- Me (and reviewers/neighbours during the course week) as the immediate users.
- Notionally: anyone who wants a once-a-day, low-noise digest of significant
  disaster events without watching raw feeds themselves.

## What it should do

- Watch three live disaster feeds:
  - **GDACS** (EU/UN multi-hazard, GeoJSON/RSS, colour-coded alert levels)
  - **USGS** (earthquakes only, GeoJSON, regenerated every minute)
  - **ReliefWeb** (UN OCHA, curated JSON API/RSS, slower — human-vetted)
- Filter out the noise and assess what remains: what happened, where, how bad,
  who is affected.
- Publish a morning situation report to `dashboard.html` at **08:30 Singapore
  time**, committed to the repo.
- Run on a schedule, unattended. Stay quiet when nothing has changed — no
  change means no report.

## Hard problems I know about upfront (unsolved, part of the work)

- **Deduplication.** The same earthquake can arrive from all three feeds under
  different identifiers. What makes two records the same event?
- **Revision.** Events get re-graded, relocated, or deleted after they've been
  reported. What happens to a published report when its event changes?
- **Alert semantics.** GDACS colours, USGS `alert`, and `alertscore` don't mean
  the same thing. Which signal drives the decision to report?
- **Availability.** No feed guarantees uptime or documents rate limits. What
  does the 08:30 report say on a morning a feed is down?

## Constraints and operating principles

- The model never decides whether to wake up: a deterministic script detects
  change; a headless model call runs only if something changed.
- Determinism where determinism is due — anything that must give the same
  answer twice lives in `scripts/`, not a prompt.
- Undocumented deviations are bugs: decisions/deviations logged in
  `implementation-notes.md`.
- Thin, verifiable vertical slices; reviewable in two minutes.
- Secrets stay out of the repo and out of the agent's context.
- Timeline: three days — Plan, Autonomy (build + overnight loop), Trust
  (review, harden, demo).

## Expected end artefacts

- `prd.html` — the product requirements.
- `system-view.html` — how the pieces fit: feeds → checks → assessment → report.
- `dashboard.html` — the product itself: the published morning sitrep.
- `goal.md` — the agent's standing objective.
- At least one reusable skill under `skills/` (e.g. a `/sitrep` generator).

## Out of scope (for now)

- ~~Real-time / intraday alerting (one report per morning is the product).~~
  *Amended 8 Jul 2026 during grilling: intraday flash alerts for Red-level
  events are IN scope (see ADR-0003); anything below Red stays
  edition-only.*
- Feeds beyond GDACS, USGS, ReliefWeb.
- Any notification channel other than the committed `dashboard.html`.

## Amendments (8 Jul 2026, from grilling — see QUESTIONS.md)

- "Stay quiet when nothing has changed" is revised: a quiet morning still
  publishes a one-line quiet edition (deterministic, no model call), so a
  missing report is unambiguous. See ADR-0003.
- Dashboard shows current best state AND a changelog of changes since the
  previous edition.
