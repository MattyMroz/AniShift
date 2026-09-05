from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from anishift.cli.console import (
    configure_utf8_streams,
    console_encoding_check,
)
from anishift.platform.binaries import is_windows
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


def test_cli_commands_do_not_import_textual(tmp_path: Path) -> None:
    install_root: Path = tmp_path / "external-bin"
    snippet: str = (
        "import sys\n"
        "from pathlib import Path\n"
        "from unittest.mock import patch\n"
        "import httpx\n"
        "from typer.testing import CliRunner\n"
        "from anishift.cli.main import app\n"
        "runner = CliRunner()\n"
        "guilty = []\n"
        "offline = patch('httpx.stream', side_effect=httpx.ConnectError('offline'))\n"
        "sandbox = patch('anishift.setup.installer.external_bin_root', return_value=Path(sys.argv[1]))\n"
        "with offline, sandbox:\n"
        "    runner.invoke(app, ['doctor'])\n"
        "    if 'textual' in sys.modules:\n"
        "        guilty.append('doctor')\n"
        "    setup = runner.invoke(app, ['setup'])\n"
        "    if 'textual' in sys.modules and 'doctor' not in guilty:\n"
        "        guilty.append('setup')\n"
        "print('setup exit code: ' + str(setup.exit_code))\n"
        "print(setup.output)\n"
        "if guilty:\n"
        "    print('textual imported by: ' + ', '.join(guilty))\n"
        "raise SystemExit(1 if guilty else 0)\n"
    )
    completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
        [sys.executable, "-c", snippet, str(install_root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
        env={**os.environ, "ANISHIFT_WORKSPACE_ROOT": str(tmp_path / "workspace"), "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not [path for path in install_root.rglob("*") if path.is_file()]
    if is_windows():
        assert "setup exit code: 1" in completed.stdout
        assert "download failed" in completed.stdout
    else:
        assert "setup exit code: 0" in completed.stdout
        assert "install via your OS package manager" in completed.stdout
