"""Anime release search and download screen built on the shared terminal renderer."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from math import ceil
from time import sleep, time
from typing import Final
from uuid import uuid4

from natsort import natsorted
from prompt_toolkit.mouse_events import MouseEvent
from rich.console import Console
from rich.text import Text

from anishift.application import (
    AcquisitionService,
    AdmissionConflict,
    AppService,
    CandidateNumbering,
    EpisodeBatch,
    EpisodeFile,
    EpisodeFiles,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeOfferView,
    EpisodeReason,
    EpisodeResult,
    EpisodeStatus,
    Franchise,
    FranchiseEntry,
    IdentityVerdict,
    ListedEpisode,
    PolishClass,
    RankedCandidate,
    SearchQuery,
    TitleCandidate,
    TitleStatus,
    confidence_text,
    conflict_label,
    decode_view,
    parse_query,
    premiere_order,
    quality_text,
    visible,
)
from anishift.application.cancellation import EventCancellationToken
from anishift.application.episode_commands import MAX_EPISODE_KEYS
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.anime_panel import AnimePanel
from anishift.cli.interactive.anime_state import AnimeRow, AnimeScreen, AnimeViewState, NoticeKind
from anishift.cli.interactive.anime_view import WIDE_COLUMNS, visible_rows
from anishift.cli.interactive.subscription_texts import (
    SubscriptionDraft,
    SubscriptionState,
    check_text,
    earlier_episodes,
    episode_label,
    notice_line,
    polish_line,
    row_state,
    row_summary,
    subscription_draft,
)
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError, ControlErrorCode
from anishift.utils.logger import get_logger

__all__ = ["AnimeController", "AnimeResult"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_WORKER_NAME: Final[str] = "anishift-anime"
"""Name of the thread carrying every search and download of this screen."""

_SEARCHING_TITLE: Final[str] = "Szukam tytułu…"
"""Sentence shown while the anime catalog names the title behind the typed phrase."""

_LOADING_ENTRIES: Final[str] = "Wczytuję wpisy…"
"""Sentence shown while the franchise of a title is fetched."""

_SENDING: Final[str] = "Wysyłam…"
"""Sentence shown while the torrent client takes the chosen releases."""

_ADDING: Final[str] = "Dodaję subskrypcję…"
"""Sentence shown while the owner reads the season and saves a new subscription."""

_DRAFT_ADD: Final[str] = "Dodaj subskrypcję"
"""Draft action that sends the subscription to the owner."""

_DRAFT_CANCEL: Final[str] = "Anuluj"
"""Draft action that returns to the screen the draft was opened from."""

_DRAFT_AIRED: Final[str] = "Już wyemitowane · zaznaczone pobiorę od razu"
"""Draft heading of the aired episodes that Dodaj subskrypcję downloads at once."""

_SUBSCRIBED: Final[str] = "Ten sezon jest już subskrybowany · Enter pokaż"
"""Draft line of a season already followed, leading to its details."""

_NOT_AIRING: Final[str] = "Ten wpis nie ma przyszłych odcinków"
"""Notice for S on an entry that cannot be subscribed."""

_ANNOUNCED: Final[str] = "Zapowiedź · odcinków jeszcze nie ma · S subskrybuj"
"""Notice for Enter on an announced entry, which opens nothing."""

_EXTRA_FORMATS: Final[frozenset[str]] = frozenset({"OVA", "SPECIAL"})
"""AniList formats U08 lists as related extras of the subscribed season."""

_WIDE_SUBSCRIPTION_KEYS: Final[int] = 61
"""Key hint width from which U08 shows full labels and I; narrower hints leave I to the ? details."""

_MAX_BATCH: Final[int] = MAX_EPISODE_KEYS
"""Most episodes one D press sends to the owner, matching its batch limit."""

_BATCH_POLL_S: Final[float] = 1.0
"""Pause between reads of one accepted episode batch receipt."""

_BATCH_WAIT_S: Final[float] = 180.0
"""Longest time the panel follows one episode batch before leaving it to the owner."""

EPISODE_REASON_LABELS: Final[dict[str, str]] = {
    EpisodeReason.ADMITTED: "Zlecono",
    EpisodeReason.NO_SUGGESTION: "Brak wydania",
    EpisodeReason.EPISODE_NOT_AIRED: "Nie wyemitowano",
    AdmissionConflict.ADMITTED: "Zlecono",
    EpisodeReason.EPISODE_IN_PROGRESS: "W toku",
    AdmissionConflict.POSSIBLY_ADMITTED: "Już zlecone?",
    AdmissionConflict.TRANSFER_RECORDED: "Konflikt hasha",
    EpisodeReason.SOURCE_FAILED: "Błąd źródła",
    EpisodeReason.LEGACY_UNREADABLE: "Błąd zleceń",
    EpisodeReason.EPISODE_FILE_UNRESOLVED: "Wskaż plik",
    EpisodeReason.TRANSFER_FAILED: "Błąd pobierania",
    EpisodeReason.PUBLICATION_FAILED: "Błąd eksportu",
    EpisodeReason.WAITING_PREVIOUS_TRANSFER: "Czeka na stare",
    EpisodeReason.PUBLICATION_MISSING: "Brak pliku",
    EpisodeReason.RESULT_MISSING: "Do pobrania",
    EpisodeReason.PACK_IN_PROGRESS: "Czeka na paczkę",
    EpisodeReason.SUBSCRIPTION_AWAITING_AIRING: "Czeka na emisję",
    EpisodeReason.SUBSCRIPTION_AWAITING_RELEASE: "Czeka na wydanie",
    EpisodeReason.SUBSCRIPTION_CHECKING: "Kontrola",
    EpisodeReason.SUBSCRIPTION_CHECK_SKIPPED: "Bez kontroli",
    EpisodeReason.SUBSCRIPTION_EXHAUSTED: "Wyczerpano próby",
}
"""Shared column labels for owner batch and episode status reasons."""

_IN_PROGRESS_HINT: Final[str] = "W toku · C anuluj w Przetwarzaniu"
"""Notice naming where an active episode can be cancelled instead of ordered again."""

_EPISODE_ADMITTED: Final[str] = "Odcinek już zlecony"
"""Notice shown when the owner refuses an already admitted episode."""

_REPEAT_HINT: Final[str] = "P pobierz ponownie"
"""Hint naming the explicit repeat after the owner refuses an already ordered episode."""

_REPEATABLE_REFUSALS: Final[dict[str, str]] = {
    AdmissionConflict.ADMITTED: _EPISODE_ADMITTED,
    AdmissionConflict.POSSIBLY_ADMITTED: EPISODE_REASON_LABELS[AdmissionConflict.POSSIBLY_ADMITTED],
    EpisodeReason.PACK_IN_PROGRESS: EPISODE_REASON_LABELS[EpisodeReason.PACK_IN_PROGRESS],
}
"""Notice of each owner refusal that P can override with an explicit repeat."""

_EPISODE_STATE_LABELS: Final[dict[str, str]] = {
    "ordered": "Zlecono",
    "downloading": "Pobieram",
    "downloaded": "Pobrano",
    "processing": "Przetwarzam",
    "processing_failed": "Błąd",
    "ready": "Gotowe",
    "possibly_admitted": "Już zlecone?",
}
"""Stan column label of each owner episode state other than not ordered."""

_UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
"""Sentence shown when the session was built without an acquisition boundary."""

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

_COMMAND_FAILED: Final[str] = (
    "Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie."
)
"""Safe explanation shared by failed catalogue commands and local worker defects."""

_ENTRY_STATUSES: Final[dict[str, str]] = {
    "FINISHED": "zakończone",
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

_SHORT_REASON_LENGTH: Final[int] = 72
"""Maximum explanation length in the compact candidate detail."""

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
    "Mapped numbering cannot be checked without target numbering.": (
        "Bez numeracji szukanego odcinka nie da się sprawdzić numeru katalogowego."
    ),
    "Mapped number equals the target absolute number; numbering is ambiguous.": (
        "Numer w nazwie równa się numerowi absolutnemu odcinka; numeracja jest niejednoznaczna."
    ),
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
    """Signal whether the anime controller stays open, returns Home or returns to the subscription list."""

    CONTINUE = "continue"
    HOME = "home"
    SUBSCRIPTIONS = "subscriptions"


class _Screen(StrEnum):
    QUERY = "query"
    TITLES = "titles"
    BUSY = "busy"
    PROBLEM = "problem"
    ENTRIES = "entries"
    EPISODES = "episodes"
    OFFER = "offer"
    CANDIDATES = "candidates"
    DRAFT = "draft"


class AnimeController:
    """Own one ephemeral release search while AppService owns the network boundary."""

    def __init__(
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
        self._lock: threading.RLock = threading.RLock()
        self._generation: int = 0
        self._worker: threading.Thread | None = None
        self._current_screen: _Screen = _Screen.QUERY
        self._query_input: TextInput = TextInput()
        self._input_focused: bool = False
        self._candidates: tuple[TitleCandidate, ...] = ()
        self._titles_shown: bool = False
        self._entries_skipped: bool = False
        self._highlighted: int = 0
        self._range_input: TextInput | None = None
        self._busy: str = _SEARCHING_TITLE
        self._work_sending: bool = False
        self._notice: str = ""
        self._problem: str = ""
        self._suggestion: str = ""
        self._problem_return: _Screen = _Screen.QUERY
        self._clock: Callable[[], float] = time
        self._show_list: Callable[[str | None, str], None] | None = None
        self._notify_list: Callable[[str], None] | None = None
        self._list_batch: str | None = None
        self._list_notice: str | None = None
        self._list_hold: bool = False
        self._subscription_command: tuple[str, Mapping[str, object], int | None] | None = None
        self._subscribed: dict[int, Mapping[str, object]] = {}
        self._paused: bool = False
        self._from_subscriptions: bool = False
        self._subscription: Mapping[str, object] | None = None
        self._subscription_details: Mapping[str, object] = {}
        self._draft: SubscriptionDraft | None = None
        self._draft_id: int = 0
        self._draft_title: str = ""
        self._draft_return: _Screen = _Screen.QUERY
        self._draft_cursor: str = ""
        self._draft_command: str = ""
        self._draft_listing: EpisodeListing | None = None
        self._draft_marks: set[int] = set()
        self._initialize_episode_state()
        self._view: AnimeViewState = AnimeViewState(query=self._query_input, query_focused=False)
        self._panel: AnimePanel = AnimePanel(self._view, self._panel_action, self._now)
        self._notice_kind: NoticeKind = NoticeKind.INFO
        if self._acquisition is None:
            self._screen = _Screen.PROBLEM
            self._problem = _UNAVAILABLE

    def _initialize_episode_state(self) -> None:
        self._franchise: Franchise | None = None
        self._entry: FranchiseEntry | None = None
        self._shown_entry: FranchiseEntry | None = None
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
        self._release_moved: bool = False
        self._busy_return: _Screen = _Screen.QUERY
        self._work_cancel: EventCancellationToken = EventCancellationToken()
        self._provider_locks: dict[str, float] = {}
        self._problem_provider: str = ""
        self._sending: set[EpisodeKey] = set()
        self._episode_states: dict[EpisodeKey, EpisodeStatus] = {}
        self._offer_view: EpisodeOfferView | None = None
        self._offer_id: str | None = None
        self._offer_refreshing: bool = False
        self._offer_refresh_pending: bool = False
        self._choice_sending: bool = False
        self._confirm_view: EpisodeOfferView | None = None
        self._files: EpisodeFiles | None = None
        self._confirm_choice: RankedCandidate | None = None
        self._pending_batch: EpisodeBatch | None = None
        self._batch_listing: EpisodeListing | None = None
        self._batch_running: bool = False
        self._batch_results: dict[EpisodeKey, EpisodeResult] = {}
        self._stale: bool = False
        self._details_open: bool = False
        self._columns: int = WIDE_COLUMNS

    @property
    def _screen(self) -> _Screen:
        return self._current_screen

    @_screen.setter
    def _screen(self, screen: _Screen) -> None:
        self._current_screen = screen
        if screen in {_Screen.QUERY, _Screen.TITLES, _Screen.ENTRIES}:
            self._shown_entry = None

    def handle_key(self, key: str) -> AnimeResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            self._sync_view()
            if key in {"interrupt", "copy", "text:c", "text:C"} and self._panel.copy(key):
                self._notice = self._view.notice
                self._notice_kind = self._view.notice_kind
                return AnimeResult.CONTINUE
            if self._handle_input(key):
                return AnimeResult.CONTINUE
            if self._details_open:
                if key in {"escape", "interrupt", "text:?"}:
                    self._details_open = False
                    self._view.selection = None
                else:
                    self._panel.handle(key)
                return AnimeResult.CONTINUE
            self._notice_kind = NoticeKind.INFO
            if self._pending_batch is not None and key == "enter" and not self._batch_running:
                self._resume_batch()
                return AnimeResult.CONTINUE
            if self._stale and key.casefold() in {"text:d", "text:p", "enter"}:
                self._notice = "Widok nieaktualny · otwórz odcinki ponownie"
                self._notice_kind = NoticeKind.WARNING
                return AnimeResult.CONTINUE
            if self._screen is _Screen.QUERY:
                result: AnimeResult = self._handle_query(key)
            elif self._screen is _Screen.TITLES:
                self._panel.handle(key)
                self._adopt_view_input()
                result = AnimeResult.CONTINUE
            elif self._screen is _Screen.BUSY:
                result = self._handle_busy(key)
            elif self._screen in {_Screen.ENTRIES, _Screen.EPISODES, _Screen.OFFER, _Screen.CANDIDATES, _Screen.DRAFT}:
                result = self._draft_mark_key(key) or self._subscription_key(key) or self._panel_key(key)
            else:
                result = self._handle_problem(key)
        return result

    def _panel_key(self, key: str) -> AnimeResult:
        self._panel.handle(key)
        self._adopt_view_input()
        return AnimeResult.CONTINUE

    def link_subscriptions(
        self, show_list: Callable[[str | None, str], None], notify_list: Callable[[str], None]
    ) -> None:
        """Receive the panel callbacks that open the subscription list and later update its notice."""
        with self._lock:
            self._show_list = show_list
            self._notify_list = notify_list

    def replay_list_batch(self) -> bool:
        """Replay the draft's order whose answer was lost, under its command ID, when one waits."""
        with self._lock:
            batch: EpisodeBatch | None = self._pending_batch
            if batch is None or batch.command_id != self._list_batch or self._batch_running:
                return False
            self._resume_batch()
            return True

    def _flush_list_notice(self) -> None:
        with self._lock:
            if self._list_hold:
                return
            notice: str | None = self._list_notice
            self._list_notice = None
            notify: Callable[[str], None] | None = self._notify_list
        if notice is not None and notify is not None:
            notify(notice)

    def refresh_subscriptions(self, rows: Sequence[Mapping[str, object]], *, paused: bool) -> None:
        """Project the owner's subscription rows used by drafts and the open subscription header."""
        with self._lock:
            self._subscribed = {key: row for row in rows if isinstance(key := row.get("anilist_id"), int)}
            self._paused = paused
            if self._subscription is not None:
                identifier: object = self._subscription.get("subscription_id")
                self._subscription = next(
                    (row for row in rows if row.get("subscription_id") == identifier), self._subscription
                )

    def take_subscription_command(self) -> tuple[str, Mapping[str, object], int | None] | None:
        """Hand one subscription command chosen in the details, with its target number, to the panel."""
        with self._lock:
            command: tuple[str, Mapping[str, object], int | None] | None = self._subscription_command
            self._subscription_command = None
            return command

    def start_subscription_search(self) -> None:
        """Open the title search on behalf of the subscription list, to which Esc returns."""
        with self._lock:
            self._generation += 1
            self._subscription = None
            self._from_subscriptions = True
            self._details_open = False
            self._screen = _Screen.QUERY
            self._input_focused = True

    @property
    def in_subscriptions(self) -> bool:
        """Whether the shown screen serves the subscription list: U08 or a search started there."""
        with self._lock:
            return self._from_subscriptions

    def leave_subscriptions(self) -> None:
        """Drop the subscription context so the Anime tab shows its own search."""
        with self._lock:
            self._leave_subscriptions()

    def open_subscription(self, row: Mapping[str, object]) -> None:
        """Show the episodes of one followed season under its subscription header."""
        with self._lock:
            self._open_subscription(row)

    def _open_subscription(self, row: Mapping[str, object]) -> None:
        self._subscription = row
        self._subscription_details = {}
        self._from_subscriptions = True
        self._details_open = False
        self._episode_marks.clear()
        self._positions[_Screen.EPISODES] = 0
        self._offsets[_Screen.EPISODES] = 0
        generation: int = self._start_work("Wczytuję odcinki…", _Screen.QUERY)
        self._spawn(self._load_subscription, (row, generation, self._work_cancel))

    def subscription_checked(self, subscription_id: str, check: Mapping[str, object]) -> None:
        """Show a finished check in the header of the open subscription."""
        with self._lock:
            if self._subscription is None or self._subscription.get("subscription_id") != subscription_id:
                return
            self._subscription_details = {**self._subscription_details, "last_check": check}
            self._notice = ""

    def _subscription_key(self, key: str) -> AnimeResult | None:
        row: Mapping[str, object] | None = self._subscription
        if row is None or self._screen is not _Screen.EPISODES:
            return None
        folded: str = key.casefold()
        kind: str | None = {
            "text:w": "subscription_resume" if row.get("paused") else "subscription_pause",
            "text:f": "subscription_check",
            "text:x": "subscription_remove",
            "delete": "subscription_remove",
        }.get(folded)
        number: int | None = self._waiting_number() if folded == "text:t" else None
        if number is not None:
            kind = "subscription_check"
        if kind is not None:
            self._subscription_command = (kind, row, number)
            self._notice = "Sprawdzam…" if kind == "subscription_check" else ""
        if kind == "subscription_remove" or key in {"escape", "interrupt"}:
            self._leave_subscriptions()
            return AnimeResult.SUBSCRIPTIONS
        return None if kind is None else AnimeResult.CONTINUE

    def _waiting_number(self) -> int | None:
        status: EpisodeStatus | None = self._cursor_status()
        return None if status is None or status.polish_wait_until is None else status.key.number

    def _cursor_status(self) -> EpisodeStatus | None:
        listing: EpisodeListing | None = self._listing
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        position: int = self._positions.get(_Screen.EPISODES, 0)
        if listing is None or position >= len(shown):
            return None
        return self._episode_states.get(EpisodeKey(listing.anilist_id, shown[position].number))

    def _leave_subscriptions(self) -> None:
        self._generation += 1
        self._subscription = None
        self._subscription_details = {}
        self._from_subscriptions = False
        self._range = None
        self._episode_marks.clear()
        self._details_open = False
        self._notice = ""
        self._screen = _Screen.QUERY

    def _load_subscription(self, row: Mapping[str, object], generation: int, cancel: EventCancellationToken) -> None:
        anilist_id: object = row.get("anilist_id")
        if self._resident is None or self._acquisition is None or not isinstance(anilist_id, int):
            self._fail(generation, _UNAVAILABLE, "", _Screen.QUERY)
            return
        try:
            details: Mapping[str, object] = self._resident.command(
                "subscription_get", {"subscription_id": row.get("subscription_id")}
            )
            franchise: Franchise = self._acquisition.franchise(anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.QUERY, "anilist")
            return
        entry: FranchiseEntry | None = next((item for item in franchise.entries if item.anilist_id == anilist_id), None)
        if entry is None:
            self._fail(generation, "Katalog nie zawiera już tego wpisu", "", _Screen.QUERY)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._subscription_details = details
            self._adopt_franchise(franchise)
            self._entries_skipped = False
            self._entry = entry
            self._shown_entry = entry
            self._listing = None
        self._load_episodes(entry, generation)

    def _start_draft(self) -> None:
        anilist_id, title, listing = self._draft_source()
        if anilist_id is None:
            return
        self._draft_return = self._screen
        self._draft_command = uuid4().hex
        self._draft_id = anilist_id
        self._draft_title = title
        if anilist_id in self._subscribed or listing is not None:
            self._open_draft(listing)
            return
        generation: int = self._start_work("Wczytuję odcinki…", self._screen)
        self._spawn(self._load_draft, (anilist_id, generation))

    def _draft_source(self) -> tuple[int | None, str, EpisodeListing | None]:
        if self._screen is _Screen.TITLES and self._candidates:
            candidate: TitleCandidate = self._candidates[self._highlighted]
            return candidate.anilist_id, candidate.english or candidate.romaji, None
        if self._screen is _Screen.ENTRIES and self._franchise is not None and self._franchise.entries:
            entry: FranchiseEntry = self._franchise.entries[self._positions.get(_Screen.ENTRIES, 0)]
            return entry.anilist_id, entry.english or entry.romaji, None
        if self._screen is _Screen.EPISODES and self._listing is not None and self._entry is not None:
            return self._listing.anilist_id, self._entry.english or self._entry.romaji, self._listing
        return None, "", None

    def _load_draft(self, anilist_id: int, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            listing: EpisodeListing = self._acquisition.episodes(anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, self._draft_return, "anizip")
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._episode_states.update(states)
            self._open_draft(listing)
        self._invalidate()

    def _open_draft(self, listing: EpisodeListing | None) -> None:
        self._screen = self._draft_return
        if self._draft_id not in self._subscribed:
            draft: SubscriptionDraft | None = (
                None if listing is None else subscription_draft(listing, self._moment(), paused=self._paused)
            )
            if draft is None:
                self._notice = _NOT_AIRING
                self._notice_kind = NoticeKind.WARNING
                return
            self._draft = draft
        else:
            self._draft = None
        self._draft_listing = listing
        self._draft_marks = {item.number for item in self._draft_episodes()}
        self._draft_cursor = ""
        self._offsets[_Screen.DRAFT] = 0
        self._follow_cursor = True
        self._screen = _Screen.DRAFT

    def _draft_rows(self) -> tuple[AnimeRow, ...]:
        if self._draft is None:
            return (AnimeRow("show", _SUBSCRIBED),)
        lines: tuple[AnimeRow, ...] = tuple(
            row
            for index, value in enumerate(self._draft.lines)
            for row in (
                *((AnimeRow(f"gap{index}", "", navigable=False),) if index else ()),
                *(
                    AnimeRow(f"line{index}.{piece}", wrapped.plain)
                    for piece, wrapped in enumerate(
                        Text(value).wrap(Console(width=self._columns - 4), self._columns - 4)
                    )
                ),
            )
        )
        episodes: tuple[ListedEpisode, ...] = self._draft_episodes()
        aired: tuple[AnimeRow, ...] = (
            (
                AnimeRow("gap.aired", "", navigable=False),
                AnimeRow("aired", _DRAFT_AIRED, navigable=False),
                *(
                    AnimeRow(
                        f"ep:{item.number}",
                        f"E{item.number}  {item.title or f'Odcinek {item.number}'}",
                        number=str(item.number),
                    )
                    for item in episodes
                ),
            )
            if episodes
            else ()
        )
        buttons: tuple[AnimeRow, ...] = (
            (AnimeRow("add", _DRAFT_ADD), AnimeRow("cancel", _DRAFT_CANCEL))
            if self._draft.addable
            else (AnimeRow("cancel", _DRAFT_CANCEL),)
        )
        return (*lines, *aired, AnimeRow("gap", "", navigable=False), *buttons)

    def _draft_episodes(self) -> tuple[ListedEpisode, ...]:
        listing: EpisodeListing | None = self._draft_listing
        if self._draft is None or listing is None:
            return ()
        return tuple(item for item in self._draft.aired if self._unordered(EpisodeKey(listing.anilist_id, item.number)))

    def _unordered(self, key: EpisodeKey) -> bool:
        status: EpisodeStatus | None = self._episode_states.get(key)
        return key not in self._sending and (status is None or status.state == "not_ordered")

    def _draft_mark_key(self, key: str) -> AnimeResult | None:
        if self._screen is not _Screen.DRAFT or key.casefold() not in {"space", "text:a"}:
            return None
        self._toggle_draft(every=key.casefold() == "text:a")
        return AnimeResult.CONTINUE

    def _toggle_draft(self, *, every: bool) -> None:
        numbers: set[int] = {item.number for item in self._draft_episodes()}
        if every:
            self._draft_marks = set() if numbers <= self._draft_marks else numbers
            return
        chosen: str = self._view.items[self._view.cursor].key if self._view.items else ""
        if chosen.startswith("ep:"):
            self._draft_marks ^= {int(chosen.removeprefix("ep:"))}

    def _draft_key(self, key: str) -> None:
        if key in {"escape", "interrupt"}:
            self._screen = self._draft_return
            return
        if key != "enter" or not self._view.items:
            return
        chosen: str = self._view.items[self._view.cursor].key
        if chosen.startswith("ep:"):
            self._toggle_draft(every=False)
        elif chosen == "cancel":
            self._screen = self._draft_return
        elif chosen == "show" and self._draft_id in self._subscribed:
            self._open_subscription(self._subscribed[self._draft_id])
        elif chosen == "add" and self._resident is not None:
            self._add_draft()

    def _add_draft(self) -> None:
        keys: tuple[EpisodeKey, ...] = tuple(
            EpisodeKey(self._draft_id, item.number)
            for item in self._draft_episodes()
            if item.number in self._draft_marks
        )
        if keys and self._pending_batch is not None:
            self._notice = "Trwa partia · Enter sprawdź wynik"
            return
        if len(keys) > _MAX_BATCH:
            self._notice = "Limit: 100 odcinków · A odznacz wszystkie"
            return
        generation: int = self._start_work(_ADDING, _Screen.DRAFT, sending=True)
        self._spawn(self._add_subscription, (self._draft_id, self._draft_command, keys, generation))

    def _add_subscription(
        self, anilist_id: int, command_id: str, keys: tuple[EpisodeKey, ...], generation: int
    ) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        try:
            answer: Mapping[str, object] = resident.subscription_add(anilist_id, command_id=command_id)
        except (AniShiftError, OSError, ValueError) as problem:
            with self._lock:
                if generation != self._generation:
                    return
                self._worker = None
                self._screen = _Screen.DRAFT
                self._notice = _stated(problem)[0]
                self._notice_kind = NoticeKind.WARNING
            self._invalidate()
            return
        identifier: object = answer.get("subscription_id")
        refusal: str = self._order_aired(resident, keys)
        show_list: Callable[[str | None, str], None] | None = None
        with self._lock:
            if generation == self._generation:
                self._worker = None
                self._from_subscriptions = False
                self._screen = self._draft_return
                show_list = self._show_list
        if show_list is not None:
            show_list(
                identifier if isinstance(identifier, str) else None,
                f"Dodano subskrypcję · {refusal}" if refusal else "",
            )
        with self._lock:
            self._list_hold = False
        self._flush_list_notice()
        self._invalidate()

    def _order_aired(self, resident: ResidentSession, keys: tuple[EpisodeKey, ...]) -> str:
        with self._lock:
            listing: EpisodeListing | None = self._draft_listing
            if not keys or listing is None or self._pending_batch is not None:
                return ""
            command_id: str = self._open_batch(listing, keys)
            self._batch_running = True
            self._list_hold = True
        try:
            batch: EpisodeBatch = resident.episode_download(keys, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime aired episodes order failed", error_class=type(problem).__name__)
            with self._lock:
                notice: str = self._batch_failed(problem, keys)
                if self._pending_batch is not None:
                    self._list_batch = command_id
                return notice
        with self._lock:
            self._batch_running = False
            self._accept_batch(batch)
            if self._pending_batch is None:
                return self._refusals(keys)
            self._list_batch = command_id
            self._resume_batch()
        return ""

    def _sync_subscription_view(self) -> None:
        if self._screen is _Screen.DRAFT:
            self._view.title = f"Nowa subskrypcja \u203a {_safe(self._draft_title)}"
            self._view.controls = (
                ("Enter wybierz · Space zaznacz · A wszystkie · Esc anuluj",)
                if self._draft_episodes()
                else ("Enter wybierz · Esc anuluj",)
            )
            keys: list[str] = [item.key for item in self._view.items]
            wanted: str = self._draft_cursor if self._draft_cursor in keys else self._draft_cursor.split(".")[0] + ".0"
            if wanted not in keys:
                wanted = next((key for key in keys if key.startswith("ep:")), "") or next(
                    (key for key in keys if key in {"add", "cancel", "show"}), ""
                )
            if wanted in keys:
                self._view.cursor = keys.index(wanted)
                self._positions[_Screen.DRAFT] = self._view.cursor
            if self._view.items and not self._view.items[self._view.cursor].navigable:
                self._view.cursor = next(
                    (index for index, item in enumerate(self._view.items) if item.navigable), self._view.cursor
                )
        facts: tuple[str, ...] = self._subscription_facts()
        if not facts or self._subscription is None:
            return
        self._view.title = f"Subskrypcje \u203a {facts[0]}"
        self._view.global_status = facts[1]
        self._view.status_kind = NoticeKind.INFO
        self._view.notice = self._view.notice or " · ".join(note for note in facts[2:] if note)
        toggle: str = "W wznów" if self._subscription.get("paused") else "W wstrzymaj"
        wide: bool = self._columns >= _WIDE_SUBSCRIPTION_KEYS
        episode_keys: str = (
            "Space zaznacz · D pobierz · I wydania · P ponownie · ? więcej"
            if wide
            else "Space · D pobierz · P ponownie · ? więcej"
        )
        if self._waiting_number() is not None:
            episode_keys = "T pobierz teraz · " + episode_keys.replace(" · P ponownie", "")
        self._view.controls = (episode_keys, f"{toggle} · F szukaj{' teraz' if wide else ''} · X usuń · Esc lista")

    def _subscription_facts(self) -> tuple[str, ...]:
        if self._screen is not _Screen.EPISODES or self._subscription is None:
            return ()
        state: SubscriptionState = row_state(self._subscription, self._moment())
        return (
            _safe(str(self._subscription.get("title", ""))),
            f"{state.text} · {row_summary(self._subscription)}",
            self._last_check(),
            "" if state.detail == state.text else state.detail,
            self._polish_line(),
            self._notice_line(),
            self._earlier_episodes(),
        )

    def _polish_line(self) -> str:
        due: EpisodeStatus | None = self._focused_status(lambda item: item.polish is not None)
        if due is None:
            return ""
        return f"E{due.key.number} {polish_line(due.polish, due.polish_wait_until, skipped=due.polish_skipped)}"

    def _notice_line(self) -> str:
        noted: EpisodeStatus | None = self._focused_status(lambda item: bool(item.notices))
        return "" if noted is None else notice_line(noted.key.number, noted.notices)

    def _focused_status(self, shown: Callable[[EpisodeStatus], bool]) -> EpisodeStatus | None:
        """Return the highlighted episode state when it has the fact, else the lowest episode that has it."""
        listing: EpisodeListing | None = self._listing
        due: EpisodeStatus | None = self._cursor_status()
        if due is not None and shown(due):
            return due
        return min(
            (
                item
                for item in self._episode_states.values()
                if shown(item) and listing is not None and item.key.anilist_id == listing.anilist_id
            ),
            key=lambda item: item.key.number,
            default=None,
        )

    def _moment(self) -> datetime:
        return datetime.fromtimestamp(self._clock(), UTC)

    def _earlier_episodes(self) -> str:
        start: object = self._subscription_details.get("first_target")
        if self._listing is None or not isinstance(start, int):
            return ""
        numbers: list[int] = []
        for item in self._listing.episodes:
            status: EpisodeStatus | None = self._episode_states.get(EpisodeKey(self._listing.anilist_id, item.number))
            if item.number < start and item.aired and (status is None or status.state == "not_ordered"):
                numbers.append(item.number)
        return earlier_episodes(numbers)

    def _last_check(self) -> str:
        check: object = self._subscription_details.get("last_check")
        if not isinstance(check, Mapping):
            return ""
        moment: object = check.get("checked_at")
        at: str = datetime.fromisoformat(moment).astimezone().strftime("%H:%M") if isinstance(moment, str) else "—"
        return f"Ostatnie sprawdzenie {at}: {check_text(check)}"

    def _now(self) -> float:
        return self._clock()

    def _adopt_view_input(self) -> None:
        if self._details_open:
            return
        self._adopt_cursor()
        if self._screen is _Screen.EPISODES:
            self._episode_marks = {int(key) for key in self._view.selected}
        if self._screen is _Screen.DRAFT and self._view.items:
            self._draft_cursor = self._view.items[self._view.cursor].key
        self._range_input = self._view.range_input
        self._input_focused = (
            self._view.query_focused if self._screen is _Screen.QUERY else self._range_input is not None
        )
        self._notice = self._view.notice
        self._notice_kind = self._view.notice_kind
        self._offsets[self._screen] = self._view.offset
        self._follow_cursor = True

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
            self._sync_view()
            self._panel.scroll(direction * 3)
            if not self._details_open:
                self._offsets[self._screen] = self._view.offset
            self._notice = ""
            self._follow_cursor = False

    def render(self, columns: int, rows: int) -> Text:
        """Render the cached state of the current screen for one terminal geometry."""
        with self._lock:
            self._columns = min(columns - 4, WIDE_COLUMNS)
            self._sync_view()
            self._visible_count = visible_rows(rows)
            offset: int = min(
                self._view.offset if self._details_open else self._offsets.get(self._screen, 0),
                max(len(self._view.items) - self._visible_count, 0),
            )
            if self._follow_cursor:
                offset = max(min(offset, self._view.cursor), self._view.cursor - self._visible_count + 1)
            self._view.offset = offset
            if not self._details_open:
                self._offsets[self._screen] = offset
            return self._panel.frame(columns, rows)

    def mouse(self, event: MouseEvent) -> None:
        """Delegate text selection and row clicks to the shared Anime panel."""
        with self._lock:
            self._panel.mouse(event)
            if self._details_open:
                return
            self._adopt_cursor()
            self._notice = self._view.notice

    def _adopt_cursor(self) -> None:
        if self._screen is _Screen.TITLES:
            self._highlighted = self._view.cursor
            return
        if self._screen is _Screen.CANDIDATES and self._view.cursor != self._positions.get(self._screen, 0):
            self._release_moved = True
        self._positions[self._screen] = self._view.cursor

    def _panel_action(self, action: str, keys: tuple[str, ...]) -> None:
        del keys
        self._adopt_view_input()
        key: str = {"back": "escape", "download": "text:d", "enter": "enter"}.get(action, f"text:{action}")
        if action == "?":
            self._details_open = True
            self._view.cursor = 0
            self._view.offset = 0
        elif action == "/":
            self._screen = _Screen.QUERY
            self._input_focused = True
        elif self._screen is _Screen.DRAFT:
            self._draft_key(key)
        elif key == "text:s":
            self._start_draft()
        elif self._screen is _Screen.TITLES:
            self._handle_titles(key)
        else:
            self._handle_episode_screen(key)
        self._sync_view()

    def _sync_view(self) -> None:  # noqa: PLR0912, PLR0915
        screens: dict[_Screen, AnimeScreen] = {
            _Screen.QUERY: AnimeScreen.QUERY,
            _Screen.TITLES: AnimeScreen.TITLES,
            _Screen.ENTRIES: AnimeScreen.ENTRIES,
            _Screen.EPISODES: AnimeScreen.EPISODES,
            _Screen.OFFER: AnimeScreen.FILES if self._files is not None else AnimeScreen.RELEASES,
            _Screen.CANDIDATES: AnimeScreen.RELEASES,
            _Screen.BUSY: AnimeScreen.QUERY if self._busy_return is _Screen.QUERY else AnimeScreen.BUSY,
            _Screen.PROBLEM: AnimeScreen.PROBLEM,
            _Screen.DRAFT: AnimeScreen.DRAFT,
        }
        screen: AnimeScreen = screens.get(self._screen, AnimeScreen.DETAILS)
        previous_cursor: int = self._view.cursor
        if self._view.screen is not (AnimeScreen.DETAILS if self._details_open else screen):
            self._view.selection = None
            self._view.selected.clear()
        self._view.screen = screen
        self._view.title = self._entry_heading()
        self._view.cursor = (
            self._highlighted if self._screen is _Screen.TITLES else self._positions.get(self._screen, 0)
        )
        self._view.query_focused = self._input_focused
        self._view.range_input = self._range_input
        self._view.notice = self._notice
        self._view.notice_kind = self._notice_kind
        self._view.global_status = ""
        self._view.status_kind = NoticeKind.WARNING
        self._view.busy = self._busy if self._screen is _Screen.BUSY else ""
        self._view.controls = ()
        self._view.items = self._display_rows()
        self._view.cursor = min(self._view.cursor, max(len(self._view.items) - 1, 0))
        if screen is AnimeScreen.EPISODES:
            self._view.selected = {str(number) for number in self._episode_marks}
        if screen is AnimeScreen.DRAFT:
            self._view.selected = {f"ep:{number}" for number in self._draft_marks}
        self._view.searching = (
            {
                str(key.number)
                for key in self._sending
                if self._listing is not None and key.anilist_id == self._listing.anilist_id
            }
            if screen is AnimeScreen.EPISODES
            else set()
        )
        if self._pending_batch is not None and screen in {AnimeScreen.EPISODES, AnimeScreen.RELEASES}:
            self._view.searching.add("pending")
        if self._choice_sending:
            self._view.searching.add("pending")
        if self._screen is _Screen.BUSY:
            self._view.controls = ("Esc wróć",)
        elif self._screen is _Screen.PROBLEM:
            self._view.notice_kind = NoticeKind.WARNING
            self._view.controls = ("Enter pobierz mimo to | Esc" if self._confirm_choice else "Enter/Esc wróć",)
        elif self._files is not None and self._screen is _Screen.OFFER:
            self._view.title = "Wybierz plik"
            self._view.controls = ("Enter wybierz plik | Esc",)
        elif self._screen is _Screen.OFFER:
            self._view.controls = ("I inne wydania | D pobierz | Esc",)
            self._view.notice = self._notice or " · ".join(self._repeat_warning())
            if self._offer_view is not None and self._offer_view.unknown_previous:
                self._view.global_status = "Nie można potwierdzić odmienności wydania"
        elif self._screen is _Screen.ENTRIES and self._franchise is not None and not self._franchise.complete:
            self._view.notice = self._notice or "Lista niepełna"
        else:
            self._sync_subscription_view()
        if screen is AnimeScreen.RELEASES and self._offer_view is not None and self._offers_running:
            pending: str = ", ".join(self._offer_view.offer.pending) or "uzupełnienia spisów"
            self._view.global_status = f"szukam jeszcze: {pending}"
        if self._details_open:
            item: AnimeRow | None = self._view.items[self._view.cursor] if self._view.items else None
            self._view.screen = AnimeScreen.DETAILS
            self._view.items = self._text_rows(
                (
                    *self._subscription_facts(),
                    item.copy_text if item else "Anime",
                    item.detail if item else "",
                    "Space zaznacz · A wszystkie/żadne · Z zakres",
                    "D pobierz · I wydania · P pobierz ponownie",
                    "C kopiuj wiersz · Ctrl+C kopiuj zaznaczenie",
                )
            )
            self._view.cursor = min(previous_cursor, max(len(self._view.items) - 1, 0))
            self._view.controls = ("C kopiuj | Esc wróć",)

    def _text_rows(self, values: Sequence[str]) -> tuple[AnimeRow, ...]:
        console: Console = Console(width=self._columns - 4)
        return tuple(
            AnimeRow(str(index), line.plain)
            for index, line in enumerate(
                line for value in values if value for line in Text(value).wrap(console, self._columns - 4)
            )
        )

    def _display_rows(self) -> tuple[AnimeRow, ...]:  # noqa: PLR0911
        if self._screen is _Screen.TITLES:
            return tuple(
                AnimeRow(
                    str(item.anilist_id),
                    item.english or item.romaji,
                    date=_year_label(item.year),
                    kind=_format_label(item.format),
                    status=_ENTRY_STATUSES.get(item.status.value, ""),
                )
                for item in self._candidates
            )
        if self._screen is _Screen.ENTRIES:
            return (
                tuple(
                    AnimeRow(
                        str(item.anilist_id),
                        item.english or item.romaji,
                        date=_year_label(item.year),
                        kind=_format_label(item.format),
                        status=_ENTRY_STATUSES.get(item.status, ""),
                    )
                    for item in self._franchise.entries
                )
                if self._franchise
                else ()
            )
        if self._screen is _Screen.EPISODES:
            return self._episode_rows() + self._special_rows()
        if self._screen is _Screen.DRAFT:
            return self._draft_rows()
        if self._screen is _Screen.OFFER and self._files is not None:
            return tuple(AnimeRow(str(item.index), f"{item.path} · {item.size:,} B") for item in self._files.files)
        if self._screen in {_Screen.OFFER, _Screen.CANDIDATES}:
            offer: EpisodeOffer | None = self._highlighted_offer()
            self._view.global_status = offer.status or "" if offer is not None else ""
            suggested: RankedCandidate | None = (
                offer.candidates[offer.suggestion] if offer is not None and offer.suggestion is not None else None
            )
            candidates: tuple[RankedCandidate, ...] = (
                self._release_candidates
                if self._screen is _Screen.CANDIDATES
                else (
                    (offer.candidates[offer.suggestion],) if offer is not None and offer.suggestion is not None else ()
                )
            )
            return tuple(
                AnimeRow(
                    item.stream.info_hash,
                    item.stream.release,
                    image=f"{item.traits.resolution}p" if item.traits.resolution else "?",
                    language=_language(item),
                    seeds=str(item.stream.seeders) if item.stream.seeders is not None else "?",
                    quality=quality_text(item),
                    confidence=_candidate_confidence(item, suggested=item == suggested),
                    detail=_candidate_reason(item, full=True) + " · " + _candidate_details(item),
                    eligible=item.supported is not False,
                    uncertain=item.identity.verdict is not IdentityVerdict.MATCH,
                    suggested=item == suggested,
                )
                for item in candidates
            ) or (
                AnimeRow(
                    "empty",
                    "Szukam…" if self._offers_running and self._offer_view is None else "Brak wydania",
                    eligible=False,
                ),
            )
        if self._screen is _Screen.BUSY:
            return (AnimeRow("busy", self._busy, navigable=False),)
        if self._screen is _Screen.PROBLEM:
            return self._text_rows((self._problem, self._retry_hint(self._problem_provider) or self._suggestion))
        return ()

    def _episode_rows(self) -> tuple[AnimeRow, ...]:
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        if self._listing is None or not shown:
            self._view.notice = self._notice or "Nie znam odcinków tego wpisu"
            return ()
        rows: list[AnimeRow] = []
        for episode in shown:
            status: EpisodeStatus | None = self._episode_states.get(
                EpisodeKey(self._listing.anilist_id, episode.number)
            )
            label: str = _episode_status_label(status) if status else ""
            if not label:
                label = EPISODE_REASON_LABELS[
                    EpisodeReason.RESULT_MISSING if episode.aired else EpisodeReason.EPISODE_NOT_AIRED
                ]
            film: bool = self._entry is not None and self._entry.format == "MOVIE"
            detail: str = ""
            if status is not None and status.reason == EpisodeReason.EPISODE_FILE_UNRESOLVED:
                detail = "Nie ustalono pliku w paczce · Enter wskaż plik"
            elif episode.airs_at_fallback:
                detail = f"E{episode.number}: termin emisji niepotwierdzony (ani.zip)"
            rows.append(
                AnimeRow(
                    str(episode.number),
                    episode.title or ("Film" if film else f"Odcinek {episode.number}"),
                    number="Film" if film else str(episode.number),
                    date=episode.airs_at.astimezone().strftime("%d.%m.%Y") if episode.airs_at else "—",
                    status=label,
                    eligible=self._episode_available(episode),
                    detail=detail,
                    refusal_text=(
                        f"E{episode.number} jeszcze nie wyemitowano"
                        if not episode.aired
                        else self._ordered_episode_notice(episode)
                    ),
                )
            )
        if self._listing.schedule_warning and not self._notice:
            deadline: float = self._listing.schedule_retry_at.timestamp() if self._listing.schedule_retry_at else 0.0
            remaining: int = max(ceil(self._provider_locks.get("anilist", deadline) - self._clock()), 0)
            self._view.notice = "Brak terminów emisji (AniList) · " + (
                f"ponów za {remaining} s" if remaining else "wróć i otwórz ponownie"
            )
        return tuple(rows)

    def _shown_episodes(self) -> tuple[ListedEpisode, ...]:
        if self._listing is None:
            return ()
        first: object = self._subscription_details.get("first_target")
        last: object = self._subscription_details.get("last_target")
        if self._subscription is None or not isinstance(first, int) or not isinstance(last, int):
            return self._listing.episodes
        known: set[int] = {item.number for item in self._listing.episodes}
        return (
            *self._listing.episodes,
            *(
                ListedEpisode(number, aired=self._target_aired(EpisodeKey(self._listing.anilist_id, number)))
                for number in range(first, last + 1)
                if number not in known
            ),
        )

    def _target_aired(self, key: EpisodeKey) -> bool:
        status: EpisodeStatus | None = self._episode_states.get(key)
        return status is None or status.reason != EpisodeReason.SUBSCRIPTION_AWAITING_AIRING

    def _related_extras(self) -> tuple[FranchiseEntry, ...]:
        if self._subscription is None or self._listing is None or self._franchise is None:
            return ()
        anilist_id: int = self._listing.anilist_id
        related: set[int] = {
            item.target_id if item.source_id == anilist_id else item.source_id
            for item in self._franchise.relations
            if anilist_id in {item.source_id, item.target_id}
        }
        return tuple(
            item for item in self._franchise.entries if item.anilist_id in related and item.format in _EXTRA_FORMATS
        )

    def _special_rows(self) -> tuple[AnimeRow, ...]:
        if self._subscription is None or self._listing is None:
            return ()
        extras: tuple[FranchiseEntry, ...] = self._related_extras()
        if not self._listing.specials and not extras:
            return ()
        return (
            AnimeRow(
                "specials", "Dodatki tego sezonu · pobierasz je osobno z listy wpisów", eligible=False, navigable=False
            ),
            *(
                AnimeRow(
                    f"special:{item.key}",
                    _safe(item.title or item.key),
                    number=item.key,
                    date=item.airs_on.strftime("%d.%m.%Y") if item.airs_on else "—",
                    eligible=False,
                    navigable=False,
                )
                for item in self._listing.specials
            ),
            *(
                AnimeRow(
                    f"related:{item.anilist_id}",
                    _safe(item.english or item.romaji),
                    number=item.format or "",
                    date=str(item.year or "—"),
                    status="Enter otwórz",
                    eligible=False,
                )
                for item in extras
            ),
        )

    def _open_extra(self, anilist_id: int) -> None:
        if self._franchise is None:
            return
        self._positions[_Screen.ENTRIES] = next(
            index for index, item in enumerate(self._franchise.entries) if item.anilist_id == anilist_id
        )
        self._subscription = None
        self._subscription_details = {}
        self._from_subscriptions = False
        self._entries_skipped = False
        self._start_episodes()

    def cancel(self) -> None:
        """Blur retained inputs and discard the result of network work still in flight."""
        with self._lock:
            self._from_subscriptions = self._from_subscriptions and self._subscription is not None
            self._input_focused = False
            self._generation += 1
            self._offers_running = False
            if self._confirm_choice is not None:
                self._screen = self._problem_return
            self._confirm_choice = None
            self._offer_view = None
            self._offer_id = None
            self._confirm_view = None
            if self._resident is not None:
                self._resident.interrupt_reads()
            if self._screen is _Screen.BUSY:
                self._stop_work()
                self._screen = self._busy_return
                self._worker = None

    @property
    def input_focused(self) -> bool:
        """Whether Anime currently owns cursor and selection navigation."""
        with self._lock:
            return self._input_focused

    @property
    def accepts_text(self) -> bool:
        """Whether a printable key is typed into a field instead of acting."""
        with self._lock:
            return self._input_focused or self._screen is _Screen.QUERY

    def _handle_input(self, key: str) -> bool:
        editor: TextInput | None = None
        if self._screen is _Screen.QUERY:
            editor = self._query_input
        elif self._screen is _Screen.EPISODES:
            editor = self._range_input
        if editor is None:
            return False
        if self._input_focused and key == "interrupt" and editor.handle(key):
            return True
        if self._screen is _Screen.EPISODES and key in {"escape", "interrupt"}:
            self._range = None
            return True
        if key in {"escape", "interrupt"} and self._input_focused:
            self._input_focused = False
            return True
        if not self._input_focused:
            if key == "enter" or (self._screen is _Screen.QUERY and key == "text:/"):
                self._input_focused = True
            elif self._screen is _Screen.QUERY and (key.startswith(("text:", "paste:")) or key in {"space", "paste"}):
                self._input_focused = True
                editor.handle(key)
            return key not in {"escape", "interrupt"}
        return editor.handle(key)

    def _back_out(self) -> AnimeResult:
        if not self._from_subscriptions:
            return AnimeResult.HOME
        self._from_subscriptions = False
        self._subscription = None
        return AnimeResult.SUBSCRIPTIONS

    def _handle_query(self, key: str) -> AnimeResult:
        if key in {"escape", "interrupt"}:
            return self._back_out()
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
        elif key == "enter":
            self._start_franchise()
        elif key == "text:/":
            self._screen = _Screen.QUERY
            self._input_focused = True
        return AnimeResult.CONTINUE

    def _handle_busy(self, key: str) -> AnimeResult:
        if key not in {"escape", "interrupt"}:
            return AnimeResult.CONTINUE
        self._generation += 1
        self._stop_work()
        self._worker = None
        self._screen = self._busy_return
        return AnimeResult.CONTINUE

    def _stop_work(self) -> None:
        if self._work_sending:
            return
        self._work_cancel.cancel()
        if self._resident is not None:
            self._resident.interrupt_reads()

    def _handle_problem(self, key: str) -> AnimeResult:
        if self._confirm_choice is not None:
            choice: RankedCandidate = self._confirm_choice
            if key in {"escape", "interrupt", "enter"}:
                self._confirm_choice = None
                self._screen = self._problem_return
                if key == "enter":
                    self._choose_release(choice, confirmed=True, shown=self._confirm_view)
                self._confirm_view = None
            return AnimeResult.CONTINUE
        if key in {"escape", "interrupt"}:
            if self._problem_return in {
                _Screen.TITLES,
                _Screen.ENTRIES,
                _Screen.EPISODES,
                _Screen.OFFER,
                _Screen.CANDIDATES,
                _Screen.DRAFT,
            }:
                self._screen = self._problem_return
                return AnimeResult.CONTINUE
            return self._back_out()
        if key != "enter":
            return AnimeResult.CONTINUE
        self._screen = self._problem_return
        self._problem = ""
        self._suggestion = ""
        return AnimeResult.CONTINUE

    def _handle_episode_screen(self, key: str) -> None:
        self._notice = ""
        if key in {"escape", "interrupt"}:
            self._back_episode_screen()
            return
        count: int = self._episode_screen_count()
        if not count:
            return
        if self._screen is _Screen.ENTRIES and key == "enter":
            self._start_episodes()
        elif self._screen is _Screen.EPISODES:
            self._episode_key(key)
        elif self._screen is _Screen.OFFER:
            self._offer_key(key)
        elif self._screen is _Screen.CANDIDATES and key.casefold() == "text:d":
            chosen: RankedCandidate | None = (
                next((item for item in self._release_candidates if item.stream.info_hash in self._view.selected), None)
                if self._view.selected
                else self._release_candidates[self._view.cursor]
            )
            if chosen is not None:
                self._choose_release(chosen)

    def _offer_key(self, key: str) -> None:
        if self._files is not None:
            if key == "enter":
                self._choose_file()
            return
        if key in {"enter", "text:i", "text:I"}:
            self._open_candidates()
        elif key.casefold() == "text:d":
            offer: EpisodeOffer | None = self._highlighted_offer()
            if offer is not None and offer.suggestion is not None:
                self._choose_release(offer.candidates[offer.suggestion])

    def _episode_screen_count(self) -> int:
        if self._screen is _Screen.ENTRIES:
            return len(self._franchise.entries) if self._franchise else 0
        if self._screen is _Screen.EPISODES:
            return len(self._shown_episodes())
        if self._screen is _Screen.OFFER:
            return len(self._files.files) if self._files is not None else len(self._offer_numbers)
        return len(self._release_candidates)

    def _back_episode_screen(self) -> None:
        if self._screen is _Screen.CANDIDATES:
            self._screen = _Screen.OFFER
        elif self._screen is _Screen.OFFER:
            self._generation += 1
            self._offer_id = None
            self._offer_view = None
            if self._resident is not None:
                self._resident.interrupt_reads()
            self._worker = None
            self._offers_running = False
            self._screen = _Screen.EPISODES
        elif self._screen is _Screen.EPISODES:
            self._generation += 1
            if not self._entries_skipped:
                self._screen = _Screen.ENTRIES
            else:
                self._screen = _Screen.TITLES if self._titles_shown else _Screen.QUERY
        else:
            self._screen = _Screen.TITLES if self._titles_shown else _Screen.QUERY

    def _episode_key(self, key: str) -> None:
        listing: EpisodeListing | None = self._listing
        if listing is None:
            return
        shown: tuple[ListedEpisode, ...] = self._shown_episodes()
        position: int = self._positions.get(_Screen.EPISODES, 0)
        if position >= len(shown):
            extra: str = self._special_rows()[position - len(shown)].key
            if key == "enter" and extra.startswith("related:"):
                self._open_extra(int(extra.removeprefix("related:")))
            return
        episode: ListedEpisode = shown[position]
        status: EpisodeStatus | None = self._episode_states.get(EpisodeKey(listing.anilist_id, episode.number))
        if key == "enter" and status is not None and status.reason == EpisodeReason.EPISODE_FILE_UNRESOLVED:
            if status.admission_id is not None:
                self._start_files(status.admission_id)
        elif (
            key.casefold() == "text:p"
            and status is not None
            and (status.state != "not_ordered" or status.admission_id is not None)
        ):
            self._start_owner_offer(episode, repeat=True)
        elif key.casefold() == "text:i":
            self._inspect_episode(episode)
        elif key.casefold() == "text:d":
            if self._resident is None:
                self._notice = _UNAVAILABLE
            else:
                self._start_episode_download(listing, episode)

    def _inspect_episode(self, episode: ListedEpisode) -> None:
        if self._resident is not None and self._listing is not None:
            self._start_owner_offer(episode)
            return
        self._start_offers(episode)

    def _start_episode_download(self, listing: EpisodeListing, highlighted: ListedEpisode) -> None:
        if self._pending_batch is not None:
            self._notice = "Trwa partia · Enter sprawdź wynik"
            return
        selected: set[int] = self._episode_marks or {highlighted.number}
        if len(selected) > _MAX_BATCH:
            self._notice = "Limit: 100 odcinków · Z zmień zakres"
            return
        keys: tuple[EpisodeKey, ...] = tuple(
            EpisodeKey(listing.anilist_id, item.number)
            for item in self._shown_episodes()
            if item.number in selected and self._episode_available(item)
        )
        if not keys:
            self._notice = (
                self._ordered_episode_notice(highlighted)
                if highlighted.aired
                else f"E{highlighted.number} jeszcze nie wyemitowano"
            )
            return
        self._notice = "Szukam wydań…"
        self._submit_batch(listing, keys)

    def _submit_batch(self, listing: EpisodeListing, keys: tuple[EpisodeKey, ...]) -> None:
        self._open_batch(listing, keys)
        self._resume_batch()

    def _open_batch(self, listing: EpisodeListing, keys: tuple[EpisodeKey, ...]) -> str:
        self._sending.update(keys)
        command_id: str = uuid4().hex
        self._pending_batch = EpisodeBatch(command_id, "", keys, "accepted")
        self._batch_listing = listing
        self._batch_results.clear()
        self._view.batch_results.clear()
        return command_id

    def _batch_failed(self, problem: AniShiftError | OSError, keys: tuple[EpisodeKey, ...]) -> str:
        self._batch_running = False
        listed: bool = self._pending_batch is not None and self._pending_batch.command_id == self._list_batch
        notice: str = "Wynik nieznany · Enter sprawdź wynik"
        if isinstance(problem, ControlError) and problem.answered and problem.code is ControlErrorCode.REFUSED:
            self._pending_batch = None
            self._list_batch = None if listed else self._list_batch
            self._sending.difference_update(keys)
            notice = "Nie zlecono · " + _stated(problem)[0]
        if listed:
            self._list_notice = notice
        return notice

    def _refusals(self, keys: tuple[EpisodeKey, ...]) -> str:
        causes: dict[str, list[int]] = {}
        for key in keys:
            result: EpisodeResult | None = self._batch_results.get(key)
            if result is None or result.reason != EpisodeReason.ADMITTED:
                causes.setdefault("przerwano" if result is None else _refused_result(result.reason)[1], []).append(
                    key.number
                )
        named: str = " · ".join(
            f"{episode_label(numbers)}: {cause}" if cause else episode_label(numbers)
            for cause, numbers in causes.items()
        )
        return f"Nie zlecono {named}" if named else ""

    def _resume_batch(self) -> None:
        batch: EpisodeBatch | None = self._pending_batch
        if batch is None or self._batch_running or self._batch_listing is None:
            return
        self._batch_running = True
        threading.Thread(
            target=self._send_episodes,
            args=(self._batch_listing, batch.keys, batch.command_id, self._generation),
            name=_WORKER_NAME,
            daemon=True,
        ).start()

    def receive(self, event: str, payload: Mapping[str, object]) -> None:
        """Correlate owner results independently of navigation and retain unknown intentions."""
        if event == "episode_offer_partial":
            with self._lock:
                if self._offer_id is not None and payload.get("offer_id") == self._offer_id:
                    self.refresh_offer()
            return
        with self._lock:
            if event == "control_problem":
                self._stale = True
                self._notice = "Widok nieaktualny: odpowiedź przekracza limit"
                self._notice_kind = NoticeKind.WARNING
                return
            batch: EpisodeBatch | None = self._pending_batch
            if batch is None or payload.get("command_id") != batch.command_id:
                return
            if event == "episode_result":
                self._accept_result(
                    decode_view(EpisodeResult, {key: value for key, value in payload.items() if key != "command_id"})
                )
            elif event == "episode_batch":
                self._accept_batch(decode_view(EpisodeBatch, payload))
        self._invalidate()
        self._flush_list_notice()

    def _accept_result(self, result: EpisodeResult) -> None:
        batch: EpisodeBatch | None = self._pending_batch
        if batch is None or result.key not in batch.keys or result.key in self._batch_results:
            return
        self._batch_results[result.key] = result
        self._sending.discard(result.key)
        self._episode_states[result.key] = EpisodeStatus(
            result.key,
            "ordered" if result.reason == EpisodeReason.ADMITTED else "not_ordered",
            None if result.reason == EpisodeReason.ADMITTED else result.reason,
            result.admission_id,
            result.operation_id,
        )
        if self._listing is None or self._listing.anilist_id != result.key.anilist_id:
            return
        if result.reason == EpisodeReason.ADMITTED:
            self._episode_marks.discard(result.key.number)
        if self._screen is not _Screen.EPISODES or self._details_open:
            return
        self._sync_view()
        if result.reason == EpisodeReason.ADMITTED:
            self._panel.result(str(result.key.number), admitted=True)
        else:
            status, cause = _refused_result(result.reason)
            self._panel.result(str(result.key.number), admitted=False, status=status, cause=cause)
        self._notice = self._view.notice
        self._notice_kind = self._view.notice_kind

    def _accept_batch(self, batch: EpisodeBatch) -> None:
        pending: EpisodeBatch | None = self._pending_batch
        if pending is None or batch.command_id != pending.command_id or batch.keys != pending.keys:
            return
        for result in batch.results:
            self._accept_result(result)
        if batch.state == "accepted":
            return
        self._sending.difference_update(batch.keys)
        self._pending_batch = None
        self._batch_running = False
        if batch.command_id == self._list_batch:
            self._list_batch = None
            self._list_notice = self._refusals(batch.keys)
        if batch.state == "interrupted":
            remaining: str = ", ".join(
                f"E{key.number}"
                for key in batch.keys
                if key not in self._batch_results or self._batch_results[key].reason != EpisodeReason.ADMITTED
            )
            if remaining:
                self._notice = f"Nie zlecono {remaining} · zaznacz je ponownie"
                self._notice_kind = NoticeKind.WARNING

    def _ordered_episode_notice(self, episode: ListedEpisode) -> str:
        del episode
        return _IN_PROGRESS_HINT

    def _episode_available(self, episode: ListedEpisode) -> bool:
        if self._listing is None or not episode.aired:
            return False
        key: EpisodeKey = EpisodeKey(self._listing.anilist_id, episode.number)
        status: EpisodeStatus | None = self._episode_states.get(key)
        return key not in self._sending and (status is None or not status.active or status.attempt)

    def _send_episodes(
        self, listing: EpisodeListing, keys: tuple[EpisodeKey, ...], command_id: str, generation: int
    ) -> None:
        resident: ResidentSession | None = self._resident
        if resident is None:
            return
        batch: EpisodeBatch | None = None
        try:
            batch = resident.episode_download(keys, command_id=command_id)
            deadline: float = self._clock() + _BATCH_WAIT_S
            while batch.state == "accepted" and self._clock() < deadline:
                with self._lock:
                    self._accept_batch(batch)
                sleep(_BATCH_POLL_S)
                batch = resident.episode_download(keys, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            logger.warning("Anime episode download failed", error_class=type(problem).__name__)
            with self._lock:
                notice: str = self._batch_failed(problem, keys)
                if generation == self._generation:
                    self._notice = notice
                    self._notice_kind = NoticeKind.WARNING
            self._invalidate()
            self._flush_list_notice()
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            self._accept_batch(batch)
            self._batch_running = False
            self._episode_states.update(
                {
                    key: state
                    for key, state in states.items()
                    if state.state != "not_ordered" or key not in self._batch_results
                }
            )
            if batch.state == "accepted" and generation == self._generation:
                self._notice = "Partia trwa · Enter sprawdź wynik"
        self._invalidate()
        self._flush_list_notice()

    def _start_franchise(self) -> None:
        candidate: TitleCandidate = self._candidates[self._highlighted]
        if candidate.status is TitleStatus.NOT_YET_RELEASED:
            self._notice = _ANNOUNCED
            return
        if self._franchise is not None and self._franchise.selected_id == candidate.anilist_id:
            self._open_entries(self._franchise)
            return
        self._franchise = None
        self._entry = None
        self._listing = None
        self._episode_marks.clear()
        self._offers.clear()
        generation: int = self._start_work(_LOADING_ENTRIES, _Screen.TITLES)
        self._spawn(self._load_franchise, (candidate.anilist_id, generation, self._work_cancel))

    def _load_franchise(self, anilist_id: int, generation: int, cancel: EventCancellationToken) -> None:
        if self._acquisition is None:
            return
        try:
            franchise: Franchise = self._acquisition.franchise(anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            self._catalog_failure(generation, problem, _Screen.TITLES, "anilist")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._worker = None
            self._open_entries(franchise)
        self._invalidate()

    def _open_entries(self, franchise: Franchise) -> None:
        self._adopt_franchise(franchise)
        self._entries_skipped = len(franchise.entries) == 1 and franchise.complete
        if self._entries_skipped:
            self._start_episodes(_Screen.TITLES if self._titles_shown else _Screen.QUERY)
            return
        self._screen = _Screen.ENTRIES

    def _adopt_franchise(self, franchise: Franchise) -> None:
        franchise = replace(
            franchise,
            entries=tuple(
                sorted(franchise.entries, key=lambda entry: premiere_order(entry.year, entry.start), reverse=True)
            ),
        )
        self._franchise = franchise
        self._positions[_Screen.ENTRIES] = 0
        self._offsets[_Screen.ENTRIES] = 0
        self._follow_cursor = True

    def _start_episodes(self, back: _Screen = _Screen.ENTRIES) -> None:
        if self._franchise is None:
            return
        entry: FranchiseEntry = self._franchise.entries[self._positions.get(_Screen.ENTRIES, 0)]
        if entry.status == "NOT_YET_RELEASED":
            self._notice = _ANNOUNCED
            return
        same: bool = self._entry == entry and self._listing is not None
        self._entry = entry
        self._shown_entry = entry
        if not same:
            self._listing = None
            self._episode_marks.clear()
            self._positions[_Screen.EPISODES] = 0
            self._offsets[_Screen.EPISODES] = 0
        generation: int = self._start_work("Wczytuję odcinki…", back)
        self._spawn(self._load_episodes, (entry, generation))

    def _read_episode_states(self, listing: EpisodeListing) -> dict[EpisodeKey, EpisodeStatus]:
        numbers: list[int] = [item.number for item in listing.episodes if item.aired]
        first: object = self._subscription_details.get("first_target")
        last: object = self._subscription_details.get("last_target")
        if self._subscription is not None and isinstance(first, int) and isinstance(last, int):
            numbers = sorted({*numbers, *range(first, last + 1)})
        if self._resident is None or not numbers:
            return {}
        try:
            statuses: tuple[EpisodeStatus, ...] = tuple(
                status
                for start in range(0, len(numbers), _MAX_BATCH)
                for status in self._resident.episode_states(listing.anilist_id, numbers[start : start + _MAX_BATCH])
            )
        except (AniShiftError, OSError, TypeError) as problem:
            logger.warning("Anime episode states read failed", error_class=type(problem).__name__)
            return {}
        return {item.key: item for item in statuses}

    def _load_episodes(self, entry: FranchiseEntry, generation: int) -> None:
        if self._acquisition is None:
            return
        try:
            listing: EpisodeListing = self._acquisition.episodes(entry.anilist_id)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            with self._lock:
                if generation != self._generation:
                    return
                self._entries_skipped = False
            self._catalog_failure(generation, problem, _Screen.ENTRIES, "anizip")
            return
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing)
        with self._lock:
            if generation != self._generation:
                return
            self._episode_states.update(states)
            if entry.format == "MOVIE":
                film: ListedEpisode = next((item for item in listing.episodes if item.number == 1), ListedEpisode(1))
                listing = replace(listing, episodes=(film,))
            self._listing = listing
            self._stale = False
            shown: tuple[ListedEpisode, ...] = self._shown_episodes()
            self._episode_marks.intersection_update(item.number for item in shown)
            self._positions[_Screen.EPISODES] = min(self._positions.get(_Screen.EPISODES, 0), max(len(shown) - 1, 0))
            self._follow_cursor = True
            self._screen = _Screen.EPISODES
            self._worker = None
        self._invalidate()

    def _start_offers(self, highlighted: ListedEpisode) -> None:
        self._files = None
        self._offer_view = None
        if self._listing is None:
            self._notice = "Brak mapowania"
            return
        numbers: tuple[int, ...] = (highlighted.number,) if highlighted.aired else ()
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

    def _start_owner_offer(self, episode: ListedEpisode, *, repeat: bool = False) -> None:
        if self._resident is None or self._listing is None or not episode.aired:
            return
        self._files = None
        self._offer_view = None
        self._offer_id = None
        self._offer_refreshing = False
        self._offer_refresh_pending = False
        self._choice_sending = False
        self._resident.interrupt_reads()
        self._offers.clear()
        self._offer_numbers = (episode.number,)
        self._positions[_Screen.OFFER] = 0
        generation: int = self._start_work("Szukam…", _Screen.EPISODES)
        self._screen = _Screen.OFFER
        self._offers_running = True
        self._spawn(
            partial(self._load_owner_offer, repeat=repeat),
            (EpisodeKey(self._listing.anilist_id, episode.number), generation),
        )

    def _load_owner_offer(self, key: EpisodeKey, generation: int, *, repeat: bool) -> None:
        if self._resident is None:
            return
        try:
            started: Mapping[str, object] = self._resident.episode_offer_start(
                key, repeat=repeat, command_id=uuid4().hex
            )
        except (AniShiftError, OSError) as problem:
            self._catalog_failure(generation, problem, _Screen.EPISODES, "torrentio")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._offer_id = decode_view(str, started.get("offer_id"))
            self._worker = None
            self.refresh_offer()

    def refresh_offer(self) -> None:
        """Recover the latest offer after a signal or a reconnected observation channel."""
        with self._lock:
            if self._offer_id is None:
                return
            if self._offer_refreshing:
                self._offer_refresh_pending = True
                return
            self._offer_refreshing = True
            self._spawn(self._read_owner_offer, (self._offer_id, self._generation))

    def _read_owner_offer(self, offer_id: str, generation: int) -> None:  # noqa: PLR0911
        if self._resident is None:
            return
        while True:
            try:
                result: Mapping[str, object] = self._resident.episode_offer_get(offer_id)
            except (AniShiftError, OSError) as problem:
                with self._lock:
                    if generation != self._generation or offer_id != self._offer_id:
                        return
                    self._offer_refreshing = False
                    self._worker = None
                    if self._choice_sending and isinstance(problem, ControlError) and problem.reason == "offer_expired":
                        return
                    if isinstance(problem, ControlError) and problem.reason == "response_too_large":
                        self.receive("control_problem", {})
                        self._invalidate()
                        return
                    self._offer_id = None
                    self._catalog_failure(generation, problem, _Screen.EPISODES, "")
                return
            with self._lock:
                if generation != self._generation or offer_id != self._offer_id:
                    return
                self._accept_offer_state(result, generation)
                if not self._offer_refresh_pending or self._offer_id is None:
                    self._offer_refreshing = False
                    self._worker = None
                    self._invalidate()
                    return
                self._offer_refresh_pending = False

    def _accept_offer_state(self, result: Mapping[str, object], generation: int) -> None:
        if result.get("state") == "failed":
            self._offer_id = None
            self._offer_view = None
            self._confirm_choice = None
            self._confirm_view = None
            reason: str = str(result.get("message"))
            self._catalog_failure(
                generation,
                ControlError(reason, code=ControlErrorCode.INTERNAL, reason=reason, answered=True),
                _Screen.EPISODES,
                "torrentio",
            )
            return
        if result.get("state") != "ready":
            return
        view: EpisodeOfferView = decode_view(EpisodeOfferView, result.get("view"))
        if self._offer_view is not None and view.revision <= self._offer_view.revision:
            return
        highlighted: str | None = (
            self._release_candidates[self._positions.get(_Screen.CANDIDATES, 0)].stream.info_hash
            if self._release_candidates
            and ((self._screen is _Screen.CANDIDATES and self._release_moved) or self._confirm_choice is not None)
            else None
        )
        self._offer_view = view
        self._stale = False
        self._offers[view.offer.key.number] = view.offer
        self._offers_running = result.get("final") is not True
        self._release_candidates = visible(view.offer.candidates)
        self._positions[_Screen.CANDIDATES] = next(
            (index for index, item in enumerate(self._release_candidates) if item.stream.info_hash == highlighted), 0
        )
        self._view.selected.intersection_update(item.stream.info_hash for item in self._release_candidates)
        self._view.selection = None

    def _choose_release(
        self, choice: RankedCandidate, *, confirmed: bool = False, shown: EpisodeOfferView | None = None
    ) -> None:
        if self._choice_sending:
            return
        if self._pending_batch is not None:
            self._notice = "Trwa partia · po jej zakończeniu otwórz wydania ponownie"
            return
        view: EpisodeOfferView | None = shown or self._offer_view
        if self._resident is None or view is None or choice.supported is False:
            return
        if choice.identity.verdict is not IdentityVerdict.MATCH and not confirmed:
            self._confirm_choice = choice
            self._confirm_view = view
            self._problem_return = self._screen
            self._problem = "Pobrać mimo niepewnej tożsamości?"
            self._suggestion = " · ".join(
                (choice.stream.release, f"E{view.offer.key.number}", _candidate_reason(choice, full=True))
            )
            self._screen = _Screen.PROBLEM
            return
        generation: int = self._generation
        self._choice_sending = True
        self._notice = _SENDING
        self._spawn(self._send_choice, (view, choice, generation, uuid4().hex))

    def _send_choice(self, view: EpisodeOfferView, choice: RankedCandidate, generation: int, command_id: str) -> None:
        if self._resident is None:
            return
        try:
            self._resident.episode_choose(
                view,
                choice.stream,
                command_id=command_id,
                deviation_confirmed=choice.identity.verdict is not IdentityVerdict.MATCH,
                conflict_confirmed=bool(view.conflict),
            )
        except (AniShiftError, OSError) as problem:
            with self._lock:
                if generation == self._generation:
                    self._choice_sending = False
                    self._offer_id = None
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        self._finish_episode_choice(generation, f"Zlecono E{view.offer.key.number}")

    def _start_files(self, admission_id: str) -> None:
        self._offer_view = None
        self._files = None
        self._offers.clear()
        self._offer_numbers = ()
        self._positions[_Screen.OFFER] = 0
        self._offsets[_Screen.OFFER] = 0
        generation: int = self._start_work("Wczytuję pliki…", _Screen.EPISODES)
        self._spawn(self._load_files, (admission_id, generation))

    def _load_files(self, admission_id: str, generation: int, notice: str = "") -> None:
        if self._resident is None:
            return
        try:
            files: EpisodeFiles = self._resident.episode_files(admission_id)
        except (AniShiftError, OSError) as problem:
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        with self._lock:
            if generation != self._generation:
                return
            self._files = files
            self._notice = notice
            self._positions[_Screen.OFFER] = 0
            self._screen = _Screen.OFFER
            self._worker = None
        self._invalidate()

    def _choose_file(self) -> None:
        files: EpisodeFiles | None = self._files
        if files is None or not files.files:
            return
        selected: EpisodeFile = files.files[self._positions.get(_Screen.OFFER, 0)]
        generation: int = self._start_work(_SENDING, _Screen.EPISODES, sending=True)
        self._spawn(self._send_file, (files, selected, generation, uuid4().hex))

    def _send_file(self, files: EpisodeFiles, selected: EpisodeFile, generation: int, command_id: str) -> None:
        if self._resident is None:
            return
        try:
            self._resident.episode_file_choose(files, selected, command_id=command_id)
        except (AniShiftError, OSError) as problem:
            if isinstance(problem, ControlError) and problem.reason == "file_map_changed":
                self._load_files(files.admission_id, generation, "Lista plików zmieniła się · wybierz ponownie")
                return
            self._catalog_failure(generation, problem, _Screen.EPISODES, "")
            return
        self._finish_episode_choice(generation, "Wybrano plik")

    def _finish_episode_choice(self, generation: int, notice: str) -> None:
        with self._lock:
            listing: EpisodeListing | None = self._listing
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(listing) if listing is not None else {}
        with self._lock:
            if generation != self._generation:
                return
            self._episode_states.update(states)
            self._notice = notice
            self._notice_kind = NoticeKind.SUCCESS
            self._offer_view = None
            self._offer_id = None
            self._choice_sending = False
            self._offers_running = False
            self._files = None
            self._screen = _Screen.EPISODES
            self._worker = None
        self._invalidate()

    def polish_refused(self, notice: str) -> None:
        """Name why the owner refused to stop a Polish wait and reread the episode states that offered it."""
        with self._lock:
            self._notice = notice
        self.refresh_episode_states()

    def refresh_episode_states(self) -> None:
        """Refresh at most one owner page around the visible episode window."""
        with self._lock:
            listing: EpisodeListing | None = self._listing
            if listing is None or self._screen is not _Screen.EPISODES:
                return
            anchor: int = (
                self._positions.get(_Screen.EPISODES, 0)
                if self._follow_cursor
                else self._offsets.get(_Screen.EPISODES, 0)
            )
            start: int = max(anchor - _MAX_BATCH // 2, 0)
            visible: EpisodeListing = replace(listing, episodes=listing.episodes[start : start + _MAX_BATCH])
        states: dict[EpisodeKey, EpisodeStatus] = self._read_episode_states(visible)
        with self._lock:
            if listing is self._listing:
                self._episode_states.update(states)
                self._episode_marks.difference_update(item.key.number for item in states.values() if item.active)

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
        if isinstance(problem, ControlError) and problem.code is ControlErrorCode.REFUSED:
            logger.info("Anime catalogue command refused", reason=problem.reason)
        else:
            logger.warning("Anime catalogue command failed", error_class=type(problem).__name__)
        if isinstance(problem, (AniShiftError, OSError)):
            self._report(generation, problem, back, provider=provider, catalog_command=True)
            return
        self._fail(generation, _COMMAND_FAILED, "", back)

    def _open_candidates(self) -> None:
        offer: EpisodeOffer | None = self._highlighted_offer()
        if offer is None:
            return
        self._release_candidates = visible(offer.candidates)
        self._positions[_Screen.CANDIDATES] = 0
        self._offsets[_Screen.CANDIDATES] = 0
        self._release_moved = False
        self._follow_cursor = True
        self._screen = _Screen.CANDIDATES

    def _highlighted_offer(self) -> EpisodeOffer | None:
        if not self._offer_numbers:
            return None
        return self._offers.get(self._offer_numbers[self._positions.get(_Screen.OFFER, 0)])

    def _start_search(self, text: str) -> None:
        self._subscription = None
        self._candidates = ()
        self._titles_shown = False
        self._entries_skipped = False
        self._franchise = None
        self._entry = None
        self._listing = None
        self._offers.clear()
        self._episode_marks.clear()
        query: SearchQuery = parse_query(text)
        generation: int = self._start_work(_SEARCHING_TITLE, _Screen.QUERY)
        self._spawn(self._find_titles, (query.title, generation, self._work_cancel))

    def _start_work(self, sentence: str, back: _Screen, *, sending: bool = False) -> int:
        self._input_focused = False
        self._generation += 1
        self._problem_provider = ""
        self._offers_running = False
        self._busy_return = back
        self._screen = _Screen.BUSY
        self._busy = sentence
        self._work_sending = sending
        self._work_cancel = EventCancellationToken()
        return self._generation

    def _spawn(self, target: Callable[..., None], arguments: tuple[object, ...]) -> None:
        worker = threading.Thread(target=target, args=arguments, name=_WORKER_NAME, daemon=True)
        self._worker = worker
        worker.start()

    def _find_titles(self, title: str, generation: int, cancel: EventCancellationToken) -> None:
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
            self._fail(generation, "Nie znaleziono tytułu", "", _Screen.QUERY)
            return
        self._open_first_title(acquisition, candidates, generation, cancel)

    def _open_first_title(
        self,
        acquisition: AcquisitionService | ResidentSession,
        candidates: tuple[TitleCandidate, ...],
        generation: int,
        cancel: EventCancellationToken,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._busy = _LOADING_ENTRIES
        self._invalidate()
        try:
            franchise: Franchise = acquisition.franchise(candidates[0].anilist_id, cancel=cancel)
        except Exception as problem:  # noqa: BLE001 - the UI worker reports a failed command without a partial view
            with self._lock:
                if generation != self._generation:
                    return
                self._store_titles(candidates, None)
            self._catalog_failure(generation, problem, _Screen.TITLES, "anilist")
            return
        self._show_titles(generation, candidates, franchise)

    def _show_titles(self, generation: int, candidates: tuple[TitleCandidate, ...], franchise: Franchise) -> None:
        entry: FranchiseEntry | None = None
        with self._lock:
            if generation != self._generation:
                return
            self._store_titles(candidates, franchise)
            if self._titles_shown:
                self._screen = _Screen.TITLES
            else:
                self._highlighted = self._candidates.index(candidates[0])
                self._screen = _Screen.ENTRIES
            if (
                not self._titles_shown
                and len(franchise.entries) == 1
                and franchise.complete
                and franchise.entries[0].status != "NOT_YET_RELEASED"
            ):
                entry = franchise.entries[0]
            if entry is not None:
                self._entries_skipped = True
                self._entry = entry
                self._shown_entry = entry
                self._positions[_Screen.EPISODES] = 0
                self._offsets[_Screen.EPISODES] = 0
                self._screen = _Screen.BUSY
                self._busy = "Wczytuję odcinki…"
                self._busy_return = _Screen.QUERY
            else:
                self._worker = None
        self._invalidate()
        if entry is not None:
            self._load_episodes(entry, generation)

    def _store_titles(self, candidates: tuple[TitleCandidate, ...], franchise: Franchise | None) -> None:
        self._candidates = tuple(
            sorted(
                natsorted(candidates, key=lambda item: (item.english or item.romaji).casefold()),
                key=lambda item: premiere_order(item.year, item.start),
                reverse=True,
            )
        )
        self._highlighted = 0
        self._franchise = None
        if franchise is not None:
            self._adopt_franchise(franchise)
        members: set[int] = {entry.anilist_id for entry in franchise.entries} if franchise is not None else set()
        self._titles_shown = any(item.anilist_id not in members for item in candidates)

    def _report(
        self,
        generation: int,
        problem: AniShiftError | OSError | ValueError,
        back: _Screen,
        *,
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
        self._fail(generation, sentence, hint, back, provider=provider, deadline=deadline)

    def _fail(  # noqa: PLR0913
        self,
        generation: int,
        sentence: str,
        suggestion: str,
        back: _Screen,
        *,
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
            self._screen = _Screen.PROBLEM
        self._invalidate()

    def _retry_hint(self, provider: str, fallback: float = 0.0) -> str:
        deadline: float = self._provider_locks.get(provider, fallback)
        if not deadline:
            return ""
        remaining: int = max(ceil(deadline - self._clock()), 0)
        return f"spróbuj za {remaining} s" if remaining else "Możesz spróbować ponownie"

    def _entry_heading(self) -> str:
        entry: FranchiseEntry | None = self._shown_entry
        return (
            "ANIME" if entry is None else f"ANIME \u203a {_safe(entry.english or entry.romaji)} ({entry.year or '—'})"
        )

    def _repeat_warning(self) -> tuple[str, ...]:
        view: EpisodeOfferView | None = self._offer_view
        if view is None or (not view.conflict and view.previous_admission_id is None):
            return ()
        warning: str = (
            f"E{view.offer.key.number} może być już zlecony · Obecne pliki zostają"
            if view.conflict
            else "Obecne pliki zostają"
        )
        return (warning, *(("Nie można potwierdzić odmienności wydania",) if view.unknown_previous else ()))


def _year_label(year: int | None) -> str:
    return str(year) if year else "—"


def _stated(problem: AniShiftError | OSError | ValueError) -> tuple[str, str]:  # noqa: PLR0911
    """Translate domain codes preserved locally or carried by a resident refusal."""
    from anishift.cli.interactive.state import refusal_text  # noqa: PLC0415

    if not isinstance(problem, AniShiftError):
        return refusal_text(problem), ""
    if isinstance(problem, ControlError) and problem.reason == "response_too_large":
        return "Odpowiedź rezydenta jest za duża", ""
    if isinstance(problem, ControlError) and problem.reason == "offer_expired":
        return "Oferta wygasła — otwórz ponownie", ""
    if isinstance(problem, ControlError) and problem.reason in _REPEATABLE_REFUSALS:
        return _REPEATABLE_REFUSALS[problem.reason], _REPEAT_HINT
    if isinstance(problem, ControlError) and problem.code is ControlErrorCode.STALE_PREVIEW:
        return "Wybór lub konflikt zmienił się", "Otwórz podgląd ponownie"
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
    return (refusal_text(problem), "") if isinstance(problem, ControlError) else ("Nie udało się wykonać operacji", "")


def _refused_result(reason: str) -> tuple[str, str]:
    """Return the Stan label and notice cause of one episode the owner did not admit."""
    known: str | None = EPISODE_REASON_LABELS.get(reason)
    if reason == EpisodeReason.EPISODE_IN_PROGRESS:
        return EPISODE_REASON_LABELS[reason], _IN_PROGRESS_HINT
    if reason in _REPEATABLE_REFUSALS:
        return EPISODE_REASON_LABELS[reason], f"{_REPEATABLE_REFUSALS[reason]} · {_REPEAT_HINT}"
    if known is not None:
        return known, known
    if reason == EpisodeReason.ACQUISITION_UNAVAILABLE:
        return "Niedostępne", _UNAVAILABLE
    refusal: ControlError = ControlError(reason, code=ControlErrorCode.REFUSED, reason=reason, answered=True)
    status: str = (
        EPISODE_REASON_LABELS[EpisodeReason.SOURCE_FAILED]
        if reason == ErrorCode.TORRENT_SOURCE_FAILED.value
        else "Nie zlecono"
    )
    return status, _stated(refusal)[0]


def _episode_status_label(status: EpisodeStatus) -> str:
    if status.polish_skipped:
        return "Bez czekania PL"
    if status.polish_wait_until is not None:
        return "Czeka na PL"
    if status.reason in EPISODE_REASON_LABELS:
        return EPISODE_REASON_LABELS[status.reason]
    if status.state == "not_ordered":
        return "" if status.reason is None else _refused_result(status.reason)[0]
    return _EPISODE_STATE_LABELS.get(status.state, "Zlecono")


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


def _format_label(value: str | None) -> str:
    return "Film" if value == "MOVIE" else value or "—"


def _language(item: RankedCandidate) -> str:
    return (
        " · ".join(
            label
            for label, present in (
                ("PL", item.traits.polish is not PolishClass.NONE),
                ("EN", item.traits.english_subtitles),
            )
            if present
        )
        or "—"
    )


def _candidate_reason(item: RankedCandidate, *, full: bool) -> str:
    return f"{_VERDICT_LABELS[item.identity.verdict]}: {_identity_reason(item, full=full)}"


def _identity_reason(item: RankedCandidate, *, full: bool) -> str:
    reason: str = _REASON_TEXTS.get(item.identity.reason, _identity_fallback(item.identity.verdict))
    if full:
        return reason
    short: str = reason.split(";", 1)[0].rstrip(".") + "."
    return short if len(short) <= _SHORT_REASON_LENGTH else _identity_fallback(item.identity.verdict)


def _identity_fallback(verdict: IdentityVerdict) -> str:
    return {
        IdentityVerdict.MATCH: "Nazwa wskazuje wybrany odcinek.",
        IdentityVerdict.INSUFFICIENT: "Nie można jednoznacznie ustalić tożsamości odcinka.",
        IdentityVerdict.MISMATCH: "Nazwa wskazuje inny materiał.",
    }[verdict]


def _candidate_details(item: RankedCandidate) -> str:
    details: list[str] = []
    if item.stream.path or item.stream.file_name:
        details.append(f"Plik: {_safe(item.stream.path or item.stream.file_name or '')}")
    if item.release_name_only:
        details.append("bez nazwy pliku")
    details.append(f"Rozmiar: {_safe(item.stream.size_text or '?')}")
    if item.traits.platform:
        details.append("wydanie z platformy")
    if item.supported is False:
        details.append("format nieobsługiwany")
    if item.ambiguous:
        details.append("niejednoznaczny plik")
    if item.traits.dub_only:
        details.append("sam dubbing")
    details.extend(_candidate_numbering(item.numbering))
    details.append(
        "Kalibracja pewności potwierdzona tylko dla korpusu E1. "
        "Dla nowych źródeł i ocen bez nazwy pliku: estymata bez potwierdzonej kalibracji."
    )
    return " · ".join(details)


def _candidate_confidence(item: RankedCandidate, *, suggested: bool) -> str:
    if item.conflict:
        return conflict_label(item.identity)
    value: str = confidence_text(item) or "?"
    return value + (" · niepewne" if suggested and item.identity.verdict is not IdentityVerdict.MATCH else "")


def _candidate_numbering(evidence: CandidateNumbering | None) -> list[str]:
    if evidence is None:
        return []
    mode: str = {"mapped": "S/E", "plain": "bez znacznika numeracji", "missing": "brak numeru"}[evidence.mode]
    return [
        f"Odczyt H1 ({mode}): sezon {evidence.season if evidence.season is not None else '?'}, "
        f"odcinek {evidence.number if evidence.number is not None else '?'}, "
        f"część {evidence.part if evidence.part is not None else '?'}",
        f"Cel: lokalny {evidence.local if evidence.local is not None else '?'}; "
        f"S/E: sezon {evidence.target_season if evidence.target_season is not None else '?'}, "
        f"odcinek {evidence.episode if evidence.episode is not None else '?'}; "
        f"absolutny {evidence.absolute if evidence.absolute is not None else '?'}; "
        f"sezon w tytule {evidence.named_season if evidence.named_season is not None else '?'}; "
        f"część {evidence.target_part if evidence.target_part is not None else '?'}",
    ]
