# HADR Monitor

Shared language for the HADR monitoring agent: the feeds it watches, the
events it tracks, and the report it publishes. Glossary only — decisions live
in `docs/adr/`, requirements in `docs/PRD.md`.

## Language

### Events and sources

**Event**:
A single real-world hazard occurrence (one earthquake, one cyclone, one
flood) tracked under our own canonical ID, merged across all sources.
_Avoid_: incident, alert, disaster, record

**Source record**:
One feed's representation of an event at a point in time — a GDACS feature,
a USGS feature, or a ReliefWeb disaster entry. Many source records map to
one event.

**Alias**:
Any identifier a source uses for an event: GDACS `eventid`, every entry in
USGS `ids`, a GLIDE number, a ReliefWeb disaster ID. Matching happens on
aliases; an event keeps all of them.

**Episode**:
GDACS's per-update subdivision of an event over its lifetime. A new episode
is an update to an existing event, never a new event.

**GLIDE**:
GLobal IDEntifier number (e.g. `EQ-2026-000093-VEN`) — the designed
cross-feed disaster key. Present on ReliefWeb disasters and, late and
inconsistently, on GDACS events.

**Tracked event**:
An event held in state, whether or not it has ever been reportable.

### Severity and change

**Alert level**:
GDACS's event-level Green/Orange/Red colour — a prediction of humanitarian
impact (population exposure × vulnerability), not a magnitude.
_Avoid_: severity, colour code

**PAGER level**:
USGS's green/yellow/orange/red estimate of fatalities and economic loss
(the `alert` field). Conceptually parallel to the GDACS alert level but a
different model; the two are never merged into one field.

**Reportable**:
Clearing the reporting threshold: GDACS Orange/Red, PAGER yellow or above,
an escalation of a tracked event, or a ReliefWeb disaster entry for an
event not yet reported.

**Escalation**:
An upward change in an event's alert or PAGER level between polls.
An escalation of an already-reported event is itself reportable.

**Downgrade**:
A downward change in an event's alert or PAGER level between polls.

**Retraction**:
A source explicitly deleting or invalidating an event that has already been
reported. Requires a positive deletion signal, never mere absence.

**Aged out**:
An event that has scrolled out of a feed's rolling window without any
deletion signal. Kept in state, not retracted — windows scroll, worlds
don't un-happen.

### The report

**Edition**:
One published issue of the morning situation report, 08:30 Singapore time,
published every day — quiet or not.
_Avoid_: sitrep (colloquial ok, but "edition" in code and docs), report

**Quiet edition**:
An edition stating that nothing reportable happened or changed — one line
plus coverage status. Produced without any model involvement.

**Flash alert**:
An out-of-cycle re-publication of the dashboard triggered by a new
Red-level event between editions.

**Changelog**:
The edition section listing what changed since the previous edition:
escalations, downgrades, revisions, retractions.

**Coverage warning**:
An edition's explicit statement that a feed was down or stale, and since
when. A missing feed is never allowed to read as a calm world.

**Staleness**:
A feed with no successful, fresh fetch within its expected cadence. Tracked
per feed, independently.

**Dashboard**:
`dashboard.html` — the single published product surface. Always shows the
current edition and the current best-known state of tracked events.
