from __future__ import annotations

import contextlib
from pathlib import Path
from typing import NoReturn

import pytest

from anishift.config.settings import Settings
from anishift.setup import doctor
from anishift.setup.doctor import (
    CheckStatus,
    check_api_keys,
    check_binaries,
    check_python_version,
    check_torrent_client,
    check_workspace,
    run_doctor,
)


def _accepts(*_args: object, **_kwargs: object) -> contextlib.AbstractContextManager[None]:
    return contextlib.nullcontext()


def _refuses(*_args: object, **_kwargs: object) -> NoReturn:
    raise OSError


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "is_windows", lambda: True)


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
    assert (tmp_path / "temp").is_dir()


@pytest.mark.usefixtures("on_windows")
def test_torrent_client_ok_when_the_web_ui_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "create_connection", _accepts)
    result = check_torrent_client(Settings(_env_file=None))
    assert result.status is CheckStatus.OK
    assert result.message == "Web UI answers on 127.0.0.1:8080"


@pytest.mark.usefixtures("on_windows")
def test_torrent_client_warns_when_qbittorrent_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "create_connection", _refuses)
    monkeypatch.setattr(doctor, "installed_executable", lambda: None)
    result = check_torrent_client(Settings(_env_file=None))
    assert result.status is CheckStatus.WARN
    assert result.message == "qBittorrent is not installed"
    assert "winget install qBittorrent.qBittorrent" in result.suggestion


@pytest.mark.usefixtures("on_windows")
def test_torrent_client_warns_when_the_web_ui_is_unreachable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(doctor, "create_connection", _refuses)
    monkeypatch.setattr(doctor, "installed_executable", lambda: tmp_path / "qbittorrent.exe")
    result = check_torrent_client(Settings(_env_file=None))
    assert result.status is CheckStatus.WARN
    assert result.message == "qBittorrent Web UI is not reachable"
    assert "anishift qbit setup" in result.suggestion


def test_torrent_client_is_skipped_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "is_windows", lambda: False)
    result = check_torrent_client(Settings(_env_file=None))
    assert result.status is CheckStatus.SKIP


def test_run_doctor_returns_all_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "is_windows", lambda: False)
    names = [r.name for r in run_doctor(Settings(_env_file=None))]
    assert names == [
        "python_version",
        "uv_installed",
        "binaries",
        "api_keys",
        "workspace",
        "console_encoding",
        "torrent_client",
    ]


def test_run_doctor_reads_the_repository_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file: Path = tmp_path / ".env"
    env_file.write_text("ANISHIFT_QBITTORRENT_URL=http://127.0.0.1:9999\n", encoding="utf-8")
    probed: list[tuple[str, int]] = []

    def connect(endpoint: tuple[str, int], timeout: float) -> NoReturn:
        del timeout
        probed.append(endpoint)
        raise OSError

    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.delenv("ANISHIFT_QBITTORRENT_URL", raising=False)
    monkeypatch.setattr(doctor, "env_path", lambda: env_file)
    monkeypatch.setattr(doctor, "is_windows", lambda: True)
    monkeypatch.setattr(doctor, "installed_executable", lambda: None)
    monkeypatch.setattr(doctor, "create_connection", connect)

    run_doctor()

    assert probed == [("127.0.0.1", 9999)]
