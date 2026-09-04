"""Immutable execution-plan contracts and deterministic graph ordering."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from anishift.application.artifacts import Artifact, ArtifactLifetime, ArtifactState
from anishift.application.intents import GroupIntent
from anishift.errors import PlanningError

# ── Constants ────────────────────────────────────────────────────────────────

_MAX_LLM_TEMPERATURE: Final[float] = 2.0
"""Maximum provider-neutral LLM sampling temperature."""

DEFAULT_AUDIO_TOLERANCE_US: Final[int] = 1_000_000
"""Accepted duration difference between supplied audio and the selected video."""


class TaskKind(StrEnum):
    """Operations that can appear in an AniShift execution graph."""

    EXTRACT_AUDIO = "extract_audio"
    EXTRACT_SUBTITLES = "extract_subtitles"
    EXTRACT_TRACKS = "extract_tracks"
    NORMALIZE_SUBTITLES = "normalize_subtitles"
    TRANSLATE_SUBTITLES = "translate_subtitles"
    SPLIT_SUBTITLES = "split_subtitles"
    SYNTHESIZE_SPEECH = "synthesize_speech"
    TRANSCODE_AUDIO = "transcode_audio"
    MIX_NARRATION = "mix_narration"
    COMPOSE_MKV = "compose_mkv"
    COMPOSE_MP4 = "compose_mp4"
    PUBLISH_ARTIFACT = "publish_artifact"


class TaskState(StrEnum):
    """Lifecycle state of one planned task."""

    BLOCKED = "blocked"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingOrderPolicy(StrEnum):
    """Ordering policy for forwarding and publishing completed group work."""

    READY_FIRST = "ready_first"
    STRICT_NATURAL = "strict_natural"


@dataclass(frozen=True, slots=True)
class PlanTask:
    """One deterministic task node referencing artifacts by stable IDs."""

    task_id: str
    group_id: str
    kind: TaskKind
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    depends_on: tuple[str, ...]
    resource_key: str
    parameters: tuple[tuple[str, str | int | bool], ...] = ()
    is_network: bool = False
    is_paid: bool = False

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.group_id.strip() or not self.resource_key.strip():
            msg = "Task ID, group ID, and resource key cannot be empty"
            raise ValueError(msg)
        _require_unique(self.requires, "required artifact IDs")
        _require_unique(self.produces, "produced artifact IDs")
        _require_unique(self.depends_on, "dependency task IDs")
        parameter_names: tuple[str, ...] = tuple(name for name, _ in self.parameters)
        _require_unique(parameter_names, "task parameter names")
        _validate_task_parameter_names(self.kind, frozenset(parameter_names))
        if not self.produces:
            msg = "A plan task must produce at least one artifact"
            raise ValueError(msg)
        if set(self.requires) & set(self.produces):
            msg = "A task cannot require and produce the same artifact"
            raise ValueError(msg)
        if self.task_id in self.depends_on:
            msg = "A task cannot depend on itself"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PlanProblem:
    """Expected warning or blocking problem surfaced in plan preview."""

    code: str
    message: str
    group_id: str | None = None
    artifact_ids: tuple[str, ...] = ()
    is_blocking: bool = True

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            msg = "Plan problem code and message cannot be empty"
            raise ValueError(msg)
        _require_unique(self.artifact_ids, "problem artifact IDs")


@dataclass(frozen=True, slots=True)
class GroupPlan:
    """Plan summary and task references for one source group."""

    group_id: str
    intent: GroupIntent
    artifact_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    problems: tuple[PlanProblem, ...] = ()

    def __post_init__(self) -> None:
        if not self.group_id.strip() or self.intent.group_id != self.group_id:
            msg = "Group plan and intent must have the same non-empty group ID"
            raise ValueError(msg)
        _require_unique(self.artifact_ids, "group artifact IDs")
        _require_unique(self.task_ids, "group task IDs")
        if any(problem.group_id not in {None, self.group_id} for problem in self.problems):
            msg = "Group plan problem belongs to another group"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RunSettingsSnapshot:
    """Validated non-secret settings consumed by planning and scheduling."""

    translation_profile_id: str
    translation_max_retries: int
    translation_concurrency: int
    llm_profile_id: str
    llm_max_concurrency: int
    tts_profile_id: str
    tts_max_retries: int
    tts_group_jobs: int
    audio_profile_id: str
    composition_profile_id: str
    processing_order_policy: ProcessingOrderPolicy
    tts_request_concurrency: int = 1
    audio_output_profile: str = "eac3"
    audio_duration_tolerance_us: int = DEFAULT_AUDIO_TOLERANCE_US
    subtitle_language_priority: tuple[str, ...] = ("eng",)
    audio_language_priority: tuple[str, ...] = ("jpn",)
    translation_is_network: bool = True
    translation_is_paid: bool = True
    llm_is_network: bool = True
    llm_is_paid: bool = True
    tts_is_network: bool = True
    tts_is_paid: bool = True
    subtitle_max_chars_per_line: int = 42
    subtitle_max_lines_per_event: int = 2
    translation_chunk_chars: int = 750
    translation_batch_size: int = 0
    llm_model_id: str = "default"
    llm_temperature: float | None = None
    llm_top_p: float | None = None
    llm_max_output_tokens: int | None = None
    llm_translation_style: str = "neutral"
    tts_model_id: str = "default"
    tts_voice_id: str = "default"
    tts_voice_label: str = "default"
    tts_native_rate: str | float | None = None
    tts_native_volume: str | float | None = None
    tts_native_pitch: str | float | None = None
    tts_engine_options: tuple[tuple[str, str | int | float | bool | None], ...] = ()
    tts_vpn_enabled: bool = True
    tts_postprocess_tempo: float = 1.0
    audio_bitrate: str | None = None
    narrator_mix_base_gain_db: float = 7.0
    voice_mix_offset_db: float = 0.0
    original_gain_db: float = 0.0
    tts_timeline_policy: str = "serialize"

    def __post_init__(self) -> None:
        _validate_profile_settings(self)
        _validate_runtime_settings(self)
        _require_unique(self.subtitle_language_priority, "subtitle language priorities")
        _require_unique(self.audio_language_priority, "audio language priorities")


def _validate_profile_settings(settings: RunSettingsSnapshot) -> None:
    profile_ids: tuple[str, ...] = (
        settings.translation_profile_id,
        settings.llm_profile_id,
        settings.tts_profile_id,
        settings.audio_profile_id,
        settings.composition_profile_id,
    )
    if any(not profile_id.strip() for profile_id in profile_ids):
        msg = "Run setting profile IDs cannot be empty"
        raise ValueError(msg)
    _require_range(settings.translation_max_retries, 0, 10, "translation retries")
    _require_range(settings.translation_concurrency, 1, 16, "translation concurrency")
    _require_range(settings.llm_max_concurrency, 1, 16, "LLM concurrency")
    _require_range(settings.tts_max_retries, 0, 10, "TTS retries")
    _require_range(settings.tts_group_jobs, 1, 100, "TTS group jobs")
    _require_range(settings.tts_request_concurrency, 1, 100, "TTS request concurrency")
    supported_audio_profiles: frozenset[str] = frozenset({"aac", "eac3", "mp3", "opus", "flac", "wav"})
    if settings.audio_output_profile.casefold() not in supported_audio_profiles:
        msg = "Audio output profile is unsupported"
        raise ValueError(msg)
    if settings.audio_duration_tolerance_us < 0:
        msg = "Audio duration tolerance cannot be negative"
        raise ValueError(msg)
    _require_range(settings.subtitle_max_chars_per_line, 20, 120, "subtitle line length")
    _require_range(settings.subtitle_max_lines_per_event, 1, 4, "subtitle line count")
    _require_range(settings.translation_chunk_chars, 200, 4000, "translation chunk size")
    if settings.translation_batch_size < 0:
        msg = "Translation batch size cannot be negative"
        raise ValueError(msg)


def _validate_runtime_settings(settings: RunSettingsSnapshot) -> None:
    runtime_ids: tuple[str, ...] = (
        settings.llm_model_id,
        settings.llm_translation_style,
        settings.tts_model_id,
        settings.tts_voice_id,
        settings.tts_voice_label,
    )
    if any(not value.strip() for value in runtime_ids):
        msg = "Run setting runtime IDs cannot be empty"
        raise ValueError(msg)
    option_names: tuple[str, ...] = tuple(name for name, _ in settings.tts_engine_options)
    _require_unique(option_names, "TTS engine option names")
    if settings.llm_temperature is not None and not 0 <= settings.llm_temperature <= _MAX_LLM_TEMPERATURE:
        msg = "LLM temperature must be between 0 and 2"
        raise ValueError(msg)
    if settings.llm_top_p is not None and not 0 <= settings.llm_top_p <= 1:
        msg = "LLM top-p must be between 0 and 1"
        raise ValueError(msg)
    if settings.llm_max_output_tokens is not None and settings.llm_max_output_tokens <= 0:
        msg = "LLM max output tokens must be positive"
        raise ValueError(msg)
    if not math.isfinite(settings.tts_postprocess_tempo) or settings.tts_postprocess_tempo <= 0:
        msg = "TTS post-process tempo must be finite and positive"
        raise ValueError(msg)
    gains: tuple[float, ...] = (
        settings.narrator_mix_base_gain_db,
        settings.voice_mix_offset_db,
        settings.original_gain_db,
    )
    if any(not math.isfinite(value) for value in gains):
        msg = "Audio gains must be finite"
        raise ValueError(msg)
    if settings.audio_bitrate is not None and not settings.audio_bitrate.strip():
        msg = "Audio bitrate cannot be blank"
        raise ValueError(msg)
    if settings.tts_timeline_policy != "serialize":
        msg = "TTS timeline policy is unsupported"
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Complete immutable plan in stable topological task order."""

    groups: tuple[GroupPlan, ...]
    artifacts: tuple[Artifact, ...]
    tasks: tuple[PlanTask, ...]
    settings: RunSettingsSnapshot
    problems: tuple[PlanProblem, ...]

    def __post_init__(self) -> None:
        group_ids: tuple[str, ...] = tuple(group.group_id for group in self.groups)
        _require_unique(group_ids, "execution group IDs")
        artifact_ids: tuple[str, ...] = tuple(artifact.artifact_id for artifact in self.artifacts)
        _require_unique(artifact_ids, "execution artifact IDs")
        task_ids: tuple[str, ...] = tuple(task.task_id for task in self.tasks)
        _require_unique(task_ids, "execution task IDs")
        ordered_tasks: tuple[PlanTask, ...] = stable_topological_order(self.tasks)
        if ordered_tasks != self.tasks:
            msg = "Execution tasks must use stable topological order"
            raise PlanningError(msg)
        self._validate_group_references()

    @property
    def can_execute(self) -> bool:
        """Whether the plan contains no blocking problem."""
        return not any(problem.is_blocking for problem in self.problems)

    def _validate_group_references(self) -> None:
        artifact_by_id: dict[str, Artifact] = {artifact.artifact_id: artifact for artifact in self.artifacts}
        task_by_id: dict[str, PlanTask] = {task.task_id: task for task in self.tasks}
        producer_by_artifact: dict[str, str] = _index_artifact_producers(self.tasks)
        if not any(problem.is_blocking for problem in self.problems):
            orphaned: tuple[str, ...] = tuple(
                artifact.artifact_id
                for artifact in self.artifacts
                if artifact.state is ArtifactState.MISSING and artifact.artifact_id not in producer_by_artifact
            )
            if orphaned:
                msg = "Executable plan contains missing artifacts without producers"
                raise PlanningError(msg)
        _validate_task_dependencies(self.tasks, task_by_id, producer_by_artifact, artifact_by_id)
        referenced_task_ids: set[str] = _validate_group_declarations(
            self.groups,
            self.problems,
            task_by_id,
            artifact_by_id,
        )
        if referenced_task_ids != set(task_by_id):
            msg = "Every execution task must belong to exactly one group plan"
            raise PlanningError(msg)


def stable_topological_order(tasks: Sequence[PlanTask]) -> tuple[PlanTask, ...]:
    """Return an input-stable topological order or raise for an invalid graph."""
    task_by_id: dict[str, PlanTask] = {}
    order_by_id: dict[str, int] = {}
    for index, task in enumerate(tasks):
        if task.task_id in task_by_id:
            msg = f"Duplicate task ID: {task.task_id}"
            raise PlanningError(msg)
        task_by_id[task.task_id] = task
        order_by_id[task.task_id] = index

    indegree: dict[str, int] = dict.fromkeys(task_by_id, 0)
    dependants: dict[str, list[str]] = {task_id: [] for task_id in task_by_id}
    for task in task_by_id.values():
        for dependency_id in task.depends_on:
            if dependency_id not in task_by_id:
                msg = f"Task {task.task_id!r} depends on unknown task {dependency_id!r}"
                raise PlanningError(msg)
            indegree[task.task_id] += 1
            dependants[dependency_id].append(task.task_id)

    ready: list[str] = [task_id for task_id, degree in indegree.items() if degree == 0]
    ordered: list[PlanTask] = []
    while ready:
        task_id: str = ready.pop(0)
        ordered.append(task_by_id[task_id])
        for dependant_id in sorted(dependants[task_id], key=order_by_id.__getitem__):
            indegree[dependant_id] -= 1
            if indegree[dependant_id] == 0:
                ready.append(dependant_id)
        ready.sort(key=order_by_id.__getitem__)

    if len(ordered) != len(task_by_id):
        msg = "Execution plan contains a dependency cycle"
        raise PlanningError(msg)
    return tuple(ordered)


def _index_artifact_producers(tasks: tuple[PlanTask, ...]) -> dict[str, str]:
    producer_by_artifact: dict[str, str] = {}
    for task in tasks:
        for artifact_id in task.produces:
            if artifact_id in producer_by_artifact:
                msg = f"Artifact {artifact_id!r} has more than one producer"
                raise PlanningError(msg)
            producer_by_artifact[artifact_id] = task.task_id
    return producer_by_artifact


def _validate_task_dependencies(
    tasks: tuple[PlanTask, ...],
    task_by_id: dict[str, PlanTask],
    producer_by_artifact: dict[str, str],
    artifact_by_id: dict[str, Artifact],
) -> None:
    for task in tasks:
        if any(task_by_id[dependency_id].group_id != task.group_id for dependency_id in task.depends_on):
            msg = "Plan tasks cannot depend on a different source group"
            raise PlanningError(msg)
        for artifact_id in task.requires:
            artifact: Artifact | None = artifact_by_id.get(artifact_id)
            if artifact is None:
                msg = f"Task {task.task_id!r} requires unknown artifact {artifact_id!r}"
                raise PlanningError(msg)
            producer_id: str | None = producer_by_artifact.get(artifact_id)
            if producer_id is not None and producer_id not in task.depends_on:
                msg = f"Task {task.task_id!r} is missing dependency {producer_id!r}"
                raise PlanningError(msg)
            if producer_id is None and artifact.state is not ArtifactState.READY:
                msg = f"Task {task.task_id!r} requires an artifact that is not ready and has no producer"
                raise PlanningError(msg)
        for artifact_id in task.produces:
            artifact = artifact_by_id.get(artifact_id)
            if artifact is None:
                msg = f"Task {task.task_id!r} produces unknown artifact {artifact_id!r}"
                raise PlanningError(msg)
            if artifact.state is not ArtifactState.MISSING:
                msg = f"Task {task.task_id!r} output must be missing before execution"
                raise PlanningError(msg)
            if artifact.lifetime is ArtifactLifetime.SOURCE:
                msg = f"Task {task.task_id!r} cannot produce a source artifact"
                raise PlanningError(msg)


def _validate_group_declarations(
    groups: tuple[GroupPlan, ...],
    problems: tuple[PlanProblem, ...],
    task_by_id: dict[str, PlanTask],
    artifact_by_id: dict[str, Artifact],
) -> set[str]:
    referenced_task_ids: set[str] = set()
    for group in groups:
        declared_artifacts: tuple[Artifact, ...] = tuple(
            artifact_by_id[artifact_id] for artifact_id in group.artifact_ids if artifact_id in artifact_by_id
        )
        if len(declared_artifacts) != len(group.artifact_ids):
            msg = f"Group {group.group_id!r} references an unknown artifact"
            raise PlanningError(msg)
        if any(artifact.group_id != group.group_id for artifact in declared_artifacts):
            msg = f"Group {group.group_id!r} references another group's artifact"
            raise PlanningError(msg)
        if any(problem not in problems for problem in group.problems):
            msg = "Group problems must also be present in execution plan problems"
            raise PlanningError(msg)
        for problem in group.problems:
            for artifact_id in problem.artifact_ids:
                artifact: Artifact | None = artifact_by_id.get(artifact_id)
                if artifact is None or artifact.group_id != group.group_id:
                    msg = f"Problem {problem.code!r} references an invalid artifact"
                    raise PlanningError(msg)
        for task_id in group.task_ids:
            task: PlanTask | None = task_by_id.get(task_id)
            if task is None or task.group_id != group.group_id:
                msg = f"Group {group.group_id!r} references an invalid task {task_id!r}"
                raise PlanningError(msg)
            referenced_artifacts: set[str] = set(task.requires) | set(task.produces)
            if not referenced_artifacts.issubset(group.artifact_ids):
                msg = f"Group {group.group_id!r} does not declare every task artifact"
                raise PlanningError(msg)
            referenced_task_ids.add(task_id)
    declared_ids: set[str] = {artifact_id for group in groups for artifact_id in group.artifact_ids}
    if declared_ids != set(artifact_by_id):
        msg = "Every execution artifact must belong to exactly one group plan"
        raise PlanningError(msg)
    return referenced_task_ids


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if any(not value.strip() for value in values):
        msg = f"{label.capitalize()} cannot contain blank values"
        raise ValueError(msg)
    if len(values) != len(set(values)):
        msg = f"{label.capitalize()} must be unique"
        raise ValueError(msg)


def _require_range(value: int, minimum: int, maximum: int, label: str) -> None:
    if not minimum <= value <= maximum:
        msg = f"{label.capitalize()} must be between {minimum} and {maximum}"
        raise ValueError(msg)


def _validate_task_parameter_names(kind: TaskKind, names: frozenset[str]) -> None:
    contracts: dict[TaskKind, tuple[frozenset[str], frozenset[str]]] = {
        TaskKind.EXTRACT_AUDIO: (
            frozenset({"source_codec", "track_id", "target_format"}),
            frozenset({"source_codec", "track_id", "target_format"}),
        ),
        TaskKind.EXTRACT_SUBTITLES: (
            frozenset({"track_id", "target_format"}),
            frozenset({"track_id", "target_format"}),
        ),
        TaskKind.EXTRACT_TRACKS: (
            frozenset({"audio_codec", "audio_track_id", "subtitle_format", "subtitle_track_id"}),
            frozenset({"audio_codec", "audio_track_id", "subtitle_format", "subtitle_track_id"}),
        ),
        TaskKind.NORMALIZE_SUBTITLES: (frozenset({"output_format"}), frozenset({"output_format"})),
        TaskKind.TRANSLATE_SUBTITLES: (
            frozenset({"output_format"}),
            frozenset({"output_format", "source_kind"}),
        ),
        TaskKind.TRANSCODE_AUDIO: (frozenset({"output_profile"}), frozenset({"output_profile"})),
        TaskKind.MIX_NARRATION: (frozenset({"output_profile"}), frozenset({"output_profile"})),
        TaskKind.COMPOSE_MKV: (frozenset({"mkv_tracks"}), frozenset({"mkv_tracks"})),
        TaskKind.COMPOSE_MP4: (
            frozenset({"audio_source", "burn_subtitles"}),
            frozenset({"audio_source", "burn_subtitles"}),
        ),
    }
    required, allowed = contracts.get(kind, (frozenset(), frozenset()))
    if not required.issubset(names) or not names.issubset(allowed):
        msg = f"Task parameters do not match the {kind.value} contract"
        raise ValueError(msg)
