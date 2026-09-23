from __future__ import annotations

import json
import multiprocessing.connection as ipc
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Final
from unittest.mock import Mock

import pytest
from loguru import logger as loguru_logger

from anishift.platform import local_control
from anishift.platform.local_control import (
    INSTANCE_FILE_NAME,
    KEY_FILE_NAME,
    MAX_FRAME_BYTES,
    MAX_OUTBOX_EVENTS,
    PROTOCOL_VERSION,
    SOCKET_FILE_NAME,
    ChannelConnection,
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlRequest,
    ControlResponse,
    ControlServer,
    InstanceRecord,
    clear_endpoint,
    connect,
    connect_or_start,
    control_endpoint,
    ensure_authkey,
    read_instance,
    write_instance,
)

_TIMEOUT_S: Final[float] = 5.0

_FLOOD_EVENTS: Final[int] = 2000

_KEY_BYTES: Final[int] = 32

_TASK_COUNT: Final[int] = 3

_HANDSHAKE_S: Final[float] = 0.3

_UNREADABLE_FRAME: Final[str] = "The frame is not a valid control request"

_CLIENT_PROBE: Final[str] = """
import json, sys
from anishift.platform.local_control import ControlClient

endpoint, key_path, kind, variant = sys.argv[1:5]
key = open(key_path, "rb").read()
if variant == "wrong":
    key = bytes(byte ^ 0xFF for byte in key)
try:
    client = ControlClient(endpoint, key, timeout_s=5.0)
except Exception as problem:
    print(type(problem).__name__)
    raise SystemExit(0)
try:
    print(json.dumps(dict(client.call(kind, {"echo": "value"}))))
except Exception as problem:
    print(type(problem).__name__)
finally:
    client.close()
"""


def _echo(request: ControlRequest) -> ControlResponse:
    if request.kind != "echo":
        return ControlResponse.refused(ControlErrorCode.UNKNOWN_COMMAND, "no such command")
    return ControlResponse.succeeded({"kind": request.kind, **request.payload})


def _state_dir(tmp_path: Path) -> Path:
    state_dir: Path = tmp_path / f"watch-{os.urandom(4).hex()}"
    state_dir.mkdir(parents=True)
    return state_dir


def _serving(
    state_dir: Path,
    handler: Callable[[ControlRequest], ControlResponse] = _echo,
    *,
    max_connections: int = 8,
    handshake_timeout_s: float = _TIMEOUT_S,
) -> tuple[ControlServer, str, bytes]:
    endpoint: str = control_endpoint(state_dir)
    key: bytes = ensure_authkey(state_dir)
    server = ControlServer(
        endpoint,
        key,
        handler,
        max_connections=max_connections,
        handshake_timeout_s=handshake_timeout_s,
    )
    return server, endpoint, key


def _closed_within(connection: ChannelConnection, timeout_s: float) -> bool:
    try:
        if not connection.poll(timeout_s):
            return False
        connection.recv_bytes()
    except EOFError, OSError:
        return True
    return False


def _child_verdict(endpoint: str, key_path: Path, kind: str, variant: str) -> str:
    child: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _CLIENT_PROBE, endpoint, str(key_path), kind, variant],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    return child.stdout.strip()


def test_a_client_in_another_process_reaches_the_server_with_the_shared_key(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, _ = _serving(state_dir)
    try:
        answer: str = _child_verdict(endpoint, state_dir / KEY_FILE_NAME, "echo", "right")
    finally:
        server.close()

    assert json.loads(answer) == {"kind": "echo", "echo": "value"}


def test_a_client_with_a_wrong_key_is_rejected_and_the_server_keeps_serving(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    try:
        refused: str = _child_verdict(endpoint, state_dir / KEY_FILE_NAME, "echo", "wrong")
        client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            accepted: Mapping[str, object] = client.call("echo", {"echo": "value"})
        finally:
            client.close()
    finally:
        server.close()

    assert refused == "AuthenticationError"
    assert accepted == {"kind": "echo", "echo": "value"}


def test_a_frame_above_the_limit_ends_its_connection_and_leaves_the_server_serving(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    oversized = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        with pytest.raises(ControlError):
            oversized.call("echo", {"echo": "x" * (MAX_FRAME_BYTES + 1)})
        oversized.close()
        survivor = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            answer: Mapping[str, object] = survivor.call("echo", {"echo": "value"})
        finally:
            survivor.close()
    finally:
        server.close()

    assert answer == {"kind": "echo", "echo": "value"}


def test_a_frame_that_is_not_a_request_is_refused_as_an_invalid_payload(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        client._connection.send_bytes(b"{not json")
        refusal: Mapping[str, object] = client._receive()
    finally:
        client.close()
        server.close()

    assert refusal["ok"] is False
    assert refusal["error"] == {
        "code": ControlErrorCode.INVALID_PAYLOAD.value,
        "message": _UNREADABLE_FRAME,
        "reason": "",
    }


def test_a_frame_of_another_protocol_version_is_refused(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        client._send({"v": PROTOCOL_VERSION + 1, "command_id": "c", "kind": "echo", "payload": {}})
        refusal: Mapping[str, object] = client._receive()
    finally:
        client.close()
        server.close()

    assert refusal["error"] == {
        "code": ControlErrorCode.INVALID_PAYLOAD.value,
        "message": _UNREADABLE_FRAME,
        "reason": "",
    }


def test_an_unknown_command_is_refused_without_closing_the_connection(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        with pytest.raises(ControlError) as refusal:
            client.call("nonsense")
        answer: Mapping[str, object] = client.call("echo", {"echo": "value"})
    finally:
        client.close()
        server.close()

    assert refusal.value.code is ControlErrorCode.UNKNOWN_COMMAND
    assert refusal.value.context.suggestion == ""
    assert answer == {"kind": "echo", "echo": "value"}


def test_only_an_unanswered_command_suggests_checking_the_resident() -> None:
    unanswered: ControlError = ControlError("the endpoint is gone", code=ControlErrorCode.REFUSED)
    answered: ControlError = ControlError("the group is busy", code=ControlErrorCode.CONFLICT, answered=True)

    assert unanswered.context.suggestion == local_control._RESIDENT_CHECK
    assert unanswered.context.suggestion
    assert answered.context.suggestion == ""
    assert not unanswered.answered
    assert answered.answered


def test_a_command_can_execute_after_its_client_times_out_without_an_answer(tmp_path: Path) -> None:
    release: threading.Event = threading.Event()
    executed: threading.Event = threading.Event()

    def delayed(request: ControlRequest) -> ControlResponse:
        assert release.wait(_TIMEOUT_S)
        executed.set()
        return _echo(request)

    server, endpoint, key = _serving(_state_dir(tmp_path), delayed)
    client: ControlClient = ControlClient(endpoint, key, timeout_s=0.1)
    try:
        with pytest.raises(ControlError) as timeout:
            client.call("echo")
        assert timeout.value.code is ControlErrorCode.INTERNAL
        assert not timeout.value.answered
        assert not executed.is_set()
        release.set()
        assert executed.wait(_TIMEOUT_S)
    finally:
        release.set()
        client.close()
        server.close()


def test_a_flooded_subscriber_receives_merged_events_instead_of_every_frame(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    subscriber = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        subscriber.subscribe()
        for sequence in range(_FLOOD_EVENTS):
            server.broadcast(
                {
                    "event": "run_event",
                    "payload": {
                        "task_id": f"task-{sequence % _TASK_COUNT}",
                        "progress_percent": sequence % 101,
                    },
                }
            )
        events: Iterator[Mapping[str, object]] = subscriber.events()
        delivered: list[Mapping[str, object]] = [next(events)]
        server.close()
        delivered.extend(events)
    finally:
        subscriber.close()
        server.close()

    tasks: set[object] = {_payload(frame)["task_id"] for frame in delivered}
    assert len(delivered) < _FLOOD_EVENTS
    assert tasks <= {f"task-{index}" for index in range(_TASK_COUNT)}


def test_the_outbox_never_holds_more_than_its_limit() -> None:
    outbox = local_control._EventOutbox(MAX_OUTBOX_EVENTS)

    for sequence in range(_FLOOD_EVENTS):
        outbox.put({"event": "run_event", "payload": {"task_id": f"task-{sequence}"}}, terminal=False)

    assert len(outbox.drain()) == MAX_OUTBOX_EVENTS


def test_the_outbox_keeps_only_the_latest_event_of_one_task() -> None:
    outbox = local_control._EventOutbox(MAX_OUTBOX_EVENTS)

    for percent in (10, 40, 90):
        outbox.put(
            {"event": "run_event", "payload": {"task_id": "task-1", "progress_percent": percent}},
            terminal=False,
        )
    drained: tuple[Mapping[str, object], ...] = outbox.drain()

    assert len(drained) == 1
    assert _payload(drained[0])["progress_percent"] == 90


def test_the_outbox_merges_every_state_change_into_one_entry() -> None:
    outbox = local_control._EventOutbox(MAX_OUTBOX_EVENTS)

    for sequence in range(_FLOOD_EVENTS):
        outbox.put({"event": "state_changed", "payload": {"auto_enabled": sequence % 2 == 0}}, terminal=False)
    drained: tuple[Mapping[str, object], ...] = outbox.drain()

    assert len(drained) == 1
    assert _payload(drained[0])["auto_enabled"] is False


def test_the_outbox_drops_progress_before_a_terminal_event() -> None:
    outbox = local_control._EventOutbox(MAX_OUTBOX_EVENTS)

    outbox.put({"event": "run_event", "payload": {"task_id": "done", "state": "succeeded"}}, terminal=True)
    for sequence in range(_FLOOD_EVENTS):
        outbox.put({"event": "run_event", "payload": {"task_id": f"task-{sequence}"}}, terminal=False)
    drained: tuple[Mapping[str, object], ...] = outbox.drain()

    assert len(drained) == MAX_OUTBOX_EVENTS
    assert [frame for frame in drained if _payload(frame).get("task_id") == "done"]


def test_a_subscription_is_acknowledged_before_any_queued_event() -> None:
    reader, writer = ipc.Pipe(duplex=False)
    served = local_control._ServedConnection(writer)
    try:
        served.publish({"event": "run_event", "payload": {"task_id": "task-1"}}, False)
        acknowledged: bool = served.subscribe({"ok": True})
        first: object = json.loads(reader.recv_bytes().decode("utf-8"))
        second: object = json.loads(reader.recv_bytes().decode("utf-8"))
    finally:
        served.close()
        reader.close()

    assert acknowledged
    assert first == {"ok": True}
    assert isinstance(second, dict)
    assert _payload(second) == {"task_id": "task-1"}


@pytest.mark.parametrize("owner", ["client", "server"])
def test_concurrent_close_releases_the_connection_handle_once(
    owner: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader, writer = ipc.Pipe(duplex=False)
    monkeypatch.setattr(local_control, "_connected", lambda endpoint, timeout_s: writer)
    monkeypatch.setattr(local_control, "_prove_key", lambda *args, **kwargs: None)
    client: ControlClient = ControlClient(control_endpoint(tmp_path), b"0" * _KEY_BYTES)
    served: local_control._ServedConnection = local_control._ServedConnection(writer)
    close: Callable[[], None] = client.close if owner == "client" else served.close
    native_close: Callable[[], None] = writer._close  # type: ignore[attr-defined]
    released: threading.Event = threading.Event()
    finish: threading.Event = threading.Event()
    second_started: threading.Event = threading.Event()
    releases: list[int] = []

    def delayed_close() -> None:
        releases.append(1)
        if len(releases) != 1:
            return
        native_close()
        released.set()
        assert finish.wait(_TIMEOUT_S)

    def close_again() -> None:
        second_started.set()
        close()

    monkeypatch.setattr(writer, "_close", delayed_close)
    first: threading.Thread = threading.Thread(target=close)
    second: threading.Thread = threading.Thread(target=close_again)
    first.start()
    try:
        assert released.wait(_TIMEOUT_S)
        second.start()
        assert second_started.wait(_TIMEOUT_S)
        second.join(_HANDSHAKE_S)
        assert releases == [1]
    finally:
        finish.set()
        first.join(_TIMEOUT_S)
        if second.ident is not None:
            second.join(_TIMEOUT_S)
        reader.close()
        writer.close()

    assert not first.is_alive()
    assert not second.is_alive()
    assert writer.closed
    assert releases == [1]


def test_an_event_published_while_subscribe_returns_is_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    answer: Callable[[local_control._ServedConnection, Callable[[], Mapping[str, object]]], bool] = (
        local_control._ServedConnection.answer
    )

    def publish_after_ack(served: local_control._ServedConnection, produce: Callable[[], Mapping[str, object]]) -> bool:
        acknowledged: bool = answer(served, produce)
        server.broadcast({"event": "run_event", "payload": {"task_id": "done", "state": "succeeded"}}, terminal=True)
        return acknowledged

    monkeypatch.setattr(local_control._ServedConnection, "answer", publish_after_ack)
    client: ControlClient = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        client.subscribe()
        assert client._connection.poll(_HANDSHAKE_S)
        assert _payload(next(client.events())) == {"task_id": "done", "state": "succeeded"}
    finally:
        client.close()
        server.close()


def test_a_handshake_waits_for_its_timeout_to_finish_closing(monkeypatch: pytest.MonkeyPatch) -> None:
    reader, writer = ipc.Pipe(duplex=False)
    native_close: Callable[[], None] = writer._close  # type: ignore[attr-defined]
    released: threading.Event = threading.Event()
    finish: threading.Event = threading.Event()
    completed: threading.Event = threading.Event()
    guards: list[threading.Thread] = []

    def delayed_close() -> None:
        guards.append(threading.current_thread())
        native_close()
        released.set()
        assert finish.wait(_TIMEOUT_S)

    def disconnected(connection: ChannelConnection, key: bytes) -> None:
        assert released.wait(_TIMEOUT_S)
        raise EOFError

    def handshake() -> None:
        with pytest.raises(EOFError):
            local_control._prove_key(writer, b"0" * _KEY_BYTES, 0, listening=False)
        completed.set()

    monkeypatch.setattr(writer, "_close", delayed_close)
    monkeypatch.setattr(ipc, "answer_challenge", disconnected)
    thread: threading.Thread = threading.Thread(target=handshake)
    thread.start()
    try:
        assert released.wait(_TIMEOUT_S)
        assert not completed.wait(_HANDSHAKE_S)
    finally:
        finish.set()
        thread.join(_TIMEOUT_S)
        for guard in guards:
            guard.join(_TIMEOUT_S)
        reader.close()
        writer.close()

    assert not thread.is_alive()
    assert completed.is_set()
    assert writer.closed


def test_a_client_that_leaves_before_the_key_exchange_keeps_the_server_serving(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir)
    try:
        ipc.Client(endpoint).close()
        client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            answer: Mapping[str, object] = client.call("echo", {"echo": "value"})
        finally:
            client.close()
    finally:
        server.close()

    assert answer == {"kind": "echo", "echo": "value"}


def test_a_silent_client_is_dropped_after_the_handshake_deadline(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir, handshake_timeout_s=_HANDSHAKE_S)
    silent: ChannelConnection = ipc.Client(endpoint)
    try:
        assert silent.poll(_TIMEOUT_S)
        challenge: bytes = silent.recv_bytes()
        dropped: bool = _closed_within(silent, _TIMEOUT_S)
        client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            answer: Mapping[str, object] = client.call("echo", {"echo": "value"})
        finally:
            client.close()
    finally:
        silent.close()
        server.close()

    assert challenge
    assert dropped
    assert answer == {"kind": "echo", "echo": "value"}


def test_a_peer_that_never_answers_the_challenge_refuses_the_client_in_time(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    endpoint: str = control_endpoint(state_dir)
    key: bytes = ensure_authkey(state_dir)
    listener = ipc.Listener(endpoint)
    release = threading.Event()

    def mute() -> None:
        accepted: ChannelConnection = listener.accept()
        release.wait(timeout=_TIMEOUT_S)
        accepted.close()

    mute_thread = threading.Thread(target=mute, daemon=True)
    mute_thread.start()
    started: float = time.monotonic()
    try:
        with pytest.raises(ControlError) as refusal:
            ControlClient(endpoint, key, timeout_s=_HANDSHAKE_S)
        elapsed: float = time.monotonic() - started
    finally:
        release.set()
        mute_thread.join(timeout=_TIMEOUT_S)
        listener.close()

    assert refusal.value.code is ControlErrorCode.REFUSED
    assert elapsed < _TIMEOUT_S


def test_a_stale_socket_file_is_cleared_and_a_missing_one_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(local_control, "is_windows", lambda: False)
    stale: Path = tmp_path / SOCKET_FILE_NAME
    stale.write_bytes(b"")

    clear_endpoint(str(stale))
    clear_endpoint(str(stale))

    assert not stale.exists()


def test_connect_or_start_starts_one_resident_and_reuses_the_running_one(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    starts: list[int] = []
    server, endpoint, _ = _serving(state_dir)

    def spawn() -> None:
        starts.append(1)
        write_instance(
            state_dir,
            InstanceRecord(instance_id="instance-1", pid=os.getpid(), endpoint=endpoint, started_at="now"),
        )

    try:
        first: ControlClient = connect_or_start(state_dir, spawn=spawn, timeout_s=_TIMEOUT_S)
        assert first.call("echo", {"echo": "value"})
        first.close()
        second: ControlClient = connect_or_start(state_dir, spawn=spawn, timeout_s=_TIMEOUT_S)
        assert second.call("echo", {"echo": "value"})
        second.close()
    finally:
        server.close()

    assert starts == [1]


def test_connect_reports_nothing_without_a_recorded_instance(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    ensure_authkey(state_dir)

    assert connect(state_dir, timeout_s=_TIMEOUT_S) is None


def test_an_endpoint_on_another_machine_is_refused_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_control, "is_windows", lambda: True)

    with pytest.raises(ControlError) as refusal:
        ControlClient(r"\\other-machine\pipe\anishift", b"0" * _KEY_BYTES)

    assert refusal.value.code is ControlErrorCode.REFUSED


def test_the_endpoint_of_a_state_directory_stays_local_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(local_control, "is_windows", lambda: True)

    assert control_endpoint(tmp_path).startswith("\\\\.\\pipe\\anishift-")


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("returncode", [0, 1])
def test_the_key_is_created_once_and_read_back_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, windows: bool, returncode: int
) -> None:
    state_dir: Path = _state_dir(tmp_path)
    run: Mock = Mock(return_value=subprocess.CompletedProcess([], returncode, stdout=b"", stderr=b""))
    monkeypatch.setattr(local_control, "is_windows", lambda: windows)
    monkeypatch.setenv("USERNAME", "test-account")
    monkeypatch.setattr(subprocess, "run", run)

    created: bytes = ensure_authkey(state_dir)
    reused: bytes = ensure_authkey(state_dir)

    assert created == reused
    assert len(created) == _KEY_BYTES
    if windows:
        run.assert_called_once_with(
            [
                "icacls",
                str(state_dir / KEY_FILE_NAME),
                "/inheritance:r",
                "/grant:r",
                "test-account:F",
                "/remove:g",
                "*S-1-5-18",
                "*S-1-5-32-544",
                "*S-1-5-32-545",
                "*S-1-5-11",
                "*S-1-1-0",
            ],
            capture_output=True,
            timeout=10.0,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    else:
        run.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="the key file is restricted through Windows ACLs")
def test_the_key_file_grants_only_the_current_account(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    ensure_authkey(state_dir)

    argv: list[str] = ["icacls", str(state_dir / KEY_FILE_NAME)]
    listing: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - fixed argv
        argv,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    permissions: str = listing.stdout.casefold()
    assert os.environ["USERNAME"].casefold() in permissions
    assert "system:(" not in permissions
    assert "administrators:(" not in permissions
    assert "everyone:(" not in permissions


def test_the_recorded_instance_survives_a_round_trip(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    record = InstanceRecord(instance_id="instance-1", pid=4321, endpoint="endpoint", started_at="2026-09-08T00:00:00Z")

    write_instance(state_dir, record)

    assert read_instance(state_dir) == record


def test_a_damaged_instance_record_names_no_resident(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    (state_dir / INSTANCE_FILE_NAME).write_text("{ broken", encoding="utf-8")

    assert read_instance(state_dir) is None


def test_a_client_over_the_connection_limit_is_refused(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    server, endpoint, key = _serving(state_dir, max_connections=1)
    held = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        assert held.call("echo", {"echo": "value"})
        extra = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
        try:
            with pytest.raises(ControlError) as refusal:
                extra.call("echo", {"echo": "value"})
        finally:
            extra.close()
    finally:
        held.close()
        server.close()

    assert refusal.value.code is ControlErrorCode.REFUSED


def test_a_handler_fault_is_answered_without_dropping_the_channel(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)

    def broken(request: ControlRequest) -> ControlResponse:
        if request.kind == "boom":
            raise RuntimeError("private-handler-payload")
        return _echo(request)

    server, endpoint, key = _serving(state_dir, broken)
    client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    captured: list[str] = []
    handler_id: int = loguru_logger.add(
        captured.append,
        format="{message} {extra}",
        level="WARNING",
        filter=lambda record: record["extra"].get("command_id") == "handler-fault",
    )
    try:
        with pytest.raises(ControlError) as refusal:
            client.call("boom", command_id="handler-fault")
        answer: Mapping[str, object] = client.call("echo", {"echo": "value"})
    finally:
        loguru_logger.remove(handler_id)
        client.close()
        server.close()

    assert refusal.value.code is ControlErrorCode.INTERNAL
    assert refusal.value.answered
    assert answer == {"kind": "echo", "echo": "value"}
    assert "RuntimeError" in "".join(captured)
    assert "handler-fault" in "".join(captured)
    assert "internal" in "".join(captured)
    assert "private-handler-payload" not in "".join(captured)


def test_a_slow_handler_never_blocks_another_connection(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def blocking(request: ControlRequest) -> ControlResponse:
        if request.kind != "slow":
            return _echo(request)
        entered.set()
        assert release.wait(timeout=_TIMEOUT_S)
        return ControlResponse.succeeded({"kind": request.kind})

    server, endpoint, key = _serving(state_dir, blocking)
    slow = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    fast = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    slow_answers: list[Mapping[str, object]] = []
    thread = threading.Thread(target=lambda: slow_answers.append(slow.call("slow")), daemon=True)
    try:
        thread.start()
        assert entered.wait(timeout=_TIMEOUT_S)
        answer: Mapping[str, object] = fast.call("echo", {"echo": "value"})
        release.set()
        thread.join(timeout=_TIMEOUT_S)
    finally:
        release.set()
        thread.join(timeout=_TIMEOUT_S)
        slow.close()
        fast.close()
        server.close()

    assert answer == {"kind": "echo", "echo": "value"}
    assert slow_answers == [{"kind": "slow"}]


def _payload(frame: Mapping[str, object]) -> Mapping[str, object]:
    payload: object = frame["payload"]
    assert isinstance(payload, dict)
    return payload
