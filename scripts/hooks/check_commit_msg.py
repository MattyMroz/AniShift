"""Enforce Conventional Commits format on the commit message.

Rejects the commit unless the first line matches:
    <type>(<scope>): <description>

The scope is MANDATORY and must come from ``SCOPES`` — this is what keeps the
history to a single, consistent format instead of a mix of scoped and
scope-less subjects. Merge commits are allowed through unchanged.

Allowed types: feat, fix, chore, docs, refactor, test, perf, style, ci, build, revert.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

# ── Constants ─────────────────────────────────────────────────────────────────

TYPES: Final[tuple[str, ...]] = (
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
"""Allowed commit types (Conventional Commits)."""

SCOPES: Final[tuple[str, ...]] = (
    "cli",
    "config",
    "pipeline",
    "platform",
    "setup",
    "services",
    "extraction",
    "subtitles",
    "translation",
    "tts",
    "llm",
    "audio",
    "composition",
    "utils",
    "logger",
    "agents",
    "deps",
    "release",
    "repo",
)
"""Allowed commit scopes; the code area a change touches. Mandatory in every commit."""

PATTERN: Final[re.Pattern[str]] = re.compile(rf"^(?:{'|'.join(TYPES)})\((?:{'|'.join(SCOPES)})\)!?: .+")
"""Match ``type(scope): description`` — scope required, from the allowed set."""


def main() -> int:
    """Validate the commit message first line; return 0 when it matches."""
    msg_path = Path(sys.argv[1])
    first_line = msg_path.read_text(encoding="utf-8").splitlines()[0].strip()

    if first_line.startswith("Merge "):
        return 0

    if PATTERN.match(first_line):
        return 0

    print("Invalid commit message.", file=sys.stderr)
    print(f"  got:      {first_line!r}", file=sys.stderr)
    print("  expected: <type>(<scope>): description  (scope is required)", file=sys.stderr)
    print(f"  types:    {', '.join(TYPES)}", file=sys.stderr)
    print(f"  scopes:   {', '.join(SCOPES)}", file=sys.stderr)
    print("  example:  feat(tts): add elevenbytes retry backoff", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
