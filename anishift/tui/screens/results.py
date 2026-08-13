"""Terminal run results and product navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Label, Select, Static

from anishift.application.results import GroupResult, GroupStatus
from anishift.tui.state import GroupIntentDraft
from anishift.tui.widgets import CommandBar, StatusFooter

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class ResultsScreen(Screen[None]):
    """Render immutable run results without reclassifying backend outcomes."""

    def compose(self) -> ComposeResult:
        """Compose filters, group outcomes, products, and manual recovery."""
        filter_options: tuple[tuple[str, str | GroupStatus], ...] = (
            ("All", "all"),
            ("Done", "done"),
            *((item.value, item) for item in GroupStatus),
        )
        with Vertical(classes="route-content"):
            yield Label("Results", classes="route-title")
            yield Select(
                filter_options,
                value="all",
                allow_blank=False,
                id="results-filter",
            )
            yield DataTable(id="results-groups", zebra_stripes=True, cursor_type="row")
            yield Static("", id="result-details")
            with Horizontal(classes="screen-actions"):
                yield Button("Open in Manual", id="result-manual")
                yield Button("Workspace", id="result-workspace")
            yield Static("", id="results-warnings")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    def on_mount(self) -> None:
        """Build stable result columns and render the current run result."""
        table = self.query_one("#results-groups", DataTable)
        table.add_columns("Group", "Status", "Products", "Errors")
        self._render_results("all")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Filter terminal statuses without creating another API state."""
        if event.select.id == "results-filter":
            value: object = event.value
            self._render_results(value.value if isinstance(value, GroupStatus) else str(value))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show products and sanitized errors for the highlighted group."""
        if event.data_table.id != "results-groups" or event.row_key.value is None:
            return
        result = self._result_by_id(str(event.row_key.value))
        if result is None:
            return
        products: str = "\n".join(str(product.path) for product in result.products) or "No new products"
        preserved: str = "\n".join(str(product.path) for product in result.preserved_products) or "None"
        errors: str = "\n".join(result.error_messages)
        self.query_one("#result-details", Static).update(
            f"Products:\n{products}\nPreserved products:\n{preserved}\nErrors:\n{errors}"
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Return to Workspace or prepare one failed/partial group for Manual."""
        if event.button.id == "result-workspace":
            await self._shell.open_route("workspace")
            return
        if event.button.id != "result-manual":
            return
        table = self.query_one("#results-groups", DataTable)
        if table.row_count == 0:
            return
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        if row_key is None:
            return
        group_id: str = str(row_key)
        result = self._result_by_id(group_id)
        if result is None or result.status is GroupStatus.SUCCEEDED:
            return
        preview_groups = self._shell.session.preview_plan.groups if self._shell.session.preview_plan else ()
        group_plan = next((group for group in preview_groups if group.group_id == group_id), None)
        if group_plan is not None:
            self._shell.session.manual_drafts[group_id] = GroupIntentDraft.from_intent(group_plan.intent)
        self._shell.session.selected_group_ids = {group_id}
        await self._shell.open_route("manual")

    def _render_results(self, status_filter: str) -> None:
        result = self._shell.session.run_result
        table = self.query_one("#results-groups", DataTable)
        table.clear()
        if result is None:
            message: str = self._shell.session.run_error or "No run result is available"
            self.query_one("#result-details", Static).update(message)
            return
        for group in result.groups:
            if status_filter not in {"all", "done", group.status.value}:
                continue
            table.add_row(
                group.group_id,
                group.status.value,
                str(len(group.products)),
                str(len(group.error_messages)),
                key=group.group_id,
            )
        self.query_one("#results-warnings", Static).update("\n".join(result.warnings))

    def _result_by_id(self, group_id: str) -> GroupResult | None:
        result = self._shell.session.run_result
        if result is None:
            return None
        return next((group for group in result.groups if group.group_id == group_id), None)
