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
        lambda frame_provider, key_handler, idle_handler, scroll_handler, **options: SimpleNamespace(
            invalidate=lambda: None
        ),
    )
    application = interactive_app._InteractiveApplication(cast("AppService", SimpleNamespace()))
    application._mode = interactive_app._ViewMode.PREPARING

    frame = application._render_frame(120, 40)

    assert "Panel" in frame.plain
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

    assert "Ekstrakcja" in frame.plain
    assert "episode-01" in frame.plain


def test_manual_progress_rows_form_one_centered_block_sized_to_their_names() -> None:
    groups: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(group_id=name, source=Path(f"{name}.mkv"), artifacts=())
        for name in ("Ao no Hako - 02", "Kusuriya no Hitorigoto - 29 (1080p)")
    )
    prepared = cast(
        "PreparedAutoRun",
        SimpleNamespace(workspace=SimpleNamespace(groups=groups), plan=SimpleNamespace(groups=groups, tasks=())),
    )
    progress = RichRunProgress(prepared, lambda: None)

    frame = interactive_app._auto_content((200, 40), progress, MascotState.EXTRACT, interactive_app._QueueView())

    lines: list[str] = [line.rstrip() for line in frame.plain.splitlines() if " | " in line]
    assert len(lines) == 2
    assert len({line.index("░") for line in lines}) == 1
    assert len({line.index(" | ") for line in lines}) == 1
    left: int = min(len(line) - len(line.lstrip()) for line in lines)
    assert abs(left - (200 - max(len(line) for line in lines))) <= 1
