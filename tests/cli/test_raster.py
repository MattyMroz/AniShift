from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import terminal_model as model
import test_interactive_mascot_native as mascots
import test_library_covers as layouts
from PIL import Image
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.text import Text

import anishift.cli.interactive.prompts as prompts_module
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeSnapshot
from anishift.cli.interactive.anime_view import render_anime
from anishift.cli.interactive.app import _auto_content, _home_content, _QueueView
from anishift.cli.interactive.covers import CoverImages, cover_box
from anishift.cli.interactive.mascot import MascotState
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_BOX: tuple[int, int] = (19, 13)


class _Covers:
    def __init__(self) -> None:
        self.shown_box: tuple[int, int] | None = _BOX

    def box(self) -> tuple[int, int] | None:
        return self.shown_box

    def image(self, anilist_id: int) -> NativeImage | None:
        return model.image(anilist_id, *_BOX)

    def prepare(self, anilist_ids: Iterable[int]) -> None:
        del anilist_ids


@pytest.fixture
def panel(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[StateController, _Covers]]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    covers: _Covers = _Covers()
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace()), lambda: None, covers=cast("CoverImages", covers)
    )
    controller._tab = state_module._Tab.FILES
    controller._connected = True
    controller._snapshot = dict(layouts._LIBRARY)
    controller._episode_info = {11: {}, 12: {}, 21: {}}
    try:
        yield controller, covers
    finally:
        controller.close()
        controller._thread.join(5)


def _terminal(controller: StateController, hover: list[int | None] | None = None) -> model.Terminal:
    pointed: list[int | None] = hover if hover is not None else [None]
    terminal: model.Terminal = model.Terminal(
        lambda columns, rows: controller.render(columns, rows, hovered=pointed[0]), controller.cover
    )
    terminal.paint()
    return terminal


def _walk(terminal: model.Terminal, controller: StateController, keys: Iterable[str]) -> None:
    for key in keys:
        controller.handle_key(key)
        terminal.paint()
        assert terminal.shown is not None


_LISTS: dict[str, Callable[[StateController], None]] = {
    "library": layouts._long_library,
    "library_episodes": lambda controller: layouts._one_title(controller, 30),
    "subscriptions": lambda controller: layouts._subscriptions(controller, 30),
    "processing": lambda controller: layouts._processing(controller, 30),
}


@pytest.mark.parametrize("arrange", _LISTS.values(), ids=_LISTS.keys())
def test_walking_the_cursor_down_and_up_keeps_every_write_whole(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, _covers = panel
    arrange(controller)
    terminal: model.Terminal = _terminal(controller)

    _walk(terminal, controller, ["down"] * 12 + ["end"] + ["up"] * 14 + ["home", "pagedown", "pageup"])


@pytest.mark.parametrize("arrange", _LISTS.values(), ids=_LISTS.keys())
def test_scrolling_the_cursor_out_of_view_keeps_the_cover_whole(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, _covers = panel
    arrange(controller)
    terminal: model.Terminal = _terminal(controller)
    for step in [1] * 12 + [-1] * 12:
        controller.scroll(step)
        terminal.paint()

        assert terminal.shown is not None


def test_hover_moving_over_rows_and_leaving_keeps_every_write_whole(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    layouts._subscriptions(controller, 30)
    hover: list[int | None] = [None]
    terminal: model.Terminal = _terminal(controller, hover)

    for row in [*range(0, 20), None, 25, 3, None]:
        hover[0] = row
        terminal.paint()

        assert terminal.shown is not None


def test_ending_processing_rows_and_moving_progress_keep_every_write_whole(
    panel: tuple[StateController, _Covers],
) -> None:
    controller, _covers = panel
    layouts._processing(controller, 24)
    for _press in range(10):
        controller.handle_key("down")
    terminal: model.Terminal = _terminal(controller)
    materials: list[dict[str, object]] = layouts._materials(controller)
    for step in range(20):
        for index, item in enumerate(materials):
            item["progress"] = 0.03 * ((index + step) % 30)
        terminal.paint()
        del materials[(step * 7) % len(materials)]
        terminal.paint()


def test_progress_beside_a_standing_cover_never_draws_it_again(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    layouts._processing(controller, 20)
    for _press in range(10):
        controller.handle_key("down")
    terminal: model.Terminal = _terminal(controller)
    drawn: int = terminal.screen.draws
    for step in range(10):
        for index, item in enumerate(layouts._materials(controller)):
            item["progress"] = 0.07 * ((index + step) % 9)
            item["series"] = item["entry_title"] = f"{'Wohs' if step % 2 else 'Show'} {index:02}"
        terminal.paint()

    assert terminal.screen.draws == drawn


def test_delete_question_and_back_leave_no_old_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    layouts._long_library(controller)
    for _press in range(5):
        controller.handle_key("down")
    terminal: model.Terminal = _terminal(controller)

    controller._library_confirm = ("s4", "s5")
    terminal.paint()
    asked: model.Shown | None = terminal.shown
    controller._library_confirm = None
    controller.handle_key("up")
    terminal.paint()

    assert asked is None
    assert terminal.shown is not None


def test_covers_switched_off_and_on_leave_no_old_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    layouts._subscriptions(controller, 30)
    terminal: model.Terminal = _terminal(controller)
    for _round in range(2):
        covers.shown_box = None
        terminal.paint()
        hidden: model.Shown | None = terminal.shown
        covers.shown_box = _BOX
        controller.handle_key("down")
        terminal.paint()

        assert hidden is None
        assert terminal.shown is not None


def test_a_view_without_a_cover_and_back_leave_no_old_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    layouts._long_library(controller)
    elsewhere: list[bool] = [False]
    terminal: model.Terminal = model.Terminal(
        lambda columns, rows: Text("Ustawienia\n" * (rows - 1)) if elsewhere[0] else controller.render(columns, rows),
        controller.cover,
    )
    terminal.paint()
    for key in ("down", "down", "up"):
        elsewhere[0] = not elsewhere[0]
        controller.handle_key(key)
        terminal.paint()


@pytest.mark.parametrize("arrange", _LISTS.values(), ids=_LISTS.keys())
def test_resizing_the_terminal_keeps_the_cover_in_its_slot(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, _covers = panel
    arrange(controller)
    terminal: model.Terminal = _terminal(controller)
    for columns, rows in ((110, 40), (170, 46), (96, 32), (140, 40)):
        controller.handle_key("down")
        terminal.resize(columns, rows)

        assert terminal.shown is not None


def _anime(cursor: int, offset: int, columns: int, rows: int) -> Text:
    items: tuple[AnimeRow, ...] = tuple(AnimeRow(str(100 + index), f"Show {index:02}") for index in range(60))
    snapshot: AnimeSnapshot = AnimeSnapshot(
        AnimeScreen.TITLES, "", items, cursor=cursor, offset=offset, fill=True, highlight=cursor, cover=_BOX
    )
    return render_anime(snapshot, columns, rows, 0.0).text


def test_anime_results_with_the_cursor_walking_and_out_of_view_keep_every_write_whole() -> None:
    view: list[int] = [0, 0]
    terminal: model.Terminal = model.Terminal(
        lambda columns, rows: _anime(view[0], view[1], columns, rows), lambda: model.image(100 + view[0], *_BOX)
    )
    for cursor, offset in [(0, 0), (1, 0), (2, 0), (12, 0), (4, 18), (40, 18), (59, 30), (59, 20), (3, 0)]:
        view[:] = [cursor, offset]
        terminal.paint()

        assert terminal.shown is not None


def test_mascot_animation_and_the_panel_keep_every_write_whole(
    panel: tuple[StateController, _Covers], monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, _covers = panel
    layouts._subscriptions(controller, 30)
    clock: list[float] = [0.0]
    monkeypatch.setattr(prompts_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    mascot: NativeImage = NativeImage(
        tuple(model.sixel(f"mascot{index}", 18, 10) for index in range(3)), (0.1, 0.1, 0.1), 0.3, 18, 10, 10
    )
    view: list[str] = ["home"]
    progress: RichRunProgress = cast("RichRunProgress", mascots._Progress())

    def frame(columns: int, rows: int) -> Text:
        if view[0] == "home":
            return _home_content(columns, rows, 0, MascotState.IDLE, native_size=(18, 10))
        if view[0] == "auto":
            return _auto_content((columns, rows), progress, MascotState.TTS, _QueueView(), native_size=(18, 10))
        return controller.render(columns, rows)

    terminal: model.Terminal = model.Terminal(
        frame,
        lambda: controller.cover() if view[0] == "panel" else mascot,
        nudge=lambda image: 2 if image is mascot else 0,
        elapsed=lambda: clock[0],
    )
    terminal.renderer._native_mascot = mascot
    terminal.renderer._native_animation_started_at = 0.0
    for step, shown in enumerate(["home"] * 4 + ["panel"] * 3 + ["auto"] * 4 + ["home"] * 2 + ["panel", "auto"]):
        clock[0] = step * 0.1
        view[0] = shown
        terminal.paint()

        assert terminal.shown is not None
    drawn: int = terminal.screen.draws
    terminal.paint()
    assert terminal.screen.draws == drawn


def test_entering_a_tab_shows_each_cover_in_its_first_frame(
    panel: tuple[StateController, _Covers], tmp_path: Path
) -> None:
    controller, _covers = panel
    for anilist_id in range(100, 130):
        Image.new("RGB", (460, 636), (anilist_id, 30, 30)).save(tmp_path / f"{anilist_id}.jpg", "JPEG")
    controller._covers = CoverImages(lambda: model.CELL, lambda: tmp_path)
    layouts._subscriptions(controller, 30)

    first: str = controller.render(140, 40).plain
    shown: NativeImage | None = controller.cover()
    controller.handle_key("down")
    controller.render(140, 40)

    assert layouts._anchor(first) is not None
    assert shown is not None
    assert (shown.cell_columns, shown.cell_rows) == cover_box(model.CELL)
    assert controller.cover() is not None


def test_exit_leaves_no_image_pixel_on_the_alternate_screen() -> None:
    stream: StringIO = StringIO()
    output: Vt100_Output = Vt100_Output(stream, lambda: Size(rows=model.SIZE[1], columns=model.SIZE[0]), term="xterm")
    with create_pipe_input() as pipe, create_app_session(input=pipe, output=output):
        renderer: TerminalRenderer = TerminalRenderer(
            lambda _columns, _rows: Text(f"\n\n   {NATIVE_IMAGE_ANCHOR}"),
            lambda _key: renderer.exit(),
            image_provider=lambda: model.image("cover", *_BOX),
            use_mascot=False,
        )
        renderer._application.run(pre_run=lambda: pipe.send_text("x"))
    screen: model.VtScreen = model.VtScreen(*model.SIZE)

    screen.feed(stream.getvalue().partition("\x1b[?1049l")[0])

    assert screen.draws == 1
    assert not any(any(row) for row in screen.pixels)
