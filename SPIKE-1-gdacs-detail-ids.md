---
shaping: true
---

## B2 Spike: GDACS per-event detail as the USGS join key

### Context

Every shape's deduplication (R1) leans on claim 2 of the join order in
ADR-0001: "USGS IDs exposed by the GDACS per-event detail endpoint". That
claim comes from `docs/blindspots.md` and has never been verified against a
real payload. GLIDE (join 1) is known to be late/absent on fresh GDACS
earthquakes, so join 2 carries real weight; if it doesn't exist, the
heuristic (join 3) becomes the primary mechanism and its tolerances need
firmer grounding.

### Goal

See the actual shape of `geteventdata` for a current earthquake and
determine what identifier(s) it shares with the USGS feed.

### Questions

| # | Question |
|---|----------|
| **B2-Q1** | What does `geteventdata?eventtype=EQ&eventid=…` actually return for a current earthquake — and where in it (if anywhere) does a USGS/NEIC event identifier appear? |
| **B2-Q2** | Is the identifier there matchable against the USGS feed's `id`/`ids` alias set (format, prefixes)? |
| **B2-Q3** | If no usable identifier exists, are origin time + epicentre in the detail payload precise enough for the ±30 min / ≤250 km heuristic to be the primary join for earthquakes? |

### Acceptance

Spike is complete when all three questions are answered from live payloads
and we can describe the concrete earthquake join mechanism (field paths and
match rule) for the reconciler.

### Findings (live payloads, 8 Jul 2026)

Investigated against the real endpoints with eventid 1550709 (M5.0
earthquake, Xunchang, China, 08 Jul 2026 02:08 UTC).

**B2-Q1 — Yes, and it's a single field.** The detail endpoint
(`geteventdata?eventtype=EQ&eventid=1550709`) returns one GeoJSON Feature
whose `properties.sourceid` is `"us6000taui"` alongside
`properties.source = "NEIC"`. Corroborating fields: `images.neic` links to
`earthquake.usgs.gov/.../shake/6000taui/...`.

**B2-Q2 — Directly matchable, no transformation.** The live USGS
`all_day.geojson` contains the same event with preferred `id =
"us6000taui"` and `ids = ",us6000taui,"` — the GDACS `sourceid` is a
verbatim member of the USGS alias set (M5.0, "15 km NNE of Xunchang,
China"). Match rule: `gdacs.properties.sourceid ∈ usgs ids-set`.

**B2-Q3 — Heuristic remains the fallback, and the inputs are adequate.**
The detail payload carries `fromdate` (origin time, naive UTC) and point
coordinates; USGS carries epoch-ms time and coordinates — both precise to
the second/severalkm, comfortably inside ±30 min / ≤250 km tolerances.
Needed when `source ≠ NEIC` or `sourceid` is empty.

**Surprise finding — a detail call per earthquake is required.** The event
*list* payload also has a `sourceid` key, but it is `""` for every EQ event
observed (19/19); only the detail endpoint populates it. GLIDE was `""` on
all of them too, confirming it cannot be the primary join for fresh
earthquakes.

**Concrete mechanism for the reconciler:**
1. New/changed GDACS EQ event → one `geteventdata` call → cache
   `sourceid` on the canonical event as an alias (never re-fetch unless
   episode changes).
2. Match `sourceid` against the union of all stored USGS aliases (every
   `ids` entry).
3. No `sourceid` / non-NEIC source → heuristic: same hazard type, origin
   time within ±30 min, epicentres ≤250 km apart.
4. GLIDE, when it eventually appears (GDACS or ReliefWeb), is added as an
   alias and can retro-merge events.
