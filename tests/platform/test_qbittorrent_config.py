from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Final

import pytest

from anishift.errors import ErrorCode
from anishift.platform import qbittorrent_config
from anishift.platform.qbittorrent_config import (
    QBittorrentConfigError,
    WebUiSetup,
    enable_web_ui,
    installed_executable,
    is_running,
    settings_path,
)

_EXISTING_INI: Final[str] = (
    "[LegalNotice]\r\nAccepted=true\r\n\r\n[Preferences]\r\nGeneral\\Locale=pl\r\n\r\n[Network]\r\nProxy=none\r\n"
)

_RUNNING_ROW: Final[bytes] = b'"qbittorrent.exe","9128","Console","1","231 452 K"\r\n'

_NO_TASKS: Final[bytes] = b"INFO: No tasks are running which match the specified criteria.\r\n"

_WEB_UI_KEYS: Final[tuple[str, ...]] = (
    "WebUI\\Enabled=true",
    "WebUI\\Address=127.0.0.1",
    "WebUI\\Port=8080",
    "WebUI\\LocalHostAuth=false",
    "WebUI\\Username=admin",
)

_INSTALL_VARIABLES: Final[tuple[str, ...]] = ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")


def test_managed_profile_imports_only_connection_preferences_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential: str = "isolated"
    source: Path = tmp_path / "personal.ini"
    original: str = (
        "[BitTorrent]\nSession\\MaxConnections=321\nSession\\QueueingSystemEnabled=true\n"
        "Session\\DefaultSavePath=C:/Personal\n[Preferences]\nWebUI\\Port=8080\nWebUI\\Username=personal\n"
    )
    source.write_text(original, encoding="utf-8")
    monkeypatch.setattr(qbittorrent_config, "settings_path", lambda: source)
    root: Path = tmp_path / "managed"
    qbittorrent_config.write_managed_profile(root, web_port=18081, torrent_port=18082, password=credential)
    target: Path = root / "qBittorrent/config/qBittorrent.ini"
    content: str = target.read_text(encoding="utf-8")
    assert "Session\\MaxConnections=321" in content
    assert "Session\\QueueingSystemEnabled=false" in content
    assert "WebUI\\Port=18081" in content
    assert "WebUI\\LocalHostAuth=true" in content
    assert "Personal" not in content
    assert "personal" not in content
    assert source.read_text(encoding="utf-8") == original
    source.write_text(original.replace("321", "999"), encoding="utf-8")
    qbittorrent_config.write_managed_profile(root, web_port=18083, torrent_port=18084, password=credential)
    assert "Session\\MaxConnections=321" in target.read_text(encoding="utf-8")


class _Tasklist:
    def __init__(self, stdout: bytes) -> None:
        self.stdout: bytes = stdout
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_options: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(list(command))
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=self.stdout, stderr=b"")


@pytest.fixture
def on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qbittorrent_config, "is_windows", lambda: True)


@pytest.fixture
def settings_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, on_windows: None) -> Path:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path: Path = tmp_path / "qBittorrent" / "qBittorrent.ini"
    path.parent.mkdir(parents=True)
    path.write_text(_EXISTING_INI, encoding="utf-8", newline="")
    return path


@pytest.mark.usefixtures("on_windows")
def test_settings_path_points_into_the_roaming_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert settings_path() == tmp_path / "qBittorrent" / "qBittorrent.ini"


def test_settings_path_refuses_outside_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qbittorrent_config, "is_windows", lambda: False)

    with pytest.raises(QBittorrentConfigError) as problem:
        settings_path()

    assert problem.value.context.code is ErrorCode.TORRENT_CLIENT_UNAVAILABLE


@pytest.mark.usefixtures("on_windows")
def test_settings_path_refuses_without_a_roaming_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APPDATA", raising=False)

    with pytest.raises(QBittorrentConfigError) as problem:
        settings_path()

    assert problem.value.context.code is ErrorCode.TORRENT_CLIENT_UNAVAILABLE


def test_enable_web_ui_adds_the_keys_and_keeps_the_line_endings(settings_file: Path) -> None:
    prepared: WebUiSetup = enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "s3cret-token")

    written: str = settings_file.read_text(encoding="utf-8", newline="")
    assert prepared.path_written is True
    assert prepared.password == "s3cret-token"  # noqa: S105
    assert written.count("\n") == written.count("\r\n")
    for key in _WEB_UI_KEYS:
        assert f"{key}\r\n" in written
    assert 'WebUI\\Password_PBKDF2="@ByteArray(' in written
    assert "s3cret-token" not in written


def test_enable_web_ui_keeps_every_other_line_and_writes_inside_the_preferences(settings_file: Path) -> None:
    enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "s3cret-token")

    written: str = settings_file.read_text(encoding="utf-8", newline="")
    assert written.startswith("[LegalNotice]\r\nAccepted=true\r\n\r\n[Preferences]\r\nGeneral\\Locale=pl\r\n")
    assert written.endswith("[Network]\r\nProxy=none\r\n")
    assert written.index("WebUI\\Enabled") < written.index("[Network]")


def test_enable_web_ui_backs_the_settings_up_before_writing(settings_file: Path) -> None:
    enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "s3cret-token")

    backup: Path = settings_file.with_name("qBittorrent.ini.anishift.bak")
    assert backup.read_text(encoding="utf-8", newline="") == _EXISTING_INI


def test_enable_web_ui_writes_nothing_the_second_time(settings_file: Path) -> None:
    enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "s3cret-token")
    first: str = settings_file.read_text(encoding="utf-8", newline="")

    again: WebUiSetup = enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "second-token")

    assert again == WebUiSetup(path_written=False, password=None)
    assert settings_file.read_text(encoding="utf-8", newline="") == first


def test_enable_web_ui_creates_the_preferences_section_when_the_file_has_none(settings_file: Path) -> None:
    settings_file.write_text("[LegalNotice]\nAccepted=true\n", encoding="utf-8", newline="")

    enable_web_ui(run=_Tasklist(_NO_TASKS), password_factory=lambda: "s3cret-token")

    written: str = settings_file.read_text(encoding="utf-8", newline="")
    assert written.startswith("[LegalNotice]\nAccepted=true\n[Preferences]\n")
    assert "WebUI\\Enabled=true\n" in written


def test_enable_web_ui_refuses_while_qbittorrent_runs(settings_file: Path) -> None:
    with pytest.raises(QBittorrentConfigError) as problem:
        enable_web_ui(run=_Tasklist(_RUNNING_ROW))

    assert problem.value.context.code is ErrorCode.TORRENT_CLIENT_REFUSED
    assert settings_file.read_text(encoding="utf-8", newline="") == _EXISTING_INI


def test_enable_web_ui_refuses_when_the_settings_file_is_missing(settings_file: Path) -> None:
    settings_file.unlink()

    with pytest.raises(QBittorrentConfigError) as problem:
        enable_web_ui(run=_Tasklist(_NO_TASKS))

    assert problem.value.context.code is ErrorCode.TORRENT_CLIENT_UNAVAILABLE


def test_is_running_reads_the_task_list_row(monkeypatch: pytest.MonkeyPatch) -> None:
    tasklist: _Tasklist = _Tasklist(_RUNNING_ROW)

    assert is_running(run=tasklist) is True
    assert tasklist.calls == [["tasklist", "/FI", "IMAGENAME eq qbittorrent.exe", "/NH", "/FO", "CSV"]]


def test_is_running_is_false_when_the_task_list_matches_nothing() -> None:
    assert is_running(run=_Tasklist(_NO_TASKS)) is False


def test_installed_executable_finds_a_standard_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in _INSTALL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))
    executable: Path = tmp_path / "qBittorrent" / "qbittorrent.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")

    assert installed_executable() == executable


def test_installed_executable_falls_back_to_the_search_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for variable in _INSTALL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(qbittorrent_config, "which", lambda _name: str(tmp_path / "qbittorrent"))

    assert installed_executable() == tmp_path / "qbittorrent"


def test_installed_executable_is_none_when_nothing_holds_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _INSTALL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(qbittorrent_config, "which", lambda _name: None)

    assert installed_executable() is None
