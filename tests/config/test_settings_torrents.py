from __future__ import annotations

import pytest

from anishift.config.settings import Settings


def test_torrent_settings_default_to_the_local_web_ui_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ANISHIFT_QBITTORRENT_URL", "ANISHIFT_QBITTORRENT_USERNAME", "ANISHIFT_QBITTORRENT_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    settings: Settings = Settings(_env_file=None)

    assert settings.qbittorrent_url == "http://127.0.0.1:8080"
    assert settings.qbittorrent_username == ""
    assert settings.qbittorrent_password == ""


def test_torrent_settings_read_the_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANISHIFT_QBITTORRENT_URL", "http://127.0.0.1:9090")
    monkeypatch.setenv("ANISHIFT_QBITTORRENT_USERNAME", "admin")
    monkeypatch.setenv("ANISHIFT_QBITTORRENT_PASSWORD", "secret")

    settings: Settings = Settings(_env_file=None)

    assert settings.qbittorrent_url == "http://127.0.0.1:9090"
    assert settings.qbittorrent_username == "admin"
    assert settings.qbittorrent_password == "secret"  # noqa: S105
    assert "secret" not in repr(settings)
