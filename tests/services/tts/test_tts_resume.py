from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from anishift.services.tts import (
    AudioFormat,
    TtsCancelledError,
    TtsClipValidationError,
    TtsResumeError,
    TtsResumeSchemaError,
)
from anishift.services.tts.artifacts import TtsArtifactLayout, sha256_file
from anishift.services.tts.fingerprint import (
    SynthesisIdentity,
    SynthesisProfile,
    synthesis_fingerprint,
)
from anishift.services.tts.resume import (
    ClipExpectation,
    ClipValidation,
    TtsResumeRepository,
)


class _Validator:
    def __init__(self) -> None:
        self.calls: list[Path] = []

    def validate_clip(
        self,
        path: Path,
        expectation: ClipExpectation,
    ) -> ClipValidation | None:
        self.calls.append(path)
        if path.read_bytes().startswith(b"valid"):
            return ClipValidation(
                format=expectation.format,
                sample_rate=24000,
                channels=1,
                duration_ms=1200,
            )
        return None


def _profile(*, voice: str = "pl-PL-ZofiaNeural") -> SynthesisProfile:
    return SynthesisProfile(
        engine_id="edge",
        endpoint_id="edge-consumer-v1",
        provider_model_id="edge-default",
        resolved_voice_id=voice,
        provider_output_id="audio-24khz-mp3",
        provider_source_format=AudioFormat.MP3,
        adapter_version="edge:v1",
        native_rate="+40%",
    )


def _identity(
    request_id: str = "spoken-1",
    *,
    text: str = "Dobry wieczór.",
    voice: str = "pl-PL-ZofiaNeural",
) -> SynthesisIdentity:
    return SynthesisIdentity(
        scope_id="scope-test",
        request_id=request_id,
        text=text,
        chunks=(text,),
        profile=_profile(voice=voice),
    )


def _commit(
    repository: TtsResumeRepository,
    identity: SynthesisIdentity,
    payload: bytes = b"valid-audio",
) -> Path:
    temporary = repository.temporary_clip_path(clip_format=AudioFormat.MP3)
    temporary.write_bytes(payload)
    clip = repository.commit_clip(
        identity,
        temporary,
        ClipExpectation(AudioFormat.MP3),
        can_commit=lambda: True,
    )
    return clip.path


def test_commit_reopen_and_lookup_revalidate_exact_clip(tmp_path: Path) -> None:
    validator = _Validator()
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", validator)
    identity = _identity()
    path = _commit(repository, identity)
    reopened = TtsResumeRepository(tmp_path / "tts", "scope-test", validator)

    hit = reopened.lookup(identity, ClipExpectation(AudioFormat.MP3))

    assert hit is not None
    assert hit.path == path
    assert hit.request_id == identity.request_id
    assert len(validator.calls) >= 2
    assert json.loads((tmp_path / "tts" / "manifest.json").read_text())["schema_version"] == 1


def test_changed_identity_misses_without_deleting_old_version(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    original = _identity()
    original_path = _commit(repository, original)

    assert (
        repository.lookup(
            replace(original, text="Inny tekst.", chunks=("Inny tekst.",)),
            ClipExpectation(AudioFormat.MP3),
        )
        is None
    )
    changed_voice = replace(original, profile=_profile(voice="pl-PL-MarekNeural"))
    changed_path = _commit(repository, changed_voice, b"valid-other")

    assert original_path.is_file()
    assert changed_path.is_file()
    assert original_path != changed_path
    assert repository.lookup(original, ClipExpectation(AudioFormat.MP3)) is not None


def test_opaque_request_id_never_enters_artifact_name(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    identity = _identity("../CON:日本語/" * 100)

    path = _commit(repository, identity)

    assert len(path.name) < 80
    assert identity.request_id not in path.name
    assert path.parent == tmp_path / "tts" / "clips"


def test_hash_mismatch_and_invalid_clip_are_cache_misses(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    identity = _identity()
    path = _commit(repository, identity)
    path.write_bytes(b"valid-but-modified")

    assert repository.lookup(identity, ClipExpectation(AudioFormat.MP3)) is None
    path.write_bytes(b"broken")
    assert repository.lookup(identity, ClipExpectation(AudioFormat.MP3)) is None


def test_exact_valid_orphan_is_adopted_but_random_file_is_ignored(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    validator = _Validator()
    repository = TtsResumeRepository(root, "scope-test", validator)
    identity = _identity()
    layout = TtsArtifactLayout(root)
    orphan = layout.clip_path(
        request_id=identity.request_id,
        fingerprint=synthesis_fingerprint(identity),
        clip_format=AudioFormat.MP3,
    )
    orphan.write_bytes(b"valid-orphan")
    random_file = layout.clips_dir / "random.mp3"
    random_file.write_bytes(b"valid-random")

    hit = repository.lookup(identity, ClipExpectation(AudioFormat.MP3))

    assert hit is not None
    assert hit.path == orphan
    assert random_file.is_file()
    assert (root / "manifest.json").is_file()


def test_corrupt_manifest_is_quarantined_without_partial_trust(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    root.mkdir()
    (root / "manifest.json").write_text('{"schema_version":1,"scope_id":')

    repository = TtsResumeRepository(root, "scope-test", _Validator())

    assert repository.warnings
    assert not (root / "manifest.json").exists()
    assert len(tuple(root.glob("manifest.corrupt.*.json"))) == 1


def test_future_manifest_is_preserved_and_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    root.mkdir()
    manifest = root / "manifest.json"
    manifest.write_text('{"schema_version":99}')

    with pytest.raises(TtsResumeSchemaError):
        TtsResumeRepository(root, "scope-test", _Validator())

    assert manifest.is_file()
    assert not tuple(root.glob("manifest.corrupt.*.json"))


def test_concurrent_commits_keep_every_manifest_entry(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    repository = TtsResumeRepository(root, "scope-test", _Validator())
    identities = tuple(_identity(f"spoken-{index}") for index in range(20))

    with ThreadPoolExecutor(max_workers=8) as executor:
        paths = tuple(executor.map(lambda item: _commit(repository, item), identities))

    manifest = json.loads((root / "manifest.json").read_text())
    assert len(manifest["entries"]) == len(identities)
    assert all(path.is_file() for path in paths)


def test_two_repository_instances_do_not_lose_manifest_updates(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    first = TtsResumeRepository(root, "scope-test", _Validator())
    second = TtsResumeRepository(root, "scope-test", _Validator())

    _commit(first, _identity("spoken-a"))
    _commit(second, _identity("spoken-b"))

    manifest = json.loads((root / "manifest.json").read_text())
    assert len(manifest["entries"]) == 2


def test_same_identity_concurrent_commit_is_first_writer_idempotent(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    identity = _identity()

    with ThreadPoolExecutor(max_workers=2) as executor:
        clips = tuple(
            executor.map(
                lambda payload: _commit(repository, identity, payload),
                (b"valid-first", b"valid-second"),
            ),
        )

    assert clips[0] == clips[1]
    hit = repository.lookup(identity, ClipExpectation(AudioFormat.MP3))
    assert hit is not None
    assert hit.clip_hash == sha256_file(hit.path)


def test_existing_final_clip_cannot_be_reused_as_commit_temp(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    original_path = _commit(repository, _identity("spoken-a"))

    with pytest.raises(TtsResumeError):
        repository.commit_clip(
            _identity("spoken-b"),
            original_path,
            ClipExpectation(AudioFormat.MP3),
            can_commit=lambda: True,
        )

    assert original_path.is_file()


def test_semantically_corrupt_entry_quarantines_whole_manifest(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    repository = TtsResumeRepository(root, "scope-test", _Validator())
    _commit(repository, _identity("spoken-a"))
    _commit(repository, _identity("spoken-b"))
    manifest_path = root / "manifest.json"
    payload = json.loads(manifest_path.read_text())
    first_entry = next(iter(payload["entries"].values()))
    first_entry["clip_path"] = "../../outside.mp3"
    manifest_path.write_text(json.dumps(payload))

    reopened = TtsResumeRepository(root, "scope-test", _Validator())

    assert reopened.warnings
    assert len(tuple(root.glob("manifest.corrupt.*.json"))) == 1
    assert not manifest_path.exists()


def test_clips_directory_redirect_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "clips").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this system")

    with pytest.raises(TtsResumeError):
        TtsResumeRepository(root, "scope-test", _Validator())

    assert not tuple(outside.iterdir())


def test_repository_root_redirect_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "tts"
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this system")

    with pytest.raises(TtsResumeError):
        TtsResumeRepository(root, "scope-test", _Validator())

    assert not tuple(outside.iterdir())


def test_cancelled_and_invalid_commits_never_publish_success(tmp_path: Path) -> None:
    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    identity = _identity()
    cancelled = repository.temporary_clip_path(clip_format=AudioFormat.MP3)
    cancelled.write_bytes(b"valid-audio")

    with pytest.raises(TtsCancelledError):
        repository.commit_clip(
            identity,
            cancelled,
            ClipExpectation(AudioFormat.MP3),
            can_commit=lambda: False,
        )
    assert not cancelled.exists()

    invalid = repository.temporary_clip_path(clip_format=AudioFormat.MP3)
    invalid.write_bytes(b"broken")
    with pytest.raises(TtsClipValidationError):
        repository.commit_clip(
            identity,
            invalid,
            ClipExpectation(AudioFormat.MP3),
            can_commit=lambda: True,
        )
    assert not invalid.exists()
    assert not (tmp_path / "tts" / "manifest.json").exists()


def test_repository_never_touches_sibling_domains(tmp_path: Path) -> None:
    audio = tmp_path / "audio" / "keep.txt"
    scratch = tmp_path / "extract-scratch" / "keep.txt"
    audio.parent.mkdir()
    scratch.parent.mkdir()
    audio.write_text("audio")
    scratch.write_text("scratch")

    repository = TtsResumeRepository(tmp_path / "tts", "scope-test", _Validator())
    _commit(repository, _identity())

    assert audio.read_text() == "audio"
    assert scratch.read_text() == "scratch"
