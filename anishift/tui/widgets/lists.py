"""The one row-list behaviour every AniShift list shares: a pointer cursor that never scrolls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import OptionList

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.content import Content
    from textual.events import MouseMove

__all__ = [
    "HoverList",
    "move_highlight",
]


def move_highlight(
    listing: OptionList,
    index: int | None,
    prompt: Callable[[int, bool], Content] | None = None,
    /,
) -> None:
    """Rest the one highlight of *listing* on *index*, repainting only the two rows that change.

    Replacing every option would reset the scroll to the top, so a cursor move never
    does that; the view then only ever moves for a row that is really off screen.
    """
    if prompt is not None:
        _repaint_row(listing, listing.highlighted, prompt, selected=False)
        _repaint_row(listing, index, prompt, selected=True)
    listing.highlighted = index
    listing.scroll_to_highlight()


def _repaint_row(
    listing: OptionList,
    index: int | None,
    prompt: Callable[[int, bool], Content],
    *,
    selected: bool,
) -> None:
    """Re-render row *index* of *listing*, skipping a row the list does not hold."""
    if index is None or not 0 <= index < listing.option_count:
        return
    listing.replace_option_prompt_at_index(index, prompt(index, selected))


class HoverList(OptionList):
    """Row list whose one highlight follows the pointer as it moves over the rows."""

    def __init__(self, hover: Callable[[int], None], *, widget_id: str) -> None:
        """Report the row the pointer rests on through *hover*."""
        super().__init__(id=widget_id, markup=False)
        self._hover: Callable[[int], None] = hover

    def _on_mouse_move(self, event: MouseMove) -> None:
        """Report the pointed row, so the highlight rests where the pointer does."""
        super()._on_mouse_move(event)
        pointed: object = event.style.meta.get("option")
        if isinstance(pointed, int):
            self._hover(pointed)
