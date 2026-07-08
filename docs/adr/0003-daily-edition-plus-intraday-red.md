# A daily edition is always published; Red events also trigger intraday flash alerts

Two deliberate deviations from the starter README's "no change → no report"
principle, decided 8 Jul 2026:

1. **Always publish.** Every morning at 08:30 SGT an edition is published,
   even on quiet mornings (a one-line "no significant events" plus coverage
   status). Rationale: absence of a report is otherwise ambiguous between
   "calm world", "dead feed" and "broken pipeline".
2. **Intraday flash alerts.** Any event crossing into Red between editions —
   newly detected at Red *or* a tracked event escalating into Red —
   re-publishes the dashboard immediately rather than waiting for morning.
   Escalation-to-Red is explicitly included: it is the scenario the
   reconciler (ADR-0001) exists to catch, so it must not be deferred to the
   08:30 edition.

The starter's underlying principle — *the model never decides whether to
wake up* — is preserved: a deterministic script detects change; quiet
editions are rendered from a template with **no model call**; the model is
invoked only when there are reportable events or changes to assess.

## Consequences

- The original REQS.md placed intraday alerting out of scope; REQS.md has
  been amended and this ADR records the reversal.
- Flash alerts require sub-daily polling: the intraday poller runs
  **hourly** (polite to SLA-free feeds, honest about GitHub Actions cron
  jitter; Red-level impact estimates develop over hours anyway).
- A flash alert re-renders `dashboard.html` early with the Red event
  flagged; the next 08:30 edition folds it into the changelog. The
  dashboard remains the single surface.
- A flash fires **once per Red spell**: `flash_published` is set on the flash
  and cleared when the event drops below Red, so a downgrade-then-re-escalation
  flashes again while sustained Red does not re-flash each poll.
- Flash latency is bounded by the hourly poll plus best-effort cron (up to
  ~2 h from occurrence, ~1 h from detection); the cadence stays hourly
  deliberately — polite to SLA-free feeds, and Red impact estimates develop
  over hours anyway.
