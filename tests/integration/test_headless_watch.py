from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

import pytest

from anishift.cli.watch import STOP_FILE_NAME
from anishift.config.workspace import ENV_WORKSPACE_ROOT

_PROBE_TIMEOUT: Final[int] = 120

_BATCH_DEADLINE_S: Final[float] = 60.0

_POLL_S: Final[float] = 0.05

_HEADLESS_PROBE: Final[str] = """
import importlib
import sys
from pathlib import Path

from anishift.utils.logger import setup_mode_from_env, shutdown_logger

state_dir = Path(sys.argv[1])
log_path = Path(sys.argv[2])
state_dir.mkdir(parents=True, exist_ok=True)

app_watch = importlib.import_module("anishift.application.watch")
cli_watch = importlib.import_module("anishift.cli.watch")
cli_main = importlib.import_module("anishift.cli.main")
app_watch.QUIET_S = 0.2
cli_watch.SCAN_INTERVAL_S = 0.2
cli_watch.watch_state_dir = lambda: state_dir
cli_watch._check_subscriptions = lambda service, now, checked_at: checked_at

setup_mode_from_env(console_enabled=False, file_path=log_path)
sys.argv = ["anishift", "watch", "--headless"]
code = 0
try:
    cli_main.app()
except SystemExit as leaving:
    code = leaving.code if isinstance(leaving.code, int) else 0
shutdown_logger()
print(code, flush=True)
"""


def _messages(log_path: Path) -> list[str]:
    if not log_path.is_file():
        return []
    lines: list[str] = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    found: list[str] = []
    for line in lines:
        try:
            found.append(json.loads(line)["record"]["message"])
        except ValueError, KeyError:
            continue
    return found


def _wait_for(log_path: Path, message: str, process: subprocess.Popen[str]) -> list[str]:
    deadline: float = time.monotonic() + _BATCH_DEADLINE_S
    while time.monotonic() < deadline:
        found: list[str] = _messages(log_path)
        if message in found:
            return found
        if process.poll() is not None:
            pytest.fail(f"the headless watch left before logging {message!r}: {found}")
        time.sleep(_POLL_S)
    pytest.fail(f"the headless watch never logged {message!r}: {_messages(log_path)}")


@pytest.mark.integration
def test_a_headless_watch_runs_a_batch_and_stops_on_request_without_a_terminal(tmp_path: Path) -> None:
    workspace: Path = tmp_path / "workspace"
    (workspace / "Test").mkdir(parents=True)
    (workspace / "Test" / "probe.txt").write_text("probe\n", encoding="utf-8")
    state_dir: Path = tmp_path / "watch"
    log_path: Path = tmp_path / "watch.log.jsonl"
    environment: dict[str, str] = {
        name: value for name, value in os.environ.items() if not name.startswith("ANISHIFT_")
    }
    environment[ENV_WORKSPACE_ROOT] = str(workspace)

    process: subprocess.Popen[str] = subprocess.Popen(  # noqa: S603 - fixed probe on this interpreter
        [sys.executable, "-c", _HEADLESS_PROBE, str(state_dir), str(log_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        messages: list[str] = _wait_for(log_path, "Batch finished", process)
    finally:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / STOP_FILE_NAME).touch()
        stdout, stderr = process.communicate(timeout=_PROBE_TIMEOUT)

    assert process.returncode == 0, stderr
    assert stdout.strip().splitlines()[-1] == "0"
    assert messages[0] == "Watch started"
    assert "Batch started" in messages
    assert not (state_dir / "daemon.pid").exists()
