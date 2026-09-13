"""The one rule deciding which execution target a workspace place stands for."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.paths import (
    AUDIOBOOK_DIRECTORY,
    COVER_DIRECTORY,
    READY_DIRECTORY,
    SUBS_DIRECTORY,
    TEMP_DIRECTORY,
    TRANSLATE_DIRECTORY,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ROOT_ROUTE",
    "WorkflowRoute",
    "WorkflowTarget",
    "WorkspacePlace",
    "resolve_route",
    "route_within",
]


class WorkflowTarget(StrEnum):
    """Closed set of execution targets one complete input set can be planned for."""

    VIDEO = "video"
    TRANSLATE = "translate"
    AUDIOBOOK = "audiobook"
    COVER = "cover"


class WorkspacePlace(StrEnum):
    """Place a workspace-relative path belongs to, named by its first segment."""

    ROOT = "root"
    SUBS = "subs"
    TRANSLATE = "translate"
    AUDIOBOOK = "audiobook"
    COVER = "cover"
    READY = "ready"
    TEMP = "temp"
    HIDDEN = "hidden"
    OUTSIDE = "outside"


@dataclass(frozen=True, slots=True)
class WorkflowRoute:
    """Place of one input, the target it may be planned for, and its sidecar duty."""

    place: WorkspacePlace
    target: WorkflowTarget | None
    requires_sidecar: bool = False

    @property
    def starts_automatic_work(self) -> bool:
        """Whether an input in this place can become automatic work by itself."""
        return self.target is not None


# ── Constants ──────────────────────────────────────────────────────────────

ROOT_ROUTE: Final[WorkflowRoute] = WorkflowRoute(WorkspacePlace.ROOT, WorkflowTarget.VIDEO)
"""Plain video work directly in the workspace, and the compatible route of every older group."""

_OUTSIDE_ROUTE: Final[WorkflowRoute] = WorkflowRoute(WorkspacePlace.OUTSIDE, None)
"""Anything leaving the workspace tree, which automatic work never takes."""

_HIDDEN_ROUTE: Final[WorkflowRoute] = WorkflowRoute(WorkspacePlace.HIDDEN, None)
"""Data hidden by a leading dot, which automatic work never takes."""

_TRAILING_NOISE: Final[str] = ". "
"""Characters Windows strips from the end of a path segment before it opens the name."""

_RESERVED_ROUTES: Final[Mapping[str, WorkflowRoute]] = MappingProxyType(
    {
        SUBS_DIRECTORY: WorkflowRoute(WorkspacePlace.SUBS, WorkflowTarget.VIDEO, requires_sidecar=True),
        TRANSLATE_DIRECTORY: WorkflowRoute(WorkspacePlace.TRANSLATE, WorkflowTarget.TRANSLATE),
        AUDIOBOOK_DIRECTORY: WorkflowRoute(WorkspacePlace.AUDIOBOOK, WorkflowTarget.AUDIOBOOK),
        COVER_DIRECTORY: WorkflowRoute(WorkspacePlace.COVER, WorkflowTarget.COVER),
        READY_DIRECTORY: WorkflowRoute(WorkspacePlace.READY, None),
        TEMP_DIRECTORY: WorkflowRoute(WorkspacePlace.TEMP, None),
    }
)
"""Every reserved first segment of a workspace-relative path, matched without case."""


def resolve_route(relative_path: Path) -> WorkflowRoute:
    """Resolve the route of one workspace-relative path, deciding on its first segment alone."""
    if relative_path.drive or relative_path.root:
        return _OUTSIDE_ROUTE
    parts: tuple[str, ...] = tuple(part for part in relative_path.parts if part not in {"", "."})
    if any(part == ".." for part in parts):
        return _OUTSIDE_ROUTE
    if any(part.startswith(".") for part in parts):
        return _HIDDEN_ROUTE
    if not parts:
        return ROOT_ROUTE
    return _RESERVED_ROUTES.get(_reserved_key(parts[0]), ROOT_ROUTE)


def _reserved_key(segment: str) -> str:
    return segment.rstrip(_TRAILING_NOISE).casefold()


def route_within(workspace_root: Path, resolved_path: Path) -> WorkflowRoute:
    """Route one already resolved path, refusing whatever really lies outside *workspace_root*."""
    if not resolved_path.is_relative_to(workspace_root):
        return _OUTSIDE_ROUTE
    return resolve_route(resolved_path.relative_to(workspace_root))
