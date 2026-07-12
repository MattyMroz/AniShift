"""Tests for the startup banner."""

from __future__ import annotations

from pathlib import Path

import pytest

from anishift.bootstrap import AppContext
from anishift.cli import banner
from anishift.cli.banner import show_banner
from anishift.config.settings import Settings
from anishift.config.user_settings import Mode, UserSettings


def _context(mode: Mode = "auto") -> AppContext:
    return AppContext(
        settings=Settings(),
        user_settings=UserSettings(mode=mode),
        workspace_root=Path(),
    )


def test_logo_constant_is_non_empty() -> None:
    assert banner._LOGO.strip()


def test_show_banner_prints_mode(capsys: pytest.CaptureFixture[str]) -> None:
    show_banner(_context(mode="manual"))
    assert "manual" in capsys.readouterr().out
