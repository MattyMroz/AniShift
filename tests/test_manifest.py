"""Tests for the resource-manifest loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.setup.manifest import (
    ManifestError,
    Resource,
    load_manifest,
    manifest_path,
)


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "bin_hashes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _raw_resource(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "kind": "binary",
        "source": {"type": "url", "url": "https://example.test/a.zip"},
        "sha256": "ab" * 32,
        "size_bytes": 10,
        "archive": "zip",
        "members": [{"archive_path": "a/x.exe", "dest": "tool/x.exe"}],
    }
    raw.update(overrides)
    return raw


def test_real_manifest_loads_both_resources() -> None:
    resources = load_manifest(manifest_path())
    assert {r.name for r in resources} == {"mkvtoolnix", "ffmpeg"}


def test_real_manifest_dests_match_binaries_layout() -> None:
    by_name = {r.name: r for r in load_manifest(manifest_path())}
    assert {m.dest for m in by_name["mkvtoolnix"].members} == {
        "mkvtoolnix/mkvextract.exe",
        "mkvtoolnix/mkvmerge.exe",
    }
    assert {m.dest for m in by_name["ffmpeg"].members} == {"ffmpeg/ffmpeg.exe", "ffmpeg/ffprobe.exe"}


def test_load_returns_typed_resources(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"tool": _raw_resource()}})
    resources = load_manifest(path)
    assert len(resources) == 1
    resource = resources[0]
    assert isinstance(resource, Resource)
    assert resource.name == "tool"
    assert resource.kind == "binary"
    assert resource.source.url == "https://example.test/a.zip"
    assert resource.members[0].dest == "tool/x.exe"


def test_missing_resources_key_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"binaries": {}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_unknown_kind_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(kind="model")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_unknown_source_type_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(source={"type": "hf", "url": "x"})}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_bad_archive_format_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(archive="rar")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_bad_sha256_length_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(sha256="abc")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_empty_members_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(members=[])}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_member_dest_traversal_raises(tmp_path: Path) -> None:
    member = {"archive_path": "a", "dest": "../evil.exe"}
    path = _write(tmp_path, {"resources": {"t": _raw_resource(members=[member])}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_corrupt_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bin_hashes.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope.json")
