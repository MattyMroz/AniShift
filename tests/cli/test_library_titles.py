from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import cast

import pytest
from test_interactive_mouse import _click
from test_panel_keys import _app, _label_point, _list_probe, _Probe

from anishift.application import EpisodeListing, ListedEpisode
from anishift.cli.interactive import state as state_module
from anishift.cli.interactive import state_library
from anishift.cli.interactive.pointer import CRUMB_SEPARATOR
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession

pytestmark = pytest.mark.unit


def _keyed(
    set_id: str, anilist_id: int, episode: int, *, series_id: int | None = 100, season: int = 2
) -> dict[str, object]:
    known: bool = series_id is not None
    return {
        "set_id": set_id,
        "name": f"[Grp] File Name {anilist_id} - {episode:02} [1080p]",
        "series": "Blue Box" if known else None,
        "season": season if known else None,
        "episode": episode if known else None,
        "anilist_id": anilist_id,
        "series_id": series_id,
        "title_source": "key",
    }


def _hand(set_id: str, name: str) -> dict[str, object]:
    return {"set_id": set_id, "name": name, "title_source": "name"}


def _keys(snapshot: Mapping[str, object]) -> list[str]:
    return [item.key for item in state_library.library_titles(snapshot)]


class _Episodes:
    def __init__(self) -> None:
        self.release: threading.Event = threading.Event()
        self.read: list[int] = []

    def new_session(self) -> _Episodes:
        return self

    def close(self) -> None:
        return

    def episodes(self, anilist_id: int) -> EpisodeListing:
        self.read.append(anilist_id)
        assert self.release.wait(5)
        moment: datetime = datetime(2026, 4, 1, 12, tzinfo=UTC)
        return EpisodeListing(
            anilist_id, None, None, "FINISHED", 2, (ListedEpisode(1, "First", moment),), (), 1, None, None
        )


@pytest.fixture
def panel(monkeypatch: pytest.MonkeyPatch) -> Iterator[StateController]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", _Episodes()), lambda: None)
    monkeypatch.setattr(controller, "_work", lambda action, **options: None)
    controller._tab = state_module._Tab.FILES
    controller._connected = True
    controller._episode_info = {1: {}, 2: {}, 5: {}, 6: {}}
    try:
        yield controller
    finally:
        controller.close()
        controller._thread.join(5)
        for thread in threading.enumerate():
            if thread.name == "anishift-library-episodes":
                thread.join(5)


def test_sets_of_one_series_form_one_title() -> None:
    snapshot: Mapping[str, object] = {"library": [_keyed("s2", 2, 1, season=3), _keyed("s1", 1, 12)]}

    titles: list[state_library.LibraryTitle] = state_library.library_titles(snapshot)

    assert [(item.key, item.title, len(item.sets)) for item in titles] == [("series:100", "Blue Box", 2)]
    assert titles[0].cover_id == 2


def test_unknown_series_groups_by_entry_until_the_series_arrives() -> None:
    unknown: Mapping[str, object] = {
        "library": [
            _keyed("a", 5, 1, series_id=None),
            _keyed("b", 5, 2, series_id=None),
            _keyed("c", 6, 1, series_id=None),
        ]
    }
    known: Mapping[str, object] = {"library": [_keyed("a", 5, 1), _keyed("b", 5, 2), _keyed("c", 6, 1)]}

    assert _keys(unknown) == ["entry:5", "entry:6"]
    assert _keys(known) == ["series:100"]


def test_hand_added_spellings_of_one_title_join_by_name() -> None:
    snapshot: Mapping[str, object] = {
        "library": [_hand("a", "[Grp] Blue Box - 01 [1080p]"), _hand("b", "Blue.Box.S01E02.1080p.WEB-DL")]
    }

    titles: list[state_library.LibraryTitle] = state_library.library_titles(snapshot)

    assert [(item.key, len(item.sets)) for item in titles] == [("name:blue box", 2)]


def test_hand_added_title_shows_from_name() -> None:
    titles: list[state_library.LibraryTitle] = state_library.library_titles(
        {"library": [_hand("a", "[Grp] Blue Box - 01 [1080p]")]}
    )

    assert state_library.title_row(titles[0]).status == "z nazwy"
    assert titles[0].from_name
    assert titles[0].cover_id is None


def test_unparsed_names_go_to_the_unrecognized_row_last() -> None:
    snapshot: Mapping[str, object] = {
        "library": [_hand("z", "zeta_notes"), _hand("a", "[Grp] Abc - 01 [1080p]"), _hand("m", "moj_film")]
    }

    titles: list[state_library.LibraryTitle] = state_library.library_titles(snapshot)

    assert [item.title for item in titles] == ["Abc", "Nie rozpoznano"]
    assert len(titles[-1].sets) == 2
    assert state_library.title_row(titles[-1]).status == "Gotowe"


def test_hidden_and_deleting_sets_leave_their_title() -> None:
    snapshot: Mapping[str, object] = {
        "library": [_keyed("a", 1, 1), _keyed("b", 1, 2), _keyed("c", 1, 3)],
        "deletions": [{"operation_id": "op", "set_id": "c", "active": True}],
    }

    titles: list[state_library.LibraryTitle] = state_library.library_titles(snapshot, hidden=("a",))

    assert [state_library.library_row_id(item) for item in titles[0].sets] == ["b"]
    assert state_library.library_titles(snapshot, hidden=("a", "b")) == []


def test_problem_sets_are_counted_in_the_state_column() -> None:
    snapshot: Mapping[str, object] = {
        "library": [_keyed("a", 1, 1)],
        "library_problems": [{**_keyed("b", 1, 2), "available": False, "problem": "library_result_missing"}],
    }

    row = state_library.title_row(state_library.library_titles(snapshot)[0])

    assert (row.number, row.status) == ("2", "1 do sprawdzenia")


def test_filter_keeps_titles_containing_the_normalized_text(panel: StateController) -> None:
    panel._snapshot = {
        "library": [_hand("a", "[Grp] Blue Box - 01"), _hand("b", "[Grp] Re-Zero - 01"), _hand("c", "[Grp] Zeta - 01")]
    }

    panel.handle_key("text:/")
    for letter in "rezero":
        panel.handle_key(f"text:{letter}")
    typed: list[str] = [item.title for item in panel._titles()]
    panel.handle_key("enter")
    kept: str = panel.render(80, 24).plain
    panel.handle_key("text:/")
    panel.handle_key("escape")

    assert typed == ["Re-Zero"]
    assert panel._library_query == ""
    assert "Filtr: rezero" in kept
    assert "Blue Box" not in kept
    assert [item.title for item in panel._titles()] == ["Blue Box", "Re-Zero", "Zeta"]


def test_enter_opens_the_title_and_escape_returns_to_it(panel: StateController) -> None:
    panel._snapshot = {"library": [_hand("a", "[Grp] Abc - 01"), _keyed("b", 1, 2), _keyed("c", 1, 1)]}

    panel.handle_key("down")
    panel.handle_key("enter")
    opened: tuple[str, ...] = panel.breadcrumb()
    episodes: list[str] = [state_library.library_row_id(item) for item in panel._episodes()]
    panel.handle_key("escape")

    assert opened == ("Biblioteka", "Blue Box")
    assert episodes == ["c", "b"]
    assert panel._library_title is None
    assert panel._selected == 1
    assert panel.breadcrumb() == ()


def test_crumb_click_returns_to_the_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    probe: _Probe = _list_probe(monkeypatch, state_module._Tab.FILES, {"library": [_hand("a", "[Grp] Abc - 01")]})
    probe.panel.handle_key("enter")
    application = _app(monkeypatch, probe)

    frame = application._render_frame(80, 24)
    _click(application, _label_point(frame, "Biblioteka", f"Biblioteka{CRUMB_SEPARATOR}"))

    assert probe.panel._library_title is None
    probe.panel.close()
    probe.panel._thread.join(5)


def test_tray_target_opens_the_title_of_its_set(panel: StateController) -> None:
    panel._snapshot = {"library": [_hand("a", "[Grp] Abc - 01"), _keyed("b", 1, 2), _keyed("c", 1, 1)]}

    panel.show_library({"set_id": "b"})

    assert panel._library_title == "series:100"
    assert state_library.library_row_id(panel._episodes()[panel._selected]) == "b"


def test_tab_switch_closes_the_title_and_its_marks(panel: StateController) -> None:
    panel._snapshot = {"library": [_keyed("b", 1, 2)]}
    panel.handle_key("enter")
    panel._library_query = "blue"

    panel.handle_key("tab")
    panel.handle_key("backtab")

    assert panel._library_title is None
    assert panel._library_input is None
    assert panel._library_query == "blue"


def test_late_episode_titles_of_another_title_are_dropped(panel: StateController) -> None:
    owner: _Episodes = cast("_Episodes", panel._parent)
    panel._episode_info = {}
    panel._snapshot = {"library": [_keyed("a", 1, 1, series_id=10), _keyed("b", 2, 1, series_id=20)]}

    panel.handle_key("enter")
    panel.handle_key("escape")
    panel.handle_key("down")
    panel.handle_key("enter")
    owner.release.set()
    for thread in threading.enumerate():
        if thread.name == "anishift-library-episodes":
            thread.join(5)

    assert sorted(owner.read) == [1, 2]
    assert 1 not in panel._episode_info
    assert panel._episode_info[2] == {1: ("First", datetime(2026, 4, 1, 12, tzinfo=UTC))}
    assert "First" in panel.render(100, 30).plain
