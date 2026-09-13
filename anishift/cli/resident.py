"""Panel session for planning and running work through the resident."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from secrets import token_hex
from typing import TYPE_CHECKING

from anishift.application import (
    CatalogOrder,
    DownloadReceipt,
    EpisodeRange,
    InspectedSourceGroup,
    InspectedWorkspace,
    PlanPreview,
    ReleaseCatalog,
    ReleaseChoice,
    SeasonContext,
    Subscription,
    SubscriptionOrder,
    TitleCandidate,
    decode_view,
    encode_intent,
    encode_view,
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


class ResidentSession:
    """Keep one editing identity and delegate its work to the authenticated owner."""

    def __init__(self, workspace_root: Path, connect: Callable[[], ControlClient]) -> None:
        self.workspace_root: Path = workspace_root
        self._connect: Callable[[], ControlClient] = connect
        self._client: ControlClient = connect()
        self._client_id: str = token_hex(16)
        self._lock: threading.Lock = threading.Lock()
        self._reserved: tuple[str, ...] = ()
        self._events: ControlClient | None = None
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

    def season_context(self, candidate: TitleCandidate) -> SeasonContext:
        """Resolve season numbering at the owner."""
        return decode_view(
            SeasonContext,
            self._call(
                "acquisition",
                {"operation": "season", "candidate": encode_view(candidate)},
            ),
        )

    def search_title(
        self,
        candidate: TitleCandidate,
        *,
        episodes: EpisodeRange | None = None,
        order: CatalogOrder = CatalogOrder.NEWEST,
        context: SeasonContext | None = None,
    ) -> ReleaseCatalog:
        """Search the selected title and episode range without a second network client."""
        return decode_view(
            ReleaseCatalog,
            self._call(
                "acquisition",
                {
                    "operation": "releases",
                    "candidate": encode_view(candidate),
                    "order": order.value,
                    "episodes": encode_view(episodes) if episodes is not None else None,
                    "context": encode_view(context) if context is not None else None,
                },
            ),
        )

    def download(self, choices: Sequence[ReleaseChoice], *, directory_name: str | None = None) -> DownloadReceipt:
        """Persist a download order at the owner before it contacts the torrent client."""
        return decode_view(
            DownloadReceipt,
            self._call(
                "download",
                {"choices": [encode_view(choice) for choice in choices], "directory": directory_name},
            ),
        )

    def follow(self, order: SubscriptionOrder) -> Subscription:
        """Add a durable standing order and let the owner's schedule check it."""
        answer: Mapping[str, object] = self._call("subscription_add", {"order": encode_view(order)})
        return decode_view(Subscription, self._call("subscription_get", {"subscription_id": answer["subscription_id"]}))

    def command(self, kind: str, payload: Mapping[str, object] | None = None) -> Mapping[str, object]:
        """Send a validated user action through the owner's command boundary."""
        return self._call(kind, payload)

    def observe(self) -> Iterator[Mapping[str, object]]:
        """Subscribe before reading the snapshot so concurrent progress is not lost."""
        events: ControlClient = self._connect()
        self._events = events
        try:
            events.subscribe()
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
        self._client.close()
        events: ControlClient | None = self._events
        if events is not None:
            events.close()

    def _call(
        self, kind: str, payload: Mapping[str, object] | None = None, *, instance_id: str | None = None
    ) -> Mapping[str, object]:
        with self._lock:
            return self._client.call(kind, {"client_id": self._client_id, **(payload or {})}, instance_id=instance_id)

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
