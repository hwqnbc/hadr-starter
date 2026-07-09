"""Trigger routing (V8 / N3): map a GitHub trigger to a pipeline mode.

Pure function, single source of truth for the workflow's branch (scripts/
schedule.py). Off-cadence triggers must never spend a model call.
"""

from __future__ import annotations

from scripts import schedule


def test_hourly_cron_is_a_poll():
    assert schedule.run_mode("schedule", schedule.HOURLY_CRON) == schedule.POLL


def test_edition_cron_is_an_edition():
    assert schedule.run_mode("schedule", schedule.EDITION_CRON) == schedule.EDITION


def test_workflow_dispatch_is_an_edition():
    assert schedule.run_mode("workflow_dispatch", None) == schedule.EDITION


def test_unknown_or_missing_cron_on_schedule_defaults_to_poll():
    # An unrecognised cron must not accidentally spend a model call.
    assert schedule.run_mode("schedule", "13 4 * * *") == schedule.POLL
    assert schedule.run_mode("schedule", None) == schedule.POLL


def test_edition_cron_is_00_30_utc_which_is_08_30_sgt():
    # 08:30 Asia/Singapore == 00:30 UTC (UTC+8, no DST).
    assert schedule.EDITION_CRON == "30 0 * * *"
    assert schedule.HOURLY_CRON == "0 * * * *"
