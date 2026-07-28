# platform

Kod zależny od systemu: wykrycie OS i rozwiązywanie ścieżek do zewnętrznych binarek (mkvtoolnix / ffmpeg). Cała logika w `binaries.py`; `__init__.py` to re-eksport.

## Pułapki

- `FFMPEG`/`FFPROBE` dzielą podkatalog `"ffmpeg"`, `MKVEXTRACT`/`MKVMERGE` dzielą `"mkvtoolnix"` — jeden podfolder trzyma po dwie binarki. `binaries.py`
- Fallback do PATH (`shutil.which`) działa TYLKO poza Windows; na Windows `resolve_binary` przeszukuje wyłącznie `external/bin/` i nigdy nie zajrzy w PATH. `binaries.py`
- `external_bin_root` liczy repo-root jako `parents[2]` — twardo zakłada głębokość `anishift/platform/binaries.py`; przeniesienie modułu zepsuje ścieżkę. `binaries.py`

## Konwencje

- `is_windows()` istnieje, by wołający NIE rozgałęziali sami po OS przy doborze rozszerzenia i fallbacku PATH. `binaries.py`
- Rozszerzenie `.exe` doklejane tylko na Windows przez `_exe_name`; gdzie indziej goły stem. `binaries.py:89-91`
- `BinaryNotFoundError` dziedziczy po `FatalError` i podnosi się z pełnym `ErrorContext` (`ErrorCode.BINARY_NOT_FOUND`). `binaries.py:52-53,141-148`
- Komunikat naprawczy `require_binary` różni się per OS: poza Windows dokleja podpowiedź o ręcznym dorzuceniu binarki do `external/bin/<tool>`. `binaries.py:138-140`
- `external/bin/<tool>/` jest gitignored, pobierane przez `anishift setup`. `binaries.py:3,138`
