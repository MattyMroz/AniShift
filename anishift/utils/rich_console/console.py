"""Preconfigured Rich console with custom theme and auto-highlighting.

Applies the 150+ style RICH_THEME, auto-highlights URLs/paths/numbers,
normalizes decimal commas, and escapes literal brackets.

Usage:
    >>> from rich_console import console
    >>> console.print("Value: 123")  # 123 is auto-colored ruby_red
    >>> console.print("Loaded /home/user/model in 1.33s")  # path + number+unit
    >>> console.print("Visit https://example.com")  # URL is blue
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Final

from rich.console import Console

from .theme import RICH_THEME

if TYPE_CHECKING:
    from typing import Any

__all__ = [
    "auto_highlight_text",
    "console",
    "normalize_numbers",
]

# ── Auto-Highlighting ─────────────────────────────────────────────────────────

_PATH_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"(?:[A-Za-z]:[/\\]|/)[\w.@+-]+(?:[/\\][\w.@+-]+)+[/\\]?"
    r"|"
    r"[\w.@+-]+(?:[/\\][\w.@+-]+){2,}[/\\]?"
    r"|"
    r"[\w.@+-]+/[\w.@+-]+\.[\w]{1,32}"
    r")"
)
"""Matches absolute (2+ segments), relative 3+ segment, or 2-segment-with-extension paths."""


def auto_highlight_text(text: str) -> str:
    """Add Rich markup to common patterns in log/console text.

    Patterns colored (in matching order):

    1. URLs (``https://...``) → ``repr.url`` (blue underline)
    2. File paths (``/foo/bar``, ``dir/sub/file.ext``) → ``repr.path`` (ruby_red)
    3. Booleans (``True``/``False``) → ``repr.bool_true``/``repr.bool_false``
    4. ``None``/``null`` → ``repr.none`` (red italic)
    5. Version strings (``v2.1.0``, ``3.13.11+cu128``) → ``repr.number``
    6. Number + unit (``1.33s``, ``245MB``, ``42ms``) → ``repr.number``
    7. Fractions (``24/24``, ``1/3``) → ``repr.number``
    8. Standalone numbers (``123``, ``45.67``) → ``repr.number``

    Natural language punctuation (``:`` ``,`` ``()`` ``—``) is intentionally
    **not** colored to keep log messages readable.

    Args:
        text: Plain text to process.

    Returns:
        Text with Rich markup tags.
    """
    if _has_rich_markup(text):
        return text

    result: str = text
    protected: list[tuple[str, str]] = []

    def build_placeholder_token(index: int) -> str:
        """Return an alphabetic placeholder token safe from later regex passes."""
        letters: list[str] = []
        current_index = index

        while True:
            current_index, remainder = divmod(current_index, 26)
            letters.append(chr(65 + remainder))
            if current_index == 0:
                break
            current_index -= 1

        suffix = "".join(reversed(letters))
        return f"PROTECTED{suffix}TOKEN"

    def protect(tagged_text: str) -> str:
        """Protect tagged text from further processing."""
        placeholder: str = build_placeholder_token(len(protected))
        protected.append((placeholder, tagged_text))
        return placeholder

    result = re.sub(
        r"(https?://[^\s]+)",
        lambda m: protect(f"[repr.url]{m.group(1)}[/repr.url]"),
        result,
    )

    result = _PATH_RE.sub(
        lambda m: protect(f"[repr.path]{m.group(0)}[/repr.path]"),
        result,
    )

    result = re.sub(
        r"\b(true|True|TRUE)\b",
        lambda m: protect(f"[repr.bool_true]{m.group(1)}[/repr.bool_true]"),
        result,
    )
    result = re.sub(
        r"\b(false|False|FALSE)\b",
        lambda m: protect(f"[repr.bool_false]{m.group(1)}[/repr.bool_false]"),
        result,
    )

    result = re.sub(
        r"\b(None|null|NULL|nil)\b",
        lambda m: protect(f"[repr.none]{m.group(1)}[/repr.none]"),
        result,
    )

    result = re.sub(
        r"\bv\d+(?:\.\d+)+(?:[+\-][\w.]+)?",
        lambda m: protect(f"[repr.number]{m.group(0)}[/repr.number]"),
        result,
    )
    result = re.sub(
        r"\b\d+\.\d+\.\d+(?:\.\d+)*(?:[+\-][\w.]+)?",
        lambda m: protect(f"[repr.number]{m.group(0)}[/repr.number]"),
        result,
    )

    result = re.sub(
        r"\b\d+(?:\.\d+)?(?:\s?)(?:ms|MB|GB|TB|KB|kB|px|dp|pt|em|rem|fps|Hz|kHz|min|sec|s)\b",
        lambda m: protect(f"[repr.number]{m.group(0)}[/repr.number]"),
        result,
    )

    result = re.sub(
        r"\b\d+/\d+\b",
        lambda m: protect(f"[repr.number]{m.group(0)}[/repr.number]"),
        result,
    )

    result = re.sub(
        r"\b\d+\.?\d*\b",
        lambda m: protect(f"[repr.number]{m.group(0)}[/repr.number]"),
        result,
    )

    result = result.replace("[", "\\[")

    for placeholder, tagged in reversed(protected):
        result = result.replace(placeholder, tagged)

    return result


# ── Number Normalization ──────────────────────────────────────────────────────


def normalize_numbers(text: str) -> str:
    """Normalize decimal separator from comma to dot (1,5 → 1.5).

    Args:
        text: Text containing numbers with comma decimals.

    Returns:
        Text with dot-separated decimals.
    """
    return re.sub(r"(\d),(\d)", r"\1.\2", text)


# ── Console Instance ──────────────────────────────────────────────────────────


def _build_console() -> Console:
    """Build a Rich console honoring the cross-tool ``FORCE_COLOR`` convention."""
    force_color = os.environ.get("FORCE_COLOR", "").lower() in {"1", "true", "yes"}
    if force_color:
        return Console(
            theme=RICH_THEME,
            force_terminal=True,
            color_system="truecolor",
            legacy_windows=False,
            width=400,
        )
    return Console(theme=RICH_THEME)


console: Console = _build_console()

# ── Rich Tag Detection ────────────────────────────────────────────────────────

_RICH_TAG_PREFIXES: Final[tuple[str, ...]] = (
    "[/",
    "[bold]",
    "[italic]",
    "[underline]",
    "[dim]",
    "[blink]",
    "[reverse]",
    "[info]",
    "[success]",
    "[warning]",
    "[error]",
    "[debug]",
    "[critical]",
    "[purple]",
    "[purple_",
    "[ruby_red]",
    "[ruby_red_",
    "[pink]",
    "[pink_",
    "[red]",
    "[red_",
    "[brown]",
    "[brown_",
    "[orange]",
    "[orange_",
    "[yellow]",
    "[yellow_",
    "[green]",
    "[green_",
    "[blue]",
    "[blue_",
    "[white]",
    "[white_",
    "[normal]",
    "[normal_",
    "[gray]",
    "[gray_",
    "[black]",
    "[black_",
    "[operator]",
    "[punctuation]",
    "[special]",
    "[repr.",
    "[markdown.",
    "[log.",
    "[logging.",
    "[tree.",
    "[progress.",
)
"""Known Rich markup prefixes for tag detection.

Prevent double-highlighting and accidental bracket escaping.
Single source of truth for ``_has_rich_markup`` and ``_highlight_outside_rich_markup``.
"""

_GENERIC_RICH_TAG_PAIR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\[([a-zA-Z_][a-zA-Z0-9_.-]*)\](.*?)\[/\1\]",
    re.DOTALL,
)
"""Regex matching paired Rich markup tags like ``[style]text[/style]``."""

_LEAF_RICH_TAG_PREFIXES: Final[tuple[str, ...]] = (
    "repr.",
    "json.",
    "iso8601.",
    "logging.",
    "log.",
    "progress.",
    "bar.",
    "table.",
    "markdown.",
    "prompt.",
    "inspect.",
    "scope.",
)
"""Rich style prefixes whose inner text should not be auto-highlighted again."""


def _has_rich_markup(text: str) -> bool:
    """Return True if text contains known or generic paired Rich markup tags."""
    if any(tag in text for tag in _RICH_TAG_PREFIXES):
        return True
    return _GENERIC_RICH_TAG_PAIR_PATTERN.search(text) is not None


def _highlight_outside_rich_markup(text: str) -> str:
    """Apply auto-highlighting around and inside paired Rich markup tags."""
    parts: list[str] = []
    current_position = 0

    for match in _GENERIC_RICH_TAG_PAIR_PATTERN.finditer(text):
        before_markup = text[current_position : match.start()]
        if before_markup:
            parts.append(auto_highlight_text(before_markup))

        style = match.group(1)
        inner_text = match.group(2)
        if style.startswith(_LEAF_RICH_TAG_PREFIXES):
            parts.append(match.group(0))
        else:
            parts.append(f"[{style}]{_highlight_outside_rich_markup(inner_text)}[/{style}]")
        current_position = match.end()

    after_markup = text[current_position:]
    if after_markup:
        parts.append(auto_highlight_text(after_markup))

    return "".join(parts) if parts else text


# ── Enhanced Console Print ────────────────────────────────────────────────────

_original_console_print = console.print


def _patched_console_print(*args: Any, **kwargs: Any) -> None:
    """Wrap console.print with auto-highlighting, normalization, and bracket escaping."""
    explicit_highlight: bool | None = kwargs.get("highlight")

    processed_args: list[Any] = []
    any_auto_highlighted = False

    for arg in args:
        if isinstance(arg, str):
            text: str = normalize_numbers(arg)
            has_markup: bool = _has_rich_markup(text)

            auto_highlighted = False
            if explicit_highlight is True and has_markup:
                text = _highlight_outside_rich_markup(text)
                auto_highlighted = True
            elif explicit_highlight is True:
                text = auto_highlight_text(text)
                auto_highlighted = True
            elif explicit_highlight is not False and has_markup:
                text = _highlight_outside_rich_markup(text)
                auto_highlighted = True
            elif explicit_highlight is not False and not has_markup:
                text = auto_highlight_text(text)
                auto_highlighted = True

            if not auto_highlighted and "[" in text:
                if not has_markup:
                    text = text.replace("[", "\\[")

            if auto_highlighted:
                any_auto_highlighted = True

            processed_args.append(text)
        else:
            processed_args.append(arg)

    if any_auto_highlighted and "highlight" not in kwargs:
        kwargs["highlight"] = False

    _original_console_print(*processed_args, **kwargs)


console.print = _patched_console_print  # type: ignore[method-assign]  # intentional monkeypatch
