from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from anishift.application.sessions import RunSession
from anishift.config import workspace
from anishift.config.workspace import (
    RUN_OWNER_MARKER_NAME,
    cleanup_orphaned_temp,
    group_temp_dir,
    run_temp_dir,
)


def _write_owner(run_root: Path, *, pid: int) -> None:
    run_root.mkdir(parents=True)
    payload: dict[str, str | int] = {"pid": pid, "run_id": run_root.name}
    (run_root / RUN_OWNER_MARKER_NAME).write_text(json.dumps(payload), encoding="utf-8")


def test_temp_path_helpers_reject_path_escape(tmp_path: Path) -> None:
    assert run_temp_dir(tmp_path, "run-1") == tmp_path / "temp" / "run-1"
    assert group_temp_dir(tmp_path, "run-1", "group-2") == tmp_path / "temp" / "run-1" / "group-2"

    for unsafe_id in ("", ".", "..", "../outside", "nested/group", "nested\\group"):
        with pytest.raises(ValueError, match="safe path component"):
            run_temp_dir(tmp_path, unsafe_id)


def test_cleanup_removes_only_inactive_direct_run_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    orphan: Path = run_temp_dir(tmp_path, "orphan")
    active: Path = run_temp_dir(tmp_path, "active")
    live: Path = run_temp_dir(tmp_path, "live")
    _write_owner(orphan, pid=80)
    active.mkdir()
    _write_owner(live, pid=81)
    unrelated: Path = tmp_path / "temp" / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(workspace, "_process_is_running", lambda pid: pid == 81)

    removed: tuple[Path, ...] = cleanup_orphaned_temp(tmp_path, active_run_ids={"active"})

    assert removed == (orphan,)
    assert not orphan.exists()
    assert active.is_dir()
    assert live.is_dir()
    assert unrelated.is_file()


def test_cleanup_preserves_unmarked_and_invalidly_marked_directories(tmp_path: Path) -> None:
    unmarked: Path = run_temp_dir(tmp_path, "unmarked")
    invalid: Path = run_temp_dir(tmp_path, "invalid")
    unmarked.mkdir(parents=True)
    invalid.mkdir()
    (invalid / RUN_OWNER_MARKER_NAME).write_text("not-json", encoding="utf-8")

    assert cleanup_orphaned_temp(tmp_path, active_run_ids=()) == ()
    assert unmarked.is_dir()
    assert invalid.is_dir()


def test_live_run_marker_prevents_orphan_cleanup(tmp_path: Path) -> None:
    run_root: Path = run_temp_dir(tmp_path, "run-1")

    with RunSession(run_root) as session:
        group_root: Path = session.group_temp("group-1")
        marker: dict[str, object] = json.loads((run_root / RUN_OWNER_MARKER_NAME).read_text(encoding="utf-8"))
        assert marker["pid"] == os.getpid()
        assert marker["run_id"] == "run-1"
        assert cleanup_orphaned_temp(tmp_path, active_run_ids=()) == ()
        assert group_root == run_root / "group-1"

    assert not run_root.exists()


def test_run_session_reports_cleanup_failure_as_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_root: Path = run_temp_dir(tmp_path, "run-1")
    session = RunSession(run_root)

    with monkeypatch.context() as patch:
        patch.setattr("anishift.application.sessions.safe_rmtree", lambda path: _raise_permission_error(path))
        with session:
            session.group_temp("group-1")

    assert session.cleanup_warnings == ("Workflow run cleanup failed; AniShift will retry it on the next start.",)
    shutil.rmtree(run_root)


def test_cleanup_missing_temp_directory_is_empty(tmp_path: Path) -> None:
    assert cleanup_orphaned_temp(tmp_path, active_run_ids=()) == ()


def _raise_permission_error(path: Path) -> None:
    raise PermissionError(path)
