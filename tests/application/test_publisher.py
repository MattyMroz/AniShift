from __future__ import annotations

import threading
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.application.publisher import ArtifactPublisher, PublishRequest
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.services.audio.errors import AudioCancelledError


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

    def corrupt_copy(_source: Path, target: Path, *, cancel: object) -> None:
        del cancel
        target.write_text("not subtitles", encoding="utf-8")

    monkeypatch.setattr("anishift.application.publisher._copy_cancellable", corrupt_copy)

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


def test_stage_removes_partial_file_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "temp.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nValid\n", encoding="utf-8")
    destination = tmp_path / "Episode.pl.srt"
    staging = tmp_path / "staging.srt"
    cancel = threading.Event()
    cancel.set()

    with pytest.raises(ExecutionError) as raised:
        ArtifactPublisher().stage(_request(source, destination), staging, cancel=cancel)

    assert raised.value.context.code is ErrorCode.CANCELLED
    assert staging.exists() is False


def test_audio_stage_forwards_cancellation_to_probe_and_decode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "temp.eac3"
    source.write_bytes(b"audio")
    destination = tmp_path / "Episode.eac3"
    staging = tmp_path / "staging.eac3"
    cancel = threading.Event()
    observed: list[threading.Event | None] = []

    def inspect(*_args: object, cancel: threading.Event | None = None, **_kwargs: object) -> None:
        observed.append(cancel)

    monkeypatch.setattr("anishift.application.publisher.require_binary", lambda _binary: Path("tool"))
    monkeypatch.setattr("anishift.application.publisher.probe_audio", inspect)
    monkeypatch.setattr("anishift.application.publisher.validate_decode", inspect)

    result = ArtifactPublisher().stage(
        _request(source, destination, ArtifactKind.NARRATION_AUDIO),
        staging,
        cancel=cancel,
    )

    assert result == staging
    assert observed == [cancel, cancel, cancel, cancel]


def test_audio_stage_preserves_cancelled_error_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "temp.eac3"
    source.write_bytes(b"audio")
    staging = tmp_path / "staging.eac3"

    def cancel_probe(*_args: object, **_kwargs: object) -> None:
        context = ErrorContext(code=ErrorCode.CANCELLED, message="audio probe cancelled")
        raise AudioCancelledError(context=context)

    monkeypatch.setattr("anishift.application.publisher.require_binary", lambda _binary: Path("tool"))
    monkeypatch.setattr("anishift.application.publisher.probe_audio", cancel_probe)

    with pytest.raises(ExecutionError) as raised:
        ArtifactPublisher().stage(
            _request(source, tmp_path / "Episode.eac3", ArtifactKind.NARRATION_AUDIO),
            staging,
            cancel=threading.Event(),
        )

    assert raised.value.context.code is ErrorCode.CANCELLED
    assert staging.exists() is False
