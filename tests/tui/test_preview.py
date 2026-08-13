from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, Static
from tui_fakes import app_service

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
)
from anishift.tui.app import AniShiftApp
from anishift.tui.screens.preview import StartConfirmationScreen


def _plan(*, blocked: bool) -> ExecutionPlan:
    source_path = Path("workspace/Episode.srt")
    source = Artifact(
        "source",
        "episode",
        ArtifactKind.SOURCE_SUBTITLES,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        source_path,
    )
    output_path = Path("workspace/Episode.pl.srt")
    output = Artifact(
        "output",
        "episode",
        ArtifactKind.FULL_PL,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.DURABLE,
        output_path,
    )
    intent = GroupIntent("episode", RunMode.AUTO, ProductIntent(frozenset({ProductKind.FULL_PL})))
    problem = PlanProblem("blocked", "Manual decision required", "episode")
    tasks: tuple[PlanTask, ...] = ()
    artifacts: tuple[Artifact, ...] = (source,)
    task_ids: tuple[str, ...] = ()
    problems: tuple[PlanProblem, ...] = (problem,) if blocked else ()
    if not blocked:
        task = PlanTask(
            "translate",
            "episode",
            TaskKind.TRANSLATE_SUBTITLES,
            ("source",),
            ("output",),
            (),
            "translation:google",
            (("output_format", "srt"),),
            True,
            True,
        )
        tasks = (task,)
        artifacts = (source, output)
        task_ids = (task.task_id,)
    group = GroupPlan("episode", intent, tuple(artifact.artifact_id for artifact in artifacts), task_ids, problems)
    settings = RunSettingsSnapshot(
        "google",
        ("deepl",),
        2,
        4,
        "gemini",
        1,
        "edge",
        2,
        4,
        "eac3",
        "balanced",
        ProcessingOrderPolicy.READY_FIRST,
    )
    return ExecutionPlan((group,), artifacts, tasks, settings, problems)


async def _assert_preview_information_and_start_gate() -> None:
    app = AniShiftApp(app_service())
    app.session.preview_plan = _plan(blocked=False)
    async with app.run_test(size=(120, 36)):
        await app.open_route("preview")
        assert "translation:google" in str(app.screen.query_one("#plan-operations", Static).render())
        assert "Episode.pl.srt" in str(app.screen.query_one("#plan-products", Static).render())
        assert "Network tasks: 1 | Paid tasks: 1" in str(app.screen.query_one("#plan-cost", Static).render())
        assert app.screen.query_one("#preview-start", Button).disabled is False


def test_preview_shows_operations_products_and_cost_flags() -> None:
    asyncio.run(_assert_preview_information_and_start_gate())


async def _assert_blocking_problem_disables_start() -> None:
    app = AniShiftApp(app_service())
    app.session.preview_plan = _plan(blocked=True)
    async with app.run_test(size=(120, 36)):
        await app.open_route("preview")
        assert "Manual decision required" in str(app.screen.query_one("#plan-problems", Static).render())
        assert app.screen.query_one("#preview-start", Button).disabled is True


def test_preview_disables_start_for_blocking_problem() -> None:
    asyncio.run(_assert_blocking_problem_disables_start())


async def _assert_paid_plan_requires_confirmation() -> None:
    app = AniShiftApp(app_service())
    app.session.preview_plan = _plan(blocked=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("preview")
        app.screen.query_one("#preview-start", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, StartConfirmationScreen)
        assert app.session.run_state == "idle"
        app.screen.query_one("#cancel-start", Button).press()
        await pilot.pause()
        assert app.session.run_state == "idle"


def test_preview_requires_confirmation_before_paid_execution() -> None:
    asyncio.run(_assert_paid_plan_requires_confirmation())
