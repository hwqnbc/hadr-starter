"""Shared test fixtures — paths to recorded feed snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def scenario_a() -> Path:
    """Directory of recorded feed snapshots for the primary reconciliation scenario."""
    return FIXTURES / "scenario_a"
