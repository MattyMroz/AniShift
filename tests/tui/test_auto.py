from __future__ import annotations

import asyncio

from textual.widgets import Select, SelectionList
from tui_fakes import app_service, inspected_workspace

from anishift.application.intents import BurnSubtitleProduct, MkvTrackProduct, Mp4AudioSource, ProductKind
from anishift.application.service import AutoPresetDraft
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import AutoScreen, PreviewScreen


async def _assert_preview_once_does_not_save() -> None:
    service = app_service()
    workspace = inspected_workspace(3)
    app = AniShiftApp(service)
    app.session.workspace = workspace
    app.session.selected_group_ids = {"episode-01", "episode-02"}
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("auto")
        assert isinstance(app.screen, AutoScreen)
        products = app.screen.query_one("#auto-products", SelectionList)
        products.select(ProductKind.SPOKEN_PL)
        products.select(ProductKind.MKV)
        products.select(ProductKind.MP4)
        app.screen.query_one("#auto-burn-subtitle", Select).value = BurnSubtitleProduct.DISPLAYED_PL
        app.screen.query_one("#auto-mp4-audio", Select).value = Mp4AudioSource.NARRATION
        app.screen.query_one("#auto-mkv-tracks", SelectionList).select(MkvTrackProduct.NARRATION_AUDIO)
        await pilot.click("#auto-preview")
        assert isinstance(app.screen, PreviewScreen)
        service.plan_auto.assert_called_once()
        assert service.plan_auto.call_args.args[0] == ("episode-01", "episode-02")
        draft = service.plan_auto.call_args.args[1]
        assert isinstance(draft, AutoPresetDraft)
        assert ProductKind.SPOKEN_PL in draft.products.requested_products
        assert draft.products.burn_subtitle_product is BurnSubtitleProduct.DISPLAYED_PL
        assert draft.products.mkv_tracks == frozenset({MkvTrackProduct.NARRATION_AUDIO})
        assert draft.products.mp4_audio_source is Mp4AudioSource.NARRATION
        service.save_preset.assert_not_called()


def test_auto_previews_one_shared_draft_without_saving() -> None:
    asyncio.run(_assert_preview_once_does_not_save())


async def _assert_save_and_reset_are_explicit() -> None:
    service = app_service()
    app = AniShiftApp(service)
    app.session.selected_group_ids = {"episode-01"}
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("auto")
        products = app.screen.query_one("#auto-products", SelectionList)
        products.select(ProductKind.MP4)
        await pilot.click("#auto-save")
        service.save_preset.assert_called_once()
        await pilot.click("#auto-reset")
        assert set(products.selected) == {ProductKind.FULL_PL}


def test_auto_saves_and_resets_only_through_explicit_actions() -> None:
    asyncio.run(_assert_save_and_reset_are_explicit())
