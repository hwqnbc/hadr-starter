"""Coverage + staleness (V7 / N11, S2) and polite retry (B7.4).

Pure logic on a controlled clock: a down/stale feed is stated, never silent, and
one dead feed never marks the others stale (US21). A failed fetch is "no news",
never a retraction (staleness != retraction).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scripts import staleness
from scripts.feeds import FeedSnapshot
from scripts.retry import fetch_with_retry

NOW = datetime(2026, 7, 9, 6, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --- record (S2) -----------------------------------------------------------


def test_record_success_sets_last_success_and_resets_failures():
    fs: dict = {"usgs": {"last_success": "old", "consecutive_failures": 3}}
    gen = datetime(2026, 7, 9, 5, 58, 0, tzinfo=UTC)
    staleness.record(fs, "usgs", ok=True, now=NOW, feed_generated_at=gen)
    assert fs["usgs"]["last_success"] == _iso(NOW)
    assert fs["usgs"]["consecutive_failures"] == 0
    assert fs["usgs"]["feed_generated_at"] == _iso(gen)


def test_record_failure_preserves_last_success_and_counts_up():
    prev = _iso(NOW - timedelta(hours=1))
    fs: dict = {"gdacs": {"last_success": prev, "consecutive_failures": 1}}
    staleness.record(fs, "gdacs", ok=False, now=NOW)
    # Staleness != retraction: the last known success is kept, not cleared.
    assert fs["gdacs"]["last_success"] == prev
    assert fs["gdacs"]["consecutive_failures"] == 2


# --- coverage / staleness --------------------------------------------------


def test_stale_computed_per_feed_independently():
    fs = {
        "usgs": {"last_success": _iso(NOW - timedelta(minutes=30)), "consecutive_failures": 0},
        "gdacs": {"last_success": _iso(NOW - timedelta(hours=3)), "consecutive_failures": 3},
    }
    cov = staleness.coverage(fs, NOW)
    by_feed = {r["feed"]: r for r in cov["feeds"]}
    assert by_feed["usgs"]["stale"] is False  # 30 min < 2x cadence
    assert by_feed["gdacs"]["stale"] is True  # 3 h > 2x hourly cadence
    assert cov["stale"] == ["gdacs"]


def test_never_succeeded_feed_is_stale():
    fs = {"reliefweb": {"last_success": None, "consecutive_failures": 5}}
    cov = staleness.coverage(fs, NOW)
    assert cov["stale"] == ["reliefweb"]


def test_banner_names_stale_feed_and_last_success_and_fallback_note():
    last = _iso(NOW - timedelta(hours=3))
    fs = {
        "usgs": {"last_success": _iso(NOW - timedelta(minutes=10)), "consecutive_failures": 0},
        "gdacs": {"last_success": last, "consecutive_failures": 3},
    }
    cov = staleness.coverage(fs, NOW)
    banner = cov["banner"]
    assert banner is not None
    item = banner["items"][0]
    assert item["label"] == "GDACS"  # banner names the feed
    assert item["last_success"] == last  # ...and its last-success time
    # EQ still covered by USGS -> fallback note, matching the demo wording.
    assert banner["note"] == "EQ coverage via USGS only"


def test_no_banner_when_all_feeds_fresh():
    fs = {"usgs": {"last_success": _iso(NOW), "consecutive_failures": 0}}
    cov = staleness.coverage(fs, NOW)
    assert cov["banner"] is None and cov["stale"] == []


# --- retry with backoff (B7.4) ---------------------------------------------


def _snap(ok: bool) -> FeedSnapshot:
    return FeedSnapshot(source="usgs", records=[], fetched_at=NOW, ok=ok)


def test_retry_succeeds_after_transient_failures():
    outcomes = [_snap(False), _snap(False), _snap(True)]
    slept: list[float] = []
    snap = fetch_with_retry(lambda: outcomes.pop(0), sleep=slept.append)
    assert snap.ok is True
    assert slept == [1.0, 2.0]  # exponential backoff between the three attempts


def test_retry_gives_up_and_returns_failed_snapshot():
    slept: list[float] = []
    snap = fetch_with_retry(lambda: _snap(False), retries=2, sleep=slept.append)
    # A failed fetch is still a valid empty snapshot (no news), not an exception.
    assert snap.ok is False
    assert len(slept) == 2


# --- staleness != retraction (through the reconciler) ----------------------


def test_failed_fetch_never_empties_existing_events():
    from scripts import reconcile
    from scripts.state import empty_state

    state = empty_state()
    state["events"]["evt-2026-0001"] = {
        "hazard": "EQ",
        "name": "M 6.0 somewhere",
        "aliases": ["usgs:us1"],
        "location": {"lat": 0.0, "lon": 0.0, "place": "x"},
        "origin_time": _iso(NOW),
        "magnitude": {"value": 6.0},
        "gdacs_alert": None,
        "pager_alert": None,
        "reported": True,
        "flash_published": False,
        "status": "active",
        "first_seen": _iso(NOW),
        "last_changed": _iso(NOW),
        "source_refs": {"usgs": "u"},
    }
    failed = FeedSnapshot(source="usgs", records=[], fetched_at=NOW, ok=False, error="boom")
    new_state, changes = reconcile.reconcile([failed], state, now=NOW)
    # The event survives, still active — a dead feed is not a retraction/aging.
    assert new_state["events"]["evt-2026-0001"]["status"] == "active"
    assert changes == []
