from __future__ import annotations

import threading
from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import pytest
from rich.text import Text

from anishift.application import AppService, InspectedWorkspace, RefusalReason
from anishift.application.cancellation import EventCancellationToken
from anishift.cli.exit_codes import EXIT_REFUSED, EXIT_SUCCESS
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.manual import ManualRun
from anishift.cli.interactive.mascot import MascotController, MascotState
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession
from anishift.errors import ExecutionError
from anishift.platform.local_control import ControlError, ControlErrorCode


def _application(
    mode: interactive_app._ViewMode,
    service: object | None = None,
) -> interactive_app._InteractiveApplication:
    application = object.__new__(interactive_app._InteractiveApplication)
    application._lock = threading.Lock()
    application._mode = mode
    application._selected = 0
    application._home_choices = interactive_app._HOME_CHOICES
    application._message = Text()
    application._message_view = interactive_app._QueueView(following=False)
    application._progress = None
    application._settings = None
    application._manual = None
    application._anime = None
    application._batch = None
    application._resident = None
    application._execution = None
    application._closing_at = None
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


class _RefusingResident:
    def __init__(self, problem: ControlError) -> None:
        self._problem: ControlError = problem
        self.closed: int = 0

    def new_session(self) -> _RefusingResident:
        return self

    def discover(self, *, cancel: object = None) -> InspectedWorkspace:
        del cancel
        return InspectedWorkspace((), ())

    def reserve(self, group_ids: Sequence[str]) -> None:
        del group_ids
        raise self._problem

    def close(self) -> None:
        self.closed += 1


def _auto_application(
    problem: ControlError,
) -> tuple[
    interactive_app._InteractiveApplication,
    list[str],
    list[int],
]:
    application: interactive_app._InteractiveApplication = _application(
        interactive_app._ViewMode.PREPARING, SimpleNamespace(default_preset_id=lambda: "preset")
    )
    application._generation = 0
    application._worker = None
    application._preflight_cancel = EventCancellationToken()
    application._batch = ("episode",)
    application._exit_code = EXIT_SUCCESS
    application._resident = cast("ResidentSession", _RefusingResident(problem))
    notices: list[str] = []
    shown: list[int] = []
    application._state = cast(
        "StateController",
        SimpleNamespace(show_processing=lambda: shown.append(1), set_notice=notices.append),
    )
    application._mascot = MascotController(lambda: None)
    application._renderer = cast("TerminalRenderer", SimpleNamespace(invalidate=lambda: None))
    return application, notices, shown


def test_auto_over_a_group_already_running_shows_progress_without_a_notice_or_a_refusal() -> None:
    application, notices, shown = _auto_application(
        ControlError(
            "The requested group is already being processed",
            code=ControlErrorCode.ALREADY_PROCESSING,
            answered=True,
        )
    )

    application._prepare_and_run(0)

    assert application._mode is interactive_app._ViewMode.STATE
    assert notices == [""]
    assert shown == [1]
    assert application._exit_code == EXIT_SUCCESS
    assert application._closing_at is None
    assert application._worker is None


def test_auto_over_a_group_held_by_another_client_keeps_its_notice_and_refused_exit() -> None:
    application, notices, shown = _auto_application(
        ControlError(
            "Another client holds one of the requested groups",
            code=ControlErrorCode.CONFLICT,
            reason=RefusalReason.GROUP_RESERVED.value,
            answered=True,
        )
    )

    application._prepare_and_run(0)

    assert shown == []
    assert len(notices) == 1
    assert "Inny panel zajął ten odcinek" in notices[0]
    assert "Another client holds one of the requested groups" not in notices[0]
    assert "Check whether the resident runs" not in notices[0]
    assert application._exit_code == EXIT_REFUSED
    assert application._closing_at is not None


@pytest.mark.parametrize("manual", [False, True])
def test_resident_work_opens_processing_before_starting_its_worker(
    monkeypatch: pytest.MonkeyPatch, manual: bool
) -> None:
    application: interactive_app._InteractiveApplication = _application(interactive_app._ViewMode.HOME)
    application._generation = 0
    application._worker = None
    application._resident = cast("ResidentSession", object())
    notices: list[str] = []
    application._state = cast(
        "StateController", SimpleNamespace(show_processing=lambda: None, set_notice=notices.append)
    )
    application._mascot = MascotController(lambda: None)
    application._renderer = cast("TerminalRenderer", SimpleNamespace(invalidate=lambda: None))
    modes: list[interactive_app._ViewMode] = []

    def make_thread(**_kwargs: object) -> threading.Thread:
        return cast("threading.Thread", SimpleNamespace(start=lambda: modes.append(application._mode)))

    monkeypatch.setattr(threading, "Thread", make_thread)
    if manual:
        application._start_manual_run(cast("ManualRun", object()))
    else:
        application._start_auto()
    assert modes == [interactive_app._ViewMode.STATE]
    assert notices == ["Przygotowanie"]
