from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from anishift.application.cancellation import EventCancellationToken
from anishift.application.sessions import RunSession
from anishift.errors import ExecutionError, RunConflictError


def _raise_inside_session(run_root: Path) -> None:
    with RunSession(run_root) as session:
        session.group_temp("group-1")
        raise RuntimeError("handler failed")


def test_run_session_cleans_successful_scope_and_rejects_late_generation(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"
    session = RunSession(run_root)

    with session:
        generation: int = session.generation
        group_root: Path = session.group_temp("group-1")
        (group_root / "clip.wav").write_bytes(b"audio")
        assert session.accepts_generation(generation)

    assert not run_root.exists()
    assert session.accepts_generation(generation) is False


def test_run_session_cleans_scope_after_exception(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"

    with pytest.raises(RuntimeError, match="handler failed"):
        _raise_inside_session(run_root)

    assert not run_root.exists()


def test_run_session_cleans_scope_after_cancel(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"
    cancel = EventCancellationToken()

    with RunSession(run_root) as session:
        session.group_temp("group-1")
        cancel.cancel()
        assert cancel.is_cancelled()

    assert not run_root.exists()


def test_run_session_refuses_existing_directory_without_deleting_it(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"
    run_root.mkdir()
    sentinel = run_root / "owned-by-other-process"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(RunConflictError), RunSession(run_root):
        raise AssertionError

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_old_session_does_not_delete_recreated_root_owned_by_another_run(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"
    session = RunSession(run_root)
    session.__enter__()
    shutil.rmtree(run_root)
    run_root.mkdir()
    sentinel = run_root / "new-owner"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(RunConflictError, match="ownership changed"):
        session.__exit__(None, None, None)

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_active_session_claim_prevents_same_process_reuse_after_root_disappears(tmp_path: Path) -> None:
    run_root = tmp_path / "run-1"
    first = RunSession(run_root)

    with first:
        shutil.rmtree(run_root)
        with pytest.raises(RunConflictError, match="already in use"):
            RunSession(run_root).__enter__()


def test_failed_enter_releases_process_local_root_claim(tmp_path: Path) -> None:
    parent = tmp_path / "blocked-parent"
    parent.write_text("file", encoding="utf-8")
    run_root = parent / "run-1"

    with pytest.raises(RunConflictError, match="already in use"):
        RunSession(run_root).__enter__()
    parent.unlink()
    parent.mkdir()
    with RunSession(run_root):
        assert run_root.is_dir()


def test_group_temp_rejects_escape_and_inactive_session(tmp_path: Path) -> None:
    session = RunSession(tmp_path / "run-1")

    with pytest.raises(ExecutionError, match="active"):
        session.group_temp("group-1")
    with session, pytest.raises(ValueError, match="safe group ID"):
        session.group_temp("../outside")
