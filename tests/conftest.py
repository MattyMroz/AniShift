from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"


def hidden_window_options() -> dict[str, object]:
    if sys.platform == "win32":
        startup: subprocess.STARTUPINFO = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": startup}
    return {}


def pytest_collection_modifyitems(config: pytest.Config, items: Iterable[pytest.Item]) -> None:
    if "network" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="network test: run with -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
