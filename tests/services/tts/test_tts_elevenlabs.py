from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from anishift.services.tts import (
    AudioFormat,
    AvailabilityStatus,
    SynthesisRequest,
    TtsAuthError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfig,
    TtsConfigError,
    TtsEngine,
    TtsInputError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
    TtsVoiceError,
    VoiceInfo,
)
from anishift.services.tts.engines.elevenlabs import (
    ElevenLabsBackend,
    ElevenLabsConfig,
    ElevenLabsSdkBackend,
    ElevenLabsTtsEngine,
)
from anishift.services.tts.engines.elevenlabs import api_backend as elevenlabs_backend
from anishift.services.tts.engines.elevenlabs.api_backend import ElevenLabsApiError
from anishift.services.tts.engines.elevenlabs.constants import DEFAULT_MODEL_ID
from anishift.services.tts.engines.elevenlabs.options import ElevenLabsAttempt


class FakeCancellation:
    is_cancelled = False
    generation = 1

    async def wait(self) -> None:
        return None

    def can_commit(self, generation: int) -> bool:
        return generation == self.generation and not self.is_cancelled


class FakeBackend:
    def __init__(self, audio: bytes | None = None) -> None:
        self.audio = audio or _mp3_bytes()
        self.attempts: list[ElevenLabsAttempt] = []
        self.voice_calls = 0
        self.closed = False
        self.cancel: FakeCancellation | None = None
        self.voices = (
            _voice("voice-selected", "Selected"),
            _voice("voice-custom", "Custom"),
        )

    async def synthesize_once(self, attempt: ElevenLabsAttempt) -> bytes:
        self.attempts.append(attempt)
        if self.cancel is not None:
            self.cancel.is_cancelled = True
        return self.audio

    async def list_voices_once(self, *, deadline_s: float) -> tuple[VoiceInfo, ...]:
        self.voice_calls += 1
        return self.voices

    async def close(self) -> None:
        self.closed = True


class FakeApiError(Exception):
    def __init__(
        self,
        status_code: int | None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers


class FakeTextToSpeechClient:
    def __init__(
        self,
        *,
        chunks: tuple[object, ...] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks if chunks is not None else (_mp3_bytes(),)
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def convert(
        self,
        voice_id: str,
        **kwargs: object,
    ) -> AsyncIterator[bytes]:
        self.calls.append((voice_id, kwargs))
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[bytes]:
        if self.error is not None:
            raise self.error
        for chunk in self.chunks:
            yield cast("bytes", chunk)


class FakeVoicesClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses: list[object] = [
            SimpleNamespace(
                voices=[
                    SimpleNamespace(
                        voice_id="voice-selected",
                        name="Selected",
                        labels={"gender": "female", "language": "pl"},
                    ),
                ],
            ),
        ]

    async def search(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeSdkClient:
    def __init__(
        self,
        text_to_speech: FakeTextToSpeechClient,
        voices: FakeVoicesClient | None = None,
    ) -> None:
        self.text_to_speech = text_to_speech
        self.voices = voices or FakeVoicesClient()


def _run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


def _mp3_bytes() -> bytes:
    return b"\xff\xfb\x90\x00" + b"\x00" * 1020


def _wav_bytes() -> bytes:
    return b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + b"\x00" * 36


def _opus_bytes() -> bytes:
    return b"OggS" + b"\x00" * 100


def _voice(voice_id: str, label: str) -> VoiceInfo:
    return VoiceInfo(
        id=voice_id,
        label=label,
        engine_id="elevenlabs",
        language="pl",
    )


def _config(
    *,
    api_key: str = "secret-elevenlabs-key",
    model_id: str = DEFAULT_MODEL_ID,
    voice_id: str = "voice-selected",
    options: dict[str, str | int | float | bool | None] | None = None,
    metadata_cache_root: Path | None = None,
) -> TtsConfig:
    return TtsConfig(
        engine_id="elevenlabs",
        provider_model_id=model_id,
        voice_id=voice_id,
        max_concurrency=4,
        queue_capacity=8,
        engine_options=options or {},
        elevenlabs_api_key=api_key,
        metadata_cache_root=metadata_cache_root,
    )


def _request(
    destination: Path,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    voice_id: str = "voice-selected",
    options: dict[str, str | int | float | bool | None] | None = None,
) -> SynthesisRequest:
    return SynthesisRequest(
        request_id="speech-1",
        text="Zażółć gęślą jaźń",
        voice_id=voice_id,
        provider_model_id=model_id,
        native_rate=None,
        native_volume=None,
        native_pitch=None,
        options=options or {},
        destination=destination,
        deadline_s=10.2,
    )


def _runtime_backend(
    config: TtsConfig,
    text_client: FakeTextToSpeechClient,
    *,
    voices_client: FakeVoicesClient | None = None,
    settings_calls: list[dict[str, object]] | None = None,
) -> ElevenLabsSdkBackend:
    provider_config = ElevenLabsConfig.from_tts_config(config)
    recorded_settings: list[dict[str, object]] = settings_calls if settings_calls is not None else []

    def voice_settings_factory(**kwargs: object) -> object:
        recorded_settings.append(kwargs)
        return kwargs

    client = FakeSdkClient(text_client, voices_client)
    runtime = elevenlabs_backend._SdkRuntime(
        client=cast("elevenlabs_backend._SdkClient", client),
        voice_settings_factory=voice_settings_factory,
        api_error_type=FakeApiError,
        http_client=None,
    )
    return ElevenLabsSdkBackend(
        provider_config,
        runtime_factory=lambda _: runtime,
    )


def test_missing_key_is_visible_without_loading_sdk(tmp_path: Path) -> None:
    backend = cast("ElevenLabsBackend", FakeBackend())
    engine = ElevenLabsTtsEngine(
        _config(api_key=""),
        backend=backend,
        sdk_probe=lambda: True,
    )

    availability = _run(engine.availability())
    with pytest.raises(TtsAuthError, match="key is missing"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))

    assert availability.status is AvailabilityStatus.MISSING_KEY
    assert not engine.is_available


def test_missing_sdk_is_reported_before_provider_call(tmp_path: Path) -> None:
    backend = FakeBackend()
    engine = ElevenLabsTtsEngine(
        _config(),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: False,
    )

    with pytest.raises(TtsProviderUnavailableError, match="not installed"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))

    assert _run(engine.availability()).status is AvailabilityStatus.MISSING_BINARY
    assert not backend.attempts


def test_sdk_runtime_is_lazy_until_first_provider_call(tmp_path: Path) -> None:
    runtime_loads = 0
    text_client = FakeTextToSpeechClient()
    provider_config = ElevenLabsConfig.from_tts_config(_config())
    runtime = elevenlabs_backend._SdkRuntime(
        client=cast("elevenlabs_backend._SdkClient", FakeSdkClient(text_client)),
        voice_settings_factory=lambda **kwargs: kwargs,
        api_error_type=FakeApiError,
        http_client=None,
    )

    def runtime_factory(config: ElevenLabsConfig) -> elevenlabs_backend._SdkRuntime:
        nonlocal runtime_loads
        runtime_loads += 1
        return runtime

    backend = ElevenLabsSdkBackend(provider_config, runtime_factory=runtime_factory)
    engine = ElevenLabsTtsEngine(_config(), backend=backend, sdk_probe=lambda: True)

    assert runtime_loads == 0

    _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))

    assert runtime_loads == 1


def test_custom_model_voice_settings_and_output_token_reach_backend(tmp_path: Path) -> None:
    options: dict[str, str | int | float | bool | None] = {
        "output_format": "opus_48000_96",
        "similarity_boost": 0.8,
        "speed": 0.9,
        "stability": 0.3,
        "style": 0.2,
        "use_speaker_boost": False,
    }
    backend = FakeBackend(_opus_bytes())
    engine = ElevenLabsTtsEngine(
        _config(model_id="custom_model_v1", voice_id="custom_voice_42", options=options),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )
    destination = tmp_path / "clip.opus"

    result = _run(
        engine.synthesize(
            _request(
                destination,
                model_id="custom_model_v1",
                voice_id="custom_voice_42",
                options=options,
            ),
            cancel=FakeCancellation(),
        ),
    )

    assert result.format is AudioFormat.OPUS
    assert result.provider_model_id == "custom_model_v1"
    assert result.voice_id == "custom_voice_42"
    assert backend.attempts[0].output_format == "opus_48000_96"
    assert backend.attempts[0].voice_settings.speed == 0.9
    assert destination.read_bytes() == _opus_bytes()


@pytest.mark.parametrize(
    ("options", "match"),
    [
        ({"stability": -0.1}, "between 0.0 and 1.0"),
        ({"speed": 1.3}, "between 0.7 and 1.2"),
        ({"use_speaker_boost": "yes"}, "must be boolean"),
        ({"output_format": "pcm_44100"}, "Unsupported"),
        ({"unknown": 1}, "Unsupported"),
    ],
)
def test_invalid_options_are_rejected_before_provider_call(
    options: dict[str, str | int | float | bool | None],
    match: str,
) -> None:
    with pytest.raises((TtsConfigError, TtsUnsupportedError), match=match):
        ElevenLabsConfig.from_tts_config(_config(options=options))


def test_sdk_joins_response_iterator_and_disables_internal_retry(tmp_path: Path) -> None:
    chunks: tuple[object, ...] = (b"\xff\xfb", b"\x90\x00", b"\x00" * 1020)
    text_client = FakeTextToSpeechClient(chunks=chunks)
    settings_calls: list[dict[str, object]] = []
    config = _config()
    backend = _runtime_backend(config, text_client, settings_calls=settings_calls)
    engine = ElevenLabsTtsEngine(config, backend=backend, sdk_probe=lambda: True)
    destination = tmp_path / "clip.mp3"

    _run(engine.synthesize(_request(destination), cancel=FakeCancellation()))

    voice_id, kwargs = text_client.calls[0]
    assert len(text_client.calls) == 1
    assert voice_id == "voice-selected"
    assert kwargs["model_id"] == DEFAULT_MODEL_ID
    assert kwargs["output_format"] == "mp3_44100_128"
    assert kwargs["request_options"] == {
        "max_retries": 0,
        "timeout_in_seconds": 11,
    }
    assert settings_calls == [
        {
            "similarity_boost": 0.75,
            "speed": 1.0,
            "stability": 0.5,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    ]
    assert destination.read_bytes() == b"".join(cast("tuple[bytes, ...]", chunks))


@pytest.mark.parametrize(
    ("chunks", "expected_error"),
    [
        ((), TtsClipValidationError),
        ((b"",), TtsClipValidationError),
        ((b"<html>failure</html>",), TtsClipValidationError),
        (("not-bytes",), TtsClipValidationError),
    ],
)
def test_invalid_response_iterator_never_writes_output(
    tmp_path: Path,
    chunks: tuple[object, ...],
    expected_error: type[Exception],
) -> None:
    text_client = FakeTextToSpeechClient(chunks=chunks)
    config = _config()
    engine = ElevenLabsTtsEngine(
        config,
        backend=_runtime_backend(config, text_client),
        sdk_probe=lambda: True,
    )
    destination = tmp_path / "clip.mp3"

    with pytest.raises(expected_error):
        _run(engine.synthesize(_request(destination), cancel=FakeCancellation()))

    assert not destination.exists()


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (400, TtsInputError),
        (401, TtsAuthError),
        (403, TtsAuthError),
        (404, TtsVoiceError),
        (429, TtsRateLimitError),
        (500, TtsProviderUnavailableError),
        (503, TtsProviderUnavailableError),
    ],
)
def test_sdk_http_errors_are_typed_without_internal_retry(
    tmp_path: Path,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    text_client = FakeTextToSpeechClient(
        error=FakeApiError(status_code, headers={"Retry-After": "7.5"}),
    )
    config = _config()
    engine = ElevenLabsTtsEngine(
        config,
        backend=_runtime_backend(config, text_client),
        sdk_probe=lambda: True,
    )

    with pytest.raises(expected_error) as exc_info:
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))

    assert len(text_client.calls) == 1
    if isinstance(exc_info.value, (TtsRateLimitError, TtsProviderUnavailableError)):
        assert exc_info.value.retry_after_s == 7.5


def test_sdk_timeout_is_one_typed_attempt(tmp_path: Path) -> None:
    request = httpx.Request("POST", "https://api.elevenlabs.io/v1/text-to-speech/voice")
    text_client = FakeTextToSpeechClient(error=httpx.ReadTimeout("timeout", request=request))
    config = _config()
    engine = ElevenLabsTtsEngine(
        config,
        backend=_runtime_backend(config, text_client),
        sdk_probe=lambda: True,
    )

    with pytest.raises(TtsTimeoutError, match="timed out"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))

    assert len(text_client.calls) == 1


def test_voice_list_is_normalized_and_cached_with_ttl() -> None:
    clock = 100.0
    voices_client = FakeVoicesClient()
    voices_client.responses.append(voices_client.responses[0])
    text_client = FakeTextToSpeechClient()
    config = _config()
    backend = _runtime_backend(config, text_client, voices_client=voices_client)
    engine = ElevenLabsTtsEngine(
        config,
        backend=backend,
        sdk_probe=lambda: True,
        clock=lambda: clock,
    )

    first = _run(engine.list_voices())
    second = _run(engine.list_voices())
    clock = 401.0
    third = _run(engine.list_voices())

    assert first == second == third
    assert first[0].id == "voice-selected"
    assert first[0].gender == "female"
    assert first[0].language == "pl"
    assert len(voices_client.calls) == 2
    assert all(call["request_options"] == {"max_retries": 0, "timeout_in_seconds": 30} for call in voices_client.calls)


def test_voice_list_follows_sdk_pagination_without_retry() -> None:
    page_cursor = "page-" + str(2)
    voices_client = FakeVoicesClient()
    voices_client.responses = [
        SimpleNamespace(
            voices=[SimpleNamespace(voice_id="voice-1", name="One", labels={})],
            has_more=True,
            next_page_token=page_cursor,
        ),
        SimpleNamespace(
            voices=[SimpleNamespace(voice_id="voice-2", name="Two", labels={})],
            has_more=False,
            next_page_token=None,
        ),
    ]
    config = _config()
    backend = _runtime_backend(
        config,
        FakeTextToSpeechClient(),
        voices_client=voices_client,
    )
    engine = ElevenLabsTtsEngine(config, backend=backend, sdk_probe=lambda: True)

    voices = _run(engine.list_voices())

    assert tuple(voice.id for voice in voices) == ("voice-1", "voice-2")
    assert voices_client.calls[0]["next_page_token"] is None
    assert voices_client.calls[1]["next_page_token"] == page_cursor
    assert all(call["request_options"] == {"max_retries": 0, "timeout_in_seconds": 30} for call in voices_client.calls)


def test_voice_list_cache_persists_without_secret(
    tmp_path: Path,
) -> None:
    wall_clock = 1_000.0
    config = _config(metadata_cache_root=tmp_path)
    first_backend = FakeBackend()
    first = ElevenLabsTtsEngine(
        config,
        backend=cast("ElevenLabsBackend", first_backend),
        sdk_probe=lambda: True,
        wall_clock=lambda: wall_clock,
    )

    expected = _run(first.list_voices())

    cache_path = tmp_path / "elevenlabs-voices.json"
    second_backend = FakeBackend()
    second = ElevenLabsTtsEngine(
        config,
        backend=cast("ElevenLabsBackend", second_backend),
        sdk_probe=lambda: True,
        wall_clock=lambda: wall_clock + 1.0,
    )

    assert _run(second.list_voices()) == expected
    assert second_backend.voice_calls == 0
    assert config.elevenlabs_api_key not in cache_path.read_text(encoding="utf-8")


def test_persisted_voice_cache_keeps_elapsed_ttl(
    tmp_path: Path,
) -> None:
    config = _config(metadata_cache_root=tmp_path)
    first = ElevenLabsTtsEngine(
        config,
        backend=cast("ElevenLabsBackend", FakeBackend()),
        sdk_probe=lambda: True,
        wall_clock=lambda: 1_000.0,
    )
    _run(first.list_voices())
    monotonic = 500.0
    backend = FakeBackend()
    second = ElevenLabsTtsEngine(
        config,
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
        clock=lambda: monotonic,
        wall_clock=lambda: 1_299.0,
    )

    _run(second.list_voices())
    monotonic = 502.0
    _run(second.list_voices())

    assert backend.voice_calls == 1


def test_concurrent_voice_lists_share_one_provider_request() -> None:
    backend = FakeBackend()
    engine = ElevenLabsTtsEngine(
        _config(),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )

    async def scenario() -> tuple[tuple[VoiceInfo, ...], ...]:
        return tuple(await asyncio.gather(*(engine.list_voices() for _ in range(4))))

    results = _run(scenario())

    assert all(result == results[0] for result in results)
    assert backend.voice_calls == 1


def test_live_availability_recovers_after_transient_failure() -> None:
    class RecoveringBackend(FakeBackend):
        async def list_voices_once(
            self,
            *,
            deadline_s: float,
        ) -> tuple[VoiceInfo, ...]:
            self.voice_calls += 1
            if self.voice_calls == 1:
                raise ElevenLabsApiError(status_code=503, headers={})
            return self.voices

    backend = RecoveringBackend()
    engine = ElevenLabsTtsEngine(
        _config(),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )

    first = _run(engine.availability(live=True))
    second = _run(engine.availability(live=True))

    assert first.status is AvailabilityStatus.SERVICE_UNAVAILABLE
    assert second.status is AvailabilityStatus.READY
    assert backend.voice_calls == 2


def test_closed_engine_never_returns_cached_voices() -> None:
    backend = FakeBackend()
    engine = ElevenLabsTtsEngine(
        _config(),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )
    _run(engine.list_voices())
    _run(engine.close())

    with pytest.raises(TtsProviderUnavailableError, match="closed"):
        _run(engine.list_voices())


def test_wav_output_uses_real_native_format(tmp_path: Path) -> None:
    options: dict[str, str | int | float | bool | None] = {"output_format": "wav_24000"}
    backend = FakeBackend(_wav_bytes())
    engine = ElevenLabsTtsEngine(
        _config(options=options),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )

    result = _run(
        engine.synthesize(
            _request(tmp_path / "clip.wav", options=options),
            cancel=FakeCancellation(),
        ),
    )

    assert result.format is AudioFormat.WAV
    assert engine.synthesis_profile.provider_output_id == "wav_24000"
    assert engine.synthesis_profile.provider_source_format is AudioFormat.WAV


def test_cancellation_prevents_request_and_late_write(tmp_path: Path) -> None:
    backend = FakeBackend()
    cancel = FakeCancellation()
    cancel.is_cancelled = True
    engine = ElevenLabsTtsEngine(
        _config(),
        backend=cast("ElevenLabsBackend", backend),
        sdk_probe=lambda: True,
    )

    with pytest.raises(TtsCancelledError, match="before request"):
        _run(engine.synthesize(_request(tmp_path / "early.mp3"), cancel=cancel))

    cancel.is_cancelled = False
    backend.cancel = cancel
    with pytest.raises(TtsCancelledError, match="before write"):
        _run(engine.synthesize(_request(tmp_path / "late.mp3"), cancel=cancel))

    assert len(backend.attempts) == 1
    assert not (tmp_path / "late.mp3").exists()


def test_secret_is_absent_from_repr_and_fingerprint() -> None:
    sensitive_value = "elevenlabs-secret-that-must-not-leak"
    config = _config(api_key=sensitive_value)
    provider_config = ElevenLabsConfig.from_tts_config(config)
    engine = ElevenLabsTtsEngine(
        config,
        backend=cast("ElevenLabsBackend", FakeBackend()),
        sdk_probe=lambda: True,
    )

    assert sensitive_value not in repr(config)
    assert sensitive_value not in repr(provider_config)
    assert sensitive_value not in repr(engine.synthesis_profile)
    assert isinstance(engine, TtsEngine)
