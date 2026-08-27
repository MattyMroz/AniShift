"""Recognition of one file dropped on the terminal, which arrives as pasted text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from anishift.application import PRIMARY_SOURCE_SUFFIXES
from anishift.tui.strings import (
    COMPOSER_DROP_MISSING,
    COMPOSER_DROP_OUTSIDE,
    COMPOSER_DROP_UNSUPPORTED,
)

__all__ = [
    "DropKind",
    "DropVerdict",
    "dropped_paths",
    "inspect_drop",
]

# ── Constants ──────────────────────────────────────────────────────────────

_RUNS: Final[re.Pattern[str]] = re.compile(r'"([^"]*)"|\'([^\']*)\'|(\S+)')
"""One dropped line split into its double-quoted, single-quoted and bare runs."""

_SEPARATORS: Final[frozenset[str]] = frozenset({"/", "\\"})
"""Characters every dropped path carries, and a pasted sentence hardly ever does."""

_SCHEME_MARK: Final[str] = "://"
"""Mark of an address, which names no file of this machine."""


class DropKind(StrEnum):
    """What one pasted text turned out to be."""

    NOT_A_DROP = "not_a_drop"
    ACCEPTED = "accepted"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class DropVerdict:
    """What one pasted text asks for, and why a recognised drop was refused."""

    kind: DropKind
    paths: tuple[Path, ...] = ()
    reason: str = ""


def dropped_paths(text: str) -> tuple[Path, ...]:
    """Return every path *text* drops, or nothing at all when it drops none."""
    runs: tuple[str, ...] = tuple(run for line in text.splitlines() for run in _line_runs(line))
    if not runs or not all(_is_path(run) for run in runs):
        return ()
    return tuple(Path(run) for run in runs)


def inspect_drop(text: str, *, root: Path) -> DropVerdict:
    """Judge the drop *text* carries against the sources a scan of *root* reads."""
    paths: tuple[Path, ...] = dropped_paths(text)
    if not paths:
        return DropVerdict(kind=DropKind.NOT_A_DROP)
    reason: str = next((refusal for path in paths if (refusal := _refusal(path, root))), "")
    if reason:
        return DropVerdict(kind=DropKind.REFUSED, paths=paths, reason=reason)
    return DropVerdict(kind=DropKind.ACCEPTED, paths=paths)


def _line_runs(line: str) -> tuple[str, ...]:
    """Return the runs of one line, reading a quoted run as one whole path."""
    return tuple(run for match in _RUNS.finditer(line) if (run := _run_of(match)))


def _run_of(match: re.Match[str]) -> str:
    """Return the text one match holds, whichever of the three shapes carried it."""
    return match.group(1) or match.group(2) or match.group(3) or ""


def _is_path(run: str) -> bool:
    """Whether *run* has the shape of a dropped path instead of a written word."""
    if _SCHEME_MARK in run or not Path(run).suffix:
        return False
    return any(character in _SEPARATORS for character in run)


def _refusal(path: Path, root: Path) -> str:
    """Return why *path* cannot become work, or nothing at all when it can."""
    if not _is_file(path):
        return COMPOSER_DROP_MISSING
    if path.suffix.casefold() not in PRIMARY_SOURCE_SUFFIXES:
        return COMPOSER_DROP_UNSUPPORTED
    if not _is_scanned(path, root):
        return COMPOSER_DROP_OUTSIDE
    return ""


def _is_file(path: Path) -> bool:
    """Whether *path* names a file that is there right now."""
    try:
        return path.is_file()
    except OSError:
        return False


def _is_scanned(path: Path, root: Path) -> bool:
    """Whether one scan of *root* reads the directory *path* lies in."""
    try:
        return path.resolve().parent == root.resolve()
    except OSError:
        return False
