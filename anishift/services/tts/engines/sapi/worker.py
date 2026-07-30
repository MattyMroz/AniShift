"""Persistent PowerShell worker lifecycle for SAPI."""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Protocol, cast

from anishift.services.tts.errors import (
    TtsCancelledError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
)
from anishift.services.tts.protocols import CancellationToken

from .config import SapiConfig
from .constants import MAX_IPC_MESSAGE_BYTES
from .protocol import SapiWorkerRequest, SapiWorkerResponse, decode_voice_list
from .types import SapiHost, SapiSynthesisResult, SapiVoiceRecord

__all__ = [
    "PowerShellSapiVoiceProbe",
    "SapiVoiceProbe",
    "SapiWorkerController",
]


class _AsyncReader(Protocol):
    async def readline(self) -> bytes:
        """Read one binary line."""
        ...


class _AsyncWriter(Protocol):
    def write(self, data: bytes) -> None:
        """Buffer bytes for stdin."""
        ...

    async def drain(self) -> None:
        """Flush buffered stdin bytes."""
        ...

    def close(self) -> None:
        """Close stdin and signal EOF."""
        ...

    async def wait_closed(self) -> None:
        """Wait until stdin is closed."""
        ...


class _SapiProcess(Protocol):
    stdin: _AsyncWriter
    stdout: _AsyncReader
    stderr: _AsyncReader

    @property
    def returncode(self) -> int | None:
        """Return the process exit code once terminated."""
        ...

    async def wait(self) -> int:
        """Wait for process termination."""
        ...

    def terminate(self) -> None:
        """Request process termination."""
        ...

    def kill(self) -> None:
        """Force process termination."""
        ...


type _ProcessFactory = Callable[[tuple[str, ...]], Awaitable[_SapiProcess]]
"""Factory spawning one binary-pipe worker process."""


class SapiVoiceProbe(Protocol):
    """Passively enumerate voices without invoking ``Speak``."""

    async def list_voices(
        self,
        host: SapiHost,
        worker_asset: Path,
        *,
        timeout_s: float,
    ) -> tuple[SapiVoiceRecord, ...]:
        """Return voices installed for one process architecture."""
        ...


class PowerShellSapiVoiceProbe:
    """One-shot passive SAPI voice enumeration."""

    async def list_voices(
        self,
        host: SapiHost,
        worker_asset: Path,
        *,
        timeout_s: float,
    ) -> tuple[SapiVoiceRecord, ...]:
        """Run only the worker's ``GetVoices`` operation."""
        command: tuple[str, ...] = _voice_list_command(host, worker_asset)
        try:
            process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=_creation_flags(),
            )
        except OSError as error:
            message: str = "Failed to start the passive SAPI voice probe"
            raise TtsProviderUnavailableError(message) from error
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
        except asyncio.CancelledError:
            process.kill()
            await _bounded_wait(process, timeout_s=1.0)
            raise
        except TimeoutError as error:
            process.kill()
            await _bounded_wait(process, timeout_s=1.0)
            message = "Passive SAPI voice probe timed out"
            raise TtsTimeoutError(message) from error
        if process.returncode != 0:
            message = f"Passive SAPI voice probe exited with code {process.returncode}"
            raise TtsProviderUnavailableError(message)
        lines: list[bytes] = [line for line in stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            message = "Passive SAPI voice probe returned an invalid response count"
            raise TtsProviderUnavailableError(message)
        return decode_voice_list(lines[0], architecture=host.architecture)


class SapiWorkerController:
    """Own one persistent sequential SAPI worker and restart it after failure."""

    def __init__(
        self,
        config: SapiConfig,
        *,
        process_factory: _ProcessFactory | None = None,
    ) -> None:
        """Create a lazy controller without spawning PowerShell."""
        self._config: SapiConfig = config
        self._process_factory: _ProcessFactory = process_factory or _spawn_process
        self._process: _SapiProcess | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False

    @property
    def is_running(self) -> bool:
        """Whether the current worker process is alive."""
        return self._process is not None and self._process.returncode is None

    async def synthesize(
        self,
        request_id: str,
        text: str,
        output_path: Path,
        *,
        deadline_s: float,
        cancel: CancellationToken,
    ) -> SapiSynthesisResult:
        """Send one correlated command and await one bounded response."""
        async with self._lock:
            if self._closed:
                message: str = "SAPI worker controller is closed"
                raise TtsProviderUnavailableError(message)
            process: _SapiProcess = await self._ensure_process()
            request = SapiWorkerRequest(
                request_id=request_id,
                voice_name=self._config.profile.voice_name,
                text=text,
                output_path=output_path,
            )
            started_at: float = time.perf_counter()
            try:
                process.stdin.write(request.encode())
                await process.stdin.drain()
                raw_response: bytes = await self._read_response(
                    process,
                    deadline_s=deadline_s,
                    cancel=cancel,
                )
                response: SapiWorkerResponse = SapiWorkerResponse.decode(raw_response)
                self._validate_response(response, request)
            except asyncio.CancelledError:
                await self._discard_worker()
                raise
            except OSError as error:
                await self._discard_worker()
                message = "SAPI worker pipe failed"
                raise TtsProviderUnavailableError(message) from error
            except TtsProviderUnavailableError, TtsTimeoutError, TtsCancelledError:
                await self._discard_worker()
                raise
            if not response.ok:
                await self._discard_worker()
                message = f"SAPI worker failed: {response.error_code}"
                raise TtsProviderUnavailableError(message)
            return SapiSynthesisResult(
                request_id=request_id,
                output_path=output_path,
                request_time_ms=(time.perf_counter() - started_at) * 1000.0,
            )

    async def close(self) -> None:
        """Close stdin, wait to the configured deadline, then hard-kill."""
        async with self._lock:
            if self._closed and self._process is None:
                return
            self._closed = True
            process: _SapiProcess | None = self._process
            if process is None:
                return
            try:
                process.stdin.close()
                with suppress(OSError):
                    await process.stdin.wait_closed()
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self._config.shutdown_deadline_s,
                )
            except asyncio.CancelledError:
                await self._kill_process(process)
                if process.returncode is not None:
                    await self._clear_process()
                raise
            except TimeoutError:
                await self._kill_process(process)
            if process.returncode is None:
                message = "SAPI worker did not exit after forced shutdown"
                raise TtsProviderUnavailableError(message)
            await self._clear_process()

    async def _ensure_process(self) -> _SapiProcess:
        process: _SapiProcess | None = self._process
        if process is not None and process.returncode is None:
            return process
        if self._config.host is None:
            message: str = "SAPI PowerShell host is unavailable"
            raise TtsProviderUnavailableError(message)
        command: tuple[str, ...] = _worker_command(self._config)
        try:
            process = await self._process_factory(command)
        except OSError as error:
            message = "Failed to start the SAPI worker"
            raise TtsProviderUnavailableError(message) from error
        self._process = process
        self._stderr_task = asyncio.create_task(_drain_stderr(process.stderr), name="sapi-stderr")
        return process

    async def _read_response(
        self,
        process: _SapiProcess,
        *,
        deadline_s: float,
        cancel: CancellationToken,
    ) -> bytes:
        if cancel.is_cancelled:
            message: str = "SAPI synthesis cancelled before response"
            raise TtsCancelledError(message)
        read_task: asyncio.Task[bytes] = asyncio.create_task(process.stdout.readline())
        cancel_task: asyncio.Task[None] = asyncio.create_task(cancel.wait())
        done, pending = await asyncio.wait(
            {read_task, cancel_task},
            timeout=deadline_s,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if cancel_task in done or cancel.is_cancelled:
            if read_task not in done:
                read_task.cancel()
                await asyncio.gather(read_task, return_exceptions=True)
            message = "SAPI synthesis cancelled while waiting for the worker"
            raise TtsCancelledError(message)
        if read_task not in done:
            message = "SAPI worker request timed out"
            raise TtsTimeoutError(message)
        try:
            raw_response: bytes = read_task.result()
        except ValueError as error:
            message = "SAPI worker response exceeded the protocol limit"
            raise TtsProviderUnavailableError(message) from error
        if not raw_response:
            message = f"SAPI worker exited before responding (code={process.returncode})"
            raise TtsProviderUnavailableError(message)
        return raw_response

    @staticmethod
    def _validate_response(response: SapiWorkerResponse, request: SapiWorkerRequest) -> None:
        if response.request_id != request.request_id:
            message: str = "SAPI worker response request id does not match"
            raise TtsProviderUnavailableError(message)
        if response.ok and response.output_path != request.output_path:
            message = "SAPI worker response output path does not match"
            raise TtsProviderUnavailableError(message)

    async def _discard_worker(self) -> None:
        process: _SapiProcess | None = self._process
        if process is not None and process.returncode is None:
            await self._kill_process(process)
        if process is not None and process.returncode is None:
            self._closed = True
            message: str = "SAPI worker could not be terminated safely"
            raise TtsProviderUnavailableError(message)
        if process is None or process.returncode is not None:
            await self._clear_process()

    async def _kill_process(self, process: _SapiProcess) -> None:
        with suppress(ProcessLookupError):
            process.kill()
        with suppress(TimeoutError):
            await asyncio.wait_for(
                process.wait(),
                timeout=self._config.shutdown_deadline_s,
            )

    async def _clear_process(self) -> None:
        stderr_task: asyncio.Task[None] | None = self._stderr_task
        self._process = None
        self._stderr_task = None
        if stderr_task is None:
            return
        stderr_task.cancel()
        with suppress(asyncio.CancelledError, OSError, ValueError):
            await stderr_task


async def _spawn_process(command: tuple[str, ...]) -> _SapiProcess:
    process: asyncio.subprocess.Process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=MAX_IPC_MESSAGE_BYTES + 1,
        creationflags=_creation_flags(),
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        message: str = "SAPI worker pipes were not created"
        process.kill()
        raise TtsProviderUnavailableError(message)
    return cast("_SapiProcess", process)


async def _drain_stderr(stderr: _AsyncReader) -> None:
    while await stderr.readline():
        pass


def _worker_command(config: SapiConfig) -> tuple[str, ...]:
    if config.host is None:
        message: str = "SAPI PowerShell host is unavailable"
        raise TtsProviderUnavailableError(message)
    return (
        str(config.host.executable),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(config.worker_asset),
        "-VoiceName",
        config.profile.voice_name,
        "-Rate",
        str(config.resolved_rate),
        "-Volume",
        str(config.resolved_volume),
    )


def _voice_list_command(host: SapiHost, worker_asset: Path) -> tuple[str, ...]:
    return (
        str(host.executable),
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(worker_asset),
        "-ListVoices",
    )


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


async def _bounded_wait(process: asyncio.subprocess.Process, *, timeout_s: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=timeout_s)
