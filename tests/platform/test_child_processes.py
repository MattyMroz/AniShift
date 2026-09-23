from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from anishift.platform.qbittorrent_process import _process_identity


@pytest.mark.integration
@pytest.mark.skipif(sys.platform != "win32", reason="Windows job ownership")
def test_owner_death_stops_inherited_tools_but_preserves_independent_clients(tmp_path: Path) -> None:
    script: str = """
import json
import subprocess
import sys
import time
from pathlib import Path
from anishift.platform.child_processes import contain_children, independent_child_flags
root = Path(sys.argv[1])
contain_children()
worker = (
    'import sys,time; from pathlib import Path; stop=Path(sys.argv[1]); '
    'deadline=time.monotonic()+30; '
    'exec("while not stop.exists() and time.monotonic()<deadline: time.sleep(0.05)")'
)
command = [sys.executable, '-c', worker, str(root / 'stop')]
tool = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
client = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | independent_child_flags())
(root / 'pids.json').write_text(json.dumps([tool.pid, client.pid]), encoding='utf-8')
time.sleep(30)
"""
    parent: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", script, str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    children: list[int] = []
    try:
        deadline: float = time.monotonic() + 10.0
        receipt: Path = tmp_path / "pids.json"
        while not receipt.exists() and parent.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert receipt.exists(), parent.communicate(timeout=2)[1]
        children = json.loads(receipt.read_text(encoding="utf-8"))
        assert all(_process_identity(pid) is not None for pid in children)
        parent.terminate()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5.0
        while _process_identity(children[0]) is not None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert _process_identity(children[0]) is None
        assert _process_identity(children[1]) is not None
    finally:
        (tmp_path / "stop").touch()
        if parent.poll() is None:
            parent.terminate()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 5.0
        while any(_process_identity(pid) is not None for pid in children) and time.monotonic() < deadline:
            time.sleep(0.02)
