---
kind: review
status: fail
reviewed-state: PR #72, commit f80ff9f na `origin/work/application/02-resumable-runs`, `git diff 0759e04 f80ff9f`
date: 2026-10-25
---

# Review: PR #72 — sprzątanie stagingu zleceń, których nie da się wznowić

## Zakres

- przedmiot: commit `f80ff9f` — `anishift/application/automation.py` (konstruktor `AutomationOwner`, nowy `_resumable_run`, `_retry_proposal`) i test `test_restarted_owner_removes_staging_of_runs_that_cannot_resume` w `tests/application/test_automation.py`
- baseline: `origin/main` `0759e04`
- authority: kontrakt z briefu (zlecenia wznawialne — przerwane `ACCEPTED`/`RUNNING`, `PAUSED`, `FAILED`/`PARTIAL` z ważnym dziennikiem — zostają nietknięte; przejściowy błąd I/O nie może kasować; `_resumable_run` jest jedyną definicją; cleanup po zdobyciu blokady), `AGENTS.md` (root, `anishift/`, `anishift/application/`, `tests/`), skill `simple`, `coding/references/python.md`
- ryzyka: nieodwracalne usunięcie stagingu wznawialnego zlecenia, kolejność cleanup względem recovery, inne procesy bez żywego PID, test niezdolny wykryć regresji
- poza review: pełny suite, mypy `--platform linux`, zachowanie runtime u właściciela

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** `_resumable_run` traktuje każdy `OSError` (i każdą chwilową niedostępność wejścia) przy odczycie dziennika jako „nie da się wznowić”, a konstruktor od razu i nieodwracalnie kasuje wtedy katalog `temp/run-*`. Odtworzyłem to dwoma testami roboczymi: po przejściowym `PermissionError` i po chwilowym zniknięciu źródła dziennik znów się wczytuje, a stagingu już nie ma. Kontrakt wprost tego zabrania. Sama refaktoryzacja `_retry_proposal`, kolejność względem blokady i `_restore_runs` oraz ochrona `ACCEPTED`/`RUNNING`/`PAUSED` są poprawne.

## Findings

### Krytyczne

#### Przejściowy błąd odczytu albo chwilowo niedostępne wejście kasuje staging wznawialnego zlecenia

- miejsce / scenariusz: `anishift/application/automation.py:1307-1314` (`_resumable_run`: `except AniShiftError, OSError, ValueError: return False`) w połączeniu z `automation.py:839-849` (wynik od razu trafia do `cleanup_orphaned_temp`). `RunJournal.load` (`anishift/application/recovery.py:115-130`) robi `stat` każdego wejścia i wyjścia przez `_proof` (`recovery.py:293-298`) i czyta plik dziennika. Każdy `OSError` po drodze, np. `PermissionError` przy pliku zablokowanym na Windows, `FileNotFoundError` źródła zewnętrznego na odłączonym dysku albo udziale sieciowym (ścieżki zewnętrzne są dowolne: `anishift/application/inspection.py:221-248`), albo źródło chwilowo przeniesione przez użytkownika, daje `False`. Katalog z markerem martwego PID jest wtedy usuwany (`anishift/config/workspace.py:183-212`). Drugi wariant tej samej przyczyny znam tylko z odczytu kodu: przy awarii między `ReadyStore.execute` a `RunJournal.relocate` w `_record_ready` (`automation.py:7399` w `_move_ready`, `automation.py:7417` i `7316-7324` w `_record_ready`) ukończona grupa zlecenia `PARTIAL` leży już w `ready/`, ale dziennik nie jest jeszcze przepięty. Przy następnym starcie cleanup w konstruktorze biegnie przed dokończeniem relokacji (`automation.py:827-829` tylko wczytuje `pending()`), więc `validate_inputs` zawodzi i staging grupy nieudanej znika.
- dowód: DIRECT. Robocze testy w scratchpadzie (poza repo) na helperach z `test_automation.py`:
  - `test_journal_read_permission_error` — przy `RunJournal.load`, który raz rzuca `PermissionError`, po konstrukcji ownera `run_temp_dir(..., "run-failed")` nie istnieje, choć zwykły `RunJournal.load` zaraz potem się udaje;
  - `test_source_temporarily_absent` — źródło przeniesione na czas konstrukcji i oddane: dziennik wczytuje się poprawnie, staging usunięty.

  Oba przechodzą, czyli kasowanie zachodzi. Na `0759e04` ten katalog przetrwałby, bo chronione było każde zlecenie inne niż `SUCCEEDED`. To więc regresja tego PR. Wariant z relokacją: ASSUMED, wynika z kodu, nie odtwarzałem go.
- wpływ: `_completed` zapisuje w dzienniku dowody plików pośrednich ze stagingu (`recovery.py:317-328`), a `validate_outputs` ich wymaga, dopóki plan ma taski (`recovery.py:132-144`). Po skasowaniu katalogu dziennik nie wczyta się już nigdy, ukończone płatne kroki (tłumaczenie, TTS) przepadają, a `_retry_proposal` spada na lokalną przebudowę od zera. Skutek jest nieodwracalny. Prawdopodobieństwo jest niskie, ale okno otwiera się przy każdym starcie rezydenta, czyli co najmniej przy każdym restarcie PC.
- minimalna reakcja: (DESIGN FLAW, decyzja orkiestratora lub właściciela) predykat cleanupu musi odróżniać „na pewno martwe” od „nie wiadomo” i przy „nie wiadomo” zachować katalog. Pewnie martwe: brak pliku dziennika, nieparsowalny dziennik albo nieobsługiwana wersja, `ExecutionError` z niezgodnym dowodem istniejącego pliku. Niepewne: każdy inny `OSError`, brak wejścia spoza workspace, grupa z oczekującą relokacją. `_retry_proposal` może dalej używać ostrożnego „nie oferuj wznowienia przy błędzie”, więc potrzebny jest wynik trójstanowy albo osobny wariant dla cleanupu. Do tego test z `PermissionError` i z oczekującą relokacją. Do rozstrzygnięcia przez właściciela: czy źródło usunięte z workspace (przypadek „Dead” z testu PR) ma być kasowane od razu, czy po N startach albo po czasie.

### Poważne

Brak.

### Mniejsze

#### Test nie chroni najważniejszej klasy retencji: przerwanych `ACCEPTED`/`RUNNING`

- miejsce / scenariusz: `tests/application/test_automation.py:2632-2664`. Scenariusze to tylko `FAILED` z martwym źródłem, `PAUSED` i `FAILED` z ważnym dziennikiem.
- dowód: DIRECT. To jedyny test ownera, który symuluje martwy PID (`git grep _process_is_running` w `tests/`: ten test i `tests/workspace/test_temp_lifecycle.py`). Pozostałe testy recovery piszą marker z PID bieżącego procesu, a ten jest zawsze „żywy” (`workspace.py:251-252`), więc nie wykryją skasowania. Gdyby ktoś usunął z `automation.py:842` warunek stanu, `PAUSED` dalej przechodziłby przez `_resumable_run`, a `ACCEPTED`/`RUNNING` z nieważnym dziennikiem, które `_restore_runs` musi zobaczyć, zostałyby skasowane bez czerwonego testu. Mój roboczy test macierzy stanów potwierdza obecne zachowanie: `accepted`/`running` zachowane, `cancelled`/`partial` z martwym dziennikiem/`succeeded` usunięte.
- wpływ: regresja prowadząca do utraty przerwanej pracy przeszłaby bramki. Brakuje też przypadków `PARTIAL` i przejściowego błędu (por. finding krytyczny).
- minimalna reakcja: sparametryzować test o `ACCEPTED`/`RUNNING` z nieważnym dziennikiem (oczekiwane: zachowany), `PARTIAL` z ważnym dziennikiem (zachowany) i `CANCELLED` (usunięty).

#### Literał stanów aktywnych powiela istniejącą stałą `_ACTIVE_STATES`

- miejsce / scenariusz: `automation.py:842` `{RequestState.ACCEPTED, RequestState.RUNNING, RequestState.PAUSED}` wobec `_ACTIVE_STATES` w `automation.py:615-618` („Request states that still own their groups”).
- dowód: DIRECT, odczyt kodu.
- wpływ: reguła „Reuse przed nowym kodem” z `AGENTS.md`. Dwie kopie tej samej wiedzy mogą się rozjechać.
- minimalna reakcja: `item.state in _ACTIVE_STATES or self._resumable_run(item)`.

#### Nieodwracalne usunięcie stagingu nie zostawia śladu w logu

- miejsce / scenariusz: `automation.py:846-849`. Wynik `cleanup_orphaned_temp` (krotka usuniętych katalogów, `workspace.py:183`) jest odrzucany, logowana jest tylko porażka.
- dowód: DIRECT, odczyt kodu.
- wpływ: `AGENTS.md` wymaga strukturalnego logu granic operacji i recovery. Gdy właściciel zgłosi utratę wznowienia, nie da się ustalić, że katalog usunął start rezydenta.
- minimalna reakcja: `logger.info(..., removed=len(removed))` bez ścieżek absolutnych.

### Sugestie

- Retencja jest szersza niż osiągalność (ASSUMED, nie odtwarzałem). `_retry_proposal` bierze tylko najnowsze zlecenie grupy (`automation.py:7916-7918`), a `_resume_preview` najnowsze z dokładnym zbiorem grup (`automation.py:3030-3041`). Starsze `FAILED` z ważnym dziennikiem, wyparte nowszym zleceniem tej samej grupy, zostaje chronione bez ścieżki wznowienia. To kierunek bezpieczny, ale część wycieku zostaje.
- Kontrakt „jedyna definicja” jest spełniony tylko częściowo. `_resume_preview` (`automation.py:3036`) ma własny zbiór `{PARTIAL, FAILED, PAUSED}`. Nie jest to błąd, bo dziennik waliduje później `_plan` (`automation.py:3160`), ale te dwa miejsca warto zbliżyć.
- `CANCELLED` nie ma ścieżki wznowienia w produkcie. Surowe IPC `preview` przyjmuje jednak `resume_run_id` z payloadu (`automation.py:3127`), a `_admit` odrzuca tylko `SUCCEEDED` (`automation.py:3324-3326`). Żaden klient tego nie wysyła (jedyny producent to `resume_preview` w `anishift/cli/resident.py:415`). Jawne odrzucenie `CANCELLED` w `_admit` domknęłoby kontrakt.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
| --- | --- | --- |
| Przerwane `ACCEPTED`/`RUNNING` zachowane dla `_restore_runs` | pass | `automation.py:842`; roboczy test macierzy stanów: zachowane przy martwym źródle |
| `PAUSED` zachowane | pass | `automation.py:842`; test PR, asercja `run-paused` |
| `FAILED`/`PARTIAL` z ważnym dziennikiem zachowane | fail przy przejściowym błędzie | finding krytyczny, dwa robocze testy |
| Przejściowy błąd I/O nie kasuje | fail | `automation.py:1312-1313` + robocze testy |
| `_retry_proposal` zachowuje dotychczasowe zachowanie | pass | diff: ten sam warunek stanów i ta sama obsługa wyjątków, wyniesione do helpera |
| `CANCELLED` bez ścieżki wznowienia w produkcie | pass | `automation.py:3036`, `7929`, `7141-7151`; `cli/resident.py:415` |
| Cleanup po blokadzie, przed recovery | pass | `cli/watch.py:322` `lock.acquire()` przed `AutomationOwner(...)` w `watch.py:332`; `_restore_runs` biegnie później, a stany aktywne są chronione bez warunku na dzienniku |
| Błąd I/O cleanupu nie zatrzymuje rezydenta | pass | `automation.py:846-849` (`NotADirectoryError` i błędy `safe_rmtree` to `OSError`) |
| Reguły repo (typy, brak komentarzy, docstringi) | pass z uwagą | `retained: tuple[str, ...]`, prywatny helper bez docstringu, brak komentarzy; duplikat `_ACTIVE_STATES` (finding mniejszy) |
| Test wykrywa regresję i trzyma się konwencji | częściowo | `@pytest.mark.integration`, brak prozy, wykrywa brak cleanupu; luki opisane w findingu mniejszym |

## Regresje i integracja

- Inne procesy i PID. `anishift run --preset` (`cli/main.py:490-507`) i panel produkcyjny (`cli/main.py:176`, `resident=session`) wykonują pracę przez `ResidentSession`, więc katalogi runów niosą PID rezydenta. Własny PID jest zawsze „żywy” (`workspace.py:251-252`). Katalog bez markera albo z markerem niepełnym jest pomijany (`workspace.py:195-202`), a PID ponownie użyty przez inny proces chroni katalog, czyli działa w bezpiecznym kierunku. Lokalne `execute_plan` w panelu (`cli/interactive/app.py:845`) działa tylko przy `resident=None`, czego `main.py` nie robi.
- `_finish_run` (`service.py:584-587`) w bieżącej sesji dalej chroni każdy nieudany run z dziennikiem, także `CANCELLED`. Nowa reguła działa dopiero po restarcie.
- Wznowienie po skasowanym katalogu nie zawiesza się: `_admit` przekazuje `resume=... and run_temp_dir(...).exists()` (`automation.py:3399`). Run bez wyjść w stagingu rusza od zera, a run z wyjściami jest odrzucany przez `RunJournal.load`.
- Dług poza zakresem: `AppService._start_run` (`service.py:527-529`) w procesie innym niż rezydent nie zna jego retencji. Dziś nie ma takiego procesu produkcyjnego.

## Wykonane kontrole

```text
git rev-parse HEAD && git status --short
f80ff9feda03796ba911f1286d99baa2a43d657f, czysty checkout — testy biegły na stanie commita

uv run pytest tests/application/test_automation.py -k "restarted_owner_removes_staging or retry or resume" -p no:cacheprovider
29 passed in 6.95s, exit 0

robocze testy w scratchpadzie (poza repo), uv run pytest -c pyproject.toml --rootdir=. -n0 -p no:cacheprovider
test_repro_pr72.py: test_source_temporarily_absent, test_journal_read_permission_error — oba zielone, czyli staging usunięty, choć dziennik potem się wczytuje
test_repro_active.py (macierz stanów, martwe źródło): accepted kept=True, running kept=True, cancelled kept=False, partial kept=False, succeeded kept=False — 5 passed

uv run ruff check anishift/ tests/ --no-cache → All checks passed!
uv run ruff format --check anishift/ tests/ --no-cache → 675 files already formatted
uv run mypy anishift/application/automation.py tests/application/test_automation.py → Success: no issues found in 2 source files
```

## Niewykonane lub nierozstrzygające kontrole

- Wariant z oczekującą relokacją `ready/` nie był odtworzony. Opiera się na odczycie kodu (ASSUMED).
- Nie sprawdzałem, czy `os.stat` w CPython 3.14 na Windows 11 zwraca `OSError` dla pliku zablokowanego bez współdzielenia (zależy od `GetFileInformationByName` i fallbacku). Przejściowy błąd zasymulowałem `PermissionError`.
- Pełny `uv run pytest`, mypy całego pakietu i `--platform linux`: REPORTED w treści commita, nie uruchamiałem ich.

## Wymagana ocena człowieka

Nie dotyczy, zmiana nie ma części wizualnej.

## Ograniczenia review

- Ocena dotyczy commita `f80ff9f`. Po moich przebiegach testów inny agent zaczął zmieniać pliki robocze (`discovery.py`, `workflows.py`, `paths.py`), ale wszystkie testy i bramki biegły wcześniej, na czystym checkoucie przy HEAD `f80ff9f`. Robocze testy korzystały z prywatnych helperów `test_automation.py` i monkeypatcha `_process_is_running`.
- Brak findingu w innych ścieżkach nie dowodzi, że innych błędów nie ma.

## Zalecany następny krok

- Orkiestrator lub właściciel rozstrzyga regułę „na pewno martwe” wobec „nie wiadomo” (finding krytyczny). Autor potem poprawia predykat cleanupu, rozszerza test o `PermissionError`, `ACCEPTED`/`RUNNING`, `PARTIAL` i `CANCELLED`, podmienia literał na `_ACTIVE_STATES` i dodaje log liczby usuniętych katalogów. Na końcu weryfikacja przez świeżego recenzenta.
