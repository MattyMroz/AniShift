# utils

Przenośne (współdzielone z mm_avh): zero zależności od AniShift. Fasada `__init__` reeksportuje tylko lekkie `safe_*`/`PathTraversalError`; ciężkie zależności (torch przez `device`) NIE są ładowane przy imporcie pakietu.

## Podpakiety (każdy ma własny AGENTS.md)

- `logger/` — logger loguru z sinkami JSON/Rich, scrubbingiem, readerami
- `rich_console/` — preskonfigurowana `console`, motyw, paski postępu
- `timer/` — `Timer`, `ExecutionTimer`, `@timed`, `format_duration`

## Luźne pliki

- `_retry.py` — presety tenacity (`NETWORK_RETRY` dekorator, `build_retry()` per-call)
- `device.py` — wybór CUDA>CPU bez importu torcha
- `safe_fs.py` — `safe_rmtree`/`safe_move` z retry na `PermissionError`
- `safe_path.py` — `safe_resolve` chroniący przed path traversal
- `secrets.py` — niemutujące redagowanie sekretów w dictach
- `timing.py` — `elapsed_ms_since` na zegarze monotonicznym
- `_portable.py` — manifest przenośności (moduły, zależności, smoke-testy)

## Pułapki

- `device.py` NIGDY nie importuje torcha sam — torch w `sys.modules` sprawia, że `onnxruntime.InferenceSession` używa cuDNN torcha i zwalnia ładowanie modeli ONNX o dynamicznym kształcie. `device.py:1-13,44-46`
- `DeviceInfo` ma pola `mps`/`has_mps`, ale żadna ścieżka nie zwraca `device="mps"` — `has_mps` zawsze `False`. `device.py:36,104-116`
- `build_retry` przekazuje `sleep=asyncio.sleep` przez referencję (late-binding), by `monkeypatch.setattr(asyncio,"sleep",...)` działał — przeniesienie do domyślnego argumentu ominęłoby patcha. `_retry.py:143-152`
- W `build_retry` `max_attempts` to CAŁKOWITA liczba wywołań (`stop_after_attempt`), nie liczba dodatkowych ponowień. `_retry.py:142,153`
- `_is_retryable_network_error` rozpoznaje `DownloadError` po nazwach w `__mro__` (lazy) i celowo NIE ponawia gdy w MRO jest też `OfflineError`. `_retry.py:77-81`
- `safe_rmtree`/`safe_move` pętlą `range(retries + 1)` — przy `retries=3` to 4 próby, backoff 0.5→1.0→2.0 s. `safe_fs.py:46,53,80`
- `safe_resolve` używa `is_relative_to` na już rozwiązanych ścieżkach (po `.resolve()` obu stron) — symlinki są śledzone przed sprawdzeniem. `safe_path.py:33-36`
- Dwa różne `timing.py`: `utils/timing.py` (`elapsed_ms`) i `utils/logger/timing.py` — nie mylić przy imporcie.

## Konwencje

- `secrets.py` przesłania stdlibowy `secrets` — wewnątrz pakietu bezpieczne, ale absolutny `import secrets` po dodaniu `anishift` do ścieżki może trafić w ten plik. `secrets.py:1`
- `_retry.py` i `device.py` używają `except Exception` (device.py przy sondowaniu torch/ort) mimo reguły „nigdy except Exception". `device.py:53,93`
- `NETWORK_RETRY` ma budżet CZASOWY 60 s (`stop_after_delay`), `build_retry` limit LICZBY prób — dwa modele stopu. `_retry.py:61,104-110`
- `_retry` importowany pełną ścieżką `anishift.utils._retry`, nie z `__init__`. `_retry.py:9`
