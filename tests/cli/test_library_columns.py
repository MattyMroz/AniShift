from __future__ import annotations

from collections.abc import Iterator, Mapping
from types import SimpleNamespace
from typing import cast

import pytest

from anishift.application import LibrarySet
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive.pointer import CRUMB_SEPARATOR
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

_POINTER: str = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"
_BLUE_BOX: str = "Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264.MSubs-ToonsHub"
_LONG: str = (
    "Magic.Repo.Man.Dumped.by.My.Party.Ill.Cash.In.With.a.Cute.Support.Fairy.to.Become.the.Strongest"
    ".S01E01.1080p.CR.WEB-DL.AAC2.0.H.264-VARYG"
)


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
@pytest.mark.parametrize(
    ("relocations", "expected"),
    [
        (
            [
                {"group_id": "group-1a2b", "name": f"{_BLUE_BOX}.mkv", "problem": "failed"},
                {"group_id": "group-3c4d", "name": None, "problem": "failed"},
            ],
            "P ponów przenoszenie do biblioteki · Blue Box S02E01, inne zestawy: 1",
        ),
        (
            [
                {"group_id": "group-1a2b", "name": None, "problem": "failed"},
                {"group_id": "group-3c4d", "problem": "failed"},
            ],
            "P ponów przenoszenie do biblioteki · zestawy: 2",
        ),
    ],
)
def test_library_relocation_line_names_sets_and_never_shows_a_group_id(
    library: StateController, relocations: list[dict[str, object]], expected: str
) -> None:
    library._snapshot = {"library": _rows(_BLUE_BOX), "relocations": relocations}

    frame: str = library.render(120, 40).plain

    assert expected in frame
    assert "group-" not in frame


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
    assert "P ponów przenoszenie do biblioteki" in frame
    assert "Powiększ" not in frame
    assert "Odcinek" not in frame


@pytest.mark.unit
def test_an_older_resident_naming_a_relocation_by_its_group_id_counts_it_as_unnamed(library: StateController) -> None:
    library._snapshot = {
        "library": _rows(_BLUE_BOX),
        "relocations": [{"group_id": "group-1a2b", "name": "group-1a2b", "problem": "failed"}],
    }

    frame: str = library.render(120, 40).plain

    assert "P ponów przenoszenie do biblioteki · zestawy: 1" in frame
    assert "group-" not in frame
