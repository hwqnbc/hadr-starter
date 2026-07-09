"""The scheduled workflow is enabled and the model secret is quarantined (V8).

Text assertions (no YAML dependency): the workflow must declare both crons and
dispatch, serialise runs, commit with [skip ci], and — critically — expose
ANTHROPIC_API_KEY to the guarded model step ALONE, never to fetch/reconcile/gate
(N14). The scaffold's disabled file must be gone (renamed, i.e. enabled).
"""

from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
SITREP = WORKFLOWS / "sitrep.yml"


def _text() -> str:
    return SITREP.read_text(encoding="utf-8")


def _text_no_comments() -> str:
    """The workflow with comment lines stripped — assert on real YAML, not prose."""
    lines = [ln for ln in _text().splitlines() if not ln.lstrip().startswith("#")]
    return "\n".join(lines)


def test_workflow_is_enabled_not_the_disabled_scaffold():
    assert SITREP.exists(), "sitrep.yml must exist (renamed from .disabled)"
    assert not (WORKFLOWS / "sitrep.yml.disabled").exists()


def test_declares_both_crons_and_dispatch():
    t = _text()
    assert '"0 * * * *"' in t  # N1 hourly poll
    assert '"30 0 * * *"' in t  # N2 daily edition, 08:30 SGT == 00:30 UTC
    assert "workflow_dispatch" in t


def test_serialises_runs_with_a_concurrency_group():
    assert "concurrency:" in _text()


def test_commits_state_and_dashboard_with_skip_ci():
    t = _text()
    assert "data/state.json" in t and "dashboard.html" in t
    assert "[skip ci]" in t


def test_model_secret_is_referenced_only_in_the_guarded_step():
    # In real YAML (comments stripped), ANTHROPIC_API_KEY must live in exactly one
    # step — the model step — and never in the pipeline (fetch/reconcile/gate) step.
    t = _text_no_comments()

    # Split into steps on the YAML list marker.
    steps = t.split("\n      - ")
    secret_steps = [s for s in steps if "ANTHROPIC_API_KEY" in s]
    assert len(secret_steps) == 1, "the secret must be confined to a single step"
    guarded = secret_steps[0]
    # That single step is the model step: it runs `hadr assess` and installs claude.
    assert "hadr assess" in guarded
    assert "claude" in guarded

    # The deterministic pipeline step must not reference the secret or the model.
    pipeline_steps = [s for s in steps if "hadr run" in s]
    assert pipeline_steps, "expected a `hadr run` pipeline step"
    for step in pipeline_steps:
        assert "ANTHROPIC_API_KEY" not in step
        assert "claude" not in step


def test_model_step_is_non_fatal_so_editions_still_publish():
    # ADR-0003 always-publish: the deterministic dashboard is rendered before the
    # model step, so a failing model call must not abort the job before the commit.
    # The guarded model step must be continue-on-error.
    steps = _text_no_comments().split("\n      - ")
    guarded = [s for s in steps if "hadr assess" in s]
    assert len(guarded) == 1, "expected exactly one guarded model step"
    assert "continue-on-error: true" in guarded[0]
