from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from anishift.application import runtime
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, ModelAvailability, ModelProbeResult
from anishift.config import user_settings as user_settings_module
from anishift.config.model_catalog import ModelCatalog, parse_model_catalog
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, load_user_settings, save_user_settings
from anishift.errors import ConfigError, ErrorCode
from anishift.services.llm import LlmAuthError, LlmConfig, LlmRequest, LlmResponse, LlmTimeoutError, LlmUsage
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.services.media import DefaultMediaProbe

_ENROLLMENT = "https://acme.palantirfoundry.com"
_TOKEN = "palantir-token-sentinel-cafebabe"  # noqa: S105
_ALIAS = "foundry/gpt-main"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("FOUNDRY_API_TOKEN", raising=False)


class _RecordingProber:
    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[LlmConfig] = []
        self._failure: Exception | None = failure

    def __call__(self, config: LlmConfig) -> None:
        self.calls.append(config)
        if self._failure is not None:
            raise self._failure


def _unused_handlers(
    run_root: Path,
    plan: ExecutionPlan,
    source_groups: Mapping[str, InspectedSourceGroup],
) -> TaskHandler:
    del run_root, plan, source_groups
    raise AssertionError("Editing model settings must not execute a plan")


def _catalog(source: str | None = None) -> ModelCatalog:
    default = """
    {
      "schema_version": 1,
      "providers": {
        "foundry-openai": { "protocol": "openai_chat", "path": "/api/v2/llm/proxy/openai/v1" }
      },
      "models": { "foundry/gpt-main": { "provider": "foundry-openai", "model": "gpt-provider-id" } },
      "defaults": { "primary": "foundry/gpt-main", "translation": "foundry/gpt-main" }
    }
    """
    return parse_model_catalog(source if source is not None else default)


def _service(  # noqa: PLR0913 - one builder for every service variant these tests need
    tmp_path: Path,
    *,
    user_settings: UserSettings | None = None,
    settings: Settings | None = None,
    catalog: ModelCatalog | None = None,
    prober: _RecordingProber | None = None,
    saved: list[UserSettings] | None = None,
) -> AppService:
    store: list[UserSettings] = saved if saved is not None else []
    return AppService(
        workspace_root=tmp_path,
        settings=settings or Settings(_env_file=None),
        user_settings=user_settings or UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=_unused_handlers,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=store.append,
        catalog_loader=lambda: catalog if catalog is not None else _catalog(),
        model_prober=prober,
        env_file=tmp_path / ".env",
    )


def _connected(tmp_path: Path, prober: _RecordingProber) -> AppService:
    return _service(
        tmp_path,
        user_settings=UserSettings(palantir_enrollment_base_url=_ENROLLMENT),
        settings=Settings(_env_file=None, palantir_token=_TOKEN),
        prober=prober,
    )


def _snapshot(**overrides: object) -> RunSettingsSnapshot:
    base: dict[str, object] = {
        "translation_profile_id": "llm",
        "translation_fallback_chain": (),
        "translation_max_retries": 3,
        "translation_concurrency": 2,
        "llm_profile_id": "palantir",
        "llm_max_concurrency": 2,
        "tts_profile_id": "edge",
        "tts_max_retries": 3,
        "tts_group_jobs": 2,
        "audio_profile_id": "eac3",
        "composition_profile_id": "default",
        "processing_order_policy": ProcessingOrderPolicy.READY_FIRST,
        "llm_model_id": _ALIAS,
    }
    base.update(overrides)
    return RunSettingsSnapshot(**base)  # type: ignore[arg-type]


def _plan(**overrides: object) -> ExecutionPlan:
    return ExecutionPlan((), (), (), _snapshot(**overrides), ())


def test_the_main_model_and_the_translation_model_are_settable_independently(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, user_settings=UserSettings(translation_engine="llm"))
    before: UserSettings = service.settings_snapshot()

    after_main: UserSettings = service.update_setting("primary_model_alias", _ALIAS)

    assert after_main.primary_model_alias == _ALIAS
    assert after_main.llm_provider == before.llm_provider
    assert after_main.llm_provider_model_id == before.llm_provider_model_id

    after_translation: UserSettings = service.update_setting("llm_provider_model_id", "other-model")

    assert after_translation.llm_provider_model_id == "other-model"
    assert after_translation.primary_model_alias == _ALIAS


def test_switching_the_translation_provider_never_clears_the_main_model(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, user_settings=UserSettings(translation_engine="llm"))
    service.update_setting("primary_model_alias", _ALIAS)

    switched: UserSettings = service.update_setting("llm_provider", "palantir")

    assert switched.llm_provider == "palantir"
    assert switched.primary_model_alias == _ALIAS


def test_the_enrollment_address_is_a_preference_and_accepts_only_an_https_origin(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path)

    stored: UserSettings = service.update_setting("palantir_enrollment_base_url", _ENROLLMENT)

    assert stored.palantir_enrollment_base_url == _ENROLLMENT

    for rejected in ("http://acme.palantirfoundry.com", f"{_ENROLLMENT}/?token=1", f"{_ENROLLMENT}#f", "acme"):
        with pytest.raises(ValueError, match="required format"):
            service.update_setting("palantir_enrollment_base_url", rejected)

    assert service.settings_snapshot().palantir_enrollment_base_url == _ENROLLMENT


def test_an_empty_enrollment_address_is_a_legal_not_configured_value(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, user_settings=UserSettings(palantir_enrollment_base_url=_ENROLLMENT))

    cleared: UserSettings = service.update_setting("palantir_enrollment_base_url", "")

    assert cleared.palantir_enrollment_base_url == ""


def test_both_model_preferences_survive_a_save_and_load_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(user_settings_module, "config_path", lambda: tmp_path / "settings.json")
    save_user_settings(
        UserSettings(primary_model_alias=_ALIAS, palantir_enrollment_base_url=_ENROLLMENT),
    )

    loaded: UserSettings = load_user_settings()

    assert loaded.primary_model_alias == _ALIAS
    assert loaded.palantir_enrollment_base_url == _ENROLLMENT


def test_a_persisted_enrollment_address_that_is_not_https_falls_back_to_not_configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings_file: Path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings_module, "config_path", lambda: settings_file)
    settings_file.write_text(
        '{"palantir_enrollment_base_url": "http://acme.palantirfoundry.com", "primary_model_alias": 7}',
        encoding="utf-8",
    )

    loaded: UserSettings = load_user_settings()

    assert loaded.palantir_enrollment_base_url == ""
    assert loaded.primary_model_alias == ""


def test_the_palantir_token_is_written_to_the_canonical_environment_variable(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path)

    service.update_secret("palantir_token", _TOKEN)

    assert (tmp_path / ".env").read_text(encoding="utf-8") == f'ANISHIFT_PALANTIR_TOKEN="{_TOKEN}"\n'
    assert service.environment_statuses()["palantir_token"] is True
    assert _TOKEN not in repr(service.environment_statuses())


def test_the_model_catalog_is_read_on_demand_and_never_written(tmp_path: Path) -> None:
    reads: list[int] = []

    def loader() -> ModelCatalog:
        reads.append(1)
        return _catalog()

    service: AppService = AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=_unused_handlers,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
        catalog_loader=loader,
        env_file=tmp_path / ".env",
    )

    assert set(service.model_catalog().models) == {_ALIAS}
    assert set(service.model_catalog().models) == {_ALIAS}
    assert len(reads) == 2
    assert not hasattr(service, "save_model_catalog")


def test_probing_a_model_sends_exactly_one_request_and_stores_nothing(tmp_path: Path) -> None:
    prober = _RecordingProber()
    saved: list[UserSettings] = []
    service: AppService = _service(
        tmp_path,
        user_settings=UserSettings(palantir_enrollment_base_url=_ENROLLMENT),
        settings=Settings(_env_file=None, palantir_token=_TOKEN),
        prober=prober,
        saved=saved,
    )

    result: ModelProbeResult = service.probe_model(_ALIAS)

    assert result.availability is ModelAvailability.VERIFIED
    assert result.alias == _ALIAS
    assert result.error_class == ""
    assert result.checked_at.tzinfo is not None
    assert len(prober.calls) == 1
    assert prober.calls[0].max_retries == 0
    assert saved == []
    assert list(tmp_path.iterdir()) == []
    assert service.model_catalog().models[_ALIAS].model_id == "gpt-provider-id"


def test_a_probe_result_never_carries_the_token_the_address_or_a_provider_message(tmp_path: Path) -> None:
    failure = LlmAuthError(f"provider rejected {_TOKEN} at {_ENROLLMENT}")
    service: AppService = _connected(tmp_path, _RecordingProber(failure))

    result: ModelProbeResult = service.probe_model(_ALIAS)

    assert result.availability is ModelAvailability.ERROR
    assert result.error_class == "LlmAuthError"
    assert _TOKEN not in repr(result)
    assert _ENROLLMENT not in repr(result)
    assert "provider rejected" not in repr(result)


def test_a_transient_failure_is_reported_as_an_error_class_after_one_attempt(tmp_path: Path) -> None:
    prober = _RecordingProber(LlmTimeoutError("timed out"))
    service: AppService = _connected(tmp_path, prober)

    result: ModelProbeResult = service.probe_model(_ALIAS)

    assert result.availability is ModelAvailability.ERROR
    assert result.error_class == "LlmTimeoutError"
    assert len(prober.calls) == 1


def test_probing_an_unknown_alias_reports_an_error_without_sending_a_request(tmp_path: Path) -> None:
    prober = _RecordingProber()
    service: AppService = _connected(tmp_path, prober)

    result: ModelProbeResult = service.probe_model("foundry/absent")

    assert result.availability is ModelAvailability.ERROR
    assert result.error_class == "ConfigError"
    assert prober.calls == []


def test_probing_without_an_enrollment_address_reports_an_error_without_sending_a_request(tmp_path: Path) -> None:
    prober = _RecordingProber()
    service: AppService = _service(
        tmp_path,
        settings=Settings(_env_file=None, palantir_token=_TOKEN),
        prober=prober,
    )

    result: ModelProbeResult = service.probe_model(_ALIAS)

    assert result.availability is ModelAvailability.ERROR
    assert result.error_class == "ConfigError"
    assert prober.calls == []


def test_probing_without_a_token_reports_an_error_without_sending_a_request(tmp_path: Path) -> None:
    prober = _RecordingProber()
    service: AppService = _service(
        tmp_path,
        user_settings=UserSettings(palantir_enrollment_base_url=_ENROLLMENT),
        prober=prober,
    )

    result: ModelProbeResult = service.probe_model(_ALIAS)

    assert result.availability is ModelAvailability.ERROR
    assert result.error_class == "LlmAuthError"
    assert prober.calls == []


def test_reading_the_catalog_and_the_status_never_probes(tmp_path: Path) -> None:
    prober = _RecordingProber()
    service: AppService = _connected(tmp_path, prober)

    service.model_catalog()
    service.settings_catalog()
    statuses = {(item.domain, item.engine_id): item for item in service.engine_availability()}

    assert prober.calls == []
    assert statuses["llm", "palantir"].is_available
    assert statuses["llm", "palantir"].reason == "ready"


def test_a_configured_token_alone_is_not_reported_as_a_ready_palantir_engine(tmp_path: Path) -> None:
    service: AppService = _service(tmp_path, settings=Settings(_env_file=None, palantir_token=_TOKEN))

    statuses = {(item.domain, item.engine_id): item for item in service.engine_availability()}

    assert not statuses["llm", "palantir"].is_available
    assert "palantir_enrollment_base_url" in statuses["llm", "palantir"].reason


def test_an_empty_catalog_or_an_absent_translation_alias_is_not_reported_as_ready(tmp_path: Path) -> None:
    empty: ModelCatalog = _catalog('{"schema_version": 1, "providers": {}, "models": {}}')
    without_models: AppService = _service(
        tmp_path,
        user_settings=UserSettings(palantir_enrollment_base_url=_ENROLLMENT),
        settings=Settings(_env_file=None, palantir_token=_TOKEN),
        catalog=empty,
    )
    stale: AppService = _service(
        tmp_path,
        user_settings=UserSettings(
            palantir_enrollment_base_url=_ENROLLMENT,
            llm_provider="palantir",
            llm_provider_model_id="foundry/absent",
        ),
        settings=Settings(_env_file=None, palantir_token=_TOKEN),
    )

    first = {(item.domain, item.engine_id): item for item in without_models.engine_availability()}
    second = {(item.domain, item.engine_id): item for item in stale.engine_availability()}

    assert not first["llm", "palantir"].is_available
    assert "empty model catalog" in first["llm", "palantir"].reason
    assert not second["llm", "palantir"].is_available
    assert "absent from the catalog" in second["llm", "palantir"].reason


def test_resolving_an_alias_builds_the_complete_palantir_configuration() -> None:
    config: LlmConfig = runtime.palantir_llm_config(
        _catalog(),
        _ALIAS,
        enrollment_base_url=_ENROLLMENT,
        token=_TOKEN,
        max_retries=2,
    )

    assert config.engine_id == "palantir"
    assert config.alias == _ALIAS
    assert config.provider_id == "foundry-openai"
    assert config.protocol is ModelProtocol.OPENAI_CHAT
    assert config.base_url == f"{_ENROLLMENT}/api/v2/llm/proxy/openai/v1"
    assert config.provider_model_id == "gpt-provider-id"
    assert config.api_key == _TOKEN
    assert config.max_retries == 2
    assert _TOKEN not in repr(config)


def test_resolving_an_unknown_alias_fails_with_a_typed_error_naming_the_alias() -> None:
    with pytest.raises(ConfigError) as raised:
        runtime.palantir_llm_config(
            _catalog(),
            "foundry/absent",
            enrollment_base_url=_ENROLLMENT,
            token=_TOKEN,
        )

    assert raised.value.context.code is ErrorCode.CONFIG_INVALID
    assert "foundry/absent" in raised.value.context.message
    assert raised.value.context.suggestion


def test_resolving_without_an_enrollment_address_names_the_preference_but_not_its_value() -> None:
    with pytest.raises(ConfigError) as missing:
        runtime.palantir_llm_config(_catalog(), _ALIAS, enrollment_base_url="", token=_TOKEN)
    with pytest.raises(ConfigError) as malformed:
        runtime.palantir_llm_config(
            _catalog(),
            _ALIAS,
            enrollment_base_url="http://acme.palantirfoundry.com",
            token=_TOKEN,
        )

    assert missing.value.context.code is ErrorCode.CONFIG_MISSING
    assert "palantir_enrollment_base_url" in missing.value.context.message
    assert malformed.value.context.code is ErrorCode.CONFIG_INVALID
    assert "acme.palantirfoundry.com" not in repr(malformed.value.context)


def test_the_translation_run_path_resolves_the_alias_the_same_way(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "load_model_catalog", _catalog)
    monkeypatch.setattr(
        runtime,
        "load_user_settings",
        lambda: UserSettings(palantir_enrollment_base_url=_ENROLLMENT),
    )
    settings = Settings(_env_file=None, palantir_token=_TOKEN, openai_compatible_base_url="https://compat.invalid")

    config: LlmConfig = runtime._llm_config(settings, _plan(llm_temperature=0.5, llm_max_output_tokens=2048))

    assert config.engine_id == "palantir"
    assert config.base_url == f"{_ENROLLMENT}/api/v2/llm/proxy/openai/v1"
    assert config.provider_model_id == "gpt-provider-id"
    assert config.api_key == _TOKEN
    assert config.temperature == 0.5
    assert config.max_output_tokens == 2048
    assert config.max_retries == 3


def test_the_production_probe_sends_one_minimal_request_and_closes_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[LlmConfig, LlmRequest]] = []
    closed: list[str] = []

    class _FakeLlmService:
        def __init__(self, config: LlmConfig) -> None:
            self._config: LlmConfig = config

        def complete(self, request: LlmRequest) -> LlmResponse:
            seen.append((self._config, request))
            return LlmResponse(
                text="pong",
                engine_id=self._config.engine_id,
                provider_model_id=self._config.provider_model_id,
                finish_reason="stop",
                latency_ms=1.0,
                usage=LlmUsage(),
            )

        def close(self) -> None:
            closed.append("closed")

    monkeypatch.setattr(runtime, "LlmService", _FakeLlmService)
    config: LlmConfig = runtime.palantir_llm_config(
        _catalog(),
        _ALIAS,
        enrollment_base_url=_ENROLLMENT,
        token=_TOKEN,
        max_retries=5,
    )

    runtime.probe_palantir_model(config)

    sent, request = seen[0]

    assert len(seen) == 1
    assert sent.max_retries == 0
    assert sent.max_output_tokens is not None
    assert sent.max_output_tokens <= 64
    assert sent.base_url == config.base_url
    assert len(request.messages) == 1
    assert closed == ["closed"]


def test_only_the_openai_compatible_engine_inherits_its_own_base_url() -> None:
    settings = Settings(_env_file=None, openai_compatible_base_url="https://compat.invalid")

    compatible: LlmConfig = runtime._llm_config(settings, _plan(llm_profile_id="openai_compatible"))
    anthropic: LlmConfig = runtime._llm_config(settings, _plan(llm_profile_id="anthropic"))

    assert compatible.base_url == "https://compat.invalid"
    assert anthropic.base_url is None
