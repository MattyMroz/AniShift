from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_mutating_assign.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_mutating_assign", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hook = _load_hook()


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> int:
    path = tmp_path / "prod.py"
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(_hook.sys, "argv", ["check_mutating_assign.py", str(path)])
    exit_code: int = _hook.main()
    return exit_code


@pytest.mark.parametrize(
    "body",
    [
        "found[-2] += found.pop()\n",
        "found[-1] = found.pop()\n",
        "self.items[0] += self.items.pop()\n",
        "data['a'] = data.pop('b')\n",
        "row.cells[0] = row.cells.pop()\n",
        "x: int\nlookup[k] = lookup.setdefault(k, 0) + 1\n",
        "box.value += box.update(1)\n",
    ],
)
def test_assignment_mutating_its_target_container_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str
) -> None:
    assert _run(monkeypatch, tmp_path, body) == 1


@pytest.mark.parametrize(
    "body",
    [
        "trailing = found.pop()\nfound[-1] += trailing\n",
        "found[-1] += other.pop()\n",
        "value = found.pop()\n",
        "found[-1] += found[-2]\n",
        "count += 1\n",
        "found: list[str] = []\n",
    ],
)
def test_assignment_without_a_clashing_mutation_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str
) -> None:
    assert _run(monkeypatch, tmp_path, body) == 0
