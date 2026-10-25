---
kind: review
status: fail
reviewed-state: PR #73, `origin/work/application/03-tmp-staging` @ `d4653a7` (f80ff9f, 8d5ed37, 45d761a, 8a75dca, d4653a7), `git diff origin/main origin/work/application/03-tmp-staging`
date: 2026-10-25
---

# Review: PR #73 — staging `tmp`, retencja tylko wznawialnych zleceń, skrypt migracji

## Zakres

- przedmiot: cały diff PR #73. Kod produktu: `_resumable_run`/`_Resumability` i cleanup w konstruktorze `AutomationOwner` (`anishift/application/automation.py`), rename `temp` → `tmp` w `anishift/` i `tests/`, nowe reguły w `AGENTS.md`, skrypt `scripts/tmp/migrate_temp_to_tmp.py` i nowe testy w `tests/application/test_automation.py`.
- baseline: `origin/main`.
- authority: brief orkiestratora (4 kontrakty), `AGENTS.md` z brancha (nowa reguła „wycinanie raka”, katalogi trzyliterowe), `anishift/application/AGENTS.md`, `tests/AGENTS.md`, skill `simple`, `coding/references/python.md`, poprzednie review `docs/work/13-silent-stalls/review-pr72.md`, `docs/work/13-silent-stalls/diagnosis.md` (punkt 5).
- ryzyka: nieodwracalne usunięcie stagingu wznawialnego zlecenia, migracja niszcząca dane właściciela, pozostałości starej nazwy, testy niezdolne wykryć regresji.
- poza review: pełny `uv run pytest`, `mypy --platform linux`, zachowanie runtime rezydenta u właściciela (nie uruchamiałem go).

## Werdykt

**Status:** FAIL

**Najważniejszy powód:** kod produktu jest w zasadzie poprawny (zostają dwa mniejsze przypadki przejściowe). Skrypt migracji ma za to dwie udowodnione drogi do utraty danych. Obie przechodzą przez nową regułę produktu „brak pliku w workspace = DEAD”:

- skrypt zgłasza sukces (exit 0), choć dzienniki zostały nieprzepisane (E3);
- przerwanie w połowie zostawia czytelny `state.json` i dzienniki wskazujące nieistniejący `temp\` (E4).

W obu przypadkach następny start rezydenta uzna 18–22 wznawialne zlecenia za martwe i skasuje ich `tmp/run-*`. Obie poprawki są małe i dotyczą tylko skryptu. Osobno: pierwszy start po merge'u skasuje 21 katalogów (ok. 500 MB). Wśród nich jest 18 katalogów Solo Leveling, a diagnoza warunkowała ich usunięcie zgodą właściciela. Tej zgody nie znalazłem.

## Findings

### Krytyczne

Brak.

### Poważne

#### P1. Weryfikacja skryptu obejmuje tylko dzienniki, które sam przepisał, więc niedopasowana ścieżka workspace kończy się „sukcesem” i utratą stagingu

- miejsce / scenariusz: `scripts/tmp/migrate_temp_to_tmp.py:92` (`before` liczone tylko z `plan.journals`), `:179` (dopasowanie leksykalne `Path(value).is_relative_to(old)`), `:239-255` (`_verify` sprawdza tylko klucze `before`). Gdy `--workspace` ma inną pisownię niż ścieżki w dziennikach (8.3, `subst`, junction, inny korzeń), skrypt przenosi katalog i przepisuje `state.json`. Dzienniki zostają nietknięte, a weryfikacja przechodzi bez sprawdzenia czegokolwiek.
- dowód: DIRECT, eksperyment E3 na kopii. Dzienniki wskazywały długą ścieżkę kopii, a skrypt dostał `--workspace` w formie `C:\Users\MATTYM~1\...`. Wynik: `Verified: ... 0 checkpoints parse ...`, `Run checkpoints rewritten: files=0`, `exit=0`, katalog przeniesiony. Potem 22 dzienniki przestają się wczytywać (`FileNotFoundError [WinError 3]`), a `state.json` wczytuje się bieżącym kodem. Lustro logiki `_resumable_run` (`tools/classify.py`) daje `17 failed DEAD`, `5 partial DEAD` („missing under temp”). Ścieżka jest w workspace, więc konstruktor (`automation.py:848-864`) usunąłby te katalogi. Ten sam objaw wyszedł przypadkiem przy literówce w ścieżce (`files=0`, `exit 0`). Na prawdziwych dziennikach wszystkie 2150 ścieżek ma jedną pisownię (`C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\workspace`), więc przy podaniu tej ścieżki migracja przechodzi poprawnie (E1/E2).
- wpływ: nieodwracalna utrata ukończonych płatnych kroków przy błędzie operatora, podczas gdy skrypt deklaruje „Verified”. Prawdopodobieństwo jest niskie, skutek nieodwracalny, a skrypt biegnie raz na prawdziwych danych.
- minimalna reakcja: liczyć `before` dla wszystkich `runs/*.json`, a po migracji wymagać, żeby każdy wcześniej wczytywany dziennik nadal się wczytywał. Do tego odmowa, gdy planowany jest ruch katalogu, a żaden dziennik ani pole stanu nie pasuje do `<workspace>\temp`.

#### P2. Kolejność zapisów pozwala, żeby przerwanie w połowie skończyło się skasowaniem stagingu przy następnym starcie

- miejsce / scenariusz: `migrate_temp_to_tmp.py:216-230`. Kolejność to: rename katalogu, potem `state.json`, potem dzienniki. `:97` łapie tylko `Exception`, więc Ctrl+C (`KeyboardInterrupt`), zabicie procesu albo zanik zasilania pomijają rollback. Po przerwaniu między zapisem stanu a ostatnim dziennikiem stan jest poprawny, a część dzienników wskazuje nieistniejący `workspace\temp`. Ponowne uruchomienie odmawia (`_back_up`, `:208-209`), ale nic nie blokuje startu rezydenta.
- dowód: DIRECT, eksperyment E4 (`tools/crash.py`: `KeyboardInterrupt` przy 50. zapisie). Wynik: `tmp` istnieje, `state.json` wczytuje się `WatchStateStore` (168 zleceń), 150 dzienników się wczytuje, 18 zgłasza `FileNotFoundError`. Lustro `_resumable_run` daje `13 failed DEAD`, `5 partial DEAD` i 4 `RESUMABLE` z 22 wcześniej wznawialnych. Ponowne uruchomienie skryptu: `Refused ... a backup from an earlier attempt exists`, exit 1. Kontrolnie E5 (`PermissionError` przy 50. zapisie): rollback działa, hash drzewa identyczny, 168/168 dzienników nadal się wczytuje (inode zachowane).
- wpływ: jak w P1, ale wyzwala go awaria albo przerwanie w oknie około 1 s. Mało prawdopodobne, nieodwracalne.
- minimalna reakcja: najpierw dzienniki, potem rename katalogu, `state.json` na końcu. Bieżący kod odrzuca stan z `temp/.restore-…`: kopia stanu właściciela daje `ConfigError CONFIG_INVALID`, sprawdziłem to. Zapis stanu staje się więc punktem zatwierdzenia, a rezydent nie wystartuje na niedokończonej migracji. Rollback warto objąć `BaseException`.

#### P3. Pierwszy start po merge'u nieodwracalnie usunie 21 katalogów, w tym 18 Solo Leveling, bez odnotowanej zgody właściciela

- miejsce / scenariusz: `automation.py:848-864` na prawdziwych danych. `docs/work/13-silent-stalls/diagnosis.md:286`: „18 katalogów Solo Leveling | ~414 | tak, jeśli właściciel potwierdzi, że serial jest niepotrzebny”.
- dowód: DIRECT. `tools/classify.py` na kopii `state.json` i `runs/` czyta prawdziwe pliki, tylko do odczytu. Z 25 katalogów `workspace/temp/run-*`:
  - 21 z markerem martwego PID to `DEAD` („missing under <źródło w roocie>”): 18 Solo Leveling, Slime S04E01, Laid-Off Mage S01E02, Yasei 04;
  - `run-87a998bcfa11d10a` jest `RESUMABLE`;
  - 3 bez markera zostają (`workspace.py:195-202`).

  `du`: około 500 MB do usunięcia.
- wpływ: to zamierzony cel PR #72, ale diagnoza uzależniła część tego usunięcia od decyzji właściciela. Po starcie nie da się już ręcznie odzyskać opłaconych tłumaczeń ani TTS z tych katalogów.
- minimalna reakcja: (REQUIREMENT) potwierdzenie właściciela przed pierwszym startem albo ręczna kopia tych katalogów przed migracją.

### Mniejsze

#### M1. „Brakujące wejście w workspace = DEAD” obejmuje też chwilowe przeniesienie przez użytkownika

- miejsce / scenariusz: `automation.py:1328-1331`. Przykład: użytkownik zmienia nazwę folderu serii (ten sam inode) albo chwilowo przenosi plik przy wyłączonym rezydencie. Po powrocie nazwy `RunJournal.load` znów by się udało, a staging już nie istnieje. Przeniesienie przez samą relokację `ready/` jest chronione poprawnie: `pending()` znika dopiero po `RunJournal.relocate`, zapisie stanu i `acknowledge` (`automation.py:7438-7474`, `ready.py:255-257`).
- dowód: DIRECT, odczyt kodu. W `review-pr72.md` (finding krytyczny) to właśnie zostało do decyzji właściciela, a commit `8d5ed37` rozstrzyga je sam. Innego zapisu decyzji nie znalazłem. Na dziś wszystkie 21 werdyktów `DEAD` u właściciela to prawdziwe zniknięcia albo przeniesienia do `ready/`.
- wpływ: kontrakt mówi o „pewnym dowodzie”, a to jest dowód chwilowy. Zachowanie wszystkiego przywróciłoby jednak wyciek, który PR ma usunąć.
- minimalna reakcja: (REQUIREMENT) właściciel potwierdza regułę albo wybiera wariant zwłoki, np. N startów lub czas.

#### M2. `ExecutionError` „changed during validation” może wynikać z przejściowego `OSError`

- miejsce / scenariusz: `recovery.py:58-63`. `is_current()` zamienia `OSError` na `False`, a `:127-129` zamienia to na `ExecutionError`, który `automation.py:1334-1335` klasyfikuje jako `DEAD`. Pozostałe `ExecutionError` (niezgodny dowód, nieregularny plik, wersja, publikacja bez tożsamości) są trwałe. Dowód zawiera inode i `mtime_ns`, więc plik zmieniony po zapisie dowodu nigdy już się nie zgodzi. Także plik „jeszcze zapisywany”: zmiana jest trwała, a staging jest bezużyteczny dla produktu.
- dowód: DIRECT, odczyt kodu. Nie odtwarzałem.
- wpływ: niski, bo przy blokadzie rezydenta nikt nie pisze dzienników, ale to przypadek przejściowy wpadający w `DEAD`.
- minimalna reakcja: w `load` wołać `_revision` bez połykania `OSError` (zwykły `OSError` trafi wtedy do `UNKNOWN`).

#### M3. `except Exception  # noqa: BLE001` ma precyzyjną, równie bezpieczną alternatywę

- miejsce / scenariusz: `automation.py:1336`. Udokumentowane awarie `RunJournal.load` to `OSError` (oprócz `FileNotFoundError` obsłużonego wyżej), `ExecutionError` i `ValueError` (w tym `ValidationError`). Wszystkie poza `OSError` są już obsłużone. `except OSError as problem:` daje ten sam wynik dla realnych awarii. Nieoczekiwany błąd programistyczny (np. `StopIteration` z `next(...)` w `_reconcile_publication`, `recovery.py:261`) przerwałby wtedy konstruktor przed cleanupem, co też nie kasuje danych, tylko zatrzymuje start głośno. Dziś taki błąd jest maskowany ostrzeżeniem, a przy okazji `_retry_proposal` zaczyna połykać wszystko (wcześniej `AniShiftError, OSError, ValueError`).
- dowód: DIRECT, odczyt kodu, `coding/references/python.md:26` („`except Exception` tylko na granicy procesu z konkretną reakcją”).
- wpływ: kierunek bezpieczny dla danych, ale niezgodny z regułą repo i ukrywający błędy.
- minimalna reakcja: `except OSError as problem:` z tym samym ostrzeżeniem.

#### M4. Testy nie chronią dwóch gałęzi klasyfikacji

- miejsce / scenariusz: `tests/application/test_automation.py:2610-2743`.
- dowód: DIRECT, mutacje w eksporcie brancha (`git archive`), `pytest -k restarted_owner -n0`:
  - usunięcie warunku `relocating` → czerwony test relokacji;
  - `except Exception → DEAD` → czerwone oba warianty `cannot_be_read_now`;
  - „brak pliku poza workspace → DEAD” → wszystko zielone;
  - „`ExecutionError`/`ValueError` → UNKNOWN” → wszystko zielone.

  Brak też przypadków `CANCELLED`/`SUCCEEDED` (usuwane) i `PAUSED` z nieważnym dziennikiem. Konwencje są spełnione: `@pytest.mark.integration`, brak prozy, nazwy opisują scenariusz.
- wpływ: regresja kasująca staging przy odłączonym dysku ze źródłem zewnętrznym przeszłaby bramki.
- minimalna reakcja: dopisać przypadek źródła spoza workspace (oczekiwane: zachowany) i niezgodnego dowodu (oczekiwane: usunięty).

#### M5. Skrypt nie sprawdza prywatnego qBittorrenta ani torrentów w kliencie

- miejsce / scenariusz: `migrate_temp_to_tmp.py:72-75` bierze tylko `resident.lock`. qBittorrent startuje z breakaway i przeżywa rezydenta (`anishift/platform/AGENTS.md:7-9`). Klient pamięta absolutny `save_path` `...\workspace\temp\.acquisition\<op>\data`, a po migracji owner oczekuje `tmp` (`automation.py:6320`, `8818-8826` → `_SELECTION_MISMATCH`, odmowa zwolnienia poprzednika).
- dowód: DIRECT, odczyt kodu. Dziś `config/qbittorrent/qBittorrent/data/BT_backup` zawiera tylko `queue` i żaden proces qBittorrenta nie działa, więc u właściciela nie ma teraz skutku.
- wpływ: gdyby przed migracją w kliencie był torrent, jego transfer by utknął. Plików to nie kasuje.
- minimalna reakcja: odmowa przy żywym `manager.lock` albo niepustym `BT_backup` (poza `queue`), albo jawny warunek w instrukcji uruchomienia.

#### M6. Reguła nazewnicza katalogów nie jest domknięta

- miejsce / scenariusz: nowa reguła w `AGENTS.md` („Katalogi i ich identyfikatory … nie `temp`/`temporary`”). W kodzie zostają identyfikatory katalogów roboczych wewnątrz stagingu: `temporary_root` w `anishift/services/audio/types.py:176`, `anishift/services/composition/types.py:155`, `anishift/application/tts_handler.py:306` (`self._run_root / task.group_id / "audio"`), `runtime.py:311`. Test `tests/services/audio/test_audio_service_integration.py:113` używa `tmp_path / "temp"`. Do tego `anishift/platform/restore_worker.py:363` powiela wiedzę `RESTORE_STAGING_PREFIX` (`f"{TMP_DIRECTORY}/.restore-"`, bo `platform` nie importuje `application`). Stała mogłaby leżeć w `paths.py`.
- dowód: DIRECT, `git grep -n -i -E 'temp_|_temp|temp/|/temp|temporar|"temp"|\btemp\b' origin/work/application/03-tmp-staging -- anishift tests`. Pozostałe trafienia dotyczą czego innego: plików `.tmp` do zapisu atomowego, `tempfile`, `tempo`, `temperature`, `attempt`, „temporarily unavailable”, zewnętrznego `../mm_avh_working_space/temp`, nazw plików w testach (`temp.srt`), tytułu „Tempal”. Aliasów, stałych `legacy`, podwójnych ścieżek ani zgodności wstecznej dla katalogu stagingu nie ma. Wartość `WorkspacePlace` `"temp"` nie występuje w żadnym zapisanym dzienniku ani stanie.
- wpływ: drobna niespójność z regułą, którą PR sam wprowadza. Zakres reguły (czy obejmuje podkatalogi stagingu) rozstrzyga orkiestrator.
- minimalna reakcja: zmienić nazwę na `tmp_root` i przenieść prefiks restore do `paths.py` albo zawęzić brzmienie reguły.

### Sugestie

- Nieparsowalny dziennik albo nieobsługiwana wersja = `DEAD` (`automation.py:1334`). Zmiana schematu `ExecutionPlan`/`Artifact` bez podbicia `CHECKPOINT_VERSION` skasuje przy pierwszym starcie staging wszystkich nieudanych zleceń, a `anishift/application/AGENTS.md` każe nie usuwać dowodów recovery (downgrade). Warto rozważyć `UNKNOWN` dla błędu wersji i schematu.
- Skrypt przy błędnych ścieżkach mówi „Nothing to migrate” z exit 0, a przy nieistniejącym `--watch` tworzy tam `resident.lock` (zaobserwowane w scratchpadzie). Warto odmówić, gdy nie ma ani `state.json`, ani `workspace/temp`.
- Kolejność wdrożenia: nowy kod na niezmigrowanym stanie właściciela nie wystartuje, bo `WatchStateStore.load` daje `ConfigError CONFIG_INVALID` (sprawdzone na kopii). To bezpieczne zamknięcie, ale komunikat jest ogólny. Checkout właściciela stoi już na `d4653a7` z niezmigrowanym `workspace/temp` (rezydent i qBittorrent dziś nie działają, `Win32_Process`). Sekwencja: zatrzymanie → skrypt → start.
- Kopie produktu `state.json.bak`, `state.json.v*.bak` i `*-migration.bak` zachowują `temp/`. Ich ręczne przywrócenie po migracji da `CONFIG_INVALID`.
- Dług poza zakresem (ASSUMED przyczyna): `run-492cfbc8a5b59f22` (`PARTIAL`, Yasei 04). Grupa trafiła do `ready/`, ale jej dziennik zachował 3 taski, a `RunJournal.relocate` przepina tylko grupy bez tasków (`recovery.py:168-175`). Taki dziennik nigdy się już nie wczyta.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
| --- | --- | --- |
| K1: staging znika tylko przy pewnym dowodzie | pass z uwagami | `automation.py:1322-1343`; przejściowy `PermissionError` dziennika i wejścia → `UNKNOWN` (testy + mutacja M3); wyjątki: M1 (decyzja), M2 |
| K1: relokacja do `ready/` wyłączona | pass | `automation.py:848-850`; `pending` czyszczone dopiero po `relocate` + zapis + `acknowledge`; mutacja wykryta |
| K1: `ACCEPTED`/`RUNNING`/`PAUSED` zachowane, reuse `_ACTIVE_STATES` | pass | `automation.py:616-618`, `854`; test parametryzowany |
| K1: `except Exception` uzasadniony | częściowo | M3, precyzyjna alternatywa `except OSError` |
| K1: log liczby usuniętych katalogów | pass | `automation.py:863-864`, bez ścieżek absolutnych |
| K2: zero aliasów, `legacy`, podwójnych ścieżek | pass | grep po drzewie brancha; jedno źródło `TMP_DIRECTORY` (`paths.py:57`) |
| K2: identyfikatory katalogów po nowej regule | częściowo | M6 (`temporary_root`, duplikat prefiksu restore) |
| K3: skrypt nie niszczy danych | fail | P1 (E3), P2 (E4) |
| K3: rollback przywraca katalog | pass dla `Exception` | E5: hash identyczny, 168/168 wczytań; brak dla `BaseException` (P2) |
| K3: przepisanie nie trafia w ścieżki „podobne do temp” | pass | `tools/names.py`: `workspace\temp.mkv`, `temperature\…`, `Temp Series\temp\…`, `ready\temp\…`, `..\temp\…`, względne `temp/…` bez zmian; `workspace\TEMP\…` → `tmp` (Windows bez rozróżniania wielkości liter) |
| K3: idempotencja | pass | E1/E2: drugi przebieg „Nothing to migrate”, hash identyczny |
| K4: testy wykrywają regresje, konwencje | częściowo | M4; marker `integration`, brak prozy |

## Regresje i integracja

- Kolejność cleanupu: blokada rezydenta (`cli/watch.py:321`) jest brana przed `AutomationOwner(...)`, `pending()` relokacji jest wczytane przed klasyfikacją (`automation.py:836-838`), `_restore_runs` biegnie później. Bez zmian względem PR #72.
- `_start_run` (`service.py:527-529`) nadal sprząta z tym samym zbiorem `retained`. Werdykt `DEAD` z chwili startu działa więc także przy późniejszym starcie runu. Dotyczy to M1: gdy workspace był chwilowo niedostępny, katalog zniknie przy pierwszym runie po jego powrocie.
- Migracja względem produktu: rename na tym samym woluminie zachowuje `st_dev`/`st_ino`/`mtime_ns`, więc dowody `_FileProof` przeżywają (E2: 168/168, E5).

## Wykonane kontrole

```text
git fetch origin; git log origin/main..origin/work/application/03-tmp-staging
5 commitów zgodnych z briefem; HEAD checkoutu = d4653a7

git grep -n -i temp origin/work/application/03-tmp-staging -- anishift tests  (+ zawężenia)
1685 linii surowych; po odfiltrowaniu attempt/tempo/temperature/template/tempfile ~340, sklasyfikowane ręcznie (M6)

Eksperymenty na kopii (scratchpad review73/, kod skryptu i pakietu z git archive brancha, PYTHONPATH=src):
E1 kopia bez mediów, dzienniki z przemapowanym prefiksem: 96 + 10 pól stanu, 168 plików / 2150 pól, exit 0; drugi przebieg identyczny
E2 jw. + dowody plików przeliczone dla kopii: 168/168 dzienników wczytuje się przed i po, run_root → tmp
E3 --workspace w formie 8.3: files=0, exit 0, 22 dzienniki przestają się wczytywać, stan się wczytuje → 22 DEAD
E4 KeyboardInterrupt przy 50. zapisie: brak rollbacku, stan się wczytuje, 18 z 22 → DEAD; ponowienie odmawia
E5 PermissionError przy 50. zapisie: rollback, hash drzewa identyczny, 168/168
names.py: przepisanie ścieżek podobnych do temp (wynik w tabeli K3)
classify.py na prawdziwych danych (tylko odczyt): 21 DEAD z markerem, 1 RESUMABLE, 3 bez markera; ~500 MB
WatchStateStore.load(kopia stanu właściciela) kodem brancha → ConfigError CONFIG_INVALID

Mutacje w eksporcie brancha, pytest tests/application/test_automation.py -k restarted_owner -n0:
baza zielona; bez relocating → 1 FAILED; Exception→DEAD → 2 FAILED; zewnętrzny brak→DEAD → zielono; ExecutionError/ValueError→UNKNOWN → zielono

pytest tests/application/test_automation.py -k "restarted_owner or retry or resume" -p no:cacheprovider -n0
checkout (HEAD d4653a7, cudze niezacommitowane zmiany w planner/selection/media): 35 passed
eksport brancha bez external/: 1 failed (test_library_retry_after_refused_deletion_only_relocates, "External binary unavailable" — środowisko)

ruff check / ruff format --check anishift/ tests/ (eksport) → All checks passed / 675 files already formatted
mypy automation.py workspace.py test_automation.py migrate_temp_to_tmp.py → Success
gh pr view 73 → OPEN, headRefOid d4653a7, bez śladów AI
```

## Niewykonane lub nierozstrzygające kontrole

- Pełny `uv run pytest`, `mypy anishift/ tests/` i `--platform linux`: REPORTED w commitach, nie uruchamiałem.
- E2–E5 używają dowodów plików przeliczonych dla kopii. Na surowej kopii (E1) żaden dziennik nie wczytuje się ani przed, ani po migracji (inne inode), więc tam weryfikacja „loaded → loaded” jest pusta z natury eksperymentu.
- Rzeczywistego zabicia procesu ani zaniku zasilania nie symulowałem; E4 symuluje `KeyboardInterrupt` w `_write`.
- M2 tylko z odczytu kodu.

## Wymagana ocena człowieka

```text
Uruchom: nic. To decyzje przed pierwszym startem po merge'u.
Zrób: potwierdź (a) usunięcie 21 katalogów run-* (~500 MB), w tym 18 Solo Leveling (diagnosis.md:286),
      (b) regułę M1: brak źródła w workspace przy starcie = staging do usunięcia od razu.
Oczekiwany wynik: zgoda albo prośba o kopię katalogów / wariant zwłoki.
Zwróć uwagę na: usunięcia nie da się cofnąć; produkt i tak nie wznowi tych zleceń.
```

## Ograniczenia review

- W trakcie review inny agent zmieniał pliki robocze (`planner.py`, `selection.py`, `services/media/*`, testy). Kod czytałem przez `git show`/`git diff`, a eksperymenty i mutacje biegły na `git archive` brancha. Tylko jeden przebieg testów był w checkoucie z tymi zmianami.
- Narzędzia eksperymentów: `C:\Users\MattyMroz\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\b1c6e9d7-f377-43d2-802f-da71c0f1b1b3\scratchpad\review73\tools\` (`build.py`, `loads.py`, `classify.py`, `crash.py`, `names.py`).
- Brak findingu w innych ścieżkach nie dowodzi, że innych błędów nie ma.

## Zalecany następny krok

- Autor poprawia skrypt: weryfikacja wszystkich dzienników i odmowa przy zerowym dopasowaniu (P1), kolejność „dzienniki → rename → `state.json`” i rollback dla `BaseException` (P2), opcjonalnie warunek qBittorrenta (M5). Potem powtórka E3/E4 przez świeżego recenzenta.
- W kodzie produktu: M3 (`except OSError`), M2, testy z M4, decyzja co do zakresu M6.
- Właściciel rozstrzyga P3 i M1 przed pierwszym startem. Kolejność wdrożenia: zatrzymanie, skrypt na prawdziwych danych, start.
