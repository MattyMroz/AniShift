from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest

from anishift.application.library import LibraryLabel, library_label

_COLUMNS: Final[tuple[tuple[str, str, str], ...]] = (
    ("Avatar.Seven.Havens.S01E01.1080p.WEB.h264-GRACE[EZTVx.to].mkv", "Avatar Seven Havens", "S01E01"),
    ("Avatar.Seven.Havens.S01E01.1080p.WEB.h264-GRACE[EZTVx.to]", "Avatar Seven Havens", "S01E01"),
    ("Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi.DDP5.1.H.264.MSubs-ToonsHub.mkv", "Blue Box", "S02E01"),
    (
        "Magical.Explorer.S01E01.Reincarnated.as.a.Sidekick.Character.in.an.Eroge.but.Ill.Use.My.Game.Knowledge"
        ".to.Do.What.I.Want.REPACK.1080p.CR.WEB-DL.DUAL.AAC2.0.H.264-VARYG.mkv",
        "Magical Explorer",
        "S01E01",
    ),
    (
        "Reborn.as.a.Space.Mercenary.I.Woke.Up.Piloting.the.Strongest.Starship.2026.S01E01.1080p.CR.WEB-DL.DUAL"
        ".DDP2.0.H.264-AnoZu.mkv",
        "Reborn as a Space Mercenary I Woke Up Piloting the Strongest Starship",
        "S01E01",
    ),
    (
        "[DKB] Kyouran Reijou Nia Liston - S01E01 [1080p][HEVC x265 10bit][CF7BABFE].mkv",
        "Kyouran Reijou Nia Liston",
        "S01E01",
    ),
    (
        "[Erai-raws] Seihantai na Kimi to Boku 2nd Season - 07 [1080p CR WEB-DL AVC AAC][MultiSub][6ADBF21C].mkv",
        "Seihantai na Kimi to Boku",
        "S02E07",
    ),
    (
        "[Erai-raws] Tensei Kizoku - Kantei Skill de Nariagaru S3 - 01 [1080p CR WEB-DL AVC AAC][MultiSub][BF3FA5B8]",
        "Tensei Kizoku - Kantei Skill de Nariagaru",
        "S03E01",
    ),
    ("[SubsPlease] Clevatess S2 - 05 (1080p) [740FF004]", "Clevatess", "S02E05"),
    ("[Grp] Show Season 2 - 03 (1080p)", "Show", "S02E03"),
    (
        "[Erai-raws] Katainaka no Ossan Kensei ni Naru II - 02 [1080p AMZN WEB-DL AVC EAC3][MultiSub][E27C3F25]",
        "Katainaka no Ossan Kensei ni Naru",
        "S02E02",
    ),
    ("[SubsPlease] Tempal - Item no Chikara - 02 (1080p) [38DA9158]", "Tempal - Item no Chikara", "S01E02"),
    ("[SubsPlease] Lv999 no Murabito - 07 (1080p) [451CACE8]", "Lv999 no Murabito", "S01E07"),
    (
        "[Erai-raws] Koukaku Kidoutai (2026) - 05 [1080p AMZN WEB-DL AVC EAC3][MultiSub][ADDB49AE]",
        "Koukaku Kidoutai (2026)",
        "S01E05",
    ),
    (
        "[lycoris.cafe] Toumei na Yoru ni Kakeru Kimi to Me ni Mienai Koi wo Shita - 07 [source-mkv]",
        "Toumei na Yoru ni Kakeru Kimi to Me ni Mienai Koi wo Shita",
        "S01E07",
    ),
    ("[Grp]_Some_Show_-_05_[1080p].mkv", "Some Show", "S01E05"),
    ("Some.Show.S01E01-E02.1080p.WEB.mkv", "Some Show", "S01E01–E02"),
    ("[Grp] Some Show - 01-02 [1080p].mkv", "Some Show", "S01E01–E02"),
    ("[Grp] Some Show - 12.5 (1080p).mkv", "Some Show", "S01E12.5"),
    ("[Judas] Suzume no Tojimari (2022) [BD 1080p HEVC x265 10bit].mkv", "Suzume no Tojimari", "—"),
    ("Suzume.2022.1080p.BluRay.x264-GROUP.mkv", "Suzume", "—"),
    ("Porco.Rosso.1992.JAPANESE.1080p.BluRay.x264.DTS-WiKi.mkv", "Porco Rosso", "—"),
    ("Show.S00E05.1080p.WEB.mkv", "Show", "S00E05"),
    ("[Grp] Show - S00E05 [1080p]", "Show", "S00E05"),
    ("[Grp] Some.Show.S01E01 [1080p].mkv", "Some Show", "S01E01"),
    ("[Grp] Made in Abyss - Fukaki Tamashii no Reimei [BD 1080p].mkv", "Made in Abyss Fukaki Tamashii no Reimei", "—"),
    ("[UQW] Sousei no Onmyouji - Ep01 [BD 720p AVC-YUV444P10 AAC].mkv", "Sousei no Onmyouji", "—"),
    ("[Grp] Some Show - Vol.1 [BD 1080p].mkv", "Some Show", "—"),
    ("[Grp] Shingeki no Kyojin - Movie 2 [BD 1080p].mkv", "Shingeki no Kyojin Movie 2", "—"),
    (
        "[Grp] Psycho-Pass - Sinners of the System Case 1 [BD 1080p].mkv",
        "Psycho-Pass Sinners of the System Case 1",
        "—",
    ),
    ("[Grp] Kizumonogatari - Part 2 Nekketsu [BD 1080p].mkv", "Kizumonogatari Part 2 Nekketsu", "—"),
    ("[AnimeRG] One Piece - Movie 01 (2000) One Piece [1080p] [x265].mkv", "One Piece Movie 01", "—"),
    ("[Grp] Some Show - Vol. 2 [BD 1080p].mkv", "Some Show Vol. 2", "—"),
    ("Aoashi - Episode 01 - First Touch 1080p BDRip x265 FLAC 2.0 Kira [SEV].mkv", "Aoashi", "—"),
    ("[Reaktor] Steins Gate - E24 v2 [1080p][x265][10-bit][Dual-Audio].mkv", "Steins Gate", "—"),
    ("Kids on the Slope - Ep. 12 - All Blues (1080p DUAL Audio - BluRay).mkv", "Kids on the Slope", "—"),
    ("Occhi di gatto - 1x01 - Un rischioso legame (1080p x265) [Accid].mkv", "Occhi di gatto", "—"),
    (
        "[inid4c] JoJo's Bizarre Adventure - Stardust Crusaders 25 (BD 1080p FLAC).mkv",
        "JoJo's Bizarre Adventure",
        "—",
    ),
    ("Ataque a los Titanes - Temporada 1 [HDTV 720p][Cap.101][AC3 5.1 Castellano].mkv", "Ataque a los Titanes", "—"),
    ("Baki - S01.E01 - Synchronicity 1080p BDRip x265 AAC 2.0 Kira [SEV].mkv", "Baki", "—"),
    ("[Grp] Some Show - Saison 2 Finale [BD 1080p].mkv", "Some Show", "—"),
    ("Attack on Titan - Junior High - Episode 01 - Starting School! [1080p].mkv", "Attack on Titan", "—"),
    ("Some_Movie_1080p.mkv", "Some Movie", "—"),
    ("Porco Rosso - Szkarlatny Pilot.1992.PL.720p.bluray.x264.mkv", "Porco Rosso Szkarlatny Pilot", "—"),
    ("Kaze tachinu - Zrywa sie wiatr.2013.PL.BluRay.720p.x264-zyl.mkv", "Kaze tachinu Zrywa sie wiatr", "—"),
    ("Princess.Mononoke.1997.BDRemux.1080p Ita Eng Jap x264-NAHOM.mkv", "Princess Mononoke", "—"),
    ("The.Boy.and.the.Heron.2023.1080p.BluRay.x264-GROUP.mkv", "The Boy and the Heron", "—"),
    (
        "Evangelion 2.22 You Can (Not) Advance (2009) - 1080p by stress.mkv",
        "Evangelion 2.22 You Can (Not) Advance",
        "—",
    ),
    ("[Grp] Kimi no Na wa. [BD 1080p].mkv", "Kimi no Na wa.", "—"),
    ("Chainsaw.Man.-.The.Movie.Reze.Arc.2025.2160p.WEB-DL.mkv", "Chainsaw Man The Movie Reze Arc", "—"),
    (
        "Berserk.The.Golden.Age.Arc.II.-.The.Battle.For.Doldrey.2012.1080p.BluRay.x264.mkv",
        "Berserk The Golden Age Arc II The Battle For Doldrey",
        "—",
    ),
    (
        "Berserk.The.Golden.Age.Arc.III.-.The.Advent.2013.1080p.BluRay.x264.mkv",
        "Berserk The Golden Age Arc III The Advent",
        "—",
    ),
    (
        "[Final8]Hellsing Ultimate - The Dawn III (BD 1080p x264 FLAC)[D95403A3].mkv",
        "Hellsing Ultimate The Dawn III",
        "—",
    ),
    (
        "[ACX]Dragonball_Z_Movie_10_-_Broly,_Second_Coming_[Kaiser]_[BD]_[5A2E7E86].mkv",
        "Dragonball Z Movie 10 Broly, Second Coming",
        "—",
    ),
    (
        "[WZF]Mahou_Shoujo_Madoka_Magika_-_Capitulo_01v3[X264-10bit][1280x720][Sub_Esp].mkv",
        "Mahou Shoujo Madoka Magika",
        "—",
    ),
    ("[Grp] Some Show - Capitulo 05 Final [720p].mkv", "Some Show", "—"),
    ("[Grp] Some Show - Special 01v2 [720p].mkv", "Some Show", "—"),
    ("Owarimonogatari 2nd Season 01 - Mayoi Hell, Part 1.mkv", "Owarimonogatari 01", "—"),
    ("[zza] Bungou Stray Dogs - S03 - 12 [1080p].mkv", "Bungou Stray Dogs", "S03E12"),
    ("[Salieri] Spy x Family - S2 - 01 (BD 1080p HEVC) [Dual Audio].mkv", "Spy x Family", "S02E01"),
    (
        "[Anime Time] Komi-san wa, Comyushou desu. (Season 2) - 01 [1080p][HEVC 10bit x265][AAC][Multi Sub].mkv",
        "Komi-san wa, Comyushou desu.",
        "S02E01",
    ),
    (
        "[BlurayDesuYo] Shingeki no Kyojin (Season 3) - 49 (BD 1920x1080 10bit FLAC) [42B5A2B6].mkv",
        "Shingeki no Kyojin",
        "S03E49",
    ),
    ("Show - 05.5.mkv", "Show", "S01E05.5"),
    ("Berserk_01_Dual_Audio_10bit_BD720p_x265_.mkv", "Berserk 01 Dual Audio", "—"),
    (
        "Dragon Ball Z - Movie 14b - Battle of Gods, UNCut (2013 BD 1080p x265 10bit).mkv",
        "Dragon Ball Z Movie 14b Battle of Gods",
        "—",
    ),
    ("(Anime Time) Naruto Shippuden - 01 [1080p].mkv", "Naruto Shippuden", "S01E01"),
    ("[Grp] Show - OVA 1 [BD 1080p].mkv", "Show OVA 1", "—"),
    ("[Grp] Show - OVA 2 [BD 1080p].mkv", "Show OVA 2", "—"),
    ("moj_film_wakacje.mp4", "moj_film_wakacje", "—"),
    ("moj_film_wakacje", "moj_film_wakacje", "—"),
)


@pytest.mark.unit
@pytest.mark.parametrize(("name", "title", "episode"), _COLUMNS, ids=[name for name, _, _ in _COLUMNS])
def test_library_label_reads_the_title_and_episode_columns(name: str, title: str, episode: str) -> None:
    label: LibraryLabel = library_label(name)

    assert (label.title, label.episode_text) == (title, episode)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("[SubsPlease] Lv999 no Murabito - 07 (1080p) [451CACE8]", LibraryLabel("Lv999 no Murabito", 1, Decimal(7))),
        ("Blue.Box.S02E01.Deja.Vu.1080p.NF.WEB-DL.MULTi", LibraryLabel("Blue Box", 2, Decimal(1))),
        ("Some.Show.S01E01-E02.1080p.WEB", LibraryLabel("Some Show", 1, Decimal(1), Decimal(2))),
        ("[Judas] Suzume no Tojimari (2022) [BD 1080p]", LibraryLabel("Suzume no Tojimari", None, None)),
        ("moj_film_wakacje", LibraryLabel("moj_film_wakacje", None, None)),
        ("Show.S00E05.1080p.WEB", LibraryLabel("Show", 0, Decimal(5))),
    ],
)
def test_library_label_exposes_season_and_episodes_for_sorting(name: str, expected: LibraryLabel) -> None:
    assert library_label(name) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "text"),
    [
        (LibraryLabel("Blue Box", 2, Decimal(1)), "Blue Box S02E01"),
        (LibraryLabel("Some Show", 1, Decimal(1), Decimal(2)), "Some Show S01E01–E02"),
        (LibraryLabel("moj_film_wakacje", None, None), "moj_film_wakacje"),
    ],
)
def test_library_label_text_joins_the_title_and_the_episode(label: LibraryLabel, text: str) -> None:
    assert label.text == text
