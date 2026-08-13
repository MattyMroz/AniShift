"""Presentation-only state owned by one Textual session."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic

from anishift.application.inspection import InspectedWorkspace
from anishift.application.intents import (
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planning import ExecutionPlan
from anishift.application.service import AutoPresetDraft


@dataclass(slots=True)
class GroupIntentDraft:
    """Independent editable manual choices for one inspected group."""

    group_id: str
    products: set[ProductKind]
    subtitle_source_policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    translation_action: TranslationAction = TranslationAction.AUTO
    selected_subtitle_artifact_id: str | None = None
    selected_audio_artifact_id: str | None = None
    selected_audio_track_id: int | None = None
    selected_subtitle_track_id: int | None = None
    source_subtitle_language: str | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE
    preferred_video_artifact_id: str | None = None
    external_audio_role: ExternalAudioRole | None = None
    burn_subtitle_product: BurnSubtitleProduct = BurnSubtitleProduct.NONE
    mkv_tracks: set[MkvTrackProduct] = field(default_factory=set)
    mp4_audio_source: Mp4AudioSource = Mp4AudioSource.AUTO

    def clone_for(self, group_id: str) -> GroupIntentDraft:
        """Copy values into a draft with independent mutable product state."""
        cloned: GroupIntentDraft = deepcopy(self)
        cloned.group_id = group_id
        return cloned

    def to_intent(self) -> GroupIntent:
        """Materialize the immutable planner contract."""
        return GroupIntent(
            group_id=self.group_id,
            mode=RunMode.MANUAL,
            products=ProductIntent(
                frozenset(self.products),
                burn_subtitle_product=self.burn_subtitle_product,
                mkv_tracks=frozenset(self.mkv_tracks),
                mp4_audio_source=self.mp4_audio_source,
            ),
            subtitle_source_policy=self.subtitle_source_policy,
            translation_action=self.translation_action,
            preferred_video_artifact_id=self.preferred_video_artifact_id,
            selected_subtitle_artifact_id=self.selected_subtitle_artifact_id,
            selected_audio_artifact_id=self.selected_audio_artifact_id,
            selected_audio_track_id=self.selected_audio_track_id,
            selected_subtitle_track_id=self.selected_subtitle_track_id,
            source_subtitle_language=self.source_subtitle_language,
            external_audio_role=self.external_audio_role,
            subtitle_output_format=self.subtitle_output_format,
        )


@dataclass(slots=True)
class SessionState:
    """Small mutable view state for one interactive frontend session."""

    workspace_label: str
    route: str = "workspace"
    mode: str = "auto"
    preset: str = "default"
    run_state: str = "idle"
    active_run_id: str | None = None
    generation: int = 0
    inspection_generation: int = 0
    external_generation: int = 0
    workspace: InspectedWorkspace | None = None
    selected_group_ids: set[str] = field(default_factory=set)
    auto_draft: AutoPresetDraft | None = None
    manual_drafts: dict[str, GroupIntentDraft] = field(default_factory=dict)
    preview_plan: ExecutionPlan | None = None
    _started_at: float | None = None
    _clock: Callable[[], float] = monotonic

    @property
    def elapsed_seconds(self) -> int:
        """Return elapsed whole seconds only while a run is active."""
        if self._started_at is None:
            return 0
        return max(0, int(self._clock() - self._started_at))

    def select(self, *, mode: str, preset: str) -> None:
        """Update the footer selection without changing workflow state."""
        self.mode = mode
        self.preset = preset

    def begin_run(self) -> int:
        """Start a new UI generation and return its identity."""
        self.generation += 1
        self.run_state = "running"
        self.active_run_id = None
        self._started_at = self._clock()
        return self.generation

    def finish_run(self, state: str) -> None:
        """Stop elapsed time and retain the terminal run state."""
        self.run_state = state
        self.active_run_id = None
        self._started_at = None
