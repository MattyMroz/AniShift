"""Download and install external resources per the manifest.

For every manifest resource: skip it when its members are already present,
otherwise download the archive to a temp dir, verify its SHA256, extract only
the named members (rejecting path traversal), and move them into the install
root. Nothing lands in the live tree unless the archive verified.

Two entry points share those steps:

- ``ensure_binary`` / ``ensure_resource`` — lazy, called by domain code right
  before a tool is used; installs exactly one missing resource, synchronously,
  behind its own progress bar, and raises a typed domain error on failure.
- ``run_setup`` — explicit "download everything up front" behind `/setup` and
  ``anishift setup``; missing resources download in parallel behind one shared
  progress bar and failures become report entries, never exceptions.

Usage:
    from anishift.setup.installer import ensure_binary, run_setup

    mkvextract = ensure_binary(Binary.MKVEXTRACT)   # domain code (stages 3/6)
    report = run_setup()            # `/setup`, `anishift setup`
    report = run_setup(force=True)  # `/setup force` / `anishift setup --force`
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.platform.binaries import (
    Binary,
    external_bin_root,
    is_windows,
    require_binary,
    resolve_binary,
)
from anishift.setup.manifest import Resource, load_manifest
from utils.rich_console import ProgressBarManager

__all__ = [
    "HashMismatchError",
    "InstallCancelledError",
    "InstallerError",
    "ResourceOutcome",
    "ResourceResult",
    "ensure_binary",
    "ensure_resource",
    "extract_members",
    "install_resource",
    "is_installed",
    "run_setup",
    "sha256_file",
]

ResourceOutcome = Literal["installed", "skipped", "failed", "unavailable", "cancelled"]
"""What happened to one resource during a setup run."""

DownloadFn = Callable[[Resource, Path], None]
"""Downloads a resource's archive to the given target path."""

ProgressFn = Callable[[int], None]
"""Advances the shared progress bar by a number of bytes."""

# ── Constants ────────────────────────────────────────────────────────────────

_CHUNK_SIZE: Final[int] = 1 << 20
"""Stream chunk size in bytes (1 MiB)."""

_DOWNLOAD_TIMEOUT: Final[float] = 30.0
"""Per-operation (connect/read/write) HTTP timeout in seconds."""

_MAX_PARALLEL: Final[int] = 2
"""Maximum resources downloaded at the same time."""

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Future-poll interval that keeps Ctrl+C responsive on Windows."""

_EXE_SUFFIX: Final[str] = ".exe"
"""Extension stripped from a member destination to read its binary stem."""


class InstallerError(FatalError):
    """Raised when installing a resource fails."""


class HashMismatchError(InstallerError):
    """Raised when a downloaded archive fails SHA256 verification."""


class InstallCancelledError(InstallerError):
    """Raised inside a download worker when the user cancelled the run."""


@dataclass(frozen=True, slots=True)
class ResourceResult:
    """Outcome of handling one resource during a setup run.

    Attributes:
        name: Resource name from the manifest.
        outcome: What happened.
        detail: Human-readable one-liner for the report.
    """

    name: str
    outcome: ResourceOutcome
    detail: str


# ── Verification ─────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest of *path*, streamed in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def is_installed(resource: Resource, dest_root: Path) -> bool:
    """Return ``True`` when every member of *resource* exists and is non-empty."""
    for member in resource.members:
        target = dest_root / member.dest
        if not target.is_file() or target.stat().st_size == 0:
            return False
    return True


# ── Extraction ───────────────────────────────────────────────────────────────


def _fail(message: str) -> InstallerError:
    """Build an :class:`InstallerError` with a consistent context."""
    return InstallerError(
        context=ErrorContext(
            code=ErrorCode.IO_ERROR,
            message=message,
            suggestion="Re-run `anishift setup`",
        ),
    )


def _read_member(archive: Path, resource: Resource, archive_path: str) -> bytes:
    """Read one member's bytes from a zip archive."""
    try:
        with zipfile.ZipFile(archive) as zf:
            if archive_path not in zf.namelist():
                msg = f"member not found in archive: {archive_path}"
                raise _fail(msg)
            return zf.read(archive_path)
    except zipfile.BadZipFile as exc:
        msg = f"{resource.name}: broken zip archive"
        raise _fail(msg) from exc


def extract_members(archive: Path, resource: Resource, dest_root: Path) -> None:
    """Extract *resource*'s named members from *archive* into *dest_root*.

    Destinations were validated against traversal at manifest load; this
    re-checks after resolving, then writes each member.
    """
    root = dest_root.resolve()
    for member in resource.members:
        target = (dest_root / member.dest).resolve()
        if not target.is_relative_to(root):
            msg = f"member dest escapes the install root: {member.dest}"
            raise _fail(msg)
        data = _read_member(archive, resource, member.archive_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


# ── Download & install ───────────────────────────────────────────────────────


def _download_httpx(
    resource: Resource,
    target: Path,
    *,
    progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Stream *resource*'s archive to *target* over HTTPS."""
    with httpx.stream("GET", resource.source.url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                if cancel is not None and cancel.is_set():
                    raise InstallCancelledError(
                        context=ErrorContext(
                            code=ErrorCode.CANCELLED,
                            message=f"{resource.name}: download cancelled",
                        ),
                    )
                handle.write(chunk)
                if progress is not None:
                    progress(len(chunk))


def install_resource(
    resource: Resource,
    *,
    dest_root: Path,
    download: DownloadFn = _download_httpx,
    force: bool = False,
) -> ResourceResult:
    """Install one resource, skipping when already present.

    Args:
        resource: The resource to install.
        dest_root: Root the members are placed under (``external/bin``).
        download: Injectable downloader (real HTTPS by default; fakes in tests).
        force: Reinstall even when the members are present.

    Returns:
        A :class:`ResourceResult` (``installed`` or ``skipped``).

    Raises:
        HashMismatchError: When the downloaded archive fails verification.
        InstallCancelledError: When the user cancelled the download.
        InstallerError: On extraction failure or a broken archive.
        httpx.HTTPError: On network or server failure (callers map it).
        OSError: On disk failure (callers map it).
    """
    if not force and is_installed(resource, dest_root):
        return ResourceResult(resource.name, "skipped", "already present")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / f"{resource.name}.{resource.archive}"
        download(resource, archive)

        actual = sha256_file(archive)
        if actual != resource.sha256:
            raise HashMismatchError(
                context=ErrorContext(
                    code=ErrorCode.BINARY_HASH_MISMATCH,
                    message=f"{resource.name}: sha256 mismatch — corrupt download or stale manifest",
                    suggestion="Re-run `anishift setup`; if it persists, update external/bin_hashes.json",
                    details={"expected": resource.sha256, "actual": actual},
                ),
            )

        staged = tmp_dir / "staged"
        extract_members(archive, resource, staged)
        for member in resource.members:
            final = dest_root / member.dest
            final.parent.mkdir(parents=True, exist_ok=True)
            final.unlink(missing_ok=True)
            shutil.move(staged / member.dest, final)

    return ResourceResult(resource.name, "installed", "downloaded and verified")


# ── Lazy ensure (domain entry point) ─────────────────────────────────────────


def _install_single(resource: Resource, dest_root: Path) -> None:
    """Install one resource synchronously behind its own progress bar."""
    with ProgressBarManager(
        f"Downloading {resource.name}",
        total=resource.size_bytes,
        bar="blocks",
        show_download=True,
        show_speed=True,
        show_percentage=True,
        show_elapsed=True,
        show_eta=False,
        show_spinner=False,
    ) as bar:

        def _download(res: Resource, target: Path) -> None:
            _download_httpx(res, target, progress=bar.advance)

        install_resource(resource, dest_root=dest_root, download=_download)


def ensure_resource(
    name: str,
    *,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
) -> None:
    """Ensure one manifest resource is installed, downloading it on demand.

    The lazy counterpart of :func:`run_setup`, called by domain code right
    before a resource is used (for binaries via :func:`ensure_binary`). An
    installed resource returns immediately; a missing one downloads alone,
    synchronously, behind a single-resource progress bar. Off Windows this is
    a silent no-op for ``binary`` resources — the ``PATH`` fallback in
    ``binaries.py`` applies instead.

    Args:
        name: Resource name from the manifest (e.g. ``"mkvtoolnix"``).
        resources: Manifest override for tests (defaults to :func:`load_manifest`).
        dest_root: Install-root override for tests (defaults to ``external/bin``).

    Raises:
        InstallerError: When *name* is unknown or the install fails — network
            and disk errors are mapped so callers always get a domain error.
        HashMismatchError: When the downloaded archive fails verification.
        ManifestError: When the manifest itself is broken (fail-loud dev error).
    """
    loaded = resources if resources is not None else load_manifest()
    root = dest_root if dest_root is not None else external_bin_root()
    resource = next((entry for entry in loaded if entry.name == name), None)
    if resource is None:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message=f"unknown resource: {name}",
                suggestion="Fix the resource name or add it to external/bin_hashes.json",
            ),
        )
    if resource.kind == "binary" and not is_windows():
        return
    if is_installed(resource, root):
        return
    try:
        _install_single(resource, root)
    except httpx.HTTPError as exc:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.NETWORK_ERROR,
                message=f"{name}: download failed: {exc}",
                suggestion="Check your internet connection, then retry or run `anishift setup`",
            ),
        ) from exc
    except OSError as exc:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.IO_ERROR,
                message=f"{name}: install failed: {exc}",
                suggestion="Check disk space and permissions, then run `anishift setup`",
            ),
        ) from exc


def _resource_for(binary: Binary, resources: tuple[Resource, ...]) -> str | None:
    """Return the name of the resource whose members install *binary*.

    Args:
        binary: The executable to find a provider for.
        resources: Parsed manifest resources.

    Returns:
        The providing resource's name, or ``None`` when no resource installs it.
    """
    for resource in resources:
        for member in resource.members:
            stem = Path(member.dest).name.removesuffix(_EXE_SUFFIX)
            if stem == binary.value:
                return resource.name
    return None


def ensure_binary(binary: Binary) -> Path:
    """Return *binary*'s path, installing its resource first when missing.

    The single lazy entry point for domain code (stage 3 extraction, stage 6
    audio): an installed binary resolves immediately — no manifest read, no
    network — and a missing one triggers the download of exactly the one
    resource that provides it.

    Args:
        binary: The executable the caller is about to run.

    Returns:
        Absolute path to the executable.

    Raises:
        InstallerError: When the on-demand install fails (network, disk, hash).
        BinaryNotFoundError: When the binary cannot be provided at all (other
            OS without a ``PATH`` fallback, or no manifest resource maps to it).
    """
    path = resolve_binary(binary)
    if path is not None:
        return path
    resource_name = _resource_for(binary, load_manifest())
    if resource_name is not None:
        ensure_resource(resource_name)
    return require_binary(binary)


# ── Setup runner ─────────────────────────────────────────────────────────────


def _result_of(name: str, future: Future[ResourceResult]) -> ResourceResult:
    """Map one worker future to a :class:`ResourceResult`, never raising."""
    try:
        result = future.result()
    except InstallCancelledError:
        return ResourceResult(name, "cancelled", "download interrupted — will retry on next start")
    except InstallerError as exc:
        return ResourceResult(name, "failed", str(exc))
    except httpx.HTTPError as exc:
        return ResourceResult(name, "failed", f"download failed: {exc}")
    except OSError as exc:
        return ResourceResult(name, "failed", f"install failed: {exc}")
    return result


def _collect(futures: dict[str, Future[ResourceResult]]) -> dict[str, ResourceResult]:
    """Turn finished worker futures into a name-keyed result map."""
    return {name: _result_of(name, future) for name, future in futures.items()}


def _install_parallel(to_install: list[Resource], dest_root: Path, *, force: bool) -> dict[str, ResourceResult]:
    """Download and install *to_install* in parallel behind one shared bar."""
    cancel = threading.Event()
    bar_lock = threading.Lock()
    total = sum(resource.size_bytes for resource in to_install)
    futures: dict[str, Future[ResourceResult]] = {}
    try:
        with (
            ProgressBarManager(
                "Downloading tools",
                total=total,
                bar="blocks",
                show_download=True,
                show_speed=True,
                show_percentage=True,
                show_elapsed=True,
                show_eta=False,
                show_spinner=False,
            ) as bar,
            ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool,
        ):

            def _advance(amount: int) -> None:
                with bar_lock:
                    bar.advance(amount)

            def _download(resource: Resource, target: Path) -> None:
                _download_httpx(resource, target, progress=_advance, cancel=cancel)

            futures = {
                resource.name: pool.submit(
                    install_resource,
                    resource,
                    dest_root=dest_root,
                    download=_download,
                    force=force,
                )
                for resource in to_install
            }
            pending = set(futures.values())
            try:
                while pending:
                    _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
            except KeyboardInterrupt:
                cancel.set()
                raise
    except KeyboardInterrupt:
        return _collect(futures)
    return _collect(futures)


def run_setup(
    *,
    force: bool = False,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
) -> list[ResourceResult]:
    """Install every manifest resource up front; never crash the caller.

    The explicit bulk path behind `/setup` and ``anishift setup``. Per-resource
    failures (network, disk, bad hash, Ctrl+C) become ``failed`` or
    ``cancelled`` entries in the returned report instead of exceptions, so the
    caller can always render a complete report and keep running.

    Args:
        force: Reinstall everything, even resources already present.
        resources: Manifest override for tests (defaults to :func:`load_manifest`).
        dest_root: Install-root override for tests (defaults to ``external/bin``).

    Returns:
        One :class:`ResourceResult` per manifest resource, in manifest order.

    Raises:
        ManifestError: When the manifest itself is broken (fail-loud dev error).
    """
    loaded = resources if resources is not None else load_manifest()
    root = dest_root if dest_root is not None else external_bin_root()

    results: dict[str, ResourceResult] = {}
    to_install: list[Resource] = []
    for resource in loaded:
        if resource.kind == "binary" and not is_windows():
            results[resource.name] = ResourceResult(resource.name, "unavailable", "install via your OS package manager")
        elif not force and is_installed(resource, root):
            results[resource.name] = ResourceResult(resource.name, "skipped", "already present")
        else:
            to_install.append(resource)

    if to_install:
        results.update(_install_parallel(to_install, root, force=force))
    return [results[resource.name] for resource in loaded]
