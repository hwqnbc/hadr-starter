# The agent is an event-state reconciler, not a feed reader

All three feeds are revision streams: events escalate, get re-graded,
relocated, merged and deleted after first publication, and the escalation is
usually the alert that matters. We therefore maintain a persistent store of
canonical events (our own IDs), diff feed snapshots against it on every
poll, and derive all reporting from the diff — never from raw feed items.
A naive "poll → new item → alert" loop was rejected because it misses
escalations, double-reports revisions, and cannot handle retractions.

## Consequences

- Every source identifier (including all USGS `ids` aliases) is stored on
  the canonical event and matched against; join order is GLIDE number →
  USGS IDs exposed by the GDACS per-event detail → heuristic (hazard type +
  origin time ±30 min + distance ≤ 250 km).
- GDACS records are keyed on `eventid`; a new `episodeid` is an update.
- The dashboard shows current best-known state; each edition additionally
  carries a changelog of what changed since the previous edition.
