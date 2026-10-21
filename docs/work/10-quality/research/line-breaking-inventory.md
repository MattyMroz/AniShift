---
kind: research
topic: łamanie wierszy — inwentarz, reuse i wspólny rdzeń AniShift/MangaShift
status: raport badawczy (bez kodu produkcyjnego)
checked: 2026-10-18/19
baseline: worktree AniShift-wt/fuzzy, gałąź work/quality/08-fuzzy-quality @ 03e60a6
compared: AniShift-wt/q-breaks, gałąź work/quality/16-line-breaks @ c2d3be4; MangaShift @ ad47f6010 (refactor/tessera-new-standard)
---

# Łamanie wierszy: co już mamy, co z tego brać i jak zbudować wspólny rdzeń

Ten raport uzupełnia równoległe badania literatury i narzędzi NLP (brief `LB-research-v2`, pytania P1–P6). Nie powtarza ich pracy. Zajmuje się trzema sprawami: co jest już napisane i zbadane w obu repozytoriach, dlaczego stary algorytm z `08` działa lepiej od odrzuconego z `16`, oraz jak podzielić rdzeń, żeby służył też MangaShiftowi.

## 1. Streszczenie

1. Stary algorytm (`anishift/services/subtitles/linebreak.py` na `08`) ma dobrą, prostą budowę: słowa → dowód dla każdej przerwy między słowami → ranking kandydatów. Wada siedzi głównie w jednym miejscu, czyli w twardym limicie 42 znaków, który stoi na pierwszym miejscu rankingu.
2. Na 39 przypadkach ze złotego zbioru stary algorytm daje dokładnie oczekiwany układ w 17. Z 22 różnic 13 wynika wprost z limitu „co do znaku”: 9 razy naturalne cięcie (po przecinku, po myślniku albo przed spójnikiem) przegrywa, bo daje wiersz dłuższy od 42 znaków o 2–16 znaków, a 4 razy kwestia o długości 43–55 znaków zostaje rozcięta, choć oczekiwano jednego wiersza.
3. Odrzucony algorytm (`16`) poprawnie wolał cięcia po interpunkcji (68% cięć zamiast 44%), ale przesadził w drugą stronę. Ma 9 wzajemnie zależnych szkód, 12 ramp i 4 stopnie ratunku, a na korpusie odtworzeń zostawił 871 pojedynczych wierszy dłuższych niż 42 znaki, w tym 230 dłuższych niż 50; stary nie zostawił ani jednego.
4. „Chunker” (`chunk_text`, potomek `CharBreaker`/`WordBreaker` z kodu, który leży w MangaShift) oraz chunker TTS nie nadają się na wybór układu. Pakują tekst zachłannie do twardego limitu, a to jest model „co do znaku”. Wspólny rdzeń powinien za to przejąć ich fundament: `anishift/text/boundaries.py`, `graphemes.py`, `markers.py` i hierarchię granic zdanie > fraza > słowo > grafem.
5. Dokument `docs/reference/subtitle-layout-engine.md` trafnie opisuje zasady (zakazy, polskie związki, tłumaczenie całej jednostki, NLP tylko jako miękki dowód). Proponuje jednak sztywny porządek leksykograficzny, i to w dwóch sprzecznych wersjach (§11 i §22.5). Jego część o spaCy jest nieaktualna i pomija licencję modeli.
6. Stan na dziś: spaCy 3.8.16 ma koło `cp314-win_amd64` (15,2 MB), cały stos zależności też ma koła cp314. Polskie modele `pl_core_news_sm/md/lg` 3.8.0 ważą odpowiednio 20,2 / 49,5 / 573,7 MB i są na licencji **GNU GPL 3.0**, czego stary dokument nie odnotował. Repozytoria nie mają pliku licencji.
7. Jedyne zapisane badanie o bibliotece, która „gramatycznie przelatuje” polskie napisy, to §21 (spaCy) tego dokumentu. W `docs/` obu repozytoriów nie ma notatek o Morfeuszu, UDPipe, Stanzie, HerBERT, Concraft, KRNNT ani COMBO, poza jednowierszową wzmianką „do przejrzenia”.
8. MangaShift układa tekst w dymkach w przeglądarce (TypeScript, `@chenglou/pretext` 0.0.9). Robi to zachłannie, w prostokącie, z wyszukiwaniem rozmiaru fontu, bez polskich reguł i bez dzielenia wyrazów. Pretext obsługuje jednak miękki dywiz i wiersze o różnej szerokości. Usunięty w lipcu pythonowy renderer miał sylabizację regexem.
9. Proponuję rdzeń w dwóch warstwach. Warstwa (a), czysta analiza języka (`anishift/text/`), zwraca dla każdej przerwy stopień szkody cięcia 0–1, flagę pauzy, zmiany osoby i zakazu. Opcjonalnie podaje też miejsca dzielenia wyrazu, których AniShift dziś nie używa. Warstwa (b) to osobne, małe funkcje wyboru dla dialogu, szyldu i dymka.
10. Kontrakty `layout_translated(...)`, `layout_dialogue(...)`, `split_lines(event, text, count, profile)`, `split_for_layout(...)` i `LayoutLimits` zostają. Zmienia się ich wnętrze, a dwa istniejące testy, które kodują twardy limit 42 znaków, wymagają decyzji właściciela.

## 2. Zakres, metoda i stan na dzień

- Kod czytany wyłącznie w worktree `fuzzy` (`08`), `q-breaks` (`16`), `q-signs` (`18`, tylko wywołania `split_lines`) oraz w `MangaShift` (kod, `external/`, `docs/`, historia Git). Główny checkout AniShift tylko do odczytu (`workspace/.quality`).
- Pomiary własne zrobiłem skryptami w scratchpadzie sesji. Metoda jest opisana tutaj, żeby dało się ją powtórzyć:
  - **Klasy cięć na korpusie odtworzeń.** Dla `replay/u6-font` (stary algorytm + czcionka właściciela) i `replay/preview-u5-font` (odrzucony) z `workspace/.quality/experiments/replay/` wczytałem przez `pysubs2` zdarzenia w klonowanych stylach `"(dialog"`, usunąłem tagi `{…}`, podzieliłem po `\N` i sklasyfikowałem każde cięcie powierzchniowo: po interpunkcji / po jednoliterowym słowie / po przyimku / po `nie` / przed i po `się` / po spójniku / inne. Klasyfikacja opiera się na moich listach, więc liczby są przybliżone. W kilku parach w stylach dialogu zostały też nieprzetłumaczone angielskie linie.
  - **Złoty zbiór.** Słownik `_EXPECTED` z `q-breaks/tests/services/subtitles/test_subtitles_line_break_cases.py` (39 przypadków: wybory właściciela i rekomendacje przyjęte 18.10) podałem do starego `split_line(text)` z domyślnymi `max_chars=42, max_lines=2`. To tryb znakowy bez pomiaru fontu, a oczekiwane układy wybierano na obrazach z Officiną, więc porównanie pokazuje zachowanie reguł, nie pikseli.
  - **Pyphen.** `pyphen==0.18.1` w tymczasowym venv poza repo (Python 3.14), słownik `pl_PL`, 29 słów.
  - **PyPI i modele.** JSON API `https://pypi.org/pypi/<pakiet>/json` oraz GitHub API wydań `explosion/spacy-models`, stan z 2026-10-18.
- Nie oceniałem jakości parserów na naszych danych, bo to P3 równoległych badaczy (ich surowe wyniki są w `workspace/.quality/experiments/lb-research/{astra,opus55}/`). Nie weryfikowałem wszystkich cytatów z `subtitle-layout-engine.md`, tylko te, które oznaczam.

## 3. Inwentarz: co jest, gdzie i w jakim stanie

### 3.1 Wspólne prymitywy tekstu (`anishift/text/`, worktree `fuzzy`)

| Element | Gdzie | Co robi | Stan / ocena do rdzenia |
| --- | --- | --- | --- |
| `SENTENCE_ENDINGS`, `PHRASE_CUT_CHARS`, `CLOSING_MARKS` | `anishift/text/boundaries.py:11-46` | Znaki końca zdania, separatory fraz ze wszystkich pism Unicode (kategorie `Pd/Pe/Pf/Po`, bez znaków otwierających i apostrofów), domknięcia | Jedno źródło prawdy dla translation, TTS i linebreak (`anishift/text/AGENTS.md`). Brać. |
| `BREAKABLE_SPACES` | `boundaries.py:23` | Białe znaki bez NBSP/NNBSP | Chroni `\h` (twarda spacja). Brać. |
| `period_ends_sentence`, `is_false_sentence_break` + listy skrótów PL/EN | `boundaries.py:49-301` | Kropka po skrócie, inicjale lub w liczbie nie kończy zdania | Brać. |
| `split_graphemes`, `hard_split_graphemes` | `anishift/text/graphemes.py:15-44` | Grafemy (`regex` `\X`), twardy podział z zachowaniem grafemów | Brać, jako ostatnia deska dla tekstu bez spacji. Dla polskiego dialogu nigdy, bo reguła 2.1.1 z `visual-quality.md` tego zabrania. |
| `<sN>` znaczniki stylu | `anishift/text/markers.py:12-28` | Przenoszą kursywę na słowie przez tłumaczenie | Rdzeń działa na słowach bez znaczników, a potem przywraca je istniejące `restore_markers` (`subtitles/text.py:140`). |

Uwaga o duplikacji: rozpoznanie „to jest koniec zdania” istnieje dziś w czterech wersjach o różnej semantyce. Są to: regex `_RE_SENTENCE_SEP` plus `is_false_sentence_break` (`services/translation/chunking.py:33-84`), `_is_sentence_ending` (`services/tts/chunking.py:185-203`), `_tail(...)[-1:] in SENTENCE_ENDINGS` (`subtitles/linebreak.py:348,464,496` na `08`) oraz `sentence_end` z regułą „wielokropek nigdy nie kończy zdania” (`q-breaks/.../lexicon.py:324-327`). Chunkery traktują `…` jako koniec zdania, bo `LATIN_SENTENCE_ENDINGS = ".!?…"` (`boundaries.py:11`), a specyfikacja v4 i leksykon `16` — nie. Rdzeń powinien rozstrzygnąć to w jednym miejscu.

### 3.2 „Chunker” i jego pochodzenie

| Element | Gdzie | Mechanizm | Gdzie używany |
| --- | --- | --- | --- |
| `chunk_text` (`split_paragraphs/sentences/phrases/words`, `_break`, `_pack`) | `anishift/services/translation/chunking.py:66-148` | Rekurencyjne zejście akapit → zdanie → fraza → słowo → grafem, aż kawałek zmieści się w `chunk_limit` (250), potem zachłanne pakowanie do `char_limit` (750) | `application/translation_handler.py:367-386` (`read_text_document`) i `:411-418` (`text_spoken_lines`): ścieżka zwykłego tekstu `.txt` |
| `chunk_speech_text` | `anishift/services/tts/chunking.py:32-85` | Przejście od końca: dla każdej pozycji najdalsza granica w limicie znaków i bajtów, w kolejności zdanie > fraza > spacja > grafem (`_candidate_boundaries`, `:139-171`). Twarda kontrola, że tekst się nie zmienił (`:82-84`) | `services/tts/service.py:536` |
| `txt_to_spoken` / `_word_pieces` | `anishift/services/subtitles/txt.py:47-86` | Czwarta, uboższa kopia zachłannego cięcia (zdanie regexem bez skrótów, potem słowa) | `application/tts_handler.py:530`. To duplikat `chunk_text`, poza zakresem tej pracy. |
| Oryginał: `LatinPunctuator`, `WordBreaker`, `CharBreaker`, `chunk_text(text, method, limit)` | `MangaShift/external/code/image_working_space/utils/text_chunker.py:4-150` (ta sama kopia w `mm_avh_working_space/utils/text_chunker.py`) | Ta sama hierarchia z zachłannym `merge`; regexy z ręczną listą skrótów EN | Materiał referencyjny. AniShift przepisał go od zera (`docs/work/00-rebuild/stage-04-translation/plans/02-requirements-v1.md:63`, `09-chunker-linebreak.md` §2 i §8) |
| `chunk_text` TTS MangaShift | `MangaShift/mangashift/services/tts/engines/supertonic/postprocessing.py:50` | Port z `supertonic-py` (MIT) | Silnik TTS Supertonic |

Czy mechanizm chunkera nadaje się na wspólny rdzeń? **Jego hierarchia granic tak, jego algorytm wyboru nie.**

- Poziomy `_SPLITTERS` (`chunking.py:97-103`) to porządkowa siła granicy: akapit > zdanie > fraza > słowo > grafem. Taka jest też pierwsza warstwa dowodu dla łamania wierszy: koniec zdania > przecinek/średnik/dwukropek/myślnik > zwykła spacja.
- `_pack` (`:121-135`) i `chunk_speech_text` optymalizują wypełnienie twardego limitu. Nie znają równowagi wierszy, polskich związków, pomiaru fontu ani wyboru „jeden czy dwa wiersze”. Działają w modelu „mieści się / nie mieści co do znaku”, który właściciel odrzucił dla napisów. W żądaniach do tłumacza i do TTS ten model jest za to właściwy, bo tam limit jest twardy.
- `anishift/text/AGENTS.md` zabrania „uniwersalnego chunkera z przełącznikami domenowymi”. Wspólny rdzeń nie może więc być chunkerem z trybem „napisy”. Może natomiast być domenowo neutralną analizą przerw, z której korzystają osobne funkcje wyboru.

### 3.3 Łamanie wierszy i dopasowanie na `08` (stary algorytm, baza)

| Element | Gdzie | Rola |
| --- | --- | --- |
| `layout_dialogue(event, text, profile, limits)` | `subtitles/linebreak.py:305-315` | Łamie przekład dialogu przez `split_line(..., max_chars=limits.max_chars, max_lines=limits.max_lines)` i umieszcza tagi (`reflow_visible_text`/`replace_visible_text`). `profile` służy tylko stylowi przy zamianie tekstu. **Dialog jest łamany po znakach, bez pomiaru fontu.** |
| `split_line(text, *, max_chars=42, max_lines=2)` | `linebreak.py:329-336` | Dwóch mówców z myślnikami → po jednym wierszu (tylko dokładnie 2 znaczniki, pierwszy na początku). W pozostałych przypadkach `_split(..., dialogue=True)`. |
| `_split` | `linebreak.py:404-416` | Dialog: jedno cięcie, potem prawa strona z budżetem `budget-1`. Przy `max_lines=2` prawa część wraca bez sprawdzenia długości (`:406`). |
| `_dialogue_cut`, `_dialogue_candidates` | `linebreak.py:419-454` | Ranking leksykograficzny `(overflow, syntactic_risk, boundary_rank, orphan, balans + 6 za cięższą górę)`. Gdy istnieje kandydat bez przepełnienia, wygrywa on bezwzględnie (`:426-427`). Przy przepełnieniu tolerancja wynosi 2 znaki (`_OVERFLOW_TOLERANCE`, `:287`). |
| `_dialogue_protected` | `linebreak.py:457-476` | Zakazy: fałszywy koniec zdania, po przyimku, wewnątrz fraz wielowyrazowych, przed `się`, po `nie`, po tytule, para nazw z wielkiej litery, po jednoliterowym słowie, po znaku otwierającym, przed znakiem zamykającym lub interpunkcją, po `się` przy zaimku, spójniku lub `nie` |
| `_syntactic_risk`, `_boundary_rank` | `linebreak.py:483-502` | Ryzyko: po zaimku, czasowniku posiłkowym lub modalnym, spójniku, końcówce przymiotnika. Ranga: koniec zdania 0, przed spójnikiem 1, po `,;:` 2, reszta 3. |
| Listy z Wikisłownika | `linebreak.py:49-281` | 74 spójniki, 35 spójników wielowyrazowych, 37 przyimków, 50 przyimków wielowyrazowych, głowy zaimkowe, czasownikowe i tytułowe, końcówki przymiotników (z adnotacjami `# source:`) |
| `split_for_layout(text, source_verses, ...)` + `_proportional_boundaries`, `_best_cut`, `_weight` | `linebreak.py:351-401, 509-553` | **Drugi, odrębny ranking** dla szyldów i źródeł jednowierszowych: odległość od celu proporcji × mnożnik (`1/8` mocna interpunkcja, `1/4` słaba, `8` za spójnik na końcu, `1/3` przed spójnikiem) |
| `split_lines(event, text, count, profile)` | `linebreak.py:318-326` | Kontrakt „dokładnie `count` wierszy albo `None`”, dziś opakowanie na `split_for_layout`. Na `08` nikt go nie woła poza testem (`tests/services/subtitles/test_subtitles_dialogue_layout.py:42-50`). Używa go dopasowanie szyldów na `18` (`q-signs/anishift/services/subtitles/fitting.py:22,163,234`). |
| `LayoutLimits(max_chars=42, max_lines=2)` | `subtitles/layout.py:12-26` | Ustawienia użytkownika „Znaków w linii” / „Linii na napis” (`cli/interactive/settings.py:187-188`; zakres 20–120 i 1–4, `application/planning.py:254-255`) |
| `layout_translated(...)`, `_laid_out_text` | `subtitles/service.py:569-621` | Dialog → `layout_dialogue`, wyświetlane → `split_for_layout`, potem `fit_signs` (`fitting.py:46-113`, `_reflow` woła `split_for_layout` w `:88`) |
| Pomiar fontu | `subtitles/geometry.py:25, 240-264` | `measure_text`, `available_width`, `wrap_text` (emulacja zawijania libass) istnieją na `08`, ale stary dialog ich nie używa |
| Stopnie rozmyte | `subtitles/fuzzy.py:10-26` | `rise`, `fall`, `nor` (noisy-OR), 26 linii, używane przez `signs.py` |

Testy obecnego kontraktu to 45 testów w `tests/services/subtitles/test_subtitles_linebreak.py`. Dwa z nich kodują wprost model „co do znaku”:

- `test_dialogue_chooses_a_fitting_boundary_before_punctuation_bonus` (`:87-91`): „Powiedziałem mu wszystko, co wiedziałem o tamtej strasznej nocy w lesie.” ma być pocięte tak, żeby oba wiersze miały ≤ 42 znaki, czyli **nie** po przecinku.
- `test_never_exceeds_max_lines_even_when_text_cannot_fit` (`:225-229`): nigdy więcej niż 2 wiersze.

### 3.4 Wcześniejsze materiały i decyzje o NLP (punkt 5 zlecenia)

Przeszukałem `*.md`, `*.txt` i `*.json` w `AniShift/docs`, `AniShift-wt/fuzzy/docs`, `AniShift/workspace/.quality`, `MangaShift/docs`, `MangaShift/knowledge`, `EchoReader`, `mm_avh_working_space`. Szukałem nazw spaCy, Morfeusz, UDPipe, Stanza, HerBERT, Concraft, KRNNT, COMBO, Trankit, LAMBO, PoliMorf oraz słów „analizator”, „gramatycz”, „łaman”, „hyphen”, „sylab”, „chunk”, „parser”.

| Materiał | Treść | Wniosek |
| --- | --- | --- |
| `docs/reference/subtitle-layout-engine.md` §21 (`:1227-1367`) | spaCy `pl_core_news_sm`: 5 przykładów relacji (`nie → mogę`, `się → spotkamy`…), benchmark ok. 1000 kwestii/s, problem cp314, pomysł workera 3.13, kryterium przyjęcia | **To jedyne zapisane badanie „biblioteki, która gramatycznie przeleci polski napis”.** Najpewniej o nim mówi właściciel. |
| `subtitle-layout-engine.md` §27.4 (`:1845-1846`) | „Morfeusz2 — polska morfologia; Stanza — alternatywny parser” | Tylko lista „do przejrzenia” |
| `docs/work/00-rebuild/stage-04-translation/plans/02-requirements-v1.md:63` | ML (wtpsplit/nnsplit/spaCy/torch) odrzucone, bo „łamią lekki core”; własny algorytm na bazie `text_chunker.py` | Decyzja z etapu 4 |
| `.../plans/06-fixes.md:65-66, 137` | „Biblioteka NLP — rozważone, odrzucone”: ręczne listy zamiast `stopwordsiso`/spaCy | Decyzja z etapu 4 |
| `docs/work/05-automation/research/overview.md:156` | „layout engine: pomiar szerokości, spaCy, uniseg — eksperyment / odłożyć” | Odłożone |
| `docs/work/05-automation/plans/03-subtitle-layout.md:150-156` | Zakaz „nowa zależność NLP” w etapie A; stop, „gdy korpus wymaga analizy morfologicznej” | Ograniczenie z planu 05 |
| `docs/work/10-quality/fuzzy-line-breaks.md:58, 90` | „nie dodajemy parsera NLP ani LLM”; „nie ma … analizatora zależności” | Założenie spec v4, którą właściciel odrzucił razem z kodem |
| MangaShift `docs/` | Brak notatek o polskim NLP. Jest dzielenie wyrazów: `pyphen` (`docs/archive/brainstorms/2026-03-31-rendering-pipeline/brainstorm-text-rendering-pipeline.md:70-75`), Pretext + Hyphenopoly (`docs/brainstorms/render/deep-research-report (3).md:21,31`), „Automatyczna hyphenation ❌” (`docs/brainstorms/render/pretext.md:58`) | Wątek tylko o sylabizacji |

Brak znaleziska w tych katalogach nie dowodzi, że notatek nie ma gdzie indziej, na przykład w rozmowach poza repozytorium.

## 4. Ocena `docs/reference/subtitle-layout-engine.md`

Dokument powstał 27.07.2026 jako materiał na „przyszły etap” (`:1-8`, `:881-888`). Jest szeroki (1994 linie), ale nie zawiera żadnego pomiaru jakości łamania: przykłady spaCy to 5 zdań, a benchmark mierzy tylko czas.

### 4.1 Co jest trafne i warto zachować

| Decyzja | Gdzie | Dlaczego zachować |
| --- | --- | --- |
| Najpierw nie uszkodzić tekstu; zakazy grafemu, wyrazu, interpunkcji, `\h`, liczb i tagów | §2, §4, §22.4 (`:44-51, 75-153, 1425-1440`) | Pokrywa się z regułami nienaruszalnymi 2.1 w `visual-quality.md` |
| Cztery poziomy granicy: `FORBIDDEN` / `STRONG_AVOID` / `NEUTRAL` / `PREFERRED` | §3 (`:58-73`) | To gotowe wartości językowe dla rozmytej „siły granicy”. Odpowiadają trzem poziomom reguł z `visual-quality.md` (nienaruszalne / unikane za wszelką cenę / ważone). |
| Katalog polskich związków (jednoliterowe, przyimek z grupą, `nie`, `się` w obu szykach, posiłkowe/modalne, grupa nominalna, spójniki) z polskimi źródłami | §5 (`:155-340`) | Dobry spis wymagań do testów, niezależny od narzędzia |
| Tłumacz dostaje pełną jednostkę, a autorski `\N` jest metadaną | §10, §19.9 (`:514-589, 1082-1095`) | Tak działa obecny kod (`layout_translated`) |
| Ocenić wszystkich kandydatów zamiast zachłannego cięcia | §19.3 (`:937-963`) | Robią tak stary algorytm, Subtitle Edit `TextSplit` i koharu (rozdz. 6.3) |
| NLP wyłącznie jako miękki dowód, z deterministycznym wynikiem bez niego | §21.6 (`:1345-1367`) | Parser myli się na elipsach, imionach japońskich i onomatopejach. Zasada jest dobra dla każdego analizatora. |
| `spoken` i `displayed` współdzielą parser i walidację, ale mają inne profile oceny | §23.3 (`:1519-1538`) | **To jest idea wspólnego rdzenia** (rozdz. 7) |
| Korpus i benchmark przed zależnością | §26 (`:1619-1729`) | Częściowo zrobione (rozdz. 8) |

### 4.2 Co jest nieaktualne

| Twierdzenie | Gdzie | Stan na 2026-10-18 |
| --- | --- | --- |
| „spaCy 3.8.14 has no wheels … cp314”, worker na Pythonie 3.13 | §21.4–21.5 (`:1294-1343`) | **Nieaktualne.** spaCy 3.8.16 (wydany 2026-08-24) ma `spacy-3.8.16-cp314-cp314-win_amd64.whl`, 15 202 134 B ([PyPI](https://pypi.org/project/spacy/3.8.16/)); 3.8.14 i 3.8.15 nie mają cp314. Zależności z kołami `cp314-win_amd64`: `thinc` 8.3.12/8.3.13, 1,74 MB ([PyPI](https://pypi.org/project/thinc/8.3.13/)), `blis` 1.3.3, 6,3 MB ([PyPI](https://pypi.org/project/blis/1.3.3/)), `cymem` 2.0.13, `preshed` 3.0.13, `murmurhash` 1.0.15, `srsly` 2.5.4. Worker 3.13 jest zbędny. |
| Wersja i zakres modelu: „`pl_core_news_sm` 3.8.0” | §21.1 (`:1234-1242`) | Wersja się zgadza (3.8.0, wydany 2024-09-30, `spaCy >=3.8.0,<3.9.0`). Rozmiary kół z wydań GitHub: sm 20 213 213 B, md 49 492 508 B, lg 573 718 074 B ([sm](https://github.com/explosion/spacy-models/releases/tag/pl_core_news_sm-3.8.0), [md](https://github.com/explosion/spacy-models/releases/tag/pl_core_news_md-3.8.0), [lg](https://github.com/explosion/spacy-models/releases/tag/pl_core_news_lg-3.8.0)). Komponenty: tok2vec, morphologizer, parser, lemmatizer (trenowany), tagger, senter, attribute_ruler, ner. md i lg mają wektory fastText. |
| Stan starego algorytmu (lista luk) | §16 (`:803-837`) | Częściowo nieaktualna. Kod na `08` chroni już `nie`, tytuły, parę nazw, jednoliterowe słowa, znaki otwierające i zamykające, część `się` oraz dwóch mówców (`linebreak.py:339-348, 457-476`). Nadal nie ma: pomiaru fontu w dialogu, liczb z liczebnikiem lub jednostką, grup nominalnych, enklityk, więcej niż dwóch mówców ani więcej niż dwóch wierszy. |
| „Szerokość jest liczona znakami”, pomiar jako przyszły spike | §23 (`:1479-1517`) | Pomiar istnieje (`geometry.py:240-264`, research `measurement.md`), ale dialog na `08` go nie używa |

### 4.3 Czego brakuje lub co jest wątpliwe

1. **Licencja modeli spaCy.** Wszystkie trzy polskie modele mają „License: GNU GPL 3.0” (opis wydań powyżej; źródła: UD Polish PDB v2.8 i NKJP). Sam spaCy jest na MIT. Dokument tego nie wspomina, a AniShift i MangaShift nie mają pliku `LICENSE` ani pola licencji w `pyproject.toml`. Model pobierany przy instalacji (jak dziś narzędzia z `anishift setup`) nie jest rozpowszechniany z repozytorium. To nadal jednak decyzja właściciela.
2. **Jakość modeli na dialogu.** Dokument nie podaje dokładności. Według opisów wydań POS/UAS/LAS wynosi: sm 96,94/87,33/79,27, md 97,66/89,10/81,73, lg 97,83/89,59/82,54 (MORPH 87,74/89,50/90,97). To wyniki na treebanku prasowo-literackim, nie na krótkich potocznych kwestiach z anime. Rozstrzygnąć to ma P3.
3. **Sprzeczny porządek kryteriów.** §11 (`:597-609`) stawia `syntactic_damage_class` **przed** `overflow`, a §22.5 (`:1449-1461`) `overflow_width` **przed** `syntactic_damage`. Druga wersja to dokładnie błąd starego algorytmu (rozdz. 5.2). Pierwsza z kolei dopuszcza dowolnie długi wiersz, byle cięcie było składniowe, a to również skrajność.
4. **Model sztywno leksykograficzny** (§11, §22.5) stoi w sprzeczności z wymaganiem właściciela, żeby decyzja była rozmyta. Ranking krotek zamienia każdy próg w klif: przekroczenie o jeden znak przebija każdy sens.
5. **Jeden wiersz kontra dwa** sprowadza się do „jeden, gdy się mieści” (§9.2). Dokument pomija zasłanianie obrazu i zwartość bloku, o które pyta właściciel.
6. **Morfeusz2, UDPipe, Stanza** są tylko z nazwy. Dla porządku: `morfeusz2` 1.99.15 ma koło `cp310-abi3-win_amd64`, 9,7 MB, które z racji ABI3 powinno działać na 3.14 (nie testowałem; [PyPI](https://pypi.org/project/morfeusz2/1.99.15/)). Ocena należy do P3.
7. **Dzielenie wyrazów.** §13 i §20.5 (`:714-716, 1188-1196`) słusznie wykluczają je w dialogu. Brakuje jednak furtki dla zastosowań, w których dzielenie jest dozwolone (MangaShift, ciasne szyldy). Rdzeń musi ją mieć w kontrakcie, nawet jeśli AniShift z niej nie korzysta.
8. **Przykład z §5.4** (`:270-282`): „On / się boi ciemności.” jako „DOBRZE” zostawia jednowyrazowy wiersz przy 21 znakach, których nikt by nie łamał. Ilustruje regułę, ale sam jest złym układem.
9. **Budżet wydajności** (§26.5, `:1716-1729`: < 100 ms na odcinek bez NLP, < 1 s z NLP) jest dużo ostrzejszy niż obecna zgoda właściciela („kilka minut” na odcinek). Nie ogranicza więc wyboru.

## 5. Stary algorytm (`08`) a odrzucony (`16`)

### 5.1 Jak działa stary

Słowa (spacje znormalizowane z zachowaniem NBSP) → dla każdej przerwy predykaty `_dialogue_protected`, `_syntactic_risk` i `_boundary_rank` → kandydaci (każda przerwa) → minimum krotki `(overflow, risk, rank, orphan, balans)` → jedno cięcie → prawa strona bez dalszego cięcia przy 2 wierszach. Cały plik ma 605 linii, z czego ok. 230 to listy słów ze źródłami.

### 5.2 Dowody: korpus odtworzeń i złoty zbiór

Korpus odtworzeń (37 par, 14 677 zdarzeń w klonowanych stylach dialogu, te same wejścia po obu stronach):

| Miara | Stary `u6-font` | Odrzucony `preview-u5-font` |
| --- | ---: | ---: |
| Zdarzenia 1 / 2 / 3 wiersze | 10 683 / 3 994 / 0 | 11 261 / 3 414 / 2 |
| Pojedynczy wiersz > 42 znaki | **0** | **871** |
| Pojedynczy wiersz > 50 znaków | 0 | 230 |
| Zdarzenie wielowierszowe z wierszem > 42 | 217 | 837 |
| Cięcia po interpunkcji / wszystkie cięcia | 1 766 / 3 994 (44%) | 2 339 / 3 418 (68%) |
| Cięcie bezpośrednio po `się` (bez interpunkcji) | 103 | 49 |
| Wiersz z jednego słowa | 198 | 211 |
| Dwa wiersze, choć całość ma ≤ 42 znaki | 10 (dwie osoby) | 303 (np. „Obrzydlistwo! / Paskudztwo! Co za bezwstyd!”) |

W losowej próbie 60 starych cięć bez interpunkcji około 10 jest wyraźnie złych. To moja ocena, nie właściciela:

- „Można / by jednak rzec” — oderwana enklityka;
- „w głębi / duszy” — rozcięte stałe wyrażenie;
- „usłyszę jej / głos”, „przed moim / kroczem” — określnik oderwany od rzeczownika;
- „na tle / zachodzącego słońca” — cięcie tuż za przyimkiem złożonym;
- „Ale skąd to wiesz? Zupełnie / jakbyś…” — koniec zdania przegrał przez 1 znak przepełnienia;
- „tata na pewno / mi na to nie pozwoli” — wiersz zaczyna się enklityką;
- „które sekretarce / Fujiwarze” — tytuł oderwany od nazwiska;
- „mąż też się / oddala” — `się` oderwane od następującego po nim czasownika.

W próbie 20 cięć po `się` źle wypadają 2–3, na przykład „zamierzasz się / do niej dobierać”.

Złoty zbiór: stary `split_line` zgadza się z oczekiwanym układem w **17 z 39** przypadków. Różnice według przyczyny (długości w znakach liczyłem na oczekiwanych wierszach):

| Przyczyna | Przypadki | Przykład |
| --- | --- | --- |
| **A. Przepełnienie jest pierwszym kluczem** (`linebreak.py:426-427, 445-452`): naturalne cięcie (po przecinku, myślniku albo przed spójnikiem) przegrywa, bo daje wiersz o 2–16 znaków dłuższy od 42 | 03, 07, 08, 09, 10, 36, 37, 38, 39 (9) | 03: oczekiwane `31 / 58` znaków po przecinku; stary daje „…mógłbym wysadzić / w powietrze…” |
| **F. Wszystko powyżej 42 znaków jest cięte** (`_split`, `:406`) | 04 (55 zn.), 13 (48), 14 (44), 24 (43) (4) | 04: stary daje „z taką / złością”, oczekiwano jednego wiersza |
| **B/C. Budżet wierszy i mówcy**: tylko 2 wiersze, prawa część bez kontroli, tylko dokładnie dwóch mówców | 06, 26, 27, 33 (4) | 27: drugi mówca w jednym wierszu 98 znaków |
| **D/G. Luki w dowodach**: liczba z liczebnikiem, `się` między posiłkowym a głównym, brak premii za początek frazy (decyduje balans) | 11 („1,4 / miliarda”), 15 („będziesz się / bawił”), 19 („Rada / schwytała”) (3) | — |
| **H. Wtrącenie** (spójnik „że” ma wyższą rangę niż domknięcie wtrącenia) | 18 (1) | znany przypadek, odrzucony też go nie rozwiązał |
| Nie dotyczy trybu znakowego | 28 (ratunek „Jan / Kowalski” przy wąskiej szerokości) | — |

Wniosek z dowodów: rdzeń starego algorytmu (dowód przerwy i ranking kandydatów) jest zdrowy. **13 z 22 różnic bierze się z jednej reguły**, czyli 42 znaków jako twardego progu na pierwszym miejscu. Kolejne 4 to sztywny budżet dwóch wierszy, a 3 to konkretne, nazwane luki w dowodach. Mamy więc trzy konkretne przyczyny, a nie powód, żeby budować wszystko od nowa.

Dane pokazują też przybliżoną granicę gustu w znakach (nie w pikselach). Oczekiwane są pojedyncze wiersze 43–55 znaków (04, 13, 14, 24) i dwuwierszowe układy z wierszem 49–58 znaków (03, 07, 09, 10, 38). Zarazem 60-znakowy pojedynczy wiersz z galerii `obecny-vs-nowe-lamanie` 02 jest „zły”. „Długi wiersz” powinien więc rosnąć łagodnie w okolicy 50–60 znaków, a nie skakać przy 42. Kalibracja należy do P5.

### 5.3 Co dokładnie było „przekombinowane” w `16`

1. **Dziewięć szkód z ręcznymi wagami** (SENSE 0,95, PAUSE 0,45, TIGHT 0,45, MARGIN 0,45, LENGTH 0,70, FRAG 0,45, COUNT 0,45, AUTH 0,25, SHAPE 0,15; `q-breaks/.../linebreak.py:89-117`) **i dwanaście ramp** (`:119-147`), łączonych noisy-OR (`:447-462`). Szkody zależą od siebie (PAUSE, FRAG i TIGHT mierzą pokrewne rzeczy), więc każda poprawka jednej przesuwała inną. Tę historię opisuje aneks v5 w `fuzzy-line-breaks.md:11-20`.
2. **Cztery stopnie ratunku z flagami** (`_chosen`, `:387-407`), wyszukiwanie wyczerpujące do 3 cięć (`_candidates`, `:410-424`) **plus osobne DP** dla większej liczby wierszy (`_searched`, `:535-553`). To dwie metody wyszukiwania na jeden problem.
3. **Podwójna skala**: zmierzona w pikselach i znakowa (`_Scale` z 8 polami, `:167-178`, `:368-376`), do tego klasa `_Ruler` z czterema słownikami pamięci podręcznej (`:193-284`).
4. **Długość mierzona udziałem szerokości ekranu (`u`)**, nie ilością tekstu. Z wąską Officiną 60 znaków to ok. 80% szerokości, więc długi wiersz nie był karany, dopóki aneks v5 nie dołożył drugiej rampy znakowej (`fuzzy-line-breaks.md:17`).
5. **Leksykon rozrastający się pod pojedyncze przykłady z galerii** (`q-breaks/.../lexicon.py`, 477 linii): `GENITIVE_HEADS = {"woli", "imieniu", …}` (`:183-186`) wprost z „woli / Artemis”, `_NOT_ADJECTIVES` z „laska”, „deska”, „miska” (`:164-167`), `FIXED_PHRASES` z „kłody pod nogi” i „strzał w dziesiątkę” (`:204-220`). Właściciel nazwał to łataniem przypadków. Struktura dowodu `Boundary(harm, strong, speaker, protected, single, banned)` (`:277-286`) jest natomiast sensowna, bo to kształt wyniku analizy z rozdz. 7.
6. **Efekt na wyniku**: 871 pojedynczych wierszy > 42 znaków i 303 niepotrzebne podziały krótkich kwestii (tabela w 5.2).

Co `16` zrobił lepiej i warto przenieść: większy udział cięć po interpunkcji (zgodny z przypadkami A), wybrane listy (enklityki, liczebnik po liczbie, `się` po posiłkowym, odmienione określniki) oraz filtr mieszczenia zgodny z libass przez `wrap_text` dla zdarzeń zawijanych.

## 6. MangaShift

### 6.1 Co tam jest

| Element | Gdzie | Stan |
| --- | --- | --- |
| Układ tekstu w dymku | `MangaShift/desktop/src/features/editor/modules/text/layout/output-text-layout.ts:1, 55-202` | Front (TypeScript). `@chenglou/pretext` `layoutWithLines` łamie **zachłannie** w prostokącie (bbox minus padding). `fittedSize` (`:134-156`) szuka binarnie rozmiaru fontu w 20 krokach, aż wszystkie wiersze zmieszczą się w szerokości i wysokości. Tryb `autoWrap=false` przyjmuje gotowe wiersze z `\n` (`:173-182`). Brak polskich reguł, kształtu dymka, równoważenia i dzielenia wyrazów. |
| Render w backendzie | `MangaShift/mangashift/services/text_render/svg_builder.py:16-49`, `types.py:31-49` | Python dostaje gotowe pozycje wierszy, a w `:17` stoi „the backend never re-wraps text (parity)”. Powód: pomiar w Canvas i w Pythonie różni się o 2–10% (`docs/brainstorms/render/temp/subagents/research-pretext-layout.md:61, 106`). |
| Pretext 0.0.9 (MIT) | `node_modules/.bun/@chenglou+pretext@0.0.9/node_modules/@chenglou/pretext/README.md:97, 138-142` | Miękki dywiz U+00AD działa jako opcjonalny punkt podziału, z widocznym `-` po wybraniu. „Automatic hyphenation is not built in today.” `layoutNextLine` przyjmuje inną szerokość dla każdego wiersza, co pozwala na kształt dymka. `walkLineRanges` służy do wyszukiwania zrównoważonego układu. |
| Usunięty renderer Python | `git show 9451050ce^:mangashift/services/image_processing/render/text_renderer.py` (`_word_wrap` od 296, `_syllable_split` 327-338) | Usunięty 2026-07-05 (#192). Zachłanny wrap z sylabizacją regexem (`(?<=[aeiouyąęó])(?=[spółgłoski]{1,3}[aeiouyąęó])`), dywizem przy długim słowie, regułą „`...` zostaje w ostatnim wierszu” i wyszukiwaniem rozmiaru fontu |
| Legacy chunker | `external/code/image_working_space/utils/text_chunker.py` | Patrz 3.2 |
| Polski NLP, `pyphen` | `pyproject.toml`, `desktop/package.json` | Brak zależności. Plan: „TERAZ regex, LATER pyphen” (`brainstorm-text-rendering-pipeline.md:126-131`). |

Referencje zewnętrzne w `MangaShift/external/code/` (kod obcy, tylko do podglądu):

- **koharu** (MIT/Apache-2.0), Rust, `crates/koharu-renderer`. `segment.rs` liczy punkty podziału z ICU, usuwa je wewnątrz chronionych zakresów (`apply_protected_ranges`, `:255-272`) i dokłada segmenty z dywizem (`hyphenated_segments`, `:184`). `layout.rs` ma `HyphenationPolicy {Disabled, LastResort, Normal}` (`:32-40`). Programowanie dynamiczne po punktach podziału z profilem szerokości każdego wiersza dymka (`exact_profiled_line_breaks`, `:1666-1720`) minimalizuje koszt: luz² · 1000 + przepełnienie² · 10⁶ + kara przerwy + 2000 za dywiz. Kara przerwy z tekstu (`comic_break_penalty`, `:2065-2096`) wynosi: koniec zdania 0, przecinek lub myślnik 20, przed spójnikiem 40, po rodzajniku lub przyimku 300, reszta 100. **To dokładnie podział „analiza przerw + wybór z geometrią”**, tylko z angielskimi listami.
- **manga-image-translator** (GPL-3.0) `manga_translator/rendering/text_render.py:612+` (`calc_horizontal`): sylaby z PyHyphen, dywiz przy przepełnieniu, cofanie podziału między wierszami.
- **comic-translate** (Apache-2.0) `modules/rendering/hyphen_textwrap.py`: `textwrap` z dywizem przy łamaniu długiego słowa (bez słownika).

### 6.2 Dzielenie wyrazów po polsku: Pyphen

`pyphen` 0.18.1 (2026-08-14, `py3-none-any`, 2,1 MB koło, 6,3 MB po instalacji ze wszystkimi słownikami; licencja GPLv2+/LGPLv2+/MPL 1.1 do wyboru; [PyPI](https://pypi.org/project/pyphen/0.18.1/)). Słownik `hyph_pl_PL.dic` (37 931 B) pochodzi z wzorców TeX `plhyph.tex` 3.0a z 1995 r. Adaptacja OpenOffice jest na LGPL ([README](https://github.com/Kozea/Pyphen/blob/main/pyphen/dictionaries/README_hyph_pl_PL.txt)). Domyślnie zostawia min. 2 litery z każdej strony. Wyniki z mojego testu:

- poprawne: `pod-eks-cy-to-wa-ni`, `naj-traf-niej-szym`, `nie-prze-wi-dy-wal-ność`, `prze-wod-ni-czą-cy`, `dżdżow-ni-ca`, `zmar-twych-wsta-nie`;
- błędne: `zmar-z-łeś` i `mar-z-nąć` (jednoliterowy fragment), `Ka-guy-a-sa-ma` (japońskie imię z łącznikiem), `bia-ło--czer-wo-ny` (podwójny łącznik przy istniejącym dywizie).

Czas: ok. 0,3 µs na słowo po rozgrzaniu (z pamięcią podręczną Pyphen). Do użycia potrzebne są filtry: fragment ≥ 2 litery, bez podziału nazw obcych i romanizacji, osobna reguła dla istniejącego łącznika. Polska reguła o powtarzaniu łącznika na początku nowego wiersza wymaga potwierdzenia w zasadach RJP/PWN, bo nie znalazłem źródła.

### 6.3 Co da się współdzielić

- **Analizę przerw (warstwa a).** Polskie listy, interpunkcja, mówcy, stopień szkody cięcia i opcjonalnie punkty dzielenia wyrazu nie zależą od ASS ani od przeglądarki. Backend MangaShift też działa na Pythonie 3.14 (`mangashift/__pycache__/*.cpython-314.pyc`).
- **Nie da się współdzielić samego wyboru.** W MangaShift wybór musi zapaść we froncie, bo tylko pretext mierzy tak, jak się rysuje. Transport: backend po tłumaczeniu dołącza do wiersza listę przerw (JSON), a front wybiera układ, na przykład DP jak w koharu z `layoutNextLine`. Wariant prostszy to wstawienie znaków sterujących dla zachłannego pretextu: U+00AD w miejscach dywizu, U+00A0 lub U+2060 w zakazanych przerwach. Gubi on jednak stopniowanie przerw.
- Zgodnie z poleceniem właściciela niczego z tego dziś nie wdrażamy. Kontrakt rdzenia ma tylko nie zamykać tej drogi.

## 7. Projekt wspólnego rdzenia

### 7.1 Zasada podziału

```text
tekst (bez tagów i znaczników <sN>)
  └─ (a) analiza polskiego tekstu → słowa + Gap dla każdej przerwy (+ opcjonalnie punkty dywizu)
        └─ (b) wybór układu, osobny dla każdego zastosowania:
              • dialog AniShift  – 1–2 wiersze (3 w ratunku), bez dzielenia wyrazów, pomiar fontu zdarzenia
              • szyld AniShift   – dokładnie N wierszy, proporcje autorskie (kontrakt split_lines)
              • dymek MangaShift – N wierszy w kształcie, dzielenie dozwolone (front, pretext)
  └─ istniejąca rekonstrukcja: restore_markers / reflow_visible_text / replace_visible_text
```

### 7.2 Warstwa (a): analiza przerw, minimalny kontrakt

Miejsce: `anishift/text/` (np. `gaps.py`). Moduł bez importów `anishift.services`, bez przełączników domenowych, zgodnie z `anishift/text/AGENTS.md`. Zależy tylko od `boundaries.py` i `graphemes.py`, więc da się go skopiować do MangaShift bez reszty AniShift.

```python
@dataclass(frozen=True, slots=True)
class Gap:
    """Evidence for a line break at one break opportunity."""

    harm: float  # 0 = natural boundary … 1 = bound pair kept together at all costs
    pause: bool  # ends a sentence or a clause (punctuation), for shape and orphan rules
    turn: bool  # a new speaker starts after the gap
    banned: bool  # breaking here violates an inviolable rule
    hyphen: bool = False  # opportunity inside a word that prints "-"; never produced for AniShift dialogue


def gaps(words: Sequence[str]) -> tuple[Gap, ...]:
    """Return the evidence for every break between neighbouring words."""
```

Źródła dowodu, w kolejności i bez nowych pojęć:

1. Interpunkcja i skróty z `anishift/text/boundaries.py`, czyli hierarchia chunkera: koniec zdania (`harm≈0`, `pause`) > przecinek, średnik, dwukropek, myślnik (`pause`) > spacja.
2. Struktura: myślnik dialogowy (`turn`), znak otwierający na końcu lub zamykający na początku wiersza (`banned`), NBSP/`\h` (brak przerwy).
3. Listy słów ze starego `linebreak.py:49-281`, uzupełnione o konkretne klasy z `16` (enklityki, liczba lub liczebnik z rzeczownikiem, `się` po posiłkowym, odmienione określniki). Każda klasa daje stopień `harm` przypisany do wartości językowej „mocna / średnia / słaba / chroniona” (§3 starego dokumentu). Konkretne liczby kalibruje P5.
4. Opcjonalnie analizator wybrany przez P3. Może **tylko zmieniać `harm`** (miękki dowód, §21.6), nigdy `banned`. Bez analizatora wynik jest deterministyczny. Wywołanie co linię (np. `nlp()` w spaCy) zmieści się w budżecie „kilku minut”, więc kontrakt `layout_dialogue` nie musi przyjmować wsadu. To szacunek, nie pomiar.

Jedna funkcja `gaps()` zastępuje dzisiejsze dwa rozjechane rankingi (`_dialogue_*` i `_best_cut`/`_weight`) oraz rozproszone predykaty. To jedno źródło prawdy o tym, jak dobre jest cięcie w danym miejscu. Dla dymków dochodzi później funkcja punktów dywizu (`Gap(hyphen=True)` wewnątrz słowa), np. na Pyphen z filtrami z 6.2. W AniShift jej nie ma, bo reguła 2.1.1 z `visual-quality.md` zabrania rozcinania wyrazu.

### 7.3 Warstwa (b): trzy małe funkcje wyboru

| Zastosowanie | Kandydaci | Ocena | Miejsce |
| --- | --- | --- | --- |
| Dialog AniShift | Wszystkie zestawy cięć bez `banned`, zawierające wszystkie `turn`. Do `max_lines` wierszy, +1 tylko w ratunku. Przy ≤ 30 słowach to ≤ 435 zestawów na dwa wiersze i ≤ 3 654 na trzy, czyli wyliczenie wyczerpujące bez DP. | Filtr: wiersz mieści się między marginesami według istniejących `measure_text`/`wrap_text` (reguła 2.2.4), a bez profilu według znaków. Ocena rozmyta na kilku zmiennych: sens (max `harm` wybranych przerw), długość jako ilość tekstu w znakach z `max_chars` jako punktem odniesienia, a nie limitem, liczba wierszy, sierota, kształt (pomijany przy `pause`). Agregację projektuje P5. | `subtitles/linebreak.py`, wnętrze `layout_dialogue` |
| Szyld AniShift | Dokładnie `count` wierszy (kontrakt `split_lines`) | Max `harm` plus odchylenie od autorskich proporcji (logika `_proportional_boundaries`, `linebreak.py:371-401`, z `_weight` zastąpionym przez `harm`) | `subtitles/linebreak.py`, `split_lines` i `split_for_layout` |
| Dymek MangaShift (przyszłość) | DP po przerwach i dywizach z szerokością każdego wiersza z kształtu dymka | `harm` + luz/przepełnienie + kara za dywiz zależna od polityki (`Disabled`/`LastResort`/`Normal` jak w koharu), z zewnętrzną pętlą rozmiaru fontu (już jest: `fittedSize`) | Front MangaShift, TypeScript |

### 7.4 Związek z obecnymi kontraktami

- `layout_translated(split, translations, *, fonts, limits, dialogue_font)` (`service.py:569`) i `_laid_out_text` (`:611`) bez zmian.
- `layout_dialogue(event, text, profile, limits) -> DialogueLayout` (`linebreak.py:305`) zachowuje sygnaturę. W środku `split_line(...)` ustępuje `gaps()` + wyborowi dialogu, a `profile` zaczyna służyć pomiarowi (jest już przekazywany). Pole `DialogueLayout.flags` może raportować ratunek, tak jak już przewiduje typ.
- `split_lines(event, text, count, profile)` (`linebreak.py:318`) zostaje kontraktem dla dopasowania szyldów z `18`. Implementacja przechodzi na te same `gaps()`.
- `split_for_layout(text, source_verses, *, max_chars, max_lines)` (`:351`) zostaje dla `fit_signs._reflow` (`fitting.py:88`) i wyświetlanych (`service.py:614`), na tych samych `gaps()`.
- `split_line(text, *, max_chars, max_lines)` (`:329`) może zostać ścieżką bez pomiaru (SRT bez stylów), z rozmytą długością zamiast progu.
- `LayoutLimits(max_chars, max_lines)` bez zmian, ale `max_chars` zmienia znaczenie z limitu na punkt odniesienia. Ustawienie w panelu („Znaków w linii”) pozostaje.
- Testy: `test_subtitles_linebreak.py:87-91` i `:225-229` kodują twardy limit. Przy rozmytej długości trzeba je zmienić, a to zmiana kontraktu do akceptacji właściciela. Pozostałe ok. 43 testy (zakazy, mówcy, frazy, skróty, NBSP, kolejność słów) pozostają ważne.
- Chunkery translation i TTS: bez zmian. Mają inny cel (twarde limity żądań). Mogą dalej korzystać z `boundaries.py`, jak dziś.

## 8. Rekomendacje reuse

| # | Weź | Skąd | Po co |
| --- | --- | --- | --- |
| 1 | Szkielet starego algorytmu: słowa → dowód przerwy → ranking wszystkich kandydatów; obsługa mówców; znaczniki przez `restore_markers` | `08` `linebreak.py:305-476` | Działa i właściciel go akceptuje. Naprawić trzy nazwane przyczyny z 5.2 zamiast przepisywać całość. |
| 2 | Listy z Wikisłownika z adnotacjami `# source:` | `08` `linebreak.py:49-281` | Podstawa `gaps()` |
| 3 | Wybrane klasy z leksykonu `16`: `ENCLITICS`, liczba przed słowem (`_RE_NUMBER`), `się` po `VERB_HEADS`, `_DETERMINERS` | `q-breaks/.../lexicon.py:105-115, 201, 258, 413` | Zamykają konkretne błędy: „Można / by”, „1,4 / miliarda”, „będziesz się / bawił”, „taką / złością”, „moim / kroczem” |
| 4 | Kształt rekordu dowodu (`Boundary` → `Gap`, 4–5 pól zamiast 6) | `q-breaks/.../lexicon.py:277-286` | Jawny wynik analizy, łatwy do testów i do JSON |
| 5 | Pomiar i emulacja zawijania libass jako **filtr mieszczenia** | `08` `geometry.py:240-264` | Reguła 2.2.4. Nie jako miara długości (wniosek aneksu v5). |
| 6 | `rise`, `fall`, `nor` | `08` `subtitles/fuzzy.py:10-26` | Funkcje przynależności bez nowego kodu |
| 7 | `boundaries.py`, `graphemes.py`, `markers.py` | `anishift/text/` | Jedno źródło interpunkcji, grafemów i znaczników. Ujednolicić tam semantykę wielokropka. |
| 8 | Złoty zbiór 39 przypadków jako test akceptacyjny | `q-breaks/tests/services/subtitles/test_subtitles_line_break_cases.py` (`_EXPECTED`) + `workspace/.quality/experiments/fuzzy-spec/cases/` | Obiektywny wynik: dziś stary ma 17/39 w trybie znakowym |
| 9 | Korpus odtworzeń i statystyki klas cięć (rozdz. 5.2) | `workspace/.quality/experiments/replay/` | Kontrola regresji na 14 677 zdarzeniach, z mierzalnymi wskaźnikami: pojedynczy wiersz > 50, cięcia po przyimku lub `się`, niepotrzebne podziały |
| 10 | Praktyka Shishy (64 ręczne łamania) jako ludzki punkt odniesienia | `workspace/.quality/experiments/research-principles/` (`docs/work/10-quality/research/typesetting-principles.md:109-131`) | Mały, ale jedyny profesjonalny polski wzorzec w repo |
| 11 | Dla MangaShift później: koharu jako wzorzec architektury, Pyphen `pl_PL` z filtrami, miękki dywiz i `layoutNextLine` w pretext | rozdz. 6 | Bez wdrożenia teraz |

Czego nie brać:

- 9 szkód, 12 ramp, 4 stopni ratunku i podwójnej skali z `16`;
- list pisanych pod pojedyncze przykłady (`GENITIVE_HEADS`, `_NOT_ADJECTIVES`, rzadkie `FIXED_PHRASES`);
- algorytmów pakowania z chunkerów jako wyboru układu;
- długości mierzonej udziałem szerokości ekranu.

## 9. Otwarte kwestie (do decyzji lub dalszego badania)

1. **Dzielenie wyrazów w szyldach AniShift.** Właściciel widzi zastosowanie „w ciasnym obszarze”, ale reguła nienaruszalna 2.1.1 w `visual-quality.md` mówi, że żaden wyraz nie jest rozcinany. Potrzebna decyzja: zostawić zakaz, czy dopuścić dywiz w szyldach jako ostateczność. Kontrakt `Gap(hyphen=...)` obsłuży oba warianty.
2. **Licencja GPL-3.0 modeli `pl_core_news_*`**, jeśli P3 wybierze spaCy. Repozytoria nie mają pliku licencji. Potrzebna decyzja, czy model pobierany przy instalacji jest akceptowalny.
3. **Testy z twardym limitem** (`test_subtitles_linebreak.py:87-91, 225-229`) i reguła „jeden wiersz, gdy mieści się na szerokość” z `visual-quality.md` §4 (waga średnia, Shisha do ok. 57 znaków) muszą zostać pogodzone z nowym sygnałem: 60-znakowy pojedynczy wiersz jest zły, 43–55 bywa dobry.
4. **Semantyka wielokropka**: koniec zdania (chunkery) czy nie (spec v4, leksykon `16`). Do ustalenia w `boundaries.py`.
5. **Transport analizy do frontu MangaShift** (backend → API → pretext) i miejsce, w którym moduł rdzenia ma żyć fizycznie. Dziś nie ma wspólnego pakietu, więc rekomenduję kopię modułu, gdy MangaShift go zażąda, bez paczkowania na zapas.
6. **Pyphen dla polskiego** wymaga filtrów (jednoliterowe fragmenty, nazwy japońskie, istniejący łącznik). Zasadę powtarzania łącznika na początku wiersza trzeba potwierdzić w zasadach RJP/PWN.
7. **Duplikaty poza zakresem**, do osobnej decyzji: `subtitles/txt.py` powtarza `chunk_text`, a w kodzie są cztery implementacje wykrywania końca zdania (3.1).
8. W korzeniu worktree `fuzzy` leżą nieśledzone pliki innego agenta, o nazwach w rodzaju `UsersMATTYM~1AppDataLocalTempopencode*.pdf`/`.xml`. Nie ruszałem ich. Do sprzątnięcia przez ich właściciela.

## 10. Źródła

Kod (ścieżki względem worktree, gdy nie podano inaczej):

- `AniShift-wt/fuzzy` @ `03e60a6`: `anishift/text/{boundaries,graphemes,markers}.py`, `anishift/text/AGENTS.md`, `anishift/services/translation/chunking.py`, `anishift/services/tts/chunking.py`, `anishift/services/subtitles/{linebreak,layout,fitting,fuzzy,service,geometry,txt}.py`, `anishift/application/translation_handler.py`, `tests/services/subtitles/test_subtitles_linebreak.py`, `test_subtitles_dialogue_layout.py`.
- `AniShift-wt/q-breaks` @ `c2d3be4`: `anishift/services/subtitles/{linebreak,lexicon}.py`, `tests/services/subtitles/test_subtitles_line_break_cases.py`.
- `AniShift-wt/q-signs` @ `1f8898c`: `anishift/services/subtitles/fitting.py` (wywołania `split_lines`).
- `MangaShift` @ `ad47f6010`: `desktop/src/features/editor/modules/text/layout/output-text-layout.ts`, `mangashift/services/text_render/*`, `external/code/image_working_space/utils/text_chunker.py`, `external/code/koharu/crates/koharu-renderer/src/{segment,layout}.rs`, `external/code/manga-image-translator/manga_translator/rendering/text_render.py`, `external/code/comic-translate/modules/rendering/hyphen_textwrap.py`, commit `9451050ce` (usunięty renderer), README pretext 0.0.9.

Dokumenty:

- `docs/reference/subtitle-layout-engine.md`, `docs/work/10-quality/{visual-quality,fuzzy-line-breaks}.md`, `docs/work/10-quality/research/typesetting-principles.md`, `docs/work/00-rebuild/stage-04-translation/plans/{02-requirements-v1,06-fixes,09-chunker-linebreak}.md`, `docs/work/05-automation/{research/overview,plans/03-subtitle-layout}.md`.
- MangaShift: `docs/archive/brainstorms/2026-03-31-rendering-pipeline/brainstorm-text-rendering-pipeline.md`, `docs/brainstorms/render/{pretext.md,deep-research-report (3).md,temp/subagents/research-pretext-layout.md}`.
- Galeria: `AniShift/workspace/.quality/experiments/gallery/obecny-vs-nowe-lamanie/index.md`; odtworzenia `AniShift/workspace/.quality/experiments/replay/{u6-font,preview-u5-font}/`.

Rejestry (dostęp 2026-10-18):

- spaCy 3.8.16: https://pypi.org/project/spacy/3.8.16/
- thinc 8.3.13: https://pypi.org/project/thinc/8.3.13/; blis 1.3.3: https://pypi.org/project/blis/1.3.3/
- cymem: https://pypi.org/project/cymem/; preshed: https://pypi.org/project/preshed/; murmurhash: https://pypi.org/project/murmurhash/; srsly: https://pypi.org/project/srsly/; numpy 2.5.4 (koło cp314-win 12,7 MB): https://pypi.org/project/numpy/2.5.4/
- Modele: https://github.com/explosion/spacy-models/releases/tag/pl_core_news_sm-3.8.0, `…/pl_core_news_md-3.8.0`, `…/pl_core_news_lg-3.8.0`
- morfeusz2 1.99.15: https://pypi.org/project/morfeusz2/1.99.15/
- pyphen 0.18.1: https://pypi.org/project/pyphen/0.18.1/; słownik PL: https://github.com/Kozea/Pyphen/blob/main/pyphen/dictionaries/README_hyph_pl_PL.txt
- uniseg 0.10.1 (`py3-none-any`, 8,2 MB, 2026-01-09): https://pypi.org/project/uniseg/0.10.1/
