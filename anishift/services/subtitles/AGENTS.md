# subtitles

Napisy: klasyfikacja stylów ASS (DIALOG/SIGN/UNCERTAIN), split spoken/displayed, zwijanie klatka-po-klatce, zapis ASS/SRT.

## Pliki

- `classifier.py` — heurystyka klasyfikacji stylów ASS + deduplikacja animacji
- `service.py` — load/split/write + zwijanie FBF
- `text.py` — tag-bezpieczne operacje na tekście eventu ASS/SRT
- `linebreak.py` — polski reflow (`split_line`) i odtwarzanie authored layoutu (`split_for_layout`)
- `layout.py` — `LayoutLimits`: limity długości i liczby wierszy wybrane dla przebiegu
- `txt.py` — wczytanie UTF-8 i pocięcie na linie lektora
- `srt.py` — zapis przetłumaczonych linii lektora do SRT
- `types.py` — value objecty (Decision, SplitStats, SpokenLine, SubtitleKind, SubtitleSplit)
- `errors.py` — `SubtitleError` (dziedziczy `FatalError`)

## Pułapki

- Regexy sygnatur ASS budowane z `chr(92)+chr(92)` (dwa literalne backslashe, nie escape) — świadomy obchód reguły ruff psującej `\\`. `classifier.py:18,23`, `text.py:15`
- `classify_styles` liczy `raw_n` po WSZYSTKICH eventach, ale metryki tylko po zdeduplikowanych — dwie pętle po innych zbiorach. `classifier.py:189-203`
- `split_subtitles` ma cichy fallback: gdy żaden styl nie jest „spoken", a są nierysunkowe eventy, WSZYSTKIE nierysunkowe stają się „spoken". `service.py:167-169`
- W trybie auto decyzja zapada per linia przez `line_category`: actor szyldu → SIGN, chyba że linia jest zwykłym zdaniem (interpunkcja, bez `_RE_POS`) w głównym stylu dialogu (`main_dialogue_style`); styl UNCERTAIN → DIALOG tylko przy dialogowej nazwie stylu (`_RE_DLG`); inline `\an4`–`\an6` na DIALOG → SIGN. Jawne `spoken_styles` wybiera wyłącznie po stylu. `classifier.py`, `service.py`
- Translated writery pomijają spoken bez klucza `(style, visible_text)` (np. pusty tekst) — kopiują event bez zmian. `service.py`
- `replace_visible_text` zwraca raw event 1:1 dla niezmienionego visible text. Tagi z krawędzi wersu zostają na krawędzi, tagi przy granicy słowa trafiają na granicę słowa targetu, a tagi w środku słowa (gradienty) dostają osobne grafemy. Nienaruszone znaczniki `<sN>…</sN>` mają pierwszeństwo, uszkodzone są pomijane. `\h` zastępuje najbliższy whitespace targetu bez rozcinania słowa. `text.py`
- `marked_text` owija znacznikami tylko 1–4 śródwersowe granice tagów leżące przy krawędzi słowa; po `strip_span_markers` daje dokładnie `visible_text`. `SpokenLine.text` zostaje bez znaczników (klucz FBF i wejście TTS) — znaczniki dodają dopiero `spoken_lines`/`displayed_lines` w `application/translation_handler.py`. `text.py`
- `displayed_verses` nie zawiera eventów `\pN`; writer kopiuje rysunki raw i nie konsumuje dla nich pozycji tłumaczenia. `service.py`
- `spoken_to_srt` używa realnych czasów tylko gdy `end > start`; inaczej generuje czasy od kursora (15 znaków/s, 1200–8000 ms, gap 80 ms). `srt.py:49-56`
- Zapisy atomowe przez `.tmp` + `replace`, ale nazwa temp = `dest.name + ".tmp"` (dokleja do pełnej nazwy, nie podmienia suffiksu). `service.py`, `srt.py`

## Konwencje

- Pusty wynik to `None`, nie pusty plik: writery strumieni gdy wybrany strumień jest pusty, writer pełny gdy `total_events == 0`, `spoken_to_srt` gdy brak linii. `service.py`, `srt.py`
- Writery źródłowe i przetłumaczone współdzielą filtr strumienia: pełny, spoken-only i displayed-only zachowują `info`, style oraz całe eventy poza zamianą widocznego tekstu. `service.py`
- Dla `kind == "srt"` split pomija klasyfikację: każdy Dialogue z góry „spoken", `verdicts` puste. `service.py:182-184`
- Progi klasyfikacji/scoringu to nazwane `Final` z docstringami — zmiana zachowania klasyfikatora = zmiana stałych, nie logiki. `classifier.py:56-93`
- Klucz zwijania FBF/spoken to para `(style, visible_text)`; translated writer musi dostać `spoken_verses` na tym samym kluczu — sprzężenie `collapse_fbf` ↔ `_translated_file`. `service.py`
- `split_line` buduje nowy polski podział, a `split_for_layout` zachowuje authored line count dla złożonych `displayed`, jeśli target ma dość granic słów; nigdy nie rozcina pojedynczego słowa ani nie tworzy pustej linii. `linebreak.py`
- `linebreak` bierze `SENTENCE_ENDINGS` i `PHRASE_CUT_CHARS` wprost z `anishift/text/boundaries.py` (SSOT), a `text.py` grafemy z `anishift/text/graphemes.py`; rysunek `\pN` rozpoznaje wyłącznie `is_drawing`. `linebreak.py`, `text.py`

## Decyzje i odesłania

- `_header_notice` (tylko przy zapisie ASS) importuje `importlib.metadata` lokalnie i przy braku pakietu stempluje `v…`→`dev`; nagłówek zawiera URL projektu. `service.py:55,59-67`
- Heurystyka klasyfikacji wprost oparta na „measured mm_avh heuristic". `classifier.py:1`
- `srt.py` deklaruje, że plik to skrypt lektora, nie overlay wideo — czasy mają być tylko monotoniczne i czytelne. `srt.py:1-7`
