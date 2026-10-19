# subtitles

Napisy: klasyfikacja stylów ASS (DIALOG/SIGN/UNCERTAIN), split spoken/displayed, zwijanie klatka-po-klatce, zapis ASS/SRT.

## Pliki

- `classifier.py` — heurystyka klasyfikacji stylów ASS, weto linii „etykieta × forma” + deduplikacja animacji
- `service.py` — load/split/write + zwijanie FBF i kopii kwestii; `inherit_split` przenosi decyzje źródła na przekład; `layout_translated` układa nierozbity przekład (dialog, szyldy, raport) dla writerów i normalizacji
- `geometry.py` — `RenderProfile` pliku, pomiar tekstu (`measure_text`, dziś Arialem 64 px), szerokość między marginesami, `safe_width` (obszar bezpieczny od kotwicy zdarzenia), `style_changes` (zmiana kroju, rozmiaru, skali albo wagi między słowami), zawijanie i prostokąty na ekranie
- `fitting.py` — `fit_signs`: dopasowanie szerokości szyldów do autorskiej geometrii
- `restyle.py` — `DialogueFont` (rodzina p3 ID1 w oryginalnej pisowni i warianty z polskimi literami z katalogu pliku) i `restyle_dialogue`: klon `<styl> (dialog)` (przy kolizji `(dialog 2)`, `(dialog 3)`…; styl źródłowy z nazwy klonu daje tylko `clone_source`) dla każdego stylu z większością linii spoken; linie spoken i ich `\r<styl>` przechodzą do klonu, displayed zostają bajtowo identyczne
- `text.py` — tag-bezpieczne operacje na tekście eventu ASS/SRT
- `linebreak.py` — `layout_dialogue`: dialog przez rdzeń układu (pole dialogu: 90% ekranu od kotwicy, pomiar `measure_text` z tagami danego wiersza i czcionką pliku albo dialogu właściciela, granice stylu z `style_changes`, `{\q2}`, gdy libass zawinąłby wybrany wiersz; SRT bez profilu — pomiar w grafemach) i odtwarzanie authored layoutu szyldów (`split_for_layout`, do fazy E)
- `layout.py` — `LayoutLimits`: limity długości i liczby wierszy wybrane dla przebiegu; rdzeń układu tekstu (spec `docs/work/10-quality/text-layout.md`): `Field`, wstrzykiwany pomiar `Measure`, `candidates` (pełny przegląd do 3 wierszy) i `lay_out` (poziom ratunku, potem ważona suma szkód; powyżej 3 wierszy programowanie dynamiczne). Wagi `WEIGHTS` z kalibracji (`scripts/subtitle_quality/layout_calibrate.py`, raport `docs/work/10-quality/research/text-layout-calibration.md`); dialog podpięty przez `layout_dialogue`, szyldy czekają na fazę E. `DEFAULT_MAX_CHARS`/`MAX_LINES` i `LayoutLimits` z ustawień użytkownika działają już tylko na szyldy. Test `test_text_layout_catalogue.py` wymaga zbioru dopuszczalnego dla każdego przypadku katalogu i ankiety
- `signs.py` — wagi rozmyte „za” i „przeciw” czytania szyldu przez lektora (statyczne na źródle i zależne od pauzy); grupy i `SignCandidate` liczy `service.py`, wybór pauzy `application/sign_narration.py`
- `fuzzy.py` — stopnie rozmyte `rise`/`fall` (0–1, liniowo między progami) i ich łączenie `nor`
- `txt.py` — wczytanie UTF-8 i pocięcie na linie lektora
- `srt.py` — zapis przetłumaczonych linii lektora do SRT
- `types.py` — value objecty (Decision, SplitStats, SpokenLine, SubtitleKind, SubtitleSplit, FontSources, LayoutReport, TranslatedLayout)
- `errors.py` — `SubtitleError` (dziedziczy `FatalError`)

## Pułapki

- Regexy sygnatur ASS budowane z `chr(92)+chr(92)` (dwa literalne backslashe, nie escape) — świadomy obchód reguły ruff psującej `\\`. `classifier.py:18,23`, `text.py:15`
- `classify_styles` liczy `raw_n` po WSZYSTKICH eventach, ale metryki tylko po zdeduplikowanych — dwie pętle po innych zbiorach. `classifier.py:189-203`
- `split_subtitles` nie ma fallbacku: plik ASS bez linii „spoken" (piosenki NC/ED, same szyldy, notki) zostaje bez lektora; zamówiony `SPOKEN_PL` kończy się w `application/subtitle_handler.py` błędem „Subtitle file contains no lines to read aloud". `service.py`
- W trybie auto decyzja zapada per linia przez `line_category`: actor szyldu → SIGN, chyba że linia jest zwykłym zdaniem (interpunkcja, bez `_RE_POS`) w głównym stylu dialogu (`main_dialogue_style`); styl UNCERTAIN → DIALOG tylko przy dialogowej nazwie stylu (`_RE_DLG`, także `Alt`); inline `\an4`–`\an6` na DIALOG → SIGN; weto: linia DIALOG bez znaku zdania, przecinka i końcowego myślnika, pisana wersalikami (`written_in_capitals`) albo tytułowo z położeniem → SIGN, chyba że ma ≤ 3 słowa, nie ma położenia i stoi przy krawędzi ekranu. Styl nazwany kodem piosenki (`_RE_SONG_NAME`: `EDup`, `OP_EN_blue`, `IN01`) to SIGN. Jawne `spoken_styles` wybiera wyłącznie po stylu. `classifier.py`, `service.py`
- Kwestia czytana raz: zwijanie łączy serię FBF (ten sam styl i tekst, przerwa ≤ 500 ms) oraz kopie kwestii: ten sam tekst bez wielkości liter i znaków spoza słów, w innym stylu albo wersalikowe echo w tym samym stylu, ze startem ≤ 500 ms od startu oryginału albo w ciągu 500 ms po jego końcu. Start w środku długiego zdarzenia (śmiech `GJM_Overlap` przez 22 s) nie jest kopią, więc powtórka innej postaci zostaje czytana; łańcuch kontynuacji (chór `Default`/`Alt`/`Default`) łączy się. `SpokenLine` bierze tekst, styl i `order` z pierwszego zdarzenia w pliku; `collapse_fbf` zwija tylko serie FBF. `service.py`
- `layout_translated` dostaje przekład po indeksie zdarzenia Dialogue: pierwsze zdarzenie każdej `SpokenLine` i każde displayed. Pozostałe zdarzenia kwestii (seria FBF i kopie w innych stylach) biorą przekład jej pierwszego zdarzenia, chyba że mają własny klucz; zdarzenie bez przekładu i rysunek zostają bez zmian. Normalizacja polskiego źródła podaje każdemu zdarzeniu jego własny tekst (z `\h`). `service.py`
- `inherit_split(source, subs)` przenosi decyzje źródła na przekład ASS po pozycji zdarzeń Dialogue, gdy zgadzają się start, koniec, warstwa i styl (ten sam albo jego klon wg `clone_source`); niezgodność albo inna liczba zdarzeń daje `None` i SPLIT klasyfikuje polski plik z ostrzeżeniem. Linie lektora liczy na tekstach przekładu. `service.py`, `application/subtitle_handler.py`
- `replace_visible_text` zwraca raw event 1:1 dla niezmienionego visible text. Tagi z krawędzi wersu zostają na krawędzi, tagi przy granicy słowa trafiają na granicę słowa targetu, a tagi w środku słowa (gradienty) dostają osobne grafemy. Nienaruszone znaczniki `<sN>…</sN>` mają pierwszeństwo, uszkodzone są pomijane. `\h` zastępuje najbliższy whitespace targetu bez rozcinania słowa. `text.py`
- `marked_text` owija znacznikami tylko 1–4 śródwersowe granice tagów leżące przy krawędzi słowa; po `strip_span_markers` daje dokładnie `visible_text`. `SpokenLine.text` zostaje bez znaczników (klucz FBF i wejście TTS) — znaczniki dodają dopiero `spoken_lines`/`displayed_lines` w `application/translation_handler.py`. `text.py`
- `displayed_verses` nie zawiera eventów `\pN`; writer kopiuje rysunki raw i nie konsumuje dla nich pozycji tłumaczenia. `service.py`
- `spoken_to_srt` używa realnych czasów tylko gdy `end > start`; inaczej generuje czasy od kursora (15 znaków/s, 1200–8000 ms, gap 80 ms). `srt.py:49-56`
- Zapisy atomowe przez `.tmp` + `replace`, ale nazwa temp = `dest.name + ".tmp"` (dokleja do pełnej nazwy, nie podmienia suffiksu). `service.py`, `srt.py`

## Konwencje

- Pusty wynik to `None`, nie pusty plik: writery strumieni gdy wybrany strumień jest pusty, writer pełny gdy `total_events == 0`, `spoken_to_srt` gdy brak linii. `service.py`, `srt.py`
- Writery źródłowe (pełny, spoken-only, displayed-only) i przetłumaczony pełny `write_translated` zachowują `info`, style oraz całe eventy poza zamianą widocznego tekstu; strumienie przekładu rozdziela dopiero SPLIT na `FULL_PL`. `service.py`
- Dla `kind == "srt"` split pomija klasyfikację: każdy Dialogue z góry „spoken", `verdicts` puste. `service.py:182-184`
- Progi i sygnatury klasyfikatora to nazwane `Final` z docstringami. Zmiana reguły (stałej albo logiki) wymaga listy zmian decyzji linii na korpusie `workspace/.quality` względem stanu poprzedniego, sprawdzenia etykiet `labels/split-labels.csv` i zielonego `test_regression_classifier.py`. `classifier.py`
- Kwestie lektora (`SpokenLine`) i przekład kopii w `layout_translated` mają jedno źródło członkostwa: `_spoken_runs` (serie FBF po `(style, visible_text)` + kopie kwestii); publiczne `spoken_groups` (zdarzenie → pierwsze zdarzenie kwestii) czyta też replay narzędzia jakości. `service.py`, `scripts/subtitle_quality/replay.py`
- Układ zapisuje cięcia jako `\N` także dla wyjścia SRT; zapis SRT (pysubs2) zamienia je na nową linię. Dialog: tagi kładzione raz na nierozbitym wierszu (`replace_visible_text` po `restore_markers`), rdzeń układa jego widoczny tekst (`\h` jako twarda spacja), a `reflow_visible_text` wstawia cięcia — pomiar i zapis widzą te same tagi; szyld dzielony przez `split_for_layout` przed `fit_signs`. `service.py`, `linebreak.py`
- `split_for_layout` zachowuje authored line count dla złożonych `displayed`, jeśli target ma dość granic słów; nigdy nie rozcina pojedynczego słowa ani nie tworzy pustej linii. `linebreak.py`
- `linebreak` bierze `SENTENCE_ENDINGS` i `PHRASE_CUT_CHARS` wprost z `anishift/text/boundaries.py` (SSOT), a `text.py` grafemy z `anishift/text/graphemes.py`; rysunek `\pN` rozpoznaje wyłącznie `is_drawing`. `linebreak.py`, `text.py`

## Decyzje i odesłania

- `_header_notice` (tylko przy zapisie ASS) importuje `importlib.metadata` lokalnie i przy braku pakietu stempluje `v…`→`dev`; nagłówek zawiera URL projektu. `service.py:55,59-67`
- Heurystyka klasyfikacji wprost oparta na „measured mm_avh heuristic". `classifier.py:1`
- `srt.py` deklaruje, że plik to skrypt lektora, nie overlay wideo — czasy mają być tylko monotoniczne i czytelne. `srt.py:1-7`
