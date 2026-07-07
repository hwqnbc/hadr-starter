# HADR Monitor

A monitoring agent for humanitarian assistance and disaster response (HADR).

It watches live disaster feeds, decides what actually matters, and publishes a
single morning situation report — unattended, on a schedule, and quiet on the
mornings nothing has changed.

This repository is a **starter**. It describes the destination and hands you the
raw materials; it does not tell you how to get there. Working out the *how* —
the data model, the filtering, the deduplication, the scheduling — is the
course.

---

## The end state

By Wednesday afternoon this repository contains an agent that:

- **Watches live disaster feeds** — GDACS, USGS and ReliefWeb (see `feeds/`).
- **Filters out the noise and assesses what remains** — what happened, where,
  how bad, and who is affected.
- **Publishes a morning situation report** to `dashboard.html` at **08:30
  Singapore time**.
- **Runs on a schedule, unattended**, and stays quiet when nothing has changed.

How it does any of that is not specified anywhere in this repository. That is
deliberate.

---

## The three days

1. **Plan** — interrogate the feeds, write the PRD, cut the work into vertical
   slices. Decide what "an event" is, how bad is bad enough to report, and what
   the report should say. Fill in `CLAUDE.md`.
2. **Autonomy** — build the first slice end to end, write a skill, wire up the
   08:30 routine, and launch the overnight loop. Let the agent run while you
   sleep.
3. **Trust** — review code you didn't write, harden the pipeline against feeds
   that are down or events that change underneath you, and demo.

---

## The feeds

Three sources, three different shapes and cadences. Full detail, endpoints and
example payloads live in `feeds/`.

| Feed | Source | Shape | Character |
|------|--------|-------|-----------|
| **GDACS** | EU/UN Global Disaster Alert & Coordination System | GeoJSON / RSS | Multi-hazard (quakes, cyclones, floods, volcanoes, drought, wildfire), colour-coded alert levels |
| **USGS** | US Geological Survey | GeoJSON | Earthquakes only, regenerated every minute, rolling time windows |
| **ReliefWeb** | UN OCHA | JSON API (approved appname) / RSS | Curated and slower — a disaster appears once humans decide it matters |

The hard problems are written into each feed's **Open questions**, and they are
the real work of the week:

- **Deduplication.** The same earthquake can arrive from all three feeds under
  different identifiers. What makes two records the same event?
- **Revision.** Events get re-graded, relocated, or deleted after you've already
  reported them. What happens to a published report when its event changes?
- **Alert semantics.** GDACS colours, USGS `alert`, and `alertscore` do not mean
  the same thing. Which signal drives *your* decision to report?
- **Availability.** No feed guarantees uptime or documents its rate limits. What
  does the 08:30 report say on a morning a feed is down?

---

## Repository layout

| Path | What it holds |
|------|---------------|
| `README.md` | This brief. |
| `CLAUDE.md` | Project conventions for the agent. **Empty by design** — fill it in before your first prompt. |
| `implementation-notes.md` | The agent's running log: decisions, open questions, deviations. One entry per working block. |
| `feeds/` | Reference docs for GDACS, USGS and ReliefWeb — endpoints, sample payloads, and the open questions. |
| `scripts/` | Deterministic checks. Anything that must give the same answer twice does not belong in a prompt. |
| `skills/` | Skills you write on Day 2 — one folder per skill: a `SKILL.md`, its assets, and which model each step should use. |
| `docs/solutions/` | Troubleshooting knowledge base. One learning per file, so no future session pays for the same bug twice. |
| `.github/workflows/` | `claude.yml` and `claude-code-review.yml` (the @claude reviewer), plus `sitrep.yml.disabled` — the morning routine, off until you build it. |
| `.github/ISSUE_TEMPLATE/` | Templates for vertical-slice and skill issues. |

---

## Operating principles

These are baked into the scaffold's comments; treat them as the house rules.

- **The model never decides whether to wake up.** A deterministic script decides
  whether anything changed; a headless model call runs *only if it did*. See
  `.github/workflows/sitrep.yml.disabled`.
- **Determinism where determinism is due.** Anything that must give the same
  answer twice lives in `scripts/`, not in a prompt.
- **Stay quiet on quiet mornings.** A scheduled job that publishes noise costs
  minutes and trust. No change → no report.
- **An undocumented deviation is a bug.** Anything that departs from the PRD or
  `CLAUDE.md` gets recorded in `implementation-notes.md`, with the reason.
- **Thin, verifiable slices.** If a reviewer cannot confirm a slice is done in
  two minutes, it is described, not done.
- **Pay for a bug once.** When something costs more than ten minutes, the fix
  goes in `docs/solutions/` so the next session greps it instead of rediscovering
  it.
- **Secrets stay out of context.** `.env*` is git-ignored; keep credentials out
  of the repo and out of the agent's prompt.

---

## Artefacts expected by the end

| Artefact | What it is |
|----------|------------|
| `prd.html` | The product requirements — what you decided to build and why. |
| `system-view.html` | How the pieces fit: feeds → checks → assessment → report. |
| `implementation-notes.md` | The decision/deviation log, kept as you go. |
| `dashboard.html` | **The product.** The published morning sitrep. Committed to the repo (it is the exception in `.gitignore`). |
| `goal.md` | The agent's standing objective, in its own words. |
| At least one **skill** | A reusable capability under `skills/`, e.g. the `/sitrep` report generator. |

Generated churn — `reports/` and `*.sitrep.html` — stays out of git. Only
`dashboard.html` is committed.

---

## Day 1 setup

1. Sign in to Claude Code with your Team seat.
2. Create your own repository from this template, then clone it.
3. Run `/install-github-app` so **@claude** reviews your pull requests from Day 2.
4. Install OpenCode and sign in with your Go key.
5. **Fill in `CLAUDE.md`** — at least three conventions (language & tooling, test
   command, code conventions, deviations policy) before your first prompt. An
   empty conventions file is also a decision, just not one you made.

---

## Working rhythm

- Open a **Vertical slice** issue for each thin feature (`.github/ISSUE_TEMPLATE/slice.md`).
  State the goal, an observable definition of done, and what's explicitly out of
  scope.
- Build behind pull requests so **@claude** and your neighbours can review.
- Log every decision, open question and deviation in `implementation-notes.md`
  as you go — not after.
- When you install a neighbour's skill and it misbehaves, file against it with
  the **Skill issue** template.
