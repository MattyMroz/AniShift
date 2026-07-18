"""Tests for the resource installer (no network — synthetic archives)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import httpx
import pytest

from anishift.platform import binaries
from anishift.platform.binaries import Binary, BinaryNotFoundError
from anishift.setup import installer
from anishift.setup.installer import (
    HashMismatchError,
    InstallCancelledError,
    InstallerError,
    ensure_binary,
    ensure_resource,
    extract_members,
    install_resource,
    is_installed,
    run_setup,
    sha256_file,
)
from anishift.setup.manifest import Member, Resource, UrlSource


def _zip(tmp_path: Path, entries: dict[str, bytes], name: str = "pkg.zip") -> Path:
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        for entry, data in entries.items():
            zf.writestr(entry, data)
    return archive


def _resource(archive: Path, members: list[Member], name: str = "tool") -> Resource:
    return Resource(
        name=name,
        kind="binary",
        source=UrlSource(type="url", url=f"https://example.test/{name}.zip"),
        sha256=sha256_file(archive),
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=tuple(members),
    )


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    file = tmp_path / "x.bin"
    file.write_bytes(b"hello world")
    assert sha256_file(file) == hashlib.sha256(b"hello world").hexdigest()


def test_extract_members_writes_dest_tree(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/bin/tool.exe": b"MZbinary", "root/README.txt": b"junk"})
    resource = _resource(archive, [Member("root/bin/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    extract_members(archive, resource, dest_root)
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZbinary"
    assert not (dest_root / "root").exists()  # only named members land


def test_extract_members_rejects_missing_member(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/other.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    with pytest.raises(InstallerError, match="member not found"):
        extract_members(archive, resource, tmp_path / "bin")


def test_extract_members_rejects_broken_archive(tmp_path: Path) -> None:
    archive = tmp_path / "pkg.zip"
    archive.write_bytes(b"this is not a zip")
    resource = Resource(
        name="tool",
        kind="binary",
        source=UrlSource(type="url", url="https://example.test/tool.zip"),
        sha256="00" * 32,
        size_bytes=1,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )
    with pytest.raises(InstallerError, match="broken zip"):
        extract_members(archive, resource, tmp_path / "bin")


def test_is_installed_true_when_all_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest = tmp_path / "bin" / "tool"
    dest.mkdir(parents=True)
    (dest / "tool.exe").write_bytes(b"x")
    assert is_installed(resource, tmp_path / "bin") is True


def test_is_installed_false_when_missing(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    assert is_installed(resource, tmp_path / "bin") is False


def test_is_installed_false_when_empty_file(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest = tmp_path / "bin" / "tool"
    dest.mkdir(parents=True)
    (dest / "tool.exe").write_bytes(b"")
    assert is_installed(resource, tmp_path / "bin") is False


def test_install_resource_skips_when_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path) -> None:
        raise AssertionError("download must not be called when already present")

    result = install_resource(resource, dest_root=dest_root, download=_never)
    assert result.outcome == "skipped"


def test_install_resource_downloads_and_extracts(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    result = install_resource(resource, dest_root=dest_root, download=_fake)
    assert result.outcome == "installed"
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZ"


def test_install_resource_force_replaces_existing(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"NEW"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"OLD")

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    result = install_resource(resource, dest_root=dest_root, download=_fake, force=True)
    assert result.outcome == "installed"
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"NEW"


def test_install_resource_rejects_bad_hash(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = Resource(
        name="tool",
        kind="binary",
        source=UrlSource(type="url", url="https://example.test/tool.zip"),
        sha256="00" * 32,
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    with pytest.raises(HashMismatchError):
        install_resource(resource, dest_root=dest_root, download=_fake)
    assert not (dest_root / "tool" / "tool.exe").exists()


def test_run_setup_skips_all_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    results = run_setup(resources=(resource,), dest_root=dest_root)
    assert [r.outcome for r in results] == ["skipped"]


def test_run_setup_reports_unavailable_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    monkeypatch.setattr(installer, "is_windows", lambda: False)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")
    assert [r.outcome for r in results] == ["unavailable"]


def test_run_setup_installs_missing_and_isolates_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good_archive = _zip(tmp_path, {"root/good.exe": b"MZ"}, name="good.zip")
    good = _resource(good_archive, [Member("root/good.exe", "good/good.exe")], name="good")
    bad = Resource(
        name="bad",
        kind="binary",
        source=UrlSource(type="url", url="https://example.test/bad.zip"),
        sha256="00" * 32,
        size_bytes=good_archive.stat().st_size,
        archive="zip",
        members=(Member("root/good.exe", "bad/bad.exe"),),
    )
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(good_archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    results = {r.name: r for r in run_setup(resources=(good, bad), dest_root=dest_root)}
    assert results["good"].outcome == "installed"
    assert results["bad"].outcome == "failed"
    assert (dest_root / "good" / "good.exe").read_bytes() == b"MZ"
    assert not (dest_root / "bad" / "bad.exe").exists()


def test_run_setup_swallows_network_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _boom(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _boom)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")  # must NOT raise
    assert [r.outcome for r in results] == ["failed"]


def test_run_setup_marks_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _cancelled(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise InstallCancelledError("cancelled")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _cancelled)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")
    assert [r.outcome for r in results] == ["cancelled"]


def test_ensure_resource_noop_when_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)  # must not raise


def test_ensure_resource_installs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZ"


def test_ensure_resource_maps_network_error_to_domain_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _boom(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _boom)
    with pytest.raises(InstallerError, match="download failed"):
        ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)
    assert not (dest_root / "tool" / "tool.exe").exists()


def test_ensure_resource_propagates_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = Resource(
        name="tool",
        kind="binary",
        source=UrlSource(type="url", url="https://example.test/tool.zip"),
        sha256="00" * 32,
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    with pytest.raises(HashMismatchError):
        ensure_resource("tool", resources=(resource,), dest_root=tmp_path / "bin")


def test_ensure_resource_noop_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected off Windows")

    monkeypatch.setattr(installer, "is_windows", lambda: False)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    ensure_resource(resource.name, resources=(resource,), dest_root=tmp_path / "bin")  # silent no-op


def test_ensure_resource_unknown_name_raises(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="unknown resource"):
        ensure_resource("nope", resources=(), dest_root=tmp_path / "bin")


def test_ensure_binary_resolves_installed_without_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "mkvextract.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: exe)

    def _never(_name: str, **_kwargs: object) -> None:
        raise AssertionError("ensure_resource must not run when the binary resolves")

    monkeypatch.setattr(installer, "ensure_resource", _never)
    assert ensure_binary(Binary.MKVEXTRACT) == exe


def test_ensure_binary_installs_then_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "ffmpeg.exe"
    ensured: list[str] = []

    def _ensure(name: str, **_kwargs: object) -> None:
        ensured.append(name)
        exe.write_bytes(b"MZ")

    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: None)
    monkeypatch.setattr(installer, "ensure_resource", _ensure)
    monkeypatch.setattr(installer, "require_binary", lambda _binary: exe)
    assert ensure_binary(Binary.FFMPEG) == exe
    assert ensured == ["ffmpeg"]


def test_ensure_binary_unmapped_raises_binary_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: None)
    monkeypatch.setattr(binaries, "resolve_binary", lambda _binary: None)

    def _never(_name: str, **_kwargs: object) -> None:
        raise AssertionError("ensure_resource must not run for a binary without a resource")

    monkeypatch.setattr(installer, "ensure_resource", _never)
    with pytest.raises(BinaryNotFoundError):
        ensure_binary(Binary.BALCON)
