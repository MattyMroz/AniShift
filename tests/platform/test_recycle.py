from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO, cast

import pytest

import anishift.platform.recycle as recycle_module
import anishift.platform.recycle_worker as worker_module
from anishift.platform.recycle import RecycleResult, recycle_file


@pytest.mark.parametrize("output", ["{}", "broken", '{"outcome":"recycled","reason":"ok","receipt":null}'])
def test_recycle_requires_complete_native_evidence(output: str) -> None:
    assert recycle_module._decode_result(output).outcome == "uncertain"


def test_recycle_flags_never_auto_confirm_permanent_destruction() -> None:
    assert not worker_module._RECYCLE_FLAGS & 0x10
    assert worker_module._RECYCLE_FLAGS & 0x4000
    assert worker_module._RECYCLE_FLAGS & 0x80000
    assert worker_module._RECYCLE_FLAGS & 0x100000


@pytest.mark.parametrize("mode", ["success", "timeout", "crash"])
def test_recycle_bounds_the_actual_interpreter_process_and_treats_timeout_as_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    calls: list[str] = []
    captured: dict[str, object] = {}

    class Process:
        returncode: int = 1 if mode == "crash" else 0
        stdin: TextIO | None = None
        stdout: TextIO | None = None
        stderr: TextIO | None = None

        def __enter__(self) -> Process:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def communicate(self, value: str | None = None, *, timeout: float | None = None) -> tuple[str, None]:
            calls.append("communicate")
            if value is not None:
                captured["payload"] = json.loads(value)
            if mode == "timeout" and timeout is not None:
                raise subprocess.TimeoutExpired("owned-helper", timeout)
            return json.dumps({"outcome": "recycled", "reason": "recycle_completed", "receipt": "exact-item"}), None

        def kill(self) -> None:
            calls.append("kill")

        def wait(self, *, timeout: float) -> int:
            return self.returncode

    def popen(command: list[str], **kwargs: object) -> Process:
        captured.update(command=command, **kwargs)
        return Process()

    monkeypatch.setattr(recycle_module, "is_windows", lambda: True)
    monkeypatch.setattr(sys, "_base_executable", "actual-python.exe", raising=False)
    monkeypatch.setattr(subprocess, "Popen", popen)
    result: RecycleResult = recycle_file(tmp_path / "synthetic.txt", (1, 2, 3, 4))
    assert captured["command"] == ["actual-python.exe", "-m", "anishift.platform.recycle_worker"]
    assert cast("dict[str, object]", captured["payload"])["parent_pid"] == os.getpid()
    assert cast("dict[str, str]", captured["env"])["__PYVENV_LAUNCHER__"] == sys.executable
    assert result.outcome == ("recycled" if mode == "success" else "uncertain")
    assert calls == (["communicate", "kill", "communicate"] if mode == "timeout" else ["communicate"])


def test_helper_cleanup_returns_with_an_inherited_pipe_open_without_killing_its_holder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release: Path = tmp_path / "release"
    ready: Path = tmp_path / "ready"
    survived: Path = tmp_path / "survived"
    holder: str = (
        "import pathlib,sys,time; "
        "release,ready,survived=map(pathlib.Path,sys.argv[1:]); "
        "ready.touch(); "
        "exec('while not release.exists():\\n time.sleep(0.01)'); "
        "survived.touch()"
    )
    helper: str = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-c',sys.argv[1],*sys.argv[2:]], "
        "stdin=subprocess.DEVNULL,stdout=sys.stdout,stderr=subprocess.DEVNULL); time.sleep(15)"
    )
    original_popen: type[subprocess.Popen[str]] = subprocess.Popen
    processes: list[subprocess.Popen[str]] = []
    results: list[RecycleResult] = []
    entered: threading.Event = threading.Event()

    def popen(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
        process: subprocess.Popen[str] = original_popen(
            [
                str(getattr(sys, "_base_executable", sys.executable)),
                "-c",
                helper,
                holder,
                str(release),
                str(ready),
                str(survived),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        processes.append(process)
        deadline: float = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        entered.set()
        return process

    monkeypatch.setattr(recycle_module, "is_windows", lambda: True)
    monkeypatch.setattr(recycle_module, "RECYCLE_TIMEOUT_S", 0.1)
    monkeypatch.setattr(recycle_module, "RECYCLE_CLEANUP_TIMEOUT_S", 0.1)
    monkeypatch.setattr(subprocess, "Popen", popen)
    call: threading.Thread = threading.Thread(
        target=lambda: results.append(recycle_file(tmp_path / "synthetic.txt", (1, 2, 3, 4))),
        daemon=True,
    )
    call.start()
    try:
        assert entered.wait(6)
        call.join(2)
        assert not call.is_alive()
        assert results == [RecycleResult("uncertain", "recycle_cleanup_timeout")]
        assert processes[0].poll() is not None
        assert not survived.exists()
    finally:
        release.touch()
        call.join(5)
        deadline: float = time.monotonic() + 5
        while not survived.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    assert survived.exists()
    assert processes[0].stdout is not None
    deadline = time.monotonic() + 5
    while not processes[0].stdout.closed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert processes[0].stdout.closed


@pytest.mark.parametrize("flags", [0x280, 0x200, 0x202])
def test_native_predelete_veto_is_a_real_callback_hresult(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: int
) -> None:
    path: Path = tmp_path / "synthetic.txt"
    path.write_bytes(b"unchanged")
    identity: tuple[int, int, int, int] | None = worker_module._identity(path)
    assert identity is not None
    monkeypatch.setattr(
        worker_module, "_callback_type", lambda *types: ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)
    )
    sink: worker_module._ProgressSink = worker_module._ProgressSink(path, identity, cast("ctypes.CDLL", object()))
    result: int = sink.callbacks[11](ctypes.byref(sink.pointer), flags, None)
    assert result == (0 if flags == 0x280 else -2147467259)
    assert path.read_bytes() == b"unchanged"


def test_native_callback_exception_returns_failure_and_poisoned_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path: Path = tmp_path / "synthetic.txt"
    path.write_bytes(b"unchanged")
    identity: tuple[int, int, int, int] | None = worker_module._identity(path)
    assert identity is not None
    monkeypatch.setattr(
        worker_module, "_callback_type", lambda *types: ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)
    )

    def broken_identity(_path: Path) -> None:
        raise RuntimeError

    monkeypatch.setattr(worker_module, "_identity", broken_identity)
    sink: worker_module._ProgressSink = worker_module._ProgressSink(path, identity, cast("ctypes.CDLL", object()))
    assert sink.callbacks[11](ctypes.byref(sink.pointer), 0x280, None) == -2147467259
    assert sink.failed
    assert path.read_bytes() == b"unchanged"


def test_native_postdelete_cannot_succeed_without_a_recycled_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module, "_callback_type", lambda *types: ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *types)
    )
    sink: worker_module._ProgressSink = worker_module._ProgressSink(
        tmp_path / "synthetic.txt", (1, 2, 3, 4), cast("ctypes.CDLL", object())
    )
    sink.allowed = True
    assert sink.callbacks[12](ctypes.byref(sink.pointer), 0x280, None, 0, None) == -2147467259
    assert sink.receipt is None
