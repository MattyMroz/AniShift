from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from anishift.application.artifacts import ArtifactKind
from anishift.application.discovery import SOURCE_SUBTITLE_FORMATS, classify_artifact
from anishift.application.products import (
    AUDIO_PRODUCT_PROFILES,
    EPISODE_STEM_LIMIT,
    SUBTITLE_FORMATS,
    ProductName,
    classify_product,
    episode_stem,
    product_path,
    product_suffix,
    safe_name_part,
)

_PRODUCT_LITERAL: Final[re.Pattern[str]] = re.compile(
    r'\.(spoken|displayed)\.pl|"\.pl"|\.pl\.(ass|srt|txt|mkv|mp4)|\.m4a'
)

_PRODUCTS_MODULE: Final[str] = "anishift/application/products.py"

_SUBTITLE_KINDS: Final[tuple[ArtifactKind, ...]] = (
    ArtifactKind.FULL_PL,
    ArtifactKind.SPOKEN_PL,
    ArtifactKind.DISPLAYED_PL,
)

_CONTAINER_KINDS: Final[tuple[ArtifactKind, ...]] = (ArtifactKind.FINAL_MKV, ArtifactKind.FINAL_MP4)

_LONG_TITLE: Final[str] = " ".join(["Cumulonimbus"] * 20)

_LONG_SERIES: Final[str] = " ".join(["Stratocumulus"] * 20)


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2] / "anishift"


@pytest.mark.parametrize(
    ("kind", "subtitle_format", "expected"),
    [
        (ArtifactKind.FULL_PL, "ass", ".pl.ass"),
        (ArtifactKind.FULL_PL, "srt", ".pl.srt"),
        (ArtifactKind.SPOKEN_PL, "ass", ".spoken.pl.ass"),
        (ArtifactKind.DISPLAYED_PL, "srt", ".displayed.pl.srt"),
    ],
)
def test_subtitle_product_suffix(kind: ArtifactKind, subtitle_format: str, expected: str) -> None:
    assert product_suffix(kind, subtitle_format=subtitle_format) == expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [(ArtifactKind.FINAL_MKV, ".pl.mkv"), (ArtifactKind.FINAL_MP4, ".pl.mp4")],
)
def test_container_product_suffix(kind: ArtifactKind, expected: str) -> None:
    assert product_suffix(kind) == expected


@pytest.mark.parametrize(("profile", "expected"), [("aac", ".m4a"), ("eac3", ".eac3"), ("WAV", ".wav")])
def test_narration_audio_suffix_follows_the_profile(profile: str, expected: str) -> None:
    assert product_suffix(ArtifactKind.NARRATION_AUDIO, audio_profile=profile) == expected


@pytest.mark.parametrize(
    ("kind", "subtitle_format", "audio_profile"),
    [
        (ArtifactKind.FULL_PL, None, None),
        (ArtifactKind.FULL_PL, "vtt", None),
        (ArtifactKind.NARRATION_AUDIO, None, None),
        (ArtifactKind.NARRATION_AUDIO, None, "ac3"),
        (ArtifactKind.VIDEO_MKV, None, None),
    ],
)
def test_unsupported_product_request_is_rejected(
    kind: ArtifactKind,
    subtitle_format: str | None,
    audio_profile: str | None,
) -> None:
    with pytest.raises(ValueError, match=r"format|profile|product name"):
        product_suffix(kind, subtitle_format=subtitle_format, audio_profile=audio_profile)


def test_product_path_joins_the_directory_and_stem(tmp_path: Path) -> None:
    result = product_path(tmp_path, "Zażółć - 04 [1080p]", ArtifactKind.FINAL_MKV)

    assert result == tmp_path / "Zażółć - 04 [1080p].pl.mkv"


@pytest.mark.parametrize("stem", ["", "   "])
def test_product_path_rejects_a_blank_stem(tmp_path: Path, stem: str) -> None:
    with pytest.raises(ValueError, match=r"stem cannot be empty"):
        product_path(tmp_path, stem, ArtifactKind.FULL_PL, subtitle_format="ass")


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("Episode.pl.ass", ProductName("Episode", ArtifactKind.FULL_PL, "ass", None)),
        ("Episode.PL.ASS", ProductName("Episode", ArtifactKind.FULL_PL, "ass", None)),
        ("Episode.spoken.pl.ass", ProductName("Episode", ArtifactKind.SPOKEN_PL, "ass", None)),
        ("Episode.displayed.pl.srt", ProductName("Episode", ArtifactKind.DISPLAYED_PL, "srt", None)),
        ("Episode.pl.mkv", ProductName("Episode", ArtifactKind.FINAL_MKV, None, None)),
        ("Episode.pl.mp4", ProductName("Episode", ArtifactKind.FINAL_MP4, None, None)),
        ("Episode.m4a", ProductName("Episode", ArtifactKind.NARRATION_AUDIO, None, "m4a")),
        ("Episode.eac3", ProductName("Episode", ArtifactKind.NARRATION_AUDIO, None, "eac3")),
    ],
)
def test_classify_product_reads_the_naming_parts(file_name: str, expected: ProductName) -> None:
    assert classify_product(file_name) == expected


@pytest.mark.parametrize("file_name", ["Episode.mkv", "Episode.ass", "Episode.pl", "Episode.txt", ".pl.ass", ".m4a"])
def test_classify_product_ignores_names_that_are_not_products(file_name: str) -> None:
    assert classify_product(file_name) is None


def test_classify_product_prefers_the_longest_matching_suffix() -> None:
    classified = classify_product("Episode.spoken.pl.ass")

    assert classified is not None
    assert classified.kind is ArtifactKind.SPOKEN_PL
    assert classified.stem == "Episode"


def test_classify_product_reads_a_container_suffix_after_any_other_infix() -> None:
    assert classify_product("Episode.spoken.pl.mkv") == ProductName(
        "Episode.spoken",
        ArtifactKind.FINAL_MKV,
        None,
        None,
    )


def test_every_written_product_name_can_be_read_back(tmp_path: Path) -> None:
    requests: list[tuple[ArtifactKind, str | None, str | None]] = [
        (kind, subtitle_format, None) for kind in _SUBTITLE_KINDS for subtitle_format in SUBTITLE_FORMATS
    ]
    requests.extend((kind, None, None) for kind in _CONTAINER_KINDS)
    requests.extend((ArtifactKind.NARRATION_AUDIO, None, profile) for profile in AUDIO_PRODUCT_PROFILES)

    for kind, subtitle_format, audio_profile in requests:
        written = product_path(tmp_path, "Episode", kind, subtitle_format=subtitle_format, audio_profile=audio_profile)
        classified = classify_product(written.name)

        assert classified is not None
        assert classified.stem == "Episode"
        assert classified.kind is kind
        assert classified.subtitle_format == subtitle_format
        expected_codec = None if audio_profile is None else written.suffix[1:]
        assert classified.audio_codec == expected_codec


def test_product_suffixes_live_only_in_the_products_module() -> None:
    root = _package_root()
    offenders = [
        f"{path.relative_to(root.parent).as_posix()}:{number}"
        for path in sorted(root.rglob("*.py"))
        if path.relative_to(root.parent).as_posix() != _PRODUCTS_MODULE
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _PRODUCT_LITERAL.search(line)
    ]

    assert offenders == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Re: Zero", "Re - Zero"),
        ("Re:Zero", "Re-Zero"),
        ("A / B / C", "A - B - C"),
        ("Who | Why \\ How", "Who - Why - How"),
        ('The "Final" Act', "The 'Final' Act"),
        ("Fire Rat`s Cloak", "Fire Rat's Cloak"),
        ("Why? <Really> *now*", "Why Really now"),
        ("Tab\tand\x01control", "Tab andcontrol"),
        ("  Spaced   out ...  ", "Spaced out"),
        ("CON", "_CON"),
        ("aux.mkv", "_aux.mkv"),
        ("***", ""),
    ],
)
def test_safe_name_part_keeps_words_readable_and_windows_safe(text: str, expected: str) -> None:
    assert safe_name_part(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("series", "numbering", "title", "expected"),
    [
        ("Blue Box", (2, 7), "I Need to Tell You Something", "Blue Box - S02E07 - I Need to Tell You Something"),
        ("Blue Box", (2, 7), None, "Blue Box - S02E07"),
        ("Blue Box", (2, 7), "  ", "Blue Box - S02E07"),
        ("One Piece", (1, 1100), "Luffy", "One Piece - S01E1100 - Luffy"),
        ("Bocchi the Rock!", (0, 3), "Recap", "Bocchi the Rock! - S00E03 - Recap"),
        ("Your Name.", None, "Ignored", "Your Name"),
        ("Re:ZERO", (3, 1), "Theft: Part 1?", "Re-ZERO - S03E01 - Theft - Part 1"),
        ("Overgeared", (1, 2), "The End.", "Overgeared - S01E02 - The End"),
        ("Overgeared", (1, 3), "Welcome.pl", "Overgeared - S01E03"),
        ("Overgeared", (1, 4), "Behind the.cover", "Overgeared - S01E04"),
        ("Overgeared", (1, 5), "NUL", "Overgeared - S01E05 - _NUL"),
        ("Galaxy.cover", None, None, "Galaxy cover"),
    ],
)
def test_episode_stem_joins_series_code_and_title(
    series: str, numbering: tuple[int, int] | None, title: str | None, expected: str
) -> None:
    assert episode_stem(series, numbering, title) == expected


@pytest.mark.unit
def test_episode_stem_shortens_the_title_at_a_word_before_the_series() -> None:
    stem = episode_stem("The Iceblade Sorcerer Shall Rule the World", (2, 1), _LONG_TITLE)

    assert len(stem) <= EPISODE_STEM_LIMIT
    assert stem.startswith("The Iceblade Sorcerer Shall Rule the World - S02E01 - Cumulonimbus")
    assert stem.endswith("Cumulonimbus")


@pytest.mark.unit
def test_episode_stem_shortens_the_series_only_when_it_alone_passes_the_limit() -> None:
    stem = episode_stem(_LONG_SERIES, (1, 1), "Pilot")

    assert len(stem) <= EPISODE_STEM_LIMIT
    assert stem.endswith("Stratocumulus - S01E01")
    assert len(episode_stem(_LONG_SERIES, None)) <= EPISODE_STEM_LIMIT


@pytest.mark.unit
def test_episode_stem_refuses_a_series_with_nothing_usable() -> None:
    with pytest.raises(ValueError, match="series title"):
        episode_stem("???", (1, 1), "Pilot")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("series", "numbering", "title"),
    [
        ("Overgeared", (1, 3), "Welcome.pl"),
        ("Overgeared", (1, 4), "Behind the.cover"),
        ("Overgeared", (1, 6), "Spoken.spoken.pl"),
        ("Galaxy.cover", None, None),
        ("Galaxy.pl", None, None),
        ("Blue Box", (2, 7), "Mr. Smith Goes"),
        ("The Iceblade Sorcerer Shall Rule the World", (2, 1), _LONG_TITLE),
    ],
)
def test_episode_stem_names_a_primary_source_and_its_sidecars(
    series: str, numbering: tuple[int, int] | None, title: str | None
) -> None:
    stem = episode_stem(series, numbering, title)

    for suffix in (".mkv", ".mp4"):
        video = classify_artifact(Path(f"{stem}{suffix}"))
        assert video is not None
        assert video.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}
        assert video.stem == stem
    for suffix in SOURCE_SUBTITLE_FORMATS:
        sidecar = classify_artifact(Path(f"{stem}{suffix}"))
        assert sidecar is not None
        assert sidecar.kind is ArtifactKind.SOURCE_SUBTITLES
        assert sidecar.stem == stem
