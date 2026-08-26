"""The manual workflow: one independent draft per selected group, gated by Preview."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Protocol, cast

from textual import on
from textual.binding import Binding
from textual.widgets import Static

from anishift.application.intents import (
    ExternalAudioRole,
    ProductKind,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.tui import lifecycle, workers
from anishift.tui.commands.spec import CommandCategory, CommandSpec
from anishift.tui.dialogs.base import open_dialog
from anishift.tui.dialogs.select import SelectDialog, SelectOption, SelectOutcome, SelectOutcomeKind
from anishift.tui.dialogs.value import PromptDialog
from anishift.tui.messages import GroupRegistered
from anishift.tui.state import FeedbackLevel, GroupIntentDraft, RunUiState, UiFeedback
from anishift.tui.strings import (
    COMPOSER_ACCENT_GLYPH,
    GLYPH_GAP,
    GROUP_COLUMN_GAP,
    GROUP_CONFLICT_GLYPH,
    GROUP_READY_GLYPH,
    GROUP_STATE_READY,
    MANUAL_AUDIO_DESCRIPTION,
    MANUAL_AUDIO_TITLE,
    MANUAL_COPIED,
    MANUAL_COPY_DESCRIPTION,
    MANUAL_COPY_TITLE,
    MANUAL_EDIT_TITLE,
    MANUAL_EMPTY,
    MANUAL_NO_SELECTION,
    MANUAL_PATH_HINT,
    MANUAL_POLICY_AUTO,
    MANUAL_POLICY_EMBEDDED,
    MANUAL_POLICY_EXTERNAL,
    MANUAL_POLICY_NONE,
    MANUAL_POLICY_READY_POLISH,
    MANUAL_POLICY_SIDECAR,
    MANUAL_POLICY_TITLE,
    MANUAL_PREVIEW_DESCRIPTION,
    MANUAL_PREVIEW_INCOMPLETE,
    MANUAL_PREVIEW_TITLE,
    MANUAL_PRODUCT_DISPLAYED_PL,
    MANUAL_PRODUCT_FULL_PL,
    MANUAL_PRODUCT_MKV,
    MANUAL_PRODUCT_MP4,
    MANUAL_PRODUCT_NARRATION_AUDIO,
    MANUAL_PRODUCT_SOURCE_SUBTITLES,
    MANUAL_PRODUCT_SPOKEN_PL,
    MANUAL_PRODUCTS_TITLE,
    MANUAL_ROLE_NARRATION_MIX,
    MANUAL_ROLE_SOURCE_AUDIO,
    MANUAL_ROLE_TITLE,
    MANUAL_STATE_INVALID,
    MANUAL_SUBTITLE_DESCRIPTION,
    MANUAL_SUBTITLE_TITLE,
    MANUAL_SUMMARY,
    MANUAL_TRANSLATION_AUTO,
    MANUAL_TRANSLATION_DO_NOT_TRANSLATE,
    MANUAL_TRANSLATION_TITLE,
    MANUAL_TRANSLATION_TRANSLATE,
    SETTING_EMPTY_VALUE,
    SETTING_LIST_SEPARATOR,
)
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.binding import BindingType

    from anishift.application import (
        AppService,
        Artifact,
        GroupIntent,
        InspectedSourceGroup,
        InspectedWorkspace,
    )
    from anishift.tui.commands.registry import CommandRegistry
    from anishift.tui.state import SessionState

logger = get_logger(__name__)

__all__ = [
    "AUDIO_COMMAND_NAME",
    "AUDIO_KEY",
    "COPY_COMMAND_NAME",
    "COPY_KEY",
    "CURSOR_MARK",
    "MANUAL_ID",
    "MANUAL_SCOPE",
    "PREVIEW_COMMAND_NAME",
    "PREVIEW_KEY",
    "SUBTITLE_COMMAND_NAME",
    "SUBTITLE_KEY",
    "ManualHost",
    "ManualRow",
    "ManualView",
    "manual_body",
    "manual_copy_available",
    "manual_preview_available",
    "manual_register_available",
    "manual_rows",
]

# ── Constants ──────────────────────────────────────────────────────────────

MANUAL_ID: Final[str] = "manual-view"
"""Id of the one surface the work area lists manual drafts on."""

MANUAL_SCOPE: Final[str] = "manual"
"""Registry scope the manual view owns while it is on screen, and never longer."""

CURSOR_MARK: Final[str] = COMPOSER_ACCENT_GLYPH
"""Gutter of the row every contextual key acts on, so no colour has to carry it."""

PREVIEW_COMMAND_NAME: Final[str] = "manual-preview"
"""Name the registry holds the contextual preview action under."""

PREVIEW_KEY: Final[str] = "ctrl+g"
"""Key the contextual preview action answers to."""

COPY_COMMAND_NAME: Final[str] = "manual-copy"
"""Name the registry holds the copy-to-selected action under."""

COPY_KEY: Final[str] = "ctrl+y"
"""Key the copy-to-selected action answers to."""

SUBTITLE_COMMAND_NAME: Final[str] = "manual-subtitle"
"""Name the registry holds the external-subtitle action under."""

SUBTITLE_KEY: Final[str] = "ctrl+b"
"""Key the external-subtitle registration answers to."""

AUDIO_COMMAND_NAME: Final[str] = "manual-audio"
"""Name the registry holds the external-audio action under."""

AUDIO_KEY: Final[str] = "ctrl+d"
"""Key the external-audio registration answers to."""

_COPY_TARGET_FLOOR: Final[int] = 2
"""Selected drafts a copy needs before it has both a source and a target."""

_PLANNABLE_STATES: Final[frozenset[RunUiState]] = frozenset({RunUiState.IDLE, RunUiState.TERMINAL})
"""Run states a preview may reserve a planning generation under."""

_PRODUCT_LABELS: Final[dict[ProductKind, str]] = {
    ProductKind.SOURCE_SUBTITLES: MANUAL_PRODUCT_SOURCE_SUBTITLES,
    ProductKind.FULL_PL: MANUAL_PRODUCT_FULL_PL,
    ProductKind.SPOKEN_PL: MANUAL_PRODUCT_SPOKEN_PL,
    ProductKind.DISPLAYED_PL: MANUAL_PRODUCT_DISPLAYED_PL,
    ProductKind.NARRATION_AUDIO: MANUAL_PRODUCT_NARRATION_AUDIO,
    ProductKind.MKV: MANUAL_PRODUCT_MKV,
    ProductKind.MP4: MANUAL_PRODUCT_MP4,
}
"""Label every requestable product is shown and offered by."""

_POLICY_LABELS: Final[dict[SubtitleSourcePolicy, str]] = {
    SubtitleSourcePolicy.AUTO: MANUAL_POLICY_AUTO,
    SubtitleSourcePolicy.SIDECAR: MANUAL_POLICY_SIDECAR,
    SubtitleSourcePolicy.EMBEDDED: MANUAL_POLICY_EMBEDDED,
    SubtitleSourcePolicy.EXTERNAL: MANUAL_POLICY_EXTERNAL,
    SubtitleSourcePolicy.READY_POLISH: MANUAL_POLICY_READY_POLISH,
    SubtitleSourcePolicy.NONE: MANUAL_POLICY_NONE,
}
"""Label every subtitle source policy is shown and offered by."""

_TRANSLATION_LABELS: Final[dict[TranslationAction, str]] = {
    TranslationAction.AUTO: MANUAL_TRANSLATION_AUTO,
    TranslationAction.TRANSLATE: MANUAL_TRANSLATION_TRANSLATE,
    TranslationAction.DO_NOT_TRANSLATE: MANUAL_TRANSLATION_DO_NOT_TRANSLATE,
}
"""Label every translation decision is shown and offered by."""

_ROLE_LABELS: Final[dict[ExternalAudioRole, str]] = {
    ExternalAudioRole.SOURCE_AUDIO: MANUAL_ROLE_SOURCE_AUDIO,
    ExternalAudioRole.NARRATION_MIX: MANUAL_ROLE_NARRATION_MIX,
}
"""Label every external audio role is offered by."""


class _EditAspect(StrEnum):
    """One editable facet the edit menu opens its own dialog for."""

    PRODUCTS = "products"
    POLICY = "policy"
    TRANSLATION = "translation"


class _RegistrationKind(StrEnum):
    """Which external source one pending registration expects back."""

    SUBTITLE = "subtitle"
    AUDIO = "audio"


@dataclass(frozen=True, slots=True)
class _Pending:
    """One in-flight external registration, matched to its late answer by group id."""

    generation: int
    kind: _RegistrationKind
    path: Path
    role: ExternalAudioRole | None = None


@dataclass(frozen=True, slots=True)
class ManualRow:
    """One selected group as the manual view lists it, identified by its stable id."""

    name: str
    group_id: str
    products: str
    subtitle: str
    translation: str
    valid: bool


class ManualHost(workers.WorkerHost, Protocol):
    """The shell capabilities this view reaches for, and nothing more."""

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


def selected_draft_ids(state: SessionState) -> tuple[str, ...]:
    """Return the group ids that are both selected and hold a manual draft."""
    return tuple(gid for gid in state.selected_group_ids if gid in state.manual_drafts)


def manual_preview_available(state: SessionState) -> bool:
    """Whether *state* lets a preview reserve a planning generation right now."""
    return bool(selected_draft_ids(state)) and state.run_state in _PLANNABLE_STATES and not state.modal_focus_stack


def manual_copy_available(state: SessionState) -> bool:
    """Whether *state* holds a source draft and at least one target to copy into."""
    return len(selected_draft_ids(state)) >= _COPY_TARGET_FLOOR and not state.modal_focus_stack


def manual_register_available(state: SessionState) -> bool:
    """Whether *state* lets one selected draft register an external source."""
    return bool(selected_draft_ids(state)) and not state.modal_focus_stack


def product_summary(products: set[ProductKind]) -> str:
    """Return the labels of *products* in one stable order, or the empty-value word."""
    labels: list[str] = [_PRODUCT_LABELS[kind] for kind in ProductKind if kind in products]
    return SETTING_LIST_SEPARATOR.join(labels) if labels else SETTING_EMPTY_VALUE


def draft_is_valid(draft: GroupIntentDraft) -> bool:
    """Whether *draft* materialises into a valid intent, conflicts included."""
    try:
        draft.to_intent()
    except ValueError:
        return False
    return True


def manual_rows(state: SessionState) -> tuple[ManualRow, ...]:
    """Project every selected group that holds a draft into its row, in one order."""
    stems: dict[str, str] = _stems(state.workspace)
    names: dict[str, str] = {gid: stems.get(gid, gid) for gid in selected_draft_ids(state)}
    ordered: list[str] = sorted(names, key=lambda gid: (names[gid].casefold(), gid))
    return tuple(_row(state.manual_drafts[gid], names[gid]) for gid in ordered)


def manual_body(rows: Sequence[ManualRow], *, cursor: int = 0) -> str:
    """Render the summary of *rows* and every draft, marking the row keys act on."""
    if not rows:
        return MANUAL_EMPTY
    width: int = max(len(row.name) for row in rows)
    listed: list[str] = [_line(row, cursor=index == cursor, name_width=width) for index, row in enumerate(rows)]
    return "\n".join([MANUAL_SUMMARY.format(count=len(rows)), "", *listed])


def _row(draft: GroupIntentDraft, name: str) -> ManualRow:
    """Build one row from a draft and the name of its source group."""
    return ManualRow(
        name=name,
        group_id=draft.group_id,
        products=product_summary(draft.products),
        subtitle=_POLICY_LABELS[draft.subtitle_source_policy],
        translation=_TRANSLATION_LABELS[draft.translation_action],
        valid=draft_is_valid(draft),
    )


def _line(row: ManualRow, *, cursor: bool, name_width: int) -> str:
    """Return one draft row behind the gutter marking the row keys act on."""
    gutter: str = CURSOR_MARK if cursor else GLYPH_GAP
    glyph: str = GROUP_READY_GLYPH if row.valid else GROUP_CONFLICT_GLYPH
    word: str = GROUP_STATE_READY if row.valid else MANUAL_STATE_INVALID
    cells: tuple[str, ...] = (row.name.ljust(name_width), row.products, row.subtitle, row.translation)
    return f"{gutter}{glyph}{GLYPH_GAP}{GROUP_COLUMN_GAP.join(cells)}{GROUP_COLUMN_GAP}{word}"


def _stems(workspace: InspectedWorkspace | None) -> dict[str, str]:
    """Return the stem of every inspected group, keyed by its stable id."""
    if workspace is None:
        return {}
    return {group.group_id: group.source.stem for group in workspace.groups}


def _clamped(cursor: int, count: int) -> int:
    """Return the cursor kept inside the *count* rows currently listed."""
    if count <= 0:
        return 0
    return max(0, min(cursor, count - 1))


def _clear_source_specific(draft: GroupIntentDraft) -> None:
    """Drop every artifact, track and role id that belongs to one source group alone."""
    draft.preferred_video_artifact_id = None
    draft.selected_subtitle_artifact_id = None
    draft.selected_audio_artifact_id = None
    draft.selected_audio_track_id = None
    draft.selected_subtitle_track_id = None
    draft.external_audio_role = None


def _registered_artifact(group: InspectedSourceGroup, pending: _Pending) -> Artifact | None:
    """Return the artifact the group gained at the path the registration asked for."""
    return next((artifact for artifact in group.artifacts if artifact.path == pending.path), None)


def _apply_to_draft(draft: GroupIntentDraft, pending: _Pending, artifact_id: str) -> None:
    """Point one draft at the registered artifact, clearing the track it excludes."""
    if pending.kind is _RegistrationKind.SUBTITLE:
        draft.selected_subtitle_artifact_id = artifact_id
        draft.subtitle_source_policy = SubtitleSourcePolicy.EXTERNAL
        draft.selected_subtitle_track_id = None
        return
    draft.selected_audio_artifact_id = artifact_id
    draft.external_audio_role = pending.role
    draft.selected_audio_track_id = None


class ManualView(Static):
    """Independent manual drafts, keyed by stable group id and never by row index."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("enter", "edit", show=False),
    ]

    can_focus = False

    def __init__(self) -> None:
        """Build the empty view; the shell fills it from the session drafts."""
        super().__init__(id=MANUAL_ID, markup=False)
        self._cursor: int = 0
        self._pending: dict[str, _Pending] = {}

    @property
    def cursor(self) -> int:
        """Listed row every contextual key of the view acts on."""
        return self._cursor

    def on_show(self) -> None:
        """Create the missing drafts and own the manual actions while on screen."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        self._ensure_drafts(host.session_state)
        host.commands.unregister(MANUAL_SCOPE)
        host.commands.register(self._actions(), scope=MANUAL_SCOPE)
        self._paint()

    def on_hide(self) -> None:
        """Give the manual actions back the moment this view leaves the screen."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        host.commands.unregister(MANUAL_SCOPE)

    @on(GroupRegistered)
    def _on_group_registered(self, event: GroupRegistered) -> None:
        """Apply one external registration this view still waits for, or drop it."""
        event.stop()
        if self._apply_registration(event.group, event.generation):
            self._paint()

    def action_cursor_up(self) -> None:
        """Move the cursor one listed row up."""
        self._move(-1)

    def action_cursor_down(self) -> None:
        """Move the cursor one listed row down."""
        self._move(1)

    def action_edit(self) -> None:
        """Open the editor of the draft under the cursor."""
        host: ManualHost | None = self._host()
        group_id: str | None = self._active_group_id()
        if host is None or group_id is None:
            return
        options: tuple[SelectOption[_EditAspect], ...] = (
            SelectOption(value=_EditAspect.PRODUCTS, title=MANUAL_PRODUCTS_TITLE),
            SelectOption(value=_EditAspect.POLICY, title=MANUAL_POLICY_TITLE),
            SelectOption(value=_EditAspect.TRANSLATION, title=MANUAL_TRANSLATION_TITLE),
        )

        def chosen(outcome: SelectOutcome[_EditAspect] | None) -> None:
            """Open the dialog of the aspect the user picked."""
            aspect: _EditAspect | None = _single(outcome)
            if aspect is _EditAspect.PRODUCTS:
                self._edit_products(group_id)
            elif aspect is _EditAspect.POLICY:
                self._edit_policy(group_id)
            elif aspect is _EditAspect.TRANSLATION:
                self._edit_translation(group_id)

        open_dialog(self.app, host.session_state, SelectDialog(title=MANUAL_EDIT_TITLE, options=options), chosen)

    def action_preview(self) -> None:
        """Materialise the whole intent set and build the plan, or refuse an incomplete set."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        state: SessionState = host.session_state
        drafts: tuple[GroupIntentDraft, ...] = tuple(state.manual_drafts[gid] for gid in self._ordered_ids())
        if not drafts:
            self._refuse(MANUAL_NO_SELECTION)
            return
        intents: list[GroupIntent] = []
        for draft in drafts:
            try:
                intents.append(draft.to_intent())
            except ValueError:
                self._refuse(MANUAL_PREVIEW_INCOMPLETE)
                return
        generation: int | None = lifecycle.begin_planning(state)
        if generation is None:
            return
        logger.info("Manual preview requested", generation=generation, groups=len(intents))
        workers.plan_manual(self, host.service, generation=generation, intents=intents)

    def action_copy_selected(self) -> None:
        """Copy the draft under the cursor into every other selected draft."""
        host: ManualHost | None = self._host()
        source_id: str | None = self._active_group_id()
        if host is None or source_id is None:
            return
        state: SessionState = host.session_state
        source: GroupIntentDraft = state.manual_drafts[source_id]
        targets: tuple[str, ...] = tuple(gid for gid in self._ordered_ids() if gid != source_id)
        for target_id in targets:
            clone: GroupIntentDraft = source.clone_for(target_id)
            _clear_source_specific(clone)
            state.manual_drafts[target_id] = clone
        if targets:
            state.feedback = UiFeedback(level=FeedbackLevel.INFO, message=MANUAL_COPIED)
        self._paint()

    def action_register_subtitle(self) -> None:
        """Register one external subtitle for the draft under the cursor."""
        host: ManualHost | None = self._host()
        group_id: str | None = self._active_group_id()
        if host is None or group_id is None:
            return

        def entered(text: str | None) -> None:
            """Launch the subtitle registration once a path was entered."""
            if text is None:
                return
            self._launch_subtitle(group_id, Path(text))

        open_dialog(
            self.app,
            host.session_state,
            PromptDialog(title=MANUAL_SUBTITLE_TITLE, hint=MANUAL_PATH_HINT),
            entered,
        )

    def action_register_audio(self) -> None:
        """Register one external audio source for the draft under the cursor."""
        host: ManualHost | None = self._host()
        group_id: str | None = self._active_group_id()
        if host is None or group_id is None:
            return

        def entered(text: str | None) -> None:
            """Ask for the role once a path was entered."""
            if text is None:
                return
            self._ask_audio_role(group_id, Path(text))

        open_dialog(
            self.app,
            host.session_state,
            PromptDialog(title=MANUAL_AUDIO_TITLE, hint=MANUAL_PATH_HINT),
            entered,
        )

    def _ask_audio_role(self, group_id: str, path: Path) -> None:
        """Open the role picker, then launch the audio registration on the choice."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        options: tuple[SelectOption[ExternalAudioRole], ...] = tuple(
            SelectOption(value=role, title=_ROLE_LABELS[role]) for role in ExternalAudioRole
        )

        def chosen(outcome: SelectOutcome[ExternalAudioRole] | None) -> None:
            """Launch the audio registration for the role that was picked."""
            role: ExternalAudioRole | None = _single(outcome)
            if role is None:
                return
            self._launch_audio(group_id, path, role)

        open_dialog(self.app, host.session_state, SelectDialog(title=MANUAL_ROLE_TITLE, options=options), chosen)

    def _launch_subtitle(self, group_id: str, path: Path) -> None:
        """Start the external-subtitle worker under the current generation."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        generation: int = host.session_state.generation
        self._pending[group_id] = _Pending(generation=generation, kind=_RegistrationKind.SUBTITLE, path=path)
        workers.register_external_subtitle(
            self,
            host.service,
            generation=generation,
            group_id=group_id,
            path=path,
            declared_language=None,
        )

    def _launch_audio(self, group_id: str, path: Path, role: ExternalAudioRole) -> None:
        """Start the external-audio worker under the current generation."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        generation: int = host.session_state.generation
        self._pending[group_id] = _Pending(generation=generation, kind=_RegistrationKind.AUDIO, path=path, role=role)
        workers.register_external_audio(
            self,
            host.service,
            generation=generation,
            group_id=group_id,
            path=path,
            role=role,
        )

    def _apply_registration(self, group: InspectedSourceGroup, generation: int) -> bool:
        """Point the matching draft at the registered source, unless the answer is stale."""
        host: ManualHost | None = self._host()
        if host is None:
            return False
        state: SessionState = host.session_state
        pending: _Pending | None = self._pending.pop(group.group_id, None)
        if pending is None or generation != state.generation:
            return False
        draft: GroupIntentDraft | None = state.manual_drafts.get(group.group_id)
        artifact: Artifact | None = _registered_artifact(group, pending)
        if draft is None or artifact is None:
            return False
        _apply_to_draft(draft, pending, artifact.artifact_id)
        self._replace_workspace_group(state, group)
        return True

    def _replace_workspace_group(self, state: SessionState, group: InspectedSourceGroup) -> None:
        """Swap the inspected group the registration replaced back into the workspace."""
        workspace: InspectedWorkspace | None = state.workspace
        if workspace is None:
            return
        groups = tuple(group if member.group_id == group.group_id else member for member in workspace.groups)
        state.workspace = replace(workspace, groups=groups)

    def _edit_products(self, group_id: str) -> None:
        """Open the multi picker of requestable products for one draft."""
        host: ManualHost | None = self._host()
        draft: GroupIntentDraft | None = None if host is None else host.session_state.manual_drafts.get(group_id)
        if host is None or draft is None:
            return
        kinds: tuple[ProductKind, ...] = tuple(ProductKind)
        options: tuple[SelectOption[ProductKind], ...] = tuple(
            SelectOption(value=kind, title=_PRODUCT_LABELS[kind]) for kind in kinds
        )
        selected: tuple[int, ...] = tuple(index for index, kind in enumerate(kinds) if kind in draft.products)

        def chosen(outcome: SelectOutcome[ProductKind] | None) -> None:
            """Store the products the user confirmed on the draft."""
            if outcome is None or outcome.kind is not SelectOutcomeKind.MULTI:
                return
            draft.products = set(outcome.values)
            self._paint()

        open_dialog(
            self.app,
            host.session_state,
            SelectDialog(title=MANUAL_PRODUCTS_TITLE, options=options, multi=True, selected=selected),
            chosen,
        )

    def _edit_policy(self, group_id: str) -> None:
        """Open the single picker of the subtitle source policy for one draft."""
        host: ManualHost | None = self._host()
        draft: GroupIntentDraft | None = None if host is None else host.session_state.manual_drafts.get(group_id)
        if host is None or draft is None:
            return
        options: tuple[SelectOption[SubtitleSourcePolicy], ...] = tuple(
            SelectOption(value=policy, title=_POLICY_LABELS[policy]) for policy in SubtitleSourcePolicy
        )

        def chosen(outcome: SelectOutcome[SubtitleSourcePolicy] | None) -> None:
            """Store the subtitle source policy the user picked."""
            policy: SubtitleSourcePolicy | None = _single(outcome)
            if policy is None:
                return
            draft.subtitle_source_policy = policy
            self._paint()

        open_dialog(
            self.app,
            host.session_state,
            SelectDialog(title=MANUAL_POLICY_TITLE, options=options, current=draft.subtitle_source_policy),
            chosen,
        )

    def _edit_translation(self, group_id: str) -> None:
        """Open the single picker of the translation decision for one draft."""
        host: ManualHost | None = self._host()
        draft: GroupIntentDraft | None = None if host is None else host.session_state.manual_drafts.get(group_id)
        if host is None or draft is None:
            return
        options: tuple[SelectOption[TranslationAction], ...] = tuple(
            SelectOption(value=action, title=_TRANSLATION_LABELS[action]) for action in TranslationAction
        )

        def chosen(outcome: SelectOutcome[TranslationAction] | None) -> None:
            """Store the translation decision the user picked."""
            action: TranslationAction | None = _single(outcome)
            if action is None:
                return
            draft.translation_action = action
            self._paint()

        open_dialog(
            self.app,
            host.session_state,
            SelectDialog(title=MANUAL_TRANSLATION_TITLE, options=options, current=draft.translation_action),
            chosen,
        )

    def _actions(self) -> tuple[CommandSpec, ...]:
        """Build the four contextual actions the manual view owns while on screen."""
        return (
            CommandSpec(
                name=PREVIEW_COMMAND_NAME,
                title=MANUAL_PREVIEW_TITLE,
                description=MANUAL_PREVIEW_DESCRIPTION,
                category=CommandCategory.ACTION,
                run=self.action_preview,
                enabled=manual_preview_available,
                keys=(PREVIEW_KEY,),
            ),
            CommandSpec(
                name=COPY_COMMAND_NAME,
                title=MANUAL_COPY_TITLE,
                description=MANUAL_COPY_DESCRIPTION,
                category=CommandCategory.ACTION,
                run=self.action_copy_selected,
                enabled=manual_copy_available,
                keys=(COPY_KEY,),
            ),
            CommandSpec(
                name=SUBTITLE_COMMAND_NAME,
                title=MANUAL_SUBTITLE_TITLE,
                description=MANUAL_SUBTITLE_DESCRIPTION,
                category=CommandCategory.ACTION,
                run=self.action_register_subtitle,
                enabled=manual_register_available,
                keys=(SUBTITLE_KEY,),
            ),
            CommandSpec(
                name=AUDIO_COMMAND_NAME,
                title=MANUAL_AUDIO_TITLE,
                description=MANUAL_AUDIO_DESCRIPTION,
                category=CommandCategory.ACTION,
                run=self.action_register_audio,
                enabled=manual_register_available,
                keys=(AUDIO_KEY,),
            ),
        )

    def _ensure_drafts(self, state: SessionState) -> None:
        """Create a safe default draft for every selected group that holds none."""
        for group_id in state.selected_group_ids:
            if group_id not in state.manual_drafts:
                state.manual_drafts[group_id] = GroupIntentDraft(group_id=group_id, products={ProductKind.FULL_PL})

    def _ordered_ids(self) -> tuple[str, ...]:
        """Return the selected draft ids in the one order the view lists them."""
        return tuple(row.group_id for row in self._rows())

    def _rows(self) -> tuple[ManualRow, ...]:
        """Project the session drafts, or an empty tuple while the shell holds none."""
        host: ManualHost | None = self._host()
        if host is None:
            return ()
        return manual_rows(host.session_state)

    def _active_group_id(self) -> str | None:
        """Group id the cursor rests on, or ``None`` while no row is listed."""
        rows: tuple[ManualRow, ...] = self._rows()
        if not 0 <= self._cursor < len(rows):
            return None
        return rows[self._cursor].group_id

    def _move(self, delta: int) -> None:
        """Move the cursor *delta* listed rows and redraw."""
        rows: tuple[ManualRow, ...] = self._rows()
        if not rows:
            return
        self._cursor = _clamped(self._cursor + delta, len(rows))
        self._paint()

    def _refuse(self, reason: str) -> None:
        """Keep a redacted refusal on the state and redraw, starting no worker."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        host.session_state.feedback = UiFeedback.error(reason)
        self._paint()

    def _paint(self) -> None:
        """Redraw from the drafts and the selection the session state holds."""
        host: ManualHost | None = self._host()
        if host is None:
            return
        rows: tuple[ManualRow, ...] = manual_rows(host.session_state)
        self._cursor = _clamped(self._cursor, len(rows))
        self.can_focus = bool(rows)
        self.update(manual_body(rows, cursor=self._cursor))

    def _host(self) -> ManualHost | None:
        """The shell around this view, or ``None`` while it is not mounted."""
        if not self.is_attached:
            return None
        return cast("ManualHost", self.app)


def _single[T](outcome: SelectOutcome[T] | None) -> T | None:
    """Return the single confirmed value of *outcome*, or ``None`` when it holds none."""
    if outcome is None or outcome.kind is not SelectOutcomeKind.SINGLE:
        return None
    return outcome.value
