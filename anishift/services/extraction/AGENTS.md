# extraction

Ekstrakcja ścieżek z MKV: `mkvmerge -J` identify + `mkvextract --gui-mode` z paskiem postępu i anulowaniem. Heurystyczny wybór ścieżki audio i napisów przez scoring.

## Pliki

- `service.py` — identify + extract z paskiem postępu i anulowaniem
- `tracks.py` — scoring i wybór ścieżek (NIE re-eksportowany)
- `types.py` — dataclassy wartości + tabela codec→rozszerzenie
- `errors.py` — `ExtractionError` (dziedziczy `FatalError`)

## Pułapki

- `tracks.py` NIE jest re-eksportowany w `__init__.py` ani importowany przez `service.py` — scoring/wybór ścieżek dostępny tylko przez bezpośredni import modułu. `__init__.py:5`
- Funkcje scoringu przyjmują płaski `dict[str, Any]`, nie `TrackInfo`; `select_tracks` przepakowuje przez `_selector_shape`, który przemianowuje `num_entries`→`num_lines`. `tracks.py:132`
- Anulowanie dwutorowe: inline `cancel.is_set()` w pętli po stdout ORAZ osobny wątek-watcher (zablokowany read stdout sam nie zauważy anulowania). `service.py:193`
- Po exit code 0 brakujący lub pusty (0 bajtów) plik wyjściowy jest traktowany jako błąd ekstrakcji. `service.py:272`
- Anulowanie usuwa częściowe pliki (`_remove_outputs`) i RZUCA `ErrorCode.CANCELLED`, nie zwraca. `service.py:184`

## Konwencje

- `_NEW_PROCESS_GROUP` = `CREATE_NEW_PROCESS_GROUP` tylko na Windows (0 gdzie indziej) — odcina dziecko od Ctrl+C konsoli. `service.py:49`
- Oba narzędzia wołane z `--ui-language en` — komunikaty i parsowanie niezależne od locale. `service.py:133,226`
- Postęp z linii `#GUI#progress N%` (`--gui-mode`), % klampowany do max 100. `service.py:37,257`
- Przy błędzie `mkvextract` do komunikatu trafia tylko ostatnie 8 nie-progress linii stdout (stderr złączony). `service.py:43,250`
- `parse_media_info` łapie osobno `KeyError`/`ValueError`/`TypeError`, nie szeroki `except`. `service.py:91`
- `identify` ma twardy timeout 120 s na plik. `service.py:40`

## Decyzje (scoring)

- „Tekstowe napisy" = tylko `ass`/`srt`/`ssa` (przez tabelę codec→rozszerzenie), reszta odfiltrowana przed wyborem. `types.py:67`, `tracks.py:147`
- Ścieżki signs/song/forced dostają karę -200 — praktycznie nigdy nie wybrane. `tracks.py:43,52`
- `already_polish` (pol/pl) liczone po wyborze napisów, by pipeline mógł pominąć tłumaczenie. `tracks.py:55,155`
- Przy remisie scoringu wybierana niższa `id` (klucz `-int(id)`). `tracks.py:119,128`
