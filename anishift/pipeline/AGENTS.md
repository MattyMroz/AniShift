# pipeline

Orkiestracja etapów dwufazowa (ekstrakcja → tłumaczenie) plus obsługa TXT, izolacja błędów per plik, paski postępu.

## Pliki

- `runner.py` — orkiestracja, izolacja błędów per plik, pula wątków
- `types.py` — value objects (`FileOutcome`, `FileFailure`, `PipelineReport`, `TranslationSettings`) + protokoły callbacków

## Pułapki

- Trzy tryby ekstrakcji wykluczają się w ustalonej kolejności: `interaction` → sekwencyjny; brak `interaction` + brak `progress_factory` → sekwencyjny; progress → pula wątków. Dla LLM callback od razu przekazuje każdy gotowy split do strumieniowej kolejki. `runner.py`
- `_MkvState.outcome` jest mutowany przez worker tłumaczenia. Dla LLM worker-local runtime/client nie jest współdzielony; wspólny jest tylko per-run `SharedProviderState`. `runner.py`, `llm_runtime.py`, `llm_queue.py`
- `discover_inputs` cicho pomija każdy plik z infiksem `.displayed` — by nie wciągnąć własnych produktów pipeline'u jako wejść. `runner.py`
- `_extract_mkv` na starcie kasuje `workspace/tmp/<stem>` przez `safe_rmtree` — ponowny run niszczy poprzedni katalog tymczasowy bez ostrzeżenia. `runner.py:273-275`
- Anulowanie (Ctrl+C) kooperatywne przez współdzielony `threading.Event`; `KeyboardInterrupt` ustawia `cancel`, czeka na WSZYSTKIE future'y i dopiero re-raise'uje. `runner.py:186-191`
- `_should_translate` pomija pliki już polskie (`already_polish`) i splity bez `spoken_lines`/`displayed_events`; polskie źródła omijają API, ale writer nadal tworzy ich końcowe produkty. `runner.py`

## Konwencje

- Silniki tłumaczeń importowane leniwie WEWNĄTRZ funkcji (`noqa: PLC0415`, „keep engines off import path"). `runner.py:379,388,405,418,426`
- Liczba workerów skaluje się pierwiastkiem z rdzeni + 2 (`_WORKER_IO_HEADROOM`), NIE liniowo — ekstrakcja jest dyskowo-bound. `runner.py:244-253`
- Końcowy kontrakt napisów to `.pl.<kind>` (pełny), `.spoken.pl.<kind>` (spoken-only) i `.displayed.pl.<kind>` (displayed-only wraz z rysunkami). Surowy `.displayed.<kind>` nie jest produktem pipeline'u. `runner.py`
- `_extract_concurrently` odpytuje future'y w pętli z timeoutem `_WAIT_POLL_SECONDS` (0.2 s) zamiast blokującego `wait()` — by Ctrl+C był responsywny. `runner.py:186-187`
- LLM scheduler zaczyna z jednym slotem, rośnie `1 → 2 → max 4`, zatrzymuje niewysłane pliki po trwałym typed failure i wznawia failed-first po akcji `settings`. `llm_queue.py`
- LLM scheduler zgłasza przez callback przejścia `translating` oraz każdy stan terminalny; callback jest wywoływany przez wątek koordynatora, nie workerów. `llm_queue.py`
- Wyjątki łapane precyzyjnie: `AniShiftError` z rozróżnieniem `CANCELLED` vs reszta, osobno `OSError` → `IO_ERROR`; brak `except Exception`. `runner.py:330-341`
- `batch_size == 0` oznacza domyślną wartość silnika i jest podmieniane na `DEFAULT_BATCH_SIZE`. `runner.py:393`
