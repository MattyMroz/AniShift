"""Reject an assignment whose value mutates the container that its target indexes.

``items[-2] += items.pop()`` reads the target, then shortens the list, then
writes to an index that no longer exists. Any assignment, augmented or plain,
whose subscript target indexes the same object that the value calls a mutating
method on depends on evaluation order this way. Split the mutation into its own
statement first. Paths come from argv (pre-commit passes staged files).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MUTATING_METHODS = frozenset({
    "add", "append", "clear", "discard", "extend", "insert", "pop", "popitem",
    "remove", "reverse", "setdefault", "sort", "update",
})  # fmt: skip
"""Methods of built-in containers that change the container they are called on."""


def _target_bases(target: ast.expr) -> set[str]:
    """Return the source text of every object a subscript target indexes."""
    bases: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Subscript):
            bases.add(ast.unparse(node.value))
    return bases


def _mutated_objects(value: ast.expr) -> set[str]:
    """Return the source text of every object the value calls a mutating method on."""
    mutated: set[str] = set()
    for node in ast.walk(value):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MUTATING_METHODS:
            mutated.add(ast.unparse(node.func.value))
    return mutated


def _check_file(path: Path) -> list[str]:
    """Return messages for assignments whose value mutates the object their target indexes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets: list[ast.expr] = node.targets
            value: ast.expr = node.value
        elif isinstance(node, ast.AugAssign | ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        clash: set[str] = set().union(*(_target_bases(target) for target in targets)) & _mutated_objects(value)
        problems.extend(
            f"{path}:{node.lineno}: '{name}' is mutated by the value assigned into it" for name in sorted(clash)
        )
    return problems


def main() -> int:
    """Scan each argv path; return 1 if any assignment mutates the container its target indexes."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if path.suffix != ".py" or not path.is_file():
            continue
        problems.extend(_check_file(path))

    if not problems:
        return 0
    print("Mutate a container in its own statement before assigning into it:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
