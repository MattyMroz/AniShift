"""The gate that lets one empty Enter start at most one Auto request.

Exactly-once is a property of a reservation, never of elapsed time. A debounce
window only hides the second event of an auto-repeat or of a double press, and a
terminal gives no way to recognise a repeated key, so this module refuses the
second submission instead of trying to see it coming.

Reserving means moving the one run lifecycle of the session into ``planning``
through ``lifecycle.begin_planning``, which is the single owner of both the run
state and the generation. ``ALLOWED_RUN_TRANSITIONS`` already refuses to enter
``planning`` from ``planning``, ``running`` or ``cancelling``, so every further
submission finds the gate taken and receives nothing at all. There is no second
flag to keep in step with the run state.

Releasing is keyed on the generation the reservation was taken under: a plan
that failed for an interaction the user already abandoned must never hand the
gate back to the reservation that replaced it.

Public API:
    reserve: Reserve the one generation an empty Enter may start Auto under.
    release: Give the reservation of one generation back after a failed plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from anishift.tui import lifecycle
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from anishift.tui.state import SessionState

__all__ = ["release", "reserve"]

logger = get_logger(__name__)


def reserve(state: SessionState) -> int | None:
    """Reserve the generation an accepted empty Enter starts Auto under.

    Returns the reserved generation, or ``None`` when a start already in flight,
    a running workflow or a cancellation holds the gate.
    """
    generation: int | None = lifecycle.begin_planning(state)
    if generation is None:
        logger.debug("Auto request refused", run_state=state.run_state.value)
        return None
    logger.info("Auto request reserved", generation=generation)
    return generation


def release(state: SessionState, *, generation: int, reason: str) -> bool:
    """Give the reservation of *generation* back, keeping *reason* for the user.

    A release carrying any other generation answers an interaction the session
    already abandoned and changes nothing at all.
    """
    if not lifecycle.accepts_message(state, generation=generation):
        logger.debug("Late Auto release dropped", generation=generation)
        return False
    return lifecycle.abandon_planning(state, reason)
