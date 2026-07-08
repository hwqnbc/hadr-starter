"""HADR Monitor orchestration package.

Thin sequencing over the deterministic logic in ``scripts``: fetch feeds,
reconcile against committed state, render the dashboard. Decisions live in
``scripts`` (and, later, a gated model step) — never here.
"""
