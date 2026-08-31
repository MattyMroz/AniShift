from __future__ import annotations

from typing import cast

import pytest
from rich.text import Text

from anishift.cli.interactive.app import _auto_content, _fit_frame, _QueueView
from anishift.cli.interactive.mascot import MascotState
from anishift.cli.interactive.progress import RichRunProgress

_ROWS = 46
_TERMINAL = (120, 40)


class FakeProgress:
    def __init__(self, row_count: int = _ROWS, active_row: int = 0) -> None:
        self.row_count = row_count
        self.active_row = active_row

    def render(self, columns: int, *, offset: int = 0, limit: int | None = None) -> Text:
        del columns
        end = self.row_count if limit is None else offset + limit
        rows = tuple(f"plik-{index:02d}" for index in range(offset, min(end, self.row_count)))
        return Text("\n".join(rows))


def _frame(progress: FakeProgress, view: _QueueView, size: tuple[int, int] = _TERMINAL) -> str:
    content = _auto_content(size, cast("RichRunProgress", progress), MascotState.TTS, view)
    return _fit_frame(content, "1.0.0", "C:\\work", size[0], size[1]).plain


def _shown(frame: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in frame.split("\n") if line.strip().startswith("plik-"))


def test_a_queue_longer_than_the_terminal_still_fits_the_frame() -> None:
    frame = _frame(FakeProgress(), _QueueView())

    assert len(frame.split("\n")) == _TERMINAL[1]


def test_hidden_rows_below_are_announced_instead_of_cut() -> None:
    view = _QueueView()
    frame = _frame(FakeProgress(), view)

    assert "poza widokiem" in frame


def test_nothing_is_announced_when_the_whole_queue_fits() -> None:
    frame = _frame(FakeProgress(row_count=3), _QueueView())

    assert "poza widokiem" not in frame
    assert len(_shown(frame)) == 3


def test_the_view_starts_on_the_active_work() -> None:
    progress = FakeProgress(active_row=30)
    view = _QueueView()

    assert "plik-30" in _frame(progress, view)


def test_scrolling_down_reveals_later_files() -> None:
    progress = FakeProgress()
    view = _QueueView()
    _frame(progress, view)
    view.move(-view.visible, progress.row_count)
    before = _shown(_frame(progress, view))
    view.move(3, progress.row_count)

    assert _shown(_frame(progress, view)) != before


def test_scrolling_keeps_every_row_in_its_original_order() -> None:
    progress = FakeProgress()
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    shown = _shown(_frame(progress, view))

    assert shown == tuple(sorted(shown))


def test_home_pins_the_top_and_end_returns_to_the_live_work() -> None:
    progress = FakeProgress(active_row=40)
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    top = _shown(_frame(progress, view))
    view.navigate("end", progress.row_count)
    live = _shown(_frame(progress, view))

    assert top[0] == "plik-00"
    assert "plik-40" in live


def test_the_last_file_is_reachable_once_the_work_is_over() -> None:
    progress = FakeProgress(active_row=_ROWS - 1)
    view = _QueueView()
    _frame(progress, view)
    view.navigate("end", progress.row_count)

    assert _shown(_frame(progress, view))[-1] == f"plik-{_ROWS - 1:02d}"


def test_a_manual_scroll_stops_the_view_from_following_the_work() -> None:
    progress = FakeProgress(active_row=0)
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    progress.active_row = 40
    frame = _frame(progress, view)

    assert not view.following
    assert "plik-40" not in frame


def test_returning_to_the_end_resumes_following_the_work() -> None:
    progress = FakeProgress(active_row=0)
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    view.navigate("end", progress.row_count)
    progress.active_row = 40

    assert view.following
    assert "plik-40" in _frame(progress, view)


@pytest.mark.parametrize("key", ["up", "down", "pageup", "pagedown", "home", "end"])
def test_every_scroll_key_keeps_the_offset_inside_the_queue(key: str) -> None:
    progress = FakeProgress()
    view = _QueueView()
    _frame(progress, view)
    for _ in range(3):
        view.navigate(key, progress.row_count)

    assert 0 <= view.offset <= progress.row_count - view.visible


def test_a_page_moves_further_than_a_single_step() -> None:
    progress = FakeProgress()
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    view.navigate("down", progress.row_count)
    stepped = view.offset
    view.navigate("home", progress.row_count)
    view.navigate("pagedown", progress.row_count)

    assert view.offset > stepped


def test_the_wheel_moves_the_queue_without_leaving_the_view() -> None:
    progress = FakeProgress()
    view = _QueueView()
    _frame(progress, view)
    view.navigate("home", progress.row_count)
    view.move(3, progress.row_count)

    assert view.offset == 3


def test_a_line_wider_than_the_terminal_cannot_wrap_the_frame() -> None:
    content = Text("x" * 400)
    frame = _fit_frame(content, "1.0.0", "C:\\work", 80, 10)

    assert all(len(line) <= 80 for line in frame.plain.split("\n"))


def test_a_short_terminal_still_shows_queue_rows() -> None:
    frame = _frame(FakeProgress(), _QueueView(), size=(120, 12))

    assert _shown(frame)
