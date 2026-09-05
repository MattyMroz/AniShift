"""Process exit codes shared by every AniShift run that a caller reads mechanically."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from anishift.application import RunResult

__all__ = ["EXIT_CANCELLED", "EXIT_INCOMPLETE", "EXIT_REFUSED", "EXIT_SUCCESS", "run_exit_code"]

# ── Constants ─────────────────────────────────────────────────────────────────

EXIT_SUCCESS: Final[int] = 0
"""Every group of a run reached a successful terminal state."""

EXIT_REFUSED: Final[int] = 1
"""The run never started: unusable configuration, unknown preset, no sources or a blocked plan."""

EXIT_INCOMPLETE: Final[int] = 3
"""The run finished with a failed or partial group; 2 stays reserved for command-line usage errors."""

EXIT_CANCELLED: Final[int] = 4
"""Cancellation reached the run before every group succeeded."""


def run_exit_code(result: RunResult) -> int:
    """Map one terminal run result to the exit code a calling script or watcher reads."""
    if result.succeeded:
        return EXIT_SUCCESS
    if result.cancelled:
        return EXIT_CANCELLED
    return EXIT_INCOMPLETE
