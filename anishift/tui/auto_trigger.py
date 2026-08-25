"""The reservation gate letting one empty Enter start at most one Auto request."""

from __future__ import annotations

from typing import TYPE_CHECKING

from anishift.tui import lifecycle
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.tui.state import SessionState

__all__ = ["release", "reserve"]

logger = get_logger(__name__)


def reserve(state: SessionState) -> int | None:
    """Reserve the generation for one Auto start, or ``None`` while the gate is held."""
    generation: int | None = lifecycle.begin_planning(state)
    if generation is None:
        logger.debug("Auto request refused", run_state=state.run_state.value)
        return None
    logger.info("Auto request reserved", generation=generation)
    return generation


def release(state: SessionState, *, generation: int, reason: str) -> bool:
    """Give the reservation of the current *generation* back, keeping *reason* for the user."""
    if not lifecycle.accepts_message(state, generation=generation):
        logger.debug("Late Auto release dropped", generation=generation)
        return False
    return lifecycle.abandon_planning(state, reason)
