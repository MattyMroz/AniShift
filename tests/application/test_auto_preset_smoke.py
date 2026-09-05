from __future__ import annotations

import os
import subprocess
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from hashlib import sha256
from math import cos, pi, sin
from pathlib import Path
from struct import unpack

import pytest

import anishift.application.runtime as runtime_module
import anishift.config.presets as presets_module
import anishift.config.user_settings as user_settings_module
import anishift.platform.binaries as binaries_module
from anishift.application import AppService, ArtifactKind, AutoPreset, ExecutionPlan, RunEvent, RunResult, TaskKind
from anishift.application.cancellation import NeverCancelledToken
from anishift.application.intents import (
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.bootstrap import AppContext, create_app_service
from anishift.cli.interactive.settings import _PRODUCTS, SettingsController, _Editor
from anishift.cli.run import AutoRunRefusal, PreparedAutoRun, execute_auto_run, prepare_auto_run
from anishift.config.presets import AutoPresetFile, load_presets
from anishift.config.settings import Settings
from anishift.config.user_settings import TtsVoiceProfileSettings, UserSettings
from anishift.platform.binaries import TOOL_DIR, Binary
from anishift.services.media import DefaultMediaProbe, MediaCatalog, MediaTrackKind
from anishift.services.subtitles import load_subtitles
from anishift.services.translation.engines.google import service as google_module
from anishift.services.translation.engines.google.constants import LINE_SEPARATOR
from anishift.services.tts import TtsConfig, TtsService
from anishift.services.tts.engines.edge import EdgeTtsEngine
from anishift.services.tts.engines.edge.constants import ZOFIA_VOICE_ID
from anishift.services.tts.engines.edge.types import (
    EdgeAttempt,
    EdgeAudioResponse,
    EdgePatchResult,
    EdgePatchStatus,
    EdgeVoiceList,
)
from anishift.services.tts.types import AudioFormat, VoiceInfo

pytestmark = [pytest.mark.e2e, pytest.mark.smoke]

_BIN_ROOT_ENV = "ANISHIFT_SMOKE_BIN_ROOT"

_PREFIX = "PL "

_EN_LINES = ("Good morning.", "Thank you.")

_PL_LINES = ("Dzień dobry.", "Dziękuję.")

_SIGN_LINE = "EPISODE ONE"

_SIGN_TAG = r"{\pos(320,40)}"

_TIMES = (("00:00:00,400", "00:00:01,400"), ("00:00:01,800", "00:00:02,800"))

_ASS_HEADER = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, Bold, Alignment, MarginV, Encoding\n"
    "Style: Default,Arial,32,&H00FFFFFF,0,2,20,1\n"
    "Style: Sign,Arial,28,&H0000FFFF,0,8,10,1\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)

type _Track = tuple[str, str, str | None]


def _srt(lines: tuple[str, str]) -> str:
    cues: zip[tuple[tuple[str, str], str]] = zip(_TIMES, lines, strict=True)
    return "".join(f"{i}\n{start} --> {end}\n{text}\n\n" for i, ((start, end), text) in enumerate(cues, start=1))


def _ass(lines: tuple[str, str], *, sign: str | None = None) -> str:
    events: str = "".join(
        f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}\n"
        for (start, end), text in zip(_TIMES, lines, strict=True)
    )
    if sign is not None:
        events = f"Dialogue: 0,0:00:00.10,0:00:03.00,Sign,,0,0,0,,{_SIGN_TAG}{sign}\n" + events
    return _ASS_HEADER + events


def _ass_time(srt_time: str) -> str:
    hours: str
    minutes: str
    rest: str
    seconds: str
    millis: str
    hours, minutes, rest = srt_time.split(":")
    seconds, millis = rest.split(",")
    return f"{int(hours)}:{minutes}:{seconds}.{millis[:2]}"


_EN_SRT = _srt(_EN_LINES)

_PL_SRT = _srt(_PL_LINES)

_EN_ASS = _ass(_EN_LINES)

_PL_ASS = _ass(_PL_LINES)

_EN_SIGNED_ASS = _ass(_EN_LINES, sign=_SIGN_LINE)


class _FakeTranslateClient:
    def __init__(self, calls: list[str], timeout_s: float = 0.0) -> None:
        del timeout_s
        self.calls: list[str] = calls

    def translate(self, text: str, *, source_lang: str, target_lang: str) -> str:
        del source_lang, target_lang
        parts: list[str] = text.split(LINE_SEPARATOR)
        self.calls.extend(parts)
        return LINE_SEPARATOR.join(f"{_PREFIX}{part}" for part in parts)

    def close(self) -> None:
        return None


class _FakeEdgeBackend:
    def __init__(self, clip: bytes, synthesized: list[str]) -> None:
        self.clip: bytes = clip
        self.synthesized: list[str] = synthesized

    async def synthesize_once(self, attempt: EdgeAttempt) -> EdgeAudioResponse:
        self.synthesized.append(attempt.text)
        return EdgeAudioResponse(audio=self.clip, format=AudioFormat.MP3, request_time_ms=1.0)

    async def list_voices(self) -> EdgeVoiceList:
        return (VoiceInfo(id=ZOFIA_VOICE_ID, label="Zofia", engine_id="edge", language="pl-PL"),)

    async def close(self) -> None:
        return None


def _ready_patch() -> EdgePatchResult:
    return EdgePatchResult(status=EdgePatchStatus.READY, message="bypassed", detected_version="smoke", changed=False)


def _fake_edge_engine(clip: bytes, synthesized: list[str], config: TtsConfig) -> EdgeTtsEngine:
    return EdgeTtsEngine(config, patcher=_ready_patch, backend_factory=lambda: _FakeEdgeBackend(clip, synthesized))


class _Events:
    def emit(self, event: RunEvent) -> None:
        del event


def _executable(root: Path, binary: Binary) -> Path:
    suffix: str = ".exe" if binaries_module.is_windows() else ""
    return root / TOOL_DIR[binary] / f"{binary.value}{suffix}"


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=60)  # noqa: S603


def _preferences() -> UserSettings:
    return UserSettings(
        translation_engine="google",
        translation_max_retries=0,
        translation_batch_size=2,
        tts_engine="edge",
        tts_voice_id=ZOFIA_VOICE_ID,
        tts_max_retries=0,
        tts_voice_profiles={f"edge:{ZOFIA_VOICE_ID}": TtsVoiceProfileSettings(concurrency=1)},
        audio_language_priority=("jpn",),
        subtitle_language_priority=("eng", "pol"),
    )


@dataclass
class _Harness:
    workspace: Path
    ffmpeg: Path
    preferences: UserSettings
    translated: list[str] = field(default_factory=list)
    synthesized: list[str] = field(default_factory=list)

    def service(self) -> AppService:
        context: AppContext = AppContext(Settings(_env_file=None), deepcopy(self.preferences), self.workspace)
        return create_app_service(context)

    def panel(self) -> SettingsController:
        return SettingsController(self.service(), lambda: None)

    def stored_preset(self) -> AutoPreset:
        stored: AutoPresetFile = load_presets()
        return next(preset for preset in stored.presets if preset.preset_id == stored.default_preset_id)

    def prepare(self) -> tuple[AppService, PreparedAutoRun | AutoRunRefusal]:
        service: AppService = self.service()
        return service, prepare_auto_run(service, load_presets().default_preset_id)

    def plan(self) -> ExecutionPlan:
        _service: AppService
        prepared: PreparedAutoRun | AutoRunRefusal
        _service, prepared = self.prepare()
        assert isinstance(prepared, PreparedAutoRun), prepared
        return prepared.plan

    def refusal(self) -> AutoRunRefusal:
        _service, prepared = self.prepare()
        assert isinstance(prepared, AutoRunRefusal), prepared
        return prepared

    def run(self) -> tuple[ExecutionPlan, RunResult]:
        sources: dict[Path, bytes] = {
            path: sha256(path.read_bytes()).digest() for path in self.workspace.iterdir() if path.is_file()
        }
        service: AppService
        prepared: PreparedAutoRun | AutoRunRefusal
        service, prepared = self.prepare()
        assert isinstance(prepared, PreparedAutoRun), prepared
        result: RunResult = execute_auto_run(service, prepared, _Events())
        assert {path: sha256(path.read_bytes()).digest() for path in sources} == sources
        return prepared.plan, result

    def execute(self) -> dict[ArtifactKind, Path]:
        plan: ExecutionPlan
        result: RunResult
        plan, result = self.run()
        assert result.succeeded, tuple(message for group in result.groups for message in group.error_messages)
        kinds: dict[str, ArtifactKind] = {artifact.artifact_id: artifact.kind for artifact in plan.artifacts}
        products: dict[ArtifactKind, Path] = {
            kinds[item.artifact_id]: item.path for group in result.groups for item in group.products
        }
        assert all(path.parent == self.workspace and path.stat().st_size > 0 for path in products.values())
        return products

    def add_mkv(self, stem: str, tracks: tuple[_Track, ...]) -> Path:
        path: Path = self.workspace / f"{stem}.mkv"
        command: list[str] = [
            str(self.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=5:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
        ]
        inputs: Path = self.workspace.parent / "inputs"
        inputs.mkdir(exist_ok=True)
        for index, (fmt, text, _language) in enumerate(tracks):
            source: Path = inputs / f"{stem}.{index}.{fmt}"
            source.write_text(text, encoding="utf-8")
            command += ["-i", str(source)]
        command += ["-map", "0:v:0", "-map", "1:a:0"]
        command += [item for index in range(len(tracks)) for item in ("-map", f"{index + 2}:s:0")]
        command += ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-metadata:s:a:0", "language=jpn"]
        for index, (fmt, _text, language) in enumerate(tracks):
            command += [f"-c:s:{index}", fmt]
            if language is not None:
                command += [f"-metadata:s:s:{index}", f"language={language}"]
        _run([*command, str(path)])
        return path

    def add_sidecar(self, stem: str, fmt: str, text: str) -> Path:
        path: Path = self.workspace / f"{stem}.{fmt}"
        path.write_text(text, encoding="utf-8")
        return path

    def identify(self, path: Path) -> MediaCatalog:
        return DefaultMediaProbe().identify(path, cancel=NeverCancelledToken(), timeout_s=30)

    def check_mp4(self, path: Path, source: Path, *, narration: bool, burn: bool) -> None:
        _run(
            [
                str(self.ffmpeg),
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ]
        )
        audio: bytes = self.decode(path, ["-t", "0.2", "-map", "0:a:0", "-ar", "8000", "-ac", "1", "-f", "s16le"])
        samples: tuple[int, ...] = unpack(f"<{len(audio) // 2}h", audio)
        original: float = _tone_power(samples, 440)
        voice: float = _tone_power(samples, 330)
        assert original > 0
        assert (voice > original * 0.02) if narration else (voice < original * 0.02)
        options: list[str] = ["-map", "0:v:0", "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo"]
        before: bytes = self.decode(source, options)
        after: bytes = self.decode(path, options)
        assert len(before) == len(after) == 160 * 90
        changed: int = sum(new > old + 30 for old, new in zip(before, after, strict=True))
        assert changed > 10 if burn else changed < 10

    def decode(self, path: Path, options: list[str]) -> bytes:
        command: list[str] = [str(self.ffmpeg), "-v", "error", "-ss", "0.65", "-i", str(path), *options, "pipe:1"]
        return subprocess.run(command, check=True, capture_output=True, timeout=30).stdout  # noqa: S603


@pytest.fixture(scope="module")
def tool_root() -> Path:
    candidates: list[Path] = [binaries_module.external_bin_root()]
    override: str | None = os.environ.get(_BIN_ROOT_ENV)
    if override:
        candidates.append(Path(override))
    missing: dict[str, tuple[str, ...]] = {}
    for root in candidates:
        gaps: tuple[str, ...] = tuple(binary.value for binary in Binary if not _executable(root, binary).is_file())
        if not gaps:
            return root
        missing[str(root)] = gaps
    pytest.skip(f"media tools missing: {missing}; point {_BIN_ROOT_ENV} at a read-only external/bin")


@pytest.fixture(scope="module")
def mp3_clip(tool_root: Path, tmp_path_factory: pytest.TempPathFactory) -> bytes:
    clip: Path = tmp_path_factory.mktemp("smoke-clip") / "clip.mp3"
    _run(
        [
            str(_executable(tool_root, Binary.FFMPEG)),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=0.6",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "96k",
            "-id3v2_version",
            "0",
            "-write_xing",
            "0",
            str(clip),
        ]
    )
    return clip.read_bytes()


@pytest.fixture
def harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_root: Path,
    mp3_clip: bytes,
) -> _Harness:
    for name in tuple(os.environ):
        if name.startswith("ANISHIFT_") or name == "FOUNDRY_API_TOKEN":
            monkeypatch.delenv(name)
    config_dir: Path = tmp_path / "config"
    config_dir.mkdir()
    workspace: Path = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(binaries_module, "external_bin_root", lambda: tool_root)
    monkeypatch.setattr(presets_module, "presets_path", lambda: config_dir / "presets.json")
    monkeypatch.setattr(user_settings_module, "config_path", lambda: config_dir / "settings.json")
    monkeypatch.setattr(runtime_module, "config_path", lambda: config_dir / "settings.json")
    harness: _Harness = _Harness(workspace, _executable(tool_root, Binary.FFMPEG), _preferences())
    monkeypatch.setattr(google_module, "MobileTranslateClient", partial(_FakeTranslateClient, harness.translated))
    engine_factory: partial[EdgeTtsEngine] = partial(_fake_edge_engine, mp3_clip, harness.synthesized)
    monkeypatch.setattr(runtime_module, "TtsService", partial(TtsService, engine_factory=engine_factory))
    return harness


def _activate(panel: SettingsController, key: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == key:
            panel._selected = index
            panel.handle_key("enter")
            return
    raise AssertionError(f"{key} is not on this screen")


def _walk_to(panel: SettingsController, value: str) -> None:
    editor: _Editor | None = panel._editor
    assert editor is not None
    for _ in range(len(editor.options)):
        if editor.options[editor.selected].value == value:
            return
        panel.handle_key("down")
    raise AssertionError(f"{value} is not offered")


def _choose(panel: SettingsController, setting_id: str, value: str) -> None:
    _activate(panel, "category:auto")
    _activate(panel, f"setting:{setting_id}")
    _walk_to(panel, value)
    panel.handle_key("enter")
    assert panel._feedback is None, panel._feedback
    panel.handle_key("escape")


def _type_language(panel: SettingsController, text: str) -> None:
    _activate(panel, "category:auto")
    _activate(panel, "setting:source_subtitle_language")
    for character in text:
        panel.handle_key(f"text:{character}")
    panel.handle_key("enter")
    assert panel._feedback is None, panel._feedback
    panel.handle_key("escape")


def _set_products(panel: SettingsController, kinds: frozenset[ProductKind]) -> None:
    _activate(panel, "category:output")
    for wanted in (True, False):
        for index, (product, _label) in enumerate(_PRODUCTS):
            if (product in kinds) is wanted and (product in panel._output_products) is not wanted:
                panel._selected = index
                panel.handle_key("space")
                assert panel._feedback is None, panel._feedback
    panel.handle_key("escape")


def _set_tracks(panel: SettingsController, tracks: frozenset[str]) -> None:
    _activate(panel, "category:auto")
    _activate(panel, "setting:mkv_tracks")
    editor: _Editor | None = panel._editor
    assert editor is not None
    for option in editor.options:
        if (option.value in tracks) != (option.value in editor.selected_values):
            _walk_to(panel, option.value)
            panel.handle_key("space")
    panel.handle_key("escape")
    panel.close()
    assert panel._feedback is None, panel._feedback
    panel.handle_key("escape")


def _kinds(plan: ExecutionPlan) -> set[TaskKind]:
    return {task.kind for task in plan.tasks}


def _lines(path: Path) -> tuple[str, ...]:
    return tuple(event.plaintext for event in load_subtitles(path))


def _translated(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{_PREFIX}{line}" for line in lines)


def _tone_power(samples: tuple[int, ...], frequency: int) -> float:
    angle: float = 2 * pi * frequency / 8000
    real: float = sum(sample * cos(index * angle) for index, sample in enumerate(samples))
    imaginary: float = sum(sample * sin(index * angle) for index, sample in enumerate(samples))
    return real * real + imaginary * imaginary


def test_default_preset_publishes_polish_subtitles_and_narration_from_embedded_english(harness: _Harness) -> None:
    harness.add_mkv("Episode 01", (("srt", _EN_SRT, "eng"),))

    products: dict[ArtifactKind, Path] = harness.execute()

    assert set(products) == {ArtifactKind.FULL_PL, ArtifactKind.NARRATION_AUDIO}
    assert products[ArtifactKind.FULL_PL].name == "Episode 01.pl.srt"
    assert products[ArtifactKind.NARRATION_AUDIO].name == f"Episode 01.{harness.preferences.tts_output_profile}"
    assert _lines(products[ArtifactKind.FULL_PL]) == _translated(_EN_LINES)
    assert tuple(harness.translated) == _EN_LINES
    assert tuple(harness.synthesized) == _translated(_EN_LINES)


def test_all_seven_products_with_mkv_tracks_burned_mp4_and_narration_audio(harness: _Harness) -> None:
    harness.add_mkv("Episode 02", (("ass", _EN_SIGNED_ASS, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset(ProductKind))
    _set_tracks(panel, frozenset({"source_subtitles", "full_pl_subtitles", "narration_audio"}))
    _choose(panel, "mp4_audio_source", "narration")
    _choose(panel, "burn_subtitle_product", "full_pl")
    panel.close()

    stored: AutoPreset = harness.stored_preset()
    assert stored.products.requested_products == frozenset(ProductKind)
    assert stored.products.mkv_tracks == frozenset(
        {MkvTrackProduct.SOURCE_SUBTITLES, MkvTrackProduct.FULL_PL_SUBTITLES, MkvTrackProduct.NARRATION_AUDIO}
    )
    assert stored.products.mp4_audio_source is Mp4AudioSource.NARRATION
    assert stored.products.burn_subtitle_product is BurnSubtitleProduct.FULL_PL
    plan: ExecutionPlan = harness.plan()
    assert {
        TaskKind.EXTRACT_TRACKS,
        TaskKind.TRANSLATE_SUBTITLES,
        TaskKind.SPLIT_SUBTITLES,
        TaskKind.SYNTHESIZE_SPEECH,
        TaskKind.MIX_NARRATION,
        TaskKind.COMPOSE_MKV,
        TaskKind.COMPOSE_MP4,
        TaskKind.PUBLISH_ARTIFACT,
    } <= _kinds(plan)

    products: dict[ArtifactKind, Path] = harness.execute()

    assert set(products) == {
        ArtifactKind.SOURCE_SUBTITLES,
        ArtifactKind.FULL_PL,
        ArtifactKind.SPOKEN_PL,
        ArtifactKind.DISPLAYED_PL,
        ArtifactKind.NARRATION_AUDIO,
        ArtifactKind.FINAL_MKV,
        ArtifactKind.FINAL_MP4,
    }
    assert products[ArtifactKind.SOURCE_SUBTITLES].name == "Episode 02.ass"
    assert set(_lines(products[ArtifactKind.SOURCE_SUBTITLES])) == {_SIGN_LINE, *_EN_LINES}
    assert set(_lines(products[ArtifactKind.FULL_PL])) == set(_translated((_SIGN_LINE, *_EN_LINES)))
    assert _lines(products[ArtifactKind.SPOKEN_PL]) == _translated(_EN_LINES)
    assert _lines(products[ArtifactKind.DISPLAYED_PL]) == _translated((_SIGN_LINE,))
    catalog: MediaCatalog = harness.identify(products[ArtifactKind.FINAL_MKV])
    assert len(catalog.tracks_of_kind(MediaTrackKind.AUDIO)) == 2
    subtitle_languages: list[str] = sorted(
        track.language or "" for track in catalog.tracks_of_kind(MediaTrackKind.SUBTITLES)
    )
    assert subtitle_languages == ["eng", "eng", "pol"]
    assert products[ArtifactKind.FINAL_MP4].name == "Episode 02.pl.mp4"
    harness.check_mp4(products[ArtifactKind.FINAL_MP4], harness.workspace / "Episode 02.mkv", narration=True, burn=True)
    assert tuple(harness.synthesized) == _translated(_EN_LINES)


def test_source_subtitles_alone_need_no_translation_or_speech(harness: _Harness) -> None:
    harness.add_mkv("Episode 03", (("srt", _EN_SRT, "eng"),))
    _set_products(harness.panel(), frozenset({ProductKind.SOURCE_SUBTITLES}))

    plan: ExecutionPlan = harness.plan()
    assert _kinds(plan).isdisjoint({TaskKind.TRANSLATE_SUBTITLES, TaskKind.SYNTHESIZE_SPEECH})
    products: dict[ArtifactKind, Path] = harness.execute()

    assert set(products) == {ArtifactKind.SOURCE_SUBTITLES}
    assert products[ArtifactKind.SOURCE_SUBTITLES].name == "Episode 03.srt"
    assert _lines(products[ArtifactKind.SOURCE_SUBTITLES]) == _EN_LINES
    assert harness.translated == []
    assert harness.synthesized == []


@pytest.mark.parametrize("policy", ["auto", "sidecar"])
def test_sidecar_policy_prefers_the_exact_stem_sidecar_over_embedded_polish(harness: _Harness, policy: str) -> None:
    harness.add_mkv("Episode 04", (("srt", _PL_SRT, "pol"),))
    harness.add_sidecar("Episode 04", "srt", _EN_SRT)
    _choose(harness.panel(), "subtitle_source_policy", policy)

    plan: ExecutionPlan = harness.plan()

    assert TaskKind.TRANSLATE_SUBTITLES in _kinds(plan)
    assert _kinds(plan).isdisjoint({TaskKind.EXTRACT_SUBTITLES, TaskKind.EXTRACT_TRACKS})
    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _translated(_EN_LINES)
    assert tuple(harness.translated) == _EN_LINES
    assert tuple(harness.synthesized) == _translated(_EN_LINES)


def test_embedded_policy_ignores_the_sidecar(harness: _Harness) -> None:
    harness.add_mkv("Episode 05", (("srt", _PL_SRT, "pol"),))
    harness.add_sidecar("Episode 05", "srt", _EN_SRT)
    _choose(harness.panel(), "subtitle_source_policy", "embedded")

    assert harness.stored_preset().subtitle_source_policy is SubtitleSourcePolicy.EMBEDDED
    plan: ExecutionPlan = harness.plan()

    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert _kinds(plan) & {TaskKind.EXTRACT_SUBTITLES, TaskKind.EXTRACT_TRACKS}
    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _PL_LINES
    assert harness.translated == []
    assert tuple(harness.synthesized) == _PL_LINES


def test_sidecar_policy_refuses_a_source_without_a_sidecar(harness: _Harness) -> None:
    harness.add_mkv("Episode 06", (("srt", _EN_SRT, "eng"),))
    _choose(harness.panel(), "subtitle_source_policy", "sidecar")

    refusal: AutoRunRefusal = harness.refusal()

    assert [blocker.message for blocker in refusal.blockers] == ["No valid exact-stem ASS or SRT sidecar is available"]


def test_no_subtitle_source_refuses_subtitle_products_before_processing(harness: _Harness) -> None:
    harness.add_mkv("Episode 07", (("srt", _EN_SRT, "eng"),))
    _choose(harness.panel(), "subtitle_source_policy", "none")

    refusal: AutoRunRefusal = harness.refusal()

    assert "require a subtitle source" in refusal.blockers[0].message
    assert harness.translated == []


def test_auto_translation_keeps_embedded_polish_untouched(harness: _Harness) -> None:
    harness.add_mkv("Episode 08", (("srt", _PL_SRT, "pol"),))
    _set_products(harness.panel(), frozenset({ProductKind.FULL_PL}))

    plan: ExecutionPlan = harness.plan()
    assert TaskKind.NORMALIZE_SUBTITLES in _kinds(plan)
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    products: dict[ArtifactKind, Path] = harness.execute()

    assert _lines(products[ArtifactKind.FULL_PL]) == _PL_LINES
    assert harness.translated == []


def test_do_not_translate_refuses_an_embedded_english_source(harness: _Harness) -> None:
    harness.add_mkv("Episode 09", (("srt", _EN_SRT, "eng"),))
    _choose(harness.panel(), "translation_action", "do_not_translate")

    refusal: AutoRunRefusal = harness.refusal()

    assert "cannot be published as .pl without translation" in refusal.blockers[0].message


def test_do_not_translate_accepts_a_polish_source(harness: _Harness) -> None:
    harness.add_mkv("Episode 10", (("srt", _PL_SRT, "pol"),))
    _choose(harness.panel(), "translation_action", "do_not_translate")

    plan: ExecutionPlan = harness.plan()

    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert TaskKind.SYNTHESIZE_SPEECH in _kinds(plan)
    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _PL_LINES
    assert harness.translated == []
    assert tuple(harness.synthesized) == _PL_LINES


def test_forced_translation_translates_a_polish_source_again(harness: _Harness) -> None:
    harness.add_mkv("Episode 11", (("srt", _PL_SRT, "pol"),))
    _choose(harness.panel(), "translation_action", "translate")

    assert harness.stored_preset().translation_action is TranslationAction.TRANSLATE
    assert TaskKind.TRANSLATE_SUBTITLES in _kinds(harness.plan())
    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _translated(_PL_LINES)
    assert tuple(harness.translated) == _PL_LINES
    assert tuple(harness.synthesized) == _translated(_PL_LINES)


def test_language_override_marks_an_untagged_track_as_polish(harness: _Harness) -> None:
    harness.add_mkv("Episode 12", (("srt", _PL_SRT, None),))

    assert TaskKind.TRANSLATE_SUBTITLES in _kinds(harness.plan())

    _type_language(harness.panel(), "pl")

    assert harness.stored_preset().source_subtitle_language == "pl"
    plan: ExecutionPlan = harness.plan()
    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(plan)
    assert TaskKind.NORMALIZE_SUBTITLES in _kinds(plan)

    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _PL_LINES
    assert harness.translated == []
    assert tuple(harness.synthesized) == _PL_LINES


def test_language_override_forces_translation_of_a_mistagged_track(harness: _Harness) -> None:
    harness.add_mkv("Episode 13", (("srt", _EN_SRT, "pol"),))

    assert TaskKind.TRANSLATE_SUBTITLES not in _kinds(harness.plan())

    _type_language(harness.panel(), "eng")

    assert TaskKind.TRANSLATE_SUBTITLES in _kinds(harness.plan())
    products: dict[ArtifactKind, Path] = harness.execute()
    assert _lines(products[ArtifactKind.FULL_PL]) == _translated(_EN_LINES)
    assert tuple(harness.translated) == _EN_LINES
    assert tuple(harness.synthesized) == _translated(_EN_LINES)


@pytest.mark.parametrize(
    ("source_format", "source_text", "choice", "expected_name"),
    [
        ("ass", _EN_ASS, "preserve", "Episode 14.pl.ass"),
        ("ass", _EN_ASS, "srt", "Episode 14.pl.srt"),
        ("srt", _EN_SRT, "ass", "Episode 14.pl.ass"),
    ],
)
def test_output_format_controls_the_polish_subtitle_file(
    harness: _Harness,
    source_format: str,
    source_text: str,
    choice: str,
    expected_name: str,
) -> None:
    harness.add_mkv("Episode 14", ((source_format, source_text, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.FULL_PL}))
    _choose(panel, "subtitle_output_format", choice)

    assert harness.stored_preset().subtitle_output_format is SubtitleOutputFormat(choice)
    products: dict[ArtifactKind, Path] = harness.execute()

    assert products[ArtifactKind.FULL_PL].name == expected_name
    assert _lines(products[ArtifactKind.FULL_PL]) == _translated(_EN_LINES)


def test_mkv_with_source_and_displayed_tracks_carries_the_narration(harness: _Harness) -> None:
    harness.add_mkv("Episode 15", (("ass", _EN_SIGNED_ASS, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.MKV}))
    _set_tracks(panel, frozenset({"source_subtitles", "displayed_pl_subtitles", "narration_audio"}))

    products: dict[ArtifactKind, Path] = harness.execute()

    assert set(products) == {ArtifactKind.FINAL_MKV}
    catalog: MediaCatalog = harness.identify(products[ArtifactKind.FINAL_MKV])
    assert len(catalog.tracks_of_kind(MediaTrackKind.AUDIO)) == 2
    subtitle_languages: list[str] = sorted(
        track.language or "" for track in catalog.tracks_of_kind(MediaTrackKind.SUBTITLES)
    )
    assert subtitle_languages == ["eng", "eng", "pol"]
    assert not (harness.workspace / "Episode 15.pl.ass").exists()
    assert tuple(harness.synthesized) == _translated(_EN_LINES)


def test_mkv_without_tracks_only_repacks_the_video(harness: _Harness) -> None:
    harness.add_mkv("Episode 16", (("srt", _EN_SRT, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.MKV}))
    _set_tracks(panel, frozenset())

    assert harness.stored_preset().products.mkv_tracks == frozenset()
    assert _kinds(harness.plan()) == {TaskKind.COMPOSE_MKV}
    products: dict[ArtifactKind, Path] = harness.execute()
    assert set(products) == {ArtifactKind.FINAL_MKV}
    catalog: MediaCatalog = harness.identify(products[ArtifactKind.FINAL_MKV])
    assert len(catalog.tracks_of_kind(MediaTrackKind.VIDEO)) == 1
    assert len(catalog.tracks_of_kind(MediaTrackKind.AUDIO)) == 1
    assert len(catalog.tracks_of_kind(MediaTrackKind.SUBTITLES)) == 1
    assert harness.translated == []
    assert harness.synthesized == []


def test_mp4_with_original_audio_and_burned_displayed_subtitles_needs_no_speech(harness: _Harness) -> None:
    harness.add_mkv("Episode 17", (("ass", _EN_SIGNED_ASS, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.MP4}))
    _choose(panel, "mp4_audio_source", "original")
    _choose(panel, "burn_subtitle_product", "displayed_pl")

    plan: ExecutionPlan = harness.plan()
    assert {TaskKind.TRANSLATE_SUBTITLES, TaskKind.SPLIT_SUBTITLES, TaskKind.COMPOSE_MP4} <= _kinds(plan)
    assert TaskKind.SYNTHESIZE_SPEECH not in _kinds(plan)
    products: dict[ArtifactKind, Path] = harness.execute()

    assert set(products) == {ArtifactKind.FINAL_MP4}
    assert products[ArtifactKind.FINAL_MP4].name == "Episode 17.pl.mp4"
    harness.check_mp4(
        products[ArtifactKind.FINAL_MP4], harness.workspace / "Episode 17.mkv", narration=False, burn=True
    )
    assert harness.synthesized == []


def test_mp4_narration_audio_is_generated_without_the_audio_product(harness: _Harness) -> None:
    harness.add_mkv("Episode 18", (("srt", _EN_SRT, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.MP4}))
    _choose(panel, "mp4_audio_source", "narration")

    plan: ExecutionPlan = harness.plan()

    assert {TaskKind.SYNTHESIZE_SPEECH, TaskKind.MIX_NARRATION, TaskKind.COMPOSE_MP4} <= _kinds(plan)
    assert ArtifactKind.NARRATION_AUDIO not in {
        artifact.kind for artifact in plan.artifacts if artifact.planned_destination is not None
    }
    products: dict[ArtifactKind, Path] = harness.execute()
    assert set(products) == {ArtifactKind.FINAL_MP4}
    assert tuple(harness.synthesized) == _translated(_EN_LINES)
    harness.check_mp4(
        products[ArtifactKind.FINAL_MP4], harness.workspace / "Episode 18.mkv", narration=True, burn=False
    )


def test_burning_source_subtitles_needs_no_polish_text(harness: _Harness) -> None:
    harness.add_mkv("Episode 19", (("ass", _EN_ASS, "eng"),))
    panel: SettingsController = harness.panel()
    _set_products(panel, frozenset({ProductKind.MP4}))
    _choose(panel, "burn_subtitle_product", "source")
    _choose(panel, "translation_action", "do_not_translate")

    plan: ExecutionPlan = harness.plan()

    assert TaskKind.COMPOSE_MP4 in _kinds(plan)
    assert _kinds(plan).isdisjoint({TaskKind.TRANSLATE_SUBTITLES, TaskKind.SYNTHESIZE_SPEECH})

    products: dict[ArtifactKind, Path] = harness.execute()
    assert set(products) == {ArtifactKind.FINAL_MP4}
    assert harness.translated == []
    assert harness.synthesized == []
    harness.check_mp4(
        products[ArtifactKind.FINAL_MP4], harness.workspace / "Episode 19.mkv", narration=False, burn=True
    )


@pytest.mark.parametrize("with_narration", [False, True])
def test_mp4_auto_audio_follows_requested_narration(harness: _Harness, with_narration: bool) -> None:
    source: Path = harness.add_mkv("Auto audio", (("srt", _PL_SRT, "pol"),))
    requested: set[ProductKind] = {ProductKind.MP4}
    if with_narration:
        requested.add(ProductKind.NARRATION_AUDIO)
    _set_products(harness.panel(), frozenset(requested))
    products: dict[ArtifactKind, Path] = harness.execute()
    assert (ArtifactKind.NARRATION_AUDIO in products) is with_narration
    assert tuple(harness.synthesized) == (_PL_LINES if with_narration else ())
    assert harness.translated == []
    harness.check_mp4(products[ArtifactKind.FINAL_MP4], source, narration=with_narration, burn=False)


def test_displayed_products_from_a_plain_srt_fail_at_execution_without_publishing(harness: _Harness) -> None:
    harness.add_mkv("Episode 20", (("srt", _EN_SRT, "eng"),))
    _set_products(harness.panel(), frozenset({ProductKind.DISPLAYED_PL}))

    _plan: ExecutionPlan
    result: RunResult
    _plan, result = harness.run()

    assert not result.succeeded
    assert result.groups[0].error_messages == ("Requested subtitle stream is empty: displayed_pl",)
    assert not (harness.workspace / "Episode 20.displayed.pl.srt").exists()


def test_an_empty_workspace_is_refused_before_planning(harness: _Harness) -> None:
    refusal: AutoRunRefusal = harness.refusal()

    assert refusal.blockers == ()
    assert "no source group" in refusal.message


def test_an_unreadable_video_is_refused_as_not_ready(harness: _Harness) -> None:
    (harness.workspace / "Broken.mkv").write_bytes(b"not a matroska file")

    refusal: AutoRunRefusal = harness.refusal()

    assert "No discovered source group is ready" in refusal.message
    assert harness.translated == []


@pytest.mark.parametrize("language", ["eng", "pol"])
def test_subtitle_language_priority_selects_the_embedded_track(harness: _Harness, language: str) -> None:
    harness.add_mkv("Episode 21", (("srt", _EN_SRT, "eng"), ("srt", _PL_SRT, "pol")))

    assert TaskKind.TRANSLATE_SUBTITLES in _kinds(harness.plan())

    harness.preferences.subtitle_language_priority = (language,)

    assert (TaskKind.TRANSLATE_SUBTITLES in _kinds(harness.plan())) is (language == "eng")
    products: dict[ArtifactKind, Path] = harness.execute()
    expected: tuple[str, ...] = _translated(_EN_LINES) if language == "eng" else _PL_LINES
    assert _lines(products[ArtifactKind.FULL_PL]) == expected
    assert tuple(harness.translated) == (_EN_LINES if language == "eng" else ())
    assert tuple(harness.synthesized) == expected


def test_the_panel_never_writes_a_preset_it_did_not_change(harness: _Harness) -> None:
    panel: SettingsController = harness.panel()
    _activate(panel, "category:auto")
    for _ in range(6):
        panel.handle_key("down")
    panel.handle_key("escape")
    _set_products(panel, frozenset({ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO}))
    panel.close()

    assert not (harness.workspace.parent / "config" / "presets.json").exists()
