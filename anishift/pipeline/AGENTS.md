# pipeline

Strumieniowa orkiestracja ekstrakcja → tłumaczenie → TTS → audio, obsługa TXT,
izolacja błędów per plik i recovery całego providera.

## Pliki

- `runner.py` — orkiestracja, izolacja błędów per plik, pula wątków
- `narration.py` — jedyny adapter stanu napisów do neutralnych requestów TTS
- `llm_queue.py` — współbieżna kolejka plików i circuit providerów LLM
- `tts_queue.py` — strumień gotowych narration batches przez TTS i audio
- `tts_runtime.py` — composition per-run dla TTS/audio i lifecycle workera
- `recovery.py` — wspólny kontrakt `retry/settings/finish`
- `types.py` — wyniki plików, raport i protokoły pipeline

## Pułapki

- Trzy tryby ekstrakcji wykluczają się w ustalonej kolejności: `interaction` → sekwencyjny; brak `interaction` + brak `progress_factory` → sekwencyjny; progress → pula wątków. Dla LLM callback od razu przekazuje każdy gotowy split do strumieniowej kolejki. `runner.py`
- `_MkvState.outcome` jest mutowany przez worker tłumaczenia. Dla LLM worker-local runtime/client nie jest współdzielony; wspólny jest tylko per-run `SharedProviderState`. `runner.py`, `llm_runtime.py`, `llm_queue.py`
- `discover_inputs` cicho pomija każdy plik z infiksem `.displayed` — by nie wciągnąć własnych produktów pipeline'u jako wejść. `runner.py`
- `_extract_mkv` na starcie kasuje `workspace/tmp/<stem>` przez `safe_rmtree` — ponowny run niszczy poprzedni katalog tymczasowy bez ostrzeżenia. `runner.py:273-275`
- Anulowanie (Ctrl+C) jest kooperatywne przez współdzielony `threading.Event`. Dla LLM główny executor nie czeka na blokujący request SDK: pierwszy `KeyboardInterrupt` ustawia `cancel`, zamyka input i wraca, a worker odrzuca ewentualny sukces zakończony po anulowaniu. `runner.py`, `services/llm/_retry.py`
- `_should_translate` pomija pliki już polskie (`already_polish`) i splity bez `spoken_lines`/`displayed_events`; polskie źródła omijają API, ale writer nadal tworzy ich końcowe produkty. `runner.py`
- TTS jest publikowane dokładnie raz, gdy polski spoken jest gotowy: bezpośrednio
  po ekstrakcji dla polskiego źródła albo po udanym tłumaczeniu. `runner.py`,
  `narration.py`
- Trwały błąd providera TTS pauzuje nowe pliki, pozwala skończyć aktywnym, a
  niewysłane oznacza `not_processed`. Recovery uruchamia failed-first, potem
  pending, oba `natsorted`. `tts_queue.py`, `runner.py`
- Nie usuwaj gotowych tłumaczeń ani zwalidowanych klipów po błędzie TTS/audio.
  Resume ma umożliwić dalszy run. `runner.py`, `tts_runtime.py`
- Rebuild po `/settings` może sam zgłosić błąd konfiguracji. Zachowaj poprzednie
  outcomes i ponownie pytaj `retry/settings/finish`; nie mutuj kolejki przed
  udaną konstrukcją runtime/worker. `recovery.py`, `llm_queue.py`, `runner.py`

## Konwencje

- Silniki tłumaczeń importowane leniwie WEWNĄTRZ funkcji (`noqa: PLC0415`, „keep engines off import path"). `runner.py:379,388,405,418,426`
- Liczba workerów skaluje się pierwiastkiem z rdzeni + 2 (`_WORKER_IO_HEADROOM`), NIE liniowo — ekstrakcja jest dyskowo-bound. `runner.py:244-253`
- Końcowy kontrakt napisów to `.pl.<kind>` (pełny), `.spoken.pl.<kind>` (spoken-only) i `.displayed.pl.<kind>` (displayed-only wraz z rysunkami). Surowy `.displayed.<kind>` nie jest produktem pipeline'u. `runner.py`
- `_extract_concurrently` odpytuje future'y w pętli z timeoutem `_WAIT_POLL_SECONDS` (0.2 s) zamiast blokującego `wait()` — by Ctrl+C był responsywny. `runner.py:186-187`
- LLM scheduler zaczyna z jednym slotem, rośnie `1 → 2 → max 4`, zatrzymuje niewysłane pliki po trwałym typed failure i wznawia failed-first po akcji `retry` albo `settings`. `llm_queue.py`
- LLM scheduler zgłasza przez callback przejścia `translating` oraz każdy stan terminalny; callback jest wywoływany przez wątek koordynatora, nie workerów. `llm_queue.py`
- TTS queue jest producer-consumer: ekstrakcja/tłumaczenie może publikować kolejne
  pliki, gdy wcześniejsze są już syntetyzowane. Nie zamieniaj jej na batch
  uruchamiany po zakończeniu całego tłumaczenia. `tts_queue.py`, `runner.py`
- `ready_first` uruchamia pierwszy gotowy odcinek, a oczekujące szereguje
  `natsorted`; `strict_natural` czeka na rozstrzygnięcie wcześniejszej pozycji
  przez `put()` albo `skip()`. Nie usuwaj tych sygnałów z inputów kolejek.
  `llm_queue.py`, `tts_queue.py`, `runner.py`
- `ready_first` trzyma priorytet odcinka do chwili, gdy liczba niezatwierdzonych
  klipów spadnie do limitu providera; wtedy kolejny odcinek może wypełniać
  zwalniane sloty, a gotowe retry nadal mają pierwszeństwo. `strict_natural` nie
  zwalnia focusu przed końcem TTS. Audio pozostaje równoległe do kolejnego TTS;
  nie ustawiaj `max_active_batches=1`. `tts_runtime.py`, `services/tts/scheduler.py`
- Callbacki TTS/audio są nieposiadającymi observerami. Wyjątek UI nie może
  przerwać domeny ani recovery. `tts_runtime.py`, `runner.py`
- Wyjątki łapane precyzyjnie: `AniShiftError` z rozróżnieniem `CANCELLED` vs reszta, osobno `OSError` → `IO_ERROR`; brak `except Exception`. `runner.py:330-341`
- `batch_size == 0` oznacza domyślną wartość silnika i jest podmieniane na `DEFAULT_BATCH_SIZE`. `runner.py:393`
