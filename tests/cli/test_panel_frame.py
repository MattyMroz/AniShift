from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import replace
from types import SimpleNamespace
from typing import Final, cast

import pytest
from rich.text import Text
from test_panel_keys import _FIXTURES, _Library, _Probe

from anishift.cli.interactive.anime import AnimeController
from anishift.cli.interactive.state import StateController, _Tab
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit

_ARROW: Final[str] = "\N{SINGLE RIGHT-POINTING ANGLE QUOTATION MARK}"

_POINTER: Final[str] = "\N{HEAVY RIGHT-POINTING ANGLE QUOTATION MARK ORNAMENT}"

_COUNTS: Final[Mapping[str, int]] = {"downloading": 1, "processing": 2, "waiting": 3}

_STATES: Final[tuple[tuple[Mapping[str, object], str], ...]] = (
    ({"auto_enabled": True, "material_counts": _COUNTS}, "Automat: praca · pobiera 1 · przetwarza 2 · czeka 3"),
    ({"auto_enabled": True, "material_counts": {"downloading": 0, "processing": 2}}, "Automat: praca · przetwarza 2"),
    ({"auto_enabled": True, "material_counts": {}}, "Automat: bezczynny"),
    (
        {"auto_enabled": True, "material_counts": {"downloading": 0, "processing": 0, "waiting": 0}},
        "Automat: bezczynny",
    ),
    ({"auto_enabled": False, "material_counts": _COUNTS}, "Automat wstrzymany"),
    (
        {"auto_enabled": False, "pausing": True, "material_counts": _COUNTS},
        "Automat: zatrzymywanie · pobiera 1 · przetwarza 2 · czeka 3",
    ),
    (
        {"auto_enabled": False, "pause_incomplete": True, "material_counts": {"waiting": 3}},
        "Automat: pauza niepełna · czeka 3",
    ),
)

_SIZES: Final[tuple[tuple[int, int], ...]] = ((40, 12), (50, 12), (80, 12), (80, 24), (120, 30))


@pytest.fixture
def build(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], _Probe]]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    built: list[StateController] = []

    def make(name: str) -> _Probe:
        probe: _Probe = _FIXTURES[name](monkeypatch)
        built.append(probe.panel)
        return probe

    yield make
    for panel in built:
        panel.close()
        panel._thread.join(5)


def _lines(probe: _Probe, columns: int, rows: int) -> list[str]:
    return probe.panel.render(columns, rows).plain.splitlines()


def _counted(probe: _Probe, counts: Mapping[str, int] = _COUNTS) -> _Probe:
    probe.panel._snapshot = {**probe.panel._snapshot, "material_counts": counts}
    return probe


@pytest.mark.parametrize(("columns", "rows"), [(80, 24), (120, 30)])
@pytest.mark.parametrize(
    "name",
    ["query", "episodes", "u08", "subscriptions", "processing_download", "history", "library", "library_details"],
)
def test_every_tab_ends_with_the_same_automation_status(
    build: Callable[[str], _Probe], name: str, columns: int, rows: int
) -> None:
    probe: _Probe = build(name)
    base: dict[str, object] = dict(probe.panel._snapshot)
    for snapshot, status in _STATES:
        probe.panel._snapshot = {**base, **snapshot}
        assert _status(probe, columns, rows) == status
    probe.panel._connected = False
    assert _status(probe, columns, rows) == "Automat: brak połączenia"


def _status(probe: _Probe, columns: int, rows: int) -> str:
    lines: list[str] = _lines(probe, columns, rows)
    status: str = lines[-1].strip()
    assert len(lines) == rows - 1
    assert lines[-1].rstrip() == f"{' ' * ((columns - len(status)) // 2)}{status}"
    return status


@pytest.mark.parametrize(
    ("columns", "status"),
    [(49, "Automat: praca · pobiera 1 · przetwarza 2"), (40, "Automat: praca · pobiera 1")],
)
def test_a_narrow_status_drops_counts_from_the_end(build: Callable[[str], _Probe], columns: int, status: str) -> None:
    assert _lines(_counted(build("processing_download")), columns, 24)[-1].strip() == status


def test_processing_status_counts_owner_materials_instead_of_its_rows(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = _counted(build("processing_download"), {"downloading": 5, "waiting": 2})

    lines: list[str] = _lines(probe, 80, 24)

    assert len(probe.panel._processing_rows()) == 1
    assert lines[-1].strip() == "Automat: praca · pobiera 5 · czeka 2"


@pytest.mark.parametrize("name", ["query", "episodes", "subscriptions"])
def test_anime_and_subscriptions_ask_for_a_larger_terminal_at_40_by_12(
    build: Callable[[str], _Probe], name: str
) -> None:
    assert "Powiększ terminal do 50 x 12" in "\n".join(_lines(build(name), 40, 12))


@pytest.mark.parametrize("name", ["query", "subscriptions"])
def test_a_terminal_too_narrow_for_the_table_keeps_the_status_on_the_last_line(
    build: Callable[[str], _Probe], name: str
) -> None:
    probe: _Probe = _counted(build(name))

    assert "Powiększ terminal do 50 x 12" in "\n".join(_lines(probe, 40, 24))
    assert _status(probe, 40, 24) == "Automat: praca · pobiera 1"


def test_the_history_help_keeps_the_history_breadcrumb(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("history")
    probe.panel.handle_key("text:?")

    lines: list[str] = _lines(probe, 80, 24)

    assert "Wszędzie" in "\n".join(lines)
    assert [line.strip() for line in lines if _ARROW in line] == [f"Przetwarzanie {_ARROW} Historia"]


@pytest.mark.parametrize(("name", "row"), [("processing_download", "50%"), ("library", "Slime")])
def test_processing_and_library_draw_their_list_and_status_at_40_by_12(
    build: Callable[[str], _Probe], name: str, row: str
) -> None:
    lines: list[str] = _lines(_counted(build(name)), 40, 12)

    assert any(row in line for line in lines)
    assert "Powiększ" not in "\n".join(lines)
    assert lines[-1].strip() == "Automat: praca · pobiera 1"


_ANIME_SCREENS: Final[list[tuple[str, tuple[str, ...], str]]] = [
    ("query", (), "Enter szukaj · Esc wróć"),
    ("busy", (), "Wczytuję odcinki…"),
    ("episodes", ("text:?",), "C kopiuj · Esc wróć"),
    ("draft", (), "Nowa subskrypcja"),
    ("episodes", ("space",), "Zaznaczone: 1 (3)"),
]


@pytest.mark.parametrize("columns", [50, 80])
@pytest.mark.parametrize(("name", "keys", "shown"), _ANIME_SCREENS)
def test_anime_keeps_its_screen_without_a_status_below_13_rows(
    build: Callable[[str], _Probe], name: str, keys: tuple[str, ...], shown: str, columns: int
) -> None:
    probe: _Probe = _counted(build(name))
    for key in keys:
        probe.panel.handle_key(key)

    frame: str = "\n".join(_lines(probe, columns, 12))

    assert shown in frame
    assert "Automat" not in frame
    assert "Powiększ" not in frame


@pytest.mark.parametrize(("name", "keys", "shown"), _ANIME_SCREENS)
def test_anime_shows_the_status_from_13_rows(
    build: Callable[[str], _Probe], name: str, keys: tuple[str, ...], shown: str
) -> None:
    probe: _Probe = _counted(build(name))
    for key in keys:
        probe.panel.handle_key(key)

    lines: list[str] = _lines(probe, 50, 13)

    assert shown in "\n".join(lines)
    assert lines[-1].strip() == "Automat: praca · pobiera 1 · przetwarza 2"


@pytest.mark.parametrize("columns", [50, 80])
def test_subscriptions_keep_the_status_at_12_rows(build: Callable[[str], _Probe], columns: int) -> None:
    lines: list[str] = _lines(_counted(build("subscriptions")), columns, 12)

    assert any("Alpha" in line for line in lines)
    assert lines[-1].strip().startswith("Automat: praca · pobiera 1 · przetwarza 2")


@pytest.mark.parametrize("name", sorted(_FIXTURES))
def test_no_frame_line_is_wider_than_the_terminal(build: Callable[[str], _Probe], name: str) -> None:
    probe: _Probe = _counted(build(name))
    if probe.panel._details is not None:
        probe.panel._details = replace(probe.panel._details, name="Tensei shitara Slime Datta Ken " * 5)
    for columns, rows in _SIZES:
        lines: list[str] = _lines(probe, columns, rows)
        assert len(lines) <= rows - 1
        assert all(Text(line).cell_len <= columns for line in lines)


def test_a_tiny_library_frame_with_a_notice_and_a_relocation_problem_fills_the_terminal_exactly(
    build: Callable[[str], _Probe],
) -> None:
    probe: _Probe = build("library_relocation")
    probe.panel._notice = "Nie udało się potwierdzić dostępności operacji Kosza"
    probe.panel._notice_persistent = True

    lines: list[str] = _lines(probe, 40, 8)

    assert len(lines) == 7
    assert lines[-1].strip() == "Automat: bezczynny"


@pytest.mark.parametrize("rows", range(12, 31))
def test_library_details_help_shows_its_heading_only_with_a_hint_below(
    build: Callable[[str], _Probe], rows: int
) -> None:
    lines: list[str] = [line.strip() for line in _lines(build("library_details"), 80, rows)]

    heading: int | None = lines.index("Ten ekran") if "Ten ekran" in lines else None

    assert heading is None or lines[heading + 1].startswith("Enter otwórz plik")


@pytest.mark.parametrize(("columns", "rows"), [(50, 12), (80, 12), (80, 24), (120, 30)])
@pytest.mark.parametrize("name", ["episodes", "files", "history", "library_details"])
def test_an_empty_breadcrumb_keeps_its_row_so_the_content_stays(
    build: Callable[[str], _Probe], monkeypatch: pytest.MonkeyPatch, name: str, columns: int, rows: int
) -> None:
    probe: _Probe = build(name)
    shown: list[str] = _lines(probe, columns, rows)
    monkeypatch.setattr(AnimeController, "_entry_heading", lambda self: "")
    monkeypatch.setattr(StateController, "_breadcrumb", lambda self, columns: Text())

    hidden: list[str] = _lines(probe, columns, rows)

    changed: list[int] = [index for index, pair in enumerate(zip(shown, hidden, strict=True)) if pair[0] != pair[1]]
    assert len(changed) == 1
    assert _ARROW in shown[changed[0]]
    assert not hidden[changed[0]].strip()


@pytest.mark.parametrize(("columns", "rows"), [(50, 12), (80, 24), (120, 30)])
def test_a_list_row_keeps_its_line_when_history_adds_a_breadcrumb(
    build: Callable[[str], _Probe], columns: int, rows: int
) -> None:
    listed: list[str] = _lines(build("processing_download"), columns, rows)
    history: list[str] = _lines(build("history"), columns, rows)

    assert _cursor(listed) == _cursor(history)
    assert not listed[_cursor(listed) - 1].strip()
    assert _ARROW in history[_cursor(history) - 1]


def _cursor(lines: list[str]) -> int:
    return next(index for index, line in enumerate(lines) if _POINTER in line)


@pytest.mark.parametrize(
    ("name", "crumb"),
    [
        ("episodes", f"Anime {_ARROW} Slime (2018)"),
        ("candidates", f"Anime {_ARROW} Slime (2018)"),
        ("files", f"Anime {_ARROW} Slime (2018)"),
        ("u08", f"Subskrypcje {_ARROW} Alpha"),
        ("draft", f"Nowa subskrypcja {_ARROW} Slime"),
        ("history", f"Przetwarzanie {_ARROW} Historia"),
        ("library_details", f"Biblioteka {_ARROW} Slime"),
    ],
)
def test_a_deeper_screen_names_its_tab_and_item_in_the_breadcrumb(
    build: Callable[[str], _Probe], name: str, crumb: str
) -> None:
    lines: list[str] = _lines(build(name), 80, 24)

    assert [line.strip() for line in lines if _ARROW in line] == [crumb]
    assert "Wybierz plik" not in "\n".join(lines)


@pytest.mark.parametrize(
    "name", ["titles", "entries", "subscriptions", "subscriptions_empty", "processing_download", "library"]
)
def test_a_tab_list_has_an_empty_breadcrumb(build: Callable[[str], _Probe], name: str) -> None:
    content: str = "\n".join(_lines(build(name), 80, 24)[3:])

    assert _ARROW not in content
    assert "ANIME" not in content
    assert "Subskrypcje" not in content


def test_the_subscription_list_says_connecting_until_the_owner_lists_it(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("subscriptions_empty")
    probe.panel._snapshot = {}
    probe.panel._connected = False

    before: list[str] = _lines(probe, 80, 24)
    probe.panel._receive(
        cast("ResidentSession", _Library()), {"event": "state_changed", "payload": {"auto_enabled": True}}
    )
    after: list[str] = _lines(probe, 80, 24)

    assert "Łączenie…" in "\n".join(before)
    assert "Brak subskrypcji" not in "\n".join(before)
    assert before[-2].strip() == "? więcej · Esc wróć"
    assert before[-1].strip() == "Automat: brak połączenia"
    assert "Brak subskrypcji" in "\n".join(after)
    assert "Łączenie" not in "\n".join(after)
    assert after[-2].strip() == "D lub / dodaj pierwszą · ? więcej · Esc wróć"
    assert after[-1].strip() == "Automat: bezczynny"


@pytest.mark.parametrize("tab", [_Tab.SUBSCRIPTIONS, _Tab.PROGRESS, _Tab.FILES])
def test_a_fresh_panel_names_the_missing_connection_only_in_the_status(
    monkeypatch: pytest.MonkeyPatch, tab: _Tab
) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    panel: StateController = StateController(cast("ResidentSession", SimpleNamespace()), lambda: None)
    panel._tab = tab
    try:
        lines: list[str] = panel.render(80, 24).plain.splitlines()
    finally:
        panel.close()
        panel._thread.join(5)

    assert not any(text in "\n".join(lines) for text in ("Brak połączenia", "Łączenie z procesem"))
    assert lines[-1].strip() == "Automat: brak połączenia"


def _state(probe: _Probe, payload: Mapping[str, object]) -> list[str]:
    probe.panel._receive(cast("ResidentSession", _Library()), {"event": "state_changed", "payload": payload})
    return _lines(probe, 100, 30)


def test_the_library_says_loading_until_the_owner_inventories_it(build: Callable[[str], _Probe]) -> None:
    probe: _Probe = build("library_empty")

    loading: str = "\n".join(_state(probe, {"auto_enabled": True, "library": [], "library_loading": True}))
    empty: str = "\n".join(_state(probe, {"auto_enabled": True, "library": [], "library_loading": False}))
    listed: str = "\n".join(
        _state(probe, {"auto_enabled": True, "library": [{"set_id": "set", "name": "Slime"}], "library_loading": True})
    )

    assert "Wczytuję…" in loading
    assert "Biblioteka jest pusta" not in loading
    assert "Biblioteka jest pusta" in empty
    assert "Wczytuję" not in empty
    assert "Slime" in listed
    assert not any(text in listed for text in ("Wczytuję", "Biblioteka jest pusta", "Brak pozycji"))


def _empty_message(probe: _Probe, text: str) -> tuple[int, int, list[str]]:
    lines: list[Text] = list(probe.panel.render(100, 30).split("\n", allow_blank=True))
    row: int = next(index for index, line in enumerate(lines) if line.plain.strip() == text)
    column: int = lines[row].plain.index(text)
    styles: list[str] = [
        str(span.style)
        for span in lines[row].spans
        if span.start <= column and span.end >= column + len(text) and str(span.style)
    ]
    return row, column - (100 - len(text)) // 2, styles


@pytest.mark.parametrize(
    ("name", "history", "text"),
    [
        ("library_empty", False, "Biblioteka jest pusta"),
        ("processing_empty", False, "Brak aktywnego przetwarzania"),
        ("subscriptions_empty", False, "Brak subskrypcji"),
        ("processing_empty", True, "Brak pozycji"),
    ],
)
def test_every_empty_tab_shows_its_message_in_one_style_and_place(
    build: Callable[[str], _Probe], name: str, history: bool, text: str
) -> None:
    probe: _Probe = build(name)
    probe.panel._connected = True
    probe.panel._history_open = history

    assert _empty_message(probe, text) == (16, 0, ["gray"])
