from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_HOOK_PATH: Path = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_commit_msg.py"
_TEMPLATES_DIR: Path = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_msg", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hook: ModuleType = _load_hook()
_SCOPES: tuple[str, ...] = _hook.SCOPES


def _extract_area_options(template_path: Path) -> list[str]:
    lines: list[str] = template_path.read_text(encoding="utf-8").splitlines()

    area_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == "id: area":
            area_index = index
            break
    if area_index is None:
        msg = f"No 'area' dropdown found in {template_path.name}"
        raise ValueError(msg)

    options_index: int | None = None
    for index in range(area_index + 1, len(lines)):
        stripped: str = lines[index].strip()
        if stripped.startswith("- type:"):
            break
        if stripped == "options:":
            options_index = index
            break
    if options_index is None:
        msg = f"No 'options:' under 'area' dropdown in {template_path.name}"
        raise ValueError(msg)

    options: list[str] = []
    for index in range(options_index + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped.startswith("- "):
            break
        options.append(stripped[2:].strip())
    if not options:
        msg = f"Empty 'options:' under 'area' dropdown in {template_path.name}"
        raise ValueError(msg)
    return options


@pytest.mark.parametrize(
    "template_name",
    ["bug.yml", "feature.yml", "task.yml"],
)
def test_issue_template_areas_match_scopes(template_name: str) -> None:
    template_path: Path = _TEMPLATES_DIR / template_name
    areas: list[str] = _extract_area_options(template_path)
    scopes: list[str] = list(_SCOPES)
    assert areas == scopes, (
        f"{template_name} area options differ from SCOPES.\n"
        f"  Missing from template: {sorted(set(scopes) - set(areas))}\n"
        f"  Extra in template:     {sorted(set(areas) - set(scopes))}\n"
        f"  Template order: {areas}\n"
        f"  SCOPES order:   {scopes}"
    )
