from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.tts.engines.elevenreader.types import AlignmentChunk

if TYPE_CHECKING:
    from collections.abc import Iterable

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"


def requires_binaries(*binaries: Binary) -> pytest.MarkDecorator:
    missing: list[str] = [binary.value for binary in binaries if resolve_binary(binary) is None]
    return pytest.mark.skipif(bool(missing), reason=f"external binaries unavailable: {', '.join(missing)}")


def hidden_window_options() -> dict[str, object]:
    if sys.platform == "win32":
        startup: subprocess.STARTUPINFO = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": startup}
    return {}


def alignment_chunks(path: Path) -> tuple[AlignmentChunk, ...]:
    rows: list[dict[str, list[object] | float]] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    return tuple(_alignment_chunk(row) for row in rows)


def _alignment_chunk(row: dict[str, list[object] | float]) -> AlignmentChunk:
    chars, starts, durations = row["chars"], row["start_ms"], row["dur_ms"]
    assert isinstance(chars, list)
    assert isinstance(starts, list)
    assert isinstance(durations, list)
    return AlignmentChunk(
        offset_ms=float(str(row["offset_ms"])),
        chars=tuple(str(char) for char in chars),
        starts_ms=tuple(float(str(value)) for value in starts),
        durations_ms=tuple(float(str(value)) for value in durations),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: Iterable[pytest.Item]) -> None:
    if "network" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="network test: run with -m network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_real_chrome_or_ffmpeg(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("network") is not None:
        return
    from anishift.services.tts.engines.elevenreader import browser, redo  # noqa: PLC0415

    monkeypatch.setattr(browser, "open_window", _no_window)
    monkeypatch.setattr(browser, "async_playwright", _no_playwright)
    monkeypatch.setattr(redo, "mono_pcm", _no_pcm)


def _no_window(root: Path) -> None:
    message: str = f"a test opened a Chrome window on {root}"
    raise AssertionError(message)


def _no_playwright() -> None:
    message: str = "a test started Playwright"
    raise AssertionError(message)


def _no_pcm(recording: Path) -> list[int]:
    message: str = f"a test decoded {recording} with FFmpeg"
    raise AssertionError(message)
