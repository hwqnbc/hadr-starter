"""Model-assessment seam (V6 / N14): deterministic invocation, stubbed model.

No live model in CI: the client is a stub, asserted on. The *decision* to invoke
is the gate's (reportables non-empty), never the model's (ADR-0003).
"""

from __future__ import annotations

import pytest

from scripts import assess


class _StubClient:
    """Records its calls; returns a fixed well-formed assessment."""

    def __init__(self, result=None):
        self.calls: list[dict] = []
        self._result = result or {
            "event_assessments": {"evt-1": "A moderate quake struck offshore."},
            "edition_summary": "One reportable event this edition.",
        }

    def __call__(self, payload):
        self.calls.append(payload)
        return self._result


REPORTABLES = [
    {"id": "evt-1", "name": "M 6.2 - Banda Sea", "hazard": "EQ", "gdacs_alert": "Orange"}
]
CHANGELOG = {"escalations": [{"id": "evt-1", "from": "Green", "to": "Orange"}]}


def test_quiet_run_makes_no_model_call():
    stub = _StubClient()
    out = assess.assess([], CHANGELOG, client=stub)
    assert out == {}
    assert stub.calls == []  # decision is deterministic: no reportables -> no model


def test_reportable_run_calls_model_with_reportables_and_changelog():
    stub = _StubClient()
    out = assess.assess(REPORTABLES, CHANGELOG, client=stub)
    assert len(stub.calls) == 1
    payload = stub.calls[0]
    assert payload["reportables"] == REPORTABLES
    assert payload["changelog"] == CHANGELOG
    assert out["event_assessments"]["evt-1"].startswith("A moderate")
    assert out["edition_summary"]


def test_output_schema_is_validated():
    good = {"event_assessments": {"evt-1": "prose"}, "edition_summary": "summary"}
    assert assess.validate(good) == good


@pytest.mark.parametrize(
    "bad",
    [
        "not an object",
        {"event_assessments": ["not", "a", "map"], "edition_summary": "s"},
        {"event_assessments": {"evt-1": 42}, "edition_summary": "s"},
        {"event_assessments": {"evt-1": "ok"}, "edition_summary": None},
        {"edition_summary": "missing assessments"},
    ],
)
def test_malformed_output_is_rejected(bad):
    with pytest.raises(ValueError):
        assess.validate(bad)


def test_malformed_client_output_raises_through_assess():
    bad_client = lambda payload: {"event_assessments": "wrong"}  # noqa: E731
    with pytest.raises(ValueError):
        assess.assess(REPORTABLES, CHANGELOG, client=bad_client)


def test_default_client_shells_out_to_claude_p():
    # The production client shells out to `claude -p`; assert the command shape
    # without spawning a real model (inject a fake runner).
    seen = {}

    def fake_runner(argv, *, input):
        seen["argv"] = argv
        seen["input"] = input
        return '{"event_assessments": {"evt-1": "x"}, "edition_summary": "y"}'

    client = assess.default_client(runner=fake_runner)
    out = client({"reportables": REPORTABLES, "changelog": CHANGELOG})
    assert seen["argv"][0] == "claude" and "-p" in seen["argv"] and "/sitrep" in seen["argv"]
    assert "reportables" in seen["input"]
    assert out["edition_summary"] == "y"


_OBJ = '{"event_assessments": {"evt-1": "x"}, "edition_summary": "y"}'


@pytest.mark.parametrize(
    "wrapped",
    [
        _OBJ,  # bare object
        f"```json\n{_OBJ}\n```",  # fenced code block
        f"Here is the assessment:\n{_OBJ}\nThanks!",  # prose-wrapped
        f"```\n{_OBJ}\n```",  # unlabelled fence
    ],
)
def test_default_client_tolerates_fenced_or_prose_wrapped_json(wrapped):
    # A model that wraps its JSON in a fence or a sentence must not break the
    # edition — the client extracts the outermost object.
    client = assess.default_client(runner=lambda argv, *, input: wrapped)
    out = client({"reportables": REPORTABLES, "changelog": CHANGELOG})
    assert out["event_assessments"]["evt-1"] == "x"
    assert out["edition_summary"] == "y"


def test_default_client_raises_cleanly_on_no_json():
    # A hopeless reply (no object at all) fails with ValueError so the workflow's
    # non-fatal model step falls through to publish the deterministic edition.
    client = assess.default_client(runner=lambda argv, *, input: "I could not help.")
    with pytest.raises(ValueError):
        client({"reportables": REPORTABLES, "changelog": CHANGELOG})
