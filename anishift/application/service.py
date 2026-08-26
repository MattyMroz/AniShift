"""UI-independent facade for discovery, planning, execution, and configuration."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Final, Protocol

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
from anishift.config.env_file import env_path, update_env_value
from anishift.config.field_access import assign_setting_value, setting_is_active, setting_is_persisted
from anishift.config.field_catalog import SettingCatalogContext, SettingSpec, SettingValue, setting_catalog
from anishift.config.model_catalog import ModelCatalog, ModelCatalogError, load_model_catalog
from anishift.config.presets import AutoPresetFile, load_presets, save_presets
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, save_user_settings
from anishift.config.workspace import cleanup_orphaned_temp, run_temp_dir
from anishift.errors import (
    AniShiftError,
    ConfigError,
    ErrorCode,
    ErrorContext,
    ExecutionError,
    PlanningError,
    RunConflictError,
)
from anishift.services.llm.engines import available_engine_ids as available_llm_engine_ids
from anishift.services.translation.engines import available_engine_ids as available_translation_engine_ids
from anishift.services.tts.engines import available_engine_ids as available_tts_engine_ids
from anishift.setup.doctor import CheckResult, run_doctor
from anishift.setup.installer import ResourceResult, run_setup
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.services.llm import LlmConfig

__all__ = [
    "AppService",
    "AutoPresetDraft",
    "EngineAvailability",
    "ExecutionHandlerFactory",
    "ModelAvailability",
    "ModelProbeResult",
    "ModelProber",
    "SettingsDraft",
]

logger = get_logger(__name__)

type SettingsDraft = UserSettings
"""Detached mutable settings copy edited by a frontend before explicit save."""

type ModelProber = Callable[[LlmConfig], None]
"""Connection test sending at most one minimal request, raising on failure."""

# ── Constants ────────────────────────────────────────────────────────────────

_PALANTIR_ENGINE_ID: Final[str] = "palantir"
"""LLM engine whose readiness needs an enrollment address and a catalog alias."""


class ModelAvailability(StrEnum):
    """Session-only availability vocabulary of one catalog model.

    A catalog entry is never available on its own; only an explicit connection
    test moves it out of ``UNVERIFIED``, and the answer lives in one session.
    """

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ModelProbeResult:
    """Outcome of one explicit connection test, owned by the session alone.

    Attributes:
        alias: Catalog alias the test addressed.
        availability: ``VERIFIED`` or ``ERROR``; the test never leaves a model
            ``UNVERIFIED``.
        checked_at: Moment the single attempt finished, in UTC.
        error_class: Safe error class name on failure, empty on success. Never a
            response body, a header, an address or a token.
    """

    alias: str
    availability: ModelAvailability
    checked_at: datetime
    error_class: str = ""


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


@dataclass(frozen=True, slots=True)
class EngineAvailability:
    """Cheap configuration-level engine status suitable for frontends."""

    domain: str
    engine_id: str
    is_available: bool
    reason: str


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
        catalog_loader: Callable[[], ModelCatalog] = load_model_catalog,
        model_prober: ModelProber | None = None,
        env_file: Path | None = None,
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
        self._catalog_loader: Callable[[], ModelCatalog] = catalog_loader
        self._model_prober: ModelProber | None = model_prober
        self._env_file: Path = env_file if env_file is not None else env_path()
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

    def settings_catalog(self, draft: SettingsDraft | None = None) -> tuple[SettingSpec, ...]:
        """Return fields active for saved or explicitly supplied draft selections."""
        preferences: UserSettings = deepcopy(draft) if draft is not None else self.settings_snapshot()
        return setting_catalog(SettingCatalogContext.from_user_settings(preferences))

    def current_settings(self) -> Settings:
        """Return the environment settings that the next run must use."""
        with self._run_lock:
            return self._settings

    def environment_statuses(self) -> Mapping[str, bool]:
        """Return environment-only availability without exposing configured values."""
        return {
            spec.setting_id: bool(getattr(self._settings, spec.setting_id, ""))
            for spec in self.settings_catalog()
            if spec.is_secret or not hasattr(self._user_settings, spec.setting_id)
        }

    def engine_availability(self) -> tuple[EngineAvailability, ...]:
        """Describe configured engine readiness without creating provider clients."""
        secret_by_engine: tuple[tuple[str, str, str], ...] = (
            ("translation", "deepl", "deepl_api_key"),
            ("tts", "elevenlabs", "elevenlabs_api_key"),
            ("llm", "anthropic", "anthropic_api_key"),
            ("llm", "deepseek", "deepseek_api_key"),
            ("llm", "gemini", "gemini_api_key"),
            ("llm", "openai", "openai_api_key"),
            ("llm", "openai_compatible", "openai_compatible_api_key"),
            ("llm", "openrouter", "openrouter_api_key"),
            ("llm", "palantir", "palantir_token"),
        )
        configured: dict[tuple[str, str], str] = {
            (domain, engine_id): secret_id for domain, engine_id, secret_id in secret_by_engine
        }
        engines: tuple[tuple[str, str], ...] = (
            *(("translation", engine_id) for engine_id in available_translation_engine_ids()),
            *(("tts", engine_id) for engine_id in available_tts_engine_ids()),
            *(("llm", engine_id) for engine_id in available_llm_engine_ids()),
        )
        statuses: list[EngineAvailability] = []
        for domain, engine_id in engines:
            secret_id: str | None = configured.get((domain, engine_id))
            available: bool = secret_id is None or bool(getattr(self._settings, secret_id, ""))
            reason: str = "ready" if available else f"missing {secret_id}; configure environment or open Tools"
            if available and domain == "llm" and engine_id == _PALANTIR_ENGINE_ID:
                available, reason = self._palantir_readiness()
            statuses.append(EngineAvailability(domain, engine_id, available, reason))
        return tuple(statuses)

    def model_catalog(self) -> ModelCatalog:
        """Return the validated local catalog of Palantir providers and models.

        The catalog is read on demand, so a hand edit is picked up without a
        restart, and it is never written back — comments in the file survive
        because nothing here owns its content.

        Returns:
            The parsed catalog.

        Raises:
            ModelCatalogError: The runtime catalog file is missing, unreadable or
                does not satisfy the catalog contract.
        """
        return self._catalog_loader()

    def probe_model(self, alias: str) -> ModelProbeResult:
        """Run one explicit connection test for one catalog alias.

        At most one minimal request is sent, and only when this method is called:
        opening a picker, filtering it or reading a status never reaches here.
        The answer belongs to the caller's session — nothing is written to the
        catalog, the preferences, a secret or any other file.

        Args:
            alias: Catalog alias the user confirmed for the test.

        Returns:
            ``VERIFIED`` with the completion time, or ``ERROR`` with a safe error
            class when the configuration is unusable or the single attempt failed.
        """
        try:
            config: LlmConfig = self._palantir_config(alias)
            self._prober()(config)
        except AniShiftError as error:
            error_class: str = type(error).__name__
            logger.warning(
                "Model probe failed",
                alias=alias,
                error_class=error_class,
                error_code=error.context.code.value,
            )
            return ModelProbeResult(
                alias=alias,
                availability=ModelAvailability.ERROR,
                checked_at=datetime.now(UTC),
                error_class=error_class,
            )
        logger.info("Model probe verified", alias=alias)
        return ModelProbeResult(
            alias=alias,
            availability=ModelAvailability.VERIFIED,
            checked_at=datetime.now(UTC),
        )

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

    def update_setting(self, setting_id: str, value: SettingValue) -> UserSettings:
        """Change one active preference as a single all-or-nothing transaction.

        Args:
            setting_id: Catalog ID of one editable, currently active preference.
            value: Replacement value validated against that catalog spec.

        Returns:
            A detached copy of the settings that were persisted.

        Raises:
            ConfigError: The ID is unknown, secret, or inactive for the current
                selections.
            ValueError: The value is rejected by the catalog spec.
            TypeError: The value does not match the declared field type.

        Nothing is written and the in-memory settings keep their previous state
        whenever any of those failures happens.
        """
        candidate: UserSettings = self.settings_snapshot()
        spec: SettingSpec = self._editable_spec(setting_id, candidate)
        spec.validate_value(value)
        assign_setting_value(candidate, spec, value)
        candidate.__post_init__()
        self._settings_saver(candidate)
        with self._run_lock:
            self._user_settings = deepcopy(candidate)
        return deepcopy(candidate)

    def update_secret(self, setting_id: str, value: str | None) -> None:
        """Store, clear, or remove one environment secret in the ``.env`` file.

        Args:
            setting_id: Catalog ID of one secret-scoped environment setting.
            value: Replacement secret, ``""`` to keep an empty assignment, or
                ``None`` to remove the key from the file entirely.

        Raises:
            ConfigError: The ID is unknown to the catalog or is not a secret.

        The secret is never returned, logged, or rendered; only the environment
        key name and the performed action are recorded. The file is replaced
        atomically, yet a same-named variable already exported in the process
        environment keeps overriding the stored value.
        """
        spec: SettingSpec = self._secret_spec(setting_id)
        update_env_value(_env_variable(spec.setting_id), value, path=self._env_file)
        self._reload_settings()

    def reload_environment(self) -> Mapping[str, bool]:
        """Re-read the environment file and report which env settings are configured.

        Returns:
            Exactly what :meth:`environment_statuses` reports for the reloaded
            environment, so configured values stay hidden.
        """
        self._reload_settings()
        return self.environment_statuses()

    def doctor(self) -> tuple[CheckResult, ...]:
        """Return every technical diagnostic through the shared setup API."""
        return tuple(self._doctor_runner(self._settings))

    def setup(self, *, force: bool = False) -> tuple[ResourceResult, ...]:
        """Install configured external resources without exposing setup internals."""
        return tuple(self._setup_runner(force=force, show_progress=False))

    def _editable_spec(self, setting_id: str, candidate: UserSettings) -> SettingSpec:
        spec: SettingSpec | None = next(
            (item for item in self.settings_catalog(candidate) if item.setting_id == setting_id),
            None,
        )
        if spec is None or spec.is_secret or not setting_is_persisted(spec):
            unknown = ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message=f"Unknown editable setting: {setting_id}",
                suggestion="Pick one of the settings the catalog reports for the current selections",
            )
            raise ConfigError(context=unknown)
        if not setting_is_active(spec, candidate):
            inactive = ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message=f"Setting is not active for the current selections: {setting_id}",
                suggestion="Change the engine or provider this setting depends on first",
            )
            raise ConfigError(context=inactive)
        return spec

    def _secret_spec(self, setting_id: str) -> SettingSpec:
        spec: SettingSpec | None = next(
            (item for item in self.settings_catalog() if item.setting_id == setting_id and item.is_secret),
            None,
        )
        if spec is None or setting_id not in Settings.model_fields:
            unknown = ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message=f"Unknown environment secret: {setting_id}",
                suggestion="Pick one of the secret settings the catalog reports",
            )
            raise ConfigError(context=unknown)
        return spec

    def _reload_settings(self) -> None:
        reloaded: Settings = Settings(_env_file=self._env_file)
        with self._run_lock:
            self._settings = reloaded

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

    def _palantir_readiness(self) -> tuple[bool, str]:
        """Report whether a token-configured Palantir provider could really run.

        A token alone is not readiness: without the enrollment address or a
        catalog alias the run path would fail, so a status must not promise
        ready. Nothing here sends a request or echoes the address.
        """
        preferences: UserSettings = self.settings_snapshot()
        if not preferences.palantir_enrollment_base_url.strip():
            return False, "missing palantir_enrollment_base_url; set the enrollment address in Tools"
        try:
            catalog: ModelCatalog = self.model_catalog()
        except ModelCatalogError:
            return False, "unusable model catalog; fix the catalog file the setup describes"
        if not catalog.models:
            return False, "empty model catalog; add one model entry with a usable provider"
        alias: str = preferences.llm_provider_model_id.strip()
        if preferences.llm_provider == _PALANTIR_ENGINE_ID and alias not in catalog.models:
            return False, "translation model alias is absent from the catalog; select one again"
        return True, "ready"

    def _palantir_config(self, alias: str) -> LlmConfig:
        """Resolve one alias into the configuration a connection test would use."""
        from anishift.application.runtime import palantir_llm_config  # noqa: PLC0415 - avoids an import cycle

        preferences: UserSettings = self.settings_snapshot()
        return palantir_llm_config(
            self.model_catalog(),
            alias,
            enrollment_base_url=preferences.palantir_enrollment_base_url,
            token=self.current_settings().palantir_token,
        )

    def _prober(self) -> ModelProber:
        """Return the injected connection test, or the production one."""
        if self._model_prober is not None:
            return self._model_prober
        from anishift.application.runtime import probe_palantir_model  # noqa: PLC0415 - avoids an import cycle

        return probe_palantir_model

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


def _env_variable(setting_id: str) -> str:
    prefix: str = Settings.model_config.get("env_prefix", "")
    return f"{prefix}{setting_id}".upper()


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
