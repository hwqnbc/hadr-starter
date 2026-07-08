---
shaping: true
---

# HADR Monitor — Breadboard (Detail B)

Selected Shape B (`SHAPING.md`) translated into affordances and wiring.
Design-from-shaped-parts mode: parts B1–B7 become concrete U/N/S below.
Written piecemeal; sections are appended as they are completed.

## Places

| # | Place | Description |
|---|-------|-------------|
| P1 | Dashboard (`dashboard.html`) | The product surface: self-contained SPA opened in any browser |
| P1.1 | Edition header | Subplace: edition date/type, "as of" stamp |
| P1.2 | Events board | Subplace: current reportable events |
| P1.3 | Changelog | Subplace: changes since previous edition |
| P1.4 | Coverage | Subplace: per-feed status and warnings |
| P2 | Pipeline (GitHub Actions runner) | Backend place: scheduled jobs, scripts, model step |
| P3 | Feeds (external) | GDACS API, USGS summary feed, ReliefWeb RSS — systems we only read |
| P4 | Source pages (external) | GDACS report page, USGS event page, ReliefWeb disaster page — navigation targets |

## Data Stores

| # | Place | Store | Description |
|---|-------|-------|-------------|
| S1 | P2 | `data/state.json` › `events` | Canonical events: own ID, aliases[], hazard, gdacs_alert, pager_alert, magnitude, location, origin_time, reported, flash_published, last_changed, source_refs |
| S2 | P2 | `data/state.json` › `feed_status` | Per feed: last success, last feed_generated_at, consecutive failures |
| S3 | P2 | `data/state.json` › `edition_marker` | Watermark: which changes the last edition already told the reader about |
| S4 | P1 | Embedded payload in `dashboard.html` | JSON island: events + edition content + coverage, written at render, read by the SPA |
| S5 | P2 | Git repository | External store: committed state + dashboard; history is the audit log (ADR-0004) |

## UI Affordances (P1 — Dashboard SPA)

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| U1 | P1.1 | header | Edition title + date (SGT) + type badge (regular / quiet / flash) | render | — | — |
| U2 | P1.1 | header | "As of" timestamp (last successful pipeline run, SGT) | render | — | — |
| U3 | P1.1 | header | Flash alert banner (only when latest publish was a flash) | render | — | — |
| U4 | P1.1 | header | Quiet edition line ("No significant events — all feeds healthy") | render | — | — |
| U5 | P1.2 | events-board | Event cards list (current reportable events) | render | → U6 | — |
| U6 | P1.2 | event-card | Card: name, hazard icon, GDACS colour chip + PAGER chip (separate), magnitude/severity, place, origin time (SGT), affected-population line, assessment prose | render | → U7 | — |
| U7 | P1.2 | event-card | Source links (GDACS report / USGS event / ReliefWeb disaster) | click | → P4 | — |
| U8 | P1.2 | events-board | Hazard-type filter chips (EQ/TC/FL/VO/DR/WF) | click | → N20 | — |
| U9 | P1.3 | changelog | Escalation entries (prominent, top) | render | — | — |
| U10 | P1.3 | changelog | Downgrade / revision one-liners | render | — | — |
| U11 | P1.3 | changelog | Retraction notices ("USGS deleted event X — previously reported M5.2 was a false detection") | render | — | — |
| U12 | P1.4 | coverage | Per-feed status row (feed, last success, freshness) | render | — | — |
| U13 | P1.4 | coverage | Coverage warning banner ("GDACS unreachable since 03:10 SGT; EQ coverage via USGS only") | render | — | — |

Notes: every display U above is fed by the SPA bootstrap (N21) reading the
embedded payload S4 — wiring shown in the Code Affordances table and
diagram. U8→N20 is the only client-side interaction loop; everything else
is static render of S4 content.

## Code Affordances (P2 — Pipeline, and P1 client script)

| # | Place | Component | Affordance | Control | Wires Out | Returns To |
|---|-------|-----------|------------|---------|-----------|------------|
| N1 | P2 | sitrep.yml | Hourly cron trigger (`0 * * * *`) | trigger | → N3 | — |
| N2 | P2 | sitrep.yml | Edition cron trigger (`30 0 * * *` = 08:30 SGT) + `workflow_dispatch` | trigger | → N3 | — |
| N3 | P2 | sitrep.yml | Trigger branch: which cron fired? | conditional | → N4 (always), → N12 (edition only) | — |
| N4 | P2 | scripts/fetch_gdacs.py | `snapshot()` — GET `geteventlist/EVENTS4APP` | call | — | → N7, → S2 |
| N5 | P2 | scripts/fetch_usgs.py | `snapshot()` — GET `all_day.geojson`, filter `type=="earthquake"` | call | — | → N7, → S2 |
| N6 | P2 | scripts/fetch_reliefweb.py | `snapshot()` — GET disasters RSS, parse GLIDE from description | call | — | → N7, → S2 |
| N7 | P2 | scripts/reconcile.py | `reconcile(snapshots, state)` — alias join (GLIDE → sourceid → heuristic), episode folding, revision/retraction detection, aged-out guard | call | → N8 (per new/changed GDACS EQ), → S1, → S2 | → N9 |
| N8 | P2 | scripts/fetch_gdacs.py | `event_detail(eventid)` — GET `geteventdata`, extract `properties.sourceid` (SPIKE-1) | call | — | → N7 |
| N9 | P2 | scripts/gate.py | `gate(change_set, state)` — reportables + flash trigger per ADR-0002 | call | — | → N10, → N12 |
| N10 | P2 | sitrep.yml | Flash branch: `flash_trigger && hourly run`? | conditional | → N15 (with flash banner), → S1 (`flash_published`) | — |
| N11 | P2 | scripts/staleness.py | `coverage(feed_status)` — stale = no fresh success within 2× cadence | call | — | → N12, → N15 |
| N12 | P2 | scripts/edition.py | `build_edition(state, marker)` — changelog since S3, quiet/regular decision | call | → N13 (quiet) or → N14 (reportable), → S3 (advance marker) | — |
| N13 | P2 | scripts/edition.py | Quiet edition template (deterministic, no model) | call | — | → N15 |
| N14 | P2 | sitrep.yml | Guarded model step: `claude -p` runs `/sitrep` skill on reportables JSON → per-event assessment prose + edition summary | call | — | → N15 |
| N15 | P2 | scripts/render.py | `render(state, edition_content, coverage)` — writes the SPA with embedded JSON payload | call | → S4 | — |
| N16 | P2 | sitrep.yml | Commit step: `git add data/state.json dashboard.html && commit [skip ci] && push` | call | → S5 | — |
| N20 | P1 | inline `<script>` | `applyFilter(hazard)` — toggles card visibility | call | — | → U5 |
| N21 | P1 | inline `<script>` | Bootstrap: parse embedded JSON island, render all sections, convert times to SGT | call | — | → U1–U6, U9–U13 |

Concurrency note: all of N1/N2-triggered runs share one Actions
`concurrency` group (B7.2) so state commits serialise; not an affordance,
just the mechanism guaranteeing S1/S3 writes never race.

## Wiring

```mermaid
flowchart TB
    subgraph P3["P3: Feeds (external)"]
        GDACS[("GDACS API")]
        USGS[("USGS all_day")]
        RW[("ReliefWeb RSS")]
    end

    subgraph P2["P2: Pipeline (GitHub Actions)"]
        N1(["N1: hourly cron"])
        N2(["N2: edition cron 08:30 SGT"])
        N3{"N3: which trigger?"}
        N4["N4: fetch_gdacs.snapshot()"]
        N5["N5: fetch_usgs.snapshot()"]
        N6["N6: fetch_reliefweb.snapshot()"]
        N7["N7: reconcile()"]
        N8["N8: gdacs event_detail() → sourceid"]
        N9["N9: gate()"]
        N10{"N10: new Red?"}
        N11["N11: coverage()"]
        N12["N12: build_edition()"]
        N13["N13: quiet template"]
        N14["N14: claude -p /sitrep"]
        N15["N15: render()"]
        N16["N16: commit + push"]
        S1["S1: state.events"]
        S2["S2: state.feed_status"]
        S3["S3: state.edition_marker"]
        S5["S5: git repo"]
    end

    subgraph P1["P1: Dashboard SPA"]
        S4["S4: embedded JSON payload"]
        N21["N21: bootstrap render"]
        N20["N20: applyFilter()"]
        subgraph P1_1["P1.1: Edition header"]
            U1["U1: title/date/type"]
            U2["U2: as-of stamp"]
            U3["U3: flash banner"]
            U4["U4: quiet line"]
        end
        subgraph P1_2["P1.2: Events board"]
            U5["U5: event cards"]
            U6["U6: card detail"]
            U7["U7: source links"]
            U8["U8: hazard filter"]
        end
        subgraph P1_3["P1.3: Changelog"]
            U9["U9: escalations"]
            U10["U10: downgrades/revisions"]
            U11["U11: retractions"]
        end
        subgraph P1_4["P1.4: Coverage"]
            U12["U12: feed status rows"]
            U13["U13: coverage warning"]
        end
    end

    P4["P4: Source pages (external)"]

    N1 --> N3
    N2 --> N3
    N3 --> N4
    N3 --> N5
    N3 --> N6
    GDACS -.-> N4
    USGS -.-> N5
    RW -.-> N6
    N4 -.-> N7
    N5 -.-> N7
    N6 -.-> N7
    N4 --> S2
    N5 --> S2
    N6 --> S2
    N7 --> N8
    N8 -.-> N7
    GDACS -.-> N8
    N7 --> S1
    N7 -.-> N9
    N9 -.-> N10
    N10 -->|yes, hourly run| N15
    N10 --> S1
    N3 -->|edition run| N12
    S1 -.-> N12
    S3 -.-> N12
    N12 -->|quiet| N13
    N12 -->|reportable| N14
    N12 --> S3
    S2 -.-> N11
    N11 -.-> N15
    N13 -.-> N15
    N14 -.-> N15
    N15 --> S4
    N15 --> N16
    N16 --> S5

    S4 -.-> N21
    N21 -.-> U1
    N21 -.-> U2
    N21 -.-> U3
    N21 -.-> U4
    N21 -.-> U5
    N21 -.-> U9
    N21 -.-> U10
    N21 -.-> U11
    N21 -.-> U12
    N21 -.-> U13
    U5 --> U6
    U6 --> U7
    U7 --> P4
    U8 --> N20
    N20 -.-> U5

    classDef ui fill:#ffb6c1,stroke:#d87093,color:#000
    classDef nonui fill:#d3d3d3,stroke:#808080,color:#000
    classDef store fill:#e6e6fa,stroke:#9370db,color:#000
    classDef trigger fill:#98fb98,stroke:#228b22,color:#000
    classDef condition fill:#fffacd,stroke:#daa520,color:#000

    class U1,U2,U3,U4,U5,U6,U7,U8,U9,U10,U11,U12,U13 ui
    class N4,N5,N6,N7,N8,N9,N11,N12,N13,N14,N15,N16,N20,N21 nonui
    class S1,S2,S3,S4,S5 store
    class N1,N2 trigger
    class N3,N10 condition
```

## Verification pass

- **Every display U has a source:** U1–U6, U9–U13 ← N21 ← S4 ← N15. ✅
- **Every N connects:** all Ns have Wires Out and/or Returns To; N13/N14
  both return edition content to N15 (mutually exclusive branches of N12). ✅
- **Every S is read:** S1←→N7/N12, S2→N11, S3→N12, S4→N21, S5 is the
  external audit store (read by humans/PRs). ✅
- **Navigation:** the only user navigation is U7 → P4 (external source
  pages); the dashboard is otherwise a single Place. ✅
- **Flash path traced:** N1→N3→fetch→N7→N9→N10(yes)→N15→N16 — flash
  publishes without touching N12/N14 (no model call unless the edition run
  needs one). Matches R5 + ADR-0003. ✅
- **Quiet morning traced:** N2→N3→fetch→N7→N9 (empty)→N12→N13→N15→N16 —
  no model call. Matches R4. ✅
- **Feed-down traced:** N4 fails → S2 records failure → N11 flags stale →
  N15 renders U13 in every subsequent publish. Matches R6. ✅
