---
kind: plan
status: accepted
baseline: commit zaakceptowanej dokumentacji E1 (następca 8fce119 na work/acquisition/01-episode-selection)
created: 2026-09-28
parent: plans/e1-wybor-odcinka.md
---

# Plan: integracja H1 v10.3 i nowa ścieżka Anime (reszta E1)

Plan wykonawczy faz 3–9 planu-rodzica [e1-wybor-odcinka.md](e1-wybor-odcinka.md) po przyjęciu H1 v10.3. Tam, gdzie plany się różnią, obowiązuje ten; różnice zebrano w §13.

## 1. Cel

Przenieść zamrożoną H1 v10.3 ze `scripts/tmp/` do `anishift/` bez zmiany jej semantyki. Dodać adaptery ani.zip i Torrentio (odcinki i filmy) oraz graf franczyzy AniList. Udostępnić nowe pod-operacje przez owner i IPC. Zbudować nową ścieżkę Anime: tytuł → wpisy → odcinki → sugestia i inne wydania. Bez pobierania.

## 2. Rezultat użytkownika

Właściciel wpisuje nazwę w Anime, wybiera tytuł, wpis franczyzy i odcinki (albo film). Po `D` widzi dla każdego odcinka sugerowane wydanie z Torrentio. Pod `I` ogląda pozostałe wydania z oceną `zgodny` / `niepewny` / `niezgodny` i polskim powodem. Stara lista wydań według grup jest pod `G` i nadal pozwala pobierać i subskrybować.

## 3. Warunki końcowe

- [ ] `anishift/application/episode_identity.py` zawiera H1 v10.3. **Bramka A:** `classify` i `classify_many` dają werdykt i `reason` identyczne z zamrożonym artefaktem na wszystkich 36 862 rekordach `working.json` i na `identity-231.json`, na wejściach bez dowodów (§10.1): 0 różnic.
- [ ] **Bramka B:** produkcyjny builder celu H1, uruchomiony przez parsery adapterów, i oryginalne `corpus_labels.py:project_title`, uruchomione na tych samych surowych źródłach, dają identyczny `target` (równość JSON razem z typami) oraz identyczny werdykt i `reason`. 0 różnic; raport podaje liczebność i pokrycie próby.
- [ ] H1 w produkcji dostaje wyłącznie `target` i `candidate`, bez dowodów (tryb egzaminu 2, §6, §9.3).
- [ ] Ranking: najpierw werdykt, potem klucz właściciela U-04/U-05/U-06/U-23 (rodzic §10.5.5). Sugestia według §9.5.
- [ ] Pod-operacje `franchise`, `episodes` i `offer` (także dla filmu) działają przez owner i IPC ze strict round-trip. Odpowiedź ponad limit ramki daje jawną odmowę, a połączenie nadal działa (§9.8).
- [ ] UI według `ux.md` §3–§6; wszystkie powody H1 mają polskie tłumaczenia (§9.7).
- [ ] Mechanizm regresji (§10.6) działa: stały fixture, wzorzec testu i pierwszy przypadek.
- [ ] Pomiar czasu oferty i etapów Q-05 zapisany (§10.4), bramki repo zielone, H1 z właścicielem zaliczone, `outcomes/e1.md` zamknięty (§12).

## 4. Nie-cel

Pobieranie, wybór pliku w paczce, subskrypcje nową drogą, H2, `decisions.jsonl` i `cases.jsonl` (E2/E3). Pełne Q-08, czyli ograniczanie widoków i list (E2). Strojenie i nowy egzamin H1. Dowody katalogowe w wejściu H1 (§6 Decyzja). Naprawa starej drogi pod `G` (D1). Wsparcie Linuksa.

## 5. Authority i baseline

| Źródło | Rola |
| --- | --- |
| `docs/session-logs/2026-09-28-2250-e1-h1-accepted-start-build.md` | decyzje z 28.09: v10.3 przyjęta, koniec strojenia, zasada regresji, skład wykonawców |
| [../masterplan.md](../masterplan.md) E1 | cel etapu, warunek wyjścia |
| [e1-wybor-odcinka.md](e1-wybor-odcinka.md) §10.1–§10.2, §10.4–§10.8, §15 D1–D6 | kontrakty, IPC, UI, edge cases, o ile §13 nie zmienia |
| [e1-heurystyka-wyszukiwarka-weryfikator.md](e1-heurystyka-wyszukiwarka-weryfikator.md) H-1..H-9 | H1 jako wyszukiwarka |
| [../spec.md](../spec.md) U-02..U-06, U-13..U-15, U-21, U-23, U-24, W-07, W-08, R-06, Q-05, Q-08 | wymagania |
| [../ux.md](../ux.md) §3–§6, §11–§14 | ekrany, teksty, klawisze, H1 |
| `AGENTS.md`: root, `anishift/`, `application/`, `cli/`, `platform/`, `services/catalog/`, `services/torrents/`, `tests/` | reguły i bramki |
| `scripts/tmp/episode_selection.py` (SHA `6a1fa8ef…936c`) | zamrożona H1, źródło portu |
| `scripts/tmp/corpus_labels.py:project_title` | zamrożony builder celu, wzorzec buildera produkcyjnego |

**Baseline wykonania:** commit, który utrwali zaakceptowaną dokumentację E1 (ten plan i zmiany w `masterplan.md`, `e1-wybor-odcinka.md`, `ux.md`) na `work/acquisition/01-episode-selection`, jako następca `8fce119`. Faza 0 zapisuje jego SHA. W `anishift/` nie ma jeszcze kodu E1. Ostatnie bramki (`outcomes/e1.md`, 27.09): ruff/mypy PASS, `pytest` 5214 passed / 18 skipped.

**Kopia zabezpieczająca:** `%USERPROFILE%\acquisition-labels\code-freeze-2026-09-28\`.

## 6. Stan aktualny

### Obecne zachowanie

- Anime: QUERY → TITLES → Enter → RESULTS, czyli Nyaa według grup (`acquisition.py:search_title`, `cli/interactive/anime.py`).
- `automation.py:_acquisition_command` obsługuje `titles`, `search`, `season`, `releases`. Każda inna operacja dekoduje `candidate` i kończy się błędem.
- `AutomationOwner._answer` łapie wyjątek polecenia, loguje `error_class` i odpowiada `INTERNAL` z `reason = failure_code(problem) or "command_failed"`.
- `platform/local_control.py`: odbiór ma limit `MAX_FRAME_BYTES = 1 MiB`, a `recv_bytes` ponad limit zrywa połączenie. `_ServedConnection.send` nie sprawdza rozmiaru, więc za duża odpowiedź zerwałaby połączenie klienta bez komunikatu.

### Luka

- H1 żyje tylko w `scripts/tmp/` (gitignored), bez testów w CI.
- Nie ma adapterów ani.zip i Torrentio ani grafu franczyzy.
- Cel H1 w korpusie budował kod badawczy (`corpus_labels.py:project_title`). Aplikacja musi zbudować ten sam cel ze swoich adapterów.

### Decyzja: wejście H1 bez dowodów (orkiestrator, 2026-09-28, ostateczna)

Tryb produkcyjny: `classify(target, candidate)` z `evidence = {}`. `target` to dokładnie wynik `project_title`, bez `year` i `seasonYear`.

- **Egzamin 2 szedł bez dowodów:** 0/3 911 rekordów z niepustym `archived_evidence` (w working 1 439/36 862). To jest tryb zwalidowany egzaminem 2.
- **Rok:** H1 czyta rok celu z `catalog.get("seasonYear") or target.get("year")` (`episode_selection.py:359–361`), a `catalog` pochodzi z dowodów. W egzaminie 2 H1 nie widziała więc roku celu. `target.seasonYear`, dopisany w egzaminie 2 przez prywatny finalize opiekuna, jest przez H1 nieczytany.
- **Kształt `target`:** oba zbiory zbudował `project_title`, klucze są identyczne: `absolute`, `aliases`, `episode`, `episode_title`, `local_episode`, `other_episode_titles`, `other_series`, `season`, `type`. Klucza `year` nie ma nikt.
- **Pomiar trybu z dowodami** (opiekun `sol6`, exam-v2, tylko agregaty, zamrożona H1, dowody odtworzone `e1_complete.evidence` z archiwum rezerwy):
  - 0 nowych błędnych `zgodnych`;
  - pokrycie `zgodny` **spada**: 303 → 301/646; 2021+: 96 → 92/138;
  - rekordy `poprawny`: `zgodny` → `niepewny` 69, `niepewny` → `zgodny` 23.
- Reguła wymagała wzrostu pokrycia, więc tryb z dowodami odpada. Pomiar na working jest zbędny, bo nie zmieni wyniku.

Historia decyzji (dotyczy wyłącznie odrzuconego trybu z dowodami): odtworzenie dowodów na working dało 2× `niepewny` → `zgodny` przy `label = błędny`. Chodzi o rekordy AniList 21804, odcinek 1: `9b61dec2bc2e501e2ecff85b2b4390af9668be0be5faa6af7e314101a304923c` i `fcc810892410b04a86cf4a2517599839a95208181ed3476fec5e2b3ce20df5eb`.

- Bez dowodów oba mają `niepewny` („Filename year is missing from or conflicts with runtime target metadata.”).
- Z dowodami rok 2016 i mapowanie S1E1 dają `zgodny`.
- Przyczyną jest numeracja katalogu (TV_SHORT, 120 segmentów) inna niż numeracja wydawcy, czyli domena H2 (D6), nierozpoznawalna z nazwy ani metadanych.

W trybie produkcyjnym te rekordy zostają `niepewne`.

### Istniejące elementy do użycia

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| H1 v10.3 | `scripts/tmp/episode_selection.py:classify`, `rank` (przygotowanie `_target` raz na listę) | logika tożsamości 1:1 | `_preference` nie wchodzi do portu (§9.5) |
| Testy H1 | `scripts/tmp/test_episode_selection.py` | testy klasyfikacji | testy `rank`, ewaluatora/podziału i budżetu czasu obsługuje §11 F1–F2 |
| Ewaluacja | `scripts/tmp/e1_heuristic_eval.py` (`WORKING_SHA`, grupowanie po `(target, evidence)`) | szkielet bramki A | tylko część robocza |
| Builder referencyjny | `corpus_labels.py:project_title`, `_episode_title`, `_verified_source`; `e1_franchise_probe.py:collect`, `traversal`, `query`, `CHAIN`, `LEAVES`, `FIELDS` | bramka B, semantyka celu | kod badawczy, import tylko w `scripts/tmp` |
| Franczyza w korpusie | `acquisition_probe.py:Probe.franchise` (`query(3)`, do 4 zapytań, kolejne ID z `traversal(...).missing`) | algorytm adaptera | jw. |
| Torrentio w korpusie | `acquisition_probe.py:candidate_records`, `episode_metadata = mapping["episodes"].get(str(number))`; wariant filmowy `stream/movie/kitsu:<id>.json` (N-04: kandydaci dla 19, 17 i 6 filmów) | parser, oba URL-e, numer lokalny | jw. |
| Fixture | `tests/fixtures/search/*`, `tests/fixtures/acquisition/identity-231.json` | adaptery, usługa, H1 | 231 ma kształt wejścia H1 |
| Aplikacja | `AniListCatalog`, `RequestControl`, `control_views`, `nyaa.py:USER_AGENT`, `WatchState.provider_locks`, `local_control._error_frame` | jak w rodzicu §10 | — |

### Dowody

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| Egzamin 2 v10.3: 0 błędnych `zgodnych` / 3 911; pokrycie `zgodny` 46,9% (2021+: 69,6%); `zgodny ∪ niepewny` 93–100% | `%USERPROFILE%\acquisition-labels\exam-v2\report-for-author.md` | verified |
| Egzamin 2 bez dowodów (0/3 911); pomiar z dowodami: pokrycie 303 → 301/646, 2021+ 96 → 92/138 | tamże, „Dowody w wejściu”, „Tryb z dowodami” (agregaty `sol6`) | verified (opiekun egzaminu) |
| Kształt `target` egzaminu 2 = `project_title` (+ nieczytany `seasonYear`), bez `year` | tamże, „Kształt target”; `episode_selection.py:359–361` | verified (opiekun, orkiestrator) |
| `project_title` potrzebuje: media wybranego wpisu (`id`, `format`, `title`), węzłów franczyzy (`id`, `type`, `format`, `title`, `startDate.year`, `relations`), `queried`, `franchise_complete`, `mapping.episodes` ani.zip, numeru lokalnego i `episode_metadata` | `corpus_labels.py:2025–2074`, `e1_franchise_probe.py:46–93`, `acquisition_probe.py:1685` | verified |
| Kandydaci w `working.json` mają tylko `filename`/`path`/`release`, więc `_preference` z `rank` nigdy nie był oceniany na danych | klucze `working.json` | verified |
| Graf S1 ma 25 węzłów przy 10 wpisach widoku, Diaries 8 przy 2 | pomiar astry na fixture | verified (review) |
| 16 powodów pochodzi z helperów konfliktów (`episode_selection.py:948`, `:955`), 1 189 rekordów working | review astry | verified |
| `slime-s4e23:12` w v10.3 → `niepewny / No selected file.` | review astry | verified |
| H1 dopuszcza `.avi`, `.ts` itd. (`VIDEO_EXTENSIONS`); U-06 wyklucza je z sugestii | `episode_selection.py:36` | verified |
| Klasyfikacja listy: pętla `classify` ~299 ms, przygotowanie celu raz ~252 ms (100 kandydatów, katalog 1 200 tytułów) | pomiar astry | verified (review) |

## 7. Zakres

### In scope

- Port H1 z `classify_many`, przeniesienie testów klasyfikacji, skrypty bramek A i B oraz pomiaru czasu w `scripts/tmp/`.
- Kontrakty i czyste funkcje: graf i widok franczyzy, lista odcinków, `identity_target`, fakty wydania, ranking, sugestia.
- Adaptery ani.zip i Torrentio (seria i film), `AniListCatalog.franchise`, dostawcy w `http_requests.py`, wspólny `USER_AGENT`, `ErrorCode.EPISODE_CATALOG_FAILED`.
- `AcquisitionService.franchise/episodes/offer` z pamięcią, pod-operacje ownera, `ResidentSession`, `bootstrap`.
- Kontrola rozmiaru odpowiedzi w `local_control._respond` (§9.8).
- UI Anime, termin po 429 przez `provider_locks` (D4), W-08 (D5).
- Regresja (§10.6), pomiar (§10.4), H1, `outcomes/e1.md`, scoped `AGENTS.md`.

### Out of scope

Wszystko z §4.

### Forbidden

- Zmiana semantyki H1: reguł, progów, normalizacji, kolejności decyzji, tekstów `reason`. Dozwolone są tylko zmiany z §9.2.
- Przekazywanie do H1 dowodów katalogowych (`evidence` inne niż puste), etykiet, provenance, ID rekordu, `info_hash`, list tytułów lub hashy. Dopisywanie do `target` kluczy spoza `project_title` (np. `year`, `seasonYear`).
- Ciche `niepewny` przy wyjątku programistycznym (§9.9).
- Odczyt lub ponowne użycie `exam`, `exam-v1`, `exam-v2` (poza `report-for-author.md`).
- Nowy magazyn danych; zapis stanu poza `provider_locks` (D4); zmiana `PROTOCOL_VERSION`; ciche obcinanie odpowiedzi IPC.
- Nowa zależność.
- Edycja zamrożonych skryptów `scripts/tmp/` (`episode_selection.py`, `test_episode_selection.py`, `e1_heuristic_eval.py`, `e1_complete.py`, `e1_finish.py`, `corpus_labels.py`, `e1_franchise_probe.py`, `acquisition_probe.py`, `e1_apply_disputes.py`). Nowe skrypty tylko je importują.
- Ścieżki z nazwą użytkownika w repo; sekrety w logach i dokumentach.

### Deferred

- `cases.jsonl`, przegląd tygodniowy, `decisions.jsonl` (E2/E3).
- Q-08 dla widoków, Historii i list subskrypcji (E2).
- Decyzja N-03 o pustych plikach stagingu (przed E2).
- Znane luki H1 z review v10.2: tylko przez §10.6, gdy wystąpią w praktyce.

### Dozwolone decyzje lokalne

Nazwy prywatne, podział helperów, teksty zgodne znaczeniowo z `ux.md`, stałe limitów pamięci, nazwy fixture, wielkość złotej próbki w granicach §10.5, tekst odmowy „za duża odpowiedź”.

### Zatrzymaj się i wróć po decyzję, gdy

- bramka A lub B daje różnicę;
- archiwalne odpowiedzi korpusu nie dają się podać parserom adapterów (inny kształt odpowiedzi), więc bramki B nie da się wykonać bez zmiany reguł buildera;
- franczyza Slime wymaga więcej niż 4 zapytań;
- na fixture Slime Diaries lub OAD dostają `match` przy celu S1E4 albo S1E4 nie dostaje `match`;
- potrzebna jest zmiana kontraktu spoza §9 albo nowa zależność.

## 8. Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | ten plan | kontrakt | full |
| 2 | `AGENTS.md` z §5 | reguły | full |
| 3 | `.agents/skills/coding/SKILL.md` + `references/python.md`, `testing.md`, `comments-docstrings.md` | standard | full |
| 4 | [e1-wybor-odcinka.md](e1-wybor-odcinka.md) §10.1–§10.8 | kontrakty i UI | sekcje |
| 5 | `scripts/tmp/episode_selection.py`, `test_episode_selection.py` | F1 | full |
| 6 | `corpus_labels.py:project_title`, `_episode_title`; `e1_franchise_probe.py`; `acquisition_probe.py:Probe.franchise`, `candidate_records` | F2–F3 | symbole |
| 7 | `platform/local_control.py:_respond`, `_ServedConnection.send`, `MAX_FRAME_BYTES` | F4 | symbole |
| 8 | [../ux.md](../ux.md) §3–§6, §11–§14 | F5 | sekcje |

## 9. Target design

### 9.1 Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `application/episode_identity.py` (NEW) | H1 v10.3: `IdentityVerdict`, `IdentityAssessment`, `classify`, `classify_many`, `REASONS` | ranking, I/O, budowę wejścia |
| `application/episode_selection.py` (NEW) | kontrakty E1, `franchise_view`, `episode_listing`, `identity_target`, `release_facts`, `rank_candidates`, `suggestion`; importuje z `episode_identity` | reguły tożsamości, I/O |
| `services/catalog/anizip.py` (NEW) | ani.zip → `AniZipMapping` | łączenie z harmonogramem |
| `services/torrents/torrentio.py` (NEW) | Torrentio seria/film → `StreamCandidate[]` | ocena, ranking |
| `services/catalog/anilist.py` | `franchise()` → `FranchiseGraph` | projekcję widoku |
| `application/acquisition.py` | I/O, pamięć grafu, listy i widoku (rodzic §10.5.2 pkt 6–7), wybór serii/filmu | logikę wyboru |
| `application/automation.py` | pod-operacje pod `requests("user")` | — |
| `platform/local_control.py` | jawna odmowa zamiast ramki ponad limit | ograniczanie treści widoków (E2) |
| `cli/resident.py`, `cli/interactive/anime.py`, `state.py` | klient IPC, ekrany, `provider_locks` → Anime | sieć w renderze |

Oba nowe moduły aplikacji są czyste i trafiają do `_PURE_MODULES`: `episode_identity.py` w F1, `episode_selection.py` w F2, bo strażnik wymaga istnienia pliku (`test_architecture.py:99–102`). H1 ma osobny moduł, bo zmienia się tylko przez zasadę regresji. Kierunek importu: `episode_selection` → `episode_identity`, nigdy odwrotnie.

### 9.2 Port H1 (`episode_identity.py`)

Kopia v10.3 wyłącznie z tymi zmianami:

- `from __future__ import annotations` zostaje — mają go wszystkie moduły `application/` i ruff `FA` (sprawdzone w F1);
- `Verdict` zamieniony na `IdentityVerdict(StrEnum)` w tym module: `MATCH = "match"`, `INSUFFICIENT = "insufficient_evidence"`, `MISMATCH = "mismatch"` (1:1 z `zgodny` / `niepewny` / `niezgodny`); `Assessment` → `IdentityAssessment(verdict, reason)`;
- `classify_many(target, candidates) -> tuple[IdentityAssessment, ...]`: waliduje wejście i przygotowuje `_target` raz na pustych dowodach, potem woła `_classify` dla każdego kandydata. To wiernie ścieżka oryginalnego `rank`; przy niepoprawnym wejściu każdy kandydat dostaje `_invalid_evidence_assessment`;
- `REASONS: Final[frozenset[str]]`: jawny zbiór wszystkich powodów, także zwracanych przez helpery konfliktów (`_selected_work_conflict`, `_directory_season_conflict`, `_editing_variant_conflict`, `_context_conflict` i ich pomocnicze). Stała nie zmienia logiki;
- usunięte `rank`, `_preference`, `_resolution` oraz `VERDICT_ORDER` i `RESOLUTION_ORDER`, jeśli nie mają innych użyć;
- docstringi według `comments-docstrings.md`; `# noqa` tylko tam, gdzie wymaga ich ruff repo.

Sygnatura `classify(target, candidate, archived_evidence=None)` i cała logika obsługi dowodów zostają 1:1, bo ich usunięcie zmieniałoby port. Produkcja nigdy nie przekazuje dowodów. Teksty `reason`, stałe, regexy, `lru_cache`, kolejność reguł, `_valid_evidence` i `_candidate_boundary` zostają bez zmian. Inna zmiana to materialna zmiana (§14).

### 9.3 Cel H1 (`identity_target`)

H1 dostaje `target` i `candidate` o kształcie z korpusu, bez dowodów (§6 Decyzja):

- `target`: dokładnie klucze `project_title`: `aliases`, `type`, `local_episode`, `season`, `episode`, `absolute`, `episode_title`, `other_series`, `other_episode_titles`;
- `candidate`: `release`, `path`, `filename`.

`identity_target(graph, selected_id, mapping, number) -> dict[str, object]` odtwarza `corpus_labels.py:project_title` (nie rodzica §10.5.3) i potrzebuje dokładnie tych danych:

- **wybrany wpis** (`id`, `format`, `title`): węzeł `graph.nodes[selected_id]`. W aplikacji wybrany wpis jest zawsze węzłem grafu (korzeń zapytania albo wpis z widoku franczyzy);
- **łańcuch i kompletność wybranego wpisu:** `chain, _, missing = traversal(selected_id, nodes, queried)` z `CHAIN`/`LEAVES`, niezależnie od korzenia widoku i kolejności rozgrzewania pamięci. Kompletność celu to `not missing` dla **wybranego** ID, nie `graph.complete`. Przykład z working: korzeń 15051 ma `complete = True`, a wybrany 194167 ma `missing = {210157}`; takich par jest 1 736. Zgodne z rodzicem `e1-wybor-odcinka.md:591`: niepełny graf nie daje odziedziczonych aliasów;
- **`aliases`:** najpierw wartości `title` wybranego wpisu **w kolejności posortowanych kluczy** (`english`, `native`, `romaji`), bo `project_title` czyta `target["media"]["title"]` zapisane z `sort_keys=True` (`acquisition_probe.py:138`), a nie w kolejności GraphQL węzła. Potem, tylko przy `not missing`, wartości `title` najwcześniejszego węzła TV/TV_SHORT/ONA łańcucha według `(startDate.year or 9999, id)`, w kolejności tego węzła. Bez powtórzeń (`dict.fromkeys`), bez sortowania całej listy. Pomiar astry: projekcja w kolejności węzła dawała 1 125 różnic `aliases` na 1 369 tytułach working, a ta reguła usuwa wszystkie;
- **`other_series`:** wartości `title` węzłów grafu spoza łańcucha;
- **`type`:** `format` wybranego wpisu;
- **`local_episode`:** numer lokalny (ten sam, którym pytamy Torrentio; film: 1);
- **`season` / `episode` / `absolute` / `episode_title`:** z `mapping.episodes[str(number)]` (`seasonNumber`, `episodeNumber`, `absoluteEpisodeNumber`, `_episode_title`), a przy braku wpisu `None`;
- **`other_episode_titles`:** `_episode_title` pozostałych kluczy `mapping.episodes`, także `S…`, w kolejności kluczy.

Builder tworzy nowy słownik JSON przy każdym wywołaniu i nie udostępnia obiektów z pamięci usługi.

**Graf i widok.** Adapter AniList zwraca wewnętrzny `FranchiseGraph`, który nie przechodzi przez IPC:

- `root_id`;
- `nodes: Mapping[int, dict]`: węzły anime z `collect`, z polami `e1_franchise_probe.FIELDS` i `relations`, jako JSON;
- `queried: frozenset[int]`;
- `complete: bool`: `traversal(root_id, ...).missing` pusty w limicie 4 zapytań, jak `Probe.franchise`. To tylko informacja o pobraniu korzenia; builder jej nie używa (kompletność celu liczy się dla `selected_id`, wyżej).

`offer` nie wykonuje dodatkowych zapytań franczyzy, żeby uzupełnić `missing` wybranego wpisu. Działa na grafie z pamięci, a niekompletny wybrany wpis dostaje aliasy tylko własne. Dla `selected_id == root_id` (jedyny przypadek w korpusie) wynik jest identyczny z `project_title` (`franchise_complete` = `not missing` korzenia), więc bramka B się nie zmienia.

Widok `Franchise` z rodzica §10.4 (wpisy SEASON/EXTRA/OTHER) to czysta projekcja `franchise_view(graph, selected_id)`. Builder czyta pełny graf, nigdy widok. Usługa trzyma graf w pamięci obok widoku.

`AniZipMapping` (wewnętrzne) zachowuje surowe `episodes: dict[str, dict]` jako JSON obok typowanych pól z rodzica §10.4. `EpisodeListing` wysyłane przez IPC pozostaje bez zmian.

### 9.4 Film

- Protokół: `StreamSource.streams(kitsu_id: int, number: int)` → `stream/series/kitsu:{id}:{number}.json` oraz `StreamSource.movie_streams(kitsu_id: int)` → `stream/movie/kitsu:{id}.json`. Dwie jawne metody zamiast flagi.
- Usługa wybiera `movie_streams` dla wpisu z `format == "MOVIE"`. `EpisodeKey(anilist_id, 1)` oznacza jedyny wiersz „Film”, a H1 dostaje `local_episode = 1` i `type = MOVIE`, jak w korpusie.
- Zmienia to rodzica faza 7 pkt 2a, gdzie było `kitsu:<id>:1`.
- Test: dokładny URL filmu bez sufiksu numeru i dokładny URL odcinka; usługa dla MOVIE nie woła `streams`.

### 9.5 Fakty, ranking, sugestia

- `release_facts(stream)` i klucz właściciela: rodzic §10.5.5 bez zmian.
- `rank_candidates(target, streams)`: `classify_many`, potem stabilne sortowanie po `(verdict_order, *klucz_właściciela)`, gdzie `match` < `insufficient_evidence` < `mismatch`. Ten sam hash z różnymi `file_index` dostaje osobne oceny.
- `suggestion`: pierwszy `match` z `supported is not False`, inaczej pierwszy `insufficient_evidence` z `supported is not False` (R-06, UX §6), inaczej `None`. `mismatch` nigdy.
- Nieznany kontener (`supported is None`) nie dostaje kary. Werdykt pochodzi z v10.3. Przykład: `slime-s4e23:12` ma `niepewny` („No selected file.”) i może być sugestią tylko według R-06 (§13).
- `_preference` z H1 nie jest portowany: jego wejście nie istniało w korpusie, a masterplan utrzymuje ranking właściciela.

### 9.6 Kontrakty (zmiany względem rodzica §10.4)

- `IdentityVerdict` i `IdentityAssessment` żyją w `episode_identity.py`; `episode_selection.py` je importuje i eksportuje przez `application/__init__.py`.
- `StreamCandidate`, `ReleaseFacts`, `RankedCandidate`, `EpisodeOffer`, `EpisodeKey`, `Franchise*`, `ListedEpisode`, `ListedSpecial`, `EpisodeListing`: jak w rodzicu. `EpisodeOffer.counts` kluczuje wartościami `IdentityVerdict`.
- Nowe typy wewnętrzne (bez IPC): `FranchiseGraph` (§9.3) i `AniZipMapping` z surowym `episodes` (§9.3). Cel H1 to zwykły słownik JSON z `identity_target`, bez osobnego typu.
- `EpisodeTarget` usunięty.
- Protokoły: `FranchiseCatalog.franchise(anilist_id) -> FranchiseGraph`, `EpisodeCatalog.mapping(anilist_id) -> AniZipMapping`, `StreamSource.streams/movie_streams` (§9.4).
- IPC (payloady i typy odpowiedzi): rodzic §10.6.

### 9.7 Polskie powody

- `cli/interactive/anime.py:_REASON_TEXTS` mapuje każdy element `episode_identity.REASONS` na polskie zdanie. Nieznany powód dostaje zdanie ogólne dla werdyktu (obrona w runtime, nie droga normalna).
- Test domeny: każdy powód zwrócony na złotej próbce, regresjach, `identity-231` i syntetykach przeniesionych testów należy do `REASONS`. Dodatkowo literały zwracane przez `IdentityAssessment(...)` i przez helpery `*_conflict` (skan `ast`) są podzbiorem `REASONS`.
- Test CLI: `set(_REASON_TEXTS) == REASONS`.
- Bramka A dodatkowo raportuje, że wszystkie powody z `working.json` należą do `REASONS`.

### 9.8 Rozmiar odpowiedzi IPC

Najprostsze poprawne rozwiązanie, wspólne dla wszystkich odpowiedzi: `ControlServer._respond` koduje ramkę odpowiedzi, a gdy przekracza `MAX_FRAME_BYTES`:

- loguje `warning` z `command_kind` i rozmiarem;
- zwraca `_error_frame(command_id, ControlErrorCode.REFUSED, "Response too large", reason="response_too_large")` (istniejąca sygnatura `local_control.py:829`).

Połączenie zostaje, a następne polecenie działa. Nic nie jest obcinane. Zdarzenia (`publish`) poza zakresem. Panel pokazuje PROBLEM „Odpowiedź rezydenta jest za duża”.

Nowe odpowiedzi E1 są małe: `offer` to jeden odcinek, a ranking Torrentio to rzędu 100 wpisów. Mechanizm chroni przed zerwaniem połączenia, nie jest ścieżką normalną. Test transportowy: handler zwraca payload > 1 MiB → klient dostaje odmowę z `reason="response_too_large"`, a kolejne `status` na tym samym połączeniu dostaje odpowiedź.

### 9.9 Wyjątek z H1

`classify` to czysta funkcja na wejściu z naszego buildera, więc wyjątek oznacza błąd programistyczny. Nie łapiemy go w domenie ani usłudze, a `offer` kończy się błędem całej operacji:

- rezydent: istniejący `_answer` loguje `error_class`, a panel pokazuje PROBLEM z istniejącym tekstem dla `command_failed` na nowej operacji;
- panel bez rezydenta: worker loguje `error_class` i pokazuje ten sam PROBLEM.

Bez nowego kodu błędu i bez cichego `niepewny`. Przypadek z praktyki przechodzi przez §10.6. Test: fałszywa usługa rzuca `ValueError` w `offer` → PROBLEM przez owner/IPC i lokalnie, log z `error_class`, brak sugestii.

### 9.10 Docelowe drzewo

```text
anishift/
├── errors.py                         # MODIFY: EPISODE_CATALOG_FAILED
├── bootstrap.py                      # MODIFY: AniZipCatalog, TorrentioSource na wspólnym httpx.Client
├── application/
│   ├── episode_identity.py           # NEW: port H1 v10.3 + classify_many + REASONS
│   ├── episode_selection.py          # NEW: kontrakty i czyste funkcje E1
│   ├── discovery.py                  # MODIFY: publiczne VIDEO_SOURCE_SUFFIXES
│   ├── acquisition.py                # MODIFY: franchise/episodes/offer, pamięć, protokoły
│   ├── automation.py                 # MODIFY: pod-operacje
│   └── __init__.py, AGENTS.md        # MODIFY
├── platform/local_control.py, AGENTS.md   # MODIFY: odmowa ponad limit
├── services/
│   ├── http_requests.py              # MODIFY: USER_AGENT, dostawcy anizip/torrentio
│   ├── catalog/{anizip.py NEW, anilist.py, __init__.py, AGENTS.md}
│   └── torrents/{torrentio.py NEW, nyaa.py (import USER_AGENT), __init__.py, AGENTS.md}
└── cli/{resident.py, AGENTS.md, interactive/anime.py, interactive/state.py}   # MODIFY
tests/
├── application/test_episode_identity.py        # NEW: klasyfikacja, classify_many, REASONS, złota próbka, regresje
├── application/test_episode_selection.py       # NEW: w tym testy rank zaadaptowane do rank_candidates
├── application/test_architecture.py            # MODIFY: episode_identity (F1), episode_selection (F2) w _PURE_MODULES, httpx w _PURE_FORBIDDEN
├── application/test_acquisition.py, test_automation.py   # MODIFY
├── fixtures/acquisition/identity-golden.json   # NEW (§10.5)
├── fixtures/acquisition/identity-regressions.json  # NEW (§10.6)
├── platform/test_local_control.py              # MODIFY: odpowiedź ponad limit
├── services/catalog/test_anizip.py, services/torrents/test_torrentio.py   # NEW
├── services/catalog/test_anilist.py, services/test_http_requests.py       # MODIFY
├── integration/{harness.py, test_search_pipeline.py, test_search_live.py} # MODIFY
└── cli/{test_interactive_anime.py, test_interactive_state.py, test_resident.py}  # MODIFY
scripts/tmp/
├── e1_port_parity.py                 # NEW: bramka A
├── e1_input_parity.py                # NEW: bramka B
└── e1_offer_timing.py                # NEW: pomiar §10.4
```

Lista odcinków, pamięć, IPC, UI i edge cases: rodzic §10.5.1, §10.5.2, §10.6, §10.7, §10.8, poza zmianami z §13.

## 10. Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Port = v10.3 w trybie produkcyjnym | Bramka A (§10.1) | pełny zbiór roboczy na wejściach bez dowodów, bez powtórki egzaminu |
| Aplikacja buduje ten sam cel co `project_title` | Bramka B (§10.2) | te same surowe źródła po obu stronach; mierzy builder |
| Tryb produkcyjny = tryb egzaminu 2 | §6 Decyzja; zakaz dowodów i dodatkowych kluczy (§7); bramka B | egzamin 2 zwalidował dokładnie ten kształt wejścia |
| CI chroni semantykę bez danych spoza repo | złota próbka §10.5, przeniesione testy, regresje §10.6 | wykrywa dryf przy każdej zmianie |
| Ranking według spec | rodzic faza 3 (ranking, kontenery, rozdzielczość) i zaadaptowane testy `rank` | reguły mają przypadki rozróżniające |
| Adaptery, w tym film | fixture + test dokładnych URL-i + jeden ręczny `-m network` | rzeczywiste odpowiedzi |
| IPC | strict round-trip, test odmowy ponad limit | jak w rodzicu faza 6 plus §9.8 |
| UI | `test_interactive_anime.py`, test tłumaczeń, H1 | mechanika + ocena człowieka |
| Czas | §10.4 | Q-05, bez progu |
| Brak regresji | pełne bramki | `AGENTS.md` |

### 10.1 Bramka A — `e1_port_parity.py`

- Wejście: `working.json` (SHA `ede16871…` sprawdzony przed i po) i `identity-231.json`. Każdy rekord klasyfikowany jako `(target, candidate)` z `evidence = {}`, także 1 439 rekordów z zapisanym `archived_evidence` (tak jak w produkcji).
- Porównanie per rekord: `classify` artefaktu vs `classify` portu; werdykty mapowane 1:1, `reason` równy dosłownie.
- Porównanie per grupa `target`, jak `e1_heuristic_eval.py:202`: `classify_many` portu vs `classify` artefaktu dla każdego kandydata grupy.
- Raport: liczba rekordów i grup, różnice (0; pierwsze 20 tylko z polami runtime), powody spoza `REASONS` (0), P95 obu wersji. Exit ≠ 0 przy różnicy.

### 10.2 Bramka B — `e1_input_parity.py`

- **Próba:** rekordy robocze, których surowe odpowiedzi franczyzy (`franchise:<id>:<n>`) i ani.zip (`mapping:<id>`) oraz plik celu są w `%USERPROFILE%\acquisition-corpus\` i przechodzą kontrolę SHA (`corpus_labels.py:_verified_source`).
- **Referencja:** oryginalne `project_title` (import ze `scripts/tmp`).
- **Produkcja:** te same surowe odpowiedzi przez parsery adapterów (ani.zip → `AniZipMapping`, strony franczyzy → `FranchiseGraph`), potem `identity_target(graph, media_id, mapping, number)`. Candidate i numer z zapisanego rekordu. Zapytania archiwum pochodzą z `Probe.franchise` (`query(3)`), czyli z tej samej projekcji co adapter.
- **Porównanie:** `target` jako JSON, równość wartości, kolejności list i typów, a potem werdykt i `reason` H1 na obu wejściach z `evidence = {}`.
- **Raport:** liczba rekordów i tytułów porównywalnych, pokrycie względem 36 862 rekordów i liczby tytułów roboczych, różnice (0). Nieporównywalne podaje z powodem: brak źródła, SHA, kształt niepodawalny parserowi, wybrany wpis nieobecny w węzłach grafu (w aplikacji niemożliwe, §9.3).

### 10.3 Tryb wejścia H1

Bez dowodów (§6 Decyzja). Pilnują tego: zakaz w §7, bramki A i B na `evidence = {}` oraz test dokładnych kluczy `target` w F2.

### 10.4 Pomiar czasu

`e1_offer_timing.py` mierzy na nagranych fixture przez `httpx.MockTransport` i prawdziwe owner/IPC (lokalny kanał):

- etapy `offer`: `identity_target`, `classify_many`, `release_facts` + sortowanie, kodowanie/dekodowanie IPC, cała odpowiedź;
- warianty: zimna pamięć (`franchise` + `episodes` + `offer`) i ciepła (`offer` po `episodes`);
- duża lista: co najmniej 100 kandydatów i wpis z ~1 200 odcinkami (długa seria z fixture albo syntetyk z tej samej struktury);
- P50/P95 z wielu powtórzeń.

W H1 na żywo notowane są czasy etapów Q-05: tytuł → wpisy → odcinki → sugestia. Wszystko trafia do outcome, bez progu (Q-05).

### 10.5 Złota próbka

`tests/fixtures/acquisition/identity-golden.json` to deterministyczna próbka części roboczej:

- zapisany seed, warstwy typ × werdykt × kształt (pojedynczy / paczka / wielosezonowa), około 400 rekordów, ≤ 500 KiB;
- wejście H1 to `target` i `candidate` z `working.json` (wynik `project_title`), bez `archived_evidence`, `id`, `source` i `info_hash`;
- każdy rekord ma `label` oraz oczekiwane `verdict` i `reason` z zamrożonego artefaktu na tym wejściu z `evidence = {}`.

Test sprawdza:

- zgodność `(verdict, reason)` przez `classify` i `classify_many` (charakteryzacja 1:1);
- brak `match` przy `label = błędny` poza jawną listą w pliku (znane przypadki domeny H2, każdy z przyczyną).

`identity-231.json` przechodzi przez tę samą charakteryzację na swoim wejściu.

### 10.6 Zasada regresji

Błąd H1 z praktyki (H1 z właścicielem, później E2/E3):

1. Minimalny rekord `{target, candidate, expected_verdict, cause}` trafia do `identity-regressions.json`, bez ID i hashy.
2. Parametryzowany `test_identity_regression_case_keeps_expected_verdict` najpierw pada na obecnej H1.
3. Poprawka dotyka tylko przyczyny; nowy powód trafia do `REASONS` i `_REASON_TEXTS`.
4. Kontrola: testy H1, złota próbka, `e1_port_parity.py` w trybie raportu różnic na `working.json`. Każda różnica względem v10.3 jest opisana, liczba `match` przy `label = błędny` nie rośnie, a aktualizacja złotej próbki wymaga przeglądu drugiego modelu.
5. Nowa wersja H1 w docstringu modułu i wpis w `outcomes/e1.md`.

Pierwszy przypadek w E1: Slime S1E4 z fixture Torrentio. Wydanie S1E4 ma `match`, a Diaries i OAD nie mają `match`. `cases.jsonl` i przegląd tygodniowy zostają w E2/E3.

### Bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Po każdej fazie całość, zawsze na `anishift/ tests/`.

### Obowiązki regresyjne

Stara droga pod `G` (pobieranie, subskrypcje, zakres, kalkulator sezonów), PR-01 i PR-06, testy subskrypcji i pobierania warstwy aplikacji, istniejące testy `local_control`.

### Odbiór człowieka — H1

Scenariusz: `ux.md` §12 H1 (krok 1: Diaries i OAD nie są `zgodne` — rozstrzygnięte 2026-09-28). PASS: dla 10 tytułów właściciela właściwy odcinek w ≤ 3 wyborach od nazwy, sugestie sensowne albo wskazany konkretny błąd. Błąd tożsamości zakwalifikowany przez właściciela przechodzi przez §10.6; pozostałe trafiają do outcome jako znane ograniczenia.

## 11. Plan wykonania

- **Wykonawcy:** `astra` i `opus55`, naprzemiennie. Recenzentem jest zawsze drugi model, świeża instancja. `sol6` nie koduje.
- **Pętla:** autor koduje i testuje → recenzent według skilla `review` → autor poprawia → recenzent weryfikuje.
- **Briefy:** według `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`.
- **Orkiestrator:** uruchamia bramki, integruje i commituje na `work/acquisition/01-episode-selection` po każdej zaakceptowanej fazie (`typ(scope): opis`, scope z `scripts/hooks/check_commit_msg.py`).

### Faza 0 — Preflight (orkiestrator)

1. Commit zaakceptowanej dokumentacji; jego SHA to baseline, zapisany w `outcomes/e1.md`.
2. SHA-256 zamrożonych plików `scripts/tmp/` vs `code-freeze-2026-09-28\`; SHA `working.json`.
3. Bramki; wynik jako baseline.

**Gate:** zgodne SHA, bramki zielone albo znane failures zapisane.

### Faza 1 — Port H1 + bramka A (autor `astra`, recenzent `opus55`)

1. `episode_identity.py` według §9.2.
2. `tests/application/test_episode_identity.py`:
   - przeniesione wszystkie testy klasyfikacji artefaktu jako pytest (nazwy `test_<jednostka>_<scenariusz>_<oczekiwanie>`, marker `unit`, bez docstringów i komentarzy);
   - test `classify_many` = `classify` na tych samych syntetykach;
   - test `REASONS` (§9.7).
   Testy `rank` przechodzą do F2 jako testy `rank_candidates` (zachowane oczekiwania kolejności werdyktów; kolejność w obrębie werdyktu według klucza właściciela). Testy ewaluatora i podziału zostają w `scripts/tmp`. Budżet czasu nie wraca jako test; mierzy go §10.4.
3. `scripts/tmp/e1_port_parity.py` (§10.1).
4. `test_architecture.py`: `episode_identity.py` w `_PURE_MODULES`, `httpx` w `_PURE_FORBIDDEN` (rodzic faza 3, inwarianty). `episode_selection.py` dochodzi w F2, bo strażnik wymaga istnienia pliku (`test_architecture.py:99–102`).

**Gate:** bramka A = 0 różnic z liczbami, testy i bramki repo zielone, review PASS.

### Faza 2 — Kontrakty i czyste funkcje (autor `opus55`, recenzent `astra`)

1. Typy §9.6 i rodzic §10.4; `VIDEO_SOURCE_SUFFIXES` w `discovery.py`; `episode_selection.py` dopisany do `_PURE_MODULES`.
2. `franchise_view`, `episode_listing` (rodzic §10.5.2 pkt 3–5), `identity_target` (§9.3), `release_facts`, `rank_candidates`, `suggestion` (§9.5).
3. Testy:
   - listy rodzica faza 3, z nadpisaniem §13 dla `slime-s4e23:12`;
   - zaadaptowane testy `rank`;
   - `identity_target`: łańcuch, liście, niekompletna franczyza bez aliasów pierwszego sezonu; **kompletny korzeń i niekompletny wybrany liść** → aliasy tylko wybranego wpisu; kolejność aliasów (tytuły wybranego wpisu po posortowanych kluczach, potem tytuły najwcześniejszego sezonu w kolejności węzła, na węźle z kolejnością GraphQL różną od posortowanej); klucze `S…`, brak wpisu ani.zip dla numeru, film, niezależność od korzenia widoku i kolejności rozgrzewania; dokładnie klucze `project_title` (bez `year`/`seasonYear`);
   - **węzeł spoza widoku**: węzeł grafu nieobecny we wpisach `Franchise` trafia do `other_series` i wpływa na werdykt;
   - S1/Diaries/OAD na fixture (`anilist__franchise__101280`, `anizip__101280`, `torrentio__kitsu-*`) przez `identity_target` → `rank_candidates`;
   - pierwszy przypadek regresyjny (§10.6).

**Gate:** testy i bramki zielone, S1E4 → sugestia `match`, Diaries i OAD bez `match`, review PASS.

### Faza 3 — Adaptery + bramka B (autor `astra`, recenzent `opus55`)

1. Rodzic faza 4 pkt 1–7: `AniZipCatalog.mapping` (z surowym `episodes`, §9.3), `TorrentioSource.streams/movie_streams` (§9.4), `AniListCatalog.franchise` → `FranchiseGraph` (algorytm `Probe.franchise`: `query(3)`, `collect`, `traversal`, limit 4 zapytań), `_provider()`, `USER_AGENT` w `http_requests.py` (import w Nyaa i Torrentio, test nagłówka także przy ponowieniu), `EPISODE_CATALOG_FAILED`, logowanie granic.
2. Testy dokładnych URL-i serii i filmu; testy adapterów na fixture; `network` pomijane domyślnie; jeden ręczny przebieg `-m network`.
3. `scripts/tmp/e1_input_parity.py`: bramka B (§10.2).
4. `identity-golden.json` generowany jednorazowo skryptem z `working.json` według §10.5, plus jego test.

**Gate:** bramka B = 0 różnic z liczebnością i pokryciem, testy i bramki zielone, review PASS.

### Faza 4 — Usługa, IPC, wiring, limit ramki (autor `opus55`, recenzent `astra`)

1. Rodzic faza 6 pkt 1–7 i jej testy, z `FranchiseGraph` i `AniZipMapping` w pamięci usługi zamiast `EpisodeTarget`, oraz wyborem `movie_streams` dla MOVIE (§9.4).
2. §9.8 w `local_control.py` z testem transportowym; aktualizacja `platform/AGENTS.md` (odpowiedź ponad limit to odmowa, nie zerwanie).
3. Test §9.9.
3a. Kompletny korzeń i niekompletny wybrany liść: fałszywy katalog liczy zapytania — `offer` nie wykonuje żadnego dodatkowego zapytania franczyzy (§9.3).
4. `scripts/tmp/e1_offer_timing.py` (§10.4), wynik do outcome.

**Gate:** testy i bramki zielone, pomiar zapisany, review PASS.

### Faza 5 — UI (autor `astra`, recenzent `opus55`)

1. Rodzic faza 7 pkt 1–4 i jej testy (pkt 2a według §9.4).
2. `_REASON_TEXTS` z testem (§9.7).
3. Sugestia `niepewna` z dopiskiem „(niepewne wydanie)”; PROBLEM dla `response_too_large`; lokalny worker według §9.9.
4. Aktualizacja `cli/AGENTS.md`, `application/AGENTS.md`, `services/catalog/AGENTS.md`, `services/torrents/AGENTS.md`: nowe moduły, pułapki, zasada regresji H1, wejście H1 bez dowodów.

**Gate:** pełne bramki, review PASS, ręczny smoke orkiestratora w panelu na Slime i jednym filmie (bez pobierania).

### Faza 6 — H1, outcome, review końcowe

1. H1 z właścicielem (§10). Uwagi o wyglądzie poprawia `opus55` (nie autor fazy 5), recenzuje `astra`. Uwagi o znaczeniu trafiają do `spec.md`/`ux.md` po decyzji właściciela. Czasy Q-05 zapisane.
2. `outcomes/e1.md` według §12.
3. Przegląd całego diffu E1: świeży `opus55` przegląda fazy `astra`, świeży `astra` przegląda fazy `opus55` → poprawki → weryfikacja.
4. PR piętrowy tylko na polecenie właściciela.

## 12. Definition of Done i kontrakt wyniku

- [ ] §3 spełnione; bramki A i B z liczbami;
- [ ] pełne bramki zielone z liczbami;
- [ ] zakres i zakazy zachowane (diff sprawdzony przez orkiestratora);
- [ ] H1 wykonane; review rozliczone.

`outcomes/e1.md` zawiera:

- status i baseline wykonania;
- zamknięcie N-02: egzamin 1 FAIL, egzamin 2 PASS z metrykami, decyzja o końcu strojenia, SHA v10.3;
- decyzję o wejściu bez dowodów z liczbami z §6 (0/3 911 dowodów w egzaminie 2; pomiar z dowodami 303 → 301/646, 2021+ 96 → 92/138; przejścia 69/23);
- N-01 (pilot, U-02), N-03 (stan, decyzja przed E2), N-04 (wariant `movie`: kandydaci dla 19, 17 i 6 filmów, obsługa w E1);
- bramki A i B;
- pomiar czasu i etapy Q-05;
- bramki repo, zmienione pliki;
- H1 i uwagi, przypadki regresyjne;
- odchylenia (§13), znane ograniczenia (luki H1, pokrycie `zgodny` ~47%);
- stan Git, rekomendowany zakres planu E2 (w tym pełne Q-08).

## 13. Odchylenia od planu-rodzica

| Rodzic | Tu | Powód |
| --- | --- | --- |
| §10.5.3 cel odcinka (`kind` TV/OVA, `isolated_series`, tytuły innych odcinków tylko dla OVA) | §9.3: semantyka `project_title` | H1 zamrożono na tym wejściu |
| §10.5.3–§10.5.4: H1 z metadanymi katalogu (rok, liczba odcinków, sąsiedzi) jako dowodami | wejście bez dowodów: `evidence = {}`, `target` = `project_title` bez `year`/`seasonYear` | egzamin 2 szedł bez dowodów (0/3 911); tryb z dowodami obniża pokrycie `zgodny` (303 → 301/646; 2021+ 96 → 92/138) przy 0 nowych błędnych `zgodnych` (§6 Decyzja) |
| §10.4 `EpisodeTarget` | słownik JSON z `identity_target` | wejście H1 nie przechodzi przez IPC; kształt korpusu |
| §10.4 `Franchise` jako źródło celu | `FranchiseGraph` (wszystkie węzły) dla buildera, `Franchise` jako projekcja widoku | widok nie mieści węzłów potrzebnych H1 (S1: 25 vs 10) |
| §10.5.4 heurystyka w `episode_selection.py` | `episode_identity.py`, port 1:1 z `classify_many` i `REASONS` | inny powód zmian; koszt listy; komplet tłumaczeń |
| `StreamSource.streams(kitsu_id, number)`; film przez `kitsu:<id>:1` (faza 7 pkt 2a) | `streams` + `movie_streams` (`stream/movie/kitsu:<id>.json`) | N-04: wariant `movie` rozstrzygnięty lokalnie (19, 17, 6) |
| §10.5.5 ranking | bez zmian, z werdyktem jako pierwszym kluczem; `_preference` nieportowany | §9.5 |
| §10.4 `EpisodeOffer.suggestion` tylko z `match` | także najlepszy `insufficient_evidence`, gdy brak `match` | R-06, `ux.md` §6, D6 |
| §10.8 i faza 3: `slime-s4e23:12` → `match`, może być sugestią | v10.3: `niepewny` („No selected file.”); `supported=None` bez kary; sugestia tylko według R-06 | klasyfikator zamrożony; nie zmieniamy go pod oczekiwanie |
| `identity-corpus.json` | `identity-golden.json` + bramki A/B na pełnym zbiorze roboczym | pełny zbiór zamiast próbki; próbka tylko dla CI |
| brak kontroli rozmiaru odpowiedzi w E1 | jawna odmowa ponad limit (§9.8); pełne Q-08 w E2 | bez zrywania połączenia |
| Fazy 5 (N-01) i 8 (N-03) | nie istnieją | N-01 zastąpiony pilotem (U-02); N-03 wykonane 25.09, decyzja przed E2 |
| Wykonawca `astra`, review `opus5` | `astra` ↔ `opus55` naprzemiennie | decyzja właściciela 28.09 |
| UX H1 krok 1: Diaries/OAD „niezgodne” | „nie są `zgodne`” (`ux.md` §12 zaktualizowany) | rozstrzygnięte 2026-09-28 |

## 14. Materialna zmiana

Wymaga zatrzymania i powrotu do orkiestratora:

- różnica w bramce A lub B;
- przekazanie do H1 dowodów albo kluczy `target` spoza `project_title`;
- zmiana semantyki H1 poza §10.6;
- zmiana publicznych typów poza §9.6;
- nowy magazyn danych, zapis stanu poza `provider_locks`, zmiana `PROTOCOL_VERSION` lub reguł rankingu;
- nowa zależność.

## 15. Otwarte pytania do właściciela

Brak. Skład wykonawców w `AGENTS.md` rozstrzygnięty (`8fce119`).
