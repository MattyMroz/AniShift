from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_const_docstrings.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_const_docstrings", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hook = _load_hook()


def _run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str, name: str = "prod.py") -> int:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(_hook.sys, "argv", ["check_const_docstrings.py", str(path)])
    exit_code: int = _hook.main()
    return exit_code


def test_final_with_docstring_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = 'from typing import Final\n\nX: Final[int] = 1\n"""the x."""\n'
    assert _run(monkeypatch, tmp_path, body) == 0


def test_final_without_docstring_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = "from typing import Final\n\nX: Final[int] = 1\n"
    assert _run(monkeypatch, tmp_path, body) == 1


def test_type_alias_without_docstring_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = 'from typing import Literal\n\nMode = Literal["a", "b"]\n'
    assert _run(monkeypatch, tmp_path, body) == 1


def test_upper_const_without_docstring_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _run(monkeypatch, tmp_path, "TIMEOUT = 30\n") == 1


def test_dunder_all_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _run(monkeypatch, tmp_path, '__all__ = ["x"]\n') == 0


def test_regular_variable_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _run(monkeypatch, tmp_path, "count = 0\n") == 0


def test_test_file_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    body = "from typing import Final\n\nX: Final[int] = 1\n"
    assert _run(monkeypatch, tmp_path, body, name="test_x.py") == 0
