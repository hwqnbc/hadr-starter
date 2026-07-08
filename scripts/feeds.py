"""The narrow interface every feed fetcher conforms to.

One fetch module per feed, each isolated behind ``snapshot()`` so a source can
be swapped (e.g. ReliefWeb RSS -> API) without touching the reconciler
(CLAUDE.md, SHAPING B1). A fetcher never decides anything; it turns one feed's
current window into ``SourceRecord``s plus fetch metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Hazard type codes shared across feeds (CONTEXT.md): EQ | TC | FL | VO | DR | WF.
HAZARD_EQ = "EQ"


@dataclass(frozen=True)
class SourceRecord:
    """One feed's representation of an event at a point in time (CONTEXT.md).

    Times are UTC-aware ``datetime``s; conversion to SGT happens only at render.
    ``aliases`` holds every identifier this feed used for the event (USGS ``ids``
    entries, GDACS ``eventid``, a GLIDE number, ...) — matching happens on aliases
    and a canonical event keeps all of them.
    """

    source: str  # "usgs" | "gdacs" | "reliefweb"
    hazard: str  # HAZARD_* code
    aliases: list[str]  # namespaced, e.g. "usgs:us6000taui", "gdacs:1550709"
    name: str
    origin_time: datetime  # UTC
    lat: float
    lon: float
    place: str
    source_ref: str  # human-facing page URL for this feed
    magnitude: dict[str, Any] | None = None  # {"value", "type", "depth_km"} for EQ
    gdacs_alert: str | None = None  # Green|Orange|Red — GDACS impact model
    pager_alert: str | None = None  # green|yellow|orange|red — USGS PAGER model
    glide: str | None = None
    status: str = "active"  # feed-reported lifecycle, e.g. USGS "deleted"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedSnapshot:
    """Result of one fetch: the records plus enough metadata to judge coverage.

    ``ok`` is False when the fetch failed; ``records`` is then empty and the
    reconciler must treat this as *no news*, never as *everything retracted*
    (staleness != retraction).
    """

    source: str
    records: list[SourceRecord]
    fetched_at: datetime  # UTC, when we made the request
    ok: bool
    feed_generated_at: datetime | None = None  # the feed's own timestamp, UTC
    error: str | None = None
