from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from anishift.cli.console import (
    configure_utf8_streams,
    console_encoding_check,
)
from anishift.cli.main import app
from anishift.setup.doctor import CheckStatus


def test_configure_utf8_streams_reconfigures_text_wrapper() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1250", errors="strict")
    with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
        configure_utf8_streams()
    assert stream.encoding == "utf-8"


def test_configure_utf8_streams_tolerates_none() -> None:
    with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
        configure_utf8_streams()


def test_configure_utf8_streams_tolerates_stringio() -> None:
    fake = io.StringIO()
    with patch.object(sys, "stdout", fake), patch.object(sys, "stderr", fake):
        configure_utf8_streams()


def test_configure_utf8_streams_idempotent() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1250", errors="strict")
    with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
        configure_utf8_streams()
        configure_utf8_streams()
    assert stream.encoding == "utf-8"


def test_encoding_check_ok_for_utf8() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    with patch.object(sys, "stdout", stream):
        result = console_encoding_check()
    assert result.status is CheckStatus.OK


def test_encoding_check_warn_for_cp1250() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1250")
    with patch.object(sys, "stdout", stream):
        result = console_encoding_check()
    assert result.status is CheckStatus.WARN
    assert "chcp 65001" in (result.suggestion or "")
    assert "PYTHONUTF8=1" in (result.suggestion or "")


def test_doctor_report_no_unicode_error_on_cp1250_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cp1250_stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1250", errors="strict")
    monkeypatch.setattr(sys, "stdout", cp1250_stream)
    monkeypatch.setattr(sys, "stderr", cp1250_stream)
    configure_utf8_streams()
    from anishift.cli.main import _print_doctor_report  # noqa: PLC0415
    from anishift.setup.doctor import run_doctor  # noqa: PLC0415

    results = run_doctor()
    _print_doctor_report(results)


def test_doctor_command_does_not_import_textual() -> None:
    if "textual" in sys.modules:
        pytest.skip("textual already imported by another test in this process")
    runner = CliRunner()
    runner.invoke(app, ["doctor"])
    assert "textual" not in sys.modules


def test_setup_command_does_not_import_textual() -> None:
    if "textual" in sys.modules:
        pytest.skip("textual already imported by another test in this process")
    runner = CliRunner()
    runner.invoke(app, ["setup"])
    assert "textual" not in sys.modules
