"""Reject comments and bare string literals, docstrings included, in Python and JS/TS test files."""

import ast
import io
import sys
import tokenize
from pathlib import Path, PurePath
from typing import Final, TypeIs

PY_ALLOWED: Final[tuple[str, ...]] = (
    "# noqa",
    "# type:",
    "# pragma",
    "# pyright:",
    "# ruff: noqa",
    "# fmt:",
    "# jscpd:",
)
"""Python comment prefixes that are tool directives."""

SHEBANG: Final[str] = "#!"
"""Prefix of the interpreter line, allowed as the first line of a Python file."""

JS_ALLOWED: Final[tuple[str, ...]] = (
    "eslint",
    "@ts",
    "prettier",
    "biome",
    "c8",
    "istanbul",
    "v8",
)
"""Substrings that mark a JS/TS comment as a tool directive."""

PY_SUFFIXES: Final[frozenset[str]] = frozenset({".py"})
"""Extensions checked as Python."""

JS_SUFFIXES: Final[frozenset[str]] = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"})
"""Extensions checked as JS/TS."""

TEST_DIRS: Final[frozenset[str]] = frozenset({"test", "tests", "__tests__", "spec", "specs"})
"""Directory names whose files are tests whatever they are called."""

TEST_INFIXES: Final[tuple[str, ...]] = (".test.", ".spec.")
"""File name infixes of the *.test.* and *.spec.* conventions."""

TEMPLATE_QUOTE: Final[str] = "`"
"""Opener of a template literal, the only literal that spans lines."""

ALWAYS_OPEN: Final[frozenset[str]] = frozenset({'"', TEMPLATE_QUOTE})
"""Quotes that open a literal anywhere: after a tag, or paired in JSX text."""

APOSTROPHE: Final[str] = "'"
"""Quote that JSX text uses as an apostrophe, so its context decides."""

EXPRESSION_PRECEDERS: Final[frozenset[str]] = frozenset("(,=:[!&|?{};+-*%~^<>.")
"""Characters after which an apostrophe or slash opens a literal."""

EXPRESSION_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "return",
        "typeof",
        "case",
        "in",
        "of",
        "do",
        "else",
        "void",
        "delete",
        "new",
        "yield",
        "await",
        "throw",
        "from",
        "import",
        "extends",
        "as",
        "default",
        "satisfies",
        "module",
    }
)
"""Keywords after which an apostrophe or slash opens a literal."""

PROSE_FIX: Final[str] = "remove it and put what it says into a test, function or variable name"
"""The fix for a comment or bare string in a test file."""


def _is_test_file(path: PurePath) -> bool:
    """Return whether the path is a test file by naming convention."""
    if {part.lower() for part in path.parts} & TEST_DIRS:
        return True
    name: str = path.name.lower()
    stem: str = name.split(".")[0]
    return (
        name == "conftest.py"
        or stem.startswith("test_")
        or stem.endswith("_test")
        or any(infix in name for infix in TEST_INFIXES)
    )


def _cannot_parse(path: Path, data: bytes, exc: SyntaxError | ValueError) -> str:
    """Return the report line for a file that is not UTF-8 or not valid Python."""
    if isinstance(exc, UnicodeDecodeError):
        line: int = data.count(b"\n", 0, exc.start) + 1
        return f"{path}:{line}: cannot parse: not UTF-8: save the file as UTF-8"
    if isinstance(exc, SyntaxError):
        return f"{path}:{exc.lineno or 1}: cannot parse: {exc.msg}: make the file valid Python"
    return f"{path}:1: cannot parse: {exc}: make the file valid Python"


def _is_bare_string(node: object) -> TypeIs[ast.Expr]:
    """Return whether a node is a statement made of one string literal, such as a docstring."""
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _is_python_directive(token: tokenize.TokenInfo) -> bool:
    """Return whether a Python comment token is a tool directive or the shebang."""
    comment: str = token.string.strip()
    shebang: bool = token.start == (1, 0) and comment.startswith(SHEBANG)
    return shebang or comment.startswith(PY_ALLOWED)


def _check_python(path: Path) -> list[str]:
    """Return a message for every comment and bare string in a Python file."""
    data: bytes = path.read_bytes()
    try:
        src: str = data.decode("utf-8-sig")
        tree: ast.Module = ast.parse(src, filename=str(path))
    except (SyntaxError, ValueError) as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(src).readline):
        if token.type == tokenize.COMMENT and not _is_python_directive(token):
            problems.append(
                f"{path}:{token.start[0]}: comment not allowed in tests: {token.string.strip()}: {PROSE_FIX}"
            )
    for node in ast.walk(tree):
        if _is_bare_string(node):
            problems.append(f"{path}:{node.lineno}: docstring not allowed in tests: {PROSE_FIX}")
    return problems


def _line_of(src: str, index: int) -> int:
    """Return the 1-based line number of the character at the index."""
    return src.count("\n", 0, index) + 1


def _is_directive(body: str) -> bool:
    """Return whether a JS/TS comment body is a tool directive."""
    return any(mark in body for mark in JS_ALLOWED)


def _skip_string(src: str, start: int) -> int:
    """Return the index just past the string at start: a quoted one ends at its newline, a template at its backtick."""
    quote: str = src[start]
    i: int = start + 1
    while i < len(src):
        if src[i] == "\\":
            i += 2
        elif src[i] == quote:
            return i + 1
        elif src[i] == "\n" and quote != TEMPLATE_QUOTE:
            return i
        else:
            i += 1
    return len(src)


def _opens_literal(src: str, last: int) -> bool:
    """Return whether a quote or slash after the last code character src[last] (-1: none) can start an expression."""
    if last < 0 or src[last] in EXPRESSION_PRECEDERS:
        return True
    j: int = last
    while j >= 0 and (src[j].isalnum() or src[j] in "_$"):
        j -= 1
    return src[j + 1 : last + 1] in EXPRESSION_KEYWORDS


def _skip_regex(src: str, start: int) -> int:
    """Return the index just past the regex at start, or just past the slash when it is a division open to line end."""
    i: int = start + 1
    in_class: bool = False
    while i < len(src):
        ch: str = src[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            return start + 1
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "/":
            return i + 1
        i += 1
    return start + 1


def _check_js(path: Path) -> list[str]:
    """Return a message for every comment in a JS/TS file outside its literals."""
    data: bytes = path.read_bytes()
    try:
        src: str = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    last: int = -1
    i: int = 0
    while i < len(src):
        ch: str = src[i]
        pair: str = src[i : i + 2]
        if pair == "//":
            end: int = src.find("\n", i)
            end = len(src) if end == -1 else end
            body: str = src[i + 2 : end]
            if not _is_directive(body):
                problems.append(
                    f"{path}:{_line_of(src, i)}: comment not allowed in tests: //{body.strip()}: {PROSE_FIX}"
                )
            i = end
            continue
        if pair == "/*":
            end = src.find("*/", i + 2)
            end = len(src) if end == -1 else end
            if not _is_directive(src[i + 2 : end]):
                problems.append(f"{path}:{_line_of(src, i)}: block comment not allowed in tests: {PROSE_FIX}")
            i = end + 2
            continue
        if ch in ALWAYS_OPEN or (ch == APOSTROPHE and _opens_literal(src, last)):
            i = _skip_string(src, i)
        elif ch == "/" and _opens_literal(src, last):
            i = _skip_regex(src, i)
        else:
            i += 1
        if not ch.isspace():
            last = i - 1
    return problems


def main() -> int:
    """Report prose in the argv test files; return 1 if there is any."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path: Path = Path(arg)
        if not path.is_file() or not _is_test_file(path):
            continue
        if path.suffix in PY_SUFFIXES:
            problems.extend(_check_python(path))
        elif path.suffix in JS_SUFFIXES:
            problems.extend(_check_js(path))

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
