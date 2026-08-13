"""UI-independent facade for discovery, planning, execution, and configuration."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from secrets import token_hex
from typing import Protocol

from anishift.application.cancellation import CancellationToken, EventCancellationToken, NeverCancelledToken
from anishift.application.discovery import discover_groups
from anishift.application.events import RunEventSink
from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace, WorkspaceInspector
from anishift.application.intents import (
    AutoPreset,
    ExternalAudioRole,
    GroupIntent,
    ProductIntent,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.planner import plan_auto as build_auto_plan
from anishift.application.planner import plan_manual as build_manual_plan
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.results import RunResult
from anishift.application.scheduler import GraphScheduler, ResourceLimits
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.sessions import RunSession
from anishift.config.field_catalog import SettingCatalogContext, SettingSpec, setting_catalog
from anishift.config.presets import AutoPresetFile, load_presets, save_presets
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, save_user_settings
from anishift.config.workspace import cleanup_orphaned_temp, run_temp_dir
from anishift.errors import ErrorCode, ErrorContext, ExecutionError, PlanningError, RunConflictError
from anishift.setup.doctor import CheckResult, run_doctor
from anishift.setup.installer import ResourceResult, run_setup

__all__ = ["AppService", "AutoPresetDraft", "ExecutionHandlerFactory", "SettingsDraft"]

type SettingsDraft = UserSettings
"""Detached mutable settings copy edited by a frontend before explicit save."""


@dataclass(frozen=True, slots=True)
class AutoPresetDraft:
    """Unsaved automatic workflow choices accepted by one plan preview."""

    preset_id: str
    name: str
    products: ProductIntent
    subtitle_source_policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    translation_action: TranslationAction = TranslationAction.AUTO
    source_subtitle_language: str | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE

    def to_preset(self) -> AutoPreset:
        """Validate and materialize the immutable planner contract."""
        return AutoPreset(
            preset_id=self.preset_id,
            name=self.name,
            products=self.products,
            subtitle_source_policy=self.subtitle_source_policy,
            translation_action=self.translation_action,
            source_subtitle_language=self.source_subtitle_language,
            subtitle_output_format=self.subtitle_output_format,
        )


class ExecutionHandlerFactory(Protocol):
    """Build run-scoped handlers after the immutable plan is accepted."""

    def __call__(
        self,
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> TaskHandler:
        """Return one dispatcher whose resources belong to this run."""
        ...


class AppService:
    """Single synchronous application boundary shared by TUI, CLI, and tests."""

    def __init__(  # noqa: PLR0913 - explicit composition-boundary dependencies
        self,
        *,
        workspace_root: Path,
        settings: Settings,
        user_settings: UserSettings,
        inspector: WorkspaceInspector,
        handler_factory: ExecutionHandlerFactory,
        preset_loader: Callable[[], AutoPresetFile] = load_presets,
        preset_saver: Callable[[AutoPresetFile], None] = save_presets,
        settings_saver: Callable[[UserSettings], None] = save_user_settings,
        doctor_runner: Callable[[Settings | None], Sequence[CheckResult]] = run_doctor,
        setup_runner: Callable[..., Sequence[ResourceResult]] = run_setup,
    ) -> None:
        self._workspace_root: Path = workspace_root
        self._settings: Settings = settings
        self._user_settings: UserSettings = deepcopy(user_settings)
        self._inspector: WorkspaceInspector = inspector
        self._handler_factory: ExecutionHandlerFactory = handler_factory
        self._preset_loader: Callable[[], AutoPresetFile] = preset_loader
        self._preset_saver: Callable[[AutoPresetFile], None] = preset_saver
        self._settings_saver: Callable[[UserSettings], None] = settings_saver
        self._doctor_runner: Callable[[Settings | None], Sequence[CheckResult]] = doctor_runner
        self._setup_runner: Callable[..., Sequence[ResourceResult]] = setup_runner
        self._workspace: InspectedWorkspace | None = None
        self._active_run_id: str | None = None
        self._active_cancel: EventCancellationToken | None = None
        self._run_lock: threading.Lock = threading.Lock()

    def discover(self, *, cancel: CancellationToken | None = None) -> InspectedWorkspace:
        """Discover and fully inspect the current workspace without starting work."""
        token: CancellationToken = cancel or NeverCancelledToken()
        inspected: InspectedWorkspace = self._inspector.inspect(
            discover_groups(self._workspace_root),
            cancel=token,
        )
        _commit_if_active(token, lambda: self._cache_workspace(inspected))
        return inspected

    def register_external_subtitle(
        self,
        group_id: str,
        path: Path,
        declared_language: str | None,
        *,
        cancel: CancellationToken | None = None,
    ) -> InspectedSourceGroup:
        """Validate one external subtitle and update the cached inspected group."""
        token: CancellationToken = cancel or NeverCancelledToken()
        group: InspectedSourceGroup = self._require_group(group_id)
        updated: InspectedSourceGroup = self._inspector.register_external_subtitle(
            group,
            path,
            declared_language=declared_language,
            cancel=token,
        )
        _commit_if_active(token, lambda: self._replace_group(updated))
        return updated

    def register_external_audio(
        self,
        group_id: str,
        path: Path,
        role: ExternalAudioRole,
        *,
        cancel: CancellationToken | None = None,
    ) -> InspectedSourceGroup:
        """Validate one external audio source and update the cached group."""
        token: CancellationToken = cancel or NeverCancelledToken()
        group: InspectedSourceGroup = self._require_group(group_id)
        updated: InspectedSourceGroup = self._inspector.register_external_audio(
            group,
            path,
            role=role,
            cancel=token,
        )
        _commit_if_active(token, lambda: self._replace_group(updated))
        return updated

    def list_presets(self) -> tuple[AutoPreset, ...]:
        """Return all stored automatic presets without mutating persistence."""
        return self._preset_loader().presets

    def get_preset(self, preset_id: str) -> AutoPreset:
        """Return one stored preset by stable ID."""
        for preset in self.list_presets():
            if preset.preset_id == preset_id:
                return preset
        msg = f"Unknown automatic preset: {preset_id}"
        raise PlanningError(msg)

    def save_preset(self, draft: AutoPresetDraft) -> AutoPreset:
        """Persist one validated draft by replacing the preset with the same ID."""
        preset: AutoPreset = draft.to_preset()
        current: AutoPresetFile = self._preset_loader()
        presets: list[AutoPreset] = list(current.presets)
        for index, existing in enumerate(presets):
            if existing.preset_id == preset.preset_id:
                presets[index] = preset
                break
        else:
            presets.append(preset)
        updated = AutoPresetFile(current.schema_version, tuple(presets), current.default_preset_id)
        self._preset_saver(updated)
        return preset

    def plan_auto(
        self,
        group_ids: Sequence[str],
        preset: AutoPreset | AutoPresetDraft,
    ) -> ExecutionPlan:
        """Plan selected groups from a stored or one-shot automatic preset."""
        resolved: AutoPreset = preset.to_preset() if isinstance(preset, AutoPresetDraft) else preset
        return build_auto_plan(self._selected_groups(group_ids), resolved, self._settings_snapshot())

    def plan_manual(self, intents: Sequence[GroupIntent]) -> ExecutionPlan:
        """Plan one independent explicit intent for every selected group."""
        intent_by_group: dict[str, GroupIntent] = {intent.group_id: intent for intent in intents}
        if len(intent_by_group) != len(intents):
            msg = "Manual intent group IDs must be unique"
            raise PlanningError(msg)
        groups: tuple[InspectedSourceGroup, ...] = self._selected_groups(tuple(intent_by_group))
        return build_manual_plan(groups, intent_by_group, self._settings_snapshot())

    def execute(self, plan: ExecutionPlan, sink: RunEventSink) -> RunResult:
        """Execute one accepted immutable plan through a private run session."""
        if not plan.can_execute:
            msg = "A plan with blocking problems cannot be executed"
            raise ExecutionError(msg)
        run_id: str = f"run-{token_hex(8)}"
        cancel = EventCancellationToken()
        self._claim_run(run_id, cancel)
        run_root: Path = run_temp_dir(self._workspace_root, run_id)
        active_ids: tuple[str, ...] = (run_id,)
        try:
            cleanup_orphaned_temp(self._workspace_root, active_run_ids=active_ids)
            source_groups: dict[str, InspectedSourceGroup] = {
                group.group_id: group for group in self._selected_groups(tuple(item.group_id for item in plan.groups))
            }
            session = RunSession(run_root)
            with session:
                handler: TaskHandler = self._handler_factory(run_root, plan, source_groups)
                scheduler = GraphScheduler(
                    handler,
                    limits=ResourceLimits.from_settings(plan.settings),
                    run_id=run_id,
                    session=session,
                )
                try:
                    result: RunResult = scheduler.run(plan, cancel=cancel, events=sink)
                finally:
                    _close_handler(handler)
            if session.cleanup_warnings:
                result = replace(result, warnings=(*result.warnings, *session.cleanup_warnings))
            return result
        finally:
            self._release_run(run_id)

    def cancel(self, run_id: str) -> bool:
        """Request cancellation only when *run_id* is the active local run."""
        with self._run_lock:
            if self._active_run_id != run_id or self._active_cancel is None:
                return False
            self._active_cancel.cancel()
            return True

    def settings_catalog(self) -> tuple[SettingSpec, ...]:
        """Return fields active for the current saved engine selections."""
        return setting_catalog(SettingCatalogContext.from_user_settings(self._user_settings))

    def settings_snapshot(self) -> SettingsDraft:
        """Return a detached mutable copy that cannot affect an active plan."""
        with self._run_lock:
            return deepcopy(self._user_settings)

    def save_settings(self, draft: SettingsDraft) -> UserSettings:
        """Validate and persist an explicit detached settings draft."""
        validated: UserSettings = deepcopy(draft)
        validated.__post_init__()
        self._settings_saver(validated)
        with self._run_lock:
            self._user_settings = deepcopy(validated)
        return deepcopy(validated)

    def doctor(self) -> tuple[CheckResult, ...]:
        """Return every technical diagnostic through the shared setup API."""
        return tuple(self._doctor_runner(self._settings))

    def setup(self, *, force: bool = False) -> tuple[ResourceResult, ...]:
        """Install configured external resources without exposing setup internals."""
        return tuple(self._setup_runner(force=force))

    def _selected_groups(self, group_ids: Sequence[str]) -> tuple[InspectedSourceGroup, ...]:
        requested: tuple[str, ...] = tuple(group_ids)
        if not requested or len(requested) != len(set(requested)):
            msg = "Selected group IDs must be non-empty and unique"
            raise PlanningError(msg)
        workspace: InspectedWorkspace = self._require_workspace()
        by_id: dict[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
        try:
            return tuple(by_id[group_id] for group_id in requested)
        except KeyError as error:
            msg = f"Unknown inspected source group: {error.args[0]}"
            raise PlanningError(msg) from error

    def _require_group(self, group_id: str) -> InspectedSourceGroup:
        return self._selected_groups((group_id,))[0]

    def _require_workspace(self) -> InspectedWorkspace:
        with self._run_lock:
            workspace: InspectedWorkspace | None = self._workspace
        if workspace is None:
            msg = "Discover the workspace before planning or registering external files"
            raise PlanningError(msg)
        return workspace

    def _replace_group(self, updated: InspectedSourceGroup) -> None:
        workspace: InspectedWorkspace = self._require_workspace()
        groups: tuple[InspectedSourceGroup, ...] = tuple(
            updated if group.group_id == updated.group_id else group for group in workspace.groups
        )
        with self._run_lock:
            self._workspace = replace(workspace, groups=groups)

    def _cache_workspace(self, inspected: InspectedWorkspace) -> None:
        with self._run_lock:
            self._workspace = inspected

    def _settings_snapshot(self) -> RunSettingsSnapshot:
        with self._run_lock:
            preferences: UserSettings = deepcopy(self._user_settings)
        return _run_settings_snapshot(preferences)

    def _claim_run(self, run_id: str, cancel: EventCancellationToken) -> None:
        with self._run_lock:
            if self._active_run_id is not None:
                context = ErrorContext(
                    code=ErrorCode.IO_ERROR,
                    message="Another AniShift workflow is already active",
                )
                raise RunConflictError(context=context)
            self._active_run_id = run_id
            self._active_cancel = cancel

    def _release_run(self, run_id: str) -> None:
        with self._run_lock:
            if self._active_run_id == run_id:
                self._active_run_id = None
                self._active_cancel = None


def _run_settings_snapshot(preferences: UserSettings) -> RunSettingsSnapshot:
    fallback: tuple[str, ...] = tuple(
        engine for engine in preferences.translation_fallback_chain if engine != preferences.translation_engine
    )
    profile = preferences.active_tts_profile
    tts_jobs: int = profile.concurrency or 1
    return RunSettingsSnapshot(
        translation_profile_id=preferences.translation_engine,
        translation_fallback_chain=fallback,
        translation_max_retries=preferences.translation_max_retries,
        translation_concurrency=preferences.translation_concurrency,
        llm_profile_id=preferences.llm_provider,
        llm_max_concurrency=preferences.llm_max_concurrency,
        tts_profile_id=preferences.tts_engine,
        tts_max_retries=preferences.tts_max_retries,
        tts_group_jobs=4,
        tts_request_concurrency=tts_jobs,
        audio_profile_id=preferences.tts_output_profile,
        composition_profile_id=preferences.composition_quality_preset,
        processing_order_policy=ProcessingOrderPolicy(preferences.processing_order_policy),
        audio_output_profile=preferences.tts_output_profile,
        subtitle_language_priority=preferences.subtitle_language_priority,
        audio_language_priority=preferences.audio_language_priority,
        translation_is_paid=preferences.translation_engine != "google",
        llm_is_paid=True,
        tts_is_network=preferences.tts_engine != "sapi",
        tts_is_paid=preferences.tts_engine in {"elevenbytes", "elevenlabs"},
        translation_batch_size=preferences.translation_batch_size,
        llm_model_id=preferences.llm_provider_model_id,
        llm_temperature=preferences.llm_temperature,
        llm_top_p=preferences.llm_top_p,
        llm_max_output_tokens=preferences.llm_max_output_tokens,
        llm_prompt_id=preferences.llm_prompt_id,
        llm_style_id=preferences.llm_style_id,
        llm_module_ids=tuple(preferences.llm_module_ids),
        tts_model_id=preferences.tts_provider_model_id,
        tts_voice_id=preferences.resolved_tts_voice_id,
        tts_native_rate=profile.native_rate,
        tts_native_volume=profile.native_volume,
        tts_native_pitch=profile.native_pitch,
        tts_engine_options=tuple(sorted(profile.engine_options.items())),
        tts_vpn_enabled=preferences.elevenbytes_vpn_enabled,
        tts_postprocess_tempo=profile.postprocess_tempo,
        audio_bitrate=preferences.tts_output_bitrate,
        narrator_mix_base_gain_db=preferences.narrator_mix_base_gain_db,
        voice_mix_offset_db=profile.voice_mix_offset_db,
        original_gain_db=preferences.original_gain_db,
        tts_timeline_policy=preferences.tts_timeline_policy,
    )


def _close_handler(handler: TaskHandler) -> None:
    close: object = getattr(handler, "close", None)
    if callable(close):
        close()


def _commit_if_active(token: CancellationToken, action: Callable[[], None]) -> None:
    if isinstance(token, EventCancellationToken):
        if token.commit_if_active(action):
            return
        token.raise_if_cancelled()
    token.raise_if_cancelled()
    action()
