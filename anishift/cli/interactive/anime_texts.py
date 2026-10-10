"""Polish labels and problem statements of the Anime tab, computed without I/O."""

from __future__ import annotations

from typing import Final

from anishift.application import AdmissionConflict, EpisodeReason, EpisodeStatus
from anishift.application.events import sanitize_event_message
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError, ControlErrorCode

__all__ = [
    "COMMAND_FAILED",
    "EPISODE_REASON_LABELS",
    "IN_PROGRESS_HINT",
    "UNAVAILABLE",
    "episode_status_label",
    "error_code",
    "refused_result",
    "safe",
    "stated",
]

# ── Constants ─────────────────────────────────────────────────────────────────

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

IN_PROGRESS_HINT: Final[str] = "W toku · X anuluj w Przetwarzaniu"
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

UNAVAILABLE: Final[str] = "Pobieranie jest niedostępne w tej sesji"
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

COMMAND_FAILED: Final[str] = (
    "Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie."
)
"""Safe explanation shared by failed catalogue commands and local worker defects."""


def stated(problem: AniShiftError | OSError | ValueError) -> tuple[str, str]:  # noqa: PLR0911
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
    code: ErrorCode | None = error_code(problem)
    texts: tuple[str, str] | None = _PROBLEM_TEXTS.get(code) if code is not None else None
    if texts is not None:
        if isinstance(problem, ControlError) and code in {
            ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            ErrorCode.TORRENT_CLIENT_UNAUTHORIZED,
            ErrorCode.TORRENT_CLIENT_REFUSED,
        }:
            return texts[0], "Sprawdź prywatny klient AniShift i log"
        return texts
    return (refusal_text(problem), "") if isinstance(problem, ControlError) else ("Nie udało się wykonać operacji", "")


def refused_result(reason: str) -> tuple[str, str]:
    """Return the Stan label and notice cause of one episode the owner did not admit."""
    known: str | None = EPISODE_REASON_LABELS.get(reason)
    if reason == EpisodeReason.EPISODE_IN_PROGRESS:
        return EPISODE_REASON_LABELS[reason], IN_PROGRESS_HINT
    if reason in _REPEATABLE_REFUSALS:
        return EPISODE_REASON_LABELS[reason], f"{_REPEATABLE_REFUSALS[reason]} · {_REPEAT_HINT}"
    if known is not None:
        return known, known
    if reason == EpisodeReason.ACQUISITION_UNAVAILABLE:
        return "Niedostępne", UNAVAILABLE
    refusal: ControlError = ControlError(reason, code=ControlErrorCode.REFUSED, reason=reason, answered=True)
    status: str = (
        EPISODE_REASON_LABELS[EpisodeReason.SOURCE_FAILED]
        if reason == ErrorCode.TORRENT_SOURCE_FAILED.value
        else "Nie zlecono"
    )
    return status, stated(refusal)[0]


def episode_status_label(status: EpisodeStatus) -> str:
    """Return the Stan column label of one owner episode state, empty for a plain not ordered one."""
    if status.polish_skipped:
        return "Bez czekania PL"
    if status.polish_wait_until is not None:
        return "Czeka na PL"
    if status.reason in EPISODE_REASON_LABELS:
        return EPISODE_REASON_LABELS[status.reason]
    if status.state == "not_ordered":
        return "" if status.reason is None else refused_result(status.reason)[0]
    return _EPISODE_STATE_LABELS.get(status.state, "Zlecono")


def _download_counts(problem: ControlError) -> dict[str, int] | None:
    keys: tuple[str, ...] = ("sent", "accepted", "uncertain")
    counts: dict[str, int] = {
        key: value for key in keys if type(value := problem.context.details.get(key)) is int and value >= 0
    }
    return counts if len(counts) == len(keys) else None


def error_code(problem: AniShiftError | OSError | ValueError) -> ErrorCode | None:
    """Return the domain code a failure carries locally or in a resident refusal."""
    if isinstance(problem, ControlError):
        try:
            return ErrorCode(problem.reason)
        except ValueError:
            return None
    return problem.context.code if isinstance(problem, AniShiftError) else None


def safe(value: str) -> str:
    """Sanitize one catalogue text for display without its trailing period."""
    return (sanitize_event_message(value) or "").rstrip(".")
