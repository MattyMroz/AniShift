---
kind: plan
status: draft
baseline: main @ 4365a51 (working tree clean)
created: 2026-10-25
---

# Plan: strażnik utknięć materiału w rezydencie

Specyfikacja: [specification.md](specification.md). Review planu: [reviews/round-1.md](reviews/round-1.md); poprawki z review są już naniesione poniżej.

## Cel

Owner rezydenta wykrywa materiał, który utknął w dowolnym etapie przepływu, i sygnalizuje go właścicielowi istniejącymi kanałami: toast, trwały licznik w pasku stanu panelu, ikona zasobnika, etykieta w wierszu Przetwarzania. Dedup jednokrotny na materiał i stan, reset po zmianie.

## Warunki końcowe

- [ ] Test regresji scenariusza 24.10 zielony (acquisition `complete` bez zlecenia, plik w workspace).
- [ ] Testy jednostkowe trackera i testy integracyjne ownera zielone, w tym brak sygnału przy pauzie Auto i zamykaniu.
- [ ] Testy CLI: etykieta wiersza, licznik w pasku stanu, `problem` ikony zasobnika.
- [ ] Dry run na kopii stanu (proxy na poziomie stanu, Faza 4): dokładnie 2 grupy z incydentu, 0 innych kandydatów.
- [ ] Cztery bramki jakości zielone, bez nowych `noqa` poza uzasadnionymi.
- [ ] `WATCH_STATE_SCHEMA_VERSION` nadal 5; `git diff` nie dotyka `watch_state.py`.

## Nie-cel

Naprawa przyczyny incydentu 24.10, ustawienia progów, wpisy do Historii i `decisions.jsonl`, nawigacja toastu do Przetwarzania, wykrywanie „sukces bez ready/”, alert przy martwym rezydencie (szczegóły: sekcja „Poza zakresem” specyfikacji).

## Authority i baseline

| Źródło | Rola |
|---|---|
| `docs/work/14-stall-watchdog/specification.md` | wymagania, progi, zakazy |
| `anishift/application/automation.py` | owner: pętla, kandydaci, zapis, powiadomienia (czytać po symbolach, plik ma 9372 linie) |
| `anishift/application/control.py` | `NotificationKey`, `AcquisitionState`, `RequestState`, `AutomationPolicy` |
| `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `tests/AGENTS.md` | konwencje i pułapki obszaru |

**Baseline:** `main` @ `4365a51`, drzewo czyste. Znane wcześniejsze failures: do zmierzenia w Fazie 0 (`uv run pytest`), zapisać w raporcie; nie naprawiać.

## Stan aktualny

### Obecne zachowanie

- `_loop` (`automation.py:1135`) buduje terminy z `_settle_at`, `_transfers_at`, `_inspection_at`, `_subscriptions_at`, `_ready_retry_at`; bez terminów śpi na kolejce. Po `Empty` woła `_inspect_changes`, `_refresh_automatic`, `_poll_transfers`, `_poll_subscriptions`, `_poll_ready`; po każdym elemencie kolejki trzy ostatnie `_poll_*` (linie 1151-1157, 1177-1179).
- `_admit_library` (`1329`) liczy `eligible` (komprehensja 1336-1353: `auto_admissible` ∧ `¬_confirmed_absence_completes`, bez relokowanych i usuwanych), a `_start_automatic` (`1406`) wychodzi po cichu przy `origin is None` (1408) i `not plan.can_execute or not plan.tasks` (1411).
- `_publish_event` (`8077`) wywoływany z wątków roboczych; pod `_progress_lock` zapisuje `_run_events`. Zdarzenie nie ma znacznika czasu (`events.py:57`).
- `_notify_group` (`8143`) i `_notify_ready_result` (`8241`): klucz do `notified` w tym samym `_save`, publikacja po udanym zapisie, `_publish_notification` (`8290`) wysyła ramkę `notification` (`terminal=True`).
- `_observe_subscriptions` (`4490`) po każdym `_save` iteruje `notified - previous.notified` i przekazuje do `_notify_subscription`, który ignoruje klucze bez prefiksu `subscription:` (`4567`).
- `_status` (`1710`): `material_counts` (1723-1737), `materials` z `_processing_materials` (1877).
- CLI: `cli/watch.py:351-371` (`broadcast`: `tray.update(problem=...)`, `tray.notify`); `state.py:149` `_STATUS_COUNTS`, `state.py:1488` `_global_status`; `state_processing.py:112` `processing_rows`, `:181` `download_progress`; `state.py:1514` `_processing_entries`.

### Root cause / gap

Przepływ nie ma żadnego sygnału „za długo bez postępu”. Stan „czeka” jest legalny w każdym etapie, więc jego trwanie nigdy nie jest oceniane (dowód: incydent 24.10 i trzy wcześniejsze utknięcia 58 min / 23,9 h / 31,8 h w `history.jsonl`).

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| Kanał toastu | `automation.py:8290` `_publish_notification` | publikacja ramki `notification` | cel `None` otwiera Bibliotekę przy kliknięciu |
| Dedup | `control.py:104` `NotificationKey`, `WatchState.notified` | klucz zapisany razem ze stanem | pole nigdy nie jest sprzątane; strażnik też go nie sprząta (klucze rzadkie, nowy stan = nowy klucz) |
| Zapis | `automation.py:7738` `_save` | atomowy zapis stanu, `False` przy błędzie | zapis stanu ~2 MB; skan zapisuje tylko przy zmianie |
| Termin w pętli | wzorzec `_ready_retry_at` (`5952-5970`) | `_stalls_at` + `_poll_stalls` | tylko wątek ownera |
| Eligibility | `_admit_library` (`1336`) | wydzielić do `_eligible_groups` i użyć w obu miejscach | refaktor ma zachować zachowanie 1:1 |
| `needs_work` | `watch.py:87` | „Auto jeszcze coś produkuje dla grupy” | wymaga `preset` i `recipes` |
| Ledger Auto | `watch.py:107` `WatchLedger` (`_finished`, `_started`) | nowa publiczna metoda `settled(group_id)`: grupa już uruchomiona dla dokładnie bieżącego odcisku w tym procesie | bez niej `needs_work` daje fałszywe alarmy (review R1) |
| Nazwa relokacji | `automation.py:1978` `_relocation_name` | nazwa materiału dla `relocation_stuck` | może zwrócić `None` |
| Nazwa zlecenia | `automation.py:1988` `_processing_name` | nazwa dla `run_silent` | – |
| Transfer bez postępu | `transfers.py:141` `TransferInspector.stalled` | zbiór zatrzymanych haszy, próg z `policy.transfer_stall_s` | tylko w pamięci |
| Sanityzacja | `events.py` `sanitize_event_message` | każdy tekst do toastu i logu | – |
| Pasek stanu | `state.py:149` `_STATUS_COUNTS` | jedna pozycja `("stalled", "utknęło")` | kolejność = kolejność w pasku |
| Ikona zasobnika | `tray.py:181` `update(problem=...)` | `problem` już istnieje | w `cli/watch.py:360`; wyrażenie wydzielić do małej funkcji obok `_busy` (`cli/watch.py:454`), bo `broadcast` jest domknięciem w `run_resident` i nie da się go testować |
| Logger | `from anishift.utils.logger import get_logger` | `logger.warning` strukturalnie | bez nazw, ścieżek, ID |

### Dowody

| Twierdzenie | Dowód | Status |
|---|---|---|
| Dwa materiały z 24.10 są `complete`+`cleaned`, mają `group_id`, nie mają zlecenia ani rekordu `ready_groups` | odczyt `config/watch/state.json` (skrypt `python -I`, tylko odczyt) | verified |
| To jedyne takie przypadki w stanie | ten sam skrypt, pętla po wszystkich `assignments` | verified |
| Przekazania: 77/80 ≤ 19 s; 3/80 utknęło | analiza `history.jsonl` (`download_confirmed` → `order_admitted` po nazwie) | verified |
| Zlecenia: mediana 112 s, p99 644 s, maks 1413 s (n=102); pobrania mediana 94 s, maks 542 s (n=84) | ta sama analiza | verified |
| 8/8 zleceń `failed`/`partial` miało klucz w `notified` | odczyt `state.json` | verified |
| `recheck_interval_s` nieużywane poza serializacją | grep po `anishift/` | verified |
| Klucze bez `subscription:` omija `_notify_subscription` | `automation.py:4567` | verified |
| Zachowanie kontrolek `tray.update` z `problem` | `tray.py:181-190,296-300` | verified |
| Rendering wiersza przetwarzania, którego run nie ma w `_runs`, bez wyjątku | `state.py:1518,1528` indeksuje `self._runs[...]` | verified: ryzyko, patrz Edge cases |
| `auto_admissible` blokuje tylko `FAILED`/`PARTIAL` z tym samym odciskiem, nie `SUCCEEDED` | `control.py:1144-1163` | verified: `eligible ∧ needs_work` samo nie znaczy „Auto powinno wystartować”, ledger (`_finished`) też blokuje |
| `_refresh_automatic` wychodzi bez śladu, gdy `command_receipts` ma wpis `pending`, `_recovering` lub `_inspecting` | `automation.py:1315-1320` | verified: kolejna klasa cichych utknięć, dlatego strażnik ocenia skutek, nie wywołanie |
| `_transfers` istnieje od konstruktora, `stalled` jest puste do pierwszego odczytu | `automation.py:868`, `transfers.py:129` | verified: po restarcie fakty o transferach wracają z opóźnieniem |
| Kandydaci na kopii stanu | Faza 4 (proxy na poziomie stanu) | unknown do wykonania |

## Zakres

### In scope

Nowy czysty moduł `anishift/application/stalls.py`; budowa kandydatów i wpięcie w `automation.py`; jedna mała metoda `WatchLedger.settled` w `watch.py`; flagi w snapshocie; zmiany w 3 miejscach CLI; testy; dwa wpisy w AGENTS.md; `_PURE_MODULES`.

### Out of scope

Patrz „Nie-cel”.

### Forbidden

- Zmiana `watch_state.py`, `WATCH_STATE_SCHEMA_VERSION`, migracji, formatu `state.json`.
- Edycja `pyproject.toml`, dodanie zależności.
- Nowy wątek, proces, plik trwały, sink logów.
- Zmiana semantyki `_admit_library`/`_start_automatic`/`WatchLedger._is_candidate` (tylko wydzielenie `_eligible_groups` i dodanie `WatchLedger.settled`).
- Uruchamianie, zatrzymywanie lub zapytania do żywego rezydenta; odczyt/zapis `config/watch/` poza Fazą 4 (tam wyłącznie kopie do `tmp_path`/scratchpadu).
- Komentarze opisowe i docstringi w testach (hook `check_test_comments.py`).
- Commit na `main`.

### Deferred

Nawigacja toastu do Przetwarzania; wykrywanie „sukces bez ready/”; ustawienia progów.

### Dozwolone decyzje lokalne

Nazwy prywatnych metod, kolejność argumentów, dokładne słownictwo krótkich etykiet (w ramach tabeli poniżej), sposób wyliczenia nazwy materiału z istniejących pól, wybór `digest` (`hashlib.sha256(...).hexdigest()[:12]`, jeśli w repo nie ma gotowego helpera do odcisków; sprawdzić `grep -rn "hexdigest" anishift/application`).

### Zatrzymaj się i wróć po decyzję, gdy

- konieczna jest zmiana schematu stanu lub `watch_state.py`;
- wydzielenie `_eligible_groups` zmienia wynik któregokolwiek istniejącego testu `test_automation.py`/`test_watch.py`;
- dry run (Faza 4) wskaże kandydata inny niż dwa znane;
- zapis klucza do `notified` okazuje się wywoływać skutek uboczny w `_observe_subscriptions` lub `_record_history`;
- potrzebna jest zmiana publicznej fasady `anishift/application/__init__.py`.

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
|---|---|---|---|
| 1 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/references/python.md` | obowiązkowe standardy | full |
| 2 | `.agents/skills/coding/references/comments-docstrings.md`, `testing.md` | komentarze i testy | full |
| 3 | `AGENTS.md`, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `tests/AGENTS.md` | pułapki | full |
| 4 | `specification.md` w tym katalogu | kontrakt | full |
| 5 | `automation.py` | symbole: `_loop`, `_admit_library`, `_start_automatic`, `_status`, `_processing_materials`, `_download_materials`, `_selective_materials`, `_notify_group`, `_publish_notification`, `_save`, `_publish_event`, `_publish_state`, `_ready_waiting`, `_retry_ready`, `_relocation_name`, `_processing_name`, `_working`, `__init__` | symbols |
| 6 | `control.py` 193-250 i 1063-1163, `watch.py` 87-172, `transfers.py` 120-150 | typy i funkcje reuse | section |
| 7 | `cli/watch.py` 340-372, `state.py` 149-160 / 1486-1500 / 1514-1545, `state_processing.py` 112-211 | miejsca zmian CLI | section |
| 8 | `tests/application/test_notification.py` (`_notifications`, `_start`), `test_automation.py` (`_serving`, `_owned`, `_await`, `_request`, `_completed_library`) | harness | symbols |

## Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
|---|---|---|
| `_admit_library` (wydzielenie `_eligible_groups`) | zmiana zachowania Auto | cały `tests/application/test_automation.py`, `test_watch.py`, `test_notification.py` bez zmian w asercjach |
| `WatchState.notified` | nowe klucze `stalled:*` (bez sprzątania) | `test_watch_state.py` (round-trip), `test_subscription_owner.py` (klucze subskrypcji nietknięte) |
| `WatchLedger` | nowa metoda tylko do odczytu | `tests/application/test_watch.py`: istniejące testy bez zmian + test `settled` |
| `_observe_subscriptions` | reakcja na nowe klucze | test: klucz `stalled:*` nie wywołuje toastu subskrypcji |
| Snapshot `_status` | nowe pole `material_counts.stalled`, nowy klucz wiersza `stalled` | `test_interactive_state.py`, `test_panel_frame.py`; konsumenci używają `.get`, więc brak klucza jest bezpieczny |
| Pętla ownera | nowy termin budzi bezczynny rezydent | test: bez kandydatów `_stalls_at is None` po skanie |
| `_publish_event` (gorąca ścieżka, wątki robocze) | dodatkowy zapis pod `_progress_lock` | brak nowego locka; jedno przypisanie słownika |
| Przetwarzanie w panelu | wiersz nieznanego runu | test renderu wiersza `stalled` bez wpisu w `_runs` |
| Ikona zasobnika | stale zapalone `problem` | `problem` zależy od aktualnego licznika `stalled`, który spada do 0, gdy kandydaci znikną z kolejnego skanu |
| Prywatność logów | nowe `logger.warning` | log tylko `kind` i `age_min` |

## Target design

### Odpowiedzialności i ownership

| Element | Odpowiada za | Owner danych/stanu | Nie odpowiada za |
|---|---|---|---|
| `stalls.py` | rodzaje, progi, tracker „od kiedy”, klucze, teksty polskie | pamięć trackera (jeden obiekt w ownerze) | I/O, stan trwały, ocena domenowa „co jest kandydatem” |
| `AutomationOwner` | budowa kandydatów z własnych struktur, skan, zapis `notified`, publikacja, flagi snapshotu | `WatchState.notified` (jedyny trwały ślad), `_stalls`, `_stalls_at`, `_run_activity` | decyzja o naprawie |
| `WatchLedger.settled` | odpowiedź „grupa już uruchomiona dla tego odcisku” | ledger (pamięć procesu) | ocena utknięcia |
| `cli/*` | wyświetlenie `stalled` i licznika | brak | wyliczanie utknięć |

### Source of truth

- autorytatywny stan: dane ownera (acquisitions, requests, library, ready, transfers) + zegar `self._clock()`;
- stan pochodny: `_stalls` (ostatni zbiór aktualnie utkniętych), `StallTracker._seen` (pierwsze obserwacje);
- mutacje: tylko wątek ownera (skan, `_poll_stalls`); `_run_activity` zapisują wątki robocze pod `_progress_lock`, czyta owner pod tym samym lockiem;
- odczyt: snapshot `_status`;
- lifecycle: tracker i `_stalls` żyją w procesie; `notified` przeżywa restart; po restarcie licznik startuje od nowa (kotwica `updated_at` skraca czas dla `transfer_unsettled`), a już ogłoszony klucz nie powtarza toastu.

### Przepływ danych lub sterowania

```text
_publish_state / serve() -> _arm_stalls() ->  _stalls_at = monotonic()+60 s
_loop: deadline -> _poll_stalls() -> _scan_stalls()
  guard: ¬shutting_down ∧ _library ≠ None ∧ ¬_recovering
  candidates = _stall_candidates(now)       # 8 producentów, pamięć + stat dla eligible∧needs_work
  stalls     = tracker.observe(candidates, now)   # tylko przekroczone progi
  ongoing    = stalls bez rodzajów zdarzeniowych       # to widać w panelu, dopóki trwa
  fresh      = stalls, których key ∉ notified
  if fresh: _save(notified ∪ fresh.keys) ; przy False: return (retry w następnym takcie)
  _announce(fresh)        # 1..2 toasty albo 1 zbiorczy (>=3), log
  _stalls = ongoing ; jeśli zmienił się zbiór: _publish_state()
  _stalls_at = monotonic()+60 s jeśli candidates niepuste, inaczej None
_status -> material_counts.stalled = len(_stalls); wiersze z subject w _stalls dostają "stalled": etykieta
cli: pasek stanu "utknęło N", tray problem, etykieta wiersza
```

### Docelowe drzewo

```text
anishift/application/
├── stalls.py                      # NEW  czysty: rodzaje, progi, kandydat, tracker, klucze, teksty
├── watch.py                       # MODIFY  WatchLedger.settled
├── automation.py                  # MODIFY  producenci kandydatów, skan, wpięcie, flagi snapshotu
└── AGENTS.md                      # MODIFY  2 wpisy (pure list + owner/stalls)
anishift/cli/
├── watch.py                       # MODIFY  tray problem z licznika stalled (mała funkcja obok _busy)
└── interactive/
    ├── state.py                   # MODIFY  _STATUS_COUNTS, status wiersza processing
    └── state_processing.py        # MODIFY  processing_rows, download_progress
tests/application/
├── test_stalls.py                 # NEW  unit
├── test_stall_watchdog.py         # NEW  integration (owner)
├── test_architecture.py           # MODIFY  "stalls.py" w _PURE_MODULES
└── test_watch.py                  # MODIFY  test WatchLedger.settled
tests/cli/
├── test_interactive_state.py      # MODIFY  wiersz stalled, pasek stanu
└── test_watch_daemon.py           # MODIFY  test funkcji liczącej tray problem
```

### Mapa plików

| Ścieżka | Operacja | Rola zmiany | Uwagi |
|---|---|---|---|
| `anishift/application/stalls.py` | CREATE | reguły i tracker | importuje tylko `control.NotificationKey`, stdlib |
| `anishift/application/automation.py` | MODIFY | patrz „Kontrakty ownera” | refaktor `_eligible_groups` 1:1 |
| `anishift/application/watch.py` | MODIFY | `WatchLedger.settled(group_id) -> bool` | tylko odczyt `_finished` i `_snapshots` |
| `anishift/application/AGENTS.md` | MODIFY | 2 krótkie wpisy | dopiero po zielonych bramkach |
| `anishift/cli/watch.py` | MODIFY | funkcja `_tray_problem(payload)` obok `_busy`; `problem=` w `broadcast` ją woła | wiersz 360 |
| `anishift/cli/interactive/state.py` | MODIFY | `_STATUS_COUNTS`; `status` wiersza processing | – |
| `anishift/cli/interactive/state_processing.py` | MODIFY | `processing_rows`, `download_progress` | – |
| `tests/application/test_architecture.py` | MODIFY | `_PURE_MODULES` | jedna pozycja |
| `tests/application/test_stalls.py`, `test_stall_watchdog.py`, `test_watch.py`, `tests/cli/test_interactive_state.py`, `tests/cli/test_watch_daemon.py` | CREATE/MODIFY | testy | marker w pliku |
| `anishift/application/watch_state.py`, `control.py`, `history.py`, `pyproject.toml` | READ ONLY | – | Forbidden |

### Publiczne kontrakty

#### `anishift/application/stalls.py`

```text
StallKind (StrEnum), wartości:
  transfer_unsettled | transfer_stalled | client_unreadable | source_not_started
  | source_attention | run_silent | failure_unannounced | relocation_stuck

STALL_AFTER_S: Final[Mapping[StallKind, int]]
  transfer_unsettled 1800 | transfer_stalled 0 | client_unreadable 1800 | source_not_started 600
  | source_attention 3600 | run_silent 1800 | failure_unannounced 300 | relocation_stuck 900

EVENT_KINDS: Final[frozenset[StallKind]] = {failure_unannounced}      # zdarzenie, nie trwały stan: bez licznika i bez flagi wiersza
STALE_AFTER: Final[timedelta] = 7 dni
STALL_SCAN_INTERVAL_S: Final[float] = 60.0
SUMMARY_FROM: Final[int] = 3
STALL_KEY_PREFIX: Final[str] = "stalled:"

StallCandidate(kind, subject: str, signature: str, name: str, since: datetime | None = None)
  .key -> NotificationKey = (subject, signature, f"{STALL_KEY_PREFIX}{kind.value}")
  inwariant: since (jeśli podane) jest aware

Stall(candidate: StallCandidate, since: datetime)          # since = faktyczny początek liczenia
  .key, .kind

StallTracker()
  .observe(candidates: Iterable[StallCandidate], now: datetime) -> tuple[Stall, ...]
      start = candidate.since or pierwsza obserwacja (zapamiętana pod key)
      zwraca kandydatów z now - start >= STALL_AFTER_S[kind]; porządek: start rosnąco, potem key
      zapomina pierwsze obserwacje kluczy, których nie ma w bieżących kandydatach (zmiana sygnatury = zerowanie licznika)
      czas aware; kandydaci z tym samym key scala (pierwszy wygrywa)

recent(moment: datetime, now: datetime) -> bool              # now - moment <= STALE_AFTER
row_label(kind) -> str          # krótka etykieta wiersza, np. "Utknięte · plik nie trafił do przetwarzania"
stall_message(stall: Stall, now: datetime) -> str            # "{nazwa} · {powód} od {N} min"
SUMMARY_TITLE / STALL_TITLE: Final[str]                      # "Materiał utknął"; zbiorczy: f"Utknęło {n} materiałów · sprawdź Przetwarzanie"
```

Etykiety i powody (polskie, jedno źródło):

| Rodzaj | `row_label` | powód w komunikacie |
|---|---|---|
| `transfer_unsettled` | Utknięte · klient nie potwierdził pobrania | klient nie potwierdził pobrania |
| `transfer_stalled` | Utknięte · pobieranie bez postępu | pobieranie nie posuwa się |
| `client_unreadable` | Utknięte · klient pobierania nie odpowiada | klient pobierania nie odpowiada |
| `source_not_started` | Utknięte · plik nie trafił do przetwarzania | plik czeka na przetwarzanie |
| `source_attention` | Utknięte · plik czeka na decyzję | plik czeka na sprawdzenie |
| `run_silent` | Utknięte · zlecenie bez postępu | zlecenie nie robi postępu |
| `failure_unannounced` | Utknięte · błąd bez powiadomienia | zlecenie zakończyło się błędem |
| `relocation_stuck` | Utknięte · wynik nie trafił do ready/ | wynik nie trafił do ready/ |

#### Kontrakty ownera (`automation.py`)

```text
AutomationOwner.__init__(..., stall_scan_interval_s: float = STALL_SCAN_INTERVAL_S)    # wzorzec scan_interval_s
_eligible_groups(workspace, preset) -> tuple[InspectedSourceGroup, ...]                  # wydzielone 1:1 z _admit_library
_stall_candidates(now: datetime) -> tuple[StallCandidate, ...]                           # sklejka producentów
_arm_stalls() / _poll_stalls() / _scan_stalls() / _announce_stalls(fresh, now)
status: material_counts["stalled"]: int ; wiersz materials[i]["stalled"]: str (etykieta) gdy subject ∈ _stalls
```

Producenci (każdy zwraca `StallCandidate`; nazwa przez `sanitize_event_message`; `since` tylko tam, gdzie jest trwała kotwica):

| Rodzaj | subject | signature | since | selekcja |
|---|---|---|---|---|
| `transfer_unsettled` | `operation_id` | `updated_at` | `updated_at` | stan ∈ {ADMITTED, PENDING_SEND, UNCERTAIN}, `_working(item)`, `¬_protected_acquisition(item)`, `recent(updated_at)` |
| `transfer_stalled` | `operation_id` | `updated_at` | – | `_transfers is not None`, `info_hash ∈ _transfers.stalled`, stan ACCEPTED, `_working(item)` |
| `client_unreadable` | `"client"` | `"client"` | – | `_transfers_problem is not None` ∧ istnieje `_working(item)` ∧ stan acquisition nieterminalny |
| `source_not_started` | `group_id` | skrót odcisku `_group_fingerprint(group)` | – | grupa ∈ `_eligible_groups(...)` ∧ `needs_work(group, preset, recipes)` ∧ `¬self._ledger.settled(group_id)`; `preset` jak w `_admit_library` |
| `source_attention` | `group_id` | `reason` wiersza | – | wiersze `_processing_materials()` z `attention is True` |
| `run_silent` | `request_id` | `"{request_id}:{generation}:{ostatnie zdarzenie w sekundach}"`, bez ostatniego członu gdy brak zdarzeń | ostatnie zdarzenie z `_run_activity` albo `None` | `request.state ∈ _ACTIVE_STATES` ∧ (`policy.auto_enabled` ∨ `¬request.automatic`) ∧ `¬_pausing()` |
| `failure_unannounced` | `group_id` | `"{request_id}:{generation}"` | – | ostatnie zlecenie grupy w stanie FAILED/PARTIAL, grupa ∉ `_succeeded_groups(request)`, `recent(request.accepted_at)`, brak klucza `k[0]==group ∧ k[1]==signature` w `notified` (jakiegokolwiek rodzaju, także własnego) |
| `relocation_stuck` | `group_id` | `"move"` | – | `_ready_moves.keys() ∪ _ready_problems.keys()` minus `_ready_inflight` minus (`move.deferred` ∧ `¬_working()`) |

Wiersze dostają flagę, gdy `subject` ∈ aktualnych `_stalls` (bez rodzajów zdarzeniowych) i równa się `row["group_id"]`, `row["acquisition_id"]` lub `row["run_id"]`. Kandydat nie znaczy utknięcie: staje się nim dopiero po progu w trackerze.

#### Model danych / schema

```text
identity: NotificationKey = (subject, signature, "stalled:<kind>")
pola: bez nowych pól w WatchState; nowe klucze w istniejącym zbiorze notified
inwarianty: klucz jest dopisywany raz i nie jest usuwany (jak pozostałe klucze w tym zbiorze); nowy stan to nowa sygnatura, a więc nowy klucz
serializacja: istniejąca (_decode_notification, watch_state.py:1775), trzy teksty
migracja: brak
```

### Algorytm

Skan (`_scan_stalls`), kolejność jest wiążąca:

1. Guard: `_shutting_down`, `_library is None`, `_recovering` → zakończ bez zmian (bez uzbrojenia).
2. `now = self._clock()`; `candidates = _stall_candidates(now)`; `stalls = tracker.observe(candidates, now)`.
3. `ongoing = tuple(s for s in stalls if s.kind not in EVENT_KINDS)`; `fresh = tuple(s for s in stalls if s.key not in notified)`.
4. Jeśli `fresh`: `_save(replace(state, notified=notified | {s.key for s in fresh}))`; przy `False` zostaw `_stalls` bez zmian, uzbrój następny takt i wyjdź.
5. Po udanym zapisie: `_announce_stalls(fresh, now)`: `len(fresh) >= SUMMARY_FROM` → jeden zbiorczy toast, inaczej po jednym; `logger.warning("Material stalled", kind=..., age_min=...)` dla każdego.
6. `_stalls = ongoing`; jeśli zmienił się zbiór subjectów albo było `fresh`: `_publish_state()` (po ustawieniu `_stalls_at`, żeby nie uzbroić drugi raz).
7. `_stalls_at = monotonic() + interval` jeśli `candidates` niepuste, inaczej `None`.

`_arm_stalls` ustawia `_stalls_at` tylko gdy jest `None` i owner się nie zamyka; woła go `serve()` oraz `_publish_state()`.

### Zachowanie UI/UX

- Pasek stanu panelu: `utknęło N` (tuple `("stalled", "utknęło")` w `_STATUS_COUNTS` przed `attention`); `_WORK_COUNTS` bez zmian; podczas pauzy `counted` jest i tak pomijane (`state.py:1496`).
- Wiersz Przetwarzania: gdy `item["stalled"]` ustawione, status wiersza to ta etykieta (dla `stage=="processing"` argument `status` w `render_group`, dla pozostałych pierwsza gałąź `download_progress`). Wiersz zlecenia, którego `run_id` nie ma w `self._runs`, renderuje się ścieżką `render_material_progress`, nigdy przez `self._runs[...]`.
- `processing_rows` dołącza wiersze z `stalled`, których nie ma jeszcze na liście (po tożsamości), na końcu.
- Ikona zasobnika: `problem` także gdy `material_counts.stalled > 0` (funkcja `_tray_problem(payload)`, odporna na brak lub zły typ `material_counts`); tooltip „wymaga uwagi” istnieje (`tray.py:300`).
- Toast: tytuł „Materiał utknął”, treść `stall_message`. Kliknięcie: jak inne toasty bez celu.
- Wygląd oceniany przez człowieka: tak, jeden checkpoint (Faza 3).

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| Scenariusz 24.10: acquisition `complete`, plik w workspace, brak zlecenia, `_start_automatic` nic nie robi | po 10 min jedno powiadomienie, klucz w `notified`, wiersz `stalled`, licznik 1 | integration `test_completed_download_without_request_is_reported_once_after_threshold` |
| Powtórny skan | brak nowego powiadomienia | integration |
| Plik zmieniony (inny odcisk) | nowy klucz, nowe powiadomienie po kolejnych 10 min | integration |
| Zlecenie startuje (ręcznie/Auto) po alarmie | licznik 0, wiersz bez flagi, klucz zostaje | integration |
| To samo utknięcie w tym samym stanie wraca po ustąpieniu | brak nowego toastu (stan niezmieniony); flaga w panelu wraca po progu | integration |
| Grupa przetworzona (`_finished` = bieżący odcisk), brakuje produktu, Auto jej nie restartuje | brak kandydata (`settled`) | integration `test_source_already_processed_for_the_same_fingerprint_is_not_reported` |
| `_refresh_automatic` wychodzi przez wpis `pending` w `command_receipts` | kandydat `source_not_started` mimo to powstaje po progu | integration |
| Pauza Auto | brak kandydatów `source_not_started` i `run_silent` automatycznych | integration |
| Zamykanie (`_shutting_down`) | skan nic nie robi | integration |
| `_save` zwraca `False` | brak toastu, brak zmiany `_stalls`, ponowienie w następnym takcie | integration (zamrożony store jak `_STORE_FROZEN` w `test_automation.py`) |
| Restart ownera z kluczem już w `notified` | brak powtórnego toastu; licznik i flaga wracają po progu | integration |
| Restart, gdy `TransferInspector.stalled` jest jeszcze puste | brak powtórki toastu `transfer_stalled` (klucz nie jest sprzątany) | integration |
| 3 utknięcia w jednym skanie | jeden zbiorczy toast, trzy klucze | integration |
| Stare `uncertain` (> 7 dni) | brak kandydata | unit `recent` + integration |
| `failure_unannounced` po toastcie strażnika | kandydat znika (klucz własny liczy się jako ogłoszenie), klucz zostaje; brak pętli toastów | integration |
| `failure_unannounced`, gdy `_notify_group` zdążył | brak kandydata | integration |
| Kandydat `run_silent`, nowe zdarzenie przed progiem | `since` przesuwa się, brak alarmu | unit + integration |
| Wiersz `stalled` dla zlecenia bez wpisu w `_runs` | render bez wyjątku | cli unit |
| Błąd w producencie (np. `OSError` przy `stat`) | `_scan_stalls` łapie `OSError`/`AniShiftError`/`ValueError`, loguje klasę błędu, uzbraja następny takt; owner żyje | integration |
| `_transfers is None`, `_service.acquisition is None` | producenci transferów zwracają `()` | unit/integration |

### Reuse i zależności

- Użyj: `sanitize_event_message`, `_publish_notification`, `_save`, `_relocation_name`, `_processing_name`, `needs_work`, `_group_fingerprint`, `auto_admissible` przez `_eligible_groups`, `ReadyMove`/`_ready_*`.
- Nie duplikuj: komprehensji `eligible`, logiki nazw, klucza `(group, run:gen, stan)`.
- Nowa zależność: zakazana.

## Plan wykonania

Wykonawca: jeden (Opus), sekwencyjnie, bez worktree, w głównym checkout. Po każdej fazie bramki z sekcji „Strategia dowodu”. Przed pracą: wiadomość do właściciela, że agenci nie ruszają żywego rezydenta (patrz Fazy 4).

### Faza 0: Preflight

**Cel:** czysty baseline i branch.

**Działania:**

1. `git switch -c work/application/01-stall-watchdog` z `main` @ `4365a51` (numer `01`: pierwszy branch scope `application` w tej serii; jeśli istnieje kolizja nazwy, wziąć kolejny numer).
2. Przeczytać kontekst z tabeli.
3. `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run pytest`: zapisać wyniki i znane failures.

**Gate:** baseline opisany w raporcie; brak zmian w drzewie.

### Faza 1: Czysty moduł i testy jednostkowe

**Cel:** `stalls.py` z trackerem i tekstami, w pełni testowany bez ownera.

**Działania:** napisać moduł wg kontraktu; dopisać `"stalls.py"` do `_PURE_MODULES`; napisać `tests/application/test_stalls.py` (`pytestmark = pytest.mark.unit`).

**Testy (nazwy bez komentarzy i docstringów):**

- `test_candidate_below_threshold_is_not_reported`
- `test_candidate_at_threshold_is_reported_with_its_first_observation_as_start`
- `test_durable_since_shortens_the_wait_after_a_restart`
- `test_changed_signature_restarts_the_clock_for_the_same_subject`
- `test_candidate_that_disappears_forgets_its_first_observation`
- `test_every_kind_has_a_threshold_and_a_label`
- `test_recent_rejects_a_moment_older_than_seven_days`
- `test_only_failure_unannounced_is_an_event_kind`
- `test_stall_key_uses_the_stalled_prefix_and_never_collides_with_group_notice_keys`
- `test_stall_message_contains_name_reason_and_minutes_without_paths`
- `test_duplicate_candidate_keys_are_merged`

**Inwarianty:** brak importu `os`, `anishift.config`, `anishift.services`, CLI (`test_architecture.py`).

**Gate:** `uv run pytest tests/application/test_stalls.py tests/application/test_architecture.py` zielone, mypy i ruff zielone.

### Faza 2: Wpięcie w ownera i testy integracyjne

**Cel:** skan w pętli, kandydaci, zapis klucza, toast, flagi snapshotu, regresja 24.10.

**Działania:**

1. Wydzielić `_eligible_groups` z `_admit_library` (1:1) i dodać `WatchLedger.settled` (z testem w `test_watch.py`); przepuścić `tests/application` na tym kroku osobno (gate refaktoru).
2. Dodać pola `_stall_tracker`, `_stalls`, `_stalls_at`, `_run_activity`, parametr `stall_scan_interval_s`.
3. `_publish_event`: `self._run_activity[event.run_id] = self._clock()` w istniejącym `with self._progress_lock`; sprzątanie wpisów zakończonych zleceń w `_scan_stalls`.
4. Dodać `_stalls_at` do krotki terminów w `_loop` i `_poll_stalls()` w obu miejscach (po `_poll_ready`, linie 1156 i 1179); `serve()` wywołuje `_arm_stalls()`, `_publish_state()` wywołuje `_arm_stalls()`.
5. Producenci, `_scan_stalls`, `_announce_stalls`.
6. `_status`: `material_counts["stalled"]`; `_processing_materials`: flaga `stalled` na wierszach (po zbudowaniu listy, bez rekurencji do skanu).
7. Testy `tests/application/test_stall_watchdog.py` (`pytestmark = pytest.mark.integration`). Harness: `_notifications`-podobny kontekst z wstrzykniętym zegarem (`clock=`), `stall_scan_interval_s` małe, skan wywoływany przez `owner._on_owner(owner._scan_stalls)`; uniemożliwienie startu Auto przez `monkeypatch.setattr(AutomationOwner, "_start_automatic", ...)` (symuluje nieznaną przyczynę).

**Testy integracyjne:**

- `test_completed_download_without_request_is_reported_once_after_threshold` (regresja 24.10)
- `test_dropped_source_that_auto_never_starts_is_reported`
- `test_report_is_not_repeated_by_a_second_scan`
- `test_changed_source_is_reported_again`
- `test_started_request_clears_the_stall_and_the_row_flag`
- `test_same_stall_returning_in_the_same_state_is_not_announced_again`
- `test_source_already_processed_for_the_same_fingerprint_is_not_reported`
- `test_pending_command_receipt_that_blocks_admission_does_not_hide_the_stall`
- `test_restarted_owner_with_empty_transfer_stall_set_does_not_repeat_the_notice`
- `test_paused_automation_reports_no_automatic_source_stall`
- `test_shutting_down_owner_reports_nothing`
- `test_failed_state_save_delays_the_toast_and_retries_next_scan`
- `test_three_stalls_in_one_scan_send_one_summary_notice_and_three_keys`
- `test_stall_keys_do_not_trigger_subscription_notices`
- `test_pending_send_acquisition_is_reported_after_thirty_minutes_from_updated_at`
- `test_stale_uncertain_acquisition_is_not_reported`
- `test_stalled_transfer_is_reported_by_its_operation`
- `test_unreadable_client_is_reported_once_for_all_transfers`
- `test_silent_active_request_is_reported_and_fresh_event_postpones_it`
- `test_failed_request_without_notice_is_reported_once_and_not_repeated`
- `test_failed_request_with_notice_is_not_reported`
- `test_stuck_relocation_is_reported`
- `test_idle_owner_disarms_the_scan_when_nothing_is_watched`
- `test_status_counts_stalled_materials_and_flags_their_rows`
- `test_restarted_owner_does_not_repeat_an_already_announced_stall`
- `test_producer_os_error_does_not_stop_the_owner`

**Inwarianty:** `WATCH_STATE_SCHEMA_VERSION == 5`; `watch_state.py` bez diffu; zachowanie `_admit_library` bez zmian.

**Gate:** `uv run pytest tests/application` zielone, w tym wszystkie dotychczasowe testy; ruff, mypy.

### Faza 3: Powierzchnia CLI i checkpoint człowieka

**Cel:** trwały sygnał w panelu i na ikonie.

**Działania:** `_STATUS_COUNTS` (+ `("stalled", "utknęło")`); `processing_rows` i `download_progress` (etykieta `stalled`); `status` dla wiersza processing w `_processing_entries`, z bezpiecznym renderem bez `_runs`; `cli/watch.py`: funkcja `_tray_problem(payload)` (prawda, gdy `transfers_problem`, `subscriptions_problem` lub `material_counts.stalled > 0`) wołana w `broadcast`.

**Testy CLI:**

- `test_processing_row_with_stalled_label_shows_the_label_as_its_status`
- `test_stalled_run_row_without_progress_entry_renders_without_error`
- `test_processing_rows_list_a_stalled_row_once`
- `test_status_line_names_stalled_materials`
- `test_tray_problem_is_set_by_stalled_materials_and_by_existing_problems`
- `test_tray_problem_ignores_a_malformed_material_counts_value`

**Automatyczna kontrola:** `uv run pytest tests/cli`.

**Human checkpoint:**

```text
Uruchom: jednorazowy skrypt w scratchpadzie, który buduje StateController z fixture snapshotu z testów CLI (wiersz pobrania, wiersz zlecenia i wiersz plik-nie-wystartował z flagą stalled) i drukuje wyrenderowane wiersze Przetwarzania oraz linię statusu przy szerokości 80 i 120 kolumn (bez żywego rezydenta)
Zrób: przeczytaj wydruk
Oczekiwany rezultat: wiersz z etykietą "Utknięte · plik nie trafił do przetwarzania", pasek stanu "utknęło 1" (ikona zasobnika jest sprawdzona testem, nie wydrukiem)
Zwróć uwagę na: czytelność etykiety przy wąskim terminalu (obcinanie), brak podwójnych wierszy
Przekaż wynik jako: zrzut ekranu lub opis "OK / uwagi"
```

**Gate:** testy CLI zielone; checkpoint zaliczony (ocenia właściciel; zmiana wyglądu poza etykietą wymaga jego decyzji, pamięć: wygląd panelu zostaje).

### Faza 4: Dry run stanu, dokumentacja, bramki

**Cel:** dowód na prawdziwych danych i domknięcie.

**Działania:**

1. Dry run wyłącznie na kopiach, na poziomie stanu (proxy; pełny owner wymaga mediów i usług, a `bootstrap.production_service()` dotknąłby żywego `config/`, więc go nie używać): skopiować `config/watch/state.json` do katalogu w scratchpadzie, wczytać przez `WatchStateStore(kopia).load()` i skryptem jednorazowym (scratchpad, nie repo) policzyć: (a) `transfer_unsettled` (stan ∈ {ADMITTED, PENDING_SEND, UNCERTAIN}, `recent(updated_at)`), (b) `failure_unannounced` (ostatnie zlecenie grupy FAILED/PARTIAL, `recent(accepted_at)`, bez klucza), (c) „przekazane bez zlecenia” (przypisanie z `group_id`, bez zlecenia i bez `ready_groups`, plik o tej nazwie w listingu `workspace/` zdjętym `os.scandir` tylko po nazwach).
2. Oczekiwane: (a) 0 (22 stare `uncertain` są starsze niż 7 dni), (b) 0 (8/8 ogłoszonych), (c) dokładnie 2: `group-ff01423f74795750` i `group-55419e02a62ce6bd`. Cokolwiek więcej: STOP, eskalacja. Pełne zachowanie ownera dowodzi test regresji z Fazy 2 i obserwacja po wdrożeniu.
3. `anishift/application/AGENTS.md`: dopisać `stalls.py` do listy czystych modułów i jedno zdanie w sekcji „Owner i stan rezydenta” (kandydaci, klucze `stalled:*` bez sprzątania, brak progów w polityce).
4. Pełne bramki.

**Gate:** wynik dry run zgodny; cztery bramki zielone.

## Dodatkowi wykonawcy

| Jednostka | Cel | Kontekst | Write scope | Wynik | Owner integracji |
|---|---|---|---|---|---|
| Wykonawca (Opus) | Fazy 0-4 | ten plan + specyfikacja | pliki z mapy | commity na branchu | orkiestrator |
| Recenzent (Sonnet, świeża instancja, inna rodzina niż autor kodu) | review diffu | diff + specyfikacja + plan, bez raportu autora | tylko odczyt | werdykt wg skilla `review` | orkiestrator |

Zasada krzyżowa (AGENTS.md): autor nie recenzuje własnej pracy. Poprawki po review robi autor, recenzent weryfikuje. Wykonawcy na `astra`/`opus55` zawieszeni zgodnie z notatką o OpenCode; potwierdza orkiestrator.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| Incydent 24.10 byłby zauważony | integration `test_completed_download_without_request_is_reported_once_after_threshold` | odtwarza stan (acquisition `complete` bez zlecenia) i niezależnie od przyczyny wyłącza start Auto |
| Reguły progów i dedup | unit `test_stalls.py` | czysta logika |
| Brak fałszywych alarmów w zdrowym przepływie | dry run stanu (proxy) + testy graniczne (`settled`, pauza, `pending` receipt) + istniejące testy ownera bez zmian + 7 dni obserwacji | dowód na realnych danych tam, gdzie możliwy; reszta to obserwacja po wdrożeniu |
| Refaktor `_eligible_groups` zachowuje Auto | pełne `tests/application` przed i po | istniejące testy kodują kontrakt |
| Bezczynny rezydent pozostaje bezczynny | integration `test_idle_owner_disarms_the_scan_when_nothing_is_watched` | sprawdza `_stalls_at is None` |
| Widoczność w panelu | testy CLI + checkpoint człowieka | wygląd ocenia człowiek |

### Targeted automated checks

```text
uv run pytest tests/application/test_stalls.py tests/application/test_architecture.py
uv run pytest tests/application/test_stall_watchdog.py
uv run pytest tests/application tests/cli
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Ruff i mypy zawsze na `anishift/ tests/`, nigdy na podkatalogu. Przed pushem hook uruchomi też mypy `--platform linux`.

### Regression obligations

- `tests/application/test_automation.py`, `test_notification.py`, `test_watch.py`, `test_subscription_owner.py`, `test_watch_state.py` bez zmiany asercji.
- `tests/cli/test_interactive_state.py`, `test_panel_frame.py`, `test_panel_keys.py` bez zmiany asercji, poza dodanymi.

### Human acceptance

- Co automaty nie potwierdzają: czytelność etykiety i paska, rzeczywisty brak fałszywych alarmów w tygodniu pracy.
- Scenariusz: checkpoint Fazy 3 oraz 7 dni normalnego użycia po wdrożeniu.
- PASS: etykieta czytelna; w 7 dni każdy toast „Materiał utknął” odpowiada prawdziwemu utknięciu (lub fałszywy alarm zgłoszony i skorygowany).

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| Fałszywe alarmy `source_not_started` dla plików legalnie czekających (trwająca publikacja, wydania legacy pobierane do workspace) | toast w ciągu tygodnia | odcisk źródła zeruje licznik przy zmianie; `settled` wycina już przetworzone; w razie potrzeby dołożyć warunek w producencie | więcej niż 1 fałszywy alarm tygodniowo: powrót do właściciela po próg |
| Skan opóźnia pętlę ownera | pomiar czasu `_scan_stalls` w teście z 200 grupami (log `age`/czas) | ograniczyć `stat` do `eligible ∧ needs_work` (już w kontrakcie) | czas skanu > 100 ms przy realnej bibliotece |
| Pętla toastów | testy `failed_request_with_notice...`, `report_is_not_repeated...`, `same_stall_returning...` | klucze nigdy nie są usuwane, kandydat zdarzeniowy znika po własnym kluczu | każdy powtarzający się toast |
| Zapis stanu (2 MB) | liczba `_save` w teście | zapis tylko przy `fresh` | zapis częstszy niż przy nowym utknięciu |
| Wydzielenie `_eligible_groups` zmienia Auto | czerwone istniejące testy | cofnąć do komprehensji 1:1 | każdy czerwony istniejący test |
| `run_silent` fałszywy przy długim kroku bez zdarzeń | dane: maks 23,6 min całego zlecenia | próg 30 min jest powyżej | alarm w prawdziwej długiej pracy: podnieść próg lub dodać zdarzenia postępu |
| Zbieżność z równoległym śledztwem przyczyny (workstream `13-silent-stalls`) | zmiany w `_start_automatic`/`_file_origin` po drugiej stronie | strażnik nie zależy od przyczyny; rebase | konflikt semantyczny w `_admit_library` |

## Lokalna adaptacja

Nazwy prywatnych metod, kolejność i grupowanie argumentów, słownictwo etykiet w ramach tabeli, sposób liczenia nazwy materiału, położenie testu tray w pliku, który już testuje `broadcast`.

## Materialna zmiana

Zmiana schematu stanu, dopisywanie do `history.jsonl`/`decisions.jsonl`, nowy wątek lub proces, zmiana semantyki Auto, progi jako ustawienie użytkownika, zmiana publicznej fasady `anishift.application`.

## Branch i commity

Branch: `work/application/01-stall-watchdog` (wzorzec `work/<scope>/<nn>-<nazwa>`, jak `work/subtitles/02-single-word-break-crash`). Commity wg tematu, scope z `scripts/hooks/check_commit_msg.py` (`application`, `cli`), bez śladów AI:

1. `feat(application): report materials stuck at any stage of the resident flow` (stalls.py, owner, `WatchLedger.settled`, testy, `_PURE_MODULES`)
2. `feat(cli): show stalled materials in the status line, processing rows and tray` (CLI + testy)
3. `docs(application): describe the stall watchdog in the owner notes` (AGENTS.md)

Wypchnięcie i PR dopiero na polecenie właściciela. Wpis w `docs/README.md` (tabela workstreamów) dodaje wykonawca przy PR, po potwierdzeniu numeru workstreamu.

## Definition of Done

- [ ] wymagany rezultat działa, regresja 24.10 zielona;
- [ ] cztery bramki przeszły;
- [ ] zakres i zakazy zachowane (`git diff --stat` bez `watch_state.py`, `pyproject.toml`);
- [ ] dowody mają konkretne wyniki (liczby testów, wynik dry run);
- [ ] checkpoint człowieka wykonany;
- [ ] review krzyżowe: PASS lub PASS WITH FINDINGS bez poważnych;
- [ ] odchylenia i finalny stan przekazane.

## Kontrakt wyniku

```text
status
finalny rezultat
zmienione elementy (pliki)
konkretne dowody (komendy i wyniki, wynik dry run)
human feedback
lokalne odchylenia
materialne odkrycia
znane ograniczenia
stan repo / commity
rekomendowany następny krok
```
