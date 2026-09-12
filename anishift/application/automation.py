"""The one owner of the automation state, its reservations and its processing requests."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from queue import SimpleQueue
from secrets import token_hex
from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import ArtifactLifetime, ArtifactState
from anishift.application.control import (
    CommandReceipt,
    ManualHandledMarker,
    ProcessingRequest,
    RequestState,
    Reservation,
    SourceSelection,
    WatchState,
    mark_manual_handled,
    record_command,
    record_request,
    release,
    reserve,
)
from anishift.application.events import sanitize_event_message
from anishift.application.intents import RequestOrigin
from anishift.application.results import GroupStatus
from anishift.application.selection import ready_group_ids
from anishift.application.watch import snapshot_sources, source_fingerprint
from anishift.errors import AniShiftError
from anishift.platform.local_control import ControlErrorCode, ControlRequest, ControlResponse
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from anishift.application.control import CommandOutcome, SettingsSnapshot, SourceFingerprint
    from anishift.application.events import RunEvent
    from anishift.application.inspection import InspectedSourceGroup, InspectedWorkspace
    from anishift.application.intents import AutoPreset, ProductKind
    from anishift.application.planning import ExecutionPlan, RunSettingsSnapshot
    from anishift.application.results import RunResult
    from anishift.application.scheduler import RunHandle
    from anishift.application.service import AppService
    from anishift.application.subscriptions import Subscription, SubscriptionService
    from anishift.application.watch_state import WatchStateStore

__all__ = ["AutomationOwner"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

OWNER_THREAD_NAME: Final[str] = "anishift-owner"
"""Name of the one thread every command of the resident is performed on."""

IO_THREAD_PREFIX: Final[str] = "anishift-owner-io"
"""Name prefix of the pool the slow input and output of a command runs on."""

IO_WORKERS: Final[int] = 2
"""Slow commands performed beside each other while the owner keeps answering."""

COMMAND_TIMEOUT_S: Final[float] = 300.0
"""Wait for one command before the connection is answered with an internal fault."""

_ID_BYTES: Final[int] = 8
"""Random bytes making one generated run, preview or command identifier unique."""

_UNKNOWN_COMMAND: Final[str] = "The resident does not know this command"
"""Reason returned for a command kind outside the documented set."""

_STALE_INSTANCE: Final[str] = "The resident restarted; refresh the state and try again"
"""Reason returned when a command names an instance that no longer owns the state."""

_STALE_PREVIEW: Final[str] = "The sources changed since the preview; ask for a new one"
"""Reason returned when a preview no longer describes the current sources."""

_UNKNOWN_PREVIEW: Final[str] = "The resident holds no such preview"
"""Reason returned for a preview identifier this instance never issued."""

_GROUP_HELD: Final[str] = "Another client holds one of the requested groups"
"""Reason returned when a reservation or an active request blocks the command."""

_STATE_NOT_SAVED: Final[str] = "The automation state could not be saved, so nothing changed"
"""Reason returned when the command was abandoned instead of applied unrecorded."""

_NO_ANSWER: Final[str] = "The resident did not finish the command in time"
"""Reason returned when the owner thread was still busy when the budget ran out."""

_COMMAND_FAILED: Final[str] = "The resident could not complete the command"
"""Reason returned when performing one command raised instead of answering."""

_SHUTTING_DOWN: Final[str] = "The resident is shutting down and admits no new work"
"""Reason returned for work requested after a shutdown was accepted."""

_NO_SUBSCRIPTIONS: Final[str] = "This resident was composed without a torrent client"
"""Reason returned for a subscription command with no subscription service behind it."""

_NOT_PLANNABLE: Final[str] = "The sources cannot be planned into an executable run"
"""Reason returned when planning fails or the plan carries a blocking problem."""

_MUTATING_KINDS: Final[frozenset[str]] = frozenset(
    {
        "set_auto",
        "set_directory_auto",
        "reserve",
        "release",
        "start",
        "cancel",
        "shutdown",
        "subscription_enable",
        "subscription_disable",
        "subscription_remove",
    }
)
"""Commands whose outcome is recorded, so repeating an identifier repeats no effect."""

_SLOW_KINDS: Final[frozenset[str]] = frozenset({"preview", "subscriptions_check"})
"""Commands performed on the pool, because they scan the library or reach the network."""

_INSTANCE_CHECKED_KINDS: Final[frozenset[str]] = frozenset({"start", "reserve", "release", "cancel"})
"""Commands a client may only send to the instance it last read the state from."""

_ACTIVE_STATES: Final[frozenset[RequestState]] = frozenset({RequestState.ACCEPTED, RequestState.RUNNING})
"""Request states that still own their groups."""

_RESULT_STATES: Final[Mapping[GroupStatus, RequestState]] = {
    GroupStatus.SUCCEEDED: RequestState.SUCCEEDED,
    GroupStatus.PARTIAL: RequestState.PARTIAL,
    GroupStatus.FAILED: RequestState.FAILED,
    GroupStatus.CANCELLED: RequestState.CANCELLED,
}
"""Terminal group outcome mapped onto the state one request is recorded with."""

_SNAPSHOT_FIELDS: Final[tuple[str, ...]] = (
    "translation_profile_id",
    "translation_concurrency",
    "llm_profile_id",
    "llm_model_id",
    "llm_translation_style",
    "llm_max_concurrency",
    "tts_profile_id",
    "tts_model_id",
    "tts_voice_id",
    "tts_voice_label",
    "tts_group_jobs",
    "audio_profile_id",
    "audio_output_profile",
    "composition_profile_id",
    "processing_order_policy",
)
"""Planning settings identifying how one request was accepted."""

_WORST_FIRST: Final[tuple[RequestState, ...]] = (
    RequestState.CANCELLED,
    RequestState.FAILED,
    RequestState.PARTIAL,
)
"""Order deciding the state of a request whose groups ended differently."""

type Clock = Callable[[], datetime]
"""Source of the moment a command or a record was accepted."""

type Broadcast = Callable[[Mapping[str, object]], None]
"""Hands one event to every subscriber of the control channel."""


@dataclass(frozen=True, slots=True)
class _Preview:
    """One planned answer a client may turn into a request while its sources hold."""

    preview_id: str
    client_id: str
    plan: ExecutionPlan
    groups: tuple[InspectedSourceGroup, ...]
    fingerprints: Mapping[str, SourceFingerprint]
    products: frozenset[ProductKind]
    origin: RequestOrigin
    source_selection: SourceSelection


@dataclass(slots=True)
class _Command:
    """One command waiting for the owner thread, and the answer it will carry back."""

    request: ControlRequest
    done: threading.Event
    response: ControlResponse | None = None

    def answer(self, response: ControlResponse) -> None:
        """Publish the outcome to the connection thread that is waiting for it."""
        self.response = response
        self.done.set()


@dataclass(frozen=True, slots=True)
class _Completion:
    """One finished request the owner thread has to record."""

    request_id: str
    result: RunResult | None


class AutomationOwner:
    """Owns the watch state, admits requests and answers every control command."""

    def __init__(
        self,
        service: AppService,
        store: WatchStateStore,
        *,
        instance_id: str,
        clock: Clock = lambda: datetime.now(UTC),
        broadcast: Broadcast | None = None,
    ) -> None:
        """Load the persisted state and prepare the owner thread and its pool."""
        self._service: AppService = service
        self._store: WatchStateStore = store
        self._instance_id: str = instance_id
        self._clock: Clock = clock
        self._broadcast: Broadcast | None = broadcast
        self._state: WatchState = store.load()
        self._queue: SimpleQueue[_Command | _Completion] = SimpleQueue()
        self._pool: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=IO_WORKERS,
            thread_name_prefix=IO_THREAD_PREFIX,
        )
        self._previews: dict[str, _Preview] = {}
        self._pending: dict[str, frozenset[ProductKind]] = {}
        self._shutting_down: bool = False

    @property
    def instance_id(self) -> str:
        """Identity every client must name on a command that owns a group."""
        return self._instance_id

    @property
    def state(self) -> WatchState:
        """The automation state as it was last persisted."""
        return self._state

    def attach_broadcast(self, broadcast: Broadcast) -> None:
        """Publish run events and state changes through *broadcast*."""
        self._broadcast = broadcast

    def handle(self, request: ControlRequest) -> ControlResponse:
        """Queue one command for the owner thread and wait for its answer."""
        command = _Command(request=request, done=threading.Event())
        self._queue.put(command)
        if not command.done.wait(COMMAND_TIMEOUT_S):
            logger.warning("A control command was not answered in time", command_kind=request.kind)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _NO_ANSWER)
        answered: ControlResponse | None = command.response
        return answered if answered is not None else ControlResponse.refused(ControlErrorCode.INTERNAL, _NO_ANSWER)

    def request_shutdown(self) -> None:
        """Ask the owner to stop admitting work and end once the active requests finish."""
        shutdown = ControlRequest(command_id=f"shutdown-{token_hex(_ID_BYTES)}", kind="shutdown", payload={})
        self._queue.put(_Command(request=shutdown, done=threading.Event()))

    def serve(self) -> None:
        """Run the owner loop until a shutdown drains every active request."""
        threading.current_thread().name = OWNER_THREAD_NAME
        self._service.set_background_admission(self._state.policy.auto_enabled)
        try:
            self._loop()
        finally:
            self._pool.shutdown(wait=True)

    def _loop(self) -> None:
        while True:
            try:
                item: _Command | _Completion = self._queue.get()
            except KeyboardInterrupt:
                self._begin_shutdown()
                if self._drained():
                    return
                continue
            if isinstance(item, _Completion):
                self._record_completion(item)
            else:
                self._dispatch(item)
            if self._drained():
                return

    def _drained(self) -> bool:
        """Whether a shutdown may end the loop: nothing runs and every request was recorded."""
        if not self._shutting_down:
            return False
        return not self._pending and not self._service.active_run_ids()

    def _dispatch(self, command: _Command) -> None:
        request: ControlRequest = command.request
        receipt: CommandReceipt | None = self._receipt(request)
        if receipt is not None:
            command.answer(ControlResponse.succeeded(dict(receipt.outcome)))
            return
        if request.kind in _INSTANCE_CHECKED_KINDS and request.instance_id not in {None, self._instance_id}:
            command.answer(ControlResponse.refused(ControlErrorCode.STALE_INSTANCE, _STALE_INSTANCE))
            return
        if request.kind in _SLOW_KINDS:
            self._pool.submit(self._answer, command)
            return
        self._answer(command)

    def _answer(self, command: _Command) -> None:
        """Answer one command, keeping a faulty one from ending the owner loop."""
        try:
            command.answer(self._perform(command.request))
        except Exception:  # noqa: BLE001 - the owner must survive any single faulty command
            logger.warning("A control command failed", command_kind=command.request.kind)
            command.answer(ControlResponse.refused(ControlErrorCode.INTERNAL, _COMMAND_FAILED))

    def _perform(self, request: ControlRequest) -> ControlResponse:  # noqa: PLR0911 - one branch per command kind
        match request.kind:
            case "status":
                return ControlResponse.succeeded(self._status())
            case "set_auto":
                return self._set_auto(request)
            case "set_directory_auto":
                return self._set_directory_auto(request)
            case "reserve":
                return self._reserve(request)
            case "release":
                return self._release(request)
            case "preview":
                return self._preview(request)
            case "start":
                return self._start(request)
            case "cancel":
                return self._cancel(request)
            case "reload_settings":
                return self._reload_settings()
            case "shutdown":
                return self._shutdown(request)
            case kind if kind.startswith("subscription"):
                return self._subscription_command(request)
            case _:
                return ControlResponse.refused(ControlErrorCode.UNKNOWN_COMMAND, _UNKNOWN_COMMAND)

    # ── Policy ────────────────────────────────────────────────────────────────

    def _status(self) -> dict[str, object]:
        policy = self._state.policy
        return {
            "instance_id": self._instance_id,
            "pid": os.getpid(),
            "auto_enabled": policy.auto_enabled,
            "directory_exceptions": dict(policy.directory_exceptions),
            "requests": [
                {
                    "request_id": request.request_id,
                    "origin": request.origin.value,
                    "source_selection": request.source_selection.value,
                    "state": request.state.value,
                    "group_ids": list(request.group_ids),
                }
                for request in self._state.requests
                if request.state in _ACTIVE_STATES
            ],
            "reservations": [
                {"group_id": item.group_id, "client_id": item.client_id} for item in self._state.reservations
            ],
            "subscriptions": self._subscription_counts(),
            "shutting_down": self._shutting_down,
            "updated_at": self._now(),
        }

    def _set_auto(self, request: ControlRequest) -> ControlResponse:
        enabled: bool | None = _flag(request.payload, "enabled")
        if enabled is None:
            return _invalid("A switch command needs an `enabled` flag")
        policy = replace(self._state.policy, auto_enabled=enabled)
        outcome: dict[str, str | int | bool | None] = {"auto_enabled": enabled}
        refusal: ControlResponse | None = self._commit(request, replace(self._state, policy=policy), outcome)
        if refusal is not None:
            return refusal
        self._service.set_background_admission(enabled)
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _set_directory_auto(self, request: ControlRequest) -> ControlResponse:
        directory: str | None = _text(request.payload, "directory", allow_empty=True)
        exception: object = request.payload.get("enabled")
        if directory is None or (exception is not None and not isinstance(exception, bool)):
            return _invalid("A directory exception needs a `directory` and a boolean or null `enabled`")
        exceptions: dict[str, bool] = dict(self._state.policy.directory_exceptions)
        if exception is None:
            exceptions.pop(directory, None)
        else:
            exceptions[directory] = exception
        policy = replace(self._state.policy, directory_exceptions=exceptions)
        outcome: dict[str, str | int | bool | None] = {"directory": directory, "enabled": exception}
        refusal: ControlResponse | None = self._commit(request, replace(self._state, policy=policy), outcome)
        if refusal is not None:
            return refusal
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    # ── Reservations ──────────────────────────────────────────────────────────

    def _reserve(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        group_ids: tuple[str, ...] | None = _identifiers(request.payload, "group_ids")
        if client_id is None or group_ids is None:
            return _invalid("A reservation needs a `client_id` and `group_ids`")
        moment: str = self._now()
        candidate: WatchState = self._state
        for group_id in group_ids:
            held: WatchState | None = reserve(
                candidate,
                Reservation(
                    group_id=group_id,
                    fingerprint=self._previewed_fingerprint(group_id),
                    client_id=client_id,
                    reserved_at=moment,
                ),
            )
            if held is None:
                return ControlResponse.refused(ControlErrorCode.CONFLICT, _GROUP_HELD)
            candidate = held
        outcome: dict[str, str | int | bool | None] = {"reserved": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    def _release(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        group_ids: tuple[str, ...] | None = _identifiers(request.payload, "group_ids")
        if client_id is None or group_ids is None:
            return _invalid("A release needs a `client_id` and `group_ids`")
        candidate: WatchState = self._state
        for group_id in group_ids:
            candidate = release(candidate, group_id, client_id)
        outcome: dict[str, str | int | bool | None] = {"released": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    # ── Preview and start ─────────────────────────────────────────────────────

    def _preview(self, request: ControlRequest) -> ControlResponse:
        client_id: str | None = _text(request.payload, "client_id")
        origin: RequestOrigin | None = _origin(request.payload)
        selection: SourceSelection | None = _selection(request.payload)
        if client_id is None or origin is None or selection is None:
            return _invalid("A preview needs a `client_id`, a known `origin` and `source_selection`")
        planned: tuple[ExecutionPlan, tuple[InspectedSourceGroup, ...], AutoPreset] | None = self._plan(request.payload)
        if planned is None:
            return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, _NOT_PLANNABLE)
        plan, groups, preset = planned
        preview = _Preview(
            preview_id=f"preview-{token_hex(_ID_BYTES)}",
            client_id=client_id,
            plan=plan,
            groups=groups,
            fingerprints={group.group_id: _group_fingerprint(group) for group in groups},
            products=preset.products.requested_products,
            origin=origin,
            source_selection=selection,
        )
        self._previews[preview.preview_id] = preview
        return ControlResponse.succeeded(
            {
                "preview_id": preview.preview_id,
                "instance_id": self._instance_id,
                "can_execute": plan.can_execute,
                "groups": _product_projection(plan),
            }
        )

    def _plan(
        self,
        payload: Mapping[str, object],
    ) -> tuple[ExecutionPlan, tuple[InspectedSourceGroup, ...], AutoPreset] | None:
        preset_id: str | None = _text(payload, "preset_id")
        try:
            workspace: InspectedWorkspace = self._service.discover()
            preset: AutoPreset = self._service.get_preset(preset_id or self._service.default_preset_id())
            groups: tuple[InspectedSourceGroup, ...] = _requested_groups(workspace, payload)
            plan: ExecutionPlan = self._service.plan_auto(tuple(group.group_id for group in groups), preset)
        except (AniShiftError, OSError, KeyError, ValueError) as problem:
            logger.warning("A preview could not be planned", error_class=type(problem).__name__)
            return None
        return plan, groups, preset

    def _start(self, request: ControlRequest) -> ControlResponse:
        if self._shutting_down:
            return ControlResponse.refused(ControlErrorCode.REFUSED, _SHUTTING_DOWN)
        client_id: str | None = _text(request.payload, "client_id")
        preview_id: str | None = _text(request.payload, "preview_id")
        if client_id is None or preview_id is None:
            return _invalid("A start needs a `client_id` and a `preview_id`")
        preview: _Preview | None = self._previews.get(preview_id)
        refusal: ControlResponse | None = self._unstartable(preview, client_id)
        if refusal is not None or preview is None:
            return refusal if refusal is not None else _invalid(_UNKNOWN_PREVIEW)
        return self._admit(request, preview, tuple(group.group_id for group in preview.groups), client_id)

    def _unstartable(self, preview: _Preview | None, client_id: str) -> ControlResponse | None:
        """Return why *preview* cannot become a request, or ``None`` when it can."""
        if preview is None:
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _UNKNOWN_PREVIEW)
        if preview.client_id != client_id:
            return ControlResponse.refused(ControlErrorCode.CONFLICT, _GROUP_HELD)
        if not preview.plan.can_execute:
            return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, _NOT_PLANNABLE)
        if any(_group_fingerprint(group) != preview.fingerprints[group.group_id] for group in preview.groups):
            self._previews.pop(preview.preview_id, None)
            return ControlResponse.refused(ControlErrorCode.STALE_PREVIEW, _STALE_PREVIEW)
        if self._blocked(tuple(group.group_id for group in preview.groups), client_id):
            return ControlResponse.refused(ControlErrorCode.CONFLICT, _GROUP_HELD)
        return None

    def _admit(
        self,
        request: ControlRequest,
        preview: _Preview,
        group_ids: tuple[str, ...],
        client_id: str,
    ) -> ControlResponse:
        run_id: str = f"run-{token_hex(_ID_BYTES)}"
        accepted = ProcessingRequest(
            request_id=run_id,
            generation=1,
            group_ids=group_ids,
            fingerprints=dict(preview.fingerprints),
            origin=preview.origin,
            source_selection=preview.source_selection,
            rebuild=None,
            settings=_settings_snapshot(preview.plan.settings),
            state=RequestState.ACCEPTED,
            attempts=1,
            accepted_at=self._now(),
        )
        candidate: WatchState = record_request(self._state, accepted)
        for group_id in group_ids:
            candidate = release(candidate, group_id, client_id)
        outcome: dict[str, str | int | bool | None] = {"run_id": run_id, "groups": len(group_ids)}
        refusal: ControlResponse | None = self._commit(request, candidate, outcome)
        if refusal is not None:
            return refusal
        self._previews.pop(preview.preview_id, None)
        self._pending[run_id] = preview.products
        try:
            handle: RunHandle = self._service.submit_plan(
                preview.plan,
                _OwnerSink(self._publish_event),
                origin=preview.origin,
                run_id=run_id,
            )
        except (AniShiftError, OSError) as problem:
            logger.warning("An accepted request could not be submitted", error_class=type(problem).__name__)
            self._pending.pop(run_id, None)
            self._save(record_request(self._state, replace(accepted, state=RequestState.FAILED)))
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _NOT_PLANNABLE)
        self._watch_run(run_id, handle)
        self._publish_state()
        return ControlResponse.succeeded(outcome)

    def _cancel(self, request: ControlRequest) -> ControlResponse:
        run_id: str | None = _text(request.payload, "run_id")
        if run_id is None:
            return _invalid("A cancellation needs a `run_id`")
        cancelled: bool = self._service.cancel(run_id)
        outcome: dict[str, str | int | bool | None] = {"run_id": run_id, "cancelled": cancelled}
        refusal: ControlResponse | None = self._commit(request, self._state, outcome)
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    def _watch_run(self, run_id: str, handle: RunHandle) -> None:
        """Report the terminal outcome of one accepted request back to the owner thread."""

        def wait() -> None:
            try:
                result: RunResult | None = handle.result()
            except (AniShiftError, OSError, TimeoutError) as problem:
                logger.warning("A request ended in a terminal fault", error_class=type(problem).__name__)
                result = None
            self._queue.put(_Completion(request_id=run_id, result=result))

        # An unnamed thread keeps the "anishift-" prefix for the threads that must be joined.
        threading.Thread(target=wait, daemon=True).start()

    def _record_completion(self, completion: _Completion) -> None:
        products: frozenset[ProductKind] = self._pending.pop(completion.request_id, frozenset())
        recorded: ProcessingRequest | None = next(
            (item for item in self._state.requests if item.request_id == completion.request_id),
            None,
        )
        if recorded is None:
            return
        finished: ProcessingRequest = replace(recorded, state=_request_state(completion.result))
        candidate: WatchState = record_request(self._state, finished)
        if finished.origin is RequestOrigin.USER and products:
            candidate = _marked(candidate, finished, products, self._now())
        self._save(candidate)
        self._publish_state()

    # ── Settings, subscriptions and shutdown ──────────────────────────────────

    def _reload_settings(self) -> ControlResponse:
        try:
            self._service.reload_preferences()
        except (AniShiftError, OSError) as problem:
            logger.warning("Preferences could not be reloaded", error_class=type(problem).__name__)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return ControlResponse.succeeded({"reloaded": True})

    def _shutdown(self, request: ControlRequest) -> ControlResponse:
        outcome: dict[str, str | int | bool | None] = {"shutting_down": True}
        refusal: ControlResponse | None = self._commit(request, self._state, outcome)
        if refusal is not None:
            return refusal
        self._begin_shutdown()
        return ControlResponse.succeeded(outcome)

    def _begin_shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._service.set_background_admission(False)
        logger.info("The resident is shutting down", active_runs=len(self._service.active_run_ids()))
        self._publish_state()

    def _subscription_command(self, request: ControlRequest) -> ControlResponse:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            return ControlResponse.refused(ControlErrorCode.REFUSED, _NO_SUBSCRIPTIONS)
        if request.kind == "subscriptions_list":
            return ControlResponse.succeeded({"subscriptions": [_subscription_view(item) for item in service.list()]})
        if request.kind == "subscriptions_check":
            outcomes = service.check_all()
            return ControlResponse.succeeded(
                {
                    "checked": len(outcomes),
                    "downloaded": sum(outcome.downloaded for outcome in outcomes),
                    "problems": sum(1 for outcome in outcomes if outcome.problem),
                }
            )
        return self._subscription_mutation(request, service)

    def _subscription_mutation(self, request: ControlRequest, service: SubscriptionService) -> ControlResponse:
        identifier: str | None = _text(request.payload, "subscription_id")
        if identifier is None:
            return _invalid("A subscription command needs a `subscription_id`")
        outcome: dict[str, str | int | bool | None]
        try:
            match request.kind:
                case "subscription_enable":
                    outcome = {"subscription_id": identifier, "enabled": service.enable(identifier).enabled}
                case "subscription_disable":
                    outcome = {"subscription_id": identifier, "enabled": service.disable(identifier).enabled}
                case "subscription_remove":
                    outcome = {"subscription_id": identifier, "removed": service.remove(identifier)}
                case _:
                    return ControlResponse.refused(ControlErrorCode.UNKNOWN_COMMAND, _UNKNOWN_COMMAND)
        except (AniShiftError, OSError) as problem:
            logger.warning("A subscription command failed", error_class=type(problem).__name__)
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        refusal: ControlResponse | None = self._commit(request, self._state, outcome)
        return refusal if refusal is not None else ControlResponse.succeeded(outcome)

    def _subscription_counts(self) -> dict[str, int]:
        service: SubscriptionService | None = self._service.subscriptions
        if service is None:
            return {"enabled": 0, "disabled": 0}
        try:
            subscriptions: tuple[Subscription, ...] = service.list()
        except AniShiftError, OSError:
            return {"enabled": 0, "disabled": 0}
        enabled: int = sum(1 for item in subscriptions if item.enabled)
        return {"enabled": enabled, "disabled": len(subscriptions) - enabled}

    # ── Persistence and events ────────────────────────────────────────────────

    def _commit(
        self,
        request: ControlRequest,
        candidate: WatchState,
        outcome: CommandOutcome,
    ) -> ControlResponse | None:
        """Persist *candidate* with the receipt of *request*; a response means it failed."""
        if request.kind not in _MUTATING_KINDS:
            self._state = candidate
            return None
        receipt = CommandReceipt(command_id=request.command_id, accepted_at=self._now(), outcome=outcome)
        if not self._save(record_command(candidate, receipt)):
            return ControlResponse.refused(ControlErrorCode.INTERNAL, _STATE_NOT_SAVED)
        return None

    def _save(self, candidate: WatchState) -> bool:
        try:
            self._store.save(candidate)
        except (AniShiftError, OSError) as problem:
            logger.warning("The automation state could not be saved", error_class=type(problem).__name__)
            return False
        self._state = candidate
        return True

    def _receipt(self, request: ControlRequest) -> CommandReceipt | None:
        if request.kind not in _MUTATING_KINDS:
            return None
        return next((item for item in self._state.command_receipts if item.command_id == request.command_id), None)

    def _publish_event(self, event: RunEvent) -> None:
        self._publish(
            {
                "event": "run_event",
                "payload": {
                    "run_id": event.run_id,
                    "sequence": event.sequence,
                    "kind": event.kind.value,
                    "group_id": event.group_id,
                    "task_id": event.task_id,
                    "state": event.state.value if event.state is not None else None,
                    "progress_percent": event.progress_percent,
                    "message": event.message,
                },
            }
        )

    def _publish_state(self) -> None:
        self._publish({"event": "state_changed", "payload": self._status()})

    def _publish(self, frame: Mapping[str, object]) -> None:
        broadcast: Broadcast | None = self._broadcast
        if broadcast is not None:
            broadcast(frame)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _blocked(self, group_ids: Sequence[str], client_id: str) -> bool:
        held: Mapping[str, str] = {item.group_id: item.client_id for item in self._state.reservations}
        if any(held.get(group_id, client_id) != client_id for group_id in group_ids):
            return True
        active: frozenset[str] = frozenset(
            group_id
            for request in self._state.requests
            if request.state in _ACTIVE_STATES
            for group_id in request.group_ids
        )
        return bool(active.intersection(group_ids))

    def _previewed_fingerprint(self, group_id: str) -> SourceFingerprint:
        """Source version a preview already measured, or none when the group was not previewed."""
        for preview in self._previews.values():
            known: SourceFingerprint | None = preview.fingerprints.get(group_id)
            if known is not None:
                return known
        return ()

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat()


class _OwnerSink:
    """Forwards every run event of the resident to the subscribers of the channel."""

    def __init__(self, publish: Callable[[RunEvent], None]) -> None:
        """Bind one publisher shared by every request this resident admitted."""
        self._publish: Callable[[RunEvent], None] = publish

    def emit(self, event: RunEvent) -> None:
        """Publish one event without owning any workflow state."""
        self._publish(event)


def _marked(
    state: WatchState,
    request: ProcessingRequest,
    products: frozenset[ProductKind],
    moment: str,
) -> WatchState:
    """Record what the user settled for every group of one finished explicit request."""
    marked: WatchState = state
    for group_id in request.group_ids:
        fingerprint: SourceFingerprint | None = request.fingerprints.get(group_id)
        if fingerprint is None:
            continue
        marked = mark_manual_handled(
            marked,
            ManualHandledMarker(
                group_id=group_id,
                fingerprint=fingerprint,
                products=products,
                request_id=request.request_id,
                recorded_at=moment,
            ),
        )
    return marked


def _request_state(result: RunResult | None) -> RequestState:
    if result is None:
        return RequestState.FAILED
    states: frozenset[RequestState] = frozenset(
        _RESULT_STATES.get(group.status, RequestState.FAILED) for group in result.groups
    )
    return next((candidate for candidate in _WORST_FIRST if candidate in states), RequestState.SUCCEEDED)


def _product_projection(plan: ExecutionPlan) -> list[dict[str, object]]:
    """Report the durable products every planned group keeps and the ones it produces."""
    preserved: dict[str, set[str]] = {group.group_id: set() for group in plan.groups}
    planned: dict[str, set[str]] = {group.group_id: set() for group in plan.groups}
    for artifact in plan.artifacts:
        if artifact.lifetime is not ArtifactLifetime.DURABLE or artifact.group_id not in preserved:
            continue
        bucket: dict[str, set[str]] = preserved if artifact.state is ArtifactState.READY else planned
        bucket[artifact.group_id].add(artifact.kind.value)
    return [
        {
            "group_id": group.group_id,
            "preserved_products": sorted(preserved[group.group_id]),
            "planned_products": sorted(planned[group.group_id]),
            "problems": [
                {
                    "code": problem.code,
                    "message": sanitize_event_message(problem.message),
                    "is_blocking": problem.is_blocking,
                }
                for problem in group.problems
            ],
        }
        for group in plan.groups
    ]


def _settings_snapshot(settings: RunSettingsSnapshot) -> SettingsSnapshot:
    """Keep the planning settings identifying how one request was accepted."""
    known: frozenset[str] = frozenset(field.name for field in fields(settings))
    return {name: getattr(settings, name) for name in _SNAPSHOT_FIELDS if name in known}


def _group_fingerprint(group: InspectedSourceGroup) -> SourceFingerprint:
    return source_fingerprint(snapshot_sources(group, {}, 0.0))


def _requested_groups(workspace: InspectedWorkspace, payload: Mapping[str, object]) -> tuple[InspectedSourceGroup, ...]:
    requested: tuple[str, ...] | None = _identifiers(payload, "group_ids")
    by_id: Mapping[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
    selected: tuple[str, ...] = requested if requested is not None else ready_group_ids(workspace.groups)
    return tuple(by_id[group_id] for group_id in selected)


def _subscription_view(subscription: Subscription) -> dict[str, object]:
    return {
        "subscription_id": subscription.subscription_id,
        "series": subscription.series,
        "group": subscription.group,
        "next_episode": str(subscription.next_episode),
        "enabled": subscription.enabled,
        "end_state": subscription.end_state.value,
    }


def _invalid(message: str) -> ControlResponse:
    return ControlResponse.refused(ControlErrorCode.INVALID_PAYLOAD, message)


def _flag(payload: Mapping[str, object], key: str) -> bool | None:
    value: object = payload.get(key)
    return value if isinstance(value, bool) else None


def _text(payload: Mapping[str, object], key: str, *, allow_empty: bool = False) -> str | None:
    value: object = payload.get(key)
    if not isinstance(value, str) or (not value and not allow_empty):
        return None
    return value


def _identifiers(payload: Mapping[str, object], key: str) -> tuple[str, ...] | None:
    value: object = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return None
    return tuple(str(item) for item in value)


def _origin(payload: Mapping[str, object]) -> RequestOrigin | None:
    named: object = payload.get("origin", RequestOrigin.USER.value)
    if not isinstance(named, str):
        return None
    try:
        return RequestOrigin(named)
    except ValueError:
        return None


def _selection(payload: Mapping[str, object]) -> SourceSelection | None:
    named: object = payload.get("source_selection", SourceSelection.AUTO.value)
    if not isinstance(named, str):
        return None
    try:
        return SourceSelection(named)
    except ValueError:
        return None
