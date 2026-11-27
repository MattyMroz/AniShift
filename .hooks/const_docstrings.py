"""Require a docstring under every module-level constant and type alias; paths come from argv."""

import ast
import sys
from pathlib import Path, PurePath
from typing import Final, TypeIs

TEST_DIRS: Final[frozenset[str]] = frozenset({"test", "tests", "__tests__", "spec", "specs"})
"""Directory names whose files are tests whatever they are called, as in prose_guard."""

TEST_INFIXES: Final[tuple[str, ...]] = (".test.", ".spec.")
"""File name infixes of the *.test.* and *.spec.* conventions, as in prose_guard."""

EXAMPLES_DIR: Final[str] = "examples"
"""Directory name whose files are exempt, because examples teach."""


def _defined_name(node: ast.stmt) -> str | None:
    """Return the constant or type alias name a module-level statement defines."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id if "Final" in ast.unparse(node.annotation) else None
    if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
        return None
    name: str = node.targets[0].id
    value: str = ast.unparse(node.value)
    is_alias: bool = "Literal[" in value or "TypeAlias" in value or (" | " in value and name[0].isupper())
    return name if is_alias or name.isupper() else None


# jscpd:ignore-start
def _is_bare_string(node: object) -> TypeIs[ast.Expr]:
    """Return whether a node is a statement made of one string literal, such as a docstring."""
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _cannot_parse(path: Path, data: bytes, exc: SyntaxError | ValueError) -> str:
    """Return the report line for a file that is not UTF-8 or not valid Python."""
    if isinstance(exc, UnicodeDecodeError):
        line: int = data.count(b"\n", 0, exc.start) + 1
        return f"{path}:{line}: cannot parse: not UTF-8: save the file as UTF-8"
    if isinstance(exc, SyntaxError):
        return f"{path}:{exc.lineno or 1}: cannot parse: {exc.msg}: make the file valid Python"
    return f"{path}:1: cannot parse: {exc}: make the file valid Python"


# jscpd:ignore-end


def _check_file(path: Path) -> list[str]:
    """Return a message for every constant and type alias without a docstring."""
    data: bytes = path.read_bytes()
    try:
        body: list[ast.stmt] = ast.parse(data.decode("utf-8-sig"), filename=str(path)).body
    except (SyntaxError, ValueError) as exc:
        return [_cannot_parse(path, data, exc)]
    problems: list[str] = []
    for index, node in enumerate(body):
        name: str | None = _defined_name(node)
        if name is None or name.startswith("__"):
            continue
        following: ast.stmt | None = body[index + 1] if index + 1 < len(body) else None
        if not _is_bare_string(following):
            problems.append(f"{path}:{node.lineno}: constant '{name}' needs a docstring below it")
    return problems


# jscpd:ignore-start
def _is_test_file(path: PurePath) -> bool:
    """Return whether the path is a test file by the naming convention of prose_guard."""
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


# jscpd:ignore-end


def _is_exempt(path: Path) -> bool:
    """Return whether the path is a test or an example."""
    return _is_test_file(path) or EXAMPLES_DIR in path.parts


def main() -> int:
    """Report undocumented constants in the argv Python files; return 1 if any."""
    problems: list[str] = []
    for arg in sys.argv[1:]:
        path: Path = Path(arg)
        if path.suffix == ".py" and path.is_file() and not _is_exempt(path):
            problems.extend(_check_file(path))

    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
