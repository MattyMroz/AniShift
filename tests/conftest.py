"""Shared locations for local regression datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
"""AniShift repository root."""

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"
"""In-repository fixtures shared across the test suite."""

MM_AVH_TEMP: Final[Path] = _REPO_ROOT.parent / "mm_avh_working_space" / "temp"
"""Out-of-repository measurement data."""

TRACKS_DATASET: Final[Path] = MM_AVH_TEMP / "dataset.json"
"""The 206-entry MKV track-selection dataset."""
