# pipeline

Orkiestracja etapów dwufazowa (ekstrakcja → tłumaczenie) plus obsługa TXT, izolacja błędów per plik, paski postępu.

## Pliki

- `runner.py` — orkiestracja, izolacja błędów per plik, pula wątków
- `types.py` — value objects (`FileOutcome`, `FileFailure`, `PipelineReport`, `TranslationSettings`) + protokoły callbacków

## Pułapki

- Trzy tryby ekstrakcji wykluczają się w ustalonej kolejności: `interaction` → sekwencyjny bez pasków; brak `interaction` + brak `progress_factory` → też sekwencyjny; brak `interaction` + `progress_factory` → pula wątków z paskami. `interaction` zawsze wygrywa. `runner.py:152-162`
- Fazy dzielą jeden `_MkvState`; faza tłumaczenia mutuje `state.outcome` w miejscu — outcome z ekstrakcji NIE jest finalny dopóki nie przejdzie faza translate. `runner.py:235-241,88-99`
- `discover_inputs` cicho pomija każdy plik z infiksem `.displayed` — by nie wciągnąć własnych produktów pipeline'u jako wejść. `runner.py:82`
- `_extract_mkv` na starcie kasuje `workspace/tmp/<stem>` przez `safe_rmtree` — ponowny run niszczy poprzedni katalog tymczasowy bez ostrzeżenia. `runner.py:273-275`
- Anulowanie (Ctrl+C) kooperatywne przez współdzielony `threading.Event`; `KeyboardInterrupt` ustawia `cancel`, czeka na WSZYSTKIE future'y i dopiero re-raise'uje. `runner.py:186-191`
- `_should_translate` pomija pliki już polskie (`already_polish`) i splity bez `spoken_lines`/`displayed_events` — kończą z `split=None` i nie wejdą do fazy translate. `runner.py:356-360`

## Konwencje

- Silniki tłumaczeń importowane leniwie WEWNĄTRZ funkcji (`noqa: PLC0415`, „keep engines off import path"). `runner.py:379,388,405,418,426`
- Liczba workerów skaluje się pierwiastkiem z rdzeni + 2 (`_WORKER_IO_HEADROOM`), NIE liniowo — ekstrakcja jest dyskowo-bound. `runner.py:244-253`
- Plik `.pl.<kind>` to WHOLE-FILE: wszystkie eventy zachowane, tylko tekst zamieniony; strumień TTS (`result.spoken`) zostaje niepodzielony. `runner.py:373-383`
- `_extract_concurrently` odpytuje future'y w pętli z timeoutem `_WAIT_POLL_SECONDS` (0.2 s) zamiast blokującego `wait()` — by Ctrl+C był responsywny. `runner.py:186-187`
- Wyjątki łapane precyzyjnie: `AniShiftError` z rozróżnieniem `CANCELLED` vs reszta, osobno `OSError` → `IO_ERROR`; brak `except Exception`. `runner.py:330-341`
- `batch_size == 0` oznacza domyślną wartość silnika i jest podmieniane na `DEFAULT_BATCH_SIZE`. `runner.py:393`
