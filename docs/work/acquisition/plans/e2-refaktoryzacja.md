# E2 — audyt kodu i plan refaktoryzacji

Status: **wersja 2, po review `astra` (FAIL), do ponownej weryfikacji i akceptacji właściciela**. Dokument nie zmienia kodu.
Zakres audytu: `dd01982..5ee78e3` (branch `work/acquisition/02-download`, 31 commitów).

## 1. Metoda i konwencja

- Każdy finding ma dowód `plik:linia` albo komendę oraz ważność: **krytyczny** (utrata danych, błędny wynik bez sygnału), **poważny** (błędne zachowanie w realnym scenariuszu albo niestabilna bramka), **drobny** (czytelność, spójność, dokumentacja, martwy kod).
- „Fakt” to coś odczytanego z kodu albo uruchomionego. „Ocena” to wniosek audytora; jest oznaczona.
- Krytycznych findingów nie znaleziono.

Uruchomione komendy (stan `5ee78e3`):

```powershell
git log --oneline dd01982..HEAD            # 31 commitów
git diff --stat dd01982..HEAD -- anishift/application/automation.py   # +2621 linii
uv run ruff check anishift/ tests/          # All checks passed!
uv run ruff format --check anishift/ tests/ # 572 files already formatted
uv run pytest -o addopts="" -p no:cacheprovider -q --tb=line tests/application/test_scheduler.py tests/application/test_automation.py -k "locked_publication or resident_repeat_preserves or material_identity_survives"
#   3 przebiegi: 1x "1 failed, 4 passed" (WinError 32, F-07), 2x "5 passed"
uv run pytest -o addopts="" -p no:cacheprovider -q tests/application/test_automation.py -k resident_repeat_preserves
#   4 przebiegi osobno: 4x PASS
```

mypy i pełnego `pytest` w tym audycie nie uruchamiano.

## 2. Fakty o rozmiarze

| Plik | Linie |
| --- | ---: |
| `anishift/application/automation.py` | 7583 (`AutomationOwner` ok. 557–7000, ok. 6445 linii) |
| `anishift/cli/interactive/anime.py` | 1745 |
| `anishift/cli/interactive/state.py` | 1582 |
| `anishift/application/watch_state.py` | 1296 |
| `anishift/application/control.py` | 1030 |
| `anishift/platform/local_control.py` | 955 |
| `anishift/cli/resident.py` | 706 |
| `anishift/application/transfers.py` | 509 |

E2 dodał do `automation.py` ok. 100 metod (git diff: 129 linii ze zmienionym albo dodanym `def`). `AutomationOwner._perform` ma ok. 130 linii i `noqa: C901, PLR0911, PLR0912, PLR0915`. `StateController._receive` w `state.py` ma `noqa: C901`.

## 3. Findingi

### F-01 (poważny, potwierdzony) — timeout odpowiedzi rozsynchronizowuje kanał poleceń

Fakty z kodu:
- Gdy odpowiedź nie przyjdzie w czasie, `_receive` (`local_control.py:579-583`) rzuca `ControlError(code=INTERNAL)`. Pole `answered` zostaje domyślne `False`, a połączenie nie jest zamykane.
- `_connection_lost` (`resident.py:705-706`) zwraca `True` tylko dla `REFUSED`, więc timeout z kodem `INTERNAL` nie wywołuje `_drop` (`resident.py:579-582`). Kolejne polecenie idzie tym samym połączeniem.
- Istniejący test utrwala to zachowanie: przypadek `ControlError("late", code=INTERNAL)` ma `reopened=False` (`tests/cli/test_resident.py:309`, test `test_only_a_lost_connection_is_replaced_on_the_next_call`, `:314-330`).
- `_accepted_result` (`local_control.py:875-891`) sprawdza `ok` **przed** `command_id`:
  - spóźniona ramka błędu poprzedniego polecenia zostaje przypisana bieżącemu poleceniu jako `answered=True`;
  - spóźniona ramka sukcesu daje `INVALID_PAYLOAD` z `answered=True`.
  Żadna z nich nie zrywa sesji.
- Serwer wysyła ramki błędu z pustym `command_id` w dwóch miejscach: `_TOO_MANY_CONNECTIONS` przy przyjęciu połączenia (`local_control.py:439`) i `_UNREADABLE_FRAME` jako odpowiedź na nieczytelną ramkę (`local_control.py:459`).
- Timeouty: `DEFAULT_TIMEOUT_S = 30.0` (`local_control.py:85`); dłuższe odczyty odcinków używają `episode_read_timeout_s` (`acquisition.py:422-428`).

Potwierdzenie: recenzent `astra` odtworzył F-01 na izolowanym named pipe (`ControlServer`/`ControlClient`/`ResidentSession`). Wynik:
1. pierwsze polecenie: błąd `internal`, `answered=False` (timeout);
2. drugie polecenie: błąd `refused`, `answered=True`, `reason=first_only` — to odpowiedź na polecenie pierwsze;
3. trzecie polecenie: `invalid_payload`.

W tej wersji dokumentu nie powtarzałem tej próby.

Ocena: po jednym timeoucie kolejne odpowiedzi na tym kanale należą do poprzednich poleceń, dopóki połączenie się nie zamknie. Panel może wtedy pokazać odmowę jednego polecenia jako wynik innego. Przykład: partia D dostaje cudze `REFUSED` z `answered=True`, kończy się i porzuca swój `command_id` (`anime.py:1026-1031`).

### F-02 (poważny) — dwie rozbieżne klasyfikacje błędu transportu

Fakty:
- **Kanał poleceń** `ResidentSession` (`resident.py:705-706`): kanał jest utracony, gdy `not answered and code is REFUSED and reason != "request_too_large"`. Timeout (`INTERNAL`, `answered=False`) **nie** jest tu utratą.
- **Obserwator** `StateController._watch` (`state.py:901`): kanał jest utracony, gdy `isinstance(error, OSError) or (ControlError and not error.answered)`. Timeout **jest** tu utratą.
- **Partia D** (`anime.py:1026-1031`) liczy coś innego: potwierdzoną odmowę, `answered and code is REFUSED`. Tylko ona kończy partię i porzuca `command_id`; każdy inny błąd zostawia ID do ponowienia Enterem (`anime.py:1034`). To osobny kontrakt, nie trzecia wersja przydatności kanału:
  - `INTERNAL` z `answered=True`: kanał sprawny, partia trwa;
  - `REFUSED` z `answered=True`: kanał sprawny, partia się kończy (potwierdzone przez recenzenta).

Ocena: rozbieżność dotyczy dwóch miejsc (kanał poleceń i obserwator) i różnią się one właśnie dla timeoutu, co otwiera F-01. Warunek partii D jest poprawnie osobny i powinien taki zostać.

### F-03 (drobny) — powody odcinka to otwarty zbiór stringów bez testu pokrycia etykiet

Źródła wartości `EpisodeResult.reason` i `EpisodeStatus.reason` (`episode_commands.py:19, 71`, typ `str`):
- literały ownera, m.in.:
  - `episode_not_aired` (`automation.py:4499`), `legacy_unreadable` (`:4518`), `episode_in_progress` (`:4521`), `no_suggestion` (`:4533`), `pack_in_progress` (`:4541`);
  - `transfer_failed`, `publication_failed`, `waiting_previous_transfer` i `episode_file_unresolved` (`:4061-4070`);
  - `publication_missing` (`:4090`), `finalization_failed` (`:4110`), `admission_failed` (`:4547`);
- `failure_code(problem)` (`automation.py:4505, 4510`; `events.py:184`), czyli wartości `ErrorCode` (`errors.py:26`), np. `TORRENT_SOURCE_FAILED`;
- `response.reason` z `_admit_episode` (`automation.py:4547`):
  - wartości `RefusalReason` (`control.py:148`), np. `shutting_down` (`automation.py:4655-4656`);
  - literały `legacy_unreadable` (`:4659`) i `episode_changed` (`:4663-4664`);
- wartości `AdmissionConflict` (`control.py:201`), np. `transfer_recorded` (`automation.py:4150`) i `conflict.value` (`:4144`).

Trwałość i odczyt:
- Wyniki partii są zapisywane w receipts i odczytywane przez `decode_view(EpisodeBatch, …)` (`automation.py:4154, 4400`). `decode_view` waliduje ściśle (`control_views.py:157-159`; `strict=True`).
- Zamknięty enum w polu `reason` odrzuciłby historyczne receipts z wartościami spoza enuma.

Panel:
- `EPISODE_REASON_LABELS` (`anime.py:86-100`) daje krótką etykietę Stan. `_refused_result` (`anime.py:1650-1661`) rozróżnia etykietę od szczegółu w komunikacie. Nieznany powód dostaje „Nie zlecono” i opis z `_stated`, a `TORRENT_SOURCE_FAILED` dostaje „Błąd źródła”.
- Kontrakt rozróżnienia etykiety i szczegółu pilnuje `tests/cli/test_anime_episodes.py:1363-1402` (`no_suggestion`, `TORRENT_SOURCE_FAILED`, `shutting_down`, `acquisition_unavailable`).
- `_episode_status_label` (`anime.py:1664-1666`) przy powodzie spoza słownika wraca do etykiety stanu. Dotyczy to np. `finalization_failed`; ten powód obsługuje osobno tylko Przetwarzanie (`state.py:1394-1395`).
- `tests/` nie odwołuje się do `EPISODE_REASON_LABELS` (grep: 0 trafień).

Korekta względem wersji 1:
- Lista powodów była niepełna; dochodzą `ErrorCode`, `RefusalReason`, `AdmissionConflict` i `episode_changed`.
- Ważność obniżona z poważnej na drobną. Wartości spoza słownika mają jawny fallback (`anime.py:1657-1661, 1664-1666`), więc skutkiem jest ogólna etykieta, a nie błędny stan.

Ocena: brakuje maszynowego powiązania lokalnych literałów ownera z etykietami panelu. Nowy literał albo zmiana nazwy przejdą bez sygnału i trafią do fallbacku.

### F-04 (drobny) — etykieta `episode_in_progress` nie mieści się w kolumnie Stan

Fakty: `anime.py:89` ma `"W toku · C anuluj w Przetwarzaniu"` (33 znaki), a kolumna Stan ma 15 kolumn (`anime_view.py:57`). Ten sam tekst trafia do Stan przez `_refused_result` (`anime.py:1652-1654`) i do komunikatu przez `anime.py:995-997`.

Ocena: w tabeli widać obcięty tekst. Wskazówka powinna zostać w komunikacie, a Stan powinien dostać krótką etykietę.

### F-05 (drobny) — zdublowana etykieta „Do pobrania”

Fakty: `anime.py:99` (`result_missing`) i osobny literał w `anime.py:647`.

### F-06 (drobny) — cztery helpery tożsamości pliku

Fakty:
- `library.py` `file_identity` (z guardami);
- `automation.py:7399` `_file_identity` (rozmiar, mtime; zwraca `(-1, -1)`);
- `acquisition_staging.py:93` `file_stamp` (E2);
- `inspection.py` ok. 538 `file_stamp` oraz `service.py` ok. 1108 `file_identity` (sprzed E2).

Obecność wyniku sprawdzana jest dwiema metodami:
- `_ready_result_missing` (`automation.py:4054`): `all(file_identity(...) is None)`;
- `_handed_off_status` (`automation.py:4088`): `file_stamp` porównany z `publication.files`.

Te dwie metody nie sprawdzają tego samego. Pierwsza mówi, czy główny wynik Gotowe istnieje. Druga mówi, czy opublikowane pliki są niezmienione. Inne kontrole `file_identity`: `automation.py:1948, 2342, 2467, 6866, 6946`.

Ocena: zasada reuse z AGENTS każe zastąpić duplikat istniejącym źródłem, a E2 dodał kolejny wariant. Scalać wolno tylko helpery o tej samej semantyce (sentinel, guardy); dwóch kontroli wyniku nie należy łączyć.

### F-07 (poważny) — niestabilne testy: dwie przyczyny potwierdzone, trzy hipotezy

| Test | Fakty | Przyczyna |
| --- | --- | --- |
| `tests/application/test_automation.py:5289` `test_resident_repeat_preserves_a_local_source_and_allows_remote_repeat_after_its_removal` | Odtworzone: 1 z 3 przebiegów w zestawie z innymi testami kończy się `PermissionError: [WinError 32]` na `source.unlink()` (`test_automation.py:5340`). Osobno 4/4 PASS. | **Potwierdzona (kod + odtworzenie).** `source_is_available` (`directory_watch.py:87-100`) otwiera plik z `FILE_SHARE_READ` bez `FILE_SHARE_DELETE`. Wołają go owner (`automation.py:1993, 2374`), inspekcja (`inspection.py:186`), transfery (`transfers.py:500`) i `watch.py:84`. Po `set_auto True` owner sprawdza ten sam plik w tle, a usunięcie w tym oknie dostaje odmowę. Produkcja celowo blokuje aktywnych writerów (AGENTS); wyścig dotyczy testu. |
| `tests/platform/test_qbittorrent_process.py:344` `test_private_clients_download_concurrently_reconnect_and_stop_independently` | Znany fail z E1 i E2 (`outcomes/e2.md:151`): `first_child.poll()` zwraca `None`, a log zawiera `Kept the private torrent client running while its own window is open`. | **Potwierdzona z kodu, bez osobnego odtworzenia.** Polityka zamknięcia pomija klienta z widocznym oknem (`qbittorrent_process.py:321-323`). Test uruchamia qB przez `collide_once` (`test_qbittorrent_process.py:353-368`) bez `STARTUPINFO`/`SW_HIDE`. Fixture integracyjny robi to poprawnie (`episode_download_support.py:178-188`). Fail jest deterministyczny na pulpicie, na którym okno qB jest widoczne. |
| `tests/application/test_scheduler.py:728` `test_locked_publication_allows_other_group_to_finish` | Test ustawia `_PUBLICATION_LOCK_RETRIES=3` i opóźnienie `0.01` (`test_scheduler.py:760-761`); produkcja ma 240 × 0.25 s (`scheduler_runtime.py:53, 56`). Zamek zwalnia dopiero `GROUP_FINISHED` grupy 2 (`test_scheduler.py:752-756`). W tym audycie 3/3 PASS. | **Hipoteza.** Budżet ok. 30 ms na dokończenie grupy 2 pod obciążeniem xdist jest za mały. Po wyczerpaniu prób grupa 1 pada. |
| `tests/integration/test_episode_download.py:51` `test_selected_pack_survives_owner_and_qb_restart_` | Zgłoszony błąd to „brak wolnego portu loopback” (`outcomes/e2.md:869`), osobno 3/3 PASS. `_port()` (`episode_download_support.py:144-154`) rzuca `AssertionError("No shared loopback TCP/UDP port available")`, gdy 20 razy z rzędu nie uda się `udp.bind` na numerze portu przydzielonym dla TCP. Dzieje się to **przed** startem qB: `private_client` woła `_port()` w linii 164, a `prepare()` dopiero w 201. | **Hipoteza, przyczyna nieznana.** Zgłoszony objaw to nieudana alokacja, nie kolizja przy starcie qB. Kod błędu `udp.bind` (`except OSError: continue`, `:151-152`) jest połykany, więc nie wiadomo, czy to `WSAEADDRINUSE` (port zajęty przez innego workera xdist) czy `WSAEACCES` (wykluczony zakres portów Windows, `netsh int ipv4 show excludedportrange`). **Osobne ryzyko** (nie tłumaczy zgłoszonego objawu): TOCTOU między zamknięciem gniazd w `_port()` a startem qB na tym porcie. Objawiłoby się błędem startu klienta albo asercją `listen_port` (`:212`). |
| `tests/application/test_automation.py:4232` `test_material_identity_survives_bundle_metadata_preparation_processing_and_ready[True]` | Raportowany jako flaky; w tym audycie 3/3 PASS. Część asercji nie używa `_await`, choć następuje po zdarzeniach asynchronicznych (`test_automation.py:4310-4314, 4318-4320`); budżet `entered.wait(1.0)` w linii 4309. | **Hipoteza.** Bez logu z nieudanego przebiegu przyczyna jest niepotwierdzona. |

Korekta względem wersji 1: nagłówek mówił o „trzech z pięciu” rozpoznanych przyczynach, a sama tabela traktowała scheduler jako hipotezę. Potwierdzone są dwie. Opis portu rozdzielono na alokację (zgłoszony objaw) i kolizję przy starcie (osobne ryzyko).

### F-08 (drobny) — nieużywane ścieżki produkcyjne `ResidentSession` i zaplecze grup

Fakty:
- `resident.py` `search` (207), `download` (240) i `follow` (359) nie mają wywołań z CLI. Panel Anime używa `find_titles`, `franchise`, `episodes`, `offer`, `episode_download` i `episode_states` (`anime.py:1015, 1073, 1131, 1142, 1348, 1438, 1461`). `validate_deletion` nie ma wywołań produkcyjnych.
- D5 (`plans/e2-panel-anime.md:366-368`) usunął **z UI** zakładki Anime katalog grup, G i S. Istniejące subskrypcje działają dalej.
- Owner nadal używa `acquisition.download` (`automation.py:3616`, `subscriptions.py:847`). `catalog_releases` i `order_groups` (`acquisition.py:431, 470`) obsługują subskrypcje grupowe. `subscription_add` istnieje (`control.py:809`, `automation.py:412, 3363, 3372`).
- Masterplan odkłada usunięcie starego zaplecza do E5 (`masterplan.md:32`: „stare zaplecze w E5”; `masterplan.md:44`, `masterplan.md:115-118`). E3 usuwa pomost `G` i drogę grup w UI (`masterplan.md:42`).

Korekta względem wersji 1: plan kierował całe usunięcie do E3. Zgodnie z masterplanem E3 obejmuje tylko to, co wymusza migracja subskrypcji, a reszta trafia do E5.

### F-09 (drobny) — pozostałości legacy daemona i flag `--resident`

Fakty:
- `cli/watch.py:172` `run_daemon` ma tylko wywołania testowe; produkcja używa `run_resident` (`watch.py:316`, `main.py:231-239, 271-277`).
- `request_stop` (`watch.py:149-160`) obsługuje `STOP_FILE_NAME = "stop"` (`watch.py:71`), czytany tylko w `watch.py:265, 269`.
- `batch_command` i `spawn_window` (`watch.py:133-146`); `watch batch` (`main.py:282-290`) jest tylko komunikatem migracyjnym.
- Flagi `--resident` w `main.py:156/170`, `187/189` i `295/303` nic nie robią (`del resident`).

Ocena: stara pętla zostaje wyłącznie dla testów porównawczych (`cli/AGENTS.md`); usuwanie należy do E5.

### F-10 (drobny) — nieaktualne instrukcje i dokumenty

Fakty:
- `anishift/cli/AGENTS.md`: „Stare `run_daemon` pozostaje domyślne do przełączenia w P08” oraz ukryte `--resident` „przed domyślnym przełączeniem w P08”. Kod już tego nie robi (F-09).
- `anishift/AGENTS.md:9`: lista `services/` pomija `torrents` i `catalog`.
- `anishift/application/AGENTS.md` ma ok. 422 linie z przemieszanym EN/PL i urwanym zdaniem w okolicy linii 46-47.
- `outcomes/e2.md:26-32`: tabela ról z F0 jest nieaktualna (linia 13 to przyznaje). Autorem F4 był `astra`, a dokument wskazuje `opus55` (`outcomes/e2.md:801`).
- `masterplan.md:41`: pomost `G` „zostaje, bo tylko z niego da się jeszcze dodać subskrypcję”, a D5 go usunął.

### F-11 (drobny, ocena) — `AutomationOwner` łączy wiele osi zmian; projekcja odcinków nie jest czysta

Fakt: jedna klasa obsługuje bibliotekę, usuwanie i przywracanie, pauzę, podgląd i przyjęcie runów, subskrypcje, odcinki, cykl transferu selektywnego, publikację, ready store, historię, powiadomienia i ponowienia (§2).

Zależności metod projekcji stanu odcinków (fakty):
- `_lifecycle_status` (`automation.py:4093-4123`) czyta `self._ready_problems` (`:4109`) i `self._succeeded_groups` (`:4112`). Ta druga metoda (`:1694-1720`) bierze `_progress_lock`, czyta `_run_events`, dzienniki runów z dysku (`_journal_completed_groups`, `:1722`) i zapisuje cache `_completed_groups` (`:1715-1719`).
- `_assignment_status` (`:4056-4072`) woła `self._replacement_ready` (`:4067`).
- `_legacy_episode_status` (`:4125-4160`) woła `self._download_materials` (`:4135`), czyta `self._episode_offers` (`:4145`) i `_transfer_conflict` (`:4149`) oraz dekoduje receipts (`:4151-4159`).
- `_legacy_episode_records` (`:4162-4167`) woła `SubscriptionService.list()`.
- `_ready_result_missing` (`:4040-4054`) i `_handed_off_status` (`:4074-4091`) czytają system plików.
- Już czyste i poza klasą są `_handed_off`, `_selection_confirmed` i `_published_group`.

Korekta względem wersji 1: projekcja nie jest „czystymi funkcjami nad `WatchState` i systemem plików”. Zależy od stanu runów w pamięci pod blokadą, cache, ofert sesji i usługi subskrypcji. Realnie czysty podzbiór z jawnymi wejściami jest mały: wyliczenie powodu przypisania w `:4061-4070` (wejścia: `transfer`, `assignment`, wynik `_replacement_ready`).

Ocena: przed E3 nie ma podstaw do wydzielania modułu. Decyzja o granicy należy do planu E3, który doda nowe stany.

### F-12 (drobny) — `selection_union` jest martwy w produkcji, a AGENTS opisuje go jako część ścieżki

Fakty:
- `selection_union` (`transfers.py:404`, eksport `:38`) jest wołany tylko w `tests/application/test_selective_transfers.py:77, 82, 89`.
- `application/AGENTS.md:198-199`: „`selection_union` checks every index/path/size against that map. Persist the union and revision before calling the manager.”
- Produkcyjna suma wyboru to `AcquisitionConfirmation.wanted_files` (`control.py:528`): indeksy z `item.files` aktywnych przypisań, bez sprawdzania ścieżki i rozmiaru. Spójność z mapą plików pilnuje porównanie rewizji `file_map_revision` w `_apply_selection` (`automation.py:5218-5220`) przed `service.select_files` (`:5223-5225`).

Ocena: instrukcja opisuje kontrakt, którego kod nie wykonuje. Kolejny wykonawca może na nim polegać. Trzeba albo poprawić AGENTS i usunąć `selection_union` wraz z jego testami, albo użyć go w `_apply_selection`. Wybór zależy od tego, czy sama zgodność rewizji wystarcza; recenzent i audytor nie znaleźli scenariusza, w którym nie wystarcza.

### F-13 (drobny) — AGENTS błędnie opisuje los `ADMITTED`

Fakty:
- `application/AGENTS.md:253-256`: „`ADMITTED` nie jest uzgadniane ani wznawiane, a komenda `transfer` na jego hash dostaje `transfer_not_started`”.
- Cykl transferów próbuje wysłać dopuszczone `ADMITTED`: `_advance_transfer_actions` → `_send_selective` (`automation.py:4908-4910`) → `_send_selective_locked` (`:5031-5049`). `_begin_send` zapisuje trwałe `PENDING_SEND` przed `add_metadata` (`:5091-5097`), a `_finish_send` zapisuje `ACCEPTED` albo `UNCERTAIN` (`:5043-5049`, `:5099-5105`). Niespełnione warunki (`:5034-5042`, `:5084-5090`) zostawiają przyjęcie do późniejszej obsługi.
- Druga część zdania jest nadal prawdziwa: `transfer` na hash w stanie `ADMITTED` dostaje `transfer_not_started` (`automation.py:6021-6024`).

Ocena: pierwsza część zdania jest nieaktualna; poprawka ogranicza się do dokumentacji.

## 4. Plan

Wielkość: **S** do ok. 150 linii zmian, **M** do ok. 500, **L** powyżej. To szacunek audytora, nie pomiar.

### Etap A — przed E3

**A1. Wspólna klasyfikacja błędu transportu i domknięcie kanału po timeoucie** (F-01, F-02) — S/M

Co:
1. Jedno źródło odpowiedzi na pytanie „kanał nie nadaje się do dalszego użycia”, przy `ControlError` w `platform/local_control.py`. Używają go oba miejsca transportowe: `ResidentSession` (`resident.py:705`) i obserwator (`state.py:901`). Utrata obejmuje EOF/OSError, timeout i obcy `command_id`; `request_too_large` nadal jej nie oznacza.
2. Po takim błędzie klient zamyka połączenie, a kolejne wywołanie łączy się od nowa i niczego nie wysyła ponownie (kontrakt z `cli/AGENTS.md`).
3. `_accepted_result` sprawdza `command_id` przed `ok`. Semantyka:
   - **obcy, niepusty `command_id`** → błąd transportu z `answered=False`, bo to nie jest odpowiedź na to polecenie, a kanał jest zamykany;
   - **pusty `command_id` w ramce błędu** → błąd protokołu przypisany bieżącemu poleceniu (`answered=True`), zgodnie z `_UNREADABLE_FRAME` (`local_control.py:459`) i `_TOO_MANY_CONNECTIONS` (`:439`);
   - **pusty `command_id` w ramce sukcesu** → odrzucenie jako ramka nieczytelna.
4. Warunek potwierdzonej odmowy partii D (`anime.py:1026-1028`) **zostaje osobny i bez zmian**. Kończy partię tylko `answered=True` z `REFUSED`, a timeout i obcy `command_id` zostawiają ID do ponowienia.

Dlaczego: usuwa odtworzone błędne przypisanie odpowiedzi (F-01) i rozbieżność transportu (F-02), nie mieszając jej z decyzją o końcu partii.

Pliki: `anishift/platform/local_control.py`, `anishift/cli/resident.py`, `anishift/cli/interactive/state.py`, testy w `tests/platform/test_local_control.py`, `tests/cli/test_resident.py`, `tests/cli/test_anime_episodes.py`, opis w `cli/AGENTS.md`.

Zmiana istniejącego kontraktu testowego: przypadek `ControlError("late", code=INTERNAL)` w `tests/cli/test_resident.py:309` zmienia się z `reopened=False` na `True`. To świadoma zmiana kontraktu: timeout zrywa kanał. Pozostałe przypadki (`:307, 308, 310`) zostają.

Ryzyko:
- Utrata ID partii D po timeoucie. Pilnuje tego regresja poniżej.
- Ramka z `command_id` bieżącego polecenia, która przyjdzie po zamknięciu, ginie razem z połączeniem. Wynik odzyskuje się przez receipt (`episode_download` z tym samym `command_id`, `automation.py:4397-4404`).

Dowód:
- nowy test na prawdziwym named pipe, odtwarzający scenariusz recenzenta: timeout, potem drugie i trzecie polecenie. Na `5ee78e3` musi padać, a po zmianie każde polecenie dostaje własną odpowiedź albo czyste ponowne połączenie;
- testy semantyki `_accepted_result` dla obcego, pustego-błąd i pustego-sukces `command_id`;
- regresja partii D: po timeoucie i po obcym `command_id` `_pending_batch` oraz zaznaczenia zostają, a Enter ponawia z tym samym `command_id`. Po `REFUSED` z `answered=True` partia się kończy, a po `INTERNAL` z `answered=True` trwa;
- istniejące testy `tests/cli/test_resident.py`, `tests/cli/test_anime_episodes.py` i `tests/platform/test_local_control.py`.

**A2. Kontrakt lokalnych powodów ownera i test etykiet** (F-03, F-04, F-05) — S/M

Co:
1. Inwentaryzacja źródeł powodów (lista z F-03) jako część pracy, potwierdzona grepem.
2. `StrEnum` **tylko dla literałów ownera**, czyli wartości, których nie ma w `ErrorCode`, `RefusalReason` ani `AdmissionConflict`. Enum należy do `application/episode_commands.py`. Nie powielać wartości istniejących enumów; użyć ich bezpośrednio.
3. Pola `EpisodeResult.reason` i `EpisodeStatus.reason` **zostają typu `str`**. Historyczne receipts (`decode_view`, `strict=True`) mogą zawierać dowolną z tych wartości albo wartość już nieistniejącą.
4. Słownik etykiet panelu pozostaje w `anime.py`. Test pokrycia sprawdza:
   - każdy element nowego enuma ma etykietę Stan albo jawny wpis „fallback do etykiety stanu”;
   - każda etykieta Stan ma ≤ 15 komórek;
   - nieznany powód odmowy, poza obsługiwanymi wyjątkami (`acquisition_unavailable` → „Niedostępne”, `TORRENT_SOURCE_FAILED` → „Błąd źródła”, `anime.py:1655-1661`), daje „Nie zlecono” i szczegół z `_stated`; fallback etykiety stanu w projekcji (`anime.py:1664-1669`) jest osobny i zostaje.
5. Skrócić `episode_in_progress` (np. „W toku”); wskazówka „C anuluj w Przetwarzaniu” zostaje w komunikacie. Literał „Do pobrania” z `anime.py:647` brać ze słownika.

Dlaczego: maszyna pilnuje powiązania literałów ownera z panelem, nie zmieniając formatu kanału ani zapisanego stanu.

Pliki: `anishift/application/episode_commands.py`, `anishift/application/automation.py` (miejsca emisji literałów), `anishift/cli/interactive/anime.py`, `anishift/cli/interactive/state.py` (porównania `reason`), nowy test w `tests/cli/`.

Ryzyko: zmiana wartości stringów na kanale albo w ledgerze. `StrEnum` serializuje się jako ta sama wartość; test round-trip to potwierdza.

Dowód:
- nowy test pokrycia i szerokości; na `5ee78e3` pada na szerokości `episode_in_progress`;
- round-trip IPC `EpisodeBatch` przez `encode_view`/`decode_view` z powodem z enuma ownera, z `ErrorCode` i z `RefusalReason`;
- odczyt historycznego receipt (zapisany JSON z `TORRENT_SOURCE_FAILED` i `shutting_down`) przez `automation.py:4154`;
- bez zmian przechodzi `tests/cli/test_anime_episodes.py:1363-1402`, który pilnuje rozróżnienia etykiety i szczegółu;
- `tests/application/test_episode_commands.py`.

**A3. Naprawa niestabilnych testów z potwierdzoną przyczyną** (F-07) — S

- `test_resident_repeat_…`: przed `unlink()` wyłączyć auto i poczekać na bezczynność puli I/O ownera albo usuwać w ograniczonej pętli `_await`, ponawiając wyłącznie przy `WinError 32`. Kodu produkcyjnego nie zmieniać.
- `test_private_clients_…`: uruchamiać qB w `collide_once` z `SW_HIDE`. Logikę `hidden` z `tests/integration/episode_download_support.py:178-188` przenieść do wspólnego helpera testowego zamiast kopiować.
- Pliki: `tests/application/test_automation.py`, `tests/platform/test_qbittorrent_process.py`, wspólny helper testowy.
- Ryzyko: rozluźnienie testu tak, że przestanie wykrywać regresję. Asercje kontraktu zostają.
- Dowód: 10 przebiegów zestawu z §1 bez `WinError 32`; `test_private_clients_…` PASS na pulpicie właściciela; pełny `uv run pytest`.

**A4. Diagnoza trzech hipotez** (F-07) — S, najpierw badanie, potem zmiana

- `test_locked_publication_…`: pętla pod `-n auto` z logiem. Jeśli potwierdzi się wyczerpanie prób, podnieść budżet w teście (np. 1000 × 0.01 s), zachowując asercję kolejności `["group-2", "group-1"]`.
- `test_selected_pack_…`, alokacja: najpierw zebrać kod błędu `udp.bind` (tymczasowo w helperze testowym albo w komunikacie `AssertionError`) oraz `netsh int ipv4 show excludedportrange protocol=udp`. Naprawa zależy od kodu błędu:
  - `WSAEACCES`: wybierać port spoza wykluczonych zakresów;
  - `WSAEADDRINUSE`: inny sposób alokacji, np. pozwolić qB wybrać port i odczytać `listen_port` z preferencji.
- `test_selected_pack_…`, kolizja przy starcie (osobne ryzyko): naprawiać dopiero, gdy pojawi się jej objaw (błąd startu qB albo asercja `:212`).
- `test_material_identity_…[True]`: log nieudanego przebiegu, potem `_await` tylko tam, gdzie log to potwierdzi.
- Dowód: log nieudanego przebiegu przed zmianą, potem seria PASS.

**A5. Konsolidacja helperów tożsamości pliku** (F-06) — S/M

- Co: przyjąć `library.file_identity` jako źródło i zastąpić nim `_file_identity` (`automation.py:7399`) oraz `file_stamp` (`acquisition_staging.py:93`), ale tylko gdy semantyka (sentinel, guardy na linkach i katalogach) jest zgodna. Duplikaty sprzed E2 (`inspection.py`, `service.py`) tylko przy identycznej semantyce. Dwóch różnych kontroli wyniku (`automation.py:4054` i `4088`) nie łączyć.
- Ryzyko: różny sentinel (`None` kontra `(-1, -1)`); każde miejsce wymaga sprawdzenia, nie mechanicznej podmiany.
- Dowód: `tests/application/test_automation.py`, `tests/application/test_library_undo.py`, `tests/cli/test_library_actions.py`, `tests/application/test_acquisition_staging.py`, `tests/application/test_inspection.py`; mypy obu platform.

**A6. Instrukcje, dokumenty i `selection_union`** (F-10, F-12, F-13) — S

- `cli/AGENTS.md`: P08, `--resident`, kontrakt timeoutu po A1.
- `anishift/AGENTS.md:9`: dopisać `torrents` i `catalog`.
- `application/AGENTS.md`: przycięcie i ujednolicenie języka wg skilla `agents-md`; zdanie o `ADMITTED` (`:253-256`) poprawione zgodnie z F-13; opis wyboru plików (`:198-199`) zgodny z F-12.
- `selection_union`: wariant według pytania 6 w §6.
- `outcomes/e2.md`: tabela ról, autor F4. `masterplan.md:41`: D5.
- Dowód: przegląd przez inny model; zgodność z kodem sprawdzona grepem cytowanych symboli.

### Etap B — decyzja planu E3

**B1. Granica projekcji stanu odcinków** (F-11) — decyzja, nie osobny refaktor.

Plan E3 rozstrzyga, gdzie powstaną nowe stany subskrypcji. Wydzielenie wymaga jawnych wejść:
- zakończone grupy runów (dziś `_succeeded_groups` pod `_progress_lock` z cache);
- `_ready_problems`;
- oferty sesji;
- lista subskrypcji;
- wynik `_replacement_ready`.

Jeśli E3 tego nie potrzebuje, projekcja zostaje w ownerze. Ewentualny pierwszy krok to czysty podzbiór z `automation.py:4061-4070`.

### Etap C — w E3: tylko to, co wymusza migracja

**C1.** E3 usuwa z UI pomost `G` i drogę grup (`masterplan.md:42`). Z zaplecza (F-08) usuwa tylko to, czego wymaga przeniesienie starych subskrypcji. Nie da się tego dziś wyliczyć, bo zależy od projektu E3, więc lista należy do planu E3.

### Etap D — w E5: stare zaplecze i legacy daemon

**D1.** Zgodnie z masterplanem (`masterplan.md:32, 44, 115-118`):
- reszta z F-08: `ResidentSession.search/download/follow`, `validate_deletion` (jeśli nadal nieużywane), `catalog_releases`, `order_groups`, `acquisition.download` dla grup;
- F-09: `run_daemon`, plik `stop`, `batch_command`/`spawn_window`, `watch batch`, flagi `--resident`.

Ryzyko: zewnętrzne skróty albo zadania wywołujące stare flagi. `autostart.py` używa `resident_command()`; trzeba sprawdzić istniejące zadanie `AniShift Watch` u właściciela. Wielkość S/M.

### Odrzucone

- Kosmetyka typu `del episode` w `_ordered_episode_notice` (`anime.py:995-997`): znika przy A2 albo nie ma wpływu.
- Zamknięty enum w polach `reason` (F-03): łamie odczyt historycznych receipts przy `strict=True`.
- Ogólny podział `AutomationOwner` „dla rozmiaru” (F-11): brak zmiany, którą by uprościł; projekcja zależy od stanu pod blokadą.
- Podział `anime.py` i `state.py`: brak findingu poprawności.
- Zmiana `source_is_available` na `FILE_SHARE_DELETE`: zachowanie jest zamierzone, a problem leży w teście (A3).
- Łączenie `_ready_result_missing` z kontrolą stempli publikacji (F-06): to dwa różne pytania.

## 5. Kolejność

1. A1 i A2 przed E3. A1 zmienia kontrakt kanału, na którym E3 zbuduje kolejne polecenia; A2 ustala mechanizm etykiet, który E3 rozszerzy.
2. A3 równolegle z A1/A2 (inne pliki). A4 po A3.
3. A5 po A2, bo oba dotykają `automation.py`.
4. A6 na końcu etapu A, żeby opisać stan po zmianach.
5. B1 i C1 w planie E3. D1 w E5.

Każdy etap to osobny commit; autor i recenzent pochodzą z różnych rodzin modeli (AGENTS); bramki z `AGENTS.md` przed commitem.

## 6. Pytania do właściciela

1. **Zakres przed E3.** Rekomendacja: A1–A6. Minimum: A1, A3, A6.
2. **A1: timeout zamyka kanał** zamiast czytać i porzucać spóźnioną ramkę. Zmienia to kontrakt z `tests/cli/test_resident.py:309`. Rekomendacja: zamykać, bo jest prościej, a odzysk wyniku przez receipt i ten sam `command_id` już istnieje.
3. **A2: krótka etykieta `episode_in_progress`.** Rekomendacja: „W toku”; wskazówka o C tylko w komunikacie.
4. **Kolejność sprzątania.** Rekomendacja zgodna z masterplanem: w E3 tylko to, co wymusza migracja subskrypcji, a stare zaplecze i legacy daemon w E5. Czy chcesz przesunąć któreś usunięcie wcześniej?
5. **D1: testy porównawcze ze starą pętlą.** Czy są jeszcze potrzebne do E5?
6. **`selection_union` (F-12).** Rekomendacja: usunąć funkcję i jej testy, a w AGENTS opisać rzeczywistą ochronę, czyli porównanie rewizji mapy plików. Alternatywa: użyć `selection_union` w `_apply_selection`, co da dodatkową walidację ścieżki i rozmiaru kosztem zmiany produkcyjnej ścieżki.
7. **Strażnik maszynowy.** Test pokrycia etykiet z A2 to nowy strażnik w rozumieniu AGENTS. Zgoda?

### Decyzje orkiestratora (delegacja właściciela 2026-10-02, do potwierdzenia)

Właściciel polecił kontynuować bez pytań. Przyjęto rekomendacje: 1 — A1–A6 przed E3; 2 — timeout zamyka kanał; 3 — „W toku”; 4 — kolejność zgodna z masterplanem; 5 — testy porównawcze starej pętli zostają do E5; 6 — usunąć `selection_union` i opisać ochronę rewizją mapy plików; 7 — test pokrycia etykiet jako zwykły test jednostkowy w `tests/cli/`, bez hooka; zamiana na strażnika wymaga zgody właściciela. Recenzja `astra` (FAIL → PASS) zamknięta.

## 7. Niepewności

- F-01 odtworzył recenzent; w tej wersji nie powtarzałem próby.
- Przyczyny `test_locked_publication_…`, `test_selected_pack_…` i `test_material_identity_…[True]` są hipotezami. Dla `test_selected_pack_…` nie znamy kodu błędu `udp.bind`.
- Przyczyna `test_private_clients_…` wynika z kodu i logu z outcome; nie uruchamiałem tego testu w tym audycie.
- Zgłoszony przypadek AniList `212888` → `no_suggestion` nie ma fixture w repo (grep `212888` w `tests/` i `docs/work/acquisition`: 0 trafień). Bez sieci go nie badałem.
- Nie zbadałem, czy stan `UNCERTAIN` poprzedniego transferu może współistnieć z równoległym stagingiem nowego (`waiting_previous_transfer`, `automation.py:4068`).
- Nie szukałem scenariusza, w którym zgodność rewizji mapy plików nie wystarcza bez `selection_union` (F-12).
- mypy i pełny `pytest` nie zostały uruchomione w tym audycie.
