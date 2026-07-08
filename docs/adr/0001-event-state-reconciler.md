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
- The heuristic is a **last-resort** join, used only when no shared
  identifier links the records. It never merges records carrying distinct
  same-source identifiers (two USGS `ids`, two GDACS `eventid`s ⇒ distinct
  events), so an aftershock sequence — each shock with its own USGS id —
  stays separate despite falling inside the proximity window. Multiple
  in-window candidates are broken by nearest-in-time-and-space; ambiguous
  matches stay separate rather than merge.
- **Joins are revisable.** A wrong merge is **split**, and two events later
  found to be one (shared GLIDE, preferred-ID flip) are **merged**. Split and
  merge sit in the update policy beside escalation / downgrade / revision /
  retraction, and each appears in the changelog so a correction is as visible
  as the original claim.
- The dashboard shows current best-known state; each edition additionally
  carries a changelog of what changed since the previous edition.
