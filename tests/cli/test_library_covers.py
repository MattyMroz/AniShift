from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import test_panel_keys as keys
from PIL import Image, ImageOps

from anishift.application import AppService
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import covers as covers_module
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeSnapshot, NoticeKind
from anishift.cli.interactive.anime_view import render_anime, shown_rows
from anishift.cli.interactive.covers import CoverImages
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
from anishift.cli.interactive.prompts import TerminalRenderer
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_BOX: tuple[int, int] = (19, 13)
_GAP: int = 2


class _Covers:
    def __init__(self, box: tuple[int, int] | None = _BOX) -> None:
        self.shown_box: tuple[int, int] | None = box
        self.asked: list[int] = []
        self.prepared: list[int] = []

    def box(self) -> tuple[int, int] | None:
        return self.shown_box

    def image(self, anilist_id: int) -> NativeImage | None:
        self.asked.append(anilist_id)
        return NativeImage((f"cover-{anilist_id}",), (1.0,), 1.0, _BOX[0], _BOX[1], _BOX[1])

    def prepare(self, anilist_ids: Iterable[int]) -> None:
        self.prepared = list(anilist_ids)


def _keyed(set_id: str, anilist_id: int, series: str, season: int) -> dict[str, object]:
    return {
        "set_id": set_id,
        "name": f"[Grp] {series} - 01",
        "series": series,
        "season": season,
        "episode": 1,
        "anilist_id": anilist_id,
        "entry_title": series if season == 1 else f"{series} Season {season}",
        "title_source": "key",
    }


_LIBRARY: Mapping[str, object] = {
    "library": [
        _keyed("a1", 11, "Alpha", 1),
        _keyed("a2", 12, "Alpha", 2),
        _keyed("b1", 21, "Beta", 1),
        {"set_id": "hand", "name": "[Grp] Gamma - 01"},
    ],
    "covers": [12, 21],
}


@pytest.fixture
def panel(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[StateController, _Covers]]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    covers: _Covers = _Covers()
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace()), lambda: None, covers=cast("CoverImages", covers)
    )
    controller._tab = state_module._Tab.FILES
    controller._connected = True
    controller._snapshot = dict(_LIBRARY)
    controller._episode_info = {11: {}, 12: {}, 21: {}}
    try:
        yield controller, covers
    finally:
        controller.close()
        controller._thread.join(5)


def _subscriptions(controller: StateController, count: int) -> None:
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._snapshot = {"covers": list(range(100, 100 + count))}
    controller._subscriptions = [
        {"subscription_id": f"s{index}", "title": f"Show {index:02}", "anilist_id": 100 + index}
        for index in range(count)
    ]


def _anchor(frame: str) -> tuple[int, int] | None:
    for row, line in enumerate(frame.splitlines()):
        if NATIVE_IMAGE_ANCHOR in line:
            return row, line.index(NATIVE_IMAGE_ANCHOR)
    return None


def _row_of(frame: str, title: str) -> int:
    return next(row for row, line in enumerate(frame.splitlines()) if title in line)


def test_slot_absent_without_sixel(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    covers.shown_box = None

    assert _anchor(controller.render(120, 40).plain) is None
    assert controller.cover() is None


def test_slot_absent_when_the_terminal_is_small(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    covers.shown_box = (40, 13)
    controller._snapshot = {
        **_LIBRARY,
        "library": [_keyed("a1", 12, "A Title Long Enough To Leave No Room For The Cover", 1)],
    }

    assert _anchor(controller.render(60, 40).plain) is None
    assert _anchor(controller.render(120, 14).plain) is None
    assert controller.cover() is None


def test_slot_absent_when_no_listed_title_has_a_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    controller._snapshot = {**_LIBRARY, "covers": []}

    assert _anchor(controller.render(120, 40).plain) is None


def test_frame_without_slot_equals_the_plain_layout(
    panel: tuple[StateController, _Covers], monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, covers = panel
    covers.shown_box = None
    without: str = controller.render(120, 40).plain
    monkeypatch.setattr(controller, "_covers", None)

    assert controller.render(120, 40).plain == without


def test_slot_stands_left_of_the_table_in_blank_cells(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel

    lines: list[str] = controller.render(120, 40).plain.splitlines()
    anchor: tuple[int, int] | None = _anchor("\n".join(lines))

    assert anchor is not None
    row, column = anchor
    cells: list[str] = [line[column : column + _BOX[0]].ljust(_BOX[0]) for line in lines[row : row + _BOX[1]]]
    assert cells[0] == NATIVE_IMAGE_ANCHOR + " " * (_BOX[0] - 1)
    assert all(not text.strip() for text in cells[1:])
    assert lines[_row_of("\n".join(lines), "Alpha")].index("Alpha") > column + _BOX[0]


@pytest.mark.parametrize("columns", [100, 120, 160])
def test_slot_and_table_are_centered_with_the_edge_margin_at_least_the_gap(
    panel: tuple[StateController, _Covers], columns: int
) -> None:
    controller, covers = panel
    _subscriptions(controller, 3)

    frame: str = controller.render(columns, 40).plain
    covers.shown_box = None
    plain: str = controller.render(columns, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)
    left: int = frame.splitlines()[_row_of(frame, "Tytuł")].index("Tytuł")
    alone: int = plain.splitlines()[_row_of(plain, "Tytuł")].index("Tytuł")

    assert anchor is not None
    assert left - (anchor[1] + _BOX[0]) == _GAP + 2
    assert anchor[1] >= _GAP
    assert abs(left - (alone + (_BOX[0] + _GAP) / 2)) <= 1


def test_narrow_terminal_keeps_the_margin_equal_to_the_gap(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 3)
    controller._subscriptions[0] = {**controller._subscriptions[0], "title": "A Title Long Enough To Be Cut Short"}

    anchor: tuple[int, int] | None = _anchor(controller.render(62, 40).plain)

    assert anchor is not None
    assert anchor[1] == _GAP


def test_title_shortens_before_the_slot_goes(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 3)
    controller._subscriptions[0] = {**controller._subscriptions[0], "title": "A Title Long Enough To Be Cut Short"}

    kept: str = controller.render(80, 40).plain
    dropped: str = controller.render(50, 40).plain

    row: str = kept.splitlines()[_row_of(kept, "A Title")]
    assert _anchor(kept) is not None
    assert "A Title Long Enough To Be Cut Short" not in row
    assert "…" in row
    assert _anchor(dropped) is None
    assert "Show 01" in dropped


def test_slot_is_centered_on_the_cursor_row(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _subscriptions(controller, 40)
    for _ in range(12):
        controller.handle_key("down")

    frame: str = controller.render(120, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 12")
    assert controller.cover() is not None
    assert covers.asked == [112]


def test_slot_sticks_to_the_top_on_the_first_row(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 40)

    frame: str = controller.render(120, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] == _row_of(frame, "Tytuł")


def test_slot_sticks_to_the_bottom_on_the_last_row(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 40)
    controller.handle_key("end")

    frame: str = controller.render(120, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + _BOX[1] - 1 == _row_of(frame, "Show 39")


def test_short_list_slot_hangs_from_the_column_header_and_never_above_it(
    panel: tuple[StateController, _Covers],
) -> None:
    controller, _covers = panel
    _subscriptions(controller, 3)
    controller.handle_key("down")

    frame: str = controller.render(120, 30).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] == _row_of(frame, "Tytuł")
    assert anchor[0] + _BOX[1] <= _row_of(frame, "Esc wróć")


def test_hovered_row_moves_the_slot_and_the_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _subscriptions(controller, 40)

    frame: str = controller.render(120, 40, hovered=15).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 15")
    assert controller.cover() is not None
    assert covers.asked == [115]
    assert controller._selected == 0


def test_hover_outside_the_shown_rows_keeps_the_cursor_row(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _subscriptions(controller, 40)

    controller.render(120, 40, hovered=39)
    controller.cover()

    assert covers.asked == [100]


def test_render_prepares_every_listed_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel

    controller.render(120, 40)

    assert sorted(covers.prepared) == [12, 21]


def test_each_season_entry_shows_its_own_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel

    frame: str = controller.render(120, 40).plain
    first: NativeImage | None = controller.cover()
    controller.handle_key("down")
    controller.render(120, 40)
    second: NativeImage | None = controller.cover()
    controller.handle_key("enter")
    controller.render(120, 40)
    opened: NativeImage | None = controller.cover()
    controller.handle_key("escape")
    controller.handle_key("end")
    controller.render(120, 40)

    assert "Alpha Season 2" in frame
    assert first is None
    assert second is not None
    assert second.payloads == ("cover-12",)
    assert opened is not None
    assert opened.payloads == ("cover-12",)
    assert controller.cover() is None
    assert covers.asked == [12, 12]


def test_subscription_row_shows_its_own_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._subscriptions = [
        {"subscription_id": "s1", "title": "Alpha", "anilist_id": 12, "episode_count": 12, "aired": 3, "ready": 1},
        {"subscription_id": "s2", "title": "Beta", "anilist_id": 21, "episode_count": 12, "aired": 3, "ready": 1},
    ]

    controller.handle_key("down")
    controller.render(120, 40)

    assert controller.cover() is not None
    assert covers.asked == [21]


def _processing(controller: StateController, count: int) -> None:
    controller._tab = state_module._Tab.PROGRESS
    controller._snapshot = {
        "covers": list(range(100, 100 + count)),
        "materials": [
            {
                "material_id": f"m{index}",
                "info_hash": f"hash{index}",
                "stage": "download",
                "acquisition_state": "accepted",
                "state": "downloading",
                "progress": 0.5,
                "name": f"file-{index}.mkv",
                "anilist_id": 100 + index,
                "series": f"Show {index:02}",
                "entry_title": f"Show {index:02}",
                "season": 1,
                "episode": 1,
            }
            for index in range(count)
        ],
    }


def test_processing_slot_stands_left_of_the_rows_centered_on_the_cursor(
    panel: tuple[StateController, _Covers],
) -> None:
    controller, covers = panel
    _processing(controller, 20)
    for _ in range(8):
        controller.handle_key("down")

    frame: str = controller.render(140, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 08")
    assert frame.splitlines()[_row_of(frame, "Show 08")].index("Show 08") > anchor[1] + _BOX[0]
    assert controller.cover() is not None
    assert covers.asked == [108]


def test_processing_slot_sticks_to_the_bottom_of_the_blank_rows_on_the_last_row(
    panel: tuple[StateController, _Covers],
) -> None:
    controller, _covers = panel
    _processing(controller, 30)
    controller.handle_key("end")

    frame: str = controller.render(140, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)
    footer: int = next(row for row, line in enumerate(frame.splitlines()) if "historia" in line)

    assert anchor is not None
    assert anchor[0] + _BOX[1] <= footer
    assert anchor[0] + (_BOX[1] - 1) // 2 < _row_of(frame, "Show 29")


def test_processing_hover_moves_the_slot_and_the_cover(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _processing(controller, 20)

    frame: str = controller.render(140, 40, hovered=10).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 10")
    assert controller.cover() is not None
    assert covers.asked == [110]


def _long_library(controller: StateController) -> None:
    controller._tab = state_module._Tab.FILES
    controller._snapshot = {
        "library": [_keyed(f"s{index}", 100 + index, f"Show {index:02}", 1) for index in range(60)],
        "covers": list(range(100, 160)),
    }
    controller._episode_info = {100 + index: {} for index in range(60)}


def _column(frame: str, title: str) -> int:
    return frame.splitlines()[_row_of(frame, title)].index(title)


_LONG_LISTS: tuple[Callable[[StateController], None], ...] = (
    _long_library,
    lambda controller: _subscriptions(controller, 60),
    lambda controller: _processing(controller, 60),
)
_LONG_LIST_IDS: tuple[str, ...] = ("library", "subscriptions", "processing")


@pytest.mark.parametrize("arrange", _LONG_LISTS, ids=_LONG_LIST_IDS)
def test_cursor_scrolled_above_the_view_keeps_the_slot_at_the_top_with_its_cover(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, covers = panel
    arrange(controller)
    top: str = controller.render(120, 40).plain
    for _press in range(4):
        controller.handle_key("down")
    for _step in range(6):
        controller.scroll(1)

    frame: str = controller.render(120, 40).plain
    controller.cover()

    assert "Show 04" not in frame
    assert _anchor(frame) is not None
    assert _anchor(frame) == _anchor(top)
    assert _column(frame, "Show 20") == _column(top, "Show 20")
    assert covers.asked == [104]


@pytest.mark.parametrize("arrange", _LONG_LISTS, ids=_LONG_LIST_IDS)
def test_cursor_scrolled_below_the_view_keeps_the_slot_at_the_bottom_with_its_cover(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, covers = panel
    arrange(controller)
    controller.handle_key("end")
    bottom: str = controller.render(120, 40).plain
    for _step in range(3):
        controller.scroll(-1)

    frame: str = controller.render(120, 40).plain
    controller.cover()

    assert "Show 59" not in frame
    assert _anchor(frame) is not None
    assert _anchor(frame) == _anchor(bottom)
    assert _column(frame, "Show 50") == _column(bottom, "Show 50")
    assert covers.asked == [159]


@pytest.mark.parametrize("arrange", _LONG_LISTS, ids=_LONG_LIST_IDS)
def test_hover_after_scrolling_the_cursor_out_of_view_moves_the_slot_and_the_cover(
    panel: tuple[StateController, _Covers], arrange: Callable[[StateController], None]
) -> None:
    controller, covers = panel
    arrange(controller)
    for _step in range(6):
        controller.scroll(1)

    frame: str = controller.render(120, 40, hovered=25).plain
    anchor: tuple[int, int] | None = _anchor(frame)
    controller.cover()

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 25")
    assert covers.asked == [125]


def _anime_titles(cursor: int, offset: int) -> AnimeSnapshot:
    items: tuple[AnimeRow, ...] = tuple(AnimeRow(str(100 + index), f"Show {index:02}") for index in range(60))
    return AnimeSnapshot(
        AnimeScreen.TITLES, "", items, cursor=cursor, offset=offset, fill=True, highlight=cursor, cover=_BOX
    )


def _anime_frame(cursor: int, offset: int) -> str:
    return render_anime(_anime_titles(cursor, offset), 120, 40, 0.0).text.plain


def test_anime_results_with_the_cursor_out_of_view_keep_the_slot_at_the_cursor_edge() -> None:
    last: int = 60 - shown_rows(_anime_titles(0, 0), 120, 40)
    top: str = _anime_frame(0, 0)
    above: str = _anime_frame(4, 18)
    bottom: str = _anime_frame(59, last)
    below: str = _anime_frame(59, last - 9)

    assert _anchor(above) is not None
    assert _anchor(above) == _anchor(top)
    assert _column(above, "Show 20") == _column(top, "Show 20")
    assert _anchor(below) is not None
    assert _anchor(below) == _anchor(bottom)
    assert _column(below, "Show 50") == _column(bottom, "Show 50")


def test_processing_slot_and_rows_are_centered_as_one_block(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _processing(controller, 3)

    frame: str = controller.render(140, 40).plain
    covers.shown_box = None
    plain: str = controller.render(140, 40).plain
    anchor: tuple[int, int] | None = _anchor(frame)
    left: int = frame.splitlines()[_row_of(frame, "Show 00")].index("Show 00")
    alone: int = plain.splitlines()[_row_of(plain, "Show 00")].index("Show 00")

    assert anchor is not None
    assert anchor[1] >= _GAP
    assert abs(left - (alone + (_BOX[0] + _GAP) / 2)) <= 2


def test_processing_without_a_slot_equals_the_plain_layout(
    panel: tuple[StateController, _Covers], monkeypatch: pytest.MonkeyPatch
) -> None:
    controller, covers = panel
    _processing(controller, 3)
    covers.shown_box = None
    without: str = controller.render(140, 40).plain
    monkeypatch.setattr(controller, "_covers", None)

    assert controller.render(140, 40).plain == without
    assert _anchor(without) is None


def _library_titles(controller: StateController) -> None:
    controller._tab = state_module._Tab.FILES


def _library_episodes(controller: StateController) -> None:
    controller._tab = state_module._Tab.FILES
    controller.handle_key("down")
    controller.handle_key("enter")


def _many_subscriptions(controller: StateController) -> None:
    _subscriptions(controller, 30)
    for _press in range(12):
        controller.handle_key("down")


@pytest.mark.parametrize(
    "arrange",
    [
        _library_titles,
        _library_episodes,
        lambda controller: _subscriptions(controller, 3),
        _many_subscriptions,
        lambda controller: _processing(controller, 3),
    ],
)
@pytest.mark.parametrize(("columns", "hovered"), [(120, None), (90, 1), (200, 2)])
def test_covers_switched_off_and_on_give_the_frame_without_a_slot_and_back(
    panel: tuple[StateController, _Covers],
    monkeypatch: pytest.MonkeyPatch,
    arrange: Callable[[StateController], None],
    columns: int,
    hovered: int | None,
) -> None:
    controller, covers = panel
    arrange(controller)
    with monkeypatch.context() as patched:
        patched.setattr(controller, "_covers", None)
        plain: str = controller.render(columns, 40, hovered=hovered).plain
    on: str = controller.render(columns, 40, hovered=hovered).plain
    covers.shown_box = None
    off: str = controller.render(columns, 40, hovered=hovered).plain
    covers.shown_box = _BOX
    again: str = controller.render(columns, 40, hovered=hovered).plain

    assert off == plain
    assert again == on


@pytest.mark.parametrize(
    "name",
    ["titles", "entries", "episodes", "u08", "subscriptions", "processing_download", "library", "library_episodes"],
)
def test_every_panel_view_without_covers_equals_its_frame_without_a_slot(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    monkeypatch.setattr(StateController, "_cached_covers", lambda _self, ids: tuple(7 for _item in ids))
    probe: keys._Probe = keys._FIXTURES[name](monkeypatch)
    controller: StateController = probe.panel
    covers: _Covers = _Covers()
    try:
        plain: str = controller.render(160, 40).plain
        controller._covers = cast("CoverImages", covers)
        on: str = controller.render(160, 40).plain
        covers.shown_box = None
        off: str = controller.render(160, 40).plain
        covers.shown_box = _BOX
        again: str = controller.render(160, 40).plain
    finally:
        controller.close()
        controller._thread.join(5)

    assert _anchor(on) is not None
    assert off == plain
    assert again == on


class _CellRenderer:
    native_mascot_size: tuple[int, int] | None = None
    native_mascot: NativeImage | None = None
    native_cell: tuple[int, int] | None = (10, 20)
    animation_phase: int = 0

    def __init__(self, *_arguments: object, **_options: object) -> None:
        self.redraws: int = 0

    def invalidate(self) -> None:
        self.redraws += 1


def test_k_in_the_panel_gives_the_frame_without_a_slot_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interactive_app, "TerminalRenderer", _CellRenderer)
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    preferences: SimpleNamespace = SimpleNamespace(show_covers=True)
    service: SimpleNamespace = SimpleNamespace(
        settings_snapshot=lambda: preferences,
        update_setting=lambda setting_id, value: setattr(preferences, setting_id, value),
    )
    application: interactive_app._InteractiveApplication = interactive_app._InteractiveApplication(
        cast("AppService", service)
    )
    application._mode = interactive_app._ViewMode.STATE
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace()), lambda: None, covers=application._covers
    )
    application._state = controller
    _subscriptions(controller, 3)
    try:
        on: str = application._render_frame(120, 40).plain
        application._handle_key("text:k")
        off: str = application._render_frame(120, 40).plain
        controller._covers = None
        plain: str = application._render_frame(120, 40).plain
        controller._covers = application._covers
        application._handle_key("text:k")
        again: str = application._render_frame(120, 40).plain
    finally:
        controller.close()
        controller._thread.join(5)

    assert _anchor(on) is not None
    assert off == plain
    assert again == on


def test_processing_history_has_no_slot(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _processing(controller, 3)
    controller._history_open = True

    assert _anchor(controller.render(140, 40).plain) is None


def _one_title(controller: StateController, episodes: int, title: str = "Alpha") -> None:
    controller._snapshot = {
        "library": [{**_keyed(f"x{number}", 12, title, 1), "episode": number} for number in range(1, episodes + 1)],
        "covers": [12],
    }
    controller.handle_key("enter")


def test_one_title_slot_stands_still_while_the_cursor_and_hover_move(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    _one_title(controller, 20)

    first: tuple[int, int] | None = _anchor(controller.render(120, 40).plain)
    for _press in range(15):
        controller.handle_key("down")
    moved: tuple[int, int] | None = _anchor(controller.render(120, 40).plain)
    hovered: str = controller.render(120, 40, hovered=2).plain
    rows: list[int] = [_row_of(hovered, f"S01E{number:02}") for number in range(1, 21)]

    assert first is not None
    assert first == moved == _anchor(hovered)
    assert abs(first[0] + (_BOX[1] - 1) / 2 - (rows[0] + rows[-1]) / 2) <= 1
    assert controller.cover() is not None
    assert covers.asked[-1] == 12


def test_one_title_with_one_episode_and_a_long_name_keeps_its_slot(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _one_title(controller, 1, "The Exiled Heavy Knight Knows How to Game the System")

    frame: str = controller.render(120, 30).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] == _row_of(frame, "Tytuł")
    assert anchor[0] + _BOX[1] <= _row_of(frame, "Esc wróć")
    assert controller.cover() is not None


_LONG_EPISODE: str = "A Much Longer Episode Title Than Usual"


def _subscription_episodes(cursor: int, columns: int) -> list[str]:
    items: tuple[AnimeRow, ...] = tuple(
        AnimeRow(f"e{index}", f"{_LONG_EPISODE} {index}", number=str(index), date="29.11.2026", status="Gotowe")
        for index in (1, 2, 3)
    )
    snapshot: AnimeSnapshot = AnimeSnapshot(
        AnimeScreen.EPISODES,
        "",
        items,
        cursor=cursor,
        crumbs=("Subskrypcje", "Show"),
        global_status="E9 · 29.11 13:30 · odcinki 8/13 · gotowe 0",
        status_kind=NoticeKind.INFO,
        cover=_BOX,
    )
    return render_anime(snapshot, columns, 40, 0.0).text.plain.splitlines()


@pytest.mark.parametrize("columns", [140, 200])
def test_subscription_episodes_keep_crumbs_and_summary_out_of_the_slot_and_centered_on_the_block(
    columns: int,
) -> None:
    lines: list[str] = _subscription_episodes(0, columns)
    frame: str = "\n".join(lines)
    anchor: tuple[int, int] | None = _anchor(frame)
    crumbs: int = _row_of(frame, "Subskrypcje")
    summary: int = _row_of(frame, "gotowe 0")
    header: int = _row_of(frame, "Tytuł")

    assert anchor is not None
    assert anchor[0] == header
    assert crumbs < summary < anchor[0]
    assert _anchor("\n".join(_subscription_episodes(2, columns))) == anchor
    right: int = max(len(line.rstrip()) for line in lines[header : header + 4])
    for row in (crumbs, summary):
        text: str = lines[row].strip()
        middle: float = lines[row].index(text) + len(text) / 2
        assert abs(middle - (anchor[1] + right) / 2) <= 1


def _cover_file(directory: Path, anilist_id: int) -> None:
    Image.new("RGB", (460, 636), (200, 30, 30)).save(directory / f"{anilist_id}.jpg", "JPEG")


def test_prepared_covers_encode_off_the_render_thread_and_hit_at_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    threads: list[str] = []
    encode = covers_module.cover_image

    def recorded(path: Path, cell: tuple[int, int]) -> NativeImage | None:
        threads.append(threading.current_thread().name)
        return encode(path, cell)

    monkeypatch.setattr(covers_module, "cover_image", recorded)
    for anilist_id in (1, 2, 3):
        _cover_file(tmp_path, anilist_id)
    done: threading.Event = threading.Event()
    images: CoverImages = CoverImages(
        lambda: done.set() if len(threads) == 3 else None, lambda: (10, 20), lambda: tmp_path
    )

    images.prepare([1, 2, 3])
    worker: threading.Thread | None = images._worker
    done.wait(10)
    if worker is not None:
        worker.join(10)

    assert threads == ["anishift-cover"] * 3
    assert all(images.image(anilist_id) is not None for anilist_id in (1, 2, 3))
    assert len(threads) == 3
    assert images._worker is None


def test_covers_switched_off_leave_the_table_centered_without_a_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    shown: list[bool] = [False]
    images: CoverImages = CoverImages(lambda: None, lambda: (10, 20), lambda: tmp_path, shown=lambda: shown[0])
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace()), lambda: None, covers=images
    )
    controller._tab = state_module._Tab.FILES
    controller._snapshot = dict(_LIBRARY)
    try:
        off: str = controller.render(120, 40).plain
        monkeypatch.setattr(controller, "_covers", None)
        plain: str = controller.render(120, 40).plain
        monkeypatch.setattr(controller, "_covers", images)
        shown[0] = True
        on: str = controller.render(120, 40).plain
        worker: threading.Thread | None = images._worker
        if worker is not None:
            worker.join(10)
    finally:
        controller.close()
        controller._thread.join(5)

    assert images.box() is not None
    assert off == plain
    assert _anchor(off) is None
    assert _anchor(on) is not None


def test_panel_reads_the_covers_setting_again_after_settings_close() -> None:
    application: interactive_app._InteractiveApplication = object.__new__(interactive_app._InteractiveApplication)
    preferences: SimpleNamespace = SimpleNamespace(show_covers=True)
    application._service = cast("AppService", SimpleNamespace(settings_snapshot=lambda: preferences))
    application._lock = threading.Lock()
    application._settings = None
    application._resident = None
    application._show_covers = None

    before: bool = application._covers_shown()
    preferences.show_covers = False
    cached: bool = application._covers_shown()
    application._close_settings()

    assert (before, cached, application._covers_shown()) == (True, True, False)


def test_k_saves_the_flipped_covers_setting_and_redraws_the_panel() -> None:
    application: interactive_app._InteractiveApplication = object.__new__(interactive_app._InteractiveApplication)
    preferences: SimpleNamespace = SimpleNamespace(show_covers=True)
    saved: list[tuple[str, object]] = []
    redraws: list[None] = []

    def update_setting(setting_id: str, value: object) -> None:
        saved.append((setting_id, value))
        setattr(preferences, setting_id, value)

    application._service = cast(
        "AppService", SimpleNamespace(settings_snapshot=lambda: preferences, update_setting=update_setting)
    )
    application._state = cast(
        "StateController", SimpleNamespace(handle_key=lambda _key: state_module.StateResult.COVERS)
    )
    application._renderer = cast("TerminalRenderer", SimpleNamespace(invalidate=lambda: redraws.append(None)))
    application._lock = threading.Lock()
    application._show_covers = None

    application._handle_state_key("text:k")
    hidden: bool = application._covers_shown()
    application._handle_state_key("text:k")

    assert saved == [("show_covers", False), ("show_covers", True)]
    assert (hidden, application._covers_shown(), len(redraws)) == (False, True, 2)


def test_asked_cover_jumps_the_prepared_queue(tmp_path: Path) -> None:
    images: CoverImages = CoverImages(lambda: None, lambda: (10, 20), lambda: tmp_path)
    images._worker = cast("threading.Thread", SimpleNamespace())

    images.prepare([1, 2, 3])
    assert images.image(3) is None

    assert list(images._queue)[:1] == [3]


def test_cover_is_scaled_into_the_fixed_slot_and_a_bad_file_gives_none(tmp_path: Path) -> None:
    _cover_file(tmp_path, 21)
    (tmp_path / "22.jpg").write_bytes(b"broken")

    image: NativeImage | None = covers_module.cover_image(tmp_path / "21.jpg", (10, 20))

    assert image is not None
    assert (image.cell_columns, image.cell_rows) == _BOX
    assert image.payloads[0].startswith('\x1bP9;1;0q"1;1;190;260')
    assert covers_module.cover_image(tmp_path / "22.jpg", (10, 20)) is None
    assert covers_module.cover_image(tmp_path / "missing.jpg", (10, 20)) is None


def _striped(size: tuple[int, int]) -> Image.Image:
    picture: Image.Image = Image.new("RGB", size, (200, 30, 30))
    picture.paste((30, 200, 30), (0, 0, size[0], 20))
    picture.paste((30, 30, 200), (0, size[1] - 20, size[0], size[1]))
    return picture


def _channel(picture: Image.Image, point: tuple[int, int], index: int) -> int:
    pixel: object = picture.getpixel(point)
    assert isinstance(pixel, tuple)
    return int(pixel[index])


def test_a_typical_cover_fills_the_slot_cropping_more_of_the_bottom_than_the_top() -> None:
    slot: tuple[int, int] = (190, 260)
    filled: Image.Image = covers_module.filled_cover(_striped((460, 665)), slot).convert("RGBA")

    assert filled.size == slot
    assert filled.getchannel("A").getextrema() == (255, 255)
    assert _channel(filled, (95, 0), 1) > 150
    assert _channel(filled, (95, 259), 2) < 80


@pytest.mark.parametrize("size", [(460, 460), (300, 650)])
def test_a_cover_far_from_the_slot_shape_shows_whole_on_a_blurred_fill(size: tuple[int, int]) -> None:
    slot: tuple[int, int] = (190, 260)
    picture: Image.Image = _striped(size)
    whole: Image.Image = ImageOps.contain(picture, slot, Image.Resampling.LANCZOS)
    filled: Image.Image = covers_module.filled_cover(picture, slot).convert("RGBA")
    left: int = (slot[0] - whole.width) // 2
    top: int = (slot[1] - whole.height) // 2

    assert max(size[0] / size[1], 190 / 260) / min(size[0] / size[1], 190 / 260) - 1 > covers_module.CROP_TOLERANCE
    assert filled.getchannel("A").getextrema() == (255, 255)
    assert filled.crop((left, top, left + whole.width, top + whole.height)).convert("RGB").tobytes() == whole.tobytes()
    assert 0 < _channel(filled, (0, 0), 0) < 200
