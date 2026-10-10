"""Presentation snapshots and local selection for the Anime panel."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

from rich.text import Text

from anishift.cli.interactive.text_input import TextInput

# ── Constants ─────────────────────────────────────────────────────────────────

FLASH_SECONDS: Final[float] = 0.4
"""Duration of the acknowledgement highlight after a confirmed admission."""

_QUERY_CELLS: Final[int] = 32
"""Width of the centered search box before the typed text widens it."""

_RANGE_COLUMNS: Final[int] = 80
"""Widest terminal width used to size the episode range editor."""


def query_left(columns: int, text: str) -> int:
    """Return the prompt column of a search box centered on at least 32 cells."""
    return max((columns - min(max(len(text) + 3, _QUERY_CELLS), columns)) // 2, 0)


class AnimeScreen(StrEnum):
    """Identify the presentation without owning catalogue or transfer state."""

    QUERY = "query"
    TITLES = "titles"
    ENTRIES = "entries"
    EPISODES = "episodes"
    RELEASES = "releases"
    DETAILS = "details"
    FILES = "files"
    BUSY = "busy"
    PROBLEM = "problem"
    DRAFT = "draft"
    SUBSCRIPTIONS = "subscriptions"


class NoticeKind(StrEnum):
    """Describe feedback independently of its displayed wording."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class AnimeRow:
    """Carry display values and eligibility supplied by the owner or fixture."""

    key: str
    title: str
    number: str = ""
    date: str = ""
    kind: str = ""
    status: str = ""
    image: str = ""
    language: str = ""
    seeds: str = ""
    progress: str = ""
    ready: str = ""
    detail: str = ""
    eligible: bool = True
    suggested: bool = False
    uncertain: bool = False
    navigable: bool = True
    refusal_text: str = ""
    quality: str = ""
    confidence: str = ""
    note: str = ""

    @property
    def copy_text(self) -> str:
        """Return the full textual row without presentation markers."""
        return " · ".join(
            value
            for value in (
                self.number,
                self.title,
                self.date,
                self.kind,
                self.status,
                self.image,
                self.language,
                self.seeds,
                self.progress,
                self.ready,
                f"Jakość: {self.quality}" if self.quality else "",
                f"Pewność: {self.confidence}" if self.confidence else "",
            )
            if value
        )

    @property
    def refusal(self) -> str:
        """Explain why an ineligible row cannot be selected or downloaded."""
        return (
            self.refusal_text
            or self.detail
            or ("Nie wyemitowano" if self.status == "Nie wyemitowano" else "Zlecono | P pobierz ponownie")
        )


@dataclass(frozen=True, slots=True, order=True)
class TextPoint:
    """Address a terminal cell in reading order."""

    row: int
    column: int


@dataclass(frozen=True, slots=True)
class AnimeSnapshot:
    """Freeze all inputs needed for a deterministic frame."""

    screen: AnimeScreen
    title: str
    items: tuple[AnimeRow, ...] = ()
    cursor: int = 0
    offset: int = 0
    selected: frozenset[str] = frozenset()
    searching: frozenset[str] = frozenset()
    flashes: tuple[tuple[str, float], ...] = ()
    notice: str = ""
    notice_kind: NoticeKind = NoticeKind.INFO
    field: str = ""
    field_cursor: int = 0
    field_selection: tuple[int, int] | None = None
    query_focused: bool = True
    editing_range: bool = False
    selection: tuple[TextPoint, TextPoint] | None = None
    controls: tuple[str, ...] = ()
    global_status: str = ""
    status_kind: NoticeKind = NoticeKind.WARNING
    rendered_field: Text | None = None
    busy: str = ""


@dataclass(slots=True)
class AnimeViewState:
    """Keep transient input, cursor and feedback independently of the owner."""

    screen: AnimeScreen = AnimeScreen.QUERY
    title: str = "ANIME"
    items: tuple[AnimeRow, ...] = ()
    cursor: int = 0
    offset: int = 0
    selected: set[str] = field(default_factory=set)
    searching: set[str] = field(default_factory=set)
    flashes: dict[str, float] = field(default_factory=dict)
    notice: str = ""
    notice_kind: NoticeKind = NoticeKind.INFO
    batch_results: dict[str, str | None] = field(default_factory=dict)
    query: TextInput = field(default_factory=TextInput)
    range_input: TextInput | None = None
    query_focused: bool = True
    selection: tuple[TextPoint, TextPoint] | None = None
    controls: tuple[str, ...] = ()
    global_status: str = ""
    status_kind: NoticeKind = NoticeKind.WARNING
    busy: str = ""

    def snapshot(self, width: int = 80) -> AnimeSnapshot:
        """Freeze local values without changing state or reading a clock."""
        editor: TextInput = self.range_input or self.query
        return AnimeSnapshot(
            screen=self.screen,
            title=self.title,
            items=self.items,
            cursor=self.cursor,
            offset=self.offset,
            selected=frozenset(self.selected),
            searching=frozenset(self.searching),
            flashes=tuple(self.flashes.items()),
            notice=self.notice,
            notice_kind=self.notice_kind,
            field=editor.text,
            field_cursor=editor.cursor,
            field_selection=editor.selection_range,
            query_focused=self.query_focused,
            editing_range=self.range_input is not None,
            selection=self.selection,
            controls=self.controls,
            global_status=self.global_status,
            status_kind=self.status_kind,
            rendered_field=editor.render(
                max(min(width, _RANGE_COLUMNS) - 12, 1)
                if self.range_input is not None
                else max(width - query_left(width, editor.text) - 3, 1),
                focused=self.query_focused or self.range_input is not None,
            ),
            busy=self.busy,
        )

    def toggle(self) -> None:
        """Toggle an eligible row without submitting an operation."""
        if not self.items or self.searching:
            return
        item: AnimeRow = self.items[self.cursor]
        if not item.eligible:
            self.notice = item.refusal
            return
        if item.key in self.selected:
            self.selected.remove(item.key)
            return
        if self.screen is AnimeScreen.RELEASES:
            self.selected.clear()
        self.selected.add(item.key)

    def select_all(self) -> None:
        """Toggle the eligible episode set only."""
        if self.searching or self.screen is not AnimeScreen.EPISODES:
            return
        eligible: set[str] = {item.key for item in self.items if item.eligible}
        self.selected = set() if eligible <= self.selected else eligible

    def apply_range(self, value: str) -> bool:
        """Replace the draft using exact displayed numbers, including fractional specials."""
        try:
            chosen: set[str] = _range_keys(value, self.items)
        except ValueError:
            self.notice = "Zakres: podaj 1,3,7.5 albo 5-"
            return False
        self.selected = chosen
        self.range_input = None
        self.notice = ""
        return True


def _range_keys(value: str, items: tuple[AnimeRow, ...]) -> set[str]:
    numbers: dict[Decimal, AnimeRow] = {}
    for item in items:
        try:
            numbers[Decimal(item.number)] = item
        except InvalidOperation:
            continue
    selected: set[str] = set()
    for part in value.split(","):
        match: re.Match[str] | None = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?)?)?\s*", part)
        if match is None:
            raise ValueError
        first: Decimal = Decimal(match[1])
        last: Decimal = Decimal(match[2]) if match[2] else max(numbers, default=first) if "-" in part else first
        if first not in numbers or last not in numbers or last < first:
            raise ValueError
        selected.update(item.key for number, item in numbers.items() if first <= number <= last and item.eligible)
    return selected
