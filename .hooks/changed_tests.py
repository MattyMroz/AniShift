#!/usr/bin/env python3
"""Run the test command before the last -- on the changed test files after it, without the commit's git variables."""

import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import PurePath
from typing import Final

FIELDS: Final[dict[str, Callable[[str], str]]] = {
    "{file}": lambda file: file,
    "{dir}": lambda file: str(PurePath(file).parent),
    "{name}": lambda file: PurePath(file).name,
    "{stem}": lambda file: PurePath(file).stem,
}
"""Placeholders that make the command run once per file, with how each one reads the file path."""


# jscpd:ignore-start
@functools.cache
def _local_git_variables() -> frozenset[str]:
    listed: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, check=False
    )
    return frozenset(listed.stdout.split())


def hook_free_env() -> dict[str, str]:
    """Return the environment without the git variables of the commit, so a test's git calls stay in its own repo."""
    local: frozenset[str] = _local_git_variables()
    return {
        name: value for name, value in os.environ.items() if name not in local and not name.startswith("PRE_COMMIT_")
    }


# jscpd:ignore-end


def _fill(command: Sequence[str], file: str) -> list[str]:
    """Return the command with the placeholders of one file filled in."""
    filled: list[str] = []
    for part in command:
        for field, value in FIELDS.items():
            part = part.replace(field, value(file))
        filled.append(part)
    return filled


def main(argv: Sequence[str]) -> int:
    """Run the command before the last -- on the files after it; return 1 when any run failed, 2 without the --."""
    if "--" not in argv:
        print("changed_tests.py: end the command with -- before the files", file=sys.stderr)
        return 2
    split: int = len(argv) - 1 - list(reversed(argv)).index("--")
    command: list[str] = list(argv[:split])
    files: list[str] = list(argv[split + 1 :])
    if not command:
        print(
            "changed_tests.py: no test command before --: write the test command before -- in the hook entry",
            file=sys.stderr,
        )
        return 2
    if not files:
        return 0
    env: dict[str, str] = hook_free_env()
    command[0] = shutil.which(command[0]) or command[0]
    if any(field in part for part in command for field in FIELDS):
        runs: list[list[str]] = [_fill(command, file) for file in files]
    else:
        runs = [[*command, *(file if PurePath(file).is_absolute() else f"./{file}" for file in files)]]
    codes: list[int] = [subprocess.run(run, check=False, env=env).returncode for run in runs]
    return 1 if any(codes) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
