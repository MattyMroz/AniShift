"""Recoverable relocation of completed source groups into the shared ready directory."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import TypeAdapter

from anishift.application.artifacts import SourceGroup, create_group_id
from anishift.application.control import RequestState, WatchState
from anishift.application.discovery import ArtifactName, classify_artifact
from anishift.application.results import RunResult
from anishift.errors import ExecutionError
from anishift.paths import READY_DIRECTORY, ready_dir
from anishift.utils.logger import get_logger

logger = get_logger(__name__)


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

    def apply_result(self, result: RunResult, workspace: Path) -> RunResult:
        """Point a completed result at the relocated products and group identity."""
        paths: dict[Path, Path] = {workspace / item.source: workspace / item.destination for item in self.files}
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
        """Update confirmations and successful requests after every rename is proven."""
        paths: dict[str, str] = {item.source: item.destination for item in self.files}
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
            acquisitions=tuple(
                replace(
                    item,
                    directory="",
                    required_files=tuple(
                        paths.get((Path(item.directory) / name).as_posix(), (Path(item.directory) / name).as_posix())
                        for name in item.required_files
                    ),
                )
                if any((Path(item.directory) / name).as_posix() in paths for name in item.required_files)
                else item
                for item in state.acquisitions
            ),
            notified=frozenset(
                (self.destination_group_id if group == self.group_id else group, generation, result)
                for group, generation, result in state.notified
            ),
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

    def prepare(self, group: SourceGroup, products: Sequence[Path]) -> ReadyMove | None:
        """Record a collision-free destination before moving the first source or product."""
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
        destination_stem: str = group.stem
        destinations: tuple[Path, ...] = self._destinations(files, destination_stem)
        ordinal: int = 2
        while any(path.exists() for path in destinations):
            destination_stem = f"{group.stem} [{ordinal}]"
            destinations = self._destinations(files, destination_stem)
            ordinal += 1
        move: ReadyMove = ReadyMove(
            group.group_id,
            create_group_id(Path(READY_DIRECTORY), destination_stem),
            tuple(
                _record(source, destination, self._workspace)
                for source, destination in zip(files, destinations, strict=True)
            ),
        )
        self._save(move)
        return move

    def execute(self, move: ReadyMove) -> None:
        """Finish exclusive same-volume moves, recovering even between link and unlink."""
        for item in move.files:
            self._move_file(item)
        logger.info("Completed group moved to ready", files=len(move.files))

    def acknowledge(self, move: ReadyMove) -> None:
        """Remove the journal only after the owner's updated state is durable."""
        self._path(move.group_id).unlink(missing_ok=True)

    def _destinations(self, files: tuple[Path, ...], stem: str) -> tuple[Path, ...]:
        destinations: list[Path] = []
        for path in files:
            candidate: ArtifactName | None = classify_artifact(path)
            if candidate is None:
                message: str = "A completed group contains an unrecognized file"
                raise ExecutionError(message)
            destinations.append(ready_dir(self._workspace) / f"{stem}{path.name[len(candidate.stem) :]}")
        if len(set(destinations)) != len(destinations):
            message = "Relocation would give two group files the same destination"
            raise ExecutionError(message)
        return tuple(destinations)

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
