"""Rows, actions and commands of the panel's Subscriptions tab."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Final

from anishift.cli.interactive.actions import PANEL_ACTIONS, Action, ScreenActions
from anishift.cli.interactive.anime_state import AnimeRow
from anishift.cli.interactive.state_texts import safe_text
from anishift.cli.interactive.subscription_texts import (
    CHECK_SHOWN_S,
    SubscriptionState,
    check_state,
    check_text,
    row_columns,
    row_state,
    watched_line,
)

__all__ = [
    "NO_SUBSCRIPTIONS",
    "command_kind",
    "shown_check",
    "subscription_actions",
    "subscription_rows",
    "subscription_warning",
]

# ── Constants ─────────────────────────────────────────────────────────────────

NO_SUBSCRIPTIONS: Final[str] = "Brak subskrypcji"
"""Only line of an empty subscription list."""

_CHECKING: Final[str] = "Sprawdzam…"
"""Stan of a subscription whose requested check has not answered yet."""

_SHADOW_WARNING: Final[str] = "Tryb cienia — subskrypcje tylko zapisują propozycje"
"""Status row above the list while the owner records proposals instead of attempts."""

_RESUME_HINT: Final[str] = "O wznów"
"""Key named beside the pause state above the subscription list."""

_ADD_KEYS: Final[str] = "D lub /"
"""Keys the subscription footer names for adding a subscription."""

_COMMANDS: Final[dict[str, str]] = {
    "delete": "subscription_remove",
    "text:x": "subscription_remove",
    "text:r": "subscription_check",
    "text:f": "subscription_check",
}
"""Owner commands of the list keys other than the pause toggle."""


def subscription_rows(
    subscriptions: list[Mapping[str, object]], checks: Mapping[str, tuple[str, str, datetime]], now: datetime
) -> tuple[AnimeRow, ...]:
    """Return one table row per subscription, showing a recent check in place of its state."""
    rows: list[AnimeRow] = []
    for item in subscriptions:
        state: SubscriptionState = row_state(item, now)
        shown: tuple[str, str, datetime] | None = checks.get(str(item.get("subscription_id")))
        if shown is not None and now < shown[2]:
            state = SubscriptionState(shown[0], shown[1])
        episodes, ready = row_columns(item)
        title: str = safe_text(item.get("title", ""))
        rows.append(
            AnimeRow(
                str(item.get("subscription_id")),
                title,
                number=episodes,
                ready=ready,
                status=state.text,
                detail="" if state.detail == state.text else state.detail,
                note=watched_line(item),
            )
        )
    return tuple(rows)


def subscription_actions(row: Mapping[str, object] | None, *, loaded: bool) -> ScreenActions:
    """Return the actions of the highlighted subscription, or adding the first one to a loaded empty list."""
    undo: tuple[Action, ...] = (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS)
    if row is None:
        return ScreenActions(((_ADD_KEYS, "dodaj pierwszą"),) if loaded else (), undo)
    toggle: Action = ("W", "wznów" if row.get("paused") else "wstrzymaj")
    return ScreenActions(
        (("Enter", "szczegóły"), (_ADD_KEYS, "dodaj"), toggle), (("R", "sprawdź teraz"), ("X", "usuń"), *undo)
    )


def subscription_warning(*, problem: bool, pause: str, shadow: bool) -> str:
    """Return the status row above the list: a monitoring problem, the pause or shadow mode."""
    if problem:
        return "Monitoring nie działa: nie można zapisać stanu"
    if pause:
        return f"{pause} · {_RESUME_HINT}"
    return _SHADOW_WARNING if shadow else ""


def command_kind(key: str, row: Mapping[str, object]) -> str:
    """Return the owner command a list key sends for ``row``, the pause toggle by default."""
    return _COMMANDS.get(key, "subscription_resume" if row.get("paused") else "subscription_pause")


def shown_check(check: Mapping[str, object] | None, now: datetime) -> tuple[str, str, datetime]:
    """Return the Stan, notice and expiry of a pending check, or of the owner's result ``check``."""
    expires: datetime = now + timedelta(seconds=CHECK_SHOWN_S)
    if check is None:
        return _CHECKING, _CHECKING, expires
    return check_state(check), check_text(check), expires
