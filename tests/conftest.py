from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"

MM_AVH_TEMP: Final[Path] = _REPO_ROOT.parent / "mm_avh_working_space" / "temp"

TRACKS_DATASET: Final[Path] = MM_AVH_TEMP / "dataset.json"


def pytest_collection_modifyitems(config: pytest.Config, items: Iterable[pytest.Item]) -> None:
    if "network" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="network test: run with -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
