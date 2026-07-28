"""Full-screen ``/settings`` panel — arrow-key editing with auto-save.

Arrow keys only (no WASD): ``↑``/``↓`` pick a field, ``←``/``→`` or ``Enter``
cycle its value, ``Esc``/``q`` returns to the shell. Each change is persisted
immediately. The translation-engine list is derived from the registry; the TTS
engine and voice lists stay static placeholders until stage 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from anishift.bootstrap import AppContext
from anishift.config.user_settings import (
    LLM_MAX_CONCURRENCY_RANGE,
    MAX_RETRIES_RANGE,
    TEMPO_RANGE,
    VOLUME_RANGE,
    UserSettings,
    config_path,
    save_user_settings,
)
from anishift.services.llm.engines import (
    available_engine_ids as available_llm_engine_ids,
)
from anishift.services.llm.engines import (
    suggested_model_ids,
)
from anishift.services.translation.engines import available_engine_ids
from anishift.services.translation.engines.llm.prompts import PromptRegistry

__all__ = ["open_settings_panel"]

# ── Constants ──────────────────────────────────────────────────────────────

_RETRIES_STEP: Final[int] = 1
"""Retry-count increment per ``←``/``→`` press."""

_TTS_ENGINES: Final[tuple[str, ...]] = ("edge", "elevenlabs", "balcon")
"""Placeholder TTS-engine ids (real list arrives in stage 6)."""

_VOICES: Final[tuple[str, ...]] = ("pl-PL-MarekNeural", "pl-PL-ZofiaNeural")
"""Placeholder TTS voices (real list arrives in stage 6)."""

_OUTPUT_VARIANTS: Final[tuple[str, ...]] = ("players", "merge", "burn")
"""Selectable output-assembly variants."""

_MODES: Final[tuple[str, ...]] = ("auto", "manual")
"""Selectable processing modes."""

_TEMPO_STEP: Final[float] = 0.05
"""Tempo increment per ``←``/``→`` press."""

_VOLUME_STEP: Final[int] = 5
"""Volume increment (percent) per ``←``/``→`` press."""


@dataclass(frozen=True, slots=True)
class _Field:
    """One editable row of the panel.

    Attributes:
        key: The :class:`UserSettings` attribute name.
        label: Human-readable label shown on the left.
    """

    key: str
    label: str


_FIELDS: Final[tuple[_Field, ...]] = (
    _Field("mode", "Mode"),
    _Field("translation_engine", "Translation"),
    _Field("translation_max_retries", "Max retries"),
    _Field("tts_engine", "TTS engine"),
    _Field("voice", "Voice"),
    _Field("tempo", "Tempo"),
    _Field("volume", "Volume"),
    _Field("output_variant", "Output"),
    _Field("move_results_to_output", "-> output/"),
)
"""Editable rows, top to bottom."""

_LLM_FIELDS: Final[tuple[_Field, ...]] = (
    _Field("llm_provider", "LLM provider"),
    _Field("llm_provider_model_id", "LLM model"),
    _Field("llm_prompt_id", "Prompt"),
    _Field("llm_style_id", "Style"),
    _Field("llm_module_ids", "Modules"),
    _Field("llm_max_concurrency", "LLM workers"),
)
"""Always-visible LLM configuration rows."""


@dataclass(slots=True)
class _PanelState:
    """Mutable cursor and inline model-editing state."""

    row: int = 0
    editing: bool = False
    buffer: str = ""


def _translation_engines(context: AppContext) -> tuple[str, ...]:
    """Return selectable engine ids: registry order, filtered by availability.

    Every registered engine remains visible; availability is rendered separately.
    """
    engines = list(available_engine_ids())
    return tuple(engines) or ("google",)


def _cycle(options: tuple[str, ...], current: str, delta: int) -> str:
    """Return the option ``delta`` steps from ``current`` (wrapping)."""
    index = options.index(current) if current in options else 0
    return options[(index + delta) % len(options)]


def _clamp_float(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return round(min(max(value, low), high), 2)


def _clamp_int(value: int, low: int, high: int) -> int:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return min(max(value, low), high)


def _visible_fields(_settings: UserSettings) -> tuple[_Field, ...]:
    """Return panel rows with LLM configuration always visible."""
    return (*_FIELDS[:3], *_LLM_FIELDS, *_FIELDS[3:])


def _prompt_registry() -> PromptRegistry:
    """Load built-in and config-relative custom prompts."""
    return PromptRegistry(custom_root=config_path().parent / "prompts")


def _step_field(  # noqa: C901, PLR0912 - one typed dispatcher owns all panel rows
    settings: UserSettings,
    field: _Field,
    delta: int,
    engines: tuple[str, ...],
    registry: PromptRegistry,
) -> None:
    """Advance ``field`` by ``delta`` on ``settings`` in place."""
    if field.key == "mode":
        settings.mode = _cycle(_MODES, settings.mode, delta)  # type: ignore[assignment]
    elif field.key == "translation_engine":
        settings.translation_engine = _cycle(engines, settings.translation_engine, delta)
    elif field.key == "translation_max_retries":
        settings.translation_max_retries = _clamp_int(
            settings.translation_max_retries + delta * _RETRIES_STEP, *MAX_RETRIES_RANGE
        )
    elif field.key == "llm_provider":
        previous = settings.llm_provider
        previous_suggestions = suggested_model_ids(previous)
        settings.llm_provider = _cycle(available_llm_engine_ids(), previous, delta)
        new_suggestions = suggested_model_ids(settings.llm_provider)
        if (
            not settings.llm_provider_model_id or settings.llm_provider_model_id in previous_suggestions
        ) and new_suggestions:
            settings.llm_provider_model_id = new_suggestions[0]
    elif field.key == "llm_provider_model_id":
        suggestions = suggested_model_ids(settings.llm_provider)
        if suggestions:
            settings.llm_provider_model_id = _cycle(
                suggestions,
                settings.llm_provider_model_id,
                delta,
            )
    elif field.key == "llm_prompt_id":
        options = tuple(registry.list_ids("task"))
        if options:
            settings.llm_prompt_id = _cycle(options, settings.llm_prompt_id, delta)
    elif field.key == "llm_style_id":
        options = tuple(registry.list_ids("style"))
        if options:
            settings.llm_style_id = _cycle(options, settings.llm_style_id, delta)
    elif field.key == "llm_module_ids":
        options = tuple(registry.list_ids("module"))
        if delta < 0:
            if settings.llm_module_ids:
                settings.llm_module_ids.pop()
            return
        selected = set(settings.llm_module_ids)
        next_module = next((module_id for module_id in options if module_id not in selected), None)
        if next_module is not None:
            settings.llm_module_ids.append(next_module)
    elif field.key == "llm_max_concurrency":
        settings.llm_max_concurrency = _clamp_int(
            settings.llm_max_concurrency + delta,
            *LLM_MAX_CONCURRENCY_RANGE,
        )
    elif field.key == "tts_engine":
        settings.tts_engine = _cycle(_TTS_ENGINES, settings.tts_engine, delta)
    elif field.key == "voice":
        settings.voice = _cycle(_VOICES, settings.voice, delta)
    elif field.key == "output_variant":
        settings.output_variant = _cycle(_OUTPUT_VARIANTS, settings.output_variant, delta)  # type: ignore[assignment]
    elif field.key == "tempo":
        settings.tempo = _clamp_float(settings.tempo + delta * _TEMPO_STEP, *TEMPO_RANGE)
    elif field.key == "volume":
        settings.volume = _clamp_int(settings.volume + delta * _VOLUME_STEP, *VOLUME_RANGE)
    elif field.key == "move_results_to_output":
        settings.move_results_to_output = not settings.move_results_to_output


def _value_text(  # noqa: PLR0911 - row-specific rendering stays explicit
    context: AppContext,
    settings: UserSettings,
    field: _Field,
    *,
    editing_buffer: str | None = None,
) -> str:
    """Render the current value of ``field`` for display."""
    value = getattr(settings, field.key)
    if field.key == "llm_provider_model_id" and editing_buffer is not None:
        return f"{editing_buffer}▏"
    if field.key == "llm_provider_model_id":
        suggestions = suggested_model_ids(settings.llm_provider)
        suffix = "" if value in suggestions else " (custom — verify for provider)"
        return f"{value}{suffix}"
    if field.key == "llm_provider":
        return f"{value} ({_provider_availability(context, settings.llm_provider)})"
    if field.key == "translation_engine" and value == "llm":
        return f"{value} ({_provider_availability(context, settings.llm_provider)})"
    if field.key == "llm_module_ids":
        return ", ".join(settings.llm_module_ids) or "none"
    if field.key == "tempo":
        return f"{value:.2f}x"
    if field.key == "volume":
        return f"{value}%"
    if field.key == "move_results_to_output":
        return "yes" if value else "no"
    return str(value)


def _provider_availability(context: AppContext, provider: str) -> str:
    """Return a non-secret local availability marker for one provider."""
    if provider == "openai_compatible":
        return "ready" if context.settings.openai_compatible_base_url.strip() else "missing base URL"
    keys: dict[str, str] = {
        "anthropic": context.settings.anthropic_api_key,
        "gemini": context.settings.gemini_api_key,
        "openai": context.settings.openai_api_key,
        "deepseek": context.settings.deepseek_api_key,
        "openrouter": context.settings.openrouter_api_key,
    }
    return "ready" if keys.get(provider, "").strip() else "missing key"


def open_settings_panel(  # noqa: C901, PLR0915 - prompt_toolkit bindings share local state
    context: AppContext,
) -> UserSettings:
    """Open the arrow-key settings panel and return the edited preferences.

    Args:
        context: Wired context whose ``user_settings`` seed the panel.

    Returns:
        The mutated :class:`UserSettings` (already persisted on every change).
    """
    settings = context.user_settings
    engines = _translation_engines(context)
    registry = _prompt_registry()
    state = _PanelState()

    def render() -> StyleAndTextTuples:
        lines: StyleAndTextTuples = [("class:title", " AniShift · Settings\n\n")]
        fields = _visible_fields(settings)
        state.row = min(state.row, len(fields) - 1)
        for i, field in enumerate(fields):
            marker = "> " if i == state.row else "  "
            style = "class:active" if i == state.row else "class:normal"
            edit_buffer = state.buffer if state.editing and i == state.row else None
            value = _value_text(
                context,
                settings,
                field,
                editing_buffer=edit_buffer,
            )
            lines.append((style, f"{marker}{field.label:<16}{value}\n"))
        hint = (
            " type model · Enter save · Esc cancel"
            if state.editing
            else " ↑↓ field · ←→ change · e edit model · Esc back"
        )
        lines.append(("class:hint", f"\n{hint}"))
        return lines

    bindings = KeyBindings()

    @bindings.add("up")
    def _up(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            return
        fields = _visible_fields(settings)
        state.row = (state.row - 1) % len(fields)

    @bindings.add("down")
    def _down(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            return
        fields = _visible_fields(settings)
        state.row = (state.row + 1) % len(fields)

    @bindings.add("left")
    def _left(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            return
        fields = _visible_fields(settings)
        _step_field(settings, fields[state.row], -1, engines, registry)
        save_user_settings(settings)

    @bindings.add("right")
    def _right(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            return
        fields = _visible_fields(settings)
        _step_field(settings, fields[state.row], 1, engines, registry)
        save_user_settings(settings)

    @bindings.add("enter")
    def _enter(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            if state.buffer.strip():
                settings.llm_provider_model_id = state.buffer.strip()
                save_user_settings(settings)
            state.editing = False
            state.buffer = ""
            return
        fields = _visible_fields(settings)
        _step_field(settings, fields[state.row], 1, engines, registry)
        save_user_settings(settings)

    @bindings.add("escape")
    def _quit(event: KeyPressEvent) -> None:
        if state.editing:
            state.editing = False
            state.buffer = ""
            return
        event.app.exit()

    @bindings.add("q")
    def _quit_or_type_q(event: KeyPressEvent) -> None:
        if state.editing:
            state.buffer += "q"
            return
        event.app.exit()

    @bindings.add("e")
    def _edit_model(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            state.buffer += "e"
            return
        fields = _visible_fields(settings)
        if fields[state.row].key == "llm_provider_model_id":
            state.editing = True
            state.buffer = settings.llm_provider_model_id

    @bindings.add("backspace")
    def _backspace(event: KeyPressEvent) -> None:
        del event
        if state.editing:
            state.buffer = state.buffer[:-1]

    @bindings.add("<any>")
    def _type_model(event: KeyPressEvent) -> None:
        if state.editing and event.data.isprintable():
            state.buffer += event.data

    control = FormattedTextControl(render, focusable=True, show_cursor=False)
    layout = Layout(HSplit([Window(control)]))
    application: Application[None] = Application(
        layout=layout,
        key_bindings=bindings,
        full_screen=True,
    )
    application.run()
    return settings
