from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from anishift.application.control_views import encode_view
from anishift.application.subscription_targets import SubscriptionRow
from anishift.cli.interactive.state import StateController
from anishift.cli.resident import ResidentSession
from anishift.platform.local_control import ControlError, ControlErrorCode


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
        from_number=3,
        downloaded=1,
        targets_total=4,
        due_at=None,
        paused=False,
        pause_reason=None,
        problem=None,
        review_pending=False,
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


@pytest.mark.parametrize("key", ["space", "text:w"])
@pytest.mark.parametrize(
    ("selected", "kind", "identifier"), [(1, "subscription_pause", "a"), (2, "subscription_resume", "b")]
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
    panel._selected = 1

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
    panel._selected = 1

    panel.handle_key("enter")

    assert panel._notice == "Ta subskrypcja nie ma wpisu AniList · usuń ją i dodaj ponownie"
    assert remote.calls == []


@pytest.mark.parametrize(("selected", "key"), [(0, "space"), (0, "delete"), (0, "text:w"), (0, "text:f")])
def test_keys_without_a_meaning_for_the_row_send_nothing(
    panel: StateController, remote: _Remote, selected: int, key: str
) -> None:
    panel._selected = selected

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


def test_every_row_states_its_progress_and_one_honest_state(panel: StateController) -> None:
    now: datetime = datetime.now(UTC)
    panel._subscriptions = [
        _row("p", "Problem", anilist_id=None, problem="season_unrecognized", from_number=None, targets_total=None),
        _row("m", "Moved", paused=True, pause_reason="migrated_missing", review_pending=True, targets_total=None),
        _row("r", "Review", review_pending=True, targets_total=None, from_number=None),
        _row("s", "Soon", due_at=(now + timedelta(days=3, hours=1, seconds=30)).isoformat()),
        _row("h", "Hour", due_at=(now + timedelta(minutes=30, seconds=30)).isoformat()),
        _row("w", "Waiting", due_at=(now - timedelta(days=2, hours=1)).isoformat()),
        _row("y", "Yesterday", due_at=(now - timedelta(days=1, hours=1)).isoformat()),
        _row("n", "Recent", due_at=(now - timedelta(hours=5, minutes=1)).isoformat()),
        _row("u", "Undated"),
    ]

    frame: str = _frame(panel, rows=40)

    assert "D Dodaj subskrypcję · Aktywne: 8" in frame
    assert "Problem · od ? · Pobrano 1/?" in frame
    assert "Nie rozpoznano sezonu — usuń i dodaj ponownie" in frame
    assert "Moved · od 3 · Pobrano 1/?" in frame
    assert "Wstrzymana — zakończona przez starą wersję · W wznów" in frame
    assert "Review · od ? · Pobrano 1/?" in frame
    assert "Sprawdzam przeniesioną subskrypcję" in frame
    assert "Soon · od 3 · Pobrano 1/4" in frame
    assert "Emisja za 3 d 01:00:" in frame
    assert "Emisja za 00:30:" in frame
    assert "Czeka na wydanie (od 2 dni)" in frame
    assert "Czeka na wydanie (od 1 dzień)" in frame
    assert "Czeka na wydanie (od 5 h)" in frame
    assert "Termin nieznany" in frame


@pytest.mark.parametrize(
    ("problem", "auto_enabled", "banner"),
    [
        ("save_failed", True, "Monitoring nie działa: nie można zapisać stanu"),
        ("save_failed", False, "Monitoring nie działa: nie można zapisać stanu"),
        ("", False, "AniShift wstrzymany — subskrypcje czekają"),
    ],
)
def test_the_footer_names_why_monitoring_does_not_progress(
    panel: StateController, problem: str, auto_enabled: bool, banner: str
) -> None:
    panel._subscriptions_problem = problem
    panel._snapshot = {"auto_enabled": auto_enabled}

    assert banner in _frame(panel)


@pytest.mark.parametrize(("columns", "rows"), [(120, 30), (50, 24)])
@pytest.mark.parametrize("subscriptions", [[], [_row("a", "Alpha")]])
def test_the_banner_holds_a_fixed_row_above_the_list_whether_shown_or_not(
    panel: StateController, subscriptions: list[Mapping[str, object]], columns: int, rows: int
) -> None:
    panel._subscriptions = subscriptions
    running: list[str] = _frame(panel, columns, rows).splitlines()
    panel._snapshot = {"auto_enabled": False}
    paused: list[str] = _frame(panel, columns, rows).splitlines()

    add_row: int = next(index for index, line in enumerate(running) if "D Dodaj subskrypcję" in line)
    banner_row: int = next(index for index, line in enumerate(paused) if "subskrypcje czekają" in line)
    assert "D Dodaj subskrypcję" in paused[add_row]
    assert banner_row < add_row
    assert running[banner_row].strip() == ""


def test_a_wrapped_state_line_keeps_its_indent_on_narrow_terminals(panel: StateController) -> None:
    panel._subscriptions = [
        _row("p", "Problem", anilist_id=None, problem="season_unrecognized", from_number=None, targets_total=None)
    ]

    lines: list[str] = _frame(panel, 50, 24).splitlines()

    first: int = next(index for index, line in enumerate(lines) if "Nie rozpoznano" in line)
    continuation: str = lines[first + 1]
    assert "ponownie" in continuation
    assert len(continuation) - len(continuation.lstrip()) == lines[first].index("Nie rozpoznano")


def test_an_empty_list_offers_only_the_add_row(panel: StateController) -> None:
    panel._subscriptions = []

    frame: str = _frame(panel)

    assert "D Dodaj subskrypcję · Brak subskrypcji" in frame
    assert "Aktywne" not in frame


def test_a_healthy_running_list_shows_no_banner(panel: StateController) -> None:
    frame: str = _frame(panel)

    assert "Monitoring nie działa" not in frame
    assert "subskrypcje czekają" not in frame


@pytest.mark.parametrize(("selected", "toggle"), [(1, "W wstrzymaj"), (2, "W wznów")])
def test_the_key_hint_follows_the_selected_row(panel: StateController, selected: int, toggle: str) -> None:
    panel._selected = selected

    frame: str = _frame(panel)

    assert toggle in frame
    assert "Ctrl+Z cofnij" in frame


@pytest.mark.parametrize(("columns", "rows"), [(120, 30), (50, 24), (50, 12)])
def test_the_list_fits_narrow_and_short_terminals(panel: StateController, columns: int, rows: int) -> None:
    panel._subscriptions = [_row(f"s{index}", f"Series {index}") for index in range(30)]

    lines: list[str] = _frame(panel, columns, rows).splitlines()

    assert len(lines) <= rows
    assert all(len(line) <= columns for line in lines)
