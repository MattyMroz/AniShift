"""Owner payload values and refusals as the resident panel's sanitized Polish text."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from anishift.application import RefusalReason
from anishift.application.events import sanitize_event_message
from anishift.platform.local_control import ControlError, ControlErrorCode

__all__ = ["LIBRARY_PROBLEMS", "refusal_text", "rows", "safe_text"]

# ── Constants ─────────────────────────────────────────────────────────────────

_RETRY_PROBLEMS: Final[dict[str, str]] = {
    "retry_source_missing": "Brak lokalnego źródła; usuniętej treści nie można odtworzyć",
    "retry_reference_missing": "Brak zachowanej referencji wydania; wybierz wydanie ponownie w Anime",
    "retry_choose_one": (
        "Zakres zawiera lokalne materiały; wybierz jeden numer, aby zobaczyć właściwe dokończenie lub poprawkę"
    ),
    "retry_source_available": "Źródło jest już lokalnie; ponownie wybierz Ponów, aby przygotować Ręczny",
    "retry_acquisition_pending": "Wcześniejsze przekazanie nadal wymaga uzgodnienia; nie dodano drugiego pobrania",
    "legacy_subscription_retry": "Pobierz ten odcinek ponownie z Anime (P)",
}
"""Actionable retry refusals without claiming missing source bytes can be recovered."""

_CLIENT_PROBLEMS: Final[dict[str, str]] = {
    "The private torrent window was closed; downloads remain stopped until explicitly resumed": (
        "qBittorrent wyłączony · zlecenia czekają na wznowienie"
    ),
    "The private torrent client was taken over; automatic control is disabled": ("qBittorrent sterowany ręcznie"),
    "The private torrent client was opened manually; automatic control stopped": (
        "Otwarto qBittorrenta · sterowanie automatyczne wstrzymane"
    ),
    "The private torrent client could not start; resolve the problem and explicitly resume": (
        "Nie udało się uruchomić qBittorrenta · usuń przyczynę i wybierz Wznów"
    ),
}
"""Polish explanations of private client states surfaced by the transport boundary."""

_REFUSAL_TEXTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        RefusalReason.GROUP_RESERVED.value: "Inny panel zajął ten odcinek",
        RefusalReason.GROUP_PROCESSING.value: "Ten odcinek jest już przetwarzany",
        RefusalReason.GROUP_RELOCATING.value: "Gotowy odcinek jest przenoszony do biblioteki",
        RefusalReason.SESSION_CLOSED.value: "Połączenie z procesem w tle wygasło",
        RefusalReason.CLIENT_BOUND.value: "Ten panel jest już połączony w innej sesji",
        RefusalReason.NOT_RESERVED.value: "Najpierw zajmij odcinek, potem dodaj do niego plik",
        RefusalReason.FOREIGN_PREVIEW.value: "Ten wybór należy do innego panelu",
        RefusalReason.NOT_RESUMABLE.value: "Tej pracy nie da się wznowić",
        RefusalReason.PAUSED.value: "AniShift jest wstrzymany · wybierz Wznów, aby podjąć pracę",
        RefusalReason.SHUTTING_DOWN.value: "AniShift się kończy · nie przyjmuje już nowej pracy",
        RefusalReason.TRANSFER_METADATA_PENDING.value: (
            "Trwa przygotowanie pobrania · poczekaj na potwierdzenie wyboru plików"
        ),
    }
)
"""Polish sentence the panel shows for every refusal cause the resident names."""

_UNKNOWN_REFUSAL: Final[str] = "Proces w tle odrzucił polecenie"
"""Polish sentence for a refusal this version cannot name any more precisely."""

_CONTROL_PROBLEMS: Final[Mapping[ControlErrorCode, str]] = MappingProxyType(
    {
        ControlErrorCode.STALE_INSTANCE: "Proces w tle został uruchomiony ponownie · otwórz panel ponownie",
        ControlErrorCode.UNKNOWN_COMMAND: "Proces w tle nie obsługuje tego polecenia",
        ControlErrorCode.INVALID_PAYLOAD: "Proces w tle odrzucił niepoprawne dane polecenia",
        ControlErrorCode.STALE_PREVIEW: "Podgląd jest nieaktualny · przygotuj go ponownie",
        ControlErrorCode.CONFLICT: "Polecenie koliduje z bieżącą pracą",
        ControlErrorCode.ALREADY_PROCESSING: "Ten odcinek jest już przetwarzany",
        ControlErrorCode.REFUSED: _UNKNOWN_REFUSAL,
        ControlErrorCode.INTERNAL: "Wewnętrzny błąd procesu w tle · sprawdź log",
    }
)
"""Polish fallback for each public control code when no more precise reason is known."""

_SUBSCRIPTION_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "subscription_missing": "Tej subskrypcji już nie ma",
        "nothing_to_restore": "Brak usuniętej subskrypcji do przywrócenia",
        "subscription_exists": "Ten sezon jest już subskrybowany",
        "subscription_limit": "Osiągnięto limit subskrypcji; usuń jedną, aby dodać lub przywrócić",
        "subscription_not_airing": "Ten wpis nie ma przyszłych odcinków",
        "subscription_cut_unknown": "Nie wiadomo, ile odcinków już wyemitowano · spróbuj później",
        "source_failed": "Nie udało się odczytać katalogu · spróbuj ponownie",
        "target_not_waiting": "Ten odcinek już nie czeka na polskie napisy",
    }
)
"""Polish subscription refusals selected by machine reason rather than application prose."""

LIBRARY_PROBLEMS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "library_set_missing": "Tego zestawu nie ma już w bibliotece",
        "library_result_missing": "Brakuje potwierdzonego głównego wyniku",
        "library_result_changed": "Główny wynik istnieje, ale jest zmieniony lub niepotwierdzony",
        "library_ownership_unknown": "Pochodzenie zestawu wymaga rozstrzygnięcia przed usunięciem",
        "library_source_held": "Źródło czeka na zwolnienie przez torrent",
        "library_source_missing": "Brakuje źródłowego pliku wideo tego zestawu",
        "library_scope_changed": "Zestaw zmienił się · przygotuj nowe potwierdzenie",
        "library_source_busy": "Plik jest nadal zapisywany lub niedostępny",
        "library_deleting": "Zestaw jest chroniony przez operację Kosza lub przywracania",
        "recycle_unsupported": "Kosz jest niedostępny dla tego środowiska",
        "recycle_unavailable": "Nie udało się potwierdzić dostępności operacji Kosza",
        "recycle_refused": "System odmówił przeniesienia pliku do Kosza",
        "recycle_timeout": "Upłynął limit operacji · jej wynik pozostaje niepewny",
        "recycle_cleanup_timeout": "Upłynął limit zamykania operacji · jej wynik pozostaje niepewny",
        "recycle_interrupted": "Operacja została przerwana · jej wynik pozostaje niepewny",
        "recycle_invalid_evidence": "Brak poprawnego potwierdzenia operacji Kosza",
        "recycle_incomplete": "System nie potwierdził pełnego wyniku operacji",
        "library_release_unavailable": "Nie można odczytać potwierdzenia zwolnienia torrenta",
        "restore_nothing": "Brak usuniętego zestawu do przywrócenia",
        "restore_already_completed": "Ostatnie usunięcie zostało już cofnięte",
        "restore_destination_occupied": "Miejsce przywracania jest zajęte · istniejący plik pozostawiono bez zmian",
        "restore_receipt_missing": "Brak dokładnego elementu w Koszu · mógł zostać opróżniony",
        "restore_unsupported_destination": "Przywracanie wymaga dostępnego miejsca na tym samym woluminie NTFS",
        "restore_unsafe_path": "Ścieżka przywracania jest niedostępna lub prowadzi przez dowiązanie",
        "restore_scope_changed": "Pliki przywracania zmieniły się · nie wykonano kolejnej operacji",
        "restore_interrupted": "Przywracanie przerwane · Ctrl+Z sprawdzi zapisany stan przed ponowieniem",
        "restore_incomplete": "System nie potwierdził pełnego przywrócenia",
        "restore_inflight": "Przywracanie wymaga rozliczenia zapisanej operacji",
    }
)
"""Polish explanations keyed by the owner's library reason codes."""


def refusal_text(problem: BaseException) -> str:
    """Translate ControlError reasons and codes, otherwise return sanitized exception text."""
    reason: str = problem.reason if isinstance(problem, ControlError) else ""
    if reason in _RETRY_PROBLEMS:
        return _RETRY_PROBLEMS[reason]
    if reason in _SUBSCRIPTION_PROBLEMS:
        return _SUBSCRIPTION_PROBLEMS[reason]
    fallback: str = safe_text(str(problem))
    if isinstance(problem, ControlError):
        fallback = (
            _CONTROL_PROBLEMS[problem.code]
            if problem.answered
            else (
                "Brak potwierdzonej odpowiedzi procesu w tle · sprawdź, czy proces działa, "
                "oraz Historię i log przed ponowieniem"
            )
        )
    return _REFUSAL_TEXTS.get(reason) or LIBRARY_PROBLEMS.get(reason) or fallback or _UNKNOWN_REFUSAL


def safe_text(value: object) -> str:
    """Return owner text sanitized for the terminal, with private client states in Polish."""
    message: str = sanitize_event_message(str(value)) or ""
    return _CLIENT_PROBLEMS.get(message, message)


def rows(value: object) -> list[Mapping[str, object]]:
    """Return the mappings of an owner payload list, or none when the value is not a list."""
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
