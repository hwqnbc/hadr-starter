# Data-source blindspot pass — GDACS, USGS, ReliefWeb

Written 7 Jul 2026, before any ingestion code exists. A survey of the
unknown unknowns in these three feeds and in the HADR-monitoring problem
itself. Endpoint specifics live in [`feeds/`](../feeds/); this document is
about the semantics and failure modes that aren't visible from an example
response. It also answers several of the open questions recorded in the
per-feed notes.

## The big reframes (things that change the architecture)

### 1. This is an event-state reconciler, not a feed reader

All three sources are **revision streams, not append-only logs**. Events
change alert level, magnitude, and location after first publication, and can
be deleted or merged. A naive "poll → new item → alert" loop is wrong on
day one:

- A GDACS event starts **Green** and escalates to **Red** hours later as
  impact estimates improve. The escalation *is* the alert that matters, and
  it arrives as an update to an event already seen, not as a new item.
- USGS earthquakes are revised constantly: magnitude changes, `status` can
  become `deleted`, and the **preferred event ID itself can change** when
  networks merge duplicate detections (the `ids` property lists all aliases;
  the preferred ID can flip from e.g. `ci41287863` to `us6000tafd`). Store
  every alias and match on any of them.
- ReliefWeb entries are edited after publication (`date.changed`).

Consequence: the agent needs a persistent event store keyed by its own
canonical ID, diffing on each poll, with an explicit policy for escalation,
downgrade, revision, and retraction of an already-reported event. This is
most of the real work.

### 2. The three feeds answer different questions

They are not three redundant hazard feeds:

| Source | Question it answers | Latency |
|---|---|---|
| USGS | "Did the ground shake?" (physical detection, earthquakes only) | minutes |
| GDACS | "Does it matter for people?" (estimated humanitarian impact, multi-hazard) | minutes–hours |
| ReliefWeb | "What is the humanitarian system doing about it?" (curated documents) | hours–days |

ReliefWeb is **not a detection source**; treating it like a real-time feed
is the most common mistake with it. Its value is confirmation, GLIDE
numbers, appeals, and situation reports *after* GDACS/USGS fire.

### 3. Cross-source deduplication is mandatory, because GDACS ingests USGS

Every significant earthquake appears in USGS first, then in GDACS (whose EQ
events carry `source: "NEIC"` — the same agency behind the USGS feed), then
in ReliefWeb if it is bad enough. Without correlation the agent
double-reports every quake. Available joins, in order of reliability:

1. **GLIDE numbers** — the designed cross-feed key. Present on ReliefWeb
   disasters (e.g. `EQ-2026-000093-VEN`) and as a `glide` field on GDACS
   events. Coverage is inconsistent and late: GDACS earthquakes often have
   `glide: ""` at first sight, and GLIDEs are only assigned to disasters
   that clear a significance bar.
2. **GDACS per-event detail** — for earthquakes, the detail endpoint
   exposes the originating USGS/NEIC identifiers.
3. **Fallback heuristic** — hazard type + origin-time window + spatial
   proximity. Needed whenever 1 and 2 are absent.

## Per-source gotchas

### GDACS

- **Events vs. episodes.** An event (e.g. a tropical cyclone) accumulates
  many *episodes* — one per update along its track. Keying on `episodeid`
  turns one cyclone into dozens of "events". Key on `eventid`; treat a new
  `episodeid` as an update.
- **Which alert level is "the" alert level** (open question 1 in
  [`feeds/gdacs.md`](../feeds/gdacs.md)): `alertlevel`/`alertscore` are the
  event-level (whole-lifetime) assessment; `episodealertlevel`/
  `episodealertscore` describe the latest episode. Report the event-level
  colour, but diff it between polls — yes, it changes after first
  publication, in both directions.
- **Alert colours are impact predictions, not magnitudes.** Green/Orange/Red
  models *population exposure × vulnerability*. A M7.8 under empty ocean is
  Green; a M6.2 under Kathmandu is Red.
- **Coverage is uneven by hazard.** EQ and TC are systematic and fast.
  Floods (GloFAS/media-driven), droughts, wildfires and volcanoes are
  patchier and slower — do not rely on GDACS for flood *detection*.
  Landslides, heatwaves, epidemics and conflict are essentially absent.
- **The JSON event-list endpoint is a rolling window** (roughly the most
  recent events over the last few days), not an archive. Miss a poll cycle
  during an outage and events can scroll out; historical pulls need the
  separate search method.
- **No SLA, no published rate limits** (open question 3): it is run by the
  EC Joint Research Centre and has occasional outages. Poll politely (every
  few minutes, not seconds), and build **staleness detection** so "feed is
  down" is reported as such rather than reading as "world is calm". A
  morning report generated from a dead feed must say the feed is dead.
- Timestamps (`fromdate`, `todate`, `datemodified`) are UTC but carry no
  timezone suffix; parse them as UTC explicitly.

### USGS

- **"All earthquakes" is not all earthquakes.** Detection threshold varies
  hugely by region: ~M2.0 in California, while small events in sparsely
  instrumented regions (much of Africa, parts of Asia) never appear. Below
  ~M4.5 the feed is heavily US-biased — for global HADR, filter to M4.5+ or
  consume noise with false geographic confidence.
- **Multiple IDs per event** (open question 1 in
  [`feeds/usgs.md`](../feeds/usgs.md)): several seismic networks detect the
  same quake and their solutions get associated; `ids` lists every
  identifier and `id` is the currently *preferred* one, which can change.
  Store all aliases.
- **Revisions and deletions** (open question 2): `status: "automatic"`
  solutions are unreviewed and will move; magnitude and location firm up
  over hours–days, and events are occasionally deleted (false detections,
  duplicates). An already-published report needs a correction/retraction
  path.
- **`alert` is the PAGER level** (open question 3): green/yellow/orange/red
  estimates of fatalities and economic loss, populated minutes-to-an-hour
  after origin for significant quakes, and revised. It is conceptually
  parallel to GDACS colours (both are impact models) but a *different
  model* — do not merge them into one field. PAGER orange/red is a far
  better HADR trigger than any raw-magnitude threshold.
- Use the **pre-built summary feeds for polling** (CDN-cached, regenerated
  ~every minute); the FDSN event query API is for backfill, per USGS's own
  guidance. Feeds follow a published feed-lifecycle/deprecation policy.
- The `type` property includes non-earthquakes (quarry blasts, ice quakes,
  explosions) — filter on it. The `tsunami` flag only means "check
  tsunami.gov"; actual tsunami warnings are a separate NOAA/PTWC source not
  in our current stack.
- Timestamps are **epoch milliseconds**, magnitudes come in different types
  (mb, ml, mw — the `magType` field) that are not strictly comparable, and
  the third geometry coordinate is depth in km (shallower = more damaging
  at equal magnitude).

### ReliefWeb

- **v1 is decommissioned (HTTP 410); v2 is the only API.** Since
  1 Nov 2025 the required `appname` must be **pre-approved** via a form and
  email confirmation — request it before integration day, because approval
  takes time (open question 1 in
  [`feeds/reliefweb.md`](../feeds/reliefweb.md)). The public RSS feed needs
  no approval and is the interim fallback; what it lacks versus the API is
  structured fields, filtering, the reports endpoint, and reliable
  update/change detection.
- **It is a document-search API** (`reports`, `disasters`, `jobs`,
  `training` content types) driven by a JSON query DSL. Responses return
  almost no fields by default — request them explicitly via
  `fields[include]` — and default ordering is relevance-like, so sort by
  date explicitly.
- **Rate limits** (open question 3): historically 1,000 calls/day and
  1,000 entries/call, with usage monitored and adjusted per application.
  Budget the call pattern (a few polled filters, not per-event queries) and
  back off on 429s.
- **Three date fields** — `date.created` (posted to ReliefWeb),
  `date.original` (the document's own date), `date.changed` (last edit).
  Polling on the wrong one either misses late-posted documents or endlessly
  re-processes edits. Poll on created/changed with an overlap window.
- **The `disasters` endpoint is the bridge** (open question 2): it carries
  the GLIDE number, affected-country taxonomy, and a status
  (`alert`/`ongoing`/`past`) — the closest thing to a canonical
  "humanitarian event" registry, even though it lags GDACS/USGS by days.
- **Reporting bias:** document volume tracks international attention, not
  severity. Do not use document count as a severity proxy.

## Cross-cutting blindspots

- **Slow-onset hazards break the "event" model.** Droughts and complex
  emergencies have no t=0; if they are in scope they need anomaly/threshold
  logic that these feeds serve poorly.
- **Known gaps in this stack:** conflict and displacement (ACLED, IDMC),
  epidemics (WHO), tsunami warnings (NOAA/PTWC), wildfire detail
  (NASA FIRMS), satellite activations (Copernicus EMS), IFRC operational
  data (GO API). NASA EONET is a useful normalized multi-hazard aggregator.
  These need not be added — but hazard scope should be chosen knowing they
  exist.
- **Alert fatigue is the product-killer.** GDACS emits Green events daily
  and USGS M4.5+ fires ~5–10×/day. The thresholding policy (e.g. "report on
  GDACS Orange+, PAGER yellow+, or any escalation of a previously-seen
  event") is the decision that makes the agent useful or ignorable.
- **Licensing is friendly but SLA-free:** USGS is public domain, GDACS free
  with attribution, ReliefWeb per its terms plus appname approval. None
  guarantee uptime; monitor all three for staleness independently.

## Decisions the blindspots force

1. **Mission:** detection ("tell me fast"), situational awareness ("keep a
   picture"), or response tracking ("what is the system doing")? Sets
   source weighting and latency targets.
2. **Scope:** hazard types, regions, and minimum severity — expressed as
   GDACS colour / PAGER level, not raw magnitude.
3. **Update policy:** behaviour on escalation, downgrade, revision, and
   retraction of an already-reported event.
4. **Dedup policy:** one canonical event across sources, or per-source
   streams.
5. **Persistence:** where event state lives between runs (it must live
   somewhere, per reframe 1).
6. **ReliefWeb appname registration:** request early; build against the RSS
   feed while waiting.

## Sources

- ReliefWeb API documentation: <https://apidoc.reliefweb.int/> and
  appname policy <https://apidoc.reliefweb.int/parameters#appname>
- GDACS feed reference: <https://www.gdacs.org/feed_reference.aspx> and
  API quick start <https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v1.pdf>
- USGS GeoJSON feeds: <https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php>,
  feed overview <https://earthquake.usgs.gov/earthquakes/feed/>,
  FDSN event API <https://earthquake.usgs.gov/fdsnws/event/1/>,
  ComCat documentation <https://earthquake.usgs.gov/data/comcat/>
- Verified endpoint snapshots in this repo: [`feeds/gdacs.md`](../feeds/gdacs.md),
  [`feeds/usgs.md`](../feeds/usgs.md), [`feeds/reliefweb.md`](../feeds/reliefweb.md)
