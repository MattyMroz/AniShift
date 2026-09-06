"""Web UI keys written into the settings file qBittorrent keeps in the roaming profile."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile, which
from typing import TYPE_CHECKING, Final

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.platform.binaries import is_windows
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "QBittorrentConfigError",
    "Runner",
    "WebUiSetup",
    "enable_web_ui",
    "installed_executable",
    "is_running",
    "settings_path",
]

logger = get_logger(__name__)

type Runner = Callable[..., subprocess.CompletedProcess[bytes]]
"""Command executor injected in tests, shaped like :func:`subprocess.run`."""

# ── Constants ─────────────────────────────────────────────────────────────────

_APPDATA: Final[str] = "APPDATA"
"""Environment variable naming the roaming profile of the current user."""

_SETTINGS_DIRECTORY: Final[str] = "qBittorrent"
"""Folder below the roaming profile that holds the client settings."""

_SETTINGS_NAME: Final[str] = "qBittorrent.ini"
"""File name of the settings document the Web UI keys belong to."""

_BACKUP_SUFFIX: Final[str] = ".anishift.bak"
"""Suffix of the copy taken before the settings file is rewritten."""

_INSTALL_LOCATIONS: Final[tuple[tuple[str, str], ...]] = (
    ("ProgramFiles", "qBittorrent/qbittorrent.exe"),
    ("ProgramFiles(x86)", "qBittorrent/qbittorrent.exe"),
    ("LOCALAPPDATA", "Programs/qBittorrent/qbittorrent.exe"),
)
"""Standard installations, each an environment variable and the path below it."""

_EXECUTABLE_STEM: Final[str] = "qbittorrent"
"""Program name looked up on ``PATH`` when no standard location holds the client."""

_TASKLIST: Final[str] = "tasklist"
"""Windows process lister shipped with the system."""

_IMAGE_FILTER: Final[str] = "IMAGENAME eq qbittorrent.exe"
"""Task-list filter that keeps the answer to the client process alone."""

_PROCESS_ROW: Final[str] = '"qbittorrent.exe"'
"""First field of the comma-separated row a running client produces."""

_NO_WINDOW: Final[int] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""Creation flag that keeps the task-list probe free of a console window."""

_CONSOLE_ENCODING: Final[str] = "utf-8"
"""Decoding of the task-list answer; only its ASCII image name is ever matched."""

_PREFERENCES_SECTION: Final[str] = "[Preferences]"
"""Settings section every Web UI key belongs to."""

_PASSWORD_KEY: Final[str] = "WebUI\\Password_PBKDF2"  # noqa: S105 - a settings key, not a secret
"""Key holding the hash qBittorrent 5 refuses to start the Web UI without."""

_DEFAULT_PORT: Final[int] = 8080
"""Port the Web UI listens on unless the caller asks for another one."""

_LOOPBACK: Final[str] = "127.0.0.1"
"""Address the Web UI binds to, which keeps it off every other machine."""

_WEB_UI_USER: Final[str] = "admin"
"""Account name the generated password belongs to."""

_SALT_BYTES: Final[int] = 16
"""Length of the random salt stored beside the password hash."""

_PBKDF2_ITERATIONS: Final[int] = 100_000
"""Iteration count qBittorrent applies when it derives the password hash."""

_KEY_BYTES: Final[int] = 64
"""Length of the derived key qBittorrent stores as the password hash."""

_UNSUPPORTED_MESSAGE: Final[str] = "The qBittorrent settings file exists on Windows only"
"""Refusal stated when the settings file is requested on another system."""

_UNSUPPORTED_HINT: Final[str] = "Enable the qBittorrent Web UI yourself on this system"
"""Suggestion offered beside a refused request outside Windows."""

_MISSING_PROFILE_MESSAGE: Final[str] = "This session has no roaming profile holding the qBittorrent settings"
"""Refusal stated when the roaming-profile variable is unset."""

_MISSING_PROFILE_HINT: Final[str] = "Sign in with the account that runs qBittorrent"
"""Suggestion offered when the roaming profile cannot be located."""

_RUNNING_MESSAGE: Final[str] = "Close qBittorrent first; it rewrites its settings on exit"
"""Refusal stated when the client would overwrite the new keys on its way out."""

_RUNNING_HINT: Final[str] = "Quit qBittorrent, then run `anishift qbit setup` again"
"""Suggestion offered while the client still runs."""

_MISSING_SETTINGS_MESSAGE: Final[str] = "qBittorrent has no settings file yet"
"""Refusal stated when the client has never written its settings."""

_MISSING_SETTINGS_HINT: Final[str] = "Start qBittorrent once, close it, then run `anishift qbit setup` again"
"""Suggestion offered when the settings file is absent."""


@dataclass(frozen=True, slots=True)
class WebUiSetup:
    """Outcome of one write: whether the file changed and the password created for it."""

    path_written: bool
    password: str | None


class QBittorrentConfigError(FatalError):
    """Raised when the Web UI keys cannot be written into the client settings."""


def _default_run(command: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    """Run *command* to completion without opening a console window."""
    return subprocess.run(  # noqa: S603 - fixed tasklist argv
        command,
        capture_output=True,
        text=False,
        creationflags=_NO_WINDOW,
        check=False,
    )


def settings_path() -> Path:
    """Return the settings file qBittorrent keeps in the roaming profile of this user."""
    if not is_windows():
        raise _unavailable(_UNSUPPORTED_MESSAGE, _UNSUPPORTED_HINT)
    profile: str = os.environ.get(_APPDATA, "")
    if not profile:
        raise _unavailable(_MISSING_PROFILE_MESSAGE, _MISSING_PROFILE_HINT)
    return Path(profile) / _SETTINGS_DIRECTORY / _SETTINGS_NAME


def installed_executable() -> Path | None:
    """Return the installed client, looked up in the standard locations and then on ``PATH``."""
    for variable, relative in _INSTALL_LOCATIONS:
        root: str = os.environ.get(variable, "")
        if not root:
            continue
        candidate: Path = Path(root) / relative
        if candidate.is_file():
            return candidate
    found: str | None = which(_EXECUTABLE_STEM)
    return Path(found) if found else None


def is_running(*, run: Runner = _default_run) -> bool:
    """Report whether a qBittorrent process currently owns the settings file."""
    completed: subprocess.CompletedProcess[bytes] = run([_TASKLIST, "/FI", _IMAGE_FILTER, "/NH", "/FO", "CSV"])
    listing: str = completed.stdout.decode(_CONSOLE_ENCODING, errors="replace")
    return any(line.strip().casefold().startswith(_PROCESS_ROW) for line in listing.splitlines())


def enable_web_ui(
    *,
    port: int = _DEFAULT_PORT,
    run: Runner = _default_run,
    password_factory: Callable[[], str] = secrets.token_urlsafe,
) -> WebUiSetup:
    """Add the missing Web UI keys to the client settings, leaving every other line as it was."""
    path: Path = settings_path()
    if is_running(run=run):
        raise _refused(_RUNNING_MESSAGE, _RUNNING_HINT)
    if not path.is_file():
        raise _unavailable(_MISSING_SETTINGS_MESSAGE, _MISSING_SETTINGS_HINT)
    document: str = path.read_text(encoding="utf-8", newline="")
    lines: list[str] = document.splitlines(keepends=True)
    start: int | None = _section_start(lines)
    present: frozenset[str] = _section_keys(lines, start)
    missing: dict[str, str] = {key: value for key, value in _web_ui_keys(port).items() if key not in present}
    password: str | None = None
    if _PASSWORD_KEY not in present:
        password = password_factory()
        missing[_PASSWORD_KEY] = _password_value(password)
    if not missing:
        return WebUiSetup(path_written=False, password=None)
    copyfile(path, path.with_name(path.name + _BACKUP_SUFFIX))
    end_of_line: str = "\r\n" if "\r\n" in document else "\n"
    path.write_text(_with_keys(lines, missing, end_of_line, start), encoding="utf-8", newline="")
    logger.info(
        "qBittorrent Web UI enabled in the client settings",
        keys=len(missing),
        password_generated=password is not None,
    )
    return WebUiSetup(path_written=True, password=password)


def _web_ui_keys(port: int) -> dict[str, str]:
    """Return the Web UI keys that need no secret, in the order they are written."""
    return {
        "WebUI\\Enabled": "true",
        "WebUI\\Address": _LOOPBACK,
        "WebUI\\Port": str(port),
        "WebUI\\LocalHostAuth": "false",
        "WebUI\\Username": _WEB_UI_USER,
    }


def _password_value(password: str) -> str:
    """Return *password* in the salted PBKDF2 form qBittorrent stores in its settings."""
    salt: bytes = secrets.token_bytes(_SALT_BYTES)
    digest: bytes = hashlib.pbkdf2_hmac(
        "sha512",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_KEY_BYTES,
    )
    encoded: str = f"{base64.b64encode(salt).decode('ascii')}:{base64.b64encode(digest).decode('ascii')}"
    return f'"@ByteArray({encoded})"'


def _section_start(lines: Sequence[str]) -> int | None:
    """Return the index of the preferences header, or ``None`` when the file has none."""
    for index, line in enumerate(lines):
        if line.strip() == _PREFERENCES_SECTION:
            return index
    return None


def _section_end(lines: Sequence[str], start: int) -> int:
    """Return the index just past the last key of the preferences section."""
    end: int = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].lstrip().startswith("["):
            end = index
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return end


def _section_keys(lines: Sequence[str], start: int | None) -> frozenset[str]:
    """Return the key names already present in the preferences section."""
    if start is None:
        return frozenset()
    return frozenset(
        lines[index].split("=", 1)[0].strip()
        for index in range(start + 1, _section_end(lines, start))
        if "=" in lines[index]
    )


def _with_keys(lines: Sequence[str], missing: Mapping[str, str], end_of_line: str, start: int | None) -> str:
    """Return the document with *missing* added to the preferences section."""
    added: list[str] = [f"{key}={value}{end_of_line}" for key, value in missing.items()]
    if start is None:
        return "".join([*_terminated(lines, end_of_line), f"{_PREFERENCES_SECTION}{end_of_line}", *added])
    end: int = _section_end(lines, start)
    return "".join([*_terminated(lines[:end], end_of_line), *added, *lines[end:]])


def _terminated(lines: Sequence[str], end_of_line: str) -> list[str]:
    """Return *lines* with the last one closed, so an added key starts on its own row."""
    closed: list[str] = list(lines)
    if closed and not closed[-1].endswith("\n"):
        closed[-1] += end_of_line
    return closed


def _unavailable(message: str, suggestion: str) -> QBittorrentConfigError:
    """Build the error for settings this system or this profile cannot offer."""
    return QBittorrentConfigError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            message=message,
            suggestion=suggestion,
        ),
    )


def _refused(message: str, suggestion: str) -> QBittorrentConfigError:
    """Build the error for a write the running client would undo."""
    return QBittorrentConfigError(
        context=ErrorContext(
            code=ErrorCode.TORRENT_CLIENT_REFUSED,
            message=message,
            suggestion=suggestion,
        ),
    )
