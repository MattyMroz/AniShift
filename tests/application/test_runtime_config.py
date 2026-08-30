from __future__ import annotations

import threading
from typing import Any, cast

import pytest

from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.runtime import _audio_config, _LlmCompleter, _raise_translation_error, _tts_config
from anishift.config.settings import Settings
from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.types import AudioCodecProfile, TimelinePolicy
from anishift.services.llm import (
    LlmAuthError,
    LlmCancelledError,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequest,
    LlmRequestError,
    LlmResponse,
    LlmRole,
    LlmService,
    LlmTimeoutError,
    LlmUsage,
)
from anishift.services.translation.errors import (
    TranslationAuthError,
    TranslationContextLengthError,
    TranslationEngineError,
    TranslationError,
    TranslationQuotaError,
    TranslationRateLimitError,
)
from anishift.services.translation.protocols import LlmCompletionRequest
from anishift.services.tts.config import DEFAULT_RETRY_BACKOFF_SECONDS


def _snapshot(**overrides: Any) -> RunSettingsSnapshot:
    fields: dict[str, Any] = {
        "translation_profile_id": "llm",
        "translation_fallback_chain": (),
        "translation_max_retries": 3,
        "translation_concurrency": 2,
        "llm_profile_id": "gemini",
        "llm_max_concurrency": 2,
        "tts_profile_id": "elevenbytes",
        "tts_max_retries": 3,
        "tts_group_jobs": 2,
        "audio_profile_id": "eac3",
        "composition_profile_id": "default",
        "processing_order_policy": ProcessingOrderPolicy.READY_FIRST,
    }
    fields.update(overrides)
    return RunSettingsSnapshot(**fields)


def _plan(**overrides: Any) -> ExecutionPlan:
    return ExecutionPlan((), (), (), _snapshot(**overrides), ())


class _RecordingLlmService:
    def __init__(self) -> None:
        self.request: LlmRequest | None = None

    def complete(self, request: LlmRequest, *, cancel: threading.Event) -> LlmResponse:
        del cancel
        self.request = request
        return LlmResponse(
            text="result",
            engine_id="fake",
            provider_model_id="fake-model",
            finish_reason="stop",
            latency_ms=1.0,
            usage=LlmUsage(),
        )


def test_the_run_snapshot_becomes_the_speech_configuration() -> None:
    plan: ExecutionPlan = _plan(
        tts_model_id="run7",
        tts_voice_id="dallin",
        tts_request_concurrency=100,
        tts_native_rate="+10%",
        tts_native_volume="+0%",
        tts_native_pitch="-5Hz",
        tts_engine_options=(("endpoint", "primary"),),
    )

    config = _tts_config(Settings(_env_file=None, elevenlabs_api_key="unused-by-elevenbytes"), plan)

    assert config.engine_id == "elevenbytes"
    assert config.provider_model_id == "run7"
    assert config.voice_id == "dallin"
    assert config.max_concurrency == 100
    assert config.queue_capacity == 200
    assert config.max_retries == 3
    assert config.native_rate == "+10%"
    assert config.native_volume == "+0%"
    assert config.native_pitch == "-5Hz"
    assert config.engine_options == {"endpoint": "primary"}
    assert config.elevenlabs_api_key == "unused-by-elevenbytes"
    assert config.metadata_cache_root is not None
    assert config.metadata_cache_root.name == "config"


def test_llm_completer_preserves_system_and_separate_user_parts() -> None:
    service = _RecordingLlmService()
    completer = _LlmCompleter(cast("LlmService", service), threading.Event())

    result = completer.complete(
        LlmCompletionRequest(
            system="system",
            user_parts=("translation", "style", '{"subtitles":[]}'),
        )
    )

    assert result.text == "result"
    assert service.request is not None
    assert tuple(message.role for message in service.request.messages) == (
        LlmRole.SYSTEM,
        LlmRole.USER,
    )
    assert tuple(part.text for part in service.request.messages[0].parts) == ("system",)
    assert tuple(part.text for part in service.request.messages[1].parts) == (
        "translation",
        "style",
        '{"subtitles":[]}',
    )


def test_the_elevenbytes_profile_keeps_its_own_deadline_and_retry_delays() -> None:
    config = _tts_config(Settings(_env_file=None), _plan())

    assert config.request_timeout_s == 45.0
    assert config.retry_backoff_seconds == (5.0, 10.0, 15.0, 30.0)


def test_the_sapi_profile_uses_its_own_short_request_deadline() -> None:
    config = _tts_config(Settings(_env_file=None), _plan(tts_profile_id="sapi", tts_model_id="sapi5"))

    assert config.request_timeout_s == 10.0
    assert config.retry_backoff_seconds == DEFAULT_RETRY_BACKOFF_SECONDS


def test_a_neutral_profile_falls_back_to_the_shared_deadline_and_delays() -> None:
    config = _tts_config(Settings(_env_file=None), _plan(tts_profile_id="edge"))

    assert config.request_timeout_s == 30.0
    assert config.retry_backoff_seconds == DEFAULT_RETRY_BACKOFF_SECONDS


@pytest.mark.parametrize("vpn_enabled", [True, False])
def test_only_the_elevenbytes_vpn_disables_the_speech_scheduler_deadline(*, vpn_enabled: bool) -> None:
    config = _tts_config(Settings(_env_file=None), _plan(tts_vpn_enabled=vpn_enabled))

    assert config.elevenbytes_vpn_enabled is vpn_enabled
    assert config.scheduler_timeout_enabled is not vpn_enabled


@pytest.mark.parametrize("profile_id", ["sapi", "edge"])
def test_another_profile_keeps_the_scheduler_deadline_whatever_the_vpn_preference(profile_id: str) -> None:
    config = _tts_config(Settings(_env_file=None), _plan(tts_profile_id=profile_id, tts_vpn_enabled=True))

    assert config.scheduler_timeout_enabled


def test_a_single_worker_still_receives_a_usable_queue_capacity() -> None:
    config = _tts_config(Settings(_env_file=None), _plan(tts_request_concurrency=1))

    assert config.max_concurrency == 1
    assert config.queue_capacity == 2


def test_the_run_snapshot_becomes_the_audio_configuration() -> None:
    plan: ExecutionPlan = _plan(
        audio_output_profile="aac",
        audio_bitrate="192k",
        narrator_mix_base_gain_db=7.0,
        voice_mix_offset_db=-2.0,
        original_gain_db=-1.5,
    )

    config = _audio_config(plan)

    assert config.codec_profile is AudioCodecProfile.AAC
    assert config.bitrate == "192k"
    assert config.narrator_mix_base_gain_db == 7.0
    assert config.voice_mix_offset_db == -2.0
    assert config.original_gain_db == -1.5
    assert config.timeline_policy is TimelinePolicy.SERIALIZE


@pytest.mark.parametrize(
    ("llm_error", "expected"),
    [
        (LlmCancelledError("cancelled"), TranslationError),
        (LlmContextLengthError("context"), TranslationContextLengthError),
        (LlmAuthError("auth"), TranslationAuthError),
        (LlmRateLimitError("rate"), TranslationRateLimitError),
        (LlmQuotaError("quota"), TranslationQuotaError),
        (LlmPaymentError("payment"), TranslationQuotaError),
        (LlmTimeoutError("timeout"), TranslationEngineError),
        (LlmProviderUnavailableError("unavailable"), TranslationEngineError),
        (LlmConfigError("config"), TranslationEngineError),
        (LlmModelError("model"), TranslationEngineError),
        (LlmOutputBlockedError("blocked"), TranslationEngineError),
        (LlmRequestError("request"), TranslationEngineError),
    ],
)
def test_a_provider_failure_becomes_its_translation_equivalent(
    llm_error: LlmError,
    expected: type[Exception],
) -> None:
    with pytest.raises(expected):
        _raise_translation_error(llm_error)


def test_a_rate_limit_is_never_reported_as_an_exhausted_quota() -> None:
    with pytest.raises(TranslationRateLimitError) as raised:
        _raise_translation_error(LlmRateLimitError("rate"))

    assert not isinstance(raised.value, TranslationQuotaError)


def test_the_translation_failure_keeps_the_structured_provider_context() -> None:
    context = ErrorContext(code=ErrorCode.LLM_AUTH_FAILED, message="safe")

    with pytest.raises(TranslationAuthError) as raised:
        _raise_translation_error(LlmAuthError(context=context))

    assert raised.value.context is context
    assert isinstance(raised.value.__cause__, LlmAuthError)
