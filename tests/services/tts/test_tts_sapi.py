from __future__ import annotations

import asyncio
import io
import json
import wave
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.services.tts import (
    AudioFormat,
    AvailabilityStatus,
    ProcessArchitecture,
    SynthesisRequest,
    TtsCancellation,
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfig,
    TtsEngine,
    TtsInputError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
    TtsUnsupportedError,
)
from anishift.services.tts.engines.sapi import SapiTtsEngine
from anishift.services.tts.engines.sapi.config import SapiConfig
from anishift.services.tts.engines.sapi.protocol import SapiWorkerRequest
from anishift.services.tts.engines.sapi.service import SapiRuntime
from anishift.services.tts.engines.sapi.types import (
    SapiHost,
    SapiSynthesisResult,
    SapiVoiceRecord,
)
from anishift.services.tts.engines.sapi.worker import (
    SapiWorkerController,
    _ProcessFactory,
)
from anishift.services.tts.protocols import CancellationToken

type ResponseHandler = Callable[[dict[str, object]], bytes | None]


class FakeCancellation:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.is_cancelled = cancelled
        self.generation = 1
        self._event = asyncio.Event()
        if cancelled:
            self._event.set()

    async def wait(self) -> None:
        await self._event.wait()

    def can_commit(self, generation: int) -> bool:
        return generation == self.generation and not self.is_cancelled

    def cancel(self) -> None:
        self.is_cancelled = True
        self._event.set()


class FakeVoiceProbe:
    def __init__(
        self,
        voices: dict[ProcessArchitecture, tuple[SapiVoiceRecord, ...]],
    ) -> None:
        self._voices = voices
        self.calls: list[ProcessArchitecture] = []

    async def list_voices(
        self,
        host: SapiHost,
        worker_asset: Path,
        *,
        timeout_s: float,
    ) -> tuple[SapiVoiceRecord, ...]:
        assert worker_asset.is_file()
        assert timeout_s > 0
        self.calls.append(host.architecture)
        return self._voices.get(host.architecture, ())


class FakeController:
    def __init__(self, *, header_only: bool = False) -> None:
        self.header_only = header_only
        self.calls: list[tuple[str, str, Path]] = []
        self.closed = False

    async def synthesize(
        self,
        request_id: str,
        text: str,
        output_path: Path,
        *,
        deadline_s: float,
        cancel: CancellationToken,
    ) -> SapiSynthesisResult:
        assert deadline_s > 0
        assert not cancel.is_cancelled
        self.calls.append((request_id, text, output_path))
        output_path.write_bytes(_wav_bytes(header_only=self.header_only))
        return SapiSynthesisResult(
            request_id=request_id,
            output_path=output_path,
            request_time_ms=4.5,
        )

    async def close(self) -> None:
        self.closed = True


class QueueReader:
    def __init__(self) -> None:
        self._items: asyncio.Queue[bytes] = asyncio.Queue()

    async def readline(self) -> bytes:
        return await self._items.get()

    def feed(self, line: bytes) -> None:
        self._items.put_nowait(line)


class OversizedReader(QueueReader):
    async def readline(self) -> bytes:
        raise ValueError


class EmptyReader:
    async def readline(self) -> bytes:
        return b""


class FakeWriter:
    def __init__(
        self,
        process: FakeProcess,
        handler: ResponseHandler,
        *,
        broken: bool,
    ) -> None:
        self._process = process
        self._handler = handler
        self._broken = broken
        self._pending: deque[bytes] = deque()
        self.closed = False

    def write(self, data: bytes) -> None:
        if self._broken:
            raise BrokenPipeError
        self._pending.append(data)

    async def drain(self) -> None:
        raw: bytes = self._pending.popleft()
        payload = cast("dict[str, object]", json.loads(raw))
        response: bytes | None = self._handler(payload)
        if response is not None:
            self._process.stdout.feed(response)

    def close(self) -> None:
        self.closed = True
        self._process.finish(0)

    async def wait_closed(self) -> None:
        return None


class StubbornWriter(FakeWriter):
    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(
        self,
        handler: ResponseHandler,
        *,
        broken: bool = False,
        oversized: bool = False,
    ) -> None:
        self.stdout: QueueReader = OversizedReader() if oversized else QueueReader()
        self.stderr = EmptyReader()
        self.returncode: int | None = None
        self._finished = asyncio.Event()
        self.stdin = FakeWriter(self, handler, broken=broken)
        self.killed = False
        self.terminated = False

    async def wait(self) -> int:
        await self._finished.wait()
        return cast("int", self.returncode)

    def terminate(self) -> None:
        self.terminated = True
        self.finish(-15)

    def kill(self) -> None:
        self.killed = True
        self.finish(-9)

    def finish(self, code: int) -> None:
        if self.returncode is None:
            self.returncode = code
            self._finished.set()


class StubbornProcess(FakeProcess):
    def __init__(self, handler: ResponseHandler) -> None:
        super().__init__(handler)
        self.stdin = StubbornWriter(self, handler, broken=False)
        self.kill_calls = 0

    def kill(self) -> None:
        self.killed = True
        self.kill_calls += 1


class FakeProcessFactory:
    def __init__(
        self,
        handlers: tuple[ResponseHandler, ...],
        *,
        broken_first: bool = False,
        oversized_first: bool = False,
    ) -> None:
        self._handlers = deque(handlers)
        self._broken_first = broken_first
        self._oversized_first = oversized_first
        self.commands: list[tuple[str, ...]] = []
        self.processes: list[FakeProcess] = []

    async def __call__(self, command: tuple[str, ...]) -> FakeProcess:
        handler: ResponseHandler = self._handlers.popleft()
        process = FakeProcess(
            handler,
            broken=self._broken_first and not self.processes,
            oversized=self._oversized_first and not self.processes,
        )
        self.commands.append(command)
        self.processes.append(process)
        return process


def _run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(coroutine)


def _config(*, voice_id: str = "zosia") -> TtsConfig:
    return TtsConfig(
        engine_id="sapi",
        provider_model_id="sapi5",
        voice_id=voice_id,
        max_concurrency=1,
        queue_capacity=4,
    )


def _windows_hosts(
    tmp_path: Path,
    *,
    x64: bool = True,
    x86: bool = True,
) -> tuple[Path, Path]:
    windows_dir: Path = tmp_path / "Windows"
    if x64:
        host64 = windows_dir / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        host64.parent.mkdir(parents=True)
        host64.touch()
    if x86:
        host86 = windows_dir / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        host86.parent.mkdir(parents=True)
        host86.touch()
    worker: Path = tmp_path / "sapi_worker.ps1"
    worker.touch()
    return windows_dir, worker


def _record(
    name: str,
    architecture: ProcessArchitecture,
) -> SapiVoiceRecord:
    return SapiVoiceRecord(
        id=f"voice:{architecture.value}:{name}",
        name=name,
        architecture=architecture,
    )


def _runtime(
    tmp_path: Path,
    probe: FakeVoiceProbe,
    *,
    controller: FakeController | None = None,
    x64: bool = True,
    x86: bool = True,
) -> SapiRuntime:
    windows_dir, worker = _windows_hosts(tmp_path, x64=x64, x86=x86)
    return SapiRuntime(
        platform_name="win32",
        windows_dir=windows_dir,
        worker_asset=worker,
        controller=controller,
        voice_probe=probe,
    )


def _request(
    tmp_path: Path,
    *,
    voice_id: str = "zosia",
    text: str = "Zażółć gęślą jaźń.",
) -> SynthesisRequest:
    clips: Path = tmp_path / "scope with spaces Ą" / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    destination: Path = clips / ".clip-próba.wav.tmp"
    destination.touch()
    return SynthesisRequest(
        request_id="scope:request:attempt",
        text=text,
        voice_id=voice_id,
        provider_model_id="sapi5",
        native_rate=None,
        native_volume=None,
        native_pitch=None,
        options={},
        destination=destination,
        deadline_s=0.1,
    )


def _wav_bytes(*, header_only: bool = False) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22_050)
        stream.writeframes(b"" if header_only else b"\x00\x00")
    return output.getvalue()


def _success(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            {
                "protocol_version": 1,
                "request_id": payload["request_id"],
                "ok": True,
                "output_path": payload["output_path"],
            },
        ).encode()
        + b"\n"
    )


def _controller_config(tmp_path: Path) -> SapiConfig:
    windows_dir, worker = _windows_hosts(tmp_path)
    return SapiConfig.from_tts_config(
        _config(),
        platform_name="win32",
        windows_dir=windows_dir,
        worker_asset=worker,
    )


def test_non_windows_is_unsupported_without_probe(tmp_path: Path) -> None:
    worker: Path = tmp_path / "sapi_worker.ps1"
    worker.touch()
    probe = FakeVoiceProbe({})
    engine = SapiTtsEngine(
        _config(),
        runtime=SapiRuntime(
            platform_name="linux",
            worker_asset=worker,
            voice_probe=probe,
        ),
    )

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.UNSUPPORTED_PLATFORM
    assert probe.calls == []


@pytest.mark.parametrize(
    ("voice_id", "x64", "x86", "architecture"),
    [
        ("zosia", False, True, "x64"),
        ("agnieszka", True, False, "x86"),
    ],
)
def test_selected_architecture_host_must_exist(
    tmp_path: Path,
    voice_id: str,
    x64: bool,
    x86: bool,
    architecture: str,
) -> None:
    probe = FakeVoiceProbe({})
    engine = SapiTtsEngine(
        _config(voice_id=voice_id),
        runtime=_runtime(tmp_path, probe, x64=x64, x86=x86),
    )

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.MISSING_BINARY
    assert architecture in availability.message
    assert probe.calls == []


@pytest.mark.parametrize(
    ("voice_id", "architecture"),
    [
        ("zosia", ProcessArchitecture.X64),
        ("agnieszka", ProcessArchitecture.X86),
    ],
)
def test_passive_probe_finds_voice_in_required_architecture(
    tmp_path: Path,
    voice_id: str,
    architecture: ProcessArchitecture,
) -> None:
    profile = SapiConfig.from_tts_config(
        _config(voice_id=voice_id),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe({architecture: (_record(profile.voice_name, architecture),)})
    engine = SapiTtsEngine(
        _config(voice_id=voice_id),
        runtime=_runtime(tmp_path, probe),
    )

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.READY
    assert any(voice.architecture is architecture for voice in availability.voices)
    assert probe.calls == [ProcessArchitecture.X64, ProcessArchitecture.X86]
    assert isinstance(engine, TtsEngine)


def test_passive_probe_reports_missing_voice(tmp_path: Path) -> None:
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X64: (_record("Another voice", ProcessArchitecture.X64),)},
    )
    engine = SapiTtsEngine(_config(), runtime=_runtime(tmp_path, probe))

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.MISSING_VOICE


def test_passive_probe_reports_architecture_mismatch(tmp_path: Path) -> None:
    profile = SapiConfig.from_tts_config(
        _config(),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X86: (_record(profile.voice_name, ProcessArchitecture.X86),)},
    )
    engine = SapiTtsEngine(_config(), runtime=_runtime(tmp_path, probe))

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.MISSING_VOICE
    assert "wrong process architecture" in availability.message


@pytest.mark.parametrize(
    ("voice_id", "rate", "volume", "architecture"),
    [
        ("zosia", 2, 70, ProcessArchitecture.X64),
        ("agnieszka", 5, 65, ProcessArchitecture.X86),
    ],
)
def test_builtin_profile_defaults_resolve_to_native_sapi_values(
    tmp_path: Path,
    voice_id: str,
    rate: int,
    volume: int,
    architecture: ProcessArchitecture,
) -> None:
    windows_dir, worker = _windows_hosts(tmp_path)

    config = SapiConfig.from_tts_config(
        _config(voice_id=voice_id),
        platform_name="win32",
        windows_dir=windows_dir,
        worker_asset=worker,
    )

    assert config.resolved_rate == rate
    assert config.resolved_volume == volume
    assert config.host is not None
    assert config.host.architecture is architecture


def test_default_availability_never_calls_synthesis(tmp_path: Path) -> None:
    profile = SapiConfig.from_tts_config(
        _config(),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X64: (_record(profile.voice_name, ProcessArchitecture.X64),)},
    )
    controller = FakeController()
    engine = SapiTtsEngine(
        _config(),
        runtime=_runtime(tmp_path, probe, controller=controller),
    )

    availability = _run(engine.availability())

    assert availability.status is AvailabilityStatus.READY
    assert controller.calls == []
    assert not tuple(tmp_path.rglob("*.wav"))


def test_live_availability_uses_isolated_synthesis_probe(tmp_path: Path) -> None:
    profile = SapiConfig.from_tts_config(
        _config(),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X64: (_record(profile.voice_name, ProcessArchitecture.X64),)},
    )
    live_controller = FakeController()
    windows_dir, worker = _windows_hosts(tmp_path)
    engine = SapiTtsEngine(
        _config(),
        runtime=SapiRuntime(
            platform_name="win32",
            windows_dir=windows_dir,
            worker_asset=worker,
            live_controller=live_controller,
            voice_probe=probe,
        ),
    )

    availability = _run(engine.availability(live=True))

    assert availability.status is AvailabilityStatus.READY
    assert len(live_controller.calls) == 1
    assert live_controller.calls[0][2].parent.name == "clips"
    assert live_controller.calls[0][2].name == ".clip-live.wav.tmp"
    assert live_controller.closed


@pytest.mark.parametrize("text", ["Ź", "Zażółć gęślą jaźń."])
def test_synthesis_accepts_one_character_and_unicode_paths(
    tmp_path: Path,
    text: str,
) -> None:
    profile = SapiConfig.from_tts_config(
        _config(),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X64: (_record(profile.voice_name, ProcessArchitecture.X64),)},
    )
    controller = FakeController()
    engine = SapiTtsEngine(
        _config(),
        runtime=_runtime(tmp_path, probe, controller=controller),
    )
    request: SynthesisRequest = _request(tmp_path, text=text)

    result = _run(engine.synthesize(request, cancel=FakeCancellation()))

    assert result.path == request.destination.resolve()
    assert result.format is AudioFormat.WAV
    assert result.voice_id.endswith("@x64")
    assert controller.calls[0][1] == text


def test_header_only_wav_is_rejected(tmp_path: Path) -> None:
    profile = SapiConfig.from_tts_config(
        _config(),
        platform_name="linux",
        worker_asset=tmp_path / "unused",
    ).profile
    probe = FakeVoiceProbe(
        {ProcessArchitecture.X64: (_record(profile.voice_name, ProcessArchitecture.X64),)},
    )
    engine = SapiTtsEngine(
        _config(),
        runtime=_runtime(tmp_path, probe, controller=FakeController(header_only=True)),
    )

    with pytest.raises(TtsClipValidationError):
        _run(engine.synthesize(_request(tmp_path), cancel=FakeCancellation()))


def test_destination_outside_reserved_clip_contract_is_rejected(tmp_path: Path) -> None:
    probe = FakeVoiceProbe({})
    controller = FakeController()
    engine = SapiTtsEngine(
        _config(),
        runtime=_runtime(tmp_path, probe, controller=controller),
    )
    destination: Path = tmp_path / "outside.wav"
    destination.touch()
    request = SynthesisRequest(
        request_id="r",
        text="x",
        voice_id="zosia",
        provider_model_id="sapi5",
        native_rate=None,
        native_volume=None,
        native_pitch=None,
        options={},
        destination=destination,
        deadline_s=1.0,
    )

    with pytest.raises(TtsInputError):
        _run(engine.synthesize(request, cancel=FakeCancellation()))

    assert controller.calls == []


def test_protocol_preserves_unicode_without_command_interpolation(tmp_path: Path) -> None:
    request = SapiWorkerRequest(
        request_id="r",
        voice_name="Zosia",
        text="Zażółć `$(malicious)`",
        output_path=tmp_path / "clips" / ".clip-x.wav.tmp",
    )

    payload = cast("dict[str, object]", json.loads(request.encode()))

    assert payload["text"] == "Zażółć `$(malicious)`"
    assert payload["operation"] == "synthesize"


def test_controller_reuses_one_worker_for_more_than_one_hundred_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject_thread_wait(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError

    monkeypatch.setattr(asyncio, "to_thread", reject_thread_wait)

    async def scenario() -> tuple[SapiWorkerController, FakeProcessFactory]:
        factory = FakeProcessFactory((_success,))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        clips: Path = tmp_path / "clips"
        clips.mkdir(exist_ok=True)
        cancel = TtsCancellation()
        for index in range(101):
            await controller.synthesize(
                f"request-{index}",
                f"Tekst {index}",
                clips / f".clip-{index}.wav.tmp",
                deadline_s=0.1,
                cancel=cancel,
            )
        return controller, factory

    controller, factory = _run(scenario())

    assert len(factory.processes) == 1
    assert controller.is_running
    _run(controller.close())
    assert factory.processes[0].stdin.closed


def test_controller_timeout_kills_worker_and_next_request_restarts(
    tmp_path: Path,
) -> None:
    def blocked(payload: dict[str, object]) -> None:
        del payload

    async def scenario() -> tuple[SapiWorkerController, FakeProcessFactory]:
        factory = FakeProcessFactory((blocked, _success))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        cancel = FakeCancellation()
        with pytest.raises(TtsTimeoutError):
            await controller.synthesize(
                "blocked",
                "x",
                tmp_path / "blocked.wav",
                deadline_s=0.001,
                cancel=cancel,
            )
        await controller.synthesize(
            "restarted",
            "x",
            tmp_path / "restarted.wav",
            deadline_s=0.1,
            cancel=cancel,
        )
        return controller, factory

    controller, factory = _run(scenario())

    assert factory.processes[0].killed
    assert len(factory.processes) == 2
    assert controller.is_running
    _run(controller.close())


def test_controller_broken_pipe_discards_worker(tmp_path: Path) -> None:
    async def scenario() -> tuple[SapiWorkerController, FakeProcessFactory]:
        factory = FakeProcessFactory((_success,), broken_first=True)
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        with pytest.raises(TtsProviderUnavailableError):
            await controller.synthesize(
                "broken",
                "x",
                tmp_path / "broken.wav",
                deadline_s=0.1,
                cancel=FakeCancellation(),
            )
        return controller, factory

    controller, factory = _run(scenario())

    assert factory.processes[0].killed
    assert not controller.is_running


def test_close_retries_cleanup_when_forced_kill_does_not_finish(
    tmp_path: Path,
) -> None:
    async def scenario() -> StubbornProcess:
        process = StubbornProcess(_success)

        async def factory(command: tuple[str, ...]) -> StubbornProcess:
            del command
            return process

        config = replace(
            _controller_config(tmp_path),
            shutdown_deadline_s=0.001,
        )
        controller = SapiWorkerController(
            config,
            process_factory=cast("_ProcessFactory", factory),
        )
        await controller.synthesize(
            "request",
            "x",
            tmp_path / "request.wav",
            deadline_s=0.1,
            cancel=FakeCancellation(),
        )
        with pytest.raises(TtsProviderUnavailableError):
            await controller.close()
        with pytest.raises(TtsProviderUnavailableError):
            await controller.close()
        return process

    process = _run(scenario())

    assert process.kill_calls == 2


def test_controller_discards_worker_after_oversized_response(
    tmp_path: Path,
) -> None:
    async def scenario() -> FakeProcessFactory:
        factory = FakeProcessFactory((_success,), oversized_first=True)
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        with pytest.raises(TtsProviderUnavailableError, match="protocol limit"):
            await controller.synthesize(
                "oversized",
                "x",
                tmp_path / "oversized.wav",
                deadline_s=0.1,
                cancel=FakeCancellation(),
            )
        return factory

    factory = _run(scenario())

    assert factory.processes[0].killed
    assert factory.processes[0].returncode is not None


@pytest.mark.parametrize(
    "response",
    [
        b"",
        b"not-json\n",
        b'{"protocol_version":1,"request_id":"wrong","ok":true,"output_path":"x"}\n',
    ],
)
def test_controller_rejects_exit_malformed_json_and_wrong_id(
    tmp_path: Path,
    response: bytes,
) -> None:
    def invalid(payload: dict[str, object]) -> bytes:
        if response.startswith(b'{"protocol_version"'):
            decoded = cast("dict[str, object]", json.loads(response))
            decoded["output_path"] = payload["output_path"]
            return json.dumps(decoded).encode() + b"\n"
        return response

    async def scenario() -> FakeProcessFactory:
        factory = FakeProcessFactory((invalid,))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        with pytest.raises(TtsProviderUnavailableError):
            await controller.synthesize(
                "expected",
                "x",
                tmp_path / "result.wav",
                deadline_s=0.1,
                cancel=FakeCancellation(),
            )
        return factory

    factory = _run(scenario())

    assert factory.processes[0].killed


def test_controller_cancellation_kills_worker_without_orphan(tmp_path: Path) -> None:
    def blocked(payload: dict[str, object]) -> None:
        del payload

    async def scenario() -> FakeProcessFactory:
        factory = FakeProcessFactory((blocked,))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        cancellation = FakeCancellation(cancelled=True)
        with pytest.raises(TtsCancelledError):
            await controller.synthesize(
                "cancelled",
                "x",
                tmp_path / "cancelled.wav",
                deadline_s=0.1,
                cancel=cancellation,
            )
        await controller.close()
        return factory

    factory = _run(scenario())

    assert factory.processes[0].killed
    assert factory.processes[0].returncode is not None


def test_controller_active_cancellation_kills_worker_immediately(tmp_path: Path) -> None:
    async def scenario() -> FakeProcessFactory:
        request_started = asyncio.Event()

        def blocked(payload: dict[str, object]) -> None:
            del payload
            request_started.set()

        factory = FakeProcessFactory((blocked,))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        cancellation = FakeCancellation()
        synthesis = asyncio.create_task(
            controller.synthesize(
                "cancelled-active",
                "x",
                tmp_path / "cancelled-active.wav",
                deadline_s=30.0,
                cancel=cancellation,
            ),
        )
        await asyncio.wait_for(request_started.wait(), timeout=0.1)

        cancellation.cancel()

        with pytest.raises(TtsCancelledError):
            await asyncio.wait_for(synthesis, timeout=0.1)
        await controller.close()
        return factory

    factory = _run(scenario())

    assert factory.processes[0].killed
    assert factory.processes[0].returncode is not None


def test_worker_command_is_argument_list_with_initialized_voice(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, ...]:
        factory = FakeProcessFactory((_success,))
        controller = SapiWorkerController(
            _controller_config(tmp_path),
            process_factory=cast("_ProcessFactory", factory),
        )
        await controller.synthesize(
            "request",
            "text",
            tmp_path / "clip.wav",
            deadline_s=0.1,
            cancel=FakeCancellation(),
        )
        await controller.close()
        return factory.commands[0]

    command = _run(scenario())

    assert "-NoLogo" in command
    assert "-NoProfile" in command
    assert "-NonInteractive" in command
    assert "-File" in command
    assert "-VoiceName" in command
    assert "text" not in command


@pytest.mark.parametrize(
    ("native_rate", "native_volume"),
    [(1.5, None), (None, 65.5)],
)
def test_agnieszka_rejects_fractional_native_settings(
    native_rate: float | None,
    native_volume: float | None,
) -> None:
    config = TtsConfig(
        engine_id="sapi",
        provider_model_id="sapi5",
        voice_id="agnieszka",
        max_concurrency=1,
        queue_capacity=4,
        native_rate=native_rate,
        native_volume=native_volume,
    )

    with pytest.raises(TtsUnsupportedError, match="integer"):
        SapiConfig.from_tts_config(config, platform_name="linux")
