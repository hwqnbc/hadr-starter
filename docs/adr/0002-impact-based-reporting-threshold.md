# Reporting threshold is impact-based, not magnitude-based

GDACS emits Green events daily and USGS M4.5+ fires 5–10× a day; raw
magnitude thresholds either drown the reader or miss a M6.2 under a city.
An event is **reportable** when any of: GDACS event-level alert is Orange or
Red; USGS PAGER level is yellow, orange or red; an already-tracked event
escalates; or a ReliefWeb disaster entry appears for an event not yet
reported (human curation overrides model thresholds). Green/quiet events
are tracked in state but not reported.

## Considered options

- Raw magnitude cut-offs (e.g. M5.5+) — rejected: magnitude is not impact.
- GDACS Orange/Red only — rejected: misses PAGER-flagged and
  human-curated events.
