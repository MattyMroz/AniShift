"""Diagnostic doctor — health checks returned as a structured report.

One flat, synchronous module (no ``doctor_checks/`` package, no async gather):
AniShift has ~6 checks, not 15. ``run_doctor()`` runs them in order and returns
a list of :class:`CheckResult`. The CLI renders the list.

Checks:

1. ``python_version``  — interpreter >= 3.14
2. ``uv_installed``    — uv on PATH
3. ``binaries``        — mkvextract, mkvmerge, ffmpeg present (balcon: Windows only)
4. ``api_keys``        — which optional API keys are configured (never a failure)
5. ``workspace``       — workspace root resolves and is writable
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from anishift.config.settings import Settings
from anishift.config.workspace import ensure_workspace_dir, resolve_workspace_root
from anishift.errors import AniShiftError
from anishift.platform.binaries import Binary, is_windows, resolve_binary

__all__ = [
    "CheckResult",
    "CheckStatus",
    "run_doctor",
]

_MIN_PYTHON: Final[tuple[int, int]] = (3, 14)
"""Minimum Python version supported by the project."""

_REQUIRED_BINARIES: Final[tuple[Binary, ...]] = (
    Binary.FFMPEG,
    Binary.MKVEXTRACT,
    Binary.MKVMERGE,
)
"""Binaries required on every platform (balcon is optional / Windows-only)."""

_API_KEYS: Final[dict[str, str]] = {
    "deepl_api_key": "DeepL",
    "elevenlabs_api_key": "ElevenLabs",
    "anthropic_api_key": "Anthropic",
    "gemini_api_key": "Gemini",
    "openai_api_key": "OpenAI",
    "deepseek_api_key": "DeepSeek",
    "openrouter_api_key": "OpenRouter",
    "openai_compatible_api_key": "OpenAI-compatible",
}
"""API keys surfaced by the doctor: Settings attribute name -> display label."""


class CheckStatus(StrEnum):
    """Outcome category of a single :class:`CheckResult`."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one diagnostic check.

    Attributes:
        name: Stable check identifier (``"python_version"``).
        status: Outcome category.
        message: One-line human-readable summary.
        suggestion: Optional actionable hint shown on failure.
        details: Extra structured context for machine consumers.
    """

    name: str
    status: CheckStatus
    message: str
    suggestion: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def check_python_version() -> CheckResult:
    """Check the running interpreter meets the minimum supported version."""
    current: tuple[int, int] = sys.version_info[:2]
    have = ".".join(str(n) for n in current)
    need = ".".join(str(n) for n in _MIN_PYTHON)
    if current < _MIN_PYTHON:
        return CheckResult(
            name="python_version",
            status=CheckStatus.FAIL,
            message=f"Python {need}+ required, found {have}",
            suggestion=f"Install Python {need}+ and re-create the venv with `uv sync`",
        )
    return CheckResult(
        name="python_version",
        status=CheckStatus.OK,
        message=f"Python {have}",
        details={"version": have},
    )


def check_uv_installed() -> CheckResult:
    """Check that ``uv`` is on ``PATH``."""
    path = shutil.which("uv")
    if path is None:
        return CheckResult(
            name="uv_installed",
            status=CheckStatus.FAIL,
            message="uv binary not found on PATH",
            suggestion="Install uv: https://docs.astral.sh/uv/getting-started/installation/",
        )
    return CheckResult(
        name="uv_installed",
        status=CheckStatus.OK,
        message=f"uv found at {path}",
        details={"path": path},
    )


def _balcon_status() -> str:
    """Return the balcon availability tag (``ok`` / ``windows-only`` / ``missing``)."""
    if resolve_binary(Binary.BALCON) is not None:
        return "ok"
    if not is_windows():
        return "windows-only"
    return "missing"


def check_binaries() -> CheckResult:
    """Check that the required external binaries resolve."""
    missing = [b.value for b in _REQUIRED_BINARIES if resolve_binary(b) is None]
    details: dict[str, Any] = {
        "missing": missing,
        "balcon": _balcon_status(),
    }
    if missing:
        suggestion = "Run `anishift setup` to download them into external/bin/"
        if is_windows():
            # On Windows only bundled binaries count — PATH is not searched.
            suggestion += " (on Windows binaries must be bundled there, not just on PATH)"
        return CheckResult(
            name="binaries",
            status=CheckStatus.FAIL,
            message=f"missing external binaries: {', '.join(missing)}",
            suggestion=suggestion,
            details=details,
        )
    return CheckResult(
        name="binaries",
        status=CheckStatus.OK,
        message="mkvextract, mkvmerge, ffmpeg present",
        details=details,
    )


def check_api_keys(settings: Settings | None = None) -> CheckResult:
    """Report which optional API keys are configured. Never a failure."""
    resolved = settings if settings is not None else Settings()
    configured = [label for attr, label in _API_KEYS.items() if getattr(resolved, attr)]
    if not configured:
        return CheckResult(
            name="api_keys",
            status=CheckStatus.WARN,
            message="no API keys configured (some engines will be disabled)",
            suggestion="Copy .env.example to .env and fill in the keys you need",
            details={"configured": []},
        )
    return CheckResult(
        name="api_keys",
        status=CheckStatus.OK,
        message=f"configured: {', '.join(configured)}",
        details={"configured": configured},
    )


def check_workspace() -> CheckResult:
    """Check the workspace root resolves and can be created."""
    try:
        root = resolve_workspace_root()
        ensure_workspace_dir(root)
    except (AniShiftError, OSError) as exc:
        return CheckResult(
            name="workspace",
            status=CheckStatus.FAIL,
            message=f"workspace not usable: {exc}",
            suggestion="Set ANISHIFT_WORKSPACE_ROOT or run from a repo checkout",
        )
    return CheckResult(
        name="workspace",
        status=CheckStatus.OK,
        message=f"workspace ready at {root}",
        details={"root": str(root)},
    )


def run_doctor(settings: Settings | None = None) -> list[CheckResult]:
    """Run every diagnostic check in order and return the collected list."""
    return [
        check_python_version(),
        check_uv_installed(),
        check_binaries(),
        check_api_keys(settings),
        check_workspace(),
    ]
