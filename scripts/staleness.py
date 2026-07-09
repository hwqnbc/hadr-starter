"""Feed coverage + staleness (B6 / N11) and the per-feed status store (S2).

A feed that is down or stale must be *stated*, never silent (US11, US21): the
absence of a report is otherwise ambiguous between "calm world", "dead feed" and
"broken pipeline". This module is pure — a controlled ``now`` is passed in — so
the staleness logic is fully testable with recorded fixtures.

Two responsibilities:

- ``record`` folds one fetch's outcome into ``state["feed_status"]`` (S2): each
  feed's ``last_success``, its own ``feed_generated_at`` and a
  ``consecutive_failures`` counter. A failed fetch never clears the last known
  success — staleness is *not* retraction.
- ``coverage`` reads ``feed_status`` and, per feed *independently*, decides
  ``stale`` = no fresh success within 2x the poll cadence. It returns render-
  ready rows (U12) and, when something is stale, a banner (U13). Timestamps stay
  UTC ISO; the renderer converts to SGT at display time (CLAUDE.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from scripts.feeds import iso_utc

# Hourly poll cadence (ADR-0003). A feed is stale after 2x with no fresh success.
POLL_CADENCE = timedelta(hours=1)
STALE_MULTIPLIER = 2

FEED_LABELS = {"usgs": "USGS", "gdacs": "GDACS", "reliefweb": "ReliefWeb"}

# Which hazards each feed can cover — used to phrase a fallback note ("EQ
# coverage via USGS only") when a broad feed goes stale but USGS is healthy.
FEED_HAZARDS = {
    "usgs": {"EQ"},
    "gdacs": {"EQ", "TC", "FL", "VO", "DR", "WF"},
    "reliefweb": {"EQ", "TC", "FL", "VO", "DR", "WF"},
}

# A stable display order regardless of dict insertion order.
_FEED_ORDER = ("usgs", "gdacs", "reliefweb")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def label(feed: str) -> str:
    return FEED_LABELS.get(feed, feed.upper())


def record(
    feed_status: dict[str, Any],
    source: str,
    *,
    ok: bool,
    now: datetime,
    feed_generated_at: datetime | None = None,
) -> None:
    """Fold one fetch outcome into ``feed_status[source]`` (S2). Mutates in place.

    On success: refresh ``last_success`` and ``feed_generated_at``, reset the
    failure counter. On failure: keep the last known success (staleness is not
    retraction) and increment ``consecutive_failures``.
    """
    prior = feed_status.get(source, {})
    entry: dict[str, Any] = {
        "last_attempt": iso_utc(now),
        "last_success": prior.get("last_success"),
        "feed_generated_at": prior.get("feed_generated_at"),
        "consecutive_failures": prior.get("consecutive_failures", 0),
    }
    if ok:
        entry["last_success"] = iso_utc(now)
        entry["consecutive_failures"] = 0
        if feed_generated_at is not None:
            entry["feed_generated_at"] = iso_utc(feed_generated_at)
    else:
        entry["consecutive_failures"] = prior.get("consecutive_failures", 0) + 1
    feed_status[source] = entry


def is_stale(last_success: str | None, now: datetime, *, cadence: timedelta = POLL_CADENCE) -> bool:
    """A feed is stale when there has been no fresh success within 2x cadence.

    A feed that has never succeeded (``last_success is None``) is stale.
    """
    if last_success is None:
        return True
    return now - _parse_iso(last_success) > cadence * STALE_MULTIPLIER


def _fallback_note(stale_feeds: list[str], healthy: set[str]) -> str | None:
    """Phrase what coverage survives. Kept UTC-free — it names feeds, not times.

    If a broad feed (GDACS/ReliefWeb) is stale for earthquakes but USGS is still
    healthy, earthquake coverage continues via USGS — say so.
    """
    lost_eq = any("EQ" in FEED_HAZARDS.get(f, set()) for f in stale_feeds)
    if lost_eq and "usgs" in healthy:
        return "EQ coverage via USGS only"
    return None


def coverage(
    feed_status: dict[str, Any],
    now: datetime,
    *,
    cadence: timedelta = POLL_CADENCE,
) -> dict[str, Any]:
    """Per-feed freshness (N11). Pure: ``(feed_status, now) -> render-ready dict``.

    Returns ``{"feeds": [row...], "stale": [feed...], "banner": {...}|None}``.
    Each row carries the feed, its label, ``last_success`` (UTC ISO), the failure
    count and a per-feed ``stale`` flag — computed independently, so one dead feed
    never marks the others stale. ``banner`` is populated only when something is
    stale; it names each stale feed and its last-success time for U13.
    """
    ordered = [f for f in _FEED_ORDER if f in feed_status]
    ordered += [f for f in sorted(feed_status) if f not in _FEED_ORDER]

    rows: list[dict[str, Any]] = []
    stale_feeds: list[str] = []
    healthy: set[str] = set()
    for feed in ordered:
        fs = feed_status[feed]
        last_success = fs.get("last_success")
        stale = is_stale(last_success, now, cadence=cadence)
        rows.append(
            {
                "feed": feed,
                "label": label(feed),
                "last_success": last_success,
                "feed_generated_at": fs.get("feed_generated_at"),
                "consecutive_failures": fs.get("consecutive_failures", 0),
                "stale": stale,
            }
        )
        if stale:
            stale_feeds.append(feed)
        else:
            healthy.add(feed)

    banner = None
    if stale_feeds:
        banner = {
            "items": [
                {"feed": f, "label": label(f), "last_success": feed_status[f].get("last_success")}
                for f in stale_feeds
            ],
            "note": _fallback_note(stale_feeds, healthy),
        }
    return {"feeds": rows, "stale": stale_feeds, "banner": banner}
