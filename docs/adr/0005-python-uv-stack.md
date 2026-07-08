# Python + uv stack, static dashboard, GitHub Actions scheduling

Python 3.12+ managed by `uv`, tests with `pytest`, lint/format with `ruff`.
HTTP via `httpx`; no web framework or build toolchain — `dashboard.html`
is a self-contained single-page application: one committed HTML file with
inline JS/CSS and the event state embedded as JSON at render time. Scheduling via GitHub Actions cron
(08:30 SGT = 00:30 UTC; Actions cron is best-effort, which the product
tolerates). Chosen over TypeScript/Go for iteration speed in a three-day
build and the strength of Python's parsing/data ecosystem for
GeoJSON/RSS/XML feeds.
