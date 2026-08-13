"""Selectable, sortable view of inspected source groups."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import DataTable, Input, SelectionList

from anishift.application.artifacts import ArtifactState
from anishift.application.inspection import InspectedSourceGroup


class GroupSelectionChanged(Message):
    """Current stable group IDs selected for planning."""

    def __init__(self, group_ids: frozenset[str]) -> None:
        super().__init__()
        self.group_ids: frozenset[str] = group_ids


class GroupTable(Horizontal):
    """Keep group selection separate from render order and filtering."""

    def __init__(self, selected_ids: set[str]) -> None:
        super().__init__(id="group-table")
        self._groups: tuple[InspectedSourceGroup, ...] = ()
        self._selected_ids: set[str] = set(selected_ids)
        self._visible_ids: set[str] = set()
        self._rendering: bool = False

    def compose(self) -> ComposeResult:
        """Compose the checkbox list, filter field, and artifact summary."""
        yield SelectionList[str](id="group-selection")
        with Horizontal(id="group-detail"):
            yield Input(placeholder="Filter groups", id="group-filter")
            yield DataTable(id="group-artifacts", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        """Initialize stable artifact columns."""
        self.query_one("#group-artifacts", DataTable).add_columns("Group", "Sources", "Embedded", "Conflicts")

    def set_groups(self, groups: tuple[InspectedSourceGroup, ...]) -> None:
        """Replace groups while preserving selection for surviving IDs."""
        self._groups = tuple(sorted(groups, key=lambda item: (item.source.stem.casefold(), item.group_id)))
        surviving: set[str] = {group.group_id for group in self._groups}
        self._selected_ids.intersection_update(surviving)
        if not self._selected_ids:
            self._selected_ids.update(surviving)
        self._render_groups("")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter by source stem without changing the stable selection set."""
        if event.input.id == "group-filter":
            self._render_groups(event.value)

    def on_selection_list_selected_changed(self, _event: SelectionList.SelectedChanged[str]) -> None:
        """Publish selection independently of visible sort order."""
        if self._rendering:
            return
        selection = self.query_one("#group-selection", SelectionList)
        self._selected_ids.difference_update(self._visible_ids)
        self._selected_ids.update(selection.selected)
        self.post_message(GroupSelectionChanged(frozenset(self._selected_ids)))

    def _render_groups(self, filter_text: str) -> None:
        normalized: str = filter_text.strip().casefold()
        visible: tuple[InspectedSourceGroup, ...] = tuple(
            group for group in self._groups if not normalized or normalized in group.source.stem.casefold()
        )
        self._visible_ids = {group.group_id for group in visible}
        selection = self.query_one("#group-selection", SelectionList)
        table = self.query_one("#group-artifacts", DataTable)
        self._rendering = True
        try:
            selection.clear_options()
            table.clear()
            for group in visible:
                selection.add_option((group.source.stem, group.group_id, group.group_id in self._selected_ids))
                source_count: int = sum(artifact.state is ArtifactState.READY for artifact in group.artifacts)
                embedded_count: int = sum(len(catalog.tracks) for catalog in group.media_catalogs.values())
                kinds: str = ", ".join(sorted({artifact.kind.value for artifact in group.artifacts}))
                table.add_row(
                    group.source.stem,
                    f"{source_count}: {kinds}",
                    str(embedded_count),
                    str(len(group.conflicts)),
                )
        finally:
            self._rendering = False
