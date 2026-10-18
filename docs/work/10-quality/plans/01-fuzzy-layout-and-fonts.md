---
kind: plan
status: draft
baseline: work/quality/08-fuzzy-quality @ 2301cd0 (+ commit dokumentów planu)
created: 2026-10-18
---

# Plan: rozmyte układanie napisów, pomiar prawdziwą czcionką i czcionka dialogów

## Cel

Zastąpić sztywne heurystyki napisów (szyldy, lektor, kursywa i kolory, łamanie dialogów) heurystykami rozmytymi ze specyfikacji, oprzeć je na pomiarze tekstu prawdziwą czcionką odcinka, dodać czcionkę dialogów właściciela dołączaną do MKV i uporządkować strukturę kodu tak, żeby każda heurystyka miała jedno miejsce i jedno źródło prawdy.

## Rezultat użytkownika

Właściciel ogląda odcinek w mpv i widzi:

- szyldy w czcionkach typesettera, które nie wychodzą poza ekran, nie zlewają się z sąsiednimi napisami i nie są niepotrzebnie zmniejszane;
- dialogi w swojej czcionce (Officina), bez mieszania krojów w polskich literach, łamane po sensie;
- lektora, który czyta kwestie, a nie szyldy, także w małych stylach typu `Alt`;
- kursywę i kolory na właściwych słowach;
- wypalone MP4 w tych samych czcionkach co MKV.

## Warunki końcowe

- [ ] Wymagania [visual-quality.md](../visual-quality.md) są spełnione na galerii przed/po na tym samym tekście, ocenionej przez orkiestratora i właściciela (sekcja „Strategia dowodu”).
- [ ] Pomiar produkcyjny przechodzi test regresji wobec libass: p90 ≤ 1,5% i p99 ≤ 4% szerokości dla zdarzeń statycznych ≥ 100 px na 36 parach (research [measurement.md](../research/measurement.md)).
- [ ] Bramki repo przechodzą: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run mypy --platform linux anishift/ tests/`, `uv run pytest`. Wyjątek: znane testy prywatnego qBittorrent w worktree (przechodzą w głównym checkoucie).
- [ ] Legacy z sekcji „Decyzje” D8 jest usunięte, nie zostawione obok nowego kodu.
- [ ] Specyfikacje techniczne są zgodne z `visual-quality.md` i z decyzjami D1–D12 (poprawki w F0).

## Nie-cel

- Przesuwanie napisów (dialog do góry przy kolizji z szyldem), analiza obrazu, OCR.
- Limit długości tłumaczenia (otwarta decyzja właściciela).
- Głośność lektora, timing napisów (etapy 5–6 masterplanu).
- Wsparcie Linuksa poza tym, co wymusza `mypy --platform linux`.
- Skrypty `scripts/slime_*.py` (decyzja właściciela).

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| [visual-quality.md](../visual-quality.md) | wymaganie nadrzędne: cel, poziomy reguł, cechy i wagi |
| [fuzzy-signs-and-split.md](../fuzzy-signs-and-split.md) (A szyldy, B lektor, C style) | kontrakt mechaniki, z poprawkami D9 |
| [fuzzy-line-breaks.md](../fuzzy-line-breaks.md) | kontrakt mechaniki łamania, z poprawkami D9 |
| [research/code-map.md](../research/code-map.md) | stan kodu, legacy, drzewo docelowe |
| [research/measurement.md](../research/measurement.md) | metoda pomiaru i dowody dokładności |
| [research/fonts.md](../research/fonts.md) | dopasowanie czcionek w libass, korpus, test mpv właściciela, mux |
| [research/typesetting-principles.md](../research/typesetting-principles.md) | zasady profesjonalne, praktyka Shishy |
| [research/split-and-styles.md](../research/split-and-styles.md) | stan lektora i stylów na etykietach |
| `AGENTS.md` (root i obszarów), skille `simple`, `coding` (+ `references/python.md`, `comments-docstrings.md`, `testing.md`), `workflow`, `subagent`, `review` | reguły pracy i kodu |

**Baseline:** gałąź `work/quality/08-fuzzy-quality` w worktree `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift-wt\fuzzy`, commit `2301cd0` = integracja nocnych poprawek (`659afba`) + obie specyfikacje.

**Znane wcześniejsze failures:** nocne poprawki miały sztywne progi i trzy pogorszenia na galerii (szyldy 03, 04; łamanie 05, 06); agenci opisywali obrazy optymistycznie (astra nazwała pogorszenie poprawą); równoległe pełne pytest przeciążały CPU i dawały fałszywe porażki testów czasowych; testy qBittorrent nie startują w worktree.

## Stan aktualny

### Obecne zachowanie (F, szczegóły w code-map.md)

- Szyld: `fitting.py` mierzy Arialem 64 px, tolerancja 3%, podłoga 72%, wspólna skala obu osi, bez filtrów ekranu i kolizji; per zdarzenie.
- Lektor: `classifier.py` ocenia styl schodkami punktów; korekty per linia (aktor, `\an4–6`, nazwa); klasyfikacja działa trzy razy na różnych plikach (źródło, `FULL_PL`, `SPOKEN_PL`).
- Style: znaczniki `<sN>` dla ≤ 2 granic; warunki T1–T3 gubią akcenty.
- Łamanie: `translation/linebreak.py`, rankingi krotkami, 42 znaki; układ powstaje w `translation_verses` przed writerem, bez kontekstu stylu i fontu.
- Czcionki: AniShift nie dołącza żadnej; mkvmerge kopiuje załączniki źródła; wypalanie MP4 bez katalogu czcionek rysuje wszystko Arialem.

### Root cause

1. Brak wiarygodnego pomiaru wymusza sztywne progi znakowe i procentowe.
2. Układ powstaje w złym miejscu (przed writerem), więc nie zna fontu, stylu ani geometrii.
3. Decyzje mają wiele źródeł prawdy (trzy klasyfikacje, dwie definicje grafemu, dwa regexy `\p`).

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| Estymator pomiaru | `workspace/.quality/experiments/research-measurement/measure_lib.py` (`font_index`, `select_face`, `parse_event`, `estimate`) | algorytm i stałe (1000 px, atrament, widoczność obrysu, blur k=1,83, synteza kursywy 0,34, fallback glifów) | kod eksperymentu: przepisać według `coding`, z testami |
| Inwentarz czcionek | `.../research-fonts/inventory.py` | dopasowanie p3 ID1/ID4/PS i ocena wariantu jak libass | j.w. |
| Skalowanie tagów | `fitting.py` `_RE_SCALING`, `_scale_text` | nakładanie skali na `\fscx/\fscy`, `\t`, `\r` | przyjąć osobne `fx`, `fy` |
| Szerokość ekranu | `fitting.py` `_play_width` | PlayResX z fallbackiem | przenieść do `geometry.py` |
| Listy językowe | `linebreak.py` l.30–270 (`_CONJUNCTIONS`, `_PREPOSITIONS_MULTIWORD`, `_PRONOUN_HEADS`, `_VERB_HEADS`, `_TITLE_HEADS`, `_ADJECTIVE_ENDINGS`, `_REFLEXIVE_HEADS`…) i helpery `_clean`, `_tail`, `_names_pair`, `_protected` | dane i detektory sygnałów | przenieść do `lexicon.py` |
| Grafemy | `anishift/text/graphemes.py` `split_graphemes` | jedyna definicja grafemu | usunąć duplikat w `text.py` |
| Granice | `anishift/text/boundaries.py` (`SENTENCE_ENDINGS`, `PHRASE_CUT_CHARS`, `is_false_sentence_break`) | sygnały INT | importować wprost |
| Znaczniki | `anishift/text/markers.py` | składnia `<sN>` | bez zmian |
| Pomiar libass | `scripts/quality/render.py::measure_boxes`, `extract_attachments`, `render_shot` | kalibracja i galerie | narzędzie dev, nie produkcja |
| Galerie przed/po | `workspace/.quality/experiments/visual-fixes/*/` (`visualize.py`, `render_styles.py`, `render_split.py`) | wzorzec obrazu przed/po z powiększeniem | przenieść logikę do narzędzia |
| Ustawienia | `config/user_settings.py`, `field_catalog.py`, wzorzec `subtitle_max_chars_per_line` | nowe pole `dialogue_font_file` | — |
| Ekstrakcja | `services/extraction/service.py` `identify` (nazwy załączników) | lista załączników źródła | dodać ekstrakcję plików |

### Dowody

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| Pomiar Pillow (atrament, 1000 px, obrys/cień/blur, fallback) ma p90 1,14% wobec libass | measurement.md, `analysis.txt`, n=4622 | verified |
| libass nie kerninguje bez `Kerning: yes`; 0/284 plików ma ten nagłówek | measurement.md H2 | verified |
| libass dopasowuje p3 ID1, ID4, PS; nie ID16 | fonts.md §2–3, test mpv | verified |
| mpv właściciela rysuje „ITC Officina Sans Std PL Book” plikiem Bold | fonts.md §3, test `--no-config` | verified |
| Gandhi Sans (20/40 par) nie ma ąćęńśźż; mieszanie krojów | fonts.md §4, log libass | verified |
| Wypalanie MP4 rysuje szyldy Arialem | fonts.md, `burn1.log` vs `burn2.log` | verified |
| Klasyfikacja działa trzy razy | code-map.md §0.2 | verified |
| Pogorszenia nocnych poprawek (szyldy 03/04, łamanie 05/06) | `visual-fixes/`, ocena orkiestratora | verified (human) |

## Decyzje orkiestratora

Wiążące dla wszystkich wykonawców. Każda ma powód; zmiana wymaga przeplanowania.

- **D1. Pomiar produkcyjny = Pillow + fontTools**, metoda z measurement.md §Rekomendacja pkt 1–8: pomiar w stałym rozmiarze 1000 px i skalowanie liniowe; skala `fs / (winAscent + winDescent)` (fallback typo/bbox jak libass) × `fscx/100`; bez kerningu; szerokość wiersza = od lewej krawędzi atramentu pierwszego glifu do prawej ostatniego, plus `fsp·fscx/100` między znakami; obrys tylko przy `\3a < FF` lub `BorderStyle 3`, cień tylko przy `\4a < FF`; blur `+k·σ` na stronę, k = 1,83; `BorderStyle 3`: pudełko z advance + `2·bord` (+`shad`); synteza kursywy + 0,34 × wznios; wysokość z atramentu, interlinia `fs·fscy/100`. Plik z `Kerning: yes` → status przybliżony. **Powód:** jedyna zmierzona metoda spełniająca bramkę; RAQM niedostępny i niepotrzebny.
- **D2. Dopasowanie czcionek jak libass:** klucze p3 ID1 (rodzina, wszystkie języki), p3 ID4 (pełna nazwa) i nazwa PostScript, bez rozróżniania wielkości liter; ID16 nie jest kluczem. Trafienie pełną nazwą/PS wybiera krój od razu; trafienie rodziną wybiera wariant o najmniejszym `73·|Δwaga|/256` + kara kursywy (+1 brak żądanej, +4 niechciana). Gdy rodzina jest w czcionkach odcinka, wybór tylko spośród nich. Synteza pogrubienia, gdy żądana waga > waga kroju + 150; kursywy, gdy żądana kursywa, a krój jej nie ma. Brakujący glif: najpierw inne kroje tej rodziny z glifem, potem **krój zastępczy profilu**: czcionka dialogów właściciela, jeśli ustawiona (tak działa mpv właściciela przez `sub-font`), w przeciwnym razie Arial tej samej wagi i nachylenia. **Powód:** fonts.md §2, measurement.md §„Gdzie estymacja zawodzi”.
- **D3. Decyzje lektor/ekran liczone raz, na źródle.** Zadanie `SPLIT_SUBTITLES` dostaje w planerze także artefakt źródłowy i przenosi decyzje źródła na `FULL_PL` po indeksie zdarzenia (writer zachowuje 1:1 zdarzenia, pamięć „Stage 4 ASS write variant”). Przy niezgodnej liczbie zdarzeń: klasyfikacja `FULL_PL` z ostrzeżeniem w logu. TTS czyta `SPOKEN_PL` jako w całości spoken, bez trzeciej klasyfikacji. Ścieżka polskiego źródła (`NORMALIZE`) klasyfikuje swoje źródło jak dotąd. **Powód:** code-map §0.2; jedna prawda zamiast trzech.
- **D4. Układ tylko w writerze.** `translation_verses` przestaje układać wiersze: tłumaczenie oddaje nierozbity tekst (z odtworzonymi znacznikami), a writer per zdarzenie robi: podmiana czcionki → tekst i tagi (C) → łamanie dialogu (LB) albo dopasowanie szyldów (A, raz na plik). **Powód:** pomiar wymaga stylu, fontu, marginesów i `PlayRes`; ma je tylko writer.
- **D5. Czcionka dialogów** (`subtitles/restyle.py`): nowe pole ustawień `dialogue_font_file` (ścieżka, puste = wyłączone) w `user_settings.py` i panelu (Ustawienia), przenoszone do snapshotu planu jak `subtitle_max_chars_per_line`. Walidacja przed przetwarzaniem: fontTools czyta plik, ma p3 ID1 i wszystkie 18 polskich liter; inaczej brak podmiany i ostrzeżenie (bez przerywania). Style, w których większość linii jest spoken, dostają `Fontname` = p3 ID1 pliku; ich linie displayed dostają na początku `{\fn<oryginalny Fontname>}`; istniejące `\fn` w liniach zostają. Do MKV dołączamy wszystkie pliki z katalogu wybranego pliku o tej samej rodzinie p3 ID1 (`--attach-file`), pomijając plik, gdy źródło ma załącznik o tej samej nazwie. SRT bez zmian. **Powód:** fonts.md §5–6; decyzja właściciela 18.10.
- **D6. Czcionki przy wypalaniu MP4:** ekstrakcja załączników źródła (`extraction.extract_attachments`) do katalogu czcionek odcinka w `workspace/temp`, dołożenie plików czcionki dialogów, przekazanie `fonts_dir` do `subtitle_filter_argument`. **Powód:** istniejący błąd z tą samą infrastrukturą co D5; mały koszt, widoczny zysk.
- **D7. Struktura** (szczegóły w „Docelowe drzewo”): nowa domena `services/fonts/` (bez pysubs2 i bez subtitles, więc composition i extraction mogą jej używać); w `services/subtitles/` moduły `fuzzy.py`, `geometry.py`, `ranges.py`, `lexicon.py`, `layout.py`, `restyle.py`; `linebreak.py` przenosimy z `translation/` do `subtitles/`; `layout_config.py` dzielimy (limity układu → `subtitles/layout.py`, rozmiar kawałka tłumaczenia zostaje w `translation/`); `scripts/quality/` → `scripts/subtitle_quality/`, testy → `tests/scripts/subtitle_quality/`.
- **D8. Legacy do usunięcia (nie zostawiamy obok):** w `fitting.py` pomiar Arialem, `_MIN_SCALE`, `_WIDTH_TOLERANCE`, `_FONT_SIZE`, wspólny czynnik osi, `_pixel_scale`, `_wraps_only_translation`, `_reflow`, `_BALANCED_LINES`, `fit_sign_text`; w `classifier.py` schodkowe `_classify_metrics`, progi `_SCORE_*`, `_FRAC_*`, `_POS_*`, `_PUNCT_MIN`, `_AVG_TEXT_MIN`, `_DLG_MAX_POS_RATIO`, `UNCERTAIN` jako kategoria decyzyjna, `line_category`, `_sign_actor`, `_RE_MID_ALIGN`, `_RE_POS` (druga definicja położenia), `_RE_DRAW` (duplikat); w `text.py` własne grafemy (l.54–65, 595–634), martwe `insertions`, `_RE_DRAW_TAG`, T1–T3 (`_MAX_MARKED_BOUNDARIES`, `_RE_EMPHASIS_OFF`, `_marked_boundaries`) po przeniesieniu logiki do `ranges.py`; w `linebreak.py` `_dialogue_cut`, `_dialogue_candidates`, `_TOP_HEAVY_PENALTY`, `_OVERFLOW_TOLERANCE`, rekurencyjny `_split`, `_best_cut`, `_weight`, `_greedy_cut`, `_proportional_boundaries`; `service.py` `reflow_polish_dialogue`, `preview_styles`; `translation_handler.translation_verses` (część układająca); `subtitle_handler.LegacySubtitleProducts`/`LegacySubtitleAdapter`; import `SENTENCE_ENDINGS` przez `translation.chunking` (import wprost z `text.boundaries`). `Category` zostaje tylko, jeśli po B ma konsumenta; inaczej usunąć. **Powód:** reguła właściciela „wycinaj legacy jak raka”; code-map §2.
- **D9. Poprawki specyfikacji (w F0, przed kodem):** `fuzzy-line-breaks.md` l.12 i 41 (font nienaruszalny → wyjątek stylów dialogowych D5); `fuzzy-signs-and-split.md` §A.3 (metoda pomiaru D1, klucze D2, `u` dla prawdziwego fontu ≈ 0,012, fallback modelowany krojem zastępczym D2 zamiast stałego `u = 0,07`), §B (D3), §A.4 (szyld wielowierszowy może zmienić liczbę wierszy, gdy czytelność „bardzo źle”, decyzja domyślna D12-3), drobne rozjazdy plik:linia z code-map §2. Galeria łamania dostaje przypadki 05 i 06 z `visual-fixes/line-breaks/` jako kontrakt (cięcie po przecinku musi wygrać).
- **D10. Jedno źródło funkcji rozmytych:** `subtitles/fuzzy.py` (`rise`, `fall`, `nor`), używane przez A, B i LB.
- **D11. Raport przebiegu bez nowego artefaktu:** writer zwraca liczniki (poziomy ostateczne szyldów, statusy przybliżone, `overflow_unavoidable`, rozluźnione ochrony fraz, glify zastępcze, podmiana czcionki) i loguje jedno strukturalne podsumowanie na plik (`get_logger`, bez tekstów i ścieżek absolutnych). Narzędzie jakości czyta te same liczniki.
- **D12. Otwarte decyzje właściciela → wartości domyślne do czasu galerii:** (1) szyld szerszy od angielskiego na wolnym tle: kara rośnie powoli (wolniej niż przy ramce z maski lub rysunku); (2) czytelność: kara od 30 px, pełna przy 16 px wysokości wiersza w 1080p, oznaczone „do kalibracji”; (3) szyld wielowierszowy może zmienić liczbę wierszy przy czytelności „bardzo źle”; (4) bez limitu długości tłumaczenia; (5) `dialogue_font_file` domyślnie puste, właściciel wskazuje plik w panelu; (6) szyld w foncie bez polskich liter: bez zmiany czcionki, raport.

## Zakres

### In scope

Wszystko z decyzji D1–D12, testy, narzędzie replay i galerie przed/po, aktualizacja `AGENTS.md` obszarów (`subtitles`, nowe `fonts`, `composition`, `scripts`), README/ustawienia panelu dla nowego pola.

### Out of scope

Nie-cele z sekcji wyżej; zmiana silników tłumaczenia i promptów poza przekazaniem nierozbitego tekstu i bazy stylu (`base`) do `marked_text`.

### Forbidden

- Edycja `pyproject.toml` ręcznie (zależności tylko `uv add fonttools`).
- Commity na `main`, merge do `main`, push — bez akceptacji właściciela.
- Zmiany w głównym checkoucie `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift` (może z niego działać rezydent właściciela) poza `workspace/.quality/`.
- Wywołania płatnych API (tłumaczenie, TTS) bez zgody orkiestratora.
- Zabijanie procesów python; więcej niż jeden pełny `pytest` naraz na maszynie (pełny pytest tylko z `-n 8` albo sekwencyjnie, uzgodnione z orkiestratorem).
- Komentarze opisowe w kodzie, wielolinijkowe docstringi bez potrzeby, `except Exception`, druga wersja istniejącego helpera.

### Deferred

Osadzanie czcionki w `[Fonts]` ASS; korekta wielkości czcionki dialogów; zastępcza czcionka całych szyldów bez polskich liter; przenoszenie dialogu do góry; limit długości tłumaczenia.

### Dozwolone decyzje lokalne

Nazwy prywatnych funkcji, podział prywatnych helperów, kolejność testów, techniczne szczegóły cache — o ile publiczne kontrakty z tego planu zostają.

### Zatrzymaj się i wróć po decyzję, gdy

- publiczny kontrakt z tego planu nie da się zrealizować albo wymaga zmiany innej jednostki;
- test regresji pomiaru nie spełnia progu D1;
- zmiana dotyka planera poza D3/D5/D6 albo formatu artefaktów;
- galeria pokazuje pogorszenie, którego nie da się uzasadnić ważeniem cech.

## Kontekst do przeczytania (każdy wykonawca)

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\.agents\skills\simple\SKILL.md`, `coding\SKILL.md`, `coding\references\python.md`, `comments-docstrings.md`, `testing.md` | standard kodu | full |
| 2 | `AGENTS.md` (root), `anishift/AGENTS.md`, `tests/AGENTS.md`, AGENTS.md obszaru | reguły repo | full |
| 3 | ten plan | kontrakt jednostki | full |
| 4 | `visual-quality.md` | cel | full |
| 5 | sekcja specyfikacji technicznej jednostki | mechanika | section |
| 6 | research jednostki | dowody, gotowe algorytmy | full |

`.agents/` nie jest widoczne w worktree — skille czytać z głównego checkoutu (ścieżka wyżej).

## Impact scan

| Kontrakt / subsystem | Ryzyko | Obowiązek regresyjny |
| --- | --- | --- |
| Writer ASS/SRT (`_translated_file`) | wysokie: kolejność kroków, 1:1 zdarzeń, idempotencja | testy `test_subtitles_translated_write.py`, replay na 36 parach, liczba zdarzeń wejście = wyjście |
| Planer (`SPLIT_SUBTITLES` wymaga źródła, D3; ustawienie czcionki, D5; katalog czcionek, D6) | średnie: lifecycle artefaktów, wznowienie | `test_planner.py`, `test_auto_preset_smoke.py`, plan z i bez ustawienia czcionki |
| Tłumaczenie (`translation_handler`) | średnie: nierozbity tekst, `base` do `marked_text` | `test_translate_only.py`, `test_translation_layout_wiring.py` |
| TTS (`SPOKEN_PL` bez reklasyfikacji) | niskie | `test_execution_handlers.py` sekcja TTS |
| Composition (mkvmerge `--attach-file`, ffmpeg `fontsdir`) | niskie | `test_composition_commands.py` nowe przypadki |
| Ustawienia/panel | niskie | testy `config/` i `cli/interactive` dla nowego pola |
| Narzędzie jakości | niskie | `tests/scripts/subtitle_quality/` |
| Wydajność | niskie: 0,2–0,7 ms/zdarzenie | pomiar czasu replay na 36 parach w raporcie jednostki |

## Target design

### Odpowiedzialności i ownership

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `services/fonts/index.py` | indeks krojów z plików, dopasowanie nazwy jak libass, krój zastępczy, pokrycie znaków | pysubs2, style ASS |
| `services/fonts/metrics.py` | metryki glifów w 1000 px (advance, atrament, wznios), cache | tagi ASS |
| `services/subtitles/geometry.py` | profil renderu pliku, spany tagów, szerokość/wysokość tekstu zdarzenia, dostępna szerokość, prostokąt na ekranie, emulacja zawijania libass, przecięcia | wybór wariantu |
| `services/subtitles/fuzzy.py` | `rise`, `fall`, `nor` | progi domen |
| `services/subtitles/classifier.py` | B: profil stylu, dialogowość linii, weto, serie, decyzje | układ tekstu |
| `services/subtitles/ranges.py` | C: stan stylu, zakresy, znaczniki, kotwice | tłumaczenie |
| `services/subtitles/text.py` | tag-bezpieczne operacje na widocznym tekście | zakresy stylu |
| `services/subtitles/lexicon.py` | polskie listy i detektory sygnałów | ocena cięcia |
| `services/subtitles/linebreak.py` | LB: kandydaci cięć, ocena Q, ratunek, tryb `unmeasured` | szyldy |
| `services/subtitles/layout.py` | limity układu z ustawień (`L_ref`, `N_ref`) | rozmiar kawałka tłumaczenia |
| `services/subtitles/fitting.py` | A: obiekty, kandydaci, filtry, szkody, wybór, raport | łamanie dialogu |
| `services/subtitles/restyle.py` | podmiana czcionki stylów dialogowych | dołączanie plików do MKV |
| `services/subtitles/service.py` | load, split, writery (orkiestracja kroków writera) | heurystyki |
| `services/extraction` | wyciąganie załączników MKV do katalogu | wybór czcionek |
| `services/composition` | `--attach-file`, `fontsdir` | decyzja, które pliki dołączyć (application) |
| `application/*` | przekazanie ustawień, artefaktów, list plików czcionek | heurystyki |
| `scripts/subtitle_quality/` | kalibracja libass, replay, galerie, metryki | produkcja |

### Przepływ danych (docelowy)

```text
źródło ASS/SRT (+ załączniki MKV)
-> extraction: katalog czcionek odcinka (D6)
-> split_subtitles(źródło): decyzje spoken/displayed (B)            [raz, D3]
-> marked_text(..., base) -> tłumaczenie -> restore_markers (C)      [tekst nierozbity, D4]
-> writer _translated_file:
     profile = RenderProfile.from_subs(subs, FontIndex(czcionki odcinka + czcionka dialogów))
     restyle_dialogue(subs, decyzje, czcionka dialogów)               (D5)
     per zdarzenie: replace_visible_text (C)
       dialog -> layout_dialogue(event, text, profile, limits) (LB)
     szyldy -> fit_signs(out, teksty, profile, decyzje) (A, raz na plik)
     -> FULL_PL + liczniki (D11)
-> SPLIT_SUBTITLES(FULL_PL, decyzje źródła) -> SPOKEN_PL / DISPLAYED_PL   (D3)
-> TTS(SPOKEN_PL jako całość spoken)
-> composition: mkvmerge (+ --attach-file czcionki dialogów) / ffmpeg (fontsdir)
```

### Docelowe drzewo

```text
anishift/
├── text/                                   # KEEP (boundaries, graphemes, markers)
├── services/
│   ├── fonts/                              # NEW domena
│   │   ├── __init__.py                     # NEW: FontIndex, FontFace, FontMatch, read_faces
│   │   ├── index.py                        # NEW
│   │   ├── metrics.py                      # NEW
│   │   ├── types.py                        # NEW
│   │   └── AGENTS.md                       # NEW
│   ├── extraction/service.py               # MODIFY: extract_attachments
│   ├── subtitles/
│   │   ├── __init__.py                     # MODIFY: publiczne API
│   │   ├── service.py                      # MODIFY: writer = orkiestracja; − reflow_polish_dialogue, − preview_styles
│   │   ├── fuzzy.py                        # NEW
│   │   ├── geometry.py                     # NEW
│   │   ├── classifier.py                   # MODIFY (przepisany wg B)
│   │   ├── ranges.py                       # NEW (C)
│   │   ├── text.py                         # MODIFY: − grafemy, − T1–T3, − martwy kod
│   │   ├── lexicon.py                      # NEW (listy z linebreak.py)
│   │   ├── linebreak.py                    # NEW tu (przeniesiony z translation/, przepisany wg LB)
│   │   ├── layout.py                       # NEW (limity układu z layout_config)
│   │   ├── fitting.py                      # MODIFY (przepisany wg A)
│   │   ├── restyle.py                      # NEW
│   │   └── AGENTS.md                       # MODIFY
│   ├── translation/
│   │   ├── linebreak.py                    # DELETE (przeniesiony)
│   │   └── layout_config.py                # MODIFY: tylko rozmiar kawałka tłumaczenia (nazwa wg kodu)
│   └── composition/
│       ├── types.py                        # MODIFY: attached_fonts, fonts_dir
│       └── commands.py                     # MODIFY: --attach-file, fontsdir
├── application/
│   ├── planner.py                          # MODIFY: D3, D5, D6
│   ├── translation_handler.py              # MODIFY: bez układu w translation_verses
│   ├── subtitle_handler.py                 # MODIFY: decyzje źródła; − LegacySubtitleAdapter
│   ├── tts_handler.py                      # MODIFY: SPOKEN_PL bez reklasyfikacji
│   └── composition_handler.py              # MODIFY: pliki czcionek
├── config/user_settings.py, field_catalog.py   # MODIFY: dialogue_font_file
scripts/
├── quality/                                # DELETE (przemianowany)
└── subtitle_quality/                       # NEW nazwa: render, metrics, report, frames, episode, calibrate, replay, compare
tests/
├── services/fonts/                         # NEW
├── services/subtitles/                     # MODIFY + NEW (fuzzy, geometry, ranges, restyle, linebreak przeniesiony)
└── scripts/subtitle_quality/               # NEW (przeniesione test_quality_*)
```

### Publiczne kontrakty

Sygnatury są wiążące dla jednostek równoległych. Wykonawca może dodać pola i funkcje prywatne; zmiana poniższych wymaga zgody orkiestratora.

```python
# anishift/services/fonts/types.py
@dataclass(frozen=True, slots=True)
class FontFace:
    path: Path
    face_index: int
    family_names: frozenset[str]   # p3 ID1, casefold
    full_names: frozenset[str]     # p3 ID4 + PostScript, casefold
    weight: int                    # OS/2 usWeightClass
    italic: bool
    units_per_em: int
    ascent: int                    # winAscent z fallbackiem libass
    descent: int
    codepoints: frozenset[int]

@dataclass(frozen=True, slots=True)
class FontMatch:
    face: FontFace
    exact: bool                    # False = krój zastępczy profilu
    synthetic_bold: bool
    synthetic_italic: bool

# anishift/services/fonts/index.py
def read_faces(path: Path) -> tuple[FontFace, ...]
class FontIndex:
    @classmethod
    def from_paths(cls, paths: Iterable[Path], *, fallback: Path | None = None) -> FontIndex
    def match(self, name: str, *, weight: int, italic: bool) -> FontMatch | None
    def glyph_match(self, request: FontMatch, codepoint: int) -> FontMatch   # D2: rodzina, potem zastępczy
def polish_coverage(face: FontFace) -> str                                    # brakujące z „ąćęłńóśźżĄĆĘŁŃÓŚŹŻ”

# anishift/services/subtitles/geometry.py
@dataclass(frozen=True, slots=True)
class RenderProfile:
    play_res_x: int
    play_res_y: int
    wrap_style: int
    scaled_border: bool
    fonts: FontIndex
    @classmethod
    def from_subs(cls, subs: SSAFile, fonts: FontIndex) -> RenderProfile

@dataclass(frozen=True, slots=True)
class TextBox:
    line_widths: tuple[float, ...]   # px skryptu, z widocznym obrysem/cieniem/blur
    width: float
    height: float
    edge: float                      # nieskalująca się część (obrys, cień, blur) w poziomie
    status: Literal["exact", "approximate"]
    fallback_glyphs: int

def measure_text(event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0) -> TextBox
def available_width(event: SSAEvent, profile: RenderProfile) -> float
def wrap_text(event: SSAEvent, text: str, profile: RenderProfile) -> str        # emulacja zawijania libass
def screen_rect(event: SSAEvent, box: TextBox, profile: RenderProfile) -> Rect  # kotwica: \pos / \an / marginesy

# anishift/services/subtitles/fuzzy.py
def rise(x: float, a: float, b: float) -> float
def fall(x: float, a: float, b: float) -> float
def nor(*degrees: float) -> float

# anishift/services/subtitles/fitting.py
@dataclass(frozen=True, slots=True)
class SignFit:
    texts: dict[int, str]            # indeks zdarzenia -> tekst po dopasowaniu
    report: FitReport                # liczniki D11
def fit_signs(subs: SSAFile, texts: Mapping[int, str], profile: RenderProfile) -> SignFit

# anishift/services/subtitles/linebreak.py
@dataclass(frozen=True, slots=True)
class LayoutLimits: max_chars: int; max_lines: int
@dataclass(frozen=True, slots=True)
class DialogueLayout:
    text: str                        # z jawnymi \N
    flags: frozenset[str]            # np. "overflow_unavoidable", "relaxed_phrases", "unmeasured"
def layout_dialogue(event: SSAEvent, text: str, profile: RenderProfile | None, limits: LayoutLimits) -> DialogueLayout

# anishift/services/subtitles/restyle.py
@dataclass(frozen=True, slots=True)
class DialogueFont:
    family: str                      # p3 ID1
    files: tuple[Path, ...]          # warianty tej rodziny z katalogu pliku
    @classmethod
    def from_file(cls, path: Path) -> DialogueFont      # SubtitleError przy braku polskich liter/nazwy
def restyle_dialogue(subs: SSAFile, decisions: Sequence[Decision], font: DialogueFont) -> SSAFile

# anishift/services/subtitles/ranges.py (C)
def marked_text(text: str, base: StyleState, styles: Mapping[str, SSAStyle]) -> str   # nazwy wg kodu C.2
```

`Decision`, `SubtitleSplit`, `split_subtitles` zachowują dzisiejszy kształt publiczny (pola `decisions`, `verdicts`, `spoken`, `stats`); `StyleVerdict` zmienia pola wg specyfikacji B (D „Zmiana API”).

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| Rodzina nieobecna w czcionkach odcinka i systemie | krój zastępczy profilu, status przybliżony, licznik | automated |
| Glif spoza `cmap` | krój tej rodziny z glifem, potem zastępczy; licznik glifów | automated (Gandhi Sans) |
| `Kerning: yes` | status przybliżony | automated |
| Zdarzenie animowane/obracane | dopasowanie jak statyczne, status przybliżony, osobny licznik | automated |
| Plik czcionki dialogów bez polskich liter / nieczytelny | brak podmiany, ostrzeżenie, praca trwa | automated |
| Źródło ma załącznik o nazwie pliku czcionki dialogów | bez ponownego dołączenia | automated |
| Liczba zdarzeń FULL_PL ≠ źródła | klasyfikacja FULL_PL + ostrzeżenie | automated |
| Napis identyczny z angielskim | wynik bajtowo identyczny | automated |
| SRT | bez podmiany czcionki, łamanie w trybie bez profilu stylu (`profile=None` → `unmeasured`) | automated |
| Cięcie po przecinku kontra krótsze cięcie (galeria 05/06) | wygrywa przecinek | automated + human |
| Sąsiednie szyldy („piętnastyPojawił”) | wariant bez kolizji | automated + human |

## Plan wykonania

Zasada wykonawcza: każda jednostka ma własny worktree i gałąź od wyniku poprzedniej fali; autor = subagent Claude (Opus 5.5); przegląd = świeża astra (OpenCode, inna rodzina); poprawki = autor; weryfikacja = recenzent. Commity po temacie, format `typ(scope): opis`, bez stopek AI. Orkiestrator scala do `work/quality/08-fuzzy-quality` i rozwiązuje konflikty.

### Faza 0 — Preflight i przebudowa bez zmiany zachowania (1 wykonawca, sekwencyjnie)

**Cel:** stan, od którego jednostki równoległe nie będą się wzajemnie blokować.

**Działania:**

1. `uv add fonttools`.
2. Poprawki specyfikacji D9 (commit dokumentów).
3. Przeniesienie `translation/linebreak.py` → `subtitles/linebreak.py`, podział `layout_config.py` (D7), aktualizacja importów i testów (przeniesienie testów do `tests/services/subtitles/`).
4. `scripts/quality` → `scripts/subtitle_quality`, testy → `tests/scripts/subtitle_quality/`, odwołania w dokumentach.
5. Usunięcie martwego i zdublowanego kodu bez zmiany zachowania: grafemy w `text.py` → `text/graphemes.py`; martwe `insertions`; `_RE_DRAW_TAG`/`_RE_DRAW` → `is_drawing`; import `SENTENCE_ENDINGS` wprost; `LegacySubtitleAdapter` z testem; `preview_styles`.
6. `subtitles/fuzzy.py` z testami.
7. Szwy writera: `_translated_file` woła trzy prywatne funkcje kroków (`_layout_dialogue`, `_fit_signs_batch`, `_restyle`), dziś delegujące do obecnego zachowania. Jednostki U4/U5/U6 wymieniają tylko ich wnętrze.
8. `scripts/subtitle_quality/replay.py`: dla każdej pary bierze `source.en.ass`, dzieli je i podaje writerowi polski tekst widoczny z istniejącego `output.pl.ass` (zdarzenia 1:1 po indeksie), bez LLM. Zapisuje wynik do wskazanego katalogu i porównuje bajtowo z innym katalogiem. To siatka regresji dla wszystkich jednostek.

**Gate:** wszystkie bramki zielone; replay 36 par na kodzie po F0 daje wynik bajtowo identyczny z replayem na `2301cd0`.

### Fala A — równolegle po F0

| Jednostka | Cel | Write scope | Spec / research |
| --- | --- | --- | --- |
| **U1 Pomiar** | `services/fonts/*`, `subtitles/geometry.py`, `extraction.extract_attachments`, `scripts/subtitle_quality/calibrate.py` (test regresji wobec libass, progi D1) | te ścieżki + testy | D1, D2; measurement.md, fonts.md; A.2–A.3 |
| **U2 Lektor** | `classifier.py` wg B, D3 (planer: źródło dla SPLIT, TTS bez reklasyfikacji), `subtitle_handler`, `tts_handler`, testy B, test regresji E8 | `classifier.py`, `service.py` (tylko split), `planner.py` (SPLIT), `subtitle_handler.py`, `tts_handler.py`, testy | B, D3; split-and-styles.md |
| **U3 Style** | `ranges.py` wg C, `text.py` (bez T1–T3), `marked_text(base, styles)` w `translation_handler` (tylko wywołania `marked_text`/`restore_markers`) | `ranges.py`, `text.py`, `text/markers.py`, wskazane linie `translation_handler.py`, testy | C; split-and-styles.md |
| **U7 Galerie** | `scripts/subtitle_quality/compare.py`: obraz przed/po na tym samym tekście z dwóch katalogów replay, wybór przypadków (największe zmiany szerokości, kolizji, cięć, decyzji lektora, przypadki trudne), powiększenie, podpis po polsku; reuse `visual-fixes/*` | `scripts/subtitle_quality/compare.py`, testy | sekcja „Strategia dowodu” |

**Gate fali A:** bramki zielone w każdym worktree; U1: test regresji pomiaru spełnia progi D1; U2: 425/425 kwestii czytanych na etykietach, bramka regresji wg E8; U3: testy C (w tym `Water?`, negacja kursywy, `\3c`, alfa); przegląd astry bez blokerów; scalenie do 08.

### Fala B — równolegle po scaleniu U1

| Jednostka | Cel | Write scope | Spec |
| --- | --- | --- | --- |
| **U4 Szyldy** | `fitting.py` wg A (obiekty, K0/A/B/C/D, filtry ekranu i kolizji z sąsiadami, szkody, poziomy ostateczne, raport), wnętrze `_fit_signs_batch` | `fitting.py`, szew w `service.py`, testy | A, D12-1/2/3 |
| **U5 Łamanie** | `lexicon.py`, `linebreak.py` wg LB z pomiarem, `layout.py`, wnętrze `_layout_dialogue`, usunięcie układania z `translation_verses`, normalizacja polskiego źródła | te ścieżki + część układająca `translation_handler.py`, testy | LB, D4 |
| **U6 Czcionka dialogów i mux** | `restyle.py`, ustawienie i panel, planer (pole w snapshocie, katalog czcionek), `composition` (`--attach-file`, `fontsdir`), `extraction` (użycie `extract_attachments` z U1), wnętrze `_restyle` | te ścieżki + testy | D5, D6 |

**Gate fali B:** jak fala A; dodatkowo replay 36 par przechodzi bez wyjątków, liczba zdarzeń zachowana.

### Faza I — Integracja i dowód wizualny (orkiestrator)

1. Scalenie fali B do 08, pełne bramki.
2. Replay 36 par: przed = baseline `2301cd0`, po = 08; galerie U7 dla każdego obszaru, w tym przypadki trudne z `visual-quality.md` §10.4.
3. Ocena orkiestratora obraz po obrazie (lepiej / bez zmian / gorzej) z zapisem w `docs/work/10-quality/reviews/`.
4. Zrzut z mpv właściciela dla 3–5 przypadków (zgodność z FFmpeg) i jeden krótki fragment przy x2 dla szyldu ruchomego.
5. Galeria dla właściciela; jego decyzje D12 → kalibracja stałych; outcome w `docs/work/10-quality/outcomes/`.

## Dodatkowi wykonawcy

| Jednostka | Autor | Recenzent | Worktree / gałąź |
| --- | --- | --- | --- |
| F0 | Claude Opus 5.5 | astra | `AniShift-wt/q-f0` / `work/quality/09-restructure` |
| U1 | Claude Opus 5.5 | astra | `q-measure` / `work/quality/10-measurement` |
| U2 | Claude Opus 5.5 | astra | `q-lector` / `work/quality/11-lector` |
| U3 | Claude Opus 5.5 | astra | `q-ranges` / `work/quality/12-style-ranges` |
| U7 | Claude Opus 5.5 | astra | `q-gallery` / `work/quality/13-gallery` |
| U4 | Claude Opus 5.5 | astra | `q-signs` / `work/quality/14-signs` |
| U5 | Claude Opus 5.5 | astra | `q-breaks` / `work/quality/15-line-breaks` |
| U6 | Claude Opus 5.5 | astra | `q-font` / `work/quality/16-dialogue-font` |

Każdy brief wg szablonu `subagent`: jeden rezultat, write scope, forbidden, baseline, wymagane dowody (komendy bramek i ich wynik, liczby z replay), warunki stopu. Pełny pytest w danej chwili uruchamia najwyżej jeden wykonawca (`-n 8`); pozostali uruchamiają testy swojego obszaru.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Pomiar zgodny z libass | `calibrate.py` na 36 parach, progi D1 | ten sam wzorzec co research |
| Dopasowanie czcionek jak libass | testy na plikach z `fonts/` par i folderu mpv (ID1/ID4/PS, warianty, synteza, glify) | odtwarza przypadki z logów libass |
| Szyldy wg A | testy jednostkowe a0–a10, replay, galeria same-text | obejmuje filtry, szkody i poziomy ostateczne |
| Łamanie wg LB | testy 36 przypadków galerii + 05/06, replay | kontrakt galerii |
| Lektor wg B | etykiety 425/425, kontrprzykłady B.6, E8 | dane z etykietami |
| Style wg C | testy C.3, galeria same-text | konkretne przypadki z `visual-fixes/styles` |
| Czcionka dialogów | testy restyle, mux z `--attach-file`, `mkvmerge -J` na wyniku, zrzut mpv | koniec potoku |
| Wygląd dla człowieka | galerie i zrzuty mpv, ocena orkiestratora i właściciela | wymóg `visual-quality.md` |

### Targeted automated checks

```text
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/ ; uv run mypy --platform linux anishift/ tests/
uv run pytest tests/<obszar> (+ pełny pytest -n 8 przed scaleniem)
scripts/subtitle_quality calibrate (U1), replay (U7, faza I)
```

### Regression obligations

- Liczba zdarzeń wejście = wyjście dla każdego pliku replay.
- Napisy identyczne z angielskim bajtowo identyczne.
- Brak nowych zgubionych kwestii lektora na etykietach.

### Human acceptance

- Galeria przed/po na tym samym tekście dla każdego obszaru i przypadków trudnych; PASS: orkiestrator i właściciel nie widzą nieuzasadnionych pogorszeń.
- Odcinek testowy w mpv z czcionką dialogów; PASS: właściciel akceptuje wygląd dialogów i szyldów.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
| --- | --- | --- | --- |
| Konflikty scalania w `service.py` / `translation_handler.py` | konflikty git | szwy F0, rozłączne write scope | konflikt w kontrakcie publicznym |
| Pomiar gorszy na nowych danych | calibrate poza progiem | analiza źródła błędu wg measurement.md H3 | gdy poprawka zmienia D1 |
| B obniża bramkę regresji | E8 < 0,93 | analiza listy zmian | gdy trzeba zmienić próg właściciela |
| Officina wygląda źle z obrysem typesettera | galeria | pokazać właścicielowi | zawsze decyzja właściciela |
| Rezydent właściciela działa z głównego checkoutu | — | żadnych zmian w głównym checkoucie | przed scaleniem do main |
| Agent opisuje pogorszenie jako poprawę | ocena orkiestratora rozbieżna z opisem | orkiestrator ogląda każdy obraz sam | — |

## Definition of Done

- [ ] warunki końcowe spełnione;
- [ ] przeglądy astry bez otwartych blokerów, poprawki zweryfikowane przez recenzenta;
- [ ] galeria i ocena orkiestratora zapisane w `reviews/`, ocena właściciela w `outcomes/`;
- [ ] `masterplan.md` zaktualizowany;
- [ ] nic nie trafiło do `main` bez akceptacji właściciela.
