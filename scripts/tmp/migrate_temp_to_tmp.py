"""Move the owner's workspace staging from temp to tmp once, with the resident stopped."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter

from anishift.application.recovery import RunJournal, _Checkpoint
from anishift.application.watch_state import WatchStateStore
from anishift.bootstrap import bootstrap
from anishift.cli.watch import RESIDENT_LOCK_FILE_NAME
from anishift.config.workspace import run_tmp_dir
from anishift.errors import AniShiftError
from anishift.paths import TMP_DIRECTORY, run_journal_dir, watch_dir
from anishift.platform.process_lock import ProcessLock

# ── Constants ─────────────────────────────────────────────────────────────────

OLD_NAME: Final[str] = "temp"
"""Name of the staging directory this script retires."""

OLD_PREFIX: Final[str] = f"{OLD_NAME}/"
"""Workspace-relative beginning of every stored staging path this script rewrites."""

BACKUP_SUFFIX: Final[str] = ".temp-to-tmp.bak"
"""Ending of the copies kept of the state and of the run checkpoints before any change."""

PLACEHOLDER: Final[str] = ".gitkeep"
"""Tracked file that may already sit alone in a freshly checked out staging directory."""

CHECKPOINTS: Final[TypeAdapter[_Checkpoint]] = TypeAdapter(_Checkpoint)
"""Reader and writer of one run checkpoint in the product's own format."""


class MigrationError(Exception):
    """Refusal or failure that leaves the owner's files as they were."""


@dataclass
class Plan:
    """Every change one migration would make, counted before anything is written."""

    state: dict[str, object] | None = None
    acquisitions: int = 0
    restores: int = 0
    journals: dict[Path, bytes] = field(default_factory=dict)
    journal_fields: int = 0
    move: bool = False
    placeholder: bool = False
    created: bool = False

    @property
    def empty(self) -> bool:
        """Whether the files already use the new staging name."""
        return self.state is None and not self.journals and not self.move


def main() -> int:
    """Run the migration on the given watch directory and workspace, answering the process exit code."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    watch: Path = watch_dir()
    workspace: Path = bootstrap(create_dirs=False).workspace_root
    if not (watch / "state.json").is_file() or not workspace.is_dir():
        print("Refused: the resident state or the workspace is not where the resident reads it.", file=sys.stderr)
        return 1
    lock: ProcessLock = ProcessLock(watch / RESIDENT_LOCK_FILE_NAME)
    if not lock.acquire():
        print("Refused: the resident is running; close AniShift first.", file=sys.stderr)
        return 1
    try:
        migrate(watch, workspace)
    except MigrationError as problem:
        print(f"Refused or rolled back: {problem}", file=sys.stderr)
        return 1
    finally:
        lock.release()
    return 0


def migrate(watch: Path, workspace: Path) -> None:
    """Back up, move the directory, rewrite stored paths, verify, and restore everything on any failure."""
    plan: Plan = _plan(watch, workspace)
    if plan.empty:
        print("Nothing to migrate: the staging directory and every stored path already use tmp.")
        return
    before: dict[Path, str] = _journal_loads(tuple(sorted(run_journal_dir(watch).glob("*.json"))))
    _back_up(watch)
    try:
        _apply(plan, watch, workspace)
        _verify(watch, workspace, before)
    except BaseException as problem:
        _restore(plan, watch, workspace)
        if not isinstance(problem, Exception):
            raise
        raise MigrationError(f"{type(problem).__name__}: {problem}") from problem
    print(f"Directory moved: {'yes' if plan.move else 'no'} (placeholder replaced: {plan.placeholder})")
    print(f"State fields rewritten: acquisitions[].directory={plan.acquisitions}, restore staging={plan.restores}")
    print(f"Run checkpoints rewritten: files={len(plan.journals)}, path fields={plan.journal_fields}")
    print(f"Backups: state.json{BACKUP_SUFFIX}, runs{BACKUP_SUFFIX}/")


def _plan(watch: Path, workspace: Path) -> Plan:
    plan: Plan = Plan()
    state_path: Path = watch / "state.json"
    if state_path.is_file():
        document: dict[str, object] = json.loads(state_path.read_text(encoding="utf-8"))
        plan.acquisitions, plan.restores = _rewrite_state(document)
        if plan.acquisitions or plan.restores:
            plan.state = document
        stray: list[str] = _old_paths(document)
        if stray:
            raise MigrationError(f"{len(stray)} other state fields name temp/, first {stray[0]}")
    for path in sorted(run_journal_dir(watch).glob("*.json")):
        rewritten: tuple[bytes, int] | None = _rewrite_journal(path, workspace)
        if rewritten is not None:
            plan.journals[path] = rewritten[0]
            plan.journal_fields += rewritten[1]
    old: Path = workspace / OLD_NAME
    current: Path = workspace / TMP_DIRECTORY
    if old.exists():
        if not old.is_dir() or old.is_symlink() or old.is_junction():
            raise MigrationError("workspace/temp is not a plain directory")
        leftovers: list[str] = sorted(item.name for item in current.iterdir()) if current.exists() else []
        if leftovers not in ([], [PLACEHOLDER]):
            raise MigrationError(f"workspace/tmp already holds {len(leftovers)} entries, first {leftovers[0]}")
        plan.move = True
        plan.placeholder = leftovers == [PLACEHOLDER]
    return plan


def _rewrite_state(document: dict[str, object]) -> tuple[int, int]:
    acquisitions: int = 0
    for item in _items(document.get("acquisitions")):
        acquisitions += _rename(item, "directory")
    restores: int = 0
    for deletion in _items(document.get("pending_deletions")):
        restore: object = deletion.get("restore")
        if isinstance(restore, dict):
            for outcome in _items(restore.get("outcomes")):
                restores += _rename(outcome, "staging")
    return acquisitions, restores


def _items(value: object) -> list[dict[str, object]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _rename(item: dict[str, object], key: str) -> int:
    value: object = item.get(key)
    if not isinstance(value, str) or not value.startswith(OLD_PREFIX):
        return 0
    item[key] = f"{TMP_DIRECTORY}/{value.removeprefix(OLD_PREFIX)}"
    return 1


def _old_paths(value: object, place: str = "") -> list[str]:
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in _old_paths(item, f"{place}.{key}")]
    if isinstance(value, list):
        return [found for item in value for found in _old_paths(item, f"{place}[]")]
    return [place] if isinstance(value, str) and value.startswith(OLD_PREFIX) else []


def _rewrite_journal(path: Path, workspace: Path) -> tuple[bytes, int] | None:
    document: object = json.loads(path.read_bytes())
    old: Path = (workspace / OLD_NAME).resolve()
    current: Path = workspace / TMP_DIRECTORY
    count: list[int] = [0]

    def moved(value: object) -> object:
        if isinstance(value, dict):
            return {key: moved(item) for key, item in value.items()}
        if isinstance(value, list):
            return [moved(item) for item in value]
        if isinstance(value, str) and Path(value).is_absolute() and Path(value).resolve().is_relative_to(old):
            count[0] += 1
            return str(current / Path(value).resolve().relative_to(old))
        return value

    rewritten: object = moved(document)
    if not count[0]:
        return None
    checkpoint: _Checkpoint = CHECKPOINTS.validate_python(rewritten)
    return CHECKPOINTS.dump_json(checkpoint, fallback=dict, warnings=False), count[0]


def _journal_loads(paths: tuple[Path, ...]) -> dict[Path, str]:
    outcomes: dict[Path, str] = {}
    for path in paths:
        try:
            RunJournal.load(path)
        except (AniShiftError, OSError, ValueError) as problem:
            outcomes[path] = type(problem).__name__
        else:
            outcomes[path] = "loaded"
    return outcomes


def _back_up(watch: Path) -> None:
    state: Path = watch / "state.json"
    state_copy: Path = watch / f"state.json{BACKUP_SUFFIX}"
    runs: Path = run_journal_dir(watch)
    runs_copy: Path = watch / f"runs{BACKUP_SUFFIX}"
    if state_copy.exists() or runs_copy.exists():
        raise MigrationError(f"a backup from an earlier attempt exists; inspect *{BACKUP_SUFFIX} before retrying")
    if state.is_file():
        shutil.copy2(state, state_copy)
    if runs.is_dir():
        shutil.copytree(runs, runs_copy)


def _apply(plan: Plan, watch: Path, workspace: Path) -> None:
    for path, content in plan.journals.items():
        _write(path, content)
    if plan.move:
        current: Path = workspace / TMP_DIRECTORY
        if plan.placeholder:
            (current / PLACEHOLDER).unlink()
        if current.exists():
            current.rmdir()
        (workspace / OLD_NAME).rename(current)
        if plan.placeholder and not (current / PLACEHOLDER).exists():
            (current / PLACEHOLDER).write_bytes(b"")
            plan.created = True
    if plan.state is not None:
        _write(watch / "state.json", (json.dumps(plan.state, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def _write(path: Path, content: bytes) -> None:
    temporary: Path = path.with_name(f"{path.name}.migrating")
    temporary.write_bytes(content)
    temporary.replace(path)


def _verify(watch: Path, workspace: Path, before: dict[Path, str]) -> None:
    state: Path = watch / "state.json"
    if state.is_file():
        WatchStateStore(state).load()
        if _old_paths(json.loads(state.read_text(encoding="utf-8"))):
            raise MigrationError("the state still names temp/")
    lost: list[str] = []
    old: Path = (workspace / OLD_NAME).resolve()
    for path, outcome in _journal_loads(tuple(before)).items():
        checkpoint: _Checkpoint = CHECKPOINTS.validate_json(path.read_bytes(), strict=True)
        if checkpoint.run_root.resolve().is_relative_to(old) or checkpoint.run_root.parent.name == OLD_NAME:
            raise MigrationError(f"checkpoint {path.name} still points at the temp staging directory")
        if checkpoint.run_root != run_tmp_dir(workspace, path.stem):
            raise MigrationError(f"checkpoint {path.name} does not point at its tmp run directory")
        if before[path] == "loaded" and outcome != "loaded":
            lost.append(path.name)
    if lost:
        raise MigrationError(f"{len(lost)} checkpoints loaded before the move and not after, first {lost[0]}")
    loaded: int = sum(outcome == "loaded" for outcome in before.values())
    print(f"Verified: state loads; {len(before)} checkpoints parse with tmp run roots; {loaded} that loaded still load")


def _restore(plan: Plan, watch: Path, workspace: Path) -> None:
    current: Path = workspace / TMP_DIRECTORY
    if plan.move and current.exists() and not (workspace / OLD_NAME).exists():
        if plan.created:
            (current / PLACEHOLDER).unlink()
        current.rename(workspace / OLD_NAME)
        if plan.placeholder:
            current.mkdir()
            (current / PLACEHOLDER).write_bytes(b"")
    state_copy: Path = watch / f"state.json{BACKUP_SUFFIX}"
    if state_copy.is_file():
        shutil.copy2(state_copy, watch / "state.json")
    runs_copy: Path = watch / f"runs{BACKUP_SUFFIX}"
    if runs_copy.is_dir():
        shutil.rmtree(run_journal_dir(watch))
        shutil.copytree(runs_copy, run_journal_dir(watch))


if __name__ == "__main__":
    sys.exit(main())
