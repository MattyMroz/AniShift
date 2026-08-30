"""Optional native terminal image rendering for the AniShift mascot."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from importlib.resources import as_file, files
from pathlib import Path
from typing import Final

from anishift.utils.logger import get_logger

__all__ = ["NATIVE_MASCOT_ANCHOR", "NativeMascotImage", "load_native_mascot"]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────────

NATIVE_MASCOT_ANCHOR: Final[str] = "\ue000"
"""Private-use marker replaced by a native image before terminal output."""

_ASSET_PACKAGE: Final[str] = "anishift.cli.interactive.assets"
"""Package containing runtime presentation assets."""

_ASSET_PARTS: Final[tuple[str, ...]] = ("mascot", "idle", "01.png")
"""Package-relative path of the approved mascot still."""

_CHAFA_TIMEOUT_SECONDS: Final[float] = 3.0
"""Maximum time allowed for one native frame encoding."""

_MASCOT_SIZE: Final[str] = "20x14"
"""Terminal-cell area reserved by the interactive brand layout."""

_ESCAPE: Final[bytes] = b"\x1b"
"""Escape byte starting supported terminal image control sequences."""


class _NativeProtocol(StrEnum):
    """Identify the native image protocol supported by the active terminal."""

    SIXEL = "sixels"
    KITTY = "kitty"


@dataclass(frozen=True, slots=True)
class NativeMascotImage:
    """Hold one cached control sequence and its vertical layout offset."""

    payload: str
    row_offset: int


def load_native_mascot() -> NativeMascotImage | None:
    """Encode the approved still once when the current terminal supports images."""
    protocol: _NativeProtocol | None = _detect_protocol()
    executable: str | None = shutil.which("chafa")
    if protocol is None or executable is None:
        return None
    asset = files(_ASSET_PACKAGE).joinpath(*_ASSET_PARTS)
    try:
        with as_file(asset) as asset_path:
            return _encode(executable, asset_path, protocol)
    except subprocess.TimeoutExpired:
        logger.warning("Native mascot encoder timed out")
    except OSError, UnicodeDecodeError, ValueError:
        logger.warning("Native mascot encoder failed")
    return None


def _detect_protocol() -> _NativeProtocol | None:
    if os.name != "nt":
        return None
    if os.environ.get("WT_SESSION"):
        return _NativeProtocol.SIXEL
    if os.environ.get("TERM_PROGRAM", "").casefold() == "vscode":
        return _NativeProtocol.KITTY
    return None


def _encode(executable: str, asset_path: Path, protocol: _NativeProtocol) -> NativeMascotImage | None:
    arguments: list[str] = [
        executable,
        f"--format={protocol}",
        "--exact-size=on",
        f"--size={_MASCOT_SIZE}",
        f"--view-size={_MASCOT_SIZE}",
        "--align=mid,left",
        "--margin-bottom=0",
        "--margin-right=0",
        "--animate=off",
        "--probe=off",
        "--relative=off",
        "--polite=on",
        str(asset_path),
    ]
    completed = subprocess.run(  # noqa: S603
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=_CHAFA_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        return None
    output: bytes = completed.stdout.rstrip(b"\r\n")
    start: int = output.find(_ESCAPE)
    if start < 0 or not output.endswith(b"\x1b\\"):
        return None
    prefix: bytes = output[:start]
    payload: str = output[start:].decode("ascii")
    return NativeMascotImage(payload=payload, row_offset=prefix.count(b"\n"))
