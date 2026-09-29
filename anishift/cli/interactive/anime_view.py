"""Pure terminal layout with explicit text-only mouse hit regions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from rich.text import Text

from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeSnapshot, NoticeKind, TextPoint
from anishift.text.graphemes import split_graphemes

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_COLUMNS: Final[int] = 50
"""Minimum supported terminal width."""

WIDE_COLUMNS: Final[int] = 80
"""Width at which the keyboard footer occupies one row."""

HEADER_ROWS: Final[int] = 5
"""Fixed first data-row offset, independent of selection and feedback."""

MIN_ROWS: Final[int] = 12
"""Minimum height retaining a data row and all footer regions."""

SPINNER: Final[str] = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
"""Braille spinner advancing at ten frames per second without changing geometry."""


@dataclass(frozen=True, slots=True)
class TextCell:
    """Map one selectable grapheme to screen cells and Rich character offsets."""

    point: TextPoint
    width: int
    start: int
    end: int
    text: str


@dataclass(frozen=True, slots=True)
class AnimeFrame:
    """Return the painted frame and its text-only interaction geometry."""

    text: Text
    cells: tuple[TextCell, ...]
    visible: int
    first_row: int = HEADER_ROWS

    def selected_cells(self, selection: tuple[TextPoint, TextPoint] | None) -> tuple[TextCell, ...]:
        """Return whole graphemes intersected by an inclusive reading-order selection."""
        if selection is None:
            return ()
        start, end = sorted(selection)
        return tuple(
            cell
            for cell in self.cells
            if cell.point <= end and TextPoint(cell.point.row, cell.point.column + cell.width) > start
        )

    def selected_text(self, selection: tuple[TextPoint, TextPoint] | None) -> str:
        """Copy text in reading order while omitting markers, borders and padding."""
        lines: dict[int, list[str]] = {}
        previous: TextCell | None = None
        for cell in self.selected_cells(selection):
            line: list[str] = lines.setdefault(cell.point.row, [])
            if previous is not None and previous.point.row == cell.point.row and previous.end != cell.start:
                line.append(" ")
            line.append(cell.text)
            previous = cell
        return "\n".join("".join(line).strip() for line in lines.values()).strip()


class _Canvas:
    def __init__(self, columns: int, rows: int) -> None:
        self.columns: int = columns
        self.lines: list[Text] = [Text(" " * columns, style="anime_base") for _ in range(rows)]
        self.regions: list[tuple[int, int, str]] = []

    def put(self, row: int, column: int, value: str, style: str = "anime_text", *, selectable: bool = False) -> None:
        if not 0 <= row < len(self.lines) or column >= self.columns:
            return
        value = fit(value, self.columns - column)
        line: Text = self.lines[row]
        prefix: Text = line[: _character_offset(line.plain, column)]
        prefix.append(value, style)
        prefix.append(line[_character_offset(line.plain, column + Text(value).cell_len) :])
        self.lines[row] = prefix
        if selectable:
            self.regions.append((row, column, value))

    def finish(self, visible: int, selection: tuple[TextPoint, TextPoint] | None) -> AnimeFrame:
        cells: list[TextCell] = []
        offsets: list[int] = []
        offset: int = 0
        for line in self.lines:
            offsets.append(offset)
            offset += len(line.plain) + 1
        for row, column, value in sorted(self.regions):
            index: int = _character_offset(self.lines[row].plain, column)
            cell_column: int = column
            for grapheme in split_graphemes(value):
                width: int = Text(grapheme).cell_len
                cells.append(
                    TextCell(
                        TextPoint(row, cell_column),
                        width,
                        offsets[row] + index,
                        offsets[row] + index + len(grapheme),
                        grapheme,
                    )
                )
                cell_column += width
                index += len(grapheme)
        text: Text = Text("\n").join(self.lines)
        frame: AnimeFrame = AnimeFrame(text, tuple(cells), visible)
        for cell in frame.selected_cells(selection):
            text.stylize("anime_selection", cell.start, cell.end)
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


def _character_offset(value: str, column: int) -> int:
    used: int = 0
    index: int = 0
    for grapheme in split_graphemes(value):
        if used >= column:
            break
        used += Text(grapheme).cell_len
        index += len(grapheme)
    return index


def render_anime(snapshot: AnimeSnapshot, columns: int, rows: int, now: float) -> AnimeFrame:
    """Render one immutable snapshot using the caller's clock and terminal geometry."""
    canvas: _Canvas = _Canvas(max(columns, 1), max(rows, 1))
    if columns < MIN_COLUMNS or rows < MIN_ROWS:
        canvas.put(0, 0, "Powiększ terminal do 50 x 12", "anime_warning")
        return canvas.finish(0, None)
    canvas.put(0, 1, " Anime ", "anime_tab")
    canvas.put(0, 10, "Subskrypcje  Przetwarzanie  Biblioteka", "anime_muted")
    canvas.put(1, 0, "─" * columns, "anime_border")
    if snapshot.screen is not AnimeScreen.QUERY:
        canvas.put(2, 2, snapshot.title, "anime_heading", selectable=True)
    key_rows: int = 1 if columns >= WIDE_COLUMNS else 2
    footer: int = rows - key_rows - 3
    visible: int = max(footer - HEADER_ROWS, 0)
    if snapshot.screen is AnimeScreen.QUERY:
        _query(canvas, snapshot, footer)
    else:
        _table(canvas, snapshot, visible, now)
    canvas.put(footer, 0, "─" * columns, "anime_border")
    _footer(canvas, snapshot, footer, key_rows)
    return canvas.finish(visible, snapshot.selection)


def _query(canvas: _Canvas, snapshot: AnimeSnapshot, footer: int) -> None:
    width: int = min(canvas.columns - 6, 54)
    column: int = (canvas.columns - width) // 2 if snapshot.centered_query else 2
    row: int = min(max(4, footer // 2 - 1) if snapshot.centered_query else 4, footer - 4)
    canvas.put(row, column, "Szukaj anime", "anime_muted")
    canvas.put(row + 1, column, "┌" + "─" * (width - 2) + "┐", "anime_accent")
    canvas.put(row + 2, column, "│" + " " * (width - 2) + "│", "anime_accent")
    canvas.put(row + 3, column, "└" + "─" * (width - 2) + "┘", "anime_accent")
    _field(canvas, row + 2, column + 2, snapshot, width - 4)


def _field(canvas: _Canvas, row: int, column: int, snapshot: AnimeSnapshot, width: int) -> None:
    editor_text: Text = Text(snapshot.field)
    prefix: int = Text(snapshot.field[: snapshot.field_cursor]).cell_len
    offset: int = max(prefix - width + 1, 0)
    start: int = _character_offset(editor_text.plain, offset)
    value: str = fit(snapshot.field[start:], width)
    canvas.put(row, column, value, selectable=True)
    if not snapshot.query_focused and not snapshot.editing_range:
        return
    if snapshot.field_selection is not None:
        selection_start, selection_end = snapshot.field_selection
        left: int = column + max(Text(snapshot.field[:selection_start]).cell_len - offset, 0)
        right: int = column + min(Text(snapshot.field[:selection_end]).cell_len - offset, width)
        canvas.lines[row].stylize(
            "anime_selection",
            _character_offset(canvas.lines[row].plain, left),
            _character_offset(canvas.lines[row].plain, max(right, left)),
        )
    cursor: int = column + prefix - offset
    canvas.lines[row].stylize(
        "reverse",
        _character_offset(canvas.lines[row].plain, cursor),
        _character_offset(canvas.lines[row].plain, cursor + 1),
    )


def _columns(screen: AnimeScreen, width: int) -> tuple[tuple[str, int], ...]:
    if screen is AnimeScreen.ENTRIES:
        return (("Premiera", 2), ("Tytuł", 13), ("Typ", width - 21), ("Status", width - 13))
    if screen is AnimeScreen.RELEASES:
        return (("Wydanie", 8), ("Obraz", width - 26), ("Język", width - 19), ("Seedy", width - 9))
    return (("Nr", 6), ("Tytuł", 11), ("Emisja", width - 28), ("Stan", width - 17))


def _table(canvas: _Canvas, snapshot: AnimeSnapshot, visible: int, now: float) -> None:
    if snapshot.screen is AnimeScreen.DETAILS:
        for index, item in enumerate(snapshot.items[snapshot.offset : snapshot.offset + visible]):
            canvas.put(HEADER_ROWS + index, 2, item.title, selectable=True)
        return
    columns: tuple[tuple[str, int], ...] = _columns(snapshot.screen, canvas.columns)
    for label, column in columns:
        canvas.put(4, column, label, "anime_muted")
    for index, item in enumerate(snapshot.items[snapshot.offset : snapshot.offset + visible], snapshot.offset):
        _item(canvas, snapshot, item, index, now)


def _item(
    canvas: _Canvas,
    snapshot: AnimeSnapshot,
    item: AnimeRow,
    index: int,
    now: float,
) -> None:
    row: int = HEADER_ROWS + index - snapshot.offset
    columns: tuple[tuple[str, int], ...] = _columns(snapshot.screen, canvas.columns)
    style: str = "anime_active" if index == snapshot.cursor else "anime_base"
    if dict(snapshot.flashes).get(item.key, 0) > now:
        style = "anime_flash"
    canvas.lines[row] = Text(" " * canvas.columns, style=style)
    canvas.put(row, 0, ">" if index == snapshot.cursor else " ", style)
    if snapshot.screen in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}:
        canvas.put(
            row,
            3 if snapshot.screen is AnimeScreen.RELEASES else 2,
            ("[x]" if item.key in snapshot.selected else "[ ]") if item.eligible else "   ",
            "anime_accent" if item.key in snapshot.selected else "anime_muted",
        )
    status: str = f"{SPINNER[int(now * 10) % len(SPINNER)]} szukam" if item.key in snapshot.searching else item.status
    values: tuple[str, ...] = (item.number, item.title, item.date, status)
    if snapshot.screen is AnimeScreen.ENTRIES:
        values = (item.date, item.title, item.kind, item.status)
    elif snapshot.screen is AnimeScreen.RELEASES:
        values = (item.title, item.image, item.language, item.seeds.rjust(5))
        canvas.put(row, 1, "!" if item.uncertain else "*" if item.suggested else " ", "anime_warning")
    for position, ((_, column), value) in enumerate(zip(columns, values, strict=True)):
        gap: int = 2 if snapshot.screen is AnimeScreen.RELEASES else 1
        end: int = columns[position + 1][1] - gap if position + 1 < len(columns) else canvas.columns - 1
        color: str = "anime_success" if value in {"Zlecono", "Pobrano"} else "anime_text"
        if item.key in snapshot.searching and value == status:
            color = "anime_accent"
        if value in {"Brak wydania", "Nie wyemitowano", "Nieznany", "Problem"}:
            color = "anime_warning"
        canvas.put(
            row,
            column,
            fit(value, end - column),
            color,
            selectable=item.key not in snapshot.searching or value != status,
        )


def _footer(canvas: _Canvas, snapshot: AnimeSnapshot, footer: int, key_rows: int) -> None:
    selected: list[str] = [item.number for item in snapshot.items if item.key in snapshot.selected]
    summary: str = f"Zaznaczone: {len(selected)} ({', '.join(selected)})" if selected else ""
    if snapshot.screen is AnimeScreen.EPISODES:
        canvas.put(footer + 1, 1, summary, "anime_accent")
    notice: str = snapshot.notice
    if not notice and snapshot.items:
        item: AnimeRow = snapshot.items[snapshot.cursor]
        notice = item.detail or item.status
        columns: tuple[tuple[str, int], ...] = _columns(snapshot.screen, canvas.columns)
        position: int = 0 if snapshot.screen is AnimeScreen.RELEASES else 1
        gap: int = 2 if snapshot.screen is AnimeScreen.RELEASES else 1
        title_width: int = columns[position + 1][1] - columns[position][1] - gap
        if snapshot.screen is AnimeScreen.DETAILS:
            title_width = canvas.columns - 2
        if not notice and Text(item.title).cell_len > title_width:
            notice = item.title
    color: str = {
        NoticeKind.INFO: "anime_muted",
        NoticeKind.SUCCESS: "anime_success",
        NoticeKind.WARNING: "anime_warning",
    }[snapshot.notice_kind]
    canvas.put(footer + 2, 1, notice, color, selectable=True)
    keys: tuple[str, ...] = _keys(snapshot.screen, key_rows)
    if snapshot.editing_range:
        canvas.put(footer + 1, 1, "Zakres: " + " " * (canvas.columns - 9), "anime_accent")
        _field(canvas, footer + 1, 9, snapshot, canvas.columns - 10)
        keys = ("Enter zastosuj | Esc anuluj",)
    for index, value in enumerate(keys):
        canvas.put(footer + 3 + index, 1, value, "anime_muted")


def _keys(screen: AnimeScreen, rows: int) -> tuple[str, ...]:
    if screen is AnimeScreen.QUERY:
        return ("Enter szukaj",)
    if screen is AnimeScreen.ENTRIES:
        return ("Enter odcinki | / szukaj | ? więcej | Esc",)
    if screen is AnimeScreen.RELEASES:
        return ("Space zaznacz | D pobierz | ? więcej | Esc",)
    if screen is AnimeScreen.DETAILS:
        return ("C kopiuj | Ctrl+C kopiuj zaznaczenie | Esc",)
    if rows == 1:
        return ("Space zaznacz | D pobierz | I wydania | P ponownie | ? więcej | Esc",)
    return ("Space zaznacz | D pobierz | I wydania", "P ponownie | ? więcej | Esc")
