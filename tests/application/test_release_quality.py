from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from itertools import permutations

import pytest

from anishift.application.release_quality import (
    AudioClass,
    LanguageDeclaration,
    LanguageSource,
    PolishClass,
    ReleaseTraits,
    ResolutionClass,
    class_key,
    language_code,
    quality_score,
    release_traits,
    resolution_class,
    seed_points,
)


def _declaration(  # noqa: PLR0913 - explicit declaration fields keep precedence cases readable
    source: LanguageSource = LanguageSource.TSUKIHIME,
    *,
    file: str | None = None,
    subtitles: frozenset[str] | None = None,
    audio: frozenset[str] | None = None,
    complete_audio: bool = True,
    polish_bare: bool = False,
) -> LanguageDeclaration:
    return LanguageDeclaration(source, file, subtitles, audio, complete_audio, polish_bare)


def _traits(  # noqa: PLR0913 - defaults for the public quality boundary
    names: Sequence[str] = (),
    *,
    tags: Sequence[str] = (),
    declarations: Sequence[LanguageDeclaration] = (),
    file: str | None = None,
    pack: bool = False,
    donghua: bool = False,
    seeders: int | None = 0,
) -> ReleaseTraits:
    return release_traits(names, tags, declarations, file=file, pack=pack, donghua=donghua, seeders=seeders)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("pl-PL", "pl"),
        ("ja-JP", "ja"),
        ("zh-Hant", "zh"),
        ("zh_TW", "zh"),
        ("PL", "pl"),
        ("pl", "pl"),
        (" en-US ", "en"),
        ("pt-BR", "pt"),
    ],
)
def test_language_code_regional(code: str, expected: str) -> None:
    assert language_code(code) == expected


@pytest.mark.unit
def test_hardsub_from_nekobt_tag_wins() -> None:
    traits: ReleaseTraits = _traits(
        ("[Nyaa] Example - 01 [1080p]", "[TsukiHime] Example - 01"),
        tags=("{Tags:HS;A=ja;F=pl;S=en}",),
    )
    assert traits.hardsub
    assert traits.polish is PolishClass.POLISH


@pytest.mark.unit
@pytest.mark.parametrize("marker", ["HardSub", "hardsubs", "Hard-Sub", "Hard Sub"])
def test_hardsub_from_any_name_or_tag(marker: str) -> None:
    assert _traits(("Example - 01", f"Example - 01 [{marker}]")).hardsub
    assert _traits(tags=(marker,)).hardsub


@pytest.mark.unit
def test_raw_from_any_source_does_not_match_raws_group() -> None:
    assert _traits(("Example - 01", "Example - 01 [RAW]")).raw
    assert _traits(tags=("RAW",)).raw
    assert not _traits(("[Erai-raws] Example - 01", "[Tsundere-Raws] Example - 01")).raw


@pytest.mark.unit
def test_dub_only_complete_original_list_beats_english_dub() -> None:
    traits: ReleaseTraits = _traits(
        ("Example - 01 [English Dub]",),
        declarations=(_declaration(audio=frozenset({"ja", "en"})),),
    )
    assert not traits.dub_only


@pytest.mark.unit
def test_dub_only_truncated_torrentio_name_does_not_override_dual_audio() -> None:
    names: tuple[str, ...] = ("Example [English Dub]...", "Example - 01 [Dual-Audio]")
    for ordered in permutations(names):
        assert not _traits(ordered, tags=("Dubbed",)).dub_only


@pytest.mark.unit
def test_dub_only_higher_complete_list_excludes_lower_original_audio() -> None:
    traits: ReleaseTraits = _traits(
        ("Example - 01 [Multi-Audio]",),
        tags=("A=ja,en",),
        declarations=(_declaration(audio=frozenset({"en"})),),
    )
    assert traits.dub_only
    assert not traits.polish_audio_beside_original


@pytest.mark.unit
def test_dub_only_dual_audio_with_partial_polish_audio_gets_fifteen_points() -> None:
    traits: ReleaseTraits = _traits(("Example - 01 [1080p] [Dual-Audio] [Polish audio]",))
    assert not traits.dub_only
    assert traits.polish_audio_beside_original
    assert traits.polish is PolishClass.NONE
    assert quality_score(traits) == 35.0


@pytest.mark.unit
def test_dub_only_polish_dub_and_polish_subtitles_without_original() -> None:
    traits: ReleaseTraits = _traits(("Example - 01 [1080p] [PL dub] [Napisy PL]",))
    assert traits.dub_only
    assert traits.polish is PolishClass.POLISH
    assert not traits.polish_audio_beside_original
    assert quality_score(traits) == 60.0


@pytest.mark.unit
@pytest.mark.parametrize("marker", ["[Dub]", "English Dub", "Eng Dub", "Dubbed", "PL dub", "Polish dub", "Dubbing PL"])
def test_dub_only_closed_marker_list(marker: str) -> None:
    assert _traits((f"Example - 01 [{marker}]",)).dub_only


@pytest.mark.unit
@pytest.mark.parametrize("marker", ["Polish audio", "Lektor PL", "English audio", "dubstep"])
def test_dub_only_partial_audio_does_not_prove_missing_original(marker: str) -> None:
    traits: ReleaseTraits = _traits((f"Example - 01 [{marker}]",))
    assert not traits.dub_only
    assert not traits.polish_audio_beside_original
    assert traits.polish is PolishClass.NONE


@pytest.mark.unit
def test_dub_only_ignores_empty_complete_list() -> None:
    declarations: tuple[LanguageDeclaration, ...] = (_declaration(audio=frozenset()),)
    assert not _traits(("[Dubbed] [Dual-Audio]",), declarations=declarations).dub_only
    assert _traits(("[Dubbed]",), declarations=declarations).dub_only


@pytest.mark.unit
def test_dub_only_file_complete_list_beats_release_complete_list() -> None:
    declarations: tuple[LanguageDeclaration, ...] = (
        _declaration(audio=frozenset({"en"})),
        _declaration(LanguageSource.NEKOBT, file="01.mkv", audio=frozenset({"ja", "pl"})),
    )
    traits: ReleaseTraits = _traits(declarations=declarations, file="01.mkv")
    assert not traits.dub_only
    assert traits.polish_audio_beside_original


@pytest.mark.unit
def test_dub_only_partial_file_audio_does_not_replace_complete_release_audio() -> None:
    traits: ReleaseTraits = _traits(
        file="Example [Polish audio] [Dual-Audio].mkv",
        declarations=(_declaration(audio=frozenset({"en"})),),
    )
    assert traits.dub_only
    assert not traits.polish_audio_beside_original


@pytest.mark.unit
def test_dub_only_lower_complete_list_cannot_remove_original_audio() -> None:
    traits: ReleaseTraits = _traits(
        tags=("A=en",),
        declarations=(_declaration(audio=frozenset({"ja"})),),
    )
    assert not traits.dub_only


@pytest.mark.unit
def test_complete_audio_without_polish_overrides_partial_polish_audio() -> None:
    traits: ReleaseTraits = _traits(
        ("Example [Polish audio] [Dual-Audio]",),
        declarations=(_declaration(audio=frozenset({"ja", "en"})),),
    )
    assert not traits.polish_audio_beside_original
    assert not traits.dub_only


@pytest.mark.unit
@pytest.mark.parametrize("file", [None, "01.mkv"])
def test_pack_release_languages_ignored(file: str | None) -> None:
    traits: ReleaseTraits = _traits(
        ("Example [1080p] [PL sub] [MultiSub] [Polish audio] [Dual-Audio] [PL dub]",),
        tags=("A=pl;F=pl;S=en",),
        declarations=(_declaration(subtitles=frozenset({"pl", "en"}), audio=frozenset({"pl"})),),
        file=file,
        pack=True,
    )
    assert traits.polish is PolishClass.NONE
    assert not traits.english_subtitles
    assert not traits.polish_audio_beside_original
    assert not traits.dub_only
    assert traits.resolution == 1080


@pytest.mark.unit
@pytest.mark.parametrize("pack", [False, True])
def test_file_declaration_beats_release(pack: bool) -> None:
    traits: ReleaseTraits = _traits(
        ("Example [PL sub]",),
        declarations=(
            _declaration(subtitles=frozenset({"pl"})),
            _declaration(LanguageSource.FILE_NAME, file="01.mkv", subtitles=frozenset({"en"})),
            _declaration(file="02.mkv", subtitles=frozenset({"pl"})),
        ),
        file="01.mkv",
        pack=pack,
    )
    assert traits.polish is PolishClass.NONE
    assert traits.english_subtitles


@pytest.mark.unit
def test_two_files_in_pack_keep_independent_languages() -> None:
    declarations: tuple[LanguageDeclaration, ...] = (
        _declaration(file="01.mkv", subtitles=frozenset({"pl"})),
        _declaration(file="02.mkv", subtitles=frozenset({"en"})),
    )
    first: ReleaseTraits = _traits(file="01.mkv", pack=True, declarations=declarations)
    second: ReleaseTraits = _traits(file="02.mkv", pack=True, declarations=declarations)
    assert first.polish is PolishClass.POLISH
    assert not first.english_subtitles
    assert second.polish is PolishClass.NONE
    assert second.english_subtitles


@pytest.mark.unit
def test_torrentio_flag_is_scoped_to_its_known_file() -> None:
    declaration: LanguageDeclaration = _declaration(
        LanguageSource.TORRENTIO_FLAG,
        file="01.mkv",
        polish_bare=True,
        complete_audio=False,
    )
    assert _traits(file="01.mkv", pack=True, declarations=(declaration,)).polish is PolishClass.BARE
    assert _traits(file="02.mkv", pack=True, declarations=(declaration,)).polish is PolishClass.NONE
    assert _traits(pack=True, declarations=(declaration,)).polish is PolishClass.NONE


@pytest.mark.unit
@pytest.mark.parametrize("pack", [False, True])
def test_multisub_name_does_not_cancel_torrentio_polish_flag(pack: bool) -> None:
    file: str = "X - 01 [1080p][MultiSub].mkv"
    declaration: LanguageDeclaration = _declaration(
        LanguageSource.TORRENTIO_FLAG, file=file, polish_bare=True, complete_audio=False
    )
    without_flag: ReleaseTraits = _traits(file=file, pack=pack, seeders=10)
    traits: ReleaseTraits = _traits(file=file, pack=pack, seeders=10, declarations=(declaration,))
    assert without_flag.polish is PolishClass.NONE
    assert traits.polish is PolishClass.BARE
    assert traits.english_subtitles
    assert quality_score(traits) == pytest.approx(quality_score(without_flag) + 20.0)


@pytest.mark.unit
@pytest.mark.parametrize("source", [LanguageSource.TSUKIHIME, LanguageSource.NEKOBT, LanguageSource.FILE_NAME])
def test_explicit_subtitle_list_without_polish_still_cancels_torrentio_flag(source: LanguageSource) -> None:
    file: str = "X - 01 [MultiSub].mkv"
    traits: ReleaseTraits = _traits(
        file=file,
        declarations=(
            _declaration(source, file=file, subtitles=frozenset({"en"})),
            _declaration(LanguageSource.TORRENTIO_FLAG, file=file, polish_bare=True, complete_audio=False),
        ),
    )
    assert traits.polish is PolishClass.NONE


@pytest.mark.unit
@pytest.mark.parametrize("token", ["Polish audio", "Lektor PL"])
def test_partial_file_audio_does_not_exclude_original_from_complete_list(token: str) -> None:
    traits: ReleaseTraits = _traits(
        file=f"Example [{token}].mkv",
        declarations=(_declaration(audio=frozenset({"ja", "pl"})),),
    )
    assert not traits.dub_only
    assert traits.audio is AudioClass.ORIGINAL
    assert traits.polish_audio_beside_original


@pytest.mark.unit
@pytest.mark.parametrize("empty", [None, frozenset()])
def test_empty_list_does_not_override_lower(empty: frozenset[str] | None) -> None:
    traits: ReleaseTraits = _traits(
        ("Example [PL sub] [MultiSub] [Polish audio] [Multi-Audio]",),
        declarations=(_declaration(subtitles=empty, audio=empty),),
    )
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert traits.polish_audio_beside_original


@pytest.mark.unit
@pytest.mark.parametrize("tags", [("F=pl", "S=en,fr"), ("{Tags:A=ja;F=pl-PL;S=en,fr}",)])
def test_nekobt_fansub_pl_with_official_without_pl(tags: tuple[str, ...]) -> None:
    traits: ReleaseTraits = _traits(tags=tags)
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert quality_score(traits) == 40.0


@pytest.mark.unit
@pytest.mark.parametrize(
    ("higher", "lower"),
    [
        (LanguageSource.TSUKIHIME, LanguageSource.NEKOBT),
        (LanguageSource.NEKOBT, LanguageSource.FILE_NAME),
        (LanguageSource.FILE_NAME, LanguageSource.RELEASE_NAME),
        (LanguageSource.RELEASE_NAME, LanguageSource.TORRENTIO_FLAG),
    ],
)
def test_higher_declaration_wins_subtitles_and_audio(higher: LanguageSource, lower: LanguageSource) -> None:
    declarations: tuple[LanguageDeclaration, ...] = (
        _declaration(lower, subtitles=frozenset({"pl", "en"}), audio=frozenset({"ja", "pl"}), polish_bare=True),
        _declaration(higher, subtitles=frozenset({"fr"}), audio=frozenset({"ko"})),
    )
    for ordered in permutations(declarations):
        traits: ReleaseTraits = _traits(("Example [PL sub] [MultiSub] [Polish audio]",), declarations=ordered)
        assert traits.polish is PolishClass.NONE
        assert not traits.english_subtitles
        assert not traits.polish_audio_beside_original
        assert traits.audio is AudioClass.KOREAN
        assert not traits.dub_only


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subtitles", "pack", "expected"),
    [
        (frozenset({"pl", "en"}), False, PolishClass.POLISH),
        (frozenset({"en"}), False, PolishClass.NONE),
        (frozenset(), False, PolishClass.NONE),
        (None, False, PolishClass.NONE),
        (frozenset({"pl", "en"}), True, PolishClass.BARE),
        (frozenset({"en"}), True, PolishClass.BARE),
    ],
    ids=["release-pl", "release-without-pl", "release-audio-only", "release-audio-none", "pack-pl", "pack-without-pl"],
)
def test_release_subtitle_list_decides_before_file_torrentio_flag(
    subtitles: frozenset[str] | None, pack: bool, expected: PolishClass
) -> None:
    file: str = "X - 01 [1080p].mkv"
    traits: ReleaseTraits = _traits(
        file=file,
        pack=pack,
        declarations=(
            _declaration(LanguageSource.TORRENTIO_FLAG, file=file, polish_bare=True, complete_audio=False),
            _declaration(subtitles=subtitles, audio=frozenset({"ja"})),
        ),
    )
    assert traits.polish is expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("subtitles", "expected"),
    [(frozenset({"en"}), PolishClass.NONE), (frozenset({"pl"}), PolishClass.POLISH), (None, PolishClass.BARE)],
)
def test_release_subtitle_list_decides_before_file_bare_token(
    subtitles: frozenset[str] | None, expected: PolishClass
) -> None:
    traits: ReleaseTraits = _traits(file="X - 01 [PL].mkv", declarations=(_declaration(subtitles=subtitles),))
    assert traits.polish is expected


@pytest.mark.unit
@pytest.mark.parametrize(("tags", "expected"), [(("F=pl;S=en",), PolishClass.POLISH), (("S=en",), PolishClass.NONE)])
def test_release_nekobt_subtitles_decide_before_file_torrentio_flag(
    tags: tuple[str, ...], expected: PolishClass
) -> None:
    file: str = "X - 01 [1080p].mkv"
    flag: LanguageDeclaration = _declaration(
        LanguageSource.TORRENTIO_FLAG, file=file, polish_bare=True, complete_audio=False
    )
    assert _traits(file=file, tags=tags, declarations=(flag,)).polish is expected


@pytest.mark.unit
def test_higher_declaration_wins_bare_token_and_flag() -> None:
    traits: ReleaseTraits = _traits(
        file="Example PL.mkv",
        declarations=(
            _declaration(file="Example PL.mkv", subtitles=frozenset({"en"})),
            _declaration(LanguageSource.TORRENTIO_FLAG, file="Example PL.mkv", polish_bare=True),
        ),
    )
    assert traits.polish is PolishClass.NONE
    assert traits.english_subtitles


@pytest.mark.unit
def test_audio_declaration_does_not_override_subtitle_declaration() -> None:
    traits: ReleaseTraits = _traits(
        tags=("F=pl;S=en",),
        declarations=(_declaration(audio=frozenset({"ja"})),),
    )
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert _traits(("Example [PL]",), declarations=(_declaration(audio=frozenset({"ja"})),)).polish is PolishClass.NONE


@pytest.mark.unit
def test_subtitle_declaration_does_not_override_audio_declaration() -> None:
    traits: ReleaseTraits = _traits(
        tags=("A=ja,pl",),
        declarations=(_declaration(subtitles=frozenset({"en"})),),
    )
    assert traits.polish is PolishClass.NONE
    assert traits.polish_audio_beside_original


@pytest.mark.unit
@pytest.mark.parametrize("token", ["Napisy PL", "PLsub", "PL sub", "Polish sub", "pl_sub"])
def test_polish_subtitle_tokens(token: str) -> None:
    traits: ReleaseTraits = _traits((f"Example - 01 [{token}]",))
    assert traits.polish is PolishClass.POLISH
    assert quality_score(traits) == 40.0


@pytest.mark.unit
@pytest.mark.parametrize("token", ["Lektor PL", "Polish audio", "PL dub", "Polish dub", "Dubbing PL"])
def test_polish_audio_tokens_do_not_imply_polish_subtitles(token: str) -> None:
    traits: ReleaseTraits = _traits((f"Example - 01 [{token}] [Dual-Audio]",))
    assert traits.polish is PolishClass.NONE
    assert traits.polish_audio_beside_original
    assert not traits.dub_only
    assert quality_score(traits) == 15.0


@pytest.mark.unit
@pytest.mark.parametrize("token", ["PL", "POL", "Polish"])
def test_polish_bare_tokens(token: str) -> None:
    traits: ReleaseTraits = _traits((f"Example - 01 [{token}] [MultiSub]",))
    assert traits.polish is PolishClass.BARE
    assert traits.english_subtitles
    assert quality_score(traits) == 30.0


@pytest.mark.unit
@pytest.mark.parametrize("token", ["ENG sub", "English sub", "MultiSub", "Multi-Subs"])
def test_english_subtitle_tokens_do_not_imply_polish(token: str) -> None:
    traits: ReleaseTraits = _traits((f"Example - 01 [{token}]",))
    assert traits.polish is PolishClass.NONE
    assert traits.english_subtitles
    assert quality_score(traits) == 10.0


@pytest.mark.unit
def test_english_subtitle_name_does_not_contradict_release_polish_subtitles() -> None:
    traits: ReleaseTraits = _traits(("Example [PL sub]",), file="Example [English sub].mkv")
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert quality_score(traits) == 40.0


@pytest.mark.unit
def test_file_name_does_not_read_pack_directory_as_file_language() -> None:
    assert _traits(file="Example [PL sub]/01.mkv", pack=True).polish is PolishClass.NONE
    assert _traits(file="Example/01 [PL sub].mkv", pack=True).polish is PolishClass.POLISH


@pytest.mark.unit
def test_tokens_from_equivalent_release_names_are_combined() -> None:
    names: tuple[str, ...] = ("Example [MultiSub]", "Example [PL sub] [Polish audio] [Dual-Audio]")
    for ordered in permutations(names):
        traits: ReleaseTraits = _traits(ordered)
        assert traits.polish is PolishClass.POLISH
        assert traits.english_subtitles
        assert traits.polish_audio_beside_original


@pytest.mark.unit
def test_file_name_quality_tokens_with_underscore_separators() -> None:
    traits: ReleaseTraits = _traits(file="Example_01_PL_sub_Polish_audio_Dual-Audio_NF_WEB-DL.mkv")
    assert traits.polish is PolishClass.POLISH
    assert traits.polish_audio_beside_original
    assert traits.platform
    assert _traits(file="Example_01_BD_Remux.mkv").bluray


@pytest.mark.unit
def test_declarations_normalize_regional_languages_before_scoring() -> None:
    traits: ReleaseTraits = _traits(
        declarations=(_declaration(subtitles=frozenset({"pl-PL", "EN-us"}), audio=frozenset({"ja-JP", "PL"})),)
    )
    assert traits.polish is PolishClass.POLISH
    assert traits.english_subtitles
    assert traits.polish_audio_beside_original
    assert not traits.dub_only
    assert quality_score(traits) == 55.0


@pytest.mark.unit
def test_donghua_zh_is_original() -> None:
    traits: ReleaseTraits = _traits(donghua=True, declarations=(_declaration(audio=frozenset({"zh-Hant", "pl"})),))
    assert traits.audio is AudioClass.ORIGINAL
    assert not traits.dub_only
    assert traits.polish_audio_beside_original


@pytest.mark.unit
def test_japanese_title_zh_not_original() -> None:
    traits: ReleaseTraits = _traits(declarations=(_declaration(audio=frozenset({"zh-Hant", "pl"})),))
    assert traits.dub_only
    assert not traits.polish_audio_beside_original


@pytest.mark.unit
def test_no_audio_declaration_assumes_original() -> None:
    traits: ReleaseTraits = _traits()
    assert traits.audio is AudioClass.ORIGINAL
    assert not traits.dub_only


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("1080p", 1080),
        ("1440×1080", 1080),
        ("1920x1080", 1080),
        ("2160p", 2160),
        ("4K", 2160),
        ("720p", 720),
        ("480i", 480),
        ("unknown", None),
        ("1080p 720p", None),
    ],
)
def test_resolution_from_names(name: str, expected: int | None) -> None:
    assert _traits((f"Example [{name}]",)).resolution == expected


@pytest.mark.unit
def test_resolution_class_order() -> None:
    heights: list[int | None] = [None, 480, 576, 1440, 900, 720, 2160, 1080]
    assert sorted(heights, key=resolution_class) == [1080, 2160, 720, 900, 1440, 576, 480, None]
    assert resolution_class(1080) == (ResolutionClass.FULL_HD, 0)
    assert resolution_class(900) == (ResolutionClass.OTHER, 180)
    assert resolution_class(None) == (ResolutionClass.UNKNOWN, 0)


@pytest.mark.unit
def test_polish_class_order() -> None:
    base: ReleaseTraits = _traits(("Example [1080p]",))
    traits: list[ReleaseTraits] = [replace(base, polish=polish) for polish in reversed(PolishClass)]
    assert [item.polish for item in sorted(traits, key=class_key)] == list(PolishClass)
    assert class_key(replace(base, resolution=720, polish=PolishClass.POLISH)) > class_key(base)


@pytest.mark.unit
def test_audio_class_order() -> None:
    japanese: ReleaseTraits = _traits(declarations=(_declaration(audio=frozenset({"ja"})),))
    korean: ReleaseTraits = _traits(declarations=(_declaration(audio=frozenset({"ko"})),))
    assert japanese.audio is AudioClass.ORIGINAL
    assert korean.audio is AudioClass.KOREAN
    assert not korean.dub_only
    assert class_key(japanese) < class_key(korean)
    assert class_key(replace(korean, polish=PolishClass.POLISH)) < class_key(japanese)


@pytest.mark.unit
@pytest.mark.parametrize("platform", ["NF", "CR", "ADN", "AMZN", "HIDIVE", "BILI", "DSNP", "Netflix", "Crunchyroll"])
def test_platform_requires_web_and_whole_platform_token(platform: str) -> None:
    traits: ReleaseTraits = _traits((f"Example [{platform} WEB-DL]",))
    assert traits.platform
    assert quality_score(traits) == 5.0
    assert not _traits((f"Example [{platform}]",)).platform
    assert not _traits((f"Example [X{platform}X WEB-DL]",)).platform


@pytest.mark.unit
@pytest.mark.parametrize("marker", ["Blu-ray", "Bluray", "BD", "BDRip", "remux", "BDRemux", "BD remux"])
def test_bluray_minus_ten(marker: str) -> None:
    traits: ReleaseTraits = _traits((f"Example [1080p] [{marker}]",))
    assert traits.bluray
    assert quality_score(traits) == 10.0


@pytest.mark.unit
@pytest.mark.parametrize("codec", ["AVC", "HEVC", "AV1", "x264", "x265", "H.264", "H.265"])
def test_codec_no_points(codec: str) -> None:
    assert quality_score(_traits((f"Example [1080p] [{codec}]",))) == 20.0


@pytest.mark.unit
@pytest.mark.parametrize(("seeders", "expected"), [(0, 0.0), (5, 4.557), (50, 10.0), (400, 10.0)])
def test_seed_points_logarithmic(seeders: int, expected: float) -> None:
    assert seed_points(seeders) == pytest.approx(expected, abs=0.001)


@pytest.mark.unit
def test_seed_points_unknown() -> None:
    assert seed_points(None) == 5.0


@pytest.mark.unit
def test_quality_points_english_added_only_without_confirmed_polish() -> None:
    base: ReleaseTraits = _traits(("Example [MultiSub]",))
    assert quality_score(base) == 10.0
    assert quality_score(replace(base, polish=PolishClass.BARE)) == 30.0
    assert quality_score(replace(base, polish=PolishClass.POLISH)) == 40.0


@pytest.mark.unit
def test_quality_points_range_and_unrounded_value() -> None:
    assert quality_score(_traits(("Example [BD]",))) == 0.0
    assert quality_score(_traits(("Example [2160p]",))) == 5.0
    best: ReleaseTraits = _traits(
        ("Example [1080p NF WEB-DL]",),
        seeders=50,
        declarations=(_declaration(subtitles=frozenset({"pl", "en"}), audio=frozenset({"ja", "pl"})),),
    )
    assert quality_score(best) == 90.0
    assert quality_score(replace(best, seeders=5)) == pytest.approx(84.55706747093605, abs=1e-12)


@pytest.mark.unit
def test_owner_order_f_a_c_e_b_d() -> None:
    declarations: tuple[tuple[str, frozenset[str], frozenset[str], int], ...] = (
        ("B", frozenset({"en"}), frozenset({"ja", "en"}), 400),
        ("D", frozenset({"en"}), frozenset({"ja"}), 900),
        ("E", frozenset({"pl"}), frozenset({"ja", "en", "fr"}), 5),
        ("C", frozenset({"pl"}), frozenset({"ja", "en"}), 30),
        ("A", frozenset({"pl"}), frozenset({"ja"}), 80),
        ("F", frozenset({"pl"}), frozenset({"ja", "pl"}), 60),
    )
    cases: dict[str, ReleaseTraits] = {
        name: _traits(
            ("Example [1080p]",), seeders=seeders, declarations=(_declaration(subtitles=subtitles, audio=audio),)
        )
        for name, subtitles, audio, seeders in declarations
    }
    assert sorted(cases, key=lambda name: (*class_key(cases[name]), -quality_score(cases[name]))) == list("FACEBD")
    assert [quality_score(cases[name]) for name in "FACEBD"] == pytest.approx(
        [85, 70, 68.7338, 64.5571, 40, 40], abs=0.0001
    )
