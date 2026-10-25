---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: strażnik utknięć materiału

## Cel

Każdy materiał, który utknął w dowolnym miejscu przepływu rezydenta (pobranie → przekazanie do Auto → zlecenie → przeniesienie do `ready/`), ma po rozsądnym, ustalonym czasie wywołać widoczny sygnał dla właściciela. Strażnik jest niezależny od przyczyny: patrzy na skutek („nic się nie dzieje, a powinno”), nie na konkretny błąd.

## Użytkownik i intencja

Właściciel (jeden użytkownik lokalny, Windows) nie ogląda panelu na bieżąco. Chce dowiedzieć się o utknięciu w ciągu kilkudziesięciu minut, nie po dwóch dniach, i nie chce być zalewany powtórzeniami.

## Stan wyjściowy

Fakty z kodu i danych (baseline `main` @ `4365a51`, stan `config/watch/state.json` z 2026-10-25, tylko odczyt).

- Incydent z 24.10: acquisition `6b04ba6aa3563210` (Magical Explorer S01E05) i `d0b6dd57500f884f` (Kashita Maryoku S01E04) są `complete`, `cleaned`, z `assignment.group_id`, a w `state.requests` nie ma żadnego zlecenia dla ich grup (`group-ff01423f74795750`, `group-55419e02a62ce6bd`). Pliki leżą w `workspace/`. Żaden klucz w `state.notified` ich nie dotyczy. To jedyne dwa takie przypadki w całym stanie (wszystkie inne grupy z `assignment.group_id` mają zlecenie lub rekord `ready_groups`).
- Ta sama klasa wystąpiła wcześniej i zniknęła dopiero po restarcie rezydenta. `config/watch/history.jsonl`: odstęp `download_confirmed` → `order_admitted` grupy wynosi mediana 8 s, p90 12 s, 77 z 80 pomiarów ≤ 19 s; trzy pozostałe to 3507 s, 85942 s (23,9 h) i 114577 s (31,8 h), wszystkie zakończone o 2026-10-23 17:04.
- Przekazanie do Auto: `AutomationOwner._admit_library` (`anishift/application/automation.py:1329`) wybiera `eligible` grupy, a `_start_automatic` (`automation.py:1406`) wychodzi po cichu przy `origin is None` (1408) i przy `not plan.can_execute or not plan.tasks` (1411), bez logu i bez śladu w stanie.
- Panel pokazuje taki materiał jako „Przygotowanie” bez końca: `_selective_materials` (`automation.py:2115`) emituje wiersz `stage="waiting"`, `reason="preparing"`, a `download_progress` (`anishift/cli/interactive/state_processing.py:181`) nie ma gałęzi „za długo”. Licznik `material_counts.waiting` (`automation.py:1731`) go wlicza jako zwykłe oczekiwanie.
- Istniejące powiadomienia pokrywają tylko część przepływu:
  - `_notify_group` (`automation.py:8143`): toast „Materiał wymaga uwagi” przy niepowodzeniu grupy w zleceniu; klucz `(group, "<run>:<gen>", "<stan>")` w `WatchState.notified`. Dane: 8 z 8 ostatnich zleceń `failed`/`partial` ma taki klucz.
  - `_notify_ready_result` (`automation.py:8241`): toast „Gotowy materiał”.
  - Subskrypcje: `_escalations`/`_escalate` (`automation.py:4597`, `4584`) dla celów `DUE`/wyczerpanych/„od 7 dni”.
  - Pasek stanu i ikona zasobnika: `transfers_problem`/`subscriptions_problem` (`anishift/cli/watch.py:360`).
  - Nic nie powiadamia o: acquisition w `PENDING_SEND`/`UNCERTAIN`/`ADMITTED`, zatrzymanym transferze nieobjętym subskrypcją (`TransferInspector.stalled`, `automation.py:1798` tylko jako flaga), pliku w workspace bez zlecenia, zleceniu aktywnym bez postępu, przeniesieniu do `ready/` zablokowanym (`_ready_problems`, `automation.py:7294`).
- Toast to chwilowy balon (`anishift/platform/tray.py:192`, znika po timeoucie); kto jest nieobecny, go nie zobaczy. Trwały sygnał musi istnieć także w panelu i na ikonie.
- Pętla ownera śpi na kolejce bez timeoutu, gdy nie ma terminów (`automation.py:1135-1150`, `anishift/application/AGENTS.md`: „bezczynny rezydent nie pracuje”).
- `AutomationPolicy.recheck_interval_s` (`control.py:245`, 3600 s) nie jest czytane przez żadną logikę poza serializacją (`watch_state.py:281,765,1430`); dotyczy dawnego wyszukiwania i nie nadaje się na takt strażnika.

## Ustalenia

- Strażnik mierzy skutek: materiał jest utknięty, gdy warunek „powinno iść dalej, a nie idzie” trwa nieprzerwanie dłużej niż próg danego etapu. Skutek: wykrywa także przyczyny, których dziś nikt nie zna.
- Kanały sygnału są istniejące, nowego kanału nie ma: toast przez `_publish_notification` (`automation.py:8290`), trwała deduplikacja przez `WatchState.notified` (`control.py:104,961`), widoczność w panelu przez snapshot `_status`/`material_counts` i wiersze Przetwarzania, ikona zasobnika przez `problem`. Skutek: brak zmiany schematu stanu (`WATCH_STATE_SCHEMA_VERSION` zostaje 5), brak nowego pliku.
- Progi są stałymi modułu, nie ustawieniem w `AutomationPolicy`. Skutek: zmiana progu nie wymaga migracji stanu (schemat jest wersjonowany, `anishift/application/AGENTS.md`, „Owner i stan rezydenta”).
- Stan „od kiedy trwa” strażnika jest w pamięci ownera. Skutek: po restarcie rezydenta liczenie zaczyna się od nowa, z wyjątkiem etapów z trwałą kotwicą czasu (`acquisition.updated_at`), a powiadomienie nie powtarza się, bo klucz jest w `notified`.

## Definicja utknięcia (etapy i progi)

Każdy wiersz to jeden rodzaj utknięcia (`StallKind`). „Warunek” to wszystko, co musi być prawdą jednocześnie. Warunki wykluczające wspólne dla wszystkich: owner się zamyka (`_shutting_down`), biblioteka niewczytana (`_library is None`) albo trwa odzyskiwanie (`_recovering`), kotwica trwała starsza niż 7 dni (opuszczony materiał, który widać w panelu, ale nie alarmuje).

| Etap | Rodzaj | Warunek | Próg | Kotwica | Dowód w danych |
|---|---|---|---|---|---|
| acquisition `admitted`/`pending_send`/`uncertain` | `transfer_unsettled` | `_working(item)`, stan nie przeszedł dalej, brak ochrony (`_protected_acquisition`) | 30 min | `acquisition.updated_at` | pobrania trwają mediana 94 s, maks 542 s (n=84); kontrola wysyłki co 10 s, 5 prób (`automation.py:289,469`) |
| acquisition `accepted`, transfer bez postępu | `transfer_stalled` | `info_hash` w `TransferInspector.stalled` (`transfers.py:141`) | 0 min dodatkowo; próg daje `policy.transfer_stall_s` = 10 min (`control.py:137`) | pierwsza obserwacja | istniejąca polityka „needs attention” |
| acquisition `accepted`, klient nieczytelny | `client_unreadable` | `_transfers_problem` ustawiony i istnieje pracujące acquisition w stanie nieterminalnym | 30 min | pierwsza obserwacja | `automation.py:1130,6899,7084` |
| przekazanie do Auto (acquisition `complete` lub plik wrzucony ręcznie) | `source_not_started` | grupa jest `eligible` w `_admit_library`, `needs_work(...)` (`watch.py:87`), nie jest „już uruchomiona dla tego odcisku” w ledgerze Auto (`WatchLedger._finished`, `watch.py:107`) i nie ma aktywnego zlecenia; ten sam odcisk źródła (`_group_fingerprint`) | 10 min | pierwsza obserwacja; zmiana odcisku zeruje licznik | 77/80 przekazań ≤ 19 s; 3/80 utknęły ≥ 58 min |
| plik w workspace czeka na decyzję | `source_attention` | wiersz `stage="waiting"`, `attention=True` (`resolve_readiness` nie `ready`, `automation.py:1914-1931`) | 60 min | pierwsza obserwacja | brak danych, próg to decyzja właściciela |
| zlecenie `accepted`/`running`/`paused` | `run_silent` | brak jakiegokolwiek `RunEvent` dla zlecenia przez cały próg; dla `paused` tylko gdy `policy.auto_enabled` (albo zlecenie ręczne) | 30 min | czas ostatniego zdarzenia w pamięci, a bez niego pierwsza obserwacja | 102 zlecenia: mediana 112 s, p99 644 s, maks 1413 s (23,6 min) |
| zlecenie `failed`/`partial` | `failure_unannounced` | grupa niesukcesowa w ostatnim zleceniu grupy i brak jakiegokolwiek klucza w `notified` z `k[0]=group`, `k[1]="<run>:<gen>"` (także własnego klucza strażnika, więc sygnał wychodzi raz) | 5 min | pierwsza obserwacja | 8/8 awarii miało toast, więc to bezpiecznik na ścieżkę bez `GROUP_FINISHED` |
| przeniesienie do `ready/` | `relocation_stuck` | grupa w `_ready_moves` lub `_ready_problems`, poza `_ready_inflight`, i poza odroczoną relokacją przy wyłączonym Auto | 15 min | pierwsza obserwacja | 3 próby + odczekanie do 300 s (`automation.py:295,438`) |

Etapy, które NIE są utknięciem tego strażnika:

- zlecenie `succeeded` bez rekordu `ready_groups`: dla 27 grup z 13–14.09 to legalne pozostałości sprzed `ready/`, a istnieją sukcesy bez przeniesienia (`products` puste + `absent`, `automation.py:7288`). Wykrywanie wymagałoby osobnej definicji „powinno być przeniesione” (patrz Nierozstrzygnięte);
- zlecenie `cancelled`: decyzja użytkownika;
- pauza Auto (`auto_enabled == False`): decyzja właściciela; wiersze automatyczne są wtedy „Wstrzymano” (`state_processing.py:168`), a `_admit_library` nie uznaje ich za `eligible`;
- cele subskrypcji w stanie `DUE`/`EXHAUSTED`: obsługuje je istniejący kanał subskrypcji.

## Wymagania funkcjonalne

- Dla każdego rodzaju z tabeli, po przekroczeniu progu, owner publikuje jedno powiadomienie `notification` (kanał `_publish_notification`) o tytule „Materiał utknął”.
- Treść powiadomienia zawiera nazwę materiału (po `sanitize_event_message`), krótki powód po polsku i czas trwania w minutach; nie zawiera ścieżek bezwzględnych, URL-i, haszy ani ID.
- Dla jednego klucza `(materiał, sygnatura stanu, rodzaj)` powiadomienie wychodzi najwyżej raz, dopóki utknięcie trwa. Klucz leży w `WatchState.notified` zapisanym w tym samym `_save`, co poprzedza publikację (wzorzec `_notify_group`, `automation.py:8155`).
- Sygnatura stanu zmienia się, gdy zmienia się to, co utknęło (odcisk źródła, `updated_at` acquisition, `<run>:<gen>`). Zmiana sygnatury to nowy klucz i nowe powiadomienie.
- Klucze strażnika nie są usuwane z `notified` (jak pozostałe klucze w tym zbiorze). Skutek: powrót utknięcia w tym samym stanie nie powiadamia drugi raz, ale znów jest widoczny w panelu i na ikonie; restart rezydenta nie powtarza toastu.
- Gdy w jednym skanie wypada co najmniej 3 nowych utknięć, owner wysyła jedno zbiorcze powiadomienie „Utknęło N materiałów · sprawdź Przetwarzanie”; klucze zapisuje wszystkie.
- Utknięcie jest widoczne trwale, dopóki trwa, niezależnie od toastu: snapshot `material_counts` ma nowy licznik `stalled` (liczba aktualnie utkniętych), pasek stanu panelu pokazuje „utknęło N”, ikona zasobnika przechodzi w „wymaga uwagi”, a wiersze Przetwarzania, które istnieją dla danego materiału, dostają etykietę „Utknięte · powód”.
- Skan jest wpięty w pętlę ownera jako kolejny termin (jak `_ready_retry_at`, `automation.py:5966`), co `STALL_SCAN_INTERVAL_S` = 60 s tylko gdy istnieje kandydat albo state się zmienił; bezczynny rezydent bez kandydatów nie budzi się.
- Błąd zapisu stanu nie gubi sygnału: bez udanego zapisu klucza toast nie wychodzi, a skan jest ponawiany w kolejnym takcie.

## Wymagania jakościowe

- Brak fałszywych alarmów w zdrowym przepływie: reguły stanowe na kopii prawdziwego `state.json` wskazują dokładnie dwa materiały z incydentu 24.10 i żadnego innego (patrz Warunki sukcesu).
- Opóźnienie sygnału: najwyżej próg etapu + 2 takty skanu (jeden na pierwszą obserwację, jeden na przekroczenie progu), czyli próg + 120 s.
- Koszt: skan to przegląd istniejących struktur w pamięci plus `stat` plików tylko dla grup `eligible` ∧ `needs_work`; bez I/O sieciowego, bez nowych odczytów dysku poza tym.
- Prywatność: log i toast bez ścieżek bezwzględnych, tytułów z URL, haszy, ID zleceń (reguły logowania z `AGENTS.md`).

## Inwarianty

- `WatchState` zapisuje wyłącznie owner (`anishift/application/AGENTS.md`); strażnik nie dodaje drugiego autora ani drugiego pliku stanu.
- Strażnik niczego nie naprawia, nie ponawia, nie startuje ani nie anuluje pracy; tylko obserwuje i sygnalizuje.
- Klucze strażnika w `notified` mają trzecie pole z prefiksem `stalled:`; `_notify_subscription` (`automation.py:4563`) ignoruje klucze bez prefiksu `subscription:`.
- Pauza Auto, zamykanie i odzyskiwanie nie generują sygnałów utknięcia.
- Moduł z regułami (`anishift/application/stalls.py`) jest czysty: bez I/O, `anishift.config`, `anishift.services` i CLI (`tests/application/test_architecture.py`, lista `_PURE_MODULES`).

## Ograniczenia

- Tylko Windows; bez Linuksa.
- Bez nowej zależności, bez edycji `pyproject.toml`.
- Kod i komentarze po angielsku; teksty dla użytkownika po polsku.
- `automation.py` zostaje jednym plikiem; w nim tylko budowa kandydatów i wpięcie, reguły i tracker w nowym czystym module.

## Zakazane

- Zmiana `WATCH_STATE_SCHEMA_VERSION`, walidatorów `watch_state.py` lub migracji.
- Nowy plik trwały, nowy sink logów, nowy proces, nowy wątek.
- Naprawianie przyczyny incydentu 24.10 w tym zakresie (osobny workstream badawczy).
- Ruszanie rezydenta, `config/watch/`, `workspace/` podczas projektowania; podczas wykonania tylko w testach na kopiach w `tmp_path`.
- Dopisywanie zdarzeń stall do `history.jsonl` albo `decisions.jsonl`.

## Zakres

- Moduł reguł i trackera, budowa kandydatów w ownerze, skan w pętli, powiadomienie, flaga `stalled` w snapshocie i wierszach, licznik, pasek stanu, ikona zasobnika, testy, wpis w `anishift/application/AGENTS.md`.

## Poza zakresem

- Naprawa przyczyny, automatyczne ponowienie lub restart.
- Ustawienia użytkownika dla progów, wyciszanie, tryb „nie przeszkadzać”.
- Powiadomienia poza Windows (e-mail, telefon), alert gdy rezydent w ogóle nie działa (nic go wtedy nie wyśle; osobny temat „watchdog watchdoga”).
- Nawigacja kliknięcia toastu do zakładki Przetwarzanie (kliknięcie otwiera panel jak inne toasty bez celu, `automation.py:8307`).
- Wykrywanie sukcesów bez przeniesienia do `ready/`.

## Odłożone

- Otwieranie panelu na zakładce Przetwarzanie po kliknięciu toastu: wymaga rozszerzenia nawigacji `panel_open` (`cli/interactive/app.py:368`), niepotrzebne do wykrycia.

## Odrzucone

- Zapis zdarzenia „utknięcie” w Historii (`HistoryKind`, `history.py:31`): Historia pokazuje wyłącznie zdarzenia terminalne materiału; utknięcie nie jest terminalne i zaśmiecałoby widok „50 ostatnich materiałów”.
- Trwały zegar utknięć w `WatchState`: wymaga bumpu schematu i migracji; zysk to tylko szybsze wykrycie po restarcie, a etapy z kotwicą `updated_at` i tak go dostają.
- Wykorzystanie `recheck_interval_s` jako taktu: 3600 s jest większe niż progi, a pole nie jest czytane przez logikę.

## Preferencje

- Jeden spójny rzeczownik w UI: „utknęło/Utknięte”.

## Warunki sukcesu

- Test regresji scenariusza 24.10 (`tests/application/test_stall_watchdog.py`): stan z acquisition `complete` bez zlecenia i plikiem w workspace, Auto włączone, start Auto uniemożliwiony; po przesunięciu zegara o 10 min i skanie: dokładnie jedno powiadomienie, klucz w `notified`, wiersz z flagą `stalled`, `material_counts.stalled == 1`; drugi skan nie wysyła nic; po zmianie pliku (inny odcisk) nowe powiadomienie.
- Testy jednostkowe trackera: próg, brak powtórzenia, zerowanie licznika po zmianie sygnatury i po zniknięciu kandydata, kotwica trwała, odrzucenie kotwicy starszej niż 7 dni.
- Test, że pauza Auto i zamykanie owner'a nie wywołują sygnału.
- Dry run reguł stanowych na kopii `config/watch/state.json` i nazwach plików z `workspace/` (pełny owner wymaga mediów i usług): `transfer_unsettled` 0, `failure_unannounced` 0, „przekazane bez zlecenia” dokładnie 2 (grupy z incydentu). Ocena: agent wykonawczy; wynik w raporcie wykonania.
- Test graniczny: grupa już uruchomiona dla dokładnie bieżącego odcisku, z brakującym produktem, nie jest zgłaszana.
- Bramki: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run pytest` zielone.
- Akceptacja człowieka po wdrożeniu: 7 dni działania; każdy toast „Materiał utknął” to prawdziwe utknięcie albo zgłoszony fałszywy alarm (wtedy korekta progu lub warunku). Ocenia właściciel.

## Nierozstrzygnięte (decyzje właściciela)

- D1 `source_not_started` 10 min, `transfer_unsettled` 30 min, `client_unreadable` 30 min, `run_silent` 30 min, `relocation_stuck` 15 min, `failure_unannounced` 5 min, `source_attention` 60 min: wartości wyprowadzone z danych wyżej; do zatwierdzenia lub korekty.
- D2 Okno „opuszczone”: 7 dni (jak „Nie znaleziono … od 7 dni”, `automation.py:4575`). Starsze utknięcia z trwałą kotwicą nie alarmują (w stanie: 22 stare `uncertain` z września i października).
- D3 Zbiorczy toast od 3 utknięć w jednym skanie.
- D4 Czy utknięcie z powodu pauzy Auto trwającej wiele godzin ma kiedyś alarmować (dziś: nie).
- D5 Czy wykrywać „sukces bez przeniesienia do `ready/`” (dziś: nie, brak jednoznacznej definicji).
- D6 Znane ograniczenie: to samo utknięcie, które wraca w tym samym stanie (ten sam odcisk pliku, ten sam `updated_at`), nie powiadamia ponownie. Wariant z usuwaniem kluczy odrzucony, bo po restarcie powtarzałby toasty (fakty o transferach wracają z opóźnieniem, `automation.py:868`). Akceptacja ograniczenia: właściciel.
- D7 Najsłabiej uzasadnione rodzaje (brak danych): `source_attention` (60 min) i `client_unreadable` (30 min; ikona zasobnika już pokazuje `transfers_problem`). Właściciel może je wyciąć bez wpływu na resztę.
