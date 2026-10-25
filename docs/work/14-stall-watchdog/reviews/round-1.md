---
kind: review
status: pass-with-findings
reviewed-state: docs/work/14-stall-watchdog/plan.md i specification.md (szkic 1), kod @ main 4365a51
date: 2026-10-25
---

# Review: plan strażnika utknięć materiału, runda 1

## Zakres

- przedmiot: `plan.md` i `specification.md` w tym katalogu;
- baseline: `main` @ `4365a51`, `config/watch/state.json` i `history.jsonl` z 2026-10-25 (tylko odczyt);
- authority: polecenie zadania, `AGENTS.md` (root, `anishift/`, `application/`, `cli/`, `tests/`), skille `review`, `planning`, `specification`, `simple`;
- ryzyka: fałszywe alarmy, spam, głuchota (alarm nie wychodzi), ruszenie kontraktów Auto, nietestowalność, rozjazd z wzorcami repo;
- poza review: implementacja (jej nie ma), przyczyna incydentu 24.10 (osobny agent).

Autor review nie jest autorem kodu (kodu nie ma); to ten sam wykonawca, który napisał plan, wrócił do niego po wpisaniu wszystkich twierdzeń do tabel dowodów i sprawdził każde twierdzenie o kodzie jeszcze raz w źródle. Niezależny przegląd świeżą instancją innej rodziny pozostaje zalecany przed wykonaniem (patrz „Zalecany następny krok”).

## Werdykt

**Status:** PASS WITH FINDINGS. Po naniesieniu poprawek R1-R6 plan jest decision-complete; zostają decyzje właściciela D1-D7 ze specyfikacji.

**Najważniejszy powód:** szkic miał trzy poważne wady projektowe (fałszywe alarmy z ledgera Auto, powtórki toastów po restarcie przez sprzątanie kluczy, pętla toastów dla niepowodzeń); wszystkie usunięto w planie, a każda ma test, który by ją wykrył.

## Findings

### Krytyczne

Brak.

### Poważne

#### R1. `source_not_started` dawał fałszywe alarmy dla grup już uruchomionych (naprawione w planie)

- miejsce / scenariusz: szkic uznawał za utknięty każdy plik `eligible ∧ needs_work`. `auto_admissible` (`control.py:1144-1163`) blokuje tylko `FAILED`/`PARTIAL` z tym samym odciskiem, a `SUCCEEDED` przepuszcza; to ledger Auto (`WatchLedger._finished`, `watch.py:166-168`) odmawia ponownego startu grupy już uruchomionej dla bieżącego odcisku. Plik po udanym zleceniu z brakującym produktem (np. usunięty ręcznie) byłby więc zgłaszany po 10 min, choć Auto celowo go nie rusza.
- dowód: DIRECT, odczyt `control.py:1144-1163`, `watch.py:154-172`, `automation.py:1329-1364`.
- wpływ: fałszywe toasty, utrata zaufania do sygnału.
- reakcja zastosowana: warunek `¬ledger.settled(group_id)`; nowa publiczna metoda tylko do odczytu `WatchLedger.settled` (plik `watch.py` w mapie plików), testy `test_source_already_processed_for_the_same_fingerprint_is_not_reported` i test jednostkowy `settled` w `test_watch.py`.

#### R2. Sprzątanie kluczy powodowało powtórki toastów po restarcie (naprawione w planie)

- miejsce / scenariusz: szkic usuwał klucz z `notified`, gdy utknięcie „nie jest już przekroczone”. Po restarcie tracker jest pusty, `TransferInspector.stalled` też (`automation.py:868`, `transfers.py:129`), więc pierwszy skan uznałby wszystkie ogłoszone utknięcia za ustąpione, usunął klucze i po kolejnych 10-30 minutach ogłosił je drugi raz.
- dowód: DIRECT, analiza przepływu szkicu względem inicjalizacji w konstruktorze.
- wpływ: złamany wymóg „jedno powiadomienie na materiał i stan”.
- reakcja zastosowana: klucze nie są usuwane (jak reszta `notified`); „reset po zmianie” realizuje sygnatura stanu (odcisk pliku, `updated_at`, `<run>:<gen>:<ostatnie zdarzenie>`). Koszt: powrót tego samego utknięcia w tym samym stanie nie powiadamia ponownie (D6, jawna decyzja właściciela); test `test_restarted_owner_with_empty_transfer_stall_set_does_not_repeat_the_notice`.

#### R3. `failure_unannounced` mógł wejść w pętlę toastów (naprawione w planie)

- miejsce / scenariusz: zlecenie `failed` zostaje `failed` na zawsze. Gdyby własny klucz strażnika nie wyłączał kandydata, a utknięcie było „trwałe”, licznik `stalled` świeciłby bez końca albo toast wracałby co 5 min.
- dowód: DIRECT, `RequestState` nie ma przejścia ze stanu terminalnego bez akcji użytkownika (`control.py:193-202`); 8/8 niepowodzeń w stanie ma już klucz z `_notify_group`.
- reakcja zastosowana: rodzaj zdarzeniowy (`EVENT_KINDS`): kandydat znika, gdy istnieje jakikolwiek klucz `(grupa, "<run>:<gen>")`, także własny; nie wlicza się do licznika ani flagi wiersza; testy `test_failed_request_without_notice_is_reported_once_and_not_repeated`, `test_failed_request_with_notice_is_not_reported`. Widoczność: Historia już pokazuje błędy zleceń.

#### R4. Dry run na „prawdziwym ownerze” był niewykonalny bez dotykania żywego `config/` (naprawione w planie)

- miejsce / scenariusz: szkic Fazy 4 budował ownera z kopii stanu; `bootstrap.production_service()` ustawia ścieżki produkcyjne, a pełny owner wymaga mediów i usług.
- dowód: DIRECT, `anishift/AGENTS.md` („`bootstrap()` jedyny composition root”), zakaz ruszania rezydenta w zadaniu.
- reakcja zastosowana: dry run na poziomie stanu (`WatchStateStore(kopia).load()` + nazwy plików), z oczekiwanym wynikiem 0/0/2 wyliczonym z danych; pełne zachowanie dowodzi test regresji. Checkpoint człowieka zmieniony na wydruk renderu z fixture, bez żywego rezydenta.

#### R5. Funkcji liczącej `problem` ikony nie dało się przetestować (naprawione w planie)

- miejsce / scenariusz: wyrażenie `problem=bool(...)` leży w domknięciu `broadcast` wewnątrz `run_resident` (`cli/watch.py:351-363`); w `tests/` brak testu tego miejsca (grep `enable_tray`, `TrayIcon` poza `platform/test_tray.py`).
- reakcja zastosowana: mała funkcja `_tray_problem(payload)` obok `_busy` (`cli/watch.py:454`, istniejący precedens) i dwa testy, w tym odporność na zły typ `material_counts`.

#### R6. Renderowanie wiersza zlecenia bez wpisu w `_runs` rzuciłoby `KeyError` (naprawione w planie)

- miejsce / scenariusz: `_processing_entries` indeksuje `self._runs[str(item["run_id"])]` dla każdego wiersza `stage == "processing"` (`state.py:1518,1528`). Wiersz zlecenia `failed` (rodzaj `failure_unannounced`) albo zlecenia bez widoku postępu nie ma wpisu w `_runs`.
- reakcja zastosowana: kontrakt UI („render ścieżką `render_material_progress`, nigdy przez `_runs[...]`”), test `test_stalled_run_row_without_progress_entry_renders_without_error`; dodatkowo `failure_unannounced` nie dostaje wiersza (rodzaj zdarzeniowy).

### Mniejsze

#### R7. Opóźnienie sygnału w specyfikacji było niedoszacowane (naprawione)

- było: „próg + 60 s”; faktycznie pierwsza obserwacja następuje w pierwszym skanie po uzbrojeniu, a przekroczenie w następnym: próg + 2 takty. Poprawione na próg + 120 s.

#### R8. Standardy kodu niezapisane w planie (naprawione przez odesłanie)

- stałe `Final` z jednolinijkowym docstringiem pod spodem, nagłówek `# ── Constants`, typowane zmienne lokalne, brak komentarzy opisowych w testach i helperach (`AGENTS.md`, hook `check_test_comments.py`). Plan odsyła do tych dokumentów w tabeli „Kontekst do przeczytania” (pozycje 1-3); wykonawca czyta je przed pracą.

### Sugestie (nie blokują, nie zastosowane)

- S1. `client_unreadable` i `source_attention` mają najsłabsze dane (brak pomiarów; `transfers_problem` już zapala ikonę). Pozostawione, bo zadanie wymaga pokrycia „dowolnego miejsca”; oznaczone w D7 jako pierwsze do wycięcia.
- S2. Kliknięcie toastu otwiera Bibliotekę, nie Przetwarzanie (`automation.py:8307-8321`). Wymaga rozszerzenia nawigacji panelu; odłożone w specyfikacji.
- S3. Rozważyć późniejsze wydzielenie producentów kandydatów z `automation.py` (9,4 tys. linii). Świadomie wbrew: pamięć projektu mówi, że `automation.py` zostaje całością.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
|---|---|---|
| Ogólny strażnik dla każdego etapu | pass | tabela rodzajów w specyfikacji obejmuje: pobranie (3 rodzaje), przekazanie do Auto, plik wymagający decyzji, zlecenie aktywne, zlecenie nieudane, relokację |
| Progi uzasadnione danymi i oznaczone jako decyzje | pass | `history.jsonl` (n=80/102/84), `state.json`; D1-D7 |
| Reuse istniejącego kanału | pass | `_publish_notification`, `notified`, `material_counts`, `tray.update(problem)`, brak nowego pliku/schematu |
| Wpięcie w pętlę, bezczynny rezydent bez pracy | pass | termin `_stalls_at` jak `_ready_retry_at`; test rozbrojenia |
| `policy.recheck_interval_s` | pass | ustalono: nieużywane poza serializacją, odrzucone jako takt |
| Jedno powiadomienie na materiał i stan, reset po zmianie | pass z ograniczeniem | sygnatura stanu; D6 |
| Test regresji scenariusza 24.10 | pass | `test_completed_download_without_request_is_reported_once_after_threshold` |
| Branch i commity zgodne z hookiem | pass | scope `application`, `cli`; wzorzec `work/<scope>/<nn>-<nazwa>` |
| Testy z markerami, bez komentarzy i docstringów | pass | `pytestmark` unit/integration; nazwy opisują scenariusz |
| Zero zmian kodu, configów, `config/watch/`, `workspace/`, bez gita i subagentów | pass | zapisano wyłącznie w `docs/work/14-stall-watchdog/` |

## Regresje i integracja

- Zmiana semantyki Auto: plan zabrania (tylko wydzielenie `_eligible_groups` 1:1 i `WatchLedger.settled` jako odczyt); bramka: pełne `tests/application` po refaktorze.
- Konflikt z równoległym workstreamem śledzącym przyczynę (`docs/work/13-silent-stalls/`, pusty katalog w chwili review): strażnik nie zależy od przyczyny; ryzyko semantyczne tylko w `_admit_library` i `_start_automatic`, gdzie plan niczego nie zmienia poza wydzieleniem.

## Wykonane kontrole

```text
odczyt źródeł: automation.py (_loop, _admit_library, _start_automatic, _status, _processing_materials,
  _download_materials, _selective_materials, _notify_group, _notify_ready_result, _publish_notification,
  _save, _publish_event, _prepare_ready, _retry_ready, _schedule_transfers), control.py, watch.py,
  history.py, transfers.py, tray.py, cli/watch.py, state.py, state_processing.py, test_notification.py
analiza state.json (python -I, odczyt): acquisitions 131, requests 162, notified 235; 2 przypadki "przekazane bez zlecenia";
  8/8 failed|partial z kluczem; 22 stare uncertain (> 7 dni)
analiza history.jsonl: handoff n=80 mediana 8.4 s, p90 11.6 s, 77 <= 19.3 s, 3 utknięcia (3507 s, 85942 s, 114577 s);
  zlecenia n=102 mediana 112 s, p99 644 s, maks 1413 s; pobrania n=84 mediana 94 s, maks 542 s
grep recheck_interval_s po anishift/: tylko control.py:245 i serializacja w watch_state.py
```

## Niewykonane lub nierozstrzygające kontrole

- Uruchomienie kodu: celowo brak (zadanie: tylko dokumenty).
- Zachowanie `_ledger.settled` po restarcie rezydenta (ledger pusty): nie testowane, zachowanie Auto bez zmian; strażnik wtedy widzi grupy jako niezakończone, co jest zgodne z tym, że Auto też je ponownie rozważy.
- Czy `eligible ∧ needs_work ∧ ¬settled` nie produkuje szumu na dużej bibliotece: dowodzi dopiero obserwacja po wdrożeniu (7 dni).

## Wymagana ocena człowieka

```text
Uruchom: czytaj specification.md, sekcje "Definicja utknięcia" i "Nierozstrzygnięte"
Zrób: potwierdź lub skoryguj progi D1-D3, okno 7 dni (D2), próg zbiorczego toastu (D3), rozstrzygnij D4-D7
Oczekiwany wynik: lista decyzji "tak/nie/zmiana"
Zwróć uwagę na: D6 (brak powtórnego toastu dla tego samego stanu) i D7 (rodzaje bez danych)
```

## Ograniczenia review

- Autor planu i autor review to ta sama instancja; niezależność ograniczona (kod i dane sprawdzone ponownie w źródle, ale bez świeżego kontekstu).
- Numery linii pochodzą z `main` @ `4365a51`; wykonawca dopasowuje je lokalnie po symbolach.

## Zalecany następny krok

Właściciel rozstrzyga D1-D7; potem świeża instancja Sonnet (inna rodzina niż przyszły autor kodu) robi krótki review planu z kodem w ręku, bez raportu autora, i dopiero wtedy start Fazy 0.
