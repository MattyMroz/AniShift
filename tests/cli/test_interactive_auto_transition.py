from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import AppService
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive.mascot import MascotState
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.run import PreparedAutoRun


def test_auto_preflight_has_no_visible_intermediate_screen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        interactive_app,
        "TerminalRenderer",
        lambda frame_provider, key_handler, idle_handler, scroll_handler: SimpleNamespace(invalidate=lambda: None),
    )
    application = interactive_app._InteractiveApplication(cast("AppService", SimpleNamespace()))
    application._mode = interactive_app._ViewMode.PREPARING

    frame = application._render_frame(120, 40)

    assert "Auto" in frame.plain
    assert "Przygotowanie" not in frame.plain
    assert "Skanowanie" not in frame.plain


def test_first_auto_execution_frame_contains_real_extraction_rows() -> None:
    group = SimpleNamespace(group_id="episode-01", source=Path("episode-01.mkv"), artifacts=())
    prepared = cast(
        "PreparedAutoRun",
        SimpleNamespace(
            workspace=SimpleNamespace(groups=(group,)),
            plan=SimpleNamespace(groups=(group,), tasks=()),
        ),
    )
    progress = RichRunProgress(prepared, lambda: None)

    frame = interactive_app._auto_content((120, 40), progress, MascotState.EXTRACT, interactive_app._QueueView())

    assert "Extracting" in frame.plain
    assert "episode-01" in frame.plain
