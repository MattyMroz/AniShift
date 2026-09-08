from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Final

import pytest

from anishift.platform import local_control
from anishift.platform.local_control import (
    INSTANCE_FILE_NAME,
    KEY_FILE_NAME,
    MAX_FRAME_BYTES,
    MAX_OUTBOX_EVENTS,
    PROTOCOL_VERSION,
    ControlClient,
    ControlError,
    ControlErrorCode,
    ControlRequest,
    ControlResponse,
    ControlServer,
    InstanceRecord,
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
) -> tuple[ControlServer, str, bytes]:
    endpoint: str = control_endpoint(state_dir)
    key: bytes = ensure_authkey(state_dir)
    return ControlServer(endpoint, key, handler, max_connections=max_connections), endpoint, key


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
    assert refusal["error"] == {"code": ControlErrorCode.INVALID_PAYLOAD.value, "message": _UNREADABLE_FRAME}


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

    assert refusal["error"] == {"code": ControlErrorCode.INVALID_PAYLOAD.value, "message": _UNREADABLE_FRAME}


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
    assert answer == {"kind": "echo", "echo": "value"}


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
        outbox.put({"event": "state_changed", "payload": {"sequence": sequence}})

    assert len(outbox.drain()) == MAX_OUTBOX_EVENTS


def test_the_outbox_keeps_only_the_latest_event_of_one_task() -> None:
    outbox = local_control._EventOutbox(MAX_OUTBOX_EVENTS)

    for percent in (10, 40, 90):
        outbox.put({"event": "run_event", "payload": {"task_id": "task-1", "progress_percent": percent}})
    drained: tuple[Mapping[str, object], ...] = outbox.drain()

    assert len(drained) == 1
    assert _payload(drained[0])["progress_percent"] == 90


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


def test_the_key_is_created_once_and_read_back_unchanged(tmp_path: Path) -> None:
    state_dir: Path = _state_dir(tmp_path)

    created: bytes = ensure_authkey(state_dir)
    reused: bytes = ensure_authkey(state_dir)

    assert created == reused
    assert len(created) == _KEY_BYTES


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
            raise RuntimeError("handler")
        return _echo(request)

    server, endpoint, key = _serving(state_dir, broken)
    client = ControlClient(endpoint, key, timeout_s=_TIMEOUT_S)
    try:
        with pytest.raises(ControlError) as refusal:
            client.call("boom")
        answer: Mapping[str, object] = client.call("echo", {"echo": "value"})
    finally:
        client.close()
        server.close()

    assert refusal.value.code is ControlErrorCode.INTERNAL
    assert answer == {"kind": "echo", "echo": "value"}


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
