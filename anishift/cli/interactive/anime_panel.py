"""Input adapter for the production Anime view and injected catalogue actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from rich.text import Text

from anishift.application.episode_commands import MAX_EPISODE_KEYS
from anishift.cli.interactive.anime_clipboard import copy_text
from anishift.cli.interactive.anime_state import (
    FLASH_SECONDS,
    AnimeRow,
    AnimeScreen,
    AnimeViewState,
    NoticeKind,
)
from anishift.cli.interactive.anime_view import AnimeFrame, render_anime
from anishift.cli.interactive.pointer import COPY_KEYS, Click, ClickKind, Gesture, PointerGesture
from anishift.cli.interactive.text_input import TextInput


class AnimePanel:
    """Own view interactions while delegating catalogue and download work to the caller."""

    def __init__(
        self,
        state: AnimeViewState,
        action: Callable[[str, tuple[str, ...]], None],
        clock: Callable[[], float],
        clipboard: Callable[[str], bool] = copy_text,
    ) -> None:
        self.state: AnimeViewState = state
        self._action: Callable[[str, tuple[str, ...]], None] = action
        self._clock: Callable[[], float] = clock
        self._clipboard: Callable[[str], bool] = clipboard
        self._frame: AnimeFrame | None = None
        self._size: tuple[int, int] = (80, 24)
        self._gesture: PointerGesture = PointerGesture(clock)

    def frame(self, columns: int, rows: int) -> Text:
        """Build a frame and retain only the last painted interaction map."""
        if self._size != (columns, rows):
            self.state.selection = None
            self._gesture.reset()
        self._size = (columns, rows)
        now: float = self._clock()
        self.state.flashes = {key: deadline for key, deadline in self.state.flashes.items() if deadline > now}
        self._frame = render_anime(self.state.snapshot(columns), columns, rows, now)
        return self._frame.text

    def switch_state(self, state: AnimeViewState) -> None:
        """Restore a view while discarding mouse coordinates from both painted contexts."""
        self.state.selection = None
        self.state = state
        self.state.selection = None
        self._gesture.reset()
        self._frame = None

    def _clear_notice(self) -> None:
        self.state.notice = ""
        self.state.notice_kind = NoticeKind.INFO

    def show(self, screen: AnimeScreen, title: str, items: tuple[AnimeRow, ...]) -> None:
        """Install owner-provided display rows without inferring domain identities."""
        self.state.screen = screen
        self.state.title = title
        self.state.items = items
        self.state.cursor = next((index for index, item in enumerate(items) if item.navigable), 0)
        self.state.offset = 0
        self.state.selection = None
        self._clear_notice()
        self._gesture.reset()
        self._frame = None

    def handle(self, key: str) -> None:
        """Route normalized terminal keys, giving selected-text copying priority."""
        letter: str = key.removeprefix("text:").lower()
        self._clear_notice()
        if (key in COPY_KEYS or letter == "c") and self.copy(key):
            return
        if self._edit(key):
            return
        if key in {"escape", "interrupt"}:
            self.state.selection = None
            self._action("back", ())
            return
        if self._navigate(key):
            return
        self._command(letter, key)

    def _edit(self, key: str) -> bool:
        editor: TextInput | None = self.state.range_input
        if editor is not None:
            if key in {"escape", "interrupt"}:
                self.state.range_input = None
            elif key == "enter":
                self.state.apply_range(editor.text)
            else:
                editor.handle(key)
            return True
        if self.state.screen is not AnimeScreen.QUERY:
            return False
        if key in {"escape", "interrupt"} and self.state.query_focused:
            self.state.query_focused = False
            return True
        if not self.state.query_focused:
            if key.startswith(("text:", "paste:")) or key == "enter":
                self.state.query_focused = True
            else:
                return False
        if key == "enter":
            if self.state.query.text.strip():
                self._action("search", (self.state.query.text.strip(),))
            return True
        return self.state.query.handle(key)

    def copy(self, key: str) -> bool:
        """Copy painted selection or the current row before navigation handles the key."""
        if key not in COPY_KEYS and (self.state.screen is AnimeScreen.QUERY or self.state.range_input is not None):
            return False
        value: str = self._frame.selected_text(self.state.selection) if self._frame is not None else ""
        editor: TextInput | None = self.state.range_input
        if self.state.screen is AnimeScreen.QUERY and self.state.query_focused:
            editor = self.state.query
        if not value and editor is not None and key in COPY_KEYS:
            value = editor.selected_text
        if not value and (key == "interrupt" or self.state.screen is AnimeScreen.QUERY or self.state.range_input):
            return False
        selected: bool = bool(value)
        if not value and self.state.items:
            value = self.state.items[self.state.cursor].copy_text
        if value:
            success: bool = self._clipboard(value)
            self.state.notice = (
                ("Skopiowano zaznaczenie" if selected else "Skopiowano wiersz")
                if success
                else "Nie udało się skopiować"
            )
            self.state.notice_kind = NoticeKind.SUCCESS if success else NoticeKind.WARNING
        return bool(value)

    def _navigate(self, key: str) -> bool:
        visible: int = max(self._frame.visible, 1) if self._frame is not None else 1
        destinations: dict[str, int] = {
            "up": self.state.cursor - 1,
            "down": self.state.cursor + 1,
            "pageup": self.state.cursor - visible,
            "pagedown": self.state.cursor + visible,
            "home": 0,
            "end": len(self.state.items) - 1,
        }
        if key not in destinations:
            return False
        available: list[int] = [index for index, item in enumerate(self.state.items) if item.navigable]
        if not available:
            return True
        target: int = max(0, min(destinations[key], len(self.state.items) - 1))
        direction: int = -1 if key in {"up", "pageup", "end"} else 1
        beyond: list[int] = [index for index in available if (index - target) * direction >= 0]
        if key in {"up", "down"} and not [index for index in available if (index - self.state.cursor) * direction > 0]:
            beyond = [available[-1] if key == "up" else available[0]]
        self.state.cursor = min(beyond, key=lambda index: abs(index - target)) if beyond else self.state.cursor
        self.state.offset = min(self.state.offset, self.state.cursor)
        self.state.offset = max(self.state.offset, self.state.cursor - visible + 1)
        self.state.selection = None
        return True

    def _command(self, letter: str, key: str) -> None:
        if key == "space" and self.state.screen in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}:
            self.state.toggle()
        elif letter == "a":
            self.state.select_all()
        elif letter == "z" and self.state.screen is AnimeScreen.EPISODES and not self.state.searching:
            self.state.range_input = TextInput()
        elif letter == "d":
            self._download()
        elif letter == "p" and self.state.searching:
            self.state.notice = "Trwa wyszukiwanie wydań"
        elif key == "enter" or letter in {"i", "p", "s", "?", "/"}:
            if self.state.items and not self.state.items[self.state.cursor].navigable:
                return
            keys: tuple[str, ...] = (self.state.items[self.state.cursor].key,) if self.state.items else ()
            self._action(letter, keys)

    def _download(self) -> None:
        if self.state.searching:
            self.state.notice = "Trwa wyszukiwanie wydań"
            return
        if not self.state.items or self.state.screen not in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}:
            return
        chosen: tuple[AnimeRow, ...] = tuple(item for item in self.state.items if item.key in self.state.selected)
        chosen = chosen or (self.state.items[self.state.cursor],)
        if len(chosen) > MAX_EPISODE_KEYS:
            self.state.notice = "Limit: 100 odcinków | Z zmień zakres"
            return
        if any(not item.eligible for item in chosen):
            refused: AnimeRow = next(item for item in chosen if not item.eligible)
            self.state.notice = refused.refusal
        eligible: tuple[str, ...] = tuple(item.key for item in chosen if item.eligible)
        if eligible:
            self._action("download", eligible)

    def searching(self, keys: tuple[str, ...]) -> None:
        """Mark only an active request as pending; never infer an admission."""
        if not self.state.searching:
            self.state.batch_results.clear()
        self.state.searching.update(keys)
        self.state.notice = "Szukam wydań…"
        self.state.notice_kind = NoticeKind.INFO

    def result(self, key: str, *, admitted: bool, status: str = "Brak wydania", cause: str = "") -> None:
        """Apply one confirmed result and expire its acknowledgement independently."""
        self.state.batch_results[key] = None if admitted else cause
        self.state.searching.discard(key)
        self.state.items = tuple(
            replace(item, status="Zlecono" if admitted else status, eligible=not admitted) if item.key == key else item
            for item in self.state.items
        )
        if admitted:
            self.state.selected.discard(key)
            self.state.flashes[key] = self._clock() + FLASH_SECONDS
        successes: list[str] = []
        failures: list[str] = []
        for item in self.state.items:
            if item.key not in self.state.batch_results:
                continue
            label: str = item.number or item.title
            refused: str | None = self.state.batch_results[item.key]
            if refused is None:
                successes.append(label)
            else:
                failures.append(f"{label}: {refused}" if refused else label)
        parts: list[str] = []
        if successes:
            parts.append("Zlecono " + ", ".join(successes))
        if failures:
            parts.append(("nie zlecono " if successes else "Nie zlecono ") + ", ".join(failures))
            parts.append("I wydania")
        self.state.notice = " · ".join(parts)
        self.state.notice_kind = NoticeKind.WARNING if failures else NoticeKind.SUCCESS

    def scroll(self, direction: int) -> None:
        """Scroll without changing the keyboard cursor or episode choices."""
        self._clear_notice()
        visible: int = self._frame.visible if self._frame is not None else 1
        self.state.offset = max(0, min(self.state.offset + direction, len(self.state.items) - visible))
        self.state.selection = None
        self._gesture.reset()

    def mouse(self, event: MouseEvent) -> Click:
        """Select only painted text on drag; a click clears the selection, points at its row and names the request."""
        gesture: Gesture | None = self._gesture.track(event)
        if gesture is None:
            return Click()
        if event.event_type is MouseEventType.MOUSE_DOWN:
            self._clear_notice()
        self.state.selection = gesture.selection
        click: Click = self._gesture.resolve(self._frame.text if self._frame is not None else Text(), gesture)
        if click.kind not in {ClickKind.ROW, ClickKind.LINE}:
            return click
        if click.value >= len(self.state.items) or not self.state.items[click.value].navigable:
            self._gesture.reset()
            return Click()
        self.state.cursor = click.value
        return click
