"""Pure deterministic planner from inspected groups and user intent to a task DAG."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    create_artifact_id,
)
from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanProblem,
    PlanTask,
    RunSettingsSnapshot,
    TaskKind,
    stable_topological_order,
)
from anishift.application.selection import choose_auto_sidecar, choose_primary_video
from anishift.errors import PlanningError

if TYPE_CHECKING:
    from anishift.application.inspection import InspectedSourceGroup


class _TrackKindView(Protocol):
    @property
    def value(self) -> str: ...


class _MediaTrackView(Protocol):
    @property
    def track_id(self) -> int: ...

    @property
    def kind(self) -> _TrackKindView: ...

    @property
    def codec_id(self) -> str: ...

    @property
    def language(self) -> str | None: ...

    @property
    def is_default(self) -> bool: ...

    @property
    def subtitle_format(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class _EmbeddedTrack:
    video: Artifact
    track_id: int
    codec_id: str
    language: str | None
    subtitle_format: str | None = None


def plan_auto(
    groups: Sequence[InspectedSourceGroup],
    preset: AutoPreset,
    settings: RunSettingsSnapshot,
) -> ExecutionPlan:
    """Build one fresh automatic plan for every selected inspected group."""
    ordered_groups: tuple[InspectedSourceGroup, ...] = _ordered_unique_groups(groups)
    intents: dict[str, GroupIntent] = {
        group.group_id: GroupIntent(
            group_id=group.group_id,
            mode=RunMode.AUTO,
            products=preset.products,
            subtitle_source_policy=preset.subtitle_source_policy,
            translation_action=preset.translation_action,
            source_subtitle_language=preset.source_subtitle_language,
            subtitle_output_format=preset.subtitle_output_format,
        )
        for group in ordered_groups
    }
    return _plan(ordered_groups, intents, settings)


def plan_manual(
    groups: Sequence[InspectedSourceGroup],
    intents: Mapping[str, GroupIntent],
    settings: RunSettingsSnapshot,
) -> ExecutionPlan:
    """Build independent manual plans using the exact intent of every group."""
    ordered_groups: tuple[InspectedSourceGroup, ...] = _ordered_unique_groups(groups)
    expected_ids: set[str] = {group.group_id for group in ordered_groups}
    if set(intents) != expected_ids:
        msg = "Manual planning requires exactly one intent for every selected group"
        raise PlanningError(msg)
    if any(intent.mode is not RunMode.MANUAL for intent in intents.values()):
        msg = "Manual planning accepts only manual group intents"
        raise PlanningError(msg)
    return _plan(ordered_groups, intents, settings)


def _ordered_unique_groups(groups: Sequence[InspectedSourceGroup]) -> tuple[InspectedSourceGroup, ...]:
    group_ids: tuple[str, ...] = tuple(group.group_id for group in groups)
    if len(group_ids) != len(set(group_ids)):
        msg = "Planning groups must have unique IDs"
        raise PlanningError(msg)
    return tuple(
        sorted(
            groups,
            key=lambda group: (
                group.source.directory.as_posix().casefold(),
                group.source.stem.casefold(),
                group.group_id,
            ),
        )
    )


def _plan(
    groups: tuple[InspectedSourceGroup, ...],
    intents: Mapping[str, GroupIntent],
    settings: RunSettingsSnapshot,
) -> ExecutionPlan:
    group_plans: list[GroupPlan] = []
    artifacts: list[Artifact] = []
    tasks: list[PlanTask] = []
    problems: list[PlanProblem] = []
    for group in groups:
        intent: GroupIntent = intents[group.group_id]
        builder = _GroupPlanner(group, intent, settings)
        group_plan, group_artifacts, group_tasks = builder.build()
        group_plans.append(group_plan)
        artifacts.extend(group_artifacts)
        tasks.extend(group_tasks)
        problems.extend(group_plan.problems)
    if any(problem.is_blocking for problem in problems):
        source_artifacts: tuple[Artifact, ...] = tuple(
            sorted(
                (artifact for group in groups for artifact in group.artifacts),
                key=lambda artifact: artifact.artifact_id,
            )
        )
        source_ids_by_group: dict[str, tuple[str, ...]] = {
            group.group_id: tuple(
                artifact.artifact_id for artifact in source_artifacts if artifact.group_id == group.group_id
            )
            for group in groups
        }
        group_plans = [
            replace(group_plan, artifact_ids=source_ids_by_group[group_plan.group_id], task_ids=())
            for group_plan in group_plans
        ]
        artifacts = list(source_artifacts)
        tasks = []
    ordered_tasks: tuple[PlanTask, ...] = stable_topological_order(tasks)
    return ExecutionPlan(
        groups=tuple(group_plans),
        artifacts=tuple(artifacts),
        tasks=ordered_tasks,
        settings=settings,
        problems=tuple(problems),
    )


class _GroupPlanner:
    def __init__(
        self,
        group: InspectedSourceGroup,
        intent: GroupIntent,
        settings: RunSettingsSnapshot,
    ) -> None:
        self.group: InspectedSourceGroup = group
        self.intent: GroupIntent = intent
        self.settings: RunSettingsSnapshot = settings
        self.artifacts: dict[str, Artifact] = {artifact.artifact_id: artifact for artifact in group.artifacts}
        self.tasks: list[PlanTask] = []
        self.producer_by_artifact: dict[str, str] = {}
        self.problems: list[PlanProblem] = []
        self._video: Artifact | None = None
        self._subtitle_input: Artifact | _EmbeddedTrack | None = None
        self._source_subtitles: Artifact | None = None
        self._full_pl: Artifact | None = None
        self._spoken_pl: Artifact | None = None
        self._displayed_pl: Artifact | None = None
        self._narration: Artifact | None = None

    def build(self) -> tuple[GroupPlan, tuple[Artifact, ...], tuple[PlanTask, ...]]:
        if self.intent.group_id != self.group.group_id:
            msg = "Group intent belongs to another inspected group"
            raise PlanningError(msg)
        if self.group.conflicts:
            self._problem(
                "source_conflict",
                "Source group contains an unresolved discovery conflict",
            )
        self._validate_manual_selections()
        if any(artifact.kind is ArtifactKind.STANDALONE_TEXT for artifact in self.group.artifacts):
            self._build_text_plan()
        else:
            self._build_media_plan()
        blocking: bool = any(problem.is_blocking for problem in self.problems)
        group_tasks: tuple[PlanTask, ...] = () if blocking else stable_topological_order(self.tasks)
        artifact_values: tuple[Artifact, ...] = tuple(
            sorted(self.artifacts.values(), key=lambda artifact: artifact.artifact_id)
        )
        group_plan = GroupPlan(
            group_id=self.group.group_id,
            intent=self.intent,
            artifact_ids=tuple(artifact.artifact_id for artifact in artifact_values),
            task_ids=tuple(task.task_id for task in group_tasks),
            problems=tuple(self.problems),
        )
        return group_plan, artifact_values, group_tasks

    def _validate_manual_selections(self) -> None:
        if self.intent.mode is not RunMode.MANUAL:
            return
        if self.intent.preferred_video_artifact_id is not None:
            self._select_video()
        if self.intent.selected_subtitle_artifact_id is not None:
            self._select_subtitle_input()
        if self.intent.selected_subtitle_track_id is not None:
            self._select_embedded_track("subtitles")
        if self.intent.selected_audio_track_id is not None:
            self._select_embedded_track("audio")
        if self.intent.selected_audio_artifact_id is None:
            return
        selected: Artifact | None = self.artifacts.get(self.intent.selected_audio_artifact_id)
        if (
            selected is None
            or selected.state is not ArtifactState.READY
            or selected.kind not in {ArtifactKind.SOURCE_AUDIO, ArtifactKind.NARRATION_AUDIO}
        ):
            self._problem("audio_selection_invalid", "Selected audio artifact is unavailable or invalid")
            return
        expected_kind: ArtifactKind | None = {
            None: None,
            ExternalAudioRole.SOURCE_AUDIO: ArtifactKind.SOURCE_AUDIO,
            ExternalAudioRole.NARRATION_MIX: ArtifactKind.NARRATION_AUDIO,
        }[self.intent.external_audio_role]
        if expected_kind is not None and selected.kind is not expected_kind:
            self._problem("audio_role_invalid", "Selected external audio does not match its declared role")
            return
        video: Artifact | None = self._select_video()
        if video is None:
            return
        if selected.duration_us is None or video.duration_us is None:
            self._problem("audio_duration_unknown", "Selected audio and video require validated durations")
            return
        if abs(selected.duration_us - video.duration_us) > self.settings.audio_duration_tolerance_us:
            self._problem("audio_duration_mismatch", "Selected audio duration differs from the selected video")

    def _build_text_plan(self) -> None:
        requested: frozenset[ProductKind] = self.intent.products.requested_products
        if requested != frozenset({ProductKind.FULL_PL}):
            self._problem(
                "txt_products_unsupported",
                "Standalone TXT can produce only full Polish SRT subtitles",
            )
            return
        source: Artifact | None = self._ready_artifact(ArtifactKind.STANDALONE_TEXT)
        if source is None:
            self._problem("txt_invalid", "Standalone TXT source is not ready")
            return
        if self.intent.translation_action is TranslationAction.DO_NOT_TRANSLATE:
            self._problem("txt_translation_required", "TXT requires translation for a Polish subtitle product")
            return
        translated: Artifact = self._intermediate(
            ArtifactKind.FULL_PL,
            "txt-translation",
            subtitle_format="srt",
            language="pol",
        )
        self._add_task(
            TaskKind.TRANSLATE_SUBTITLES,
            requires=(source,),
            produces=(translated,),
            variant="txt",
            resource_key=_translation_resource_key(self.settings),
            parameters=(("source_kind", "txt"), ("output_format", "srt")),
            is_network=self.settings.translation_is_network,
            is_paid=self.settings.translation_is_paid,
        )
        self._publish_subtitle(translated, ArtifactKind.FULL_PL, ".pl.srt")

    def _build_media_plan(self) -> None:
        products = self.intent.products
        requested: frozenset[ProductKind] = products.requested_products
        needs_narration: bool = (
            ProductKind.NARRATION_AUDIO in requested
            or MkvTrackProduct.NARRATION_AUDIO in products.mkv_tracks
            or products.mp4_audio_source is Mp4AudioSource.NARRATION
        )
        if products.mp4_audio_source is Mp4AudioSource.AUTO and ProductKind.NARRATION_AUDIO in requested:
            needs_narration = True
        self._adopt_manual_narration()
        needs_generated_narration: bool = needs_narration and self._narration is None
        needs_spoken: bool = ProductKind.SPOKEN_PL in requested or needs_generated_narration
        needs_displayed: bool = (
            ProductKind.DISPLAYED_PL in requested
            or products.burn_subtitle_product is BurnSubtitleProduct.DISPLAYED_PL
            or MkvTrackProduct.DISPLAYED_PL_SUBTITLES in products.mkv_tracks
        )
        needs_full: bool = (
            ProductKind.FULL_PL in requested
            or products.burn_subtitle_product is BurnSubtitleProduct.FULL_PL
            or MkvTrackProduct.FULL_PL_SUBTITLES in products.mkv_tracks
        )
        needs_source: bool = (
            ProductKind.SOURCE_SUBTITLES in requested
            or products.burn_subtitle_product is BurnSubtitleProduct.SOURCE
            or MkvTrackProduct.SOURCE_SUBTITLES in products.mkv_tracks
        )
        needs_any_subtitles: bool = needs_source or needs_full or needs_spoken or needs_displayed

        if needs_any_subtitles:
            self._select_subtitle_input()
        if needs_source:
            self._ensure_source_subtitles()
        if needs_full:
            self._ensure_full_pl()
        self._ensure_split_outputs(needs_spoken=needs_spoken, needs_displayed=needs_displayed)
        if needs_narration:
            self._ensure_narration()

        if ProductKind.SOURCE_SUBTITLES in requested and self._source_subtitles is not None:
            self._publish_source_subtitles(self._source_subtitles)
        if ProductKind.FULL_PL in requested and self._full_pl is not None:
            suffix: str = f".pl.{self._subtitle_format(self._full_pl)}"
            self._publish_subtitle(self._full_pl, ArtifactKind.FULL_PL, suffix)
        if ProductKind.SPOKEN_PL in requested and self._spoken_pl is not None:
            suffix = f".spoken.pl.{self._subtitle_format(self._spoken_pl)}"
            self._publish_subtitle(self._spoken_pl, ArtifactKind.SPOKEN_PL, suffix)
        if ProductKind.DISPLAYED_PL in requested and self._displayed_pl is not None:
            suffix = f".displayed.pl.{self._subtitle_format(self._displayed_pl)}"
            self._publish_subtitle(self._displayed_pl, ArtifactKind.DISPLAYED_PL, suffix)
        if ProductKind.NARRATION_AUDIO in requested and self._narration is not None:
            self._publish_audio(self._narration)

        if ProductKind.MKV in requested:
            self._compose_mkv()
        if ProductKind.MP4 in requested:
            self._compose_mp4()

    def _select_video(self) -> Artifact | None:
        if self._video is not None:
            return self._video
        candidate: Artifact | None = None
        if self.intent.mode is RunMode.MANUAL and self.intent.preferred_video_artifact_id is not None:
            candidate = self.artifacts.get(self.intent.preferred_video_artifact_id)
            if candidate is None or candidate.kind not in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}:
                self._problem("video_selection_invalid", "Selected video artifact is unavailable")
                return None
        else:
            candidate = choose_primary_video(tuple(self.artifacts.values()))
        if candidate is None or candidate.state is not ArtifactState.READY:
            self._problem("video_missing", "A validated MKV or MP4 source is required")
            return None
        self._video = candidate
        return candidate

    def _select_subtitle_input(  # noqa: C901,PLR0911,PLR0912 - explicit source policies stay visible
        self,
    ) -> Artifact | _EmbeddedTrack | None:
        if self._subtitle_input is not None:
            return self._subtitle_input
        policy: SubtitleSourcePolicy = self.intent.subtitle_source_policy
        if policy is SubtitleSourcePolicy.NONE:
            self._problem("subtitle_source_missing", "Requested products require a subtitle source")
            return None
        if self.intent.mode is RunMode.MANUAL and self.intent.selected_subtitle_artifact_id is not None:
            selected: Artifact | None = self.artifacts.get(self.intent.selected_subtitle_artifact_id)
            allowed: frozenset[ArtifactKind] = frozenset(
                {
                    ArtifactKind.SOURCE_SUBTITLES,
                    ArtifactKind.FULL_PL,
                    ArtifactKind.SPOKEN_PL,
                    ArtifactKind.DISPLAYED_PL,
                }
            )
            if selected is None or selected.kind not in allowed or selected.state is not ArtifactState.READY:
                self._problem("subtitle_selection_invalid", "Selected subtitle artifact is unavailable or invalid")
                return None
            if not self._subtitle_artifact_matches_policy(selected, policy):
                self._problem(
                    "subtitle_policy_mismatch",
                    f"Selected subtitle artifact does not match {policy.value} policy",
                    artifacts=(selected,),
                )
                return None
            if (
                selected.kind in {ArtifactKind.FULL_PL, ArtifactKind.SPOKEN_PL, ArtifactKind.DISPLAYED_PL}
                and self.intent.translation_action is TranslationAction.TRANSLATE
            ):
                self._problem(
                    "polish_product_not_translatable",
                    "A .pl product cannot be selected as fresh translation input",
                    artifacts=(selected,),
                )
            self._subtitle_input = selected
            return selected
        if self.intent.mode is RunMode.MANUAL and self.intent.selected_subtitle_track_id is not None:
            selected_embedded: _EmbeddedTrack | None = self._select_embedded_track("subtitles")
            if selected_embedded is None:
                self._problem("subtitle_selection_invalid", "Selected embedded subtitle track is unavailable")
                return None
            self._subtitle_input = selected_embedded
            return selected_embedded
        if self.intent.mode is RunMode.MANUAL and policy in {
            SubtitleSourcePolicy.SIDECAR,
            SubtitleSourcePolicy.EXTERNAL,
            SubtitleSourcePolicy.READY_POLISH,
        }:
            self._problem(
                "subtitle_selection_missing",
                f"Manual {policy.value} policy requires an explicit subtitle artifact",
            )
            return None
        if self.intent.mode is RunMode.MANUAL and policy is SubtitleSourcePolicy.EMBEDDED:
            self._problem(
                "subtitle_selection_missing",
                "Manual embedded policy requires an explicit subtitle track",
            )
            return None
        if policy is SubtitleSourcePolicy.READY_POLISH:
            if self.intent.mode is not RunMode.MANUAL:
                self._problem("subtitle_policy_invalid", "Ready Polish products can be selected only in manual mode")
                return None
            selected = self._ready_artifact(ArtifactKind.FULL_PL)
            if selected is None:
                self._problem("subtitle_source_missing", "No ready Polish subtitle product is available")
                return None
            self._subtitle_input = selected
            return selected
        if policy in {SubtitleSourcePolicy.AUTO, SubtitleSourcePolicy.SIDECAR}:
            selected = choose_auto_sidecar(tuple(self.artifacts.values()))
            if selected is not None and selected.state is ArtifactState.READY:
                self._subtitle_input = selected
                return selected
            if policy is SubtitleSourcePolicy.SIDECAR:
                self._problem("subtitle_source_missing", "No valid exact-stem ASS or SRT sidecar is available")
                return None
        if policy is SubtitleSourcePolicy.EXTERNAL:
            self._problem("subtitle_selection_missing", "External subtitle policy requires a selected artifact")
            return None
        embedded: _EmbeddedTrack | None = self._select_embedded_track("subtitles")
        if embedded is None:
            self._problem("subtitle_source_missing", "No compatible subtitle source is available")
            return None
        self._subtitle_input = embedded
        return embedded

    def _select_embedded_track(self, kind: str) -> _EmbeddedTrack | None:
        video: Artifact | None = self._select_video()
        if video is None:
            return None
        catalog = self.group.media_catalogs.get(video.artifact_id)
        if catalog is None:
            self._problem("media_catalog_missing", "Selected video has no validated media catalog")
            return None
        selected_id: int | None = (
            self.intent.selected_subtitle_track_id if kind == "subtitles" else self.intent.selected_audio_track_id
        )
        candidates = tuple(
            track
            for track in catalog.tracks
            if track.kind.value == kind and (kind != "subtitles" or track.subtitle_format in {"ass", "srt"})
        )
        if selected_id is not None:
            selected = next((track for track in candidates if track.track_id == selected_id), None)
            if selected is None:
                self._problem(f"{kind}_track_invalid", f"Selected embedded {kind} track is unavailable")
                return None
        else:
            priorities: tuple[str, ...] = (
                self.settings.subtitle_language_priority
                if kind == "subtitles"
                else self.settings.audio_language_priority
            )
            selected = min(candidates, key=lambda track: _track_rank(track, priorities), default=None)
            if selected is None:
                return None
        return _EmbeddedTrack(
            video=video,
            track_id=selected.track_id,
            codec_id=selected.codec_id,
            language=selected.language,
            subtitle_format=selected.subtitle_format,
        )

    def _ensure_source_subtitles(self) -> Artifact | None:
        if self._source_subtitles is not None:
            return self._source_subtitles
        selected: Artifact | _EmbeddedTrack | None = self._subtitle_input or self._select_subtitle_input()
        if isinstance(selected, Artifact):
            if selected.kind is not ArtifactKind.SOURCE_SUBTITLES:
                self._problem(
                    "source_subtitles_unavailable",
                    "The selected derived subtitle product cannot restore source subtitles",
                    artifacts=(selected,),
                )
                return None
            language: str | None = self._source_language(selected.language)
            if selected.language != language:
                selected = replace(selected, language=language)
                self.artifacts[selected.artifact_id] = selected
                self._subtitle_input = selected
            self._source_subtitles = selected
            return selected
        if selected is None or selected.subtitle_format is None:
            return None
        extracted: Artifact = self._intermediate(
            ArtifactKind.SOURCE_SUBTITLES,
            f"embedded-{selected.video.artifact_id}-{selected.track_id}",
            subtitle_format=selected.subtitle_format,
            language=self._source_language(selected.language),
        )
        self._add_task(
            TaskKind.EXTRACT_SUBTITLES,
            requires=(selected.video,),
            produces=(extracted,),
            variant=f"track-{selected.track_id}",
            resource_key="extraction",
            parameters=(("track_id", selected.track_id), ("target_format", selected.subtitle_format)),
        )
        self._source_subtitles = extracted
        return extracted

    def _ensure_full_pl(  # noqa: PLR0911 - each compatible manual starting point terminates independently
        self,
    ) -> Artifact | None:
        if self._full_pl is not None:
            return self._full_pl
        selected: Artifact | _EmbeddedTrack | None = self._subtitle_input or self._select_subtitle_input()
        if isinstance(selected, Artifact) and selected.kind is ArtifactKind.FULL_PL:
            if self.intent.translation_action is TranslationAction.TRANSLATE:
                self._problem(
                    "polish_product_not_translatable",
                    "A .pl product cannot be selected as fresh translation input",
                    artifacts=(selected,),
                )
                return None
            if self._requested_format_matches(selected):
                self._full_pl = selected
                return selected
            converted: Artifact = self._intermediate(
                ArtifactKind.FULL_PL,
                "manual-format-conversion",
                subtitle_format=self._output_format(selected.subtitle_format),
                language="pol",
            )
            self._add_task(
                TaskKind.NORMALIZE_SUBTITLES,
                requires=(selected,),
                produces=(converted,),
                variant="manual-format-conversion",
                resource_key="subtitles",
                parameters=(("output_format", self._subtitle_format(converted)),),
            )
            self._full_pl = converted
            return converted
        if isinstance(selected, Artifact) and selected.kind in {ArtifactKind.SPOKEN_PL, ArtifactKind.DISPLAYED_PL}:
            self._problem(
                "full_polish_unavailable",
                "The selected partial Polish product cannot recreate full subtitles",
                artifacts=(selected,),
            )
            return None
        source: Artifact | None = self._ensure_source_subtitles()
        if source is None:
            return None
        language: str | None = self._source_language(source.language)
        action: TranslationAction = self.intent.translation_action
        should_translate: bool = action is TranslationAction.TRANSLATE or (
            action is TranslationAction.AUTO and language != "pol"
        )
        if action is TranslationAction.DO_NOT_TRANSLATE and language != "pol":
            self._problem(
                "false_polish_product",
                "A non-Polish or unknown subtitle source cannot be published as .pl without translation",
                artifacts=(source,),
            )
            return None
        output_format: str = self._output_format(source.subtitle_format)
        full: Artifact = self._intermediate(
            ArtifactKind.FULL_PL,
            "fresh-polish",
            subtitle_format=output_format,
            language="pol",
        )
        if should_translate:
            self._add_task(
                TaskKind.TRANSLATE_SUBTITLES,
                requires=(source,),
                produces=(full,),
                variant="polish",
                resource_key=_translation_resource_key(self.settings),
                parameters=(("output_format", output_format),),
                is_network=self.settings.translation_is_network,
                is_paid=self.settings.translation_is_paid,
            )
        else:
            self._add_task(
                TaskKind.NORMALIZE_SUBTITLES,
                requires=(source,),
                produces=(full,),
                variant="polish-bypass",
                resource_key="subtitles",
                parameters=(("output_format", output_format),),
            )
        self._full_pl = full
        return full

    def _ensure_split_outputs(self, *, needs_spoken: bool, needs_displayed: bool) -> None:
        if not needs_spoken and not needs_displayed:
            return
        selected: Artifact | _EmbeddedTrack | None = self._subtitle_input or self._select_subtitle_input()
        if isinstance(selected, Artifact) and selected.kind is ArtifactKind.SPOKEN_PL:
            self._spoken_pl = self._convert_partial_product(selected, ProductKind.SPOKEN_PL)
            if needs_displayed:
                self._problem(
                    "displayed_polish_unavailable",
                    "Spoken-only subtitles cannot recreate displayed subtitles",
                    artifacts=(selected,),
                )
            return
        if isinstance(selected, Artifact) and selected.kind is ArtifactKind.DISPLAYED_PL:
            self._displayed_pl = self._convert_partial_product(selected, ProductKind.DISPLAYED_PL)
            if needs_spoken:
                self._problem(
                    "spoken_polish_unavailable",
                    "Displayed-only subtitles cannot recreate spoken subtitles",
                    artifacts=(selected,),
                )
            return
        full: Artifact | None = self._ensure_full_pl()
        if full is None:
            return
        outputs: list[Artifact] = []
        if needs_spoken:
            self._spoken_pl = self._intermediate(
                ArtifactKind.SPOKEN_PL,
                "split-spoken",
                subtitle_format=self._subtitle_format(full),
                language="pol",
            )
            outputs.append(self._spoken_pl)
        if needs_displayed:
            self._displayed_pl = self._intermediate(
                ArtifactKind.DISPLAYED_PL,
                "split-displayed",
                subtitle_format=self._subtitle_format(full),
                language="pol",
            )
            outputs.append(self._displayed_pl)
        self._add_task(
            TaskKind.SPLIT_SUBTITLES,
            requires=(full,),
            produces=tuple(outputs),
            variant="polish",
            resource_key="subtitles",
        )

    def _convert_partial_product(self, source: Artifact, requested_kind: ProductKind) -> Artifact:
        if requested_kind not in self.intent.products.requested_products or self._requested_format_matches(source):
            return source
        converted: Artifact = self._intermediate(
            source.kind,
            f"manual-{source.kind.value}-format-conversion",
            subtitle_format=self._output_format(source.subtitle_format),
            language="pol",
        )
        if converted.artifact_id in self.producer_by_artifact:
            return converted
        self._add_task(
            TaskKind.NORMALIZE_SUBTITLES,
            requires=(source,),
            produces=(converted,),
            variant=f"manual-{source.kind.value}-format-conversion",
            resource_key="subtitles",
            parameters=(("output_format", self._subtitle_format(converted)),),
        )
        return converted

    def _ensure_narration(self) -> Artifact | None:
        if self._narration is not None:
            return self._narration
        if self.intent.mode is RunMode.MANUAL and self.intent.selected_audio_artifact_id is not None:
            selected: Artifact | None = self.artifacts.get(self.intent.selected_audio_artifact_id)
            if (
                selected is None
                or selected.state is not ArtifactState.READY
                or selected.kind not in {ArtifactKind.SOURCE_AUDIO, ArtifactKind.NARRATION_AUDIO}
            ):
                self._problem("audio_selection_invalid", "Selected audio artifact is unavailable or invalid")
                return None
            is_mix: bool = selected.kind is ArtifactKind.NARRATION_AUDIO or (
                self.intent.external_audio_role is ExternalAudioRole.NARRATION_MIX
            )
            if is_mix:
                self._narration = selected
                return selected
        spoken: Artifact | None = self._spoken_pl
        if spoken is None:
            self._ensure_split_outputs(needs_spoken=True, needs_displayed=False)
            spoken = self._spoken_pl
        source_audio: Artifact | None = self._select_source_audio()
        if spoken is None or source_audio is None:
            return None
        manifest: Artifact = self._intermediate(ArtifactKind.TTS_MANIFEST, "tts-manifest")
        self._add_task(
            TaskKind.SYNTHESIZE_SPEECH,
            requires=(spoken,),
            produces=(manifest,),
            variant="narration",
            resource_key=f"tts:{self.settings.tts_profile_id}",
            is_network=self.settings.tts_is_network,
            is_paid=self.settings.tts_is_paid,
        )
        narration: Artifact = self._intermediate(
            ArtifactKind.NARRATION_AUDIO,
            "narration-mix",
            audio_codec=self.settings.audio_output_profile.casefold(),
        )
        self._add_task(
            TaskKind.MIX_NARRATION,
            requires=(source_audio, manifest),
            produces=(narration,),
            variant="narration",
            resource_key=f"audio:{self.settings.audio_profile_id}",
            parameters=(("output_profile", self.settings.audio_output_profile.casefold()),),
        )
        self._narration = narration
        return narration

    def _adopt_manual_narration(self) -> None:
        if self.intent.mode is not RunMode.MANUAL or self.intent.selected_audio_artifact_id is None:
            return
        selected: Artifact | None = self.artifacts.get(self.intent.selected_audio_artifact_id)
        if selected is None or selected.state is not ArtifactState.READY:
            return
        if selected.kind is ArtifactKind.NARRATION_AUDIO or (
            self.intent.external_audio_role is ExternalAudioRole.NARRATION_MIX
        ):
            self._narration = selected

    def _select_source_audio(self) -> Artifact | None:
        if self.intent.mode is RunMode.MANUAL and self.intent.selected_audio_artifact_id is not None:
            selected: Artifact | None = self.artifacts.get(self.intent.selected_audio_artifact_id)
            if selected is not None and (
                selected.kind is ArtifactKind.SOURCE_AUDIO
                or self.intent.external_audio_role is ExternalAudioRole.SOURCE_AUDIO
            ):
                return selected
        embedded: _EmbeddedTrack | None = self._select_embedded_track("audio")
        if embedded is None:
            self._problem("audio_source_missing", "Narration mixing requires a compatible source audio track")
            return None
        source_audio: Artifact = self._intermediate(
            ArtifactKind.SOURCE_AUDIO,
            f"embedded-{embedded.video.artifact_id}-{embedded.track_id}",
            audio_codec=embedded.codec_id,
        )
        self._add_task(
            TaskKind.EXTRACT_AUDIO,
            requires=(embedded.video,),
            produces=(source_audio,),
            variant=f"track-{embedded.track_id}",
            resource_key="extraction",
            parameters=(
                ("source_codec", embedded.codec_id),
                ("track_id", embedded.track_id),
                ("target_format", "audio_copy"),
            ),
        )
        return source_audio

    def _publish_source_subtitles(self, source: Artifact) -> Artifact | None:
        if source.lifetime is ArtifactLifetime.SOURCE and self._is_exact_stem_sidecar(source):
            return source
        suffix: str = f".{self._subtitle_format(source)}"
        destination: Path = self.group.source.directory / f"{self.group.source.stem}{suffix}"
        collision: Artifact | None = next(
            (
                artifact
                for artifact in self.group.artifacts
                if artifact.path is not None
                and _same_path(artifact.path, destination)
                and artifact.artifact_id != source.artifact_id
            ),
            None,
        )
        if collision is not None:
            self._problem(
                "source_path_collision",
                "Embedded or external subtitles cannot replace an existing exact-stem source sidecar",
                artifacts=(collision,),
            )
            return None
        target: Artifact = self._durable_target(
            ArtifactKind.SOURCE_SUBTITLES,
            destination,
            subtitle_format=self._subtitle_format(source),
            language=source.language,
        )
        self._add_publish(source, target)
        return target

    def _publish_subtitle(self, source: Artifact, kind: ArtifactKind, suffix: str) -> Artifact:
        destination: Path = self.group.source.directory / f"{self.group.source.stem}{suffix}"
        if source.state is ArtifactState.READY and source.path is not None and _same_path(source.path, destination):
            return source
        target: Artifact = self._durable_target(
            kind,
            destination,
            subtitle_format=self._subtitle_format(source),
            language="pol",
        )
        self._add_publish(source, target)
        return target

    def _publish_audio(self, source: Artifact) -> Artifact:
        profile: str = self.settings.audio_output_profile.casefold()
        extension: str = _audio_product_extension(profile)
        publish_source: Artifact = source
        if (
            source.lifetime is ArtifactLifetime.SOURCE
            or source.audio_codec is None
            or source.audio_codec.casefold() != profile
        ):
            publish_source = self._intermediate(
                ArtifactKind.NARRATION_AUDIO,
                "narration-transcode",
                audio_codec=profile,
            )
            self._add_task(
                TaskKind.TRANSCODE_AUDIO,
                requires=(source,),
                produces=(publish_source,),
                variant="narration-product",
                resource_key=f"audio:{self.settings.audio_profile_id}",
                parameters=(("output_profile", profile),),
            )
        destination: Path = self.group.source.directory / f"{self.group.source.stem}{extension}"
        if (
            publish_source.state is ArtifactState.READY
            and publish_source.path is not None
            and _same_path(publish_source.path, destination)
        ):
            return publish_source
        target: Artifact = self._durable_target(
            ArtifactKind.NARRATION_AUDIO,
            destination,
            audio_codec=profile,
        )
        self._add_publish(publish_source, target)
        return target

    def _compose_mkv(self) -> None:
        video: Artifact | None = self._select_video()
        if video is None:
            return
        requires: list[Artifact] = [video]
        tracks: list[str] = []
        for track in sorted(self.intent.products.mkv_tracks, key=lambda item: item.value):
            artifact: Artifact | None = {
                MkvTrackProduct.SOURCE_SUBTITLES: self._source_subtitles,
                MkvTrackProduct.FULL_PL_SUBTITLES: self._full_pl,
                MkvTrackProduct.DISPLAYED_PL_SUBTITLES: self._displayed_pl,
                MkvTrackProduct.NARRATION_AUDIO: self._narration,
            }[track]
            if artifact is None:
                self._problem("mkv_track_unavailable", f"Requested MKV track is unavailable: {track.value}")
                continue
            requires.append(artifact)
            tracks.append(track.value)
        target: Artifact = self._durable_target(
            ArtifactKind.FINAL_MKV,
            self.group.source.directory / f"{self.group.source.stem}.pl.mkv",
        )
        self._add_task(
            TaskKind.COMPOSE_MKV,
            requires=tuple(_unique_artifacts(requires)),
            produces=(target,),
            variant="mkv",
            resource_key=f"composition:{self.settings.composition_profile_id}",
            parameters=(("mkv_tracks", ",".join(tracks)),),
        )

    def _compose_mp4(self) -> None:
        video: Artifact | None = self._select_video()
        if video is None:
            return
        requires: list[Artifact] = [video]
        burn: Artifact | None = self._burn_artifact()
        if burn is not None:
            requires.append(burn)
        audio_source: Mp4AudioSource = self.intent.products.mp4_audio_source
        use_narration: bool = audio_source is Mp4AudioSource.NARRATION or (
            audio_source is Mp4AudioSource.AUTO and self._narration is not None
        )
        if use_narration:
            if self._narration is None:
                self._problem(
                    "mp4_narration_unavailable", "MP4 requests narration but no narration source is available"
                )
            else:
                requires.append(self._narration)
        target: Artifact = self._durable_target(
            ArtifactKind.FINAL_MP4,
            self.group.source.directory / f"{self.group.source.stem}.pl.mp4",
        )
        self._add_task(
            TaskKind.COMPOSE_MP4,
            requires=tuple(_unique_artifacts(requires)),
            produces=(target,),
            variant="mp4",
            resource_key=f"composition:{self.settings.composition_profile_id}",
            parameters=(
                ("audio_source", "narration" if use_narration else "original"),
                ("burn_subtitles", self.intent.products.burn_subtitle_product.value),
            ),
        )

    def _burn_artifact(self) -> Artifact | None:
        return {
            BurnSubtitleProduct.NONE: None,
            BurnSubtitleProduct.SOURCE: self._source_subtitles,
            BurnSubtitleProduct.FULL_PL: self._full_pl,
            BurnSubtitleProduct.DISPLAYED_PL: self._displayed_pl,
        }[self.intent.products.burn_subtitle_product]

    def _ready_artifact(self, kind: ArtifactKind) -> Artifact | None:
        candidates: tuple[Artifact, ...] = tuple(
            artifact
            for artifact in self.artifacts.values()
            if artifact.kind is kind and artifact.state is ArtifactState.READY
        )
        return min(candidates, key=_artifact_path_key, default=None)

    def _intermediate(
        self,
        kind: ArtifactKind,
        variant: str,
        *,
        subtitle_format: str | None = None,
        language: str | None = None,
        audio_codec: str | None = None,
    ) -> Artifact:
        artifact_id: str = create_artifact_id(self.group.group_id, kind, variant=f"intermediate:{variant}")
        existing: Artifact | None = self.artifacts.get(artifact_id)
        if existing is not None:
            return existing
        artifact = Artifact(
            artifact_id=artifact_id,
            group_id=self.group.group_id,
            kind=kind,
            path=None,
            state=ArtifactState.MISSING,
            lifetime=ArtifactLifetime.INTERMEDIATE,
            subtitle_format=subtitle_format,
            language=language,
            audio_codec=audio_codec,
        )
        self.artifacts[artifact_id] = artifact
        return artifact

    def _durable_target(
        self,
        kind: ArtifactKind,
        destination: Path,
        *,
        subtitle_format: str | None = None,
        language: str | None = None,
        audio_codec: str | None = None,
    ) -> Artifact:
        existing: Artifact | None = next(
            (
                artifact
                for artifact in self.artifacts.values()
                if artifact.kind is kind and artifact.path is not None and _same_path(artifact.path, destination)
            ),
            None,
        )
        if existing is not None:
            self._problem(
                "product_overwrite",
                f"Existing product will be replaced atomically: {destination.name}",
                artifacts=(existing,),
                is_blocking=False,
            )
        artifact_id: str = (
            existing.artifact_id
            if existing is not None
            else create_artifact_id(self.group.group_id, kind, Path(destination.name))
        )
        target = Artifact(
            artifact_id=artifact_id,
            group_id=self.group.group_id,
            kind=kind,
            path=None,
            state=ArtifactState.MISSING,
            lifetime=ArtifactLifetime.DURABLE,
            planned_destination=destination,
            preserved_path=existing.path if existing is not None else None,
            subtitle_format=subtitle_format,
            language=language,
            audio_codec=audio_codec,
        )
        self.artifacts[artifact_id] = target
        return target

    def _add_publish(self, source: Artifact, target: Artifact) -> None:
        self._add_task(
            TaskKind.PUBLISH_ARTIFACT,
            requires=(source,),
            produces=(target,),
            variant=target.kind.value,
            resource_key="filesystem",
        )

    def _add_task(  # noqa: PLR0913 - task contract keeps execution flags explicit at call sites
        self,
        kind: TaskKind,
        *,
        requires: tuple[Artifact, ...],
        produces: tuple[Artifact, ...],
        variant: str,
        resource_key: str,
        parameters: tuple[tuple[str, str | int | bool], ...] = (),
        is_network: bool = False,
        is_paid: bool = False,
    ) -> None:
        if not produces:
            return
        task_id: str = _task_id(self.group.group_id, kind, variant)
        dependencies: tuple[str, ...] = tuple(
            sorted(
                {
                    producer
                    for artifact in requires
                    if (producer := self.producer_by_artifact.get(artifact.artifact_id)) is not None
                }
            )
        )
        task = PlanTask(
            task_id=task_id,
            group_id=self.group.group_id,
            kind=kind,
            requires=tuple(artifact.artifact_id for artifact in requires),
            produces=tuple(artifact.artifact_id for artifact in produces),
            depends_on=dependencies,
            resource_key=resource_key,
            parameters=tuple(sorted(parameters)),
            is_network=is_network,
            is_paid=is_paid,
        )
        if any(existing.task_id == task_id for existing in self.tasks):
            msg = f"Planner generated duplicate task ID: {task_id}"
            raise PlanningError(msg)
        self.tasks.append(task)
        for artifact in produces:
            if artifact.artifact_id in self.producer_by_artifact:
                msg = f"Planner generated two producers for {artifact.artifact_id}"
                raise PlanningError(msg)
            self.producer_by_artifact[artifact.artifact_id] = task_id

    def _problem(
        self,
        code: str,
        message: str,
        *,
        artifacts: tuple[Artifact, ...] = (),
        is_blocking: bool = True,
    ) -> None:
        artifact_ids: tuple[str, ...] = tuple(item.artifact_id for item in artifacts)
        if any(
            problem.code == code and problem.artifact_ids == artifact_ids and problem.is_blocking is is_blocking
            for problem in self.problems
        ):
            return
        self.problems.append(
            PlanProblem(
                code=code,
                message=message,
                group_id=self.group.group_id,
                artifact_ids=artifact_ids,
                is_blocking=is_blocking,
            )
        )

    def _source_language(self, detected: str | None) -> str | None:
        declared: str | None = self.intent.source_subtitle_language
        value: str | None = declared if declared is not None else detected
        if value is None:
            return None
        normalized: str = value.strip().casefold()
        if normalized in {"pl", "pol", "pl-pl"}:
            return "pol"
        return normalized or None

    def _subtitle_artifact_matches_policy(
        self,
        artifact: Artifact,
        policy: SubtitleSourcePolicy,
    ) -> bool:
        if policy is SubtitleSourcePolicy.AUTO:
            return True
        if policy is SubtitleSourcePolicy.SIDECAR:
            return artifact.kind is ArtifactKind.SOURCE_SUBTITLES and self._is_exact_stem_sidecar(artifact)
        if policy is SubtitleSourcePolicy.EXTERNAL:
            return artifact.kind is ArtifactKind.SOURCE_SUBTITLES and not self._is_exact_stem_sidecar(artifact)
        if policy is SubtitleSourcePolicy.READY_POLISH:
            return artifact.kind is ArtifactKind.FULL_PL
        return False

    def _output_format(self, source_format: str | None) -> str:
        requested: SubtitleOutputFormat = self.intent.subtitle_output_format
        if requested is SubtitleOutputFormat.ASS:
            return "ass"
        if requested is SubtitleOutputFormat.SRT:
            return "srt"
        return source_format if source_format in {"ass", "srt"} else "srt"

    def _requested_format_matches(self, artifact: Artifact) -> bool:
        requested: SubtitleOutputFormat = self.intent.subtitle_output_format
        return requested is SubtitleOutputFormat.PRESERVE or artifact.subtitle_format == requested.value

    def _subtitle_format(self, artifact: Artifact) -> str:
        return artifact.subtitle_format if artifact.subtitle_format in {"ass", "srt"} else "srt"

    def _is_exact_stem_sidecar(self, artifact: Artifact) -> bool:
        if artifact.path is None or artifact.kind is not ArtifactKind.SOURCE_SUBTITLES:
            return False
        expected: Path = self.group.source.directory / f"{self.group.source.stem}.{self._subtitle_format(artifact)}"
        return _same_path(artifact.path, expected)


def _track_rank(track: _MediaTrackView, priorities: tuple[str, ...]) -> tuple[int, int, int, int]:
    normalized_priorities: tuple[str, ...] = tuple(language.casefold() for language in priorities)
    language: str | None = track.language.casefold() if track.language is not None else None
    try:
        priority: int = normalized_priorities.index(language) if language is not None else len(normalized_priorities)
        preferred: int = 0 if language in normalized_priorities else 1
    except ValueError:
        priority = len(normalized_priorities)
        preferred = 1
    return preferred, priority, 0 if track.is_default else 1, track.track_id


def _task_id(group_id: str, kind: TaskKind, variant: str) -> str:
    digest: str = sha256(f"{group_id}:{kind.value}:{variant.casefold()}".encode()).hexdigest()
    return f"task-{kind.value}-{digest[:12]}"


def _translation_resource_key(settings: RunSettingsSnapshot) -> str:
    if settings.translation_profile_id == "llm":
        return f"llm:{settings.llm_profile_id}"
    return f"translation:{settings.translation_profile_id}"


def _artifact_path_key(artifact: Artifact) -> tuple[str, str, str]:
    if artifact.path is None:
        return "", "", artifact.artifact_id
    return artifact.path.as_posix().casefold(), artifact.path.as_posix(), artifact.artifact_id


def _same_path(first: Path, second: Path) -> bool:
    return first.as_posix().casefold() == second.as_posix().casefold()


def _unique_artifacts(artifacts: Sequence[Artifact]) -> tuple[Artifact, ...]:
    unique: dict[str, Artifact] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.artifact_id, artifact)
    return tuple(unique.values())


def _audio_product_extension(profile: str) -> str:
    return ".m4a" if profile == "aac" else f".{profile}"
