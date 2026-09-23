"""Selectable list layout shared by Manual and State."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.text import Text


def header(title: str, columns: int, rows: int, content_rows: int) -> Text:
    """Build the centered heading used by selectable lists."""
    top: int = max((rows - content_rows - 5) // 2, 0)
    shown: str = truncate_right(title, max(columns - 2, 1))
    left: int = max((columns - len(shown)) // 2, 0)
    content: Text = Text("\n" * top)
    content.append(f"{' ' * left}{shown}\n\n", style="white_bold")
    return content


def append_row(content: Text, left: int, label: str | Text, active: bool, marker: str = "  ") -> None:
    """Append one selectable row using the shared pointer and palette."""
    content.append(" " * left)
    content.append("\u276f " if active else "  ", style="brand_accent" if active else "white_bold")
    content.append(marker, style="brand_accent" if active else "white_bold")
    if isinstance(label, Text):
        content.append_text(label)
    else:
        content.append(label, style="brand_accent" if active else "white_bold")
    content.append("\n")


def left_padding(columns: int, entries: Sequence[str]) -> int:
    """Center a list using the width of its labels and markers."""
    width: int = max((len(entry) for entry in entries), default=1) + 4
    return max((columns - min(width, columns)) // 2, 0)


def fit_entries(entries: Sequence[str], columns: int) -> tuple[str, ...]:
    """Fit list labels inside the terminal margins."""
    width: int = max(columns - 8, 1)
    return tuple(truncate_right(entry, width) for entry in entries)


def truncate_right(value: str, width: int) -> str:
    """Shorten a label with an ellipsis when necessary."""
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def visible_window(count: int, selected: int, rows: int, *, heights: Sequence[int] | None = None) -> tuple[int, int]:
    """Keep the selected row visible within the list viewport."""
    budget: int = max(rows - 7, 1)
    if heights is not None and count:
        start: int = min(selected, count - 1)
        end: int = start + 1
        used: int = heights[start]
        while start > 0 and used + heights[start - 1] <= max(budget // 2, heights[selected]):
            start -= 1
            used += heights[start]
        while end < count and used + heights[end] <= budget:
            used += heights[end]
            end += 1
        while start > 0 and used + heights[start - 1] <= budget:
            start -= 1
            used += heights[start]
        return start, end
    if count <= budget:
        return 0, count
    start = min(max(selected - budget // 2, 0), count - budget)
    return start, start + budget


def wrap_entries(entries: Sequence[str | Text], columns: int) -> tuple[tuple[str | Text, ...], ...]:
    """Wrap plain labels through Rich while retaining measured progress rows intact."""
    width: int = max(columns - 8, 1)
    console: Console = Console(width=width)
    return tuple(
        (label,) if isinstance(label, Text) else tuple(line.plain for line in Text(label).wrap(console, width)) or ("",)
        for label in entries
    )


def append_wrapped_row(content: Text, left: int, lines: Sequence[str | Text], active: bool, marker: str) -> None:
    """Keep a wrapped title under its label with one pointer and one selection marker."""
    for index, line in enumerate(lines):
        label: str | Text = line
        if index and isinstance(line, str):
            label = Text(line, style="brand_accent" if active else "white_bold")
        append_row(content, left, label, active and index == 0, marker if index == 0 else " " * len(marker))


def with_footer(content: Text, hints: Sequence[str | Text], columns: int, rows: int) -> Text:
    """Pin centered keyboard hints above the shared application status line."""
    width: int = max(columns - 2, 1)
    console: Console = Console(width=width)
    footer: list[Text] = [
        line
        for hint in hints
        for line in ((hint if isinstance(hint, Text) else Text(hint, style="gray")).wrap(console, width) or (Text(),))
    ]
    footer = footer[: max(rows - 1, 1)]
    budget: int = max(rows - 1 - len(footer), 0)
    body: list[Text] = list(content.split("\n"))[:budget]
    result: Text = Text("\n").join(body)
    result.append("\n" * max(budget - len(body) + int(bool(body)), 0))
    for index, line in enumerate(footer):
        if index:
            result.append("\n")
        result.append(" " * max((columns - line.cell_len) // 2, 0))
        result.append_text(line)
    return result
