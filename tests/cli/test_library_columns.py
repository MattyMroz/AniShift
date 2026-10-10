from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import LibrarySet
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeSnapshot
from anishift.cli.interactive.anime_view import _SUBSCRIPTION_STATUS_WIDTH, render_anime
from anishift.cli.interactive.pointer import CRUMB_SEPARATOR
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

_POINTER: str = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
_BLUE_BOX: str = "Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264.MSubs-ToonsHub"
_LONG: str = (
    "Magic.Repo.Man.Dumped.by.My.Party.Ill.Cash.In.With.a.Cute.Support.Fairy.to.Become.the.Strongest"
    ".S01E01.1080p.CR.WEB-DL.AAC2.0.H.264-VARYG"
)
_LONG_TITLE: str = "Magic Repo Man Dumped by My Party Ill Cash In With a Cute Support Fairy to Become the Strongest"


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> Iterator[StateController]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    controller._tab = state_module._Tab.FILES
    controller._connected = True
    controller._notice = ""
    try:
        yield controller
    finally:
        controller.close()
        controller._thread.join(5)


def _rows(*names: str) -> list[dict[str, object]]:
    return [{"set_id": f"set-{index}", "name": name} for index, name in enumerate(names)]


def _line(frame: str, text: str) -> str:
    lines: list[str] = [line for line in frame.splitlines() if text in line]
    assert len(lines) == 1, text
    return lines[0]


@pytest.mark.unit
def test_library_rows_sort_by_title_then_season_then_episode_with_the_film_last() -> None:
    snapshot: Mapping[str, object] = {
        "library": _rows(
            "[Grp] Show - 10 [1080p]",
            "[Grp] Show S2 - 01 [1080p]",
            "[Grp] Show [BD 1080p]",
            "[Grp] Show - 2 [1080p]",
            "zeta_notes",
            "[Grp] Abc 10 - 01 [1080p]",
            "[Grp] Abc 9 - 01 [1080p]",
            "[Grp] Hell's Paradise - 01 [1080p]",
            "[Grp] Gachiakuta - 01 [1080p]",
        )
    }

    order: list[object] = [row["name"] for row in state_module._library_rows(snapshot)]

    assert order == [
        "[Grp] Abc 9 - 01 [1080p]",
        "[Grp] Abc 10 - 01 [1080p]",
        "[Grp] Gachiakuta - 01 [1080p]",
        "[Grp] Hell's Paradise - 01 [1080p]",
        "[Grp] Show - 2 [1080p]",
        "[Grp] Show - 10 [1080p]",
        "[Grp] Show S2 - 01 [1080p]",
        "[Grp] Show [BD 1080p]",
        "zeta_notes",
    ]


@pytest.mark.unit
@pytest.mark.parametrize("columns", [50, 80, 120])
def test_library_draws_the_name_and_episode_columns_under_their_header(library: StateController, columns: int) -> None:
    library._snapshot = {"library": _rows(_BLUE_BOX, _LONG, "moj_film_wakacje")}

    frame: str = library.render(columns, 24).plain

    header: str = _line(frame, "Odcinek")
    assert header.index("Nazwa") < header.index("Odcinek")
    for title, episode in (("Blue Box", "S02E01"), ("Magic Repo", "S01E01"), ("moj_film_wakacje", "—")):
        row: str = _line(frame, title)
        assert row.index(episode) == header.index("Odcinek")
    assert _BLUE_BOX not in frame
    assert ("…" in _line(frame, "Magic Repo")) is (columns < 120)


@pytest.mark.unit
def test_library_breadcrumb_names_the_set_by_title_and_episode(library: StateController) -> None:
    library._details = LibrarySet("set", "group", _BLUE_BOX, None, f"ready/{_BLUE_BOX}.mkv", (), True, None)

    frame: str = library.render(120, 40).plain

    assert library.breadcrumb() == ("Biblioteka", "Blue Box S02E01")
    assert f"Biblioteka{CRUMB_SEPARATOR}Blue Box S02E01" in frame


@pytest.mark.unit
def test_library_refresh_keeps_the_selected_set_after_the_order_changes(library: StateController) -> None:
    library._snapshot = {"library": _rows("[Grp] Show - 02 [1080p]", "[Grp] Show - 10 [1080p]")}
    library.handle_key("down")
    payload: dict[str, object] = {
        "library": [
            *_rows("[Grp] Show - 02 [1080p]", "[Grp] Show - 10 [1080p]"),
            {"set_id": "set-new", "name": "[Grp] Show - 05 [1080p]"},
        ]
    }

    library._preserve_library_selection(payload)
    library._snapshot = payload

    assert state_module._library_rows(payload)[library._selected]["set_id"] == "set-1"
    assert _POINTER in _line(library.render(80, 24).plain, "E10")


@pytest.mark.unit
def test_a_narrow_library_lists_title_and_episode_in_one_line(library: StateController) -> None:
    library._snapshot = {
        "library": _rows(_BLUE_BOX),
        "relocations": [{"group_id": "group-1a2b", "name": f"{_BLUE_BOX}.mkv", "problem": "failed"}],
    }

    frame: str = library.render(40, 12).plain

    assert "Blue Box S02E01" in _line(frame, _POINTER)
    assert "przenoszenie" not in frame
    assert "Powiększ" not in frame
    assert "Odcinek" not in frame


def _fill(panel: StateController, tab: int, count: int) -> str:
    panel._tab = tab
    panel._snapshot = {
        "auto_enabled": True,
        "library": _rows(*(f"[Grp] Show {index:02} - 01 [1080p]" for index in range(count))),
        "relocations": [{"group_id": "group-1a2b", "name": f"{_BLUE_BOX}.mkv", "problem": "failed"}],
    }
    panel._subscriptions = [
        {"subscription_id": f"sub-{index}", "title": f"Show {index:02}", "episode_count": 12, "done": 3, "ready": 1}
        for index in range(count)
    ]
    return "Nazwa" if tab == state_module._Tab.FILES else "Tytuł"


def _regions(lines: list[str], label: str) -> tuple[int, int, int]:
    tabs: int = next(index for index, line in enumerate(lines) if "Biblioteka" in line and "Anime" in line)
    header: int = next(index for index, line in enumerate(lines) if line.strip().startswith(label))
    keys: int = next(index for index, line in enumerate(lines) if "Esc wróć" in line)
    return tabs, header, keys


@pytest.mark.unit
@pytest.mark.parametrize("tab", [state_module._Tab.FILES, state_module._Tab.SUBSCRIPTIONS])
@pytest.mark.parametrize(("columns", "rows"), [(80, 24), (100, 30), (120, 40)])
def test_an_overflowing_table_fills_every_row_between_the_tabs_and_the_keys(
    library: StateController, tab: int, columns: int, rows: int
) -> None:
    label: str = _fill(library, tab, 40)

    lines: list[str] = library.render(columns, rows).plain.splitlines()

    tabs, header, keys = _regions(lines, label)
    data: list[str] = lines[header + 1 : keys - 1]
    assert header == tabs + 2
    assert not lines[tabs + 1].strip()
    assert not lines[keys - 1].strip()
    assert all("Show" in line for line in data)
    assert len(data) == library._page == len(lines) - header - 4
    assert keys == len(lines) - 2
    assert len(lines) == rows - 1
    assert lines[-1].strip() == "Automat: bezczynny"
    assert "przenoszenie" not in "\n".join(lines)


@pytest.mark.unit
@pytest.mark.parametrize("tab", [state_module._Tab.FILES, state_module._Tab.SUBSCRIPTIONS])
def test_a_table_that_fits_stays_centered_between_the_tabs_and_the_keys(library: StateController, tab: int) -> None:
    label: str = _fill(library, tab, 5)

    lines: list[str] = library.render(100, 30).plain.splitlines()

    tabs, header, keys = _regions(lines, label)
    above: int = header - tabs - 1
    below: int = keys - header - 6
    assert [line for line in lines[header + 1 : header + 6] if "Show" in line] == lines[header + 1 : header + 6]
    assert min(above, below) > 2
    assert abs(above - below) <= 2
    assert lines[-1].strip() == "Automat: bezczynny"


@pytest.mark.unit
def test_short_library_names_keep_the_table_narrow_and_centered(library: StateController) -> None:
    library._snapshot = {"library": _rows("[Grp] Show - 01 [1080p]", "[Grp] Other Show - 02 [1080p]")}

    header: str = _line(library.render(100, 30).plain, "Odcinek")

    left: int = header.index("Nazwa") - 2
    right: int = 100 - len(header.rstrip())
    assert abs(left - right) <= 1
    assert left > 20


def _margins(header: str, first: str, last: str, last_width: int) -> tuple[int, int]:
    return header.index(first) - 2, 100 - header.index(last) - last_width


@pytest.mark.unit
@pytest.mark.parametrize("tab", [state_module._Tab.FILES, state_module._Tab.SUBSCRIPTIONS])
def test_the_table_narrows_and_stays_centered_when_the_longest_name_scrolls_away(
    library: StateController, tab: int
) -> None:
    label: str = _fill(library, tab, 30)
    library._snapshot = {"library": _rows(_LONG, *(f"[Grp] Show - {index:02} [1080p]" for index in range(30)))}
    library._subscriptions = [
        {"subscription_id": "sub-long", "title": _LONG_TITLE, "episode_count": 12, "done": 3, "ready": 1},
        *library._subscriptions,
    ]
    last, width = (
        ("Odcinek", len("Odcinek")) if tab == state_module._Tab.FILES else ("Stan", _SUBSCRIPTION_STATUS_WIDTH)
    )

    first: str = library.render(100, 30).plain
    library.handle_key("end")
    scrolled: str = library.render(100, 30).plain

    wide_left, wide_right = _margins(_line(first, last), label, last, width)
    left, right = _margins(_line(scrolled, last), label, last, width)
    assert "Magic Repo" in _line(first, _POINTER)
    assert "…" in _line(first, _POINTER)
    assert "Magic Repo" not in scrolled
    assert wide_left <= 2
    assert abs(wide_left - wide_right) <= 1
    assert left > 20
    assert abs(left - right) <= 1
    assert _line(scrolled, "Show 29" if tab == state_module._Tab.SUBSCRIPTIONS else "E29").index("S") == left + 2


@pytest.mark.unit
def test_search_results_narrow_and_stay_centered_when_the_longest_title_scrolls_away() -> None:
    items: tuple[AnimeRow, ...] = (
        AnimeRow("long", _LONG_TITLE, date="2026", kind="TV"),
        *(AnimeRow(str(index), f"Show {index:02}", date="2026", kind="TV") for index in range(30)),
    )

    first: str = render_anime(AnimeSnapshot(AnimeScreen.TITLES, "Anime", items), 100, 30, 0).text.plain
    scrolled: str = render_anime(
        AnimeSnapshot(AnimeScreen.TITLES, "Anime", items, cursor=30, offset=20), 100, 30, 0
    ).text.plain

    wide_left, wide_right = _margins(_line(first, "Status"), "Premiera", "Status", len("Status"))
    left, right = _margins(_line(scrolled, "Status"), "Premiera", "Status", len("Status"))
    assert "Magic Repo" in first
    assert "Magic Repo" not in scrolled
    assert wide_left <= 2
    assert abs(wide_left - wide_right) <= 1
    assert left > 20
    assert abs(left - right) <= 1
