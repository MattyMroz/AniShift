"""The one table the shell lists discovered source groups in, keyed by group id."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, cast

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

from anishift.application import ArtifactKind, ArtifactState, group_is_ready
from anishift.tui import workers
from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.state import RunUiState
from anishift.tui.strings import (
    COMMAND_REFRESH_DESCRIPTION,
    COMMAND_REFRESH_TITLE,
    COMPOSER_ACCENT_GLYPH,
    GLYPH_GAP,
    GROUP_COLUMN_GAP,
    GROUP_CONFLICT_GLYPH,
    GROUP_MISSING_GLYPH,
    GROUP_READY_GLYPH,
    GROUP_SELECTED_GLYPH,
    GROUP_STATE_CONFLICT,
    GROUP_STATE_NO_SIDECAR,
    GROUP_STATE_READY,
    GROUP_UNSELECTED_GLYPH,
    SELECT_FILTER_PLACEHOLDER,
    SELECT_NO_RESULTS,
    SELECTION_SUMMARY,
    SETTING_LIST_SEPARATOR,
    STATUS_GLYPH,
    WORKSPACE_EMPTY,
)
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.binding import BindingType
    from textual.events import Key, MouseMove
    from textual.screen import Screen

    from anishift.application import AppService, Artifact, InspectedSourceGroup, InspectedWorkspace
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandRun
    from anishift.tui.state import SessionState

__all__ = [
    "CURSOR_MARK",
    "MIN_WINDOW_ROWS",
    "PAGE_ROWS",
    "REFRESH_COMMAND_NAME",
    "REFRESH_KEY",
    "WORKSPACE_SCOPE",
    "GroupRow",
    "GroupState",
    "GroupTable",
    "WorkspaceHost",
    "filtered_rows",
    "group_line",
    "group_rows",
    "group_state",
    "groups_body",
    "listed_top",
    "pointed_row",
    "refresh_available",
    "state_text",
    "table_body",
    "window_start",
]

logger = get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

CURSOR_MARK: Final[str] = COMPOSER_ACCENT_GLYPH
"""Gutter of the row every contextual key acts on, so no colour has to carry it."""

MIN_WINDOW_ROWS: Final[int] = 8
"""Rows the table lists at once while its container has no room left under the summary block."""

PAGE_ROWS: Final[int] = 10
"""Rows one page key moves the cursor by."""

REFRESH_COMMAND_NAME: Final[str] = "refresh"
"""Name the registry holds the contextual refresh action under."""

REFRESH_KEY: Final[str] = "ctrl+r"
"""Key the contextual refresh action answers to."""

WORKSPACE_SCOPE: Final[str] = "workspace"
"""Registry scope a listed table owns while it is on screen, and never longer."""

_HEADER_ROWS: Final[int] = 4
"""Rows the summary block may take above the first listed group."""

_VIDEO_KINDS: Final[tuple[ArtifactKind, ...]] = (ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4)
"""Container kinds a group names its main source with, the preferred one first."""

_DIGIT_RUN: Final[re.Pattern[str]] = re.compile(r"(\d+)")
"""Split of one name into its alternating text and number parts."""

_DIGIT_WIDTH: Final[int] = 12
"""Digits one number part is padded to, so 2 orders before 10."""

_DIGIT_PAD: Final[str] = "0"
"""Character padding a number part up to a comparable width."""

_SUFFIX_MARK: Final[str] = "."
"""Character introducing the extension a file name ends with."""

_REFRESH_RUN_STATES: Final[frozenset[RunUiState]] = frozenset({RunUiState.IDLE, RunUiState.TERMINAL})
"""Run states a refresh may replace the whole workspace projection under."""


class GroupState(StrEnum):
    """What an inspection found about one source group."""

    READY = "ready"
    CONFLICT = "conflict"
    NO_SIDECAR = "no_sidecar"


_STATE_GLYPHS: Final[dict[GroupState, str]] = {
    GroupState.READY: GROUP_READY_GLYPH,
    GroupState.CONFLICT: GROUP_CONFLICT_GLYPH,
    GroupState.NO_SIDECAR: GROUP_MISSING_GLYPH,
}
"""Glyph every group state is marked with, so colour is never the only signal."""

_STATE_WORDS: Final[dict[GroupState, str]] = {
    GroupState.READY: GROUP_STATE_READY,
    GroupState.CONFLICT: GROUP_STATE_CONFLICT,
    GroupState.NO_SIDECAR: GROUP_STATE_NO_SIDECAR,
}
"""Word every group state is named by."""


@dataclass(frozen=True, slots=True)
class GroupRow:
    """One source group as the table lists it, identified by its stable id."""

    name: str
    state: GroupState
    selected: bool
    group_id: str = ""
    source: str = ""
    artifacts: str = ""


class WorkspaceHost(workers.WorkerHost, Protocol):
    """The shell capabilities this table reaches for, and nothing more."""

    @property
    def service(self) -> AppService:
        """The one application facade every workflow of the shell goes through."""
        ...

    @property
    def session_state(self) -> SessionState:
        """The single session state the shell owns."""
        ...

    @property
    def commands(self) -> CommandRegistry:
        """The one registry every command and contextual action of the shell goes through."""
        ...


def refresh_available(state: SessionState) -> bool:
    """Whether *state* lets a refresh discard and rebuild the workspace projection."""
    return state.run_state in _REFRESH_RUN_STATES and not state.modal_focus_stack


def _refresh_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the refresh key and its palette row."""
    return CommandSpec(
        name=REFRESH_COMMAND_NAME,
        title=COMMAND_REFRESH_TITLE,
        description=COMMAND_REFRESH_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=refresh_available,
        keys=(REFRESH_KEY,),
    )


def state_text(state: GroupState) -> str:
    """Return the glyph and the word one group state is shown as."""
    return f"{_STATE_GLYPHS[state]}{GLYPH_GAP}{_STATE_WORDS[state]}"


def group_state(group: InspectedSourceGroup) -> GroupState:
    """Return the word and glyph state of one group, asking the application for its readiness."""
    if group.conflicts:
        return GroupState.CONFLICT
    if group_is_ready(group):
        return GroupState.READY
    return GroupState.NO_SIDECAR


def group_rows(
    workspace: InspectedWorkspace | None,
    *,
    selected: frozenset[str] | None = None,
    descending: bool = False,
) -> tuple[GroupRow, ...]:
    """Project every inspected group into its row, in the one natural order."""
    groups: tuple[InspectedSourceGroup, ...] = () if workspace is None else workspace.groups
    picked: frozenset[str] = frozenset() if selected is None else selected
    return tuple(
        GroupRow(
            name=group.source.stem,
            state=group_state(group),
            selected=group.group_id in picked,
            group_id=group.group_id,
            source=_main_source(group),
            artifacts=_artifact_summary(group),
        )
        for group in sorted(groups, key=_order_key, reverse=descending)
    )


def filtered_rows(rows: Sequence[GroupRow], query: str) -> tuple[GroupRow, ...]:
    """Return the rows whose name holds *query*, matched without regard to case."""
    needle: str = query.strip().casefold()
    if not needle:
        return tuple(rows)
    return tuple(row for row in rows if needle in row.name.casefold())


def window_start(cursor: int, count: int, height: int, anchor: int = 0) -> int:
    """Return the first row a window of *height* rows shows, left on *anchor* while it holds *cursor*."""
    if height <= 0 or count <= height:
        return 0
    settled: int = max(0, min(anchor, count - height))
    if cursor < settled:
        return cursor
    if cursor >= settled + height:
        return cursor - height + 1
    return settled


def pointed_row(line: int, *, top: int, start: int, listed: int) -> int | None:
    """Return the listed row rendered at *line*, or ``None`` off every listed row."""
    offset: int = line - top
    if not 0 <= offset < listed:
        return None
    return start + offset


def group_line(row: GroupRow, *, name_width: int, source_width: int = 0, artifacts_width: int = 0) -> str:
    """Return one group row: its selection marker, its columns and its state."""
    marker: str = GROUP_SELECTED_GLYPH if row.selected else GROUP_UNSELECTED_GLYPH
    cells: tuple[str, ...] = (
        row.name.ljust(name_width),
        row.source.ljust(source_width),
        row.artifacts.ljust(artifacts_width),
        state_text(row.state),
    )
    return f"{marker}{GLYPH_GAP}{GROUP_COLUMN_GAP.join(cells)}"


def table_body(  # noqa: PLR0913 - the one renderer of the table, so its whole contract stays explicit
    rows: Sequence[GroupRow],
    *,
    cursor: int = 0,
    query: str = "",
    window: int = MIN_WINDOW_ROWS,
    anchor: int = 0,
    status: str = "",
) -> str:
    """Render the summary of *rows* and the window of matches *anchor* holds *cursor* in."""
    if not rows:
        return WORKSPACE_EMPTY
    header: list[str] = _header(rows, query=query, status=status)
    matches: tuple[GroupRow, ...] = filtered_rows(rows, query)
    if not matches:
        return "\n".join([*header, "", SELECT_NO_RESULTS])
    widths: tuple[int, int, int] = _widths(matches)
    start: int = window_start(cursor, len(matches), window, anchor)
    listed: list[str] = [
        _table_line(row, cursor=index == cursor, widths=widths)
        for index, row in enumerate(matches[start : start + window], start=start)
    ]
    return "\n".join([*header, "", *listed])


def listed_top(rows: Sequence[GroupRow], *, query: str = "", status: str = "") -> int:
    """Return the rendered line the first row ``table_body`` lists sits on."""
    return len(_header(rows, query=query, status=status)) + 1


def groups_body(rows: Sequence[GroupRow], *, status: str = "") -> str:
    """Render every row of *rows* at once, without a window and without a filter."""
    return table_body(rows, window=len(rows), status=status)


def _header(rows: Sequence[GroupRow], *, query: str, status: str) -> list[str]:
    """Return the selection summary, then the run status and the filter when set."""
    lines: list[str] = [
        SELECTION_SUMMARY.format(selected=sum(1 for row in rows if row.selected), total=len(rows)),
    ]
    if status:
        lines.append(f"{STATUS_GLYPH}{GLYPH_GAP}{status}")
    if query:
        lines.append(f"{SELECT_FILTER_PLACEHOLDER}{GLYPH_GAP}{query}")
    return lines


def _table_line(row: GroupRow, *, cursor: bool, widths: tuple[int, int, int]) -> str:
    """Return one listed row behind the gutter marking the row keys act on."""
    gutter: str = CURSOR_MARK if cursor else GLYPH_GAP
    body: str = group_line(
        row,
        name_width=widths[0],
        source_width=widths[1],
        artifacts_width=widths[2],
    )
    return f"{gutter}{body}"


def _widths(rows: Sequence[GroupRow]) -> tuple[int, int, int]:
    """Return the columns the name, the source and the artifacts each take."""
    return (
        max(len(row.name) for row in rows),
        max(len(row.source) for row in rows),
        max(len(row.artifacts) for row in rows),
    )


def _order_key(group: InspectedSourceGroup) -> tuple[str, str]:
    """Return the one order of the table: the natural name, then the stable id."""
    return _natural_key(group.source.stem), group.group_id


def _natural_key(name: str) -> str:
    """Return the key ordering *name* so the numbers inside it compare as numbers."""
    return "".join(
        part.rjust(_DIGIT_WIDTH, _DIGIT_PAD) if part.isdigit() else part for part in _DIGIT_RUN.split(name.casefold())
    )


def _main_source(group: InspectedSourceGroup) -> str:
    """Return the format of the main source of one group, never any path of it."""
    for kind in _VIDEO_KINDS:
        video: Artifact | None = next((artifact for artifact in group.artifacts if artifact.kind is kind), None)
        if video is not None:
            return _format_of(video)
    first: Artifact | None = next(iter(group.artifacts), None)
    return "" if first is None else _format_of(first)


def _artifact_summary(group: InspectedSourceGroup) -> str:
    """Return the format of every artifact of one group, unusable ones marked."""
    return SETTING_LIST_SEPARATOR.join(_artifact_cell(artifact) for artifact in group.artifacts)


def _artifact_cell(artifact: Artifact) -> str:
    """Return the format of one artifact, glyph-marked when validation refused it."""
    text: str = _format_of(artifact)
    if artifact.state is ArtifactState.READY:
        return text
    return f"{GROUP_MISSING_GLYPH}{text}"


def _format_of(artifact: Artifact) -> str:
    """Return the extension of one artifact, which is never a path of its own."""
    if artifact.path is None:
        return ""
    return artifact.path.suffix.removeprefix(_SUFFIX_MARK).casefold()


def _clamped(cursor: int, count: int) -> int:
    """Return the cursor kept inside the *count* rows currently listed."""
    if count <= 0:
        return 0
    return max(0, min(cursor, count - 1))


class GroupTable(Static):
    """Discovered source groups, selected by stable group id and never by row index."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("pageup", "page_up", show=False),
        Binding("pagedown", "page_down", show=False),
        Binding("space", "toggle_group", show=False),
        Binding("backspace", "erase_filter", show=False),
        Binding("escape", "clear_filter", show=False),
        Binding("ctrl+s", "reverse_order", show=False),
    ]

    can_focus = False

    def __init__(self, *, widget_id: str) -> None:
        """Build the empty table; the shell fills it from the inspected workspace."""
        super().__init__(id=widget_id, markup=False)
        self._cursor: int = 0
        self._query: str = ""
        self._descending: bool = False
        self._status: str = ""
        self._window_top: int = 0
        self._window_rows: int = MIN_WINDOW_ROWS
        self._shown: tuple[GroupRow, ...] = ()

    @property
    def filter_query(self) -> str:
        """Text every listed row currently has to hold."""
        return self._query

    @property
    def cursor(self) -> int:
        """Listed row every contextual key of the table acts on."""
        return self._cursor

    @property
    def window_top(self) -> int:
        """First listed row the table currently shows, which no pointer ever moves."""
        return self._window_top

    @property
    def descending(self) -> bool:
        """Whether the one natural order of the table is currently turned around."""
        return self._descending

    def show(self, workspace: InspectedWorkspace | None) -> None:
        """Render *workspace*, keeping neither it nor the generation that produced it."""
        self.show_rows(self._project(workspace), status=self._status)

    def show_rows(self, rows: Sequence[GroupRow], *, status: str = "") -> None:
        """Render rows the caller projected itself, such as a simulated sequence."""
        self._status = status
        self._shown = tuple(rows)
        self.can_focus = bool(rows)
        matches: int = len(filtered_rows(rows, self._query))
        self._cursor = _clamped(self._cursor, matches)
        self._window_rows = self._window()
        self._window_top = window_start(self._cursor, matches, self._window_rows, self._window_top)
        self.update(
            table_body(
                rows,
                cursor=self._cursor,
                query=self._query,
                window=self._window_rows,
                anchor=self._window_top,
                status=status,
            ),
        )

    def on_mount(self) -> None:
        """Follow every layout of the screen, because a reflow never resizes this table itself."""
        self.screen.screen_layout_refresh_signal.subscribe(self, self._reflow)

    def on_show(self) -> None:
        """Own the refresh action for exactly as long as this table is on screen."""
        host: WorkspaceHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(WORKSPACE_SCOPE)
        host.commands.register((_refresh_action(self.action_refresh),), scope=WORKSPACE_SCOPE)

    def on_hide(self) -> None:
        """Give the refresh action back the moment this table leaves the screen."""
        host: WorkspaceHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(WORKSPACE_SCOPE)

    def on_mouse_move(self, event: MouseMove) -> None:
        """Carry the cursor to the row the pointer rests on, touching neither the window nor the selection."""
        pointed: int | None = self._pointed_row(event.offset.y)
        if pointed is None or pointed == self._cursor:
            return
        self._cursor = pointed
        self._paint()

    def on_key(self, event: Key) -> None:
        """Take one printable key into the filter, leaving every bound key alone."""
        character: str | None = event.character
        if character is None or character.isspace() or not character.isprintable():
            return
        if self._rows() is None:
            return
        event.stop()
        event.prevent_default()
        self._query += character
        self._cursor = 0
        self._paint()

    def action_cursor_up(self) -> None:
        """Move the cursor one listed row up."""
        self._move(-1)

    def action_cursor_down(self) -> None:
        """Move the cursor one listed row down."""
        self._move(1)

    def action_page_up(self) -> None:
        """Move the cursor one page of listed rows up."""
        self._move(-PAGE_ROWS)

    def action_page_down(self) -> None:
        """Move the cursor one page of listed rows down."""
        self._move(PAGE_ROWS)

    def action_toggle_group(self) -> None:
        """Add the group under the cursor to the selection, or take it out."""
        host: WorkspaceHost | None = self._host()
        rows: tuple[GroupRow, ...] | None = self._rows()
        if host is None or rows is None:
            return
        matches: tuple[GroupRow, ...] = filtered_rows(rows, self._query)
        if not 0 <= self._cursor < len(matches):
            return
        host.session_state.selected_group_ids ^= {matches[self._cursor].group_id}
        self._paint()

    def action_erase_filter(self) -> None:
        """Take the last character back out of the filter."""
        if not self._query or self._rows() is None:
            return
        self._query = self._query[:-1]
        self._cursor = 0
        self._paint()

    def action_clear_filter(self) -> None:
        """Drop the whole filter and list every discovered group again."""
        if not self._query or self._rows() is None:
            return
        self._query = ""
        self._cursor = 0
        self._paint()

    def action_reverse_order(self) -> None:
        """Turn the one order of the table around, keeping every selected group."""
        if self._rows() is None:
            return
        self._descending = not self._descending
        self._cursor = 0
        self._paint()

    def action_refresh(self) -> None:
        """Inspect the workspace again off the UI thread, under the current generation."""
        host: WorkspaceHost | None = self._host()
        if host is None:
            return
        generation: int = host.session_state.generation
        logger.info("Workspace refresh requested", generation=generation)
        workers.discover(host, host.service, generation=generation)

    def _reflow(self, _screen: Screen[object]) -> None:
        """Redraw the last rows the one time a layout leaves the container another height."""
        if self._window() == self._window_rows:
            return
        self.show_rows(self._shown, status=self._status)

    def _move(self, delta: int) -> None:
        """Move the cursor *delta* listed rows and redraw the window around it."""
        rows: tuple[GroupRow, ...] | None = self._rows()
        if rows is None:
            return
        self._cursor = _clamped(self._cursor + delta, len(filtered_rows(rows, self._query)))
        self._paint()

    def _paint(self) -> None:
        """Redraw from the workspace and the selection the session state holds."""
        host: WorkspaceHost | None = self._host()
        if host is None:
            return
        self.show(host.session_state.workspace)

    def _pointed_row(self, line: int) -> int | None:
        """Listed row the pointer rests on at rendered *line*, or ``None`` off every listed row."""
        rows: tuple[GroupRow, ...] | None = self._rows()
        if rows is None:
            return None
        matches: tuple[GroupRow, ...] = filtered_rows(rows, self._query)
        if not matches:
            return None
        return pointed_row(
            line,
            top=listed_top(rows, query=self._query, status=self._status),
            start=self._window_top,
            listed=min(self._window_rows, len(matches) - self._window_top),
        )

    def _rows(self) -> tuple[GroupRow, ...] | None:
        """Project the inspected workspace, or refuse while the shell holds none."""
        host: WorkspaceHost | None = self._host()
        if host is None or host.session_state.workspace is None:
            return None
        return self._project(host.session_state.workspace)

    def _project(self, workspace: InspectedWorkspace | None) -> tuple[GroupRow, ...]:
        """Turn *workspace* into rows under the one selection and the one order."""
        return group_rows(workspace, selected=self._selected(), descending=self._descending)

    def _selected(self) -> frozenset[str]:
        """Group ids the session state currently holds selected."""
        host: WorkspaceHost | None = self._host()
        if host is None:
            return frozenset()
        return frozenset(host.session_state.selected_group_ids)

    def _window(self) -> int:
        """Rows the table lists at once, never more than the height its container offers."""
        parent: object = self.parent
        if not isinstance(parent, Widget):
            return MIN_WINDOW_ROWS
        height: int = parent.content_size.height
        if height <= _HEADER_ROWS:
            return MIN_WINDOW_ROWS
        return height - _HEADER_ROWS

    def _host(self) -> WorkspaceHost | None:
        """The shell around this table, or ``None`` while it is not mounted."""
        if not self.is_attached:
            return None
        return cast("WorkspaceHost", self.app)
