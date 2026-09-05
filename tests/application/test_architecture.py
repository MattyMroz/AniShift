from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from anishift import application
from anishift.application.cancellation import CancellationToken, NeverCancelledToken

_REPO_ROOT: Final[Path] = Path(__file__).parents[2]

_APPLICATION_PACKAGE: Final[str] = "anishift.application"

_APPLICATION_ROOT: Final[Path] = _REPO_ROOT / "anishift" / "application"

_UI_PACKAGES: Final[tuple[str, ...]] = ("cli", "tui")

_PURE_MODULES: Final[tuple[str, ...]] = ("artifacts.py", "intents.py", "planning.py", "planner.py", "selection.py")

_PURE_FORBIDDEN: Final[tuple[str, ...]] = (
    "anishift.cli",
    "anishift.config",
    "anishift.services",
    "anishift.tui",
    "os",
    "rich",
    "subprocess",
    "textual",
    "typer",
)

_USER_INTERFACES: Final[tuple[str, ...]] = ("anishift.cli", "anishift.tui", "rich", "textual", "typer")

_BACKEND_PACKAGES: Final[tuple[str, ...]] = ("anishift.services",)

_INTERNAL_ANCHORS: Final[frozenset[str]] = frozenset(
    {
        f"{_APPLICATION_PACKAGE}.discovery",
        f"{_APPLICATION_PACKAGE}.inspection",
        f"{_APPLICATION_PACKAGE}.scheduler",
        f"{_APPLICATION_PACKAGE}.service",
    },
)


def _imported_modules(source: str) -> set[str]:
    tree: ast.Module = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _touches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)


def _facade_surface() -> frozenset[str]:
    tree: ast.Module = ast.parse((_APPLICATION_ROOT / "__init__.py").read_text(encoding="utf-8"))
    return frozenset(
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith(f"{_APPLICATION_PACKAGE}.")
    )


def _internal_application_modules() -> frozenset[str]:
    every: frozenset[str] = frozenset(
        f"{_APPLICATION_PACKAGE}.{path.stem}" for path in _APPLICATION_ROOT.glob("*.py") if path.stem != "__init__"
    )
    return every - _facade_surface()


def _layer_offenders(source: str, internal: frozenset[str]) -> list[str]:
    forbidden: tuple[str, ...] = (*sorted(internal), *_BACKEND_PACKAGES)
    return sorted(module for module in _imported_modules(source) if _touches(module, forbidden))


def _sources(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _ui_sources() -> list[Path]:
    return [path for package in _UI_PACKAGES for path in _sources(_REPO_ROOT / "anishift" / package)]


def test_application_contracts_do_not_depend_on_ui_io_or_domain_services() -> None:
    for module_name in _PURE_MODULES:
        path: Path = _APPLICATION_ROOT / module_name
        assert path.is_file()
        imports: set[str] = _imported_modules(path.read_text(encoding="utf-8"))
        assert not any(_touches(module, _PURE_FORBIDDEN) for module in imports)
    planner_imports: set[str] = _imported_modules((_APPLICATION_ROOT / "planner.py").read_text(encoding="utf-8"))
    assert f"{_APPLICATION_PACKAGE}.discovery" not in planner_imports


def test_the_application_layer_never_imports_a_user_interface() -> None:
    offenders: list[str] = [
        f"{path.name}:{module}"
        for path in _sources(_APPLICATION_ROOT)
        for module in sorted(_imported_modules(path.read_text(encoding="utf-8")))
        if _touches(module, _USER_INTERFACES)
    ]
    assert offenders == []


def test_the_ui_layers_import_only_the_public_application_surface() -> None:
    internal: frozenset[str] = _internal_application_modules()
    offenders: list[str] = [
        f"{path.name}:{module}"
        for path in _ui_sources()
        for module in _layer_offenders(path.read_text(encoding="utf-8"), internal)
    ]
    assert offenders == []


def test_every_internal_application_module_is_closed_to_the_ui_layers() -> None:
    internal: frozenset[str] = _internal_application_modules()
    assert internal >= _INTERNAL_ANCHORS
    unguarded: list[str] = [
        module for module in sorted(internal) if not _layer_offenders(f"from {module} import Thing\n", internal)
    ]
    assert unguarded == []
    assert _layer_offenders("from anishift.services.tts import TtsService\n", internal) == ["anishift.services.tts"]


def test_public_application_facade_excludes_io_helpers() -> None:
    assert "Artifact" in application.__all__
    assert "ExecutionPlan" in application.__all__
    assert "create_artifact_id" not in application.__all__
    assert "stable_topological_order" not in application.__all__


def test_never_cancelled_token_satisfies_minimal_contract() -> None:
    token: CancellationToken = NeverCancelledToken()
    assert token.is_cancelled() is False
    token.raise_if_cancelled()
