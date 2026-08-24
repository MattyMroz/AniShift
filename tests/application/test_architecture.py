from __future__ import annotations

import ast
from pathlib import Path

from anishift import application
from anishift.application.cancellation import CancellationToken, NeverCancelledToken


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_application_contracts_do_not_depend_on_ui_io_or_domain_services() -> None:
    root = Path(__file__).parents[2] / "anishift" / "application"
    pure_modules = ("artifacts.py", "intents.py", "planning.py", "planner.py", "selection.py")
    forbidden = (
        "anishift.cli",
        "anishift.config",
        "anishift.pipeline",
        "anishift.services",
        "anishift.tui",
        "os",
        "rich",
        "subprocess",
        "textual",
        "typer",
    )
    for module_name in pure_modules:
        path = root / module_name
        if not path.exists():
            continue
        imports = _imported_modules(path)
        assert not any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden for module in imports
        )
    planner_imports = _imported_modules(root / "planner.py")
    assert "anishift.application.discovery" not in planner_imports


def test_public_application_facade_excludes_io_helpers() -> None:
    assert "Artifact" in application.__all__
    assert "ExecutionPlan" in application.__all__
    assert "create_artifact_id" not in application.__all__
    assert "stable_topological_order" not in application.__all__


def test_never_cancelled_token_satisfies_minimal_contract() -> None:
    token: CancellationToken = NeverCancelledToken()
    assert token.is_cancelled() is False
    token.raise_if_cancelled()
