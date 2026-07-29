from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from anishift.services.tts import (
    AudioFormat,
    AvailabilityStatus,
    SynthesisRequest,
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfig,
    TtsEngine,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
)
from anishift.services.tts.engines.elevenbytes import ElevenBytesConfig, ElevenBytesTtsEngine
from anishift.services.tts.engines.elevenbytes.api_backend import ElevenBytesApiBackend
from anishift.services.tts.engines.elevenbytes.constants import (
    DALLIN_VOICE_ID,
    PUBLIC_PROXY_TOKEN,
    REQUEST_HEADERS,
)


class FakeCancellation:
    is_cancelled = False
    generation = 1

    async def wait(self) -> None:
        return None

    def can_commit(self, generation: int) -> bool:
        return generation == self.generation and not self.is_cancelled


def _run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


def _mp3_bytes() -> bytes:
    return b"\xff\xfb\x90\x00" + b"\x00" * 1020


def _config(
    *,
    variant: str = "run6",
    voice_id: str = "dallin",
    options: dict[str, str | int | float | bool | None] | None = None,
) -> TtsConfig:
    return TtsConfig(
        engine_id="elevenbytes",
        provider_model_id=variant,
        voice_id=voice_id,
        max_concurrency=12,
        queue_capacity=24,
        engine_options=options or {},
    )


def _request(
    destination: Path,
    *,
    variant: str = "run6",
    voice_id: str = "dallin",
    options: dict[str, str | int | float | bool | None] | None = None,
) -> SynthesisRequest:
    return SynthesisRequest(
        request_id="speech-1",
        text="Zażółć gęślą jaźń",
        voice_id=voice_id,
        provider_model_id=variant,
        native_rate=None,
        native_volume=None,
        native_pitch=None,
        options=options or {},
        destination=destination,
        deadline_s=10.0,
    )


def _engine(
    config: TtsConfig,
    handler: httpx.AsyncBaseTransport,
) -> ElevenBytesTtsEngine:
    provider_config = ElevenBytesConfig.from_tts_config(config)
    backend = ElevenBytesApiBackend(provider_config, transport=handler)
    return ElevenBytesTtsEngine(config, backend=backend)


def test_run6_sends_exact_contract_without_v3_fields(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=_mp3_bytes(), headers={"Content-Type": "audio/mpeg"})

    engine = _engine(_config(), httpx.MockTransport(handler))
    destination = tmp_path / "clip.mp3"

    result = _run(engine.synthesize(_request(destination), cancel=FakeCancellation()))
    _run(engine.close())

    assert len(requests) == 1
    assert isinstance(engine, TtsEngine)
    assert str(requests[0].url) == "https://teamsp.org/xi/run6.php"
    assert parse_qs(requests[0].content.decode()) == {
        "key": [PUBLIC_PROXY_TOKEN],
        "text": ["Zażółć gęślą jaźń"],
        "voice": [DALLIN_VOICE_ID],
    }
    assert all(requests[0].headers[name] == value for name, value in REQUEST_HEADERS.items())
    assert destination.read_bytes() == _mp3_bytes()
    assert result.format is AudioFormat.MP3
    assert result.provider_model_id == "run6"
    assert result.voice_id == DALLIN_VOICE_ID


def test_run7_uses_separate_endpoint_and_exact_voice_settings(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    options: dict[str, str | int | float | bool | None] = {
        "stability": 0.25,
        "similarity_boost": 0.8,
        "style": 0.1,
        "use_speaker_boost": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=_mp3_bytes(), headers={"Content-Type": "audio/mpeg"})

    engine = _engine(_config(variant="run7", options=options), httpx.MockTransport(handler))

    _run(
        engine.synthesize(
            _request(tmp_path / "clip.mp3", variant="run7", options=options),
            cancel=FakeCancellation(),
        ),
    )
    voices = _run(engine.list_voices())
    _run(engine.close())

    assert str(requests[0].url) == "https://teamsp.org/xi/run7.php"
    assert parse_qs(requests[0].content.decode()) == {
        "key": [PUBLIC_PROXY_TOKEN],
        "similarity_boost": ["0.8"],
        "stability": ["0.25"],
        "style": ["0.1"],
        "text": ["Zażółć gęślą jaźń"],
        "use_speaker_boost": ["false"],
        "voice": [DALLIN_VOICE_ID],
    }
    assert voices[0].experimental


def test_custom_voice_id_is_preserved(tmp_path: Path) -> None:
    payloads: list[dict[str, list[str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(parse_qs(request.content.decode()))
        return httpx.Response(200, content=_mp3_bytes(), headers={"Content-Type": "audio/mpeg"})

    engine = _engine(_config(voice_id="custom-provider-id"), httpx.MockTransport(handler))

    result = _run(
        engine.synthesize(
            _request(tmp_path / "clip.mp3", voice_id="custom-provider-id"),
            cancel=FakeCancellation(),
        ),
    )
    _run(engine.close())

    assert payloads[0]["voice"] == ["custom-provider-id"]
    assert result.voice_id == "custom-provider-id"


def test_run6_rejects_run7_options_before_network() -> None:
    with pytest.raises(TtsUnsupportedError, match="run6"):
        ElevenBytesConfig.from_tts_config(_config(options={"stability": 0.5}))


def test_run7_rejects_out_of_range_voice_setting() -> None:
    with pytest.raises(TtsUnsupportedError, match="between 0 and 1"):
        ElevenBytesConfig.from_tts_config(
            _config(variant="run7", options={"stability": 1.5}),
        )


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (403, TtsProviderUnavailableError),
        (500, TtsProviderUnavailableError),
        (429, TtsRateLimitError),
    ],
)
def test_http_failures_are_typed_without_internal_retry(
    tmp_path: Path,
    status_code: int,
    expected_error: type[Exception],
) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code, headers={"Retry-After": "7"})

    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(expected_error):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))
    _run(engine.close())

    assert call_count == 1


def test_retry_after_is_exposed_to_shared_scheduler(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "7.5"})

    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(TtsRateLimitError) as exc_info:
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))
    _run(engine.close())

    assert exc_info.value.retry_after_s == 7.5


@pytest.mark.parametrize(
    ("content", "content_type"),
    [
        (b"", "audio/mpeg"),
        (b"<html>not audio</html>" * 100, "text/html"),
        (b"x" * 2048, "audio/mpeg"),
    ],
)
def test_invalid_provider_audio_is_rejected(
    tmp_path: Path,
    content: bytes,
    content_type: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"Content-Type": content_type})

    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(TtsClipValidationError):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))
    _run(engine.close())

    assert not (tmp_path / "clip.mp3").exists()


def test_timeout_is_single_typed_attempt(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("timeout", request=request)

    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(TtsTimeoutError, match="timed out"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=FakeCancellation()))
    _run(engine.close())

    assert call_count == 1


def test_cancelled_request_does_not_call_provider(tmp_path: Path) -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, content=_mp3_bytes(), headers={"Content-Type": "audio/mpeg"})

    cancel = FakeCancellation()
    cancel.is_cancelled = True
    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(TtsCancelledError, match="before request"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=cancel))
    _run(engine.close())

    assert call_count == 0


def test_cancelled_late_result_is_not_written(tmp_path: Path) -> None:
    cancel = FakeCancellation()

    def handler(request: httpx.Request) -> httpx.Response:
        cancel.is_cancelled = True
        return httpx.Response(200, content=_mp3_bytes(), headers={"Content-Type": "audio/mpeg"})

    destination = tmp_path / "clip.mp3"
    engine = _engine(_config(), httpx.MockTransport(handler))

    with pytest.raises(TtsCancelledError, match="before write"):
        _run(engine.synthesize(_request(destination), cancel=cancel))
    _run(engine.close())

    assert not destination.exists()


def test_live_availability_reports_proxy_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    engine = _engine(_config(), httpx.MockTransport(handler))

    availability = _run(engine.availability(live=True))
    _run(engine.close())

    assert availability.status is AvailabilityStatus.SERVICE_UNAVAILABLE
    assert not engine.is_available
