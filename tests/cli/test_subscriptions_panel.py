from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from rich.text import Text

from anishift.application.control_views import encode_view
from anishift.application.subscription_targets import SubscriptionRow
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import ControlError, ControlErrorCode

_SIZES: list[tuple[int, int]] = [(120, 30), (50, 24), (50, 12)]


class _Remote:
    def __init__(self, refusal: str = "") -> None:
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []
        self.refusal: str = refusal

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        self.calls.append((kind, payload))
        if self.refusal:
            raise ControlError("refused", code=ControlErrorCode.REFUSED, reason=self.refusal, answered=True)
        return {}

    def close(self) -> None:
        pass


class _Parent:
    def __init__(self, remote: _Remote) -> None:
        self.remote: _Remote = remote

    def new_session(self) -> _Remote:
        return self.remote


def _row(subscription_id: str, title: str, **changes: object) -> dict[str, object]:
    row: SubscriptionRow = SubscriptionRow(
        subscription_id=subscription_id,
        anilist_id=1,
        title=title,
        due_at=None,
        paused=False,
        pause_reason=None,
        problem=None,
        review_pending=False,
        episode_count=4,
        on_disk=1,
    )
    return {**encode_view(row), **changes}


@pytest.fixture
def remote() -> _Remote:
    return _Remote()


@pytest.fixture
def panel(monkeypatch: pytest.MonkeyPatch, remote: _Remote) -> Iterator[StateController]:
    monkeypatch.setattr(StateController, "_watch", lambda self: None)
    controller: StateController = StateController(cast("ResidentSession", _Parent(remote)), lambda: None)
    controller._tab = 1
    controller._connected = True
    controller._notice = ""
    controller._snapshot = {"auto_enabled": True}
    controller._subscriptions = [_row("a", "Alpha"), _row("b", "Beta", paused=True, pause_reason="user")]
    try:
        yield controller
    finally:
        controller.close()
        controller._thread.join(5)


def _settle(controller: StateController) -> None:
    deadline: float = time.monotonic() + 5
    while controller._busy and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not controller._busy


def _frame(controller: StateController, columns: int = 120, rows: int = 30) -> str:
    return controller.render(columns, rows).plain


def _line(lines: list[str], needle: str) -> int:
    return next(index for index, line in enumerate(lines) if needle in line)


def _warning(lines: list[str]) -> str:
    return lines[next(index for index, line in enumerate(lines) if line.strip() == "Subskrypcje") + 1].strip()


@pytest.mark.parametrize("key", ["space", "text:w"])
@pytest.mark.parametrize(
    ("selected", "kind", "identifier"), [(0, "subscription_pause", "a"), (1, "subscription_resume", "b")]
)
def test_space_and_w_toggle_the_selected_subscription(  # noqa: PLR0913
    panel: StateController, remote: _Remote, key: str, selected: int, kind: str, identifier: str
) -> None:
    panel._selected = selected

    panel.handle_key(key)
    _settle(panel)

    assert remote.calls == [(kind, {"subscription_id": identifier})]
    assert panel._notice == ""


@pytest.mark.parametrize("key", ["delete", "text:x"])
def test_removing_names_the_title_and_keeps_the_undo_hint_until_the_state_moves(
    panel: StateController, remote: _Remote, key: str
) -> None:
    panel._selected = 0

    panel.handle_key(key)
    _settle(panel)

    assert remote.calls == [("subscription_remove", {"subscription_id": "a"})]
    assert panel._notice == "Usunięto Alpha · Ctrl+Z cofnij"
    assert panel._notice_persistent
    assert "Usunięto Alpha · Ctrl+Z cofnij" in _frame(panel)


def test_ctrl_z_restores_the_last_removed_subscription_from_any_row(panel: StateController, remote: _Remote) -> None:
    panel.handle_key("undo")
    _settle(panel)

    assert remote.calls == [("subscription_restore", None)]


def test_enter_on_a_subscription_without_an_anilist_entry_explains_how_to_recover(
    panel: StateController, remote: _Remote
) -> None:
    panel._subscriptions = [_row("a", "Alpha", anilist_id=None)]
    panel._selected = 0

    panel.handle_key("enter")

    assert panel._notice == "Ta subskrypcja nie ma wpisu AniList · usuń ją i dodaj ponownie"
    assert remote.calls == []


@pytest.mark.parametrize("key", ["space", "delete", "text:w", "text:f"])
def test_row_keys_on_an_empty_list_send_nothing(panel: StateController, remote: _Remote, key: str) -> None:
    panel._subscriptions = []

    panel.handle_key(key)

    assert remote.calls == []
    assert panel._notice == ""


@pytest.mark.parametrize(
    ("reason", "text"),
    [
        ("subscription_missing", "Tej subskrypcji już nie ma"),
        ("nothing_to_restore", "Brak usuniętej subskrypcji do przywrócenia"),
        ("subscription_exists", "Ten sezon jest już subskrybowany"),
        ("subscription_limit", "Osiągnięto limit subskrypcji; usuń jedną, aby dodać lub przywrócić"),
    ],
)
def test_a_refused_subscription_command_shows_its_polish_reason(
    panel: StateController, remote: _Remote, reason: str, text: str
) -> None:
    remote.refusal = reason

    panel.handle_key("undo")
    _settle(panel)

    assert panel._notice == text
    assert text in _frame(panel)


def test_every_row_is_one_line_of_title_episodes_ready_and_state(panel: StateController) -> None:
    now: datetime = datetime.now(UTC)
    panel._subscriptions = [
        _row("p", "Problem", anilist_id=None, problem="season_unrecognized", episode_count=None, on_disk=0),
        _row("m", "Moved", paused=True, pause_reason="migrated_missing", review_pending=True, episode_count=None),
        _row("r", "Review", review_pending=True, on_disk=0),
        _row("s", "Soon", episode_count=12, ready=1, due_at=(now + timedelta(days=3, hours=1, seconds=30)).isoformat()),
        _row("h", "Hour", due_at=(now + timedelta(minutes=30, seconds=30)).isoformat()),
        _row("w", "Waiting", due_at=(now - timedelta(days=2, hours=1)).isoformat()),
        _row("y", "Yesterday", due_at=(now - timedelta(days=1, hours=1)).isoformat()),
        _row("n", "Recent", due_at=(now - timedelta(hours=5, minutes=1)).isoformat()),
        _row("u", "Undated"),
    ]

    lines: list[str] = _frame(panel, rows=40).splitlines()

    expected: dict[str, tuple[str, ...]] = {
        "Problem": ("0/?", "0", "Nie rozpoznano sezonu"),
        "Moved": ("1/?", "0", "Wstrzymana"),
        "Review": ("0/4", "0", "Weryfikuję"),
        "Soon": ("1/12", "1", "Emisja za 3d 01:00:"),
        "Hour": ("1/4", "0", "Emisja za 00:30:"),
        "Waiting": ("1/4", "0", "Czeka na wydanie (od 2 dni)"),
        "Yesterday": ("1/4", "0", "Czeka na wydanie (od 1 dzień)"),
        "Recent": ("1/4", "0", "Czeka na wydanie (od 5 h)"),
        "Undated": ("1/4", "0", "Termin nieznany"),
    }
    for title, values in expected.items():
        line: str = lines[_line(lines, f" {title} ")]
        position: int = line.index(title) + len(title)
        for value in values:
            position = line.index(f"  {value}", position) + len(value) + 2
    frame: str = "\n".join(lines)
    assert "Odcinki" in frame
    assert "Gotowe" in frame
    assert "Pobrano" not in frame
    assert "E3" not in frame
    assert "Aktywne" not in frame
    assert "D Dodaj subskrypcję" not in frame
    assert " od 3 " not in frame


def test_the_highlighted_row_explains_its_full_state_beneath_the_table(panel: StateController) -> None:
    panel._subscriptions = [
        _row("p", "Problem", anilist_id=None, problem="season_unrecognized"),
        _row("m", "Moved", paused=True, pause_reason="migrated_missing"),
    ]

    first: str = _frame(panel)
    panel.handle_key("down")
    second: str = _frame(panel)

    assert "Nie rozpoznano sezonu — usuń i dodaj ponownie" in first
    assert "Wstrzymana — zakończona przez starą wersję · W wznów" in second
    assert "usuń i dodaj ponownie" not in second
    assert "pobrano" not in first + second
    assert "· Problem" not in first


def test_a_row_shown_whole_leaves_nothing_beneath_the_table(panel: StateController) -> None:
    panel._subscriptions = [_row("u", "Undated")]

    lines: list[str] = _frame(panel).splitlines()

    assert [line for line in lines if "Termin nieznany" in line] == [lines[_line(lines, " Undated ")]]
    assert sum("Undated" in line for line in lines) == 1


def test_problem_and_conflict_states_share_the_style_of_every_other_state(panel: StateController) -> None:
    panel._subscriptions = [
        _row("u", "Undated"),
        _row("p", "Problem", problem="season_unrecognized"),
        _row("c", "Conflict", episode_count=2, beyond_count=6),
        _row("s", "Selected", paused=True, pause_reason="user"),
    ]
    panel._selected = 3

    rendered: Text = panel.render(120, 30)

    def styles(needle: str) -> set[str]:
        index: int = rendered.plain.index(needle)
        return {str(span.style) for span in rendered.spans if span.start <= index < span.end}

    assert styles("Nie rozpoznano sezonu ") == styles("Konflikt liczby odcinków ") == styles("Termin nieznany ")


def test_the_episodes_column_uses_the_success_style_only_once_a_file_is_on_disk(panel: StateController) -> None:
    panel._subscriptions = [
        _row("e", "Empty", on_disk=0, episode_count=12),
        _row("o", "Owned", on_disk=3, episode_count=12),
        _row("s", "Selected"),
    ]
    panel._selected = 2

    rendered: Text = panel.render(120, 30)

    def styles(value: str) -> set[str]:
        index: int = rendered.plain.index(f" {value} ") + 1
        return {str(span.style) for span in rendered.spans if span.start <= index < span.end}

    assert "success" in styles("3/12")
    assert "success" not in styles("0/12")


@pytest.mark.parametrize(
    ("problem", "shadow", "warning"),
    [
        ("save_failed", False, "Monitoring nie działa: nie można zapisać stanu"),
        ("save_failed", True, "Monitoring nie działa: nie można zapisać stanu"),
        ("", True, "Tryb cienia — subskrypcje tylko zapisują propozycje"),
    ],
)
def test_the_status_row_names_why_monitoring_does_not_progress(
    panel: StateController, problem: str, shadow: bool, warning: str
) -> None:
    panel._subscriptions_problem = problem
    panel._subscriptions_shadow = shadow

    assert _warning(_frame(panel).splitlines()) == warning


@pytest.mark.parametrize(("columns", "rows"), _SIZES)
def test_the_global_pause_shows_only_in_the_status_line(panel: StateController, columns: int, rows: int) -> None:
    running: list[str] = _frame(panel, columns, rows).splitlines()
    panel._snapshot = {"auto_enabled": False}
    paused: list[str] = _frame(panel, columns, rows).splitlines()

    assert [line for line in running if "Praca" not in line] == [
        line for line in paused if "Automat wstrzymany" not in line
    ]
    assert "Automat wstrzymany" in paused[-1]
    assert "subskrypcje czekają" not in "\n".join(paused)


@pytest.mark.parametrize("rows", [24, 12])
def test_a_check_result_leads_the_text_beneath_the_table_of_a_narrow_terminal(
    panel: StateController, rows: int
) -> None:
    panel._subscriptions = [_row("a", "That Time I Got Reincarnated as a Slime Season 4", episode_count=12)]
    panel._receive_check(
        {
            "subscription_id": "a",
            "last_check": {"number": 6, "outcome": "proposed", "matching": 1, "uncertain": 8, "mismatched": 4},
        }
    )

    lines: list[str] = _frame(panel, 50, rows).splitlines()

    assert lines[_line(lines, "13 kandydatów")].strip().startswith("Sprawdzono E6: 13 kandydatów")
    assert "Praca" in lines[-1]


@pytest.mark.parametrize(("columns", "rows"), _SIZES)
@pytest.mark.parametrize("change", ["notice", "warning", "check"])
def test_rows_keep_their_position_when_feedback_appears(
    panel: StateController, columns: int, rows: int, change: str
) -> None:
    before: list[str] = _frame(panel, columns, rows).splitlines()
    if change == "notice":
        panel._notice = "Usunięto Gamma · Ctrl+Z cofnij"
    elif change == "warning":
        panel._subscriptions_problem = "save_failed"
    else:
        panel._receive_check({"subscription_id": "a", "last_check": {"number": 6, "outcome": "no_candidates"}})
    after: list[str] = _frame(panel, columns, rows).splitlines()

    for title in ("Alpha", "Beta") if rows > 12 else ("Alpha",):
        assert _line(before, title) == _line(after, title)
        assert before[_line(before, title)].index(title) == after[_line(after, title)].index(title)


@pytest.mark.parametrize(("columns", "rows"), _SIZES)
def test_an_empty_list_names_the_add_key(panel: StateController, columns: int, rows: int) -> None:
    panel._subscriptions = []

    frame: str = _frame(panel, columns, rows)

    assert "Brak subskrypcji" in frame
    assert "/ dodaj pierwszą · ? więcej · Esc wróć" in frame.split("Brak subskrypcji")[1]
    assert "Enter szczegóły" not in frame
    assert "Aktywne" not in frame


def test_d_and_enter_on_an_empty_list_open_the_search(panel: StateController) -> None:
    panel._subscriptions = []

    panel.handle_key("enter")

    assert panel._tab == 1
    assert panel._anime is None


def test_a_healthy_running_list_shows_no_warning(panel: StateController) -> None:
    assert _warning(_frame(panel).splitlines()) == ""


@pytest.mark.parametrize(("selected", "toggle"), [(0, "W wstrzymaj"), (1, "W wznów")])
def test_the_key_hint_follows_the_selected_row(panel: StateController, selected: int, toggle: str) -> None:
    panel._selected = selected

    frame: str = _frame(panel)

    assert toggle in frame
    assert "? więcej" in frame


@pytest.mark.parametrize(("columns", "rows"), _SIZES)
def test_the_list_fits_and_every_row_and_key_stays_reachable(panel: StateController, columns: int, rows: int) -> None:
    panel._subscriptions = [_row(f"s{index}", f"Series {index:02d}") for index in range(30)]
    seen: set[str] = set()

    for _ in range(30):
        lines: list[str] = _frame(panel, columns, rows).splitlines()
        assert len(lines) < rows
        assert all(Text(line).cell_len <= columns for line in lines)
        seen.update(f"Series {index:02d}" for index in range(30) if any(f"Series {index:02d}" in x for x in lines))
        panel.handle_key("down")

    frame: str = _frame(panel, columns, rows)
    assert seen == {f"Series {index:02d}" for index in range(30)}
    for hint in ("Enter szczegóły", "/ dodaj", "W wstrzymaj", "? więcej", "Esc wróć"):
        assert hint in frame
    panel.handle_key("text:?")
    shown: str = _frame(panel, columns, rows)
    for hint in ("R sprawdź teraz", "X usuń", "Ctrl+Z cofnij"):
        assert hint in shown


@pytest.mark.parametrize(
    ("columns", "labels", "beneath"),
    [
        (120, 4, ""),
        (50, 2, "odcinki 1/12 · gotowe 0 · That Time I Got Reincarnated as a Slime Season 4"),
    ],
)
def test_narrow_terminals_drop_optional_columns_and_show_only_what_the_row_hides_beneath_the_table(
    panel: StateController, columns: int, labels: int, beneath: str
) -> None:
    panel._subscriptions = [_row("a", "That Time I Got Reincarnated as a Slime Season 4", episode_count=12)]

    lines: list[str] = _frame(panel, columns, 24).splitlines()
    header: str = lines[_line(lines, "Tytuł")]
    keys: int = _line(lines, "Enter szczegóły")
    notice: str = " ".join(line.strip() for line in lines[_line(lines, "Tytuł") + 2 : keys] if line.strip())

    shown: list[str] = [label for label in ("Tytuł", "Odcinki", "Gotowe", "Stan") if label in header]
    assert len(shown) == labels
    assert {"Tytuł", "Stan"} <= set(shown)
    assert notice == beneath
