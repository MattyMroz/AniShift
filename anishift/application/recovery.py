"""Durable remaining work and proof of an interrupted product publication."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from anishift.application.artifacts import Artifact, ArtifactLifetime, ArtifactState
from anishift.application.planning import ExecutionPlan
from anishift.application.results import ProducedArtifact, TaskResult
from anishift.errors import AniShiftError, ExecutionError

if TYPE_CHECKING:
    from anishift.application.planning import PlanTask
    from anishift.application.ready import ReadyMove

# ── Constants ─────────────────────────────────────────────────────────────────

CHECKPOINT_VERSION: Final[int] = 1
"""Schema of the remaining graph stored beside the owner's request ledger."""


@dataclass(frozen=True, slots=True)
class _FileProof:
    path: Path
    size: int
    modified_ns: int
    device: int
    inode: int
    artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class _Checkpoint:
    version: int
    plan: ExecutionPlan
    run_root: Path
    inputs: tuple[_FileProof, ...]
    outputs: tuple[_FileProof, ...] = ()
    pending: TaskResult | None = None
    staged: _FileProof | None = None
    inflight: frozenset[str] = frozenset()


class RunJournal:
    """Persist a resumable graph before publishing and after each completed task."""

    def __init__(self, path: Path, checkpoint: _Checkpoint) -> None:
        self._path: Path = path
        self._checkpoint: _Checkpoint = checkpoint
        self._failed: bool = False
        self._revision: tuple[int, int, int, int] | None = None

    def is_current(self) -> bool:
        """Check journal identity without rereading its graph or validating media files."""
        try:
            return self._revision == _revision(self._path)
        except OSError:
            return False

    @property
    def plan(self) -> ExecutionPlan:
        """Return the remaining graph with verified completed artifacts as ready inputs."""
        return self._checkpoint.plan

    @property
    def failed(self) -> bool:
        """Whether recording this run failed and further tasks must stop."""
        return self._failed

    @property
    def uncertain_remote_work(self) -> bool:
        """Whether a remote operation started without a durable completion proof."""
        return bool(self._checkpoint.inflight)

    def started(self, task: PlanTask) -> None:
        """Record potentially charged work before dispatching its external operation."""
        self._require_writable()
        if task.is_network or task.is_paid:
            self._save(replace(self._checkpoint, inflight=self._checkpoint.inflight | {task.task_id}))

    def products(self, group_id: str) -> tuple[ProducedArtifact, ...]:
        """Return published products retained from this run's completed tasks."""
        identifiers: frozenset[str | None] = frozenset(item.artifact_id for item in self._checkpoint.outputs)
        return tuple(
            ProducedArtifact(artifact.artifact_id, artifact.path, {"published": True, "recovered": True})
            for artifact in self.plan.artifacts
            if artifact.group_id == group_id
            and artifact.lifetime is ArtifactLifetime.DURABLE
            and artifact.state is ArtifactState.READY
            and artifact.path is not None
            and artifact.artifact_id in identifiers
        )

    @classmethod
    def create(cls, path: Path, plan: ExecutionPlan, run_root: Path) -> RunJournal:
        """Persist a fresh accepted plan without altering any source or product."""
        inputs: set[Path] = {
            artifact.path
            for artifact in plan.artifacts
            if artifact.state is ArtifactState.READY and artifact.path is not None
        }
        inputs.update(artifact.preserved_path for artifact in plan.artifacts if artifact.preserved_path is not None)
        journal: RunJournal = cls(
            path, _Checkpoint(CHECKPOINT_VERSION, plan, run_root, tuple(_proof(item) for item in sorted(inputs)))
        )
        journal._save(journal._checkpoint)
        return journal

    @classmethod
    def load(cls, path: Path) -> RunJournal:
        """Reconcile an interrupted rename and reject changed or missing saved inputs."""
        revision: tuple[int, int, int, int] = _revision(path)
        checkpoint: _Checkpoint = TypeAdapter(_Checkpoint).validate_json(path.read_bytes(), strict=True)
        if checkpoint.version != CHECKPOINT_VERSION:
            msg = "The saved run checkpoint has an unsupported version"
            raise ExecutionError(msg)
        journal: RunJournal = cls(path, checkpoint)
        journal._revision = revision
        journal._reconcile_publication()
        journal.validate_inputs()
        journal.validate_outputs()
        if not journal.is_current():
            msg = "The saved run checkpoint changed during validation"
            raise ExecutionError(msg)
        return journal

    def validate_outputs(self) -> None:
        """Reject changed required output proofs without rereading the saved graph."""
        required_outputs: set[str] = {
            artifact.artifact_id
            for artifact in self.plan.artifacts
            if self.plan.tasks or artifact.lifetime is ArtifactLifetime.DURABLE
        }
        for output in self._checkpoint.outputs:
            if output.artifact_id not in required_outputs:
                continue
            if _proof(output.path, output.artifact_id) != output:
                msg = "A saved run output changed or is missing"
                raise ExecutionError(msg)

    def validate_inputs(self, group_id: str | None = None) -> None:
        """Reject changed inputs in the selected group or the complete saved run."""
        self._require_writable()
        paths: set[Path] = {
            path
            for artifact in self.plan.artifacts
            if group_id is None or artifact.group_id == group_id
            for path in (artifact.path, artifact.preserved_path)
            if path is not None
        }
        if any(_proof(item.path) != item for item in self._checkpoint.inputs if group_id is None or item.path in paths):
            msg = "An input or preserved product changed after the run was accepted"
            raise ExecutionError(msg)

    @classmethod
    def relocate(cls, path: Path, move: ReadyMove, workspace: Path) -> bool:
        """Rebind a completed group's checkpoint only after every renamed proof retains its file identity."""
        checkpoint: _Checkpoint = TypeAdapter(_Checkpoint).validate_json(path.read_bytes(), strict=True)
        if checkpoint.version != CHECKPOINT_VERSION:
            msg: str = "The saved run checkpoint has an unsupported version"
            raise ExecutionError(msg)
        group_ids: frozenset[str] = frozenset({move.group_id, move.destination_group_id})
        completed: bool = any(
            group.group_id in group_ids
            and not group.task_ids
            and not any(problem.is_blocking for problem in group.problems)
            for group in checkpoint.plan.groups
        )
        if not completed:
            return False
        paths: dict[Path | None, Path | None] = {
            workspace / item.source: workspace / item.destination for item in move.moved
        }
        inputs: tuple[_FileProof, ...] = tuple(_relocated_proof(item, paths) for item in checkpoint.inputs)
        outputs: tuple[_FileProof, ...] = tuple(_relocated_proof(item, paths) for item in checkpoint.outputs)
        plan: ExecutionPlan = replace(
            checkpoint.plan,
            groups=tuple(
                replace(
                    group,
                    group_id=move.destination_group_id,
                    intent=replace(group.intent, group_id=move.destination_group_id),
                    problems=tuple(
                        replace(problem, group_id=move.destination_group_id)
                        if problem.group_id == move.group_id
                        else problem
                        for problem in group.problems
                    ),
                )
                if group.group_id == move.group_id
                else group
                for group in checkpoint.plan.groups
            ),
            artifacts=tuple(
                replace(
                    artifact,
                    group_id=move.destination_group_id if artifact.group_id == move.group_id else artifact.group_id,
                    path=paths.get(artifact.path, artifact.path),
                    planned_destination=paths.get(artifact.planned_destination, artifact.planned_destination),
                    preserved_path=paths.get(artifact.preserved_path, artifact.preserved_path),
                )
                for artifact in checkpoint.plan.artifacts
            ),
            problems=tuple(
                replace(problem, group_id=move.destination_group_id) if problem.group_id == move.group_id else problem
                for problem in checkpoint.plan.problems
            ),
        )
        updated: _Checkpoint = replace(checkpoint, plan=plan, inputs=inputs, outputs=outputs)
        if updated != checkpoint:
            cls(path, checkpoint)._save(updated)
        return True

    def prepare(self, task: PlanTask, result: TaskResult) -> None:
        """Record a validated staging file before the coordinator can replace its destination."""
        self._require_writable()
        self._reconcile_publication()
        artifacts: dict[str, Artifact] = {artifact.artifact_id: artifact for artifact in self.plan.artifacts}
        if not any(artifacts[artifact_id].lifetime is ArtifactLifetime.DURABLE for artifact_id in task.produces):
            return
        if self._checkpoint.pending == result:
            return
        if result.absent_outputs and not result.outputs:
            return
        if len(result.outputs) != 1 or result.outputs[0].metadata.get("validated") is not True:
            msg = "Publication recovery requires exactly one validated staged product"
            raise ExecutionError(msg)
        if result.task_id != task.task_id or tuple(output.artifact_id for output in result.outputs) != task.produces:
            msg = "Publication outputs do not match the saved task"
            raise ExecutionError(msg)
        if not result.outputs[0].path.resolve().is_relative_to((self._checkpoint.run_root / task.group_id).resolve()):
            msg = "Publication staging escaped its run group"
            raise ExecutionError(msg)
        self._save(replace(self._checkpoint, pending=result, staged=_proof(result.outputs[0].path)))

    def committed(self, result: TaskResult) -> None:
        """Remove completed work from the persisted graph while retaining its files."""
        self._require_writable()
        try:
            self._save(_completed(self._checkpoint, result))
        except AniShiftError, OSError, ValueError:
            self._failed = True
            raise

    def persist(self) -> None:
        """Persist reconciled publication proof before accepting a resumed run."""
        self._require_writable()
        self._save(self._checkpoint)

    def _reconcile_publication(self) -> None:
        pending: TaskResult | None = self._checkpoint.pending
        staged: _FileProof | None = self._checkpoint.staged
        if pending is None or staged is None or staged.path.exists():
            return
        output: ProducedArtifact = pending.outputs[0]
        artifact: Artifact = next(item for item in self.plan.artifacts if item.artifact_id == output.artifact_id)
        destination: Path | None = artifact.planned_destination
        if destination is None or not staged.inode or _proof(destination) != replace(staged, path=destination):
            msg = "An interrupted publication has no conclusive file identity"
            raise ExecutionError(msg)
        published: ProducedArtifact = replace(output, path=destination, metadata={**output.metadata, "published": True})
        self._checkpoint = _completed(self._checkpoint, TaskResult(pending.task_id, (published,)))

    def _save(self, checkpoint: _Checkpoint) -> None:
        data: bytes = TypeAdapter(_Checkpoint).dump_json(checkpoint, fallback=dict, warnings=False)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = self._path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self._path)
        except OSError:
            self._failed = True
            raise
        finally:
            temporary.unlink(missing_ok=True)
        self._checkpoint = checkpoint
        self._revision = _revision(self._path)

    def _require_writable(self) -> None:
        if self._failed:
            msg = "The run checkpoint could not be saved; reload it before resuming"
            raise ExecutionError(msg)


def _proof(path: Path, artifact_id: str | None = None) -> _FileProof:
    stat: os.stat_result = path.stat()
    if not path.is_file() or path.is_symlink():
        msg = "A run checkpoint requires a regular file"
        raise ExecutionError(msg)
    return _FileProof(path, stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino, artifact_id)


def _revision(path: Path) -> tuple[int, int, int, int]:
    stat: os.stat_result = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino


def _relocated_proof(proof: _FileProof, paths: dict[Path | None, Path | None]) -> _FileProof:
    destination: Path | None = paths.get(proof.path)
    if destination is None:
        return proof
    updated: _FileProof = replace(proof, path=destination)
    if _proof(destination, proof.artifact_id) != updated:
        msg: str = "A relocated checkpoint file changed; its original proof was preserved"
        raise ExecutionError(msg)
    return updated


def _completed(checkpoint: _Checkpoint, result: TaskResult) -> _Checkpoint:
    paths: frozenset[Path] = frozenset(output.path for output in result.outputs)
    outputs: tuple[_FileProof, ...] = tuple(item for item in checkpoint.outputs if item.path not in paths)
    return replace(
        checkpoint,
        plan=_remaining(checkpoint.plan, result),
        inputs=tuple(item for item in checkpoint.inputs if item.path not in paths),
        outputs=(*outputs, *(_proof(output.path, output.artifact_id) for output in result.outputs)),
        pending=None,
        staged=None,
        inflight=checkpoint.inflight - {result.task_id},
    )


def _remaining(plan: ExecutionPlan, result: TaskResult) -> ExecutionPlan:
    produced: dict[str, ProducedArtifact] = {output.artifact_id: output for output in result.outputs}
    artifacts: list[Artifact] = []
    for artifact in plan.artifacts:
        if artifact.artifact_id in result.absent_outputs:
            artifacts.append(replace(artifact, path=None, state=ArtifactState.ABSENT))
            continue
        output: ProducedArtifact | None = produced.get(artifact.artifact_id)
        artifacts.append(
            replace(
                artifact,
                path=output.path,
                state=ArtifactState.READY,
                preserved_path=None,
            )
            if output is not None
            else artifact
        )
    return replace(
        plan,
        artifacts=tuple(artifacts),
        tasks=tuple(
            replace(
                task, depends_on=tuple(identifier for identifier in task.depends_on if identifier != result.task_id)
            )
            for task in plan.tasks
            if task.task_id != result.task_id
        ),
        groups=tuple(
            replace(group, task_ids=tuple(identifier for identifier in group.task_ids if identifier != result.task_id))
            for group in plan.groups
        ),
    )
