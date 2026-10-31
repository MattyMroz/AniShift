"""Rows, progress labels, actions and History texts of the panel's Processing tab."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Final

from anishift.application import EpisodeReason, HistoryEvent, RetryProposal
from anishift.cli.interactive.actions import PANEL_ACTIONS, Action, ScreenActions
from anishift.cli.interactive.anime import EPISODE_REASON_LABELS
from anishift.cli.interactive.progress import RichRunProgress
from anishift.cli.interactive.state_texts import RESTORING, deleting_sets, rows, safe_text
from anishift.text.plural import plural

__all__ = [
    "HISTORY_PROBLEMS",
    "HISTORY_SPAN",
    "HISTORY_UNAVAILABLE",
    "NO_HISTORY",
    "NO_PROCESSING",
    "cancel_command",
    "cancel_target",
    "deletable_set",
    "download_progress",
    "failed_group",
    "held",
    "history_actions",
    "history_entry",
    "material_name",
    "pause_toggle",
    "processing_actions",
    "processing_rows",
    "question_text",
    "retry_entry",
    "row_ids",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_DOWNLOAD_PROBLEMS: Final[dict[str, str]] = {
    "The automation state could not be saved, so nothing changed": "Błąd zapisu stanu",
    "The download destination could not be read, so no name was reserved": "Folder nieczytelny",
    "Something took a name reserved for this download; clear that name and retry": "Nazwa pliku zajęta",
    "No file list was received for this download; resume it to keep waiting": "Brak listy plików",
    "This download no longer matches its saved file selection or folder": "Pliki się zmieniły",
    "The client does not show this download; resume it to check again": "qBittorrent go nie widzi",
    "This download was stopped before its file list arrived and cannot resume safely": "Zatrzymane za wcześnie",
}
"""Short Polish cause of each download problem the owner reports, by its owner sentence."""

_READINESS_LABELS: Final[dict[str, str]] = {
    "subtitle_source_missing": "Brak napisów",
    "sidecar_missing": "Brak napisów obok",
    "ambiguous_sidecar": "Kilka plików napisów",
    "video_missing": "Brak wideo",
    "content_source_missing": "Brak źródła",
    "ambiguous_content_source": "Kilka źródeł",
    "source_incomplete": "Plik niekompletny",
    "source_path_collision": "Konflikt nazw",
    "unsupported_source": "Nieobsługiwany plik",
    "image_missing": "Brak okładki",
    "ambiguous_image": "Kilka okładek",
    "place_starts_no_work": "Folder bez Auto",
    "processing_failed": "Błąd",
}
"""Short Polish cause of a workspace material that waits for the user, not for a queue."""

_HISTORY_LABELS: Final[dict[str, str]] = {
    "order_admitted": "przyjęto zamówienie",
    "download_confirmed": "pobrano źródło",
    "regeneration": "przyjęto regenerację",
    "processing_success": "ukończono",
    "processing_error": "błąd",
    "processing_interrupted": "przerwano",
    "delete_outcome": "usuwanie",
    "subscription_finished": "subskrypcja zakończona",
}
"""Operation boundary labels shown once per logical material."""

HISTORY_PROBLEMS: Final[dict[str, str]] = {
    "history_corrupt": "Historia niedostępna · uszkodzony zapis; przetwarzanie działa dalej",
    "history_unavailable": "Historia niedostępna · błąd odczytu lub zapisu; przetwarzanie działa dalej",
}
"""Persistent observation warnings distinct from an empty history."""

HISTORY_SPAN: Final[str] = "Historia z ostatnich 30 dni"
"""Help line naming how far back the default history reaches."""


NO_PROCESSING: Final[str] = "Brak aktywnego przetwarzania"
"""Only line of an empty Processing list."""

NO_HISTORY: Final[str] = "Brak pozycji"
"""Only line of an empty History list."""

HISTORY_UNAVAILABLE: Final[str] = "Historia niedostępna"
"""Only line of a History list the owner could not read."""

_RETRY_LABELS: Final[dict[str, str]] = {
    "manual": "Popraw wybrany lokalny materiał w Ręcznym · wybór zakresu przebudowy",
    "reacquire": "Pobierz ponownie zachowane wydanie · nowe jawne zamówienie",
}
"""Only row of a local or remote retry proposal, by the owner's retry route."""

_TRANSFER_LABELS: Final[dict[str, str]] = {
    "queuedDL": "W kolejce",
    "uploading": "Pobrane",
    "stalledUP": "Pobrane",
    "forcedUP": "Pobrane",
    "queuedUP": "Pobrane",
    "moving": "Przenoszenie",
}
"""Labels of the remaining torrent client states of a recorded download."""


def processing_rows(
    payload: Mapping[str, object],
    runs: Mapping[str, tuple[str, RichRunProgress]],
    hidden: Collection[str] = (),
    restoring: Collection[Mapping[str, object]] = (),
) -> list[Mapping[str, object]]:
    """Return downloads, admitted, started, restoring and to-check work, minus rows being deleted."""
    running: set[str] = {
        str(item["request_id"])
        for item in rows(payload.get("requests"))
        if item.get("state") in {"accepted", "running"}
    }
    processing: list[Mapping[str, object]] = [
        item
        for item in rows(payload.get("materials"))
        if item.get("stage") == "processing"
        and item.get("state") in {"accepted", "running"}
        and str(item.get("run_id")) in running
        and (progress := runs.get(str(item.get("run_id")))) is not None
        and progress[1].group_active(str(item.get("group_id")))
    ]
    downloads: list[Mapping[str, object]] = [
        item
        for item in rows(payload.get("materials"))
        if item.get("acquisition_state") in {"pending_send", "accepted", "complete"}
        and (
            item.get("stage") == "download"
            or (
                item.get("stage") == "waiting"
                and item.get("reason") in {"preparing", EpisodeReason.FINALIZATION_FAILED}
            )
        )
    ]
    preparing: list[Mapping[str, object]] = [
        {**item, "stage": "waiting", "reason": "preparing", "admitted_processing": True}
        for item in rows(payload.get("materials"))
        if item.get("stage") == "processing"
        and item.get("state") in {"accepted", "running"}
        and str(item.get("run_id")) in running
        and (
            (progress := runs.get(str(item.get("run_id")))) is None
            or progress[1].group_pending(str(item.get("group_id")))
        )
    ]
    attention: list[Mapping[str, object]] = [item for item in rows(payload.get("materials")) if item.get("attention")]
    deleting: set[str] = deleting_sets(payload, hidden)
    listed: list[Mapping[str, object]] = [
        item for item in [*downloads, *preparing, *processing, *attention] if item.get("set_id") not in deleting
    ]
    present: set[object] = {item.get("set_id") for item in listed}
    return [*listed, *(item for item in restoring if item.get("set_id") not in present)]


def row_ids(materials: list[Mapping[str, object]]) -> list[str]:
    """Return the identity each processing row keeps across snapshots."""
    return [
        str(item["acquisition_id"])
        if item.get("acquisition_id")
        and sum(other.get("acquisition_id") == item["acquisition_id"] for other in materials) == 1
        else str(item.get("material_id") or f"{item.get('run_id')}:{item.get('group_id')}")
        for item in materials
    ]


def held(snapshot: Mapping[str, object], item: Mapping[str, object]) -> bool:
    """Answer whether the global pause holds this automatic row."""
    return bool(snapshot.get("paused")) and item.get("automatic") is not False


def material_name(item: Mapping[str, object]) -> str:
    """Return the row's source name, or ``Materiał`` for an absent or ID-only label."""
    name: str = safe_text(item.get("name", ""))
    if not name or name in {item.get("info_hash"), item.get("material_id"), item.get("group_id")}:
        return "Materiał"
    return name


def download_progress(  # noqa: PLR0911
    item: Mapping[str, object], snapshot: Mapping[str, object], *, connected: bool
) -> tuple[str, float | None]:
    """Return the label and measured fraction of a download row."""
    fraction: object = item.get("progress")
    measured: float | None = float(fraction) if isinstance(fraction, (int, float)) else None
    if item.get("restoring"):
        return RESTORING, None
    if item.get("reason") == EpisodeReason.FINALIZATION_FAILED:
        return "Błąd zapisu", None
    if item.get("attention"):
        return _READINESS_LABELS.get(str(item.get("reason")), "Do sprawdzenia"), None
    if item.get("stage") == "waiting":
        return ("Wstrzymano" if held(snapshot, item) else "Przygotowanie"), None
    if item.get("problem"):
        return _DOWNLOAD_PROBLEMS.get(str(item.get("problem")), "Wymaga uwagi"), None
    if item.get("reason") == EpisodeReason.WAITING_PREVIOUS_TRANSFER:
        return EPISODE_REASON_LABELS[EpisodeReason.WAITING_PREVIOUS_TRANSFER], None
    if not connected or snapshot.get("transfers_problem"):
        return "Brak odczytu", None
    state: object = item.get("state")
    if _download_toggle(item) == ("resume", "wznów"):
        return "Wstrzymano", measured
    if state in {"metaDL", "forcedMetaDL"} or item.get("acquisition_state") == "pending_send":
        return "Łączę", measured
    if state is None:
        return "Brak transferu", None
    if state in {"error", "missingFiles"}:
        return "Błąd transferu", None
    if state in {"downloading", "forcedDL", "stalledDL"}:
        label: str = "Brak odczytu" if measured is None else ("Brak źródeł" if state == "stalledDL" else "Pobieranie")
        return label, measured
    return _TRANSFER_LABELS.get(str(state), "Sprawdzanie"), measured


def failed_group(item: Mapping[str, object]) -> str | None:
    """Return the group whose failed processing P retries on this row, or None elsewhere."""
    group: object = item.get("group_id")
    return str(group) if item.get("reason") == "processing_failed" and group else None


def deletable_set(item: Mapping[str, object]) -> str | None:
    """Return the set Del deletes on a failed row, as in the Library, or None elsewhere."""
    set_id: object = item.get("set_id")
    return str(set_id) if failed_group(item) is not None and set_id else None


def cancel_target(item: Mapping[str, object]) -> tuple[str, str] | None:
    """Return the identity a cancellation of this row names, or None when it cannot be cancelled."""
    if item.get("stage") == "download" and item.get("info_hash"):
        return "info_hash", str(item["info_hash"])
    if (item.get("stage") == "processing" or item.get("admitted_processing")) and item.get("run_id"):
        return "run_id", str(item["run_id"])
    return None


def pause_toggle(item: Mapping[str, object]) -> tuple[str, str] | None:
    """Return the transfer action and label of W on a download row, or None elsewhere."""
    target: tuple[str, str] | None = cancel_target(item)
    return _download_toggle(item) if target is not None and target[0] == "info_hash" else None


def cancel_command(target: tuple[str, str]) -> tuple[str, Mapping[str, object]]:
    """Return the owner command cancelling ``target``."""
    if target[0] == "info_hash":
        return "transfer", {"info_hash": target[1], "action": "cancel"}
    return "cancel", {"run_id": target[1]}


def question_text(target: tuple[str, str], targeted: list[Mapping[str, object]]) -> str:
    """Return the cancellation question for the rows ``target`` names, or nothing when none remains."""
    if not targeted:
        return ""
    if target[0] == "info_hash":
        return "Anulować pobieranie?" if len(targeted) == 1 else f"Anulować pobieranie ({_materials(len(targeted))})?"
    scope: object = targeted[0].get("group_ids", [])
    return f"Anulować całe zlecenie ({_materials(len(scope) if isinstance(scope, list) else 1)})?"


def history_actions(*, listed: bool) -> ScreenActions:
    """Return the actions of the History list, opening and retrying only on a listed material."""
    material: tuple[Action, ...] = (("Enter", "otwórz"), ("P", "ponów")) if listed else ()
    return ScreenActions((*material, ("/", "szukaj")), (("H", "zamknij"), *PANEL_ACTIONS))


def processing_actions(item: Mapping[str, object] | None) -> ScreenActions:
    """Return the actions of the highlighted processing row."""
    target: tuple[str, str] | None = None if item is None else cancel_target(item)
    toggle: tuple[str, str] | None = None if item is None else pause_toggle(item)
    footer: tuple[Action, ...] = (
        *((("P", "ponów"),) if item is not None and failed_group(item) is not None else ()),
        *((("Del", "usuń"),) if item is not None and deletable_set(item) is not None else ()),
        *((("W", toggle[1]),) if toggle is not None else ()),
        *((("X", "anuluj"),) if target is not None else ()),
        ("H", "historia"),
    )
    return ScreenActions(footer, (("Ctrl+Z", "cofnij"), *PANEL_ACTIONS))


def history_entry(item: HistoryEvent) -> str:
    """Return the History row of one terminal material."""
    return (
        f"{item.occurred_at[:19].replace('T', ' ')} · {safe_text(item.name)}"
        f" · {_HISTORY_LABELS.get(item.kind, item.kind)}"
        + (" · odtworzony zapis · czas przyjęcia" if item.recovered_from_admission else "")
    )


def retry_entry(proposal: RetryProposal) -> str:
    """Return the only row of a retry proposal."""
    if proposal.action == "resume":
        return f"Dokończ całe zapisane zlecenie · {_materials(len(proposal.group_ids))} · podgląd"
    return _RETRY_LABELS.get(proposal.action, "Nieznana droga ponowienia")


def _materials(count: int) -> str:
    return f"{count} {plural(count, 'materiał', 'materiały', 'materiałów')}"


def _download_toggle(item: Mapping[str, object]) -> tuple[str, str] | None:
    if item.get("acquisition_state") == "pending_send" or item.get("state") in {
        "metaDL",
        "forcedMetaDL",
        "error",
        "missingFiles",
    }:
        return None
    if item.get("state") in {"pausedDL", "stoppedDL", "pausedUP", "stoppedUP"}:
        return "resume", "wznów"
    return "stop", "wstrzymaj"
