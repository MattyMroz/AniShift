from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_test_comments.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_test_comments", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hook = _load_hook()


def _run(monkeypatch: pytest.MonkeyPatch, path: Path) -> int:
    monkeypatch.setattr(_hook.sys, "argv", ["check_test_comments.py", str(path)])
    exit_code: int = _hook.main()
    return exit_code


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_clean_python_test_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "test_clean.py", "def test_x() -> None:\n    assert True  # noqa: S101\n")
    assert _run(monkeypatch, path) == 0


def test_python_docstring_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "test_doc.py", 'def test_x() -> None:\n    """nope"""\n    assert True\n')
    assert _run(monkeypatch, path) == 1


def test_python_prose_comment_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "test_c.py", "def test_x() -> None:\n    x = 1  # prose\n    assert x\n")
    assert _run(monkeypatch, path) == 1


def test_python_type_ignore_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "test_t.py", "def test_x() -> None:  # type: ignore[misc]\n    assert True\n")
    assert _run(monkeypatch, path) == 0


def test_tsx_prose_comment_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "widget.test.tsx", "export const x = 1; // prose\n")
    assert _run(monkeypatch, path) == 1


def test_tsx_hash_in_string_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "s.test.ts", 'const s = "// not a comment";\n')
    assert _run(monkeypatch, path) == 0


def test_tsx_eslint_directive_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "d.test.tsx", "const x = 1; // eslint-disable-line\n")
    assert _run(monkeypatch, path) == 0


def test_non_test_file_skipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write(tmp_path, "helper.py", 'def f() -> None:\n    """this is fine"""\n')
    assert _run(monkeypatch, path) == 0
