from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from anishift.application import AppService
from anishift.cli.interactive import app as interactive_app
from anishift.cli.interactive import covers as covers_module
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.covers import CoverImages
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
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

    anchor: tuple[int, int] | None = _anchor(controller.render(62, 40).plain)

    assert anchor is not None
    assert anchor[1] == _GAP


def test_title_shortens_before_the_slot_goes(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 3)
    controller._subscriptions[0] = {**controller._subscriptions[0], "title": "A Title Long Enough To Be Cut Short"}

    kept: str = controller.render(80, 40).plain
    dropped: str = controller.render(56, 40).plain

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


def test_short_list_centers_the_slot_on_the_cursor_above_the_table(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    _subscriptions(controller, 3)
    controller.handle_key("down")

    frame: str = controller.render(120, 30).plain
    anchor: tuple[int, int] | None = _anchor(frame)

    assert anchor is not None
    assert anchor[0] + (_BOX[1] - 1) // 2 == _row_of(frame, "Show 01")
    assert anchor[0] < _row_of(frame, "Tytuł")


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
    done.wait(10)

    assert threads == ["anishift-cover"] * 3
    assert all(images.image(anilist_id) is not None for anilist_id in (1, 2, 3))
    assert len(threads) == 3


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
