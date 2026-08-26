"""The screen showing what the run that ended left behind, and the manual recovery it offers."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from textual.widgets import Static

from anishift.application import GroupStatus
from anishift.application.intents import ProductKind
from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.state import GroupIntentDraft
from anishift.tui.strings import (
    EXECUTION_CANCELLED_GLYPH,
    EXECUTION_DONE_GLYPH,
    EXECUTION_FAILED_GLYPH,
    EXECUTION_STATE_CANCELLED,
    EXECUTION_STATE_FAILED,
    GLYPH_GAP,
    GROUP_COLUMN_GAP,
    PLAN_GROUP_GLYPH,
    PLAN_INDENT,
    PLAN_NONE,
    PLAN_PRODUCTS_LABEL,
    RESULTS_BACK_DESCRIPTION,
    RESULTS_BACK_TITLE,
    RESULTS_EMPTY,
    RESULTS_ERROR_LABEL,
    RESULTS_MANUAL_DESCRIPTION,
    RESULTS_MANUAL_TITLE,
    RESULTS_OPEN_DESCRIPTION,
    RESULTS_PARTIAL_GLYPH,
    RESULTS_PRESERVED_LABEL,
    RESULTS_RECOVERY_HINT,
    RESULTS_STATUS_PARTIAL,
    RESULTS_STATUS_SUCCEEDED,
    RESULTS_SUMMARY,
    RESULTS_TITLE,
    RESULTS_WARNINGS_LABEL,
)
from anishift.tui.widgets.plan_view import relative_text

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from anishift.application import GroupResult, ProducedArtifact, RunResult
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.commands.spec import CommandRun
    from anishift.tui.state import SessionState

__all__ = [
    "MANUAL_COMMAND_NAME",
    "MANUAL_KEY",
    "RESULTS_COMMAND_NAME",
    "RESULTS_ID",
    "RESULTS_SCOPE",
    "WORKSPACE_COMMAND_NAME",
    "ResultsHost",
    "ResultsView",
    "group_lines",
    "recoverable_groups",
    "recovery_available",
    "recovery_draft",
    "results_action",
    "results_available",
    "results_body",
    "results_lines",
    "status_text",
]

# ── Constants ──────────────────────────────────────────────────────────────

RESULTS_ID: Final[str] = "results-view"
"""Identifier of the one region rendering the result of a finished run."""

RESULTS_SCOPE: Final[str] = "results"
"""Registry scope the results screen owns while it is on screen, and never longer."""

RESULTS_COMMAND_NAME: Final[str] = "results"
"""Name of the action showing the result the session holds, and nothing else."""

MANUAL_COMMAND_NAME: Final[str] = "results-manual"
"""Name of the contextual action preparing one manual draft out of a result."""

WORKSPACE_COMMAND_NAME: Final[str] = "results-workspace"
"""Name of the contextual action leaving the results for the workspace."""

MANUAL_KEY: Final[str] = "ctrl+l"
"""Key preparing a manual draft for a group that did not finish."""

_STATUS_GLYPHS: Final[Mapping[GroupStatus, str]] = MappingProxyType(
    {
        GroupStatus.SUCCEEDED: EXECUTION_DONE_GLYPH,
        GroupStatus.PARTIAL: RESULTS_PARTIAL_GLYPH,
        GroupStatus.FAILED: EXECUTION_FAILED_GLYPH,
        GroupStatus.CANCELLED: EXECUTION_CANCELLED_GLYPH,
    },
)
"""Glyph every terminal group status is marked with, so colour is never the only signal."""

_STATUS_WORDS: Final[Mapping[GroupStatus, str]] = MappingProxyType(
    {
        GroupStatus.SUCCEEDED: RESULTS_STATUS_SUCCEEDED,
        GroupStatus.PARTIAL: RESULTS_STATUS_PARTIAL,
        GroupStatus.FAILED: EXECUTION_STATE_FAILED,
        GroupStatus.CANCELLED: EXECUTION_STATE_CANCELLED,
    },
)
"""Word every terminal group status is named by, beside its own glyph."""

_RECOVERABLE: Final[frozenset[GroupStatus]] = frozenset({GroupStatus.PARTIAL, GroupStatus.FAILED})
"""Statuses of a group one manual draft could take further, partial included."""


def status_text(status: GroupStatus) -> str:
    """Return the glyph and the word one terminal group status is shown by."""
    return f"{_STATUS_GLYPHS[status]}{GLYPH_GAP}{_STATUS_WORDS[status]}"


def results_available(state: SessionState) -> bool:
    """Whether this session holds the result of a run it can show."""
    return state.result is not None


def recoverable_groups(result: RunResult | None) -> tuple[GroupResult, ...]:
    """Return every group of *result* a manual draft could take further."""
    if result is None:
        return ()
    return tuple(group for group in result.groups if group.status in _RECOVERABLE)


def recovery_available(state: SessionState) -> bool:
    """Whether *state* holds a group one manual draft could take further right now."""
    return bool(recoverable_groups(state.result)) and not state.modal_focus_stack


def recovery_draft(state: SessionState, group_id: str) -> GroupIntentDraft:
    """Return a manual draft of *group_id* holding mutable state and fresh sources of its own."""
    kept: GroupIntentDraft | None = state.manual_drafts.get(group_id)
    if kept is None:
        return GroupIntentDraft(group_id=group_id, products={ProductKind.FULL_PL})
    draft: GroupIntentDraft = kept.clone_for(group_id)
    draft.preferred_video_artifact_id = None
    draft.selected_subtitle_artifact_id = None
    draft.selected_audio_artifact_id = None
    draft.selected_audio_track_id = None
    draft.selected_subtitle_track_id = None
    return draft


def group_lines(group: GroupResult, *, root: Path | None) -> tuple[str, ...]:
    """Return every line one terminal group contributes to the results."""
    heading: str = f"{PLAN_GROUP_GLYPH}{GLYPH_GAP}{group.group_id}{GROUP_COLUMN_GAP}{status_text(group.status)}"
    body: tuple[str, ...] = (
        *_product_lines(PLAN_PRODUCTS_LABEL, group.products, root),
        *_product_lines(RESULTS_PRESERVED_LABEL, group.preserved_products, root),
        *_error_lines(group),
    )
    return (heading, *(f"{PLAN_INDENT}{line}" for line in body))


def results_lines(result: RunResult | None, *, root: Path | None = None) -> tuple[str, ...]:
    """Return every line the results screen renders for *result*, group by group."""
    if result is None:
        return (RESULTS_EMPTY,)
    succeeded: int = sum(1 for group in result.groups if group.status is GroupStatus.SUCCEEDED)
    header: str = RESULTS_SUMMARY.format(succeeded=succeeded, total=len(result.groups))
    grouped: tuple[str, ...] = tuple(line for group in result.groups for line in group_lines(group, root=root))
    return (header, "", *grouped, *_warning_lines(result), *_hint_lines(result))


def results_body(state: SessionState, *, root: Path | None = None) -> str:
    """Return the rendered text of the result this session holds as one body."""
    return f"{RESULTS_TITLE}\n\n" + "\n".join(results_lines(state.result, root=root))


def results_action(run: CommandRun) -> CommandSpec:
    """Build the action that shows the result of a session holding one."""
    return CommandSpec(
        name=RESULTS_COMMAND_NAME,
        title=RESULTS_TITLE,
        description=RESULTS_OPEN_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=results_available,
    )


def _manual_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that owns the recovery key and its palette row."""
    return CommandSpec(
        name=MANUAL_COMMAND_NAME,
        title=RESULTS_MANUAL_TITLE,
        description=RESULTS_MANUAL_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
        enabled=recovery_available,
        keys=(MANUAL_KEY,),
    )


def _workspace_action(run: CommandRun) -> CommandSpec:
    """Build the contextual action that leaves the results for the workspace."""
    return CommandSpec(
        name=WORKSPACE_COMMAND_NAME,
        title=RESULTS_BACK_TITLE,
        description=RESULTS_BACK_DESCRIPTION,
        category=CommandCategory.ACTION,
        run=run,
    )


def _product_lines(label: str, products: Sequence[ProducedArtifact], root: Path | None) -> tuple[str, ...]:
    """Return *label* and one line per product, located relative to *root* alone."""
    if not products:
        return (_field(label, PLAN_NONE),)
    located: tuple[str, ...] = tuple(f"{PLAN_INDENT}{relative_text(product.path, root)}" for product in products)
    return (_field(label, ""), *located)


def _error_lines(group: GroupResult) -> tuple[str, ...]:
    """Return the redacted errors of *group*, or the empty value while it holds none."""
    if not group.error_messages:
        return (_field(RESULTS_ERROR_LABEL, PLAN_NONE),)
    listed: tuple[str, ...] = tuple(f"{PLAN_INDENT}{message}" for message in group.error_messages)
    return (_field(RESULTS_ERROR_LABEL, ""), *listed)


def _warning_lines(result: RunResult) -> tuple[str, ...]:
    """Return the redacted warnings of the whole run, under one label of their own."""
    if not result.warnings:
        return ()
    listed: tuple[str, ...] = tuple(f"{PLAN_INDENT}{warning}" for warning in result.warnings)
    return ("", RESULTS_WARNINGS_LABEL, *listed)


def _hint_lines(result: RunResult) -> tuple[str, ...]:
    """Return the note promising no resume, while one group could be planned again."""
    if not recoverable_groups(result):
        return ()
    return ("", RESULTS_RECOVERY_HINT)


def _field(label: str, value: str) -> str:
    """Return one label and the value it carries, as one line."""
    return f"{label}{GROUP_COLUMN_GAP}{value}".rstrip()


@runtime_checkable
class ResultsHost(Protocol):
    """What the results screen needs from the shell that owns it."""

    @property
    def session_state(self) -> SessionState:
        """The one session state the shell owns."""

    @property
    def commands(self) -> CommandRegistry:
        """The one command registry the shell owns."""

    @property
    def workspace_root(self) -> Path | None:
        """The directory every rendered location stays inside of."""

    def recover_in_manual(self) -> bool:
        """Give one group that did not finish a manual draft of its own."""

    def leave_results(self) -> None:
        """Show the workspace again, keeping the result the session holds."""


class ResultsView(Static):
    """The one region rendering a terminal result and offering the recovery it allows."""

    def __init__(self) -> None:
        """Render nothing until the shell hands this view the result of a run."""
        super().__init__("", id=RESULTS_ID, markup=False)

    def show(self, state: SessionState, *, root: Path | None) -> None:
        """Render the result of *state*, with every location relative to *root*."""
        self.update(results_body(state, root=root))

    def on_show(self) -> None:
        """Own the recovery and the workspace actions while this view is on screen."""
        host: ResultsHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(RESULTS_SCOPE)
        host.commands.register(
            (_manual_action(self.action_open_manual), _workspace_action(self.action_workspace)),
            scope=RESULTS_SCOPE,
        )

    def on_hide(self) -> None:
        """Give both actions back the moment this view leaves the screen."""
        host: ResultsHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(RESULTS_SCOPE)

    def action_open_manual(self) -> None:
        """Prepare one manual draft through the gate that picks the group."""
        host: ResultsHost | None = self._host()
        if host is None:
            return
        host.recover_in_manual()

    def action_workspace(self) -> None:
        """Leave the results for the workspace, keeping the result itself."""
        host: ResultsHost | None = self._host()
        if host is None:
            return
        host.leave_results()

    def _host(self) -> ResultsHost | None:
        """Return the shell this view renders for, when it is a results host."""
        app: object = self.app
        return app if isinstance(app, ResultsHost) else None
