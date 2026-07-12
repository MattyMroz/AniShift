"""Enforce Conventional Commits format on the commit message.

Rejects the commit if the first line does not match:
    <type>(optional scope): <description>

Allowed types: feat, fix, chore, docs, refactor, test, perf, style, ci, build, revert.
Merge commits are allowed through unchanged.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "chore",
    "docs",
    "refactor",
    "test",
    "perf",
    "style",
    "ci",
    "build",
    "revert",
)

PATTERN = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([\w./-]+\))?!?: .+")


def main() -> int:
    msg_path = Path(sys.argv[1])
    first_line = msg_path.read_text(encoding="utf-8").splitlines()[0].strip()

    if first_line.startswith("Merge "):
        return 0

    if PATTERN.match(first_line):
        return 0

    print("Invalid commit message.", file=sys.stderr)
    print(f"  got:      {first_line!r}", file=sys.stderr)
    print("  expected: <type>(scope): description", file=sys.stderr)
    print(f"  types:    {', '.join(TYPES)}", file=sys.stderr)
    print("  example:  feat(tts): add elevenbytes retry backoff", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
