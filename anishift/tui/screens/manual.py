"""Independent per-group manual workflow screen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, Static

from anishift.application.artifacts import ArtifactKind
from anishift.application.cancellation import EventCancellationToken
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.intents import ExternalAudioRole, ProductKind
from anishift.errors import AniShiftError
from anishift.tui.messages import ExternalArtifactFailed, ExternalArtifactRegistered
from anishift.tui.state import GroupIntentDraft
from anishift.tui.widgets import CommandBar, StatusFooter
from anishift.tui.widgets.intent_form import IntentForm

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


@dataclass(frozen=True, slots=True)
class _ExternalRequest:
    generation: int
    group_id: str
    path: Path
    language: str | None
    audio_role: ExternalAudioRole | None


class ManualScreen(Screen[None]):
    """Edit and plan distinct choices for every selected source group."""

    def __init__(self) -> None:
        super().__init__()
        self._external_cancel: EventCancellationToken | None = None

    def compose(self) -> ComposeResult:
        """Compose group selector, one replaceable form, and workflow actions."""
        group_ids: tuple[str, ...] = tuple(sorted(self._shell.session.selected_group_ids))
        with Vertical(classes="route-content"):
            yield Label("Manual workflow", classes="route-title")
            yield Select(
                ((group_id, group_id) for group_id in group_ids),
                value=group_ids[0] if group_ids else Select.NULL,
                id="manual-group",
            )
            yield Vertical(id="manual-form-host")
            with Horizontal(id="external-subtitle-fields"):
                yield Input(placeholder="External ASS/SRT path", id="external-subtitle-path")
                yield Input(placeholder="Language, e.g. eng", id="external-subtitle-language")
                yield Button("Validate subtitle", id="register-subtitle")
            with Horizontal(id="external-audio-fields"):
                yield Input(placeholder="External audio path", id="external-audio-path")
                yield Select(
                    ((role.value, role) for role in ExternalAudioRole),
                    value=ExternalAudioRole.SOURCE_AUDIO,
                    allow_blank=False,
                    id="external-audio-role",
                )
                yield Button("Validate audio", id="register-audio")
            with Horizontal(classes="screen-actions"):
                yield Button("Copy to selected", id="manual-copy")
                yield Button("Preview", id="manual-preview", variant="primary")
                yield Button("Back", id="back")
            yield Static("", id="manual-feedback")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    async def on_mount(self) -> None:
        """Create independent defaults and mount the first group form."""
        for group_id in self._shell.session.selected_group_ids:
            self._shell.session.manual_drafts.setdefault(
                group_id,
                GroupIntentDraft(group_id, {ProductKind.FULL_PL}),
            )
        await self._mount_current_form()

    async def on_select_changed(self, event: Select.Changed) -> None:
        """Persist the previous group before switching form ownership."""
        if event.select.id != "manual-group" or not isinstance(event.value, str):
            return
        current: IntentForm | None = self.query_one("#manual-form-host", Vertical).query_one_optional(IntentForm)
        if current is not None:
            current.apply()
        await self._mount_form(event.value)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Copy independent values, preview all drafts, or return."""
        if event.button.id in {"register-subtitle", "register-audio"}:
            self._register_external(is_audio=event.button.id == "register-audio")
            return
        form: IntentForm = self.query_one(IntentForm)
        form.apply()
        if event.button.id == "back":
            await self._shell.open_route("workspace")
        elif event.button.id == "manual-copy":
            for group_id in self._shell.session.selected_group_ids:
                if group_id != form.draft.group_id:
                    self._shell.session.manual_drafts[group_id] = form.draft.clone_for(group_id)
            self.query_one("#manual-feedback", Static).update("Copied to selected groups")
        elif event.button.id == "manual-preview":
            empty_group_ids: tuple[str, ...] = tuple(
                group_id
                for group_id in sorted(self._shell.session.selected_group_ids)
                if not self._shell.session.manual_drafts[group_id].products
            )
            if empty_group_ids:
                self.query_one("#manual-feedback", Static).update(
                    f"Select at least one product for: {', '.join(empty_group_ids)}"
                )
                return
            intents = tuple(
                self._shell.session.manual_drafts[group_id].to_intent()
                for group_id in sorted(self._shell.session.selected_group_ids)
            )
            self._shell.session.preview_plan = self._shell.service.plan_manual(intents)
            await self._shell.open_route("preview")

    def on_unmount(self) -> None:
        """Invalidate external validation results after leaving Manual."""
        self._shell.session.external_generation += 1
        if self._external_cancel is not None:
            self._external_cancel.cancel()

    def _register_external(self, *, is_audio: bool) -> None:
        if self._external_cancel is not None:
            self._external_cancel.cancel()
        group_id = self.query_one("#manual-group", Select).value
        if not isinstance(group_id, str):
            return
        path_id: str = "#external-audio-path" if is_audio else "#external-subtitle-path"
        raw_path: str = self.query_one(path_id, Input).value.strip()
        if not raw_path:
            self.query_one("#manual-feedback", Static).update("Choose an external file")
            return
        self._shell.session.external_generation += 1
        generation: int = self._shell.session.external_generation
        token = EventCancellationToken()
        self._external_cancel = token
        language: str | None = None
        role = ExternalAudioRole.SOURCE_AUDIO
        if is_audio:
            role_value = self.query_one("#external-audio-role", Select).value
            if isinstance(role_value, ExternalAudioRole):
                role = role_value
        else:
            language = self.query_one("#external-subtitle-language", Input).value.strip() or None
        request = _ExternalRequest(generation, group_id, Path(raw_path), language, role if is_audio else None)
        self._validate_external(request, token)

    @work(thread=True, exclusive=False, group="external-validation")
    def _validate_external(
        self,
        request: _ExternalRequest,
        cancel: EventCancellationToken,
    ) -> None:
        try:
            if request.audio_role is not None:
                group = self._shell.service.register_external_audio(
                    request.group_id,
                    request.path,
                    request.audio_role,
                    cancel=cancel,
                )
                kinds = {ArtifactKind.SOURCE_AUDIO, ArtifactKind.NARRATION_AUDIO}
            else:
                group = self._shell.service.register_external_subtitle(
                    request.group_id,
                    request.path,
                    request.language,
                    cancel=cancel,
                )
                kinds = {ArtifactKind.SOURCE_SUBTITLES}
        except AniShiftError as error:
            if not cancel.is_cancelled():
                self.app.call_from_thread(
                    self.post_message,
                    ExternalArtifactFailed(request.generation, str(error)),
                )
            return
        artifact_id: str = next(
            artifact.artifact_id for artifact in reversed(group.artifacts) if artifact.kind in kinds
        )
        self.app.call_from_thread(
            self.post_message,
            ExternalArtifactRegistered(
                request.generation,
                group,
                artifact_id,
                audio_role=request.audio_role,
            ),
        )

    async def on_external_artifact_registered(self, message: ExternalArtifactRegistered) -> None:
        """Apply only the latest validation result to its matching draft."""
        if message.generation != self._shell.session.external_generation or not self.is_mounted:
            return
        workspace = self._shell.session.workspace
        if workspace is None:
            return
        groups = tuple(
            message.group if group.group_id == message.group.group_id else group for group in workspace.groups
        )
        self._shell.session.workspace = type(workspace)(groups, workspace.warnings)
        selected_group = self.query_one("#manual-group", Select).value
        if selected_group == message.group.group_id:
            current = self.query_one("#manual-form-host", Vertical).query_one_optional(IntentForm)
            if current is not None:
                current.apply()
        draft = self._shell.session.manual_drafts[message.group.group_id]
        if message.audio_role is not None:
            draft.selected_audio_artifact_id = message.artifact_id
            draft.selected_audio_track_id = None
            draft.external_audio_role = message.audio_role
        else:
            draft.selected_subtitle_artifact_id = message.artifact_id
            draft.selected_subtitle_track_id = None
        if selected_group == message.group.group_id:
            await self._mount_form(message.group.group_id)
        self.query_one("#manual-feedback", Static).update("External file validated")

    def on_external_artifact_failed(self, message: ExternalArtifactFailed) -> None:
        """Render only a failure from the latest validation generation."""
        if message.generation == self._shell.session.external_generation and self.is_mounted:
            self.query_one("#manual-feedback", Static).update(message.error)

    async def _mount_current_form(self) -> None:
        value = self.query_one("#manual-group", Select).value
        if isinstance(value, str):
            await self._mount_form(value)

    async def _mount_form(self, group_id: str) -> None:
        host = self.query_one("#manual-form-host", Vertical)
        await host.remove_children()
        workspace = self._shell.session.workspace
        if workspace is None:
            return
        group: InspectedSourceGroup = next(item for item in workspace.groups if item.group_id == group_id)
        await host.mount(IntentForm(self._shell.session.manual_drafts[group_id], group))
