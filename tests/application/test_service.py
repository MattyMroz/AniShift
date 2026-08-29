from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fakes import (
    CollectingRunSink,
    FailingGroupHandler,
    FakeMediaProbe,
    FakeTranslationService,
    write_media_source,
    write_text_source,
)

import anishift.application.service as service_module
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ProductIntent, ProductKind
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, TaskKind
from anishift.application.results import GroupStatus, RunResult
from anishift.application.scheduler_contracts import ResourceLimits, TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.bootstrap import AppContext, bootstrap, create_app_service
from anishift.config.model_catalog import ModelCatalog, parse_model_catalog
from anishift.config.presets import AutoPresetFile, default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import RunConflictError
from anishift.services.extraction import ExtractionRequest, ExtractionResult
from anishift.services.media import DefaultMediaProbe

_PALANTIR_TOKEN = "palantir-token-sentinel-deadbeef"  # noqa: S105


class _UnusedExtraction:
    def extract(
        self,
        request: ExtractionRequest,
        *,
        cancel: object,
        timeout_s: float,
    ) -> ExtractionResult:
        del request, cancel, timeout_s
        raise AssertionError("TXT flow must not extract media tracks")


def _service(  # noqa: PLR0913 - one builder for every service variant the tests need
    tmp_path: Path,
    translation: FakeTranslationService,
    *,
    fail_group_id: str | None = None,
    preset_store: list[AutoPresetFile] | None = None,
    inspector: WorkspaceInspector | None = None,
    settings: Settings | None = None,
    user_settings: UserSettings | None = None,
    catalog_loader: Callable[[], ModelCatalog] | None = None,
) -> AppService:
    stored: list[AutoPresetFile] = preset_store if preset_store is not None else [default_preset_file()]

    def handlers(
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> TaskHandler:
        del plan
        discovered_groups = {group_id: group.source for group_id, group in source_groups.items()}
        delegate = ExecutionHandlers(
            ExtractionTaskHandler(_UnusedExtraction(), run_root=run_root, timeout_s=30.0),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(translation, run_root=run_root),
            publish=PublishTaskHandler(run_root=run_root, source_groups=discovered_groups),
        )
        return FailingGroupHandler(delegate, group_id=fail_group_id)

    return AppService(
        workspace_root=tmp_path,
        settings=settings or Settings(_env_file=None),
        user_settings=user_settings or UserSettings(),
        inspector=inspector or WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=handlers,
        preset_loader=lambda: stored[0],
        preset_saver=lambda value: stored.__setitem__(0, value),
        settings_saver=lambda value: None,
        catalog_loader=catalog_loader or _catalog,
    )


def _catalog() -> ModelCatalog:
    source = """
    {
      "schema_version": 1,
      "providers": { "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" } },
      "models": { "foundry/gpt-main": { "provider": "foundry-openai", "model": "id-1" } }
    }
    """
    return parse_model_catalog(source)


def test_real_service_flows_from_discovery_through_partial_execution(tmp_path: Path) -> None:
    for name in ("Episode 1", "Episode 2", "Episode 3"):
        write_media_source(tmp_path / f"{name}.mkv")
    preset_store: list[AutoPresetFile] = [default_preset_file()]
    service: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        preset_store=preset_store,
        inspector=WorkspaceInspector(FakeMediaProbe()),
    )
    workspace = service.discover()
    selected = workspace.groups[:2]
    draft = AutoPresetDraft(
        "preview",
        "Preview once",
        ProductIntent(frozenset({ProductKind.FULL_PL, ProductKind.SPOKEN_PL})),
    )
    fail_group_id: str = selected[1].group_id
    service = _service(
        tmp_path,
        FakeTranslationService(),
        fail_group_id=fail_group_id,
        preset_store=preset_store,
        inspector=WorkspaceInspector(FakeMediaProbe()),
    )
    workspace = service.discover()
    selected = workspace.groups[:2]

    plan: ExecutionPlan = service.plan_auto(tuple(group.group_id for group in selected), draft)
    sink = CollectingRunSink()
    result: RunResult = service.execute(plan, sink)

    assert tuple(group.status for group in result.groups) == (GroupStatus.SUCCEEDED, GroupStatus.PARTIAL)
    assert (tmp_path / "Episode 1.pl.srt").is_file()
    assert (tmp_path / "Episode 1.spoken.pl.srt").is_file()
    assert (tmp_path / "Episode 2.pl.srt").is_file()
    assert not (tmp_path / "Episode 2.spoken.pl.srt").exists()
    assert not any((tmp_path / "temp").iterdir())
    assert service.list_presets() == default_preset_file().presets
    assert sink.events[0].kind.value == "run_started"
    assert sink.events[-1].kind.value == "run_finished"


def test_preview_draft_does_not_save_and_explicit_save_replaces_preset(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    store: list[AutoPresetFile] = [default_preset_file()]
    service: AppService = _service(tmp_path, FakeTranslationService(), preset_store=store)
    group_id: str = service.discover().groups[0].group_id
    draft = AutoPresetDraft("default", "Changed", ProductIntent(frozenset({ProductKind.SPOKEN_PL})))

    service.plan_auto((group_id,), draft)
    assert store[0] == default_preset_file()

    saved = service.save_preset(draft)
    assert store[0].presets == (saved,)


def test_active_run_rejects_a_second_execute_before_creating_another_scope(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    entered = threading.Event()
    release = threading.Event()
    service: AppService = _service(tmp_path, FakeTranslationService(entered=entered, release=release))
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    sink = CollectingRunSink()
    results: list[RunResult] = []
    thread = threading.Thread(target=lambda: results.append(service.execute(plan, sink)))
    thread.start()
    assert entered.wait(timeout=1.0)

    with pytest.raises(RunConflictError, match="already active"):
        service.execute(plan, CollectingRunSink())

    assert len(tuple((tmp_path / "temp").iterdir())) == 1
    assert service.cancel(sink.events[0].run_id)
    assert not service.cancel("another-run")
    release.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert len(results) == 1
    assert results[0].cancelled
    assert not any((tmp_path / "temp").iterdir())


def test_settings_draft_and_plan_snapshot_are_detached(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    group_id: str = service.discover().groups[0].group_id
    draft = service.settings_snapshot()
    draft.translation_concurrency = 3
    draft.tts_voice_profiles = {
        key: replace(profile, postprocess_tempo=1.5) for key, profile in draft.tts_voice_profiles.items()
    }
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )

    service.save_settings(draft)

    assert plan.settings.translation_concurrency == 1
    assert plan.settings.llm_max_concurrency == 4
    assert plan.settings.tts_postprocess_tempo == 1.25
    assert plan.settings.tts_group_jobs == 1
    assert plan.settings.tts_request_concurrency == 100
    assert plan.settings.processing_order_policy is ProcessingOrderPolicy.READY_FIRST
    assert service.settings_snapshot().translation_concurrency == 3


def test_auto_plan_preserves_ready_first_four_file_llm_queue(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    preferences = UserSettings(
        translation_engine="llm",
        llm_max_concurrency=4,
        processing_order_policy="ready_first",
    )
    service: AppService = _service(tmp_path, FakeTranslationService(), user_settings=preferences)
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    limits: ResourceLimits = ResourceLimits.from_settings(plan.settings)

    assert plan.settings.processing_order_policy is ProcessingOrderPolicy.READY_FIRST
    assert limits.worker_limit("llm:gemini", plan.settings) == 4


def test_auto_keeps_legacy_single_episode_tts_with_provider_request_concurrency(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _service(tmp_path, FakeTranslationService())
    group_id: str = service.discover().groups[0].group_id

    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )
    limits: ResourceLimits = ResourceLimits.from_settings(plan.settings)

    assert limits.worker_limit(f"tts:{plan.settings.tts_profile_id}", plan.settings) == 1
    assert plan.settings.tts_request_concurrency == 100


def test_auto_uses_the_legacy_extraction_pool_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks: tuple[SimpleNamespace, ...] = tuple(
        SimpleNamespace(group_id=f"group-{index}", kind=TaskKind.EXTRACT_TRACKS) for index in range(6)
    )
    plan: ExecutionPlan = cast("ExecutionPlan", SimpleNamespace(tasks=tasks))
    monkeypatch.setattr(os, "cpu_count", lambda: 16)

    assert service_module._extraction_worker_count(plan) == 6


def test_engine_availability_exposes_reasons_without_secret_values(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, FakeTranslationService())

    statuses = {(item.domain, item.engine_id): item for item in service.engine_availability()}

    assert statuses["translation", "google"].is_available
    assert not statuses["translation", "deepl"].is_available
    assert statuses["translation", "deepl"].reason == "missing deepl_api_key; configure environment or open Tools"


def test_engine_availability_reports_the_palantir_token_in_both_directions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)
    connected: UserSettings = UserSettings(palantir_enrollment_base_url="https://example.palantirfoundry.com")
    without_token: AppService = _service(tmp_path, FakeTranslationService(), user_settings=connected)
    with_token: AppService = _service(
        tmp_path,
        FakeTranslationService(),
        settings=Settings(_env_file=None, palantir_token=_PALANTIR_TOKEN),
        user_settings=connected,
    )

    missing = {(item.domain, item.engine_id): item for item in without_token.engine_availability()}
    ready = {(item.domain, item.engine_id): item for item in with_token.engine_availability()}

    assert not missing["llm", "palantir"].is_available
    assert missing["llm", "palantir"].reason == "missing palantir_token; configure environment or open Tools"
    assert ready["llm", "palantir"].is_available
    assert ready["llm", "palantir"].reason == "ready"
    assert _PALANTIR_TOKEN not in str(ready["llm", "palantir"])


def test_bootstrap_builds_the_shared_service_without_creating_provider_clients(tmp_path: Path) -> None:
    workspace_root: Path = tmp_path / "workspace"
    context: AppContext = bootstrap(
        settings=Settings(workspace_root=str(workspace_root), _env_file=None),
        create_dirs=False,
    )

    service: AppService = create_app_service(context)

    assert isinstance(service, AppService)
    assert not workspace_root.exists()
