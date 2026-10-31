from __future__ import annotations

import contextlib
from pathlib import Path
from typing import NoReturn

import pytest

from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.services.tts.engines.elevenreader.api_backend import save_cleanup, write_session
from anishift.services.tts.engines.elevenreader.config import profile_dir
from anishift.services.tts.engines.elevenreader.types import AccountCleanup
from anishift.setup import doctor
from anishift.setup.doctor import (
    CheckStatus,
    check_api_keys,
    check_binaries,
    check_elevenreader,
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


def test_managed_diagnostics_do_not_prepare_tools_or_touch_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor, "is_windows", lambda: True)
    monkeypatch.setattr(doctor, "external_bin_root", lambda: tmp_path / "bin")
    result = doctor.check_managed_torrent_client()
    assert result.status is CheckStatus.OK
    assert "first download order" in result.message
    assert list(tmp_path.iterdir()) == []


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
    monkeypatch.setattr(doctor, "load_user_settings", UserSettings)
    names = [r.name for r in run_doctor(Settings(_env_file=None))]
    assert names == [
        "python_version",
        "uv_installed",
        "binaries",
        "api_keys",
        "workspace",
        "console_encoding",
        "torrent_client",
        "elevenreader",
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
    monkeypatch.setattr(doctor, "load_user_settings", UserSettings)

    run_doctor()

    assert probed == [("127.0.0.1", 9999)]


@pytest.fixture
def elevenreader_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root: Path = tmp_path / "elevenreader"
    monkeypatch.setattr(doctor, "elevenreader_dir", lambda: root)
    monkeypatch.setattr(doctor, "find_chrome", lambda: tmp_path / "chrome.exe")
    return root


@pytest.mark.unit
def test_check_elevenreader_other_engine_skips(elevenreader_root: Path) -> None:
    result = check_elevenreader("elevenbytes")

    assert result.status is CheckStatus.SKIP


@pytest.mark.unit
def test_check_elevenreader_other_engine_owed_account_cleanup_warns(elevenreader_root: Path) -> None:
    save_cleanup(elevenreader_root, AccountCleanup(read_ids=["read"]))

    result = check_elevenreader("elevenbytes")

    assert result.status is CheckStatus.WARN
    assert "anishift document" in result.message
    assert result.suggestion == "Ustawienia → Lektor → Zaloguj / sprawdź sesję"


@pytest.mark.unit
def test_check_elevenreader_without_chrome_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "find_chrome", lambda: None)

    result = check_elevenreader("elevenreader")

    assert result.status is CheckStatus.FAIL
    assert "ElevenBytes" in result.suggestion


@pytest.mark.unit
def test_check_elevenreader_without_profile_warns_with_sign_in_hint(elevenreader_root: Path) -> None:
    write_session(elevenreader_root, signed_in=True)

    result = check_elevenreader("elevenreader")

    assert result.status is CheckStatus.WARN
    assert result.suggestion == "Ustawienia → Lektor → Zaloguj / sprawdź sesję"


@pytest.mark.unit
def test_check_elevenreader_last_check_signed_out_warns(elevenreader_root: Path) -> None:
    profile_dir(elevenreader_root).mkdir(parents=True)
    write_session(elevenreader_root, signed_in=False)

    result = check_elevenreader("elevenreader")

    assert result.status is CheckStatus.WARN


@pytest.mark.unit
def test_check_elevenreader_signed_in_profile_is_ok(elevenreader_root: Path) -> None:
    profile_dir(elevenreader_root).mkdir(parents=True)
    write_session(elevenreader_root, signed_in=True)

    result = check_elevenreader("elevenreader")

    assert result.status is CheckStatus.OK
    assert "signed in" in result.message


@pytest.mark.unit
def test_check_elevenreader_owed_account_cleanup_warns_with_repair_hint(elevenreader_root: Path) -> None:
    profile_dir(elevenreader_root).mkdir(parents=True)
    write_session(elevenreader_root, signed_in=True)
    save_cleanup(elevenreader_root, AccountCleanup(read_ids=["read"]))

    result = check_elevenreader("elevenreader")

    assert result.status is CheckStatus.WARN
    assert "anishift document" in result.message
    assert result.suggestion == "Ustawienia → Lektor → Zaloguj / sprawdź sesję"
