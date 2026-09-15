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
    NarrationTimeline,
    PlanPreview,
    ProductIntent,
    ProductKind,
    RebuildRequest,
    RunMode,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TaskKind,
    TranslationAction,
    WorkflowTarget,
    legal_narration_timelines,
    legal_products,
    preview_plan,
)
from anishift.application.events import sanitize_event_message
from anishift.cli.interactive.menu import (
    append_row as _append_row,
)
from anishift.cli.interactive.menu import (
    fit_entries as _fit_entries,
)
from anishift.cli.interactive.menu import (
    header as _header,
)
from anishift.cli.interactive.menu import (
    left_padding as _left_padding,
)
from anishift.cli.interactive.menu import (
    visible_window as _visible_window,
)
from anishift.cli.interactive.menu import with_footer
from anishift.cli.interactive.state import refusal_text
from anishift.cli.interactive.text_input import TextInput
from anishift.cli.resident import ResidentSession
from anishift.errors import AniShiftError

__all__ = ["ManualController", "ManualDraft", "ManualResult", "ManualRun", "default_draft", "materialize_intent"]

# ── Constants ─────────────────────────────────────────────────────────────────

_MENU_HINT: Final[str] = "↑↓ · Enter · Esc"
"""Keyboard hint used by single-choice menus."""

_MULTI_HINT: Final[str] = "↑↓ · Enter/Space zmień · Esc wróć"
"""Keyboard hint used by multi-choice menus."""

_GROUP_ACTIONS: Final[tuple[tuple[str, ProductKind | None], ...]] = (
    ("Podgląd", None),
    ("Dostosuj źródła i produkty", None),
    ("Regeneruj lektora", ProductKind.NARRATION_AUDIO),
    ("Regeneruj polskie napisy", ProductKind.FULL_PL),
    ("Dokończ poprzednią pracę", None),
    ("Anuluj", None),
)
"""Actions applied to the selected episode scope."""

_INPUT_HINT: Final[str] = "Enter zatwierdź · Esc wróć"
"""Keyboard hint used by external path input."""

_PRODUCT_LABELS: Final[tuple[tuple[ProductKind, str], ...]] = (
    (ProductKind.FULL_PL, "Polskie napisy"),
    (ProductKind.NARRATION_AUDIO, "Polski lektor"),
    (ProductKind.MKV, "MKV"),
    (ProductKind.MP4, "MP4"),
    (ProductKind.COVER_MP4, "Okładka MP4"),
)
"""Every public product the panel can name, in the order a screen offers the ones a group allows."""

_TIMELINE_LABELS: Final[tuple[tuple[NarrationTimeline, str], ...]] = (
    (NarrationTimeline.CONTINUOUS, "Jedno po drugim, z krótką pauzą"),
    (NarrationTimeline.SOURCE_TIMES, "W czasach z dokumentu"),
)
"""Every reading an audiobook can be recorded on, in the order a screen offers the ones a group allows."""

_PREVIEW_STAGES: Final[tuple[tuple[TaskKind, str], ...]] = (
    (TaskKind.TRANSLATE_SUBTITLES, "tłumaczenie"),
    (TaskKind.SYNTHESIZE_SPEECH, "synteza mowy"),
    (TaskKind.MIX_NARRATION, "miks audio"),
)
"""Potentially costly work made explicit before starting a preview."""

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
    TIMELINE = "timeline"
    SUBTITLES = "subtitles"
    AUDIO = "audio"
    VIDEO = "video"
    PREVIEW = "preview"
    INPUT = "input"
    BUSY = "busy"


class _CustomRow(StrEnum):
    PRODUCTS = "Wynik"
    SUBTITLES = "Napisy źródłowe"
    AUDIO = "Audio źródłowe"
    VIDEO = "Wideo źródłowe"
    TIMELINE = "Czytanie"
    DONE = "Gotowe"
    BACK = "Wróć"


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
    narration_timeline: NarrationTimeline = NarrationTimeline.CONTINUOUS
    target: WorkflowTarget | None = None


@dataclass(frozen=True, slots=True)
class ManualRun:
    """Carry the inspected workspace and accepted manual plan to shared execution."""

    workspace: InspectedWorkspace
    plan: ExecutionPlan | PlanPreview
    resident: ResidentSession | None = None


@dataclass(frozen=True, slots=True)
class _SourceChoice:
    label: str
    kind: _ChoiceKind
    policy: SubtitleSourcePolicy = SubtitleSourcePolicy.AUTO
    artifact_id: str | None = None
    track_id: int | None = None
    video_artifact_id: str | None = None
    audio_role: ExternalAudioRole | None = None


def default_draft(group: InspectedSourceGroup, preset: AutoPreset) -> ManualDraft:
    """Project the active automatic preset onto one group, keeping only the products its place allows."""
    draft = ManualDraft(
        group_id=group.group_id,
        products=preset.products,
        subtitle_source_policy=preset.subtitle_source_policy,
        translation_action=preset.translation_action,
        source_subtitle_language=preset.source_subtitle_language,
        subtitle_output_format=preset.subtitle_output_format,
        target=group.source.route.target,
    )
    allowed: frozenset[ProductKind] = legal_products(group)
    requested: frozenset[ProductKind] = preset.products.requested_products & allowed
    if requested == preset.products.requested_products:
        return draft
    return _with_products(draft, requested or _first_product(allowed))


def _first_product(allowed: frozenset[ProductKind]) -> frozenset[ProductKind]:
    """Return the one product a place offers first, because a draft can never request nothing at all."""
    return frozenset({next(product for product, _label in _PRODUCT_LABELS if product in allowed)})


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
        narration_timeline=draft.narration_timeline,
        target=draft.target,
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
        service: AppService | ResidentSession,
        workspace: InspectedWorkspace,
        preset: AutoPreset,
        invalidate: Callable[[], None],
    ) -> None:
        self._service: AppService | ResidentSession = service
        self._scope_actions: tuple[tuple[str, ProductKind | None], ...] = (
            _GROUP_ACTIONS if isinstance(service, ResidentSession) else (*_GROUP_ACTIONS[:-2], _GROUP_ACTIONS[-1])
        )
        self._workspace: InspectedWorkspace = workspace
        self._preset: AutoPreset = preset
        self._invalidate: Callable[[], None] = invalidate
        self._groups: dict[str, InspectedSourceGroup] = {group.group_id: group for group in workspace.groups}
        self._group_ids: tuple[str, ...] = tuple(self._groups)
        self._labels: dict[str, str] = _group_labels(workspace.groups, service.workspace_root)
        self._selected_groups: set[str] = set()
        self._drafts: dict[str, ManualDraft] = {
            group_id: default_draft(group, preset) for group_id, group in self._groups.items()
        }
        self._screen: _Screen = _Screen.GROUPS
        self._selected: int = 0
        self._edit_ids: tuple[str, ...] = ()
        self._edit_index: int = 0
        self._product_selection: set[ProductKind] = set()
        self._product_rows: tuple[tuple[ProductKind, str], ...] = ()
        self._source_choices: tuple[_SourceChoice, ...] = ()
        self._plan: ExecutionPlan | PlanPreview | None = None
        self._automatic_preview: bool = False
        self._ready_run: ManualRun | None = None
        self._input_kind: _InputKind | None = None
        self._input: TextInput = TextInput()
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
            elif self._screen is _Screen.TIMELINE:
                self._handle_timeline(key)
                result = ManualResult.STAY
            elif self._screen in {_Screen.SUBTITLES, _Screen.AUDIO, _Screen.VIDEO}:
                self._handle_source(key)
                result = ManualResult.STAY
            elif self._screen is _Screen.PREVIEW:
                result = self._handle_preview(key)
            else:
                result = ManualResult.STAY
        if result is ManualResult.BACK_HOME and isinstance(self._service, ResidentSession):
            self._service.close()
        return result

    def render(self, columns: int, rows: int) -> Text:
        """Render the current cached wizard state for one terminal geometry."""
        with self._lock:
            renderer: Callable[[int, int], Text] = {
                _Screen.GROUPS: self._render_groups,
                _Screen.GROUP_ACTION: self._render_group_action,
                _Screen.CUSTOM: self._render_custom,
                _Screen.PRODUCTS: self._render_products,
                _Screen.TIMELINE: self._render_timeline,
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
        if isinstance(self._service, ResidentSession):
            self._service.close()

    def take_ready_run(self) -> ManualRun | None:
        """Return and clear the run accepted by the preview."""
        with self._lock:
            ready: ManualRun | None = self._ready_run
            self._ready_run = None
        return ready

    def _handle_busy_key(self, key: str) -> ManualResult:
        if key not in {"escape", "interrupt"}:
            return ManualResult.STAY
        if isinstance(self._service, ResidentSession):
            self._generation += 1
            return ManualResult.BACK_HOME
        self._generation += 1
        token: EventCancellationToken | None = self._cancel
        self._cancel = None
        self._screen = _Screen.CUSTOM
        self._feedback = None
        if token is not None:
            token.cancel()
        return ManualResult.STAY

    def _handle_groups(self, key: str) -> ManualResult:
        row_count: int = len(self._group_ids) + len(self._scope_actions)
        if key == "up":
            self._move(-1, row_count)
        elif key == "down":
            self._move(1, row_count)
        elif key in {"space", "enter"} and self._selected < len(self._group_ids):
            group_id: str = self._group_ids[self._selected]
            self._select_scope(self._selected_groups ^ {group_id})
        elif key == "enter":
            return self._handle_scope_action(self._selected - len(self._group_ids))
        elif key == "a":
            self._select_scope(set() if self._selected_groups else set(self._group_ids))
        elif key == "home":
            self._selected = 0
        elif key == "end":
            self._selected = len(self._group_ids)
        return ManualResult.STAY

    def _select_scope(self, selected: set[str]) -> None:
        if isinstance(self._service, ResidentSession):
            try:
                self._service.reserve(tuple(group for group in self._group_ids if group in selected))
            except (AniShiftError, OSError) as problem:
                self._feedback = f"✗ Nie można zarezerwować odcinków · {refusal_text(problem)}"
                return
        self._selected_groups = selected
        self._feedback = None

    def _handle_scope_action(self, action: int) -> ManualResult:
        if action == len(self._scope_actions) - 1:
            return ManualResult.BACK_HOME
        if not self._selected_groups:
            self._feedback = "✗ Wybierz co najmniej jeden odcinek"
            return ManualResult.STAY
        self._edit_ids = tuple(group_id for group_id in self._group_ids if group_id in self._selected_groups)
        self._edit_index = 0
        self._automatic_preview = action != 1
        if isinstance(self._service, ResidentSession):
            self._start_remote_preview(action)
            return ManualResult.STAY
        if action == 1:
            self._open(_Screen.GROUP_ACTION)
            return ManualResult.STAY
        product: ProductKind | None = self._scope_actions[action][1]
        rebuild: RebuildRequest | None = None if product is None else RebuildRequest(frozenset({product}))
        try:
            self._plan = self._service.plan_auto(self._edit_ids, self._preset, rebuild=rebuild)
        except (AniShiftError, OSError, TypeError, ValueError) as problem:
            self._plan = None
            self._feedback = f"✗ Nie można zbudować planu · {refusal_text(problem)}"
        self._open(_Screen.PREVIEW, clear_feedback=False)
        return ManualResult.STAY

    def _start_remote_preview(self, action: int | None = None) -> None:
        service: AppService | ResidentSession = self._service
        if not isinstance(service, ResidentSession):
            return
        self._generation += 1
        generation: int = self._generation
        self._screen = _Screen.BUSY
        self._feedback = None
        group_ids: tuple[str, ...] = self._edit_ids
        intents: tuple[GroupIntent, ...] = tuple(materialize_intent(self._drafts[group_id]) for group_id in group_ids)

        def prepare() -> None:
            plan: PlanPreview | None = None
            problem: str | None = None
            try:
                service.reserve(group_ids)
                if action is None:
                    plan = service.plan_manual(intents)
                elif action == len(self._scope_actions) - 2:
                    plan = service.plan_resume(group_ids)
                elif action != 1:
                    product: ProductKind | None = self._scope_actions[action][1]
                    rebuild: RebuildRequest | None = None if product is None else RebuildRequest(frozenset({product}))
                    plan = service.plan_auto(group_ids, self._preset, rebuild=rebuild)
            except (AniShiftError, OSError, TypeError, ValueError) as error:
                problem = f"✗ Nie można przygotować odcinków · {refusal_text(error)}"
            with self._lock:
                if generation != self._generation:
                    return
                self._plan = plan
                self._feedback = problem
                target: _Screen = _Screen.GROUP_ACTION if action == 1 and problem is None else _Screen.PREVIEW
                self._open(target, clear_feedback=False)
            self._invalidate()

        threading.Thread(target=prepare, name="anishift-manual-preview", daemon=True).start()

    def _handle_group_action(self, key: str) -> ManualResult:
        if not self._navigate(key, 3):
            return ManualResult.STAY
        group_id: str = self._current_group_id()
        if self._selected == 0:
            self._drafts[group_id] = default_draft(self._current_group(), self._preset)
            self._advance_group()
        elif self._selected == 1:
            self._open(_Screen.CUSTOM)
        else:
            return self._previous_group()
        return ManualResult.STAY

    def _custom_rows(self) -> tuple[_CustomRow, ...]:
        rows: list[_CustomRow] = [_CustomRow.PRODUCTS, _CustomRow.SUBTITLES, _CustomRow.AUDIO]
        if self._has_video_choice():
            rows.append(_CustomRow.VIDEO)
        if len(self._timeline_rows()) > 1:
            rows.append(_CustomRow.TIMELINE)
        rows.extend((_CustomRow.DONE, _CustomRow.BACK))
        return tuple(rows)

    def _timeline_rows(self) -> tuple[tuple[NarrationTimeline, str], ...]:
        allowed: frozenset[NarrationTimeline] = legal_narration_timelines(self._current_group())
        return tuple(item for item in _TIMELINE_LABELS if item[0] in allowed)

    def _handle_custom(self, key: str) -> ManualResult:
        rows: tuple[_CustomRow, ...] = self._custom_rows()
        if not self._navigate(key, len(rows)):
            return ManualResult.STAY
        chosen: _CustomRow = rows[self._selected]
        if chosen is _CustomRow.PRODUCTS:
            draft: ManualDraft = self._drafts[self._current_group_id()]
            allowed: frozenset[ProductKind] = legal_products(self._current_group())
            self._product_rows = tuple(item for item in _PRODUCT_LABELS if item[0] in allowed)
            self._product_selection = set(draft.products.requested_products) & allowed
            self._open(_Screen.PRODUCTS)
        elif chosen is _CustomRow.SUBTITLES:
            self._source_choices = _subtitle_choices(self._current_group())
            self._open(_Screen.SUBTITLES)
            self._selected = self._source_selection_index()
        elif chosen is _CustomRow.AUDIO:
            self._source_choices = _audio_choices(self._current_group())
            self._open(_Screen.AUDIO)
            self._selected = self._source_selection_index()
        elif chosen is _CustomRow.VIDEO:
            self._source_choices = _video_choices(self._current_group())
            self._open(_Screen.VIDEO)
            self._selected = self._source_selection_index()
        elif chosen is _CustomRow.TIMELINE:
            self._open(_Screen.TIMELINE)
            self._selected = self._timeline_selection_index()
        elif chosen is _CustomRow.DONE:
            self._advance_group()
        else:
            self._open(_Screen.GROUP_ACTION)
        return ManualResult.STAY

    def _timeline_selection_index(self) -> int:
        current: NarrationTimeline = self._drafts[self._current_group_id()].narration_timeline
        rows: tuple[tuple[NarrationTimeline, str], ...] = self._timeline_rows()
        return next((index for index, (timeline, _label) in enumerate(rows) if timeline is current), 0)

    def _handle_timeline(self, key: str) -> None:
        rows: tuple[tuple[NarrationTimeline, str], ...] = self._timeline_rows()
        if not self._navigate(key, len(rows) + 1):
            return
        if self._selected == len(rows):
            self._open(_Screen.CUSTOM)
            return
        group_id: str = self._current_group_id()
        self._drafts[group_id] = replace(self._drafts[group_id], narration_timeline=rows[self._selected][0])
        self._open(_Screen.CUSTOM)

    def _handle_products(self, key: str) -> None:
        save_index: int = len(self._product_rows)
        back_index: int = save_index + 1
        if key == "up":
            self._move(-1, back_index + 1)
        elif key == "down":
            self._move(1, back_index + 1)
        elif key in {"space", "enter"} and self._selected < len(self._product_rows):
            product: ProductKind = self._product_rows[self._selected][0]
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
            self._input.reset()
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
        plan: ExecutionPlan | PlanPreview | None = self._plan
        option_count: int = 3 if plan is not None and plan.can_execute else 2
        if not self._navigate(key, option_count):
            return ManualResult.STAY
        if plan is not None and plan.can_execute and self._selected == 0:
            resident: ResidentSession | None = self._service if isinstance(self._service, ResidentSession) else None
            self._ready_run = ManualRun(self._workspace, plan, resident)
            return ManualResult.START_RUN
        back_index: int = 1 if plan is not None and plan.can_execute else 0
        if self._selected == back_index:
            self._edit_index = 0
            self._open(_Screen.GROUPS if self._automatic_preview else _Screen.GROUP_ACTION)
            return ManualResult.STAY
        return ManualResult.BACK_HOME

    def copy_selection(self) -> bool:
        """Copy the selected external-source path without leaving its editor."""
        with self._lock:
            return self._screen is _Screen.INPUT and self._input.handle("interrupt")

    def _handle_input_key(self, key: str) -> None:
        if self._input.handle(key):
            return
        if key in {"escape", "interrupt"}:
            self._open(_Screen.CUSTOM)
        elif key == "enter":
            raw_path: str = self._input.text.strip().strip('"')
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
                reason: str = refusal_text(problem) if problem is not None else "Nieznany błąd"
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
        if isinstance(self._service, ResidentSession):
            self._start_remote_preview()
            return
        try:
            intents: tuple[GroupIntent, ...] = tuple(
                materialize_intent(self._drafts[group_id]) for group_id in self._edit_ids
            )
            self._plan = self._service.plan_manual(intents)
        except (AniShiftError, OSError, TypeError, ValueError) as problem:
            self._plan = None
            self._feedback = f"✗ Nie można zbudować planu · {refusal_text(problem)}"
        self._open(_Screen.PREVIEW, clear_feedback=False)

    def _back(self) -> ManualResult:
        if self._screen is _Screen.GROUPS:
            return ManualResult.BACK_HOME
        if self._screen is _Screen.GROUP_ACTION:
            return self._previous_group()
        if self._screen in {
            _Screen.CUSTOM,
            _Screen.PRODUCTS,
            _Screen.TIMELINE,
            _Screen.SUBTITLES,
            _Screen.AUDIO,
            _Screen.VIDEO,
            _Screen.INPUT,
        }:
            target: _Screen = _Screen.GROUP_ACTION if self._screen is _Screen.CUSTOM else _Screen.CUSTOM
            self._open(target)
            return ManualResult.STAY
        self._edit_index = 0
        self._open(_Screen.GROUPS if self._automatic_preview else _Screen.GROUP_ACTION)
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
        if screen is _Screen.GROUPS and isinstance(self._service, ResidentSession):
            self._service.release()
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
        entries: tuple[str, ...] = (*labels, *(label for label, _ in self._scope_actions))
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        start, end = _visible_window(len(entries), self._selected, rows)
        content: Text = _header("WYBIERZ ODCINKI", columns, rows, end - start)
        left: int = _left_padding(columns, shown)
        for index in range(start, end):
            marker: str = (
                f"{'●' if self._group_ids[index] in self._selected_groups else '○'} " if index < len(labels) else "  "
            )
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, columns, rows, "↑↓ · Space wybierz · A wszystkie · End podgląd · Esc wróć")

    def _render_group_action(self, columns: int, rows: int) -> Text:
        entries: tuple[str, ...] = ("Użyj ustawień domyślnych", "Dostosuj ten odcinek", "Wróć")
        title: str = self._labels[self._current_group_id()]
        return self._render_menu(title, entries, columns, rows)

    def _render_custom(self, columns: int, rows: int) -> Text:
        entries: tuple[str, ...] = tuple(row.value for row in self._custom_rows())
        return self._render_menu(self._labels[self._current_group_id()], entries, columns, rows)

    def _render_timeline(self, columns: int, rows: int) -> Text:
        offered: tuple[tuple[NarrationTimeline, str], ...] = self._timeline_rows()
        current: int = self._timeline_selection_index()
        entries: tuple[str, ...] = (*(label for _timeline, label in offered), "Wróć")
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        content: Text = _header("CZYTANIE ODCINKA", columns, rows, len(entries))
        left: int = _left_padding(columns, shown)
        for index, _label in enumerate(entries):
            marker: str = f"{'●' if index == current else '○'} " if index < len(offered) else "  "
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, columns, rows, _MENU_HINT)

    def _render_products(self, columns: int, rows: int) -> Text:
        rows_offered: tuple[tuple[ProductKind, str], ...] = self._product_rows
        entries: tuple[str, ...] = (*(label for _product, label in rows_offered), "Zapisz", "Wróć")
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        content: Text = _header("WYNIK ODCINKA", columns, rows, len(entries))
        left: int = _left_padding(columns, shown)
        for index, _label in enumerate(entries):
            marker: str = (
                f"{'●' if rows_offered[index][0] in self._product_selection else '○'} "
                if index < len(rows_offered)
                else "  "
            )
            _append_row(content, left, shown[index], index == self._selected, marker)
        return self._finish(content, columns, rows, _MULTI_HINT)

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
        return self._finish(content, columns, rows, _MENU_HINT)

    def _render_preview(self, columns: int, rows: int) -> Text:
        plan: ExecutionPlan | PlanPreview | None = self._plan
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
        return self._finish(content, columns, rows, _MENU_HINT)

    def _preview_summary(self, plan: ExecutionPlan | PlanPreview | None) -> tuple[str, ...]:
        if plan is None:
            return ("Plan nie jest dostępny",)
        counts: Counter[ProductKind] = Counter(
            product for group in plan.groups for product in group.intent.products.requested_products
        )
        lines: list[str] = [f"{len(plan.groups)} odcinków"]
        lines.extend(f"{label}: {counts[product]}" for product, label in _PRODUCT_LABELS if counts[product])
        view: PlanPreview = plan if isinstance(plan, PlanPreview) else preview_plan(plan, "", "")
        for label, attribute in (("Zachowane", "preserved_products"), ("Do wykonania", "planned_products")):
            products: Counter[str] = Counter(
                product.value for group in view.groups for product in getattr(group, attribute)
            )
            shown: list[str] = [
                f"{name.lower()} ({products[kind.value]})" for kind, name in _PRODUCT_LABELS if products[kind.value]
            ]
            if shown:
                lines.append(f"{label}: {', '.join(shown)}")
        work: list[str] = [
            f"{label} ({len({task.group_id for task in view.tasks if task.kind is kind})})"
            for kind, label in _PREVIEW_STAGES
            if any(task.kind is kind for task in view.tasks)
        ]
        if work:
            lines.append(f"Wymagane: {', '.join(work)}")
        return tuple(lines)

    def _blocker_lines(self, plan: ExecutionPlan | PlanPreview | None) -> tuple[str, ...]:
        if plan is None:
            return ()
        return tuple(
            f"✗ {self._labels.get(problem.group_id or '', 'Plan')} · "
            f"{_PROBLEM_MESSAGES.get(problem.code, _safe(problem.message))}"
            for problem in plan.problems
            if problem.is_blocking
        )

    def _warning_lines(self, plan: ExecutionPlan | PlanPreview | None) -> tuple[str, ...]:
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
        left: int = max((columns - min(max(len(self._input.text) + 3, 24), columns)) // 2, 0)
        width: int = max(columns - left - 3, 1)
        content.append(f"{' ' * left}> ", style="white_bold")
        content.append_text(self._input.render(width))
        content.append("\n")
        return self._finish(content, columns, rows, _INPUT_HINT)

    def _render_busy(self, columns: int, rows: int) -> Text:
        spinner: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 10) % 10]
        line: str = f"{spinner} Sprawdzanie pliku…"
        content: Text = _header("TRYB RĘCZNY", columns, rows, 2)
        left: int = max((columns - len(line)) // 2, 0)
        content.append(f"{' ' * left}{line}", style="brand_accent")
        return self._finish(content, columns, rows, "Esc anuluj")

    def _render_menu(self, title: str, entries: tuple[str, ...], columns: int, rows: int) -> Text:
        shown: tuple[str, ...] = _fit_entries(entries, columns)
        start, end = _visible_window(len(entries), self._selected, rows)
        content: Text = _header(title, columns, rows, end - start)
        left: int = _left_padding(columns, shown)
        for index in range(start, end):
            _append_row(content, left, shown[index], index == self._selected)
        return self._finish(content, columns, rows, _MENU_HINT)

    def _finish(self, content: Text, columns: int, rows: int, hint: str) -> Text:
        if self._feedback is not None:
            content.append(self._feedback + "\n", style="error")
        return with_footer(content, (hint,), columns, rows)


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


def _safe(value: str) -> str:
    return (sanitize_event_message(value) or "").rstrip(".")
