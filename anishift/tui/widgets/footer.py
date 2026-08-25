"""The one-row bottom bar: working path with git branch, then the version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Final

from textual.containers import Horizontal
from textual.widgets import Static

from anishift.tui.strings import HOME_MARK, LOCATION_SEPARATOR, PATH_ELLIPSIS

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Resize

__all__ = [
    "DISTRIBUTION",
    "LOCATION_ID",
    "VERSION_ID",
    "BottomBar",
    "app_version",
    "git_branch",
    "location_text",
    "shortened_path",
]

# ── Constants ──────────────────────────────────────────────────────────────

LOCATION_ID: Final[str] = "footer-location"
"""Id of the left half of the bar: the working path and the branch."""

VERSION_ID: Final[str] = "footer-version"
"""Id of the right half of the bar: the version of the application."""

DISTRIBUTION: Final[str] = "anishift"
"""Name of the distribution whose metadata carries the version."""

_GIT_DIR_NAME: Final[str] = ".git"
"""Name of the git directory, or of the file pointing at one in a worktree."""

_GIT_DIR_PREFIX: Final[str] = "gitdir:"
"""Prefix of the line a worktree writes instead of a git directory."""

_HEAD_FILE_NAME: Final[str] = "HEAD"
"""Name of the file inside a git directory that names the checked-out ref."""

_BRANCH_REF_PREFIX: Final[str] = "ref: refs/heads/"
"""Prefix marking a head that points at a branch instead of a commit."""


def app_version() -> str:
    """Return the version of the installed application, or nothing."""
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return ""


def git_branch(start: Path) -> str:
    """Return the branch checked out at *start*, or nothing.

    A missing repository, a detached head and an unreadable git directory all
    answer the same way: the bar shows an empty segment instead of failing.
    """
    git_dir: Path | None = _git_dir(start)
    if git_dir is None:
        return ""
    head: str | None = _read(git_dir / _HEAD_FILE_NAME)
    if head is None or not head.startswith(_BRANCH_REF_PREFIX):
        return ""
    return head.removeprefix(_BRANCH_REF_PREFIX)


def shortened_path(path: Path, home: Path) -> str:
    """Return *path* with *home* folded to a short mark, when it lies under it."""
    try:
        relative: Path = path.relative_to(home)
    except ValueError:
        return str(path)
    return str(Path(HOME_MARK) / relative)


def location_text(*, path: str, branch: str, width: int) -> str:
    """Return *path* and *branch* shortened from the left to fit *width*.

    Leading components go first, so the interesting tail of the path, the branch
    and therefore the identity of the checkout all survive a narrow terminal.
    """
    branded: str = f"{path}{LOCATION_SEPARATOR}{branch}" if branch else path
    if len(branded) <= width:
        return branded
    tail: str = f"{LOCATION_SEPARATOR}{branch}" if branch else ""
    room: int = width - len(tail) - len(PATH_ELLIPSIS)
    if room <= 0:
        return tail[:width]
    return f"{PATH_ELLIPSIS}{path[len(path) - room :]}{tail}"


def _git_dir(start: Path) -> Path | None:
    """Return the git directory governing *start*, or ``None`` without one."""
    for candidate in (start, *start.parents):
        entry: Path = candidate / _GIT_DIR_NAME
        if entry.is_dir():
            return entry
        pointer: str | None = _read(entry) if entry.is_file() else None
        if pointer is not None and pointer.startswith(_GIT_DIR_PREFIX):
            return Path(pointer.removeprefix(_GIT_DIR_PREFIX).strip())
    return None


def _read(path: Path) -> str | None:
    """Return the first line of *path*, or ``None`` when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError, UnicodeDecodeError, IndexError:
        return None


class BottomBar(Horizontal):
    """The one-row bottom bar: working path with branch, then version."""

    def __init__(self, *, widget_id: str) -> None:
        """Read the path, the branch and the version of this session once."""
        super().__init__(id=widget_id)
        self._path: str = shortened_path(Path.cwd(), Path.home())
        self._branch: str = git_branch(Path.cwd())
        self._release: str = app_version()
        self._location: Static = Static(id=LOCATION_ID)
        self._version: Static = Static(self._release, id=VERSION_ID)

    def compose(self) -> ComposeResult:
        """Draw the location on the left and the version on the right."""
        yield self._location
        yield self._version

    def on_mount(self) -> None:
        """Fill the left half for the width the bar was mounted at."""
        self._fill(self.size.width)

    def on_resize(self, event: Resize) -> None:
        """Shorten or restore the left half for the new width of the bar."""
        self._fill(event.size.width)

    def _fill(self, width: int) -> None:
        """Render the location into the columns the version leaves free."""
        room: int = max(0, width - len(self._release))
        self._location.update(location_text(path=self._path, branch=self._branch, width=room))
