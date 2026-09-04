"""Sole owner of stdout/stderr UTF-8 reconfiguration for the CLI process."""

from __future__ import annotations

import sys
from typing import Final

from anishift.setup.doctor import CheckResult, CheckStatus

__all__ = [
    "configure_utf8_streams",
    "console_encoding_check",
]

# ── Constants ──

_UTF8_NAMES: Final[frozenset[str]] = frozenset({"utf8", "cp65001", "65001"})
"""Normalized encoding names treated as UTF-8-safe — no reconfiguration advice needed."""


def configure_utf8_streams() -> None:
    """Reconfigure stdout and stderr to UTF-8 with replacement error handling."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except OSError, AttributeError:
            continue


def console_encoding_check() -> CheckResult:
    """Report the effective console encoding — OK for UTF-8, WARN otherwise."""
    encoding: str = _effective_encoding()
    normalized: str = encoding.lower().replace("-", "").replace("_", "")

    if normalized in _UTF8_NAMES:
        return CheckResult(
            name="console_encoding",
            status=CheckStatus.OK,
            message=f"Console encoding: {encoding}",
            details={"encoding": encoding},
        )
    return CheckResult(
        name="console_encoding",
        status=CheckStatus.WARN,
        message=f"Console encoding is {encoding}, not UTF-8",
        suggestion="Run `chcp 65001` before launching or set PYTHONUTF8=1",
        details={"encoding": encoding},
    )


def _effective_encoding() -> str:
    """Return the best-effort encoding name from stdout."""
    stream = sys.stdout
    if stream is None:
        return "unknown"
    return getattr(stream, "encoding", "unknown") or "unknown"
