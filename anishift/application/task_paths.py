"""Safe task-owned staging paths shared by application handlers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from anishift.application.artifacts import Artifact
from anishift.application.planning import PlanTask
from anishift.errors import ExecutionError

__all__ = ["task_staging_path"]

# ── Constants ────────────────────────────────────────────────────────────────

_SAFE_COMPONENT: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
"""Allowed generated identifier syntax for one staging path component."""

_SAFE_SUFFIX: Final[re.Pattern[str]] = re.compile(r"\.[A-Za-z0-9]+\Z")
"""Allowed single-extension syntax for a staging output."""


def task_staging_path(run_root: Path, task: PlanTask, output: Artifact, suffix: str) -> Path:
    """Return one output path inside the exact run/group scope."""
    if _SAFE_COMPONENT.fullmatch(task.group_id) is None or _SAFE_COMPONENT.fullmatch(output.artifact_id) is None:
        msg = "Task and artifact IDs must be safe staging path components"
        raise ExecutionError(msg)
    if _SAFE_SUFFIX.fullmatch(suffix) is None:
        msg = "Task staging suffix must be one safe extension"
        raise ExecutionError(msg)
    group_root: Path = run_root / task.group_id
    group_root.mkdir(parents=True, exist_ok=True)
    return group_root / f"{output.artifact_id}{suffix}"
