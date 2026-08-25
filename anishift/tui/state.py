"""Presentation-only state of one interactive AniShift session."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final

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

if TYPE_CHECKING:
    from anishift.application import (
        AutoPresetDraft,
        ExecutionPlan,
        InspectedWorkspace,
        RunEvent,
        RunResult,
    )

__all__ = [
    "DEFAULT_PRESET_ID",
    "FeedbackLevel",
    "GroupIntentDraft",
    "RunUiState",
    "SessionState",
    "UiFeedback",
    "UiRoute",
]

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_PRESET_ID: Final[str] = "default"
"""Auto-preset a fresh session starts from, mirroring ``config.presets.DEFAULT_PRESET_ID``."""


class UiRoute(StrEnum):
    """The only routes the application host can show."""

    WORKSPACE = "workspace"
    AUTO = "auto"
    MANUAL = "manual"
    PREVIEW = "preview"
    EXECUTION = "execution"
    RESULTS = "results"
    TOOLS = "tools"


class RunUiState(StrEnum):
    """Explicit lifecycle of the one run a session can own."""

    IDLE = "idle"
    PLANNING = "planning"
    RUNNING = "running"
    CANCELLING = "cancelling"
    TERMINAL = "terminal"


class FeedbackLevel(StrEnum):
    """Severity of one message the shell shows about the last operation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class UiFeedback:
    """One redacted message about the last operation, shown to the user."""

    level: FeedbackLevel
    message: str

    @classmethod
    def error(cls, message: str) -> UiFeedback:
        """Build the feedback of one refused, abandoned or broken operation."""
        return cls(level=FeedbackLevel.ERROR, message=message)


@dataclass(slots=True)
class GroupIntentDraft:
    """Editable manual decisions of ``GroupIntent`` and ``ProductIntent`` for one group."""

    group_id: str
    products: set[ProductKind]
    subtitle_source_policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    translation_action: TranslationAction = TranslationAction.AUTO
    preferred_video_artifact_id: str | None = None
    selected_subtitle_artifact_id: str | None = None
    selected_audio_artifact_id: str | None = None
    selected_audio_track_id: int | None = None
    selected_subtitle_track_id: int | None = None
    source_subtitle_language: str | None = None
    external_audio_role: ExternalAudioRole | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE
    burn_subtitle_product: BurnSubtitleProduct = BurnSubtitleProduct.NONE
    mkv_tracks: set[MkvTrackProduct] = field(default_factory=set)
    mp4_audio_source: Mp4AudioSource = Mp4AudioSource.AUTO

    @classmethod
    def from_intent(cls, intent: GroupIntent) -> GroupIntentDraft:
        """Restore every editable decision from an immutable group intent."""
        return cls(
            group_id=intent.group_id,
            products=set(intent.products.requested_products),
            subtitle_source_policy=intent.subtitle_source_policy,
            translation_action=intent.translation_action,
            preferred_video_artifact_id=intent.preferred_video_artifact_id,
            selected_subtitle_artifact_id=intent.selected_subtitle_artifact_id,
            selected_audio_artifact_id=intent.selected_audio_artifact_id,
            selected_audio_track_id=intent.selected_audio_track_id,
            selected_subtitle_track_id=intent.selected_subtitle_track_id,
            source_subtitle_language=intent.source_subtitle_language,
            external_audio_role=intent.external_audio_role,
            subtitle_output_format=intent.subtitle_output_format,
            burn_subtitle_product=intent.products.burn_subtitle_product,
            mkv_tracks=set(intent.products.mkv_tracks),
            mp4_audio_source=intent.products.mp4_audio_source,
        )

    def clone_for(self, group_id: str) -> GroupIntentDraft:
        """Copy every decision into a draft with independent mutable state."""
        cloned: GroupIntentDraft = deepcopy(self)
        cloned.group_id = group_id
        return cloned

    def to_intent(self) -> GroupIntent:
        """Materialize the immutable manual planner contract."""
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
    """The single mutable presentation state of one session."""

    route: UiRoute = UiRoute.WORKSPACE
    generation: int = 0
    workspace: InspectedWorkspace | None = None
    selected_group_ids: set[str] = field(default_factory=set)
    default_preset_id: str = DEFAULT_PRESET_ID
    auto_draft: AutoPresetDraft | None = None
    manual_drafts: dict[str, GroupIntentDraft] = field(default_factory=dict)
    plan: ExecutionPlan | None = None
    active_run_id: str | None = None
    run_state: RunUiState = RunUiState.IDLE
    events: list[RunEvent] = field(default_factory=list)
    result: RunResult | None = None
    feedback: UiFeedback | None = None
    focus_id: str | None = None
    modal_focus_stack: list[str | None] = field(default_factory=list)

    @property
    def group_count(self) -> int:
        """Number of source groups the loaded workspace holds."""
        return 0 if self.workspace is None else len(self.workspace.groups)
