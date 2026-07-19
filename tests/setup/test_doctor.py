from __future__ import annotations

from pathlib import Path

import pytest

from anishift.config.settings import Settings
from anishift.setup import doctor
from anishift.setup.doctor import (
    CheckStatus,
    check_api_keys,
    check_binaries,
    check_python_version,
    check_workspace,
    run_doctor,
)


def test_python_version_ok_on_current_interpreter() -> None:
    result = check_python_version()
    assert result.status is CheckStatus.OK


def test_binaries_fail_when_all_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "resolve_binary", lambda _b: None)
    monkeypatch.setattr(doctor, "is_windows", lambda: False)
    result = check_binaries()
    assert result.status is CheckStatus.FAIL
    assert set(result.details["missing"]) == {"mkvextract", "mkvmerge", "ffmpeg"}


def test_binaries_ok_when_required_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(doctor, "resolve_binary", lambda _b: tmp_path / "bin")
    result = check_binaries()
    assert result.status is CheckStatus.OK


def test_api_keys_warn_when_none_configured() -> None:
    result = check_api_keys(Settings(_env_file=None))
    assert result.status is CheckStatus.WARN
    assert result.details["configured"] == []


def test_api_keys_ok_when_one_configured() -> None:
    result = check_api_keys(Settings(_env_file=None, deepl_api_key="x"))
    assert result.status is CheckStatus.OK
    assert "DeepL" in result.details["configured"]


def test_workspace_ok_with_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANISHIFT_WORKSPACE_ROOT", str(tmp_path))
    result = check_workspace()
    assert result.status is CheckStatus.OK
    assert (tmp_path / "tmp").is_dir()


def test_run_doctor_returns_all_checks() -> None:
    names = [r.name for r in run_doctor(Settings(_env_file=None))]
    assert names == ["python_version", "uv_installed", "binaries", "api_keys", "workspace"]
