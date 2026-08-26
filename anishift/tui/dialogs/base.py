"""The one modal frame every AniShift dialog is built on, and the only way in."""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar, Final

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from anishift.tui import lifecycle
from anishift.tui.state import FeedbackLevel, SessionState, UiFeedback
from anishift.tui.strings import DIALOG_ALREADY_OPEN, DIALOG_CANCEL_LABEL
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App, ComposeResult
    from textual.binding import BindingType
    from textual.events import Click, Resize
    from textual.geometry import Size
    from textual.widget import Widget

__all__ = [
    "DIALOG_MARGIN_COLUMNS",
    "DIALOG_TOP_DIVISOR",
    "PANEL_ID",
    "TITLE_ID",
    "DialogScreen",
    "DialogSize",
    "dialog_top",
    "dialog_width",
    "open_dialog",
    "refuse_second_dialog",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

DIALOG_MARGIN_COLUMNS: Final[int] = 2
"""Columns the panel always leaves free, so no terminal size can clip it."""

DIALOG_TOP_DIVISOR: Final[int] = 4
"""Fraction of the terminal height the top edge of the panel sits at."""

PANEL_ID: Final[str] = "dialog-panel"
"""Id of the one panel every dialog draws its content into."""

TITLE_ID: Final[str] = "dialog-title"
"""Id of the single-row heading of the panel."""


class DialogSize(IntEnum):
    """The three panel widths a dialog may claim, in columns."""

    MEDIUM = 60
    LARGE = 88
    XLARGE = 116


def dialog_width(size: DialogSize, *, terminal_width: int) -> int:
    """Columns *size* takes on a terminal of *terminal_width*, never the last two."""
    return max(1, min(int(size), terminal_width - DIALOG_MARGIN_COLUMNS))


def dialog_top(*, terminal_height: int) -> int:
    """Row the top edge of the panel sits at on a terminal of *terminal_height*."""
    return max(0, terminal_height // DIALOG_TOP_DIVISOR)


class DialogScreen[T](ModalScreen[T]):
    """The shared modal frame: backdrop, size, cancelling and refocus."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", DIALOG_CANCEL_LABEL, show=False, priority=True),
        Binding("ctrl+c", "cancel", DIALOG_CANCEL_LABEL, show=False, priority=True),
    ]

    def __init__(self, *, title: str, size: DialogSize = DialogSize.LARGE) -> None:
        """Build the panel of one dialog titled *title* and *size* columns wide."""
        super().__init__()
        self._title: str = title
        self._dialog_size: DialogSize = size
        self._panel: Vertical = Vertical(id=PANEL_ID)

    @property
    def dialog_size(self) -> DialogSize:
        """Width class this dialog claims on the terminal."""
        return self._dialog_size

    def compose(self) -> ComposeResult:
        """Draw the heading and the content of the concrete dialog in one panel."""
        with self._panel:
            yield Static(self._title, id=TITLE_ID)
            yield from self.compose_dialog()

    def compose_dialog(self) -> ComposeResult:
        """Rows the concrete dialog draws below the heading."""
        raise NotImplementedError

    def cancel_result(self) -> T:
        """Result this kind of dialog hands back when nothing was decided."""
        raise NotImplementedError

    def on_mount(self) -> None:
        """Place the panel for the terminal the dialog opened on."""
        self._place_panel()

    def on_resize(self, _event: Resize) -> None:
        """Keep the panel inside a terminal that changed while the dialog is open."""
        self._place_panel()

    def on_click(self, event: Click) -> None:
        """Treat a click on the dim backdrop as a cancel."""
        if event.widget is self:
            self.action_cancel()

    def action_cancel(self) -> None:
        """Leave the dialog without a decision, whatever asked for it."""
        self.dismiss(self.cancel_result())

    def _place_panel(self) -> None:
        """Clamp the panel width and push its top edge down the terminal."""
        size: Size = self.app.size
        self._panel.styles.width = dialog_width(self._dialog_size, terminal_width=size.width)
        self._panel.styles.margin = (dialog_top(terminal_height=size.height), 0, 0, 0)


def refuse_second_dialog(app: App[Any], state: SessionState) -> bool:
    """Tell the user one dialog is already open, and report that nothing may open now."""
    if not any(isinstance(screen, DialogScreen) for screen in app.screen_stack):
        return False
    logger.debug("Second dialog refused")
    state.feedback = UiFeedback(level=FeedbackLevel.WARNING, message=DIALOG_ALREADY_OPEN)
    return True


def open_dialog[T](
    app: App[Any],
    state: SessionState,
    dialog: DialogScreen[T],
    callback: Callable[[T | None], None] | None = None,
) -> bool:
    """Push *dialog* over the current surface and return whether it opened."""
    if refuse_second_dialog(app, state):
        return False
    focused: Widget | None = app.focused
    lifecycle.open_modal(state, None if focused is None else focused.id)
    app.push_screen(dialog, _dismissal(app, state, callback))
    return True


def _dismissal[T](
    app: App[Any],
    state: SessionState,
    callback: Callable[[T | None], None] | None,
) -> Callable[[T | None], None]:
    """Wrap *callback* so every dismiss path restores the focus of the caller."""

    def dismissed(result: T | None) -> None:
        """Give the focus back, then hand the result to the caller."""
        focus_id: str | None = lifecycle.close_modal(state)
        if focus_id is not None:
            app.call_next(_refocus, app, focus_id)
        if callback is not None:
            callback(result)

    return dismissed


def _refocus(app: App[Any], focus_id: str) -> None:
    """Focus the remembered element again, but only while it still exists."""
    remembered: list[Widget] = app.screen.query(f"#{focus_id}").nodes
    if not remembered:
        return
    remembered[0].focus()
