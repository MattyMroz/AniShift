---
kind: plan
status: do-akceptacji
baseline: bde35d7
base_branch: work/acquisition/00-model-catalog-v2
created: 2026-09-23
updated: 2026-09-25
stage: E1
---

# Plan E1: wybór odcinka na prawdziwych danych i pomiary

## 1. Cel

Zbudować nową ścieżkę zakładki Anime **tytuł → wpisy franczyzy → odcinki → sugestia wydania i inne wydania** na żywych danych AniList, ani.zip i Torrentio, z heurystyką tożsamości i rankingiem ze specyfikacji — bez pobierania i bez zmian stanu trwałego poza istniejącym zapisem `provider_locks` po 429 (§7). Równolegle zmierzyć N-01–N-04 (spec §15), aby plany E2 i E3 powstały na faktach.

## 2. Rezultat użytkownika

Właściciel otwiera Panel → Anime, wpisuje tytuł, wybiera rok/wpis, widzi sezony, części, dodatki i filmy franczyzy, wchodzi w sezon, widzi odcinki z datami emisji, zaznacza odcinki i `D` pokazuje dla każdego sugerowane wydanie z powodem, a `I` wszystkie wydania z oceną „zgodny / niepewny / niezgodny”. Nic się nie pobiera. Dostaje też raport: jak szybko nowe odcinki pojawiają się w źródle, ile wydań heurystyka odrzuca na jego tytułach, czy magnet daje listę plików, czy filmy działają.

## 3. Warunki końcowe

- [ ] W-01–W-08, R-01–R-03, R-05, R-06, R-08 spełnione w nowej ścieżce; R-04 bez akcji wyboru (lista „Inne wydania” z oceną i powodem). Bez pobierania i subskrybowania z nowej ścieżki.
- [ ] Korpus ≥ 2000 unikalnych tytułów i ≥ 10 000 unikalnych oznaczonych rekordów (odcinek + kandydat) zebrany warstwowo; niezależne etykiety A/B, arbitraż i lista dla właściciela rozliczone (§9 N-02).
- [ ] Przed budową heurystyki zamrożono losowy, stratyfikowany podział na część roboczą i odłożoną, z ziarnem i sumami SHA-256; autor heurystyki nie miał dostępu do części odłożonej ani przed egzaminem, ani podczas strojenia.
- [ ] Heurystyka zbudowana od zera wyłącznie na części roboczej zdała jednorazowy egzamin na części odłożonej: 0 błędnych `zgodnych`; udział `niepewnych`, błędnych `niezgodnych` i pokrycie per warstwa przedstawione właścicielowi i przez niego zaakceptowane, bez z góry narzuconych progów.
- [ ] `episode_selection.py` realizuje zamrożone reguły po egzaminie; testy na stałych próbkach oznaczonego korpusu i przypadkach szczególnych opierają oczekiwania na etykietach, nie na decyzjach prototypu. Historyczne 231 rekordów zachowuje etykiety, ich siłę i pochodzenie; parytet z prototypem nie jest celem.
- [ ] Ranking spełnia U-04, U-05, U-06, U-23 na przypadkach granicznych z §10.8 i fazy 3.
- [ ] Stara ścieżka wyników grupowych (ekran RESULTS, `D` pobierz, `O` subskrybuj) działa jak dziś, osiągalna z listy tytułów klawiszem `G`; właściciel może nadal pobierać i dodawać subskrypcje w czasie E1.
- [ ] Pełne bramki `AGENTS.md` zielone; nowe testy bez sieci; testy `network` dla nowych adapterów istnieją i przechodzą ręcznie.
- [ ] Raport pomiarów `outcomes/e1.md` z odpowiedziami na N-01–N-04 i decyzjami dla E2/E3 według reguł §9.
- [ ] H1 wykonane przez właściciela, uwagi rozliczone.
- [ ] Niezależne review `opus5` bez otwartych findingów krytycznych i poważnych.

## 4. Nie-cel

Pobieranie, subskrybowanie, zmiany WatchState (poza istniejącym `provider_locks` po 429) i `subscriptions.json`, migracje, zmiany zakładki Subskrypcje, Przetwarzania, Biblioteki, Ręcznego i Ustawień, kontrola zawartości pobranych plików, usuwanie kodu Nyaa i starych funkcji `acquisition.py` używanych przez subskrypcje.

## 5. Authority i baseline

| Źródło | Rola |
| --- | --- |
| [../spec.md](../spec.md) | Wymagania i ustalenia |
| [../README.md](../README.md) §3/§4 | Manifest: rozliczone weto i decyzje (§3), zgody Z-1 i Z-3 (§4); Z-2 wycofana |
| [../ux.md](../ux.md) §2–§6, §11–§13 | Ekrany U01–U04, stany, H1 i klawisze |
| [../masterplan.md](../masterplan.md) | Granice etapu E1 |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `anishift/services/torrents/AGENTS.md`, `tests/AGENTS.md` | Reguły kodu, testów, logowania |
| `.agents/skills/coding/SKILL.md` + `.agents/skills/coding/references/python.md`, `.agents/skills/coding/references/comments-docstrings.md`, `.agents/skills/coding/references/testing.md` | Standard kodu |
| `workspace/.archive/acquisition/evidence/matching/prepare.py.txt` | Prototyp badawczy: opcjonalny punkt porównania na części roboczej, nie wzorzec reguł ani oczekiwań |
| `workspace/.archive/acquisition/evidence/polish/study.py.txt`, `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt` | Rozpoznawanie języków, rozdzielczości, źródeł z nazw |
| `../research/anime-api-metadata-validation.md`, `../research/anime-api-release-validation.md` | Kontrakty pól ani.zip i Torrentio |

**Baseline:** HEAD `bde35d7`, gałąź bazowa E1 `work/acquisition/00-model-catalog-v2`, stan po E00. Dokumenty acquisition są śledzone; drzewo robocze przed tą aktualizacją nie miało zgłoszonych zmian. PR #56 scalił local-automation do `main` jako `c58392a` (2026-09-23; potwierdzone przez `git log main` i `gh pr view 56`). Wykonawca zaczyna od nowej gałęzi (faza 0).

**Znane wcześniejsze failures:** historyczny test routingu ponowienia biblioteki został poprawiony i przemianowany w `c559ded`; obecna kotwica: `tests/application/test_automation.py:test_library_retry_after_refused_deletion_only_relocates`. Ta aktualizacja dokumentów nie uruchamia testów; faza 0 ustala rzeczywisty baseline. Znany błąd numeracji AniList `182205` opisano w §6.1 i §15.

**Ścieżki:** ścieżki zaczynające się od `anishift/`, `tests/`, `scripts/`, `config/`, `workspace/` i `.agents/` są względem roota repo; skróty `application/`, `services/`, `cli/`, `platform/` w opisie kodu oznaczają podkatalogi `anishift/`, a w drzewie §10.3 obowiązuje pokazany korzeń (`anishift/` lub `tests/`). `evidence/` oznacza `workspace/.archive/acquisition/evidence/`, a `outcomes/` — `docs/work/acquisition/outcomes/`. Skille pod `.agents/` są lokalnymi zasobami przez dowiązania, a archiwalne dowody i pliki runtime w `config/` są lokalne i gitignorowane — istnieją na tej maszynie, ale sam checkout `bde35d7` ich nie dostarczy. Przed E1 trzeba potwierdzić ich lokalną dostępność; źródłem decyzji i zgód jest śledzony [../README.md](../README.md) §3/§4 wraz z uzupełnieniem Z-1 z 2026-09-25 zapisanym w §9 poniżej.

## 6. Stan aktualny

### 6.1 Obecne zachowanie

- `anishift/cli/interactive/anime.py:AnimeController` ma ekrany QUERY → BUSY → TITLES → BUSY → RESULTS → DONE/PROBLEM. `_search_title` najpierw pobiera `season_context`, potem wywołuje `search_title`; wyniki Nyaa są grupowane według grup wydających. `_find_titles` przy braku tytułu albo błędzie katalogu przechodzi do surowego Nyaa. Według zmienionego W-08 zostaje przejście przy braku tytułu z jawnym komunikatem; awaria katalogu ma kończyć się komunikatem błędu (§10.7).
- `anishift/cli/interactive/anime.py:AnimeController._acquisition` wskazuje `anishift/cli/resident.py:ResidentSession` (IPC) albo `anishift/application/acquisition.py:AcquisitionService`. Wspólne wejścia to `find_titles`, `season_context`, `search_title`, `search`, `download`; `ResidentSession.download` używa osobnego polecenia `download`, z trwałym przyjęciem u właściciela.
- `anishift/application/automation.py:AutomationOwner._acquisition_command` obsługuje `titles`, `search`, `season`, `releases` pod `acquisition.requests("user")`. Po `titles` i `search` dekoduje `candidate` **przed** sprawdzeniem pozostałych nazw operacji (linia 3241); brak `candidate` daje wyjątek walidacji, a `AutomationOwner._answer` zwraca `refused(INTERNAL, …, "command_failed")`. „Unknown acquisition operation” pada dopiero przy poprawnym `candidate`.
- `anishift/services/catalog/anilist.py:AniListCatalog.search`, `prequel_episodes`, `episode_offset`, `airing_schedule` już istnieją. `TitleCandidate.prequel_ids` zawiera wyłącznie bezpośrednie relacje PREQUEL do TV/TV_SHORT/ONA; nie ma jeszcze modelu franczyzy.
- `anishift/services/http_requests.py:_provider` rozpoznaje hosty AniList i Nyaa, potem ścieżkę `/api/v2/` jako qBittorrent; reszta to `other`. `RequestControl._admit` daje odstęp 1 s tylko AniList i Nyaa; `_cooldown` zapisuje blokadę przez callback właściciela (dozwolony wyjątek E1: §7, D4 w §15).
- Nie ma adapterów ani.zip i Torrentio, heurystyki tożsamości ani rankingu w kodzie aplikacji.
- Po E00 `anishift/services/llm/engines/palantir/constants.py:PALANTIR_MODELS` zawiera 22 modele; `anishift/config/model_catalog.py:load_model_catalog` jest projekcją stałych, bez plików i sieci. `anishift/application/runtime.py:palantir_llm_config` rozwiązuje alias, provider, trasę i token. `LlmConfig` ma wariant rozumowania i opcjonalne konto zapasowe, lecz fabryka runtime ich nie ustawia; `Settings` nie ma tokena konta 2 (§9 N-02).
- **Znany błąd sezonów:** masterplan dokumentuje `ResidentSession.season_context()` dla „4th Season”, AniList `182205`, z `offset=48` i błędnym rozróżnieniem S04E23/S03E23. Klient tylko dekoduje wynik IPC. `anishift/application/acquisition.py:AcquisitionService.season_context` sumuje `PrequelEntry.episodes`, a indeks liczy z wpisów bez `cour` + 1 (dla wybranego cour bez +1). `anishift/services/catalog/anilist.py:AniListCatalog.prequel_episodes` idzie po przefiltrowanych PREQUEL, najwyżej 8 wpisów, z pomijaniem cykli; nieznana liczba odcinków daje 0. `_prequel_ids` odrzuca krawędź do OVA/filmu, więc nie przechodzi przez taki wpis do wcześniejszych sezonów. W `read_episode` pary SxxEyy są porównywane z **indeksem**, a offset służy numeracji absolutnej — sam offset 48 nie jest bezpośrednią przyczyną odrzucenia S04E23. Dokładnej odpowiedzi AniList powodującej ten wynik nie odtwarzano w tej aktualizacji. Nowy przepływ §10.5.2–§10.5.3 omija ten kalkulator. Decyzja D1: bez osobnej naprawy starej drogi; jej UI znika w E3, zaplecze w E5.

### 6.2 Luka

Brak modelu wpisu franczyzy i listy odcinków; brak źródła kandydatów per odcinek; tożsamość i jakość wydania wynikają z parsowania nazw Nyaa i filtrów grup.

### 6.3 Istniejące elementy do użycia

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| Wyszukiwanie tytułów | `anishift/services/catalog/anilist.py:AniListCatalog.search`, `anishift/services/catalog/types.py:TitleCandidate` | Istniejące wyszukiwanie | Wynik jest w kolejności AniList; W-03 wymaga kolejności widoku |
| Harmonogram emisji | `anishift/services/catalog/anilist.py:AniListCatalog.airing_schedule`, `anishift/services/catalog/types.py:SeasonAiring` | Daty emisji odcinków (U-13) | Pusty harmonogram nie tworzy odcinków z liczby sezonu |
| Limity HTTP | `anishift/services/http_requests.py:RequestControl`, `request_scope` | Dodać nazwy `anizip`, `torrentio` | Bez nowego odstępu (Q-04) |
| Wątek sieciowy i generacje UI | `anishift/cli/interactive/anime.py:AnimeController._spawn`, `_generation` | Wzorzec dla nowych ekranów | Render bez I/O |
| Pole tekstowe, zakres | `anishift/cli/interactive/text_input.py:TextInput`, `anishift/cli/interactive/anime.py:_parse_range`, `_RANGE_RE` | Pole i istniejąca obsługa zakresu | Obecny parser zwraca `EpisodeRange` z `Decimal`, nie listę int; stara droga ma zachować swój kontrakt |
| Kodowanie widoków IPC | `anishift/application/control_views.py:encode_view`, `decode_view`, `_adapter` | Nowe dataclassy | Strict decode; typy dostępne w runtime w module definicji (§10.4) |
| Oceniający korpus | `anishift/config/model_catalog.py:load_model_catalog`, `anishift/application/runtime.py:palantir_llm_config`, `anishift/services/llm/service.py:LlmService.complete` | Istniejąca droga Palantira po E00 | Model po aliasie; konfiguracja konta 2 nie jest podłączona do `Settings` |
| Wiadomości LLM | `anishift/services/llm/types.py:LlmRequest`, `LlmMessage`, `TextPart`, `FilePart` | SYSTEM z instrukcją + USER z JSON jako tekstem | Każda wiadomość wymaga `TextPart`; `FilePart` tylko w USER i dla wspieranej modalności, nie jest potrzebny do N-02 |
| Klient torrent | `anishift/services/torrents/qbittorrent.py:QBittorrentClient.add_torrent`, `files`, `remove` | Wzorzec HTTP i odczytu plików | Brak argumentu `stopCondition` i metody priorytetów; `remove` zachowuje pliki. N-03 pozostaje izolowanym skryptem, nie używa profilu rezydenta |
| Nagrane odpowiedzi | `tests/fixtures/search/`, `tests/integration/harness.py` | Konwencja fixture i `manifest.json` | — |
| Surowe odpowiedzi z badań | `workspace/.archive/acquisition/evidence/sources/metadata/*.raw.json`, `workspace/.archive/acquisition/evidence/sources/releases/*.body.json`, `workspace/.archive/acquisition/evidence/sources/ova/*.raw.json` | Fixture testów adapterów | Stan z 2026-09-22 |
| Zbiór 231 rekordów | `workspace/.archive/acquisition/evidence/matching/dataset.json`, `targets.json` | Historyczne dane z etykietami i źródło pewnych kontroli oceniających | 439 KB — zachować siłę i pochodzenie etykiet, nie traktować decyzji prototypu jako wzorca |
| Izolowany profil qB | `workspace/.archive/acquisition/evidence/bundle/run01/probe-*.py.txt` | Wzorzec próby N-03 | Tam DHT wyłączone; tu potrzebne |

### 6.4 Dowody stanu

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| Pod-operacje `acquisition` można dodawać bez zmiany wersji protokołu, jeśli nowe gałęzie stoją przed dekodowaniem `candidate` | `anishift/application/automation.py:AutomationOwner._acquisition_command`, `AutomationOwner._answer`; `anishift/platform/local_control.py:PROTOCOL_VERSION` = 1 | verified |
| Torrentio zwraca tylko `infoHash` | `../research/anime-api-release-validation.md:195,292` | verified |
| Format linii Torrentio: nazwa wydania, opcjonalna ścieżka, `👤 N 💾 X ⚙️ provider`, linia języków `A / B / 🇬🇧` | `workspace/.archive/acquisition/evidence/sources/releases/slime-s1e4.body.json` | verified |
| ani.zip: `episodes["1".."n"]`, `episodes["S1"..]`, `mappings.kitsu_id`, `mappings.type`, `episodeCount`, `specialCount`, pola odcinka `seasonNumber`, `episodeNumber`, `absoluteEpisodeNumber`, `airDateUtc`, `title.en` | `workspace/.archive/acquisition/evidence/sources/metadata/slime-s1.raw.json` | verified |
| AniList przyjmie zagnieżdżone relacje w jednym zapytaniu | — | unknown → faza 0 |

## 7. Zakres

### In scope

- Pure: `anishift/application/episode_selection.py` (tożsamość, fakty wydania, ranking).
- Adaptery: ani.zip, Torrentio, franczyza w AniList.
- `AcquisitionService`: `franchise`, `episodes`, `offer`; pamięć odpowiedzi ani.zip i franczyz.
- Rezydent i `ResidentSession`: pod-operacje `franchise`, `episodes`, `offer`.
- `AnimeController`: nowe ekrany ENTRIES, EPISODES, OFFER, CANDIDATES jako domyślna droga po wyborze tytułu; dotychczasowy ekran RESULTS z grupami, zachowanymi `D` i `O`, osiągalny z TITLES klawiszem `G` („Wydania wg grup — stara wersja”) oraz przy braku tytułu w AniList (D5). Wspólny komunikat błędu źródła zmienia się także dla Nyaa (§10.7).
- Faza 0: podłączenie danych konta 2 Palantira przez `Settings` i `palantir_llm_config` na potrzeby oceny korpusu, bez zmian `anishift/services/llm/` (D2).
- Skrypty pomiarowe w `scripts/tmp/` i raport `outcomes/e1.md`.
- Testy, fixture, aktualizacja scoped `AGENTS.md` dla zmienionych modułów.

### Out of scope

Wszystko z §4.

### Forbidden

- Zapis do WatchState, `subscriptions.json`, ustawień, presetów. Jedyny wyjątek w nowej drodze E1: istniejący zapis `WatchState.provider_locks` po 429 przez `RequestControl._cooldown` → callback `_restore_provider_locks` → wątek `AutomationOwner._save_provider_lock`, bez nowego modelu danych lub migracji (D4). Odczyt danych konta 2 przez `Settings` nie zapisuje ustawień; wartości do `.env` wpisuje właściciel, agent nigdy nie czyta `.env` ani plików z tokenami.
- Dodawanie torrentów do qBittorrenta użytkownika lub rezydenta (próba N-03 tylko w izolowanym profilu).
- Pobieranie treści mediów (próba N-03 kończy się przed startem treści).
- Nowe zależności runtime.
- Rejestr silników dla katalogu lub Torrentio.
- Zmiana `PROTOCOL_VERSION`.
- Opisowe komentarze w kodzie i proza w testach (reguły `AGENTS.md`).

### Deferred

- Akcje Pobierz (`D` w podglądzie), Pobierz ponownie (`P`), Subskrybuj (`O`) → E2/E3. W E1 klawisze `O` i `P` na liście odcinków nie istnieją; `D` otwiera podgląd sugestii bez przycisku pobrania.
- Stany zleceń na liście odcinków → E2.
- Usunięcie ekranu RESULTS, grup, klawisza `G`, `O` z wyników, `take_draft` i `AnimeResult.SUBSCRIBE` → E3 (gdy nowa droga ma Pobierz i Subskrybuj). Do tego czasu stara droga pod `G` jest jedynym miejscem tworzenia subskrypcji.
- Usunięcie `search_title`, `catalog_releases`, grup i Nyaa z warstwy aplikacji → E5 (używa ich jeszcze stara subskrypcja).

### Dozwolone decyzje lokalne

- Nazwy prywatnych helperów, podział funkcji wewnątrz nowych modułów.
- Głębokość zagnieżdżenia relacji AniList (1–3) według wyniku fazy 0.
- Dokładne teksty etykiet, jeśli zachowują znaczenie z `ux.md`.
- Limit liczby zapamiętanych franczyz i list odcinków (stała z docstringiem).

### Zatrzymaj się i wróć po decyzję, gdy

- AniList odrzuca zapytanie o relacje przy każdej głębokości albo wymaga więcej niż 4 zapytań dla franczyzy Slime.
- Korpus nie osiąga wymaganej liczności lub pokrycia warstw w granicach Z-1; odłożone dane ujawniono autorowi; egzamin wykazał błędny `zgodny` albo właściciel nie zaakceptował zmierzonego pokrycia (§9 N-02, §15).
- Torrentio lub ani.zip odpowiada innym formatem niż w §6.4.
- Próba N-03 wymaga zmiany prywatnego profilu qB rezydenta.
- Potrzebna jest nowa zależność lub nowy kod błędu poza wymienionym w §10.2.

## 8. Kontekst do przeczytania (kolejność)

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | `AGENTS.md` + scoped `AGENTS.md` z §5 | Reguły | full |
| 2 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md` i jego referencje z §5 | Standard | full |
| 3 | `../spec.md` §3.3, §4, §5.1–5.2 | Kontrakt | sections |
| 4 | `../ux.md` §2–§6, §11–§13 | Ekrany, H1 i klawisze | sections |
| 5 | `anishift/cli/interactive/anime.py` | Kontroler do przebudowy | full |
| 6 | `anishift/application/acquisition.py:TitleCatalog`, `AcquisitionService`, `read_episode` | Protokoły, usługa i stara numeracja | symbols |
| 7 | `anishift/application/automation.py:AutomationOwner._acquisition_command`, `AutomationOwner._answer` | Dispatcher `acquisition` | symbols |
| 8 | `anishift/cli/resident.py:ResidentSession` | Klient IPC | symbols |
| 9 | `anishift/services/catalog/anilist.py`, `types.py` | Adapter AniList | full |
| 10 | `anishift/services/http_requests.py` | Limity | full |
| 11 | `anishift/bootstrap.py:_acquisition_service` | Wiring | symbol |
| 12 | `workspace/.archive/acquisition/evidence/matching/prepare.py.txt` | Pochodzenie historycznych etykiet; prototyp opcjonalnie do porównania, bez obowiązku odtwarzania reguł | sections |
| 13 | `workspace/.archive/acquisition/evidence/polish/study.py.txt:36–80`, `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt:34–116` | Ekstrakcja faktów | sections |
| 14 | `tests/integration/harness.py`, `tests/cli/test_interactive_anime.py` (struktura) | Testy | symbols |
| 15 | `anishift/services/llm/AGENTS.md`, `anishift/services/llm/engines/palantir/constants.py:PALANTIR_MODELS`, `anishift/config/model_catalog.py:load_model_catalog`, `anishift/application/runtime.py:palantir_llm_config` | Oceniający po E00 | symbols |
| 16 | `../outcomes/e00.md`, `e00-projekt-kodu.md` (Rozstrzygnięcia) | Dowody E00 i granice konfiguracji | sections |

## 9. Pomiary i reguły decyzji

Pomiary zapisują wyniki w `workspace/.archive/acquisition/evidence/e1/` (pliki < 500 KiB, bez sekretów, bez ścieżek absolutnych użytkownika). N-02 ma osobne archiwum surowych odpowiedzi poza checkoutem oraz odłożone dane dostępne wyłącznie opiekunowi (§9 N-02); nie kopiować ich do wspólnego katalogu wyników. Skrypty w `scripts/tmp/` są jednorazowe i nie są importowane przez aplikację.

**Uzupełnienie Z-1 — decyzja właściciela z 2026-09-25:** Torrentio na VPS zwróciło Cloudflare HTTP 403; dostęp lokalny na Windows działa. N-01 przeniesiono na Windows właściciela, nadal na 7 dni. N-02/N-04 działają lokalnie z surowymi danymi w `%USERPROFILE%/acquisition-corpus`, z limitem 1000 prób Torrentio w każdym ruchomym oknie 24 h, ≤4000 łącznie i twardym oknem 4 dób od pierwotnego startu. Reszta Z-1 z [../README.md](../README.md) §4 pozostaje bez zmian. Dane i historia prób VPS są zachowane; zmiana miejsca nie upoważnia do migracji archiwum, obejścia mismatch SHA ani kasowania wcześniejszych prób. To datowane uzupełnienie zgody, nie zmiana treści README.

### N-01 — opóźnienie pojawienia się odcinka

- **Próbka:** 8–12 tytułów o statusie RELEASING, których kolejny odcinek ma emisję w oknie 7 dni od startu pomiaru: najpierw wszystkie tytuły z aktywnych subskrypcji właściciela w `config/subscriptions.json` (identyfikator AniList z wpisu; tylko odczyt), uzupełnione najpopularniejszymi tytułami w emisji z AniList (`Page(media(status: RELEASING, sort: POPULARITY_DESC))`). Lista MAL nie jest używana (decyzja właściciela).
- **Miejsce:** lokalny Windows właściciela, według uzupełnienia Z-1 z 2026-09-25. N-01 działa przez 7 dni w odłączonym procesie z trwałym wznowieniem do pierwotnego deadline; nie uruchamiać go na VPS.
- **Przygotowanie pomiaru:** `scripts/tmp/` jest ignorowane przez regułę `tmp/` w `.gitignore`; sam checkout nie zawiera skryptów. Po fazach 3–4 potwierdzić lokalny commit/diff implementacji, SHA-256 skryptu i zasobów oraz import nowych adapterów i `episode_selection`. Wcześniejszy zbieracz N-02/N-04 z fazy 1 działa na surowych odpowiedziach, bez zależności od tych modułów. Tryb `freshness` i jego odłączony start/wznowienie powstają w fazie 5; obecny launcher `collect` obsługuje N-02/N-04, nie N-01.
- **Procedura (po utworzeniu skryptu CREATE):** `uv run python scripts/tmp/acquisition_probe.py freshness --days 7`. Dla każdego odcinka z emisją w oknie: od `airingAt` co 15 min przez 48 h, potem co 1 h do końca okna: (a) Torrentio `kitsu:<id>:<n>` + heurystyka; (b) RSS Nyaa dla aliasu tytułu (istniejący `anishift/services/torrents/nyaa.py:search_releases`, kategorie jak dziś) + ta sama heurystyka po nazwach. Zapis: czas pierwszego kandydata `zgodny` w każdym źródle, liczba kandydatów, zbiory hashy `zgodnych` z obu źródeł (pokrycie), nagłówki `Age`/`CF-Cache-Status`, odpowiedzi 429.
- **Wznowienie:** skrypt dopisuje JSONL i po restarcie pomija wykonane odczyty.
- **Horyzont per odcinek:** koniec pomiaru to zawsze start + 7 dni (Z-1), bez automatycznego przedłużania. Do zbioru rozstrzygającego wchodzą tylko odcinki obserwowane w obu źródłach od emisji przez co najmniej 48 h, z poprawnymi odczytami w zaplanowanych punktach tego okresu. Jeśli pierwsze zgodne wydanie Nyaa pojawi się później, trzeba dodatkowo mieć poprawne odczyty Torrentio do Nyaa + 1 h włącznie. Późna emisja, luka po restarcie, 429/błąd źródła lub koniec okna przed wymaganym terminem oznacza `incomplete_observation` z powodem; brak odpowiedzi nie jest pustym wynikiem. Takie odcinki pozostają w raporcie, lecz nie uczestniczą w regule opóźnienia ani pokrycia. „Wcale” znaczy wyłącznie „nie znaleziono w pełnym zmierzonym horyzoncie”, nigdy „nie istnieje”.
- **Reguła decyzji dla E3:**
  - Reguły poniżej dotyczą wyłącznie zbioru rozstrzygającego. Odcinek bez zgodnego wydania w obu źródłach nie dowodzi przewagi żadnego z nich; raportuje się go osobno. Mniej niż 5 pełnych, porównywalnych obserwacji → wynik nierozstrzygający i decyzja właściciela przed E2/E3, bez przedłużenia pomiaru w ramach obecnej zgody.
  - Jeśli w każdym porównywalnym odcinku Torrentio ma zgodnego kandydata nie później niż Nyaa + 1 h (istniejący interwał sprawdzania; gdy tylko Torrentio ma wydanie, warunek jest spełniony) → E3 używa tylko Torrentio; pierwsze sprawdzenie po emisji = najkrótsze zaobserwowane opóźnienie Torrentio zaokrąglone w dół do 15 min.
  - Jeśli w którymkolwiek porównywalnym odcinku Torrentio jest później niż Nyaa + 1 h albo nie ma wydania do końca pełnego horyzontu, a Nyaa je ma → E3 dodaje RSS Nyaa jako drugie źródło kandydatów subskrypcji, oceniane tą samą heurystyką; kod Nyaa nie jest usuwany w E5.
  - **Pokrycie:** jeśli w którymkolwiek odcinku zbioru rozstrzygającego Nyaa ma zgodne wydanie, którego nie ma Torrentio, a które według rankingu byłoby lepsze od najlepszego z Torrentio → E2 łączy kandydatów z obu źródeł także dla zwykłego Pobierz (deduplikacja po hashu).

### N-02 — budowa heurystyki od zera i jednorazowy egzamin

Decyzja właściciela (2026-09-24): najpierw duży oznaczony korpus, potem jego podział, budowa reguł wyłącznie na części roboczej i jeden egzamin na danych niewidzianych przez autora. Dopiero po zdaniu egzaminu powstaje czysta domena aplikacji. Cel: **≥ 2000 unikalnych tytułów i ≥ 10 000 unikalnych oznaczonych rekordów (odcinek + kandydat)**. Historyczne 231 rekordów nie ustanawia reguł; prototyp może być jednym z porównań na części roboczej.

- **Dobór tytułów:** początkowe 2000 różnych wpisów AniList, warstwowo, żeby próba nie była skrzywiona w stronę popularnych serii TV:
  - 1200 TV/TV_SHORT/ONA — po równo z przedziałów lat premiery: do 2005, 2006–2012, 2013–2018, 2019–2023, 2024+; w każdym przedziale kolejno według popularności AniList;
  - 400 OVA/SPECIAL i 200 MOVIE — tak samo po przedziałach lat;
  - 200 wpisów będących kontynuacją (ma krawędź `PREQUEL`: sezony 2+, części, cour) — tu heurystyka myli się najczęściej;
  - wszystkie tytuły z aktywnych subskrypcji właściciela (`config/subscriptions.json`, tylko odczyt), wliczone do puli.
   Najpierw zarezerwować kontynuacje i wpisy właściciela, potem uzupełnić pozostałe pule bez powtórzeń ID; tytuł liczy się tylko raz. Wpisy MOVIE należą do puli 200 filmów także wtedy, gdy są kontynuacją; pula dodatkowych 200 kontynuacji obejmuje pozostałe formaty. Zachować przekroje lat oraz osobne oznaczenia TV, sezonów/kontynuacji, OVA, ONA, specjali, filmów, spin-offów i długich serii z numeracją absolutną. Paczki/batche oznaczać na rekordach kandydatów; te przekroje mogą się nakładać i nie zwiększają liczności. Dobór w pulach ma zapewniać obecność tych przypadków, nie tylko popularność. Lista wpisów, warstwy, metoda doboru i ziarno zapisane w `evidence/e1/corpus/titles.json` u opiekuna; po podziale autor otrzymuje z niej wyłącznie tytuły robocze i agregaty, a pełny plik dołącza do chronionych źródeł. Brak którejś warstwy jest jawną luką do uzupełnienia w budżecie albo eskalacji, nie sukcesem korpusu.
- **Odcinki na tytuł:** odcinek 1 i ostatni wyemitowany, bez podwójnego zapytania, gdy to ten sam odcinek (film: jeden odczyt po N-04; przy braku obsługi raportować brak pokrycia filmów, nie tworzyć fikcyjnych rekordów). Każdy tytuł ma zapisane metadane AniList/ani.zip i wynik pozyskiwania kandydatów albo konkretny brak/błąd. Rekord identyfikuje cel `(anilist_id, numer)` i kandydata `(hash, fileIdx/ścieżka/nazwa pliku)`; powtórzona odpowiedź nie powiększa korpusu, różne cele tej samej paczki pozostają różnymi rekordami. Brak mapowania, pusta odpowiedź i błąd źródła nie są oznaczonym rekordem odcinek + kandydat.
- **Zbieranie przed kodem domeny:** lokalnie na Windows, po kontroli SHA-256/checkoutu. `scripts/tmp/acquisition_collect_local.ps1 -Action launch` uruchamia odłączony `acquisition_probe.py collect`: najpierw `movies` (N-04), potem `corpus` (N-02), we wspólnym archiwum i budżecie. W fazie 1 skrypt zbiera surowe AniList (franczyza i odcinki), ani.zip i Torrentio przez istniejący `httpx`/`RequestControl`; nie importuje jeszcze nieistniejących adapterów ani `episode_selection` i nie ocenia tożsamości. Surowe odpowiedzi leżą **poza checkoutem**, w `%USERPROFILE%/acquisition-corpus`; po podziale również kopie źródeł części odłożonej są niedostępne autorowi heurystyki. Lokalne `evidence/e1/corpus/` przechowuje jawny manifest, sumy i agregaty, a tylko część robocza może zawierać rekordy/próbki audytu dostępne autorowi (pliki < 500 KiB).
- **Obsługa lokalna:** przed startem opiekun przygotowuje archiwum i plik ID-only `%USERPROFILE%/acquisition-corpus/owner-ids.json`. Komendy z roota repo:

  ```powershell
  # Start
  powershell.exe -NoProfile -File ".\scripts\tmp\acquisition_collect_local.ps1" -Action launch
  # Status
  powershell.exe -NoProfile -File ".\scripts\tmp\acquisition_collect_local.ps1" -Action status
  # Cooperative stop
  powershell.exe -NoProfile -File ".\scripts\tmp\acquisition_collect_local.ps1" -Action stop
  # Resume after restart or stop
  powershell.exe -NoProfile -File ".\scripts\tmp\acquisition_collect_local.ps1" -Action launch
  # Owner-authorized retry after an uncertain attempt
  powershell.exe -NoProfile -File ".\scripts\tmp\acquisition_collect_local.ps1" -Action launch -RetryUncertain
  ```

  Zwykłe wznowienie nie resetuje liczników/deadline i nie wysyła zapisanych odpowiedzi ponownie. Niepewna próba domyślnie zatrzymuje pracę odwracalną pauzą; jawne `-RetryUncertain` (CLI: `--retry-uncertain`) zapisuje zgodę właściciela w journalu i dopuszcza nową próbę obciążającą budżet, zachowując wcześniejszą. Zgoda nie obejmuje kolejnej awarii nowej próby. Stop jest kooperacyjny, więc trwający HTTP może najpierw się zakończyć. Mismatch SHA/kontraktu wymaga osobnej decyzji; switch go nie obchodzi.
- **Wykonalność i Z-1:** zgoda [../README.md](../README.md) §4, uzupełniona decyzją z 2026-09-25 powyżej, obejmuje 2000 tytułów, ≤4000 prób Torrentio łącznie, ≤1000 w każdym rolling 24 h i twarde 4 doby lokalnie oraz osobny 7-dniowy N-01. Dla 200 filmów i 1800 pozostałych wpisów maksimum podstawowego doboru to `200 × 1 + 1800 × 2 = 3800` zapytań, przed odjęciem braków mapowania i wspólnych pierwszych/ostatnich odcinków. Próba N-04 ma `3 × 2 = 6` zapytań; nawet bez ponownego użycia jej odpowiedzi razem to 3806, pozostaje `4000 − 3806 = 194` na uzupełnienia lub ponowienia. Równomierny odstęp `86400 / 1000 = 86,4 s` daje dla 3806 prób około 3,8 doby + narzut i około 4,7 h nominalnego zapasu do 4 dób. Katalog, opóźnienia i przestoje mogą wyczerpać ten zapas; wynik kończy się wtedy jawną luką i eskalacją, bez automatycznego wydłużenia. 3806 jest szacunkiem górnym podstawowego doboru, nie wymaganym minimum ani warunkiem preflight — rzeczywisty dobór często potrzebuje mniej prób. Używać trwałego licznika wszystkich prób, także błędnych i niepewnych, zapisywanego przed transportem. 4000 jest granicą wymagającą nowej zgody przed przekroczeniem, nie deklarowanym limitem serwisu.
  - Aby 3800 odpowiedzi dało 10 000 rekordów, potrzeba średnio `10000 / 3800 ≈ 2,632` unikalnego kandydata; dla całych 4000 zapytań dolna granica średniej to 2,5 (błędy i próby bez rekordów podnoszą wymaganą średnią udanych odczytów). Z-1 **może** wystarczyć, ale liczby kandydatów i pokrycia warstw nie da się zagwarantować przed zebraniem. Historyczna gęsta próbka nie dowodzi wydajności nowego doboru. Kontrole dosypywane modelom, duplikaty i historyczne 231 nie uzupełniają minimum 10 000 nowych rekordów.
  - AniList: przy 1–4 zapytaniach franczyzy na wpis to 2000–8000 zapytań; istniejący odstęp 1 s daje nominalnie około 33 min 20 s–2 h 13 min 20 s samych odstępów. Do tego dochodzą strony listy tytułów, harmonogramów, opóźnienia odpowiedzi i cooldowny. Raportowany limit około 30/min oznacza przy jego obowiązywaniu około 1 h 6 min 40 s–4 h 26 min 40 s na same franczyzy; odstęp 1 s nie gwarantuje braku 429. ani.zip: do 2000 podstawowych odczytów mapowań. Zapisać rzeczywiste liczniki wszystkich źródeł; nie rozszerzać okna samoczynnie.
  - Torrentio: limit serwisu 5000/24 h/IP pozostaje niepotwierdzony. Licznik zbieracza obejmuje wspólne N-02/N-04, lecz **sam nie chroni przed innym ruchem aplikacji ani innymi procesami używającymi tego samego łącza**. Nie wyprowadzać z niego gwarancji zapasu dostawcy; respektować 429/cooldown, a 403 raportować jako blokadę źródła. Dla 12 równoczesnych obserwacji N-01 co 15 min to `12 × 96 = 1152` odczyty/dobę (do 12 dodatkowych odczytów początkowych); to osobny pomiar z dotychczasowym harmonogramem, nie zwiększenie budżetu korpusu. N-01 zaczyna po kodzie domeny i adapterach, więc podstawowe zbieranie korpusu i N-01 nie muszą się nakładać.
  - Jeśli po wykorzystaniu budżetu lub 4 dób brak 10 000 rekordów albo warstwy, zatrzymać zbieranie i rozstrzygnąć jedno pytanie Z-1 w §15; nie zmniejszać celu. Czas etykietowania i pracy offline nie jest czasem zapytań Z-1; bez pomiaru czasu paczki i udziału sporów nie ma wiarygodnej liczby dni dla całości. Dla dokładnie 10 000 rekordów i paczki 100: A i B wykonają po 100 paczek, razem 200 wywołań i `200 × 110 = 22 000` ocen wraz z kontrolami, przed arbitrażem, ponowieniami i ewentualnym podziałem paczek.
- **Ocena poprawności (etykiety) — cały korpus, nie próbka** (decyzja właściciela 2026-09-23: nieograniczona liczba agentów OpenCode):
   - każdy rekord korpusu (odcinek + kandydat) oceniają **dwaj niezależni „oceniający” — A: `foundry/gpt-6-astra`, B: `foundry-anthropic/claude-opus-5`**, każdy na całym korpusie (D3, 2026-09-24). „Oceniający” to wywołanie modelu z jednym stałym poleceniem oceny, bez narzędzi i bez dostępu do repozytorium; nie widzi decyzji heurystyki ani oceny drugiego modelu;
   - oceniający dostaje paczkę do 100 rekordów: tytuły i aliasy celu, numer lokalny/TVDB/absolutny, tytuł odcinka, nazwę wydania, ścieżkę, nazwę pliku; zwraca dla każdego `{id, etykieta, powód}` w JSON: `poprawny` / `błędny` / `nie da się ustalić` i jedno zdanie uzasadnienia do 160 znaków;
    - **kontrola jakości agenta:** do każdej paczki dosypywanych jest 10 losowych, różnych rekordów wyłącznie z jednoznacznie zakotwiczonego podzbioru `identity-231.json`. Fixture zachowuje `label`, `label_strength`, `label_provenance` i `label_rationale`. Podzbiór kontrolny dopuszcza tylko `label_strength` z listy `corrected_absolute`, `corrected_tvdb`, `title_or_tvdb_anchor`, po sprawdzeniu zgodności wskazanej kotwicy z wejściem modelu; listę ID, dowody i ziarno losowania zapisuje faza 0. `name_consistent` nie jest automatycznie wzorcem, a wszystkie 12 `ova-4` z `local_number_assumption` są wykluczone. Gdy pozostaje mniej niż 10 pewnych rekordów, próba zatrzymuje się zamiast dobierać niepewne. Wzorzec odpowiedzi to `label`, nie `heuristic.decision`: `match` → `poprawny`, `mismatch` → `błędny`, `insufficient_evidence` → `nie da się ustalić`. Ani etykiety, ich siła/pochodzenie/uzasadnienie, ani decyzja heurystyki nie trafiają do modelu. Pozostałe rekordy zostają danymi historycznymi, lecz nie odrzucają paczki oceniającego ani nie ustanawiają oczekiwanych decyzji nowej heurystyki. Źródła: `workspace/.archive/acquisition/evidence/matching/prepare.py.txt:186–214`, `../research/anime-api-report.md` §16. Paczka z błędem na rekordzie kontrolnym jest odrzucana i oceniana od nowa (ten sam model, nowe wywołanie; przy drugim błędzie — właściciel);
   - **niezgodność dwóch oceniających — decyzja właściciela 2026-09-25 (D3):** dyskusja dwóch świeżych instancji A (Astra) i B (Opus 5), bez historii i narzędzi. Każda widzi rekord oraz obie oceny z uzasadnieniami jako anonimowe „ocena 1/2”, w losowej kolejności, bez nazw modeli. Najwyższy dostępny `reasoning_variant` z `PALANTIR_MODELS` (obecnie `max` dla obu). Każda odpowiedź odnosi się do konkretnego faktu rekordu i argumentu drugiej strony, następnie podaje etykietę i powód. Zgoda wymaga tej samej etykiety i dwóch uzasadnień zakotwiczonych w danych. Najwyżej 3 rundy; od rundy 2 każda strona otrzymuje ostatni argument partnera. Brak zgody po rundzie 3 albo zgodne „nie da się ustalić” → lista właściciela. Kontrole nie uczestniczą w dyskusji. Zachować liczbę rund i przebieg etykiet, bez pełnych odpowiedzi; Gemini i Grok nie uczestniczą w aktywnym arbitrażu;
    - **Checkpoint dyskusji:** trwały zapis zawiera etykietę i zwartą kapsułę argumentu do 160 znaków, wskazanie pola i cytatu faktu oraz cytat **całego** ostatniego argumentu partnera i relację do niego (`supports`/`rebuts`/`insufficient`). Jedna litera, słowo lub dowolny wspólny podciąg nie spełnia kontraktu cytatu argumentu. Kapsuła zawiera cytat faktu i nowy argument; cytat partnera jest osobnym polem, aby kolejne rundy nie zagnieżdżały poprzednich kapsuł. Rozwinięte uzasadnienie do 1200 znaków zawiera oba cytaty i ich ocenę; jest walidowane, a następnie odrzucane wraz z pełną odpowiedzią. Walidator sprawdza strukturę i dosłowne kotwice, nie rozstrzyga semantycznie racji modeli. Następna runda zawsze używa nowej kapsuły, również bez restartu; resume w środku rundy zachowuje zapisaną stronę, uzupełnia brakującą i nie zeruje limitu rund. Nie odtwarza usuniętej prozy z samych etykiet. Błędny kontrakt odpowiedzi trafia do właściciela;
  - właściciel sprawdza wszystkie rekordy z tej listy i dodatkowo 50 losowych rekordów zgodnie ocenionych przez oba modele; każda jego niezgodność z oceną modeli → przegląd całej warstwy (np. wszystkich OVA), z której pochodził rekord;
  - oceniający są narzędziem oceny poza aplikacją; zakaz modelu AI w samym rozpoznawaniu odcinka (spec §9) nadal obowiązuje;
   - **Mechanizm — silnik LLM AniShift (`anishift.services.llm`, silnik Palantir)** (decyzja właściciela 2026-09-23; stan po E00): `scripts/tmp/corpus_labels.py` (CREATE, §10.3) nie ma własnej obsługi HTTP ani providerów i nie używa silnika tłumaczenia.
     - **Modele:** oceniający A — alias `foundry/gpt-6-astra` (ID providera `gpt-6-astra`); oceniający B — `foundry-anthropic/claude-opus-5` (ID `claude-opus-5`). Te same dwa modele w świeżych wywołaniach prowadzą dyskusję; nie ma trzeciego arbitra (decyzja właściciela 2026-09-25). Alias i wariant rozwiązuje `anishift/services/llm/engines/palantir/constants.py:PALANTIR_MODELS`; nie zastępować go ID z list modeli silników natywnych. Dostępność wywołań potwierdza `../outcomes/e00.md` (182/182); poprawność ocen sprawdza próba fazy 0.
     - **Wybór i konfiguracja:** `anishift/config/model_catalog.py:load_model_catalog()` zwraca projekcję `PALANTIR_MODELS` i `PALANTIR_PROVIDERS`, bez odczytu konfiguracji plikowej. `anishift/application/runtime.py:palantir_llm_config(catalog, alias, enrollment_base_url=..., token=..., max_retries=...)` rozwiązuje alias do `ModelEntry`, `ProviderEntry` i `LlmConfig(engine_id="palantir", provider_model_id, alias, provider_id, protocol, base_url, api_key)`. Trasa providera jest dołączana do adresu enrollmentu przez `palantir_model_config`; skrypt nie buduje URL-i żądań. Adres pochodzi z `anishift/config/user_settings.py:load_user_settings()` → `UserSettings.palantir_enrollment_base_url`. Token odczytuje wyłącznie `anishift/config/settings.py:Settings` → `palantir_token`: `ANISHIFT_PALANTIR_TOKEN` z env/pliku środowiska, a gdy pusty — `FOUNDRY_API_TOKEN` (precedencja w `anishift/services/llm/palantir_token.py:resolve_palantir_token`). Fabryka ma domyślnie `max_retries=0`, więc skrypt jawnie przekazuje wartość > 0.
      - **Rozumowanie i protokoły:** `anishift/services/llm/config.py:LlmConfig.reasoning_variant` domyślnie wynosi `None` i fabryka runtime go nie zmienia; oznacza opcje domyślne modelu przy niezależnej ocenie. Dyskusja wybiera najwyższy wariant z `PALANTIR_MODELS`; obecnie Opus 5 i Astra udostępniają `low`, `medium`, `high`, `xhigh`, `max`. Jawny wariant przekazuje kopia konfiguracji przez `dataclasses.replace`; obsługuje go istniejące `anishift/services/llm/engines/palantir/config.py:request_options`. Próba zapisuje użyty wariant, także `None`. Anthropic używa Messages z adaptive thinking, Astra — Responses (`store=False`, strumień). `LlmService.complete` zwraca końcowy `LlmResponse`, nie surowe delty; silnik pomija `temperature`/`top_p` dla aktywnego myślenia OpenAI/Anthropic.
      - **Paczka:** jedno `LlmService.complete(LlmRequest(messages=...))`: `LlmMessage(role=LlmRole.SYSTEM, parts=(TextPart(...),))` ze stałym poleceniem z `scripts/tmp/corpus_labels_prompt.md` (CREATE) + wiadomość USER z rekordami JSON jako `TextPart`. Ocena jest parsowana z `LlmResponse.text` do listy `{id, etykieta, powód}`. `FilePart` nie jest potrzebny do tekstowego korpusu. Usługa jest zamykana po przebiegu (context manager); każda instancja należy do jednego synchronicznego workera.
      - **Budżet odpowiedzi (B5):** start niezależnych ocen A i B to **100 rekordów roboczych + 10 pewnych kontroli, `max_output_tokens=32000`**. Dyskusja ma osobny kontrakt pojedynczego rekordu opisany wyżej. Skrypt ustawia `LlmConfig.max_output_tokens` przez `dataclasses.replace` przed utworzeniem usługi. Szacunek na rekord `{id, etykieta, powód}`: 80 tokenów na jednozdaniowy powód do 160 znaków oraz 48 na ID, etykietę i składnię JSON; razem 128 tokenów. Pełna lista to około `110 × 128 + 2 = 14082` tokenów, poniżej połowy budżetu (`16000`); reszta pozostaje na rozumowanie i błąd oszacowania. To założenie robocze do pomiaru w fazie 0, nie limit modelu ani gwarancja tokenizacji. `ModelEntry` i `PalantirModel` celowo nie mają limitów (E00, `e00-projekt-kodu.md`, Rozstrzygnięcie 15); nie potrzeba nowego źródła tych danych. Pełnowymiarowa próba na każdym modelu zapisuje rzeczywiste zużycie i `finish_reason`, a jej poprawny wynik potwierdza roboczą parę rozmiar/budżet dla tego modelu, bez zmian katalogu i silnika.
      - **Jedna reguła adaptacji budżetu/paczki:** przed parsowaniem JSON sprawdzić `LlmResponse.finish_reason`; `max_tokens` i `max_output_tokens` odrzucają całą odpowiedź, także poprawny JSON. Po ucięciu podzielić rekordy robocze na połowy (większa część zaokrąglona w górę), zachowując budżet. Po potwierdzonym odrzuceniu wartości parametru budżetu przez proxy (4xx) zmniejszyć budżet o połowę i tak samo podzielić paczkę; w razie potrzeby dzielić dalej, aż każda część spełni `128 × (liczba rekordów roboczych + 10) + 2 ≤ max_output_tokens / 2`. Każda część otrzymuje 10 pewnych kontroli. Nie ponawiać identycznej odrzuconej/uciętej paczki; zmienioną parę rozmiar/budżet potwierdzić pełnowymiarową próbą na danym modelu przed dalszą oceną. Podział jest deterministyczny, ma trwałe ID części w JSONL i obejmuje niezależne paczki A i B; dyskusja pojedynczego rekordu nie podlega podziałowi. Ucięcie przy jednym rekordzie roboczym + 10 kontrolnych, brak miejsca na takie minimum lub dalsze odrzucenie minimum kończy ocenę na tym modelu i wraca po decyzję, bez pomijania kontroli. Inne 4xx nie są dowodem złego budżetu i podlegają istniejącej obsłudze błędów. To adaptacja kontraktu odpowiedzi w skrypcie, nie retry transportu ani zmiana silnika.
     - **Konto 2 (D2, krok fazy 0):** `Settings.palantir_fallback_origin` ← `ANISHIFT_PALANTIR_FALLBACK_ORIGIN` oraz `Settings.palantir_fallback_api_key` ← `ANISHIFT_PALANTIR_FALLBACK_API_KEY`, oba `str`, domyślnie `""`, `repr=False`, przez istniejący odczyt env/`.env`. Konto 2 wymaga **obu** wartości: osobnego tokena oraz adresu enrollmentu `https://host` (opcjonalny końcowy `/`), bez ścieżki, query i fragmentu. Dowód: `anishift/services/llm/engines/palantir/accounts.py:palantir_accounts`, `account_request` oraz `config.py:require_palantir_origin`. `fallback_origin` nie jest pełnym URL-em providera: `account_request` zmienia tylko scheme/netloc i bearer token, zachowując trasę oraz query żądania konta 1. `palantir_llm_config` otrzymuje opcjonalne argumenty `fallback_origin=""`, `fallback_api_key=""` i przekazuje je do istniejących pól `LlmConfig`; `corpus_labels.py` przekazuje wartości z `Settings`. Bez konta 2 działa konto 1 jak dziś; niepełna para nie włącza failoveru, zgodnie z istniejącym `palantir_accounts`. Przed oceną na dwóch kontach faza 0 wymaga kompletnej pary. Właściciel sam wpisuje wartości do `.env`; agent nie czyta `.env` ani plików z tokenami. Bez nowych pól panelu i zmian wywołań silnika tłumaczenia.
     - **Retry i failover:** retry wyłącznie błędów przejściowych należy do `LlmService` i `anishift/services/llm/_retry.py:retry_transient`; skrypt nie dodaje retry transportu. `anishift/services/llm/engines/palantir/http.py:_send` przełącza konto wyłącznie po HTTP 429/≥500, przed odczytem body; cooldown 60 s jest wspólny procesowo, kluczowany originem (`accounts.py:account_order`, `start_cooldown`). Błąd sieci, body, generowania lub autoryzacji nie uruchamia failoveru. Kod `anishift/services/llm/` pozostaje bez zmian.
     - **Równoległość (D3, decyzja właściciela 2026-09-25):** globalny start 4 workery dla A/B, dyskusji i obu kont; osobne `LlmService`/klienty per wywołanie. Pierwsze kwalifikujące się okno 10 ukończonych pełnych paczek ustala mediany bazowe. Następne stabilne okno 10 paczek bez 429, 5xx, niekompletnych/uciętych odpowiedzi i wzrostu median ponad 25% → +2. Porównywać tylko modele obecne w obu oknach z minimum 3 próbkami każdego w każdym oknie; przy braku danych utrzymać limit. Okno ze wzrostem ponad 25% nie zastępuje stabilnej bazy. Po 429 albo dwóch kolejnych oknach z takim wzrostem → połowa limitu, minimum 1. Retry i cooldown pozostają wyłącznie w `LlmService`. Limit nie jest zmierzonym limitem dostawcy.
      - Skrypt dzieli rekordy na paczki (do 100 + 10 kontrolnych, najwyżej rozmiar potwierdzony dla modelu w fazie 0), po kontroli `finish_reason` waliduje poprawny JSON, każdy `id` dokładnie raz, dozwoloną etykietę i niepusty powód do 160 znaków. Niepoprawna, lecz nieucięta odpowiedź oznacza paczkę ocenianą od nowa, najwyżej dwa razy, potem wszystkie jej rekordy trafiają do właściciela. **Jeden pisarz** odbiera zakończone paczki oraz decyzje podziału i zapisuje je od razu do JSONL; workerzy nie zapisują pliku. Wznawianie odtwarza drzewo podziałów i budżety części, pomija ukończone pary `(oceniający, id części)` i podejmuje niezapisane, także luki po paczkach ukończonych poza kolejnością; bez powtórnego wysyłania rodzica po podziale i bez duplikacji ocen. Liczy zgodność, obsługuje rekordy kontrolne i listę dla właściciela. Dwa niezależne pełne przebiegi = dwaj oceniający. Działa lokalnie na Windows; opiekun przygotowuje przycięte rekordy z lokalnego archiwum poza checkoutem.
      - **E1 nie zmienia kodu `anishift.services.llm` ani silnika tłumaczenia.** Brak modelu albo trwały błąd wywołania oznacza zatrzymanie i powrót po decyzję, nie obejście w skrypcie. Pełne paczki A/B mają historyczne potwierdzenie phase0c w `outcomes/e1.md`. Historyczne próby trzecich modeli nie są bramką aktywnej fazy 1; decyzja 2026-09-25 zastępuje je dyskusją A/B. Dyskusja ocenia jeden sporny rekord bez kontroli, przy budżecie 32000; ucięcie lub błędny kontrakt kieruje rekord do właściciela.
- **Podział przed budową reguł:** po zamknięciu etykiet opiekun danych (właściciel albo osobny wykonawca, który nie będzie autorem heurystyki) ustala z właścicielem liczebności części roboczej i odłożonej na podstawie rzeczywistych liczności warstw. Zapisuje je przed losowaniem wraz z algorytmem, ziarnem i SHA-256 wejścia w `split-manifest.json`; nie dobiera proporcji po obejrzeniu wyników heurystyki. Podział jest stały, losowy i stratyfikowany według zapisanych warstw, z licznikami każdego przekroju w obu częściach. Grupować wspólne franczyzy oraz rekordy współdzielące hash/pliki w jednej części, żeby sezon, paczka albo duplikat nie przeciekał między budową a egzaminem. Gdy grupowanie uniemożliwia reprezentację warstwy w obu częściach, uzupełnić dane w zgodzie Z-1 albo zgłosić lukę; nie rozcinać grup dla pozornej stratyfikacji. Historyczne 231, kontrole, materiały pilota i inne rekordy już widziane przez przyszłego autora (także ich grupy powiązane) są wyłącznie robocze i nie stanowią nowego egzaminu.
- **Techniczne odseparowanie:** opiekun przygotowuje osobne `working.jsonl` i `heldout.jsonl` (przy większym rozmiarze deterministyczne części < 500 KiB, ze wspólnym manifestem) oraz sumy SHA-256 danych, etykiet i mapy podziału. Autor dostaje tylko część roboczą i manifest z agregatami/sumami, bez ID, nazw, wejść i etykiet odłożonych rekordów. `heldout.jsonl`, jego surowe źródła, oceny modeli, logi paczek i kopie zostają poza checkoutem w katalogu pod osobnym kontem opiekuna; konto/sesja autora nie ma odczytu pełnego lokalnego archiwum ani jego kopii, także historycznych danych VPS. Sam zakaz w poleceniu lub suma kontrolna nie blokuje odczytu: przed przekazaniem pracy sprawdzić faktyczną odmowę odczytu z konta autora. Jeśli środowisko nie potrafi tej granicy zapewnić, budowa czeka. Autor startuje w świeżej sesji, bez transkryptów zbierania/etykietowania. Opiekun i autor mogą używać tego samego modelu, ale nie tej samej sesji ani przestrzeni dostępu.
- **Budowa od zera:** jednorazowy `scripts/tmp/identity_study.py` analizuje etykiety i stroi jawne deterministyczne reguły tylko na `working.jsonl`; bez LLM/ML w rozpoznawaniu. Rejestrować wersje reguł, błędy i metryki per warstwa. Prototyp może być porównaniem na roboczej części, nie źródłem oczekiwań ani wymogiem implementacyjnym. Część robocza jest wielokrotnego użytku; przed egzaminem zamrozić reguły, kod, normalizację wejścia i wersję skryptu metryk z sumami SHA-256. Brak dostępu do odłożonej części dotyczy także strojenia ekstrakcji celu, parserów i wyboru wariantu reguł.
- **Egzamin raz:** opiekun uruchamia `scripts/tmp/identity_exam.py` na zamrożonym artefakcie, w odizolowanym procesie bez sieci i zapisu przez kod heurystyki, z kontrolowanym wyjściem. Zatwierdzony skrypt przekazuje regułom tylko wejście pojedynczego rekordu, nigdy etykietę, przechwytuje stdout/stderr/wyjątki i zwraca autorowi **wyłącznie agregaty metryk**, bez ID, nazw, przykładów i szczegółów rekordowych. Review skryptu przed egzaminem wyklucza kanały wycieku i zmianę reguł podczas wykonania. Manifest i SHA-256 części odłożonej sprawdzić przed i po; wynik wiąże sumę reguł, danych, etykiet oraz skryptu. Opiekun zapisuje próbę jako wykorzystaną **przed pierwszym odczytem rekordów**; awaria po otwarciu danych również zużywa część. Nie ma drugiego uruchomienia na tej części dla poprawionego wariantu.
- **Metryki i decyzja:** osobno dla części roboczej i egzaminacyjnej: liczby tytułów, odcinków i rekordów per warstwa; macierz etykieta × decyzja, liczba błędnych `zgodnych` (`match` przy `błędny`), liczba i udział `niepewnych` w całej warstwie, liczba i udział błędnych `niezgodnych` w rekordach o etykiecie `poprawny`, odsetek odcinków z co najmniej jednym `match` oraz czas oceny. Dla każdego odsetka podać licznik i mianownik; pusty mianownik to brak danych, nie 0%. Osobno pokazać `match` przy `nie da się ustalić`: nie uznawać go za potwierdzony sukces ani nie ukrywać przez usunięcie rekordu; wymaga rozliczenia z właścicielem. Braki mapowań, puste odpowiedzi i błędy zbierania pozostają w raporcie pokrycia wszystkich 2000 tytułów.
  - Warunek egzaminu: **0 błędnych `zgodnych`**. Udział `niepewnych` i błędnych `niezgodnych` per warstwa właściciel ocenia na liczbach, bez progu wymyślonego w planie; heurystyka zwracająca wszędzie `niepewny` nie przechodzi automatycznie dzięki zeru błędnych akceptacji. Wynik jest dowodem dla zmierzonej części, nie gwarancją braku błędu na dowolnych danych.
  - Porażka egzaminu albo odrzucenie pokrycia przez właściciela → nowa iteracja na części roboczej i **nowa część odłożona**, ze świeżych danych albo wcześniej zamrożonej, niewykorzystanej rezerwy. Stara część jest trwale oznaczona jako wykorzystana; po egzaminie może zasilać diagnozę/regresje, lecz nigdy ponownie dowód uogólniania. Zmiana reguł po zdanym egzaminie również wymaga nowego egzaminu; nowe zapytania tylko w granicach zgody albo po jej rozszerzeniu (§15).
- **Regresja w domenie po egzaminie:** stałe próbki z części roboczej obejmują każdą warstwę, jej wykryte błędy, przypadki sporne rozliczone etykietą oraz dotychczasowe edge cases. Trafiają do `tests/fixtures/acquisition/identity-corpus.json` z ID, wejściem, etykietą, siłą/pochodzeniem i oczekiwaniem uzasadnionym etykietą. Nie kopiować do fixture nadal niewykorzystanych odłożonych rekordów ani ich źródeł. Historyczne słabe etykiety zachować z jawną siłą, a przed użyciem jako twarde oczekiwanie rozliczyć z opiekunem; nie kopiować błędów `heuristic.decision`. Oczekiwanie `niepewny` przy zbyt słabym dowodzie wymaga jawnego uzasadnienia z danych, nie parytetu z prototypem.

### N-03 — metadane z samego hasha

- **Procedura:** `scripts/tmp/magnet_probe.py` uruchamia osobny `qbittorrent.exe` z `--profile=<temp>`, `--webui-port`, `--torrenting-port` (wzorzec `workspace/.archive/acquisition/evidence/bundle/run01/probe-*.py.txt`), z włączonym DHT i domyślnymi ustawieniami sieci, zapis do katalogu tymczasowego poza repo. Dla 3 kandydatów `zgodnych` z N-02 (1 pojedynczy plik, 2 paczki): dodanie magnetu `magnet:?xt=urn:btih:<hash>&tr=<trackery z sources>` z parametrem `stopCondition=MetadataReceived`; odczyt co 1 s `torrents/info` i `torrents/files` do otrzymania listy plików; zapis czasu; ustawienie priorytetu 0 wszystkim plikom poza wskazanym (mapowanie według U-18) i priorytetu 1 wskazanemu; **bez startu**; odczyt `downloaded`, listy plików na dysku; usunięcie torrentu z `deleteFiles=true`; zatrzymanie procesu; usunięcie katalogu tymczasowego.
- **Wynik:** czas do metadanych, bajty pobrane przed zatrzymaniem, pliki utworzone na dysku, zgodność `fileIdx` z indeksem qB, czy mapowanie U-18 wskazało plik jednoznacznie.
- **Reguła decyzji:** jeśli wszystkie 3 dały listę plików, zatrzymały się bez zapisu plików treści i mapowanie było jednoznaczne → E2 używa tej sekwencji. Jeśli którakolwiek nie dała metadanych w 10 min albo zapisała treść → stop przed E2, decyzja właściciela.

### N-04 — filmy

- **Procedura (po utworzeniu skryptu CREATE):** `uv run python scripts/tmp/acquisition_probe.py movies` dla 3 filmów z franczyz z próbki: Torrentio `stream/movie/kitsu:<id>.json` i `stream/series/kitsu:<id>:1.json`.
- **Reguła decyzji:** jeśli którykolwiek wariant zwraca kandydatów dla wszystkich 3 filmów → E2 dodaje Pobierz dla filmów (plan E2 określi regułę tożsamości filmu). W przeciwnym razie U-21 zostaje odłożone.

## 10. Target design

### 10.1 Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `services/catalog/anilist.py` | Zapytania AniList, parsowanie do typów katalogu | Grupowanie wpisów w UI, tożsamość wydań |
| `services/catalog/anizip.py` (NEW) | Zapytanie ani.zip po AniList ID, parsowanie odcinków i mapowań, czas ważności z `Cache-Control` | Łączenie z harmonogramem AniList |
| `services/torrents/torrentio.py` (NEW) | Zapytanie Torrentio po Kitsu ID i numerze, parsowanie strumieni do faktów surowych | Ocena tożsamości, ranking |
| `application/episode_selection.py` (NEW) | Kontrakty E1, uzupełnienie listy odcinków, cel odcinka, heurystyka tożsamości, fakty wydania z nazw, ranking | I/O, konfiguracja, UI |
| `application/acquisition.py` | Pobranie franczyzy, danych listy (ani.zip + harmonogram + liczba odcinków), wywołanie czystego składania listy i oferty; pamięć odpowiedzi | Render, stan trwały |
| `application/automation.py` | Dispatch nowych pod-operacji pod limitem `requests("user")` | Logika wyboru |
| `cli/resident.py` | Metody klienta IPC | — |
| `cli/interactive/anime.py` | Stan ekranów i klawisze | Sieć w renderze |

### 10.2 Przepływ danych

```text
Anime.Query ──titles──▶ AniList.search ──▶ TitleCandidate[]
Titles(Enter) ──franchise(anilist_id)──▶ AniList relations (warstwami, id_in) ──▶ Franchise
Entries(Enter) ──episodes(anilist_id)──▶ ani.zip(anilist_id) + AniList.airing_schedule (także episode_count) ──▶ episode_selection ──▶ EpisodeListing
Episodes(D, dla każdego zaznaczonego, po kolei) ──offer(anilist_id, numer)──▶
      Torrentio(kitsu_id, numer) ──▶ StreamCandidate[]
      episode_target(franchise, listing, numer) ──▶ EpisodeTarget
      assess_identity + release_facts + rank ──▶ EpisodeOffer
Offer(I) ──▶ Candidates (lokalnie, bez sieci)
```

Błędy: AniList → `TitleCatalogError` (`TITLE_CATALOG_FAILED`), ani.zip → `TitleCatalogError` z nowym kodem `EPISODE_CATALOG_FAILED`, Torrentio → `TorrentSourceError` (`TORRENT_SOURCE_FAILED`). Jedyny nowy kod błędu: `ErrorCode.EPISODE_CATALOG_FAILED` w `anishift/errors.py` (sekcja Catalog).

### 10.3 Docelowe drzewo (zmiany)

`CREATE` oznacza plik lub rodzinę plików tworzonych w E1, nie istniejące API. Pozostałe wymienione moduły, symbole i polecenia pomiarowe z §10–§11 są projektowane, jeśli nie opisano ich w §6 jako istniejących. Skróty ścieżek rozwija §5.

```text
anishift/
├── errors.py                                  # MODIFY: EPISODE_CATALOG_FAILED
├── bootstrap.py                               # MODIFY: wiring AniZipCatalog, TorrentioSource
├── config/settings.py                         # MODIFY: dane konta 2 Palantira z env/.env (faza 0)
├── application/
│   ├── runtime.py                             # MODIFY: opcjonalne fallback_origin/fallback_api_key w palantir_llm_config
│   ├── episode_selection.py                   # CREATE: wszystkie nowe kontrakty §10.4 i czyste funkcje
│   ├── discovery.py                           # MODIFY: publiczna VIDEO_SOURCE_SUFFIXES
│   ├── acquisition.py                         # MODIFY: franchise/episodes/offer, pamięć
│   ├── automation.py                          # MODIFY: pod-operacje franchise/episodes/offer
│   ├── __init__.py                            # MODIFY: eksport nowych typów
│   └── AGENTS.md                              # MODIFY: opis episode_selection
├── services/
│   ├── http_requests.py                       # MODIFY: dostawcy anizip, torrentio
│   ├── catalog/
│   │   ├── anilist.py                         # MODIFY: franchise()
│   │   ├── anizip.py                          # CREATE
│   │   ├── __init__.py                        # MODIFY
│   │   └── AGENTS.md                          # MODIFY
│   └── torrents/
│       ├── torrentio.py                       # CREATE
│       ├── __init__.py                        # MODIFY
│       └── AGENTS.md                          # MODIFY
└── cli/
    ├── resident.py                            # MODIFY: franchise/episodes/offer
    ├── AGENTS.md                              # MODIFY: nowe ekrany Anime
    └── interactive/
        ├── anime.py                           # MODIFY: nowe ekrany, komunikaty, przejście do Nyaa według W-08
        └── state.py                           # MODIFY: przekazanie istniejących provider_locks do Anime
tests/
├── config/test_model_settings.py              # MODIFY: Settings → fabryka → konto 2, prywatność i brak konta 2
├── fixtures/
│   ├── search/manifest.json                   # MODIFY: wpisy anizip, torrentio, anilist franchise
│   ├── search/anizip__*.json                   # CREATE (kopie z evidence)
│   ├── search/torrentio__*.json                # CREATE (kopie z evidence)
│   ├── search/anilist__franchise__*.json        # CREATE (nagrane w fazie 0)
│   ├── acquisition/identity-231.json           # CREATE (przycięty dataset.json)
│   └── acquisition/identity-corpus.json        # CREATE (N-02)
├── application/test_episode_selection.py       # CREATE
├── application/test_architecture.py            # MODIFY: episode_selection.py w _PURE_MODULES, httpx w _PURE_FORBIDDEN
├── application/test_acquisition.py            # MODIFY
├── application/test_automation.py             # MODIFY: pod-operacje, W-08, komunikat obu źródeł, blokada po 429
├── services/catalog/test_anizip.py             # CREATE
├── services/catalog/test_anilist.py           # MODIFY
├── services/torrents/test_torrentio.py          # CREATE
├── services/test_http_requests.py             # MODIFY
├── integration/harness.py                     # MODIFY: odtwarzanie anizip/torrentio
├── integration/test_search_pipeline.py        # MODIFY: nowa ścieżka
├── integration/test_search_live.py            # MODIFY: network dla anizip/torrentio/franchise
├── cli/test_interactive_anime.py              # MODIFY
├── cli/test_interactive_state.py              # MODIFY: provider_locks przekazane do Anime
└── cli/test_resident.py                       # MODIFY
scripts/tmp/
├── acquisition_probe.py                       # CREATE (jednorazowy)
├── acquisition_collect_local.ps1               # CREATE (odłączony start/status/stop/resume N-02/N-04)
├── corpus_labels.py                           # CREATE (N-02, opisany w §9)
├── corpus_labels_prompt.md                    # CREATE (stałe polecenie z §9)
├── identity_study.py                           # CREATE (analiza i strojenie tylko części roboczej)
├── identity_exam.py                            # CREATE (jednorazowy egzamin u opiekuna, tylko metryki)
└── magnet_probe.py                            # CREATE (jednorazowy)
workspace/.archive/acquisition/evidence/e1/     # CREATE: wyniki pomiarów (lokalnie, poza gitem)
├── corpus/                                    # CREATE: jawny manifest podziału, sumy, agregaty, tylko dane robocze
└── magnet/                                    # CREATE: wynik N-03
docs/work/acquisition/outcomes/e1.md            # CREATE: wynik etapu
%USERPROFILE%/acquisition-corpus/               # CREATE: surowe dane lokalnie na Windows, poza checkoutem; odłożone źródła dostępne tylko opiekunowi
```

### 10.4 Kontrakty danych

Poniższe dataclassy są **nowymi kontraktami E1**, wszystkie zdefiniowane w `anishift/application/episode_selection.py`: `@dataclass(frozen=True, slots=True)`, kodowane przez istniejące `anishift/application/control_views.py:encode_view`/`decode_view`. `EntryGroup` i `IdentityVerdict` są nowymi enumami w tym samym module. Numery odcinków są `int`: tak numerują je klucze ani.zip (`"1".."n"`) i istniejące `anishift/services/catalog/types.py:EpisodeAiring.episode`.

**Ownership i kierunek importów — decyzja:** `Franchise`, `EpisodeListing`, `StreamCandidate`, `EpisodeTarget`, `RankedCandidate` oraz ich nowe typy składowe należą do czystej aplikacji, nie do `services/*/types.py`. Adaptery importują te kontrakty z `application/episode_selection.py`; czysty moduł nie importuje usług nawet pod `TYPE_CHECKING`. Wzorzec własności czystych dataclassów: `anishift/application/artifacts.py:Artifact`; wzorzec kontraktu aplikacji używanego przez usługę: `anishift/application/cancellation.py:CancellationToken` → `anishift/services/media/probe.py:MediaProbe.identify`. Istniejące `TitleStatus`, `SeasonAiring` i `EpisodeAiring` zostają w katalogu. Na granicy `AcquisitionService` projektuje harmonogram do `ListedEpisode` i przekazuje status jako `TitleStatus.value` (`str`); adapter franczyzy tak samo zapisuje wartość statusu. Nie powstaje drugi enum statusów ani zmiana kontraktu adaptera `airing_schedule`.

**IPC — decyzja:** wszystkie typy użyte w adnotacjach nowych dataclassów są dostępne w runtime w module definicji: nowe dataclassy i enumy lokalnie, `date`/`datetime` przez zwykłe importy. Nie ukrywać tych importów pod `TYPE_CHECKING`. `control_views._adapter` korzysta z przestrzeni modułu przekazanego modelu przez `TypeAdapter(model)`; nowe kontrakty nie wymagają rozszerzania wyjątków `Release`/`ReleaseName` w `_types_namespace`. `application/__init__.py` eksportuje typy dla CLI. Faza 6 potwierdza strict round-trip `Franchise`, `EpisodeListing` i `EpisodeOffer` z zagnieżdżonym `RankedCandidate.stream`, enumami, datami i `None`; nie osłabia strażnika architektury ani dekodera.

**`application/episode_selection.py` — katalog i lista**

```text
FranchiseEntry
  anilist_id: int
  romaji: str
  english: str | None
  native: str | None
  format: str | None            # AniList: TV, TV_SHORT, ONA, OVA, SPECIAL, MOVIE, MUSIC
  status: str                   # wartość istniejącego TitleStatus, przekazana przez granicę I/O
  year: int | None              # seasonYear, inaczej startDate.year
  start: date | None
  relation: str                 # "SELF" dla wybranego; inaczej typ krawędzi, po której wpis dołączono
  group: EntryGroup             # StrEnum: SEASON="season", EXTRA="extra", OTHER="other" (reguła §10.5.1)

Franchise
  selected_id: int
  entries: tuple[FranchiseEntry, ...]   # kolejność: SEASON, EXTRA, OTHER (jawny indeks grupy); w grupie start rosnąco, brak daty na końcu, potem anilist_id
  relations: tuple[FranchiseRelation, ...]  # rzeczywiste krawędzie, niezależne od grup i korzenia widoku
  complete: bool                        # False, gdy przerwano na limicie zapytań

FranchiseRelation
  source_id: int
  target_id: int
  relation: str                 # oryginalny relationType AniList

ListedEpisode
  number: int                   # klucz ani.zip, numer z harmonogramu albo uzupełnienie 1..episode_count
  title: str | None             # title.en, inaczej title["x-jat"], inaczej None
  airs_at: datetime | None      # AniList airingSchedule (U-13); brak → airDateUtc ani.zip; brak → None
  season: int | None            # seasonNumber (TVDB)
  episode: int | None           # episodeNumber (TVDB)
  absolute: int | None          # absoluteEpisodeNumber

ListedSpecial
  key: str                      # "S1", "S2"…
  title: str | None
  airs_on: date | None          # data z airDateUtc ani.zip

AniZipMapping                   # surowy wynik adaptera ani.zip
  kitsu_id: int | None
  catalog_type: str | None      # mappings.type
  episode_count: int | None     # episodeCount
  episodes: tuple[ListedEpisode, ...]   # bez harmonogramu AniList; airs_at = airDateUtc
  specials: tuple[ListedSpecial, ...]
  max_age_s: int | None         # z nagłówka Cache-Control: max-age; brak nagłówka → None

EpisodeListing                  # wynik czystego złożenia ani.zip + harmonogram + liczba odcinków
  anilist_id: int
  kitsu_id: int | None
  catalog_type: str | None
  status: str                   # wartość istniejącego TitleStatus, przekazana przez granicę I/O
  episode_count: int | None     # AniList episodes, inaczej episodeCount ani.zip
  episodes: tuple[ListedEpisode, ...]
  specials: tuple[ListedSpecial, ...]
  aired: int | None             # U-15: RELEASING → liczba dat harmonogramu AniList ≤ teraz; FINISHED → liczba odcinków AniList; inaczej/brak danych → None
  schedule_warning: str | None  # "TITLE_CATALOG_FAILED" po błędzie harmonogramu, inaczej None; kod, nie tekst wyjątku
  schedule_retry_at: datetime | None  # blokada anilist z RequestControl w chwili odpowiedzi; brak blokady → None
```

**`application/episode_selection.py` — kandydat źródła**

```text
StreamCandidate
  info_hash: str                # małe litery
  name: str | None              # surowe pole name Torrentio; deklaracja rozdzielczości, nie tożsamości
  file_index: int | None        # fileIdx; brak ≠ 0
  file_name: str | None         # behaviorHints.filename
  release: str                  # pierwsza linia title
  path: str | None              # druga linia title, gdy nie zaczyna się od 👤
  seeders: int | None           # liczba po 👤
  size_text: str | None         # tekst po 💾, np. "592.94 MB"
  provider: str | None          # tekst po ⚙️
  tags: tuple[str, ...]         # linia po linii 👤, podzielona " / " (np. "Dubbed", "Multi Subs", "🇵🇱")
  trackers: tuple[str, ...]     # elementy sources z prefiksem "tracker:", bez prefiksu
```

**`application/episode_selection.py` — cel i ocena**

```text
EpisodeKey
  anilist_id: int
  number: int

IdentityVerdict(StrEnum): MATCH="match", MISMATCH="mismatch", INSUFFICIENT="insufficient_evidence"

IdentityAssessment
  verdict: IdentityVerdict
  reason: str                   # angielskie zdanie z heurystyki; UI tłumaczy przez mapę zdanie → polskie zdanie

EpisodeTarget                   # pola i znaczenie jak w workspace/.archive/acquisition/evidence/matching/targets.json
  aliases: tuple[str, ...]
  other_series: tuple[str, ...]
  kind: str                     # "TV" | "OVA"
  local_episode: int
  season: int | None
  episode: int | None
  absolute: int | None
  episode_title: str | None
  other_episode_titles: tuple[str, ...]
  isolated_series: bool = False # osobna gałąź spin-off/OTHER; nie występuje w zamrożonych celach badania

ReleaseFacts
  resolution: int | None        # §10.5.5
  polish: bool                  # 🇵🇱 w tags albo token "POL"/"Polish"/"PL" (reguła study.language)
  multisub: bool                # "Multi Subs", "MultiSub", "Multi-Subs", "Multiple Subtitle"
  platform: str | None          # "Netflix" dla NF/Netflix, "Crunchyroll" dla CR/Crunchyroll (całe tokeny)
  dub_only: bool                # "Dubbed" w tags i brak "Dual Audio"/"Multi Audio" (niezależnie od polish)
  container: str | None         # rozszerzenie file_name (małe litery, z kropką); brak nazwy/rozszerzenia → None
  supported: bool | None        # True: obsługiwany; False: jawnie nieobsługiwany; None: kontener nieznany

RankedCandidate
  stream: StreamCandidate
  identity: IdentityAssessment
  facts: ReleaseFacts

EpisodeOffer
  key: EpisodeKey
  candidates: tuple[RankedCandidate, ...]   # zgodni wg klucza §10.5.5, potem niepewni (ten sam klucz), potem niezgodni (kolejność odpowiedzi)
  suggestion: int | None                    # indeks pierwszego zgodnego z supported is not False
  checked_at: datetime
  counts: dict[str, int]                    # klucze: "match", "insufficient_evidence", "mismatch"
```

Funkcje publiczne `episode_selection.py`:

```text
episode_listing(anilist_id: int, mapping: AniZipMapping, status: str, episode_count: int | None, schedule: Sequence[ListedEpisode], now: datetime, *, schedule_warning: str | None = None, schedule_retry_at: datetime | None = None) -> EpisodeListing
episode_target(franchise: Franchise, listing: EpisodeListing, number: int) -> EpisodeTarget
assess_identity(target: EpisodeTarget, stream: StreamCandidate) -> IdentityAssessment
release_facts(stream: StreamCandidate) -> ReleaseFacts
rank_candidates(target: EpisodeTarget, streams: Sequence[StreamCandidate]) -> tuple[RankedCandidate, ...]
```

Protokoły w `application/acquisition.py` (wzorzec istniejącego `TitleCatalog`):

```text
EpisodeCatalog:   mapping(anilist_id: int) -> AniZipMapping
FranchiseCatalog: franchise(anilist_id: int) -> Franchise          # realizuje AniListCatalog
StreamSource:     streams(kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]
```

### 10.5 Algorytmy

#### 10.5.1 Franczyza (AniList)

1. Fragment pól wpisu (na każdym poziomie): `id type format status seasonYear startDate { year month day } title { romaji english native }`.
2. Zapytanie warstwy: `query ($ids: [Int]) { Page(perPage: 50) { media(id_in: $ids, type: ANIME) { <pola> relations { edges { relationType node { <pola> relations { edges { relationType node { <pola> } } } } } } } } }` — zagnieżdżenie `relations` do głębokości `d` ustalonej w fazie 0 (3, 2 albo 1); każdy poziom ma pełny fragment pól.
3. Start: `$ids = [selected_id]`. Z odpowiedzi zbieramy węzły do głębokości `d`. Łańcuchem idziemy tylko krawędziami `PREQUEL` i `SEQUEL` między węzłami `type=ANIME`. Węzły dołączone krawędzią `SIDE_STORY`, `SPIN_OFF`, `ALTERNATIVE`, `SUMMARY`, `PARENT` są liśćmi (nie rozwijamy ich relacji), poza opisanym niżej wejściem OVA/SPECIAL przez `PARENT`. Inne relacje i węzły `MANGA`/`NOVEL` są pomijane (W-05).
4. Jeśli na najgłębszym poziomie są węzły łańcucha z nierozwiniętymi krawędziami `PREQUEL`/`SEQUEL`, następne zapytanie pyta o nie (`$ids` = te węzły). Łącznie najwyżej `_MAX_FRANCHISE_REQUESTS = 4` zapytania (stała, docstring: limit czasu wejścia w tytuł przy limicie AniList ~30/min); po limicie `complete=False`.
5. Grupy: `SEASON` — format TV, TV_SHORT, ONA **i** wpis w łańcuchu PREQUEL/SEQUEL (albo wybrany); `EXTRA` — OVA, SPECIAL; `OTHER` — MOVIE, MUSIC oraz TV/TV_SHORT/ONA dołączone jako liść.
6. Faza 0 potwierdza liczbę zapytań dla Slime; więcej niż 4 → warunek zatrzymania §7.

**Krawędzie a widok:** zachować w `Franchise.relations` rzeczywiste końce i typy pobranych krawędzi anime (także relacje zwrócone w zagnieżdżonych liściach), z deduplikacją. `FranchiseEntry.relation` i `group` są wyłącznie projekcją dla korzenia widoku, nie dowodem wspólnej tożsamości. Kontekst celu §10.5.3 wylicza się z grafu względem ID wybranego odcinka, nigdy przez znalezienie pierwszego `SEASON` w widoku. Dla bezpośredniego wejścia w OVA/SPECIAL krawędź `PARENT` dołącza łańcuch macierzysty PREQUEL/SEQUEL potrzebny aliasom dodatku; nie dotyczy to spin-offu TV ani `OTHER`. Nadal obowiązuje łączny limit 4 zapytań. Faza 0 nagrywa również wejścia bezpośrednie OVA i Diaries; brak grafu wystarczającego do odtworzenia identycznego celu w tym budżecie wymaga eskalacji, nie dodatkowych ukrytych zapytań przy `offer`.

#### 10.5.2 Lista odcinków i pamięć

1. ani.zip `GET https://api.ani.zip/mappings?anilist_id=<id>`; 404 → `AniZipMapping` z pustymi listami i `kitsu_id=None` (UI: „Brak mapowania odcinków dla tego wpisu”); inne błędy → `TitleCatalogError(EPISODE_CATALOG_FAILED)`.
2. AniList `airing_schedule(id)` (istniejące). `TitleCatalogError` → częściowy sukces: lista z datami ani.zip, `schedule_warning="TITLE_CATALOG_FAILED"` i `schedule_retry_at` z `request_control.blocked_until(("anilist",))`, bez ponownego HTTP. Źródło zastępcze statusu: ostatni poprawny, niewygasły `SeasonAiring` tego ID, inaczej `FranchiseEntry.status` tego ID z pamięci, inaczej `TitleStatus.UNKNOWN.value`. Liczba odcinków AniList i harmonogram: tylko z takiego niewygasłego `SeasonAiring`; bez niego do czystej funkcji idą `episode_count=None` i pusty harmonogram, a liczba do złożenia listy pochodzi z ani.zip. `aired=None`, jeśli brak potwierdzenia AniList wymaganej liczby/dat; nie liczyć go z zastępczego `episodeCount` ani.zip. Brak metadanych nie usuwa listy uzyskanej z ani.zip. UI pokazuje „Terminy emisji niedostępne (AniList)” oraz termin albo wskazówkę ponowienia (§10.7), nie PROBLEM całej operacji.
3. `AcquisitionService` przekazuje surowe dane do czystej funkcji `episode_selection.episode_listing`: `episode_count` z `SeasonAiring`, status jako `TitleStatus.value`, harmonogram jako `ListedEpisode` z `number`/`airs_at`, pozostałe pola `None`, mapowanie ani.zip i jawny czas `now`; przy błędzie używa danych zastępczych, ostrzeżenia i terminu z pkt 2. Funkcja wybiera liczbę odcinków z AniList, a przy jej braku z ani.zip, łączy numery ani.zip i harmonogramu oraz uzupełnia brakujące numery `1..episode_count` (W-07). Wynik jest unikalny po numerze i rosnący; liczba odcinków nie usuwa pozycji istniejących w źródłach. Uzupełnione pozycje mają tylko `number`, pozostałe pola `None` — nie wymyślamy tytułu, daty ani numeracji TVDB. Przy pustych obu listach i znanej liczbie 12 powstaje 12 pozycji, przy nieznanej liczbie nie dopisujemy numerów. Kontrakt `AniListCatalog.airing_schedule` pozostaje bez zmian, zgodnie z `tests/services/catalog/test_anilist.py:test_a_valid_empty_schedule_is_not_invented_from_the_episode_count`.
4. `airs_at`: harmonogram AniList; brak → `airDateUtc` ani.zip; brak → None. Pola `airDate`/`airdate` nie są używane. Sama znana liczba odcinków nie oznacza emisji: uzupełnione numery bez daty pokazują „—” i „Nie wyemitowano”, chyba że U-15 potwierdza emisję (status „w emisji” lub „zakończony” oraz numer ≤ liczbie wyemitowanych według AniList). Dla tego sprawdzenia przy RELEASING liczymy tylko daty harmonogramu AniList ≤ `now`, przy FINISHED używamy liczby odcinków AniList; brak potwierdzenia nie pozwala zaznaczyć odcinka (UX §5). Nie wnioskujemy emisji z samej liczby sezonu ani daty jego startu.
5. Klucze `S…` → `specials`.
6. **Pamięć w `AcquisitionService`** (jedna mapa, klucz `anilist_id` wpisu):
   - `EpisodeListing` i `Franchise` wpisu — ważne `max_age_s` sekund od pobrania odpowiedzi ani.zip; brak nagłówka → `_FALLBACK_CACHE_S = 900` (stała, docstring: wartość `Cache-Control` ani.zip zmierzona 2026-09-22).
   - `Franchise` jest zapisywana wyłącznie pod ID korzenia, dla którego pobrano widok. Nie kopiować jej pod wszystkie ID ani nie zmieniać tylko `selected_id`/`SELF`. Przy wyborze wpisu z tego widoku usługa buduje z zachowanego grafu kontekst tożsamości dla wybranego ID (§10.5.3), a nie nowy widok franczyzy; zapamiętuje go pod ID celu osobno od widoku. Kontekst nie zawiera grup zależnych od korzenia. Bezpośrednie wejście i wejście przez franczyzę muszą dawać ten sam kontekst na tych samych danych, także po odwróceniu kolejności rozgrzewania pamięci. Niepełny graf nie jest traktowany jako pełny kontekst ani nie może nadpisać pełnego; gdy nie pozwala ustalić tożsamości, nie wolno wydać sugestii na podstawie odziedziczonych aliasów.
   - `aired` i stany odcinków liczone są przy każdej odpowiedzi z bieżącego czasu i danych źródłowych; ta sama pozycja pamięci zachowuje harmonogram oraz liczbę odcinków AniList do U-15, aby nie wyprowadzać emisji z uzupełnionych numerów ani dat zastępczych ani.zip.
   - Częściowy sukces zachowuje ostrzeżenie i pochodzenie danych; nie odświeża wieku ostatniego poprawnego harmonogramu. Jawne ponowne wejście po upływie blokady ponawia tylko brakujący harmonogram (ani.zip nadal według TTL); bez blokady jest to możliwe od razu. Poprawna odpowiedź usuwa ostrzeżenie. Render ani upływ czasu nie uruchamiają zapytań.
   - Wypieranie: najdawniej użyty wpis, gdy mapa przekroczy `_REMEMBERED_ENTRIES` (stała, docstring: limit pamięci procesu rezydenta).
   - Pamięć służy wyłącznie odczytom w E1. E2 przed zleceniem pobiera dane ponownie.
7. `offer(key)`: kontekst wybranego wpisu i lista z pamięci (przy bezpośrednim wywołaniu bez pamięci najpierw pobrane zwykłą drogą franczyzy/listy); nie wymaga widoku `Franchise` pod ID liścia, jeśli jego kontekst jest już zbudowany z grafu. Torrentio zawsze na żywo. Dla 12 odcinków jednego wpisu: 12 zapytań Torrentio i 0 dodatkowych zapytań AniList/ani.zip po pierwszym wejściu we wpis.

#### 10.5.3 Cel odcinka

Kontekst celu wyznacza się względem wybranego ID z rzeczywistych metadanych. Historyczne `make_targets` i `targets.json` dokumentują pochodzenie dawnych danych; nie narzucają parytetu nowej heurystyki. Poniższe zasady izolacji franczyz i braków metadanych pozostają kontraktem wejścia, a ich wpływ na ocenę sprawdzają etykiety korpusu:

To nowa droga numeracji: lista korzysta z numerów lokalnych ani.zip, harmonogramu i uzupełnienia z liczby odcinków (§10.5.2), a cel i ranking z pól `ListedEpisode`. Nie używa `ResidentSession.season_context`, `SeasonContext.offset` ani `read_episode`. **Omija** znany błąd AniList `182205` w nowym widoku; stary RESULTS pod `G` i stare subskrypcje zachowują dotychczasowy kalkulator. Właściciel zaakceptował brak osobnej naprawy starej drogi, bo jej UI znika w E3, a zaplecze w E5 (D1).

- Najpierw z `Franchise.relations` wyznaczyć własny łańcuch PREQUEL/SEQUEL wybranego wpisu; przejście przez OVA/film na takim łańcuchu jest dozwolone, ale `SPIN_OFF`, `ALTERNATIVE`, `SUMMARY` i poboczne TV/ONA nie łączą tożsamości. OVA/SPECIAL może użyć jednoznacznej relacji `PARENT` (odwrotnej `SIDE_STORY`) do łańcucha macierzystego. Nie wybierać rodzica według kolejności wejścia lub cache; niejednoznaczność oznacza brak odziedziczonych aliasów i brak pewnej sugestii, aż kontekst będzie rozstrzygnięty.
- `aliases` = `romaji`, `english`, `native` wybranego wpisu + te same pola najwcześniejszego sezonu **jego własnego łańcucha** (dla dodatku: jednoznacznego łańcucha macierzystego); bez powtórzeń i pustych, kolejność: wybrany, potem pierwszy sezon. Spin-off i wpis `OTHER` nie dziedziczą aliasów głównej serii, także gdy po wejściu bezpośrednim sam spin-off jest pokazany jako `SEASON`. Diaries ma wyłącznie własne nazwy; relacja z S1 nie dodaje ogólnego „Tensei Shitara Slime Datta Ken”. Synonimy nie wchodzą (jak w badaniu).
- `other_series` = odrębne gałęzie względem własnego łańcucha: dla głównej serii i jej OVA zachować z badania nazwy spin-offów po ostatnim `": "`; dla wybranego spin-offu/`OTHER` rozpatrywać obce gałęzie, nigdy jego samego. Pominąć nazwę wykluczającą, jeśli po normalizacji występuje we własnym aliasie (ogólna nazwa S1 jest częścią pełnego romaji Diaries i odrzucałaby również poprawne Diaries). Brak takiego wykluczenia nie uprawnia do `match`: własny alias nadal jest wymagany.
- `isolated_series=True` dla osobnej gałęzi spin-offu/`OTHER`, niezależnie od grupy widoku. Chroni przed wspólnymi paczkami: gdy kandydat ma `path` lub `file_name`, własny alias musi wystąpić w wybranej ścieżce/pliku; ogólny tytuł paczki wymieniający także Diaries nie dowodzi, że wskazany plik należy do Diaries. Przy braku własnego aliasu w wybranym pliku wynik jest `insufficient_evidence`, chyba że istniejąca reguła już wykazała `mismatch`. Samodzielne wydanie bez ścieżki/nazwy pliku może użyć własnego aliasu w `release`. Poprawne wydania z jawną własną nazwą nadal przechodzą zwykłe reguły numeracji.
- `kind` = `"OVA"` dla formatu OVA/SPECIAL, inaczej `"TV"`.
- `local_episode` = numer; `season`/`episode`/`absolute` z `ListedEpisode`.
- `episode_title` = obecny `title` bez prefiksu `"Extra: "`, z odwróconym apostrofem zamienionym na `'`; brak lub pusty wynik → `None`. `other_episode_titles` = tak samo dla pozostałych odcinków wpisu (tylko `OVA`), po odfiltrowaniu brakujących i pustych tytułów.
- **Znana różnica wobec badania:** tylko dla `ova-1` badanie uzupełniło `season`/`episode` z listingu TVDB Sonarr, bo ani.zip ma tam `seasonNumber=None` (odcinki 1 i 2 wpisu OVA). W produkcji te pola zostają `None` (§10.5.4). `ova-4` ma w ani.zip `seasonNumber=0`, `episodeNumber=5` — tak jak w `targets.json`.

#### 10.5.4 Heurystyka

`assess_identity` realizuje deterministyczną heurystykę wyprowadzoną **od zera z oznaczonej części roboczej** w fazie 2 (§9 N-02), po jednorazowym egzaminie i akceptacji metryk przez właściciela. Plan nie przepisuje teraz zestawu reguł z 231 przykładów. Skrypt analizy/strojenia zapisuje reguły, ich przesłanki i kontrprzykłady z części roboczej; wynik fazy 2 jest wejściem implementacji domeny. Prototyp z `prepare.py.txt` jest najwyżej kandydatem do porównania na danych roboczych, nigdy źródłem oczekiwanych decyzji.

Kontrakty danych i przypadki szczególne, które nowa heurystyka musi respektować:

- `target.season is None` nie dowodzi innego sezonu: ani jawna para `SxxEyy`, ani `S01` w ścieżce nie może sama powodować `mismatch` przez porównanie do braku danych.
- OVA z `episode_title=None` oraz brakujące/puste tytuły innych odcinków nie powodują wyjątku ani pozornego dopasowania pustej nazwy. Zgodna kotwica TVDB może uzasadnić `match`; sam numer lokalny bez tytułu i kotwicy nie wystarcza. Oczekiwania konkretnych fixture wynikają z etykiet i dostępnego dowodu.
- Izolacja Diaries/S1 i wspólnych paczek z §10.5.3 obowiązuje niezależnie od korzenia grafu i kolejności rozgrzania pamięci; własny poprawny alias nie może odrzucać sam siebie.
- Osobno sprawdzić składanie celu z grafu i ocenę kandydata; zielony test na ręcznie przygotowanym celu nie dowodzi poprawności danych dostarczonych przez usługę. Różnica wobec prototypu nie jest błędem sama w sobie; sprzeczność z etykietą wymaga diagnozy, a nie przepisania oczekiwań pod wynik.

W fazie 3 przenieść zamrożone reguły do czystego `episode_selection.py` bez ponownego strojenia. Zgodność wykonania wersji egzaminowanej i domenowej sprawdzić offline na części roboczej; nie uruchamiać ponownie odłożonego zbioru jako testu portu. Materialna zmiana reguł lub przygotowania wejścia wymaga nowego egzaminu na niewykorzystanych danych. Ranking §10.5.5 pozostaje osobnym, niezmienionym kontraktem właściciela.

#### 10.5.5 Fakty i ranking

- `release_facts` czyta tokeny z `release`, `path`, `file_name` i `tags`; rozdzielczość dodatkowo z zachowanego `StreamCandidate.name` (wzorce: `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt:34–74`, `workspace/.archive/acquisition/evidence/polish/study.py.txt:36–61`). `name` nie trafia do heurystyki tożsamości.
- **Rozdzielczość** (dokładna reguła `pilot.py.txt:resolutions` i `extract`): ze źródeł `release`, `path`, `file_name`, `name` (w badaniu `label`) zebrać sumę różnych wysokości. Regexy: `(?i)(?<!\d)(360|480|576|720|1080|1440|2160)[pi]\b`, `(?i)\b\d{3,4}x(360|480|576|720|1080|1440|2160)\b` (wysokość) oraz `(?i)\b4k\b` → 2160. Nie używać pełnego `title`/`presentation` ani linii tagów jako dodatkowego źródła rozdzielczości. Dokładnie jedna różna wartość → ta wartość; zero albo kilka różnych, także konflikt `name` z nazwą pliku → `None`, bez pierwszeństwa któregokolwiek źródła. `1080i` i `1440x1080` dają klasę 1080; `11080p` nie daje 1080.
- **Obsługiwane kontenery:** `VIDEO_SOURCE_SUFFIXES` — nowa publiczna stała w `application/discovery.py` wyliczona z `_PRIMARY_SOURCE_KINDS` (rodzaje `VIDEO_*`, dziś `.mkv`, `.mp4`); bez kopiowania listy.
- **Nieznany kontener:** brak `file_name` lub jego rozszerzenia daje `container=None`, `supported=None`, a nie `False`. U-06 wyklucza z sugestii wyłącznie jawnie nieobsługiwany kontener. Nieznany konkuruje z obsługiwanym według tego samego U-04/U-05/U-23, bez dodatkowej kary za brak metadanych, i może być sugestią, jeśli ma `match`; ustalenie pliku z metadanych pozostaje U-18 w E2. Badanie zachowuje takie rekordy w puli zgodnych (`pilot.py.txt:extract`, `in_conservative_pool`/`needs_metadata`); przykład `matching/dataset.json`, `slime-s4e23:12`: `filename=null`, etykieta i heurystyka `match`.
- **Klucz sortowania** (rosnąco; realizuje U-04, U-05, U-06, U-23):

```text
(
  facts.supported is False,             # U-06: nieznany kontener bez kary
  facts.dub_only,                       # U-23
  resolution_class(facts.resolution),   # U-04 (1), U-05
  not facts.polish,                     # U-04 (2)
  not facts.multisub,                   # U-04 (3)
  facts.platform is None,               # U-04 (4)
  stream.seeders is None,               # U-04 (5): brak seedów za każdą znaną liczbą
  -(stream.seeders or 0),
  original_index,                       # U-04 (6)
)
```

`resolution_class(h)`: 1080 → `(0, 0)`, 2160 → `(1, 0)`, 720 → `(2, 0)`, inna znana → `(3, abs(h - 1080))`, `None` → `(4, 0)`.

### 10.6 IPC

Nowe pod-operacje polecenia `acquisition`, obsługiwane w `_acquisition_command` **przed** dekodowaniem `candidate`. `PROTOCOL_VERSION` bez zmian.

| Pod-operacja | Payload | Odpowiedź |
| --- | --- | --- |
| `franchise` | `{"anilist_id": int}` | `Franchise` |
| `episodes` | `{"anilist_id": int}` | `EpisodeListing` |
| `offer` | `{"anilist_id": int, "number": int}` | `EpisodeOffer` |

- `offer` dotyczy jednego odcinka; panel pyta o zaznaczone odcinki kolejno i wypełnia podgląd przyrostowo (rozmiar odpowiedzi ≤ jednej listy Torrentio; Q-08).
- **Pierwszeństwo przyczyny:** owner opakowuje także błędy dostawców w `INTERNAL`, ale `failure_code` zachowuje kod w `reason` (`automation.py:AutomationOwner._answer`, `events.py:failure_code`). Panel najpierw dekoduje `reason` istniejącą drogą `_code` i pokazuje komunikat właściwego dostawcy oraz jego cooldown (§10.7). Rozpoznany `TITLE_CATALOG_FAILED`, `EPISODE_CATALOG_FAILED` lub `TORRENT_SOURCE_FAILED` nigdy nie staje się komunikatem restartu.
- **Starszy rezydent** (sprzed E1) odpowie na te pod-operacje `refused(INTERNAL, …, "command_failed")`. Tylko para `INTERNAL` + `reason="command_failed"` dla `franchise`/`episodes`/`offer` daje: „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” Inne nierozpoznane powody zachowują zwykły bezpieczny komunikat odmowy. Bez osobnego mechanizmu wykrywania wersji.

### 10.7 Zachowanie UI

Pełne makiety, teksty i klawisze: [../ux.md](../ux.md) §3–§6, §11–§13 (§12: H1, §13: klawisze). Najważniejsze reguły dla E1:

- Ekrany: QUERY → TITLES → ENTRIES → EPISODES → OFFER → CANDIDATES; BUSY i PROBLEM jak dziś. Z TITLES klawisz `G` otwiera dotychczasowy RESULTS z zachowanymi akcjami — pomost usuwany w E3. Wspólny `TORRENT_SOURCE_FAILED` ma tekst „Źródło wydań nie odpowiada” zarówno dla Nyaa, jak i Torrentio; to jawna zmiana komunikatu starej drogi, nie jej pobierania ani subskrybowania.
- `_find_titles`: po poprawnej pustej odpowiedzi AniList (także po istniejącej próbie ze skróconym hasłem) komunikat „Brak tytułu w AniList, szukam wydań na Nyaa” i `_search` wpisanego hasła → RESULTS z trwałą notką `_NO_TITLE` („Brak tytułu w AniList, wyniki dla hasła”). Awaria AniList, w tym 429, daje PROBLEM i zero zapytań Nyaa. Brak mapowania ani.zip również nie uruchamia Nyaa. D5 zmienia wyłącznie przypadek braku tytułu w W-08.
- **Termin po 429:** źródłem pozostaje `RequestControl`, a w trybie rezydenta jego istniejący zapis `WatchState.provider_locks`. `AutomationOwner._save_provider_lock` zapisuje i publikuje `state_changed` z `provider_locks[{provider, until, reason}]`; `ResidentSession.observe` dostarcza też początkowy `status`. `StateController._receive` oraz `attach_anime` przekazują te pola do nowego `AnimeController.refresh_provider_locks`, obok obecnego `refresh_acquisitions`. Kontroler zachowuje wyłącznie projekcję terminu dla komunikatu i identyfikator źródła nieudanej operacji (`anilist`, `anizip`, `torrentio`, `nyaa`); wspólny kod `TORRENT_SOURCE_FAILED` sam nie rozróżnia dwóch ostatnich. Publikacja może przyjść przed lub po błędzie — oba porządki aktualizują ten sam komunikat. Bez rezydenta worker odczytuje istniejące `AcquisitionService.request_control.blocked_until((provider,))` i przekazuje termin z wynikiem błędu. UI wylicza pozostały czas z `until` i bieżącego zegara, np. „spróbuj za 90 s”; po upływie „Możesz spróbować ponownie”. Bez aktywnej blokady zwykła wskazówka ponowienia, bez wymyślonego czasu. Render nie odpytuje IPC/HTTP; UI nie ustala własnej blokady ani nie ponawia automatycznie. Dopuszczaniem żądań nadal zarządza wyłącznie `RequestControl`.
- Esc wraca o jeden ekran i odtwarza kursor i zaznaczenia; nie wykonuje sieci, gdy dane są w pamięci kontrolera.
- **Częściowy błąd harmonogramu:** `EpisodeListing.schedule_warning` utrzymuje na EPISODES notkę „Terminy emisji niedostępne (AniList)” bez ukrywania odcinków. Początkowy termin daje `schedule_retry_at`; kolejne `provider_locks` aktualizują go tą samą drogą co błędy (§10.7), również gdy zdarzenie przyszło przed listą. Bez aktywnej blokady: „Możesz spróbować ponownie — wróć do wpisów i otwórz wpis”. To jawne wejście odświeża brakujący harmonogram; sam Esc, render i zegar nie wykonują I/O. Daty zastępcze ani.zip są oznaczone jako takie; nie zastępują potwierdzenia AniList dla U-15.
- `D` na EPISODES bez zaznaczeń używa podświetlonego odcinka.
- OFFER nie ma akcji „Pobierz” w E1; stopka: „Enter/I inne wydania · Esc odcinki”.
- `O` i `P` na EPISODES nie są obsługiwane w E1 (brak w stopce).
- Każdy wynik wątku sieciowego sprawdza generację; spóźniony wynik jest porzucany.

### 10.8 Edge cases

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| AniList poprawnie zwraca brak tytułu | Jawny komunikat → Nyaa dla wpisanego hasła → RESULTS z notką; Esc → QUERY | unit + integration przez owner/IPC |
| AniList zawodzi albo ani.zip nie odpowiada | Komunikat właściwego źródła, zero zastępczych zapytań Nyaa | unit + integration |
| Tytuł bez wpisu ani.zip (404) | ENTRIES działa; EPISODES: „Brak mapowania odcinków dla tego wpisu”; `D` niedostępne | unit + integration |
| Przyszły wpis z pustą listą ani.zip, harmonogram z 12 numerami | 12 odcinków z datami, stan „Nie wyemitowano” | unit |
| Przyszły wpis, puste odcinki ani.zip i harmonogram, AniList zna `episode_count=12` | 12 odcinków bez dat, stan „Nie wyemitowano”, bez zaznaczania do podglądu | unit (czysta domena) |
| Sprzeczne `airDate`/`airdate` | Ignorowane; użyte `airs_at` z AniList | unit |
| Torrentio 0 kandydatów | „Brak kandydatów w źródle (sprawdzono HH:MM)” | unit |
| Kandydat bez `fileIdx` | Ocena tożsamości po nazwie wydania i ścieżce; brak indeksu pokazany w szczegółach | unit |
| `slime-s4e23:12`, brak nazwy pliku/kontenera | `match`, `supported=None`; uczestniczy bez kary w rankingu i może być sugestią | unit |
| OVA bez tytułu oraz brakujące tytuły innych odcinków | Bez wyjątku i bez pozornego dopasowania pustego tytułu; kotwica TVDB nadal działa, sam numer lokalny daje `insufficient_evidence` | unit na oznaczonych fixture |
| Ten sam hash dla kilku odcinków | Osobne oceny per odcinek | unit (EMBER idx 3/28/25) |
| `Dubbed` bez `Dual Audio` | Za wszystkimi innymi zgodnymi | unit |
| 1440×1080 | Klasa 1080 | unit |
| Rozdzielczość tylko w `name`, `1080i`, sprzeczne `name=2160p` i `file_name=1080p` | Odczyt `name`; klasa 1080 dla `1080i`; konflikt daje `None` | unit + fixture adaptera |
| `.avi`, `.ts` | `supported=False`, nigdy sugestia | unit |
| Brak seedów | „?” i koniec kolejności przy remisie | unit |
| 429 AniList/ani.zip/Torrentio/Nyaa, `Retry-After: 90` | Ten sam termin w `RequestControl`, `provider_locks` i komunikacie Anime; upływ czasu bez dodatkowego HTTP, oba porządki dostarczenia błędu i snapshotu | MockTransport + owner/IPC + kontroler z fake clock |
| Nyaa lub Torrentio: `TORRENT_SOURCE_FAILED` | Dla obu „Źródło wydań nie odpowiada”; właściwy termin według dostawcy operacji | unit + integration |
| `INTERNAL` z rozpoznanym `reason` dostawcy na nowej operacji | Właściwy komunikat źródła i cooldown, nigdy restart | owner → IPC → kontroler, każdy z trzech kodów źródeł |
| Rezydent w starszej wersji (`INTERNAL` + `reason="command_failed"` na `offer`) | Komunikat „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” | owner z ogólnym błędem → IPC → kontroler oraz fałszywa stara sesja |
| ani.zip działa, harmonogram AniList zwraca 429 | Sukces `EpisodeListing`: odcinki, ostrzeżenie i termin; status/dane zastępcze według §10.5.2, bez pozornego `aired` | MockTransport → owner → IPC → UI, fake clock |
| Esc w trakcie `offer` dla 12 odcinków | Kolejne zapytania nie są wysyłane; spóźnione odpowiedzi porzucane | unit (kontroler z fałszywą usługą) |

## 11. Plan wykonania

Wykonawca kodu: subagent `astra` (brief według `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`). Opiekun danych oddziela korpus egzaminacyjny od świeżej sesji autora heurystyki (§9 N-02). Review: świeży `opus5` przed egzaminem oraz po fazach 4, 7 i na końcu. Orkiestrator integruje i sprawdza dowody. Kolejność: preflight → korpus i etykiety → podział, budowa i egzamin → czysta domena → adaptery → N-01 → usługa/IPC → UI → N-03 → H1 i wynik. Kod przygotowawczy D2 i skrypty pomiarowe poprzedzają egzamin zgodnie z D2/D3; kod nowej ścieżki aplikacji powstaje dopiero po nim.

### Faza 0 — Preflight

**Cel:** czysty punkt startu i odpowiedź na pytanie o relacje AniList.

1. `git status`, `git log -3`; zweryfikować baseline `bde35d7` i bazę `work/acquisition/00-model-catalog-v2`, potem utworzyć `work/acquisition/01-episode-selection` według wzorca repo `work/<obszar>/<nn>-<slug>`. E1 zaczyna po E00; local-automation jest już scalone przez PR #56. Dokumenty acquisition są śledzone. Obowiązują rozstrzygnięcia D1–D5 w §15, decyzje i rozliczone weto z [../README.md](../README.md) §3 oraz zgody Z-1/Z-3 z §4 (Z-2 wycofana).
2. Uruchomić bramki z `AGENTS.md`; zapisać wynik (liczby passed/failed/skipped, nazwy failures) w `outcomes/e1.md` jako baseline.
3. Jedno zapytanie AniList (Slime S1, `id=101280`) z zagnieżdżeniem relacji 3, potem 2, potem 1; zapisać, która głębokość przechodzi bez błędu złożoności. Nagrać wszystkie warstwy franczyzy jako `tests/fixtures/search/anilist__franchise__101280.json` i analogicznie dla Solo Leveling (`id=151807`, istniejące fixture) oraz Haibane Renmei (`anilist_id` z `mappings` w `workspace/.archive/acquisition/evidence/sources/metadata/haibane.raw.json`).
4. Skopiować fixture z `workspace/.archive/acquisition/evidence/sources/metadata/` (slime-s1, slime-s4, slime-ova, haibane) jako `tests/fixtures/search/anizip__<anilist_id>.json` i z `workspace/.archive/acquisition/evidence/sources/releases/` oraz `workspace/.archive/acquisition/evidence/sources/ova/` jako `tests/fixtures/search/torrentio__kitsu-<id>-<n>.json`; dopisać do `manifest.json` (klucze `anizip`, `torrentio`, `anilist_franchise`).
5. Przyciąć `workspace/.archive/acquisition/evidence/matching/dataset.json` do pól `id`, `state.target`, `state.candidate`, **`label`, `label_strength`, `label_provenance`, `label_rationale`** → `tests/fixtures/acquisition/identity-231.json`; sprawdzić rozmiar < 500 KiB i zgodność zachowanych pól wszystkich 231 rekordów ze źródłem. Decyzje prototypu pozostają w archiwum wyłącznie do porównania, nie jako oczekiwania testu. `label` służy kontroli oceniających tylko dla jawnej listy pewnych ID wybranej według §9 N-02. Sprawdzić kotwice tej listy, zapisać ją z dowodami i ziarnem; kontrola bez sieci potwierdza wykluczenie 12 `local_number_assumption` z kontroli i brak pól oceny w wejściu modeli. Źródło: `workspace/.archive/acquisition/evidence/matching/prepare.py.txt:main`.
5a. **Mały krok kodu D2 — MODIFY:** `anishift/config/settings.py`, `anishift/application/runtime.py`, `tests/config/test_model_settings.py`. Dodać dwa pola `Settings` i opcjonalne argumenty fabryki zgodnie z §9 N-02 „Konto 2”; nie zmieniać `anishift/services/llm/`. Właściciel wpisuje obie wartości do `.env`; agent sprawdza tylko wynik walidacji konfiguracji, bez czytania lub wypisywania sekretów.
5b. **Testy D2 bez sieci:** w `tests/config/test_model_settings.py` syntetyczne env i tymczasowy plik środowiska (nigdy `.env` właściciela): oba pola wczytane dosłownie, env ma pierwszeństwo; `Settings` → argumenty `palantir_llm_config` → `LlmConfig` → istniejące `palantir_accounts` daje dwa konta, a `account_request` zachowuje trasę providera. Brak konta 2 oraz niepełna para dają dotychczasowe konto 1; niepoprawny kompletny origin/token odrzucony przez istniejącą walidację silnika. Syntetyczny token 2 i origin 2 nie występują w `repr(Settings)`, `repr(LlmConfig)`, błędach ani przechwyconych logach budowy/wywołania z MockTransport, także przy 429/5xx i failoverze. Uruchomić ten plik oraz istniejące `tests/services/llm/test_palantir_auth.py`, `test_palantir_accounts.py`, `test_palantir_requests.py`; ruff/mypy na całym `anishift/ tests/`.
5c. Po przygotowaniu fixture z pkt 5 utworzyć `scripts/tmp/corpus_labels.py` i `scripts/tmp/corpus_labels_prompt.md` (CREATE). Próba każdego modelu: pełna paczka **100 rekordów roboczych + 10 pewnych kontroli**, z reprezentatywnymi długimi nazwami/ścieżkami i kontraktem odpowiedzi z §9 N-02, przez `load_model_catalog` → `palantir_llm_config` (konto 1 jak dziś, kompletne konto 2 z pól `Settings`, jawne `max_retries` > 0) → kopia `LlmConfig` z jawnym **`max_output_tokens=32000`** → `LlmService.complete(LlmRequest)`. A: `foundry/gpt-6-astra`, B: `foundry-anthropic/claude-opus-5`, arbiter: `foundry-google/gemini-3.1-pro-preview`. Zapisać alias, szacunek wyjścia i budżet, `reasoning_variant` (domyślnie `None`), rozmiar paczki, `finish_reason`, rzeczywiste użycie tokenów (brak pola oznaczyć jako brak danych, nie zero), kompletność JSON i zgodność pewnych kontroli z `label`; nie wysyłać etykiet ani decyzji heurystyki. Odrzucenie wartości budżetu przez proxy (4xx) albo ucięcie uruchamia wyłącznie regułę adaptacji z §9 i kolejną pełnowymiarową próbę zmienionej pary rozmiar/budżet dla tego modelu; zapisać przebieg adaptacji. Dopiero kompletny wynik zatwierdza parę roboczą. Na potwierdzonych rozmiarach ustalić startowy limit równoległości (co najmniej dwa workery), zapisać czasy i liczby 429/5xx. Bez sieci, na fałszywym completion, sprawdzić oba powody ucięcia (także przy poprawnym JSON), odrzucenie budżetu 4xx odróżnione od innych błędów, mniejsze części z kontrolami i zachowaniem połowy budżetu na szacowany JSON, limit długości powodu, zatrzymanie przy minimum, limit aktywnych wywołań, kompletne niezależne oceny A/B oraz wznowienie po podziale/zmianie budżetu i zapisach poza kolejnością przez jednego pisarza. Retry transportu i przełączanie kont pozostają w `LlmService`. Podstawa: [../README.md](../README.md) §3, D2/D3 i Z-1 w §4.

**Kontrola:** bramki uruchomione; fixture trzech franczyz AniList oraz wejść OVA/Diaries z §10.5.1; fixture ani.zip/Torrentio z sumami SHA-256 zgodnymi z `workspace/.archive/acquisition/evidence/manifest.json`; testy D2 zielone, dwa konta dostępne bez ujawnienia wartości; zapisany wynik pełnowymiarowej próby każdego oceniającego, potwierdzone budżety i startowy limit współbieżności D3.

**Gate:** znana głębokość relacji; baseline zapisany; pomiary w granicach Z-1 ([../README.md](../README.md) §4), ocena modelami zgodnie z §3.

### Faza 1 — Zbieranie i oznaczenie korpusu (N-02, N-04)

**Cel:** ≥ 2000 tytułów i ≥ 10 000 unikalnych oznaczonych rekordów, zanim autor zacznie budować heurystykę.

**Pliki:** `scripts/tmp/acquisition_probe.py` (CREATE, surowy zbieracz `collect` → `movies`/`corpus` bez importu przyszłej domeny i adapterów), `acquisition_collect_local.ps1` (odłączony launcher Windows), `corpus_labels.py`, `corpus_labels_prompt.md`, `corpus_labels_debate_prompt.md`; dane według §9 N-02. Zbieranie i przegląd etykiet prowadzi opiekun danych, nie przyszły autor heurystyki.

**Działania:** potwierdzić licznik i okno Z-1 uzupełnione decyzją z 2026-09-25 (§9): 1000 prób Torrentio/rolling 24 h, ≤4000 łącznie, twarde 4 doby; zweryfikować lokalne sumy/checkout, przygotować archiwum poza checkoutem i uruchomić odłączony launcher Windows według komend §9 N-02. Wykonać N-04 i zebrać korpus z zapisanymi warstwami; dane VPS zachować. Oznaczyć cały korpus niezależnie przez A i B, z kontrolami i dyskusją D3 według §9 N-02 (decyzja właściciela 2026-09-25): świeże instancje Astra/Opus 5, anonimowa losowana kolejność ocen, najwyższe rozumowanie, 1–3 rundy, konkretny fakt i argument partnera; kontrole poza dyskusją. Stosować regułę współbieżności 4/+2/połowa z §9. Konto 2 obsługiwane, ale niewymagane; dostępne konto 1 wystarcza. Jeden pisarz zapisuje kapsuły do resume, etykiety i liczbę rund, bez pełnych odpowiedzi. Właściciel rozlicza brak zgody/nieustalone oraz 50 losowych zgodnych ocen. Zapisać pochodzenie i siłę ostatecznych etykiet oraz braki źródeł, bez uruchamiania heurystyki na pełnym korpusie.

**Kontrola:** unikalność tytułów/rekordów, obecność warstw, kompletność ocen A/B, rozliczenie kontroli i listy właściciela, liczniki zapytań/czasu i sumy surowych danych. Wynik `nie da się ustalić` jest jawną etykietą, nie brakującą oceną.

**Gate:** spełnione minima i pokrycie warstw w granicach zgody. Brak danych po 4000 próbach lub 4 dobach → pytanie Z-1 w §15; nie przechodzić do budowy na mniejszym korpusie ani automatycznie wydłużać okna. N-04 zachowuje swoją regułę decyzji; brak kandydatów filmowych zapisuje lukę korpusu do rozstrzygnięcia, nie fikcyjny wynik.

### Faza 2 — Podział, budowa od zera i jednorazowy egzamin

**Cel:** reguły o potwierdzonej jakości na danych niewidzianych przez autora.

**Pliki:** `scripts/tmp/identity_study.py`, `scripts/tmp/identity_exam.py` (CREATE); manifest podziału, część robocza i odłożona w miejscach/uprawnieniach z §9 N-02.

**Działania:** opiekun ustala i zamraża liczebności z właścicielem, wykonuje losowy podział stratyfikowany z grupowaniem franczyz/hashów, zapisuje ziarno i sumy oraz sprawdza odmowę odczytu odłożonych danych przez konto autora. Świeża sesja autora otrzymuje tylko część roboczą. Buduje reguły od zera i iteruje offline na jej etykietach; przed egzaminem zamraża cały artefakt, w tym przygotowanie celu/wejścia. Świeży `opus5` sprawdza metodykę, izolację i skrypt egzaminacyjny bez ujawniania odłożonych rekordów autorowi. Opiekun wykonuje egzamin raz i przekazuje wyłącznie metryki per warstwa; właściciel ocenia pokrycie.

**Kontrola:** kompletne manifesty i SHA-256 przed/po, brak wspólnych grup/ID rekordów między budową a egzaminem oraz brak historycznych kontroli w egzaminie; próba mechanizmu izolacji i raportowania na syntetycznych danych przed otwarciem właściwej części; rejestr wykorzystania części odłożonej. Zero błędnych `zgodnych`, jawne `niepewne`, błędne `niezgodne` i przypadki bez rozstrzygającej etykiety.

**Gate:** egzamin zdany i metryki zaakceptowane przez właściciela. Porażka → iteracja na roboczej części oraz nowa odłożona część, nie drugi egzamin na tej samej. Po sukcesie zamrożone reguły i stałe oznaczone próbki robocze są wejściem fazy 3.

### Faza 3 — Czysta domena

**Cel:** `episode_selection.py` z heurystyką po egzaminie i rankingiem właściciela.

**Pliki:** `anishift/application/episode_selection.py` (NEW, wszystkie nowe typy z §10.4), `anishift/application/discovery.py` (`VIDEO_SOURCE_SUFFIXES`), `tests/application/test_episode_selection.py` (NEW), `tests/application/test_architecture.py`, `anishift/application/__init__.py`.

**Działania:**
1. Typy z §10.4.
2. `assess_identity` z zamrożonych reguł fazy 2 według §10.5.4, bez strojenia na danych egzaminacyjnych.
3. `release_facts`, `rank_candidates` według §10.5.5.
4. `episode_target` według §10.5.3.
5. `episode_listing` według §10.5.2: czyste łączenie i uzupełnianie numerów z liczby odcinków, bez zmiany adaptera AniList.

**Inwarianty:** brak importów I/O, `httpx`, `config`, `cli` i `anishift.services` w `episode_selection.py`, także pod `TYPE_CHECKING`. Wszystkie nowe kontrakty są lokalne (§10.4); dopisać moduł do `tests/application/test_architecture.py:_PURE_MODULES` oraz `httpx` do `_PURE_FORBIDDEN`, bez usuwania istniejących zakazów ani wyjątków. Na baseline `git grep -n httpx -- anishift/application/artifacts.py anishift/application/intents.py anishift/application/planning.py anishift/application/planner.py anishift/application/selection.py anishift/application/workflows.py` dał 0 trafień (sprawdzone 2026-09-24); przed edycją powtórzyć, a nowe trafienie zgłosić zamiast rozszerzać zakres o naprawę. `test_application_contracts_do_not_depend_on_ui_io_or_domain_services` ma maszynowo wymuszać także zakaz `httpx`.

**Testy (nazwy opisują zachowanie, bez prozy):**
- stałe próbki `identity-corpus.json` z części roboczej: wszystkie warstwy i rozliczone przypadki błędów/sporów; oczekiwania z ostatecznych etykiet i siły dowodu, nigdy z `heuristic.decision`;
- historyczne fałszywe odrzucenia (`slime-s1e4:33`, `bebop-e1:33`) sprawdzić wobec ich etykiet i produkcyjnych wejść; nie utrwalać błędnych odrzuceń dla zgodności z prototypem, brak dostatecznej kotwicy jawnie uzasadnić;
- S1 odrzuca Diaries, Diaries nie daje `match` wydaniom S1 z pasującym numerem (także wspólnej paczce wymieniającej obie serie); oba wpisy zachowują `match` własnych jednoznacznych wydań. Pełny alias Diaries zawierający nazwę S1 nie odrzuca sam siebie. Ten sam cel/kandydat daje identyczną ocenę niezależnie od korzenia grafu;
- `season=None` + `S00E02` w nazwie i `S01` w ścieżce → nie `mismatch` z powodu pary ani sezonu;
- OVA z `episode_title=None` i brakującymi/pustymi tytułami innych odcinków: bez wyjątku i bez dopasowania pustej nazwy; zgodna para TVDB → `match`, sam numer lokalny bez kotwicy → `insufficient_evidence`, obecny tytuł innego OVA nadal → `mismatch`;
- ranking: 1080p bez PL przed 720p z PL; 2160p przed 720p; 720p przed 480p; w 1080p: PL przed MultiSub, MultiSub przed NF bez MultiSub, NF przed wydaniem bez oznaczeń; 1440×1080 = 1080; `Dubbed` bez `Dual Audio` za 480p bez dubbingu; `.avi` nigdy sugestią; brak seedów (`None`) za każdą znaną liczbą, także za 0;
- nieznany kontener (`slime-s4e23:12` oraz nazwa bez rozszerzenia) → `supported=None`, bez kary w kluczu U-04, może być sugestią; znane `.avi`/`.ts` → `False`, nigdy sugestia;
- rozdzielczość tylko w `name`; `1080i`, `1440x1080`, `4K`, odrzucenie fałszywego `11080p`; konflikt między `name` i nazwą pliku → `None`;
- ten sam hash z różnymi `file_index` oceniany osobno.
- znana liczba odcinków 12 przy pustych ani.zip i harmonogramie → dokładnie numery 1–12, wszystkie metadane `None`; dla zapowiedzi brak potwierdzenia emisji, a dla FINISHED emisja potwierdzona liczbą AniList zgodnie z U-15;
- częściowe źródła → uzupełnienie luk bez duplikatów i utraty metadanych; brak liczby i puste źródła → brak wymyślonych numerów.

**Kontrola:** `uv run pytest tests/application/test_episode_selection.py tests/application/test_architecture.py`; ruff/mypy na całym `anishift/ tests/`.

**Gate:** testy oznaczonych fixture i przypadków szczególnych zielone; wykonanie domeny zgodne z zamrożonym artefaktem egzaminowanym na części roboczej. Różnica semantyczna wymaga nowego egzaminu, nie edycji oczekiwań.

### Faza 4 — Adaptery

**Cel:** ani.zip, Torrentio, franczyza AniList, dostawcy w `RequestControl`.

**Pliki:** `anishift/services/catalog/anizip.py` (NEW), `anishift/services/catalog/anilist.py`, `anishift/services/catalog/__init__.py`, `anishift/services/torrents/torrentio.py` (NEW), `anishift/services/torrents/__init__.py`, `anishift/services/http_requests.py`, `anishift/errors.py`, testy: `tests/services/catalog/test_anizip.py` (NEW), `tests/services/torrents/test_torrentio.py` (NEW), `tests/services/catalog/test_anilist.py`, `tests/services/test_http_requests.py`, `tests/integration/test_search_live.py`.

**Działania:**
1. `AniZipCatalog(http)` z metodą `mapping(anilist_id: int) -> AniZipMapping`; parsowanie §10.5.2 pkt 1 i 5; `max_age_s` z `Cache-Control`.
2. `TorrentioSource(http)` z metodą `streams(kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]`; URL `https://torrentio.strem.fun/stream/series/kitsu:{kitsu_id}:{number}.json`; parsowanie linii `title` (§6.4) oraz zachowanie surowego `name` w `StreamCandidate` (test pola i jego braku).
3. `AniListCatalog.franchise(anilist_id) -> Franchise` według §10.5.1.
4. `_provider()` w `http_requests.py`: host `api.ani.zip` → `anizip`, `torrentio.strem.fun` → `torrentio`.
5. `ErrorCode.EPISODE_CATALOG_FAILED`.
6. Logowanie granic: jedno `logger.info` na zakończone zapytanie (dostawca, operacja, liczba elementów, czas), `logger.warning` na błąd (dostawca, kod) — bez URL z tytułami, bez treści.
7. Testy `network` (pomijane domyślnie): ani.zip dla Slime S1, Torrentio `kitsu:41024:4`, franczyza Slime.

**Kontrola:** testy adapterów na fixture; `uv run pytest -m network tests/integration/test_search_live.py` wykonane ręcznie raz (wynik do outcome).

**Gate:** review `opus5` faz 3–4 (read-only): kontrakty z §10.4, zgodność z regułami po egzaminie i etykietami fixture, parsowanie; findingi krytyczne/poważne poprawione. Surowe wejścia z roboczego korpusu potwierdzają, że nowe adaptery zachowują przygotowanie danych wersji egzaminowanej.

### Faza 5 — Start pomiaru N-01

**Cel:** uruchomić 7-dniowy pomiar po uzyskaniu sprawdzonej heurystyki i adapterów.

**Pliki:** `scripts/tmp/acquisition_probe.py` (rozszerzenie zbieracza fazy 1 o `freshness`). Używa adapterów z fazy 4 i `episode_selection` przez import pakietu `anishift`; własny `httpx.Client` z `RequestControl`; zapis do `workspace/.archive/acquisition/evidence/e1/`.

**Działania:** `freshness` według §9 N-01. Przed startem sprawdzić lokalne ignorowane skrypty/zasoby oraz checkout implementacji faz 3–4; zanotować commit/diff i sumy skryptów. Zapewnić odłączony start lokalnie na Windows właściciela; skrypt drukuje, jak go wznowić. Launcher `collect` fazy 1 nie uruchamia `freshness` bez rozszerzenia w tej fazie. N-02/N-04 są już rozliczone w fazach 1–2; nie zbierać ich ponownie. Pomiar trwa równolegle z dalszą integracją, do pierwotnego końca 7 dni.

**Kontrola:** pierwsze wpisy JSONL; brak wyjątków w pierwszej godzinie.

**Gate:** udzielona Z-1 ([../README.md](../README.md) §4) z uzupełnieniem z 2026-09-25 (§9): 7-dniowy pomiar świeżości/pokrycia lokalnie na Windows; liczniki i reguły niepełnej obserwacji według §9 N-01.

### Faza 6 — Usługa, IPC, wiring

**Pliki:** `anishift/application/acquisition.py`, `anishift/application/automation.py`, `anishift/cli/resident.py`, `anishift/bootstrap.py`, `anishift/application/__init__.py`; testy: `tests/application/test_acquisition.py`, `tests/application/test_automation.py`, `tests/cli/test_resident.py`, `tests/integration/harness.py`, `tests/integration/test_search_pipeline.py`.

**Działania:**
1. `AcquisitionService.__init__` przyjmuje `episode_catalog: EpisodeCatalog | None` i `stream_source: StreamSource | None`; franczyzę bierze z istniejącego `title_catalog`, którego protokół rozszerza się o `FranchiseCatalog.franchise` (§10.4).
2. Metody: `franchise(anilist_id)`, `episodes(anilist_id)`, `offer(key: EpisodeKey)`; pamięć i zachowanie według §10.5.2 pkt 6–7.
3. `_acquisition_command`: gałęzie `franchise`, `episodes`, `offer` przed dekodowaniem `candidate`.
4. `ResidentSession.franchise/episodes/offer`.
5. `bootstrap._acquisition_service` tworzy oba adaptery na wspólnym `httpx.Client` z `RequestControl`.
6. Harness integracyjny odtwarza `anizip__*`, `torrentio__*`, `anilist__franchise__*`.
7. `AcquisitionService` projektuje istniejący `SeasonAiring` do wejść `episode_listing` (§10.4–§10.5.2); transportuje nowe kontrakty bez importów usług w czystej domenie.

**Testy:**
- Slime: franczyza zawiera S1, S2 (obie części), S3, S4 w `SEASON`, OVA w `EXTRA`, Slime Diaries w `OTHER`.
- `episode_target` zbudowany z nagranych fixture dla `slime-s1e4`, `slime-s4e23`, `slime-s4e10`, `haibane-e1`, `ova-4` i `ova-1` zachowuje pola potwierdzone metadanymi i kontraktem §10.5.3, a wynik oceny odpowiada rozliczonym etykietom. Dla `ova-1` nie dopisuje badawczych kotwic z Sonarr: `season`/`episode` pozostają `None`. `targets.json` jest źródłem historycznego pochodzenia, nie wzorcem portu.
- S1E4 → sugestia zgodna; Slime Diaries i OAD nie są zgodne.
- S1 i Diaries: wejście bezpośrednie oraz przez franczyzę, zimna pamięć i obie kolejności rozgrzewania. Porównać konteksty, oceny i sugestie tych samych kandydatów; S1 odrzuca Diaries, Diaries odrzuca S1, własne poprawne wydania pozostają zgodne. OVA wybrane z S1 i bezpośrednio zachowuje ten sam łańcuch macierzysty; niepełny graf nie nadpisuje pełnego kontekstu.
- 12 × `offer` dla jednego wpisu → 12 zapytań Torrentio i 0 dodatkowych zapytań AniList/ani.zip po `episodes` (licznik w harnessie).
- Dispatcher: `offer` bez pola `candidate` zwraca `EpisodeOffer`, nie odmowę.
- Błędy AniList/ani.zip/Torrentio przechodzą przez prawdziwe `_answer` jako `INTERNAL` z właściwym `reason`; klient IPC zachowuje przyczynę. Osobno zwykły błąd polecenia daje `reason="command_failed"`. Kontroler w fazie 7 rozróżnia oba przypadki.
- ani.zip zwraca listę, `airing_schedule` zwraca 429: owner odpowiada sukcesem z `EpisodeListing.schedule_warning` i `schedule_retry_at`, a strict IPC zachowuje oba pola. Przypadki z poprawnym niewygasłym `SeasonAiring`, wyłącznie statusem `FranchiseEntry` i bez metadanych AniList potwierdzają źródła statusu/liczby oraz brak fałszywego `aired`; ponowienie po blokadzie usuwa notkę bez ponownego ani.zip w TTL.
- Strict round-trip przez `control_views.encode_view`/`decode_view`: `Franchise`, `EpisodeListing`, `EpisodeOffer` z pełnym `RankedCandidate.stream`, enumami, datami i polami `None`; dekoder odrzuca błędne typy pól; regresja starego `Release` nadal przechodzi.

**Gate:** testy zielone.

### Faza 7 — UI

**Pliki:** `anishift/cli/interactive/anime.py`, `anishift/cli/interactive/state.py` (wyłącznie przekazanie istniejących `provider_locks` do Anime), `anishift/cli/AGENTS.md`, `tests/cli/test_interactive_anime.py`, `tests/cli/test_interactive_state.py`, `tests/application/test_automation.py` (wspólny komunikat źródła, W-08 i 429 przez owner/IPC). Stara droga nadal produkuje szkic subskrypcji.

**Działania:**
1. Ekrany ENTRIES, EPISODES, OFFER, CANDIDATES według ux.md §4–§6.
2. Po Enter na tytule — nowa droga (ENTRIES). Klawisz `G` na TITLES otwiera dotychczasową drogę `search_title` → RESULTS z zachowanymi akcjami (`D`, `O`, `S`, `F`, zakres) i kalkulatorem sezonów (D1); wspólny komunikat błędu zmienia pkt 3. Stopka TITLES: „Enter wybierz · G wydania wg grup (stara wersja) · / szukaj · Esc wróć”.
2c. `_find_titles` według W-08 i §10.7: brak tytułu → komunikat → Nyaa → RESULTS z `_NO_TITLE`; błąd AniList → PROBLEM, bez Nyaa. Zachować sortowanie fallbacku po seedach i Esc → QUERY. Usunąć wyłącznie fallback po awarii katalogu; dopisać aktualne zachowanie do scoped `AGENTS.md`.
2b. CANDIDATES (U-24): pokazuje 1080p, 2160p i nieznaną rozdzielczość; 720p i niższe tylko, gdy nie ma żadnego zgodnego 1080p/2160p.
2a. Wpis-film w ENTRIES: Enter otwiera EPISODES z jednym wierszem „Film” i notką „Pobieranie filmów zależy od pomiaru E1”; `D` na nim otwiera podgląd tylko wtedy, gdy `kitsu_id` jest znane (zapytanie `kitsu:<id>:1`), inaczej notka „Brak mapowania”.
3. `_PROBLEM_TEXTS`: `TORRENT_SOURCE_FAILED` → „Źródło wydań nie odpowiada” dla obu źródeł (Nyaa i Torrentio), `EPISODE_CATALOG_FAILED` → „Lista odcinków niedostępna”. Zastąpić stare asercje „Nyaa nie odpowiada” w `tests/cli/test_interactive_anime.py` i `tests/application/test_automation.py:test_anime_enter_search_crosses_owner_ipc_and_controlled_http`. Ten ostatni test rozdziela teraz awarię katalogu (zero Nyaa) od błędu Nyaa po poprawnym pustym wyniku lub wejściu przez `G`; zachować sprawdzenie obu kodów błędu i brak wycieku payloadu, zamiast usuwać scenariusz błędu źródła.
3a. Podłączyć termin następnej próby ścieżką §10.7: istniejący snapshot/status → `StateController._receive`/`attach_anime` → `AnimeController.refresh_provider_locks`; w lokalnym workerze odczyt `request_control.blocked_until`. `until` jest tylko odczytywane, bez drugiego cooldownu i bez I/O w renderze.
4. Zakres `Z`: lista `1,3,9-12` i „od N” (`5-`); tylko liczby całkowite; nieznany numer → notka „Brak odcinka 30 w tym wpisie”.

**Testy:** przejścia i Esc na każdym ekranie; `G` otwiera starą drogę — testy jej akcji zmieniają klawisz wejścia z Enter na `G`, a asercje błędów rozliczają pkt 3; tylko `INTERNAL` z `reason="command_failed"` na nowej operacji daje komunikat o restarcie; `D` bez zaznaczeń; zaznaczenie 1 i 3 bez 2; `Z` z listą; Esc w trakcie `offer`; spóźniony wynik po Esc; litery w TextInput nie są skrótami; wąski terminal (≤ 50 kolumn) bez nakładania; render bez wywołań usługi (fałszywa usługa licząca wywołania).

- Przez owner i IPC: `INTERNAL` z każdym rozpoznanym kodem dostawcy na `franchise`/`episodes`/`offer` pokazuje właściwe źródło i cooldown, bez tekstu restartu; zwykły błąd z `command_failed` pokazuje restart. Nieznany inny `reason` nie jest uznany za dowód starego rezydenta.
- Częściowy sukces: ani.zip działa, AniList 429 z `Retry-After: 90`; przez owner i IPC dociera lista, notka o harmonogramie i termin. Notka pozostaje podczas nawigacji po odcinkach; fake clock i oba porządki snapshot/lista aktualizują czas bez I/O. Jawne ponowne wejście po terminie pobiera harmonogram i usuwa notkę.

- W-08: poprawny pusty katalog przechodzi do Nyaa z widocznym komunikatem i notką; awaria/429 AniList oraz błąd ani.zip nie uruchamiają Nyaa. Zaktualizować `test_only_a_catalog_failure_falls_back_to_release_search` do nowego kontraktu (lokalnie i przez IPC), zachować `test_the_fallback_results_name_the_order_they_arrived_in` i `test_escape_from_the_fallback_results_returns_to_the_query` dla braku tytułu.
- 429: MockTransport zwraca `Retry-After: 90`; owner zapisuje/publikuje ten sam `until`, `StateController` przekazuje go przy dołączeniu Anime i kolejnym zdarzeniu, kontroler pokazuje „spróbuj za 90 s”, po przesunięciu fake clock o 30 s — „za 60 s”, po terminie — możliwość ponowienia, bez dodatkowego żądania. Sprawdzić każdy provider, brak pomylenia terminu Nyaa/Torrentio, błąd przed i po snapshotcie, lokalny odczyt `blocked_until` oraz brak wymyślonego czasu przy błędzie bez blokady.

**Kontrola:** pełne bramki.

**Gate:** review `opus5` faz 6–7.

### Faza 8 — Próba N-03

**Pliki:** `scripts/tmp/magnet_probe.py` (NEW), wynik w `evidence/e1/magnet/`.

**Działania:** §9 N-03, lokalnie na Windows właściciela (nie na VPS). Binarka qBittorrent: ta, której używa AniShift (`external/` albo ścieżka z `platform/binaries.py`); profil i dane wyłącznie w `%TEMP%`; porty losowe wolne; po próbie weryfikacja: proces nie istnieje, port nie nasłuchuje, katalog usunięty.

**Gate:** udzielona Z-3 ([../README.md](../README.md) §4) na próbę metadanych w tymczasowym qBittorrencie; wynik zapisany.

### Faza 9 — H1, wynik etapu, review końcowe

1. Po zakończeniu `freshness` (7 dni): analiza N-01 według reguły; dołączyć zamknięte wyniki N-02 z faz 1–2, manifesty podziału, dowód jednorazowego egzaminu i akceptację metryk oraz N-03/N-04. Bez ponownego strojenia i egzaminowania na wykorzystanej części odłożonej.
2. H1 z właścicielem (ux.md §12): scenariusz, wynik, uwagi. Uwagi o wyglądzie → poprawka UI w tej fazie; uwagi o znaczeniu → spec.
3. `outcomes/e1.md` według kontraktu §16.
4. Świeży `opus5` review całości (kod + outcome) → poprawki → weryfikacja.
5. Commit(y) w formacie `typ(scope): opis` (scope z `scripts/hooks/check_commit_msg.py`), PR piętrowy na `work/acquisition/00-model-catalog-v2` — tylko na zlecenie właściciela.

## 12. Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Heurystyka zbudowana na oznaczonym korpusie uogólnia na niewidziane dane | ≥ 2000 tytułów / ≥ 10 000 rekordów; zamrożony podział, izolacja i jednorazowy egzamin: 0 błędnych `zgodnych`, metryki per warstwa zaakceptowane przez właściciela | Oddziela strojenie od oceny; sumy i rejestr prób wiążą wynik z danymi i regułami |
| Domena realizuje sprawdzone reguły | Stałe oznaczone fixture, przypadki szczególne i porównanie zamrożonego artefaktu z domeną na części roboczej | Wykrywa regresje integracji bez ponownego wykorzystania egzaminu |
| Ranking według spec | Testy przypadków granicznych | Każda reguła U-04/05/06/23 ma przypadek rozróżniający |
| Parsowanie ani.zip/Torrentio | Fixture z badań + 1 test `network` | Rzeczywiste odpowiedzi |
| Franczyza | Fixture nagrane w fazie 0 | Rzeczywiste odpowiedzi 3 franczyz |
| IPC | `test_automation.py`, `test_resident.py` | Strict encode/decode |
| UI | `test_interactive_anime.py` + H1 | Mechanika + ocena człowieka |
| Brak regresji | Pełne bramki | Obowiązek `AGENTS.md` |
| Konfiguracja oceniających zgodna z E00 i D2/D3 | Rozszerzone `tests/config/test_model_settings.py` (env, fabryka, konto 2, repr/logi, brak konta 2), istniejące `tests/config/test_model_catalog.py`, `tests/services/llm/test_palantir_auth.py`, `tests/services/llm/test_palantir_requests.py`, `tests/services/llm/test_palantir_accounts.py` + pełna paczka na A/B/arbitrze, pewne kontrole oraz sprawdzenie ucięcia/podziału/równoległości/JSONL w fazie 0 | Dowód podłączenia dwóch kont, prywatności, budżetu, kompletnego JSON/etykiet i wznowienia; bez zmian silnika w E1 |
| N-01–N-04 | Skrypty + surowe dane w `evidence/e1/` | Odtwarzalność |

### Bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Polecenia są zgodne z `AGENTS.md` i `pyproject.toml` na `bde35d7`. `pytest` bez podkatalogu obejmuje też testy narzędzi pakietu; testy `network` włącza jawne `-m network` z fazy 4 (`tests/conftest.py:pytest_collection_modifyitems`). Mypy z targetem Linux jest bramką statyczną; CI uruchamia pytest tylko na Windows (`.github/workflows/ci.yml`). Pomiary E1 działają lokalnie na Windows według decyzji z 2026-09-25; nie rozszerzają wsparcia aplikacji na Linux.

### Obowiązki regresyjne

PR-06 (cztery zakładki, marka), PR-01 (panel odłącza się bez zatrzymania pracy), istniejące testy subskrypcji i pobierania z warstwy aplikacji (nieużywane przez nowe UI, ale nadal działające).

### Odbiór człowieka — H1

Pełny scenariusz: [../ux.md](../ux.md) §12, H1. Warunek PASS: właściciel dochodzi do właściwego odcinka (w tym Slime S1E4) w ≤ 3 wyborach od wpisania nazwy dla 10 swoich tytułów i uznaje sugestie za sensowne albo wskazuje konkretny błąd.

## 13. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
| --- | --- | --- | --- |
| Limit złożoności AniList | Faza 0 | Mniejsza głębokość, więcej warstw | > 4 zapytań dla Slime |
| Zmiana formatu Torrentio | Test `network` | Aktualizacja parsera + fixture | Brak pól `infoHash` |
| Pomiar przerwany lub emisja pod koniec okna | Luki w JSONL albo brak pełnego horyzontu §9 N-01 | Wznowienie wyłącznie do pierwotnego końca 7 dni; niepełne obserwacje poza zbiorem rozstrzygającym | < 5 pełnych porównywalnych odcinków → decyzja właściciela; dalszy pomiar wymaga nowej zgody |
| Za dużo `niepewnych` lub błędnych `niezgodnych` | Metryki N-02 per warstwa | Decyzja właściciela na liczbach, bez arbitralnego progu | Brak akceptacji → nowa iteracja robocza i nowy egzamin |
| Brak 10 000 rekordów lub reprezentacji warstw w Z-1 | Liczniki po maksymalnie 4000 próbach / 4 dobach | Zatrzymać zbieranie z raportem braków, bez automatycznego wydłużenia | Jedno pytanie Z-1 w §15 |
| 429 podczas zbierania | Odpowiedź i cooldown źródła | Wznowienie tylko w pierwotnym budżecie/czasie, bez obchodzenia limitu | Potrzebny dodatkowy wolumen/czas → §15 |
| Wyciek albo ponowne użycie części odłożonej | Dostęp autora do danych/źródeł/ocen lub drugi wpis próby dla tej samej części | Unieważnić ją jako dowód, zachować ślad w manifeście | Nowa niewykorzystana część przed egzaminem |
| Stary rezydent po aktualizacji | Test IPC | Komunikat restartu | — |

## 14. Lokalna adaptacja

Wolno: nazwy prywatne, podział helperów, teksty zgodne znaczeniowo z ux.md, głębokość relacji, stałe limitów pamięci, dokładne nazwy plików fixture.

## 15. Materialna zmiana — zatrzymanie

Zmiana typów publicznych względem §10.4, nowy magazyn danych aplikacji, zapis stanu trwałego poza wyjątkiem `provider_locks` z §7, nowa zależność, zmiana wersji protokołu lub reguł rankingu — wymagają powrotu do orkiestratora i aktualizacji planu. Budowa i strojenie heurystyki na części roboczej należą do fazy 2; nie wymagają parytetu z prototypem. Zmiana po zamrożeniu egzaminowanym, ujawnienie odłożonych danych lub brak niewykorzystanej części do kolejnego egzaminu zatrzymują integrację do czasu rozliczenia §9 N-02.

### Rozstrzygnięcia właściciela — 2026-09-24

| ID | Ustalenie | Miejsce wykonania |
| --- | --- | --- |
| D1 | Nowa droga omija błąd numeracji AniList `182205`; starej drogi pod `G` nie naprawiamy osobno, bo UI znika w E3, zaplecze w E5. | §6.1, §10.5.3; masterplan „Znany błąd poza etapami” |
| D2 | Dwa konta Palantira do oceny korpusu. Faza 0 podłącza origin i token 2 z `Settings` do `palantir_llm_config`; wartości w `.env` wpisuje właściciel. Bez zmian `anishift/services/llm/`; brak konta 2 zachowuje dzisiejsze działanie. | §9 N-02 „Konto 2”, §10.3, faza 0 pkt 5a–5b |
| D3 | Zastąpione decyzją właściciela 2026-09-25: Astra jako A i Opus 5 jako B oceniają niezależnie cały korpus; niezgody rozstrzyga dyskusja świeżych A/B, anonimowe losowane oceny, najwyższe rozumowanie i maksymalnie 3 rundy. Brak zgody lub obie nieustalone → właściciel. Kontrole poza dyskusją. Jeden pisarz JSONL i resume na krótkich kapsułach argumentów, bez pełnych odpowiedzi. Start 4, +2 po stabilnym oknie 10 pełnych paczek, połowa po 429/dwóch wzrostach median >25%; szczegóły w §9. Retry/cooldown/failover pozostają w `LlmService`. Konto 2 obsługiwane, lecz brak danych konta 2 nie blokuje fazy 1. | §9 N-02, faza 1; zastępuje historyczny wybór arbitra z fazy 0 |
| D4 | Istniejący zapis `provider_locks` po 429 jest dozwolonym wyjątkiem od zakazu zmian stanu, bez nowego modelu danych. | §7 Forbidden; termin w UI: §10.7 i faza 7 |
| D5 | Brak tytułu w AniList: komunikat i przejście do Nyaa (stara lista wydań). Awaria źródła nadal daje błąd bez tego przejścia. | spec W-08, UX U01, §10.7–§10.8 i faza 7 |

**Jedno pytanie do właściciela — rozszerzenie Z-1, jeśli podstawowa próba nie wystarczy:** czy zezwalasz na dodatkowy wolumen/czas lokalnie na Windows, gdy 2000 tytułów, maksymalnie 4000 prób Torrentio przy 1000/rolling 24 h i twardych 4 dobach nie da ≥ 10 000 unikalnych oznaczonych rekordów we wszystkich warstwach albo zabraknie świeżej części do kolejnego egzaminu? Podstawa to Z-1 uzupełniona decyzją z 2026-09-25 (§9). Podstawowy dobór to najwyżej 3800 zapytań + 6 N-04 = 3806 (194 rezerwy), około 3,8 doby przy 86,4 s odstępu + narzut, z około 4,7 h nominalnego zapasu. Przestoje mogą zakończyć próbę luką; brak automatycznego wydłużenia. Wymagana średnia ≥ 2,632 rekordu na podstawowe zapytanie; przy 4000 całkowitych próbach dolna granica to 2,5. Nie da się dziś podać uczciwego dodatkowego wolumenu: przy zatrzymaniu przedstawić rzeczywiste `R` rekordów, brak `max(0, 10000 − R)`, brakujące warstwy/tytuły i zmierzone tempo. Dla dodatniego tempa `y` unikalnych rekordów na próbę orientacyjny dodatkowy wolumen to `ceil(max(0, 10000 − R) / y)`, minimum okien dobowych `ceil(dodatkowe_próby / 1000)`; pokrycie warstw i świeży egzamin wycenić osobno z danych, bez obietnicy wynikającej tylko ze średniej. Gdy `y=0`, raportować brak podstaw do oszacowania. Bez zgody nie przekraczać wolumenu, liczby tytułów ani okna; 7 dni N-01 nie jest zgodą na 7 dni dodatkowego korpusu. To pytanie warunkowe: obecna zgoda wystarcza do podstawowego zbierania, lecz nie gwarantuje osiągnięcia nowego celu. Wyniki N-01–N-04 pozostają zadaniem E1 według §9.

**B5 — rozstrzygnięte w planie:** budżet wynika z kontraktu odpowiedzi, a wykonalność pełnych paczek A/B potwierdziły próby phase0c. Decyzja właściciela 2026-09-25 zastępuje trzeciego arbitra dyskusją A/B na najwyższym rozumowaniu, do trzech rund i bez kontroli w dyskusji. Nie wymaga limitów w katalogu ani zmiany silnika. Historyczne wyniki Gemini/Groka pozostają dowodami fazy 0, nie aktywną ścieżką ani warunkiem fazy 1.

## 16. Definition of Done i kontrakt wyniku

- [ ] warunki §3 spełnione;
- [ ] bramki zielone z liczbami w outcome;
- [ ] zakres i zakazy zachowane (diff sprawdzony przez orkiestratora);
- [ ] H1 wykonane;
- [ ] N-01–N-04 z decyzjami;
- [ ] review `opus5` rozliczone.

`outcomes/e1.md` zawiera: status; zmienione pliki; wyniki bramek (liczby); liczności i warstwy korpusu, koszty zapytań/czas w Z-1, rozliczenie etykiet, manifest podziału (ziarno i sumy), dowód izolacji, wersję reguł i jednorazowy wynik egzaminu z metrykami oraz decyzją właściciela; wyniki N-01–N-04 z liczbami i decyzjami według §9; wynik H1 i uwagi; odchylenia od planu; znane ograniczenia; stan Git (gałąź, commity); rekomendowany zakres planu E2. Raport dostępny autorowi nie ujawnia rekordów nadal odłożonych.
