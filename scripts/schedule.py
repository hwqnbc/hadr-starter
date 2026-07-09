"""Trigger routing (B4 / N3): map a GitHub trigger to a pipeline mode.

The scheduled workflow fires on two crons and on manual dispatch; this pure
function is the single source of truth for what each trigger means, so the YAML
and the tests never drift. It makes no decision the model could: it only maps a
trigger name + cron string to a mode.

- The **edition** cron (08:30 SGT) and any manual ``workflow_dispatch`` produce a
  full edition run: fetch -> reconcile -> gate -> build edition -> (guarded)
  model assessment -> render.
- The **hourly** cron produces a lightweight poll: fetch -> reconcile -> gate,
  persisting state and re-rendering only when a flash fires (N10). No edition
  build, no model call on a poll.
"""

from __future__ import annotations

# The two crons the workflow declares (UTC). 08:30 SGT == 00:30 UTC.
HOURLY_CRON = "0 * * * *"
EDITION_CRON = "30 0 * * *"

POLL = "poll"
EDITION = "edition"


def run_mode(event_name: str, cron: str | None = None) -> str:
    """Map ``(github event, cron)`` to ``"poll"`` or ``"edition"``. Pure.

    A scheduled run is an edition only on the edition cron; every other scheduled
    run (i.e. the hourly cron, or an unrecognised cron) is a poll — off-cadence
    triggers must not spend a model call. A manual ``workflow_dispatch`` is always
    a full edition so an operator can force one on demand (US15).
    """
    if event_name == "schedule":
        return EDITION if (cron or "").strip() == EDITION_CRON else POLL
    return EDITION
