"""Download and install external resources per the manifest."""

from __future__ import annotations

import hashlib
import tempfile
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import nullcontext
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
from anishift.utils.logger import get_logger
from anishift.utils.rich_console import MultiProgressManager, ProgressBarManager

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

logger = get_logger(__name__)


class InstallerError(FatalError):
    """Raised when installing a resource fails."""


class HashMismatchError(InstallerError):
    """Raised when a downloaded archive fails SHA256 verification."""


class InstallCancelledError(InstallerError):
    """Raised inside a download worker when the user cancelled the run."""


@dataclass(frozen=True, slots=True)
class ResourceResult:
    """Outcome of handling one resource during a setup run."""

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
    """Extract *resource*'s named members from *archive* into *dest_root*."""
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
    cancel: Callable[[], bool] | None = None,
) -> None:
    """Stream *resource*'s archive to *target* over HTTPS."""
    _raise_if_cancelled(cancel)
    with httpx.stream("GET", resource.source.url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                _raise_if_cancelled(cancel)
                handle.write(chunk)
                if progress is not None:
                    progress(len(chunk))
    _raise_if_cancelled(cancel)


def _raise_if_cancelled(cancel: Callable[[], bool] | None) -> None:
    """Stop resource preparation at a cooperative cancellation boundary."""
    if cancel is not None and cancel():
        raise InstallCancelledError(
            context=ErrorContext(code=ErrorCode.CANCELLED, message="Resource preparation cancelled"),
        )


def install_resource(
    resource: Resource,
    *,
    dest_root: Path,
    download: DownloadFn = _download_httpx,
    force: bool = False,
) -> ResourceResult:
    """Install one resource, skipping when already present."""
    if not force and is_installed(resource, dest_root):
        logger.debug("External resource installation skipped", resource=resource.name, reason="already_present")
        return ResourceResult(resource.name, "skipped", "already present")

    logger.info("External resource installation started", resource=resource.name, force=force)
    dest_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest_root, ignore_cleanup_errors=True) as tmp:
        tmp_dir: Path = Path(tmp)
        archive: Path = tmp_dir / f"{resource.name}.{resource.archive}"
        download(resource, archive)

        actual: str = sha256_file(archive)
        if actual != resource.sha256:
            raise HashMismatchError(
                context=ErrorContext(
                    code=ErrorCode.BINARY_HASH_MISMATCH,
                    message=f"{resource.name}: sha256 mismatch — corrupt download or stale manifest",
                    suggestion="Re-run `anishift setup`; if it persists, update external/bin_hashes.json",
                    details={"expected": resource.sha256, "actual": actual},
                ),
            )

        staged: Path = tmp_dir / "staged"
        extract_members(archive, resource, staged)
        for member in resource.members:
            final: Path = dest_root / member.dest
            final.parent.mkdir(parents=True, exist_ok=True)
            (staged / member.dest).replace(final)

    logger.info("External resource installation completed", resource=resource.name)
    return ResourceResult(resource.name, "installed", "downloaded and verified")


# ── Lazy ensure (domain entry point) ─────────────────────────────────────────


def _install_single(
    resource: Resource,
    dest_root: Path,
    *,
    show_progress: bool,
    progress: ProgressFn | None,
    cancel: Callable[[], bool] | None,
) -> None:
    """Install one resource with optional terminal and byte progress observers."""
    with (
        ProgressBarManager(
            f"Downloading {resource.name}",
            total=resource.size_bytes,
            bar="blocks",
            show_download=True,
            show_speed=True,
            show_percentage=True,
            show_elapsed=True,
            show_eta=False,
            show_spinner=False,
        )
        if show_progress
        else nullcontext()
    ) as bar:

        def advance(amount: int) -> None:
            if bar is not None:
                bar.advance(amount)
            if progress is not None:
                progress(amount)

        def _download(res: Resource, target: Path) -> None:
            _download_httpx(res, target, progress=advance, cancel=cancel)
            _raise_if_cancelled(cancel)

        install_resource(resource, dest_root=dest_root, download=_download)


def ensure_resource(  # noqa: PLR0913 - optional install boundary controls
    name: str,
    *,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
    show_progress: bool = True,
    progress: ProgressFn | None = None,
    cancel: Callable[[], bool] | None = None,
) -> None:
    """Ensure one manifest resource is installed, downloading it on demand."""
    _raise_if_cancelled(cancel)
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
        _install_single(resource, root, show_progress=show_progress, progress=progress, cancel=cancel)
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
    """Return the name of the resource whose members install *binary*."""
    for resource in resources:
        for member in resource.members:
            stem = Path(member.dest).name.removesuffix(_EXE_SUFFIX)
            if stem == binary.value:
                return resource.name
    return None


def ensure_binary(
    binary: Binary,
    *,
    show_progress: bool = True,
    progress: ProgressFn | None = None,
    cancel: Callable[[], bool] | None = None,
) -> Path:
    """Return *binary*'s path, installing its resource first when missing."""
    _raise_if_cancelled(cancel)
    path = resolve_binary(binary)
    if path is not None:
        return path
    resource_name = _resource_for(binary, load_manifest())
    if resource_name is not None:
        ensure_resource(resource_name, show_progress=show_progress, progress=progress, cancel=cancel)
    _raise_if_cancelled(cancel)
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


def _install_parallel(
    to_install: list[Resource],
    dest_root: Path,
    *,
    force: bool,
    show_progress: bool,
) -> dict[str, ResourceResult]:
    """Download and install *to_install* in parallel, one progress bar per resource."""
    if not show_progress:
        return _install_parallel_silent(to_install, dest_root, force=force)
    cancel = threading.Event()
    futures: dict[str, Future[ResourceResult]] = {}
    try:
        with (
            MultiProgressManager(show_download=True) as bar,
            ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool,
        ):
            tasks = {resource.name: bar.add_task(resource.name, total=resource.size_bytes) for resource in to_install}

            def _download_for(resource: Resource) -> DownloadFn:
                task = tasks[resource.name]

                def _download(res: Resource, target: Path) -> None:
                    def _advance(amount: int) -> None:
                        bar.advance(task, amount)

                    _download_httpx(res, target, progress=_advance, cancel=cancel.is_set)
                    bar.update(task, res.size_bytes)

                return _download

            futures = {
                resource.name: pool.submit(
                    install_resource,
                    resource,
                    dest_root=dest_root,
                    download=_download_for(resource),
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


def _install_parallel_silent(
    to_install: list[Resource],
    dest_root: Path,
    *,
    force: bool,
) -> dict[str, ResourceResult]:
    futures: dict[str, Future[ResourceResult]] = {}
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = {
            resource.name: pool.submit(
                install_resource,
                resource,
                dest_root=dest_root,
                force=force,
            )
            for resource in to_install
        }
    return _collect(futures)


def run_setup(
    *,
    force: bool = False,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
    show_progress: bool = True,
) -> list[ResourceResult]:
    """Install every manifest resource up front; never crash the caller."""
    loaded = resources if resources is not None else load_manifest()
    root = dest_root if dest_root is not None else external_bin_root()
    logger.info("Setup run started", resource_count=len(loaded), force=force)

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
        results.update(_install_parallel(to_install, root, force=force, show_progress=show_progress))
    ordered = [results[resource.name] for resource in loaded]
    logger.info(
        "Setup run completed",
        installed=sum(result.outcome == "installed" for result in ordered),
        skipped=sum(result.outcome == "skipped" for result in ordered),
        failed=sum(result.outcome == "failed" for result in ordered),
        cancelled=sum(result.outcome == "cancelled" for result in ordered),
        unavailable=sum(result.outcome == "unavailable" for result in ordered),
    )
    return ordered
