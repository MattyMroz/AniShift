from __future__ import annotations

import ctypes
import io
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from typing import cast

import pytest

import anishift.platform.recycle as recycle_module
import anishift.platform.recycle_worker as worker_module
from anishift.platform.recycle import RecycleResult, RestoreRequest, recycle_session, restore_session


@pytest.mark.parametrize(
    "output",
    [
        "{}",
        "broken",
        '{"outcome":"recycled","reason":"ok","receipt":null,"path":"01.mkv"}',
        '{"outcome":"refused","reason":"ok","receipt":null,"path":"02.mkv"}',
        '{"outcome":"refused","reason":"ok","receipt":null}',
    ],
)
def test_recycle_requires_complete_native_evidence_for_the_requested_file(output: str) -> None:
    assert recycle_module._decode_result(output, "01.mkv").outcome == "uncertain"


def test_recycle_flags_never_auto_confirm_permanent_destruction() -> None:
    assert not worker_module._RECYCLE_FLAGS & 0x10
    assert worker_module._RECYCLE_FLAGS & 0x4000
    assert worker_module._RECYCLE_FLAGS & 0x80000
    assert worker_module._RECYCLE_FLAGS & 0x100000


_FAKE_HELPER: str = (
    "import json,pathlib,sys,time\n"
    "mode,log=sys.argv[1],pathlib.Path(sys.argv[2])\n"
    "for line in sys.stdin:\n"
    "    with log.open('a',encoding='utf-8') as handle: handle.write(line)\n"
    "    if mode=='crash': sys.exit(3)\n"
    "    if mode=='silent': time.sleep(30)\n"
    "    payload=json.loads(line)\n"
    "    name=pathlib.Path(str(payload.get('path'))).name\n"
    "    answer=({'outcome':'refused','reason':'recycle_refused','receipt':None} if 'refuse' in name else\n"
    "        {'outcome':'ready','reason':'restore_ready_bin','receipt':None} if payload.get('check_only') else\n"
    "        {'outcome':'restored','reason':'restore_completed','receipt':None} if 'operation' in payload else\n"
    "        {'outcome':'recycled','reason':'recycle_completed','receipt':'item-'+name})\n"
    "    echo=payload.get('path') if mode!='foreign' else 'foreign.mkv'\n"
    "    print(json.dumps({**answer,'path':echo}),flush=True)\n"
)


def _fake_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: str
) -> tuple[list[list[str]], list[dict[str, object]], Path]:
    commands: list[list[str]] = []
    options: list[dict[str, object]] = []
    log: Path = tmp_path / "requests.jsonl"
    original_popen: type[subprocess.Popen[str]] = subprocess.Popen

    def popen(command: list[str], **kwargs: object) -> subprocess.Popen[str]:
        commands.append(command)
        options.append(kwargs)
        return original_popen(
            [str(getattr(sys, "_base_executable", sys.executable)), "-c", _FAKE_HELPER, mode, str(log)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )

    monkeypatch.setattr(recycle_module, "is_windows", lambda: True)
    monkeypatch.setattr(subprocess, "Popen", popen)
    return commands, options, log


def _logged(log: Path) -> list[dict[str, object]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_recycle_session_reports_each_file_of_a_set_from_one_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, options, log = _fake_helper(monkeypatch, tmp_path, "answer")
    names: tuple[str, ...] = ("01.mkv", "02-refuse.mkv", "03.mkv")
    with recycle_session() as recycle:
        results: list[RecycleResult] = [recycle(tmp_path / name, (1, 2, 3, index)) for index, name in enumerate(names)]
    assert results == [
        RecycleResult("recycled", "recycle_completed", "item-01.mkv"),
        RecycleResult("refused", "recycle_refused"),
        RecycleResult("recycled", "recycle_completed", "item-03.mkv"),
    ]
    assert len(commands) == 1
    assert commands[0][1:] == ["-m", "anishift.platform.recycle_worker"]
    assert cast("dict[str, str]", options[0]["env"])["__PYVENV_LAUNCHER__"] == sys.executable
    sent: list[dict[str, object]] = _logged(log)
    assert [Path(str(item["path"])).name for item in sent] == list(names)
    assert [item["identity"] for item in sent] == [[1, 2, 3, index] for index in range(3)]
    assert {item["parent_pid"] for item in sent} == {os.getpid()}


def test_restore_session_checks_and_restores_every_item_through_one_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands, _options, log = _fake_helper(monkeypatch, tmp_path, "answer")
    requests: list[RestoreRequest] = [
        RestoreRequest(tmp_path, f"ready/{index}.mkv", f"tmp/.restore-one/{index}", (1, 2, 3, index), f"bin-{index}")
        for index in range(2)
    ]
    with restore_session() as restore:
        checks: list[RecycleResult] = [restore(request, True) for request in requests]
        results: list[RecycleResult] = [restore(request, False) for request in requests]
    assert {item.outcome for item in checks} == {"ready"}
    assert {item.outcome for item in results} == {"restored"}
    assert len(commands) == 1
    assert [(item["operation"], item["path"], item["check_only"]) for item in _logged(log)] == [
        ("restore", "ready/0.mkv", True),
        ("restore", "ready/1.mkv", True),
        ("restore", "ready/0.mkv", False),
        ("restore", "ready/1.mkv", False),
    ]


@pytest.mark.parametrize(
    ("mode", "reason"),
    [("silent", "recycle_timeout"), ("crash", "recycle_interrupted"), ("foreign", "recycle_invalid_evidence")],
)
def test_recycle_session_lost_or_foreign_answer_is_uncertain_and_never_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, reason: str
) -> None:
    commands, _options, log = _fake_helper(monkeypatch, tmp_path, mode)
    monkeypatch.setattr(recycle_module, "RECYCLE_TIMEOUT_S", 0.5)
    with recycle_session() as recycle:
        first: RecycleResult = recycle(tmp_path / "01.mkv", (1, 2, 3, 4))
        second: RecycleResult = recycle(tmp_path / "02.mkv", (1, 2, 3, 5))
    assert first == RecycleResult("uncertain", reason)
    assert second == RecycleResult("refused", "recycle_unavailable")
    assert len(commands) == 1
    assert [Path(str(item["path"])).name for item in _logged(log)] == ["01.mkv"]


def test_recycle_session_without_a_request_starts_no_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands, _options, _log = _fake_helper(monkeypatch, tmp_path, "answer")
    with recycle_session():
        pass
    assert commands == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows recycle worker")
def test_worker_isolates_once_and_answers_every_request_line_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    isolations: list[str] = []
    monkeypatch.setattr(worker_module, "_watch_parent", lambda pid: isolations.append(f"parent-{pid}"))
    monkeypatch.setattr(worker_module, "_private_desktop", lambda: isolations.append("desktop"))
    monkeypatch.setattr(worker_module, "_supported_path", lambda path: True)
    monkeypatch.setattr(worker_module, "_identity", lambda path: (1, 2, 3, 4))
    monkeypatch.setattr(worker_module, "_locked_source", lambda *args: nullcontext())
    monkeypatch.setattr(
        worker_module,
        "_native_recycle",
        lambda path, identity: RecycleResult("recycled", "recycle_completed", f"item-{path.name}"),
    )
    lines: str = "".join(
        json.dumps({"path": str(tmp_path / name), "identity": [1, 2, 3, 4], "parent_pid": 7}) + "\n"
        for name in ("01.mkv", "02.mkv", "03.mkv")
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    worker_module._isolate.cache_clear()
    try:
        worker_module.main()
    finally:
        worker_module._isolate.cache_clear()
    answers: list[dict[str, object]] = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [item["receipt"] for item in answers] == ["item-01.mkv", "item-02.mkv", "item-03.mkv"]
    assert [item["path"] for item in answers] == [str(tmp_path / name) for name in ("01.mkv", "02.mkv", "03.mkv")]
    assert isolations == ["parent-7", "desktop"]


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

    def call_once() -> None:
        with recycle_session() as recycle:
            results.append(recycle(tmp_path / "synthetic.txt", (1, 2, 3, 4)))

    call: threading.Thread = threading.Thread(target=call_once, daemon=True)
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
