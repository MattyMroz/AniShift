"""Typed Textual editor for one UI-neutral setting specification."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, Select, Static, Switch, TextArea
from textual.widgets.select import NoSelection

from anishift.config.field_catalog import SettingSpec, SettingValue, SettingValueType
from anishift.config.user_settings import CustomVoiceSetting


class SettingField(Vertical):
    """Render and parse one setting without owning persistence."""

    def __init__(self, spec: SettingSpec, value: SettingValue, *, environment_configured: bool | None = None) -> None:
        super().__init__(classes="setting-field")
        self.spec: SettingSpec = spec
        self.value: SettingValue = value
        self.environment_configured: bool | None = environment_configured

    def compose(self) -> ComposeResult:
        """Choose a widget solely from the setting catalog contract."""
        yield Label(self.spec.label, classes="setting-label")
        if self.environment_configured is not None:
            status: str = "configured" if self.environment_configured else "missing"
            yield Static(status, classes=f"secret-status {status}", id=self._control_id)
        elif self.spec.value_type is SettingValueType.BOOLEAN:
            yield Switch(bool(self.value), id=self._control_id)
        elif self.spec.value_type is SettingValueType.OBJECT_LIST:
            yield TextArea(self._render_objects(), id=self._control_id)
        elif self.spec.allowed_values and self.spec.value_type not in {
            SettingValueType.STRING_LIST,
            SettingValueType.STRING_SET,
        }:
            yield Select(
                ((str(option), option) for option in self.spec.allowed_values),
                value=self.value,
                allow_blank=False,
                id=self._control_id,
            )
        else:
            yield Input(value=self._render_scalar(), id=self._control_id)
        yield Static(self.spec.description, classes="setting-description")

    @property
    def _control_id(self) -> str:
        return f"setting-{self.spec.setting_id.replace('.', '-')}"

    def read_value(self) -> SettingValue:
        """Parse and locally validate the current widget value."""
        if self.environment_configured is not None:
            return self.value
        if self.spec.value_type is SettingValueType.BOOLEAN:
            switch = self.query_one_optional(Switch)
            value: SettingValue = switch.value if switch is not None else self.value
        elif self.spec.value_type is SettingValueType.OBJECT_LIST:
            area = self.query_one_optional(TextArea)
            value = self._parse_objects(area.text) if area is not None else self.value
        elif self.spec.allowed_values and self.spec.value_type not in {
            SettingValueType.STRING_LIST,
            SettingValueType.STRING_SET,
        }:
            select = self.query_one_optional(Select)
            selected: object | NoSelection = select.value if select is not None else NoSelection()
            value = selected if not isinstance(selected, NoSelection) else self.value  # type: ignore[assignment]
        else:
            input_widget = self.query_one_optional(Input)
            value = self._parse_scalar(input_widget.value) if input_widget is not None else self.value
        self.spec.validate_value(value)
        return value

    def _render_scalar(self) -> str:
        if self.value is None:
            return ""
        if isinstance(self.value, (tuple, frozenset)):
            return ", ".join(str(item) for item in self.value)
        return str(self.value)

    def _render_objects(self) -> str:
        if not isinstance(self.value, tuple):
            return ""
        return "\n".join(
            f"{item.alias} | {item.label} | {item.voice_id}"
            for item in self.value
            if isinstance(item, CustomVoiceSetting)
        )

    def _parse_scalar(self, raw: str) -> SettingValue:
        value_type: SettingValueType = self.spec.value_type
        stripped: str = raw.strip()
        if (
            value_type
            in {
                SettingValueType.OPTIONAL_STRING,
                SettingValueType.OPTIONAL_INTEGER,
                SettingValueType.OPTIONAL_FLOAT,
            }
            and not stripped
        ):
            return None
        if value_type in {SettingValueType.INTEGER, SettingValueType.OPTIONAL_INTEGER}:
            return int(stripped)
        if value_type in {SettingValueType.FLOAT, SettingValueType.OPTIONAL_FLOAT}:
            return float(stripped)
        values: tuple[str, ...] = tuple(item.strip() for item in stripped.split(",") if item.strip())
        if value_type is SettingValueType.STRING_LIST:
            return values
        if value_type is SettingValueType.STRING_SET:
            return frozenset(values)
        return stripped

    def _parse_objects(self, raw: str) -> tuple[CustomVoiceSetting, ...]:
        values: list[CustomVoiceSetting] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            parts: tuple[str, ...] = tuple(part.strip() for part in line.split("|"))
            if len(parts) != len(self.spec.object_fields) or any(not part for part in parts):
                msg = "Custom voices require: alias | label | provider voice ID"
                raise ValueError(msg)
            values.append(CustomVoiceSetting(*parts))
        return tuple(values)
