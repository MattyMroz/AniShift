from __future__ import annotations

from pathlib import Path

import pytest

from anishift.config.workspace import (
    DEFAULT_SUBDIRS,
    ENV_WORKSPACE_ROOT,
    ReservedNameConflict,
    ensure_workspace_dir,
    occupied_task_dirs,
    resolve_workspace_root,
)
from anishift.paths import TASK_DIRECTORIES


def test_resolve_workspace_root_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_WORKSPACE_ROOT, str(tmp_path))
    assert resolve_workspace_root() == tmp_path.resolve()


def test_resolve_workspace_root_blank_env_falls_back_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_WORKSPACE_ROOT, "   ")
    assert resolve_workspace_root().name == "workspace"


def test_ensure_workspace_dir_creates_only_default_subdirs(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    assert ensure_workspace_dir(root) == ()
    assert root.is_dir()
    assert sorted(p.name for p in root.iterdir()) == sorted(DEFAULT_SUBDIRS)
    assert DEFAULT_SUBDIRS == ("temp", "subs", "translate", "audiobook", "cover")
    assert DEFAULT_SUBDIRS[1:] == TASK_DIRECTORIES


def test_ensure_workspace_dir_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    ensure_workspace_dir(root)
    (root / "subs" / "01.mkv").write_bytes(b"kept")
    assert ensure_workspace_dir(root) == ()
    assert (root / "temp").is_dir()
    assert (root / "subs" / "01.mkv").read_bytes() == b"kept"


def test_a_file_holding_a_task_name_refuses_only_that_place_and_survives(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "cover").write_text("mine", encoding="utf-8")
    conflicts = ensure_workspace_dir(root)
    assert [(item.name, item.kind) for item in conflicts] == [("cover", ReservedNameConflict.NOT_A_DIRECTORY)]
    assert (root / "cover").read_text(encoding="utf-8") == "mine"
    assert conflicts[0].message.startswith("cover: ")
    assert all((root / name).is_dir() for name in ("temp", "subs", "translate", "audiobook"))


def test_a_link_holding_a_task_name_is_refused_and_never_followed(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.txt").write_text("outside", encoding="utf-8")
    try:
        (root / "translate").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this system")
    conflicts = ensure_workspace_dir(root)
    assert [(item.name, item.kind) for item in conflicts] == [("translate", ReservedNameConflict.LINK)]
    assert (elsewhere / "keep.txt").read_text(encoding="utf-8") == "outside"
    assert occupied_task_dirs(root) == ()


def test_occupied_task_dirs_reports_content_without_changing_the_workspace(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    ensure_workspace_dir(root)
    assert occupied_task_dirs(root) == ()
    (root / "audiobook" / "01.mkv").write_bytes(b"already here")
    (root / "temp" / "staging").mkdir()
    assert occupied_task_dirs(root) == ("audiobook",)
    assert sorted(p.name for p in root.iterdir()) == sorted(DEFAULT_SUBDIRS)


def test_ensure_workspace_dir_rejects_file_collision(tmp_path: Path) -> None:
    collision = tmp_path / "ws"
    collision.write_text("not a dir", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        ensure_workspace_dir(collision)
