# platform

Kod zależny od systemu: wykrycie OS i ścieżki binarek (`binaries.py`), blokada jednej instancji procesu (`process_lock.py`), zadanie Windows przy logowaniu (`autostart.py`). `__init__.py` to re-eksport binarek.

## Pułapki

- `ProcessLock` trzyma uchwyt przez cały czas życia procesu; plik blokady zostaje po zakończeniu i jego
  istnienie NIE oznacza zajętej blokady. Sprawdzaj przez nieblokujące `acquire()`. `process_lock.py`
- `autostart.py` zarządza wyłącznie zadaniem `AniShift Watch` przez `schtasks` (ONLOGON, bieżący
  użytkownik, `/RL LIMITED`); nie dotyka innych zadań, nie podnosi uprawnień. Poza Windows odmawia.
  `enable` także uruchamia zadanie od razu. `autostart.py`

- `FFMPEG`/`FFPROBE` dzielą podkatalog `"ffmpeg"`, `MKVEXTRACT`/`MKVMERGE` dzielą `"mkvtoolnix"` — jeden podfolder trzyma po dwie binarki. `binaries.py`
- Niepusty plik w `external/bin/` ma pierwszeństwo; fallback `shutil.which` działa
  także na Windows. Plik 0 B nie jest gotową binarką w żadnym źródle. `binaries.py`
- `external_bin_root` liczy repo-root jako `parents[2]` — twardo zakłada głębokość `anishift/platform/binaries.py`; przeniesienie modułu zepsuje ścieżkę. `binaries.py`

## Konwencje

- `is_windows()` istnieje, by wołający NIE rozgałęziali sami po OS przy doborze rozszerzenia i fallbacku PATH. `binaries.py`
- Rozszerzenie `.exe` doklejane tylko na Windows przez `_exe_name`; gdzie indziej goły stem. `binaries.py:89-91`
- `BinaryNotFoundError` dziedziczy po `FatalError` i podnosi się z pełnym `ErrorContext` (`ErrorCode.BINARY_NOT_FOUND`). `binaries.py:52-53,141-148`
- Komunikat naprawczy `require_binary` różni się per OS: poza Windows dokleja podpowiedź o ręcznym dorzuceniu binarki do `external/bin/<tool>`. `binaries.py:138-140`
- `external/bin/<tool>/` jest gitignored, pobierane przez `anishift setup`. `binaries.py:3,138`
