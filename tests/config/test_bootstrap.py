from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from anishift.application.cancellation import CancellationToken, EventCancellationToken
from anishift.application.service import AppService
from anishift.bootstrap import AppContext, bootstrap, create_app_service
from anishift.config.env_file import update_env_value
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.platform import binaries
from anishift.platform.binaries import Binary
from anishift.services.media import DefaultMediaProbe
from anishift.services.media.types import ContainerKind, MediaCatalog
from anishift.setup import installer
from anishift.setup.installer import InstallerError
from anishift.setup.manifest import Member, Resource, UrlSource


def test_config_imports_in_a_fresh_process() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import anishift.config"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_bootstrap_reloads_changed_dotenv_without_injecting_process_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    monkeypatch.setattr("anishift.bootstrap.env_path", lambda: path)
    monkeypatch.delenv("ANISHIFT_ELEVENLABS_API_KEY", raising=False)
    path.write_text("ANISHIFT_ELEVENLABS_API_KEY=first\n", encoding="utf-8")

    first = bootstrap(create_dirs=False)
    path.write_text("ANISHIFT_ELEVENLABS_API_KEY=second\n", encoding="utf-8")
    second = bootstrap(create_dirs=False)

    assert first.settings.elevenlabs_api_key == "first"
    assert second.settings.elevenlabs_api_key == "second"
    assert "ANISHIFT_ELEVENLABS_API_KEY" not in os.environ


def test_bootstrap_resolves_workspace_override_from_literal_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / ".env"
    workspace = tmp_path / "custom workspace"
    monkeypatch.setattr("anishift.bootstrap.env_path", lambda: path)
    monkeypatch.delenv("ANISHIFT_WORKSPACE_ROOT", raising=False)
    update_env_value(
        "ANISHIFT_WORKSPACE_ROOT",
        str(workspace),
        path=path,
    )

    context = bootstrap(create_dirs=False)

    assert context.workspace_root == workspace.resolve()
    assert "ANISHIFT_WORKSPACE_ROOT" not in os.environ


@pytest.mark.parametrize(("suffix", "expected"), [("mkv", ["mkvtoolnix", "ffmpeg"]), ("mp4", ["ffmpeg"]), ("txt", [])])
def test_production_discovery_prepares_missing_tools_before_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    expected: list[str],
) -> None:
    resources: list[Resource] = []
    archives: dict[str, bytes] = {}
    for name, tools in (
        ("mkvtoolnix", (Binary.MKVMERGE, Binary.MKVEXTRACT)),
        ("ffmpeg", (Binary.FFMPEG, Binary.FFPROBE)),
    ):
        buffer: io.BytesIO = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for binary in tools:
                archive.writestr(f"{binary.value}.exe", b"MZ")
        payload: bytes = buffer.getvalue()
        archives[name] = payload
        resources.append(
            Resource(
                name=name,
                kind="binary",
                source=UrlSource(type="url", url=f"https://example.test/{name}.zip"),
                sha256=hashlib.sha256(payload).hexdigest(),
                size_bytes=len(payload),
                archive="zip",
                members=tuple(Member(f"{binary.value}.exe", f"{name}/{binary.value}.exe") for binary in tools),
            )
        )
    downloaded: list[str] = []
    probed: list[Path] = []
    install_root: Path = tmp_path / "tools"
    workspace: Path = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / f"episode.{suffix}").write_text("source", encoding="utf-8")

    def download(
        resource: Resource,
        target: Path,
        *,
        progress: Callable[[int], None] | None,
        cancel: Callable[[], bool] | None,
    ) -> None:
        assert cancel is not None
        assert not cancel()
        downloaded.append(resource.name)
        target.write_bytes(archives[resource.name])
        if progress is not None:
            progress(len(archives[resource.name]))

    def identify(
        self: DefaultMediaProbe,
        path: Path,
        *,
        cancel: CancellationToken,
        timeout_s: float,
    ) -> MediaCatalog:
        assert downloaded == expected
        assert binaries.require_binary(Binary.FFMPEG).is_file()
        assert binaries.require_binary(Binary.FFPROBE).is_file()
        if suffix == "mkv":
            assert binaries.require_binary(Binary.MKVMERGE).is_file()
            assert binaries.require_binary(Binary.MKVEXTRACT).is_file()
        probed.append(path)
        return MediaCatalog(path, ContainerKind(suffix), 1_000_000, ())

    monkeypatch.setattr(binaries, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(binaries, "external_bin_root", lambda: install_root)
    monkeypatch.setattr(installer, "external_bin_root", lambda: install_root)
    monkeypatch.setattr(installer, "load_manifest", lambda: tuple(resources))
    monkeypatch.setattr(installer, "_download_httpx", download)
    monkeypatch.setattr(installer, "ProgressBarManager", lambda *args, **kwargs: pytest.fail("Unexpected renderer"))
    monkeypatch.setattr(DefaultMediaProbe, "identify", identify)
    context: AppContext = AppContext(Settings(_env_file=None), UserSettings(), workspace)
    service: AppService = create_app_service(context)
    assert downloaded == []
    assert not install_root.exists()

    first = service.discover()
    second = service.discover()

    assert second is first
    assert downloaded == expected
    assert len(probed) == (0 if suffix == "txt" else 1)


def test_production_preparation_failure_is_safe_and_does_not_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "episode.mkv").write_bytes(b"media")

    def fail_install(binary: Binary, **kwargs: object) -> Path:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.NETWORK_ERROR,
                message="secret-url-sentinel",
            )
        )

    monkeypatch.setattr(installer, "ensure_binary", fail_install)
    monkeypatch.setattr(DefaultMediaProbe, "identify", lambda *args, **kwargs: pytest.fail("Probe ran before setup"))
    service: AppService = create_app_service(AppContext(Settings(_env_file=None), UserSettings(), tmp_path))

    with pytest.raises(ExecutionError) as captured:
        service.discover()

    assert captured.value.context.code is ErrorCode.NETWORK_ERROR
    assert "secret-url-sentinel" not in str(captured.value)
    assert "mkvmerge" in str(captured.value)


def test_cancelled_discovery_does_not_prepare_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "episode.mkv").write_bytes(b"media")
    token: EventCancellationToken = EventCancellationToken()
    token.cancel()
    monkeypatch.setattr(installer, "ensure_binary", lambda *args, **kwargs: pytest.fail("Cancelled preparation ran"))
    service: AppService = create_app_service(AppContext(Settings(_env_file=None), UserSettings(), tmp_path))

    with pytest.raises(ExecutionError) as captured:
        service.discover(cancel=token)

    assert captured.value.context.code is ErrorCode.CANCELLED
