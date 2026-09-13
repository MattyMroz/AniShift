"""Diagnostic doctor — health checks returned as a structured report."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from socket import create_connection
from typing import Any, Final
from urllib.parse import SplitResult, urlsplit

from anishift.config.env_file import env_path
from anishift.config.settings import Settings
from anishift.config.workspace import ensure_workspace_dir, resolve_workspace_root
from anishift.errors import AniShiftError
from anishift.platform.binaries import Binary, external_bin_root, is_windows, resolve_binary
from anishift.platform.qbittorrent_config import installed_executable
from anishift.utils.logger import get_logger

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
"""Binaries required on every platform."""

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

_WEB_UI_HOST: Final[str] = "127.0.0.1"
"""Host probed when the configured Web UI address names none."""

_WEB_UI_PORT: Final[int] = 8080
"""Port probed when the configured Web UI address names none."""

_WEB_UI_TIMEOUT: Final[float] = 1.0
"""Seconds the doctor waits for the Web UI socket before calling it unreachable."""

_TORRENT_INSTALL_HINT: Final[str] = "winget install qBittorrent.qBittorrent, then run `anishift qbit setup`"
"""Advice offered when no qBittorrent installation was found."""

_TORRENT_SETUP_HINT: Final[str] = "Run `anishift qbit setup` (close qBittorrent first) and start qBittorrent"
"""Advice offered when qBittorrent is installed but its Web UI stays silent."""

logger = get_logger(__name__)


class CheckStatus(StrEnum):
    """Outcome category of a single :class:`CheckResult`."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one diagnostic check."""

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


def check_binaries() -> CheckResult:
    """Check that the required external binaries resolve."""
    missing = [b.value for b in _REQUIRED_BINARIES if resolve_binary(b) is None]
    details: dict[str, Any] = {"missing": missing}
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


def check_torrent_client(settings: Settings | None = None) -> CheckResult:
    """Check the qBittorrent Web UI answers and, when it stays silent, whether the client exists."""
    if not is_windows():
        return CheckResult(
            name="torrent_client",
            status=CheckStatus.SKIP,
            message="qBittorrent is managed on Windows only",
        )
    resolved = settings if settings is not None else Settings()
    host, port = _web_ui_endpoint(resolved.qbittorrent_url)
    if _web_ui_answers(host, port):
        return CheckResult(
            name="torrent_client",
            status=CheckStatus.OK,
            message=f"Web UI answers on {host}:{port}",
        )
    if installed_executable() is None:
        return CheckResult(
            name="torrent_client",
            status=CheckStatus.WARN,
            message="qBittorrent is not installed",
            suggestion=_TORRENT_INSTALL_HINT,
        )
    return CheckResult(
        name="torrent_client",
        status=CheckStatus.WARN,
        message="qBittorrent Web UI is not reachable",
        suggestion=_TORRENT_SETUP_HINT,
    )


def _web_ui_endpoint(url: str) -> tuple[str, int]:
    """Split the configured Web UI address into the host and port to probe."""
    parts: SplitResult = urlsplit(url)
    try:
        port: int | None = parts.port
    except ValueError:
        port = None
    return parts.hostname or _WEB_UI_HOST, port or _WEB_UI_PORT


def _web_ui_answers(host: str, port: int) -> bool:
    """Report whether something accepts a connection on the Web UI endpoint."""
    try:
        with create_connection((host, port), timeout=_WEB_UI_TIMEOUT):
            return True
    except OSError:
        return False


def check_managed_torrent_client() -> CheckResult:
    """Report private binary readiness without starting a client or touching its profile."""
    if not is_windows():
        return CheckResult("torrent_client", CheckStatus.SKIP, "Managed qBittorrent requires Windows")
    files: tuple[str, ...] = ("qbittorrent/qbittorrent.exe", "qbittorrent/qt.conf")
    installed: bool = all(
        (external_bin_root() / name).is_file() and (external_bin_root() / name).stat().st_size > 0 for name in files
    )
    message: str = (
        "Private qBittorrent prepared in external/bin/qbittorrent; starts for downloads only"
        if installed
        else "Private qBittorrent will be downloaded and verified on the first download order"
    )
    return CheckResult("torrent_client", CheckStatus.OK, message)


def run_doctor(settings: Settings | None = None, *, managed_torrents: bool = False) -> list[CheckResult]:
    """Run every diagnostic check in order and return the collected list."""
    from anishift.cli.console import console_encoding_check  # noqa: PLC0415 - avoid circular import

    logger.info("Environment diagnostics started")
    # The .env file sits beside the repository, so it is read the way bootstrap reads it
    # instead of relying on the current working directory.
    resolved: Settings = settings if settings is not None else Settings(_env_file=env_path())
    results = [
        check_python_version(),
        check_uv_installed(),
        check_binaries(),
        check_api_keys(resolved),
        check_workspace(),
        console_encoding_check(),
        check_managed_torrent_client() if managed_torrents else check_torrent_client(resolved),
    ]
    logger.info(
        "Environment diagnostics completed",
        ok=sum(result.status is CheckStatus.OK for result in results),
        warnings=sum(result.status is CheckStatus.WARN for result in results),
        failures=sum(result.status is CheckStatus.FAIL for result in results),
        skipped=sum(result.status is CheckStatus.SKIP for result in results),
    )
    for result in results:
        if result.status in {CheckStatus.WARN, CheckStatus.FAIL}:
            logger.warning("Environment diagnostic issue", check=result.name, status=result.status.value)
    return results
