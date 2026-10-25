---
kind: diagnosis
status: done
baseline: 4365a51 (main, czyste drzewo)
created: 2026-10-25
---

# Diagnoza: układ linii dialogu rośnie ponadkwadratowo z liczbą słów

## Pytanie

Dlaczego `layout_dialogue` (`anishift/services/subtitles/linebreak.py`) dla linii o kilkuset słowach liczy się sekundami, a dla ok. 1000 słów nie kończy się wcale, i jaka jest realna górna granica długości linii dialogu w napisach anime.

## Pomiary

Stanowisko: Windows 11, `uv run python`, Python 3.14, czysty `main` (`4365a51`). Tekst syntetyczny z polskich słów (cykl 26 słów), zdarzenie `SSAEvent(text="x")`. Profil renderu jak `_profile()` w `tests/services/subtitles/test_subtitles_dialogue_layout.py` (`RenderProfile.from_subs(subs, None)`, Arial 50 px, 1920×1080, bez indeksu czcionek — pomiar zastępczy Pillow). Czasy to pojedyncze wywołanie `layout_dialogue` po rozgrzaniu importów; pamięć z osobnego przebiegu z `tracemalloc` (który sam spowalnia kod 1,5–2×, więc czasów z tamtego przebiegu nie podaję).

Skrypt: `C:\Users\MATTYM~1\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\b1c6e9d7-f377-43d2-802f-da71c0f1b1b3\scratchpad\perf\bench.py` (uruchomienie z katalogu repo: `uv run python <ścieżka>/bench.py 20 40 80 160 320`; profil: `... bench.py prof 160 profile|none`).

### Czas i pamięć `layout_dialogue`

| n słów | bez profilu [s] | z profilem [s] | szczyt RAM bez profilu [MB] | szczyt RAM z profilem [MB] | par (start, end) w `_measure` | kandydatów `_enumerated` |
|---|---|---|---|---|---|---|
| 19 | 0,039 | 0,039 | — | — | 190 | 172 |
| 20 | 0,064 | 0,065 | 0,6 | 0,6 | 210 | 191 |
| 32 | 0,032 | 0,166 | — | — | 528 | 497 |
| 40 | 0,087 | 0,335 | 2,3 | 2,8 | 820 | 781 |
| 50 | 0,079 | 0,452 | — | — | 1 275 | 1 226 |
| 64 | 0,161 | 0,829 | — | — | 2 080 | 2 017 |
| 80 | 0,329 | 1,742 | 10,9 | 13,6 | 3 240 | 3 161 |
| 160 | 1,354 | 7,634 | 57,1 | 71,6 | 12 880 | 12 721 |
| 320 | 5,541 | 42,310 | 329,0 | 413,8 | 51 360 | 51 041 |
| 640 | 37,881 | 273,544 | — | — | 205 120 | 204 481 |

Kandydatów `_enumerated` = 1 + (n−1) + C(n−1, 2): wszystkie podziały na 1–3 wiersze. Wiersz n = 640 mierzony równolegle z drugim przebiegiem na tej samej maszynie, więc jest zawyżony o kontencję CPU; rząd wielkości się zgadza.

Wykładnik wzrostu między n = 160 i n = 320: bez profilu ×4,1 (≈ n^2,0), z profilem ×5,5 (≈ n^2,5); między 320 i 640: ×6,8 i ×6,5 (≈ n^2,7). Między 80 i 160: ×4,1 i ×4,4. Wraz z n wykładnik zbliża się do 3. Czas rośnie szybciej niż kwadratowo, bo każdy z O(n²) kandydatów płaci koszt liniowy w n (złączanie słów, pomiar wiersza znak po znaku), a stały koszt na kandydata jeszcze dominuje przy tych rozmiarach. Pamięć rośnie ~n^2,5 (57 → 329 MB).

### Tabela par w `_measure` (sama konstrukcja, bez układu)

Skrypt `measure_build.py` w tym samym katalogu. `_measure` buduje słownik wszystkich par (start, end) z góry, zanim rdzeń układu zacznie pracę.

| n słów | budowa `_measure` [s] | szczyt RAM tabeli [MB] | par (start, end) | kandydatów `_enumerated` |
|---|---|---|---|---|
| 160 | 0,09 | 14 | 12 880 | 12 721 |
| 320 | 0,59 | 88 | 51 360 | 51 041 |
| 640 | 2,59 | 619 | 205 120 | 204 481 |
| 1000 | 11,09 | 2 245 | 500 500 | 499 501 |

Przy 1000 słowach sama tabela zajmuje 2,2 GB, zanim padnie pierwsze wywołanie `lay_out`. Pełnego przebiegu dla 1000 słów nie powtarzałem (zgłoszone > 1000 s CPU); ekstrapolacja z 320 → 1000 przy wykładniku 2,5 daje ≈ 730 s samego CPU z profilem, a do tego ok. 500 tys. obiektów `Layout` z trzema złączonymi wierszami każdy, więc proces wchodzi w wymianę pamięci. To tłumaczy „bez końca”.

### Profil `cProfile`, n = 160, z profilem renderu (13,4 s pod profilerem)

Pełny wydruk: `scratchpad\perf\prof160_profile.txt`.

| funkcja | wywołań | cumtime [s] | uwagi |
|---|---|---|---|
| `layout.py:383 _enumerated` | 1 | 13,13 | pętla po 12 721 kandydatach |
| `layout.py:446 _evaluate` | 12 721 | 13,08 | po jednym na kandydata |
| `layout.py:523 _line_size` | 38 002 | 11,26 | pomiar każdego wiersza kandydata |
| `linebreak.py:131 unscaled` → `geometry.py:261 measure_text` | 4 102 → 12 881 | 11,02 → 10,97 | jedna linia tekstu ma kilka wariantów z tagami, każdy mierzony osobno |
| `geometry.py:1147 _substitute_layout` → `PIL getlength` | 12 881 → 4 105 | 7,22 → 6,61 | 1,6 ms na wywołanie; `_verse_width` ma `lru_cache(4096)`, a unikalnych wierszy jest 4 102 |
| `geometry.py:558 _parse` → `geometry.py:482 <genexpr>` | 12 884 → 4 249 416 | 3,54 → 2,78 | jeden obiekt `_Char` na każdy znak każdego mierzonego fragmentu |
| `layout.py:499 _line_shape` | 38 002 | 1,13 | `_chars`, `agrees`, flagi |

Z 13,4 s aż 11,0 s to `measure_text` wołany raz na każdy unikalny fragment (start, end): parsowanie znak po znaku plus pomiar Pillow. Liczba fragmentów to O(n²), długość każdego O(n), więc łączna praca to O(n³) znaków.

### Profil `cProfile`, n = 160, bez profilu renderu (2,26 s pod profilerem)

Pełny wydruk: `scratchpad\perf\prof160_none.txt`.

| funkcja | wywołań | cumtime [s] | uwagi |
|---|---|---|---|
| `layout.py:383 _enumerated` | 1 | 2,10 | |
| `layout.py:446 _evaluate` | 12 721 | 2,06 | 0,16 ms na kandydata |
| `layout.py:499 _line_shape` | 38 002 | 0,95 | |
| `graphemes.py:15 split_graphemes` → `regex.findall` | 8 209 | 0,62 → 0,60 | `_chars` i `chars_measure` na każdy unikalny wiersz |
| `layout.py:523 _line_size` | 38 002 | 0,50 | |
| `str.join` | 152 177 | 0,12 | złączanie słów wiersza w `_lines`, `_line_shape`, `_line_size` |

Bez profilu pomiar jest tani (grafemy), więc czas to niemal czysty koszt O(n²) kandydatów razy liniowe złączanie i ocena wierszy.

## Przyczyna

Trzy ogniwa tego samego łańcucha; żadne nie jest błędem implementacji, wszystkie są kosztem projektu rdzenia bez ograniczenia na wejściu.

1. **Pełny przegląd podziałów na 1–3 wiersze** — `anishift/services/subtitles/layout.py:383-392` (`_enumerated`, `_splits`): `combinations(allowed, lines - 1)` daje 1 + (n−1) + C(n−1, 2) ≈ n²/2 kandydatów. Każdy kandydat przechodzi `_evaluate` (`layout.py:446`), które złącza słowa każdego wiersza (`_lines` `layout.py:590-592`, `_line_shape` `layout.py:501`, `_line_size` `layout.py:525`) i trzyma gotowy obiekt `Layout` z wierszami w liście `found` (`layout.py:327`). Koszt O(n) na kandydata → O(n³) znaków i O(n²) obiektów w pamięci. To świadoma decyzja specyfikacji (`docs/work/10-quality/text-layout.md` §5.1: „dla dialogu (K ≤ 3) przegląd pełny”), poprawna dla linii dialogu o kilkunastu słowach.
2. **Tabela wszystkich par w `_measure`** — `anishift/services/subtitles/linebreak.py:123-129`: podwójna pętla `for start … for end` złącza `words[start:end]` i `tagged[start:end]` dla każdej pary, czyli n(n+1)/2 wpisów po O(n) znaków, zbudowanych z góry. Przy 1000 słowach: 500 500 wpisów, 11 s i 2,2 GB, zanim ruszy układ.
3. **Pomiar każdego unikalnego fragmentu znak po znaku** — `linebreak.py:131-133` (`unscaled`) woła `measure_text` (`geometry.py:261`) dla każdego wariantu z tagami każdego wiersza-kandydata. `measure_text` parsuje tekst tworząc `_Char` na każdy znak (`geometry.py:482`) i mierzy: bez indeksu czcionek przez `PIL.ImageFont.getlength` (`geometry.py:1187`, 1,6 ms na wywołanie, cache 4096 wpisów przepełniony od n ≈ 90), z indeksem przez `_glyph` na każdy znak. Pamięć podręczna (`cache(measure)` w `_case` `layout.py:355`, `cache` na `unscaled`) działa — problem nie leży w powtórkach, tylko w liczbie unikalnych fragmentów O(n²) razy ich długości O(n).

Złożoność czasowa: O(n³) znaków w obu trybach; z profilem stała na znak jest ~5× większa (parser `_Char` + FreeType). Złożoność pamięciowa: O(n²) wpisów po O(n) znaków = O(n³) bajtów (tabela `_measure` i lista `found`).

## Realna górna granica linii dialogu

Skrypt `corpus_lines.py` (ten sam katalog), tylko odczyt `workspace/ready/**/*.ass` i `*.srt` (101 plików: 66 w korzeniu i 35 w `Nowy folder`; pliki `.spoken.pl.ass` i `.displayed.pl.ass` liczone razem z `.pl.ass`, więc część linii występuje dwukrotnie). Każdy plik przeszedł `split_subtitles`, więc decyzja spoken/displayed jest ta sama, jaką widzi `layout_translated`. Liczone są słowa widocznego tekstu (`BREAKABLE_SPACES.split(visible_text(..., preserve_hard_spaces=True))`) i znaki złączonego tekstu. Pełny wynik: `scratchpad\perf\corpus_out.md`.

| strumień | linii | maks. słów | maks. znaków | p99 słów | p99,9 słów |
|---|---|---|---|---|---|
| dialog (spoken, przez `layout_dialogue`) | 22 439 | **19** | **143** | 12–13 | 14 |
| szyldy (displayed, przez `fit_signs`) | 1 774 | 32 | 213 | 16 | 27 |

Najdłuższe linie dialogu:

| słów | znaków | plik | tekst |
|---|---|---|---|
| 19 | 143 | The.Laid-Off.Cheat-Granting.Mage…S01E03 | „KIEDY POSZŁEM PRZEPROSIĆ PRZYJACIÓŁKĘ, KTÓRA PRZEZ DWA LATA KISIŁA SIĘ W POKOJU, POCZĘSTOWANO NAS JABŁKOWYMI KRÓLICZKAMI” (tytuł odcinka zaklasyfikowany jako dialog) |
| 19 | 109 | The.Laid-Off.Cheat-Granting.Mage…S01E03 | „Jak ona śmie szczerzyć zęby i bawić się w poszukiwaczkę przygód po tym, jak zostawiła swoich ludzi na śmierć?” |
| 18 | 99 | [SubsPlease] Sasaki to Pii-chan S2 - 02 | „Za nic nie pozwolę, by jakiś dziwaczny demon wziął mnie na ręce, zanim zrobi to facet z sąsiedztwa.” |
| 17 | 91 | The.Detective.Is.Already.Dead.S02E01 | „Tyle że kryła się w niej druga osobowość, „Hel”, o której nawet ona sama nie miała pojęcia.” |

Rozkład słów w dialogu: 95% linii ≤ 10 słów, 99,6% ≤ 13, 100% ≤ 19. Przy 19 słowach `layout_dialogue` kosztuje 0,04 s w obu trybach, dlatego na prawdziwych plikach problem nie występuje.

Fizyczny sufit: pole dialogu to najwyżej 3 wiersze (`_DIALOGUE_RESCUE_LINES`), a kolano długości wiersza to 56 znaków (`_KNEE_CHARS`, 0,76 szerokości ekranu); przy średnio ~6 znakach na słowo plus spacja trzy pełne wiersze w szerokości 0,9 ekranu mieszczą ok. 30–35 słów. Linia dłuższa nie ma układu mieszczącego się w polu niezależnie od algorytmu — rdzeń i tak zwróciłby układ z flagą `OUTSIDE`.

## Wniosek

Koszt jest własnością pełnego przeglądu rdzenia (O(n²) kandydatów × O(n) na kandydata) i tabeli par `_measure`, nie błędem w pętli. Dla linii dialogu z korpusu (≤ 19 słów) układ liczy się w dziesiątkach milisekund. Uszkodzony albo nietypowy plik z linią o setkach słów blokuje rezydenta na minuty i może wyczerpać pamięć. Najprostsza naprawa to twardy limit słów na wejściu `layout_dialogue` z jawnym fallbackiem i licznikiem w raporcie — projekt w `plan.md`.
