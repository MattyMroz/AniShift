# extraction

Neutralna ekstrakcja pojedynczej ścieżki z MKV/MP4 do jawnej ścieżki celu oraz zachowany interfejs legacy ekstrakcji MKV. Heurystyczny wybór ścieżki audio i napisów pozostaje osobnym mechanizmem legacy.

## Pliki

- `service.py` — publiczny `ExtractionService` oraz legacy identify/extract
- `mkv.py`, `mp4.py` — adaptery ekstrakcji dla kontenerów
- `_adapter.py` — wspólna walidacja wyniku i mapowanie kontrolowanego procesu
- `tracks.py` — scoring i wybór ścieżek (NIE re-eksportowany)
- `types.py` — neutralne request/result/format oraz typy legacy
- `errors.py` — `ExtractionError` (dziedziczy `FatalError`)

## Pułapki

- `tracks.py` NIE jest re-eksportowany w `__init__.py` ani importowany przez `service.py` — scoring/wybór ścieżek dostępny tylko przez bezpośredni import modułu. `__init__.py:5`
- `ExtractionRequest.target_path` jest dokładnym celem w katalogu run-scope; adapter nie może go zastąpić, zmienić rozszerzenia ani nadpisać istniejącego pliku.
- MP4 używa indeksów streamów z `ffprobe`; napisy `mov_text`/`tx3g` są normalizowane przez FFmpeg do SRT. Audio jest kopiowane bez transkodowania.
- Neutralny adapter usuwa pusty lub częściowy cel po błędzie, timeout i anulowanie mapuje na kontrolowany `ExtractionError`.
- Funkcje scoringu przyjmują płaski `dict[str, Any]`, nie `TrackInfo`; `select_tracks` przepakowuje przez `_selector_shape`, który przemianowuje `num_entries`→`num_lines`. `tracks.py:132`
- Legacy `extract_tracks` czyta stdout w osobnym wątku, a wątek wywołujący pilnuje
  cancellation i jednego deadline'u, także po EOF. Cleanup czeka najwyżej 5 s po
  terminate, potem używa kill i kolejnego ograniczonego wait. Błąd callbacka również
  zatrzymuje proces i usuwa częściowe wyjścia. `service.py`
- Exit 0 lub ostrzegawczy exit 1 `mkvextract` wymaga wszystkich niepustych plików;
  exit 1 po walidacji zapisuje warning, exit 2 pozostaje błędem. Reguła obejmuje
  bulk i neutralny adapter MKV; nie przenoś jej na FFmpeg. `service.py`, `_adapter.py`, `mkv.py`
- Anulowanie obu interfejsów usuwa częściowe pliki i RZUCA `ErrorCode.CANCELLED`, nie zwraca.

## Konwencje

- Realny test deadline używa bazowego interpretera, nie windowsowego venv redirectora:
  modeluje jednoprocowe `mkvextract`. Czytnik jest właścicielem stdout i zamyka je
  także po opóźnionym EOF. Nie utożsamiaj zamknięcia procesu narzędzia z gwarancją
  zamknięcia dowolnego drzewa potomków niestandardowego wrappera.
- `_NEW_PROCESS_GROUP` = `CREATE_NEW_PROCESS_GROUP` tylko na Windows (0 gdzie indziej) — odcina dziecko od Ctrl+C konsoli. `service.py:49`
- Oba narzędzia wołane z `--ui-language en` — komunikaty i parsowanie niezależne od locale. `service.py:133,226`
- Postęp z linii `#GUI#progress N%` (`--gui-mode`), % klampowany do max 100. `service.py:37,257`
- Przy błędzie `mkvextract` do komunikatu trafia tylko ostatnie 8 nie-progress linii stdout (stderr złączony). `service.py:43,250`
- `parse_media_info` łapie osobno `KeyError`/`ValueError`/`TypeError`, nie szeroki `except`. `service.py:91`
- `identify` ma twardy timeout 120 s na plik. `service.py:40`
- Bulk extraction ma osobny `timeout_s` (domyślnie 3600 s); handler przekazuje
  timeout ekstrakcji z runtime. Nie używaj limitu krótkiego probe dla całej ekstrakcji.
- Oba interfejsy odrzucają istniejący cel przed uruchomieniem procesu; cleanup
  dotyczy wyłącznie nowych wyjść tej ekstrakcji.

## Decyzje (scoring)

- „Tekstowe napisy" = tylko `ass`/`srt`/`ssa` (przez tabelę codec→rozszerzenie), reszta odfiltrowana przed wyborem. `types.py:67`, `tracks.py:147`
- Ścieżki signs/song/forced dostają karę -200 — praktycznie nigdy nie wybrane. `tracks.py:43,52`
- `already_polish` (pol/pl) liczone po wyborze napisów, by pipeline mógł pominąć tłumaczenie. `tracks.py:55,155`
- Przy remisie scoringu wybierana niższa `id` (klucz `-int(id)`). `tracks.py:119,128`
- Wagi języków to LISTA priorytetów (`DEFAULT_AUDIO_PRIORITY`, `DEFAULT_SUBTITLE_PRIORITY`), podawana z preferencji (`config/settings.json`); pozycja na liście daje 100, 90, 80..., spoza listy 0. `tracks.py`
- Bonus za ścieżkę domyślną (1) MUSI być mniejszy niż krok priorytetu (10) — przy równych wartościach ścieżka domyślna przebijała preferowany język. `tracks.py`
- `MediaInfo.attachments` niesie nazwy plików załączników (czcionki) z `mkvmerge -J`; domyślnie pusta krotka. `types.py`, `service.py`
