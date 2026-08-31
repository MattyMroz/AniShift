"""Curated interactive settings built on the single terminal renderer."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from rich.text import Text

from anishift.application import (
    AppService,
    AutoPreset,
    AutoPresetDraft,
    BurnSubtitleProduct,
    EnvironmentSettingStatus,
    ModelAvailability,
    ModelProbeResult,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    TranslationModelOption,
)
from anishift.cli.interactive.settings_editors import parse_setting_input
from anishift.config.field_access import read_setting_value, setting_is_active
from anishift.config.field_catalog import SettingSpec, SettingValue, SettingValueType
from anishift.config.model_catalog import ModelCatalog, ModelEntry
from anishift.config.user_settings import UserSettings
from anishift.errors import AniShiftError

__all__ = ["SettingsController", "SettingsResult"]

# ── Constants ─────────────────────────────────────────────────────────────────

_POINTER: Final[str] = "\u276f"
"""Marker placed before the active interactive row."""

_MENU_HINT: Final[str] = "↑↓ · Enter · Esc"
"""Keyboard hint used by settings menus."""

_MULTI_HINT: Final[str] = "↑↓ · Enter/Space zmień · Esc wróć"
"""Keyboard hint used by the output product selector."""

_MULTI_SELECT_HINT: Final[str] = "↑↓ · Space zmień · Enter zapisz · Esc anuluj"
"""Keyboard hint used by multi-choice setting editors."""

_INPUT_HINT: Final[str] = "Enter zapisz · Esc anuluj"
"""Keyboard hint used by scalar and password editors."""

_SAVED_MESSAGE: Final[str] = "✓ Zapisano"
"""Confirmation shown after one successful transaction."""

_BACK_KEY: Final[str] = "back"
"""Stable action key returning to the parent menu."""

_RESET_KEY: Final[str] = "reset-settings"
"""Stable action key restoring non-secret panel preferences."""

_BACK_LABEL: Final[str] = "Cofnij"
"""Label of the row that collapses one level."""

_SAVE_DELAY_SECONDS: Final[float] = 0.4
"""Idle time that coalesces a run of arrow presses into one saved transaction."""

_COARSE_INTEGER_SPAN: Final[int] = 1000
"""Range above which whole numbers step by hundreds instead of by one."""

_FINE_FLOAT_SPAN: Final[float] = 2.0
"""Range up to which fractional values step by hundredths."""

_MEDIUM_FLOAT_SPAN: Final[float] = 20.0
"""Range up to which fractional values step by halves."""

_FINE_FLOAT_STEP: Final[float] = 0.05
"""Step used by probabilities, temperatures and other narrow fractions."""

_COARSE_FLOAT_STEP: Final[float] = 0.5
"""Step used by tempo multipliers and decibel gains."""

_COARSE_INTEGER_STEP: Final[int] = 100
"""Step used by token limits and other wide whole-number ranges."""

_ROOT_ITEMS: Final[tuple[tuple[str, str], ...]] = (
    ("Ogólne", "category:general"),
    ("Tłumaczenie", "category:translation"),
    ("Lektor", "category:tts"),
    ("Wynik", "category:output"),
    ("Połączenia", "category:connections"),
    ("Przywróć domyślne", _RESET_KEY),
    (_BACK_LABEL, _BACK_KEY),
)
"""Settings root entries in product-defined order."""

type _SettingField = tuple[str, str, str]
"""Setting ID, Polish label, and visible menu section."""

_GENERAL_FIELDS: Final[tuple[_SettingField, ...]] = (
    ("processing_order_policy", "Kolejność przetwarzania", "PRZETWARZANIE"),
    ("audio_language_priority", "Priorytet języków audio", "JĘZYKI"),
    ("subtitle_language_priority", "Priorytet języków napisów", "JĘZYKI"),
    ("composition_quality_preset", "Jakość obrazu", "WYNIK"),
)
"""General persisted preferences exposed by the product."""

_TRANSLATION_FIELDS: Final[tuple[_SettingField, ...]] = (
    ("translation_engine", "Silnik tłumaczenia", "PODSTAWOWE"),
    ("translation_fallback_chain", "Silniki awaryjne", "PODSTAWOWE"),
    ("translation_batch_size", "Linii na zapytanie", "WYDAJNOŚĆ"),
    ("translation_concurrency", "Partii jednocześnie", "WYDAJNOŚĆ"),
    ("translation_max_retries", "Ponowienia", "WYDAJNOŚĆ"),
    ("llm_max_concurrency", "Plików LLM jednocześnie", "WYDAJNOŚĆ"),
    ("llm_temperature", "Temperatura", "MODEL LLM"),
    ("llm_top_p", "Top-p", "MODEL LLM"),
    ("llm_max_output_tokens", "Limit tokenów odpowiedzi", "MODEL LLM"),
    ("llm_translation_style", "Styl", "PROMPT"),
)
"""Persisted translation fields exposed by the product."""

_TTS_FIELDS: Final[tuple[_SettingField, ...]] = (
    ("tts_engine", "Silnik", "PODSTAWOWE"),
    ("tts_provider_model_id", "Model / endpoint", "PODSTAWOWE"),
    ("tts_voice_id", "Głos", "PODSTAWOWE"),
    ("tts_profile.concurrency", "Syntez jednocześnie", "WYDAJNOŚĆ"),
    ("tts_max_retries", "Ponowienia", "WYDAJNOŚĆ"),
    ("elevenbytes_vpn_enabled", "VPN ElevenBytes", "WYDAJNOŚĆ"),
    ("tts_profile.postprocess_tempo", "Tempo końcowe", "GŁOS"),
    ("tts_profile.voice_mix_offset_db", "Korekta głośności głosu", "GŁOS"),
    ("tts_profile.native_rate", "Tempo natywne", "GŁOS"),
    ("tts_profile.native_volume", "Głośność natywna", "GŁOS"),
    ("tts_profile.native_pitch", "Wysokość głosu", "GŁOS"),
    ("tts_profile.engine_options.stability", "Stabilność", "GŁOS"),
    ("tts_profile.engine_options.similarity_boost", "Podobieństwo", "GŁOS"),
    ("tts_profile.engine_options.style", "Ekspresja", "GŁOS"),
    ("tts_profile.engine_options.use_speaker_boost", "Wzmocnienie mówcy", "GŁOS"),
    ("tts_profile.engine_options.speed", "Prędkość natywna", "GŁOS"),
    ("tts_profile.engine_options.output_format", "Format natywny", "DŹWIĘK"),
    ("tts_output_profile", "Kodek lektora", "DŹWIĘK"),
    ("tts_output_bitrate", "Bitrate lektora", "DŹWIĘK"),
    ("narrator_mix_base_gain_db", "Głośność lektora", "DŹWIĘK"),
    ("original_gain_db", "Głośność oryginału", "DŹWIĘK"),
)
"""Persisted narration fields exposed by the product."""

_FIELDS_COVERED_ELSEWHERE: Final[dict[str, str]] = {
    "llm_provider": "chosen atomically together with the model",
    "llm_provider_model_id": "chosen atomically together with the provider",
    "openai_compatible_base_url": "edited inside the connections category",
    "palantir_enrollment_base_url": "edited inside the connections category",
    "primary_model_alias": "deliberately hidden from the product surface",
}
"""Editable fields intentionally absent from the section layout, with the reason."""

_KNOWN_LAYOUT_GAPS: Final[dict[str, str]] = {
    "elevenbytes_custom_voices": "object lists have no editor yet",
}
"""Editable fields still unreachable, tracked so the shortfall stays counted."""

_PRODUCTS: Final[tuple[tuple[ProductKind, str], ...]] = (
    (ProductKind.FULL_PL, "Polskie napisy"),
    (ProductKind.NARRATION_AUDIO, "Polski lektor"),
    (ProductKind.MKV, "MKV"),
    (ProductKind.MP4, "MP4"),
)
"""Public output products and their labels."""

_ENGINE_LABELS: Final[dict[str, str]] = {
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "deepl": "DeepL",
    "edge": "Microsoft Edge",
    "elevenbytes": "ElevenBytes",
    "elevenlabs": "ElevenLabs",
    "gemini": "Gemini",
    "google": "Google",
    "llm": "LLM",
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-compatible",
    "openrouter": "OpenRouter",
    "palantir": "Palantir Foundry",
    "sapi": "Windows SAPI",
}
"""Readable labels for engine IDs exposed by the curated menus."""


class SettingsResult(StrEnum):
    """Signal whether the settings controller remains active."""

    STAY = "stay"
    BACK_HOME = "back_home"


class _Category(StrEnum):
    GENERAL = "general"
    TRANSLATION = "translation"
    TTS = "tts"
    OUTPUT = "output"
    CONNECTIONS = "connections"


class _EditorKind(StrEnum):
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    TEXT = "text"
    PASSWORD = "password"  # noqa: S105 - editor kind, never a credential
    CONFIRM = "confirm"


class _EditorAction(StrEnum):
    UPDATE_SETTING = "update_setting"
    SELECT_MODEL = "select_model"
    UPDATE_SECRET = "update_secret"  # noqa: S105 - operation name, never a credential
    UPDATE_ENVIRONMENT = "update_environment"
    REMOVE_SECRET = "remove_secret"  # noqa: S105 - operation name, never a credential
    RESET_SETTINGS = "reset_settings"


@dataclass(frozen=True, slots=True)
class _MenuItem:
    key: str
    label: str
    current: str = ""
    section: str = ""


@dataclass(frozen=True, slots=True)
class _Option:
    value: str
    label: str
    group: str = ""
    provider_id: str = ""


@dataclass(frozen=True, slots=True)
class _Connection:
    key: str
    label: str
    secret_id: str
    address_id: str = ""
    can_probe: bool = False


@dataclass(slots=True)
class _Editor:
    title: str
    kind: _EditorKind
    action: _EditorAction
    setting_id: str
    options: tuple[_Option, ...] = ()
    selected: int = 0
    offset: int = 0
    visible_count: int = 0
    current_value: str = ""
    buffer: str = ""
    selected_values: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _PendingEdit:
    setting_id: str
    value: SettingValue
    deadline: float


@dataclass(frozen=True, slots=True)
class _CatalogSnapshot:
    settings: UserSettings
    specs: dict[str, SettingSpec]


@dataclass(frozen=True, slots=True)
class _Feedback:
    text: str
    style: str


_CONNECTIONS: Final[tuple[_Connection, ...]] = (
    _Connection("palantir", "Palantir Foundry", "palantir_token", "palantir_enrollment_base_url", True),
    _Connection("gemini", "Gemini", "gemini_api_key"),
    _Connection("openai", "OpenAI", "openai_api_key"),
    _Connection("anthropic", "Anthropic", "anthropic_api_key"),
    _Connection("deepseek", "DeepSeek", "deepseek_api_key"),
    _Connection("openrouter", "OpenRouter", "openrouter_api_key"),
    _Connection(
        "openai-compatible",
        "OpenAI-compatible",
        "openai_compatible_api_key",
        "openai_compatible_base_url",
    ),
    _Connection("deepl", "DeepL", "deepl_api_key"),
    _Connection("elevenlabs", "ElevenLabs", "elevenlabs_api_key"),
)
"""Environment-backed connections that already exist in the backend."""


class SettingsController:
    """Own local settings navigation while all persistence stays in AppService."""

    def __init__(self, service: AppService, invalidate: Callable[[], None]) -> None:
        self._service: AppService = service
        self._invalidate: Callable[[], None] = invalidate
        self._category: _Category | None = None
        self._connection: _Connection | None = None
        self._items: tuple[_MenuItem, ...] = ()
        self._selected: int = 0
        self._offset: int = 0
        self._visible_count: int = 0
        self._pending: _PendingEdit | None = None
        self._follow_cursor: bool = True
        self._editor: _Editor | None = None
        self._output_products: set[ProductKind] = set()
        self._feedback: _Feedback | None = None
        self._busy: bool = False
        self._generation: int = 0
        self._lock: threading.Lock = threading.Lock()
        self._refresh_menu()

    def handle_key(self, key: str) -> SettingsResult:
        """Apply one normalized terminal key without performing render-time I/O."""
        if key not in {"left", "right"}:
            self._commit_pending()
        if self._busy:
            return self._handle_busy_key(key)
        if self._editor is not None:
            self._handle_editor_key(key)
            return SettingsResult.STAY
        if key in {"escape", "interrupt"}:
            return self._go_back()
        if self._category is _Category.OUTPUT:
            self._handle_output_key(key)
            return SettingsResult.STAY
        return self._handle_menu_key(key)

    def flush_pending(self) -> None:
        """Persist a delayed edit once the user has stopped pressing arrows."""
        pending: _PendingEdit | None = self._pending
        if pending is None or time.monotonic() < pending.deadline:
            return
        self._commit_pending()
        self._invalidate()

    def _commit_pending(self) -> None:
        pending: _PendingEdit | None = self._pending
        if pending is None:
            return
        self._pending = None
        try:
            self._service.update_setting(pending.setting_id, pending.value)
        except AniShiftError, OSError:
            self._feedback = _Feedback("✗ Nie udało się zapisać ustawienia", "error")
        except TypeError, ValueError:
            self._feedback = _Feedback(self._validation_message(pending.setting_id), "error")
        else:
            self._feedback = _Feedback(_SAVED_MESSAGE, "success")
        self._refresh_menu()

    def _adjust_selected(self, direction: int) -> None:
        if not self._items:
            return
        key: str = self._items[self._selected].key
        if not key.startswith("setting:"):
            return
        setting_id: str = key.removeprefix("setting:")
        try:
            snapshot: _CatalogSnapshot = self._catalog_snapshot()
        except AniShiftError, OSError:
            return
        spec: SettingSpec | None = snapshot.specs.get(setting_id)
        if spec is None:
            return
        current: SettingValue = self._effective_value(snapshot, spec)
        stepped: tuple[SettingValue] | None = _stepped_value(spec, current, direction)
        if stepped is None:
            return
        self._pending = _PendingEdit(setting_id, stepped[0], time.monotonic() + _SAVE_DELAY_SECONDS)
        self._feedback = None

    def _effective_value(self, snapshot: _CatalogSnapshot, spec: SettingSpec) -> SettingValue:
        pending: _PendingEdit | None = self._pending
        if pending is not None and pending.setting_id == spec.setting_id:
            return pending.value
        return read_setting_value(snapshot.settings, spec)

    def render(self, columns: int, rows: int) -> Text:
        """Render the cached current menu or editor for one terminal geometry."""
        with self._lock:
            if self._editor is not None:
                return self._render_editor(columns, rows, self._editor)
            if self._category is _Category.OUTPUT:
                return self._render_output(columns, rows)
            return self._render_menu(columns, rows)

    def _handle_busy_key(self, key: str) -> SettingsResult:
        if key not in {"escape", "interrupt"}:
            return SettingsResult.STAY
        with self._lock:
            self._generation += 1
            self._busy = False
            self._feedback = _Feedback("Anulowano", "warning")
        return SettingsResult.STAY

    def _apply_navigation(self, key: str, length: int) -> bool:
        if key == "up":
            self._move(-1, length)
        elif key == "down":
            self._move(1, length)
        elif key == "pageup":
            self._jump(self._selected - self._page_stride(), length)
        elif key == "pagedown":
            self._jump(self._selected + self._page_stride(), length)
        elif key == "home":
            self._jump(0, length)
        elif key == "end":
            self._jump(length - 1, length)
        else:
            return False
        return True

    def _handle_menu_key(self, key: str) -> SettingsResult:
        if self._apply_navigation(key, len(self._items)):
            return SettingsResult.STAY
        if key in {"left", "right"}:
            self._adjust_selected(1 if key == "right" else -1)
            return SettingsResult.STAY
        if key != "enter" or not self._items:
            return SettingsResult.STAY
        return self._activate(self._items[self._selected].key)

    def _handle_output_key(self, key: str) -> None:
        save_index: int = len(_PRODUCTS)
        reset_index: int = save_index + 1
        back_index: int = reset_index + 1
        row_count: int = back_index + 1
        if self._apply_navigation(key, row_count):
            return
        if key in {"space", "enter"} and self._selected < len(_PRODUCTS):
            self._toggle_output_product(self._selected)
            return
        if key != "enter":
            return
        if self._selected == save_index:
            self._save_output()
            return
        if self._selected == reset_index:
            self._output_products = {ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO}
            self._feedback = _Feedback("Przywrócono domyślny wybór · Zapisz, aby zatwierdzić", "info")
            return
        if self._selected == back_index:
            self._category = None
            self._refresh_menu()

    def _toggle_output_product(self, index: int) -> None:
        product: ProductKind = _PRODUCTS[index][0]
        if product in self._output_products:
            self._output_products.remove(product)
        else:
            self._output_products.add(product)
        self._feedback = None

    def _handle_editor_key(self, key: str) -> None:
        editor: _Editor | None = self._editor
        if editor is None:
            return
        if key in {"escape", "interrupt"}:
            self._editor = None
            self._feedback = None
            return
        if editor.kind in {_EditorKind.SELECT, _EditorKind.MULTI_SELECT, _EditorKind.CONFIRM}:
            self._handle_choice_editor(editor, key)
            return
        if key == "backspace":
            editor.buffer = editor.buffer[:-1]
            self._feedback = None
            return
        if key == "space":
            editor.buffer += " "
            self._feedback = None
            return
        if key.startswith("text:"):
            editor.buffer += key.removeprefix("text:")
            self._feedback = None
            return
        if key == "enter":
            self._submit_editor(editor)

    def _handle_choice_editor(self, editor: _Editor, key: str) -> None:
        if _navigate_editor(editor, key):
            return
        if key == "space" and editor.kind is _EditorKind.MULTI_SELECT:
            value: str = editor.options[editor.selected].value
            if value in editor.selected_values:
                editor.selected_values.remove(value)
            else:
                editor.selected_values.add(value)
            self._feedback = None
            return
        if key == "enter":
            self._submit_editor(editor)

    def _move(self, delta: int, length: int) -> None:
        if length:
            self._selected = (self._selected + delta) % length
        self._follow_cursor = True
        self._feedback = None

    def _jump(self, index: int, length: int) -> None:
        if length:
            self._selected = min(max(index, 0), length - 1)
        self._follow_cursor = True
        self._feedback = None

    def _page_stride(self) -> int:
        return max(self._visible_count - 1, 1)

    def _activate(self, key: str) -> SettingsResult:
        self._feedback = None
        if key == _BACK_KEY:
            return self._go_back()
        if key == _RESET_KEY:
            self._open_reset_confirmation()
            return SettingsResult.STAY
        if key.startswith("category:"):
            self._enter_category(_Category(key.removeprefix("category:")))
        elif key.startswith("setting:"):
            self._open_setting_editor(key.removeprefix("setting:"))
        elif key == "translation-model":
            self._open_model_editor()
        elif key.startswith("connection:"):
            self._connection = _connection_by_key(key.removeprefix("connection:"))
            self._selected = 0
            self._offset = 0
            self._refresh_menu()
        elif key == "connection-secret":
            self._open_password_editor()
        elif key == "connection-address":
            self._open_address_editor()
        elif key == "connection-remove":
            self._open_remove_confirmation()
        elif key == "connection-probe":
            self._start_probe()
        return SettingsResult.STAY

    def _enter_category(self, category: _Category) -> None:
        self._category = category
        self._connection = None
        self._selected = 0
        self._offset = 0
        if category is _Category.OUTPUT:
            self._load_output()
            return
        self._refresh_menu()

    def _go_back(self) -> SettingsResult:
        self._feedback = None
        if self._editor is not None:
            self._editor = None
            return SettingsResult.STAY
        if self._connection is not None:
            self._connection = None
            self._selected = 0
            self._offset = 0
            self._refresh_menu()
            return SettingsResult.STAY
        if self._category is not None:
            self._category = None
            self._selected = 0
            self._offset = 0
            self._refresh_menu()
            return SettingsResult.STAY
        return SettingsResult.BACK_HOME

    def _refresh_menu(self) -> None:
        try:
            self._items = self._build_menu_items()
        except AniShiftError, OSError, TypeError, ValueError:
            self._items = (_MenuItem(_BACK_KEY, _BACK_LABEL),)
            self._selected = 0
            self._offset = 0
            self._feedback = _Feedback("✗ Nie można wczytać ustawień", "error")
        self._selected = min(self._selected, max(len(self._items) - 1, 0))
        self._offset = min(self._offset, self._selected)

    def _build_menu_items(self) -> tuple[_MenuItem, ...]:
        if self._category is None:
            return tuple(_MenuItem(key, label) for label, key in _ROOT_ITEMS)
        if self._connection is not None:
            return self._connection_menu_items(self._connection)
        if self._category is _Category.GENERAL:
            items: tuple[_MenuItem, ...] = self._setting_items(_GENERAL_FIELDS)
        elif self._category is _Category.TRANSLATION:
            items = self._translation_items()
        elif self._category is _Category.TTS:
            items = self._setting_items(_TTS_FIELDS)
        elif self._category is _Category.CONNECTIONS:
            items = self._connection_items()
        else:
            items = ()
        return items

    def _translation_items(self) -> tuple[_MenuItem, ...]:
        snapshot: _CatalogSnapshot = self._catalog_snapshot()
        items: list[_MenuItem] = [self._setting_item(snapshot, *_TRANSLATION_FIELDS[0])]
        if snapshot.settings.translation_engine == "llm":
            items.append(
                _MenuItem(
                    "translation-model",
                    "Model tłumaczenia",
                    self._model_label(snapshot.settings),
                    "PODSTAWOWE",
                ),
            )
        items.extend(self._active_setting_items(snapshot, _TRANSLATION_FIELDS[1:]))
        items.append(_MenuItem(_BACK_KEY, _BACK_LABEL))
        return tuple(items)

    def _setting_items(self, fields: tuple[_SettingField, ...]) -> tuple[_MenuItem, ...]:
        snapshot: _CatalogSnapshot = self._catalog_snapshot()
        items: list[_MenuItem] = list(self._active_setting_items(snapshot, fields))
        items.append(_MenuItem(_BACK_KEY, _BACK_LABEL))
        return tuple(items)

    def _active_setting_items(
        self,
        snapshot: _CatalogSnapshot,
        fields: tuple[_SettingField, ...],
    ) -> tuple[_MenuItem, ...]:
        items: list[_MenuItem] = []
        for setting_id, label, section in fields:
            spec: SettingSpec | None = snapshot.specs.get(setting_id)
            if spec is None or not setting_is_active(spec, snapshot.settings):
                continue
            items.append(self._setting_item(snapshot, setting_id, label, section))
        return tuple(items)

    def _setting_item(
        self,
        snapshot: _CatalogSnapshot,
        setting_id: str,
        label: str,
        section: str,
    ) -> _MenuItem:
        spec: SettingSpec = _required_spec(snapshot.specs, setting_id)
        value: SettingValue = self._effective_value(snapshot, spec)
        return _MenuItem(f"setting:{setting_id}", label, _format_value(setting_id, value), section)

    def _connection_items(self) -> tuple[_MenuItem, ...]:
        statuses: dict[str, EnvironmentSettingStatus] = {
            status.setting_id: status for status in self._service.environment_setting_statuses()
        }
        items: list[_MenuItem] = []
        for connection in _CONNECTIONS:
            status: EnvironmentSettingStatus | None = statuses.get(connection.secret_id)
            current: str = _connection_status(status)
            items.append(_MenuItem(f"connection:{connection.key}", connection.label, current))
        items.append(_MenuItem(_BACK_KEY, _BACK_LABEL))
        return tuple(items)

    def _connection_menu_items(self, connection: _Connection) -> tuple[_MenuItem, ...]:
        items: list[_MenuItem] = [_MenuItem("connection-secret", "Ustaw / zmień klucz")]
        if connection.address_id:
            items.append(_MenuItem("connection-address", "Adres", self._connection_address(connection)))
        items.append(_MenuItem("connection-remove", "Usuń klucz"))
        if connection.can_probe:
            items.append(_MenuItem("connection-probe", "Testuj połączenie"))
        items.append(_MenuItem(_BACK_KEY, _BACK_LABEL))
        return tuple(items)

    def _connection_address(self, connection: _Connection) -> str:
        if connection.address_id == "palantir_enrollment_base_url":
            return self._service.settings_snapshot().palantir_enrollment_base_url or "brak"
        value: str = getattr(self._service.current_settings(), connection.address_id, "")
        return value or "brak"

    def _catalog_snapshot(self) -> _CatalogSnapshot:
        settings: UserSettings = self._service.settings_snapshot()
        specs: dict[str, SettingSpec] = {spec.setting_id: spec for spec in self._service.settings_catalog(settings)}
        return _CatalogSnapshot(settings, specs)

    def _model_label(self, settings: UserSettings) -> str:
        if settings.llm_provider != "palantir":
            provider: str = _ENGINE_LABELS.get(settings.llm_provider, settings.llm_provider)
            return f"{provider} · {settings.llm_provider_model_id}"
        try:
            catalog: ModelCatalog = self._service.model_catalog()
        except AniShiftError:
            return "Palantir · katalog niedostępny"
        entry: ModelEntry | None = catalog.models.get(settings.llm_provider_model_id)
        if entry is None:
            return f"Palantir · {settings.llm_provider_model_id}"
        if entry.model_id.casefold().startswith("replace-with-"):
            return "Palantir · model nieustawiony"
        return f"Palantir · {entry.label}"

    def _open_setting_editor(self, setting_id: str) -> None:
        snapshot: _CatalogSnapshot = self._catalog_snapshot()
        spec: SettingSpec = _required_spec(snapshot.specs, setting_id)
        current: SettingValue = read_setting_value(snapshot.settings, spec)
        if spec.value_type is SettingValueType.BOOLEAN:
            options: tuple[_Option, ...] = (_Option("true", "Tak"), _Option("false", "Nie"))
            current_text: str = "true" if current is True else "false"
            self._editor = _Editor(
                title=_field_title(setting_id),
                kind=_EditorKind.SELECT,
                action=_EditorAction.UPDATE_SETTING,
                setting_id=setting_id,
                options=options,
                selected=_selected_option(options, current_text),
                current_value=current_text,
            )
            return
        if spec.allowed_values and spec.value_type in {SettingValueType.STRING_LIST, SettingValueType.STRING_SET}:
            if not isinstance(current, (tuple, frozenset)):
                msg = f"Collection setting {setting_id!r} returned a scalar value"
                raise TypeError(msg)
            options = tuple(_Option(str(value), _choice_label(setting_id, str(value))) for value in spec.allowed_values)
            selected_values: set[str] = {str(value) for value in current}
            selected: int = next(
                (index for index, option in enumerate(options) if option.value in selected_values),
                0,
            )
            self._editor = _Editor(
                title=_field_title(setting_id),
                kind=_EditorKind.MULTI_SELECT,
                action=_EditorAction.UPDATE_SETTING,
                setting_id=setting_id,
                options=options,
                selected=selected,
                selected_values=selected_values,
            )
            return
        if spec.allowed_values:
            choice_options: tuple[_Option, ...] = tuple(
                _Option(str(value), _choice_label(setting_id, str(value))) for value in spec.allowed_values
            )
            choice_selected: int = _selected_option(choice_options, str(current))
            self._editor = _Editor(
                title=_field_title(setting_id),
                kind=_EditorKind.SELECT,
                action=_EditorAction.UPDATE_SETTING,
                setting_id=setting_id,
                options=choice_options,
                selected=choice_selected,
                current_value=str(current),
            )
            return
        self._editor = _Editor(
            title=_field_title(setting_id),
            kind=_EditorKind.TEXT,
            action=_EditorAction.UPDATE_SETTING,
            setting_id=setting_id,
            buffer=_format_input(current),
        )

    def _open_model_editor(self) -> None:
        try:
            choices: tuple[TranslationModelOption, ...] = self._service.translation_model_options()
        except AniShiftError:
            self._feedback = _Feedback(
                "✗ Nie można wczytać modeli · Sprawdź Połączenia i katalog Palantir",
                "error",
            )
            return
        options: tuple[_Option, ...] = tuple(
            _Option(
                choice.model_id,
                choice.label,
                _model_group_label(choice.group_id),
                choice.provider_id,
            )
            for choice in choices
        )
        if not options:
            self._feedback = _Feedback("✗ Brak modeli · Najpierw skonfiguruj dostawcę w Połączeniach", "error")
            return
        settings: UserSettings = self._service.settings_snapshot()
        self._editor = _Editor(
            title="MODEL TŁUMACZENIA",
            kind=_EditorKind.SELECT,
            action=_EditorAction.SELECT_MODEL,
            setting_id="llm_provider_model_id",
            options=options,
            selected=_selected_model_option(options, settings.llm_provider, settings.llm_provider_model_id),
            current_value=f"{settings.llm_provider}\x1f{settings.llm_provider_model_id}",
        )

    def _open_reset_confirmation(self) -> None:
        self._editor = _Editor(
            title="PRZYWRÓCIĆ USTAWIENIA DOMYŚLNE?",
            kind=_EditorKind.CONFIRM,
            action=_EditorAction.RESET_SETTINGS,
            setting_id="reset-settings",
            options=(_Option("no", "Nie"), _Option("yes", "Tak")),
        )

    def _open_password_editor(self) -> None:
        connection: _Connection = _required_connection(self._connection)
        self._editor = _Editor(
            title=f"{connection.label.upper()} · KLUCZ",
            kind=_EditorKind.PASSWORD,
            action=_EditorAction.UPDATE_SECRET,
            setting_id=connection.secret_id,
        )

    def _open_address_editor(self) -> None:
        connection: _Connection = _required_connection(self._connection)
        current: str = self._connection_address(connection)
        if current == "brak":
            current = ""
        action: _EditorAction = (
            _EditorAction.UPDATE_SETTING
            if connection.address_id == "palantir_enrollment_base_url"
            else _EditorAction.UPDATE_ENVIRONMENT
        )
        self._editor = _Editor(
            title=f"{connection.label.upper()} · ADRES",
            kind=_EditorKind.TEXT,
            action=action,
            setting_id=connection.address_id,
            buffer=current,
        )

    def _open_remove_confirmation(self) -> None:
        connection: _Connection = _required_connection(self._connection)
        self._editor = _Editor(
            title=f"USUNĄĆ KLUCZ · {connection.label.upper()}?",
            kind=_EditorKind.CONFIRM,
            action=_EditorAction.REMOVE_SECRET,
            setting_id=connection.secret_id,
            options=(_Option("no", "Nie"), _Option("yes", "Tak")),
        )

    def _submit_editor(self, editor: _Editor) -> None:
        if editor.kind is _EditorKind.MULTI_SELECT:
            raw_value: str = ",".join(
                option.value for option in editor.options if option.value in editor.selected_values
            )
        else:
            raw_value = editor.options[editor.selected].value if editor.options else editor.buffer
        if editor.kind is _EditorKind.PASSWORD and not raw_value.strip():
            self._editor = None
            self._feedback = None
            return
        if editor.action is _EditorAction.REMOVE_SECRET and raw_value == "no":
            self._editor = None
            self._feedback = None
            return
        if editor.action is _EditorAction.RESET_SETTINGS and raw_value == "no":
            self._editor = None
            self._feedback = None
            return
        try:
            self._apply_editor(editor, raw_value)
        except AniShiftError, OSError:
            self._feedback = _Feedback("✗ Nie udało się zapisać ustawienia", "error")
            return
        except TypeError, ValueError:
            self._feedback = _Feedback(self._validation_message(editor.setting_id), "error")
            return
        self._editor = None
        message: str = (
            "✓ Przywrócono ustawienia domyślne" if editor.action is _EditorAction.RESET_SETTINGS else _SAVED_MESSAGE
        )
        self._feedback = _Feedback(message, "success")
        self._refresh_menu()

    def _apply_editor(self, editor: _Editor, raw_value: str) -> None:
        if editor.action is _EditorAction.UPDATE_SETTING:
            spec: SettingSpec = _required_spec(self._catalog_snapshot().specs, editor.setting_id)
            value: SettingValue = parse_setting_input(spec, raw_value)
            self._service.update_setting(editor.setting_id, value)
            return
        if editor.action is _EditorAction.SELECT_MODEL:
            option: _Option = editor.options[editor.selected]
            self._service.select_translation_model(option.provider_id, option.value)
            return
        if editor.action is _EditorAction.UPDATE_SECRET:
            self._service.update_secret(editor.setting_id, raw_value)
            return
        if editor.action is _EditorAction.UPDATE_ENVIRONMENT:
            spec = _required_spec(self._catalog_snapshot().specs, editor.setting_id)
            value = parse_setting_input(spec, raw_value)
            self._service.update_environment_setting(editor.setting_id, str(value))
            return
        if editor.action is _EditorAction.REMOVE_SECRET and raw_value == "yes":
            self._service.update_secret(editor.setting_id, None)
            return
        if editor.action is _EditorAction.RESET_SETTINGS and raw_value == "yes":
            self._service.reset_settings()

    def _validation_message(self, setting_id: str) -> str:
        try:
            spec: SettingSpec = _required_spec(self._catalog_snapshot().specs, setting_id)
        except AniShiftError, OSError, ValueError:
            return "✗ Nieprawidłowa wartość"
        if spec.minimum is not None and spec.maximum is not None:
            return f"✗ Nieprawidłowa wartość · Zakres: {spec.minimum:g}–{spec.maximum:g}"
        return "✗ Nieprawidłowa wartość"

    def _load_output(self) -> None:
        try:
            preset: AutoPreset = self._default_preset()
        except AniShiftError, OSError, TypeError, ValueError:
            self._output_products = set()
            self._feedback = _Feedback("✗ Nie można wczytać ustawień wyniku", "error")
            return
        public: frozenset[ProductKind] = frozenset(product for product, _label in _PRODUCTS)
        self._output_products = set(preset.products.requested_products & public)

    def _save_output(self) -> None:
        if not self._output_products:
            self._feedback = _Feedback("✗ Wybierz co najmniej jeden wynik", "error")
            return
        try:
            current: AutoPreset = self._default_preset()
            requested: frozenset[ProductKind] = frozenset(self._output_products)
            products: ProductIntent = ProductIntent(
                requested_products=requested,
                burn_subtitle_product=(
                    current.products.burn_subtitle_product if ProductKind.MP4 in requested else BurnSubtitleProduct.NONE
                ),
                mkv_tracks=current.products.mkv_tracks if ProductKind.MKV in requested else frozenset(),
                mp4_audio_source=(
                    current.products.mp4_audio_source if ProductKind.MP4 in requested else Mp4AudioSource.AUTO
                ),
            )
            draft: AutoPresetDraft = AutoPresetDraft(
                preset_id=current.preset_id,
                name=current.name,
                products=products,
                subtitle_source_policy=current.subtitle_source_policy,
                translation_action=current.translation_action,
                source_subtitle_language=current.source_subtitle_language,
                subtitle_output_format=current.subtitle_output_format,
            )
            self._service.save_preset(draft)
        except AniShiftError, OSError, TypeError, ValueError:
            self._feedback = _Feedback("✗ Nie udało się zapisać ustawień wyniku", "error")
            return
        self._feedback = _Feedback(_SAVED_MESSAGE, "success")
        self._category = None
        self._selected = 0
        self._offset = 0
        self._refresh_menu()

    def _default_preset(self) -> AutoPreset:
        return self._service.get_preset(self._service.default_preset_id())

    def _start_probe(self) -> None:
        try:
            catalog: ModelCatalog = self._service.model_catalog()
            alias: str = self._service.settings_snapshot().llm_provider_model_id
        except AniShiftError:
            self._feedback = _Feedback("✗ Nie można wczytać katalogu modeli", "error")
            return
        if alias not in catalog.models:
            self._feedback = _Feedback("✗ Najpierw wybierz model tłumaczenia", "error")
            return
        with self._lock:
            self._generation += 1
            generation: int = self._generation
            self._busy = True
            self._feedback = _Feedback("Testowanie połączenia…", "info")
        worker: threading.Thread = threading.Thread(
            target=self._run_probe,
            args=(alias, generation),
            name="anishift-connection-probe",
            daemon=True,
        )
        worker.start()

    def _run_probe(self, alias: str, generation: int) -> None:
        try:
            result: ModelProbeResult = self._service.probe_model(alias)
            success: bool = result.availability is ModelAvailability.VERIFIED
        except AniShiftError, OSError, TypeError, ValueError:
            success = False
        with self._lock:
            if generation != self._generation:
                return
            self._busy = False
            self._feedback = _Feedback(
                "✓ Połączenie działa" if success else "✗ Test połączenia nie powiódł się",
                "success" if success else "error",
            )
        self._invalidate()

    def _render_menu(self, columns: int, rows: int) -> Text:
        title: str = _menu_title(self._category, self._connection)
        back: _MenuItem | None = self._items[-1] if self._items and self._items[-1].key == _BACK_KEY else None
        scrollable: tuple[_MenuItem, ...] = self._items[:-1] if back is not None else self._items
        feedback_rows: int = 1 if self._feedback is not None else 0
        row_budget: int = max(rows - 6 - feedback_rows - int(back is not None), 1)
        sections: tuple[str, ...] = tuple(item.section for item in scrollable)
        start, end = _visible_window(
            sections,
            min(self._selected, max(len(scrollable) - 1, 0)),
            self._offset,
            row_budget,
            follow_cursor=self._follow_cursor,
        )
        # The row budget is only known here, so this is where a corrected offset
        # has to be kept for the next key press to scroll from.
        self._offset = start
        self._visible_count = end - start
        visible: tuple[_MenuItem, ...] = scrollable[start:end]
        has_above: bool = start > 0
        has_below: bool = end < len(scrollable)
        option_rows: int = _sectioned_row_count(tuple(item.section for item in visible))
        body_rows: int = option_rows + int(has_above) + int(has_below) + int(back is not None) + 4 + feedback_rows
        left: int = _menu_left_padding(columns, visible if back is None else (*visible, back))
        content: Text = Text("\n" * max((max(rows - 1, 1) - body_rows) // 2, 0))
        content.append(" " * left)
        content.append(_truncate_right(title, max(columns - left, 1)), style="white_bold")
        content.append("\n\n")
        if has_above:
            content.append(" " * left)
            content.append("↑ więcej\n", style="gray")
        previous_section: str = ""
        for index, item in enumerate(visible, start=start):
            if item.section and item.section != previous_section:
                content.append(" " * left)
                content.append(f"{_truncate_right(item.section, max(columns - left, 1))}\n", style="gray")
                previous_section = item.section
            content.append(" " * left)
            content.append(f"{_POINTER} " if index == self._selected else "  ", style="purple_bold")
            available: int = max(columns - left - 2, 1)
            current: str = _truncate_right(item.current, max(available // 2, 1)) if item.current else ""
            label_width: int = max(available - len(current) - (3 if current else 0), 1)
            content.append(
                _truncate_right(item.label, label_width),
                style="purple_bold" if index == self._selected else "white_bold",
            )
            if current:
                content.append(f" · {current}", style="gray")
            content.append("\n")
        if has_below:
            content.append(" " * left)
            content.append("↓ więcej\n", style="gray")
        if back is not None:
            selected_back: bool = self._selected == len(self._items) - 1
            content.append(" " * left)
            content.append(f"{_POINTER} " if selected_back else "  ", style="purple_bold")
            content.append(
                _truncate_right(back.label, max(columns - left - 2, 1)),
                style="purple_bold" if selected_back else "white_bold",
            )
            content.append("\n")
        self._append_feedback(content, left, columns)
        content.append(" " * left)
        content.append(_MENU_HINT, style="gray")
        return content

    def _render_output(self, columns: int, rows: int) -> Text:
        save_index: int = len(_PRODUCTS)
        reset_index: int = save_index + 1
        back_index: int = reset_index + 1
        body_rows: int = len(_PRODUCTS) + 7 + (1 if self._feedback is not None else 0)
        labels: tuple[_MenuItem, ...] = tuple(_MenuItem("", label) for _product, label in _PRODUCTS)
        actions: tuple[_MenuItem, ...] = (
            _MenuItem("", "Zapisz"),
            _MenuItem("", "Przywróć domyślne"),
            _MenuItem("", _BACK_LABEL),
        )
        left: int = _menu_left_padding(columns, (*labels, *actions))
        content: Text = Text("\n" * max((max(rows - 1, 1) - body_rows) // 2, 0))
        content.append(" " * left)
        content.append("WYNIK", style="white_bold")
        content.append("\n\n")
        for index, (product, label) in enumerate(_PRODUCTS):
            content.append(" " * left)
            content.append(f"{_POINTER} " if index == self._selected else "  ", style="purple_bold")
            content.append("● " if product in self._output_products else "○ ", style="purple_bold")
            content.append(label, style="purple_bold" if index == self._selected else "white_bold")
            content.append("\n")
        for index, label in (
            (save_index, "Zapisz"),
            (reset_index, "Przywróć domyślne"),
            (back_index, _BACK_LABEL),
        ):
            content.append(" " * left)
            content.append(f"{_POINTER} " if self._selected == index else "  ", style="purple_bold")
            content.append(label, style="purple_bold" if self._selected == index else "white_bold")
            content.append("\n")
        self._append_feedback(content, left, columns)
        content.append(" " * left)
        content.append(_MULTI_HINT, style="gray")
        return content

    def _render_editor(self, columns: int, rows: int, editor: _Editor) -> Text:
        start, end, body_rows = _editor_window(
            tuple(option.group for option in editor.options),
            editor.selected,
            editor.offset,
            rows,
            self._feedback is not None,
        )
        editor.offset = start
        editor.visible_count = end - start
        visible: tuple[_Option, ...] = editor.options[start:end]
        has_above: bool = bool(editor.options) and start > 0
        has_below: bool = bool(editor.options) and end < len(editor.options)
        width: int = max([len(editor.title), *(len(option.label) + 4 for option in visible)], default=20)
        left: int = max((columns - min(width, columns)) // 2, 0)
        content: Text = Text("\n" * max((max(rows - 1, 1) - body_rows) // 2, 0))
        content.append(" " * left)
        content.append(_truncate_right(editor.title, max(columns - left, 1)), style="white_bold")
        content.append("\n\n")
        if editor.options:
            if has_above:
                content.append(" " * left)
                content.append("↑ więcej\n", style="gray")
            previous_group: str = ""
            for index, option in enumerate(visible, start=start):
                if option.group and option.group != previous_group:
                    content.append(" " * left)
                    content.append(f"{_truncate_right(option.group, max(columns - left, 1))}\n", style="gray")
                    previous_group = option.group
                content.append(" " * left)
                content.append(f"{_POINTER} " if index == editor.selected else "  ", style="purple_bold")
                content.append(f"{_option_marker(editor, option, index)} ", style="purple_bold")
                option_width: int = max(columns - left - 4, 1)
                content.append(
                    _truncate_right(option.label, option_width),
                    style="purple_bold" if index == editor.selected else "white_bold",
                )
                content.append("\n")
            if has_below:
                content.append(" " * left)
                content.append("↓ więcej\n", style="gray")
        else:
            shown: str = "•" * len(editor.buffer) if editor.kind is _EditorKind.PASSWORD else editor.buffer
            available: int = max(columns - left - 4, 1)
            content.append(" " * left)
            content.append(f"{_POINTER} ", style="purple_bold")
            content.append(_truncate_left(shown, available), style="white_bold")
            content.append("█", style="purple_bold")
            content.append("\n")
        self._append_feedback(content, left, columns)
        content.append(" " * left)
        hint: str = _INPUT_HINT if not editor.options else _MENU_HINT
        if editor.kind is _EditorKind.MULTI_SELECT:
            hint = _MULTI_SELECT_HINT
        content.append(hint, style="gray")
        return content

    def _append_feedback(self, content: Text, left: int, columns: int) -> None:
        if self._feedback is None:
            return
        content.append(" " * left)
        content.append(_truncate_right(self._feedback.text, max(columns - left, 1)), style=self._feedback.style)
        content.append("\n")


def _required_spec(specs: dict[str, SettingSpec], setting_id: str) -> SettingSpec:
    try:
        return specs[setting_id]
    except KeyError as error:
        msg = f"Required product setting is absent: {setting_id}"
        raise ValueError(msg) from error


def _required_connection(connection: _Connection | None) -> _Connection:
    if connection is None:
        msg = "Connection action requires an active connection"
        raise ValueError(msg)
    return connection


def _connection_by_key(key: str) -> _Connection:
    for connection in _CONNECTIONS:
        if connection.key == key:
            return connection
    msg = f"Unknown connection key: {key}"
    raise ValueError(msg)


def _selected_option(options: tuple[_Option, ...], current: str) -> int:
    return next((index for index, option in enumerate(options) if option.value == current), 0)


def _selected_model_option(options: tuple[_Option, ...], provider_id: str, model_id: str) -> int:
    return next(
        (
            index
            for index, option in enumerate(options)
            if option.provider_id == provider_id and option.value == model_id
        ),
        0,
    )


def _field_title(setting_id: str) -> str:
    labels: dict[str, str] = {
        field_id: label for field_id, label, _section in (*_GENERAL_FIELDS, *_TRANSLATION_FIELDS, *_TTS_FIELDS)
    }
    return labels.get(setting_id, setting_id).upper()


def _choice_label(setting_id: str, value: str) -> str:
    if setting_id in {"translation_engine", "tts_engine"}:
        return _ENGINE_LABELS.get(value, value)
    labels: dict[tuple[str, str], str] = {
        ("processing_order_policy", "ready_first"): "Najpierw gotowe",
        ("processing_order_policy", "strict_natural"): "Ścisła kolejność plików",
        ("composition_quality_preset", "high"): "Wysoka",
        ("composition_quality_preset", "balanced"): "Zrównoważona",
        ("composition_quality_preset", "compact"): "Kompaktowa",
    }
    if (setting_id, value) in labels:
        return labels[(setting_id, value)]
    return value.replace("_", " ").strip().title()


def _format_value(setting_id: str, value: SettingValue) -> str:
    if value is None:
        return "domyślnie"
    if isinstance(value, bool):
        return "tak" if value else "nie"
    if isinstance(value, float):
        multiplier_fields: frozenset[str] = frozenset(
            {"tts_profile.postprocess_tempo", "tts_profile.engine_options.speed"},
        )
        gain_fields: frozenset[str] = frozenset(
            {"tts_profile.voice_mix_offset_db", "narrator_mix_base_gain_db", "original_gain_db"},
        )
        suffix: str = "×" if setting_id in multiplier_fields else " dB" if setting_id in gain_fields else ""
        return f"{value:g}{suffix}"
    if isinstance(value, str):
        return _choice_label(setting_id, value)
    if isinstance(value, (tuple, frozenset)):
        return ", ".join(str(item) for item in value) or "brak"
    return str(value)


def _format_input(value: SettingValue) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (tuple, frozenset)):
        return ", ".join(str(item) for item in value)
    return str(value)


def _model_group_label(group_id: str) -> str:
    labels: dict[str, str] = {
        "anthropic": "ANTHROPIC",
        "deepseek": "DEEPSEEK",
        "gemini": "GOOGLE GEMINI",
        "openai": "OPENAI",
        "openai_compatible": "OPENAI-COMPATIBLE",
        "openrouter": "OPENROUTER",
        "palantir:openai_chat": "PALANTIR FOUNDRY · OPENAI",
        "palantir:anthropic_messages": "PALANTIR FOUNDRY · ANTHROPIC",
        "palantir:google_generate": "PALANTIR FOUNDRY · GOOGLE",
        "palantir:xai_responses": "PALANTIR FOUNDRY · XAI",
    }
    return labels.get(group_id, group_id.upper())


def _connection_status(status: EnvironmentSettingStatus | None) -> str:
    if status is None or not status.is_configured:
        return "brak"
    return "skonfigurowane · system" if status.is_system_override else "skonfigurowane"


def _menu_title(category: _Category | None, connection: _Connection | None) -> str:
    if connection is not None:
        return connection.label.upper()
    titles: dict[_Category | None, str] = {
        None: "USTAWIENIA",
        _Category.GENERAL: "OGÓLNE",
        _Category.TRANSLATION: "TŁUMACZENIE",
        _Category.TTS: "LEKTOR",
        _Category.CONNECTIONS: "POŁĄCZENIA",
        _Category.OUTPUT: "WYNIK",
    }
    return titles[category]


def _menu_left_padding(columns: int, items: tuple[_MenuItem, ...]) -> int:
    width: int = max(
        (len(item.label) + len(item.current) + (3 if item.current else 0) + 2 for item in items), default=1
    )
    return max((columns - min(width, columns)) // 2, 0)


def _sectioned_row_count(sections: tuple[str, ...]) -> int:
    rows: int = len(sections)
    previous: str = ""
    for section in sections:
        if section and section != previous:
            rows += 1
            previous = section
    return rows


def _numeric_step(spec: SettingSpec) -> float:
    """Return the increment one arrow press applies to a numeric field."""
    span: float | None = None
    if spec.minimum is not None and spec.maximum is not None:
        span = float(spec.maximum) - float(spec.minimum)
    if spec.value_type in {SettingValueType.INTEGER, SettingValueType.OPTIONAL_INTEGER}:
        return _COARSE_INTEGER_STEP if span is not None and span > _COARSE_INTEGER_SPAN else 1
    if span is not None and span <= _FINE_FLOAT_SPAN:
        return _FINE_FLOAT_STEP
    if span is not None and span <= _MEDIUM_FLOAT_SPAN:
        return _COARSE_FLOAT_STEP
    return _COARSE_FLOAT_STEP


def _stepped_number(spec: SettingSpec, current: SettingValue, direction: int) -> tuple[SettingValue] | None:
    """Wrap the neighbouring number, or return ``None`` when the field cannot step.

    The result is wrapped because clearing an optional field is itself a valid step
    towards ``None``, which a bare return could not tell from "not applicable".
    """
    optional: bool = spec.value_type in {
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.OPTIONAL_FLOAT,
    }
    integral: bool = spec.value_type in {SettingValueType.INTEGER, SettingValueType.OPTIONAL_INTEGER}
    step: float = _numeric_step(spec)
    if current is None:
        start: SettingValue = spec.default if spec.default is not None else spec.minimum
        if not isinstance(start, (int, float)) or isinstance(start, bool):
            return None
        return (int(start) if integral else round(float(start), 2),)
    if not isinstance(current, (int, float)) or isinstance(current, bool):
        return None
    raw: float = float(current) + direction * step
    if spec.minimum is not None and raw < float(spec.minimum):
        if optional:
            return (None,)
        return (int(spec.minimum) if integral else float(spec.minimum),)
    if spec.maximum is not None and raw > float(spec.maximum):
        raw = float(spec.maximum)
    return (round(raw) if integral else round(raw, 2),)


def _stepped_choice(spec: SettingSpec, current: SettingValue, direction: int) -> tuple[SettingValue] | None:
    """Wrap the neighbouring allowed value, never wrapping past either end."""
    values: tuple[SettingValue, ...] = spec.allowed_values
    if not values:
        return None
    texts: list[str] = [str(value) for value in values]
    try:
        position: int = texts.index(str(current))
    except ValueError:
        position = 0
    target: int = min(max(position + direction, 0), len(values) - 1)
    if target == position:
        return None
    return (values[target],)


def _stepped_value(spec: SettingSpec, current: SettingValue, direction: int) -> tuple[SettingValue] | None:
    """Wrap the value one arrow press away, or return ``None`` when arrows do not apply."""
    if spec.value_type is SettingValueType.BOOLEAN:
        return (not current if isinstance(current, bool) else True,)
    if spec.value_type in {SettingValueType.STRING_LIST, SettingValueType.STRING_SET, SettingValueType.OBJECT_LIST}:
        return None
    if spec.allowed_values:
        return _stepped_choice(spec, current, direction)
    if spec.value_type in {
        SettingValueType.INTEGER,
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.FLOAT,
        SettingValueType.OPTIONAL_FLOAT,
    }:
        return _stepped_number(spec, current, direction)
    return None


def _navigate_editor(editor: _Editor, key: str) -> bool:
    """Move an editor cursor for one navigation key, reporting whether it applied."""
    length: int = len(editor.options)
    if not length:
        return False
    stride: int = max(editor.visible_count - 1, 1)
    if key == "up":
        editor.selected = (editor.selected - 1) % length
    elif key == "down":
        editor.selected = (editor.selected + 1) % length
    elif key == "pageup":
        editor.selected = max(editor.selected - stride, 0)
    elif key == "pagedown":
        editor.selected = min(editor.selected + stride, length - 1)
    elif key == "home":
        editor.selected = 0
    elif key == "end":
        editor.selected = length - 1
    else:
        return False
    return True


def _option_marker(editor: _Editor, option: _Option, index: int) -> str:
    """Return the filled or hollow marker one editor row shows."""
    if editor.kind is _EditorKind.CONFIRM:
        return "●" if index == editor.selected else "○"
    if editor.kind is _EditorKind.MULTI_SELECT:
        return "●" if option.value in editor.selected_values else "○"
    if editor.action is _EditorAction.SELECT_MODEL:
        return "●" if f"{option.provider_id}\x1f{option.value}" == editor.current_value else "○"
    return "●" if option.value == editor.current_value else "○"


def _window_end(sections: tuple[str, ...], start: int, row_budget: int) -> int:
    """Return the first index past the rows that still fit below ``start``."""
    used: int = int(start > 0)
    previous: str = ""
    end: int = start
    while end < len(sections):
        section: str = sections[end]
        cost: int = 1 + int(bool(section) and section != previous)
        if used + cost + int(end + 1 < len(sections)) > row_budget:
            break
        used += cost
        previous = section or previous
        end += 1
    return max(end, start + 1)


def _visible_window(
    sections: tuple[str, ...],
    cursor: int,
    offset: int,
    row_budget: int,
    *,
    follow_cursor: bool,
) -> tuple[int, int]:
    """Return the visible slice for one scroll offset, honouring section labels.

    The walk is linear because the offset only ever moves forward until the cursor
    fits, unlike the earlier brute force over every start and end pair.
    """
    if not sections:
        return 0, 0
    offset = min(max(offset, 0), len(sections) - 1)
    if not follow_cursor:
        return offset, _window_end(sections, offset, row_budget)
    cursor = min(max(cursor, 0), len(sections) - 1)
    offset = min(offset, cursor)
    end: int = _window_end(sections, offset, row_budget)
    while cursor >= end and offset < len(sections) - 1:
        offset += 1
        end = _window_end(sections, offset, row_budget)
    return offset, end


def _editor_window(
    groups: tuple[str, ...],
    selected: int,
    offset: int,
    rows: int,
    has_feedback: bool,
) -> tuple[int, int, int]:
    row_budget: int = max(rows - 6 - int(has_feedback), 1)
    start, end = _visible_window(groups, selected, offset, row_budget, follow_cursor=True)
    visible_groups: tuple[str, ...] = groups[start:end]
    option_rows: int = _sectioned_row_count(visible_groups) if visible_groups else 1
    body_rows: int = option_rows + int(start > 0) + int(end < len(groups)) + 4 + int(has_feedback)
    return start, end, body_rows


def _truncate_right(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"{value[: width - 1]}…"


def _truncate_left(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    if width <= 1:
        return "…"
    return f"…{value[-(width - 1) :]}"
