from __future__ import annotations

from pathlib import Path

import pytest

from anishift import paths
from anishift.application.watch_state import watch_state_path
from anishift.cli.watch import watch_state_dir
from anishift.config.env_file import env_path
from anishift.config.model_catalog import model_catalog_path
from anishift.config.presets import presets_path
from anishift.config.workspace import resolve_workspace_root, run_temp_dir
from anishift.platform.binaries import external_bin_root
from anishift.setup.manifest import manifest_path


def test_application_locations_share_one_repository_anchor_and_config_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository: Path = tmp_path / "repo"
    repository.mkdir()
    (repository / "pyproject.toml").touch()
    configuration: Path = tmp_path / "account/config"
    monkeypatch.setattr(paths, "__file__", str(repository / "anishift/paths.py"))
    monkeypatch.setenv(paths.ENV_CONFIG_DIR, str(configuration))
    monkeypatch.delenv("ANISHIFT_WORKSPACE_ROOT", raising=False)
    assert paths.repo_root() == repository
    assert resolve_workspace_root() == repository / "workspace"
    assert external_bin_root() == repository / "external/bin"
    assert manifest_path() == repository / "external/bin_hashes.json"
    assert env_path() == repository / ".env"
    assert paths.config_path() == configuration / "settings.json"
    assert presets_path() == configuration / "presets.json"
    assert model_catalog_path() == configuration / "anishift.models.jsonc"
    assert watch_state_dir() == configuration / "watch"
    assert watch_state_path() == watch_state_dir() / "state.json"
    assert paths.relocation_journal_dir(watch_state_dir()) == configuration / "watch/relocations"
    assert paths.torrent_profile_dir() == configuration / "qbittorrent"
    assert paths.log_path() == configuration.parent / "logs/anishift.log.jsonl"
    assert not configuration.exists()
    assert not (repository / "workspace").exists()


def test_selected_workspace_keeps_ready_and_run_staging_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root: Path = tmp_path / "library"
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(root))
    assert resolve_workspace_root() == root
    assert paths.ready_dir(root) == root / "ready"
    assert run_temp_dir(root, "run-1") == paths.temp_dir(root) / "run-1"
    assert not root.exists()
