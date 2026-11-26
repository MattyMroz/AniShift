from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image

from anishift.cli.interactive import covers as covers_module
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.covers import CoverImages
from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, NativeImage
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_BOX: tuple[int, int] = (19, 12)


class _Covers:
    def __init__(self, box: tuple[int, int] | None = _BOX) -> None:
        self.shown_box: tuple[int, int] | None = box
        self.asked: list[int] = []

    def box(self) -> tuple[int, int] | None:
        return self.shown_box

    def image(self, anilist_id: int) -> NativeImage | None:
        self.asked.append(anilist_id)
        return NativeImage((f"cover-{anilist_id}",), (1.0,), 1.0, _BOX[0], _BOX[1], _BOX[1])


def _keyed(set_id: str, anilist_id: int, series_id: int, series: str, season: int) -> dict[str, object]:
    return {
        "set_id": set_id,
        "name": f"[Grp] {series} - 01",
        "series": series,
        "season": season,
        "episode": 1,
        "anilist_id": anilist_id,
        "series_id": series_id,
        "title_source": "key",
    }


_LIBRARY: Mapping[str, object] = {
    "library": [
        _keyed("a1", 11, 10, "Alpha", 1),
        _keyed("a2", 12, 10, "Alpha", 2),
        _keyed("b1", 21, 20, "Beta", 1),
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


def _anchor(frame: str) -> tuple[int, int] | None:
    for row, line in enumerate(frame.splitlines()):
        if NATIVE_IMAGE_ANCHOR in line:
            return row, line.index(NATIVE_IMAGE_ANCHOR)
    return None


def test_slot_absent_without_sixel(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    covers.shown_box = None

    assert _anchor(controller.render(120, 40).plain) is None
    assert controller.cover() is None


def test_slot_absent_when_the_terminal_is_small(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel
    covers.shown_box = (40, 12)
    controller._snapshot = {
        **_LIBRARY,
        "library": [_keyed("a1", 12, 10, "A Title Long Enough To Leave No Room For The Cover", 1)],
    }

    assert _anchor(controller.render(60, 40).plain) is None
    assert _anchor(controller.render(120, 18).plain) is None
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


def test_slot_cells_stay_blank_in_the_frame(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel

    lines: list[str] = controller.render(120, 40).plain.splitlines()
    anchor: tuple[int, int] | None = _anchor("\n".join(lines))

    assert anchor is not None
    row, column = anchor
    cells: list[str] = [line[column : column + _BOX[0]].ljust(_BOX[0]) for line in lines[row : row + _BOX[1]]]
    assert cells[0] == NATIVE_IMAGE_ANCHOR + " " * (_BOX[0] - 1)
    assert all(not text.strip() for text in cells[1:])
    assert "Alpha" in lines[row + 1]


def test_render_neither_reads_files_nor_encodes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    monkeypatch.setattr(covers_module, "cover_image", lambda *_args: pytest.fail("render encoded a cover"))
    images: CoverImages = CoverImages(lambda: None, lambda: (10, 20), lambda: tmp_path)
    controller: StateController = StateController(
        cast("ResidentSession", SimpleNamespace()), lambda: None, covers=images
    )
    controller._tab = state_module._Tab.FILES
    controller._snapshot = dict(_LIBRARY)
    try:
        frame: str = controller.render(120, 40).plain
    finally:
        controller.close()
        controller._thread.join(5)

    assert _anchor(frame) is not None
    assert images._worker is None


def test_title_cover_is_the_newest_set_entry(panel: tuple[StateController, _Covers]) -> None:
    controller, covers = panel

    controller.render(120, 40)
    first: NativeImage | None = controller.cover()
    controller.handle_key("enter")
    controller.render(120, 40)
    opened: NativeImage | None = controller.cover()
    controller.handle_key("escape")
    controller.handle_key("end")
    controller.render(120, 40)

    assert first is not None
    assert first.payloads == ("cover-12",)
    assert opened is not None
    assert opened.payloads == ("cover-12",)
    assert controller.cover() is None
    assert covers.asked == [12, 12]


_LONG: str = "As a Reincarnated Aristocrat, I'll Use My Appraisal Skill to Rise in the World"


@pytest.mark.parametrize("columns", [100, 140])
def test_scrolling_keeps_the_slot_in_one_place(panel: tuple[StateController, _Covers], columns: int) -> None:
    controller, _covers = panel
    controller._snapshot = {
        "library": [
            _keyed("long", 1, 1, _LONG, 1),
            *(_keyed(f"s{index}", 100 + index, 100 + index, f"Show {index:02}", 1) for index in range(40)),
        ],
        "covers": [1, *range(100, 140)],
    }

    frame: str = controller.render(columns, 30).plain
    first: tuple[int, int] | None = _anchor(frame)
    controller.handle_key("end")
    scrolled: tuple[int, int] | None = _anchor(controller.render(columns, 30).plain)

    assert first is not None
    assert scrolled == first
    assert ("…" in next(line for line in frame.splitlines() if "As a Reincarnated" in line)) is (columns == 100)


def test_scrolling_subscriptions_keeps_the_slot_in_one_place(panel: tuple[StateController, _Covers]) -> None:
    controller, _covers = panel
    controller._tab = state_module._Tab.SUBSCRIPTIONS
    controller._snapshot = {"covers": [1, *range(100, 140)]}
    controller._subscriptions = [
        {"subscription_id": "long", "title": _LONG, "anilist_id": 1, "episode_count": 12, "aired": 3, "ready": 1},
        *(
            {"subscription_id": f"s{index}", "title": f"Show {index:02}", "anilist_id": 100 + index}
            for index in range(40)
        ),
    ]

    first: tuple[int, int] | None = _anchor(controller.render(140, 30).plain)
    controller.handle_key("end")

    assert first is not None
    assert _anchor(controller.render(140, 30).plain) == first


def test_cover_is_scaled_into_the_fixed_slot_and_a_bad_file_gives_none(tmp_path: Path) -> None:
    path: Path = tmp_path / "21.jpg"
    Image.new("RGB", (460, 636), (200, 30, 30)).save(path, "JPEG")
    (tmp_path / "22.jpg").write_bytes(b"broken")

    image: NativeImage | None = covers_module.cover_image(path, (10, 20))

    assert image is not None
    assert (image.cell_columns, image.cell_rows) == (18, 12)
    assert image.payloads[0].startswith('\x1bP9;1;0q"1;1;180;240')
    assert covers_module.cover_image(tmp_path / "22.jpg", (10, 20)) is None
    assert covers_module.cover_image(tmp_path / "missing.jpg", (10, 20)) is None


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
