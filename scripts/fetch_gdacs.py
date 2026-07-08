"""GDACS feed fetcher (B1.1 / N4, N8).

``snapshot()`` reads the ``EVENTS4APP`` event list into source records, keyed on
``eventid`` (a new ``episodeid`` is an update to the same event, never a new one).
``event_detail()`` fetches one event's detail payload for its ``properties.sourceid``
— the verbatim USGS alias that lets a GDACS earthquake join the USGS feed (SPIKE-1).
The list payload carries ``sourceid`` empty for every EQ, so the detail call is
required; callers cache the result on the canonical event and never re-fetch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.feeds import FeedSnapshot, SourceRecord

EVENT_LIST_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/EVENTS4APP"
EVENT_DETAIL_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventdata"

# GDACS eventtype codes map straight onto our hazard codes (CONTEXT.md).
_HAZARDS = {"EQ", "TC", "FL", "VO", "DR", "WF"}


def _parse_naive_utc(value: str) -> datetime:
    """GDACS timestamps ('2026-07-06T11:29:36') are naive UTC — attach UTC."""
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _feature_to_record(feature: dict[str, Any]) -> SourceRecord:
    props = feature["properties"]
    coords = feature["geometry"]["coordinates"]  # [lon, lat]
    eventid = props["eventid"]

    aliases = [f"gdacs:{eventid}"]
    glide = (props.get("glide") or "").strip()
    if glide:
        aliases.append(f"glide:{glide}")

    return SourceRecord(
        source="gdacs",
        hazard=props.get("eventtype", ""),
        aliases=aliases,
        name=props.get("name", ""),
        origin_time=_parse_naive_utc(props["fromdate"]),
        lat=coords[1],
        lon=coords[0],
        place=props.get("country", ""),
        source_ref=props.get("url", {}).get("report", ""),
        gdacs_alert=props.get("alertlevel"),
        glide=glide or None,
        extra={
            "eventid": eventid,
            "episodeid": props.get("episodeid"),
            "gdacs_source": props.get("source"),
        },
    )


def parse(payload: dict[str, Any], *, fetched_at: datetime) -> FeedSnapshot:
    """Pure: EVENTS4APP payload -> FeedSnapshot (all hazards GDACS reports)."""
    records = [
        _feature_to_record(f)
        for f in payload.get("features", [])
        if f.get("properties", {}).get("eventtype") in _HAZARDS
    ]
    return FeedSnapshot(source="gdacs", records=records, fetched_at=fetched_at, ok=True)


def snapshot(
    *,
    client: httpx.Client | None = None,
    fixture: str | Path | None = None,
) -> FeedSnapshot:
    """Fetch the current GDACS event list (or read a recorded fixture)."""
    fetched_at = datetime.now(tz=UTC)

    if fixture is not None:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        return parse(payload, fetched_at=fetched_at)

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        resp = client.get(EVENT_LIST_URL)
        resp.raise_for_status()
        return parse(resp.json(), fetched_at=fetched_at)
    except httpx.HTTPError as exc:
        # Graceful degradation: reconciler treats ok=False as "no news" (V7 covers
        # the visible coverage warning). One dead feed must not crash the run.
        return FeedSnapshot(
            source="gdacs", records=[], fetched_at=fetched_at, ok=False, error=str(exc)
        )
    finally:
        if owns_client:
            client.close()


def sourceid_from_detail(payload: dict[str, Any]) -> str | None:
    """Extract ``properties.sourceid`` (the USGS alias) from a detail payload."""
    props = payload.get("properties", payload)
    sourceid = (props.get("sourceid") or "").strip()
    return sourceid or None


def event_detail(
    eventid: int | str,
    *,
    client: httpx.Client | None = None,
    fixture: str | Path | None = None,
) -> str | None:
    """Return the USGS ``sourceid`` for one GDACS earthquake, or None."""
    if fixture is not None:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        return sourceid_from_detail(payload)

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30.0)
    try:
        resp = client.get(EVENT_DETAIL_URL, params={"eventtype": "EQ", "eventid": eventid})
        resp.raise_for_status()
        return sourceid_from_detail(resp.json())
    except httpx.HTTPError:
        # No sourceid available this run — the reconciler falls back to the
        # proximity heuristic, and a later run can still establish the alias.
        return None
    finally:
        if owns_client:
            client.close()
