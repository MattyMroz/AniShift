from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from anishift.bootstrap import bootstrap
from anishift.config.env_file import update_env_value


def test_config_imports_in_a_fresh_process() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import anishift.config"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_bootstrap_reloads_changed_dotenv_without_injecting_process_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    monkeypatch.setattr("anishift.bootstrap.env_path", lambda: path)
    monkeypatch.delenv("ANISHIFT_ELEVENLABS_API_KEY", raising=False)
    path.write_text("ANISHIFT_ELEVENLABS_API_KEY=first\n", encoding="utf-8")

    first = bootstrap(create_dirs=False)
    path.write_text("ANISHIFT_ELEVENLABS_API_KEY=second\n", encoding="utf-8")
    second = bootstrap(create_dirs=False)

    assert first.settings.elevenlabs_api_key == "first"
    assert second.settings.elevenlabs_api_key == "second"
    assert "ANISHIFT_ELEVENLABS_API_KEY" not in os.environ


def test_bootstrap_resolves_workspace_override_from_literal_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    workspace = tmp_path / "custom workspace"
    monkeypatch.setattr("anishift.bootstrap.env_path", lambda: path)
    monkeypatch.delenv("ANISHIFT_WORKSPACE_ROOT", raising=False)
    update_env_value(
        "ANISHIFT_WORKSPACE_ROOT",
        str(workspace),
        path=path,
    )

    context = bootstrap(create_dirs=False)

    assert context.workspace_root == workspace.resolve()
    assert "ANISHIFT_WORKSPACE_ROOT" not in os.environ
