"""Read-only rendering of an immutable execution plan."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Label, Static

from anishift.application.planning import ExecutionPlan


class PlanView(VerticalScroll):
    """Expose sources, operations, products, cost flags, and problems."""

    def __init__(self, plan: ExecutionPlan) -> None:
        super().__init__(id="plan-view")
        self.plan: ExecutionPlan = plan

    def compose(self) -> ComposeResult:
        """Compose complete planner information without reinterpreting it."""
        network: int = sum(task.is_network for task in self.plan.tasks)
        paid: int = sum(task.is_paid for task in self.plan.tasks)
        required_ids: set[str] = {artifact_id for task in self.plan.tasks for artifact_id in task.requires}
        yield Label("Plan preview", classes="route-title")
        yield Static(f"Groups: {', '.join(group.group_id for group in self.plan.groups)}", id="plan-groups")
        yield Static(
            "Sources: "
            + ", ".join(
                str(artifact.path)
                for artifact in self.plan.artifacts
                if artifact.path is not None and artifact.state.value == "ready"
            ),
            id="plan-sources",
        )
        yield Static(
            "Skipped alternatives: "
            + ", ".join(
                artifact.path.name
                for artifact in self.plan.artifacts
                if artifact.path is not None
                and artifact.state.value == "ready"
                and artifact.artifact_id not in required_ids
            ),
            id="plan-alternatives",
        )
        yield Static(
            "Operations: " + ", ".join(f"{task.kind.value} [{task.resource_key}]" for task in self.plan.tasks),
            id="plan-operations",
        )
        yield Static(
            "Products: "
            + ", ".join(
                str(artifact.planned_destination)
                for artifact in self.plan.artifacts
                if artifact.planned_destination is not None
            ),
            id="plan-products",
        )
        yield Static(f"Network tasks: {network} | Paid tasks: {paid}", id="plan-cost")
        yield Static(
            f"Translation: {self.plan.settings.translation_profile_id} | "
            f"fallback: {', '.join(self.plan.settings.translation_fallback_chain) or 'none'} | "
            f"concurrency: {self.plan.settings.translation_concurrency}",
            id="plan-providers",
        )
        yield Static(
            "Overwrites: "
            + ", ".join(problem.message for problem in self.plan.problems if problem.code == "product_overwrite"),
            id="plan-overwrites",
        )
        yield Static(
            "Problems: " + ", ".join(f"{problem.code}: {problem.message}" for problem in self.plan.problems),
            id="plan-problems",
        )
