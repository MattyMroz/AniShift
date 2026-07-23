"""Reject docstrings and descriptive comments in test files.

Test intent belongs in the test name, not in prose. This hook blocks any
docstring or plain comment inside a test file, while allowing tool directives
that the toolchain needs (``# noqa``, ``# type:``, ``# pragma`` for Python;
``// eslint``, ``// @ts`` for TS/JS).

Portable across repos and languages — the file extension selects the rules:
    .py                        -> tokenizer + AST (comments + docstrings)
    .ts/.tsx/.js/.jsx/.mjs/... -> line/block comment scan (strings skipped)

A file counts as a test when its name contains ``test`` or ``spec`` (matching
``test_*.py``, ``*.test.tsx``, ``*.spec.ts``). Paths come from argv (pre-commit
passes the staged files).
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path
from typing import Final

# ── Constants ─────────────────────────────────────────────────────────────────

PY_ALLOWED: Final[tuple[str, ...]] = ("# noqa", "# type:", "# pragma")
"""Python comment prefixes that are tool directives, not prose."""

JS_ALLOWED: Final[tuple[str, ...]] = ("eslint", "@ts", "prettier", "biome", "c8", "istanbul", "v8")
"""Substrings marking a JS/TS comment as a tool directive, not prose."""

PY_SUFFIXES: Final[frozenset[str]] = frozenset({".py"})
"""Extensions handled by the Python tokenizer/AST path."""

JS_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"})
"""Extensions handled by the JS/TS comment scanner."""

TEST_MARKERS: Final[tuple[str, ...]] = ("test", "spec")
"""A filename containing any of these marks the file as a test."""


def _is_test_file(path: Path) -> bool:
    """Whether *path* is a test file by name (``test_*.py``, ``*.test.tsx``...)."""
    name = path.name.lower()
    return any(marker in name for marker in TEST_MARKERS)


def _check_python(path: Path) -> list[str]:
    """Return violation messages for a Python test file."""
    src = path.read_text(encoding="utf-8")
    problems: list[str] = []

    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT and not tok.string.strip().startswith(PY_ALLOWED):
            problems.append(f"{path}:{tok.start[0]}: comment not allowed in tests: {tok.string.strip()}")

    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and (
            ast.get_docstring(node) and node.body
        ):
            problems.append(f"{path}:{node.body[0].lineno}: docstring not allowed in tests")
    return problems


def _check_js(path: Path) -> list[str]:
    """Return violation messages for a TS/JS test file (strings skipped)."""
    src = path.read_text(encoding="utf-8")
    problems: list[str] = []
    line = 1
    i = 0
    n = len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {'"', "'", "`"}:
            quote = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            body = src[i + 2 : src.find("\n", i) if "\n" in src[i:] else n]
            if not any(mark in body for mark in JS_ALLOWED):
                problems.append(f"{path}:{line}: comment not allowed in tests: //{body.strip()}")
            i = src.find("\n", i)
            if i == -1:
                break
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i)
            body = src[i + 2 : end if end != -1 else n]
            if not any(mark in body for mark in JS_ALLOWED):
                problems.append(f"{path}:{line}: block comment not allowed in tests")
            line += body.count("\n")
            i = (end + 2) if end != -1 else n
            continue
        i += 1
    return problems


def main() -> int:
    """Scan each argv path; return 1 if any test file carries prose."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.is_file() or not _is_test_file(path):
            continue
        if path.suffix in PY_SUFFIXES:
            problems.extend(_check_python(path))
        elif path.suffix in JS_SUFFIXES:
            problems.extend(_check_js(path))

    if not problems:
        return 0
    print("Tests must carry no docstrings or descriptive comments (name says it):", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print("  Allowed: # noqa, # type:, # pragma (py); // eslint, // @ts (ts/js).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
