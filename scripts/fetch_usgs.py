"""USGS earthquake feed fetcher (B1.2 / N5).

GET the ``all_day.geojson`` rolling window, keep only earthquakes, and turn each
feature into a ``SourceRecord``. Epoch-ms times become UTC ``datetime``s; every
entry of the comma-wrapped ``ids`` string is kept as an alias so matching
survives a preferred-ID flip.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.feeds import HAZARD_EQ, FeedSnapshot, SourceRecord

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
EVENT_PAGE = "https://earthquake.usgs.gov/earthquakes/eventpage/{id}"


def _epoch_ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def parse_ids(ids: str) -> list[str]:
    """Split USGS's comma-wrapped ``ids`` string (",ci41287863,us6000tafd,")."""
    return [part for part in ids.split(",") if part]


def _feature_to_record(feature: dict[str, Any]) -> SourceRecord:
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]  # [lon, lat, depth_km]
    lon, lat, depth_km = coords[0], coords[1], coords[2]

    # Preferred id first, then every alias in `ids`, de-duplicated in order.
    raw_ids = [feature["id"], *parse_ids(props.get("ids", ""))]
    seen: set[str] = set()
    aliases = [f"usgs:{i}" for i in raw_ids if not (i in seen or seen.add(i))]

    return SourceRecord(
        source="usgs",
        hazard=HAZARD_EQ,
        aliases=aliases,
        name=props.get("title", ""),
        origin_time=_epoch_ms_to_utc(props["time"]),
        lat=lat,
        lon=lon,
        place=props.get("place", ""),
        source_ref=EVENT_PAGE.format(id=feature["id"]),
        magnitude={
            "value": props.get("mag"),
            "type": props.get("magType"),
            "depth_km": depth_km,
        },
        pager_alert=props.get("alert"),
        status=props.get("status", "active"),
    )


def parse(payload: dict[str, Any], *, fetched_at: datetime) -> FeedSnapshot:
    """Pure: GeoJSON payload -> FeedSnapshot. Filters to earthquakes."""
    generated = payload.get("metadata", {}).get("generated")
    records = [
        _feature_to_record(f)
        for f in payload.get("features", [])
        if f.get("properties", {}).get("type") == "earthquake"
    ]
    return FeedSnapshot(
        source="usgs",
        records=records,
        fetched_at=fetched_at,
        ok=True,
        feed_generated_at=_epoch_ms_to_utc(generated) if generated else None,
    )


def snapshot(
    *,
    client: httpx.Client | None = None,
    fixture: str | Path | None = None,
) -> FeedSnapshot:
    """Fetch the current USGS window (or read a recorded fixture) as a snapshot.

    Pass ``fixture`` to read recorded JSON instead of the network (tests, and the
    ``--fixture`` CLI mode). ``client`` lets callers inject a shared httpx client.
    """
    fetched_at = datetime.now(tz=UTC)

    if fixture is not None:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        return parse(payload, fetched_at=fetched_at)

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        resp = client.get(FEED_URL)
        resp.raise_for_status()
        return parse(resp.json(), fetched_at=fetched_at)
    except httpx.HTTPError as exc:
        # A feed outage must degrade gracefully: the reconciler treats ok=False as
        # "no news" (never a retraction). Coverage/staleness reporting lands in V7.
        return FeedSnapshot(
            source="usgs", records=[], fetched_at=fetched_at, ok=False, error=str(exc)
        )
    finally:
        if owns_client:
            client.close()
