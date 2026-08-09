from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.application.publisher import ArtifactPublisher, PublishRequest
from anishift.errors import ExecutionError


def _request(source: Path, destination: Path, kind: ArtifactKind = ArtifactKind.FULL_PL) -> PublishRequest:
    target = Artifact(
        artifact_id="artifact-1",
        group_id="group-1",
        kind=kind,
        path=None,
        state=ArtifactState.MISSING,
        lifetime=ArtifactLifetime.DURABLE,
        planned_destination=destination,
        language="pol" if kind is ArtifactKind.FULL_PL else None,
    )
    return PublishRequest(
        source=source,
        target=target,
        source_group=SourceGroup(
            group_id="group-1",
            stem="Episode",
            directory=destination.parent,
            artifacts=(),
        ),
    )


def test_publish_atomically_replaces_existing_product(tmp_path: Path) -> None:
    source = tmp_path / "temp.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nNew\n", encoding="utf-8")
    destination = tmp_path / "Episode.pl.srt"
    destination.write_text("old", encoding="utf-8")

    artifact = ArtifactPublisher().publish(_request(source, destination))

    assert destination.read_bytes() == source.read_bytes()
    assert artifact.path == destination
    assert artifact.state is ArtifactState.READY
    assert artifact.lifetime is ArtifactLifetime.DURABLE
    assert artifact.language == "pol"


def test_failed_validation_preserves_existing_product(tmp_path: Path) -> None:
    source = tmp_path / "temp.srt"
    source.write_text("not subtitles", encoding="utf-8")
    destination = tmp_path / "Episode.pl.srt"
    destination.write_bytes(b"previous")

    with pytest.raises(ExecutionError):
        ArtifactPublisher().publish(_request(source, destination))

    assert destination.read_bytes() == b"previous"


def test_corrupt_copy_before_replace_preserves_existing_product(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "temp.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nValid\n", encoding="utf-8")
    destination = tmp_path / "Episode.pl.srt"
    destination.write_bytes(b"previous")

    def corrupt_copy(_source: Path, target: Path) -> None:
        target.write_text("not subtitles", encoding="utf-8")

    monkeypatch.setattr("anishift.application.publisher.shutil.copy2", corrupt_copy)

    with pytest.raises(ExecutionError):
        ArtifactPublisher().publish(_request(source, destination))

    assert destination.read_bytes() == b"previous"


def test_publish_rejects_source_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "Episode.pl.ass"

    with pytest.raises(ValueError, match="must differ"):
        _request(source, source)


def test_publish_rejects_kind_suffix_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="suffix"):
        _request(tmp_path / "temp.srt", tmp_path / "Episode.pl.mp4")


def test_publish_rejects_non_durable_artifact_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a durable"):
        _request(tmp_path / "source.mkv", tmp_path / "copy.mkv", ArtifactKind.VIDEO_MKV)


def test_publish_rejects_destination_away_from_source_group(tmp_path: Path) -> None:
    destination = tmp_path / "output" / "Episode.pl.ass"
    request = _request(tmp_path / "temp.ass", destination)

    with pytest.raises(ValueError, match="next to"):
        PublishRequest(
            source=request.source,
            target=request.target,
            source_group=SourceGroup(
                group_id="group-1",
                stem="Episode",
                directory=tmp_path,
                artifacts=(),
            ),
        )


def test_publish_rejects_container_products_owned_by_composition(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a durable"):
        _request(tmp_path / "temp.mkv", tmp_path / "Episode.pl.mkv", ArtifactKind.FINAL_MKV)
