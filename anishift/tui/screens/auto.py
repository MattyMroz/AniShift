"""Automatic product and preset workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, SelectionList, Static

from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.application.service import AutoPresetDraft
from anishift.tui.widgets import CommandBar, StatusFooter

if TYPE_CHECKING:
    from anishift.tui.app import AniShiftApp


class AutoScreen(Screen[None]):
    """Edit one shared preset draft for every selected group."""

    def compose(self) -> ComposeResult:
        """Compose preset, product selection, and explicit persistence actions."""
        presets: tuple[AutoPreset, ...] = self._shell.service.list_presets()
        with Vertical(classes="route-content"):
            yield Label("Automatic workflow", classes="route-title")
            yield Static(f"Selected groups: {len(self._shell.session.selected_group_ids)}", id="auto-groups")
            yield Select(
                ((preset.name, preset.preset_id) for preset in presets),
                value=presets[0].preset_id,
                allow_blank=False,
                id="auto-preset",
            )
            with Grid(id="auto-options"):
                yield SelectionList[ProductKind](id="auto-products")
                yield Select(
                    (
                        (policy.value, policy)
                        for policy in SubtitleSourcePolicy
                        if policy not in {SubtitleSourcePolicy.EXTERNAL, SubtitleSourcePolicy.READY_POLISH}
                    ),
                    allow_blank=False,
                    id="auto-subtitle-policy",
                )
                yield Select(
                    ((action.value, action) for action in TranslationAction),
                    allow_blank=False,
                    id="auto-translation-action",
                )
                yield Input(placeholder="Source subtitle language, e.g. eng", id="auto-source-language")
                yield Select(
                    ((output_format.value, output_format) for output_format in SubtitleOutputFormat),
                    allow_blank=False,
                    id="auto-subtitle-format",
                )
                yield Select(
                    ((product.value, product) for product in BurnSubtitleProduct),
                    allow_blank=False,
                    id="auto-burn-subtitle",
                )
                yield SelectionList[MkvTrackProduct](
                    *((track.value, track, False) for track in MkvTrackProduct),
                    id="auto-mkv-tracks",
                )
                yield Select(
                    ((source.value, source) for source in Mp4AudioSource),
                    allow_blank=False,
                    id="auto-mp4-audio",
                )
            with Horizontal(classes="screen-actions"):
                yield Button("Preview once", id="auto-preview", variant="primary")
                yield Button("Save preset", id="auto-save")
                yield Button("Reset", id="auto-reset")
                yield Button("Back", id="back")
            yield Static("", id="auto-feedback")
        yield CommandBar()
        yield StatusFooter()

    @property
    def _shell(self) -> AniShiftApp:
        return cast("AniShiftApp", self.app)

    def on_mount(self) -> None:
        """Restore the session draft or load the selected persisted preset."""
        products = self.query_one("#auto-products", SelectionList)
        for product in ProductKind:
            products.add_option((product.value, product, False))
        if self._shell.session.auto_draft is None:
            self._reset_draft()
        else:
            self._render_draft(self._shell.session.auto_draft)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Reset to a newly selected stored preset."""
        if event.select.id == "auto-preset" and isinstance(event.value, str):
            self._reset_draft(event.value)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Preview without persistence, save explicitly, reset, or return."""
        if event.button.id == "back":
            await self._shell.open_route("workspace")
            return
        if event.button.id == "auto-reset":
            self._reset_draft()
            return
        draft: AutoPresetDraft | None = self._draft_from_form()
        if draft is None:
            return
        self._shell.session.auto_draft = draft
        if event.button.id == "auto-save":
            self._shell.service.save_preset(draft)
            self.query_one("#auto-feedback", Static).update("Preset saved")
        elif event.button.id == "auto-preview":
            plan = self._shell.service.plan_auto(tuple(sorted(self._shell.session.selected_group_ids)), draft)
            self._shell.session.preview_plan = plan
            await self._shell.open_route("preview")

    def _reset_draft(self, preset_id: str | None = None) -> None:
        select = self.query_one("#auto-preset", Select)
        resolved_id: str = preset_id or (select.value if isinstance(select.value, str) else "default")
        preset: AutoPreset = self._shell.service.get_preset(resolved_id)
        draft = AutoPresetDraft(
            preset.preset_id,
            preset.name,
            preset.products,
            preset.subtitle_source_policy,
            preset.translation_action,
            preset.source_subtitle_language,
            preset.subtitle_output_format,
        )
        self._shell.session.auto_draft = draft
        self._render_draft(draft)

    def _render_draft(self, draft: AutoPresetDraft) -> None:
        products = self.query_one("#auto-products", SelectionList)
        products.deselect_all()
        for index in range(products.option_count):
            option = products.get_option_at_index(index)
            if option.value in draft.products.requested_products:
                products.select(option.value)
        self.query_one("#auto-subtitle-policy", Select).value = draft.subtitle_source_policy
        self.query_one("#auto-translation-action", Select).value = draft.translation_action
        self.query_one("#auto-source-language", Input).value = draft.source_subtitle_language or ""
        self.query_one("#auto-subtitle-format", Select).value = draft.subtitle_output_format
        self.query_one("#auto-burn-subtitle", Select).value = draft.products.burn_subtitle_product
        tracks = self.query_one("#auto-mkv-tracks", SelectionList)
        tracks.deselect_all()
        for track in draft.products.mkv_tracks:
            tracks.select(track)
        self.query_one("#auto-mp4-audio", Select).value = draft.products.mp4_audio_source

    def _draft_from_form(self) -> AutoPresetDraft | None:
        selected: list[ProductKind] = list(self.query_one("#auto-products", SelectionList).selected)
        if not selected:
            self.query_one("#auto-feedback", Static).update("Select at least one product")
            return None
        current: AutoPresetDraft = self._shell.session.auto_draft or self._fallback_draft()
        burn_product = self.query_one("#auto-burn-subtitle", Select).value
        mp4_audio = self.query_one("#auto-mp4-audio", Select).value
        products = frozenset(selected)
        product_intent = ProductIntent(
            products,
            burn_subtitle_product=(
                burn_product
                if ProductKind.MP4 in products and isinstance(burn_product, BurnSubtitleProduct)
                else BurnSubtitleProduct.NONE
            ),
            mkv_tracks=(
                frozenset(self.query_one("#auto-mkv-tracks", SelectionList).selected)
                if ProductKind.MKV in products
                else frozenset()
            ),
            mp4_audio_source=(
                mp4_audio
                if ProductKind.MP4 in products and isinstance(mp4_audio, Mp4AudioSource)
                else Mp4AudioSource.AUTO
            ),
        )
        policy = self.query_one("#auto-subtitle-policy", Select).value
        action = self.query_one("#auto-translation-action", Select).value
        output_format = self.query_one("#auto-subtitle-format", Select).value
        language: str = self.query_one("#auto-source-language", Input).value.strip()
        return AutoPresetDraft(
            current.preset_id,
            current.name,
            product_intent,
            policy if isinstance(policy, SubtitleSourcePolicy) else current.subtitle_source_policy,
            action if isinstance(action, TranslationAction) else current.translation_action,
            language or None,
            output_format if isinstance(output_format, SubtitleOutputFormat) else current.subtitle_output_format,
        )

    def _fallback_draft(self) -> AutoPresetDraft:
        preset: AutoPreset = self._shell.service.list_presets()[0]
        return AutoPresetDraft(preset.preset_id, preset.name, preset.products)
