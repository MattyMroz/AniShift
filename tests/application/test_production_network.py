from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import pytest

from anishift.application import (
    AppService,
    ArtifactKind,
    AutoPreset,
    ExecutionPlan,
    InspectedWorkspace,
    MkvTrackProduct,
    ProductIntent,
    ProductKind,
    RunEvent,
    RunEventKind,
    RunResult,
    SubtitleSourcePolicy,
    TaskKind,
    TaskState,
    TranslationAction,
)
from anishift.application.cancellation import NeverCancelledToken
from anishift.bootstrap import AppContext, create_app_service
from anishift.config.settings import Settings
from anishift.config.user_settings import TtsVoiceProfileSettings, UserSettings
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import CommandResult, SubprocessRunner
from anishift.services.media import DefaultMediaProbe, MediaCatalog, MediaTrackKind
from anishift.services.subtitles import SubtitleSplit, load_subtitles, split_subtitles
from anishift.utils.logger import LoggerMode, setup_mode, shutdown_logger


class _RecordedEvents:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)


def _synthetic_mkv(ffmpeg: Path, source: Path, subtitles: Path) -> None:
    subtitles.write_text(
        "1\n00:00:00,500 --> 00:00:02,000\nGood morning.\n\n2\n00:00:03,000 --> 00:00:04,500\nThank you.\n",
        encoding="utf-8",
    )
    SubprocessRunner().run(
        (
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=10:d=6",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-i",
            str(subtitles),
            "-t",
            "6",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:s:0",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-c:s",
            "srt",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:s:0",
            "language=eng",
            str(source),
        ),
        operation="synthetic_acceptance_input",
        timeout_s=30,
    )


def _assert_products(result: RunResult, plan: ExecutionPlan, workspace: Path, ffmpeg: Path) -> None:
    kinds: dict[str, ArtifactKind] = {artifact.artifact_id: artifact.kind for artifact in plan.artifacts}
    products: dict[ArtifactKind, Path] = {
        kinds[product.artifact_id]: product.path for group in result.groups for product in group.products
    }
    assert set(products) == {ArtifactKind.FULL_PL, ArtifactKind.FINAL_MKV}
    assert all(path.parent == workspace and path.stat().st_size > 0 for path in products.values())
    translated: SubtitleSplit = split_subtitles(load_subtitles(products[ArtifactKind.FULL_PL]), kind="srt")
    assert len(translated.spoken) == 2
    assert all(line.text.strip() and line.text not in {"Good morning.", "Thank you."} for line in translated.spoken)
    catalog: MediaCatalog = DefaultMediaProbe().identify(
        products[ArtifactKind.FINAL_MKV],
        cancel=NeverCancelledToken(),
        timeout_s=30,
    )
    assert len(catalog.tracks_of_kind(MediaTrackKind.VIDEO)) == 1
    assert len(catalog.tracks_of_kind(MediaTrackKind.AUDIO)) == 2
    assert any(track.language in {"pl", "pol"} for track in catalog.tracks_of_kind(MediaTrackKind.SUBTITLES))
    assert catalog.duration_us >= 5_900_000
    decoded: CommandResult = SubprocessRunner().run(
        (
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(products[ArtifactKind.FINAL_MKV]),
            "-map",
            "0:a:1",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ),
        operation="acceptance_narration_decode",
        timeout_s=30,
    )
    volume: re.Match[str] | None = re.search(r"max_volume: (-?\d+(?:\.\d+)?) dB", decoded.stderr)
    assert volume is not None
    assert float(volume.group(1)) > -60.0


@pytest.mark.network
def test_production_mkv_google_edge_publishes_complete_polish_products(tmp_path: Path) -> None:
    binaries: dict[Binary, Path] = {}
    for binary in Binary:
        path: Path | None = resolve_binary(binary)
        if path is None:
            pytest.skip(f"installed {binary.value} is required")
        binaries[binary] = path
    workspace: Path = tmp_path / "workspace"
    workspace.mkdir()
    source: Path = workspace / "acceptance.mkv"
    setup_mode(LoggerMode.PRODUCTION, console_enabled=False, file_path=tmp_path / "acceptance.jsonl")
    started: float = perf_counter()
    try:
        _synthetic_mkv(binaries[Binary.FFMPEG], source, tmp_path / "authored.srt")
        original_digest: bytes = sha256(source.read_bytes()).digest()
        preferences: UserSettings = UserSettings(
            translation_engine="google",
            translation_max_retries=0,
            translation_batch_size=2,
            tts_engine="edge",
            tts_voice_id="pl-PL-ZofiaNeural",
            tts_max_retries=0,
            tts_voice_profiles={"edge:pl-PL-ZofiaNeural": TtsVoiceProfileSettings(concurrency=1)},
            audio_language_priority=("eng",),
            subtitle_language_priority=("eng",),
        )
        context: AppContext = AppContext(Settings(_env_file=None), preferences, workspace)
        service: AppService = create_app_service(context)
        inspected: InspectedWorkspace = service.discover()
        assert len(inspected.groups) == 1
        preset: AutoPreset = AutoPreset(
            "synthetic-acceptance",
            "Synthetic acceptance",
            ProductIntent(
                frozenset({ProductKind.MKV, ProductKind.FULL_PL}),
                mkv_tracks=frozenset({MkvTrackProduct.FULL_PL_SUBTITLES, MkvTrackProduct.NARRATION_AUDIO}),
            ),
            subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
            translation_action=TranslationAction.TRANSLATE,
            source_subtitle_language="eng",
        )
        plan: ExecutionPlan = service.plan_auto((inspected.groups[0].group_id,), preset)
        assert plan.can_execute, tuple(problem.message for problem in plan.problems)
        assert {
            TaskKind.EXTRACT_TRACKS,
            TaskKind.TRANSLATE_SUBTITLES,
            TaskKind.SYNTHESIZE_SPEECH,
            TaskKind.MIX_NARRATION,
            TaskKind.COMPOSE_MKV,
            TaskKind.PUBLISH_ARTIFACT,
        } <= {task.kind for task in plan.tasks}
        assert plan.settings.translation_max_retries == 0
        assert plan.settings.tts_max_retries == 0
        assert plan.settings.tts_voice_id == "pl-PL-ZofiaNeural"
        events: _RecordedEvents = _RecordedEvents()
        result: RunResult = service.execute(plan, events)
        assert result.succeeded, tuple(message for group in result.groups for message in group.error_messages)
        assert events.events[-1].kind is RunEventKind.RUN_FINISHED
        assert events.events[-1].state is TaskState.SUCCEEDED
        assert not any(event.kind is RunEventKind.TASK_RETRY for event in events.events)
        assert sha256(source.read_bytes()).digest() == original_digest
        _assert_products(result, plan, workspace, binaries[Binary.FFMPEG])
        print(  # noqa: T201
            f"E2E_PASS elapsed_s={perf_counter() - started:.3f} tasks={len(plan.tasks)} "
            "translated_lines=2 narration_above_minus60db=True source_preserved=True products=MKV,FULL_PL"
        )
    finally:
        shutdown_logger()
