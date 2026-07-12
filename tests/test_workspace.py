"""Tests for workspace root resolution and directory bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from anishift.config.workspace import (
    DEFAULT_SUBDIRS,
    ENV_WORKSPACE_ROOT,
    ensure_workspace_dir,
    resolve_workspace_root,
)


def test_resolve_workspace_root_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_WORKSPACE_ROOT, str(tmp_path))
    assert resolve_workspace_root() == tmp_path.resolve()


def test_resolve_workspace_root_blank_env_falls_back_to_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_WORKSPACE_ROOT, "   ")
    assert resolve_workspace_root().name == "workspace"


def test_ensure_workspace_dir_creates_only_default_subdirs(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    ensure_workspace_dir(root)
    assert root.is_dir()
    assert sorted(p.name for p in root.iterdir()) == sorted(DEFAULT_SUBDIRS)


def test_ensure_workspace_dir_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    ensure_workspace_dir(root)
    ensure_workspace_dir(root)
    assert (root / "tmp").is_dir()
    assert (root / "output").is_dir()


def test_ensure_workspace_dir_rejects_file_collision(tmp_path: Path) -> None:
    collision = tmp_path / "ws"
    collision.write_text("not a dir", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        ensure_workspace_dir(collision)
