---
kind: plan
status: draft
baseline: main 4365a51 (drzewo robocze czytane na gałęzi work/subtitles/03-pr66-review-fixes)
created: 2026-10-25
---

# Plan: styl mówcy i zakres od początku linii po tłumaczeniu (#34)

## Cel

Wdrożyć W1–W8 ze [specification.md](specification.md): zakres otwarty blokiem początku linii i zmiana stylu na styku wersów dostają znaczniki `<sN>`, tagi tych granic stają na znacznikach, a znaczniki są czytane na tym samym stylu, na którym powstały.

## Rezultat użytkownika

W polskim `.pl.ass` kursywa i kolor drugiego mówcy zaczynają się na jego kwestii, a nie na ostatnim słowie pierwszego. Wyróżnione pierwsze słowo źródła trafia na polskie słowo o tym samym znaczeniu także po zmianie szyku.

## Warunki końcowe

- [ ] S1–S6 ze specyfikacji spełnione, wyniki wpisane do opisu PR.
- [ ] Lista S3 przejrzana przez recenzenta innej rodziny modeli niż autor kodu.
- [ ] PR do `main` z `Closes #34`.

## Nie-cel

Ścieżka bez znaczników (Google, DeepL, uszkodzone znaczniki), więcej niż 2 zakresy, kolory otwierane blokiem początku linii (D2), puste wyróżnienie (D3), licznik odrzuceń. Wszystko to zostaje jak dziś.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| [specification.md](specification.md) | wymagania W1–W8, inwarianty, katalog K1–K28, decyzje D1–D5 |
| [evidence.md](evidence.md) | stan dziś, przyczyny, liczby bazowe |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/services/subtitles/AGENTS.md`, `anishift/text/AGENTS.md`, `tests/AGENTS.md` | reguły repo, pułapki `text.py`, konwencje testów |
| `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md` z `references/python.md`, `comments-docstrings.md`, `testing.md` | standard pracy i kodu |
| `docs/work/10-quality/fuzzy-signs-and-split.md` §C i aneks v4 C | wcześniejszy kontrakt stylów; to, co tu nie jest powtórzone, nie obowiązuje |

**Baseline:** `main` na 4365a51. Wykonawca zaczyna od świeżego `main` i przed zmianą sprawdza, czy `text.py`, `linebreak.py` i testy z mapy plików nie zmieniły się od tego commita. Jeśli się zmieniły, porównuje je z opisem w evidence i zgłasza różnice.

**Znane wcześniejsze failures:** w commicie `ecc7222` raportowano 5 testów qBittorrent i 3 testy czasowe niestabilne pod obciążeniem. Wykonawca zapisuje swój baseline z F0.

## Stan aktualny

- **Przyczyna C1 (mówca w wersie):** `marked_text` łączy wersy (`text.py:145`), a `_marked_boundaries` (`text.py:280-296`) bierze tylko granice z `0 < offset < długość wersu`. Tag na styku wersów nie dostaje znacznika, a przy jednowersowym przekładzie `_placed_tags` (`text.py:359-384`) mapuje go proporcjonalnie (`_map_globally`, `448-466`) i przyciąga do najbliższej krawędzi słowa.
- **Przyczyna C2/C3 (zakres od początku linii):** `_closes_a_range` (`text.py:304-317`) odrzuca linię, gdy pierwsza granica zamyka wyróżnienie, które nie jest bazą linii. Blok z offsetu 0 nie jest nigdy granicą znacznika.
- **Przyczyna ryzyka W6:** `tagged_line` (`linebreak.py:83`) bierze styl klonu, a `marked_text` w `translation_handler.py:439` styl źródła.

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| Granice tagów | `text.py::_boundaries(layout, merge_verses=True)` | grupuje tagi końca wersu k−1 i początku wersu k w jedno miejsce (styk) | klucz to pierwsza kotwica grupy |
| Stan wyróżnień | `text.py::_emphasis_at`, `_RE_EMPHASIS`, `_switched` | stan `\i \b \u \s` na pozycji, ze stylu i tagów | brak kolorów: dodać `\c`/`\1c`/`\3c` w tym samym miejscu, bez drugiego parsera |
| Negacja i baza linii | `text.py::_closes_a_range` | rozstrzyga W1 i K9 | `reopened` ma uwzględnić cięcia z W2 |
| Znaczniki | `text.py::_span_markers`, `_hugged_offset`, `_with_markers`, `_marker_anchors`, `_has_words`, `_pieces` | wstawianie, walidacja, kawałki | bez zmian semantyki walidacji |
| Styl źródła klonu | `restyle.py::clone_source` | W6 | `linebreak` może importować `restyle` (brak cyklu: `restyle` importuje `geometry` i `text`) |
| Zapisane odpowiedzi LLM | `tests/services/subtitles/test_subtitles_text.py::_saved_runs` | S5 bez nowych wywołań API | testy `integration`, pomijane bez danych |
| Powtórka writera | `python -m scripts.subtitle_quality replay`, `--compare … --events` | S4 | podaje widoczny tekst PL bez znaczników |

## Zakres

### In scope

- `text.py`: W1–W5 w `_marked_boundaries`, `_closes_a_range` i `_placed_tags` oraz prywatne helpery w tym pliku.
- `linebreak.py`: W6 w `tagged_line`.
- Testy z sekcji „Testy”.
- `anishift/services/subtitles/AGENTS.md`: pułapki `replace_visible_text` i `marked_text` (dziś l. 32–33) opisują nową regułę.

### Out of scope

Wszystko z „Poza zakresem” i „Odłożone” w specyfikacji.

### Forbidden

- Zmiany w `translation_handler.py`, `service.py`, `restyle.py`, `fitting.py`, `layout.py`, `anishift/text/markers.py`, promptach i silnikach tłumaczenia.
- Zmiana publicznych sygnatur `marked_text`, `replace_visible_text`, `restore_markers`, `tagged_line`.
- Zmiana `_MAX_MARKED_BOUNDARIES`, wag układu i ścieżki bez znaczników.
- Nowe pliki w repo poza `docs/work/20-style-boundaries/reviews/s3-marked-changes.md`. Testy trafiają do istniejących plików testowych, a skrypty pomiarowe zostają w scratchpadzie.
- `uv add`, edycja `pyproject.toml`, `--no-verify`, zmiany w `config/`, w `workspace/` (poza katalogiem `--out` w scratchpadzie) i w rezydencie.
- Opisowe komentarze w kodzie i proza w testach.

### Deferred

D2, D3 i licznik odrzuceń ze specyfikacji.

### Dozwolone decyzje lokalne

- Nazwy i podział prywatnych helperów w `text.py`.
- Wewnętrzna reprezentacja cięcia na styku: lokalny `(segment, offset)` albo pozycja globalna, jeśli wyniki K są dokładnie jak w tabeli.
- Pusty wers (`\N\N`): styki o tej samej pozycji globalnej łączą się w jedno cięcie.
- Polecenia wewnątrz `\t(…)` w bloku początku linii nigdy się nie przenoszą.
- Gdy `clone_source(event.style)` nie istnieje w `profile.styles`, `tagged_line` bierze styl zdarzenia jak dziś.

### Zatrzymaj się i wróć po decyzję, gdy

- spełnienie K wymaga zmiany pliku z listy Forbidden;
- S3 pokazuje zmianę `marked_text` w linii bez cięcia z W1 albo W2 (I1);
- S4 pokazuje jakąkolwiek różnicę zdarzeń;
- S2 zostawia bez znaczników kwestię spoza trzech wymienionych w specyfikacji;
- istniejący test spoza listy „Zmienione oczekiwania” zmienia wynik.

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres odczytu |
| --- | --- | --- | --- |
| 1 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md`, `references/python.md`, `comments-docstrings.md`, `testing.md` | standard | full |
| 2 | `AGENTS.md`, `anishift/AGENTS.md`, `anishift/services/subtitles/AGENTS.md`, `anishift/text/AGENTS.md`, `tests/AGENTS.md` | reguły i pułapki | full |
| 3 | `specification.md`, `evidence.md` (ten katalog) | kontrakt i dowody | full |
| 4 | `anishift/services/subtitles/text.py` | miejsce zmiany | full |
| 5 | `anishift/services/subtitles/linebreak.py:58-84`, `restyle.py:154-164, 204-225` | W6 | symbols |
| 6 | `anishift/application/translation_handler.py:417-457`, `service.py:564-643` | przepływ, tylko odczyt | symbols |
| 7 | `tests/services/subtitles/test_subtitles_text.py`, `test_subtitles_dialogue_layout.py` | konwencje i zmieniane testy | full |

## Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
| --- | --- | --- |
| Tekst dla tłumacza (`spoken_lines`, `displayed_lines`) | nowe znaczniki w ok. 77 kwestiach i części szyldów; klucze deduplikacji zmieniają się tylko w tych liniach | S2, S3; `tests/application/test_execution_handlers.py` (testy znaczników l. 920–971) zielone |
| `SpokenLine.text`, TTS, FBF | brak, bo znaczniki dodaje tylko handler (I5) | istniejące testy split i TTS |
| Układ dialogu (`layout_dialogue`, `style_changes`) | podział bloku początku linii (W5) zmienia tagi widziane przez pomiar | K2 przez `layout_dialogue` z profilem; `test_translated_ass_keeps_italics_hard_spaces_speakers_and_marked_words` |
| Szyldy (`fit_signs`, `_structure`) | nowe znaczniki na stykach wersów kolorowych szyldów | S3 dla szyldów; `test_sign_fitting.py` i `test_text_layout_catalogue.py` zielone |
| Ścieżka bez znaczników | nie może się zmienić (W7) | S4: zero różnic |
| Zapisane odpowiedzi LLM | `marked_text` musi dawać te same angielskie linie (I1) | `test_marked_text_reproduces_every_marked_line_of_the_saved_llm_runs` i dwa sąsiednie testy `integration` |
| Klony stylów | W6 zmienia styl odczytu znaczników dla klonów | K26; `test_subtitles_restyle.py` i `test_subtitles_translated_write.py` zielone |
| Aktywne prace | lokalna gałąź `work/subtitles/03-pr66-review-fixes` | branch z aktualnego `main`; przed PR rebase i ponowne S1–S6 |

## Target design

### Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `_marked_boundaries` | zbiór granic znaczników: wewnątrz wersu (jak dziś), styki ze zmianą stanu (W2), cięcie na offsecie 0 (W1), warunki W3 | ustawianie tagów |
| `_closes_a_range` | rozróżnienie negacji bazy linii (dziś) od zakresu otwartego na początku linii (W1); zwraca informację potrzebną do decyzji o cięciu na 0 | — |
| `_placed_tags` | tagi granic oznaczonych na pozycjach znaczników; dla cięcia W1 podział bloku początku linii (W5) | mapowanie bez znaczników (bez zmian) |
| `tagged_line` | styl odczytu znaczników = styl źródłowy klonu (W6) | wybór stylu w writerze |

### Algorytm (semantyka wiążąca, kształt kodu lokalny)

1. Wewnętrzne granice jak dziś: `_boundaries(…, merge_verses=False)`, `0 < offset < długość wersu`, bez samych komentarzy.
2. Styki (W2): dla każdego k ≥ 1 policz stan efektywny atrybutów zakresu na ostatnim grafemie przed stykiem i na pierwszym po nim, uwzględniając wszystkie tagi do pozycji styku włącznie. Różnica daje jedno cięcie obejmujące wszystkie tagi styku. Stan liczy jedno rozszerzenie `_emphasis_at` o `\c`/`\1c`/`\3c` i `\r`; kolory porównuje się liczbowo, bez alfy (Pojęcia w specyfikacji).
3. Kandydaci = granice z 1 i 2 posortowane po pozycji globalnej. Dalej obowiązują dzisiejsze warunki: najwyżej 4 granice i żadna w słowie.
4. `_closes_a_range` liczy `reopened` z kandydatów od drugiego (także styków). Jeśli dziś zwróciłby „zamyka”, to:
   - gdy zamykane wyróżnienie włączył blok początku linii, a nie styl, dodaj cięcie na offsecie 0 (W1) i sprawdź limit 4 granic jeszcze raz;
   - w przeciwnym razie brak znaczników (jak dziś, K14).
5. Warunki kawałków: każdy zakres ma słowo (dziś). Gdy w kroku 2 albo 4 doszło cięcie, poza zakresami musi zostać słowo (W3); w pozostałych liniach ten warunek nie działa.
6. `_placed_tags`: oznaczona granica (także styk i cięcie W1) bierze pozycję swojego znacznika. Dla cięcia W1 z każdego tagu na offsecie 0 przenoszą się polecenia `\i1`/`\b1`/`\u1`/`\s1` zamykanych liter, złożone w jeden blok `{…}` na pozycji znacznika. Reszta polecenia zostaje na 0 w pierwotnej kolejności, a pusty blok znika. Tagi nieoznaczone idą jak dziś.

### Mapa plików

| Ścieżka | Operacja | Rola zmiany |
| --- | --- | --- |
| `anishift/services/subtitles/text.py` | MODIFY | W1–W5 |
| `anishift/services/subtitles/linebreak.py` | MODIFY | W6 (`tagged_line`, import `clone_source`) |
| `anishift/services/subtitles/AGENTS.md` | MODIFY | pułapki `text.py` |
| `tests/services/subtitles/test_subtitles_text.py` | MODIFY | katalog K, zmienione oczekiwania |
| `tests/services/subtitles/test_subtitles_dialogue_layout.py` | MODIFY | W8 (K5), W5 przez układ (K2), W6 (K26) |
| `anishift/application/translation_handler.py`, `anishift/services/subtitles/service.py`, `restyle.py`, `fitting.py`, `anishift/text/markers.py` | READ ONLY | przepływ |

## Testy

Wszystkie testy mają marker `@pytest.mark.unit`, chyba że wskazano inaczej. Bez docstringów, komentarzy i prozy; scenariusz niesie nazwa testu i parametry. Oczekiwane wartości są dosłownie z tabeli K.

### Nowe w `test_subtitles_text.py`

| Test | Parametry |
| --- | --- |
| `test_marked_text_wraps_a_style_change_at_a_verse_break` | K5a, K6, K7, K10 (styl kursywny) |
| `test_marked_text_ignores_a_verse_break_without_a_style_change` | K11, K12, K17 |
| `test_marked_text_wraps_a_line_start_range_beside_a_mid_line_range` | K4 |
| `test_replace_visible_text_places_a_range_opened_at_the_line_start_on_the_marked_words` | K1, K3, K4 |
| `test_replace_visible_text_moves_only_the_emphasis_of_the_line_start_block` | K2 |
| `test_marked_text_wraps_a_range_closed_at_a_verse_end` | K27, K28 |
| `test_replace_visible_text_places_a_verse_break_range_on_the_marked_words` | K5a, K5b, K5c, K6, K7, K8, K9 (styl pogrubiony), K10 (styl kursywny), K27, K28 |
| `test_replace_visible_text_keeps_ranges_marked_inside_a_verse` | K21, K24 |
| `test_replace_visible_text_keeps_the_word_edge_mapping_without_intact_markers` | K18, K19 (styl kursywny), K22, K23, K25 (źródło K1, przekład bez znaczników `Co ty tu robisz, czemu?` → `{\i1}Co ty{\i0} tu robisz, czemu?`) |

### Nowe w `test_subtitles_dialogue_layout.py`

| Test | Parametry |
| --- | --- |
| `test_layout_dialogue_keeps_each_speaker_style_on_its_own_words` | K5a, K5b przez `layout_dialogue(event, text, None)`; oczekiwany tekst dosłowny, policzony raz i sprawdzony z Z1 (kursywa zaczyna się bezpośrednio przed myślnikiem drugiego mówcy, kwestia pierwszego nie ma `\i1`) |
| `test_layout_dialogue_keeps_the_line_start_block_before_a_moved_emphasis` | K2 przez `layout_dialogue(event, text, _profile())`: `{\pos(960,1024)}` zostaje na początku, `{\i1}tu{\i0}` na słowie |
| `test_tagged_line_reads_span_markers_against_the_style_a_clone_came_from` | K26: `RenderProfile` ze stylami `Default` (żółty tekst) i `Default (dialog)` (biały), zdarzenie w `Default (dialog)` |

### Zmienione oczekiwania (D5)

| Dziś | Po zmianie |
| --- | --- |
| `test_marked_text_leaves_a_range_opened_at_the_verse_start_unmarked` | `test_marked_text_wraps_a_range_opened_at_the_line_start`: K1 → `<s1>Why</s1> are you here?` |
| `test_marked_text_leaves_a_range_opened_at_a_later_verse_start_unmarked` | `test_marked_text_wraps_a_range_opened_at_a_later_verse_start`: K8 |
| `test_marked_text_leaves_emphasis_opened_at_the_line_start_and_closed_mid_line_unmarked` | `test_marked_text_wraps_emphasis_opened_at_the_line_start_and_closed_mid_line`: `<s1>You're</s1> society's darker side!` (styl pogrubiony) |
| `test_marked_text_leaves_a_negation_reopened_only_at_a_verse_end_unmarked` | `test_marked_text_wraps_a_negation_reopened_at_a_verse_end`: K9 |
| `test_marked_text_leaves_a_style_emphasis_switched_off_before_the_first_grapheme_unmarked` | zostaje z jednym parametrem (K14); drugi parametr przechodzi do `test_marked_text_wraps_a_style_change_at_a_verse_break` (K10) |

### Bez zmian (muszą przejść bez edycji)

`test_marked_text_leaves_a_word_closed_before_punctuation_unmarked` (K13), `…_leaves_verse_prefixes_and_suffixes_unmarked`, `…_leaves_more_than_two_ranges_unmarked` (K15), `…_leaves_in_word_effects_unmarked` (K16), `…_falls_back_when_markers_wrap_nothing` (K20), `…_keeps_a_verse_start_range_on_whole_words_without_markers`, `…_keeps_split_verse_prefixes_together_at_a_word_start` (K12), `…_moves_a_merged_verse_prefix_to_the_nearest_word_start`, trzy testy `integration` na zapisanych odpowiedziach LLM, `test_layout_dialogue_restores_span_markers_into_the_new_lines`, `test_translated_ass_keeps_italics_hard_spaces_speakers_and_marked_words`, `test_subtitles_translated_write.py::test_polish_reflow_preserves_speakers_and_inline_tags`, `test_text_layout.py::test_dialogue_gives_every_speaker_a_line_of_their_own`, `tests/application/test_execution_handlers.py` (l. 920–971).

## Plan wykonania

### Faza 0 - Preflight

**Działania:**

1. Przeczytaj kontekst w podanej kolejności.
2. `git switch main`, `git pull`, `git switch -c work/subtitles/04-style-boundaries`. Numer 03 jest zajęty przez `work/subtitles/03-pr66-review-fixes`; jeśli 04 też istnieje, weź kolejny.
3. Bramki repo na czystym `main`, z zapisem wyników.
4. Pomiar „przed” w scratchpadzie: spis S2 (metoda z evidence, punkt 6), wszystkie `marked_text` korpusu do pliku (podstawa S3), `python -m scripts.subtitle_quality replay workspace/.quality/corpus-pairs workspace/.quality/experiments/styles/pairs --out <scratchpad>/replay-before`.

**Gate:** bramki zielone poza zapisanymi failures; liczby bazowe zgodne z evidence (1032 kwestie z akcentem ze znacznikami, 73 od początku linii, 3 na styku, 1 z > 4 granicami). Różnicę zgłoś przed F1. Prototyp z evidence przewiduje po zmianie: 85 zmienionych kwestii i 478 zmienionych szyldów; to punkt odniesienia dla S3, nie próg.

### Faza 1 - W1–W5

**Działania:**

1. Wszystkie nowe i zmienione testy z sekcji „Testy” poza K26, uruchomione: czerwone tam, gdzie wymaga tego K.
2. Implementacja zgodna z algorytmem.
3. `uv run pytest tests/services/subtitles tests/application/test_execution_handlers.py`.

**Inwarianty:** I1–I7; bez zmian plików Forbidden.

**Gate:** wszystkie testy subtitles i handlera zielone; żaden test z listy „Bez zmian” nie edytowany.

### Faza 2 - W6: styl odczytu znaczników

Po F1, bo niezgodność stylu ujawnia dopiero granica z W1 albo W2 (dziś obie strony odrzucają takie linie tak samo).

**Działania:** test K26 (czerwony), potem zmiana `tagged_line`.

**Gate:** K26 zielone; pozostałe testy bez zmian.

### Faza 3 - Dowody na korpusie

**Działania:**

1. S2: spis „po” na tych samych plikach.
2. S3: diff `marked_text` przed/po; przy każdej zmienionej linii plik, numer linii i powód (W1, W2 albo W3). Zapis do `docs/work/20-style-boundaries/reviews/s3-marked-changes.md` (po polsku; tekst linii jak w źródle). Ten plik jest zamówionym dowodem planu.
3. S4: `replay … --out <scratchpad>/replay-after`, potem `replay --compare <before> <after> --events`.
4. S5: testy `integration` z `test_subtitles_text.py` oraz powtórka writera na `experiments/styles` (metoda z evidence, punkt 4) z tymi samymi wynikami.

**Human checkpoint:**

```text
Uruchom: nic; recenzent czyta reviews/s3-marked-changes.md
Zrób: dla każdej zmienionej linii sprawdź, czy nowe <sN> obejmują fragment o innym stylu niż reszta linii
Oczekiwany rezultat: każda zmiana to zakres od początku linii (W1) albo styk wersów ze zmianą stylu (W2)
Zwróć uwagę na: szyldy z kolorem na wersach (D1), linie z \alpha, \fs i \fn (nie mogą dawać cięć)
Przekaż wynik jako: lista numerów linii z oceną OK / problem i powodem
```

**Gate:** S2–S5 spełnione; checkpoint bez problemów albo problemy wróciły do F2.

### Faza 4 - Dokumentacja, bramki, commity, PR

**Działania:**

1. `anishift/services/subtitles/AGENTS.md`: pułapki `marked_text` i `replace_visible_text` opisują styki wersów, zakres od początku linii z podziałem bloku i styl źródłowy klonu.
2. Bramki repo:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

3. Commity według tematów (`scripts/hooks/check_commit_msg.py`, bez stopek i śladów AI):
   - `docs(subtitles): plan style boundaries after translation`: ten katalog `docs/work/20-style-boundaries/` bez `reviews/s3-marked-changes.md`;
   - `fix(subtitles): keep a speaker's style on its own words after translation`: W1–W5, testy, `AGENTS.md`, `reviews/s3-marked-changes.md`;
   - `fix(subtitles): read span markers against the style a dialogue clone came from`: W6 i K26.
4. PR do `main`, tytuł jak drugi commit, opis po angielsku: co się zmieniło, liczby S2 przed/po, wynik S4, link do listy S3, `Closes #34`. Bez stopek generatora.

**Gate:** bramki zielone; hook commit-msg przyjął wszystkie commity; recenzja krzyżowa (autor jednej rodziny modeli, recenzent innej) bez otwartych uwag krytycznych i poważnych.

## Dodatkowi wykonawcy

| Jednostka | Cel | Write scope | Wynik | Owner integracji |
| --- | --- | --- | --- | --- |
| Autor (`astra` albo `opus55`) | F0–F4 | pliki z mapy, scratchpad | branch, commity, wyniki S1–S6 | orkiestrator |
| Recenzent (inna rodzina modeli niż autor) | review kodu i checkpoint F3 | read-only | raport `review` z werdyktem | orkiestrator |

Bez pracy równoległej: zmiana dotyczy jednego pliku i jednego modelu problemu.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| #34 zamknięte (Z1, W8) | K5a/K5b przez `layout_dialogue` | odtwarza realne zdanie z Koori 03 i nierówne długości |
| Zakres od początku linii trafia po zmianie szyku | K1–K4 | dokładne oczekiwania |
| Nic się nie psuje bez znaczników | S4 zero różnic, K25 | cały korpus par, zdarzenie po zdarzeniu |
| Dziś dobre linie zostają dobre | I1 przez S3, S5, testy saved-run | korpus i prawdziwe odpowiedzi LLM |
| Skala naprawy | S2: 77 → 3 | ten sam zbiór i metoda co evidence; prototyp daje ten sam wynik |
| Dziś źle oznaczone zamknięcia przed `\N` | K27, K28, 11 kwestii w S3 | realne linie Kaguya i Katainaka |

### Human acceptance

- Przed kodem: właściciel akceptuje specyfikację, zwłaszcza katalog K i decyzje D1–D5.
- Po wdrożeniu (bez blokowania merge): właściciel ogląda w mpv najbliższy tłumaczony odcinek z linią dwóch mówców albo z akcentem na pierwszym słowie. PASS: styl jest na właściwych słowach.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
| --- | --- | --- | --- |
| W2 daje cięcia w szyldach animowanych | S3: szyldy z `\t`, `\clip`, wiele klatek | sprawdzić, czy zmienia się atrybut z listy; jeśli nie, poprawić stan efektywny | gdy reguła wymaga wyjątków dla rodzaju linii (D1) |
| Klucze `(segment, offset)` w `_placed_tags` nie pasują do cięć styku | K5/K8 czerwone mimo poprawnego `marked_text` | jedna reprezentacja pozycji dla oznaczonych granic | gdy trzeba zmienić `_boundaries` dla ścieżki bez znaczników (W7) |
| Podział bloku W5 zmienia pomiar albo `style_changes` | K2 przez `layout_dialogue` z profilem | poprawić kolejność poleceń w bloku pozostającym | gdy potrzebna zmiana w `geometry.py` |
| Więcej znaczników daje więcej odrzuceń w LLM | nie da się zmierzyć bez płatnych wywołań | ścieżka zapasowa jest dzisiejsza (W7) | gdy właściciel zgłosi błędy na realnym odcinku |
| Równoległa gałąź zmienia `text.py` | konflikt przy rebase | rebase i ponowne S1–S6 | konflikt semantyczny w znacznikach |

## Materialna zmiana

Przeplanowania wymaga zmiana publicznej sygnatury, wysyłanie wersów do tłumacza, zmiana promptu, objęcie szyldów osobną regułą albo zmiana ścieżki bez znaczników.

## Definition of Done

- [ ] W1–W8 działają, K1–K28 jako testy zielone.
- [ ] S2–S6 z liczbami w opisie PR, S3 przejrzane.
- [ ] Zakres i zakazy zachowane, bez plików spoza mapy.
- [ ] Recenzja krzyżowa zakończona.
- [ ] PR z `Closes #34`.

## Kontrakt wyniku

```text
status
gałąź i commity
liczby S2 przed/po
wynik S4 (różnice zdarzeń)
link lub ścieżka listy S3 i wynik checkpointu
wyniki bramek z komendami
odchylenia od planu i powód
otwarte ryzyka
```
