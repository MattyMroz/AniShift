"""Project completed sets and validate their exact workspace file scope."""

from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from pathlib import Path

from natsort import os_sorted

from anishift.application.artifacts import SourceGroup
from anishift.application.control import (
    ProcessingRequest,
    ProductConfirmation,
    ReadyGroup,
    RequestState,
    WatchState,
    require_relative_paths,
)
from anishift.application.control_views import LibraryFile, LibraryFileIdentity, LibrarySet
from anishift.application.discovery import ArtifactName, classify_artifact
from anishift.application.intents import GroupIntent
from anishift.application.products import main_product
from anishift.application.workflows import WorkflowRoute, WorkflowTarget, WorkspacePlace
from anishift.paths import READY_DIRECTORY


def file_identity(root: Path, name: str) -> LibraryFileIdentity | None:
    """Read a regular workspace file without accepting a symlink, junction or escaped path."""
    require_relative_paths((name,), "A library file")
    path: Path = root / name
    try:
        if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents) if part.is_relative_to(root)):
            return None
        if not path.resolve().is_relative_to(root.resolve()):
            return None
        status: os.stat_result = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    return LibraryFileIdentity(name, status.st_size, status.st_mtime_ns, status.st_dev, status.st_ino)


def project_library(state: WatchState, root: Path, groups: Sequence[SourceGroup]) -> tuple[LibrarySet, ...]:
    """Reconcile completed sets from provenance, confirmations and the shared discovery inventory."""
    discovered: dict[str, SourceGroup] = {group.group_id: group for group in groups}
    result: list[LibrarySet] = [
        _recorded_set(item, state, root, discovered.get(item.group_id)) for item in state.ready_groups
    ]
    recorded: frozenset[str] = frozenset(item.group_id for item in state.ready_groups)
    result.extend(
        item
        for group in groups
        if group.group_id not in recorded
        and group.directory.is_relative_to(root / READY_DIRECTORY)
        and (item := _legacy_set(group, state, root)) is not None
    )
    return tuple(os_sorted(result, key=lambda item: (item.name, item.set_id)))


def _recorded_set(record: ReadyGroup, state: WatchState, root: Path, group: SourceGroup | None) -> LibrarySet:
    roles: dict[str, str] = dict.fromkeys(record.sources, "source")
    roles.update(dict.fromkeys(record.products, "product"))
    roles.update(dict.fromkeys(record.pending_sources, "pending_source"))
    if group is not None:
        roles.update(
            {name: role for name, role in _discovered_members(group, root, record.target).items() if name not in roles}
        )
    files: tuple[LibraryFile, ...] = tuple(_library_file(root, name, roles[name]) for name in sorted(roles))
    available: bool = _confirmed_main(record.group_id, record.main_result, files, state.products)
    problem: str | None = None
    if not available:
        problem = (
            "library_result_changed"
            if any(item.path == record.main_result and item.identity is not None for item in files)
            else "library_result_missing"
        )
    return LibrarySet(
        record.set_id,
        record.group_id,
        record.stem,
        record.target,
        record.main_result,
        files,
        available,
        problem,
        record.target is WorkflowTarget.TRANSLATE
        and any(Path(name).suffix.casefold() == ".txt" for name in record.sources)
        and record.main_result is not None
        and Path(record.main_result).suffix.casefold() == ".srt",
    )


def _discovered_members(group: SourceGroup, root: Path, target: WorkflowTarget | None) -> dict[str, str]:
    members: dict[str, str] = {}
    for artifact in group.artifacts:
        path: Path | None = artifact.path
        if path is None or not path.is_relative_to(root) or path.parent != group.directory:
            continue
        candidate: ArtifactName | None = classify_artifact(path, WorkflowRoute(WorkspacePlace.READY, target))
        if candidate is not None and candidate.stem.casefold() == group.stem.casefold():
            members[path.relative_to(root).as_posix()] = "product" if candidate.is_derived else "source"
    return members


def _library_file(root: Path, name: str, role: str) -> LibraryFile:
    return LibraryFile(name, role, Path(name).suffix.removeprefix(".").upper(), file_identity(root, name))


def _confirmed_main(
    group_id: str, name: str | None, files: tuple[LibraryFile, ...], products: tuple[ProductConfirmation, ...]
) -> bool:
    identity: LibraryFileIdentity | None = next((item.identity for item in files if item.path == name), None)
    if identity is None:
        return False
    return any(
        item.group_id == group_id
        and item.path == name
        and (item.size, item.modified_ns) == (identity.size, identity.modified_ns)
        for item in products
    )


def _legacy_set(group: SourceGroup, state: WatchState, root: Path) -> LibrarySet | None:
    latest: ProcessingRequest | None = max(
        (item for item in state.requests if item.state is RequestState.SUCCEEDED and group.group_id in item.group_ids),
        key=lambda item: (item.generation, item.accepted_at),
        default=None,
    )
    if latest is None:
        return None
    intent: GroupIntent | None = next((item for item in latest.intents if item.group_id == group.group_id), None)
    products: tuple[str, ...] = tuple(
        item.path
        for item in state.products
        if item.group_id == group.group_id
        and (
            item.artifact_kind.removeprefix("final_") in intent.products.requested_products
            if intent is not None
            else item.request_id == latest.request_id
        )
    )
    headline: str | None = main_product([Path(name).name for name in products])
    primary: str | None = next((name for name in products if Path(name).name == headline), None)
    if primary is None:
        return None
    files: tuple[LibraryFile, ...] = tuple(
        _library_file(root, name, role) for name, role in _discovered_members(group, root, None).items()
    )
    if not _confirmed_main(group.group_id, primary, files, state.products):
        return None
    target: WorkflowTarget | None = intent.target if intent is not None else None
    return LibrarySet(
        group.group_id, group.group_id, group.stem, target, primary, files, True, "library_ownership_unknown"
    )
