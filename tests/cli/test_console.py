from __future__ import annotations

import io
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from anishift.cli.console import (
    configure_utf8_streams,
    console_encoding_check,
)
from anishift.setup.doctor import CheckStatus


def test_configure_utf8_streams_reconfigures_text_wrapper() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1250", errors="strict")
    with patch.object(sys, "stdout", stream), patch.object(sys, "stderr", stream):
        configure_utf8_streams()
    assert stream.encoding == "utf-8"
    assert stream.errors == "replace"


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


@pytest.mark.parametrize(
    "encoding",
    ["utf-8", "UTF-8", "utf8", "UTF8", "cp65001", "CP65001", "65001"],
)
def test_encoding_check_ok_for_utf8_aliases(encoding: str) -> None:
    with patch.object(sys, "stdout", SimpleNamespace(encoding=encoding)):
        result = console_encoding_check()
    assert result.status is CheckStatus.OK


@pytest.mark.parametrize(
    "encoding",
    ["cp1250", "cp852", "windows-1250", "latin-1"],
)
def test_encoding_check_warn_for_windows_code_pages(encoding: str) -> None:
    with patch.object(sys, "stdout", SimpleNamespace(encoding=encoding)):
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


@pytest.mark.parametrize("command", ["doctor", "setup"])
def test_cli_command_does_not_import_textual(command: str) -> None:
    snippet = (
        "import sys\n"
        "from typer.testing import CliRunner\n"
        "from anishift.cli.main import app\n"
        "CliRunner().invoke(app, [sys.argv[1]])\n"
        "raise SystemExit(1 if 'textual' in sys.modules else 0)\n"
    )
    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", snippet, command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
