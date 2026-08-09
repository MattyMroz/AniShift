"""Immutable user intent contracts for automatic and manual workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from anishift.application.artifacts import SourceGroup


class RunMode(StrEnum):
    """Product selection mode for one source group."""

    AUTO = "auto"
    MANUAL = "manual"


class ProductKind(StrEnum):
    """Durable products that a user can request."""

    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL = "full_pl"
    SPOKEN_PL = "spoken_pl"
    DISPLAYED_PL = "displayed_pl"
    NARRATION_AUDIO = "narration_audio"
    MKV = "mkv"
    MP4 = "mp4"


class SubtitleSourcePolicy(StrEnum):
    """Policy for selecting the subtitle source."""

    AUTO = "auto"
    SIDECAR = "sidecar"
    EMBEDDED = "embedded"
    EXTERNAL = "external"
    READY_POLISH = "ready_polish"
    NONE = "none"


class BurnSubtitleProduct(StrEnum):
    """Subtitle document burned into a requested video product."""

    NONE = "none"
    SOURCE = "source"
    FULL_PL = "full_pl"
    DISPLAYED_PL = "displayed_pl"


class MkvTrackProduct(StrEnum):
    """Optional tracks attached to a requested MKV product."""

    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL_SUBTITLES = "full_pl_subtitles"
    DISPLAYED_PL_SUBTITLES = "displayed_pl_subtitles"
    NARRATION_AUDIO = "narration_audio"


class Mp4AudioSource(StrEnum):
    """Audio selected for a requested MP4 product."""

    AUTO = "auto"
    ORIGINAL = "original"
    NARRATION = "narration"


class ExternalAudioRole(StrEnum):
    """Meaning assigned to manually registered external audio."""

    SOURCE_AUDIO = "source_audio"
    NARRATION_MIX = "narration_mix"


class SubtitleOutputFormat(StrEnum):
    """Requested serialization format for subtitle products."""

    PRESERVE = "preserve"
    ASS = "ass"
    SRT = "srt"


class TranslationAction(StrEnum):
    """Explicit translation decision for a source subtitle document."""

    AUTO = "auto"
    TRANSLATE = "translate"
    DO_NOT_TRANSLATE = "do_not_translate"


@dataclass(frozen=True, slots=True)
class ProductIntent:
    """Independent durable product and container-content decisions."""

    requested_products: frozenset[ProductKind]
    burn_subtitle_product: BurnSubtitleProduct = BurnSubtitleProduct.NONE
    mkv_tracks: frozenset[MkvTrackProduct] = frozenset()
    mp4_audio_source: Mp4AudioSource = Mp4AudioSource.AUTO

    def __post_init__(self) -> None:
        if not self.requested_products:
            msg = "At least one product must be requested"
            raise ValueError(msg)
        if self.mkv_tracks and ProductKind.MKV not in self.requested_products:
            msg = "MKV tracks require an MKV product"
            raise ValueError(msg)
        if self.mp4_audio_source is not Mp4AudioSource.AUTO and ProductKind.MP4 not in self.requested_products:
            msg = "An explicit MP4 audio source requires an MP4 product"
            raise ValueError(msg)
        if (
            self.burn_subtitle_product is not BurnSubtitleProduct.NONE
            and not {ProductKind.MKV, ProductKind.MP4} & self.requested_products
        ):
            msg = "Burned subtitles require a video product"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class GroupIntent:
    """Complete automatic or manual intent for one source group."""

    group_id: str
    mode: RunMode
    products: ProductIntent
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

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            msg = "Group intent requires a group ID"
            raise ValueError(msg)
        _validate_optional_id(self.preferred_video_artifact_id)
        _validate_optional_id(self.selected_subtitle_artifact_id)
        _validate_optional_id(self.selected_audio_artifact_id)
        _validate_optional_track_id(self.selected_audio_track_id)
        _validate_optional_track_id(self.selected_subtitle_track_id)
        if self.selected_subtitle_artifact_id and self.selected_subtitle_track_id is not None:
            msg = "Select a subtitle artifact or embedded track, not both"
            raise ValueError(msg)
        if self.selected_audio_artifact_id and self.selected_audio_track_id is not None:
            msg = "Select an audio artifact or embedded track, not both"
            raise ValueError(msg)
        if self.external_audio_role is not None and self.selected_audio_artifact_id is None:
            msg = "External audio role requires a selected audio artifact"
            raise ValueError(msg)
        if self.mode is RunMode.AUTO and self._has_manual_selection():
            msg = "Automatic intent cannot contain manual artifact or track selections"
            raise ValueError(msg)

    def _has_manual_selection(self) -> bool:
        return any(
            value is not None
            for value in (
                self.preferred_video_artifact_id,
                self.selected_subtitle_artifact_id,
                self.selected_audio_artifact_id,
                self.selected_audio_track_id,
                self.selected_subtitle_track_id,
                self.external_audio_role,
            )
        )


@dataclass(frozen=True, slots=True)
class AutoPreset:
    """Reusable automatic intent shared by selected source groups."""

    preset_id: str
    name: str
    products: ProductIntent
    subtitle_source_policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    translation_action: TranslationAction = TranslationAction.AUTO
    source_subtitle_language: str | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE

    def __post_init__(self) -> None:
        if not self.preset_id.strip() or not self.name.strip():
            msg = "Preset ID and name cannot be empty"
            raise ValueError(msg)


def apply_preset(preset: AutoPreset, groups: Sequence[SourceGroup]) -> tuple[GroupIntent, ...]:
    """Create one independent automatic intent for every selected group."""
    group_ids: tuple[str, ...] = tuple(group.group_id for group in groups)
    if len(group_ids) != len(set(group_ids)):
        msg = "Selected groups must have unique IDs"
        raise ValueError(msg)
    return tuple(
        GroupIntent(
            group_id=group_id,
            mode=RunMode.AUTO,
            products=preset.products,
            subtitle_source_policy=preset.subtitle_source_policy,
            translation_action=preset.translation_action,
            source_subtitle_language=preset.source_subtitle_language,
            subtitle_output_format=preset.subtitle_output_format,
        )
        for group_id in group_ids
    )


def _validate_optional_id(value: str | None) -> None:
    if value is not None and not value.strip():
        msg = "Selected artifact ID cannot be blank"
        raise ValueError(msg)


def _validate_optional_track_id(value: int | None) -> None:
    if value is not None and value < 0:
        msg = "Selected track ID cannot be negative"
        raise ValueError(msg)
