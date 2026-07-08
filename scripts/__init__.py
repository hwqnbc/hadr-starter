"""Deterministic HADR pipeline logic — pure where possible, covered by pytest.

Anything that must give the same answer twice lives here, never in a prompt
(ADR-0003). Orchestration and I/O sequencing live in the ``hadr`` package.
"""
