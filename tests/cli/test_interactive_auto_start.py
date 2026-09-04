from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import cast

from rich.text import Text

from anishift.application import AppService
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.mascot import MascotController, MascotState
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.errors import ExecutionError


def _application(
    mode: interactive_app._ViewMode,
    service: object | None = None,
) -> interactive_app._InteractiveApplication:
    application = object.__new__(interactive_app._InteractiveApplication)
    application._lock = threading.Lock()
    application._mode = mode
    application._selected = 0
    application._message = Text()
    application._message_view = interactive_app._QueueView(following=False)
    application._progress = None
    application._settings = None
    application._manual = None
    application._mascot = cast("MascotController", SimpleNamespace(state=MascotState.IDLE))
    application._renderer = cast("TerminalRenderer", SimpleNamespace(native_mascot_size=(18, 10)))
    application._directory = "~"
    application._service = cast("AppService", service)
    return application


def test_auto_preparation_shows_the_unchanged_home_frame() -> None:
    home = _application(interactive_app._ViewMode.HOME)
    preparing = _application(interactive_app._ViewMode.PREPARING)

    assert preparing._render_frame(120, 40).plain == home._render_frame(120, 40).plain


def test_manual_preparation_shows_the_unchanged_home_frame() -> None:
    home = _application(interactive_app._ViewMode.HOME)
    preparing = _application(interactive_app._ViewMode.MANUAL_PREPARING)

    assert preparing._render_frame(120, 40).plain == home._render_frame(120, 40).plain


def test_home_prewarms_the_workspace_scan() -> None:
    calls: list[str] = []
    service = SimpleNamespace(discover=lambda: calls.append("discover"))
    application = _application(interactive_app._ViewMode.HOME, service)

    application._prewarm_workspace()

    assert calls == ["discover"]


def test_a_failed_prewarm_does_not_break_home() -> None:
    def failing_discover() -> None:
        raise ExecutionError("probe failed")

    application = _application(interactive_app._ViewMode.HOME, SimpleNamespace(discover=failing_discover))

    application._prewarm_workspace()
