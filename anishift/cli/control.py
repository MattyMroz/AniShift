"""Thin client of the resident, shared by the technical commands and the future panel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from anishift.platform.local_control import ControlClient, ControlError, connect, connect_or_start
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["ResidentStatus", "open_control", "resident_status"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResidentStatus:
    """Whether a resident answered, and the identifier it reported."""

    running: bool
    pid: int | None


def open_control(state_dir: Path) -> ControlClient:
    """Reach the resident of *state_dir*, starting one without a window when none runs.

    Raises:
        ControlError: No resident answered after one was started.
        AutostartError: The windowless interpreter is missing beside this one.
    """
    from anishift.cli.watch import spawn_resident  # noqa: PLC0415 - keep the process launch lazy

    def start() -> None:
        """Start the resident and drop the handle; its life is not tied to this process."""
        spawn_resident()

    return connect_or_start(state_dir, spawn=start)


def resident_status(state_dir: Path) -> ResidentStatus:
    """Report whether a resident answers, without ever starting one.

    A recorded instance file proves nothing; only a completed ``status`` command does.
    """
    client: ControlClient | None = connect(state_dir)
    if client is None:
        return ResidentStatus(running=False, pid=None)
    try:
        answer: Mapping[str, object] = client.call("status")
    except ControlError:
        return ResidentStatus(running=False, pid=None)
    finally:
        client.close()
    reported: object = answer.get("pid")
    return ResidentStatus(running=True, pid=reported if isinstance(reported, int) else None)
