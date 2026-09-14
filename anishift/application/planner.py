"""Pure deterministic planner from inspected groups and user intent to a task DAG."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from natsort import os_sorted

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    create_artifact_id,
)
from anishift.application.control import (
    AudiobookRecipe,
    RecipePreferences,
    TextResultFormat,
    TranslateRecipe,
)
from anishift.application.intents import (
    AUDIOBOOK_PRODUCTS,
    TRANSLATE_PRODUCTS,
    AutoPreset,
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    Mp4AudioSource,
    NarrationTimeline,
    ProductIntent,
    ProductKind,
    RebuildRequest,
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
from anishift.application.products import product_path
from anishift.application.selection import choose_auto_sidecar, choose_primary_video
from anishift.application.workflows import WorkflowTarget
from anishift.errors import PlanningError

if TYPE_CHECKING:
    from anishift.application.inspection import InspectedSourceGroup

# ── Constants ──────────────────────────────────────────────────────────────

_DOCUMENT_SOURCE_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.STANDALONE_TEXT, ArtifactKind.SOURCE_SUBTITLES},
)
"""Documents a text place reads, whether a plain text or an authored subtitle file."""

_UNTIMED_DOCUMENT_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.STANDALONE_TEXT, ArtifactKind.TRANSLATED_TEXT},
)
"""Documents carrying words without a single timestamp, so nothing can be read by their own times."""

_DOCUMENT_TARGETS: Final[frozenset[WorkflowTarget]] = frozenset(
    {WorkflowTarget.TRANSLATE, WorkflowTarget.AUDIOBOOK},
)
"""Targets reading one document and needing neither a picture nor an existing audio track."""

_NON_DIALOGUE_SUBTITLE_NAME: Final[re.Pattern[str]] = re.compile(r"sign|song|forced", re.I)
"""Track names announcing signs, songs, or forced captions instead of full dialogue."""


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
    def name(self) -> str | None: ...

    @property
    def is_default(self) -> bool: ...

    @property
    def is_forced(self) -> bool: ...

    @property
    def subtitle_format(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class _EmbeddedTrack:
    video: Artifact
    track_id: int
    codec_id: str
    language: str | None
    subtitle_format: str | None = None


def plan_auto(  # noqa: PLR0913 - every automatic planning input stays an explicit call-site choice
    groups: Sequence[InspectedSourceGroup],
    preset: AutoPreset,
    settings: RunSettingsSnapshot,
    *,
    rebuild: RebuildRequest | None = None,
    overrides: Mapping[str, object] | None = None,
    recipes: RecipePreferences | None = None,
) -> ExecutionPlan:
    """Build one fresh automatic plan for every selected inspected group, each for the target of its own place."""
    ordered_groups: tuple[InspectedSourceGroup, ...] = _ordered_unique_groups(groups)
    products: ProductIntent = (
        preset.products
        if rebuild is None
        else replace(preset.products, requested_products=preset.products.requested_products | rebuild.products)
    )
    intents: dict[str, GroupIntent] = {
        group.group_id: _auto_intent(group, preset, products, recipes) for group in ordered_groups
    }
    snapshot: RunSettingsSnapshot = settings if overrides is None else settings.with_overrides(overrides)
    return _plan(ordered_groups, intents, snapshot, rebuild=rebuild)


def auto_group_products(
    group: InspectedSourceGroup,
    products: ProductIntent,
    recipes: RecipePreferences | None = None,
) -> ProductIntent:
    """Return the products one group is automatically asked for, by the target of its own place."""
    if group.source.route.target is WorkflowTarget.AUDIOBOOK:
        return ProductIntent(requested_products=AUDIOBOOK_PRODUCTS)
    if group.source.route.target is not WorkflowTarget.TRANSLATE:
        return products
    translate: TranslateRecipe = (recipes if recipes is not None else RecipePreferences()).translate
    holds_text: bool = any(
        artifact.kind is ArtifactKind.STANDALONE_TEXT and artifact.state is ArtifactState.READY
        for artifact in group.artifacts
    )
    writes_text: bool = holds_text and translate.text_result is TextResultFormat.TEXT
    product: ProductKind = ProductKind.TRANSLATED_TEXT if writes_text else ProductKind.FULL_PL
    return ProductIntent(requested_products=frozenset({product}))


def _auto_intent(
    group: InspectedSourceGroup,
    preset: AutoPreset,
    products: ProductIntent,
    recipes: RecipePreferences | None,
) -> GroupIntent:
    preferences: RecipePreferences = recipes if recipes is not None else RecipePreferences()
    if group.source.route.target is WorkflowTarget.TRANSLATE:
        return GroupIntent(
            group_id=group.group_id,
            mode=RunMode.AUTO,
            products=auto_group_products(group, products, recipes),
            translation_action=preferences.translate.translation_action,
            source_subtitle_language=preset.source_subtitle_language,
            subtitle_output_format=preset.subtitle_output_format,
            target=WorkflowTarget.TRANSLATE,
        )
    if group.source.route.target is WorkflowTarget.AUDIOBOOK:
        audiobook: AudiobookRecipe = preferences.audiobook
        return GroupIntent(
            group_id=group.group_id,
            mode=RunMode.AUTO,
            products=auto_group_products(group, products, recipes),
            translation_action=audiobook.translation_action,
            source_subtitle_language=preset.source_subtitle_language,
            subtitle_output_format=preset.subtitle_output_format,
            narration_timeline=audiobook.timeline,
            target=WorkflowTarget.AUDIOBOOK,
        )
    return GroupIntent(
        group_id=group.group_id,
        mode=RunMode.AUTO,
        products=products,
        subtitle_source_policy=(
            SubtitleSourcePolicy.SIDECAR if group.source.route.requires_sidecar else preset.subtitle_source_policy
        ),
        translation_action=preset.translation_action,
        source_subtitle_language=preset.source_subtitle_language,
        subtitle_output_format=preset.subtitle_output_format,
        target=group.source.route.target,
    )


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
        os_sorted(
            groups,
            key=lambda group: (
                group.source.directory.as_posix(),
                group.source.stem,
                group.group_id,
            ),
        )
    )


def _plan(
    groups: tuple[InspectedSourceGroup, ...],
    intents: Mapping[str, GroupIntent],
    settings: RunSettingsSnapshot,
    *,
    rebuild: RebuildRequest | None = None,
) -> ExecutionPlan:
    group_plans: list[GroupPlan] = []
    artifacts: list[Artifact] = []
    tasks: list[PlanTask] = []
    problems: list[PlanProblem] = []
    for group in groups:
        intent: GroupIntent = intents[group.group_id]
        builder: _GroupPlanner = _GroupPlanner(group, intent, settings, rebuild=rebuild)
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
            replace(
                group_plan,
                artifact_ids=source_ids_by_group[group_plan.group_id],
                task_ids=(),
                problems=tuple(
                    _without_planned_artifacts(problem, source_ids_by_group[group_plan.group_id])
                    for problem in group_plan.problems
                ),
            )
            for group_plan in group_plans
        ]
        problems = [problem for group_plan in group_plans for problem in group_plan.problems]
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


def _without_planned_artifacts(problem: PlanProblem, source_ids: tuple[str, ...]) -> PlanProblem:
    kept: tuple[str, ...] = tuple(artifact_id for artifact_id in problem.artifact_ids if artifact_id in source_ids)
    if kept == problem.artifact_ids:
        return problem
    return replace(problem, artifact_ids=kept)


class _GroupPlanner:
    def __init__(
        self,
        group: InspectedSourceGroup,
        intent: GroupIntent,
        settings: RunSettingsSnapshot,
        *,
        rebuild: RebuildRequest | None = None,
    ) -> None:
        self.group: InspectedSourceGroup = group
        self.intent: GroupIntent = intent
        self.settings: RunSettingsSnapshot = settings
        self._rebuild: frozenset[ProductKind] = frozenset() if rebuild is None else rebuild.products
        self._invalidated: frozenset[ArtifactKind] = _invalidated_products(intent, self._rebuild)
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
        self._source_audio: Artifact | None = None
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
        self._require_accepted_target()
        self._require_mandatory_sidecar()
        self._validate_manual_selections()
        self._build_target_plan()
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

    def _require_accepted_target(self) -> None:
        if self.intent.target is None or self.intent.target is self.group.source.route.target:
            return
        self._problem(
            "intent_target_changed",
            "This work was accepted for another place than the one its files sit in now",
        )

    def _require_mandatory_sidecar(self) -> None:
        if not self.group.source.route.requires_sidecar:
            return
        if any(
            artifact.kind is ArtifactKind.SOURCE_SUBTITLES and artifact.state is ArtifactState.READY
            for artifact in self.group.artifacts
        ):
            return
        self._problem(
            "sidecar_required",
            "This place pairs every film with its own subtitle file, whichever source the run reads",
        )

    def _build_target_plan(self) -> None:
        if self.group.source.route.target is WorkflowTarget.TRANSLATE:
            self._build_translate_plan()
            return
        if self.group.source.route.target is WorkflowTarget.AUDIOBOOK:
            self._build_audiobook_plan()
            return
        if ProductKind.TRANSLATED_TEXT in self.intent.products.requested_products:
            self._problem(
                "translated_text_unsupported",
                "Only a translate place writes a plain translated text document",
            )
            return
        if any(artifact.kind is ArtifactKind.STANDALONE_TEXT for artifact in self.group.artifacts):
            self._build_text_plan()
            return
        self._build_media_plan()

    def _validate_manual_selections(self) -> None:
        if self.intent.mode is not RunMode.MANUAL or self.group.source.route.target in _DOCUMENT_TARGETS:
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
        if self._ready_product(ArtifactKind.FULL_PL) is not None:
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
        self._draft_timings(translated)
        self._publish_subtitle(translated, ArtifactKind.FULL_PL)

    def _build_translate_plan(self) -> None:
        requested: frozenset[ProductKind] = self.intent.products.requested_products
        if not requested <= TRANSLATE_PRODUCTS:
            self._problem(
                "translate_products_unsupported",
                "A translate place writes only a Polish text or subtitle document",
            )
            return
        source: Artifact | None = self._document_source(
            "translate_source_missing",
            "translate_source_ambiguous",
        )
        if source is None:
            return
        if self.intent.translation_action is TranslationAction.DO_NOT_TRANSLATE:
            self._problem(
                "translate_translation_required",
                "A translate place cannot write a Polish document without translating",
                artifacts=(source,),
            )
            return
        if source.kind is not ArtifactKind.STANDALONE_TEXT:
            self._translate_subtitle_document(source, requested)
            return
        if ProductKind.TRANSLATED_TEXT in requested:
            self._translate_text_document(source)
        if ProductKind.FULL_PL in requested:
            self._translate_text_to_draft_subtitles(source)

    def _build_audiobook_plan(self) -> None:
        requested: frozenset[ProductKind] = self.intent.products.requested_products
        if not requested <= AUDIOBOOK_PRODUCTS:
            self._problem(
                "audiobook_products_unsupported",
                "An audiobook place writes only the recording of one document",
            )
            return
        source: Artifact | None = self._document_source(
            "audiobook_source_missing",
            "audiobook_source_ambiguous",
        )
        if source is None:
            return
        self._narration = self._ready_product(ArtifactKind.NARRATION_AUDIO)
        if self._narration is None:
            timeline: NarrationTimeline = self.intent.narration_timeline
            if timeline is NarrationTimeline.SOURCE_TIMES and source.kind in _UNTIMED_DOCUMENT_KINDS:
                self._problem(
                    "narration_times_unavailable",
                    "A plain text document carries no times a recording could keep",
                    artifacts=(source,),
                )
                return
            script: Artifact | None = self._narration_script(source)
            if script is None:
                return
            self._read_document_aloud(script)
        if ProductKind.NARRATION_AUDIO in requested and self._narration is not None:
            self._publish_audio(self._narration)

    def _narration_script(self, source: Artifact) -> Artifact | None:
        """Return the document the voice really reads, translating first only when that was asked for."""
        if self.intent.translation_action is TranslationAction.DO_NOT_TRANSLATE:
            return source
        if source.kind is not ArtifactKind.STANDALONE_TEXT:
            self._subtitle_input = source
            return self._ensure_full_pl()
        script: Artifact = self._intermediate(
            ArtifactKind.FULL_PL,
            "narration-script",
            subtitle_format="srt",
            language="pol",
        )
        self._add_task(
            TaskKind.TRANSLATE_SUBTITLES,
            requires=(source,),
            produces=(script,),
            variant="narration-script",
            resource_key=_translation_resource_key(self.settings),
            parameters=(("source_kind", "txt"), ("output_format", "srt")),
            is_network=self.settings.translation_is_network,
            is_paid=self.settings.translation_is_paid,
        )
        self._draft_timings(script)
        return script

    def _read_document_aloud(self, script: Artifact) -> None:
        """Record one document on the timeline its own place asked for."""
        timeline: NarrationTimeline = self.intent.narration_timeline
        manifest: Artifact = self._synthesize_speech(script, timeline)
        profile: str = self.settings.audio_output_profile.casefold()
        narration: Artifact = self._intermediate(
            ArtifactKind.NARRATION_AUDIO,
            f"narration-mix-{timeline.value}",
            audio_codec=profile,
        )
        self._add_task(
            TaskKind.MIX_NARRATION,
            requires=(manifest,),
            produces=(narration,),
            variant=f"narration-{timeline.value}",
            resource_key=f"audio:{self.settings.audio_profile_id}",
            parameters=(("mix_source", "standalone"), ("output_profile", profile)),
        )
        self._narration = narration

    def _synthesize_speech(self, script: Artifact, timeline: NarrationTimeline) -> Artifact:
        manifest: Artifact = self._intermediate(ArtifactKind.TTS_MANIFEST, f"tts-manifest-{timeline.value}")
        self._add_task(
            TaskKind.SYNTHESIZE_SPEECH,
            requires=(script,),
            produces=(manifest,),
            variant=f"narration-{timeline.value}",
            resource_key=f"tts:{self.settings.tts_profile_id}",
            parameters=(("narration_timeline", timeline.value), ("script_kind", script.kind.value)),
            is_network=self.settings.tts_is_network,
            is_paid=self.settings.tts_is_paid,
        )
        return manifest

    def _document_source(self, missing_code: str, ambiguous_code: str) -> Artifact | None:
        """Pick the one validated text or subtitle document the place of this group reads."""
        selected_id: str | None = self.intent.selected_subtitle_artifact_id
        if selected_id is not None:
            selected: Artifact | None = self.artifacts.get(selected_id)
            if selected is None or selected.kind not in _DOCUMENT_SOURCE_KINDS:
                self._problem("subtitle_selection_invalid", "Selected translation source is unavailable or invalid")
                return None
            if selected.state is not ArtifactState.READY:
                self._problem(
                    "subtitle_selection_invalid",
                    "Selected translation source is unavailable or invalid",
                    artifacts=(selected,),
                )
                return None
            return selected
        candidates: tuple[Artifact, ...] = tuple(
            artifact
            for artifact in self.artifacts.values()
            if artifact.kind in _DOCUMENT_SOURCE_KINDS
            and artifact.state is ArtifactState.READY
            and artifact.lifetime is ArtifactLifetime.SOURCE
        )
        if not candidates:
            self._problem(missing_code, "A validated text or subtitle source is required")
            return None
        if len(candidates) > 1:
            self._problem(
                ambiguous_code,
                "Choose which text or subtitle document this run reads",
                artifacts=tuple(sorted(candidates, key=lambda artifact: artifact.artifact_id)),
            )
            return None
        return candidates[0]

    def _translate_subtitle_document(self, source: Artifact, requested: frozenset[ProductKind]) -> None:
        if ProductKind.TRANSLATED_TEXT in requested:
            self._problem(
                "translated_text_unsupported",
                "A subtitle source keeps its own format instead of becoming a plain text document",
                artifacts=(source,),
            )
            return
        self._full_pl = self._ready_product(ArtifactKind.FULL_PL)
        self._subtitle_input = source
        full: Artifact | None = self._ensure_full_pl()
        if full is not None:
            self._publish_subtitle(full, ArtifactKind.FULL_PL)

    def _translate_text_document(self, source: Artifact) -> None:
        if self._ready_product(ArtifactKind.TRANSLATED_TEXT) is not None:
            return
        translated: Artifact = self._intermediate(ArtifactKind.TRANSLATED_TEXT, "txt-text", language="pol")
        self._add_task(
            TaskKind.TRANSLATE_SUBTITLES,
            requires=(source,),
            produces=(translated,),
            variant="txt-text",
            resource_key=_translation_resource_key(self.settings),
            parameters=(("source_kind", "txt"), ("output_format", "txt")),
            is_network=self.settings.translation_is_network,
            is_paid=self.settings.translation_is_paid,
        )
        self._publish_text(translated)

    def _translate_text_to_draft_subtitles(self, source: Artifact) -> None:
        if self._ready_product(ArtifactKind.FULL_PL) is not None:
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
        self._draft_timings(translated)
        self._publish_subtitle(translated, ArtifactKind.FULL_PL)

    def _draft_timings(self, artifact: Artifact) -> None:
        self._problem(
            "draft_subtitle_timings",
            "Subtitles built from plain text are a narration script with estimated timings",
            artifacts=(artifact,),
            is_blocking=False,
        )

    def _publish_text(self, source: Artifact) -> Artifact | None:
        destination: Path = product_path(
            self.group.source.directory,
            self.group.source.stem,
            ArtifactKind.TRANSLATED_TEXT,
        )
        collision: Artifact | None = next(
            (
                artifact
                for artifact in self.group.artifacts
                if artifact.lifetime is ArtifactLifetime.SOURCE
                and artifact.path is not None
                and _same_path(artifact.path, destination)
            ),
            None,
        )
        if collision is not None:
            self._problem(
                "text_source_path_collision",
                "A translated document cannot replace the source text it was read from",
                artifacts=(collision,),
            )
            return None
        target: Artifact = self._durable_target(ArtifactKind.TRANSLATED_TEXT, destination, language="pol")
        self._add_publish(source, target)
        return target

    def _build_media_plan(self) -> None:
        products: ProductIntent = self.intent.products
        requested: frozenset[ProductKind] = products.requested_products
        compose_mkv: bool = ProductKind.MKV in requested and self._ready_product(ArtifactKind.FINAL_MKV) is None
        compose_mp4: bool = ProductKind.MP4 in requested and self._ready_product(ArtifactKind.FINAL_MP4) is None
        mkv_tracks: frozenset[MkvTrackProduct] = products.mkv_tracks if compose_mkv else frozenset()
        burn: BurnSubtitleProduct = products.burn_subtitle_product if compose_mp4 else BurnSubtitleProduct.NONE
        needs_narration: bool = (
            ProductKind.NARRATION_AUDIO in requested
            or MkvTrackProduct.NARRATION_AUDIO in mkv_tracks
            or (compose_mp4 and _mp4_uses_narration(products))
        )
        self._full_pl = self._ready_product(ArtifactKind.FULL_PL)
        self._spoken_pl = self._ready_product(ArtifactKind.SPOKEN_PL)
        self._displayed_pl = self._ready_product(ArtifactKind.DISPLAYED_PL)
        if needs_narration:
            self._narration = self._ready_product(ArtifactKind.NARRATION_AUDIO)
        self._adopt_manual_narration()
        needs_generated_narration: bool = needs_narration and self._narration is None
        needs_spoken: bool = ProductKind.SPOKEN_PL in requested or needs_generated_narration
        needs_displayed: bool = (
            ProductKind.DISPLAYED_PL in requested
            or burn is BurnSubtitleProduct.DISPLAYED_PL
            or MkvTrackProduct.DISPLAYED_PL_SUBTITLES in mkv_tracks
        )
        needs_full: bool = (
            ProductKind.FULL_PL in requested
            or burn is BurnSubtitleProduct.FULL_PL
            or MkvTrackProduct.FULL_PL_SUBTITLES in mkv_tracks
        )
        needs_source: bool = (
            ProductKind.SOURCE_SUBTITLES in requested
            or burn is BurnSubtitleProduct.SOURCE
            or MkvTrackProduct.SOURCE_SUBTITLES in mkv_tracks
        )
        needs_fresh_full: bool = self._full_pl is None and (
            needs_full or (needs_spoken and self._spoken_pl is None) or (needs_displayed and self._displayed_pl is None)
        )

        if needs_source or needs_fresh_full:
            self._select_subtitle_input()
        self._prepare_bulk_extraction(needs_generated_narration=needs_generated_narration)
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
            self._publish_subtitle(self._full_pl, ArtifactKind.FULL_PL)
        if ProductKind.SPOKEN_PL in requested and self._spoken_pl is not None:
            self._publish_subtitle(self._spoken_pl, ArtifactKind.SPOKEN_PL)
        if ProductKind.DISPLAYED_PL in requested and self._displayed_pl is not None:
            self._publish_subtitle(self._displayed_pl, ArtifactKind.DISPLAYED_PL)
        if ProductKind.NARRATION_AUDIO in requested and self._narration is not None:
            self._publish_audio(self._narration)

        if compose_mkv:
            self._compose_mkv()
        if compose_mp4:
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
            demote: bool = kind == "subtitles"
            priorities: tuple[str, ...] = (
                self.settings.subtitle_language_priority if demote else self.settings.audio_language_priority
            )
            selected = min(
                candidates,
                key=lambda track: _track_rank(track, priorities, demote_non_dialogue=demote),
                default=None,
            )
            if selected is None:
                return None
            if demote and all(_is_non_dialogue(track) for track in candidates):
                self._problem(
                    "subtitle_dialogue_missing",
                    "Only signs, songs, or forced subtitle tracks are embedded, so the narration follows them",
                    is_blocking=False,
                )
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
            if ProductKind.SOURCE_SUBTITLES in self._rebuild and selected.lifetime is ArtifactLifetime.SOURCE:
                self._problem(
                    "source_product_not_rebuildable",
                    "Source subtitle files cannot be replaced by a generated product",
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

    def _prepare_bulk_extraction(self, *, needs_generated_narration: bool) -> None:
        selected: Artifact | _EmbeddedTrack | None = self._subtitle_input
        if (
            not needs_generated_narration
            or not isinstance(selected, _EmbeddedTrack)
            or selected.subtitle_format is None
            or selected.video.kind is not ArtifactKind.VIDEO_MKV
        ):
            return
        audio: _EmbeddedTrack | None = self._select_embedded_track("audio")
        if audio is None or audio.video.artifact_id != selected.video.artifact_id:
            return
        subtitles: Artifact = self._intermediate(
            ArtifactKind.SOURCE_SUBTITLES,
            f"embedded-{selected.video.artifact_id}-{selected.track_id}",
            subtitle_format=selected.subtitle_format,
            language=self._source_language(selected.language),
        )
        source_audio: Artifact = self._intermediate(
            ArtifactKind.SOURCE_AUDIO,
            f"embedded-{audio.video.artifact_id}-{audio.track_id}",
            audio_codec=audio.codec_id,
        )
        self._add_task(
            TaskKind.EXTRACT_TRACKS,
            requires=(selected.video,),
            produces=(source_audio, subtitles),
            variant=f"tracks-{audio.track_id}-{selected.track_id}",
            resource_key="extraction",
            parameters=(
                ("audio_codec", audio.codec_id),
                ("audio_track_id", audio.track_id),
                ("subtitle_format", selected.subtitle_format),
                ("subtitle_track_id", selected.track_id),
            ),
        )
        self._source_audio = source_audio
        self._source_subtitles = subtitles

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
        needs_spoken = needs_spoken and self._spoken_pl is None
        needs_displayed = needs_displayed and self._displayed_pl is None
        if not needs_spoken and not needs_displayed:
            return
        selected: Artifact | _EmbeddedTrack | None = (
            self._full_pl or self._subtitle_input or self._select_subtitle_input()
        )
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
        timeline: NarrationTimeline = NarrationTimeline.SOURCE_TIMES
        manifest: Artifact = self._synthesize_speech(spoken, timeline)
        profile: str = self.settings.audio_output_profile.casefold()
        narration: Artifact = self._intermediate(
            ArtifactKind.NARRATION_AUDIO,
            f"narration-mix-{timeline.value}",
            audio_codec=profile,
        )
        self._add_task(
            TaskKind.MIX_NARRATION,
            requires=(source_audio, manifest),
            produces=(narration,),
            variant=f"narration-{timeline.value}",
            resource_key=f"audio:{self.settings.audio_profile_id}",
            parameters=(("mix_source", "video"), ("output_profile", profile)),
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
        if self._source_audio is not None:
            return self._source_audio
        if self.intent.mode is RunMode.MANUAL and self.intent.selected_audio_artifact_id is not None:
            selected: Artifact | None = self.artifacts.get(self.intent.selected_audio_artifact_id)
            if selected is not None and (
                selected.kind is ArtifactKind.SOURCE_AUDIO
                or self.intent.external_audio_role is ExternalAudioRole.SOURCE_AUDIO
            ):
                self._source_audio = selected
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
        self._source_audio = source_audio
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

    def _publish_subtitle(self, source: Artifact, kind: ArtifactKind) -> Artifact:
        subtitle_format: str = self._subtitle_format(source)
        destination: Path = product_path(
            self.group.source.directory,
            self.group.source.stem,
            kind,
            subtitle_format=subtitle_format,
        )
        if source.state is ArtifactState.READY and source.path is not None and _same_path(source.path, destination):
            return source
        target: Artifact = self._durable_target(
            kind,
            destination,
            subtitle_format=subtitle_format,
            language="pol",
        )
        self._add_publish(source, target)
        return target

    def _publish_audio(self, source: Artifact) -> Artifact:
        profile: str = self.settings.audio_output_profile.casefold()
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
        destination: Path = product_path(
            self.group.source.directory,
            self.group.source.stem,
            ArtifactKind.NARRATION_AUDIO,
            audio_profile=profile,
        )
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
            product_path(self.group.source.directory, self.group.source.stem, ArtifactKind.FINAL_MKV),
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
            product_path(self.group.source.directory, self.group.source.stem, ArtifactKind.FINAL_MP4),
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

    def _ready_product(self, kind: ArtifactKind) -> Artifact | None:
        if self.intent.mode is not RunMode.AUTO or kind in self._invalidated:
            return None
        candidates: tuple[Artifact, ...] = tuple(
            artifact
            for artifact in self.group.artifacts
            if artifact.kind is kind
            and artifact.state is ArtifactState.READY
            and artifact.lifetime is ArtifactLifetime.DURABLE
            and (artifact.subtitle_format is None or self._requested_format_matches(artifact))
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
        artifact_id: str = create_artifact_id(
            self.group.group_id, kind, Path(destination.name), variant="durable-output"
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


def _is_non_dialogue(track: _MediaTrackView) -> bool:
    if track.is_forced:
        return True
    return track.name is not None and _NON_DIALOGUE_SUBTITLE_NAME.search(track.name) is not None


def _track_rank(
    track: _MediaTrackView,
    priorities: tuple[str, ...],
    *,
    demote_non_dialogue: bool,
) -> tuple[int, int, int, int, int]:
    normalized_priorities: tuple[str, ...] = tuple(language.casefold() for language in priorities)
    language: str | None = track.language.casefold() if track.language is not None else None
    try:
        priority: int = normalized_priorities.index(language) if language is not None else len(normalized_priorities)
        preferred: int = 0 if language in normalized_priorities else 1
    except ValueError:
        priority = len(normalized_priorities)
        preferred = 1
    non_dialogue: int = 1 if demote_non_dialogue and _is_non_dialogue(track) else 0
    return non_dialogue, preferred, priority, 0 if track.is_default else 1, track.track_id


def _mp4_uses_narration(products: ProductIntent) -> bool:
    return products.mp4_audio_source is Mp4AudioSource.NARRATION or (
        products.mp4_audio_source is Mp4AudioSource.AUTO
        and (
            ProductKind.NARRATION_AUDIO in products.requested_products
            or MkvTrackProduct.NARRATION_AUDIO in products.mkv_tracks
        )
    )


def _invalidated_products(intent: GroupIntent, rebuild: frozenset[ProductKind]) -> frozenset[ArtifactKind]:
    if not rebuild:
        return frozenset()
    invalidated: set[ProductKind] = set(rebuild)
    if ProductKind.SOURCE_SUBTITLES in invalidated:
        invalidated.add(ProductKind.FULL_PL)
    if ProductKind.FULL_PL in invalidated:
        invalidated.update({ProductKind.SPOKEN_PL, ProductKind.DISPLAYED_PL})
    if ProductKind.SPOKEN_PL in invalidated:
        invalidated.add(ProductKind.NARRATION_AUDIO)
    products: ProductIntent = intent.products
    track_products: dict[MkvTrackProduct, ProductKind] = {
        MkvTrackProduct.SOURCE_SUBTITLES: ProductKind.SOURCE_SUBTITLES,
        MkvTrackProduct.FULL_PL_SUBTITLES: ProductKind.FULL_PL,
        MkvTrackProduct.DISPLAYED_PL_SUBTITLES: ProductKind.DISPLAYED_PL,
        MkvTrackProduct.NARRATION_AUDIO: ProductKind.NARRATION_AUDIO,
    }
    if any(track_products[track] in invalidated for track in products.mkv_tracks):
        invalidated.add(ProductKind.MKV)
    burn: BurnSubtitleProduct = products.burn_subtitle_product
    burned_product: ProductKind | None = {
        BurnSubtitleProduct.NONE: None,
        BurnSubtitleProduct.SOURCE: ProductKind.SOURCE_SUBTITLES,
        BurnSubtitleProduct.FULL_PL: ProductKind.FULL_PL,
        BurnSubtitleProduct.DISPLAYED_PL: ProductKind.DISPLAYED_PL,
    }[burn]
    if burned_product in invalidated or (ProductKind.NARRATION_AUDIO in invalidated and _mp4_uses_narration(products)):
        invalidated.add(ProductKind.MP4)
    return frozenset(
        ArtifactKind(f"final_{product.value}" if product in {ProductKind.MKV, ProductKind.MP4} else product.value)
        for product in invalidated
    )


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
