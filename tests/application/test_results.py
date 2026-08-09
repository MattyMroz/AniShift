from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from anishift.application.results import (
    GroupResult,
    GroupStatus,
    ProducedArtifact,
    RunResult,
    TaskResult,
)


def _product(artifact_id: str = "full-pl") -> ProducedArtifact:
    return ProducedArtifact(
        artifact_id=artifact_id,
        path=Path(f"workspace/{artifact_id}.ass"),
        metadata={"published": True},
    )


def test_partial_group_result_preserves_completed_products() -> None:
    product = _product()
    task_result = TaskResult(task_id="publish-full", outputs=(product,))
    group = GroupResult(
        group_id="group-1",
        status=GroupStatus.PARTIAL,
        task_results=(task_result,),
        products=(product,),
        error_messages=("MP4 composition failed",),
    )
    run = RunResult(run_id="run-1", groups=(group,))

    assert run.succeeded is False
    assert run.cancelled is False
    assert run.groups[0].products == (product,)
    with pytest.raises(FrozenInstanceError):
        group.status = GroupStatus.SUCCEEDED  # type: ignore[misc]


def test_successful_run_is_derived_from_group_statuses() -> None:
    first = GroupResult(group_id="group-1", status=GroupStatus.SUCCEEDED, products=(_product("first"),))
    second = GroupResult(group_id="group-2", status=GroupStatus.SUCCEEDED, products=(_product("second"),))

    result = RunResult(run_id="run-1", groups=(first, second))

    assert result.succeeded is True
    assert result.cancelled is False


def test_cancelled_run_can_preserve_products_completed_before_cancel() -> None:
    group = GroupResult(
        group_id="group-1",
        status=GroupStatus.CANCELLED,
        products=(_product(),),
        error_messages=("Cancelled",),
    )

    result = RunResult(run_id="run-1", groups=(group,))

    assert result.cancelled is True
    assert result.groups[0].products


def test_partial_and_failed_statuses_are_not_interchangeable() -> None:
    with pytest.raises(ValueError, match="Partial"):
        GroupResult(group_id="group-1", status=GroupStatus.PARTIAL)
    with pytest.raises(ValueError, match="partial"):
        GroupResult(group_id="group-1", status=GroupStatus.FAILED, products=(_product(),))
    with pytest.raises(ValueError, match="requires at least one error"):
        GroupResult(group_id="group-1", status=GroupStatus.FAILED)


def test_group_errors_are_safe_for_public_results() -> None:
    group = GroupResult(
        group_id="group-1",
        status=GroupStatus.FAILED,
        error_messages=(r'failed C:\Users\name\file.mkv api_key="abc def"',),
    )

    assert "Users" not in group.error_messages[0]
    assert "abc" not in group.error_messages[0]
    assert "def" not in group.error_messages[0]


def test_run_result_rejects_duplicate_groups() -> None:
    group = GroupResult(group_id="group-1", status=GroupStatus.SUCCEEDED)

    with pytest.raises(ValueError, match="unique"):
        RunResult(run_id="run-1", groups=(group, group))
