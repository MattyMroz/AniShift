from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from textual.widgets import Button, Input, Select, SelectionList
from tui_fakes import app_service, inspected_workspace

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.intents import (
    BurnSubtitleProduct,
    ExternalAudioRole,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
)
from anishift.tui.app import AniShiftApp
from anishift.tui.screens import PreviewScreen
from anishift.tui.state import GroupIntentDraft


def test_copy_to_selected_creates_independent_product_sets() -> None:
    source = GroupIntentDraft("one", {ProductKind.FULL_PL, ProductKind.MP4})
    copied = source.clone_for("two")
    copied.products.remove(ProductKind.MP4)
    assert source.products == {ProductKind.FULL_PL, ProductKind.MP4}
    assert copied.products == {ProductKind.FULL_PL}


async def _assert_three_manual_drafts_plan_independently() -> None:
    service = app_service()
    app = AniShiftApp(service)
    app.session.workspace = inspected_workspace(3)
    app.session.selected_group_ids = {"episode-01", "episode-02", "episode-03"}
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("manual")
        await pilot.pause()
        group_select = app.screen.query_one("#manual-group", Select)
        products = app.screen.query_one("#manual-products", SelectionList)
        products.select(ProductKind.MP4)
        products.select(ProductKind.MKV)
        app.screen.query_one("#manual-burn-subtitle", Select).value = BurnSubtitleProduct.FULL_PL
        app.screen.query_one("#manual-mp4-audio", Select).value = Mp4AudioSource.NARRATION
        app.screen.query_one("#manual-mkv-tracks", SelectionList).select(MkvTrackProduct.FULL_PL_SUBTITLES)
        group_select.value = "episode-02"
        await pilot.pause()
        products = app.screen.query_one("#manual-products", SelectionList)
        products.deselect(ProductKind.FULL_PL)
        products.select(ProductKind.SPOKEN_PL)
        group_select.value = "episode-03"
        await pilot.pause()
        await pilot.click("#manual-preview")
        assert isinstance(app.screen, PreviewScreen)
        intents = service.plan_manual.call_args.args[0]
        by_id = {intent.group_id: intent for intent in intents}
        assert by_id["episode-01"].products.requested_products == frozenset(
            {ProductKind.FULL_PL, ProductKind.MKV, ProductKind.MP4}
        )
        assert by_id["episode-01"].products.burn_subtitle_product is BurnSubtitleProduct.FULL_PL
        assert by_id["episode-01"].products.mkv_tracks == frozenset({MkvTrackProduct.FULL_PL_SUBTITLES})
        assert by_id["episode-01"].products.mp4_audio_source is Mp4AudioSource.NARRATION
        assert by_id["episode-02"].products.requested_products == frozenset({ProductKind.SPOKEN_PL})
        assert by_id["episode-03"].products.requested_products == frozenset({ProductKind.FULL_PL})


def test_manual_keeps_three_independent_group_intents() -> None:
    asyncio.run(_assert_three_manual_drafts_plan_independently())


async def _assert_external_subtitle_is_registered_before_selection() -> None:
    workspace = inspected_workspace(1)
    service = app_service(workspace)
    group = workspace.groups[0]
    path = Path("outside/custom.ass")
    artifact = Artifact(
        "external-subtitle",
        group.group_id,
        ArtifactKind.SOURCE_SUBTITLES,
        path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        path,
        language="eng",
        subtitle_format="ass",
    )
    service.register_external_subtitle.return_value = replace(group, artifacts=(*group.artifacts, artifact))
    app = AniShiftApp(service)
    app.session.workspace = workspace
    app.session.selected_group_ids = {group.group_id}
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("manual")
        await pilot.pause()
        app.screen.query_one("#external-subtitle-path", Input).value = str(path)
        app.screen.query_one("#external-subtitle-language", Input).value = "eng"
        app.screen.query_one("#manual-products", SelectionList).select(ProductKind.MP4)
        app.screen.query_one("#register-subtitle", Button).press()
        await pilot.pause(0.2)
        service.register_external_subtitle.assert_called_once()
        assert app.session.manual_drafts[group.group_id].selected_subtitle_artifact_id == artifact.artifact_id
        assert app.session.manual_drafts[group.group_id].products == {ProductKind.FULL_PL, ProductKind.MP4}


def test_manual_validates_external_subtitle_before_selecting_it() -> None:
    asyncio.run(_assert_external_subtitle_is_registered_before_selection())


async def _assert_external_audio_uses_declared_role() -> None:
    workspace = inspected_workspace(1)
    service = app_service(workspace)
    group = workspace.groups[0]
    path = Path("outside/narration.eac3")
    artifact = Artifact(
        "external-audio",
        group.group_id,
        ArtifactKind.NARRATION_AUDIO,
        path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        path,
    )
    service.register_external_audio.return_value = replace(group, artifacts=(*group.artifacts, artifact))
    app = AniShiftApp(service)
    app.session.workspace = workspace
    app.session.selected_group_ids = {group.group_id}
    async with app.run_test(size=(120, 36)) as pilot:
        await app.open_route("manual")
        await pilot.pause()
        app.screen.query_one("#external-audio-path", Input).value = str(path)
        app.screen.query_one("#external-audio-role", Select).value = ExternalAudioRole.NARRATION_MIX
        app.screen.query_one("#register-audio", Button).press()
        await pilot.pause(0.2)
        assert service.register_external_audio.call_args.args[:3] == (
            group.group_id,
            path,
            ExternalAudioRole.NARRATION_MIX,
        )
        assert app.session.manual_drafts[group.group_id].selected_audio_artifact_id == artifact.artifact_id
        assert app.session.manual_drafts[group.group_id].external_audio_role is ExternalAudioRole.NARRATION_MIX


def test_manual_validates_external_audio_with_declared_role() -> None:
    asyncio.run(_assert_external_audio_uses_declared_role())
