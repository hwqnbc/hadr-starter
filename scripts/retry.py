"""Polite retry-with-backoff for a single feed fetch (B7.4).

We poll SLA-free public feeds, so a transient failure gets a couple of backed-off
retries within the run before we give up and report the feed as unavailable
(US20). The sleep is injectable so tests exercise the backoff schedule without
actually waiting; the retried callable returns a ``FeedSnapshot`` whose ``ok``
flag drives whether we retry.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from scripts.feeds import FeedSnapshot

# Default: two retries after the first attempt (3 attempts total), 1s base with
# exponential backoff (1s, 2s). Deliberately gentle — we are guests on these feeds.
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 1.0


def fetch_with_retry(
    fetch: Callable[[], FeedSnapshot],
    *,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> FeedSnapshot:
    """Call ``fetch`` and retry while the snapshot is not ``ok``.

    Backs off ``backoff * 2**attempt`` seconds between tries. Returns the first
    ``ok`` snapshot, or the last failed one after ``retries`` exhausted — a failed
    fetch is still a valid (empty) snapshot the reconciler treats as "no news",
    never a retraction.
    """
    snap = fetch()
    attempt = 0
    while not snap.ok and attempt < retries:
        sleep(backoff * (2**attempt))
        attempt += 1
        snap = fetch()
    return snap
