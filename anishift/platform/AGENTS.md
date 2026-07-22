# platform

Kod zależny od systemu: wykrycie OS i rozwiązywanie ścieżek do zewnętrznych binarek (mkvtoolnix / ffmpeg / balcon). Cała logika w `binaries.py`; `__init__.py` to re-eksport.

## Pułapki

- `TOOL_DIR` mapuje `Binary.BALCON` na podkatalog `"balabolka"`, NIE `"balcon"` — nazwa katalogu nie zgadza się z wartością enuma. `binaries.py:59`
- `FFMPEG`/`FFPROBE` dzielą podkatalog `"ffmpeg"`, `MKVEXTRACT`/`MKVMERGE` dzielą `"mkvtoolnix"` — jeden podfolder trzyma po dwie binarki. `binaries.py:60-63`
- Fallback do PATH (`shutil.which`) działa TYLKO poza Windows; na Windows `resolve_binary` przeszukuje wyłącznie `external/bin/` i nigdy nie zajrzy w PATH. `binaries.py:114-119`
- `_WINDOWS_ONLY` (balcon) poza Windows zawsze zwraca `None`, zanim sprawdzi cokolwiek na dysku. `binaries.py:107-108`
- `external_bin_root` liczy repo-root jako `parents[2]` — twardo zakłada głębokość `anishift/platform/binaries.py`; przeniesienie modułu zepsuje ścieżkę. `binaries.py:79-86`

## Konwencje

- `is_windows()` istnieje, by wołający NIE rozgałęziali sami po OS — bramkowanie balcona i doboru rozszerzenia scentralizowane tutaj. `binaries.py:9-11,74-76`
- Rozszerzenie `.exe` doklejane tylko na Windows przez `_exe_name`; gdzie indziej goły stem. `binaries.py:89-91`
- `BinaryNotFoundError` dziedziczy po `FatalError` i podnosi się z pełnym `ErrorContext` (`ErrorCode.BINARY_NOT_FOUND`). `binaries.py:52-53,141-148`
- Komunikat naprawczy `require_binary` różni się per OS: poza Windows dokleja podpowiedź o ręcznym dorzuceniu binarki do `external/bin/<tool>`. `binaries.py:138-140`
- `external/bin/<tool>/` jest gitignored, pobierane przez `anishift setup`. `binaries.py:3,138`
