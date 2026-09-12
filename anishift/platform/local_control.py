"""Authenticated local control channel between the resident and its panel or CLI clients."""

from __future__ import annotations

import json
import multiprocessing.connection as ipc
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from multiprocessing import AuthenticationError
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.platform.binaries import is_windows
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

__all__ = [
    "INSTANCE_FILE_NAME",
    "KEY_FILE_NAME",
    "MAX_FRAME_BYTES",
    "MAX_OUTBOX_EVENTS",
    "PROTOCOL_VERSION",
    "SOCKET_FILE_NAME",
    "ControlClient",
    "ControlError",
    "ControlErrorCode",
    "ControlRequest",
    "ControlResponse",
    "ControlServer",
    "InstanceRecord",
    "connect",
    "connect_or_start",
    "control_endpoint",
    "ensure_authkey",
    "read_instance",
    "remove_instance",
    "write_instance",
]

logger = get_logger(__name__)

if sys.platform == "win32":
    type ChannelConnection = ipc.Connection[Any, Any] | ipc.PipeConnection[Any, Any]
    """One accepted or opened end of the channel, a named pipe on this platform."""
else:
    type ChannelConnection = ipc.Connection[Any, Any]
    """One accepted or opened end of the channel, a Unix socket on this platform."""

# ── Constants ─────────────────────────────────────────────────────────────────

PROTOCOL_VERSION: Final[int] = 1
"""Version every request, response and event frame of this channel carries."""

MAX_FRAME_BYTES: Final[int] = 1_048_576
"""Largest accepted frame; the biggest answer is one page of a paged snapshot."""

MAX_OUTBOX_EVENTS: Final[int] = 512
"""Events held for one subscriber before the oldest unmerged one is dropped."""

INSTANCE_FILE_NAME: Final[str] = "instance.json"
"""File naming the running resident; its presence alone proves nothing."""

KEY_FILE_NAME: Final[str] = "control.key"
"""File holding the shared key, readable by the current account only."""

SOCKET_FILE_NAME: Final[str] = "control.sock"
"""Endpoint of the channel outside Windows, beside the other state files."""

DEFAULT_TIMEOUT_S: Final[float] = 30.0
"""Wait for one answer before a client gives up on the resident."""

_AUTHKEY_BYTES: Final[int] = 32
"""Length of the random key both sides prove knowledge of before any frame."""

_WINDOWS_PIPE_PREFIX: Final[str] = "\\\\.\\pipe\\"
"""Only endpoint prefix accepted on Windows, which keeps the pipe on this machine."""

_ENDPOINT_DIGEST_CHARS: Final[int] = 12
"""Digest characters of the state directory that make one pipe name unique."""

_CONNECT_POLL_S: Final[float] = 0.1
"""Wait between two attempts to reach a resident that is still starting."""

_ICACLS_TIMEOUT_S: Final[float] = 10.0
"""Budget for the one ``icacls`` call restricting the key file."""

_TEMPORARY_SUFFIX: Final[str] = ".tmp"
"""Ending of the file an instance record is written to before it replaces the record."""

_TOO_MANY_CONNECTIONS: Final[str] = "The resident already serves its maximum number of clients"
"""Reason returned to a client the server has no connection slot for."""

_UNREADABLE_FRAME: Final[str] = "The frame is not a valid control request"
"""Reason returned for a frame that is not the documented request document."""

_REMOTE_ENDPOINT: Final[str] = "A control endpoint must name a pipe on this machine"
"""Refusal raised for an endpoint pointing at another computer."""

_SUBSCRIBE_KIND: Final[str] = "subscribe"
"""Command turning the connection that sent it into an event stream."""

_HANDLER_FAILED: Final[str] = "The resident could not complete the command"
"""Reason returned when the owner of the state raised instead of answering."""

_ACCEPT_JOIN_S: Final[float] = 5.0
"""Wait for the accept thread to notice that the server is closing."""

_COMMAND_ID_BYTES: Final[int] = 8
"""Random bytes making one client-generated command identifier unique."""

_NO_RESULT: Final[Mapping[str, object]] = MappingProxyType({})
"""Result of a command that answers with nothing but its acceptance."""


class ControlErrorCode(StrEnum):
    """Reason one control command was refused, carried by every failed response."""

    STALE_INSTANCE = "stale_instance"
    UNKNOWN_COMMAND = "unknown_command"
    INVALID_PAYLOAD = "invalid_payload"
    STALE_PREVIEW = "stale_preview"
    CONFLICT = "conflict"
    REFUSED = "refused"
    INTERNAL = "internal"


class ControlError(AniShiftError):
    """Raised when the local control channel cannot deliver or complete a command."""

    def __init__(self, message: str, *, code: ControlErrorCode = ControlErrorCode.INTERNAL) -> None:
        """Carry the protocol reason beside the generic AniShift error context."""
        super().__init__(
            context=ErrorContext(
                code=ErrorCode.IO_ERROR,
                message=message,
                suggestion="Check whether the resident runs and retry the command",
            )
        )
        self.code: ControlErrorCode = code


@dataclass(frozen=True, slots=True)
class ControlRequest:
    """One validated command a client asked the resident to perform."""

    command_id: str
    kind: str
    payload: Mapping[str, object]
    instance_id: str | None = None


@dataclass(frozen=True, slots=True)
class ControlResponse:
    """Outcome the resident returns for exactly one request."""

    ok: bool
    result: Mapping[str, object] = _NO_RESULT
    code: ControlErrorCode | None = None
    message: str = ""

    @classmethod
    def succeeded(cls, result: Mapping[str, object] | None = None) -> ControlResponse:
        """Return an accepted response carrying *result*."""
        return cls(ok=True, result=result if result is not None else _NO_RESULT)

    @classmethod
    def refused(cls, code: ControlErrorCode, message: str) -> ControlResponse:
        """Return a refused response naming why the command was not performed."""
        return cls(ok=False, result=_NO_RESULT, code=code, message=message)


@dataclass(frozen=True, slots=True)
class InstanceRecord:
    """Identity of the resident that last took the lock on one state directory."""

    instance_id: str
    pid: int
    endpoint: str
    started_at: str


def control_endpoint(state_dir: Path) -> str:
    """Return the endpoint the resident owning *state_dir* listens on."""
    digest: str = sha256(str(state_dir.resolve()).casefold().encode("utf-8")).hexdigest()
    if is_windows():
        return f"{_WINDOWS_PIPE_PREFIX}anishift-{digest[:_ENDPOINT_DIGEST_CHARS]}"
    return str(state_dir / SOCKET_FILE_NAME)


def ensure_authkey(state_dir: Path) -> bytes:
    """Return the shared key of *state_dir*, creating it for this account when absent."""
    path: Path = state_dir / KEY_FILE_NAME
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        descriptor: int = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _read_authkey(path)
    key: bytes = os.urandom(_AUTHKEY_BYTES)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key)
    _restrict_to_current_user(path)
    return key


def write_instance(state_dir: Path, record: InstanceRecord) -> None:
    """Record the running resident atomically beside its lock."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path: Path = state_dir / INSTANCE_FILE_NAME
    temporary: Path = path.with_name(f"{path.name}{_TEMPORARY_SUFFIX}")
    document: dict[str, object] = {
        "instance_id": record.instance_id,
        "pid": record.pid,
        "endpoint": record.endpoint,
        "started_at": record.started_at,
    }
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def read_instance(state_dir: Path) -> InstanceRecord | None:
    """Return the recorded resident, or ``None`` when nothing readable was recorded."""
    try:
        document: object = json.loads((state_dir / INSTANCE_FILE_NAME).read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None
    instance_id: object = document.get("instance_id")
    pid: object = document.get("pid")
    endpoint: object = document.get("endpoint")
    started_at: object = document.get("started_at")
    if not isinstance(instance_id, str) or not isinstance(endpoint, str):
        return None
    if not isinstance(pid, int) or isinstance(pid, bool) or not isinstance(started_at, str):
        return None
    return InstanceRecord(instance_id=instance_id, pid=pid, endpoint=endpoint, started_at=started_at)


def remove_instance(state_dir: Path) -> None:
    """Drop the instance record, so a stopped resident stops naming itself."""
    try:
        (state_dir / INSTANCE_FILE_NAME).unlink(missing_ok=True)
    except OSError:
        logger.debug("Could not remove the control instance record")


def connect(state_dir: Path, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> ControlClient | None:
    """Return a client of the resident owning *state_dir*, or ``None`` when none answers."""
    record: InstanceRecord | None = read_instance(state_dir)
    if record is None:
        return None
    key_path: Path = state_dir / KEY_FILE_NAME
    if not key_path.is_file():
        return None
    try:
        return ControlClient(record.endpoint, _read_authkey(key_path), timeout_s=timeout_s)
    except OSError, AuthenticationError, ControlError:
        return None


def connect_or_start(
    state_dir: Path,
    *,
    spawn: Callable[[], None],
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ControlClient:
    """Reach the resident of *state_dir*, starting exactly one when none answers."""
    running: ControlClient | None = connect(state_dir, timeout_s=timeout_s)
    if running is not None:
        return running
    spawn()
    deadline: float = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        started: ControlClient | None = connect(state_dir, timeout_s=timeout_s)
        if started is not None:
            return started
        time.sleep(_CONNECT_POLL_S)
    msg = "The resident did not answer after it was started"
    raise ControlError(msg, code=ControlErrorCode.REFUSED)


class ControlServer:
    """Accepts authenticated local clients and answers their validated JSON frames."""

    def __init__(
        self,
        endpoint: str,
        authkey: bytes,
        handler: Callable[[ControlRequest], ControlResponse],
        *,
        max_connections: int = 8,
    ) -> None:
        """Bind *endpoint* for this account and start accepting clients."""
        _require_local_endpoint(endpoint)
        self._endpoint: str = endpoint
        self._authkey: bytes = authkey
        self._handler: Callable[[ControlRequest], ControlResponse] = handler
        self._max_connections: int = max_connections
        self._lock: threading.Lock = threading.Lock()
        self._served: list[_ServedConnection] = []
        self._closing: threading.Event = threading.Event()
        self._listener: ipc.Listener = ipc.Listener(endpoint, authkey=authkey)
        self._accepting: threading.Thread = threading.Thread(
            target=self._accept_loop,
            name="anishift-control",
            daemon=True,
        )
        self._accepting.start()

    def broadcast(self, event: Mapping[str, object]) -> None:
        """Hand one event to every subscriber without waiting for a slow one."""
        frame: dict[str, object] = {"v": PROTOCOL_VERSION, **event}
        with self._lock:
            subscribers: tuple[_ServedConnection, ...] = tuple(item for item in self._served if item.subscribed)
        for subscriber in subscribers:
            subscriber.publish(frame)

    def close(self) -> None:
        """Stop accepting, drop every connection and join the channel's threads."""
        if self._closing.is_set():
            return
        self._closing.set()
        self._wake_accept()
        self._accepting.join(timeout=_ACCEPT_JOIN_S)
        with self._lock:
            served: tuple[_ServedConnection, ...] = tuple(self._served)
            self._served.clear()
        for item in served:
            item.close()
        try:
            self._listener.close()
        except OSError:
            logger.debug("Control listener was already closed")

    def _accept_loop(self) -> None:
        while not self._closing.is_set():
            try:
                accepted: ChannelConnection = self._listener.accept()
            except AuthenticationError:
                logger.warning("Refused a control client that proved no key")
                continue
            except OSError:
                if not self._closing.is_set():
                    logger.warning("The control listener stopped accepting clients")
                return
            if self._closing.is_set():
                accepted.close()
                return
            self._admit(accepted)

    def _admit(self, accepted: ChannelConnection) -> None:
        served = _ServedConnection(accepted)
        with self._lock:
            admitted: bool = len(self._served) < self._max_connections
            if admitted:
                self._served.append(served)
        if not admitted:
            logger.warning("Refused a control client over the connection limit")
            served.send(_error_frame("", ControlErrorCode.REFUSED, _TOO_MANY_CONNECTIONS))
            served.close()
            return
        threading.Thread(
            target=self._serve,
            args=(served,),
            name="anishift-control-client",
            daemon=True,
        ).start()

    def _serve(self, served: _ServedConnection) -> None:
        try:
            while not self._closing.is_set():
                raw: bytes | None = served.receive()
                if raw is None:
                    return
                if not self._answer(served, raw):
                    return
        finally:
            self._forget(served)
            served.close()

    def _answer(self, served: _ServedConnection, raw: bytes) -> bool:
        request: ControlRequest | None = _decode_request(raw)
        if request is None:
            return served.send(_error_frame("", ControlErrorCode.INVALID_PAYLOAD, _UNREADABLE_FRAME))
        if request.kind == _SUBSCRIBE_KIND:
            served.subscribe()
            return served.send(_result_frame(request.command_id, {"subscribed": True}))
        try:
            response: ControlResponse = self._handler(request)
        except Exception:  # noqa: BLE001 - one boundary keeping a faulty command off the channel
            logger.warning("A control command failed", command_kind=request.kind)
            return served.send(_error_frame(request.command_id, ControlErrorCode.INTERNAL, _HANDLER_FAILED))
        return served.send(_response_frame(request.command_id, response))

    def _forget(self, served: _ServedConnection) -> None:
        with self._lock:
            if served in self._served:
                self._served.remove(served)

    def _wake_accept(self) -> None:
        try:
            waker: ChannelConnection = ipc.Client(self._endpoint, authkey=self._authkey)
        except OSError, AuthenticationError:
            return
        waker.close()


class ControlClient:
    """One client connection to a resident, used for commands or for its event stream."""

    def __init__(self, endpoint: str, authkey: bytes, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        """Connect to *endpoint*, proving knowledge of *authkey* before the first frame."""
        _require_local_endpoint(endpoint)
        self._timeout_s: float = timeout_s
        self._connection: ChannelConnection = ipc.Client(endpoint, authkey=authkey)
        self._subscribed: bool = False

    def call(
        self,
        kind: str,
        payload: Mapping[str, object] | None = None,
        *,
        command_id: str | None = None,
        instance_id: str | None = None,
    ) -> Mapping[str, object]:
        """Send one command and return its result."""
        if self._subscribed:
            msg = "A subscribed connection carries events, not commands"
            raise ControlError(msg, code=ControlErrorCode.REFUSED)
        identity: str = command_id if command_id is not None else _new_command_id()
        self._send(
            {
                "v": PROTOCOL_VERSION,
                "command_id": identity,
                "instance_id": instance_id,
                "kind": kind,
                "payload": dict(payload) if payload is not None else {},
            }
        )
        return _accepted_result(self._receive(), identity)

    def subscribe(self) -> None:
        """Turn this connection into the event stream of the resident."""
        self.call(_SUBSCRIBE_KIND)
        self._subscribed = True

    def events(self) -> Iterator[Mapping[str, object]]:
        """Yield every event frame until the resident or this client closes the stream."""
        if not self._subscribed:
            msg = "Only a subscribed connection carries events"
            raise ControlError(msg, code=ControlErrorCode.REFUSED)
        while True:
            try:
                raw: bytes = self._connection.recv_bytes(maxlength=MAX_FRAME_BYTES)
            except EOFError, OSError:
                return
            frame: Mapping[str, object] | None = _decode_frame(raw)
            if frame is not None and "event" in frame:
                yield frame

    def close(self) -> None:
        """Close the connection; a second call changes nothing."""
        try:
            self._connection.close()
        except OSError:
            logger.debug("The control connection was already closed")

    def _send(self, frame: Mapping[str, object]) -> None:
        try:
            self._connection.send_bytes(_encode_frame(frame))
        except (OSError, ValueError) as problem:
            msg = "The resident closed the control connection"
            raise ControlError(msg, code=ControlErrorCode.REFUSED) from problem

    def _receive(self) -> Mapping[str, object]:
        try:
            if not self._connection.poll(self._timeout_s):
                msg = "The resident did not answer in time"
                raise ControlError(msg, code=ControlErrorCode.INTERNAL)
            raw: bytes = self._connection.recv_bytes(maxlength=MAX_FRAME_BYTES)
        except (EOFError, OSError) as problem:
            msg = "The resident closed the control connection"
            raise ControlError(msg, code=ControlErrorCode.REFUSED) from problem
        frame: Mapping[str, object] | None = _decode_frame(raw)
        if frame is None:
            msg = "The resident answered with an unreadable frame"
            raise ControlError(msg, code=ControlErrorCode.INVALID_PAYLOAD)
        return frame


class _ServedConnection:
    """One accepted connection, its send lock and the bounded outbox of its events."""

    def __init__(self, connection: ChannelConnection) -> None:
        self._connection: ChannelConnection = connection
        self._send_lock: threading.Lock = threading.Lock()
        self._outbox: _EventOutbox = _EventOutbox(MAX_OUTBOX_EVENTS)
        self._pending: threading.Event = threading.Event()
        self._closed: threading.Event = threading.Event()
        self._writer: threading.Thread | None = None

    @property
    def subscribed(self) -> bool:
        """Whether this connection was turned into an event stream."""
        return self._writer is not None

    def subscribe(self) -> None:
        """Start publishing merged events to this connection."""
        if self._writer is not None:
            return
        self._writer = threading.Thread(target=self._publish_loop, name="anishift-control-events", daemon=True)
        self._writer.start()

    def publish(self, frame: Mapping[str, object]) -> None:
        """Queue one event, replacing the pending state of the same task."""
        self._outbox.put(frame)
        self._pending.set()

    def send(self, frame: Mapping[str, object]) -> bool:
        """Write one frame, reporting whether the connection is still usable."""
        payload: bytes = _encode_frame(frame)
        with self._send_lock:
            try:
                self._connection.send_bytes(payload)
            except OSError, ValueError:
                return False
        return True

    def receive(self) -> bytes | None:
        """Read one frame, returning ``None`` when the connection ended or overflowed."""
        try:
            return self._connection.recv_bytes(maxlength=MAX_FRAME_BYTES)
        except EOFError:
            return None
        except OSError:
            logger.warning("Dropped a control connection whose frame passed the size limit")
            return None

    def close(self) -> None:
        """Close the connection and let its event writer end."""
        self._closed.set()
        self._pending.set()
        try:
            self._connection.close()
        except OSError:
            logger.debug("A control connection was already closed")

    def _publish_loop(self) -> None:
        while not self._closed.is_set():
            self._pending.wait()
            self._pending.clear()
            for frame in self._outbox.drain():
                if self._closed.is_set() or not self.send(frame):
                    return


class _EventOutbox:
    """Latest event per task plus the other events, bounded so no client grows the queue."""

    def __init__(self, limit: int) -> None:
        self._limit: int = limit
        self._lock: threading.Lock = threading.Lock()
        self._pending: dict[tuple[str, str], Mapping[str, object]] = {}
        self._sequence: int = 0

    def put(self, frame: Mapping[str, object]) -> None:
        """Store *frame*, replacing the pending event of the same task."""
        with self._lock:
            key: tuple[str, str] = self._key(frame)
            if key in self._pending:
                self._pending[key] = frame
                return
            if len(self._pending) >= self._limit:
                self._pending.pop(next(iter(self._pending)))
            self._pending[key] = frame

    def drain(self) -> tuple[Mapping[str, object], ...]:
        """Take everything queued so far, in the order the events were first seen."""
        with self._lock:
            drained: tuple[Mapping[str, object], ...] = tuple(self._pending.values())
            self._pending.clear()
        return drained

    def _key(self, frame: Mapping[str, object]) -> tuple[str, str]:
        payload: object = frame.get("payload")
        task_id: object = payload.get("task_id") if isinstance(payload, dict) else None
        if isinstance(task_id, str) and task_id:
            return ("task", task_id)
        self._sequence += 1
        return ("event", str(self._sequence))


def _encode_frame(frame: Mapping[str, object]) -> bytes:
    return json.dumps(frame, ensure_ascii=False).encode("utf-8")


def _decode_frame(raw: bytes) -> Mapping[str, object] | None:
    try:
        document: object = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return None
    if not isinstance(document, dict) or document.get("v") != PROTOCOL_VERSION:
        return None
    return document


def _decode_request(raw: bytes) -> ControlRequest | None:
    frame: Mapping[str, object] | None = _decode_frame(raw)
    if frame is None:
        return None
    command_id: object = frame.get("command_id")
    kind: object = frame.get("kind")
    payload: object = frame.get("payload", {})
    instance_id: object = frame.get("instance_id")
    if not isinstance(command_id, str) or not command_id or not isinstance(kind, str) or not kind:
        return None
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        return None
    if instance_id is not None and not isinstance(instance_id, str):
        return None
    return ControlRequest(command_id=command_id, kind=kind, payload=payload, instance_id=instance_id)


def _response_frame(command_id: str, response: ControlResponse) -> dict[str, object]:
    if response.ok:
        return _result_frame(command_id, response.result)
    code: ControlErrorCode = response.code if response.code is not None else ControlErrorCode.INTERNAL
    return _error_frame(command_id, code, response.message)


def _result_frame(command_id: str, result: Mapping[str, object]) -> dict[str, object]:
    return {"v": PROTOCOL_VERSION, "command_id": command_id, "ok": True, "result": dict(result)}


def _error_frame(command_id: str, code: ControlErrorCode, message: str) -> dict[str, object]:
    return {
        "v": PROTOCOL_VERSION,
        "command_id": command_id,
        "ok": False,
        "error": {"code": code.value, "message": message},
    }


def _accepted_result(frame: Mapping[str, object], command_id: str) -> Mapping[str, object]:
    if frame.get("ok") is not True:
        error: object = frame.get("error")
        code: str = error.get("code", "") if isinstance(error, dict) else ""
        message: str = error.get("message", "") if isinstance(error, dict) else ""
        raise ControlError(message or "The resident refused the command", code=_error_code(code))
    if frame.get("command_id") != command_id:
        msg = "The resident answered a different command"
        raise ControlError(msg, code=ControlErrorCode.INVALID_PAYLOAD)
    result: object = frame.get("result")
    if not isinstance(result, dict):
        msg = "The resident answered without a result document"
        raise ControlError(msg, code=ControlErrorCode.INVALID_PAYLOAD)
    return result


def _error_code(value: str) -> ControlErrorCode:
    try:
        return ControlErrorCode(value)
    except ValueError:
        return ControlErrorCode.INTERNAL


def _new_command_id() -> str:
    return f"cmd-{os.urandom(_COMMAND_ID_BYTES).hex()}"


def _require_local_endpoint(endpoint: str) -> None:
    if is_windows() and not endpoint.startswith(_WINDOWS_PIPE_PREFIX):
        raise ControlError(_REMOTE_ENDPOINT, code=ControlErrorCode.REFUSED)


def _read_authkey(path: Path) -> bytes:
    try:
        key: bytes = path.read_bytes()
    except OSError as problem:
        msg = "The control key file cannot be read"
        raise ControlError(msg, code=ControlErrorCode.INTERNAL) from problem
    if len(key) != _AUTHKEY_BYTES:
        msg = "The control key file does not hold a complete key"
        raise ControlError(msg, code=ControlErrorCode.INTERNAL)
    return key


def _restrict_to_current_user(path: Path) -> None:
    """Take inheritance off the key file and grant the current account alone."""
    if not is_windows():
        return
    account: str | None = os.environ.get("USERNAME")
    if not account:
        logger.warning("Left the control key with inherited permissions; no account name was set")
        return
    command: list[str] = ["icacls", str(path), "/inheritance:r", "/grant:r", f"{account}:F"]
    try:
        completed: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603 - argv built here
            command,
            capture_output=True,
            timeout=_ICACLS_TIMEOUT_S,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        logger.warning("Could not restrict the control key to the current account")
        return
    if completed.returncode != 0:
        logger.warning("Restricting the control key reported a failure", exit_code=completed.returncode)
