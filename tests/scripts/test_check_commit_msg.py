from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "check_commit_msg.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_msg", _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_hook = _load_hook()


def _check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, message: str) -> int:
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text(message, encoding="utf-8")
    monkeypatch.setattr(_hook.sys, "argv", ["check_commit_msg.py", str(msg_file)])
    exit_code: int = _hook.main()
    return exit_code


@pytest.mark.parametrize(
    "message",
    [
        "feat(translation): add deepl retry backoff",
        "fix(cli): guard empty repl line",
        "refactor(setup): derive mapping from manifest",
        "docs(agents): scan-generated control files",
        "chore(deps): bump ruff to 0.15.21",
        "feat(tts)!: change voice selection api",
    ],
)
def test_accepts_valid_scoped_subject(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, message: str) -> None:
    assert _check(monkeypatch, tmp_path, message) == 0


@pytest.mark.parametrize(
    "message",
    [
        "feat: add deepl retry backoff",  # no scope
        "fix: guard empty repl line",  # no scope
        "feat(unknown): touch mystery module",  # scope not in the allowed set
        "feature(cli): typo in type",  # invalid type
        "update(cli): non-conventional type",  # invalid type
        "feat(cli) missing colon",  # no colon
        "random text",  # not conventional at all
    ],
)
def test_rejects_invalid_subject(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, message: str) -> None:
    assert _check(monkeypatch, tmp_path, message) == 1


def test_merge_commit_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _check(monkeypatch, tmp_path, "Merge branch 'main' into feature") == 0
