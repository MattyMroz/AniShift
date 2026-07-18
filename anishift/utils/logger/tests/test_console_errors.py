"""Unit tests for console sink and error hierarchy."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ..errors import ConfigError, HandlerError, LoggerError, ParserError
from ..handlers import console as _console_handler_mod
from ..handlers.console import (
    _LEVEL_BADGE,
    _LEVEL_COLOR,
    _LEVEL_ICON,
    _build_message,
    console_sink,
    set_show_icons,
)

_CSINK_CONSOLE = f"{_console_handler_mod.__name__}.console"
_CSINK_STAT = f"{_console_handler_mod.__name__}.increment_stat"


# ── Error Hierarchy ───────────────────────────────────────────────────────────


class TestErrorHierarchy:
    """Tests for logger exception classes."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            pytest.param(ConfigError, id="ConfigError"),
            pytest.param(HandlerError, id="HandlerError"),
            pytest.param(ParserError, id="ParserError"),
        ],
    )
    def test_inherits_from_logger_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, LoggerError)

    def test_logger_error_inherits_from_exception(self) -> None:
        assert issubclass(LoggerError, Exception)

    def test_raise_and_catch(self) -> None:
        with pytest.raises(LoggerError):
            msg = "bad config"
            raise ConfigError(msg)

    def test_message_preserved(self) -> None:
        err = ParserError("invalid JSON")
        assert str(err) == "invalid JSON"


# ── Console Sink Helpers ──────────────────────────────────────────────────────


def _make_record(
    level: str = "INFO",
    message: str = "test msg",
    logger_name: str = "app",
) -> dict[str, Any]:
    """Build a minimal loguru-like record dict."""
    return {
        "level": SimpleNamespace(name=level),
        "message": message,
        "time": datetime(2024, 6, 15, 12, 0, 0),
        "extra": {"logger_name": logger_name},
    }


# ── Level Lookup Dicts ────────────────────────────────────────────────────────


class TestLevelDicts:
    """Tests for _LEVEL_BADGE, _LEVEL_COLOR, _LEVEL_ICON."""

    @pytest.mark.parametrize(
        "level",
        ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
    )
    def test_all_levels_present(self, level: str) -> None:
        assert level in _LEVEL_BADGE
        assert level in _LEVEL_COLOR
        assert level in _LEVEL_ICON


# ── console_sink ──────────────────────────────────────────────────────────────


class TestConsoleSink:
    """Tests for console_sink function."""

    @patch(_CSINK_CONSOLE)
    @patch(_CSINK_STAT)
    def test_calls_console_print(self, mock_stat: MagicMock, mock_console: MagicMock) -> None:
        record = _make_record()
        message = SimpleNamespace(record=record)
        console_sink(message)
        mock_console.print.assert_called_once()

    @patch(_CSINK_CONSOLE)
    @patch(_CSINK_STAT)
    def test_increments_stat(self, mock_stat: MagicMock, mock_console: MagicMock) -> None:
        record = _make_record(level="ERROR", logger_name="myapp")
        console_sink(SimpleNamespace(record=record))
        mock_stat.assert_called_once_with("ERROR", "myapp")


# ── set_show_icons ────────────────────────────────────────────────────────────


class TestSetShowIcons:
    """Tests for set_show_icons toggle."""

    @patch(_CSINK_CONSOLE)
    @patch(_CSINK_STAT)
    def test_icons_disabled(self, mock_stat: MagicMock, mock_console: MagicMock) -> None:
        set_show_icons(False)
        try:
            record = _make_record()
            console_sink(SimpleNamespace(record=record))
            printed_text = mock_console.print.call_args[0][0]
            # Icons should be in LEVEL_ICON but not in output
            assert "ℹ️" not in printed_text.plain
        finally:
            set_show_icons(True)


# ── _build_message ────────────────────────────────────────────────────────────


class TestBuildMessage:
    """Tests for _build_message formatting."""

    def test_contains_timestamp(self) -> None:
        text = _build_message(_make_record())
        assert "12:00:00" in text.plain

    def test_contains_level(self) -> None:
        text = _build_message(_make_record(level="WARNING"))
        assert "WARNING" in text.plain

    def test_contains_logger_name(self) -> None:
        text = _build_message(_make_record(logger_name="mymod"))
        assert "mymod" in text.plain

    def test_contains_message(self) -> None:
        text = _build_message(_make_record(message="hello world"))
        assert "hello world" in text.plain

    def test_separators(self) -> None:
        text = _build_message(_make_record())
        assert " | " in text.plain
