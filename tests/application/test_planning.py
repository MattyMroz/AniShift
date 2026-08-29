from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.intents import GroupIntent, ProductIntent, ProductKind, RunMode
from anishift.application.planning import (
    ExecutionPlan,
    GroupPlan,
    PlanProblem,
    PlanTask,
    ProcessingOrderPolicy,
    RunSettingsSnapshot,
    TaskKind,
    stable_topological_order,
)
from anishift.errors import PlanningError


def _settings() -> RunSettingsSnapshot:
    return RunSettingsSnapshot(
        translation_profile_id="google",
        translation_fallback_chain=("deepl",),
        translation_max_retries=3,
        translation_concurrency=4,
        llm_profile_id="gemini",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=3,
        tts_group_jobs=2,
        audio_profile_id="eac3",
        composition_profile_id="default",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
    )


def _intent() -> GroupIntent:
    return GroupIntent(
        group_id="episode",
        mode=RunMode.AUTO,
        products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
    )


def _artifact(artifact_id: str, *, ready: bool) -> Artifact:
    if not ready:
        return Artifact(
            artifact_id=artifact_id,
            group_id="episode",
            kind=ArtifactKind.FULL_PL,
            path=None,
            state=ArtifactState.MISSING,
            lifetime=ArtifactLifetime.INTERMEDIATE,
        )
    path = Path(f"workspace/{artifact_id}")
    return Artifact(
        artifact_id=artifact_id,
        group_id="episode",
        kind=ArtifactKind.SOURCE_SUBTITLES,
        path=path,
        state=ArtifactState.READY,
        lifetime=ArtifactLifetime.SOURCE,
        planned_destination=path,
    )


def _artifacts(
    *artifact_ids: str,
    ready_ids: frozenset[str] = frozenset({"source", "video"}),
) -> tuple[Artifact, ...]:
    return tuple(_artifact(artifact_id, ready=artifact_id in ready_ids) for artifact_id in artifact_ids)


def _task(
    task_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    requires: tuple[str, ...] = ("source",),
    produces: tuple[str, ...] = ("result",),
) -> PlanTask:
    return PlanTask(
        task_id=task_id,
        group_id="episode",
        kind=TaskKind.TRANSLATE_SUBTITLES,
        requires=requires,
        produces=produces,
        depends_on=depends_on,
        resource_key="translation:google",
        parameters=(("output_format", "srt"),),
        is_network=True,
    )


def test_topological_order_is_stable_for_shuffled_input() -> None:
    extract = _task("extract", requires=("video",), produces=("source",))
    translate = _task("translate", depends_on=("extract",))
    assert stable_topological_order((translate, extract)) == (extract, translate)
    assert stable_topological_order((extract, translate)) == (extract, translate)


def test_topological_order_preserves_input_order_for_independent_tasks() -> None:
    episode_2 = _task("episode-2", produces=("episode-2-result",))
    episode_10 = _task("episode-10", produces=("episode-10-result",))

    assert stable_topological_order((episode_2, episode_10)) == (episode_2, episode_10)


def test_topological_order_rejects_cycle() -> None:
    first = _task("first", depends_on=("second",), produces=("first-output",))
    second = _task("second", depends_on=("first",), produces=("second-output",))
    with pytest.raises(PlanningError, match="cycle"):
        stable_topological_order((first, second))


def test_topological_order_rejects_missing_dependency() -> None:
    task = _task("translate", depends_on=("missing",))
    with pytest.raises(PlanningError, match="unknown task"):
        stable_topological_order((task,))


def test_execution_plan_exposes_blocking_problems_without_exception() -> None:
    task = _task("translate")
    problem = PlanProblem("language_unknown", "Source language is required", "episode")
    group = GroupPlan("episode", _intent(), ("source", "result"), (task.task_id,), (problem,))
    plan = ExecutionPlan((group,), _artifacts("source", "result"), (task,), _settings(), (problem,))
    assert plan.can_execute is False
    assert plan.problems == (problem,)


def test_execution_plan_requires_stable_task_order() -> None:
    extract = _task("extract", requires=("video",), produces=("source",))
    translate = _task("translate", depends_on=("extract",))
    group = GroupPlan(
        "episode",
        _intent(),
        ("video", "source", "result"),
        ("extract", "translate"),
    )
    with pytest.raises(PlanningError, match="topological order"):
        ExecutionPlan(
            (group,),
            _artifacts("video", "source", "result", ready_ids=frozenset({"video"})),
            (translate, extract),
            _settings(),
            (),
        )


def test_execution_plan_requires_artifact_producer_dependency() -> None:
    extract = _task("extract", requires=("video",), produces=("source",))
    translate = _task("translate")
    group = GroupPlan(
        "episode",
        _intent(),
        ("video", "source", "result"),
        ("extract", "translate"),
    )
    with pytest.raises(PlanningError, match="missing dependency"):
        ExecutionPlan(
            (group,),
            _artifacts("video", "source", "result", ready_ids=frozenset({"video"})),
            (extract, translate),
            _settings(),
            (),
        )


def test_execution_plan_requires_group_problems_in_plan_summary() -> None:
    task = _task("translate")
    problem = PlanProblem("language_unknown", "Source language is required", "episode")
    group = GroupPlan("episode", _intent(), ("source", "result"), (task.task_id,), (problem,))
    with pytest.raises(PlanningError, match="Group problems"):
        ExecutionPlan((group,), _artifacts("source", "result"), (task,), _settings(), ())


def test_plan_models_are_frozen() -> None:
    task = _task("translate")
    with pytest.raises(FrozenInstanceError):
        task.task_id = "changed"  # type: ignore[misc]


def test_plan_task_rejects_missing_or_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="parameters"):
        replace(_task("translate"), parameters=())
    with pytest.raises(ValueError, match="parameters"):
        replace(_task("translate"), parameters=(("output_format", "srt"), ("typo", True)))


def test_settings_snapshot_validates_runtime_limits() -> None:
    settings = _settings()
    with pytest.raises(ValueError, match="must be between"):
        replace(settings, translation_concurrency=17)
    with pytest.raises(ValueError, match="must be between"):
        replace(settings, llm_max_concurrency=5)
    with pytest.raises(ValueError, match="must be between"):
        replace(settings, tts_max_retries=-1)
    with pytest.raises(ValueError, match="profile is unsupported"):
        replace(settings, audio_output_profile="m4a")


def test_execution_plan_rejects_ready_task_output() -> None:
    task = _task("translate")
    group = GroupPlan("episode", _intent(), ("source", "result"), (task.task_id,))
    artifacts = (_artifact("source", ready=True), _artifact("result", ready=True))
    with pytest.raises(PlanningError, match="output must be missing"):
        ExecutionPlan((group,), artifacts, (task,), _settings(), ())


def test_execution_plan_rejects_source_task_output() -> None:
    task = _task("translate")
    group = GroupPlan("episode", _intent(), ("source", "result"), (task.task_id,))
    source = _artifact("source", ready=True)
    path = Path("workspace/result")
    output = Artifact(
        "result",
        "episode",
        ArtifactKind.SOURCE_SUBTITLES,
        path,
        ArtifactState.MISSING,
        ArtifactLifetime.SOURCE,
        path,
    )
    with pytest.raises(PlanningError, match="cannot produce a source"):
        ExecutionPlan((group,), (source, output), (task,), _settings(), ())


def test_execution_plan_rejects_missing_artifact_without_producer() -> None:
    artifact = _artifact("orphan", ready=False)
    group = GroupPlan("episode", _intent(), (artifact.artifact_id,), ())
    with pytest.raises(PlanningError, match="without producers"):
        ExecutionPlan((group,), (artifact,), (), _settings(), ())


def test_execution_plan_rejects_problem_with_unknown_artifact() -> None:
    source = _artifact("source", ready=True)
    problem = PlanProblem("invalid", "Invalid selection", "episode", ("unknown",))
    group = GroupPlan("episode", _intent(), (source.artifact_id,), (), (problem,))
    with pytest.raises(PlanningError, match="references an invalid artifact"):
        ExecutionPlan((group,), (source,), (), _settings(), (problem,))
