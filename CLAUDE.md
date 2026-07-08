# CLAUDE.md

## Language & tooling

- Python 3.12+, environments and dependencies managed with `uv` (`uv sync`, `uv run`).
- HTTP via `httpx`. No web framework or JS build toolchain — `dashboard.html` is a self-contained single-page app: one HTML file, inline JS/CSS, event state embedded as JSON at render time (ADR-0005).
- Lint/format with `ruff` (`uv run ruff check .` and `uv run ruff format .`); both must pass before a PR.
- All timestamps are stored and compared in UTC; convert to Singapore time (SGT, UTC+8) only at render time.

## Test command

```
uv run pytest
```

## Conventions

- Use the vocabulary in `CONTEXT.md` (event, source record, alias, edition, flash alert, …) in code, comments, and docs. Respect the ADRs in `docs/adr/`.
- Deterministic logic (change detection, dedup joins, threshold checks, rendering) lives in `scripts/`, is pure where possible, and is covered by `pytest`. Model calls never make wake-up or threshold decisions (ADR-0003).
- One fetch module per feed, each isolated behind the same narrow interface, so a source can be swapped (e.g. ReliefWeb RSS → API) without touching the reconciler.
- Event state is `data/state.json` (ADR-0004): committed by the workflow, never hand-edited, schema-versioned with a top-level `"version"` key.
- Secrets stay out of the repo and out of prompts; `.env*` is git-ignored.

## Deviations policy

An undocumented deviation is a bug. Anything that departs from `docs/PRD.md`, the ADRs, or this file gets an entry in `implementation-notes.md` — what changed, why, and when — in the same PR that introduces it. If the deviation reverses a recorded decision, update or supersede the ADR too.
