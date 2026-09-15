"""Recoverable relocation of completed source groups into the shared ready directory."""

from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from anishift.application.artifacts import SourceGroup, create_group_id
from anishift.application.control import AcquisitionConfirmation, RecipePreferences, RequestState, WatchState
from anishift.application.discovery import ArtifactName, classify_artifact
from anishift.application.results import RunResult
from anishift.application.workflows import WorkflowRoute, WorkflowTarget
from anishift.errors import ExecutionError
from anishift.paths import READY_DIRECTORY, ready_dir
from anishift.utils.logger import get_logger

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TRANSIENT_DENIALS: Final[frozenset[int]] = frozenset({5, 32, 33})
"""Windows denials that disappear once a reader or scanner closes its handle."""

_RELEASE_ATTEMPTS: Final[int] = 40
"""Extra attempts allowed while a concurrent reader still holds a relocated file."""

_RELEASE_DELAY_S: Final[float] = 0.05
"""Delay between attempts of one relocated file."""


@dataclass(frozen=True, slots=True)
class ReadyFile:
    """One rename and the file identity required before removing its old pathname."""

    source: str
    destination: str
    size: int
    modified_ns: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class ReadyMove:
    """Persisted relocation of one completed group without rewriting media bytes."""

    group_id: str
    destination_group_id: str
    files: tuple[ReadyFile, ...]
    destination_stem: str = ""
    source_directory: str = ""
    source_stem: str = ""
    target: WorkflowTarget | None = None
    product_sources: tuple[str, ...] = ()
    recipe: RecipePreferences = field(default_factory=RecipePreferences)
    deferred: tuple[str, ...] = ()

    @property
    def moved(self) -> tuple[ReadyFile, ...]:
        """Return the files this stage may rename, leaving the ones a transfer still holds where they are."""
        return tuple(item for item in self.files if item.source not in frozenset(self.deferred))

    def apply_result(self, result: RunResult, workspace: Path) -> RunResult:
        """Point a completed result at the relocated products and group identity."""
        paths: dict[Path, Path] = {workspace / item.source: workspace / item.destination for item in self.moved}
        return replace(
            result,
            groups=tuple(
                replace(
                    group,
                    group_id=self.destination_group_id,
                    products=tuple(replace(item, path=paths.get(item.path, item.path)) for item in group.products),
                    preserved_products=tuple(
                        replace(item, path=paths.get(item.path, item.path)) for item in group.preserved_products
                    ),
                )
                if group.group_id == self.group_id
                else group
                for group in result.groups
            ),
        )

    def apply(self, state: WatchState) -> WatchState:
        """Update confirmations and successful requests after every proven rename of this stage."""
        paths: dict[str, str] = {item.source: item.destination for item in self.moved}
        names: dict[str, str] = {Path(old).name: Path(new).name for old, new in paths.items()}
        return replace(
            state,
            markers=tuple(
                replace(
                    marker,
                    group_id=self.destination_group_id,
                    fingerprint=tuple(
                        sorted((names.get(name, name), size, modified) for name, size, modified in marker.fingerprint)
                    ),
                )
                if marker.group_id == self.group_id
                else marker
                for marker in state.markers
            ),
            products=tuple(
                replace(product, group_id=self.destination_group_id, path=paths.get(product.path, product.path))
                if product.group_id == self.group_id
                else product
                for product in state.products
            ),
            requests=tuple(
                replace(
                    request,
                    group_ids=tuple(
                        self.destination_group_id if group == self.group_id else group for group in request.group_ids
                    ),
                    fingerprints={
                        self.destination_group_id if group == self.group_id else group: tuple(
                            sorted((names.get(name, name), size, modified) for name, size, modified in fingerprint)
                        )
                        if group == self.group_id
                        else fingerprint
                        for group, fingerprint in request.fingerprints.items()
                    },
                    intents=tuple(
                        replace(intent, group_id=self.destination_group_id)
                        if intent.group_id == self.group_id
                        else intent
                        for intent in request.intents
                    ),
                )
                if self.group_id in request.group_ids and request.state is RequestState.SUCCEEDED
                else request
                for request in state.requests
            ),
            acquisitions=tuple(_relocated_confirmation(item, paths) for item in state.acquisitions),
            notified=frozenset(
                (self.destination_group_id if group == self.group_id else group, generation, result)
                for group, generation, result in state.notified
            ),
        )


def _relocated_confirmation(item: AcquisitionConfirmation, paths: Mapping[str, str]) -> AcquisitionConfirmation:
    """Return one confirmation whose every remembered file name follows the renames this stage proved."""
    assigned: frozenset[str] = frozenset(item.required_files) | frozenset(
        path for _index, path, _size in item.file_layout
    )
    current: dict[str, str] = {name: (Path(item.directory) / name).as_posix() for name in assigned}
    if not any(name in paths for name in current.values()):
        return item
    moved: dict[str, str] = {name: paths.get(value, value) for name, value in current.items()}
    return replace(
        item,
        directory="",
        required_files=tuple(moved[name] for name in item.required_files),
        complete_files=tuple(moved[name] for name in item.complete_files),
        file_layout=tuple((index, moved[path], size) for index, path, size in item.file_layout),
    )


class ReadyStore:
    """Keep pending moves until their filesystem and owner-state updates both finish."""

    def __init__(self, directory: Path, workspace: Path) -> None:
        self._directory: Path = directory
        self._workspace: Path = workspace.resolve()

    def pending(self) -> tuple[ReadyMove, ...]:
        """Load unfinished moves before automatic admission sees partially moved files."""
        return tuple(
            TypeAdapter(ReadyMove).validate_json(path.read_bytes(), strict=True)
            for path in sorted(self._directory.glob("*.json"))
        )

    def prepare(
        self,
        group: SourceGroup,
        products: Sequence[Path],
        recipe: RecipePreferences | None = None,
    ) -> ReadyMove | None:
        """Record a collision-free destination and the accepted recipe before moving the first source or product."""
        pending: Path = self._path(group.group_id)
        if pending.exists():
            return TypeAdapter(ReadyMove).validate_json(pending.read_bytes(), strict=True)
        ready: Path = ready_dir(self._workspace)
        if group.directory.resolve() == ready.resolve():
            return None
        if ready.is_symlink() or not ready.resolve().is_relative_to(self._workspace):
            message: str = "The ready directory must remain inside the workspace"
            raise ExecutionError(message)
        files: tuple[Path, ...] = tuple(
            sorted(
                {
                    *(
                        artifact.path
                        for artifact in group.artifacts
                        if artifact.path is not None and artifact.path.is_file()
                    ),
                    *products,
                }
            )
        )
        if not files:
            return None
        if any(path.parent.resolve() != group.directory.resolve() or path.is_symlink() for path in files):
            message = "Relocation can only move regular files belonging to this source directory"
            raise ExecutionError(message)
        ready.mkdir(exist_ok=True)
        reserved: frozenset[Path] = self._reserved(group.group_id)
        destination_stem: str = group.stem
        destinations: tuple[Path, ...] = self._destinations(files, destination_stem, group.route)
        ordinal: int = 2
        while any(path.exists() or path in reserved for path in destinations):
            destination_stem = f"{group.stem} [{ordinal}]"
            destinations = self._destinations(files, destination_stem, group.route)
            ordinal += 1
        produced: frozenset[Path] = frozenset(products)
        move: ReadyMove = ReadyMove(
            group.group_id,
            create_group_id(Path(READY_DIRECTORY), destination_stem),
            tuple(
                _record(source, destination, self._workspace)
                for source, destination in zip(files, destinations, strict=True)
            ),
            destination_stem,
            source_directory=_relative_posix(group.directory, self._workspace),
            source_stem=group.stem,
            target=group.route.target,
            product_sources=tuple(path.relative_to(self._workspace).as_posix() for path in files if path in produced),
            recipe=recipe if recipe is not None else RecipePreferences(),
        )
        self._save(move)
        return move

    def execute(self, move: ReadyMove) -> None:
        """Finish exclusive same-volume moves of this stage, recovering even between link and unlink."""
        for item in move.moved:
            self._relocate(item)
        logger.info("Completed group moved to ready", files=len(move.moved), deferred=len(move.deferred))

    def defer(self, move: ReadyMove, sources: Sequence[str]) -> ReadyMove:
        """Record which sources a transfer still holds, keeping every destination this move already chose."""
        deferred: tuple[str, ...] = tuple(sorted(frozenset(sources) & {item.source for item in move.files}))
        if deferred == move.deferred:
            return move
        updated: ReadyMove = replace(move, deferred=deferred)
        self._save(updated)
        return updated

    def acknowledge(self, move: ReadyMove) -> None:
        """Remove the journal only after the owner's updated state is durable."""
        self._path(move.group_id).unlink(missing_ok=True)

    def _reserved(self, group_id: str) -> frozenset[Path]:
        """Return destinations another unfinished move already claimed, because neither has renamed a file yet."""
        return frozenset(
            self._workspace / item.destination
            for move in self.pending()
            if move.group_id != group_id
            for item in move.files
        )

    def _destinations(self, files: tuple[Path, ...], stem: str, route: WorkflowRoute) -> tuple[Path, ...]:
        destinations: list[Path] = []
        for path in files:
            candidate: ArtifactName | None = classify_artifact(path, route)
            if candidate is None:
                message: str = "A completed group contains an unrecognized file"
                raise ExecutionError(message)
            destinations.append(ready_dir(self._workspace) / f"{stem}{path.name[len(candidate.stem) :]}")
        if len(set(destinations)) != len(destinations):
            message = "Relocation would give two group files the same destination"
            raise ExecutionError(message)
        return tuple(destinations)

    def _relocate(self, item: ReadyFile) -> None:
        attempts: int = 0
        while True:
            try:
                self._move_file(item)
            except OSError as error:
                if attempts >= _RELEASE_ATTEMPTS or getattr(error, "winerror", None) not in _TRANSIENT_DENIALS:
                    raise
                attempts += 1
                logger.debug("Relocation waits for a reader to release a file", attempts=attempts)
                time.sleep(_RELEASE_DELAY_S)
                continue
            return

    def _move_file(self, item: ReadyFile) -> None:
        source: Path = self._workspace / item.source
        destination: Path = self._workspace / item.destination
        if any(
            not path.resolve().is_relative_to(self._workspace) or path.is_symlink() for path in (source, destination)
        ):
            message: str = "A relocation path escaped the workspace"
            raise ExecutionError(message)
        if destination.exists():
            _verify(destination, item)
            if source.exists():
                _verify(source, item)
                source.unlink()
            return
        _verify(source, item)
        if source.stat().st_dev != destination.parent.stat().st_dev:
            message = "Moving to ready requires the same volume"
            raise ExecutionError(message)
        os.link(source, destination)
        _verify(source, item)
        source.unlink()

    def _save(self, move: ReadyMove) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path: Path = self._path(move.group_id)
        temporary: Path = path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            stream.write(TypeAdapter(ReadyMove).dump_json(move))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)

    def _path(self, group_id: str) -> Path:
        if Path(group_id).name != group_id or group_id in {".", ".."}:
            message: str = "Relocation requires a safe group identifier"
            raise ExecutionError(message)
        return self._directory / f"{group_id}.json"


def _relative_posix(directory: Path, root: Path) -> str:
    """Return one workspace directory as the relative text a durable record may carry."""
    relative: Path = directory.resolve().relative_to(root)
    return relative.as_posix() if relative.parts else "."


def _record(source: Path, destination: Path, root: Path) -> ReadyFile:
    status: os.stat_result = source.stat()
    return ReadyFile(
        source.relative_to(root).as_posix(),
        destination.relative_to(root).as_posix(),
        status.st_size,
        status.st_mtime_ns,
        status.st_dev,
        status.st_ino,
    )


def _verify(path: Path, item: ReadyFile) -> None:
    status: os.stat_result = path.stat()
    if not path.is_file() or (status.st_size, status.st_mtime_ns, status.st_dev, status.st_ino) != (
        item.size,
        item.modified_ns,
        item.device,
        item.inode,
    ):
        message: str = "A relocation source or destination changed; both locations were preserved"
        raise ExecutionError(message)
