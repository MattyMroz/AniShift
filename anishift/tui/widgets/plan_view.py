"""Projection of one execution plan into the lines a preview screen renders."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.application import ArtifactLifetime, ArtifactState
from anishift.tui.strings import (
    GLYPH_GAP,
    PLAN_BLOCKED_WORD,
    PLAN_EMPTY,
    PLAN_GROUP_GLYPH,
    PLAN_INDENT,
    PLAN_KEPT_WORD,
    PLAN_NONE,
    PLAN_OPERATION_LABELS,
    PLAN_OPERATIONS_LABEL,
    PLAN_OUTSIDE_WORKSPACE,
    PLAN_PRODUCTS_LABEL,
    PLAN_PROFILE_MODEL_LABEL,
    PLAN_PROFILE_SPEECH_LABEL,
    PLAN_PROFILE_TRANSLATION_LABEL,
    PLAN_PROFILES_LABEL,
    PLAN_REPLACES_WORD,
    PLAN_SOURCES_LABEL,
    PLAN_WARNING_WORD,
    TOOLS_CHECK_FAIL_GLYPH,
    TOOLS_CHECK_WARN_GLYPH,
)

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.application import Artifact, ExecutionPlan, PlanProblem, PlanTask

__all__ = [
    "group_lines",
    "operation_label",
    "operation_lines",
    "plan_body",
    "plan_lines",
    "problem_lines",
    "product_lines",
    "profile_lines",
    "relative_text",
    "source_lines",
]

# ── Constants ──────────────────────────────────────────────────────────────

_FIELD_GAP: Final[str] = "  "
"""Separator between a field label and the value that field carries."""

_ITEM_SEPARATOR: Final[str] = ", "
"""Separator between two items listed on one field line."""


def operation_label(kind: str) -> str:
    """Return the human label of the planned operation named *kind*."""
    return PLAN_OPERATION_LABELS.get(kind, kind)


def relative_text(path: Path | None, root: Path | None) -> str:
    """Return *path* relative to *root*, never revealing a location above it."""
    if path is None:
        return PLAN_NONE
    if root is None:
        return path.name
    try:
        return str(path.relative_to(root))
    except ValueError:
        return PLAN_OUTSIDE_WORKSPACE


def source_lines(plan: ExecutionPlan, group_id: str, *, root: Path | None) -> tuple[str, ...]:
    """Return the one line naming every source the group *group_id* reads."""
    sources: tuple[Artifact, ...] = tuple(
        artifact
        for artifact in plan.artifacts
        if artifact.group_id == group_id and artifact.lifetime is ArtifactLifetime.SOURCE
    )
    if not sources:
        return ()
    listed: str = _ITEM_SEPARATOR.join(relative_text(artifact.path, root) for artifact in sources)
    return (_field(PLAN_SOURCES_LABEL, listed),)


def operation_lines(plan: ExecutionPlan, group_id: str) -> tuple[str, ...]:
    """Return the one line naming every planned operation, in execution order."""
    tasks: tuple[PlanTask, ...] = tuple(task for task in plan.tasks if task.group_id == group_id)
    if not tasks:
        return ()
    listed: str = _ITEM_SEPARATOR.join(operation_label(str(task.kind)) for task in tasks)
    return (_field(PLAN_OPERATIONS_LABEL, listed),)


def product_lines(plan: ExecutionPlan, group_id: str, *, root: Path | None) -> tuple[str, ...]:
    """Return one line per durable product, with its destination and what it replaces."""
    products: tuple[Artifact, ...] = tuple(
        artifact
        for artifact in plan.artifacts
        if artifact.group_id == group_id and artifact.lifetime is ArtifactLifetime.DURABLE
    )
    if not products:
        return (_field(PLAN_PRODUCTS_LABEL, PLAN_NONE),)
    return (_field(PLAN_PRODUCTS_LABEL, ""), *(_product_line(product, root) for product in products))


def problem_lines(plan: ExecutionPlan, group_id: str | None) -> tuple[str, ...]:
    """Return one line per problem of *group_id*, each carrying a glyph and a word."""
    problems: tuple[PlanProblem, ...] = tuple(
        problem for problem in _problems_of(plan, group_id) if problem.group_id == group_id
    )
    return tuple(_problem_line(problem) for problem in problems)


def profile_lines(plan: ExecutionPlan) -> tuple[str, ...]:
    """Return the lines naming the engines and the models this plan would use."""
    settings = plan.settings
    listed: tuple[tuple[str, str], ...] = (
        (PLAN_PROFILE_TRANSLATION_LABEL, settings.translation_profile_id),
        (PLAN_PROFILE_MODEL_LABEL, settings.llm_profile_id),
        (PLAN_PROFILE_SPEECH_LABEL, settings.tts_profile_id),
    )
    return (PLAN_PROFILES_LABEL, *(_indented(_field(label, value)) for label, value in listed))


def group_lines(plan: ExecutionPlan, group_id: str, *, root: Path | None) -> tuple[str, ...]:
    """Return every line one group of *plan* contributes to the preview."""
    heading: str = f"{PLAN_GROUP_GLYPH}{GLYPH_GAP}{group_id}"
    body: tuple[str, ...] = (
        *source_lines(plan, group_id, root=root),
        *operation_lines(plan, group_id),
        *product_lines(plan, group_id, root=root),
        *problem_lines(plan, group_id),
    )
    return (heading, *(_indented(line) for line in body))


def plan_lines(plan: ExecutionPlan | None, *, root: Path | None = None) -> tuple[str, ...]:
    """Return every line the preview renders for *plan*, group by group."""
    if plan is None or not plan.groups:
        return (PLAN_EMPTY,)
    grouped: tuple[str, ...] = tuple(
        line for group in plan.groups for line in group_lines(plan, group.group_id, root=root)
    )
    return (*grouped, *problem_lines(plan, None), *profile_lines(plan))


def plan_body(plan: ExecutionPlan | None, *, root: Path | None = None) -> str:
    """Return the rendered text of *plan* as one preview body."""
    return "\n".join(plan_lines(plan, root=root))


def _problems_of(plan: ExecutionPlan, group_id: str | None) -> tuple[PlanProblem, ...]:
    """Return the problems of one group, or the plan-wide problems when *group_id* is none."""
    if group_id is None:
        return plan.problems
    group = next((candidate for candidate in plan.groups if candidate.group_id == group_id), None)
    return () if group is None else group.problems


def _problem_line(problem: PlanProblem) -> str:
    """Return the line of one problem, marked by a glyph and by a word."""
    glyph: str = TOOLS_CHECK_FAIL_GLYPH if problem.is_blocking else TOOLS_CHECK_WARN_GLYPH
    word: str = PLAN_BLOCKED_WORD if problem.is_blocking else PLAN_WARNING_WORD
    return f"{glyph}{GLYPH_GAP}{word}{_FIELD_GAP}{problem.message}"


def _product_line(product: Artifact, root: Path | None) -> str:
    """Return the line of one durable product and of the product it would replace."""
    destination: str = relative_text(product.planned_destination, root)
    if product.preserved_path is not None:
        return _indented(f"{destination}{_FIELD_GAP}{PLAN_REPLACES_WORD}")
    if product.state is ArtifactState.READY:
        return _indented(f"{destination}{_FIELD_GAP}{PLAN_KEPT_WORD}")
    return _indented(destination)


def _field(label: str, value: str) -> str:
    """Return one label and the value it carries, as one line."""
    return f"{label}{_FIELD_GAP}{value}".rstrip()


def _indented(line: str) -> str:
    """Return *line* shifted under the heading that owns it."""
    return f"{PLAN_INDENT}{line}"
