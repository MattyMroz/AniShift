# subtitles

Napisy: klasyfikacja stylów ASS (DIALOG/SIGN/UNCERTAIN), split spoken/displayed, zwijanie klatka-po-klatce, zapis ASS/SRT.

## Pliki

- `classifier.py` — heurystyka klasyfikacji stylów ASS + deduplikacja animacji
- `service.py` — load/preview/split/write + zwijanie FBF
- `text.py` — tag-bezpieczne operacje na tekście eventu ASS/SRT
- `txt.py` — wczytanie UTF-8 i pocięcie na linie lektora
- `srt.py` — zapis przetłumaczonych linii lektora do SRT
- `types.py` — value objecty (Decision, SplitStats, SpokenLine, SubtitleKind, SubtitleSplit)
- `errors.py` — `SubtitleError` (dziedziczy `FatalError`)

## Pułapki

- Regexy sygnatur ASS budowane z `chr(92)+chr(92)` (dwa literalne backslashe, nie escape) — świadomy obchód reguły ruff psującej `\\`. `classifier.py:18,23`, `text.py:15`
- `classify_styles` liczy `raw_n` po WSZYSTKICH eventach, ale metryki tylko po zdeduplikowanych — dwie pętle po innych zbiorach. `classifier.py:189-203`
- `split_subtitles` ma cichy fallback: gdy żaden styl nie jest „spoken", a są nierysunkowe eventy, WSZYSTKIE nierysunkowe stają się „spoken". `service.py:167-169`
- `write_translated` pomija spoken bez klucza `(style, visible_text)` (np. pusty tekst) — kopiuje event bez zmian. `service.py:257,259-261`
- `replace_visible_text` wstawia nowy tekst w miejsce PIERWSZEGO widocznego segmentu i porzuca kolejne, zachowując tylko bloki `{...}`. `text.py:58-69`
- `spoken_to_srt` używa realnych czasów tylko gdy `end > start`; inaczej generuje czasy od kursora (15 znaków/s, 1200–8000 ms, gap 80 ms). `srt.py:49-56`
- Zapisy atomowe przez `.tmp` + `replace`, ale nazwa temp = `dest.name + ".tmp"` (dokleja do pełnej nazwy, nie podmienia suffiksu). `service.py:228,294`, `srt.py:79`

## Konwencje

- Pusty wynik to `None`, nie pusty plik: `write_displayed` gdy `displayed_events == 0`, `write_translated` gdy `total_events == 0`, `spoken_to_srt` gdy brak linii. `service.py:225,291`, `srt.py:72-73`
- Dla `kind == "srt"` split pomija klasyfikację: każdy Dialogue z góry „spoken", `verdicts` puste. `service.py:182-184`
- Progi klasyfikacji/scoringu to nazwane `Final` z docstringami — zmiana zachowania klasyfikatora = zmiana stałych, nie logiki. `classifier.py:56-93`
- Klucz zwijania FBF/spoken to para `(style, visible_text)`; `write_translated` musi dostać `spoken_verses` na tym samym kluczu — sprzężenie `collapse_fbf` ↔ `_translated_file`. `service.py:143,257`

## Decyzje i odesłania

- `_header_notice` (tylko przy zapisie ASS) importuje `importlib.metadata` lokalnie i przy braku pakietu stempluje `v…`→`dev`; nagłówek zawiera URL projektu. `service.py:55,59-67`
- Heurystyka klasyfikacji wprost oparta na „measured mm_avh heuristic". `classifier.py:1`
- `srt.py` deklaruje, że plik to skrypt lektora, nie overlay wideo — czasy mają być tylko monotoniczne i czytelne. `srt.py:1-7`
