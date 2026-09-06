---
kind: plan
status: replan-required
baseline: 369efcd (main 6eef7d1)
created: 2026-09-05
branch: work/automation/01-folder-watch
---

# Plan 01: obserwowanie folderu bez pobierania

## Aktualny punkt wejścia

Aktualna wizja rozdziela kontrolowane przyjęcie pliku (A01) i obserwowanie
obcych zapisów (A12). Ten dokument opisuje wcześniejszy wariant watchera;
nie jest warunkiem pobierania. Przeplanować według [masterplanu](../masterplan.md)
przed implementacją. Minimalna ochrona danych i pojedynczego writera pozostaje.

Właściciel doprecyzował import przez terminal: aplikacja sama kopiuje plik,
więc zna gotowość. [Research importu i Stremio](../import-and-stremio.md)
rozdziela ten przypadek od watchera. Przed wykonaniem tego planu wyodrębnić
mniejszą iterację importu U11; poniższy projekt dotyczy nadal obserwowania
zewnętrznych zapisów, nie importu kontrolowanego. Nie wdrażać klawisza A
jako wymogu dla kopii wykonanej przez AniShift.

## Cel

Po jawnym włączeniu obserwowania gotowy plik w bibliotece uruchamia wyłącznie
należącą do niego pracę przez istniejący planner i scheduler. Restart,
ponowne zdarzenie, własny produkt i drugi proces AniShift nie tworzą drugiego
zlecenia tej samej wersji wejścia.

## Rezultat użytkownika

Ustawienia dostają przełącznik „Obserwuj bibliotekę”. Gdy jest włączony,
widok Auto po zakończeniu bieżącej kolejki nie wraca do Home, lecz pokazuje
wiersze rejestru w stanach: wykryte, gotowe, w toku, ukończone, nieaktualne,
pominięte, błąd, przerwane. Klawisze: `A` akceptuj wykryty plik, `P` pauza
przyjmowania, `S` pomiń, `R` ponów, `Esc` anuluj bieżące, `W` wyłącz. Każdy
ma widoczny skutek w wierszu i stopce. Bez piątej akcji Home.

## Warunki końcowe

- [ ] F01: zdarzenie pliku planuje tylko grupę tego stemu przez `plan_auto([group_id])`.
- [ ] F02: plik bez sygnału gotowości (przekazanie z Planu 02 albo `A`) nie jest planowany; nazwy tymczasowe są ignorowane.
- [ ] F03: ta sama `input_version` ze stanem `done` nie startuje; własny produkt i `.tmp` publikacji nie tworzą wpisu; po restarcie osierocone `running` staje się `interrupted` dopiero po bezpiecznym przejęciu lease.
- [ ] F04: stan w `config/watch/`, blokady w `workspace/temp/`; w bibliotece nic poza produktami.
- [ ] F05: pauza, anulowanie i wyłączenie to trzy klawisze i trzy stany.
- [ ] F06: wykonanie przez `execute_plan`; zero nowych handlerów.
- [ ] O05: przy pierwszym włączeniu istniejące grupy dostają `seen`.
- [ ] Drugi proces AniShift: drugi watcher odmawia startu; Manual/Auto w drugim procesie odmawia startu wykonania, gdy pierwszy trzyma blokadę root.

## Nie-cel

Pobieranie, subskrypcje, obserwowanie po zamknięciu programu, inspekcja
przyrostowa, heurystyka gotowości (O11), nowe zależności.

## Authority i baseline

Specyfikacja F01–F06, O01, O02, O05; `research.md`; root i `anishift/cli`,
`application`, `config`, `tests` AGENTS. Baseline `main` `6eef7d1`; znane
failures: dwa testy sztywnej listy stylów.

## Stan aktualny i gap

Discovery skanuje płasko, planner planuje komplet, `RunSession` chroni katalog runu, a `_claim_run`
chroni wykonanie instancji serwisu, `group_id` zależy tylko od stemu, cache
inspekcji nie zna ukończeń. Brak: tożsamości root, blokady systemowej,
rejestru, filtra zdarzeń, preflightu dla podzbioru, widoku ciągłego.

## Eksperyment E01 (bramka przed kodem)

Pytanie: czy uchwytowa blokada biblioteki odmawia drugiemu procesowi
bez czekania i czy poprawnie zwalnia zasób? Przy przyszłej realizacji test
uruchamia wyłącznie własne krótkie procesy potomne w izolowanym katalogu.
Sprawdza normalne zwolnienie, konflikt, błąd wejścia do sesji oraz ponowne
przejęcie. Nie używa aplikacji, filmu ani procesów użytkownika.
Wymuszone zakończenie procesu produktu jest odłożone; ewentualny test śmierci
syntetycznego dziecka wymaga osobnego uzgodnienia zakresu.
Kandydat: blokada bajtowa Windows i flock POSIX; ustalić stały offset,
inicjalizację pliku, zamknięcie uchwytu w każdej ścieżce i brak unlink
zajętej blokady. Sieciowe katalogi i aliasy dysków nie mają domyślnej gwarancji.
Wynik oraz ograniczenia platform zapisać przed wdrożeniem watchera.

## Zakres

### In scope

Blokada root w `RunSession`, blokada watchera, tożsamość root, rejestr,
pętla pollingu, filtr zdarzeń, preflight grupy, przełącznik w Ustawieniach,
tryb ciągły w Auto.

### Forbidden

Drugi pipeline, rekursja do podkatalogów, zapis w `workspace/` poza `temp/`,
przenoszenie źródeł, automatyczne przetwarzanie istniejących grup przy
włączeniu, retry bez limitu, uruchamianie całego Auto po zdarzeniu, nowe
zależności, dopuszczenie równoległego Manual na tej samej bibliotece jako
„bezpiecznego fallbacku”, `repr` dataclass jako format trwały.

### Deferred

`watchfiles` po pomiarze, inspekcja przyrostowa, autostart, podfoldery,
heurystyka gotowości O11.

### Dozwolone decyzje lokalne

Nazwy modułów i klawiszy, interwał pollingu jako stała `Final`, układ
wierszy w widoku, dokładny podział testów.

### Zatrzymaj się i wróć po decyzję, gdy

E01 daje wynik negatywny; `discover()` na realnej bibliotece trwa dłużej niż
akceptowalnie dla pętli; zmiana `RunSession` wymagałaby zmiany kontraktu
`AppService.execute`.

## Target design

### Ownership

| Element | Odpowiada za | Owner stanu | Nie odpowiada za |
| --- | --- | --- | --- |
| `config/root_lock.py` NEW | blokada uchwytowa na pliku; `acquire(path) -> handle \| None`, `release` | plik blokady | polityka konfliktu |
| `application/sessions.py:RunSession` MODIFY | dodatkowo blokada `temp/.anishift-root.lock` na czas runu; konflikt → `RunConflictError` | root w czasie runu | rejestr |
| `config/watch_ledger.py` NEW | rejestr per root, kanoniczna serializacja, atomowy zapis jak `presets.py` | `config/watch/<root-key>.json` | decyzje produktowe |
| `application/watch.py` NEW | maszyna stanów: skan, filtr, wersje, wybór grupy | stan sesji watchera | planowanie i wykonanie |
| `AppService` KEEP | `discover`, `plan_auto`, `execute`, `cancel` | cache inspekcji, aktywny run | rejestr |
| `cli/run.py` MODIFY | `prepare_group_run(service, group_id, preset_id)` NEW obok `prepare_auto_run` | nic | UI |
| `config/user_settings.py`, `field_catalog.py` MODIFY | `watch_enabled: bool` w scope GLOBAL | preferencje | rejestr |
| `cli/interactive/app.py` MODIFY | tryb `WATCH` na regionach Auto, klawisze, pętla w tle | widok | stan zleceń |

### Tożsamość i blokady

- `root_key` = pełny SHA256 z `root.resolve()` po `casefold()`
  na Windows; plik rejestru `config/watch/<root-key>.json` zawiera także
  jawną ścieżkę root do odczytu przez człowieka. Klucz wpisu to `group_id`,
  ważny tylko w obrębie tego pliku.
- Blokada root `temp/.anishift-root.lock` jest brana w `RunSession.__enter__`
  po istniejącym `_claim_root` i zwalniana w `__exit__`; obejmuje Manual,
  Auto i watch, bo wszystkie przechodzą przez `AppService.execute`. Konflikt
  daje istniejący `RunConflictError` z komunikatem „inny proces AniShift
  wykonuje pracę w tej bibliotece”; UI pokazuje odmowę, nie czeka.
- Blokada watchera `temp/.anishift-watch.lock` trzymana przez cały czas
  obserwowania; drugi watcher odmawia. Rejestr zapisuje wyłącznie proces
  trzymający tę blokadę, więc jest jeden writer. `cleanup_orphaned_temp`
  pomija pliki, więc blokady go nie dotyczą.

### Source of truth

- wpis rejestru: `group_id`, `stem`, `state`, `input_version`, `preset_fingerprint`,
  `settings_fingerprint`, `run_id`, `pid`, `updated`, `message`; nagłówek
  pliku: `schema_version = 1`, `root`, `root_key`.
- `input_version` = SHA256 kanonicznego JSON manifestu wszystkich wybranych
  wejść grupy: nazwa względna, rozmiar, pełny SHA256 treści wideo i sidecarów.
  Hash liczyć strumieniowo w workerze, z postępem bajtowym i cancellation,
  po gotowości; nie w każdej iteracji skanowania. Zmiana podczas odczytu
  odrzuca manifest. Staty służą tylko do wykrywania potrzeby sprawdzenia,
  nie do dowodzenia równości treści. Zakończenie porównuje manifest użyty
  do planu z aktualnym; zmiana daje `stale`. Kontrakt producenta wymaga
  niezmienności gotowego wejścia podczas wykonania — nie obiecujemy ochrony
  przed dowolnym zewnętrznym writerem zmieniającym i odtwarzającym plik.
- `preset_fingerprint` = SHA256 kanonicznego JSON z `_encode_preset`
  (upublicznić jako `encode_preset`). `settings_fingerprint` = SHA256
  kanonicznego JSON jawnie wyliczonych pól `RunSettingsSnapshot` z listy
  `WATCH_SETTINGS_FIELDS` (profile, model, limity układu, polityki; bez
  sekretów). Kanoniczny JSON: `sort_keys=True`, `separators=(",", ":")`,
  zbiory posortowane, listy uporządkowane zachowują semantyczną kolejność. Zmiana odcisku ustawień nie startuje pracy; wiersz
  pokazuje „inne ustawienia”, ponowienie jest jawne.
- stany: `seen`, `detected`, `pending`, `running`, `done`, `stale`, `failed`,
  `skipped`, `interrupted`.

### Przepływ

```text
scandir root (bez rekursji)
-> odrzuć: katalogi, nazwy z kropką na początku, sufiksy .tmp/.part/.!qb/.crdownload,
   is_derived_product
-> mapa stem -> pliki źródłowe z input_stat
-> nowy stem lub zmieniony input_stat -> detected (bez startu)
-> sygnał gotowości: przekazanie z Planu 02 albo klawisz A -> policz input_version
-> input_version == wpis done -> pozostaje done; inaczej pending
-> pending i brak aktywnego runu i nie pauza -> discover() -> group_is_ready
-> plan_auto([group_id], preset) -> blokujący problem -> failed z komunikatem
-> execute_plan (RunSession bierze blokadę root) -> RunResult
-> porównaj manifest wejść planu z końcowym: zgodny + SUCCEEDED i komplet produktów -> done;
   niezgodny -> stale; PARTIAL/FAILED/CANCELLED nigdy nie stają się done
```

Jeden run naraz; kolejne `pending` czekają. Rename źródła = usunięcie
starego stemu i `detected` nowego. Usunięcie źródła w `detected`/`pending`
usuwa wpis; w `running` nie przerywa runu, wynik opisuje brak wejścia.
Usunięcie produktu przy `done` nic nie uruchamia; wiersz pokazuje „produkt
usunięty, ponów ręcznie”. Sidecar dodany po sygnale gotowości zmienia
`input_stat`, więc cofa do `detected`; sidecar dodany w trakcie runu daje
`stale`. Wpis `done` nigdy nie jest przepisywany na nową wersję na podstawie
starego `RunResult`.

### Edge cases i failures

| Przypadek | Oczekiwane | Dowód |
| --- | --- | --- |
| kopiowanie w toku, potem `A` za wcześnie | run kończy się błędem mediów → `failed` z komunikatem, brak auto-ponowienia; `A` na `failed` ponawia | automated + runtime |
| plik zarządzany przez pobieranie | blokada akceptacji A i heurystyki do przekazania z Planu 02 | automated |
| własny produkt i `.tmp` publikacji | brak nowego wpisu | automated |
| restart w trakcie runu | `interrupted` dopiero po przejęciu lease; PID nie jest dowodem śmierci | automated (syntetyczny zapis stanu) |
| drugi proces: watcher | odmowa z komunikatem | automated (dwa procesy w teście) |
| drugi proces: Manual podczas runu pierwszego | `RunConflictError` przed startem | automated |
| pauza | nowe `pending` nie startują, bieżący run kończy się | automated |
| anulowanie | `service.cancel(run_id)`, wpis `failed` „anulowano” | automated |
| wyłączenie | nie przyjmuje nowych; aktywny run kończy się lub jest jawnie anulowany; lease zwalnia dopiero po zapisie jego wyniku | automated |
| rejestr innego root | inny `root_key`, inny plik, brak kolizji stemów | automated |
| zmiana ustawień między runami | `settings_fingerprint` inny, brak startu, podpowiedź | automated |
| model przerwany w nieznanym momencie | kolejny jawny run może ponownie wołać model; nie obiecujemy dokładnie raz | dokumentacja |

### Zachowanie UI

Trzy regiony Auto bez zmian. Kolejka pokazuje wiersze rejestru posortowane:
w toku, gotowe, wykryte, błąd, nieaktualne, ukończone, pominięte, seen.
Postęp przez `RichRunProgress`. Stopka z klawiszami. Wejście: przełącznik
`watch_enabled` w Ustawieniach (istniejący edytor bool) i akcja Auto; przy
włączonym przełączniku Auto otwiera tryb ciągły. Pierwsze wejście najpierw
zapisuje istniejące grupy jako `seen`, bez uruchamiania pełnego Auto.
Wykonuje wyłącznie jawnie wskazane lub nowo potwierdzone grupy.

## Plan wykonania

1. Preflight: E01; przeczytać `discovery.py`, `service.py`, `sessions.py`,
   `run.py`, `app.py`, `presets.py`, `user_settings.py`; potwierdzić baseline.
2. `config/root_lock.py` NEW i rozszerzenie `RunSession`; testy
   `tests/config/test_root_lock.py` NEW z drugim procesem (`subprocess`)
   i `tests/application/test_sessions.py` MODIFY dla konfliktu root.
3. `config/watch_ledger.py` NEW z testami: strict keys, `schema_version`,
   kanoniczna serializacja stabilna między uruchomieniami, martwy PID,
   różne root.
4. `application/watch.py` NEW jako czysta maszyna stanów z wstrzykniętym
   skanerem, zegarem i hasherem; testy dla każdego wiersza tabeli bez I/O.
5. `cli/run.py:prepare_group_run` NEW z testem w `tests/cli/test_run.py`.
6. `watch_enabled`, pętla i widok w `app.py`; testy z realnym rendererem
   jak w Planie 04; aktualizacja `test_interactive_settings_layout.py`.
7. Pełne bramki repo, review, commity tematyczne ze scope z listy hooka.

**Checkpoint implementacji:** testy na syntetycznych grupach i mockowanym
wykonaniu: dodanie, gotowość, sidecar w trakcie (stan `stale`), drugi proces,
wyłączenie i ponowne wejście. Nie wymagać filmu, odsłuchu ani ręcznego
zabijania programu. Późniejszy odbiór UX uzgodnić oddzielnie.

## Strategia dowodu

Unit dla maszyny stanów, rejestru i serializacji; integration własnych
procesów potomnych i syntetycznego restartu; smoke `anishift --help`.
Koszt skanowania i pełnego hasha zmierzyć na przygotowanych danych,
nie na aktywnej bibliotece użytkownika.

## Dodatkowe granice wykonania

Rejestr ma jednego writera. Lease watchera pozostaje zajęty także podczas
finalizacji aktywnego runu po wyłączeniu obserwowania. Rekoncyliacja nie
opiera się wyłącznie na PID (możliwy reuse). Biblioteki sieciowe/aliasy,
niezgodny root w nagłówku i uszkodzony rejestr zatrzymują automatykę bez
nadpisywania danych.

Włączony watcher rezerwuje bibliotekę dla własnego procesu; start Manual/Auto
z innego procesu musi uwzględniać także ten lease, nie tylko chwilowy run lease.
Własny Manual ma pierwszeństwo przed pending watchera; jego wynik trzeba
przekazać temu samemu writerowi rejestru. Przed automatycznym startem następuje
ponowna kontrola wpisu i produktów pod lease. Nie obiecujemy, że ledger
odtworzy historyczne Manual wykonane poza obserwowaniem; pierwsze włączenie
oznacza zastane źródła jako `seen`.

Preflight, hash i inspekcja są poza wątkiem UI. Zmiana workspace wyłącza
przyjmowanie, kończy zapis poprzedniego root, potem otwiera osobny rejestr.
Kontrola akceptacji `A` odmawia dla plików z aktywnym wpisem acquisition.
O11 musi być zatwierdzone: ta wersja bez heurystyki jest kolejką z potwierdzeniem,
a nie obietnicą pełnego automatycznego rozpoznania dowolnej wrzutki.

## Stop

Zatrzymać, gdy O01/O02/O05/O11 nie są zatwierdzone, E01 jest negatywny, pomiar
`discover()` uniemożliwia pętlę, albo blokada w `RunSession` wymagałaby
zmiany kontraktu `AppService.execute`.
