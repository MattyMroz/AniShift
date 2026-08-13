from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    SourceGroup,
)
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
from anishift.application.intents import AutoPreset, ProductIntent, ProductKind
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.service import AppService, EngineAvailability
from anishift.config.field_catalog import setting_catalog
from anishift.config.user_settings import UserSettings


def inspected_workspace(count: int = 20) -> InspectedWorkspace:
    groups: list[InspectedSourceGroup] = []
    for number in range(1, count + 1):
        group_id = f"episode-{number:02d}"
        path = Path(f"workspace/Episode {number:02d}.mkv")
        artifact = Artifact(
            group_id,
            group_id,
            ArtifactKind.VIDEO_MKV,
            path,
            ArtifactState.READY,
            ArtifactLifetime.SOURCE,
            path,
        )
        source = SourceGroup(group_id, f"Episode {number:02d}", Path("workspace"), (artifact,))
        groups.append(InspectedSourceGroup(source, (artifact,), {}, ()))
    return InspectedWorkspace(tuple(groups), ())


def app_service(workspace: InspectedWorkspace | None = None) -> Mock:
    facade = Mock(spec=AppService)
    facade.discover.return_value = workspace or inspected_workspace()
    preset = AutoPreset("default", "Polish subtitles", ProductIntent(frozenset({ProductKind.FULL_PL})))
    facade.list_presets.return_value = (preset,)
    facade.get_preset.return_value = preset
    plan = Mock(spec=ExecutionPlan)
    plan.groups = ()
    plan.tasks = ()
    plan.artifacts = ()
    plan.problems = ()
    plan.can_execute = True
    plan.settings = RunSettingsSnapshot(
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
    facade.plan_auto.return_value = plan
    facade.plan_manual.return_value = plan
    facade.engine_availability.return_value = (EngineAvailability("translation", "google", True, "ready"),)
    facade.settings_snapshot.return_value = UserSettings()
    facade.settings_catalog.return_value = setting_catalog()
    facade.environment_statuses.return_value = {}
    return facade
