"""Editable fields for one independent manual group intent."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Select, SelectionList
from textual.widgets.select import NoSelection

from anishift.application.artifacts import ArtifactKind
from anishift.application.inspection import InspectedSourceGroup
from anishift.application.intents import (
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.services.media.types import MediaTrackKind
from anishift.tui.state import GroupIntentDraft


class IntentForm(Vertical):
    """Bind visible manual choices to one session-owned draft."""

    def __init__(self, draft: GroupIntentDraft, group: InspectedSourceGroup) -> None:
        super().__init__(id="intent-form")
        self.draft: GroupIntentDraft = draft
        self.group: InspectedSourceGroup = group

    def compose(self) -> ComposeResult:
        """Compose product and subtitle decisions without planner logic."""
        yield SelectionList[ProductKind](
            *((product.value, product, product in self.draft.products) for product in ProductKind),
            id="manual-products",
        )
        yield Select(
            ((policy.value, policy) for policy in SubtitleSourcePolicy),
            value=self.draft.subtitle_source_policy,
            allow_blank=False,
            id="manual-subtitle-policy",
        )
        yield Select(
            ((action.value, action) for action in TranslationAction),
            value=self.draft.translation_action,
            allow_blank=False,
            id="manual-translation-action",
        )
        yield Input(
            value=self.draft.source_subtitle_language or "",
            placeholder="Source subtitle language, e.g. eng",
            id="manual-source-language",
        )
        yield Select(
            ((output_format.value, output_format) for output_format in SubtitleOutputFormat),
            value=self.draft.subtitle_output_format,
            allow_blank=False,
            id="manual-subtitle-format",
        )
        yield Select(
            ((product.value, product) for product in BurnSubtitleProduct),
            value=self.draft.burn_subtitle_product,
            allow_blank=False,
            id="manual-burn-subtitle",
        )
        yield SelectionList[MkvTrackProduct](
            *((track.value, track, track in self.draft.mkv_tracks) for track in MkvTrackProduct),
            id="manual-mkv-tracks",
        )
        yield Select(
            ((source.value, source) for source in Mp4AudioSource),
            value=self.draft.mp4_audio_source,
            allow_blank=False,
            id="manual-mp4-audio",
        )
        yield Select(
            self._video_options(),
            value=self.draft.preferred_video_artifact_id or Select.NULL,
            prompt="Video source",
            id="manual-video-source",
        )
        yield Select(
            self._subtitle_options(),
            value=self._subtitle_value(),
            prompt="Subtitle source",
            id="manual-subtitle-source",
        )
        yield Select(
            self._audio_options(),
            value=self._audio_value(),
            prompt="Audio source",
            id="manual-audio-source",
        )

    def apply(self) -> None:
        """Copy the currently visible values into this form's draft."""
        self.draft.products = set(self.query_one("#manual-products", SelectionList).selected)
        policy = self.query_one("#manual-subtitle-policy", Select).value
        action = self.query_one("#manual-translation-action", Select).value
        video = self.query_one("#manual-video-source", Select).value
        subtitle = self.query_one("#manual-subtitle-source", Select).value
        audio = self.query_one("#manual-audio-source", Select).value
        output_format = self.query_one("#manual-subtitle-format", Select).value
        burn_product = self.query_one("#manual-burn-subtitle", Select).value
        mp4_audio = self.query_one("#manual-mp4-audio", Select).value
        if isinstance(policy, SubtitleSourcePolicy):
            self.draft.subtitle_source_policy = policy
        if isinstance(action, TranslationAction):
            self.draft.translation_action = action
        language: str = self.query_one("#manual-source-language", Input).value.strip()
        self.draft.source_subtitle_language = language or None
        if isinstance(output_format, SubtitleOutputFormat):
            self.draft.subtitle_output_format = output_format
        self.draft.burn_subtitle_product = (
            burn_product
            if ProductKind.MP4 in self.draft.products and isinstance(burn_product, BurnSubtitleProduct)
            else BurnSubtitleProduct.NONE
        )
        self.draft.mkv_tracks = (
            set(self.query_one("#manual-mkv-tracks", SelectionList).selected)
            if ProductKind.MKV in self.draft.products
            else set()
        )
        self.draft.mp4_audio_source = (
            mp4_audio
            if ProductKind.MP4 in self.draft.products and isinstance(mp4_audio, Mp4AudioSource)
            else Mp4AudioSource.AUTO
        )
        self.draft.preferred_video_artifact_id = video if isinstance(video, str) else None
        self.draft.selected_subtitle_artifact_id = None
        self.draft.selected_subtitle_track_id = None
        if isinstance(subtitle, str):
            kind, _, value = subtitle.partition(":")
            if kind == "artifact":
                self.draft.selected_subtitle_artifact_id = value
            elif kind == "track":
                self.draft.selected_subtitle_track_id = int(value)
        previous_audio_artifact_id: str | None = self.draft.selected_audio_artifact_id
        self.draft.selected_audio_artifact_id = None
        self.draft.selected_audio_track_id = None
        if isinstance(audio, str):
            kind, _, value = audio.partition(":")
            if kind == "artifact":
                self.draft.selected_audio_artifact_id = value
            elif kind == "track":
                self.draft.selected_audio_track_id = int(value)
        if self.draft.selected_audio_artifact_id != previous_audio_artifact_id:
            self.draft.external_audio_role = None

    def _video_options(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (artifact.path.name if artifact.path is not None else artifact.artifact_id, artifact.artifact_id)
            for artifact in self.group.artifacts
            if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}
        )

    def _subtitle_options(self) -> tuple[tuple[str, str], ...]:
        options: list[tuple[str, str]] = [
            (
                artifact.path.name if artifact.path is not None else artifact.artifact_id,
                f"artifact:{artifact.artifact_id}",
            )
            for artifact in self.group.artifacts
            if artifact.kind
            in {
                ArtifactKind.SOURCE_SUBTITLES,
                ArtifactKind.FULL_PL,
                ArtifactKind.SPOKEN_PL,
                ArtifactKind.DISPLAYED_PL,
            }
        ]
        for catalog in self.group.media_catalogs.values():
            options.extend(
                (f"Embedded subtitle {track.track_id} ({track.language or 'und'})", f"track:{track.track_id}")
                for track in catalog.tracks
                if track.kind is MediaTrackKind.SUBTITLES
            )
        return tuple(options)

    def _audio_options(self) -> tuple[tuple[str, str], ...]:
        options: list[tuple[str, str]] = [
            (
                artifact.path.name if artifact.path is not None else artifact.artifact_id,
                f"artifact:{artifact.artifact_id}",
            )
            for artifact in self.group.artifacts
            if artifact.kind in {ArtifactKind.SOURCE_AUDIO, ArtifactKind.NARRATION_AUDIO}
        ]
        for catalog in self.group.media_catalogs.values():
            options.extend(
                (f"Embedded audio {track.track_id} ({track.language or 'und'})", f"track:{track.track_id}")
                for track in catalog.tracks
                if track.kind is MediaTrackKind.AUDIO
            )
        return tuple(options)

    def _subtitle_value(self) -> str | NoSelection:
        if self.draft.selected_subtitle_artifact_id is not None:
            return f"artifact:{self.draft.selected_subtitle_artifact_id}"
        if self.draft.selected_subtitle_track_id is not None:
            return f"track:{self.draft.selected_subtitle_track_id}"
        return Select.NULL

    def _audio_value(self) -> str | NoSelection:
        if self.draft.selected_audio_artifact_id is not None:
            return f"artifact:{self.draft.selected_audio_artifact_id}"
        if self.draft.selected_audio_track_id is not None:
            return f"track:{self.draft.selected_audio_track_id}"
        return Select.NULL
