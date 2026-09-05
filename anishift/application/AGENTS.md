# application

Czysta warstwa produktu i use case'ów współdzielona przez CLI i testy.

## Kierunek zależności

- `artifacts.py`, `intents.py`, `planning.py`, `selection.py` i `planner.py` nie importują I/O,
  `anishift.services`, `anishift.config` ani CLI.
- Kontrolowane I/O należy do `discovery.py`, `inspection.py`, `publisher.py`,
  `sessions.py`, handlerów oraz fasady `service.py`; koordynator publikuje zwalidowany
  staging przez `scheduler_runtime.py`. Decyzje produktowe pozostają w plannerze.
- CLI używa publicznej fasady `anishift.application`; nie importuje
  wewnętrznych helperów I/O ani schedulera.
- Oczekiwany konflikt wejścia jest `PlanProblem`. `PlanningError` oznacza uszkodzony
  kontrakt albo graf, nie zwykłą decyzję użytkownika.

## Inwarianty

- ID grup i odkrytych artefaktów powstają wyłącznie z normalizowanych ścieżek
  względnych. Ręcznie zarejestrowany plik spoza workspace używa znormalizowanej
  ścieżki zewnętrznej wyłącznie jako wejścia stabilnego skrótu; nie używaj `hash()`
  ani losowego UUID.
- `SOURCE` ma `planned_destination == path`, `INTERMEDIATE` nie ma trwałego celu,
  a `DURABLE` otrzymuje `planned_destination` przed wykonaniem.
- `AUTO` nie zawiera ręcznych artifact/track ID. `MANUAL` może wskazać artefakt albo
  embedded track danego rodzaju, nigdy oba jednocześnie.
- `ExecutionPlan.tasks` musi wejść już w porządku zwróconym przez
  `stable_topological_order()`. Porządek jest stabilny względem naturalnie ułożonego
  wejścia, więc niezależne taski grupy `2` nie mogą przeskoczyć za grupę `10` przez
  hash w `task_id`. Każdy produkowany artefakt ma jednego producenta.
- Auto wymagające osadzonego audio i napisów z jednego MKV planuje jeden
  `EXTRACT_TRACKS`. Produkcyjny handler uruchamia jeden istniejący
  `mkvextract --gui-mode`, a każde prawdziwe `#GUI#progress N%` przekazuje bez
  uśredniania. Pula ekstrakcji ma rozmiar
  `min(file_count, round(sqrt(cpu_count)) + 2)`.
- LLM wykonuje gotowe pliki równolegle dokładnie do `llm_max_concurrency` (1-16);
  scheduler nie przycina tej liczby drugi raz. TTS
  syntetyzuje jeden plik naraz, ale `tts_request_concurrency` aktywnego profilu nie
  jest zmniejszane; audio może pracować równolegle z następną syntezą.
- Wykonywalny plan nie zawiera `MISSING` bez producenta. Task produkuje wyłącznie
  `MISSING` o lifetime `INTERMEDIATE` albo `DURABLE`, a parametry odpowiadają jego
  `TaskKind`.
- Worker otrzymuje w `ArtifactSnapshot` gotowe wejścia i niezmienne deskryptory
  planowanych wyjść, po czym zwraca `TaskResult`; mutable store pozostaje prywatny
  dla schedulera.
- `GraphScheduler.run()` anuluje własny token powiązany z tokenem wywołującego
  przed czekaniem na executory, również przy Ctrl+C i błędzie koordynatora.
- Blokada docelowego produktu odkłada ponowienie atomowego `replace` w koordynatorze.
  Nie usypiaj całej koordynacji na czas retry: niezależne grupy nadal przekazują
  postęp i kończą pracę, a każda próba ponownie sprawdza cancellation i generację sesji.
  `scheduler.py`, `scheduler_runtime.py`
- `WorkspaceInspector.inspect()` probuje grupy równolegle (`_MAX_INSPECTION_WORKERS`),
  bo każda grupa to osobny `mkvmerge`. Kolejność grup i ostrzeżeń pozostaje
  kolejnością discovery — nie zbieraj wyników w kolejności ukończenia.
  `inspection.py`
- `AppService.discover()` jest serializowane (`_discover_lock`) i reużywa poprzednią
  inspekcję, gdy odcisk workspace (ścieżka + rozmiar + mtime każdego odkrytego pliku)
  jest identyczny. Dzięki temu wielokrotne `discover()` w jednej sesji nie powtarza
  probowania, a zmiana pliku wymusza pełną inspekcję. Nie omijaj tego przez własny
  cache w UI. `service.py`
- Produkcyjne `discover()` przygotowuje brakujące narzędzia przed probe, przez
  callback z `bootstrap.py` i istniejący instalator. MKV wymaga MKVToolNix i FFmpeg,
  MP4/audio — FFmpeg; sam TXT lub napisy nie uruchamiają instalacji. Przygotowanie
  jest ciche dla terminala; konstruktory i renderer nie pobierają plików.
  Oczekiwanie na `_discover_lock` sprawdza anulowanie, również podczas Home prewarm.

## Testy

```bash
uv run pytest tests/application -v
```
