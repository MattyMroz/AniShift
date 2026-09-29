"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from time import time
from typing import Final

from natsort import natsorted
from rich.console import Console
from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AppService,
    CatalogOrder,
    DownloadReceipt,
    EntryGroup,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeRange,
    Franchise,
    FranchiseEntry,
    IdentityVerdict,
    ListedEpisode,
    RankedCandidate,
    RefusalReason,
    ReleaseCatalog,
    ReleaseChoice,
    SearchQuery,
    SeasonContext,
    SeriesGroup,
    SubscriptionOrder,
    TitleCandidate,
    TitleStatus,
    order_groups,
    parse_query,
    parse_release_name,
)
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.menu import with_footer
from anishift.cli.interactive.subscriptions import SubscriptionDraft
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError, ControlErrorCode
from anishift.utils.logger import get_logger

__all__ = ["AnimeController", "AnimeResult"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_TITLE: Final[str] = "ANIME"
"""Heading shown above every screen of this controller."""

_POINTER: Final[str] = "\u276f"
"""Marker placed before the highlighted release row."""

_BULLET: Final[str] = "▸"
"""Glyph opening one release row under its group header."""

_WORKER_NAME: Final[str] = "anishift-anime"
"""Name of the thread carrying every search and download of this screen."""

_MIN_RESOLUTION_LABEL: Final[str] = "1080p"
"""Lowest release quality the catalog lists, named for the user."""

_QUERY_HINT: Final[str] = "Enter edytuj · ←→ widok · Esc wróć"
"""Keyboard hint of the title input."""

_TITLES_HINT: Final[str] = "Enter wybierz · G wydania wg grup (stara wersja) · / szukaj · Esc wróć"
"""Keyboard hint of the title candidate list."""

_BUSY_HINT: Final[str] = "Esc anuluj"
"""Keyboard hint shown while the network thread works."""

_DONE_HINT: Final[str] = "dowolny klawisz: powrót"
"""Keyboard hint of the screen confirming the hand-off."""

_PROBLEM_HINT: Final[str] = "Enter wróć · Esc menu"
"""Keyboard hint of the screen reporting a failure."""

_RESUME_HINT: Final[str] = "Enter Wznów AniShift · Esc menu"
"""Explicit recovery action offered after a paused download refusal."""

_RESUMING: Final[str] = "Wznawiam AniShift…"
"""Sentence shown while the owner processes an explicit resume command."""

_SEARCHING_TITLE: Final[str] = "Szukam tytułu…"
"""Sentence shown while the anime catalog names the title behind the typed phrase."""

_SEARCHING_RELEASES: Final[str] = "Szukam wydań…"
"""Sentence shown while the release index answers for the chosen title."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
"""Sentence shown when the session was built without an acquisition boundary."""

_EPISODE_ONLY: Final[str] = "Subskrybuj działa tylko na numerowanym odcinku"
"""Notice shown when the highlighted release carries no episode number to watch from."""

_OTHER_SEASON: Final[str] = "To wydanie wygląda na inny sezon"
"""Notice shown when the highlighted release belongs to a season other than the chosen one."""

_NO_TITLE: Final[str] = "Brak tytułu w AniList, wyniki dla hasła"
"""Footer note shown when the title catalog knows no title and the raw phrase was searched instead."""

_RANGE_PROMPT: Final[str] = "zakres (np. 4-10)"
"""Question opening the footer prompt that marks a span of episodes."""

_RANGE_INVALID: Final[str] = "zakres: podaj np. 4-10"
"""Notice shown when the typed span cannot be read."""

_EMPTY_CATALOG: Final[str] = f"Brak wydań w {_MIN_RESOLUTION_LABEL}+ dla tego tytułu"
"""Sentence shown when the query matched nothing of the required quality."""

_EMPTY_FILTERED: Final[str] = "Brak odc. {episodes} w " + _MIN_RESOLUTION_LABEL + "+ dla tego tytułu"
"""Sentence shown when only the episode filter left the listing empty."""

_NO_SEASON_NUMBERING: Final[str] = "numeracja sezonu niedostępna"
"""Footer note shown when the season chain failed and episodes are numbered as named."""

_PROBLEM_TEXTS: Final[dict[ErrorCode, tuple[str, str]]] = {
    ErrorCode.TORRENT_SOURCE_FAILED: ("Źródło wydań nie odpowiada", "Sprawdź połączenie i spróbuj ponownie"),
    ErrorCode.EPISODE_CATALOG_FAILED: ("Lista odcinków niedostępna (ani.zip)", "Spróbuj ponownie"),
    ErrorCode.TORRENT_CLIENT_UNAVAILABLE: ("qBittorrent nie odpowiada", "Uruchom qBittorrenta z włączonym Web UI"),
    ErrorCode.TORRENT_CLIENT_UNAUTHORIZED: (
        "qBittorrent odrzucił logowanie",
        "Sprawdź login i hasło Web UI w pliku .env",
    ),
    ErrorCode.TORRENT_CLIENT_REFUSED: ("qBittorrent odrzucił żądanie", "Sprawdź ustawienia Web UI i spróbuj ponownie"),
    ErrorCode.TITLE_CATALOG_FAILED: ("AniList nie odpowiada", "Spróbuj ponownie za chwilę"),
}
"""Polish sentence and hint of every failure this screen can meet."""

_CHOICE_SEPARATOR: Final[str] = "  "
"""Separation between the facts of one release row."""

_HINT_SEPARATOR: Final[str] = " · "
"""Separation between the keyboard hints of one footer."""

_HEADER_ROWS: Final[int] = 7
"""Rows the heading, hint and footer take away from a list without its own measurement."""

_FULL_PICKER_ROWS: Final[int] = 11
"""Minimum height retaining the heading, releases, pinned actions and help."""

_STATUS_LABELS: Final[dict[TitleStatus, str]] = {
    TitleStatus.FINISHED: "zakończone",
    TitleStatus.RELEASING: "w emisji",
    TitleStatus.NOT_YET_RELEASED: "zapowiedź",
    TitleStatus.CANCELLED: "przerwane",
    TitleStatus.HIATUS: "przerwane",
}
"""Polish name of every airing state worth showing; an unknown one is left out of the row."""

_RANGE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:(?P<first>\d{1,4})(?P<dash>-)?(?P<last>\d{1,4})?|-(?P<upto>\d{1,4}))$"
)
"""Span typed in the footer: one episode, a closed span, an open end, or an upper bound."""

_COMMAND_FAILED: Final[str] = (
    "Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie."
)
"""Safe explanation shared by failed catalogue commands and local worker defects."""

_ENTRY_GROUPS: Final[dict[EntryGroup, str]] = {
    EntryGroup.SEASON: "SEZONY I CZĘŚCI",
    EntryGroup.EXTRA: "DODATKI",
    EntryGroup.OTHER: "FILMY I INNE",
}
"""Section headings of the franchise projection."""

_ENTRY_STATUSES: Final[dict[str, str]] = {
    "FINISHED": "zakończony",
    "RELEASING": "w emisji",
    "NOT_YET_RELEASED": "zapowiedź",
    "HIATUS": "przerwa w emisji",
    "CANCELLED": "anulowany",
    "UNKNOWN": "—",
}
"""Airing labels referring only to the displayed entry."""

_VERDICT_LABELS: Final[dict[IdentityVerdict, str]] = {
    IdentityVerdict.MATCH: "zgodny",
    IdentityVerdict.INSUFFICIENT: "niepewny",
    IdentityVerdict.MISMATCH: "niezgodny",
}
"""Polish identity labels, without confidence percentages."""

_DATE_COLUMNS: Final[int] = 75
"""Minimum episode view width retaining the local airing timestamp."""

_SEED_COLUMNS: Final[int] = 70
"""Minimum release row width retaining its seeder measurement."""

_SIZE_COLUMNS: Final[int] = 90
"""Minimum release row width retaining its approximate file size."""

_REASON_TEXTS: Final[dict[str, str]] = {
    "Mapped absolute number exceeds the local episode range under a specific title.": (
        "Numer absolutny wykracza poza zakres odcinków tego wpisu."
    ),
    "Named season, local episode and catalog episode title agree.": (
        "Sezon, numer lokalny i katalogowy tytuł odcinka są zgodne."
    ),
    "Season marker conflicts with the target numbering system.": (
        "Oznaczenie sezonu jest sprzeczne z numeracją szukanego odcinka."
    ),
    "Part/cour marker conflicts with the target.": "Oznaczenie części jest sprzeczne z wybranym wpisem.",
    "A franchise alias does not identify this installment.": "Nazwa franczyzy nie wskazuje jednoznacznie tego wpisu.",
    "The required part/cour is not established.": "Nie ustalono wymaganej części sezonu.",
    "Explicit mapped episode differs from target.": "Podany numer katalogowy wskazuje inny odcinek.",
    "Work anchor and exact mapped season/episode match; residual is technical or catalogued.": (
        "Tytuł oraz katalogowe numery sezonu i odcinka są zgodne; pozostały tekst jest rozpoznany."
    ),
    "Movie segment or numbering requires a more specific identity anchor.": (
        "Część lub numer filmu wymaga dokładniejszego potwierdzenia tożsamości."
    ),
    "Movie title matches with compatible year and no unidentified residual.": (
        "Tytuł filmu jest zgodny, rok nie jest sprzeczny i nie ma nierozpoznanego tekstu."
    ),
    "OVA/special needs a mapped episode or catalog episode title.": (
        "Dodatek wymaga numeru katalogowego lub katalogowego tytułu odcinka."
    ),
    "No unambiguous selected episode number.": "Brak jednoznacznego numeru wybranego odcinka.",
    "Bare number is not the local episode; absolute numbering is not established.": (
        "Numer nie pasuje do odcinka lokalnego; nie potwierdzono numeracji absolutnej."
    ),
    "Local and mapped numbering conflict.": "Numeracja lokalna i katalogowa są sprzeczne.",
    "Specific work title and local episode match; residual is technical or catalogued.": (
        "Dokładny tytuł i numer lokalny odcinka są zgodne; pozostały tekst jest rozpoznany."
    ),
    "Package directory explicitly identifies Plex extra material.": "Katalog paczki wskazuje materiał dodatkowy Plex.",
    "Package explicitly identifies a neighboring work.": "Paczka wskazuje inny powiązany tytuł.",
    "Package explicitly identifies a different season.": "Paczka wskazuje inny sezon.",
    "Package explicitly identifies a different part/cour.": "Paczka wskazuje inną część sezonu.",
    "Package explicitly identifies a different final season.": "Paczka wskazuje inny sezon finałowy.",
    "Package contains an unresolved sequel qualifier.": "Paczka zawiera niejednoznaczny dopisek sequela.",
    "Package localized season conflicts with the target or is unresolved.": (
        "Obcojęzyczne oznaczenie sezonu w paczce jest sprzeczne lub niejednoznaczne."
    ),
    "Package Roman season/part conflicts with the target or is unresolved.": (
        "Rzymski numer sezonu lub części w paczce jest sprzeczny lub niejednoznaczny."
    ),
    "Package ordinal part/cour conflicts with the target.": "Numer porządkowy części w paczce wskazuje inną część.",
    "Package localized movie format conflicts with the target.": (
        "Obcojęzyczne oznaczenie filmu w paczce nie pasuje do wybranego wpisu."
    ),
    "Package contains an unresolved continuation marker.": "Paczka zawiera niejednoznaczne oznaczenie ciągu dalszego.",
    "Package contains an uncatalogued title suffix.": "Paczka zawiera końcówkę tytułu nieznaną katalogowi.",
    "Package explicitly identifies a different language-specific media format.": (
        "Obcojęzyczne oznaczenie w paczce wskazuje inny rodzaj materiału."
    ),
    "Package season declaration conflicts with the target or is unresolved.": (
        "Deklaracja sezonu w paczce jest sprzeczna lub niejednoznaczna."
    ),
    "Package Russian season declaration is unresolved.": "Rosyjskie oznaczenie sezonu w paczce jest niejednoznaczne.",
    "Package explicitly identifies non-episode material.": "Paczka wskazuje materiał inny niż odcinek.",
    "Package explicitly identifies a different media type.": "Paczka wskazuje inny rodzaj materiału.",
    "Package year conflicts with target metadata.": "Rok paczki jest sprzeczny z metadanymi wybranego wpisu.",
    "Package explicitly identifies a numbered sequel.": "Paczka wskazuje numerowaną kontynuację.",
    "Titleless file lacks an unambiguous nearest work directory or single-work release.": (
        "Plik bez tytułu nie ma jednoznacznego katalogu ani wydania jednego tytułu."
    ),
    "Selected file or work directory identifies a neighboring catalogue work.": (
        "Wybrany plik lub katalog wskazuje inny tytuł katalogowy."
    ),
    "Selected directory has a numbered season conflicting with the target.": (
        "Numer sezonu w wybranym katalogu jest sprzeczny z wybranym odcinkiem."
    ),
    "Selected TV variant conflicts with the target editing variant.": (
        "Wariant telewizyjny pliku jest sprzeczny z wybraną wersją montażową."
    ),
    "Release editing variant is not established for the target episode.": (
        "Nie potwierdzono wersji montażowej wydania dla tego odcinka."
    ),
    "Malformed candidate metadata.": "Metadane wydania mają niepoprawny format.",
    "No selected file.": "Brak wskazanego pliku.",
    "Selected file has no allowed video extension.": "Wybrany plik nie ma dozwolonego rozszerzenia wideo.",
    "Malformed target or archived identity metadata.": "Metadane celu lub tożsamości mają niepoprawny format.",
    "Selected filename has an explicit Plex extra suffix.": "Nazwa pliku oznacza materiał dodatkowy Plex.",
    "Selected residual explicitly identifies non-episode material.": (
        "Dodatkowy tekst nazwy wskazuje materiał inny niż odcinek."
    ),
    "Unresolved leading bracket is the nearest identity context.": (
        "Nierozpoznany początkowy nawias uniemożliwia ustalenie tożsamości."
    ),
    "Selected filename more specifically identifies a neighboring work.": (
        "Dokładniejsza nazwa pliku wskazuje inny powiązany tytuł."
    ),
    "Filename year is missing from or conflicts with runtime target metadata.": (
        "Roku z nazwy pliku nie ma w metadanych celu albo jest z nimi sprzeczny."
    ),
    "Unconsumed filename text is neither technical metadata nor a catalog episode title.": (
        "Pozostały tekst nazwy nie jest metadanymi technicznymi ani katalogowym tytułem odcinka."
    ),
}
"""Translate every frozen H1 explanation at the UI boundary."""


class AnimeResult(StrEnum):
    """Signal whether the anime controller stays open or returns Home."""

    CONTINUE = "continue"
    HOME = "home"
    SUBSCRIBE = "subscribe"


class _Screen(StrEnum):
    QUERY = "query"
    TITLES = "titles"
    BUSY = "busy"
    RESULTS = "results"
    DONE = "done"
    PROBLEM = "problem"
    ENTRIES = "entries"
    EPISODES = "episodes"
    OFFER = "offer"
    CANDIDATES = "candidates"


class _Action(StrEnum):
    SELECT_ALL = "select_all"
    DOWNLOAD = "download"
    BACK = "back"


@dataclass(frozen=True, slots=True)
class _Listing:
    """How one catalog was asked for, carried from the worker thread into the screen state."""

    order: CatalogOrder
    episodes: EpisodeRange | None = None
    context: SeasonContext | None = None
    fallback: str = ""


@dataclass(frozen=True, slots=True)
class _Row:
    """One selectable group, release or explicit action."""

    label: str
    choice: ReleaseChoice | None = None
    group: int = 0
    detail: str = ""
    action: _Action | None = None


class AnimeController:
    """Own one ephemeral release search while AppService owns the network boundary."""

    def __init__(  # noqa: PLR0915
        self,
        service: AppService,
        invalidate: Callable[[], None],
        *,
        resident: ResidentSession | None = None,
    ) -> None:
        self._service: AppService = service
        self._resident: ResidentSession | None = resident
        self._acquisition: AcquisitionService | ResidentSession | None = resident or service.acquisition
        self._invalidate: Callable[[], None] = invalidate
        self._lock: threading.Lock = threading.Lock()
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._screen: _Screen = _Screen.QUERY
        self._query_input: TextInput = TextInput()
        self._input_focused: bool = False
        self._searched: str = ""
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._highlighted: int = 0
        self._candidate: TitleCandidate | None = None
        self._context: SeasonContext | None = None
        self._episodes: EpisodeRange | None = None
        self._order: CatalogOrder = CatalogOrder.NEWEST
        self._groups: tuple[SeriesGroup, ...] = ()
        self._opened_group: int | None = None
        self._rows: tuple[_Row, ...] = ()
        self._choices: tuple[int, ...] = ()
        self._marked: set[int] = set()
        self._recorded: dict[str, str] = {}
        self._downloaded: str | None = None
        self._selected: int = 0
        self._hidden: int = 0
        self._excluded: int = 0
        self._filtered: int = 0
        self._range_input: TextInput | None = None
        self._group_input: TextInput | None = None
        self._fallback: str = ""
        self._busy: str = _SEARCHING_TITLE
        self._done: str = ""
        self._notice: str = ""
        self._problem: str = ""
        self._suggestion: str = ""
        self._problem_return: _Screen = _Screen.QUERY
        self._resume_available: bool = False
        self._draft: SubscriptionDraft | None = None
        self._clock: Callable[[], float] = time
        self._franchise: Franchise | None = None
        self._entry: FranchiseEntry | None = None
        self._listing: EpisodeListing | None = None
        self._episode_marks: set[int] = set()
        self._offer_numbers: tuple[int, ...] = ()
        self._offers: dict[int, EpisodeOffer] = {}
        self._offers_running: bool = False
        self._release_candidates: tuple[RankedCandidate, ...] = ()
        self._positions: dict[_Screen, int] = {}
        self._offsets: dict[_Screen, int] = {}
        self._visible_count: int = 1
        self._follow_cursor: bool = True
        self._busy_return: _Screen = _Screen.QUERY
        self._provider_locks: dict[str, float] = {}
        self._problem_provider: str = ""
        if self._acquisition is None:
            self._screen = _Screen.PROBLEM
            self._problem = _UNAVAILABLE

    def handle_key(self, key: str) -> AnimeResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            if key in {"escape", "interrupt"}:
                self._downloaded = None
            if self._handle_input(key):
                return AnimeResult.CONTINUE
            if self._screen is _Screen.QUERY:
                result: AnimeResult = self._handle_query(key)
            elif self._screen is _Screen.TITLES:
                result = self._handle_titles(key)
            elif self._screen is _Screen.BUSY:
                result = self._handle_busy(key)
            elif self._screen is _Screen.RESULTS:
                result = self._handle_results(key)
            elif self._screen in {_Screen.ENTRIES, _Screen.EPISODES, _Screen.OFFER, _Screen.CANDIDATES}:
                self._handle_episode_screen(key)
                result = AnimeResult.CONTINUE
            elif self._screen is _Screen.DONE:
                self._screen = _Screen.RESULTS
                result = AnimeResult.CONTINUE
            else:
                result = self._handle_problem(key)
            if self._draft is not None:
                return AnimeResult.SUBSCRIBE
        return result

    def take_draft(self) -> SubscriptionDraft | None:
        """Consume a prepared subscription without storing or checking it."""
        with self._lock:
            draft: SubscriptionDraft | None = self._draft
            self._draft = None
            return draft

    def refresh_acquisitions(self, acquisitions: Sequence[Mapping[str, object]]) -> None:
        """Apply recorded owner facts without creating a local admission history."""
        with self._lock:
            self._recorded = {
                str(item["info_hash"]).casefold(): str(item.get("state", ""))
                for item in acquisitions
                if item.get("info_hash")
            }
            self._marked = {index for index in self._marked if not self._recorded_label(self._rows[index].choice)}

    def take_downloaded(self) -> str | None:
        """Consume completion only while its initiating generation remains current."""
        with self._lock:
            notice: str | None = self._downloaded
            self._downloaded = None
            return notice

    def refresh_provider_locks(self, locks: Sequence[Mapping[str, object]]) -> None:
        """Project owner retry deadlines without admitting or repeating a request."""
        deadlines: dict[str, float] = {}
        for item in locks:
            provider, until = item.get("provider"), item.get("until")
            if not isinstance(provider, str) or not isinstance(until, str):
                continue
            deadline: float | None = _deadline(until)
            if deadline is not None:
                deadlines[provider] = deadline
        with self._lock:
            self._provider_locks = deadlines

    def scroll(self, direction: int) -> None:
        """Scroll a catalogue view without changing its highlighted identity."""
        with self._lock:
            self._offsets[self._screen] = max(self._offsets.get(self._screen, 0) + direction * 3, 0)
            self._follow_cursor = False

    def render(self, columns: int, rows: int) -> Text:
        """Render the cached state of the current screen for one terminal geometry."""
        with self._lock:
            renderer: Callable[[int, int], Text] = {
                _Screen.QUERY: self._render_query,
                _Screen.TITLES: self._render_titles,
                _Screen.BUSY: self._render_busy,
                _Screen.RESULTS: self._render_results,
                _Screen.DONE: self._render_done,
                _Screen.PROBLEM: self._render_problem,
                _Screen.ENTRIES: self._render_entries,
                _Screen.EPISODES: self._render_episodes,
                _Screen.OFFER: self._render_offers,
                _Screen.CANDIDATES: self._render_candidates,
            }[self._screen]
            rendered: Text = renderer(columns, rows)
        return rendered

    def cancel(self) -> None:
        """Blur retained inputs and discard the result of network work still in flight."""
        with self._lock:
            self._input_focused = False
            self._generation += 1
            self._downloaded = None
            self._draft = None
            self._offers_running = False
            if self._screen is _Screen.DONE:
                self._screen = _Screen.RESULTS
            if self._screen is _Screen.BUSY:
                self._screen = self._busy_return
                self._worker = None

    @property
    def input_focused(self) -> bool:
        """Whether Anime currently owns cursor and selection navigation."""
        with self._lock:
            return self._input_focused

    def _handle_input(self, key: str) -> bool:
        editor: TextInput | None = None
        if self._screen is _Screen.QUERY:
            editor = self._query_input
        elif self._screen is _Screen.RESULTS:
            editor = self._group_input or self._range_input
        elif self._screen is _Screen.EPISODES:
            editor = self._range_input
        if editor is None:
            return False
        if self._input_focused and key == "interrupt" and editor.handle(key):
            return True
        if key in {"escape", "interrupt"} and self._input_focused:
            self._input_focused = False
            return True
        if not self._input_focused:
            if key == "enter" or (self._screen is _Screen.QUERY and key == "text:/"):
                self._input_focused = True
            return key not in {"escape", "interrupt"}
        return editor.handle(key)

    def _handle_query(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return AnimeResult.HOME
        if key == "enter" and self._query.strip():
            self._start_search(self._query.strip())
        return AnimeResult.CONTINUE

    @property
    def _query(self) -> str:
        return self._query_input.text

    @property
    def _range(self) -> str | None:
        return None if self._range_input is None else self._range_input.text

    @_range.setter
    def _range(self, value: str | None) -> None:
        self._range_input = None if value is None else TextInput(value)
        self._input_focused = value is not None

    def _handle_titles(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"} or not self._candidates:
            self._screen = _Screen.QUERY
        elif key in {"up", "down"}:
            delta: int = -1 if key == "up" else 1
            self._highlighted = (self._highlighted + delta) % len(self._candidates)
        elif key == "enter":
            self._start_franchise()
        elif key.casefold() == "text:g":
            self._start_title_search()
        elif key == "text:/":
            self._screen = _Screen.QUERY
            self._input_focused = True
        return AnimeResult.CONTINUE

    def _handle_busy(self, key: str) -> AnimeResult:
        if key not in {"escape", "interrupt"}:
            return AnimeResult.CONTINUE
        self._generation += 1
        self._worker = None
        self._screen = self._busy_return
        return AnimeResult.CONTINUE

    def _handle_results(self, key: str) -> AnimeResult:
        if self._group_input is not None:
            self._handle_group_input(key)
            return AnimeResult.CONTINUE
        if self._range is not None:
            return self._handle_range(key)
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._leave_results()
            return AnimeResult.CONTINUE
        if not self._choices:
            return self._handle_empty(key)
        self._apply_results_key(key)
        return AnimeResult.CONTINUE

    def _handle_empty(self, key: str) -> AnimeResult:
        if key.casefold() == "text:o" and self._candidate is not None:
            self._group_input = TextInput()
            self._input_focused = True
        elif key in {"text:f", "text:F"} and self._episodes is not None:
            self._start_unfiltered_search()
        elif key == "enter":
            self._leave_results()
        return AnimeResult.CONTINUE

    def _handle_group_input(self, key: str) -> None:
        editor: TextInput | None = self._group_input
        if editor is None:
            return
        if key in {"escape", "interrupt"}:
            self._group_input = None
            self._input_focused = False
            return
        if key != "enter" or not editor.text.strip() or self._candidate is None:
            return
        group: str = editor.text.strip()
        order: SubscriptionOrder = SubscriptionOrder(
            self._candidate.romaji,
            group,
            f"{self._candidate.romaji} {group}",
            Decimal(1),
            context=self._context,
            anilist_id=self._candidate.anilist_id,
        )
        self._draft = SubscriptionDraft.from_order(order, ())
        self._group_input = None
        self._input_focused = False

    def _leave_results(self) -> None:
        if self._opened_group is not None:
            group: int = self._opened_group
            self._opened_group = None
            self._choices = tuple(
                index for index, row in enumerate(self._rows) if row.choice is None and row.action is None
            )
            self._selected = next(index for index in self._choices if self._rows[index].group == group)
            return
        self._screen = _Screen.TITLES if self._candidates else _Screen.QUERY

    def _apply_results_key(self, key: str) -> None:
        if key in {"up", "down"}:
            self._move(-1 if key == "up" else 1)
        elif key in {"home", "end"}:
            self._selected = self._choices[0 if key == "home" else -1]
        elif key == "space":
            self._toggle()
        elif key == "enter":
            self._activate_row()
        elif key in {"text:d", "text:D"} and self._opened_group is not None:
            self._start_download()
        elif key in {"text:o", "text:O"}:
            self._start_subscription()
        elif key in {"text:a", "text:A"} and self._opened_group is not None:
            self._mark_group()
        elif key in {"text:z", "text:Z"} and self._opened_group is not None:
            self._range = ""
        elif key in {"text:s", "text:S"}:
            self._reorder()
        elif key in {"text:f", "text:F"} and self._episodes is not None:
            self._start_unfiltered_search()

    def _activate_row(self) -> None:
        row: _Row = self._rows[self._selected]
        if self._opened_group is None:
            self._opened_group = row.group
            self._choices = tuple(
                index
                for index, item in enumerate(self._rows)
                if item.group == row.group and (item.choice is not None or item.action is not None)
            )
            self._selected = self._choices[0]
        elif row.action is _Action.SELECT_ALL:
            self._mark_group()
        elif row.action is _Action.DOWNLOAD:
            self._start_download()
        elif row.action is _Action.BACK:
            self._leave_results()
        else:
            self._toggle()

    def _handle_range(self, key: str) -> AnimeResult:
        typed: str = self._range or ""
        if key in {"escape", "interrupt"}:
            self._range = None
        elif key == "enter":
            self._range = None
            self._apply_range(typed)
        return AnimeResult.CONTINUE

    def _handle_problem(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            if self._problem_return in {_Screen.TITLES, _Screen.ENTRIES, _Screen.EPISODES}:
                self._screen = self._problem_return
                return AnimeResult.CONTINUE
            return AnimeResult.HOME
        if key != "enter":
            return AnimeResult.CONTINUE
        if self._resume_available:
            generation: int = self._start_work(_RESUMING, _Screen.RESULTS)
            self._spawn(self._resume, (generation,))
            return AnimeResult.CONTINUE
        self._screen = self._problem_return
        self._problem = ""
        self._suggestion = ""
        return AnimeResult.CONTINUE

    def _handle_episode_screen(self, key: str) -> None:
        if self._screen is _Screen.EPISODES and self._range_input is not None:
            if key in {"escape", "interrupt"}:
                self._range = None
            elif key == "enter":
                typed: str = self._range_input.text
                self._range = None
                self._apply_episode_range(typed)
            return
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._back_episode_screen()
            return
        count: int = self._episode_screen_count()
        if not count:
            return
        if key in {"up", "down", "home", "end", "pageup", "pagedown"}:
            self._navigate_episode_screen(key, count)
            return
        if self._screen is _Screen.ENTRIES and key == "enter":
            self._start_episodes()
        elif self._screen is _Screen.EPISODES:
            self._episode_key(key)
        elif self._screen is _Screen.OFFER and key in {"enter", "text:i", "text:I"}:
            self._open_candidates()

    def _episode_screen_count(self) -> int:
        if self._screen is _Screen.ENTRIES:
            return len(self._franchise.entries) if self._franchise else 0
        if self._screen is _Screen.EPISODES:
            return len(self._listing.episodes) if self._listing and self._listing.kitsu_id is not None else 0
        if self._screen is _Screen.OFFER:
            return len(self._offer_numbers)
        return len(self._release_candidates)

    def _navigate_episode_screen(self, key: str, count: int) -> None:
        position: int = self._positions.get(self._screen, 0)
        if key in {"home", "end"}:
            position = 0 if key == "home" else count - 1
        elif key in {"pageup", "pagedown"}:
            position = min(max(position + (-1 if key == "pageup" else 1) * self._visible_count, 0), count - 1)
        else:
            position = (position + (-1 if key == "up" else 1)) % count
        self._positions[self._screen] = position
        self._follow_cursor = True

    def _back_episode_screen(self) -> None:
        if self._screen is _Screen.CANDIDATES:
            self._screen = _Screen.OFFER
        elif self._screen is _Screen.OFFER:
            self._generation += 1
            self._worker = None
            self._offers_running = False
            self._screen = _Screen.EPISODES
        elif self._screen is _Screen.EPISODES:
            self._screen = _Screen.ENTRIES
        else:
            self._screen = _Screen.TITLES

    def _episode_key(self, key: str) -> None:
        listing: EpisodeListing | None = self._listing
        if listing is None:
            return
        episode: ListedEpisode = listing.episodes[self._positions.get(_Screen.EPISODES, 0)]
        if key in {"space", "enter"}:
            if not episode.aired:
                self._notice = f"E{episode.number} jeszcze nie wyemitowano"
            elif episode.number in self._episode_marks:
                self._episode_marks.remove(episode.number)
            else:
                self._episode_marks.add(episode.number)
        elif key.casefold() == "text:a":
            self._episode_marks = {item.number for item in listing.episodes if item.aired}
        elif key.casefold() == "text:z":
            self._range = ""
        elif key.casefold() == "text:d":
            self._start_offers(episode)

    def _apply_episode_range(self, typed: str) -> None:
        if self._listing is None:
            return
        available: dict[int, ListedEpisode] = {item.number: item for item in self._listing.episodes}
        numbers, problem = _episode_range(typed, available)
        if problem:
            self._notice = problem
            return
        self._episode_marks = {number for number in numbers if available[number].aired}
        if len(self._episode_marks) != len(numbers):
            self._notice = "Pominięto niewyemitowane odcinki"

    def _start_franchise(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        if self._franchise is not None and self._franchise.selected_id == candidate.anilist_id:
            self._screen = _Screen.ENTRIES
            return
        self._franchise = None
        self._entry = None
        self._listing = None
        self._episode_marks.clear()
        self._offers.clear()
        generation: int = self._start_work("Wczytuję wpisy…", _Screen.TITLES)
        self._spawn(self._load_franchise, (candidate.anilist_id, generation))

    def _load_franchise(self, anilist_id: int, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            franchise: Franchise = self._acquisition.franchise(anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.TITLES, "anilist")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._franchise = franchise
            self._positions[_Screen.ENTRIES] = next(
                (index for index, entry in enumerate(franchise.entries) if entry.anilist_id == franchise.selected_id), 0
            )
            self._offsets[_Screen.ENTRIES] = 0
            self._follow_cursor = True
            self._screen = _Screen.ENTRIES
            self._worker = None
        self._invalidate()

    def _start_episodes(self) -> None:
        if self._franchise is None:
            return
        entry: FranchiseEntry = self._franchise.entries[self._positions.get(_Screen.ENTRIES, 0)]
        same: bool = self._entry == entry and self._listing is not None
        self._entry = entry
        if not same:
            self._listing = None
            self._episode_marks.clear()
            self._positions[_Screen.EPISODES] = 0
            self._offsets[_Screen.EPISODES] = 0
        generation: int = self._start_work("Wczytuję odcinki…", _Screen.ENTRIES)
        self._spawn(self._load_episodes, (entry, generation))

    def _load_episodes(self, entry: FranchiseEntry, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            listing: EpisodeListing = self._acquisition.episodes(entry.anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.ENTRIES, "anizip")
            return
        with self._lock:
            if generation != self._generation:
                return
            if entry.format == "MOVIE":
                film: ListedEpisode = next((item for item in listing.episodes if item.number == 1), ListedEpisode(1))
                listing = replace(listing, episodes=(film,))
            self._listing = listing
            self._episode_marks.intersection_update(item.number for item in listing.episodes)
            self._positions[_Screen.EPISODES] = min(
                self._positions.get(_Screen.EPISODES, 0), max(len(listing.episodes) - 1, 0)
            )
            self._follow_cursor = True
            self._screen = _Screen.EPISODES
            self._worker = None
        self._invalidate()

    def _start_offers(self, highlighted: ListedEpisode) -> None:
        if self._listing is None or self._listing.kitsu_id is None:
            self._notice = "Brak mapowania"
            return
        selected: set[int] = self._episode_marks or {highlighted.number}
        numbers: tuple[int, ...] = tuple(
            item.number for item in self._listing.episodes if item.number in selected and item.aired
        )
        if not numbers:
            self._notice = f"E{highlighted.number} jeszcze nie wyemitowano"
            return
        generation: int = self._start_work("Szukam…", _Screen.EPISODES)
        self._screen = _Screen.OFFER
        self._offers_running = True
        self._offers.clear()
        self._offer_numbers = numbers
        self._positions[_Screen.OFFER] = 0
        self._offsets[_Screen.OFFER] = 0
        self._follow_cursor = True
        self._spawn(self._load_offers, (self._listing.anilist_id, numbers, generation))

    def _load_offers(self, anilist_id: int, numbers: tuple[int, ...], generation: int) -> None:
        if self._acquisition is None:
            return
        for number in numbers:
            if not self._offer_pending(generation):
                return
            try:
                offer: EpisodeOffer = self._acquisition.offer(EpisodeKey(anilist_id, number))
            except Exception as problem:  # noqa: BLE001 - defects fail the whole offer instead of inventing a verdict
                self._catalog_failure(generation, problem, _Screen.EPISODES, "torrentio")
                return
            if not self._receive_offer(generation, number, offer):
                return
            self._invalidate()
        with self._lock:
            if generation == self._generation:
                self._worker = None
                self._offers_running = False
        self._invalidate()

    def _offer_pending(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    def _receive_offer(self, generation: int, number: int, offer: EpisodeOffer) -> bool:
        with self._lock:
            if generation != self._generation:
                return False
            self._offers[number] = offer
            return True

    def _catalog_failure(self, generation: int, problem: Exception, back: _Screen, provider: str) -> None:
        logger.warning("Anime catalogue command failed", error_class=type(problem).__name__)
        if isinstance(problem, (AniShiftError, OSError)):
            self._report(generation, problem, back, provider=provider, catalog_command=True)
            return
        self._fail(generation, _COMMAND_FAILED, "", back)

    def _open_candidates(self) -> None:
        offer: EpisodeOffer | None = self._highlighted_offer()
        if offer is None:
            return
        high: bool = any(
            item.identity.verdict is IdentityVerdict.MATCH
            and item.facts.resolution in {1080, 2160}
            and item.facts.supported is not False
            for item in offer.candidates
        )
        self._release_candidates = tuple(
            item for item in offer.candidates if not high or item.facts.resolution in {1080, 2160, None}
        )
        self._positions[_Screen.CANDIDATES] = 0
        self._offsets[_Screen.CANDIDATES] = 0
        self._follow_cursor = True
        self._screen = _Screen.CANDIDATES

    def _highlighted_offer(self) -> EpisodeOffer | None:
        if not self._offer_numbers:
            return None
        return self._offers.get(self._offer_numbers[self._positions.get(_Screen.OFFER, 0)])

    def _move(self, delta: int) -> None:
        position: int = self._choices.index(self._selected) if self._selected in self._choices else 0
        self._selected = self._choices[(position + delta) % len(self._choices)]

    def _toggle(self) -> None:
        row: _Row = self._rows[self._selected]
        choice: ReleaseChoice | None = row.choice
        if choice is None:
            return
        recorded: str = self._recorded_label(choice)
        if recorded:
            self._notice = f"{recorded} · ponowienie przez Historię"
            return
        if self._selected in self._marked:
            self._marked.discard(self._selected)
            return
        alternatives: set[int] = {
            index
            for index in self._marked
            if _is_markable(choice, None)
            and self._rows[index].group == row.group
            and (other := self._rows[index].choice) is not None
            and _is_markable(other, None)
            and other.episode == choice.episode
        }
        self._marked.difference_update(alternatives)
        if alternatives:
            self._notice = "Zmieniono wersję odcinka"
        self._marked.add(self._selected)

    def _recorded_label(self, choice: ReleaseChoice | None) -> str:
        if choice is None:
            return ""
        state: str | None = self._recorded.get(choice.release.info_hash.casefold())
        if state is None:
            return ""
        return "Pobrano" if state == "complete" else ("Zamówiono" if state == "accepted" else "Sprawdź historię")

    def _apply_range(self, typed: str) -> None:
        episodes: EpisodeRange | None = _parse_range(typed)
        if episodes is None:
            self._notice = _RANGE_INVALID
            return
        self._mark_group(episodes)

    def _mark_group(self, episodes: EpisodeRange | None = None) -> None:
        group: int = self._rows[self._selected].group
        candidates: tuple[int, ...] = tuple(
            index
            for index in self._choices
            if self._rows[index].group == group
            and _is_markable(self._rows[index].choice, episodes)
            and not self._recorded_label(self._rows[index].choice)
        )
        selected: dict[Decimal, int] = {
            choice.episode: index
            for index in candidates
            if index in self._marked and (choice := self._rows[index].choice) is not None and choice.episode is not None
        }
        for index in candidates:
            choice = self._rows[index].choice
            if choice is not None and choice.episode is not None:
                selected.setdefault(choice.episode, index)
        marked: tuple[int, ...] = tuple(selected.values())
        self._marked.update(marked)
        wanted: int | None = None if episodes is None else _range_size(episodes)
        self._notice = f"zaznaczono {len(marked)}"
        if wanted is not None and len(marked) < wanted:
            self._notice += f" z {wanted}"
        if len(candidates) > len(marked):
            self._notice += f" · pominięto alternatywy: {len(candidates) - len(marked)}"

    def _reorder(self) -> None:
        marked: frozenset[str] = frozenset(
            choice.release.info_hash for index in self._marked if (choice := self._rows[index].choice) is not None
        )
        highlighted: _Row = self._rows[self._selected]
        group: SeriesGroup = self._groups[highlighted.group]
        self._order = CatalogOrder.SEEDERS if self._order is CatalogOrder.NEWEST else CatalogOrder.NEWEST
        ranked: bool = any(group.matches_title for group in self._groups)
        self._groups = order_groups(self._groups, self._order, ranked=ranked)
        self._rows, self._choices = _catalog_rows(self._groups)
        self._marked = {index for index, row in enumerate(self._rows) if _has_hash(row.choice, marked)}
        self._selected = next(index for index in self._choices if self._groups[self._rows[index].group] is group)
        if self._opened_group is not None:
            self._opened_group = None
            self._activate_row()
            self._selected = next(
                (
                    index
                    for index in self._choices
                    if self._rows[index].action == highlighted.action and self._rows[index].choice == highlighted.choice
                ),
                self._selected,
            )

    def _start_search(self, text: str) -> None:
        self._searched = text
        self._candidates = ()
        self._candidate = None
        self._groups = ()
        self._rows = ()
        self._choices = ()
        self._marked.clear()
        self._opened_group = None
        self._context = None
        self._franchise = None
        self._entry = None
        self._listing = None
        self._offers.clear()
        self._episode_marks.clear()
        query: SearchQuery = parse_query(text)
        self._episodes = query.episodes
        generation: int = self._start_work(_SEARCHING_TITLE, _Screen.QUERY)
        self._spawn(self._find_titles, (query.title, text, generation))

    def _start_title_search(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        if candidate == self._candidate and self._rows:
            self._screen = _Screen.RESULTS
            return
        self._candidate = candidate
        self._groups = ()
        self._rows = ()
        self._choices = ()
        self._marked.clear()
        self._opened_group = None
        generation: int = self._start_work(_SEARCHING_RELEASES, _Screen.TITLES)
        self._spawn(self._search_title, (candidate, self._episodes, self._order, generation))

    def _start_unfiltered_search(self) -> None:
        candidate: TitleCandidate | None = self._candidate
        if candidate is None:
            return
        generation: int = self._start_work(_SEARCHING_RELEASES, _Screen.QUERY)
        listing: _Listing = _Listing(self._order, context=self._context, fallback=self._fallback)
        self._spawn(self._search_releases, (candidate, listing, generation))

    def _start_download(self) -> None:
        chosen: tuple[ReleaseChoice, ...] = tuple(
            choice
            for index in self._choices
            if index in self._marked
            and (choice := self._rows[index].choice) is not None
            and not self._recorded_label(choice)
        )
        if not chosen:
            self._notice = "Zaznacz co najmniej jedno wydanie"
            return
        generation: int = self._start_work(_SENDING, _Screen.RESULTS)
        self._spawn(self._download, (chosen, generation))

    def _start_subscription(self) -> None:
        row: _Row = self._rows[self._selected]
        group: SeriesGroup = self._groups[row.group]
        choice: ReleaseChoice | None = row.choice
        if self._opened_group is None:
            choice = max(
                (item for item in group.choices if _is_markable(item, None)),
                key=lambda item: item.episode if item.episode is not None else Decimal(0),
                default=group.choices[0],
            )
        if choice is None:
            return
        if choice.name.is_pack or choice.episode is None:
            self._notice = _EPISODE_ONLY
            return
        if choice.other_season:
            self._notice = _OTHER_SEASON
            return
        order: SubscriptionOrder = SubscriptionOrder(
            group.series,
            group.group,
            self._subscription_query(),
            choice.episode,
            context=self._context,
            anilist_id=self._candidate.anilist_id if self._candidate is not None else None,
        )
        numbers: tuple[Decimal, ...] = tuple(
            item.episode for item in group.choices if item.episode is not None and _is_markable(item, None)
        )
        self._draft = SubscriptionDraft.from_order(order, numbers)

    def _subscription_query(self) -> str:
        if self._candidate is None:
            return self._searched
        group: SeriesGroup = self._groups[self._rows[self._selected].group]
        return f"{group.series} {group.group}"

    def _start_work(self, sentence: str, back: _Screen) -> int:
        self._input_focused = False
        self._generation += 1
        self._downloaded = None
        self._resume_available = False
        self._problem_provider = ""
        self._offers_running = False
        self._busy_return = back
        self._screen = _Screen.BUSY
        self._busy = sentence
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _find_titles(self, title: str, text: str, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            candidates: tuple[TitleCandidate, ...] = acquisition.find_titles(title)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title lookup failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY, provider="anilist")
            return
        if not candidates:
            with self._lock:
                if generation != self._generation:
                    return
                self._busy = "Brak tytułu w AniList, szukam wydań na Nyaa"
            self._invalidate()
            self._search(text, _NO_TITLE, generation)
            return
        self._show_titles(generation, candidates)

    def _search(self, query: str, fallback: str, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search(query)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime search failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY, provider="nyaa")
            return
        self._show_results(generation, catalog, _Listing(CatalogOrder.SEEDERS, fallback=fallback))

    def _search_title(
        self,
        candidate: TitleCandidate,
        episodes: EpisodeRange | None,
        order: CatalogOrder,
        generation: int,
    ) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        note: str = ""
        try:
            context: SeasonContext | None = acquisition.season_context(candidate)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime season lookup failed", error_class=type(problem).__name__)
            context = None
            note = _NO_SEASON_NUMBERING
        self._search_releases(candidate, _Listing(order, episodes, context, note), generation)

    def _search_releases(self, candidate: TitleCandidate, listing: _Listing, generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            catalog: ReleaseCatalog = acquisition.search_title(
                candidate, episodes=listing.episodes, order=listing.order, context=listing.context
            )
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime title search failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.QUERY, provider="nyaa")
            return
        self._show_results(generation, catalog, listing)

    def _download(self, choices: Sequence[ReleaseChoice], generation: int) -> None:
        acquisition: AcquisitionService | ResidentSession | None = self._acquisition
        if acquisition is None:
            self._fail(generation, _UNAVAILABLE, "", _Screen.RESULTS)
            return
        try:
            receipt: DownloadReceipt = acquisition.download(choices)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime download failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.RESULTS)
            return
        sentence: str = f"Wysłano {receipt.count} do qBittorrenta → {_safe(receipt.directory.name)}"
        if isinstance(acquisition, ResidentSession):
            sentence = (
                f"Przyjęto {receipt.count} zamówień · pobieranie w prywatnym kliencie AniShift"
                if receipt.count > 0
                else "Zamówienia już zapisane · sprawdź prywatny klient AniShift"
            )
            if receipt.count < len(choices):
                sentence += f" · już zapisane: {len(choices) - receipt.count}"
        self._show_done(generation, sentence, choices)

    def _resume(self, generation: int) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        try:
            if resident.command("set_auto", {"enabled": True}).get("auto_enabled") is not True:
                self._fail(generation, "Brak potwierdzenia wznowienia AniShift", "", _Screen.RESULTS, resume=True)
                return
        except (AniShiftError, OSError, ValueError) as problem:
            logger.warning("Anime resume failed", error_class=type(problem).__name__)
            self._report(generation, problem, _Screen.RESULTS, resume=True)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._screen = _Screen.RESULTS
            self._problem = ""
            self._suggestion = ""
        self._invalidate()

    def _show_titles(self, generation: int, candidates: tuple[TitleCandidate, ...]) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._candidates = tuple(
                sorted(
                    natsorted(candidates, key=lambda item: (item.english or item.romaji).casefold()),
                    key=lambda item: -(item.year or 0),
                )
            )
            self._highlighted = 0
            self._screen = _Screen.TITLES
        self._invalidate()

    def _show_results(self, generation: int, catalog: ReleaseCatalog, listing: _Listing) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._order = listing.order
            self._episodes = listing.episodes
            self._context = listing.context
            self._fallback = listing.fallback
            self._groups = catalog.groups
            self._opened_group = None
            self._rows, self._choices = _catalog_rows(catalog.groups)
            self._hidden = catalog.hidden
            self._excluded = catalog.excluded
            self._filtered = catalog.filtered
            self._marked = set()
            self._range = None
            self._notice = ""
            self._selected = self._choices[0] if self._choices else 0
            self._screen = _Screen.RESULTS
        self._invalidate()

    def _show_done(self, generation: int, sentence: str, choices: Sequence[ReleaseChoice] = ()) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._done = sentence
            hashes: frozenset[str] = frozenset(choice.release.info_hash for choice in choices)
            self._marked = {index for index in self._marked if not _has_hash(self._rows[index].choice, hashes)}
            self._downloaded = sentence
            self._screen = _Screen.DONE
        self._invalidate()

    def _report(  # noqa: PLR0913
        self,
        generation: int,
        problem: AniShiftError | OSError | ValueError,
        back: _Screen,
        *,
        resume: bool = False,
        provider: str = "",
        catalog_command: bool = False,
    ) -> None:
        """State one failure of this screen in Polish and return the user to *back*."""
        sentence, hint = _stated(problem)
        code: ErrorCode | None = _code(problem)
        provider = (
            {
                ErrorCode.TITLE_CATALOG_FAILED: "anilist",
                ErrorCode.EPISODE_CATALOG_FAILED: "anizip",
            }.get(code, provider)
            if code is not None
            else provider
        )
        if (
            catalog_command
            and isinstance(problem, ControlError)
            and (problem.code is ControlErrorCode.INTERNAL and problem.reason == "command_failed")
        ):
            sentence, hint = _COMMAND_FAILED, ""
        if code not in {
            ErrorCode.TITLE_CATALOG_FAILED,
            ErrorCode.EPISODE_CATALOG_FAILED,
            ErrorCode.TORRENT_SOURCE_FAILED,
        }:
            provider = ""
        deadline: float = 0.0
        if provider and isinstance(self._acquisition, AcquisitionService):
            deadline = self._acquisition.blocked_until((provider,))
        resume = resume or (
            self._resident is not None
            and back is _Screen.RESULTS
            and isinstance(problem, ControlError)
            and problem.reason == RefusalReason.PAUSED.value
        )
        self._fail(generation, sentence, hint, back, resume=resume, provider=provider, deadline=deadline)

    def _fail(  # noqa: PLR0913
        self,
        generation: int,
        sentence: str,
        suggestion: str,
        back: _Screen,
        *,
        resume: bool = False,
        provider: str = "",
        deadline: float = 0.0,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._offers_running = False
            if back is _Screen.EPISODES:
                self._offers.clear()
                self._release_candidates = ()
            self._problem_provider = provider
            if deadline:
                self._provider_locks[provider] = deadline
            self._problem = sentence
            self._suggestion = suggestion
            self._problem_return = back
            self._resume_available = resume
            self._screen = _Screen.PROBLEM
        self._invalidate()

    def _render_query(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2) if rows >= _HEADER_ROWS else Text()
        left: int = max((columns - min(max(len(self._query) + 3, 32), columns)) // 2, 0)
        width: int = max(columns - left - 3, 1)
        content.append(f"{' ' * left}> ", style="brand_accent" if self._input_focused else "gray")
        content.append_text(self._query_input.render(width, focused=self._input_focused))
        content.append("\n")
        hint: str = "Enter szukaj · Esc zakończ · Tab widok" if self._input_focused else _QUERY_HINT
        return _finish(content, hint, columns, rows)

    def _render_titles(self, columns: int, rows: int) -> Text:
        labels: tuple[str, ...] = tuple(
            _truncate_right(_candidate_label(candidate), max(columns - 4, 1)) for candidate in self._candidates
        )
        left: int = max((columns - min(max((len(label) for label in labels), default=1) + 4, columns)) // 2, 0)
        start, end = _visible_window(len(labels), self._highlighted, rows)
        content: Text = _header(_TITLE, columns, rows, end - start)
        for index in range(start, end):
            style: str = "brand_accent" if index == self._highlighted else "white_bold"
            content.append(" " * left)
            content.append(f"{_POINTER} " if index == self._highlighted else "  ", style=style)
            content.append(f"{labels[index]}\n", style=style)
        return _finish(content, _TITLES_HINT, columns, rows)

    def _episode_view(
        self,
        columns: int,
        rows: int,
        heading: str,
        lines: Sequence[tuple[str, int | None]],
        footer: Sequence[str | Text],
    ) -> Text:
        width: int = max(columns - 2, 1)
        hints: list[Text] = [
            Text(line, style="gray") if isinstance(hint, str) else hint.copy()
            for hint in footer
            for line in (_wrapped_hint(hint, width) if isinstance(hint, str) else (hint.plain,))
        ]
        budget: int = rows - len(hints) - 3
        if budget < 1:
            return with_footer(Text("Powiększ terminal"), ("Esc wróć · Tab widok",), columns, rows)
        selected: int = self._positions.get(self._screen, 0)
        cursor: int = next((index for index, (_, position) in enumerate(lines) if position == selected), 0)
        start: int = min(self._offsets.get(self._screen, 0), max(len(lines) - budget, 0))
        if self._follow_cursor:
            start = min(start, cursor)
            start = max(start, cursor - budget + 1)
        self._offsets[self._screen] = start
        self._visible_count = budget
        content: Text = Text(_fit_text(heading, width) + "\n\n", style="white_bold")
        for label, position in lines[start : start + budget]:
            active: bool = position is not None and position == selected
            content.append(
                _fit_text((f"{_POINTER} " if active else "  ") + label, width) + "\n",
                style="brand_accent" if active else "white_bold",
            )
        return with_footer(content, hints, columns, rows)

    def _render_entries(self, columns: int, rows: int) -> Text:
        franchise: Franchise | None = self._franchise
        widths: tuple[int, ...] = (4, max(columns - 36, 1), 5, 17)
        lines: list[tuple[str, int | None]] = [(_columns(("Rok", "Tytuł", "Typ", "Status"), widths), None)]
        previous: EntryGroup | None = None
        for index, entry in enumerate(franchise.entries if franchise else ()):
            if previous != entry.group:
                lines.append((_ENTRY_GROUPS[entry.group], None))
                previous = entry.group
            lines.append(
                (
                    _columns(
                        (
                            str(entry.year or "—"),
                            _safe(entry.english or entry.romaji),
                            _format_label(entry.format),
                            _ENTRY_STATUSES.get(entry.status, "—"),
                        ),
                        widths,
                    ),
                    index,
                )
            )
        if franchise is not None and not franchise.complete:
            lines.append(("Lista niepełna — pokazano najbliższe powiązania", None))
        title: str = _safe(self._candidates[self._highlighted].english or self._candidates[self._highlighted].romaji)
        return self._episode_view(columns, rows, f"Anime \u203a {title}", lines, ("Enter odcinki · Esc tytuły",))

    def _retry_hint(self, provider: str, fallback: float = 0.0) -> str:
        deadline: float = self._provider_locks.get(provider, fallback)
        if not deadline:
            return ""
        remaining: int = max(ceil(deadline - self._clock()), 0)
        return f"spróbuj za {remaining} s" if remaining else "Możesz spróbować ponownie"

    def _render_episodes(self, columns: int, rows: int) -> Text:
        listing: EpisodeListing | None = self._listing
        lines: list[tuple[str, int | None]] = []
        if listing is None or listing.kitsu_id is None:
            lines.append(("Brak mapowania odcinków dla tego wpisu", None))
            return self._episode_view(columns, rows, self._entry_heading(), lines, ("Esc wróć",))
        film: bool = self._entry is not None and self._entry.format == "MOVIE"
        if film:
            lines.append(("Pobieranie filmów zależy od pomiaru E1", None))
        lines.append(("Zaznaczone: " + (", ".join(map(str, sorted(self._episode_marks))) or "—"), None))
        fallback_dates: bool = any(episode.airs_at_fallback for episode in listing.episodes)
        date_width: int = (22 if fallback_dates else 11) if columns >= _DATE_COLUMNS else 0
        widths: tuple[int, ...] = (3, 4, max(columns - 34 - date_width, 1), date_width, 15)
        lines.append((_columns(("", "Nr", "Tytuł", "Emisja", "Stan"), widths), None))
        for index, episode in enumerate(listing.episodes):
            state: str = "Nie zamówiono" if episode.aired else "Nie wyemitowano"
            number: str = "Film" if film else str(episode.number)
            marker: str = "[x]" if episode.number in self._episode_marks else "[ ]"
            date: str = episode.airs_at.astimezone().strftime("%d.%m %H:%M") if episode.airs_at else "—"
            if episode.airs_at_fallback:
                date += " (ani.zip)"
            lines.append((_columns((marker, number, _safe(episode.title or "—"), date, state), widths), index))
        if listing.specials:
            lines.append(("DODATKI (informacja)", None))
            lines.extend(
                (f"{item.key}  {_safe(item.title or '—')}  {item.airs_on or '—'}", None) for item in listing.specials
            )
        footer: list[str | Text] = []
        if listing.schedule_warning:
            fallback: float = listing.schedule_retry_at.timestamp() if listing.schedule_retry_at else 0.0
            retry: str = self._retry_hint("anilist", fallback)
            if not retry or retry == "Możesz spróbować ponownie":
                retry = "Możesz spróbować ponownie — wróć do wpisów i otwórz wpis"
            footer.extend(("Terminy emisji niedostępne (AniList)", retry))
        if self._notice:
            footer.append(self._notice)
        if self._range_input is not None:
            prompt: Text = Text("Zakres: ", style="gray")
            prompt.append_text(self._range_input.render(max(columns - 10, 1), focused=self._input_focused))
            footer.extend((prompt, "1,3,9-12 albo 5- · Enter zatwierdź · Esc zakończ"))
        else:
            footer.append("Space zaznacz · A wyemitowane · Z zakres · D podgląd · Esc wpisy")
        return self._episode_view(columns, rows, self._entry_heading(), lines, footer)

    def _entry_heading(self) -> str:
        entry: FranchiseEntry | None = self._entry
        return (
            "Anime" if entry is None else f"Anime \u203a {_safe(entry.english or entry.romaji)} ({entry.year or '—'})"
        )

    def _render_offers(self, columns: int, rows: int) -> Text:
        widths: tuple[int, ...] = _release_widths(columns - 10)
        lines: list[tuple[str, int | None]] = [
            ("Odc   " + _columns(("Sugerowane wydanie", "Obraz", "Język", "Seedy", "Rozm"), widths), None)
        ]
        for index, number in enumerate(self._offer_numbers):
            offer: EpisodeOffer | None = self._offers.get(number)
            if offer is None:
                label: str = "Szukam…" if self._offers_running else "Przerwano wyszukiwanie"
            elif offer.suggestion is None:
                label = _empty_offer(offer)
            else:
                item: RankedCandidate = offer.candidates[offer.suggestion]
                label = _stream_row(item, widths, uncertain=True)
            lines.append((f"E{number:<3}  {label}", index))
        highlighted: EpisodeOffer | None = self._highlighted_offer()
        reason: str = _offer_reason(highlighted) if highlighted else ""
        return self._episode_view(
            columns,
            rows,
            self._entry_heading() + " \u203a Podgląd",
            lines,
            (reason, "↑↓ wybierz · Enter/I inne wydania · Esc odcinki"),
        )

    def _render_candidates(self, columns: int, rows: int) -> Text:
        widths: tuple[int, ...] = _release_widths(
            columns - 16, unsupported=any(item.facts.supported is False for item in self._release_candidates)
        )
        lines: list[tuple[str, int | None]] = [
            ("Tożsamość   " + _columns(("Wydanie", "Obraz", "Język", "Seedy", "Rozm"), widths), None)
        ]
        lines.extend(
            (f"{_VERDICT_LABELS[item.identity.verdict]:10}  {_stream_row(item, widths)}", index)
            for index, item in enumerate(self._release_candidates)
        )
        footer: list[str | Text] = []
        if self._release_candidates:
            selected: RankedCandidate = self._release_candidates[self._positions.get(_Screen.CANDIDATES, 0)]
            reason: str = _REASON_TEXTS.get(selected.identity.reason, _identity_fallback(selected.identity.verdict))
            width: int = max(columns - 2, 1)
            console: Console = Console(width=width)
            footer.extend(
                line
                for detail in ("Powód: " + reason, _candidate_details(selected))
                for line in Text(detail, style="gray").wrap(console, width)
            )
        else:
            offer: EpisodeOffer | None = self._highlighted_offer()
            lines.append((_empty_offer(offer) if offer else "Brak kandydatów", None))
        footer.append("Esc podgląd")
        number: int = self._offer_numbers[self._positions.get(_Screen.OFFER, 0)]
        title: str = _safe(self._entry.english or self._entry.romaji) if self._entry else "—"
        return self._episode_view(columns, rows, f"Inne wydania \u203a {title} \u203a E{number}", lines, footer)

    def _render_busy(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._busy)) // 2, 0)
        content.append(f"{' ' * left}{self._busy}\n", style="brand_accent")
        hint: str = "Esc wróć · polecenie pozostaje w toku" if self._busy == _RESUMING else _BUSY_HINT
        return _finish(content, hint, columns, rows)

    def _render_results(self, columns: int, rows: int) -> Text:
        subtitle: str = (
            _group_label(self._groups[self._opened_group]) if self._opened_group is not None else self._title_header()
        )
        if not self._choices:
            return self._render_empty(columns, rows, subtitle)
        if rows < _FULL_PICKER_ROWS:
            return self._render_compact_results(columns, rows)
        labels: tuple[str, ...] = tuple(self._result_label(row, max(columns - 8, 1)) for row in self._rows)
        left: int = max((columns - min(max((len(label) for label in labels), default=1) + 8, columns)) // 2, 0)
        heading: int = 2 + int(bool(subtitle))
        lines: tuple[str | Text, ...] = (
            self._range_footer(columns)
            if self._range_input is not None
            else _wrapped_hint(self._footer(), max(columns - 2, 1))[: max(rows - heading - 2, 1)]
        )
        actions: tuple[int, ...] = tuple(index for index in self._choices if self._rows[index].action is not None)
        entries: tuple[int, ...] = tuple(index for index in self._choices if self._rows[index].action is None)
        position: int = entries.index(self._selected) if self._selected in entries else len(entries) - 1
        start, end = _visible_window(len(entries), position, max(rows - 1, 1), heading + len(lines) + len(actions))
        content: Text = _header(
            _TITLE, columns, rows, end - start + len(actions) + len(lines) - 1 + int(bool(subtitle)), subtitle
        )
        for index in (*entries[start:end], *actions):
            self._append_row(content, left, labels[index], index)
        return with_footer(content, lines, columns, rows)

    def _range_footer(self, columns: int) -> tuple[str | Text, ...]:
        prompt: Text = Text(f"{_RANGE_PROMPT}: ", style="gray")
        if self._range_input is not None:
            prompt.append_text(
                self._range_input.render(max(columns - 2 - prompt.cell_len, 1), focused=self._input_focused)
            )
        hint: str = "Enter zatwierdź · Esc zakończ" if self._input_focused else "Enter edytuj · Esc anuluj"
        return prompt, hint

    def _result_label(self, row: _Row, width: int) -> str:
        if row.action is _Action.DOWNLOAD:
            count: int = len(self._marked.intersection(self._choices))
            return f"Pobierz ({count})"
        recorded: str = self._recorded_label(row.choice)
        if recorded:
            return _truncate_right(f"{recorded} · {row.label}", width)
        return _row_label(row, width)

    def _render_compact_results(self, columns: int, rows: int) -> Text:
        position: int = self._choices.index(self._selected)
        footer: tuple[str | Text, ...] = (
            self._range_footer(columns) if self._range_input is not None else ("Enter wybierz · Esc wróć",)
        )
        start, end = _visible_window(len(self._choices), position, rows, 1 + len(footer))
        content: Text = Text()
        for index in self._choices[start:end]:
            self._append_row(content, 0, self._result_label(self._rows[index], max(columns - 8, 1)), index)
        return with_footer(content, footer, columns, rows)

    def _render_empty(self, columns: int, rows: int, subtitle: str) -> Text:
        if self._group_input is not None:
            content: Text = _header(_TITLE, columns, rows, 2, subtitle)
            content.append("Grupa wydająca: ", style="brand_accent" if self._input_focused else "gray")
            content.append_text(self._group_input.render(max(columns - 17, 1), focused=self._input_focused))
            hint: str = "Enter wybierz zakres · Esc zakończ" if self._input_focused else "Enter edytuj · Esc anuluj"
            return _finish(content, hint, columns, rows)
        sentence: str = self._empty_sentence()
        content = _header(_TITLE, columns, rows, 2, subtitle)
        left: int = max((columns - len(sentence)) // 2, 0)
        content.append(f"{' ' * left}{sentence}\n", style="warning")
        return _finish(content, _HINT_SEPARATOR.join(self._empty_hints()), columns, rows)

    def _empty_sentence(self) -> str:
        if self._filtered and self._episodes is not None:
            return _EMPTY_FILTERED.format(episodes=self._episodes.text)
        return _EMPTY_CATALOG

    def _empty_hints(self) -> tuple[str, ...]:
        hints: list[str] = [self._fallback] if self._fallback else []
        if self._candidate is not None:
            hints.append("O subskrybuj")
        if self._filtered and self._episodes is not None:
            hints.extend((f"poza filtrem: {self._filtered}", "F pokaż wszystkie", "Esc wróć"))
            return tuple(hints)
        hints.extend(self._counters())
        hints.append("Enter wróć")
        return tuple(hints)

    def _append_row(self, content: Text, left: int, label: str, index: int) -> None:
        style: str = "brand_accent" if index == self._selected else "white_bold"
        marker: str = ""
        if self._rows[index].choice is not None:
            marker = f"{'[x]' if index in self._marked else '[ ]'} {_BULLET} "
        content.append(" " * left)
        content.append(f"{_POINTER} " if index == self._selected else "  ", style=style)
        content.append(f"{marker}{label}\n", style=style)

    def _render_done(self, columns: int, rows: int) -> Text:
        content: Text = _header(_TITLE, columns, rows, 2)
        left: int = max((columns - len(self._done)) // 2, 0)
        content.append(f"{' ' * left}{self._done}\n", style="brand_accent")
        return _finish(content, _DONE_HINT, columns, rows)

    def _render_problem(self, columns: int, rows: int) -> Text:
        hint: str = self._retry_hint(self._problem_provider) or self._suggestion
        console: Console = Console(width=max(columns - 4, 1))
        lines: tuple[str, ...] = tuple(
            wrapped.plain
            for line in (self._problem, hint)
            if line
            for wrapped in Text(line).wrap(console, max(columns - 4, 1))
        )
        content: Text = _header(_TITLE, columns, rows, len(lines))
        left: int = max((columns - min(max((len(line) for line in lines), default=1), columns)) // 2, 0)
        for index, line in enumerate(lines):
            content.append(f"{' ' * left}{line}\n", style="error" if index == 0 else "gray")
        return _finish(content, _RESUME_HINT if self._resume_available else _PROBLEM_HINT, columns, rows)

    def _title_header(self) -> str:
        candidate: TitleCandidate | None = self._candidate
        if candidate is None:
            return ""
        parts: tuple[str, ...] = (
            _safe(candidate.romaji),
            _english_title(candidate),
            _status_label(candidate.status),
            f"{candidate.episodes} odc." if candidate.episodes else "",
        )
        return _HINT_SEPARATOR.join(part for part in parts if part)

    def _footer(self) -> str:
        if not self._notice and self._choices and self._opened_group is not None:
            choice: ReleaseChoice | None = self._rows[self._selected].choice
            if (
                choice is not None
                and sum(
                    _choice_label(other) == _choice_label(choice) for other in self._groups[self._opened_group].choices
                )
                > 1
            ):
                return f"{_safe(choice.release.title)} · Enter zaznacz · D pobierz · Esc wróć"
        return self._notice or self._results_hint()

    def _results_hint(self) -> str:
        hints: list[str] = [self._fallback] if self._fallback else []
        if self._opened_group is not None:
            hints.append(f"zaznaczone: {len(self._marked.intersection(self._choices))}")
        if self._episodes is not None:
            hints.append(f"filtr: odc. {self._episodes.text}")
        hints.extend(self._counters())
        if self._filtered:
            hints.append(f"poza filtrem: {self._filtered}")
        if self._opened_group is not None:
            hints.extend(("Space/Enter zaznacz", "A wszystkie", "Z zakres", "D pobierz"))
        else:
            hints.append("Enter otwórz grupę")
        hints.extend(("O subskrybuj", self._order_hint()))
        if self._episodes is not None:
            hints.append("F pokaż wszystkie")
        hints.append("Esc wróć")
        return _HINT_SEPARATOR.join(hints)

    def _order_hint(self) -> str:
        return "S najnowsze" if self._order is CatalogOrder.SEEDERS else "S seedy"

    def _counters(self) -> tuple[str, ...]:
        counters: list[str] = [f"ukryte poniżej {_MIN_RESOLUTION_LABEL}: {self._hidden}"]
        if self._excluded:
            counters.append(f"bez napisów/dubbing: {self._excluded}")
        return tuple(counters)


def _catalog_rows(groups: Sequence[SeriesGroup]) -> tuple[tuple[_Row, ...], tuple[int, ...]]:
    """Build catalog rows and the indexes of the initial group page."""
    rows: list[_Row] = []
    choices: list[int] = []
    for index, group in enumerate(groups):
        if not group.choices:
            continue
        choices.append(len(rows))
        rows.append(_Row(_group_label(group), None, index, _newest_detail(group)))
        labels: tuple[str, ...] = tuple(_choice_label(choice) for choice in group.choices)
        for choice, label in zip(group.choices, labels, strict=True):
            identified: str = label
            if labels.count(label) > 1:
                date: str = choice.release.published.strftime("%d.%m.%Y %H:%M") if choice.release.published else ""
                identified = f"{label} · {date} {_safe(choice.release.title)}".strip()
            rows.append(_Row(identified, choice, index))
        rows.extend(
            (
                _Row("Zaznacz wszystkie", group=index, action=_Action.SELECT_ALL),
                _Row("Pobierz", group=index, action=_Action.DOWNLOAD),
                _Row("Cofnij", group=index, action=_Action.BACK),
            )
        )
    return tuple(rows), tuple(choices)


def _group_label(group: SeriesGroup) -> str:
    """Name one listed group by its release group, subtitle language, and series."""
    language: str = f"{_HINT_SEPARATOR}{group.subtitle_language.upper()}" if group.subtitle_language else ""
    episodes: int = len({choice.episode for choice in group.choices if _is_markable(choice, None)})
    count: int = len(group.choices)
    noun: str = (
        "wydanie"
        if count == 1
        else ("wydania" if count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14} else "wydań")
    )
    return f"[{_safe(group.group)}{language}] {_safe(group.series)} · {episodes} odc. / {count} {noun}"


def _newest_detail(group: SeriesGroup) -> str:
    """Return the publication tail of one group, shown only when the terminal has room."""
    if group.newest is None:
        return ""
    return f"  najnowsze: {group.newest.strftime('%d.%m.%Y')}"


def _choice_label(choice: ReleaseChoice) -> str:
    facts: tuple[str, ...] = (
        _episode_label(choice),
        f"v{choice.name.version}" if choice.name.version is not None else "",
        f"{choice.name.resolution}p" if choice.name.resolution is not None else "",
        f"{choice.release.seeders} seedów",
        _safe(choice.release.size_text),
    )
    return _CHOICE_SEPARATOR.join(fact for fact in facts if fact)


def _episode_label(choice: ReleaseChoice) -> str:
    if choice.name.is_pack:
        return "cała paczka"
    episode: Decimal | None = choice.episode
    if episode is None:
        return "wydanie"
    if choice.absolute is not None:
        return f"{_episode_number(episode)} ({format(choice.absolute.normalize(), 'f')})"
    if choice.other_season:
        return f"{_episode_number(episode)}{_HINT_SEPARATOR}sezon?"
    return _episode_number(episode)


def _episode_number(episode: Decimal) -> str:
    return f"odc. {format(episode.normalize(), 'f')}"


def _candidate_label(candidate: TitleCandidate) -> str:
    """Describe one title candidate the way the chooser lists it."""
    facts: tuple[str, ...] = (
        str(candidate.year) if candidate.year else "—",
        _safe(candidate.english or candidate.romaji),
        _format_label(candidate.format),
    )
    return _HINT_SEPARATOR.join(fact for fact in facts if fact)


def _english_title(candidate: TitleCandidate) -> str:
    """Return the English title only when it says something the romaji one does not."""
    english: str = (candidate.english or "").strip()
    if not english or english.casefold() == candidate.romaji.casefold():
        return ""
    return _safe(english)


def _status_label(status: TitleStatus) -> str:
    return _STATUS_LABELS.get(status, "")


def _parse_range(typed: str) -> EpisodeRange | None:
    """Read the span typed in the footer, or nothing when it says no usable range."""
    match: re.Match[str] | None = _RANGE_RE.fullmatch(typed.strip())
    if match is None:
        return None
    upto: str | None = match.group("upto")
    if upto is not None:
        return EpisodeRange(first=None, last=Decimal(upto))
    first: Decimal = Decimal(match.group("first"))
    if match.group("dash") is None:
        return EpisodeRange(first=first, last=first)
    last: str | None = match.group("last")
    return EpisodeRange(first=first, last=None if last is None else Decimal(last))


def _range_size(episodes: EpisodeRange) -> int | None:
    """Return how many episodes a closed span asks for, or nothing when one end is open."""
    if episodes.first is None or episodes.last is None:
        return None
    return int(episodes.last - episodes.first) + 1


def _is_markable(choice: ReleaseChoice | None, episodes: EpisodeRange | None) -> bool:
    """Whether one release is a numbered episode of the chosen season inside *episodes*."""
    if choice is None or choice.name.is_pack or choice.episode is None or choice.other_season:
        return False
    return episodes is None or episodes.contains(choice.episode)


def _has_hash(choice: ReleaseChoice | None, hashes: frozenset[str]) -> bool:
    return choice is not None and choice.release.info_hash in hashes


def _row_label(row: _Row, width: int) -> str:
    full: str = f"{row.label}{row.detail}"
    return _truncate_right(full if len(full) <= width else row.label, width)


def _header(title: str, columns: int, rows: int, content_rows: int, subtitle: str = "") -> Text:
    top: int = max((rows - content_rows - 5) // 2, 0)
    shown: str = _truncate_right(title, max(columns - 2, 1))
    left: int = max((columns - len(shown)) // 2, 0)
    content = Text("\n" * top)
    content.append(f"{' ' * left}{shown}\n", style="white_bold")
    if subtitle:
        named: str = _truncate_right(subtitle, max(columns - 2, 1))
        content.append(f"{' ' * max((columns - len(named)) // 2, 0)}{named}\n", style="brand_accent")
    content.append("\n")
    return content


def _finish(content: Text, hint: str, columns: int, rows: int) -> Text:
    return with_footer(content, (hint,), columns, rows)


def _wrapped_hint(hint: str, width: int) -> tuple[str, ...]:
    lines: list[str] = []
    current: str = ""
    for part in hint.split(_HINT_SEPARATOR):
        candidate: str = f"{current}{_HINT_SEPARATOR}{part}" if current else part
        if current and Text(candidate).cell_len > width:
            lines.append(current)
            current = part
            continue
        current = candidate
    lines.append(current)
    return tuple(_fit_text(line, width) for line in lines)


def _visible_window(count: int, selected: int, rows: int, reserved: int = _HEADER_ROWS) -> tuple[int, int]:
    budget: int = max(rows - reserved, 1)
    if count <= budget:
        return 0, count
    start: int = min(max(selected - budget // 2, 0), count - budget)
    return start, start + budget


def _truncate_right(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _stated(problem: AniShiftError | OSError | ValueError) -> tuple[str, str]:  # noqa: PLR0911
    """Translate domain codes preserved locally or carried by a resident refusal."""
    from anishift.cli.interactive.state import refusal_text  # noqa: PLC0415

    if not isinstance(problem, AniShiftError):
        return refusal_text(problem), ""
    if isinstance(problem, ControlError) and problem.reason == "response_too_large":
        return "Odpowiedź rezydenta jest za duża", ""
    if isinstance(problem, ControlError) and problem.reason == "download_recorded":
        counts: dict[str, int] | None = _download_counts(problem)
        if counts is None:
            return "Nie można potwierdzić wyniku zamówienia", "Sprawdź prywatny klient AniShift i log"
        return (
            f"Przyjęto: {counts['sent']} · już przyjęte: {counts['accepted']}"
            f" · wynik przekazania niepotwierdzony: {counts['uncertain']}",
            "Sprawdź prywatny klient AniShift i log",
        )
    code: ErrorCode | None = _code(problem)
    stated: tuple[str, str] | None = _PROBLEM_TEXTS.get(code) if code is not None else None
    if stated is not None:
        if isinstance(problem, ControlError) and code in {
            ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            ErrorCode.TORRENT_CLIENT_UNAUTHORIZED,
            ErrorCode.TORRENT_CLIENT_REFUSED,
        }:
            return stated[0], "Sprawdź prywatny klient AniShift i log"
        return stated
    return refusal_text(problem), "" if isinstance(problem, ControlError) else _safe(problem.context.suggestion)


def _download_counts(problem: AniShiftError | OSError | ValueError) -> dict[str, int] | None:
    if not isinstance(problem, ControlError) or problem.reason != "download_recorded":
        return None
    keys: tuple[str, ...] = ("sent", "accepted", "uncertain")
    counts: dict[str, int] = {
        key: value for key in keys if type(value := problem.context.details.get(key)) is int and value >= 0
    }
    return counts if len(counts) == len(keys) else None


def _code(problem: AniShiftError | OSError | ValueError) -> ErrorCode | None:
    if isinstance(problem, ControlError):
        try:
            return ErrorCode(problem.reason)
        except ValueError:
            return None
    return problem.context.code if isinstance(problem, AniShiftError) else None


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")


def _deadline(value: str) -> float | None:
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _fit_text(value: str, width: int) -> str:
    if width <= 0:
        return ""
    text: Text = Text(value)
    text.truncate(width, overflow="ellipsis")
    return text.plain


def _format_label(value: str | None) -> str:
    return "Film" if value == "MOVIE" else value or "—"


def _episode_range(typed: str, available: Mapping[int, ListedEpisode]) -> tuple[set[int], str]:
    selected: set[int] = set()
    for part in typed.split(","):
        match: re.Match[str] | None = re.fullmatch(r"\s*([0-9]{1,6})(?:-([0-9]{0,6}))?\s*", part)
        if match is None:
            return set(), "Zakres: podaj 1,3,9-12 albo 5-"
        first: int = int(match[1])
        last: int = first if match[2] is None else int(match[2]) if match[2] else max(available, default=0)
        if last < first:
            return set(), "Zakres: początek musi poprzedzać koniec"
        missing: int | None = next((number for number in range(first, last + 1) if number not in available), None)
        if missing is not None:
            return set(), f"Brak odcinka {missing} w tym wpisie"
        selected.update(range(first, last + 1))
    return selected, ""


def _language(item: RankedCandidate) -> str:
    return (
        " · ".join(
            label for label, present in (("PL", item.facts.polish), ("MultiSub", item.facts.multisub)) if present
        )
        or "—"
    )


def _columns(values: Sequence[str], widths: Sequence[int]) -> str:
    return "  ".join(
        _fit_text(value, width) + " " * max(width - Text(_fit_text(value, width)).cell_len, 0)
        for value, width in zip(values, widths, strict=True)
        if width > 0
    ).rstrip()


def _release_widths(width: int, *, unsupported: bool = False) -> tuple[int, ...]:
    image: int = 13 if unsupported else 5
    seeds: int = 5 if width >= _SEED_COLUMNS else 0
    size: int = 7 if width >= _SIZE_COLUMNS else 0
    language: int = 13
    gaps: int = 4 + 2 * bool(seeds) + 2 * bool(size)
    return max(width - image - language - seeds - size - gaps, 1), image, language, seeds, size


def _stream_row(item: RankedCandidate, widths: tuple[int, ...], *, uncertain: bool = False) -> str:
    image: str = f"{item.facts.resolution}p" if item.facts.resolution else "?"
    if item.facts.supported is False:
        image += f" ({item.facts.container})"
    suffix: str = " (niepewne wydanie)" if uncertain and item.identity.verdict is IdentityVerdict.INSUFFICIENT else ""
    title: str = _fit_text(_safe(item.stream.release), max(widths[0] - Text(suffix).cell_len, 1)) + suffix
    return _columns(
        (
            title,
            image,
            _language(item),
            str(item.stream.seeders) if item.stream.seeders is not None else "?",
            _safe(item.stream.size_text or "?"),
        ),
        widths,
    )


def _empty_offer(offer: EpisodeOffer) -> str:
    checked: str = offer.checked_at.astimezone().strftime("%H:%M")
    if not offer.candidates:
        return f"Brak kandydatów w źródle (sprawdzono {checked})"
    return f"Brak wydania E{offer.key.number} (sprawdzono {checked}; niezgodnych: {offer.counts.get('mismatch', 0)})"


def _offer_reason(offer: EpisodeOffer) -> str:
    if offer.suggestion is None:
        return ""
    item: RankedCandidate = offer.candidates[offer.suggestion]
    group: str = _safe(parse_release_name(item.stream.release).group or "—")
    if item.identity.verdict is IdentityVerdict.INSUFFICIENT:
        return f"Niepewne wydanie E{offer.key.number}: może nie być tym odcinkiem · grupa: {group}"
    image: str = f"{item.facts.resolution}p" if item.facts.resolution else "obraz nieznany"
    platform: str = f" · {item.facts.platform}" if item.facts.platform else ""
    return (
        f"Powód E{offer.key.number}: {image} · {_language(item)}{platform} · grupa: {group}"
        " · pierwsze zgodne według preferencji"
    )


def _identity_fallback(verdict: IdentityVerdict) -> str:
    return {
        IdentityVerdict.MATCH: "Nazwa wskazuje wybrany odcinek.",
        IdentityVerdict.INSUFFICIENT: "Nie można jednoznacznie ustalić tożsamości odcinka.",
        IdentityVerdict.MISMATCH: "Nazwa wskazuje inny materiał.",
    }[verdict]


def _candidate_details(item: RankedCandidate) -> str:
    index: str = str(item.stream.file_index) if item.stream.file_index is not None else "brak"
    platform: str = item.facts.platform or "—"
    support: str = " · format nieobsługiwany" if item.facts.supported is False else ""
    return f"Plik: {_safe(item.stream.file_name or 'brak')} · indeks: {index} · platforma: {platform}{support}"
