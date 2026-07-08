# A daily edition is always published; Red events also trigger intraday flash alerts

Two deliberate deviations from the starter README's "no change → no report"
principle, decided 8 Jul 2026:

1. **Always publish.** Every morning at 08:30 SGT an edition is published,
   even on quiet mornings (a one-line "no significant events" plus coverage
   status). Rationale: absence of a report is otherwise ambiguous between
   "calm world", "dead feed" and "broken pipeline".
2. **Intraday flash alerts.** A new Red-level event between editions
   re-publishes the dashboard immediately rather than waiting for morning.

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
