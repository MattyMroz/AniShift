"""Shared locations for local regression datasets and the network opt-in."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
"""AniShift repository root."""

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"
"""In-repository fixtures shared across the test suite."""

MM_AVH_TEMP: Final[Path] = _REPO_ROOT.parent / "mm_avh_working_space" / "temp"
"""Out-of-repository measurement data."""

TRACKS_DATASET: Final[Path] = MM_AVH_TEMP / "dataset.json"
"""The 206-entry MKV track-selection dataset."""


def pytest_collection_modifyitems(config: pytest.Config, items: Iterable[pytest.Item]) -> None:
    """Skip ``network`` tests unless explicitly requested with ``-m network``."""
    if "network" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="network test: run with -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
