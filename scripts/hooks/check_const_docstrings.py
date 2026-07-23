"""Require a docstring under every module-level constant and type alias.

The standard asks for a docstring below each ``Final`` constant and each type
alias, but ruff/pydocstyle only check modules, classes and functions — a bare
``NAME: Final = ...`` slips through. This hook closes that gap by walking the
module body and flagging any constant/alias whose next statement is not a
string literal.

Scope: production code only. Test files, ``examples/`` and ``__dunder__``
targets are skipped. Paths come from argv (pre-commit passes staged files).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SKIP_PARTS = ("tests", "examples")


def _has_docstring_after(body: list[ast.stmt], index: int) -> bool:
    """Whether the statement after *index* is a bare string literal."""
    nxt = body[index + 1] if index + 1 < len(body) else None
    return isinstance(nxt, ast.Expr) and isinstance(nxt.value, ast.Constant) and isinstance(nxt.value.value, str)


def _target_name(node: ast.stmt) -> str | None:
    """Return the constant/alias name a module-level assignment defines, else None."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        if "Final" in ast.unparse(node.annotation):
            return node.target.id
        return None
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        value = ast.unparse(node.value)
        is_alias = "Literal[" in value or "TypeAlias" in value or (" | " in value and name[0].isupper())
        is_const = name.isupper()
        if is_alias or is_const:
            return name
    return None


def _check_file(path: Path) -> list[str]:
    """Return messages for constants/aliases missing a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for index, node in enumerate(tree.body):
        name = _target_name(node)
        if name is None or name.startswith("__"):
            continue
        if not _has_docstring_after(tree.body, index):
            problems.append(f"{path}:{node.lineno}: constant '{name}' needs a docstring below it")
    return problems


def main() -> int:
    """Scan each argv path; return 1 if any constant lacks a docstring."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.suffix != ".py" or not path.is_file():
            continue
        parts = set(path.parts)
        if parts & set(SKIP_PARTS) or path.name.startswith("test_"):
            continue
        problems.extend(_check_file(path))

    if not problems:
        return 0
    print("Every module-level constant / type alias needs a docstring below it:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
