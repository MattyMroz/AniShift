"""Polish labels and problem statements of the Anime tab, computed without I/O."""

from __future__ import annotations

from typing import Final

from anishift.application import AdmissionConflict, EpisodeReason
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.state_texts import STATES, state_word
from anishift.errors import AniShiftError, ErrorCode
from anishift.platform.local_control import ControlError, ControlErrorCode

__all__ = [
    "COMMAND_FAILED",
    "IN_PROGRESS_HINT",
    "REPEATABLE_REASONS",
    "RETRY_HINT",
    "UNAVAILABLE",
    "episode_state",
    "error_code",
    "refused_result",
    "safe",
    "stated",
]

# ── Constants ─────────────────────────────────────────────────────────────────

IN_PROGRESS_HINT: Final[str] = "W toku · Del usuń w Przetwarzaniu"
"""Notice naming where an active episode can be cancelled instead of ordered again."""

RETRY_HINT: Final[str] = "Błąd przetwarzania · P ponów"
"""Notice naming the retry of an episode whose processing failed while its source stays on disk."""

_EPISODE_ADMITTED: Final[str] = "Odcinek już zlecony"
"""Notice shown when the owner refuses an already admitted episode."""

_REPEAT_HINT: Final[str] = "P pobierz ponownie"
"""Hint naming the explicit repeat after the owner refuses an already ordered episode."""

_REPEATABLE_REFUSALS: Final[dict[str, str]] = {
    AdmissionConflict.ADMITTED: _EPISODE_ADMITTED,
    AdmissionConflict.POSSIBLY_ADMITTED: state_word(AdmissionConflict.POSSIBLY_ADMITTED),
    EpisodeReason.PACK_IN_PROGRESS: state_word(EpisodeReason.PACK_IN_PROGRESS),
}
"""Notice of each owner refusal that P can override with an explicit repeat."""

REPEATABLE_REASONS: Final[frozenset[str]] = frozenset(_REPEATABLE_REFUSALS)
"""Owner refusal reasons an explicit repeat (P) overrides."""

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

COMMAND_FAILED: Final[str] = "AniShift w tle nie wykonał polecenia · uruchom AniShift ponownie"
"""Safe explanation shared by failed catalogue commands and local worker defects."""


def stated(problem: AniShiftError | OSError | ValueError) -> tuple[str, str]:  # noqa: PLR0911
    """Translate domain codes preserved locally or carried by a resident refusal."""
    from anishift.cli.interactive.state import refusal_text  # noqa: PLC0415

    if not isinstance(problem, AniShiftError):
        return refusal_text(problem), ""
    if isinstance(problem, ControlError) and problem.reason == "response_too_large":
        return "Odpowiedź AniShift w tle jest za duża", ""
    if isinstance(problem, ControlError) and problem.reason == "offer_expired":
        return "Oferta wygasła — otwórz ponownie", ""
    if isinstance(problem, ControlError) and problem.reason in _REPEATABLE_REFUSALS:
        return _REPEATABLE_REFUSALS[problem.reason], _REPEAT_HINT
    if isinstance(problem, ControlError) and problem.code is ControlErrorCode.STALE_PREVIEW:
        return "Wybór lub konflikt zmienił się", "Otwórz podgląd ponownie"
    if isinstance(problem, ControlError) and problem.reason == "download_recorded":
        counts: dict[str, int] | None = _download_counts(problem)
        if counts is None:
            return "Nie można potwierdzić wyniku zamówienia", "Sprawdź qBittorrenta AniShift i log"
        return (
            f"Przyjęto: {counts['sent']} · już przyjęte: {counts['accepted']}"
            f" · wynik przekazania niepotwierdzony: {counts['uncertain']}",
            "Sprawdź qBittorrenta AniShift i log",
        )
    code: ErrorCode | None = error_code(problem)
    texts: tuple[str, str] | None = _PROBLEM_TEXTS.get(code) if code is not None else None
    if texts is not None:
        if isinstance(problem, ControlError) and code in {
            ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
            ErrorCode.TORRENT_CLIENT_UNAUTHORIZED,
            ErrorCode.TORRENT_CLIENT_REFUSED,
        }:
            return texts[0], "Sprawdź qBittorrenta AniShift i log"
        return texts
    return (refusal_text(problem), "") if isinstance(problem, ControlError) else ("Nie udało się wykonać operacji", "")


def refused_result(reason: str) -> tuple[str, str]:
    """Return the Stan label and notice cause of one episode the owner did not admit."""
    if reason == EpisodeReason.EPISODE_IN_PROGRESS:
        return state_word(reason), IN_PROGRESS_HINT
    if reason in _REPEATABLE_REFUSALS:
        return state_word(reason), f"{_REPEATABLE_REFUSALS[reason]} · {_REPEAT_HINT}"
    if reason in STATES:
        return state_word(reason), state_word(reason)
    if reason == EpisodeReason.ACQUISITION_UNAVAILABLE:
        return "Niedostępne", UNAVAILABLE
    refusal: ControlError = ControlError(reason, code=ControlErrorCode.REFUSED, reason=reason, answered=True)
    status: str = (
        state_word(EpisodeReason.SOURCE_FAILED) if reason == ErrorCode.TORRENT_SOURCE_FAILED.value else "Nie zlecono"
    )
    return status, stated(refusal)[0]


def episode_state(state: str, reason: str | None) -> str:
    """Return the Stan word of one owner episode state and reason, empty for a plain not ordered one."""
    if reason is not None and reason in STATES:
        return state_word(reason)
    if state == "not_ordered":
        return "" if reason is None else refused_result(reason)[0]
    return state_word(state if state in STATES else "ordered")


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
