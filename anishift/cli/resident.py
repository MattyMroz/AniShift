"""Panel session for planning and running work through the resident."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING, Final

from anishift.application import (
    DeletionPreview,
    DownloadReceipt,
    EpisodeBatch,
    EpisodeFile,
    EpisodeFiles,
    EpisodeKey,
    EpisodeListing,
    EpisodeOffer,
    EpisodeOfferView,
    EpisodeStatus,
    Franchise,
    HistoryEvent,
    InspectedSourceGroup,
    InspectedWorkspace,
    LibraryFileIdentity,
    LibrarySet,
    PlanPreview,
    RecipePreferences,
    ReleaseCatalog,
    ReleaseChoice,
    RetryProposal,
    StreamCandidate,
    TitleCandidate,
    decode_view,
    encode_intent,
    encode_view,
    episode_read_timeout_s,
)
from anishift.application.cancellation import NeverCancelledToken
from anishift.application.events import RunEvent, RunEventKind
from anishift.application.planning import TaskState
from anishift.application.results import GroupResult, GroupStatus, RunResult
from anishift.platform.local_control import ControlClient, ControlError, ControlErrorCode

if TYPE_CHECKING:
    from anishift.application.cancellation import CancellationToken
    from anishift.application.events import RunEventSink
    from anishift.application.intents import AutoPreset, ExternalAudioRole, GroupIntent, RebuildRequest

# ── Constants ─────────────────────────────────────────────────────────────────

_SESSION_CLOSED: Final[str] = "The panel session is closed"
"""Refusal raised for a catalogue read started after the session closed."""

_READ_INTERRUPTED: Final[str] = "The catalogue read was interrupted"
"""Refusal raised for a catalogue read started before the latest `interrupt_reads`."""


class ResidentSession:
    """Keep one editing identity and delegate its work to the authenticated owner."""

    def __init__(self, workspace_root: Path, connect: Callable[[], ControlClient]) -> None:
        self.workspace_root: Path = workspace_root
        self._connect: Callable[[], ControlClient] = connect
        self._client: ControlClient | None = connect()
        self._client_id: str = token_hex(16)
        self._lock: threading.Lock = threading.Lock()
        self._reserved: tuple[str, ...] = ()
        self._events: ControlClient | None = None
        self._catalog: ControlClient | None = None
        self._catalog_lock: threading.Lock = threading.Lock()
        self._state_lock: threading.Lock = threading.Lock()
        self._closed: bool = False
        self._interrupts: int = 0
        self._open_offer: str | None = None
        self._external: dict[str, dict[str, object]] = {}

    def discover(self, *, cancel: CancellationToken | None = None) -> InspectedWorkspace:
        """Read the owner's inspected library without probing it in the panel."""
        token: CancellationToken = cancel or NeverCancelledToken()
        token.raise_if_cancelled()
        workspace: InspectedWorkspace = decode_view(InspectedWorkspace, self._call("discover"))
        token.raise_if_cancelled()
        return workspace

    def new_session(self) -> ResidentSession:
        """Open an independent editing identity for one manual wizard."""
        return ResidentSession(self.workspace_root, self._connect)

    def recipes(self) -> RecipePreferences:
        """Read the shared target deltas from their resident owner."""
        return decode_view(RecipePreferences, self._call("recipes_get"))

    def update_recipe(self, setting_id: str, value: str) -> RecipePreferences:
        """Persist one target delta without replacing another panel's choices."""
        self._call("recipe_update", {"setting_id": setting_id, "value": value})
        return self.recipes()

    def reset_recipe(self, scope: str) -> RecipePreferences:
        """Restore only the confirmed target scope at its owner."""
        self._call("recipe_update", {"reset": scope})
        return self.recipes()

    def library(self) -> tuple[LibrarySet, ...]:
        """Lightly reconcile the owner's completed sets without decoding media or starting Auto."""
        items: object = self._call("library_refresh").get("sets")
        if not isinstance(items, list):
            msg = "The owner returned an invalid library"
            raise TypeError(msg)
        return tuple(decode_view(LibrarySet, item) for item in items)

    def history(self, query: str = "") -> tuple[HistoryEvent, ...]:
        """Read completed logical materials from the owner's retained operational journal."""
        items: object = self._call("history", {"query": query}).get("items")
        if not isinstance(items, list):
            msg = "The owner returned invalid history"
            raise TypeError(msg)
        return tuple(decode_view(HistoryEvent, item) for item in items)

    def retry_proposal(self, material_id: str) -> RetryProposal:
        """Classify explicit retry using current owner state without starting work."""
        return decode_view(RetryProposal, self._call("retry_prepare", {"material_id": material_id}))

    def reacquire(self, operation_id: str) -> str:
        """Explicitly repeat one retained internet order after owner revalidation."""
        return str(self._call("reacquire", {"operation_id": operation_id})["operation_id"])

    def library_details(self, set_id: str) -> LibrarySet:
        """Read the current owned-file inventory for one stable set identity."""
        return decode_view(LibrarySet, self._call("library_details", {"set_id": set_id}))

    def library_result(self, set_id: str, *, playback: bool = True) -> Path:
        """Resolve the owner-validated playback path, or the confirmed main result when playback is false."""
        payload: dict[str, object] = {"set_id": set_id}
        if not playback:
            payload["playback"] = False
        answer: Mapping[str, object] = self._call("library_open", payload)
        relative: Path = Path(str(answer["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            msg = "The owner returned an invalid library path"
            raise ValueError(msg)
        return self.workspace_root / relative

    def preview_deletion(self, set_id: str) -> DeletionPreview:
        """Prepare an exact whole-set scope without performing any file operation."""
        return decode_view(DeletionPreview, self._call("deletion_preview", {"set_id": set_id}))

    def library_file(self, set_id: str, identity: LibraryFileIdentity) -> Path:
        """Resolve exactly the selected file after current owner-side membership validation."""
        answer: Mapping[str, object] = self._call(
            "library_file_open", {"set_id": set_id, "file": encode_view(identity)}
        )
        relative: Path = Path(str(answer["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            msg = "The owner returned an invalid library path"
            raise ValueError(msg)
        return self.workspace_root / relative

    def undo_deletion(self) -> str:
        """Restore only the latest effected deletion retained by the owner."""
        return str(self._call("deletion_undo")["operation_id"])

    def validate_deletion(self, preview: DeletionPreview) -> DeletionPreview:
        """Revalidate that exact scope and its owner-side exclusions without deleting files."""
        return decode_view(
            DeletionPreview,
            self._call(
                "deletion_validate",
                {"set_id": preview.set_id, "preview_id": preview.preview_id},
                instance_id=preview.instance_id,
            ),
        )

    def delete_set(self, preview: DeletionPreview) -> str:
        """Accept one previously confirmed exact scope; completion arrives through owner state broadcasts."""
        answer: Mapping[str, object] = self._call(
            "deletion_start",
            {"set_id": preview.set_id, "preview_id": preview.preview_id},
            instance_id=preview.instance_id,
        )
        return str(answer["operation_id"])

    def find_titles(self, text: str) -> tuple[TitleCandidate, ...]:
        """Search titles through the owner's shared network admission."""
        items: object = self._call("acquisition", {"operation": "titles", "query": text}).get("items")
        if not isinstance(items, list):
            msg = "The owner returned an invalid title list"
            raise TypeError(msg)
        return tuple(decode_view(TitleCandidate, item) for item in items)

    def search(self, query: str) -> ReleaseCatalog:
        """Read releases through the owner's shared request limits."""
        return decode_view(ReleaseCatalog, self._call("acquisition", {"operation": "search", "query": query}))

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> Franchise:
        """Read the franchise view of one entry through the owner; `interrupt_reads` stops its expansion."""
        token: CancellationToken = cancel or NeverCancelledToken()
        view: Franchise = decode_view(
            Franchise, self._episode_read({"operation": "franchise", "anilist_id": anilist_id}, token)
        )
        token.raise_if_cancelled()
        return view

    def interrupt_reads(self) -> None:
        """Refuse reads started earlier and close the catalogue channel, so the owner cancels its read."""
        with self._state_lock:
            self._interrupts += 1
            self._open_offer = None
            catalog: ControlClient | None = self._catalog
            self._catalog = None
        if catalog is not None:
            catalog.close()

    def episodes(self, anilist_id: int) -> EpisodeListing:
        """Read the episode list of one entry through the owner."""
        return decode_view(EpisodeListing, self._episode_read({"operation": "episodes", "anilist_id": anilist_id}))

    def offer(self, key: EpisodeKey) -> EpisodeOffer:
        """Read the ranked live candidates of one episode through the owner."""
        return decode_view(
            EpisodeOffer,
            self._episode_read({"operation": "offer", "anilist_id": key.anilist_id, "number": key.number}),
        )

    def download(
        self,
        choices: Sequence[ReleaseChoice],
        *,
        anilist_id: int | None = None,
        episode_offset: int | None = None,
    ) -> DownloadReceipt:
        """Persist a download order at the owner, with the catalogue entry and numbering it was read in."""
        payload: dict[str, object] = {"choices": [encode_view(choice) for choice in choices]}
        if anilist_id is not None:
            payload["anilist_id"] = anilist_id
        if episode_offset is not None:
            payload["episode_offset"] = episode_offset
        return decode_view(DownloadReceipt, self._call("download", payload))

    def episode_download(self, keys: Sequence[EpisodeKey], *, command_id: str) -> EpisodeBatch:
        """Admit one owner batch, or recover its receipt using the original command identifier."""
        return decode_view(
            EpisodeBatch,
            self._call("episode_download", {"keys": [encode_view(key) for key in keys]}, command_id=command_id),
        )

    def episode_offer_start(
        self,
        key: EpisodeKey,
        *,
        repeat: bool = False,
        previous_admission_id: str | None = None,
        command_id: str,
    ) -> Mapping[str, object]:
        """Start a session-bound search without holding the catalogue channel while sources run."""
        return self._episode_interaction(
            "episode_offer_start",
            {
                "key": encode_view(key),
                "repeat": repeat,
                "previous_admission_id": previous_admission_id,
            },
            command_id=command_id,
        )

    def episode_offer_get(self, offer_id: str) -> Mapping[str, object]:
        """Read the newest retained revision or the terminal failure of an open offer."""
        try:
            return self._episode_interaction("episode_offer_get", {"offer_id": offer_id})
        except ControlError as error:
            if error.connection_lost or (error.code is ControlErrorCode.REFUSED and not error.reason):
                message: str = "The episode offer expired"
                raise ControlError(message, code=ControlErrorCode.STALE_PREVIEW, reason="offer_expired") from error
            raise

    def episode_choose(
        self,
        offer: EpisodeOfferView,
        candidate: StreamCandidate,
        *,
        command_id: str,
        deviation_confirmed: bool = False,
        conflict_confirmed: bool = False,
    ) -> Mapping[str, object]:
        """Accept the exact inspected candidate with independently confirmed identity and legacy deviations."""
        return self._episode_interaction(
            "episode_choose",
            {
                "offer_id": offer.offer_id,
                "revision": offer.revision,
                "info_hash": candidate.info_hash,
                "path": candidate.path,
                "deviation_confirmed": deviation_confirmed,
                "conflict_confirmed": conflict_confirmed,
            },
            instance_id=offer.instance_id,
            command_id=command_id,
        )

    def episode_files(self, admission_id: str) -> EpisodeFiles:
        """Read safe video choices from the current torrent file map."""
        return decode_view(EpisodeFiles, self._call("episode_files", {"admission_id": admission_id}))

    def episode_file_choose(
        self, files: EpisodeFiles, selected: EpisodeFile, *, command_id: str
    ) -> Mapping[str, object]:
        """Bind the exact inspected video and its sidecars through the owner."""
        return self._call(
            "episode_file_choose",
            {
                "admission_id": files.admission_id,
                "revision": files.revision,
                "file": encode_view(selected),
            },
            command_id=command_id,
        )

    def episode_states(self, anilist_id: int, numbers: Sequence[int]) -> tuple[EpisodeStatus, ...]:
        """Read bounded episode states without a catalogue request."""
        items: object = self._call("episode_states", {"anilist_id": anilist_id, "numbers": list(numbers)}).get("items")
        if not isinstance(items, list):
            msg = "The owner returned invalid episode states"
            raise TypeError(msg)
        return tuple(decode_view(EpisodeStatus, item) for item in items)

    def subscription_add(self, anilist_id: int, *, command_id: str) -> Mapping[str, object]:
        """Ask the owner to follow one airing season; a repeated *command_id* returns the first answer."""
        return self._call("subscription_add", {"anilist_id": anilist_id}, command_id=command_id)

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        """Send a validated user action through the owner's command boundary."""
        return self._call(kind, payload)

    def observe(self, *, panel: bool = False) -> Iterator[Mapping[str, object]]:
        """Subscribe before reading the snapshot so concurrent progress is not lost."""
        events: ControlClient = self._connect()
        self._events = events
        try:
            events.subscribe()
            if panel:
                navigation: object = self._call("panel_attach").get("navigation")
                if isinstance(navigation, Mapping):
                    yield {"event": "panel_open", "payload": navigation}
            yield {"event": "state_changed", "payload": self._call("status")}
            yield from events.events()
        finally:
            events.close()
            self._events = None

    def start(self, preview: PlanPreview) -> str:
        """Accept a preview and return immediately while execution stays with the owner."""
        answer: Mapping[str, object] = self._call(
            "start",
            {"preview_id": preview.preview_id},
            instance_id=preview.instance_id,
        )
        self._reserved = ()
        return str(answer["run_id"])

    def reserve(self, group_ids: Sequence[str]) -> None:
        """Protect the complete selected scope before opening its editor."""
        self._call("reserve", {"group_ids": list(group_ids)})
        previous: tuple[str, ...] = self._reserved
        self._reserved = tuple(group_ids)
        removed: tuple[str, ...] = tuple(group for group in previous if group not in group_ids)
        if removed:
            self._call("release", {"group_ids": list(removed)})

    def release(self) -> None:
        """Release every group held by this editing session."""
        if self._reserved:
            self._call("release", {"group_ids": list(self._reserved)})
            self._reserved = ()

    def plan_auto(
        self,
        group_ids: Sequence[str],
        preset: AutoPreset,
        *,
        rebuild: RebuildRequest | None = None,
        overrides: Mapping[str, object] | None = None,
    ) -> PlanPreview:
        """Ask the owner to preview an explicit Auto or regeneration request."""
        answer: Mapping[str, object] = self._call(
            "preview",
            {
                "group_ids": list(group_ids),
                "preset": encode_view(preset),
                "rebuild": encode_view(rebuild) if rebuild is not None else None,
                "overrides": dict(overrides or {}),
            },
        )
        return decode_view(PlanPreview, answer["preview"])

    def plan_manual(self, intents: Sequence[GroupIntent]) -> PlanPreview:
        """Ask the owner to preview the selected sources and products."""
        answer: Mapping[str, object] = self._call(
            "preview",
            {
                "source_selection": "manual",
                "group_ids": [intent.group_id for intent in intents],
                "intents": [encode_intent(intent) for intent in intents],
                "external_sources": [
                    entry
                    for entry in self._external.values()
                    if entry["group_id"] in {intent.group_id for intent in intents}
                ],
            },
        )
        return decode_view(PlanPreview, answer["preview"])

    def plan_resume(self, group_ids: Sequence[str]) -> PlanPreview:
        """Preview the verified remaining work of the selected unfinished run."""
        answer: Mapping[str, object] = self._call("resume_preview", {"group_ids": list(group_ids)})
        return decode_view(PlanPreview, answer["preview"])

    def register_external_subtitle(
        self,
        group_id: str,
        path: Path,
        declared_language: str | None,
        *,
        cancel: CancellationToken | None = None,
    ) -> InspectedSourceGroup:
        """Register an external subtitle at the owner before selecting it."""
        return self._register(
            {"group_id": group_id, "path": str(path.resolve()), "kind": "subtitle", "language": declared_language},
            cancel,
        )

    def register_external_audio(
        self,
        group_id: str,
        path: Path,
        role: ExternalAudioRole,
        *,
        cancel: CancellationToken | None = None,
    ) -> InspectedSourceGroup:
        """Register external audio with its explicit source or narration role."""
        return self._register(
            {"group_id": group_id, "path": str(path.resolve()), "kind": "audio", "role": role.value}, cancel
        )

    def execute(self, preview: PlanPreview, sink: RunEventSink) -> RunResult:
        """Start that exact preview and relay events until the owner records its outcome."""
        events: ControlClient = self._connect()
        self._events = events
        run_id: str | None = None
        try:
            events.subscribe()
            answer: Mapping[str, object] = self._call(
                "start", {"preview_id": preview.preview_id}, instance_id=preview.instance_id
            )
            run_id = str(answer["run_id"])
            self._reserved = ()
            result: RunResult | None = self._result(run_id, preview)
            if result is not None:
                self._emit_result(result, sink)
                return result
            for frame in events.events():
                payload: object = frame.get("payload")
                if not isinstance(payload, Mapping) or payload.get("run_id") != run_id:
                    continue
                if frame.get("event") == "run_event":
                    sink.emit(decode_view(RunEvent, payload))
                elif frame.get("event") == "run_finished":
                    result = self._result(run_id, preview)
                    if result is not None:
                        return result
        except KeyboardInterrupt:
            if run_id is not None:
                self.cancel(run_id)
            raise
        finally:
            events.close()
            self._events = None
        msg = "The resident connection ended before the run outcome"
        raise ControlError(msg, code=ControlErrorCode.REFUSED)

    def cancel(self, run_id: str) -> bool:
        """Cancel the requested run without changing automatic processing policy."""
        return bool(self._call("cancel", {"run_id": run_id}).get("cancelled"))

    def close(self) -> None:
        """Detach the panel and release editing ownership without cancelling a run."""
        with self._state_lock:
            self._closed = True
            client: ControlClient | None = self._client
            catalog: ControlClient | None = self._catalog
        for other in (client, self._events, catalog):
            if other is not None:
                other.close()

    def disconnect(self) -> None:
        """Close idle command and catalogue connections so their next call reaches the current resident."""
        dropped: list[ControlClient] = []
        if self._lock.acquire(blocking=False):
            try:
                with self._state_lock:
                    if self._client is not None:
                        dropped.append(self._client)
                    self._client = None
            finally:
                self._lock.release()
        if self._catalog_lock.acquire(blocking=False):
            try:
                with self._state_lock:
                    if self._catalog is not None and self._open_offer is None:
                        dropped.append(self._catalog)
                        self._catalog = None
            finally:
                self._catalog_lock.release()
        for client in dropped:
            client.close()

    def _call(
        self,
        kind: str,
        payload: Mapping[str, object] | None = None,
        *,
        instance_id: str | None = None,
        command_id: str | None = None,
    ) -> Mapping[str, object]:
        with self._lock:
            client: ControlClient = self._command_channel()
            try:
                return client.call(
                    kind,
                    {"client_id": self._client_id, **(payload or {})},
                    instance_id=instance_id,
                    command_id=command_id,
                )
            except ControlError as error:
                if error.connection_lost:
                    self._drop(client)
                raise

    def _command_channel(self) -> ControlClient:
        with self._state_lock:
            if self._closed:
                raise ControlError(_SESSION_CLOSED, code=ControlErrorCode.REFUSED)
            if self._client is not None:
                return self._client
        opened: ControlClient = self._connect()
        with self._state_lock:
            if not self._closed:
                self._client = opened
                return opened
        opened.close()
        raise ControlError(_SESSION_CLOSED, code=ControlErrorCode.REFUSED)

    def _drop(self, client: ControlClient) -> None:
        with self._state_lock:
            if self._client is client:
                self._client = None
            if self._catalog is client:
                self._catalog = None
                self._open_offer = None
        client.close()

    def _episode_read(
        self, payload: Mapping[str, object], cancel: CancellationToken | None = None
    ) -> Mapping[str, object]:
        token: CancellationToken = cancel or NeverCancelledToken()
        with self._state_lock:
            interrupts: int = self._interrupts
        with self._catalog_lock:
            token.raise_if_cancelled()
            channel: ControlClient = self._catalog_channel(interrupts)
            token.raise_if_cancelled()
            with self._state_lock:
                self._require_current(interrupts)
            try:
                return channel.call("acquisition", payload, timeout_s=episode_read_timeout_s())
            except ControlError as error:
                if error.connection_lost:
                    self._drop(channel)
                raise

    def _episode_interaction(
        self,
        kind: str,
        payload: Mapping[str, object],
        *,
        instance_id: str | None = None,
        command_id: str | None = None,
    ) -> Mapping[str, object]:
        with self._state_lock:
            interrupts: int = self._interrupts
        with self._catalog_lock:
            channel: ControlClient = self._catalog_channel(interrupts)
            try:
                result: Mapping[str, object] = channel.call(
                    kind,
                    payload,
                    instance_id=instance_id,
                    command_id=command_id,
                    timeout_s=episode_read_timeout_s(),
                )
            except ControlError as error:
                if error.connection_lost:
                    self._drop(channel)
                elif error.reason == "offer_expired":
                    with self._state_lock:
                        self._open_offer = None
                raise
            with self._state_lock:
                self._require_current(interrupts)
                if kind == "episode_offer_start":
                    self._open_offer = decode_view(str, result.get("offer_id"))
                elif kind == "episode_choose" or result.get("state") == "failed":
                    self._open_offer = None
            return result

    def _catalog_channel(self, interrupts: int) -> ControlClient:
        with self._state_lock:
            self._require_current(interrupts)
            if self._catalog is not None:
                return self._catalog
        opened: ControlClient = self._connect()
        with self._state_lock:
            if not self._closed and self._interrupts == interrupts:
                self._catalog = opened
                return opened
        opened.close()
        with self._state_lock:
            self._require_current(interrupts)
        raise ControlError(_SESSION_CLOSED, code=ControlErrorCode.REFUSED)

    def _require_current(self, interrupts: int) -> None:
        if self._closed:
            raise ControlError(_SESSION_CLOSED, code=ControlErrorCode.REFUSED)
        if self._interrupts != interrupts:
            raise ControlError(_READ_INTERRUPTED, code=ControlErrorCode.REFUSED)

    def _register(self, payload: Mapping[str, object], cancel: CancellationToken | None) -> InspectedSourceGroup:
        token: CancellationToken = cancel or NeverCancelledToken()
        token.raise_if_cancelled()
        result: InspectedSourceGroup = decode_view(InspectedSourceGroup, self._call("register_external", payload))
        token.raise_if_cancelled()
        self._external[result.artifacts[-1].artifact_id] = dict(payload)
        return result

    def _emit_result(self, result: RunResult, sink: RunEventSink) -> None:
        sink.emit(RunEvent(result.run_id, 1, RunEventKind.RUN_STARTED))
        for sequence, group in enumerate(result.groups, start=2):
            state: TaskState = TaskState.SUCCEEDED if group.status is GroupStatus.SUCCEEDED else TaskState.FAILED
            if group.status is GroupStatus.CANCELLED:
                state = TaskState.CANCELLED
            sink.emit(
                RunEvent(result.run_id, sequence, RunEventKind.GROUP_FINISHED, group_id=group.group_id, state=state)
            )

    def _result(self, run_id: str, preview: PlanPreview) -> RunResult | None:
        answer: Mapping[str, object] = self._call("run_result", {"run_id": run_id})
        if answer.get("result") is not None:
            return decode_view(RunResult, answer["result"])
        if answer.get("state") in {"accepted", "running"}:
            return None
        return RunResult(
            run_id,
            tuple(
                GroupResult(group.group_id, GroupStatus.FAILED, error_messages=("The run has no available outcome",))
                for group in preview.groups
            ),
            paused=answer.get("state") == "paused",
        )
