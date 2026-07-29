from __future__ import annotations

import asyncio
import importlib.metadata
from collections.abc import AsyncIterator, Coroutine
from pathlib import Path
from types import SimpleNamespace

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
    VoiceInfo,
)
from anishift.services.tts.engines.edge import EdgeTtsEngine
from anishift.services.tts.engines.edge import patch as edge_patch
from anishift.services.tts.engines.edge.api_backend import EdgeApiBackend
from anishift.services.tts.engines.edge.constants import (
    EDGE_PROVIDER_MODEL_ID,
    MAREK_VOICE_ID,
    OUTPUT_FORMAT,
    SUPPORTED_EDGE_TTS_VERSION,
    ZOFIA_VOICE_ID,
)
from anishift.services.tts.engines.edge.patch import ensure_edge_quality_patch
from anishift.services.tts.engines.edge.types import (
    EdgeAttempt,
    EdgeAudioResponse,
    EdgePatchResult,
    EdgePatchStatus,
)

_OLD_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_OLD_BITRATE_ASSIGNMENT = "MP3_BITRATE_BPS = 48_000"
_NEW_BITRATE_ASSIGNMENT = "MP3_BITRATE_BPS = 96_000"


class FakeCancellation:
    is_cancelled = False
    generation = 1

    async def wait(self) -> None:
        return None

    def can_commit(self, generation: int) -> bool:
        return generation == self.generation and not self.is_cancelled


class FakeDistribution:
    def __init__(self, root: Path, version: str = SUPPORTED_EDGE_TTS_VERSION) -> None:
        self.version = version
        self._root = root

    def locate_file(self, path: object) -> Path:
        return self._root / str(path)


class FakeBackend:
    def __init__(self) -> None:
        self.attempts: list[EdgeAttempt] = []
        self.closed = False
        self.voices: tuple[VoiceInfo, ...] = (
            _voice(MAREK_VOICE_ID, "Male"),
            _voice(ZOFIA_VOICE_ID, "Female"),
        )

    async def synthesize_once(self, attempt: EdgeAttempt) -> EdgeAudioResponse:
        self.attempts.append(attempt)
        return EdgeAudioResponse(
            audio=b"edge-mp3",
            format=AudioFormat.MP3,
            request_time_ms=12.5,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        return self.voices

    async def close(self) -> None:
        self.closed = True


class EmptyCommunicate:
    def stream(self) -> AsyncIterator[dict[str, object]]:
        return _empty_stream()


class RuntimeFailureError(Exception):
    pass


def _run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


async def _empty_stream() -> AsyncIterator[dict[str, object]]:
    if False:
        yield {}


def _voice(voice_id: str, gender: str) -> VoiceInfo:
    return VoiceInfo(
        id=voice_id,
        label=voice_id,
        engine_id="edge",
        language="pl-PL",
        gender=gender,
    )


def _config(
    *,
    voice_id: str = MAREK_VOICE_ID,
    rate: str | None = None,
    volume: str | None = None,
    pitch: str | None = None,
) -> TtsConfig:
    return TtsConfig(
        engine_id="edge",
        provider_model_id=EDGE_PROVIDER_MODEL_ID,
        voice_id=voice_id,
        max_concurrency=8,
        queue_capacity=16,
        native_rate=rate,
        native_volume=volume,
        native_pitch=pitch,
    )


def _request(
    destination: Path,
    *,
    voice_id: str = MAREK_VOICE_ID,
    rate: str | None = None,
    volume: str | None = None,
    pitch: str | None = None,
) -> SynthesisRequest:
    return SynthesisRequest(
        request_id="speech-1",
        text="Zażółć gęślą jaźń",
        voice_id=voice_id,
        provider_model_id=EDGE_PROVIDER_MODEL_ID,
        native_rate=rate,
        native_volume=volume,
        native_pitch=pitch,
        options={},
        destination=destination,
        deadline_s=10.0,
    )


def _ready_patch(*, changed: bool = False) -> EdgePatchResult:
    return EdgePatchResult(
        status=EdgePatchStatus.READY,
        message="ready",
        detected_version=SUPPORTED_EDGE_TTS_VERSION,
        changed=changed,
    )


def _install_fake_distribution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str = SUPPORTED_EDGE_TTS_VERSION,
    output_format: str = _OLD_OUTPUT_FORMAT,
    bitrate_assignment: str = _OLD_BITRATE_ASSIGNMENT,
) -> tuple[Path, Path]:
    package_root = tmp_path / "site-packages"
    edge_root = package_root / "edge_tts"
    edge_root.mkdir(parents=True)
    communicate_path = edge_root / "communicate.py"
    constants_path = edge_root / "constants.py"
    communicate_path.write_text(
        f"""PAYLOAD = '"outputFormat":"{output_format}"'\r\n""",
        encoding="utf-8",
        newline="",
    )
    constants_path.write_text(
        f"{bitrate_assignment}\r\n",
        encoding="utf-8",
        newline="",
    )
    distribution = FakeDistribution(package_root, version)
    monkeypatch.setattr(
        importlib.metadata,
        "distribution",
        lambda name: distribution,
    )
    return communicate_path, constants_path


def test_quality_patch_updates_output_and_bitrate_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    communicate_path, constants_path = _install_fake_distribution(tmp_path, monkeypatch)

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.READY
    assert result.changed
    assert OUTPUT_FORMAT in communicate_path.read_text(encoding="utf-8")
    assert _OLD_OUTPUT_FORMAT not in communicate_path.read_text(encoding="utf-8")
    assert _NEW_BITRATE_ASSIGNMENT in constants_path.read_text(encoding="utf-8")
    assert _OLD_BITRATE_ASSIGNMENT not in constants_path.read_text(encoding="utf-8")
    assert not tuple(communicate_path.parent.glob(".*.tmp"))


def test_quality_patch_accepts_already_patched_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    communicate_path, constants_path = _install_fake_distribution(
        tmp_path,
        monkeypatch,
        output_format=OUTPUT_FORMAT,
        bitrate_assignment=_NEW_BITRATE_ASSIGNMENT,
    )
    before = (communicate_path.read_bytes(), constants_path.read_bytes())

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.READY
    assert not result.changed
    assert (communicate_path.read_bytes(), constants_path.read_bytes()) == before


@pytest.mark.parametrize(
    ("output_format", "bitrate_assignment"),
    [
        (OUTPUT_FORMAT, _OLD_BITRATE_ASSIGNMENT),
        (_OLD_OUTPUT_FORMAT, _NEW_BITRATE_ASSIGNMENT),
    ],
)
def test_quality_patch_repairs_known_partial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_format: str,
    bitrate_assignment: str,
) -> None:
    communicate_path, constants_path = _install_fake_distribution(
        tmp_path,
        monkeypatch,
        output_format=output_format,
        bitrate_assignment=bitrate_assignment,
    )

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.READY
    assert result.changed
    assert OUTPUT_FORMAT in communicate_path.read_text(encoding="utf-8")
    assert _NEW_BITRATE_ASSIGNMENT in constants_path.read_text(encoding="utf-8")


def test_quality_patch_rejects_unknown_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    communicate_path, constants_path = _install_fake_distribution(
        tmp_path,
        monkeypatch,
        version="99.0.0",
    )

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.UNSUPPORTED_VERSION
    assert "99.0.0" in result.message
    assert SUPPORTED_EDGE_TTS_VERSION in result.message
    assert _OLD_OUTPUT_FORMAT in communicate_path.read_text(encoding="utf-8")
    assert _OLD_BITRATE_ASSIGNMENT in constants_path.read_text(encoding="utf-8")


def test_quality_patch_rejects_unknown_source_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    communicate_path, constants_path = _install_fake_distribution(tmp_path, monkeypatch)
    communicate_path.write_text("unknown = True\n", encoding="utf-8")
    constants_path.write_text("UNKNOWN = 1\n", encoding="utf-8")

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.UNKNOWN_LAYOUT
    assert not result.changed


def test_quality_patch_reports_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_distribution(name: str) -> None:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "distribution", missing_distribution)

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.PACKAGE_MISSING
    assert "reinstall" in result.message


def test_quality_patch_reports_read_only_installation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_distribution(tmp_path, monkeypatch)

    def deny_replace(source: Path, destination: Path) -> None:
        raise PermissionError

    monkeypatch.setattr(edge_patch, "_replace_file", deny_replace)

    result = ensure_edge_quality_patch()

    assert result.status is EdgePatchStatus.READ_ONLY
    assert "read-only" in result.message


def test_engine_patches_before_loading_runtime() -> None:
    events: list[str] = []
    backend = FakeBackend()

    def patcher() -> EdgePatchResult:
        events.append("patch")
        return _ready_patch()

    def backend_factory() -> FakeBackend:
        events.append("import")
        return backend

    engine = EdgeTtsEngine(
        _config(),
        patcher=patcher,
        backend_factory=backend_factory,
    )

    assert isinstance(engine, TtsEngine)
    assert events == ["patch", "import"]


@pytest.mark.parametrize("voice_id", [MAREK_VOICE_ID, ZOFIA_VOICE_ID])
def test_engine_synthesizes_selected_polish_voice_with_native_options(
    tmp_path: Path,
    voice_id: str,
) -> None:
    backend = FakeBackend()
    engine = EdgeTtsEngine(
        _config(
            voice_id=voice_id,
            rate="-10%",
            volume="+5%",
            pitch="+12Hz",
        ),
        patcher=_ready_patch,
        backend_factory=lambda: backend,
    )
    destination = tmp_path / "clip.mp3"

    result = _run(
        engine.synthesize(
            _request(
                destination,
                voice_id=voice_id,
                rate="-10%",
                volume="+5%",
                pitch="+12Hz",
            ),
            cancel=FakeCancellation(),
        ),
    )
    _run(engine.close())

    assert backend.attempts == [
        EdgeAttempt(
            text="Zażółć gęślą jaźń",
            voice_id=voice_id,
            rate="-10%",
            volume="+5%",
            pitch="+12Hz",
            deadline_s=10.0,
        ),
    ]
    assert destination.read_bytes() == b"edge-mp3"
    assert result.format is AudioFormat.MP3
    assert result.voice_id == voice_id
    assert backend.closed


def test_live_availability_distinguishes_missing_voice() -> None:
    backend = FakeBackend()
    backend.voices = (_voice(ZOFIA_VOICE_ID, "Female"),)
    engine = EdgeTtsEngine(
        _config(voice_id=MAREK_VOICE_ID),
        patcher=_ready_patch,
        backend_factory=lambda: backend,
    )

    availability = _run(engine.availability(live=True))
    _run(engine.close())

    assert availability.status is AvailabilityStatus.MISSING_VOICE
    assert MAREK_VOICE_ID in availability.message


def test_failed_patch_keeps_runtime_unloaded() -> None:
    backend_loads = 0

    def failed_patch() -> EdgePatchResult:
        return EdgePatchResult(
            status=EdgePatchStatus.UNSUPPORTED_VERSION,
            message="unsupported",
            detected_version="99",
            changed=False,
        )

    def backend_factory() -> FakeBackend:
        nonlocal backend_loads
        backend_loads += 1
        return FakeBackend()

    engine = EdgeTtsEngine(
        _config(),
        patcher=failed_patch,
        backend_factory=backend_factory,
    )

    with pytest.raises(TtsProviderUnavailableError, match="unsupported"):
        _run(engine.list_voices())

    assert backend_loads == 0
    assert not engine.is_available


def test_cancelled_request_never_reaches_runtime(tmp_path: Path) -> None:
    backend = FakeBackend()
    cancel = FakeCancellation()
    cancel.is_cancelled = True
    engine = EdgeTtsEngine(
        _config(),
        patcher=_ready_patch,
        backend_factory=lambda: backend,
    )

    with pytest.raises(TtsCancelledError, match="before request"):
        _run(engine.synthesize(_request(tmp_path / "clip.mp3"), cancel=cancel))

    assert not backend.attempts


def test_runtime_backend_rejects_empty_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    async def list_voices() -> list[dict[str, str]]:
        return []

    runtime = SimpleNamespace(
        Communicate=lambda *args, **kwargs: EmptyCommunicate(),
        list_voices=list_voices,
        exceptions=SimpleNamespace(
            NoAudioReceived=RuntimeFailureError,
            UnexpectedResponse=RuntimeFailureError,
            UnknownResponse=RuntimeFailureError,
            WebSocketError=RuntimeFailureError,
        ),
    )
    monkeypatch.setattr(
        "anishift.services.tts.engines.edge.api_backend.importlib.import_module",
        lambda name: runtime,
    )
    backend = EdgeApiBackend()

    with pytest.raises(TtsClipValidationError, match="no audio"):
        _run(
            backend.synthesize_once(
                EdgeAttempt(
                    text="Test",
                    voice_id=MAREK_VOICE_ID,
                    rate="+40%",
                    volume="+0%",
                    pitch="+0Hz",
                    deadline_s=10.0,
                ),
            ),
        )
