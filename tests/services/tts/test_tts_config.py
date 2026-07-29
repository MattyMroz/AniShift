from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace

import pytest

from anishift.errors import ErrorCode, FatalError, TransientError
from anishift.services.tts import (
    TtsAuthError,
    TtsCancelledError,
    TtsConfig,
    TtsConfigError,
    TtsInputError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
    TtsVoiceError,
)

BASE_CONFIG = TtsConfig(
    engine_id="elevenbytes",
    provider_model_id="eleven_multilingual_v2",
    voice_id="dallin",
    max_concurrency=12,
    queue_capacity=24,
)


@pytest.mark.parametrize(
    ("build_config", "field_name"),
    [
        pytest.param(
            lambda: replace(BASE_CONFIG, engine_id=""),
            "engine_id",
            id="empty-engine",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, provider_model_id=" "),
            "provider_model_id",
            id="empty-model",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, voice_id=""),
            "voice_id",
            id="empty-voice",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, max_concurrency=0),
            "max_concurrency",
            id="zero-concurrency",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, max_retries=-1),
            "max_retries",
            id="negative-retries",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, request_timeout_s=0),
            "request_timeout_s",
            id="zero-timeout",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, request_timeout_s=float("nan")),
            "request_timeout_s",
            id="nan-timeout",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, request_timeout_s=float("inf")),
            "request_timeout_s",
            id="infinite-timeout",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, shutdown_deadline_s=0),
            "shutdown_deadline_s",
            id="zero-shutdown",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, shutdown_deadline_s=float("nan")),
            "shutdown_deadline_s",
            id="nan-shutdown",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, shutdown_deadline_s=float("inf")),
            "shutdown_deadline_s",
            id="infinite-shutdown",
        ),
        pytest.param(
            lambda: replace(BASE_CONFIG, queue_capacity=0),
            "queue_capacity",
            id="zero-capacity",
        ),
    ],
)
def test_config_rejects_invalid_fields(
    build_config: Callable[[], TtsConfig],
    field_name: str,
) -> None:
    with pytest.raises(TtsConfigError) as exc_info:
        build_config()

    assert exc_info.value.context.code is ErrorCode.TTS_CONFIG_INVALID
    assert exc_info.value.context.details == {"field": field_name}


def test_config_is_frozen_slotted_and_hides_api_key() -> None:
    config = replace(BASE_CONFIG, elevenlabs_api_key="top-secret-key")

    assert "top-secret-key" not in repr(config)
    assert not hasattr(config, "__dict__")
    attribute_name = "engine_id"
    with pytest.raises(FrozenInstanceError):
        setattr(config, attribute_name, "edge")


def test_config_contains_only_synthesis_settings() -> None:
    config = BASE_CONFIG
    forbidden_fields = (
        "bitrate",
        "channel_policy",
        "codec",
        "gain_db",
        "output_path",
        "source_audio",
    )

    for field_name in forbidden_fields:
        assert not hasattr(config, field_name)


def test_error_taxonomy_distinguishes_fatal_and_transient_failures() -> None:
    fatal_errors = (
        TtsConfigError(),
        TtsAuthError(),
        TtsVoiceError(),
        TtsInputError(),
        TtsUnsupportedError(),
        TtsCancelledError(),
    )
    transient_errors = (
        TtsRateLimitError(retry_after_s=2.5),
        TtsTimeoutError(),
        TtsNetworkError(),
        TtsProviderUnavailableError(retry_after_s=5.0),
    )

    assert all(isinstance(error, FatalError) for error in fatal_errors)
    assert all(isinstance(error, TransientError) for error in transient_errors)
    assert transient_errors[0].retry_after_s == 2.5
    assert transient_errors[3].retry_after_s == 5.0
