"""The one modal frame every AniShift dialog is built on.

A dialog is a decision, not a place. ``DialogScreen`` owns the dim backdrop, the
panel width, the vertical placement, cancelling and handing the focus back; it
knows nothing about settings, providers or the domain it decides for. A concrete
dialog only fills the panel and says what its cancelled result looks like.

``open_dialog`` is the only way in, which is what keeps the contract of at most
one AniShift dialog at a time: a command that fires again while a dialog is open
changes nothing. Opening remembers the focus through
``lifecycle.open_modal``, and every dismiss path restores it through
``lifecycle.close_modal`` — but only while the remembered element still exists.

Public API:
    DIALOG_MARGIN_COLUMNS: Columns a panel always leaves free on the terminal.
    DIALOG_TOP_DIVISOR: Fraction of the terminal height the panel starts at.
    PANEL_ID: Id of the one panel a dialog draws its content into.
    TITLE_ID: Id of the single-row heading of the panel.
    DialogSize: The three panel widths a dialog may claim.
    dialog_width: Columns one size takes on a terminal of one width.
    dialog_top: Row the panel's top edge sits at on a terminal of one height.
    DialogScreen: The shared modal frame: backdrop, size, cancel and refocus.
    open_dialog: Open one dialog over the current surface, or refuse a second.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any, ClassVar, Final

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from anishift.tui import lifecycle
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.app import App, ComposeResult
    from textual.binding import BindingType
    from textual.events import Click, Resize
    from textual.geometry import Size
    from textual.widget import Widget

    from anishift.tui.state import SessionState

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
    """Columns *size* takes on a terminal of *terminal_width*.

    The panel never claims the last two columns, so shrinking the terminal
    while a dialog is open cannot push the panel off the screen.
    """
    return max(1, min(int(size), terminal_width - DIALOG_MARGIN_COLUMNS))


def dialog_top(*, terminal_height: int) -> int:
    """Row the top edge of the panel sits at on a terminal of *terminal_height*."""
    return max(0, terminal_height // DIALOG_TOP_DIVISOR)


class DialogScreen[T](ModalScreen[T]):
    """The shared modal frame: backdrop, size, cancelling and refocus.

    ``Esc`` and ``Ctrl+C`` are priority bindings of this screen, not registry
    commands: a registry key would claim ``Esc`` for the whole application and
    would add a segment to the status footer, while a screen binding lives and
    dies with the dialog itself.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Anuluj", show=False, priority=True),
        Binding("ctrl+c", "cancel", "Anuluj", show=False, priority=True),
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


def open_dialog[T](
    app: App[Any],
    state: SessionState,
    dialog: DialogScreen[T],
    callback: Callable[[T | None], None] | None = None,
) -> bool:
    """Open *dialog* over the current surface, or refuse a second one.

    Returns ``True`` when the dialog was pushed. A refused call is not an error:
    a key or a command that fires while a dialog is already open must change
    nothing.
    """
    if any(isinstance(screen, DialogScreen) for screen in app.screen_stack):
        logger.debug("Second dialog refused", dialog=type(dialog).__name__)
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
            # Textual runs this callback before it pops the dialog, so the
            # element to focus is only reachable on the next message.
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
