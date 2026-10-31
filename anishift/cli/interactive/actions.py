"""Screen actions shared by panel footers and the ? help."""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from rich.cells import cell_len
from rich.text import Text

from anishift.cli.interactive.menu import pack_keys

# ── Constants ─────────────────────────────────────────────────────────────────

type Action = tuple[str, str]
"""One key and its Polish label, as shown in a footer or help."""

EVERYWHERE: Final[tuple[Action, ...]] = (
    ("↑↓", "wybierz"),
    ("←→ Tab", "zakładki"),
    ("O", "automat"),
    ("Esc", "wróć"),
)
"""Keys working on every panel screen, listed at the end of each help."""

MORE: Final[str] = "? klawisze"
"""Footer hint opening the help of the current screen."""

_DESCRIPTION_MIN: Final[int] = 24
"""Fewest cells the description column keeps beside its key; below that it moves under the key."""

ACTION_NOTICES: Final[frozenset[str]] = frozenset({"Ctrl+Z cofnij", "P pobierz ponownie"})
"""Key hints a notice may end with, clickable like the footer."""

PANEL_ACTIONS: Final[tuple[Action, ...]] = (("M", "ręczny"), ("U", "ustawienia"))
"""Mode switches listed under ? on every list outside Anime."""

_DESCRIPTIONS: Final[dict[Action, str]] = {
    ("Enter", "szczegóły"): "Otwiera listę odcinków wybranej subskrypcji",
    ("Enter", "otwórz"): "Otwiera wybrany odcinek albo wpis",
    ("Enter", "otwórz plik"): "Otwiera wybrany plik zestawu",
    ("Enter", "obejrzyj"): "Odtwarza gotowy odcinek",
    ("Enter", "wskaż plik"): "Pokazuje pliki paczki, żeby wybrać właściwy odcinek",
    ("Enter", "odcinki"): "Pokazuje odcinki wybranego wpisu",
    ("Enter", "wybierz"): "Otwiera albo wykonuje wybrany wiersz",
    ("Enter", "szukaj"): "Szuka wpisanego tytułu",
    ("Enter", "pobierz mimo to"): "Pobiera wydanie mimo niepewności, że to właściwy odcinek",
    ("Enter", "sprawdź wynik"): "Sprawdza wynik ostatniej partii pobrań",
    ("Space", "zaznacz"): "Zaznacza wiersz, żeby D pobrało kilka naraz",
    ("D", "pobierz"): "Pobiera zaznaczone odcinki albo wybrane wydanie",
    ("D", "dodaj"): "Przechodzi do wyszukiwarki, żeby dodać subskrypcję",
    ("D", "dodaj pierwszą"): "Przechodzi do wyszukiwarki, żeby dodać subskrypcję",
    ("W", "wstrzymaj"): "Wstrzymuje automatyczne pobieranie tej pozycji",
    ("W", "wznów"): "Wznawia automatyczne pobieranie tej pozycji",
    ("R", "sprawdź teraz"): "Od razu szuka nowych odcinków tej subskrypcji",
    ("Del", "usuń"): "Usuwa wybraną pozycję; Ctrl+Z ją przywraca",
    ("X", "anuluj"): "Anuluje pobieranie albo przetwarzanie, po potwierdzeniu Enterem",
    ("Ctrl+Z", "cofnij"): "Przywraca ostatnio usuniętą pozycję",
    ("M", "ręczny"): "Otwiera tryb Ręczny dla plików z folderu AniShift",
    ("U", "ustawienia"): "Otwiera Ustawienia",
    ("H", "historia"): "Pokazuje ukończone i przerwane prace z 30 dni",
    ("H", "zamknij"): "Wraca z Historii do bieżącej pracy",
    ("P", "ponów"): "Ponawia wybraną pracę; w Historii najpierw pokazuje propozycję",
    ("P", "ponownie"): "Pobiera odcinek jeszcze raz",
    ("P", "pobierz ponownie"): "Otwiera wydania do ponownego pobrania odcinka",
    ("/", "szukaj"): "Otwiera wyszukiwarkę",
    ("F", "folder"): "Pokazuje plik w Eksploratorze",
    ("I", "wydania"): "Pokazuje wydania wybranego odcinka",
    ("Z", "zakres"): "Zaznacza odcinki po numerach, np. 1-5",
    ("A", "wszystkie"): "Zaznacza albo odznacza wszystkie odcinki",
    ("S", "subskrybuj"): "Dodaje subskrypcję tego sezonu",
    ("T", "pobierz teraz"): "Pobiera od razu, bez czekania na polskie napisy",
    ("C", "kopiuj"): "Kopiuje tekst wybranego wiersza",
    ("↑↓", "wybierz"): "Przesuwa kursor po liście",
    ("←→ Tab", "zakładki"): "Przełącza zakładki panelu",
    ("O", "automat"): "Włącza albo wyłącza cały automat",
    ("Esc", "wróć"): "Wraca poziom wyżej",
}
"""One sentence on what each key does, shown beside it in the ? help."""


@dataclass(frozen=True, slots=True)
class ScreenActions:
    """Name a screen's footer actions in priority order and the actions listed only in its help."""

    footer: tuple[Action, ...] = ()
    more: tuple[Action, ...] = ()

    @property
    def listed(self) -> tuple[Action, ...]:
        """Return every action of the screen in priority order."""
        return (*self.footer, *self.more)


def footer_segments(actions: ScreenActions, *, more: bool = True) -> tuple[str, ...]:
    """Build footer hints: footer actions, then ? klawisze and Esc wróć, merged with an Enter that also goes back."""
    shown: list[str] = [f"{key} {label}" for key, label in actions.footer]
    escape: tuple[str, ...] = ("Esc wróć",)
    if shown and shown[0] == "Enter wróć":
        shown[0], escape = "Enter/Esc wróć", ()
    return (*shown, *((MORE,) if more else ()), *escape)


def pack_footer(segments: Sequence[str], width: int) -> tuple[str, ...]:
    """Pack footer hints into two lines, dropping actions from the end but never ? or Esc."""
    optional: tuple[str, ...] = tuple(
        segment for segment in reversed(segments) if not segment.startswith(("?", "Esc", "Enter/Esc"))
    )
    return pack_keys(segments, width, optional=optional)


def help_lines(actions: Sequence[Action], width: int, *, intro: Sequence[str] = ()) -> tuple[str, ...]:
    """List the actions of this screen and of every screen as a table of key, action and what it does."""
    sections: tuple[tuple[str, Sequence[Action]], ...] = (("Ten ekran", actions), ("Wszędzie", EVERYWHERE))
    keys: int = max(cell_len(key) for _title, rows in sections for key, _label in rows)
    labels: int = max(cell_len(label) for _title, rows in sections for _key, label in rows)
    lines: list[str] = list(intro)
    for title, rows in sections:
        if not rows:
            continue
        lines.append(title)
        for key, label in rows:
            lines.extend(_help_row(key, label, keys, labels, width))
    return tuple(lines)


def _help_row(key: str, label: str, keys: int, labels: int, width: int) -> list[str]:
    lead: str = f"  {key}{' ' * (keys - cell_len(key))}  {label}{' ' * (labels - cell_len(label))}  "
    description: str = _DESCRIPTIONS.get((key, label), "")
    room: int = width - cell_len(lead)
    if not description or room < _DESCRIPTION_MIN:
        rows: list[str] = [_cropped(lead.rstrip(), width)]
        indent: str = " " * (4 + keys)
        rows.extend(indent + part for part in textwrap.wrap(description, max(width - len(indent), 1)))
        return rows
    parts: list[str] = textwrap.wrap(description, room)
    return [lead + parts[0], *(" " * cell_len(lead) + part for part in parts[1:])]


def _cropped(line: str, width: int) -> str:
    shown: Text = Text(line)
    shown.truncate(max(width, 1), overflow="crop")
    return shown.plain
