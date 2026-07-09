"""Model-assessment seam (B5 model step / N14).

The pipeline has *already decided* what is reportable (the gate, ADR-0002) and
whether to publish (the edition builder, ADR-0003). The model's only job is to
*phrase* that decided material — per-event assessment prose and a one-paragraph
edition summary. The model never makes a wake-up or threshold decision
(CLAUDE.md / ADR-0003).

Two properties matter and are enforced here, not in the model:

1. **The decision to invoke is deterministic.** ``assess`` returns ``{}`` and
   makes *no* client call when there are no reportables — a quiet morning costs
   nothing (US16). The caller passes the reportables the gate produced; the
   model is never asked whether to run.
2. **The model call is behind an injectable seam.** ``assess(..., client=...)``
   takes a callable ``client(payload) -> dict``; tests inject a stub so CI never
   touches a live model. The default client shells out to headless Claude
   (``claude -p``) running the ``/sitrep`` skill, passing the reportables +
   changelog JSON in — the model has no feed or tool access (see SKILL.md).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any, Protocol

# A client turns the JSON payload into the assessment dict. Injectable so the
# model call is stubbed in tests (no live model in CI).
AssessClient = Callable[[dict[str, Any]], dict[str, Any]]


class _CommandRunner(Protocol):
    def __call__(self, argv: list[str], *, input: str) -> str: ...  # noqa: A002


def _run_claude(argv: list[str], *, input: str) -> str:  # noqa: A002
    """Run headless Claude and return stdout. Isolated for injection in tests."""
    proc = subprocess.run(
        argv,
        input=input,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def default_client(*, runner: _CommandRunner = _run_claude) -> AssessClient:
    """The production client: shell out to ``claude -p`` running ``/sitrep``.

    The reportables + changelog payload is passed on stdin; the skill (SKILL.md)
    forbids any feed/tool access, so the model only ever sees what we hand it.
    ``ANTHROPIC_API_KEY`` is exposed to this process by the workflow's guarded
    model step alone (N14) and never to the fetch/reconcile/gate steps.
    """

    def _client(payload: dict[str, Any]) -> dict[str, Any]:
        # `-p` is headless (print) mode; the prompt invokes the /sitrep skill and
        # the JSON payload is fed on stdin. The skill is instructed to emit a bare
        # JSON object, which we parse back out.
        out = runner(
            ["claude", "-p", "/sitrep", "--output-format", "text"],
            input=json.dumps(payload, ensure_ascii=False),
        )
        return json.loads(out)

    return _client


def validate(result: Any) -> dict[str, Any]:
    """Validate the ``/sitrep`` output schema; raise ``ValueError`` if malformed.

    Expected shape::

        {"event_assessments": {"<event id>": "<prose>"...},
         "edition_summary": "<paragraph>"}
    """
    if not isinstance(result, dict):
        raise ValueError("assessment must be a JSON object")
    assessments = result.get("event_assessments")
    summary = result.get("edition_summary")
    if not isinstance(assessments, dict):
        raise ValueError("event_assessments must be an object keyed by event id")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in assessments.items()):
        raise ValueError("event_assessments must map event ids to prose strings")
    if not isinstance(summary, str):
        raise ValueError("edition_summary must be a string")
    return {"event_assessments": assessments, "edition_summary": summary}


def assess(
    reportables: list[dict[str, Any]],
    changelog: dict[str, Any] | None,
    *,
    client: AssessClient | None = None,
) -> dict[str, Any]:
    """Phrase the decided reportables. Returns ``{}`` (no model call) when quiet.

    The *decision* to invoke is deterministic: an empty ``reportables`` list means
    no reportable events, so no model runs and ``{}`` is returned. Otherwise the
    reportables + changelog are handed to ``client`` (the injected stub in tests,
    ``default_client()`` in production) and the result is schema-validated.
    """
    if not reportables:
        return {}  # quiet morning: no reportables -> no model call (US16)
    client = client or default_client()
    payload = {"reportables": reportables, "changelog": changelog or {}}
    return validate(client(payload))
