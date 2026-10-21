---
kind: research
id: R1-code-map
baseline: work/quality/08-fuzzy-quality @ 2301cd0
date: 2026-10-18
---

# Mapa kodu napisów, legacy do wycięcia i docelowe drzewo

**Oznaczenia:** **F** to fakt sprawdzony w kodzie, git albo dokumentacji narzędzia w `external/docs/`; **W** to wniosek lub rekomendacja; **?** to niewiadoma. Ścieżki są względne wobec roota repo.

## 0. Najważniejsze ustalenia

1. **F** Łamanie wierszy (`linebreak.py`, `layout_config.py`) leży w `services/translation/`, ale sama domena tłumaczenia z niego nie korzysta. Importują je tylko `services/subtitles/` (`service.py:33-34`, `fitting.py:20`) i `application/translation_handler.py:36-37`. Obie specyfikacje uzależniają łamanie od geometrii ASS i fontu, więc **W:** moduł powinien przejść do `services/subtitles/`.
2. **F** Klasyfikacja dialog/szyld działa w potoku trzy razy i za każdym razem na innym pliku:
   - na źródle w tłumaczeniu (`translation_handler.py:304`);
   - na polskim `FULL_PL` w zadaniu `SPLIT_SUBTITLES` (`subtitle_handler.py:161`, `planner.py:1379-1386` `requires=(full,)`);
   - na `SPOKEN_PL` przed TTS (`tts_handler.py:358`).

   Spoken z polskiej części łamiemy po znakach dwa razy: najpierw w `translation_verses` (`translation_handler.py:464-475`), potem w `reflow_polish_dialogue` (`subtitle_handler.py:162`, `service.py:139-157`). Reguły B liczą profil stylu (f, p, styl bazowy) na populacji zdarzeń pliku. Inna populacja, czyli plik tylko z kwestiami, oraz polski tekst (wersaliki, interpunkcja) mogą więc dać inne decyzje niż te, według których writer dopasował szyldy. **W:** decyzje liczymy raz, na źródle, a produkty pochodne je dziedziczą. Specyfikacja B tego nie opisuje i trzeba to rozstrzygnąć.
3. **F** Dziś szyld dzielimy po znakach, zanim trafi do dopasowania. W `translation_verses` jednowierszowy szyld dłuższy niż 42 znaki trafia do `split_for_layout` → `_split` → `_best_cut` (`linebreak.py:305-306, 349-361, 454-474`). Writer dostaje już dwa wiersze, a dopiero potem działa `fit_sign_text`. To sprzeczne z A.4, gdzie wariant D jest jednym z kandydatów wybieranych według S. **W:** układ szyldu ma powstawać wyłącznie w `fit_signs`, a układ dialogu w writerze, per zdarzenie (`fuzzy-line-breaks.md` §1: „layout per event przy rekonstrukcji”).
4. **F** Fonty w MKV:
   - mkvmerge kopiuje załączniki źródła domyślnie. AniShift nie używa `--no-attachments` (`commands.py:139-160`; `external/docs/mkvtoolnix/mkvmerge.html:1744-1748` „-M, --no-attachments: Don't copy attachments from this file”), więc fonty typesettera przechodzą do wyniku.
   - AniShift nie dołącza żadnego własnego fontu, bo w kodzie nie ma `--attach-file`.
   - Przy wypalaniu do MP4 parametr `fonts_dir` w `subtitle_filter_argument` istnieje (`commands.py:323-334`), ale oba wywołania go nie przekazują (`composition/service.py:328-331`, `:546`).
   - W produkcji nie ma ekstrakcji załączników. Robi to tylko narzędzie deweloperskie (`scripts/quality/render.py:108-143`).
5. **F** W `text.py` siedzi drugi, własny podział na grafemy (`text.py:54-65, 595-634`), mimo że `anishift/text/graphemes.py:11-17` (`regex` `\X`) jest wspólnym źródłem dla TTS, chunkingu i UI. Specyfikacja łamania wymaga „nigdy wnętrza grafemu” i wskazuje do reuse `text/graphemes.py`. Dwie definicje grafemu w jednym potoku to ryzyko rozjazdu kotwic.

## 1. Przepływ napisów (stan na 2301cd0)

```text
MKV w workspace
└─ EXTRACT_SUBTITLES / EXTRACT_TRACKS (planner.py:1190, 1225)
   services/extraction/service.py — mkvextract ścieżek; identify() zbiera nazwy załączników (l.100, 114), fontów nie wyciąga
   → SOURCE_SUBTITLES (.ass / .srt)

├─ [obce źródło] TRANSLATE_SUBTITLES (planner.py:1303-1312)
│   TranslationTaskHandler._translate_subtitles (translation_handler.py:288-314)
│   1. load_subtitles (subtitles/service.py:99-121)
│   2. split_subtitles(kind) (service.py:265-318)
│      ├─ SRT: wszystko spoken, bez klasyfikacji (l.274-277)
│      ├─ classify_styles (classifier.py:191-220)
│      │    dedup_animation (l.136-156) → _classify_metrics, schodkowy wynik (l.159-188)
│      ├─ _spoken_mask (service.py:227-241)
│      │    main_dialogue_style (classifier.py:223-226) + line_category (l.235-244, _sign_actor l.229-232)
│      ├─ _dialogue_decisions + fallback „nic nie czytane → czytaj wszystko” (service.py:244-262; l.259-261)
│      └─ _collapse_fbf_indexed, klucz (styl, tekst), przerwa ≤ 500 ms, PO masce (service.py:206-224, 185-198, 286-300)
│   3. spoken_lines / displayed_lines → marked_text (translation_handler.py:417-435)
│      text.py:132-146 → _marked_boundaries (l.280-296) → _span_markers (l.299+)
│   4. TranslationService.translate_file — znaczniki <sN>…</sN> (text/markers.py:12-28)
│   5. translation_verses (translation_handler.py:438-476)
│      ├─ displayed: split_for_layout(strip_span_markers, visible_verses) (linebreak.py:296-313)
│      │    1 wers źródła → _split/_best_cut po max_chars (l.349-361, 454-474)
│      │    > 1 wers → _proportional_boundaries (l.316-346)
│      ├─ spoken: split_line (linebreak.py:274-281) → _dialogue_cut / _dialogue_candidates, rangi krotkami (l.364-399)
│      └─ restore_markers (text.py:149-172)
│   6. write_translated (service.py:437-447) → _translated_file (l.382-434), per zdarzenie:
│      replace_visible_text (text.py:175-185; _placed_tags l.320-345, _marker_anchors l.348-367, _monotonic_anchors l.494-502)
│      → [spoken, ten sam widoczny tekst] reflow_visible_text (text.py:188-221)
│      → [ASS i displayed] fit_sign_text(event, text, subs) (fitting.py:134-155), wołane z service.py:431-432
│      _copy_metadata zachowuje info, style, fonts_opaque i graphics_opaque (service.py:321-328)
│      → _write_output atomowo (l.344-358)
│   → FULL_PL

├─ [polskie źródło] NORMALIZE_SUBTITLES (planner.py:1314-1321)
│   subtitle_handler._normalize (l.132-149) → normalize_subtitles (service.py:124-136)
│   → split_subtitles + reflow_polish_dialogue (service.py:139-157: split_line po znakach)
│   → FULL_PL

└─ FULL_PL → SPLIT_SUBTITLES (planner.py:1379-1386)
    subtitle_handler._split (l.151-189)
    ├─ split_subtitles(load(FULL_PL)) — druga klasyfikacja, na polskim tekście (l.161)
    ├─ reflow_polish_dialogue — drugie łamanie spoken (l.162)
    └─ write_spoken / write_displayed (service.py:368-379)
    → SPOKEN_PL → SYNTHESIZE_SPEECH (planner.py:1448-1456, 796-808)
        tts_handler._script_lines: split_subtitles(SPOKEN_PL).spoken — trzecia klasyfikacja (l.351-358)
    → DISPLAYED_PL

COMPOSE_MKV: composition_handler._build_mkv_request (l.240-282)
  → container_merge_command (commands.py:139-160)
  mkvmerge [--no-audio] źródło + --language/--track-name/--default-track-flag na każdą dołożoną ścieżkę
  bez --attach-file; załączniki źródła kopiowane domyślnie
COMPOSE_MP4 (wypalanie): subtitle_filter_argument(kind) bez fonts_dir (composition/service.py:328-331, 546)
Diagnostyka fontów: composition/fonts.py font_embedding_warnings (l.48-51) porównuje nazwy plików załączników, nie rodziny
```

### 1.1 Gdzie dziś siedzą heurystyki

| Heurystyka | Miejsce (F) | Wołana z |
| --- | --- | --- |
| Dopasowanie szyldu | `subtitles/fitting.py` w całości: Arial 64 px, podłoga 0,72, tolerancja 1,03, wspólny czynnik obu osi | `service.py:431-432` |
| Zawijanie libass (szacunek) | `fitting.py:114-120` (`_wraps_only_translation`), `_play_width` l.107-111 | `fitting.py:125` |
| Podział dialog/szyld | `subtitles/classifier.py` (styl i linia), `service.py:227-262` (maska, fallback), `service.py:185-224` (serie FBF) | `split_subtitles` |
| Łamanie dialogu | `translation/linebreak.py:274-281, 349-421` | `translation_handler.py:468`, `service.py:151` |
| Łamanie szyldu wielowierszowego | `linebreak.py:296-346`, `fitting.py:123-131` (`_reflow`) | `translation_handler.py:455`, `fitting.py:147` |
| Granice stylów (znaczniki) | `subtitles/text.py:132-172, 280-367, 494-502`; składnia w `text/markers.py` | `translation_handler.py:420, 430, 453`; writer `service.py:428` |
| Fonty | `composition/fonts.py` (diagnostyka regexem), `scripts/quality/render.py:84, 108-155` (narzędzie dev), `fitting.py:57-67` (Arial) | composition, narzędzie |

## 2. Legacy i duplikaty do wycięcia

„Zastąpione przez” wskazuje sekcję `fuzzy-signs-and-split.md` (A/B/C/D) albo `fuzzy-line-breaks.md` (LB §n).

| # | Element (plik:linia) | Dlaczego legacy | Zastąpione przez | Ryzyko |
| --- | --- | --- | --- | --- |
| 1 | `fitting.py` (cały plik): `_font`/`_width` Arial 64 px (l.57-67), `_MIN_SCALE` (l.24), `_WIDTH_TOLERANCE` (l.27), `_FONT_SIZE` (l.30), wspólny czynnik `_scales` (l.70-71), `_pixel_scale` czytający tylko prefiks (l.95-104), `_wraps_only_translation` (l.114-120), `_reflow` + `_BALANCED_LINES` (l.39, 123-131), `fit_sign_text` per zdarzenie (l.134-155) | Pomiar nie fontem odcinka (p90 błędu 7%, max 21,5%), podłoga zamiast oceny, brak obiektów, filtrów ekranu i kolizji | A.2–A.6, `fit_signs(subs, texts, fonts)` raz na plik | Średnie. Do zachowania i adaptacji: `_RE_SCALING` + `_scale_text` (l.42-45, 78-92) nakładają skalę na `\fscx/\fscy`, `\t` i `\r` zgodnie z A.2, ale muszą przyjąć osobne `fx` i `fy`. `_play_width` (l.107-111) jest wskazany do reuse w LB §1. |
| 2 | `classifier.py:159-188` `_classify_metrics` (schodki, wczesny `return DIALOG, 0.85` l.167-168) i progi l.75-103 (`_SCORE_*`, `_FRAC_DIALOG_MIN`, `_POS_*`, `_PUNCT_MIN`, `_AVG_TEXT_MIN`, `_DLG_MAX_POS_RATIO`) | Ostre schodki i kategoria UNCERTAIN zamiast dialogowości 0–1 | B.3 (RS1–RS8, styl bazowy, sim), D „Zmiana API” | Wysokie: test regresji 0,9586 → 0,933 (E8) |
| 3 | `classifier.py:28` `_RE_POS` (zawiera `clip`, `fad`, `t\(`) | Druga definicja „położenia”, sprzeczna z B.3 | B.3/B.4: jedna cecha położenia | Średnie: +14 odczytów (E7) |
| 4 | `classifier.py:114-122` `StyleVerdict.confidence`; `main_dialogue_style` (l.223-226); `line_category` + `_sign_actor` + `_RE_MID_ALIGN` (l.37, 229-244) | Decyzja po kategorii stylu i wyjątkach | D: `StyleVerdict(…, dialogue_score, look_*, hard, base, …)`, `line_dialogue_score` (B.4–B.5) | Średnie: konsumenci `Category` to `service.py:235-241`, `scripts/quality/metrics.py:233`, testy |
| 5 | `service.py:227-241` `_spoken_mask`; kolejność „maska → `_collapse_fbf_indexed`” (l.279-300) | B.5 wymaga, żeby serie powstały przed maską (seria bierze najwyższe D) | B.5 | Średnie: sprzężenie klucza `(styl, tekst)` z writerem (`AGENTS.md` subtitles) zostaje |
| 6 | `subtitles/AGENTS.md:33` „zmiana zachowania klasyfikatora = zmiana stałych, nie logiki” | Po B przestaje obowiązywać | Aktualizacja AGENTS.md przy wdrożeniu B | Niskie |
| 7 | `text.py:67` `_MAX_MARKED_BOUNDARIES`, `:70` `_RE_EMPHASIS_OFF`, `:280-296` `_marked_boundaries`, `:299+` naprzemienne `_span_markers`, `:348-367` `_marker_anchors`, `:494-502` `_monotonic_anchors` dla wszystkich tagów | Warunki T1–T3 gubią akcenty („Water?”, negacja kursywy) | C.2 (StyleState, zakresy, stałe kotwice) | Średnie: multizbiór tagów musi zostać zachowany (D, C) |
| 8 | `text.py:54-65, 595-634` własne `_graphemes`, `_extends_grapheme`, `_is_regional_indicator` | Duplikat `text/graphemes.py:15-17` (`regex` `\X`) z inną definicją klastra | Reuse `split_graphemes` (AGENTS: reuse; LB §1 wskazuje `text/graphemes.py`) | Niskie: rzadkie klastry (Hangul, indyjskie) mogą przesunąć kotwice; pokrywa to `test_subtitles_text.py` |
| 9 | `text.py:580-592` `_hard_space_positions`: zbiór `insertions` nigdy nie jest wypełniany, więc gałąź `text.py:573-574` jest martwa | Martwy kod | Usunięcie przy przepisywaniu `text.py` (C) | Brak |
| 10 | `text.py:30` `_RE_DRAW_TAG` i `classifier.py:25` `_RE_DRAW` | Dwa identyczne wzorce `\p[1-9]` | `is_drawing` (text.py:109) jako jedno źródło | Brak |
| 11 | `linebreak.py:364-399` `_dialogue_cut`/`_dialogue_candidates` z rangami-krotkami `(overflow, syntactic_risk, boundary_rank, orphan, imbalance)`, `:264` `_TOP_HEAVY_PENALTY`, `:267` `_OVERFLOW_TOLERANCE`, `:349-361` rekurencyjny `_split`, `:454-474` `_best_cut` (odległość × waga), `:487-498` `_weight`, `:536-539` `_greedy_cut`, `:316-346` `_proportional_boundaries` | Dwa różne algorytmy cięcia (dialog i szyld), limity znakowe, porządek leksykograficzny zamiast jednej oceny | LB §3–§4 (Q noisy-OR, enumeracja 0–3 cięć, graf ratunkowy). Szyldy: A.4 (D i źródło wielowierszowe korzystają z modułu łamania) | Wysokie: 45 testów `test_translation_linebreak.py` |
| 12 | Do zachowania z `linebreak.py` (reuse wg LB §2): listy `_CONJUNCTIONS`, `_CONJUNCTIONS_MULTIWORD`, `_NON_BREAKING_HEADS`, `_PREPOSITIONS_MULTIWORD`, `_PRONOUN_HEADS`, `_VERB_HEADS`, `_TITLE_HEADS`, `_ADJECTIVE_ENDINGS`, `_REFLEXIVE_HEADS` (l.30-270) i helpery `_clean`, `_tail`, `_names_pair`, `_protected`, `_speaker_start`, część `_dialogue_protected` (l.284-293, 402-451, 501-528) | Słowniki i detektory sygnałów, nie algorytm | Wejście reguł SYN/INT (LB §2) | Niskie |
| 13 | `linebreak.py:9` import `SENTENCE_ENDINGS, phrase_cut_chars` z `translation.chunking`, który sam je importuje z `text/boundaries.py` | Pośrednie źródło prawdy | Import wprost z `anishift.text.boundaries` (`PHRASE_CUT_CHARS` l.40) | Brak |
| 14 | `service.py:139-157` `reflow_polish_dialogue` (`split_line` po znakach), wołane w `normalize_subtitles` (l.135) i `subtitle_handler.py:162` | Łamanie po znakach i podwójne łamanie `FULL_PL` | LB §1–§4, jedno miejsce łamania (writer i normalizacja) z pomiarem | Średnie: wymagana idempotencja (LB §2) |
| 15 | `translation_handler.py:438-476` `translation_verses` (układ przed writerem, bez kontekstu zdarzenia) | Pomiar wymaga stylu, fontu, marginesów i `PlayRes`, a ma je dopiero writer | LB §1 (layout per zdarzenie), A.3 (`fit_signs` w writerze) | Średnie: zmiana sygnatury `write_translated*` (dziś przyjmują gotowe wersy) |
| 16 | `translation/layout_config.py:19-42` `LayoutConfig` łączy limity układu napisów z rozmiarem kawałka tłumaczenia (`chunk_chars`, `chunk_pieces`) i importuje stałe `linebreak` (l.8-9) | Dwie odpowiedzialności w jednym obiekcie | Część układu (`L_ref`, `N_ref` z LB §3) idzie do subtitles; `chunk_chars` zostaje w translation | Niskie: konsumenci to `runtime.py:642-647`, `translation_handler.py:169-174, 363-414`, `subtitle_handler.py:107-110` |
| 17 | `subtitle_handler.py:46-99` `LegacySubtitleProducts` / `LegacySubtitleAdapter` | W produkcji nieużywane; jedyny konsument to `tests/application/test_execution_handlers.py:63, 719` | Usunięcie (zasada właściciela „wycinaj jak raka”; specyfikacje tego nie wymagają) | Niskie, ale zakres do potwierdzenia |
| 18 | `service.py:160-171` `preview_styles` | Brak konsumenta w `anishift/cli` i `application` (eksport tylko w `subtitles/__init__.py`). D twierdzi, że `Category` służy „tylko do podglądu w UI”, a takiego UI dziś nie ma | Usunięcie albo podłączenie; decyzja | ? Czy `Category` ma przetrwać |
| 19 | `composition/fonts.py:34-38` `attachment_font_names` (porównanie basename) | Sam `AGENTS.md` composition mówi, że pełna walidacja wymaga metadanych rodziny | Opcjonalnie: indeks fontów (§3) daje rodziny | Niskie, poza zakresem specyfikacji |
| 20 | `scripts/quality/render.py:84` `_RE_INLINE_FONT` (duplikat `composition/fonts.py:16` `_INLINE_FONT`), `:108-143` `prepare_fonts`/`extract_attachments`, `:150-155` `event_fonts`; `metrics.py:226-227` domyślne `PlayRes` 384/288 (duplikat `fitting.py:33`) | Drugi system fontów i geometrii poza aplikacją | `services/fonts` + `extraction` + `subtitles/geometry.py` (§3) po kroku F1 | Niskie |

**Rozjazdy specyfikacji z kodem (F, drobne):**

- A.3 cytuje `scripts/quality/render.py::_extract_attachments`, a funkcja nazywa się `extract_attachments` (`render.py:122`).
- A.3 podaje `_translated_file (service.py:397–434)`, a funkcja zaczyna się w l.382 (pętla l.396–434).
- A.3 wymienia trzy źródła fontów: MKV, `fonts/` pary i system. LB §1 dodaje „osadzone fonty ASS” (`[Fonts]`, w pysubs2 `fonts_opaque`, zachowywane przez `service.py:325`). Trzeba ujednolicić.

## 3. Drzewo folderów: obecne → docelowe

### 3.1 Obecne (zakres napisów)

```text
anishift/
  text/                      boundaries.py, graphemes.py, markers.py   — prymitywy Unicode (bez importu services)
  services/
    subtitles/               __init__, classifier, fitting, service, text, txt, srt, types, errors
    translation/             linebreak.py, layout_config.py  ← łamanie napisów w domenie tłumaczenia
                             chunking, service, engines/, …
    composition/             fonts.py (diagnostyka nazw), commands.py (mkvmerge/ffmpeg), service.py, …
    extraction/              service.py (mkvextract ścieżek, identify z nazwami załączników)
  application/               translation_handler (verses), subtitle_handler (normalize/split), tts_handler, composition_handler, planner
scripts/
  quality/                   __main__, episode, frames, metrics, render, report   — pomiar libass i galerie (dev)
  slime_animation.py, slime_animation_smooth.py, slime_sad_melt_animation.py
```

### 3.2 Docelowe (W)

Zasady: płaskie moduły w domenie, jak w reszcie `services/` (podpakiet tylko dla `engines/`). Wzorzec MangaShift: `mangashift/services/text_render/{fonts.py, service.py, types.py, …}` trzyma fonty jako moduł obok usługi, która ich używa. Domeny rozdzielamy według kierunku zależności: composition nie może importować subtitles ani pysubs2 (`services/composition/AGENTS.md`).

```text
anishift/
  text/                              bez zmian (boundaries, graphemes, markers)
  services/
    fonts/                           NOWA domena techniczna; bez pysubs2 i bez subtitles, więc composition może jej używać
      __init__.py                    publiczne API: FontIndex, measure
      index.py                       buduje indeks z katalogów i plików (załączniki MKV, fonts/ pary, osadzone ASS, system, font wybrany przez właściciela); klucz z tabeli name (1/16, 4, 6) + bold/italic z OS/2, dopasowanie jak w libass (A.3); wymaga fonttools (E4)
      metrics.py                     Pillow: advance z kerningiem przy size = fs·unitsPerEm/(winAscent+winDescent), pokrycie cmap → status zastępczy (A.3)
      types.py                       FontFace, FontMatch (exact / substitute)
      AGENTS.md
    extraction/
      service.py                     + extract_attachments(): właściciel mkvextract wyciąga fonty raz na odcinek (dziś tylko w scripts/quality)
    subtitles/
      __init__.py                    publiczne API domeny
      service.py                     load, normalize, split (decyzje raz), writery; cieńszy, deleguje
      types.py, errors.py, srt.py, txt.py   bez zmian, poza nowymi value objectami (StyleVerdict v3, raport dopasowania)
      fuzzy.py                       rise, fall, nor: jedno źródło dla A.6, B.3–B.5 i LB §3 (LB `R` ≡ `rise`)
      geometry.py                    stan renderu ASS: spany (\fn \fs \fscx \fsp \b \i \bord \shad, \r), W/H, kotwica (\pos / marginesy / \an), PlayRes, ScaledBorderAndShadow, zawijanie libass, region \clip, przecięcia z sąsiadami; reuse _play_width; wspólne dla A i LB (u = W/A)
      text.py                        tag-bezpieczne operacje na widocznym tekście (grafemy z anishift.text)
      ranges.py                      C: StyleState, stan efektywny, wybór ≤ 2 zakresów, stałe kotwice znaczników
      classifier.py                  B: profil stylu, styl bazowy, RS1–RS8, cechy linii, weto, serie, line_dialogue_score
      fitting.py                     A: obiekty, kandydaci K0/A/B/C/D, filtry ekranu i kolizji, szkody, fit_signs, raport poziomów ostatecznych
      linebreak.py                   LB: generator 0–3 cięć, Q, graf ratunkowy, unmeasured; przeniesiony z translation
      lexicon.py                     polskie listy i detektory sygnałów SYN/INT (dane z dzisiejszego linebreak.py l.30-270)
      layout.py                      limity układu z LayoutConfig (L_ref, N_ref); chunk_chars zostaje w translation
      restyle.py                     podmiana fontu w stylach dialogowych na font właściciela; szyldy zachowują font typesettera
    translation/                     − linebreak.py, − layout_config.py (zostaje chunk_chars w config/constants)
    composition/
      types.py                       + ContainerCompositionRequest.attached_fonts
      commands.py                    + --attachment-mime-type / --attach-file dla fontu dialogów; fonts_dir przekazany do subtitle_filter_argument przy wypalaniu
      fonts.py                       diagnostyka; opcjonalnie rodziny z services/fonts zamiast basename
  application/
    translation_handler.py           bez translation_verses: przekazuje nierozbity przekład; base i style przechodzą do marked_text (C.2 pkt 8)
    subtitle_handler.py              split bez ponownej klasyfikacji i ponownego łamania; − LegacySubtitleAdapter
    tts_handler.py                   SPOKEN_PL czytany jako „wszystko spoken” zamiast trzeciej klasyfikacji
    planner.py / composition_handler.py   artefakt fontów odcinka (?) i parametr fontu dialogów
scripts/
  subtitle_quality/                  (przemianowane z quality/) pomiar libass, kalibracja F1, galerie; fonty i geometria z aplikacji
```

**Rola podmiany fontu dialogów (nowy wymóg).**

- **Gdzie:** `subtitles/restyle.py` działa w writerze przed łamaniem, bo łamanie mierzy już nowym fontem (wymóg właściciela). Font właściciela trafia do indeksu jako jawny plik.
- **Załącznik:** composition dostaje tylko ścieżkę pliku (`attached_fonts`) i nie zna stylów. mkvmerge przyjmuje `--attachment-mime-type` i `--attach-file` (`mkvmerge.html:1461-1490`).
- **Wypalanie:** potrzebny jest `fonts_dir` (FFmpeg `ass`/`subtitles`: „Set a directory path containing fonts…”, `ffmpeg-filters.html:28459-28461`).
- **Ustawienie:** `config/user_settings.py`, panel i snapshot planu, jak `subtitle_max_chars_per_line` (`planning.py:163-164, 249-250`, `runtime.py:642-647`).

## 4. Testy dotknięte zmianą

Liczby z `grep` na 2301cd0 (testy/asercje w pliku). „Zmiana” to szacunek.

| Plik | Testy / asercje | Zmiana |
| --- | --- | --- |
| `tests/services/subtitles/test_sign_fitting.py` | 14 / 26 | Prawie cały plik: `_fit` → `fit_signs`, wartości `fx`/`fy` w ok. 11 testach (lista w D), nowe testy filtrów i statusu |
| `tests/services/subtitles/test_subtitles_text.py` | 47 / 59 | Mechanicznie 9 wywołań `marked_text` i 28 `replace_visible_text` (argument `base`); 4 oczekiwania (l.175, 264, 268, 272); nowe przypadki C.3 i zmiana szyku |
| `tests/services/subtitles/test_subtitles_split.py` | 14 / 25 | Helper `_verdict` (l.97), l.86, 213-214; test l.138 zmienia sens i nazwę; seria przed maską; zdanie z `\an5` czytane |
| `tests/services/subtitles/test_subtitles_translated_write.py` | 15 / 66 | `StyleVerdict` l.348-349. Jeśli układ przejdzie do writera, zmienia się sygnatura `write_translated*` we wszystkich 15 testach (mechanicznie) i test `reflow_polish_dialogue` (l.103) |
| `tests/services/subtitles/test_subtitles_classifier.py` | 4 / 11 | Asercje `Category` przy klasyfikacji; testy `collapse_fbf` bez zmian |
| `tests/services/subtitles/test_regression_classifier.py` | 1 / 3 | Definicja (decyzje linii, „ściśle ponad połowa”) i próg E8; allowlista bez zmian |
| `tests/services/translation/test_translation_linebreak.py` | 45 / 74 | Przeniesienie do `tests/services/subtitles/` (uwaga: `tests/services/translation/` ma jedyny `__init__.py`, `tests/AGENTS.md`). Ok. 25 testów do ponownego wyprowadzenia: rangi i limity znakowe (l.75, 87, 143, 154, 163, 171, 179, 202, 216, 225, 232, 239, 276, 281) i 6 testów `split_for_layout` (l.321-363), które przechodzą do A.4. Ok. 20 testów ochron (nazwy, przyimki, skróty, `się`, frazy, nbsp, słowo bez cięcia) zostaje jako kontrakt z nową sygnaturą (profil albo `unmeasured`) |
| `tests/services/translation/test_translation_layout_config.py` | 10 / 11 | Podział razem z `LayoutConfig` |
| `tests/application/test_translation_layout_wiring.py`, `test_translate_only.py` | — | Ścieżki importu `LayoutConfig` i funkcji z `translation_handler` |
| `tests/application/test_execution_handlers.py` | 35 / 147 | Sekcja `LegacySubtitleAdapter` (l.63, 719), jeśli adapter zostanie usunięty |
| `tests/services/composition/test_composition_commands.py` | 17 wywołań komend | Nowe przypadki `--attach-file` i `fonts_dir`; istniejące bez zmian, jeśli pole jest opcjonalne |
| `tests/scripts/test_quality_metrics.py`, `test_quality_render.py` | 25 / 58, 6 / 29 | `Category` (l.27) zgodnie z API B; helpery fontów, gdy render przejdzie na `services/fonts`; ścieżki przy przemianowaniu |
| Nowe | — | `tests/services/fonts/` (indeks, metryki), `fuzzy`, `geometry`, `ranges`, `restyle`; wiersze kontrprób B.6; a6, a1, statusy przybliżone (D) |

`testpaths` (`pyproject.toml:134-139`) obejmuje całe `tests/`, więc nowe katalogi nie wymagają zmian konfiguracji. Nie dodawać `__init__.py` (`tests/AGENTS.md`).

## 5. `scripts/quality` i `scripts/slime_*`

**`scripts/quality` (F):**

- Aplikacja go nie importuje. Konsumentami są tylko `tests/scripts/test_quality_{frames,metrics,render,report}.py` (36 testów).
- Narzędzie importuje wnętrze aplikacji: `subtitles.classifier`, `subtitles.text`, `subtitles.service`, `composition.fonts`, `extraction.service.identify`, `platform.binaries`, `paths` i `utils.logger`.
- Obejmują go ruff i mypy (wykluczone jest tylko `scripts/tmp`, `pyproject.toml:56-67, 125-127`; ulgi `scripts/**` l.117).
- Powstało 2026-10-17/18 (17827f9, 1f060a2, 3785201).
- LB §2 nazywa libass przez FFmpeg z `render.py` „wyłącznie wzorcem kalibracji”.

**Rekomendacja (W):**

- Zostaje poza pakietem `anishift/` jako narzędzie deweloperskie, bo aplikacja nie powinna zależeć od skryptu.
- Nazwę zmieniamy na `scripts/subtitle_quality/`. Samo „quality” myli się z „bramkami jakości” z `AGENTS.md` i z `application/release_quality.py`, a nowa nazwa mówi, co jest mierzone.
- Testy przenosimy do `tests/scripts/subtitle_quality/`, bo `tests/scripts/` jest w `AGENTS.md` opisane jako miejsce testów strażników z `scripts/hooks/`.
- Po F1 jego obsługę fontów i geometrii zastępujemy modułami aplikacji (§2, wiersz 20), żeby nie było drugiego systemu pomiaru.
- Koszt: odwołania do `scripts/quality/render.py` w specyfikacjach i komenda `python -m scripts.quality`.

**`scripts/slime_*.py` (F):**

- Pliki dodał e83c703 (2026-08-30, Mateusz Mróz, „chore(repo): checkpoint interactive mascot work”) razem z assetem maskotki.
- To generatory klatek animacji slime'a dla Home (`docs/work/02-plain-cli/plans/04-mascot-polish-cleanup.md:86-103`: „źródłem obu profili jest wersjonowany generator `scripts/slime_animation.py`”, wynik w `C:\Users\MattyMroz\Pictures\MangaShiftSlime\…`, „sekwencja pozostaje poza runtime do wizualnej akceptacji”).
- Runtime używa tylko `assets/mascot/idle/01.png` (`cli/interactive/mascot.py:25`).
- Nic ich nie importuje i żaden test ich nie sprawdza, ale podlegają bramkom ruff i mypy.

**W:** Nie mają związku z napisami. Właściciel decyduje: przenieść do `scripts/mascot/`, jeśli animacja żyje, albo usunąć. Nie ruszać w workstreamie fuzzy.

## 6. Niewiadome i decyzje

1. **?** Czy decyzje spoken/displayed mają być liczone raz na źródle i dziedziczone przez `FULL_PL`, `SPOKEN_PL` i TTS (§0 pkt 2)? Wymaga dopisania do specyfikacji B albo osobnej decyzji. Jaki jest dziś realny rozjazd decyzji EN i PL, nie mierzono.
2. **?** Font dialogów w stylu mieszanym. B decyduje per linia, a font siedzi w stylu. Szyld w stylu `Default` dostaje inline `\fn` z fontem typesettera czy styl jest klonowany? Do rozstrzygnięcia przed `restyle.py`.
3. **?** Jak indeks fontów trafia do handlerów: nowy artefakt planu (np. katalog fontów odcinka z zadania ekstrakcji) czy konwencja katalogu? Artefakt to zmiana lifecycle planera, czyli decyzja materialna.
4. **?** Źródła fontów: trzy (A.3) czy cztery z osadzonymi ASS (LB §1).
5. **?** Czy `Category` i `preview_styles` mają przetrwać, skoro nie mają konsumenta w UI (§2, wiersz 18).
6. **?** Działanie filtra `ass=` FFmpeg na zewnętrznym `.ass` bez `fontsdir` wobec fontów z MKV nie było sprawdzone uruchomieniem. Z kodu wynika tylko, że `fonts_dir` nie jest przekazywany.
7. **?** Liczby testów do zmiany w `test_translation_linebreak.py` to szacunek z nazw testów, nie z przebiegu.
