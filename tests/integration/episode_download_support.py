from __future__ import annotations

import hashlib
import socket
import subprocess
import threading
import time
import wave
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import hidden_window_options

from anishift.application.acquisition import AcquisitionService
from anishift.application.automation import AutomationOwner
from anishift.application.cancellation import CancellationToken
from anishift.application.episode_selection import AniZipMapping, FranchiseGraph, ListedEpisode, StreamCandidate
from anishift.application.handlers import (
    ExecutionHandlers,
    ExtractionTaskHandler,
    LegacyExtractionAdapter,
    PublishTaskHandler,
    SubtitleTaskHandler,
    TranslationTaskHandler,
    TtsTaskHandler,
)
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.planning import ExecutionPlan, TaskKind
from anishift.application.ready import ReadyStore
from anishift.application.runtime import ProductionHandlerFactory
from anishift.application.service import AppService
from anishift.application.tts_handler import TtsProgressObserver
from anishift.application.watch_state import WatchStateStore
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.platform.binaries import Binary, require_binary
from anishift.platform.local_control import ControlClient, ControlServer, control_endpoint
from anishift.platform.qbittorrent_process import ManagedQBittorrent
from anishift.services.catalog.types import PrequelEntry, SeasonAiring, TitleCandidate, TitleStatus
from anishift.services.extraction import ExtractionService, extract_tracks, identify
from anishift.services.media import DefaultMediaProbe
from anishift.services.subtitles import DisplayedLine, SpokenLine
from anishift.services.torrents import Release, TorrentInfo, parse_release_name
from anishift.services.torrents.errors import TorrentClientError
from anishift.services.translation.protocols import TranslationCancellation, TranslationObserver
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.services.tts.types import (
    AudioFormat,
    SpeechBatch,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SynthesisStatus,
    SynthesizedRequest,
)


def wait_for(predicate: Callable[[], bool], label: str, timeout: float = 60.0) -> None:
    deadline: float = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, label
        time.sleep(0.05)


def _encode(value: object) -> bytes:
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(_encode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(_encode(key) + _encode(value[key]) for key in sorted(value)) + b"e"
    raise TypeError(type(value).__name__)


def make_pack(root: Path) -> tuple[bytes, str]:
    root.mkdir(parents=True)
    subprocess.run(  # noqa: S603
        [
            str(require_binary(Binary.FFMPEG)),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            str(root / "source.mkv"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    video: bytes = (root / "source.mkv").read_bytes()
    (root / "source.mkv").unlink()
    pack: Path = root / "F7-pack"
    pack.mkdir()
    files: list[dict[bytes, object]] = []
    payload: bytes = b""
    for number in (1, 2, 3):
        for suffix, data in (
            ("mkv", video),
            ("srt", f"1\n00:00:00,200 --> 00:00:01,500\nSynthetic episode {number}.\n".encode()),
        ):
            name: str = f"Neko to Ryuu - {number:02}.{suffix}"
            (pack / name).write_bytes(data)
            files.append({b"length": len(data), b"path": [name.encode()]})
            payload += data
    padding: bytes = bytes(173)
    (pack / "padding.bin").write_bytes(padding)
    files.append({b"length": len(padding), b"path": [b"padding.bin"], b"attr": b"p"})
    payload += padding
    assert (len(video) + len(b"1\n00:00:00,200 --> 00:00:01,500\nSynthetic episode 1.\n")) % 16384 != 0
    info: dict[bytes, object] = {
        b"name": b"F7-pack",
        b"files": files,
        b"piece length": 16384,
        b"pieces": b"".join(
            hashlib.sha1(payload[index : index + 16384], usedforsecurity=False).digest()
            for index in range(0, len(payload), 16384)
        ),
    }
    return _encode({b"info": info}), hashlib.sha1(_encode(info), usedforsecurity=False).hexdigest()


def _port() -> int:
    for _attempt in range(20):
        with socket.socket() as tcp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            tcp.bind(("127.0.0.1", 0))
            port: int = tcp.getsockname()[1]
            try:
                udp.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise AssertionError("No shared loopback TCP/UDP port available")


@contextmanager
def private_client(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    requests: list[httpx.Request],
) -> Iterator[tuple[ManagedQBittorrent, httpx.Client, int]]:
    assert require_binary(Binary.QBITTORRENT).is_file()
    peer: int = _port()
    profile: Path = root / "qBittorrent/config/qBittorrent.ini"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        "[BitTorrent]\nSession\\InterfaceAddress=127.0.0.1\nSession\\DHTEnabled=false\n"
        "Session\\LSDEnabled=false\nSession\\PeXEnabled=false\n"
        f"Session\\Port={peer}\n[Preferences]\nConnection\\UPnP=false\nAdvanced\\updateCheck=false\n"
        "Connection\\ResolvePeerCountries=false\n[RSS]\nSession\\EnableProcessing=false\n"
        "AutoDownloader\\EnableProcessing=false\n",
        encoding="utf-8",
    )
    launch: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    children: list[subprocess.Popen[bytes]] = []

    def hidden(command: Sequence[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        if f"--profile={root}" not in command:
            return launch(command, **kwargs)
        child: subprocess.Popen[bytes] = launch(command, **kwargs, **hidden_window_options())
        children.append(child)
        return child

    def record(request: httpx.Request) -> None:
        assert request.url.host == "127.0.0.1"
        requests.append(request)

    with (
        httpx.Client(trust_env=False, timeout=5, event_hooks={"request": [record]}) as http,
        monkeypatch.context() as patch,
    ):
        patch.setattr(subprocess, "Popen", hidden)
        manager: ManagedQBittorrent = ManagedQBittorrent(root, http=http)
        try:
            manager.prepare()
            manager.set_preferences(
                {
                    "ssrf_mitigation": False,
                    "dl_limit": 0,
                    "up_limit": 0,
                    "listen_port": peer,
                    "random_port": False,
                }
            )
            preferences: dict[str, object] = manager.preferences()
            assert int(str(preferences["listen_port"])) == peer
            assert preferences["current_interface_address"] == "127.0.0.1"
            assert all(preferences[key] is False for key in ("dht", "pex", "lsd", "upnp"))
            assert preferences["resolve_peer_countries"] is False
            assert preferences["rss_processing_enabled"] is False
            assert preferences["rss_auto_downloading_enabled"] is False
            assert manager._state is not None
            with httpx.Client(
                base_url=f"http://127.0.0.1:{manager._state.port}/api/v2/",
                trust_env=False,
                timeout=5,
            ) as api:
                api.post("auth/login", data={"username": "admin", "password": manager._password()}).raise_for_status()
                yield manager, api, peer
        finally:
            with suppress(OSError, TorrentClientError):
                manager.close_owned()
            manager.close()
            for child in children:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=10)
            assert all(child.poll() is not None for child in children)
            assert not tuple(root.rglob("*.mmdb"))
            logs: tuple[Path, ...] = tuple(root.rglob("*.log"))
            assert logs
            for log in logs:
                text: str = log.read_text(encoding="utf-8").casefold()
                assert not any(term in text for term in ("db-ip", "dbip", "geolocation", "geolokalizacji"))


class Releases:
    def search(self, query: str, *, categories: Sequence[str] = ()) -> tuple[Release, ...]:
        raise AssertionError((query, categories))


class Catalog:
    def __init__(self, info_hash: str) -> None:
        self.info_hash: str = info_hash
        self.asked: list[int] = []

    def search(self, text: str, *, limit: int = 7) -> tuple[TitleCandidate, ...]:
        raise AssertionError((text, limit))

    def prequel_episodes(self, candidate: TitleCandidate) -> tuple[PrequelEntry, ...]:
        return ()

    def airing_schedule(self, anilist_id: int) -> SeasonAiring:
        return SeasonAiring(anilist_id, TitleStatus.FINISHED, 3, ())

    def franchise(self, anilist_id: int, *, cancel: CancellationToken | None = None) -> FranchiseGraph:
        return FranchiseGraph(
            anilist_id,
            {
                anilist_id: {
                    "id": anilist_id,
                    "title": {"romaji": "Neko to Ryuu", "english": "Neko to Ryuu"},
                    "format": "TV",
                    "status": "FINISHED",
                    "episodes": 3,
                    "synonyms": [],
                    "relations": {"edges": []},
                    "startDate": {"year": 2020, "month": 1, "day": 1},
                }
            },
            frozenset({anilist_id}),
            True,
        )

    def mapping(self, anilist_id: int) -> AniZipMapping:
        return AniZipMapping(
            500,
            "TV",
            3,
            tuple(ListedEpisode(n, season=1, episode=n) for n in (1, 2, 3)),
            (),
            None,
            {str(n): {"episode": str(n), "seasonNumber": 1, "episodeNumber": n} for n in (1, 2, 3)},
        )

    def streams(self, kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]:
        self.asked.append(number)
        name: str = f"Neko to Ryuu - {number:02}.mkv"
        return (StreamCandidate(self.info_hash, "1080p", 99, name, name, None, 1, None, None, (), ()),)

    def movie_streams(self, kitsu_id: int) -> tuple[StreamCandidate, ...]:
        raise AssertionError(kitsu_id)


class Translation:
    def translate_file(  # noqa: PLR0913
        self,
        spoken: list[SpokenLine],
        displayed: list[DisplayedLine],
        *,
        source_lang: str = "auto",
        target_lang: str = "pl",
        cancel: TranslationCancellation | None = None,
        observer: TranslationObserver | None = None,
    ) -> FileTranslation:
        assert spoken
        assert not displayed
        return FileTranslation(
            spoken=tuple(
                TranslatedLine(line.start, line.end, line.text, "Testowy napis.", ("Testowy napis.",), line.style)
                for line in spoken
            ),
            engine_id="deterministic-test",
        )


class Tone:
    def __init__(self, root: Path) -> None:
        self.root: Path = root

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        self.root.mkdir(parents=True, exist_ok=True)
        results: list[SynthesizedRequest] = []
        for index, request in enumerate(batch.requests):
            path: Path = self.root / f"{index}.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(b"\x00\x10\x00\xf0" * 6000)
            clip: SpeechClip = SpeechClip(
                request.request_id,
                path,
                AudioFormat.WAV,
                24000,
                1,
                500,
                "test",
                "test",
                "test",
                1,
                0.0,
                False,
            )
            results.append(SynthesizedRequest(request, SynthesisStatus.SYNTHESIZED, clip, "", 0))
        return SpeechBatchResult(
            batch.scope_id,
            SpeechBatchStatus.COMPLETED,
            tuple(results),
            SpeechBatchStats(len(results), len(results), 0, 0, 0, 0, 0, 0.0, "test", "test", "test"),
            None,
        )

    def cancel(self) -> None:
        pass

    def close(self) -> None:
        pass


class Handlers(ProductionHandlerFactory):
    @staticmethod
    def _tts_handler(
        settings: Settings,
        run_root: Path,
        plan: ExecutionPlan,
        kinds: frozenset[TaskKind],
    ) -> TtsTaskHandler:
        return TtsTaskHandler(
            Tone(run_root / "tones"),
            run_root=run_root,
            group_ranks={group.group_id: rank for rank, group in enumerate(plan.groups)},
        )

    def __call__(
        self,
        run_root: Path,
        plan: ExecutionPlan,
        source_groups: Mapping[str, InspectedSourceGroup],
    ) -> ExecutionHandlers:
        kinds: frozenset[TaskKind] = frozenset(task.kind for task in plan.tasks)
        return ExecutionHandlers(
            ExtractionTaskHandler(
                ExtractionService(),
                run_root=run_root,
                timeout_s=30,
                legacy=LegacyExtractionAdapter(identify, extract_tracks),
            ),
            SubtitleTaskHandler(run_root=run_root),
            TranslationTaskHandler(Translation(), run_root=run_root),
            tts=self._tts_handler(self._settings_provider(), run_root, plan, kinds),
            audio=self._audio_handler(run_root, plan, kinds),
            composition=self._composition_handler(run_root, plan, kinds),
            publish=PublishTaskHandler(
                run_root=run_root, source_groups={key: group.source for key, group in source_groups.items()}
            ),
        )


@contextmanager
def resident(
    root: Path,
    manager: ManagedQBittorrent,
    catalog: Catalog,
) -> Iterator[tuple[AutomationOwner, AppService, ControlClient]]:
    workspace: Path = root / "workspace"
    workspace.mkdir(exist_ok=True)
    acquisition: AcquisitionService = AcquisitionService(
        source=Releases(),
        client=manager,
        torrent_management=manager,
        workspace_root=workspace,
        parse_name=parse_release_name,
        title_catalog=catalog,
        episode_catalog=catalog,
        stream_source=catalog,
    )
    settings: Settings = Settings(_env_file=None)
    service: AppService = AppService(
        workspace_root=workspace,
        settings=settings,
        user_settings=UserSettings(),
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=Handlers(lambda: settings),
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=lambda value: None,
        acquisition=acquisition,
        env_file=root / "absent.env",
    )
    store: WatchStateStore = WatchStateStore(root / "watch/state.json", subscriptions_path=root / "subscriptions.json")
    owner: AutomationOwner = AutomationOwner(
        service, store, instance_id="f7", scan_interval_s=0.1, ready_store=ReadyStore(root / "relocations", workspace)
    )
    thread: threading.Thread = threading.Thread(target=owner.serve, daemon=True)
    thread.start()
    endpoint: str = control_endpoint(root / "watch")
    server: ControlServer = ControlServer(endpoint, b"synthetic-f7", owner.handle, on_disconnect=owner.disconnect)
    owner.attach_broadcast(server.broadcast)
    client: ControlClient = ControlClient(endpoint, b"synthetic-f7", timeout_s=20)
    try:
        yield owner, service, client
    finally:
        client.close()
        owner.request_shutdown()
        thread.join(30)
        server.close()
        service.close()
        assert not thread.is_alive()


def seed_ready(manager: ManagedQBittorrent) -> bool:
    entries: tuple[TorrentInfo, ...] = manager.torrents("AniShift")
    return bool(entries) and entries[0].progress == 1 and entries[0].state in {"stalledUP", "uploading"}
