"""Guided manual workflow built on the shared terminal renderer."""

from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Final

from rich.text import Text

from anishift.application import (
    AppService,
    Artifact,
    ArtifactKind,
    ArtifactState,
    AutoPreset,
    BurnSubtitleProduct,
    EventCancellationToken,
    ExecutionPlan,
    ExternalAudioRole,
    GroupIntent,
    InspectedSourceGroup,
    InspectedWorkspace,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.events import sanitize_event_message
from anishift.errors import AniShiftError

__all__ = ["ManualController", "ManualDraft", "ManualResult", "ManualRun", "default_draft", "materialize_intent"]

# ── Constants ─────────────────────────────────────────────────────────────────

_POINTER: Final[str] = "\u276f"
"""Marker placed before the active row."""

_MENU_HINT: Final[str] = "↑↓ · Enter · Esc"
"""Keyboard hint used by single-choice menus."""

_MULTI_HINT: Final[str] = "↑↓ · Enter/Space zmień · Esc wróć"
"""Keyboard hint used by multi-choice menus."""

_INPUT_HINT: Final[str] = "Enter zatwierdź · Esc wróć"
"""Keyboard hint used by external path input."""

_PRODUCTS: Final[tuple[tuple[ProductKind, str], ...]] = (
    (ProductKind.FULL_PL, "Polskie napisy"),
    (ProductKind.NARRATION_AUDIO, "Polski lektor"),
    (ProductKind.MKV, "MKV"),
    (ProductKind.MP4, "MP4"),
)
"""Public products selectable for one source group."""

_SUBTITLE_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {
        ArtifactKind.SOURCE_SUBTITLES,
        ArtifactKind.FULL_PL,
        ArtifactKind.SPOKEN_PL,
        ArtifactKind.DISPLAYED_PL,
    }
)
"""Ready artifact kinds usable as a manual subtitle source."""

_PROBLEM_MESSAGES: Final[dict[str, str]] = {
    "audio_duration_mismatch": "Wybrane audio ma inną długość niż wideo",
    "audio_selection_invalid": "Wybrane audio jest niedostępne lub nieprawidłowe",
    "audio_source_missing": "Brak zgodnego źródła audio",
    "source_conflict": "Grupa zawiera nierozwiązany konflikt źródeł",
    "subtitle_selection_invalid": "Wybrane napisy są niedostępne lub nieprawidłowe",
    "subtitle_selection_missing": "Wybrany rodzaj napisów wymaga wskazania źródła",
    "subtitle_source_missing": "Brak zgodnego źródła napisów",
    "video_missing": "Brak prawidłowego źródła wideo",
}
"""Polish presentation of common planner blockers."""


class ManualResult(StrEnum):
    """Signal whether the manual controller stays open or starts a run."""

    STAY = "stay"
    BACK_HOME = "back_home"
    START_RUN = "start_run"


class _Screen(StrEnum):
    GROUPS = "groups"
    GROUP_ACTION = "group_action"
    CUSTOM = "custom"
    PRODUCTS = "products"
    SUBTITLES = "subtitles"
    AUDIO = "audio"
    VIDEO = "video"
    PREVIEW = "preview"
    INPUT = "input"
    BUSY = "busy"


class _InputKind(StrEnum):
    SUBTITLE = "subtitle"
    SOURCE_AUDIO = "source_audio"
    NARRATION_MIX = "narration_mix"


class _ChoiceKind(StrEnum):
    AUTO = "auto"
    ARTIFACT = "artifact"
    TRACK = "track"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class ManualDraft:
    """Ephemeral choices used to materialize one immutable group intent."""

    group_id: str
    products: ProductIntent
    subtitle_source_policy: SubtitleSourcePolicy
    translation_action: TranslationAction
    preferred_video_artifact_id: str | None = None
    selected_subtitle_artifact_id: str | None = None
    selected_audio_artifact_id: str | None = None
    selected_audio_track_id: int | None = None
    selected_subtitle_track_id: int | None = None
    source_subtitle_language: str | None = None
    external_audio_role: ExternalAudioRole | None = None
    subtitle_output_format: SubtitleOutputFormat = SubtitleOutputFormat.PRESERVE


@dataclass(frozen=True, slots=True)
class ManualRun:
    """Carry the inspected workspace and accepted manual plan to shared execution."""

    workspace: InspectedWorkspace
    plan: ExecutionPlan


@dataclass(frozen=True, slots=True)
class _SourceChoice:
    label: str
    kind: _ChoiceKind
    policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    artifact_id: str | None = None
    track_id: int | None = None
    video_artifact_id: str | None = None
    audio_role: ExternalAudioRole | None = None


def default_draft(group_id: str, preset: AutoPreset) -> ManualDraft:
    """Project the active automatic preset into an independent manual draft."""
    return ManualDraft(
        group_id=group_id,
        products=preset.products,
        subtitle_source_policy=preset.subtitle_source_policy,
        translation_action=preset.translation_action,
        source_subtitle_language=preset.source_subtitle_language,
        subtitle_output_format=preset.subtitle_output_format,
    )


def materialize_intent(draft: ManualDraft) -> GroupIntent:
    """Materialize a validated manual group intent from one local draft."""
    return GroupIntent(
        group_id=draft.group_id,
        mode=RunMode.MANUAL,
        products=draft.products,
        subtitle_source_policy=draft.subtitle_source_policy,
        translation_action=draft.translation_action,
        preferred_video_artifact_id=draft.preferred_video_artifact_id,
        selected_subtitle_artifact_id=draft.selected_subtitle_artifact_id,
        selected_audio_artifact_id=draft.selected_audio_artifact_id,
        selected_audio_track_id=draft.selected_audio_track_id,
        selected_subtitle_track_id=draft.selected_subtitle_track_id,
        source_subtitle_language=draft.source_subtitle_language,
        external_audio_role=draft.external_audio_role,
        subtitle_output_format=draft.subtitle_output_format,
    )


def _with_products(draft: ManualDraft, requested: frozenset[ProductKind]) -> ManualDraft:
    current: ProductIntent = draft.products
    products = ProductIntent(
        requested_products=requested,
        burn_subtitle_product=(
            current.burn_subtitle_product if ProductKind.MP4 in requested else BurnSubtitleProduct.NONE
        ),
        mkv_tracks=current.mkv_tracks if ProductKind.MKV in requested else frozenset(),
        mp4_audio_source=current.mp4_audio_source if ProductKind.MP4 in requested else Mp4AudioSource.AUTO,
    )
    return replace(draft, products=products)


def _group_labels(groups: Sequence[InspectedSourceGroup], workspace_root: Path) -> dict[str, str]:
    counts: Counter[str] = Counter(group.source.stem.casefold() for group in groups)
    labels: dict[str, str] = {}
    for group in groups:
        label: str = group.source.stem
        if counts[group.source.stem.casefold()] > 1:
            label = f"{label} · {_directory_suffix(group.source.directory, workspace_root)}"
        if group.conflicts:
            label = f"{label} · konflikt źródeł"
        labels[group.group_id] = label
    return labels


def _directory_suffix(directory: Path, workspace_root: Path) -> str:
    try:
        relative: Path = directory.resolve().relative_to(workspace_root.resolve())
    except ValueError:
        return directory.name or "inny katalog"
    return relative.as_posix() if relative.parts else "katalog główny"


def _subtitle_choices(group: InspectedSourceGroup) -> tuple[_SourceChoice, ...]:
    choices: list[_SourceChoice] = [_SourceChoice("Automatycznie", _ChoiceKind.AUTO)]
    for artifact in group.artifacts:
        if artifact.kind not in _SUBTITLE_KINDS or artifact.state is not ArtifactState.READY:
            continue
        policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
        if artifact.kind is ArtifactKind.SOURCE_SUBTITLES:
            policy = (
                SubtitleSourcePolicy.SIDECAR if _is_exact_sidecar(group, artifact) else SubtitleSourcePolicy.EXTERNAL
            )
        elif artifact.kind is ArtifactKind.FULL_PL:
            policy = SubtitleSourcePolicy.READY_POLISH
        choices.append(
            _SourceChoice(
                _format_artifact_label(artifact),
                _ChoiceKind.ARTIFACT,
                policy=policy,
                artifact_id=artifact.artifact_id,
            )
        )
    for video_id, catalog in group.media_catalogs.items():
        for track in catalog.tracks:
            if track.kind.value != "subtitles" or track.subtitle_format not in {"ass", "srt"}:
                continue
            choices.append(
                _SourceChoice(
                    _format_track_label(track.track_id, track.language, track.codec_id, track.name),
                    _ChoiceKind.TRACK,
                    policy=SubtitleSourcePolicy.EMBEDDED,
                    track_id=track.track_id,
                    video_artifact_id=video_id,
                )
            )
    choices.extend(
        (
            _SourceChoice("Plik zewnętrzny…", _ChoiceKind.EXTERNAL, policy=SubtitleSourcePolicy.EXTERNAL),
            _SourceChoice("Brak", _ChoiceKind.AUTO, policy=SubtitleSourcePolicy.NONE),
        )
    )
    return tuple(choices)


def _audio_choices(group: InspectedSourceGroup) -> tuple[_SourceChoice, ...]:
    choices: list[_SourceChoice] = [_SourceChoice("Automatycznie", _ChoiceKind.AUTO)]
    for artifact in group.artifacts:
        if artifact.state is not ArtifactState.READY:
            continue
        role: ExternalAudioRole | None = None
        if artifact.kind is ArtifactKind.SOURCE_AUDIO:
            role = ExternalAudioRole.SOURCE_AUDIO
        elif artifact.kind is ArtifactKind.NARRATION_AUDIO:
            role = ExternalAudioRole.NARRATION_MIX
        else:
            continue
        choices.append(
            _SourceChoice(
                _format_artifact_label(artifact),
                _ChoiceKind.ARTIFACT,
                artifact_id=artifact.artifact_id,
                audio_role=role,
            )
        )
    for video_id, catalog in group.media_catalogs.items():
        for track in catalog.tracks:
            if track.kind.value != "audio":
                continue
            choices.append(
                _SourceChoice(
                    _format_track_label(track.track_id, track.language, track.codec_id, track.name),
                    _ChoiceKind.TRACK,
                    track_id=track.track_id,
                    video_artifact_id=video_id,
                )
            )
    choices.extend(
        (
            _SourceChoice(
                "Plik zewnętrzny jako źródło…",
                _ChoiceKind.EXTERNAL,
                audio_role=ExternalAudioRole.SOURCE_AUDIO,
            ),
            _SourceChoice(
                "Gotowy zewnętrzny lektor lub mix…",
                _ChoiceKind.EXTERNAL,
                audio_role=ExternalAudioRole.NARRATION_MIX,
            ),
        )
    )
    return tuple(choices)


def _video_choices(group: InspectedSourceGroup) -> tuple[_SourceChoice, ...]:
    choices: list[_SourceChoice] = [_SourceChoice("Automatycznie", _ChoiceKind.AUTO)]
    for artifact in group.artifacts:
        if artifact.kind not in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}:
            continue
        if artifact.state is ArtifactState.READY:
            choices.append(
                _SourceChoice(
                    _format_artifact_label(artifact),
                    _ChoiceKind.ARTIFACT,
                    artifact_id=artifact.artifact_id,
                )
            )
    return tuple(choices)


def _format_track_label(track_id: int, language: str | None, codec: str, name: str | None) -> str:
    parts: list[str] = [f"#{track_id}"]
    parts.extend(value for value in (language, codec, name) if value)
    return " · ".join(parts)


def _format_artifact_label(artifact: Artifact) -> str:
    filename: str = artifact.path.name if artifact.path is not None else artifact.kind.value
    parts: list[str] = [filename]
    parts.extend(value for value in (artifact.language, artifact.subtitle_format, artifact.audio_codec) if value)
    return " · ".join(parts)


def _is_exact_sidecar(group: InspectedSourceGroup, artifact: Artifact) -> bool:
    if artifact.path is None or artifact.subtitle_format not in {"ass", "srt"}:
        return False
    expected: Path = group.source.directory / f"{group.source.stem}.{artifact.subtitle_format}"
    return artifact.path.resolve() == expected.resolve()


class ManualController:
    """Own one ephemeral manual wizard while AppService owns all product state."""

    def __init__(
        self,
        service: AppService,
        workspace: InspectedWorkspace,
        preset: AutoPreset,
        invalidate: Callable[[], None],
    ) -> None:
        self._service: AppService = service
        self._workspace: InspectedWorkspace = workspace
        self._preset: AutoPreset = preset
        self._invalidate: Callable[[], None] = invalidate
        self._groups: dict[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
        self._group_ids: tuple[str, ...] = tuple(self._groups)
        self._labels: dict[str, str] = _group_labels(workspace.groups, service.workspace_root)
        self._selected_groups: set[str] = {group.group_id for group in workspace.groups if not group.conflicts}
        self._drafts: dict[str, ManualDraft] = {
            group_id: default_draft(group_id, preset) for group_id in self._group_ids
        }
        self._screen: _Screen = _Screen.GROUPS
        self._selected: int = 0
        self._edit_ids: tuple[str, ...] = ()
        self._edit_index: int = 0
        self._product_selection: set[ProductKind] = set()
        self._source_choices: tuple[_SourceChoice, ...] = ()
        self._plan: ExecutionPlan | None = None
        self._ready_run: ManualRun | None = None
        self._input_kind: _InputKind | None = None
        self._input_buffer: str = ""
        self._feedback: str | None = None
        self._cancel: EventCancellationToken | None = None
        self._generation: int = 0
        self._lock: threading.Lock = threading.Lock()

    def handle_key(self, key: str) -> ManualResult:
        """Apply one normalized terminal key without render-time I/O."""
        with self._lock:
            if self._screen is _Screen.BUSY:
                result: ManualResult = self._handle_busy_key(key)
            elif self._screen is _Screen.INPUT:
                self._handle_input_key(key)
                result = ManualResult.STAY
            elif key in {"escape", "interrupt"}:
                result = self._back()
            elif self._screen is _Screen.GROUPS:
                result = self._handle_groups(key)
            elif self._screen is _Screen.GROUP_ACTION:
                result = self._handle_group_action(key)
            elif self._screen is _Screen.CUSTOM:
                result = self._handle_custom(key)
            elif self._screen is _Screen.PRODUCTS:
                self._handle_products(key)
                result = ManualResult.STAY
            elif self._screen in {_Screen.SUBTITLES, _Screen.AUDIO, _Screen.VIDEO}:
                self._handle_source(key)
                result = ManualResult.STAY
            elif self._screen is _Screen.PREVIEW:
                result = self._handle_preview(key)
            else:
                result = ManualResult.STAY
        return result

    def render(self, columns: int, rows: int) -> Text:
        """Render the current cached wizard state for one terminal geometry."""
        with self._lock:
            renderer: Callable[[int, int], Text] = {
                _Screen.GROUPS: self._render_groups,
                _Screen.GROUP_ACTION: self._render_group_action,
                _Screen.CUSTOM: self._render_custom,
                _Screen.PRODUCTS: self._render_products,
                _Screen.SUBTITLES: self._render_sources,
                _Screen.AUDIO: self._render_sources,
                _Screen.VIDEO: self._render_sources,
                _Screen.PREVIEW: self._render_preview,
                _Screen.INPUT: self._render_input,
                _Screen.BUSY: self._render_busy,
            }[self._screen]
            rendered: Text = renderer(columns, rows)
        return rendered

    def cancel(self) -> None:
        """Cancel an active external registration and invalidate late results."""
        with self._lock:
            self._generation += 1
            token: EventCancellationToken | None = self._cancel
            self._cancel = None
        if token is not None:
            token.cancel()

    def take_ready_run(self) -> ManualRun | None:
        """Return and clear the run accepted by the preview."""
        with self._lock:
            ready: ManualRun | None = self._ready_run
            self._ready_run = None
        return ready

    def _handle_busy_key(self, key: str) -> ManualResult:
        if key not in {"escape", "interrupt"}:
            return ManualResult.STAY
        self._generation += 1
        token: EventCancellationToken | None = self._cancel
        self._cancel = None
        self._screen = _Screen.CUSTOM
        self._feedback = None
        if token is not None:
            token.cancel()
        return ManualResult.STAY

    def _handle_groups(self, key: str) -> ManualResult:
        row_count: int = len(self._group_ids) + 2
        if key == "up":
            self._move(-1, row_count)
        elif key == "down":
            self._move(1, row_count)
        elif key in {"space", "enter"} and self._selected < len(self._group_ids):
            group_id: str = self._group_ids[self._selected]
            if group_id in self._selected_groups:
                self._selected_groups.remove(group_id)
            else:
                self._selected_groups.add(group_id)
            self._feedback = None
        elif key == "enter" and self._selected == len(self._group_ids):
            if not self._selected_groups:
                self._feedback = "✗ Wybierz co najmniej jeden odcinek"
            else:
                self._edit_ids = tuple(group_id for group_id in self._group_ids if group_id in self._selected_groups)
                self._edit_index = 0
                self._open(_Screen.GROUP_ACTION)
        elif key == "enter":
            return ManualResult.BACK_HOME
        return ManualResult.STAY

    def _handle_group_action(self, key: str) -> ManualResult:
        if not self._navigate(key, 3):
            return ManualResult.STAY
        group_id: str = self._current_group_id()
        if self._selected == 0:
            self._drafts[group_id] = default_draft(group_id, self._preset)
            self._advance_group()
        elif self._selected == 1:
            self._open(_Screen.CUSTOM)
        else:
            return self._previous_group()
        return ManualResult.STAY

    def _handle_custom(self, key: str) -> ManualResult:
        item_count: int = 6 if self._has_video_choice() else 5
        subtitle_index: int = 1
        audio_index: int = 2
        video_index: int = 3
        if not self._navigate(key, item_count):
            return ManualResult.STAY
        if self._selected == 0:
            draft: ManualDraft = self._drafts[self._current_group_id()]
            self._product_selection = set(draft.products.requested_products)
            self._open(_Screen.PRODUCTS)
        elif self._selected == subtitle_index:
            self._source_choices = _subtitle_choices(self._current_group())
            self._open(_Screen.SUBTITLES)
            self._selected = self._source_selection_index()
        elif self._selected == audio_index:
            self._source_choices = _audio_choices(self._current_group())
            self._open(_Screen.AUDIO)
            self._selected = self._source_selection_index()
        elif self._has_video_choice() and self._selected == video_index:
            self._source_choices = _video_choices(self._current_group())
            self._open(_Screen.VIDEO)
            self._selected = self._source_selection_index()
        elif self._selected == item_count - 2:
            self._advance_group()
        else:
            self._open(_Screen.GROUP_ACTION)
        return ManualResult.STAY

    def _handle_products(self, key: str) -> None:
        save_index: int = len(_PRODUCTS)
        back_index: int = save_index + 1
        if key == "up":
            self._move(-1, back_index + 1)
        elif key == "down":
            self._move(1, back_index + 1)
        elif key in {"space", "enter"} and self._selected < len(_PRODUCTS):
            product: ProductKind = _PRODUCTS[self._selected][0]
            if product in self._product_selection:
                self._product_selection.remove(product)
            else:
                self._product_selection.add(product)
            self._feedback = None
        elif key == "enter" and self._selected == save_index:
            if not self._product_selection:
                self._feedback = "✗ Wybierz co najmniej jeden wynik"
                return
            group_id: str = self._current_group_id()
            self._drafts[group_id] = _with_products(
                self._drafts[group_id],
                frozenset(self._product_selection),
            )
            self._open(_Screen.CUSTOM)
        elif key == "enter" and self._selected == back_index:
            self._open(_Screen.CUSTOM)

    def _handle_source(self, key: str) -> None:
        if key == "up":
            self._move(-1, len(self._source_choices))
            return
        if key == "down":
            self._move(1, len(self._source_choices))
            return
        if key != "enter" or not self._source_choices:
            return
        choice: _SourceChoice = self._source_choices[self._selected]
        if choice.kind is _ChoiceKind.EXTERNAL:
            self._input_kind = (
                _InputKind.SUBTITLE
                if self._screen is _Screen.SUBTITLES
                else _InputKind.SOURCE_AUDIO
                if choice.audio_role is ExternalAudioRole.SOURCE_AUDIO
                else _InputKind.NARRATION_MIX
            )
            self._input_buffer = ""
            self._open(_Screen.INPUT)
            return
        group_id: str = self._current_group_id()
        draft: ManualDraft = self._drafts[group_id]
        if self._screen is _Screen.SUBTITLES:
            draft = self._apply_subtitle_choice(draft, choice)
        elif self._screen is _Screen.AUDIO:
            draft = self._apply_audio_choice(draft, choice)
        else:
            draft = self._apply_video_choice(draft, choice.artifact_id)
        self._drafts[group_id] = draft
        self._open(_Screen.CUSTOM)

    def _handle_preview(self, key: str) -> ManualResult:
        plan: ExecutionPlan | None = self._plan
        option_count: int = 3 if plan is not None and plan.can_execute else 2
        if not self._navigate(key, option_count):
            return ManualResult.STAY
        if plan is not None and plan.can_execute and self._selected == 0:
            self._ready_run = ManualRun(self._workspace, plan)
            return ManualResult.START_RUN
        back_index: int = 1 if plan is not None and plan.can_execute else 0
        if self._selected == back_index:
            self._edit_index = 0
            self._open(_Screen.GROUP_ACTION)
            return ManualResult.STAY
        return ManualResult.BACK_HOME

    def _handle_input_key(self, key: str) -> None:
        if key in {"escape", "interrupt"}:
            self._open(_Screen.CUSTOM)
        elif key == "backspace":
            self._input_buffer = self._input_buffer[:-1]
        elif key == "space":
            self._input_buffer += " "
        elif key.startswith("text:"):
            self._input_buffer += key.removeprefix("text:")
        elif key == "enter":
            raw_path: str = self._input_buffer.strip().strip('"')
            if not raw_path:
                self._feedback = "✗ Podaj ścieżkę pliku"
                return
            self._start_registration(Path(raw_path).expanduser())

    def _apply_subtitle_choice(self, draft: ManualDraft, choice: _SourceChoice) -> ManualDraft:
        switched_video: bool = (
            choice.video_artifact_id is not None and choice.video_artifact_id != draft.preferred_video_artifact_id
        )
        return replace(
            draft,
            subtitle_source_policy=choice.policy,
            selected_subtitle_artifact_id=choice.artifact_id,
            selected_subtitle_track_id=choice.track_id,
            selected_audio_track_id=None if switched_video else draft.selected_audio_track_id,
            preferred_video_artifact_id=choice.video_artifact_id or draft.preferred_video_artifact_id,
        )

    def _apply_audio_choice(self, draft: ManualDraft, choice: _SourceChoice) -> ManualDraft:
        switched_video: bool = (
            choice.video_artifact_id is not None and choice.video_artifact_id != draft.preferred_video_artifact_id
        )
        return replace(
            draft,
            selected_audio_artifact_id=choice.artifact_id,
            selected_audio_track_id=choice.track_id,
            selected_subtitle_track_id=None if switched_video else draft.selected_subtitle_track_id,
            external_audio_role=choice.audio_role,
            preferred_video_artifact_id=choice.video_artifact_id or draft.preferred_video_artifact_id,
        )

    def _apply_video_choice(self, draft: ManualDraft, video_artifact_id: str | None) -> ManualDraft:
        if video_artifact_id == draft.preferred_video_artifact_id:
            return draft
        return replace(
            draft,
            preferred_video_artifact_id=video_artifact_id,
            selected_audio_track_id=None,
            selected_subtitle_track_id=None,
        )

    def _start_registration(self, path: Path) -> None:
        self._generation += 1
        generation: int = self._generation
        token = EventCancellationToken()
        self._cancel = token
        self._screen = _Screen.BUSY
        self._feedback = None
        input_kind: _InputKind = self._input_kind or _InputKind.SUBTITLE
        group_id: str = self._current_group_id()
        worker = threading.Thread(
            target=self._register_external,
            args=(group_id, path, input_kind, token, generation),
            name="anishift-manual-register",
            daemon=True,
        )
        worker.start()

    def _register_external(
        self,
        group_id: str,
        path: Path,
        input_kind: _InputKind,
        token: EventCancellationToken,
        generation: int,
    ) -> None:
        try:
            if input_kind is _InputKind.SUBTITLE:
                updated: InspectedSourceGroup = self._service.register_external_subtitle(
                    group_id,
                    path,
                    None,
                    cancel=token,
                )
                role: ExternalAudioRole | None = None
            else:
                role = (
                    ExternalAudioRole.SOURCE_AUDIO
                    if input_kind is _InputKind.SOURCE_AUDIO
                    else ExternalAudioRole.NARRATION_MIX
                )
                updated = self._service.register_external_audio(group_id, path, role, cancel=token)
            artifact: Artifact = updated.artifacts[-1]
        except (AniShiftError, OSError, TypeError, ValueError) as problem:
            self._finish_registration(generation, problem=problem)
            return
        self._finish_registration(generation, updated=updated, artifact=artifact, role=role)

    def _finish_registration(
        self,
        generation: int,
        *,
        updated: InspectedSourceGroup | None = None,
        artifact: Artifact | None = None,
        role: ExternalAudioRole | None = None,
        problem: AniShiftError | OSError | TypeError | ValueError | None = None,
    ) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._cancel = None
            self._screen = _Screen.CUSTOM
            if problem is not None or updated is None or artifact is None:
                reason: str = _safe(str(problem)) if problem is not None else "Nieznany błąd"
                self._feedback = f"✗ Nie udało się dodać pliku · {reason}"
            else:
                self._replace_group(updated)
                draft: ManualDraft = self._drafts[updated.group_id]
                if artifact.kind is ArtifactKind.SOURCE_SUBTITLES:
                    draft = replace(
                        draft,
                        subtitle_source_policy=SubtitleSourcePolicy.EXTERNAL,
                        selected_subtitle_artifact_id=artifact.artifact_id,
                        selected_subtitle_track_id=None,
                    )
                else:
                    draft = replace(
                        draft,
                        selected_audio_artifact_id=artifact.artifact_id,
                        selected_audio_track_id=None,
                        external_audio_role=role,
                    )
                self._drafts[updated.group_id] = draft
                self._feedback = None
        self._invalidate()

    def _replace_group(self, updated: InspectedSourceGroup) -> None:
        self._groups[updated.group_id] = updated
        groups: tuple[InspectedSourceGroup, ...] = tuple(self._groups[group_id] for group_id in self._group_ids)
        self._workspace = replace(self._workspace, groups=groups)

    def _advance_group(self) -> None:
        self._edit_index += 1
        if self._edit_index < len(self._edit_ids):
            self._open(_Screen.GROUP_ACTION)
            return
        self._build_preview()

    def _previous_group(self) -> ManualResult:
        if self._edit_index == 0:
            self._open(_Screen.GROUPS)
            return ManualResult.STAY
        self._edit_index -= 1
        self._open(_Screen.GROUP_ACTION)
        return ManualResult.STAY

    def _build_preview(self) -> None:
        try:
            intents: tuple[GroupIntent, ...] = tuple(
                materialize_intent(self._drafts[group_id]) for group_id in self._edit_ids
            )
            self._plan = self._service.plan_manual(intents)
        except (AniShiftError, OSError, TypeError, ValueError) as problem:
            self._plan = None
            self._feedback = f"✗ Nie można zbudować planu · {_safe(str(problem))}"
        self._open(_Screen.PREVIEW, clear_feedback=False)

    def _back(self) -> ManualResult:
        if self._screen is _Screen.GROUPS:
            return ManualResult.BACK_HOME
        if self._screen is _Screen.GROUP_ACTION:
            return self._previous_group()
        if self._screen in {
            _Screen.CUSTOM,
            _Screen.PRODUCTS,
            _Screen.SUBTITLES,
            _Screen.AUDIO,
            _Screen.VIDEO,
            _Screen.INPUT,
        }:
            target: _Screen = _Screen.GROUP_ACTION if self._screen is _Screen.CUSTOM else _Screen.CUSTOM
            self._open(target)
            return ManualResult.STAY
        self._edit_index = 0
        self._open(_Screen.GROUP_ACTION)
        return ManualResult.STAY

    def _navigate(self, key: str, count: int) -> bool:
        if key == "up":
            self._move(-1, count)
        elif key == "down":
            self._move(1, count)
        return key == "enter"

    def _move(self, delta: int, count: int) -> None:
        if count:
            self._selected = (self._selected + delta) % count
        self._feedback = None

    def _open(self, screen: _Screen, *, clear_feedback: bool = True) -> None:
        self._screen = screen
        self._selected = 0
        if clear_feedback:
            self._feedback = None

    def _current_group_id(self) -> str:
        return self._edit_ids[self._edit_index]

    def _current_group(self) -> InspectedSourceGroup:
        return self._groups[self._current_group_id()]

    def _has_video_choice(self) -> bool:
        videos: tuple[Artifact, ...] = tuple(
            artifact
            for artifact in self._current_group().artifacts
            if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}
            and artifact.state is ArtifactState.READY
        )
        return len(videos) > 1

    def _source_selection_index(self) -> int:
        draft: ManualDraft = self._drafts[self._current_group_id()]
        for index, choice in enumerate(self._source_choices):
            if self._screen is _Screen.SUBTITLES:
                selected: bool = (
                    choice.artifact_id == draft.selected_subtitle_artifact_id
                    and choice.track_id == draft.selected_subtitle_track_id
                    and choice.policy is draft.subtitle_source_policy
                )
            elif self._screen is _Screen.AUDIO:
                selected = (
                    choice.artifact_id == draft.selected_audio_artifact_id
                    and choice.track_id == draft.selected_audio_track_id
                    and choice.audio_role is draft.external_audio_role
                )
            else:
                selected = choice.artifact_id == draft.preferred_video_artifact_id
            if selected and choice.kind is not _ChoiceKind.EXTERNAL:
                return index
        return 0

    def _render_groups(self, columns: int, rows: int) -> Text:
        labels: tuple[str, ...] = tuple(self._labels[group_id] for group_id in self._group_ids)
        entries: tuple[str, ...] = (*labels, "Dalej", "Anuluj")
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        start, end = _visible_window(len(entries), self._selected, rows)
        content: Text = _header("WYBIERZ ODCINKI", columns, rows, end - start)
        left: int = _left_padding(columns, shown)
        for index in range(start, end):
            marker: str = (
                f"{'●' if self._group_ids[index] in self._selected_groups else '○'} " if index < len(labels) else "  "
            )
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, left, _MULTI_HINT)

    def _render_group_action(self, columns: int, rows: int) -> Text:
        entries: tuple[str, ...] = ("Użyj ustawień domyślnych", "Dostosuj ten odcinek", "Wróć")
        title: str = self._labels[self._current_group_id()]
        return self._render_menu(title, entries, columns, rows)

    def _render_custom(self, columns: int, rows: int) -> Text:
        entries: list[str] = ["Wynik", "Napisy źródłowe", "Audio źródłowe"]
        if self._has_video_choice():
            entries.append("Wideo źródłowe")
        entries.extend(("Gotowe", "Wróć"))
        return self._render_menu(self._labels[self._current_group_id()], tuple(entries), columns, rows)

    def _render_products(self, columns: int, rows: int) -> Text:
        entries: tuple[str, ...] = (*(label for _product, label in _PRODUCTS), "Zapisz", "Wróć")
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        content: Text = _header("WYNIK ODCINKA", columns, rows, len(entries))
        left: int = _left_padding(columns, shown)
        for index, _label in enumerate(entries):
            marker: str = (
                f"{'●' if _PRODUCTS[index][0] in self._product_selection else '○'} " if index < len(_PRODUCTS) else "  "
            )
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, left, _MULTI_HINT)

    def _render_sources(self, columns: int, rows: int) -> Text:
        title: str = {
            _Screen.SUBTITLES: "NAPISY ŹRÓDŁOWE",
            _Screen.AUDIO: "AUDIO ŹRÓDŁOWE",
            _Screen.VIDEO: "WIDEO ŹRÓDŁOWE",
        }[self._screen]
        entries: tuple[str, ...] = tuple(choice.label for choice in self._source_choices)
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        start, end = _visible_window(len(entries), self._selected, rows)
        content: Text = _header(title, columns, rows, end - start)
        left: int = _left_padding(columns, shown)
        current: int = self._source_selection_index()
        for index in range(start, end):
            marker: str = (
                "  "
                if self._source_choices[index].kind is _ChoiceKind.EXTERNAL
                else f"{'●' if index == current else '○'} "
            )
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, left, _MENU_HINT)

    def _render_preview(self, columns: int, rows: int) -> Text:
        plan: ExecutionPlan | None = self._plan
        summary: tuple[str, ...] = _fit_entries(self._preview_summary(plan), columns)
        blockers: tuple[str, ...] = _fit_entries(self._blocker_lines(plan), columns)
        warnings: tuple[str, ...] = _fit_entries(self._warning_lines(plan), columns)
        entries: tuple[str, ...] = (
            ("Uruchom", "Wróć do zmian", "Anuluj")
            if plan is not None and plan.can_execute
            else ("Wróć do zmian", "Anuluj")
        )
        problem_budget: int = max(rows - len(summary) - len(entries) - 8, 0)
        blockers, warnings = _limit_problems(blockers, warnings, problem_budget)
        content_rows: int = len(summary) + len(blockers) + len(warnings) + len(entries) + 2
        content: Text = _header("TRYB RĘCZNY", columns, rows, content_rows)
        left: int = _left_padding(columns, (*summary, *blockers, *warnings, *entries))
        for line in summary:
            content.append(f"{' ' * left}{line}\n", style="white_bold")
        for line in blockers:
            content.append(f"{' ' * left}{line}\n", style="error")
        for line in warnings:
            content.append(f"{' ' * left}{line}\n", style="warning")
        content.append("\n")
        for index, label in enumerate(entries):
            _append_row(content, left, label, index == self._selected)
        return self._finish(content, left, _MENU_HINT)

    def _preview_summary(self, plan: ExecutionPlan | None) -> tuple[str, ...]:
        if plan is None:
            return ("Plan nie jest dostępny",)
        counts: Counter[ProductKind] = Counter(
            product for group in plan.groups for product in group.intent.products.requested_products
        )
        lines: list[str] = [f"{len(plan.groups)} odcinków"]
        lines.extend(f"{label}: {counts[product]}" for product, label in _PRODUCTS if counts[product])
        return tuple(lines)

    def _blocker_lines(self, plan: ExecutionPlan | None) -> tuple[str, ...]:
        if plan is None:
            return ()
        return tuple(
            f"✗ {self._labels.get(problem.group_id or '', 'Plan')} · "
            f"{_PROBLEM_MESSAGES.get(problem.code, _safe(problem.message))}"
            for problem in plan.problems
            if problem.is_blocking
        )

    def _warning_lines(self, plan: ExecutionPlan | None) -> tuple[str, ...]:
        if plan is None:
            return ()
        return tuple(
            f"! {self._labels.get(problem.group_id or '', 'Plan')} · {_safe(problem.message)}"
            for problem in plan.problems
            if not problem.is_blocking
        )

    def _render_input(self, columns: int, rows: int) -> Text:
        title: str = "ZEWNĘTRZNE NAPISY" if self._input_kind is _InputKind.SUBTITLE else "ZEWNĘTRZNE AUDIO"
        content: Text = _header(title, columns, rows, 3)
        left: int = max((columns - min(max(len(self._input_buffer) + 3, 24), columns)) // 2, 0)
        width: int = max(columns - left - 3, 1)
        shown: str = self._input_buffer[-width:]
        content.append(f"{' ' * left}> {shown}▌", style="white_bold")
        content.append("\n")
        return self._finish(content, left, _INPUT_HINT)

    def _render_busy(self, columns: int, rows: int) -> Text:
        spinner: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 10) % 10]
        line: str = f"{spinner} Sprawdzanie pliku…"
        content: Text = _header("TRYB RĘCZNY", columns, rows, 2)
        left: int = max((columns - len(line)) // 2, 0)
        content.append(f"{' ' * left}{line}", style="purple_bold")
        return self._finish(content, left, "Esc anuluj")

    def _render_menu(self, title: str, entries: tuple[str, ...], columns: int, rows: int) -> Text:
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        start, end = _visible_window(len(entries), self._selected, rows)
        content: Text = _header(title, columns, rows, end - start)
        left: int = _left_padding(columns, shown)
        for index in range(start, end):
            _append_row(content, left, shown[index], index == self._selected)
        return self._finish(content, left, _MENU_HINT)

    def _finish(self, content: Text, left: int, hint: str) -> Text:
        if self._feedback is not None:
            content.append(f"{' ' * left}{self._feedback}\n", style="error")
        content.append(f"{' ' * left}{hint}", style="gray")
        return content


def _header(title: str, columns: int, rows: int, content_rows: int) -> Text:
    top: int = max((rows - content_rows - 5) // 2, 0)
    shown: str = _truncate_right(title, max(columns - 2, 1))
    left: int = max((columns - len(shown)) // 2, 0)
    content = Text("\n" * top)
    content.append(f"{' ' * left}{shown}\n\n", style="white_bold")
    return content


def _append_row(content: Text, left: int, label: str, active: bool, marker: str = "  ") -> None:
    content.append(" " * left)
    content.append(f"{_POINTER} " if active else "  ", style="purple_bold" if active else "white_bold")
    content.append(marker, style="purple_bold" if active else "white_bold")
    content.append(label, style="purple_bold" if active else "white_bold")
    content.append("\n")


def _left_padding(columns: int, entries: Sequence[str]) -> int:
    width: int = max((len(entry) for entry in entries), default=1) + 4
    return max((columns - min(width, columns)) // 2, 0)


def _fit_entries(entries: Sequence[str], columns: int) -> tuple[str, ...]:
    width: int = max(columns - 8, 1)
    return tuple(_truncate_right(entry, width) for entry in entries)


def _limit_problems(
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    budget: int,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    total: int = len(blockers) + len(warnings)
    if total <= budget:
        return blockers, warnings
    if budget < 1:
        return (), ()
    visible_blockers: tuple[str, ...] = blockers[:budget]
    remaining: int = budget - len(visible_blockers)
    visible_warnings: tuple[str, ...] = warnings[:remaining]
    hidden: int = total - len(visible_blockers) - len(visible_warnings)
    marker: str = f"… jeszcze {hidden}"
    if visible_warnings:
        return visible_blockers, (*visible_warnings[:-1], marker)
    return (*visible_blockers[:-1], marker), ()


def _truncate_right(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _visible_window(count: int, selected: int, rows: int) -> tuple[int, int]:
    budget: int = max(rows - 7, 1)
    if count <= budget:
        return 0, count
    start: int = min(max(selected - budget // 2, 0), count - budget)
    return start, start + budget


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")
