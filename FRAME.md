---
shaping: true
---

# HADR Monitor — Frame

## Source

From `REQS.md` (initial idea capture, 8 Jul 2026), verbatim:

> A monitoring agent for humanitarian assistance and disaster response
> (HADR). It watches live disaster feeds, decides what actually matters,
> and publishes a single morning situation report — unattended, on a
> schedule, and quiet on mornings when nothing has changed.

> - **Deduplication.** The same earthquake can arrive from all three feeds
>   under different identifiers. What makes two records the same event?
> - **Revision.** Events get re-graded, relocated, or deleted after they've
>   been reported. What happens to a published report when its event
>   changes?
> - **Alert semantics.** GDACS colours, USGS `alert`, and `alertscore`
>   don't mean the same thing. Which signal drives the decision to report?
> - **Availability.** No feed guarantees uptime or documents rate limits.
>   What does the 08:30 report say on a morning a feed is down?

Amended during grilling (see QUESTIONS.md, ADR-0003): quiet mornings still
publish a one-line quiet edition, and new Red-level events trigger intraday
flash alerts on the same dashboard.

## Problem

Staying aware of significant humanitarian disasters means watching three
noisy, differently-shaped, SLA-free feeds that double-report the same event
under different identifiers, revise or retract events after publication,
and emit far more noise than signal. There is no low-effort way to get a
once-a-day, trustworthy picture that distinguishes a calm world from a dead
feed, and that corrects itself when events change after being reported.

## Outcome

Every morning at 08:30 Singapore time, a single self-contained dashboard
page carries a fresh edition: reportable events (deduplicated, impact-
thresholded) with what/where/how-bad/who-affected, a changelog of changes
since yesterday, and an explicit statement of data coverage. Quiet mornings
say so in one deterministic line. A catastrophic (Red) event reaches the
dashboard within about an hour, not the next morning. The whole thing runs
unattended; nobody remembers to trigger anything, and the model is only
ever invoked when there is something real to assess.
