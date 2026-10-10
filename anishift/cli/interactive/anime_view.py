"""Pure terminal layout with explicit text-only mouse hit regions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from rich.console import Console
from rich.spinner import Spinner
from rich.text import Text

from anishift.cli.interactive.actions import pack_footer
from anishift.cli.interactive.anime_state import (
    AnimeRow,
    AnimeScreen,
    AnimeSnapshot,
    NoticeKind,
    query_left,
)
from anishift.cli.interactive.menu import append_wrapped_row
from anishift.cli.interactive.pointer import (
    CRUMB_SEPARATOR,
    TextCell,
    TextPoint,
    character_offset,
    mark_crumbs,
    mark_inert,
    mark_row,
    paint_selection,
    selected_cells,
    selected_text,
    text_cells,
)
from anishift.text.graphemes import split_graphemes

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_COLUMNS: Final[int] = 50
"""Minimum supported terminal width."""

WIDE_COLUMNS: Final[int] = 80
"""Widest text budget used for wrapped details and editors."""

_CONTEXT_ROWS: Final[int] = 2
"""Rows opening a table or list block: the context line and the global status or a blank line."""

_QUERY_TITLE: Final[str] = "ANIME"
"""Heading above the search field and its search progress, as in the classic search box."""

_QUERY_HEADING_ROWS: Final[int] = 2
"""Rows above the search field: its heading and one blank line."""

HEADER_ROWS: Final[int] = _CONTEXT_ROWS + 1
"""Rows above table data: the context rows and the column labels."""

FOOTER_ROWS: Final[int] = 5
"""Rows pinned at the bottom: selection summary, two notice lines and two key lines."""

_NOTICE_ROWS: Final[int] = 2
"""Most lines a notice or full title may occupy above the key lines."""

MIN_ROWS: Final[int] = HEADER_ROWS + 1 + FOOTER_ROWS
"""Minimum height retaining a data row and all footer regions."""

_MARGIN: Final[int] = 4
"""Cells kept free around centered blocks."""

_EPISODE_STATUS_WIDTH: Final[int] = len("Czeka na wydanie")
"""Fixed Stan column width, so a changing episode state never shifts the centered table."""

_SUBSCRIPTION_STATUS_WIDTH: Final[int] = len("Emisja E12 za 13d 23:59:59")
"""Fixed Stan column width of the subscription list, so a ticking countdown never shifts the table."""

_TITLE_FLOOR: Final[int] = 12
"""Fewest title cells kept before optional table columns are dropped."""

_COLORS: Final[dict[NoticeKind, str]] = {
    NoticeKind.INFO: "gray",
    NoticeKind.SUCCESS: "success",
    NoticeKind.WARNING: "warning",
}
"""Theme role of each feedback kind."""

_LIST_SCREENS: Final[frozenset[AnimeScreen]] = frozenset(
    {AnimeScreen.DETAILS, AnimeScreen.FILES, AnimeScreen.BUSY, AnimeScreen.PROBLEM, AnimeScreen.DRAFT}
)
"""Screens rendering one plain text column instead of a table."""

_TEXT_SCREENS: Final[frozenset[AnimeScreen]] = frozenset({AnimeScreen.DETAILS, AnimeScreen.BUSY, AnimeScreen.PROBLEM})
"""Screens of text, not lists: a click points at a row, a double click never runs Enter there."""

_FILL_NOTICE_ROWS: Final[int] = 1
"""Rows a filled table keeps beneath its data for the highlighted row's detail or a notice."""

_FILL_MIN_ROWS: Final[int] = MIN_ROWS - 1
"""Minimum height of a filled table, which has no blank row beneath its data."""


@dataclass(frozen=True, slots=True)
class AnimeFrame:
    """Return the painted frame and its text-only interaction geometry."""

    text: Text
    cells: tuple[TextCell, ...]
    visible: int
    first_row: int = HEADER_ROWS

    def selected_cells(self, selection: tuple[TextPoint, TextPoint] | None) -> tuple[TextCell, ...]:
        """Return whole graphemes intersected by an inclusive reading-order selection."""
        return selected_cells(self.cells, selection)

    def selected_text(self, selection: tuple[TextPoint, TextPoint] | None) -> str:
        """Copy text in reading order while omitting markers, borders and padding."""
        return selected_text(self.cells, selection)


@dataclass(frozen=True, slots=True)
class _Table:
    labels: tuple[str, ...]
    values: Callable[[AnimeRow], tuple[str, ...]]
    prefix: int
    title: int
    minimums: tuple[int, ...] = (0, 0, 0, 0)
    status_width: int = 0
    optional: tuple[int, ...] = ()
    right: tuple[int, ...] = ()


class _Canvas:
    def __init__(self, width: int, rows: int) -> None:
        self.width: int = width
        self.top: int = 0
        self.left: int = 0
        self.columns: int = width
        self.lines: list[Text] = [Text(" " * width) for _ in range(rows)]
        self.regions: list[tuple[int, int, str]] = []
        self.rows: dict[int, int] = {}
        self.opens: bool = True

    def place(self, columns: int) -> None:
        self.columns = max(min(columns, self.width - _MARGIN), 1)
        self.left = (self.width - self.columns) // 2

    def put(self, row: int, column: int, value: str, style: str = "white_bold", *, selectable: bool = False) -> None:
        if column >= self.columns:
            return
        self.write(row, self.left + column, Text(fit(value, self.columns - column), style), selectable=selectable)

    def center(self, row: int, value: Text, *, selectable: bool = False) -> None:
        shown: Text = value.copy()
        if shown.cell_len > self.width - 2:
            shown = Text(fit(shown.plain, self.width - 2), value.style)
        self.write(row, (self.width - shown.cell_len) // 2, shown, selectable=selectable)

    def write(self, row: int, column: int, value: Text, *, selectable: bool) -> None:
        if not 0 <= row < len(self.lines) or not value.plain:
            return
        line: Text = self.lines[row]
        prefix: Text = line[: character_offset(line.plain, column)]
        prefix.append_text(value if selectable else mark_inert(value))
        prefix.append_text(line[character_offset(line.plain, column + value.cell_len) :])
        self.lines[row] = prefix
        if selectable:
            self.regions.append((row, column, value.plain))

    def tag(self, row: int, index: int) -> None:
        self.rows[row] = index

    def finish(self, visible: int, selection: tuple[TextPoint, TextPoint] | None, first_row: int = 0) -> AnimeFrame:
        for row, index in self.rows.items():
            if 0 <= row < len(self.lines):
                mark_row(self.lines[row], index, opens=self.opens)
        cells: tuple[TextCell, ...] = text_cells([line.plain for line in self.lines], self.regions)
        text: Text = Text("\n").join(self.lines)
        frame: AnimeFrame = AnimeFrame(text, cells, visible, first_row)
        paint_selection(text, frame.selected_cells(selection))
        return frame


def fit(value: str, width: int) -> str:
    """Fit printable graphemes into terminal cells with one ellipsis."""
    clean: str = "".join(character for character in value if character.isprintable() or character == "\u200d")
    if Text(clean).cell_len <= width:
        return clean
    result: list[str] = []
    used: int = 0
    for grapheme in split_graphemes(clean):
        size: int = Text(grapheme).cell_len
        if used + size > max(width - 1, 0):
            break
        result.append(grapheme)
        used += size
    return "".join(result) + ("…" if width else "")


def visible_rows(rows: int) -> int:
    """Return how many data rows fit in a block of ``rows`` terminal rows."""
    return max(rows - HEADER_ROWS - FOOTER_ROWS, 1)


def shown_rows(snapshot: AnimeSnapshot, columns: int, rows: int) -> int:
    """Return how many item rows ``render_anime`` shows in ``columns`` x ``rows``, 0 when they do not fit."""
    if columns < MIN_COLUMNS:
        return 0
    if not snapshot.fill:
        return visible_rows(rows) if rows >= MIN_ROWS else 0
    keys: tuple[str, ...] = _key_lines(snapshot, columns - _MARGIN)
    filled: int = rows - _filled_start(snapshot) - HEADER_ROWS - _FILL_NOTICE_ROWS - len(keys)
    return filled if rows >= _FILL_MIN_ROWS else 0


def _context(snapshot: AnimeSnapshot) -> str:
    return CRUMB_SEPARATOR.join(snapshot.crumbs) if snapshot.crumbs else snapshot.title


def _filled_start(snapshot: AnimeSnapshot) -> int:
    return 0 if _context(snapshot) else -1


def render_anime(snapshot: AnimeSnapshot, columns: int, rows: int, now: float) -> AnimeFrame:
    """Render ``rows`` lines: content centered above the keys, info and keys pinned to the bottom."""
    width: int = max(columns, 1)
    visible: int = shown_rows(snapshot, columns, rows)
    if not visible:
        small: _Canvas = _Canvas(width, 1)
        small.center(0, Text("Powiększ terminal do 50 x 12", "warning"))
        return small.finish(0, None)
    keys: tuple[str, ...] = _key_lines(snapshot, width - _MARGIN)
    shown: int = len(snapshot.items[snapshot.offset : snapshot.offset + visible])
    query: bool = snapshot.screen is AnimeScreen.QUERY
    listed: bool = snapshot.screen in _LIST_SCREENS
    heading: int = _QUERY_HEADING_ROWS if query else _CONTEXT_ROWS if listed else HEADER_ROWS
    height: int = heading + (1 if query else max(shown, 1))
    canvas: _Canvas = _Canvas(width, rows)
    canvas.opens = snapshot.screen not in _TEXT_SCREENS
    middle: int = (rows - len(keys) - 1) // 2 - heading if query else (rows - len(keys) - height) // 2
    start: int = max(min(middle, rows - FOOTER_ROWS - height), 0)
    if snapshot.fill:
        start = _filled_start(snapshot)
    canvas.top = start + heading
    if not query:
        canvas.center(start + 1, Text(snapshot.global_status, _COLORS[snapshot.status_kind]))
    if not query and start >= 0:
        canvas.center(start, Text(_context(snapshot), "white_bold"))
        mark_crumbs(canvas.lines[start], snapshot.crumbs)
    title_width: int = 0
    if query:
        _query(canvas, snapshot)
    elif listed:
        title_width = _list(canvas, snapshot, visible)
    else:
        title_width = _table(canvas, snapshot, visible, now)
    _footer(canvas, snapshot, keys, title_width, now, visible)
    return canvas.finish(visible, snapshot.selection, canvas.top)


def _query(canvas: _Canvas, snapshot: AnimeSnapshot) -> None:
    canvas.center(canvas.top - _QUERY_HEADING_ROWS, Text(_QUERY_TITLE, "white_bold"))
    if snapshot.busy:
        canvas.center(canvas.top, Text(snapshot.busy, "brand_accent"))
        return
    left: int = query_left(canvas.width, snapshot.field)
    canvas.write(canvas.top, left, Text("> ", "brand_accent" if snapshot.query_focused else "gray"), selectable=False)
    canvas.write(canvas.top, left + 2, (snapshot.rendered_field or Text(snapshot.field)).copy(), selectable=True)


def _list(canvas: _Canvas, snapshot: AnimeSnapshot, visible: int) -> int:
    items: tuple[AnimeRow, ...] = snapshot.items[snapshot.offset : snapshot.offset + visible]
    draft: bool = snapshot.screen is AnimeScreen.DRAFT
    prefix: int = 2 if snapshot.screen is AnimeScreen.FILES or draft else 0
    boxed: int = 4 if draft and any(item.number for item in items) else 0
    block: list[AnimeRow] = [item for item in items if not (draft and item.key.startswith("line"))]
    canvas.place(max((Text(item.title).cell_len for item in block), default=0) + prefix + boxed)
    for index, item in enumerate(items):
        row: int = canvas.top + index
        canvas.tag(row, index + snapshot.offset)
        active: bool = index + snapshot.offset == snapshot.cursor and item.navigable
        style: str = "white_bold"
        if draft:
            style = "brand_accent" if active else "white_bold" if item.navigable else "gray"
        if draft and item.key.startswith("line"):
            canvas.center(row, Text(item.title, style), selectable=True)
            continue
        if prefix and active:
            canvas.put(row, 0, _pointer(active=True), "brand_accent")
        box: int = boxed if item.number else 0
        if box:
            marked: bool = item.key in snapshot.selected
            canvas.put(row, prefix, "[x]" if marked else "[ ]", "brand_accent" if marked else "gray")
        canvas.put(
            row,
            prefix + box if item.navigable or not draft else 0,
            item.title,
            style,
            selectable=snapshot.screen is not AnimeScreen.BUSY and (not draft or bool(item.number)),
        )
    return canvas.columns - prefix


def _spec(screen: AnimeScreen) -> _Table:
    if screen in {AnimeScreen.ENTRIES, AnimeScreen.TITLES}:
        return _Table(
            ("Premiera", "Tytuł", "Typ", "Status"), lambda item: (item.date, item.title, item.kind, item.status), 2, 1
        )
    if screen is AnimeScreen.RELEASES:
        return _Table(
            ("Wydanie", "Obraz", "Rozmiar", "Język", "Seedy", "Jakość", "Pewność"),
            lambda item: (
                item.title,
                item.image,
                item.size,
                item.language,
                item.seeds.rjust(5),
                item.quality.rjust(6),
                item.confidence,
            ),
            8,
            0,
            (0, 5, 0, Text("PL · MultiSub").cell_len, 5, 6, 7),
            optional=(2, 3, 1, 4),
            right=(2,),
        )
    if screen is AnimeScreen.SUBSCRIPTIONS:
        return _Table(
            ("Tytuł", "Odcinki", "Gotowe", "Stan"),
            lambda item: (item.title, item.number, item.ready, item.status),
            2,
            0,
            status_width=_SUBSCRIPTION_STATUS_WIDTH,
            optional=(2, 1),
        )
    if screen is AnimeScreen.LIBRARY:
        return _Table(("Nazwa", "Odcinek"), lambda item: (item.title, item.number), 2, 0, (0, 0))
    return _Table(
        ("Nr", "Tytuł", "Emisja", "Stan"),
        lambda item: (item.number, item.title, item.date, item.status),
        6,
        1,
        status_width=_EPISODE_STATUS_WIDTH,
    )


def _values(snapshot: AnimeSnapshot, item: AnimeRow, now: float) -> list[str]:
    values: list[str] = list(_spec(snapshot.screen).values(item))
    if snapshot.screen is AnimeScreen.EPISODES and item.key in snapshot.searching:
        values[-1] = f"{spinner_frame(now)} szukam"
    return values


def _widths(snapshot: AnimeSnapshot, spec: _Table, limit: int, now: float, visible: int) -> tuple[list[int], list[int]]:
    widths: list[int] = [
        max(Text(label).cell_len, minimum) for label, minimum in zip(spec.labels, spec.minimums, strict=True)
    ]
    for item in snapshot.items[snapshot.offset : snapshot.offset + visible]:
        for position, value in enumerate(_values(snapshot, item, now)):
            widths[position] = max(widths[position], Text(value).cell_len)
    if spec.status_width:
        widths[-1] = spec.status_width
    if snapshot.screen is AnimeScreen.RELEASES:
        widths[-1] = min(widths[-1], limit - spec.prefix - len("Wydanie") - len("Jakość") - 4)
    shown: list[int] = list(range(len(widths)))
    floor: list[int] = list(widths)
    floor[spec.title] = min(widths[spec.title], _TITLE_FLOOR)
    for position in spec.optional:
        if _table_width(spec, floor, shown) <= limit:
            break
        shown.remove(position)
    total: int = _table_width(spec, widths, shown)
    if total > limit:
        widths[spec.title] = max(widths[spec.title] - (total - limit), Text(spec.labels[spec.title]).cell_len)
    return widths, shown


def _table_width(spec: _Table, widths: list[int], shown: list[int]) -> int:
    return spec.prefix + sum(widths[position] for position in shown) + 2 * (len(shown) - 1)


def _table(canvas: _Canvas, snapshot: AnimeSnapshot, visible: int, now: float) -> int:
    spec: _Table = _spec(snapshot.screen)
    widths, shown = _widths(snapshot, spec, canvas.width - _MARGIN, now, visible)
    canvas.place(_table_width(spec, widths, shown))
    columns: list[tuple[int, int, int]] = []
    column: int = spec.prefix
    for position in shown:
        columns.append((position, column, widths[position]))
        label: str = spec.labels[position]
        canvas.put(canvas.top - 1, column, label.rjust(widths[position]) if position in spec.right else label, "gray")
        column += widths[position] + 2
    for index, item in enumerate(snapshot.items[snapshot.offset : snapshot.offset + visible], snapshot.offset):
        _item(canvas, snapshot, item, index, now, tuple(columns))
    return widths[spec.title]


def _pointer(*, active: bool) -> str:
    pointer: Text = Text()
    append_wrapped_row(pointer, 0, ("",), active, "")
    return pointer.plain.rstrip("\n")


def _item(  # noqa: PLR0913
    canvas: _Canvas,
    snapshot: AnimeSnapshot,
    item: AnimeRow,
    index: int,
    now: float,
    columns: tuple[tuple[int, int, int], ...],
) -> None:
    row: int = canvas.top + index - snapshot.offset
    canvas.tag(row, index)
    active: bool = index == snapshot.cursor and item.navigable
    canvas.put(row, 0, _pointer(active=active), "brand_accent" if active else "white_bold")
    if snapshot.screen in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}:
        canvas.put(
            row,
            4 if snapshot.screen is AnimeScreen.RELEASES else 2,
            "[x]"
            if item.key in snapshot.selected
            else "[ ]"
            if item.eligible or (snapshot.screen is AnimeScreen.EPISODES and item.navigable)
            else "   ",
            "brand_accent" if item.key in snapshot.selected else "gray",
        )
    if snapshot.screen is AnimeScreen.RELEASES:
        canvas.put(row, 2, ("*" if item.suggested else " ") + ("!" if item.uncertain else " "), "warning")
    searching: bool = item.key in snapshot.searching
    values: list[str] = _values(snapshot, item, now)
    right: tuple[int, ...] = _spec(snapshot.screen).right
    for position, start, width in columns:
        value: str = values[position].rjust(width) if position in right else values[position]
        status: bool = position == len(values) - 1
        downloaded: bool = snapshot.screen is AnimeScreen.SUBSCRIPTIONS and position == 1 and not value.startswith("0/")
        canvas.put(
            row,
            start,
            fit(value, width),
            "success" if downloaded else _value_style(value, active=active, item=item, searching=searching and status),
            selectable=not (searching and status),
        )


def _value_style(value: str, *, active: bool, item: AnimeRow, searching: bool) -> str:
    if not item.navigable or value == "Nie wyemitowano":
        return "gray"
    if value.startswith("Błąd"):
        return "error"
    if value in {"Brak wydania", "Nieznany", "Problem"}:
        return "warning"
    if searching:
        return "brand_accent"
    if value in {"Zlecono", "Pobrano", "Gotowe"}:
        return "success"
    return "brand_accent" if active else "white_bold"


def _number_ranges(numbers: list[str]) -> list[str]:
    runs: list[list[str]] = []
    for number in numbers:
        previous: str = runs[-1][-1] if runs else ""
        if previous.isdigit() and number.isdigit() and int(number) == int(previous) + 1:
            runs[-1].append(number)
        else:
            runs.append([number])
    return [run[0] if len(run) == 1 else f"{run[0]}-{run[-1]}" for run in runs]


def _footer(  # noqa: PLR0913
    canvas: _Canvas, snapshot: AnimeSnapshot, keys: tuple[str, ...], title_width: int, now: float, visible: int
) -> None:
    selected: list[str] = [item.number for item in snapshot.items if item.key in snapshot.selected]
    summary: Text = Text(
        f"Zaznaczone: {len(selected)} ({', '.join(_number_ranges(selected))})"
        if selected and snapshot.screen is AnimeScreen.EPISODES
        else "",
        style="brand_accent",
    )
    if snapshot.editing_range:
        summary = Text("Zakres: ", style="brand_accent")
        summary.append_text(snapshot.rendered_field or Text(snapshot.field))
    summary.truncate(canvas.width - _MARGIN, overflow="ellipsis")
    notice: str = snapshot.notice
    if not notice and snapshot.items and snapshot.screen is not AnimeScreen.QUERY:
        item: AnimeRow = snapshot.items[snapshot.cursor]
        full_name: bool = Text(item.title).cell_len > title_width and (
            snapshot.screen is AnimeScreen.RELEASES or not item.detail
        )
        notice = item.title if full_name else item.detail
        if snapshot.screen in {AnimeScreen.SUBSCRIPTIONS, AnimeScreen.RELEASES}:
            notice = _unshown(snapshot, item, canvas.width - _MARGIN, now, visible)
    color: str = _COLORS[snapshot.notice_kind]
    notice_rows: int = _FILL_NOTICE_ROWS if snapshot.fill else _NOTICE_ROWS
    lines: list[str] = _notice_lines(
        notice, canvas.width - _MARGIN, maximum=notice_rows + int(snapshot.screen is AnimeScreen.RELEASES)
    )
    bottom: int = len(canvas.lines) - len(keys)
    canvas.center(bottom - len(lines) - 1, summary, selectable=True)
    for index, line in enumerate(lines):
        canvas.center(bottom - len(lines) + index, Text(line, style=color), selectable=True)
    for index, line in enumerate(keys):
        canvas.center(bottom + index, Text(line, style="gray"))


def _unshown(snapshot: AnimeSnapshot, item: AnimeRow, limit: int, now: float, visible: int) -> str:
    spec: _Table = _spec(snapshot.screen)
    widths, shown = _widths(snapshot, spec, limit, now, visible)
    values: list[str] = _values(snapshot, item, now)
    parts: list[str] = []
    if snapshot.screen is AnimeScreen.SUBSCRIPTIONS and (item.detail or Text(values[-1]).cell_len > widths[-1]):
        parts.append(item.detail or values[-1])
    hidden: list[int] = sorted(position for position in spec.optional if position not in shown)
    parts.extend(f"{spec.labels[position].lower()} {values[position].strip()}" for position in hidden)
    if item.note:
        parts.append(item.note)
    if snapshot.screen is AnimeScreen.RELEASES and Text(values[-1]).cell_len > widths[-1]:
        parts.append(f"pewność {values[-1]}")
    if Text(item.title).cell_len > widths[spec.title]:
        parts.append(item.title)
    if snapshot.screen is AnimeScreen.RELEASES and not parts:
        parts.append(item.detail)
    return " · ".join(parts)


def _notice_lines(notice: str, width: int, *, maximum: int = _NOTICE_ROWS) -> list[str]:
    if not notice:
        return []
    lines: list[str] = [line.plain for line in Text(notice).wrap(Console(width=width), width)]
    if len(lines) > maximum:
        lines = [*lines[: maximum - 1], fit(" ".join(line.strip() for line in lines[maximum - 1 :]), width)]
    return [line.strip().removeprefix("· ").removesuffix(" ·") for line in lines]


def _key_lines(snapshot: AnimeSnapshot, width: int) -> tuple[str, ...]:
    keys: tuple[str, ...] = ("Enter zastosuj", "Esc anuluj") if snapshot.editing_range else snapshot.controls
    return pack_footer(keys or ("Esc wróć",), width)


def spinner_frame(now: float) -> str:
    """Render Rich's dots animation at ten frames per second from an explicit clock."""
    spinner: Spinner = Spinner("dots", speed=0.8)
    spinner.start_time = 0
    return str(spinner.render(now))
