# QUESTIONS.md — Grilling log

Scratch file for the `/grill-with-docs` process. All open decision questions
logged upfront; answers recorded as they arrive. Facts already answered by
`docs/blindspots.md` and `feeds/*.md` are not re-asked.

Legend: ⬜ open · ✅ answered

**Status: all 12 initial questions answered 8 Jul 2026 (batch grilling).**
Answers recorded inline below. Deviations from recommendation: Q6 (chose
"both"), Q7 (intraday Red alerts in scope), Q8 (always publish an edition).

## Q1 ⬜ Mission

Is the product **situational awareness** ("keep a picture, once a day"),
**detection** ("tell me fast"), or **response tracking** ("what is the
humanitarian system doing")?

> **Recommendation:** Situational awareness. A once-daily 08:30 sitrep is
> structurally incompatible with detection (minutes matter); response
> tracking is ReliefWeb-lag territory. This sets source weighting: GDACS
> primary, USGS enrichment, ReliefWeb confirmation.

## Q2 ⬜ Hazard scope

All six GDACS hazard types (EQ, TC, FL, VO, DR, WF), or a subset?

> **Recommendation:** All six, but detection authority differs: EQ/TC are
> reliable via GDACS+USGS; floods/drought/wildfire/volcano reported only when
> GDACS raises them (accepting known patchiness). Conflict, epidemics,
> tsunami warnings explicitly out of scope (no source in stack).

## Q3 ⬜ Geographic scope

Global, or a region of interest (e.g. Asia-Pacific, given the 08:30 SGT
anchor)?

> **Recommendation:** Global. The feeds are global, filtering is by severity
> not geography, and a region filter is a one-line addition later.

## Q4 ⬜ Severity threshold (the alert-fatigue decision)

What clears the bar for the morning report?

> **Recommendation:** Report an event when ANY of:
> - GDACS event-level alert is **Orange or Red**
> - USGS PAGER `alert` is **yellow, orange or red**
> - An **escalation** of an already-reported event (e.g. Green→Orange)
> - A ReliefWeb disaster entry appears for an event not yet reported
>   (human curation overrides thresholds)
> Green/quiet events are tracked in state but not reported.

## Q5 ⬜ Deduplication policy

One canonical event merged across sources, or per-source streams?

> **Recommendation:** One canonical event with our own internal ID. Join
> order: GLIDE number → GDACS detail's NEIC/USGS ids → heuristic (hazard
> type + origin time ±30 min + distance ≤250 km). Store all source aliases
> (including every USGS `ids` entry) for matching.

## Q6 ⬜ Update / revision policy

An already-reported event gets re-graded, relocated, revised, or deleted.
What does the next report do?

> **Recommendation:** Published reports are immutable. The next 08:30 report
> carries an **Updates** section: escalations (prominent), downgrades
> (one line), retractions ("USGS deleted event X — previously reported M5.2
> was a false detection"). Escalation of a tracked event counts as a change
> that triggers a report (see Q4).

## Q7 ⬜ Report cadence

Strictly one report at 08:30 SGT, or also intraday alerts for Red events?

> **Recommendation:** Strictly 08:30 SGT, per REQS out-of-scope. Intraday
> alerting is a future slice; the pipeline (poll → state → diff) doesn't
> preclude it.

## Q8 ⬜ "Quiet morning" definition

What exactly counts as "nothing has changed"?

> **Recommendation:** No new reportable events AND no reportable state
> changes (escalation/downgrade/revision/retraction of a tracked event)
> since the last published report → the workflow exits before the model is
> invoked; `dashboard.html` is left untouched (its "as of" timestamp shows
> the last real report). A feed being down is NOT quiet — see Q9.

## Q9 ⬜ Feed-down behaviour

What does the 08:30 report say when a feed is down or stale?

> **Recommendation:** Staleness is tracked per feed (last successful fetch +
> feed's own generated/modified timestamps). A down/stale feed forces a
> report that morning with an explicit data-coverage warning ("GDACS
> unreachable since 03:10 SGT; earthquake coverage via USGS only"). Silence
> must never be ambiguous between "calm world" and "dead feed".

## Q10 ⬜ Event-state persistence

Where does event state live between runs?

> **Recommendation:** A single JSON state file (e.g. `data/state.json`)
> committed to the repo by the scheduled workflow. Transparent, diffable in
> PRs, no external infrastructure, survives runner recycling. SQLite is the
> fallback if the file gets unwieldy (it won't at ~dozens of active events).

## Q11 ⬜ ReliefWeb access

API appname approval takes time. Build against what?

> **Recommendation:** Request the appname immediately (human task, Day 1).
> Build against the public RSS feed (`https://reliefweb.int/disasters/rss.xml`)
> now — it carries GLIDE numbers, which is the main thing dedup needs.
> Swap to the API when approved; isolate behind one fetch module.

## Q12 ⬜ Language & tooling (CLAUDE.md is empty by design)

What stack?

> **Recommendation:** Python 3.12+, `uv` for env/deps, `pytest` for tests,
> `ruff` for lint/format. Stdlib + `requests`/`httpx` covers everything;
> GeoJSON/RSS parsing needs no heavy deps. GitHub Actions cron for the 08:30
> SGT schedule (00:30 UTC). Static `dashboard.html` rendered from a template
> — no web framework.

## Answers (8 Jul 2026)

- **Q1 ✅ Mission:** Situational awareness (as recommended).
- **Q2 ✅ Hazard scope:** All six GDACS types; EQ/TC authoritative, others
  GDACS-raised only; conflict/epidemics/tsunami out (as recommended).
- **Q3 ✅ Geography:** Global (as recommended).
- **Q4 ✅ Threshold:** Impact-based — GDACS Orange/Red, PAGER yellow+,
  escalation of tracked event, or ReliefWeb disaster entry (as recommended).
- **Q5 ✅ Dedup:** One canonical event, own internal ID, GLIDE → GDACS-detail
  USGS ids → heuristic join, all aliases stored (as recommended).
- **Q6 ✅ Revisions:** **"Both"** — dashboard always shows current best
  state, PLUS a changelog section listing what changed since the last
  edition (escalations, downgrades, retractions).
- **Q7 ✅ Cadence:** **08:30 SGT edition + intraday flash alerts for
  Red-level events.** Deviates from REQS's original out-of-scope; REQS
  amended.
- **Q8 ✅ Quiet mornings:** **Always publish** — a quiet morning still gets
  a one-line "no significant events" edition, so absence of a report is
  unambiguous. Deviates from the starter README's "no change → no report"
  principle; reconciled by keeping the quiet edition fully deterministic
  (no model call).
- **Q9 ✅ Feed-down:** Explicit per-feed staleness tracking and coverage
  warnings in the edition (as recommended).
- **Q10 ✅ Persistence:** JSON state file committed to the repo by the
  workflow (as recommended).
- **Q11 ✅ ReliefWeb:** RSS now, API when appname approved; request appname
  immediately — **human task, do on Day 1** (as recommended).
- **Q12 ✅ Stack:** Python 3.12+, uv, pytest, ruff; GitHub Actions cron;
  static rendered dashboard (as recommended).

## Round 2 — A2 inconsistency check

Answered 8 Jul 2026:

- **Q13 ✅ Hourly.**
- **Q14 ✅ "Single page application"** — dashboard.html remains the only
  surface, built as a self-contained SPA (one HTML file, inline JS, event
  state embedded); flash alerts surface as a banner on that page.
- **Q15 ✅ Confirmed** — quiet editions are template-only, no model call.

Original questions kept below for the record.

## Round 3 — E1 closeout check (8 Jul 2026)

- **Q16 ⬜ Extended-outage backfill (deferred to build).** USGS `all_day`
  and the GDACS list are rolling windows; a pipeline outage longer than
  ~24 h could scroll events past us unseen. Candidate mechanism: on first
  run after a gap > 20 h, fetch `4.5_week.geojson` once as backfill.
  Not shape-affecting — resolve as an implementation slice decision and
  record in implementation-notes.md.

- **Q13 ⬜ Intraday polling cadence.** Flash alerts (Q7) require polling
  more often than daily. GDACS asks for polite polling; GitHub Actions cron
  is best-effort. How often does the intraday poller run?
  > **Recommendation:** Hourly. Red events justifying a flash alert develop
  > over hours (GDACS colour is an impact estimate, not the raw detection);
  > hourly is polite to feeds, cheap in Actions minutes, and honest about
  > Actions cron jitter.
- **Q14 ⬜ Flash alert surface.** Where does a flash alert go? Same
  `dashboard.html`, or a separate artefact/channel?
  > **Recommendation:** Same `dashboard.html` — the flash re-renders the
  > dashboard early with the new Red event flagged, and the next 08:30
  > edition folds it into the changelog. One surface, no new channels.
- **Q15 ⬜ "Model never decides to wake up" vs always-publish.** Confirm the
  reconciliation: the change-detection script decides *whether anything
  changed*; on quiet mornings the deterministic pipeline publishes the
  one-line edition WITHOUT a model call; the model is invoked only when
  there are reportable events/changes to assess.
  > **Recommendation:** Yes — quiet editions are template-only.
