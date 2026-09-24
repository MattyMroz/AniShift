---
kind: plan
status: do-akceptacji
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
created: 2026-09-23
stage: E1
---

# Plan E1: wybór odcinka na prawdziwych danych i pomiary

## 1. Cel

Zbudować nową ścieżkę zakładki Anime **tytuł → wpisy franczyzy → odcinki → sugestia wydania i inne wydania** na żywych danych AniList, ani.zip i Torrentio, z heurystyką tożsamości i rankingiem ze specyfikacji — bez pobierania i bez zmian stanu trwałego. Równolegle zmierzyć N-01–N-04 (spec §15), aby plany E2 i E3 powstały na faktach.

## 2. Rezultat użytkownika

Właściciel otwiera Panel → Anime, wpisuje tytuł, wybiera rok/wpis, widzi sezony, części, dodatki i filmy franczyzy, wchodzi w sezon, widzi odcinki z datami emisji, zaznacza odcinki i `D` pokazuje dla każdego sugerowane wydanie z powodem, a `I` wszystkie wydania z oceną „zgodny / niepewny / niezgodny”. Nic się nie pobiera. Dostaje też raport: jak szybko nowe odcinki pojawiają się w źródle, ile wydań heurystyka odrzuca na jego tytułach, czy magnet daje listę plików, czy filmy działają.

## 3. Warunki końcowe

- [ ] W-01–W-08, R-01–R-03, R-05, R-06, R-08 spełnione w nowej ścieżce; R-04 bez akcji wyboru (lista „Inne wydania” z oceną i powodem). Bez pobierania i subskrybowania z nowej ścieżki.
- [ ] Heurystyka w kodzie daje te same 231 decyzji co `workspace/.archive/acquisition/evidence/replay.py`.
- [ ] Korpus ≥ 2000 tytułów zebrany i w całości oceniony przez dwóch niezależnych agentów; 0 błędnych `zgodnych` po poprawkach reguł; lista dla właściciela sprawdzona; metryki pokrycia zapisane (§9 N-02).
- [ ] Ranking spełnia U-04, U-05, U-06, U-23 na przypadkach granicznych z §10.8 i fazy 1.
- [ ] Stara ścieżka wyników grupowych (ekran RESULTS, `D` pobierz, `O` subskrybuj) działa jak dziś, osiągalna z listy tytułów klawiszem `G`; właściciel może nadal pobierać i dodawać subskrypcje w czasie E1.
- [ ] Pełne bramki `AGENTS.md` zielone; nowe testy bez sieci; testy `network` dla nowych adapterów istnieją i przechodzą ręcznie.
- [ ] Raport pomiarów `outcomes/e1.md` z odpowiedziami na N-01–N-04 i decyzjami dla E2/E3 według reguł §9.
- [ ] H1 wykonane przez właściciela, uwagi rozliczone.
- [ ] Niezależne review `opus5` bez otwartych findingów krytycznych i poważnych.

## 4. Nie-cel

Pobieranie, subskrybowanie, zmiany WatchState i `subscriptions.json`, migracje, zmiany zakładki Subskrypcje, Przetwarzania, Biblioteki, Ręcznego i Ustawień, kontrola zawartości pobranych plików, usuwanie kodu Nyaa i starych funkcji `acquisition.py` używanych przez subskrypcje.

## 5. Authority i baseline

| Źródło | Rola |
| --- | --- |
| [../spec.md](../spec.md) | Wymagania i ustalenia |
| [../ux.md](../ux.md) §2–§6, §11, §12 | Ekrany U01–U04, stany, klawisze |
| [../masterplan.md](../masterplan.md) | Granice etapu E1 |
| `AGENTS.md`, `anishift/AGENTS.md`, `anishift/application/AGENTS.md`, `anishift/cli/AGENTS.md`, `anishift/services/catalog/AGENTS.md`, `anishift/services/torrents/AGENTS.md`, `tests/AGENTS.md` | Reguły kodu, testów, logowania |
| `.agents/skills/coding/SKILL.md` + `references/python.md`, `comments-docstrings.md`, `testing.md` | Standard kodu |
| `workspace/.archive/acquisition/evidence/matching/prepare.py.txt` | Heurystyka do przeniesienia |
| `workspace/.archive/acquisition/evidence/polish/study.py.txt`, `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt` | Rozpoznawanie języków, rozdzielczości, źródeł z nazw |
| `../research/anime-api-metadata-validation.md`, `../research/anime-api-release-validation.md` | Kontrakty pól ani.zip i Torrentio |

**Baseline:** HEAD `0e8a6bf`, gałąź `work/local-automation/06-efficiency`, zmieniony `AGENTS.md` i nieśledzone dokumenty w `docs/work/`. Wykonawca zaczyna od nowej gałęzi (faza 0).

**Znane wcześniejsze failures:** zgłoszone historycznie `test_library_routes_retry_to_selected_deletion_or_relocation` (niepotwierdzone na tym HEAD). Faza 0 ustala rzeczywisty baseline.

## 6. Stan aktualny

### 6.1 Obecne zachowanie

- `AnimeController` (`anishift/cli/interactive/anime.py`, 1327 linii) ma ekrany QUERY → TITLES → BUSY → RESULTS → DONE/PROBLEM. Po wyborze tytułu wyszukuje wydania Nyaa (`search_title`) i grupuje je po grupach wydających.
- Kontroler woła `self._acquisition`, które jest `ResidentSession` (IPC do rezydenta) albo `AcquisitionService` (bez rezydenta). Oba mają te same metody: `find_titles`, `season_context`, `search_title`, `search`, `download`.
- Rezydent obsługuje polecenie `acquisition` z pod-operacjami `titles`, `search`, `season`, `releases` (`automation.py:3229–3261`). Po `titles` i `search` dispatcher dekoduje pole `candidate` (`:3239`) **przed** sprawdzeniem nazwy operacji, więc nieznana pod-operacja bez `candidate` kończy się wyjątkiem; `_answer` (`:1136–1153`) zwraca wtedy `refused(INTERNAL, …, "command_failed")`. Komunikat „Unknown acquisition operation” pada tylko przy poprawnym `candidate`.
- `AniListCatalog` (`services/catalog/anilist.py`) ma wyszukiwanie, relacje tylko jako ID prequeli i harmonogram emisji.
- `RequestControl` (`services/http_requests.py`) rozpoznaje dostawców `anilist`, `nyaa`, `qbittorrent`; wszystko inne to `other`. Odstęp 1 s obowiązuje tylko `anilist` i `nyaa`.
- Nie ma adapterów ani.zip i Torrentio, heurystyki tożsamości ani rankingu w kodzie aplikacji.

### 6.2 Luka

Brak modelu wpisu franczyzy i listy odcinków; brak źródła kandydatów per odcinek; tożsamość i jakość wydania wynikają z parsowania nazw Nyaa i filtrów grup.

### 6.3 Istniejące elementy do użycia

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
| --- | --- | --- | --- |
| Wyszukiwanie tytułów | `AniListCatalog.search`, `TitleCandidate` | Bez zmian | — |
| Harmonogram emisji | `AniListCatalog.airing_schedule`, `SeasonAiring` | Daty emisji odcinków (U-13) | — |
| Limity HTTP | `RequestControl`, `request_scope` | Nazwy `anizip`, `torrentio` | Bez nowego odstępu (Q-04) |
| Wątek sieciowy i generacje UI | `AnimeController._spawn`, `_generation` | Wzorzec dla nowych ekranów | Render bez I/O |
| Pole tekstowe, zakres | `TextInput`, `_parse_range`, `_RANGE_RE` | Rozszerzyć o listy numerów całkowitych | — |
| Kodowanie widoków IPC | `encode_view`, `decode_view` (`control_views.py`) | Nowe dataclassy | Strict decode |
| Nagrane odpowiedzi | `tests/fixtures/search/`, `tests/integration/harness.py` | Konwencja fixture i `manifest.json` | — |
| Surowe odpowiedzi z badań | `workspace/.archive/acquisition/evidence/sources/metadata/*.raw.json`, `workspace/.archive/acquisition/evidence/sources/releases/*.body.json`, `workspace/.archive/acquisition/evidence/sources/ova/*.raw.json` | Fixture testów adapterów | Stan z 2026-09-22 |
| Zbiór 231 decyzji | `workspace/.archive/acquisition/evidence/matching/dataset.json`, `targets.json` | Test parytetu | 439 KB — przyciąć do pól testu |
| Izolowany profil qB | `workspace/.archive/acquisition/evidence/bundle/run01/probe-*.py.txt` | Wzorzec próby N-03 | Tam DHT wyłączone; tu potrzebne |

### 6.4 Dowody stanu

| Twierdzenie | Dowód | Status |
| --- | --- | --- |
| Pod-operacje `acquisition` można dodawać bez zmiany wersji protokołu, jeśli nowe gałęzie stoją przed dekodowaniem `candidate` | `automation.py:3235–3245`; stary rezydent odpowie `refused(INTERNAL, "command_failed")` (`:1136–1153`) | verified |
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
- `AnimeController`: nowe ekrany ENTRIES, EPISODES, OFFER, CANDIDATES jako domyślna droga po wyborze tytułu; dotychczasowy ekran RESULTS z grupami, `D` i `O` bez zmian, osiągalny z TITLES klawiszem `G` („Wydania wg grup — stara wersja”).
- Skrypty pomiarowe w `scripts/tmp/` i raport `outcomes/e1.md`.
- Testy, fixture, aktualizacja scoped `AGENTS.md` dla zmienionych modułów.

### Out of scope

Wszystko z §4.

### Forbidden

- Zapis do WatchState, `subscriptions.json`, ustawień, presetów.
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
- Port heurystyki nie daje parytetu 231/231 bez zmiany reguł.
- Torrentio lub ani.zip odpowiada innym formatem niż w §6.4.
- Próba N-03 wymaga zmiany prywatnego profilu qB rezydenta.
- Potrzebna jest nowa zależność lub nowy kod błędu poza wymienionym w §10.2.

## 8. Kontekst do przeczytania (kolejność)

| Kolejność | Źródło | Po co | Zakres |
| --- | --- | --- | --- |
| 1 | `AGENTS.md` + scoped `AGENTS.md` z §5 | Reguły | full |
| 2 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/SKILL.md`, `references/python.md`, `comments-docstrings.md`, `testing.md` | Standard | full |
| 3 | `../spec.md` §3.3, §4, §5.1–5.2 | Kontrakt | sections |
| 4 | `../ux.md` §2–§6, §11, §12 | Ekrany i klawisze | sections |
| 5 | `anishift/cli/interactive/anime.py` | Kontroler do przebudowy | full |
| 6 | `anishift/application/acquisition.py:115–660` | Protokoły i usługa | symbols |
| 7 | `anishift/application/automation.py:3229–3261` | Dispatcher `acquisition` | section |
| 8 | `anishift/cli/resident.py:178–215` | Klient IPC | section |
| 9 | `anishift/services/catalog/anilist.py`, `types.py` | Adapter AniList | full |
| 10 | `anishift/services/http_requests.py` | Limity | full |
| 11 | `anishift/bootstrap.py:92–135` | Wiring | section |
| 12 | `workspace/.archive/acquisition/evidence/matching/prepare.py.txt` | Heurystyka | full |
| 13 | `workspace/.archive/acquisition/evidence/polish/study.py.txt:36–80`, `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt:34–116` | Ekstrakcja faktów | sections |
| 14 | `tests/integration/harness.py`, `tests/cli/test_interactive_anime.py` (struktura) | Testy | symbols |

## 9. Pomiary i reguły decyzji

Wszystkie pomiary zapisują surowe odpowiedzi i wyniki w `workspace/.archive/acquisition/evidence/e1/` (pliki < 500 KiB, bez sekretów, bez ścieżek absolutnych użytkownika). Skrypty w `scripts/tmp/` są jednorazowe i nie są importowane przez aplikację.

### N-01 — opóźnienie pojawienia się odcinka

- **Próbka:** 8–12 tytułów o statusie RELEASING, których kolejny odcinek ma emisję w oknie 7 dni od startu pomiaru: najpierw wszystkie tytuły z aktywnych subskrypcji właściciela w `config/subscriptions.json` (identyfikator AniList z wpisu; tylko odczyt), uzupełnione najpopularniejszymi tytułami w emisji z AniList (`Page(media(status: RELEASING, sort: POPULARITY_DESC))`). Lista MAL nie jest używana (decyzja właściciela).
- **Miejsce:** VPS właściciela (Oracle Always Free, Ubuntu na ARM), dostęp z repozytorium `C:\Users\MattyMroz\Desktop\PROJECTS\VpsOracleManager`: `.\deploy\connect.ps1` (konfiguracja `deploy/config.ps1` i klucz w `.secrets/` istnieją — nie kopiować ich nigdzie). Na VPS: klon gałęzi E1 i `uv sync` w katalogu domowym użytkownika, uruchomienie w `tmux` albo `nohup`, bez Dockera i bez zmian w stackach VpsOracleManager. Zgodnie z runbookiem tego repozytorium dłuższe polecenia wysyłać jako plik `.sh` przez `scp`, nie przez zagnieżdżone cudzysłowy PowerShell. Stack `keepalive` ustępuje realnemu obciążeniu, więc pomiar mu nie przeszkadza.
- **Procedura:** `scripts/tmp/acquisition_probe.py freshness --days 7`. Dla każdego odcinka z emisją w oknie: od `airingAt` co 15 min przez 48 h, potem co 1 h do końca okna: (a) Torrentio `kitsu:<id>:<n>` + heurystyka; (b) RSS Nyaa dla aliasu tytułu (istniejący `nyaa.search_releases`, kategorie jak dziś) + ta sama heurystyka po nazwach. Zapis: czas pierwszego kandydata `zgodny` w każdym źródle, liczba kandydatów, zbiory hashy `zgodnych` z obu źródeł (pokrycie), nagłówki `Age`/`CF-Cache-Status`, odpowiedzi 429.
- **Wznowienie:** skrypt dopisuje JSONL i po restarcie pomija wykonane odczyty.
- **Reguła decyzji dla E3:**
  - Jeśli w każdym odcinku próbki Torrentio ma zgodnego kandydata nie później niż Nyaa + 1 h (istniejący interwał sprawdzania) → E3 używa tylko Torrentio; pierwsze sprawdzenie po emisji = najkrótsze zaobserwowane opóźnienie Torrentio zaokrąglone w dół do 15 min.
  - Jeśli w którymkolwiek odcinku Torrentio jest później niż Nyaa + 1 h albo wcale → E3 dodaje RSS Nyaa jako drugie źródło kandydatów subskrypcji, oceniane tą samą heurystyką; kod Nyaa nie jest usuwany w E5.
  - **Pokrycie:** jeśli w którymkolwiek odcinku Nyaa ma zgodne wydanie, którego nie ma Torrentio, a które według rankingu byłoby lepsze od najlepszego z Torrentio → E2 łączy kandydatów z obu źródeł także dla zwykłego Pobierz (deduplikacja po hashu).

### N-02 — heurystyka na korpusie co najmniej 2000 tytułów

Wymaganie właściciela (2026-09-23): prototyp heurystyki sprawdzony na 231 rekordach z trzech franczyz to za mało; próba ma objąć co najmniej 2000 tytułów.

- **Dobór tytułów:** 2000 wpisów AniList, warstwowo, żeby próba nie była skrzywiona w stronę popularnych serii TV:
  - 1200 TV/TV_SHORT/ONA — po równo z przedziałów lat premiery: do 2005, 2006–2012, 2013–2018, 2019–2023, 2024+; w każdym przedziale kolejno według popularności AniList;
  - 400 OVA/SPECIAL i 200 MOVIE — tak samo po przedziałach lat;
  - 200 wpisów będących kontynuacją (ma krawędź `PREQUEL`: sezony 2+, części, cour) — tu heurystyka myli się najczęściej;
  - wszystkie tytuły z aktywnych subskrypcji właściciela (`config/subscriptions.json`, tylko odczyt), wliczone do puli.
  Lista wpisów i ziarno losowania zapisane w `evidence/e1/corpus/titles.json`, żeby próbę dało się odtworzyć.
- **Odcinki na tytuł:** odcinek 1 i ostatni wyemitowany (film: jeden odczyt, tylko jeśli N-04 potwierdzi obsługę filmów; inaczej filmy dają tylko pomiar pokrycia).
- **Zbieranie:** `scripts/tmp/acquisition_probe.py corpus` na VPS: AniList (franczyza), ani.zip, Torrentio. Budżet: do 2000 zapytań Torrentio na dobę (reszta limitu dla N-01), więc ~4000 zapytań w 2–3 doby. AniList z istniejącym odstępem 1 s. Surowe odpowiedzi zapisywane **poza repozytorium** (na VPS, katalog `acquisition-corpus/`, z sumami SHA-256), aby heurystykę można było potem uruchamiać ponownie offline, bez nowych zapytań. W repozytorium: `evidence/e1/corpus/` z listą tytułów, sumami, wynikami i próbką audytu (pliki < 500 KiB).
- **Metryki bez etykiet (liczone automatycznie):**
  - pokrycie automatu: odsetek odcinków z co najmniej jednym kandydatem `zgodny`;
  - rozkład decyzji `zgodny` / `niepewny` / `niezgodny` i powodów, osobno dla TV, kontynuacji, OVA/SPECIAL, filmów i przedziałów lat;
  - czas heurystyki na całym korpusie.
- **Ocena poprawności (etykiety) — cały korpus, nie próbka** (decyzja właściciela 2026-09-23: nieograniczona liczba agentów OpenCode):
  - każdy rekord korpusu (odcinek + kandydat) oceniają **dwaj niezależni „oceniający” — dwa modele różnych rodzin** (najmocniejszy dostępny model Anthropic i najmocniejszy Google albo OpenAI z katalogu modeli Palantir AniShift; bez modeli typu flash/mini). „Oceniający” to wywołanie modelu z jednym stałym poleceniem oceny, bez narzędzi i bez dostępu do repozytorium; nie widzi decyzji heurystyki ani oceny drugiego modelu;
  - oceniający dostaje paczkę do 100 rekordów: tytuły i aliasy celu, numer lokalny/TVDB/absolutny, tytuł odcinka, nazwę wydania, ścieżkę, nazwę pliku; zwraca dla każdego `poprawny` / `błędny` / `nie da się ustalić` i jedno zdanie uzasadnienia, w JSON;
  - **kontrola jakości agenta:** do każdej paczki dosypywanych jest 10 losowych rekordów z 231 zbadanych (`identity-231.json`, znana etykieta). Paczka, w której oceniający myli się na którymkolwiek z nich, jest odrzucana i oceniana od nowa (ten sam model, nowe wywołanie; przy drugim błędzie — trzeci model);
  - **niezgodność dwóch oceniających** → trzeci model innej rodziny; gdy nadal brak zgody albo wynik „nie da się ustalić” → rekord trafia na listę dla właściciela;
  - właściciel sprawdza wszystkie rekordy z tej listy i dodatkowo 50 losowych rekordów zgodnie ocenionych przez oba modele; każda jego niezgodność z oceną modeli → przegląd całej warstwy (np. wszystkich OVA), z której pochodził rekord;
  - oceniający są narzędziem oceny poza aplikacją; zakaz modelu AI w samym rozpoznawaniu odcinka (spec §9) nadal obowiązuje;
  - **Mechanizm — silnik LLM AniShift (`anishift.services.llm`, silnik Palantir)** (decyzja właściciela 2026-09-23; **zależy od E00** — modele i wywołania według katalogu po E00): `scripts/tmp/corpus_labels.py` nie ma własnej obsługi HTTP ani providerów i nie używa silnika tłumaczenia. Konfigurację modelu buduje istniejącą drogą aplikacji: katalog modeli AniShift (alias modelu z `config/anishift.models.jsonc`) → `palantir_llm_config` (`anishift/application/runtime.py`) z adresem enrollmentu z `UserSettings.palantir_enrollment_base_url` i tokenem Palantir czytanym tylko przez `Settings` (`ANISHIFT_PALANTIR_TOKEN` z `.env`), z `max_retries` > 0 → `LlmService`. Każda paczka to jedno `LlmService.complete(LlmRequest)`: wiadomość systemowa ze stałym poleceniem oceny (plik obok skryptu w `scripts/tmp/`) + wiadomość użytkownika z rekordami paczki w JSON; odpowiedź to JSON z listą `{id, etykieta, powód}`. Retry błędów przejściowych (429, 5xx, timeout) należy do `LlmService` — skrypt nie dodaje własnego. Skrypt sam: dzieli rekordy na paczki (do 100 + 10 kontrolnych), waliduje odpowiedź (poprawny JSON, każdy `id` paczki dokładnie raz, etykieta z trzech dozwolonych, niepusty powód) — odpowiedź niepoprawna oznacza paczkę ocenianą od nowa, najwyżej dwa razy, potem wszystkie jej rekordy trafiają na listę dla właściciela; zapisuje wynik każdej paczki od razu po odbiorze (dopisanie linii JSONL) i po przerwaniu wznawia od pierwszej niezapisanej; parsuje etykiety, liczy zgodność, obsługuje rekordy kontrolne i buduje listę dla właściciela. Dwa przebiegi z dwoma modelami różnych rodzin = dwaj oceniający. Działa lokalnie na Windows; przycięte rekordy korpusu są wcześniej kopiowane z VPS. E1 nie zmienia kodu `anishift.services.llm` ani silnika tłumaczenia; brak modelu albo trwały błąd wywołania po E00 oznacza zatrzymanie i powrót po decyzję, nie obejście w skrypcie. **Faza 0 sprawdza na 20 rekordach, że model zwraca poprawny JSON oceny.**
- **Reguły decyzji:**
  - każdy `zgodny`, który ostateczna etykieta uznaje za błędny → blocker: poprawka reguły, przypadek do testów, ponowne uruchomienie heurystyki offline na całym korpusie. **Cel: 0 błędnych `zgodnych` w całym korpusie**;
  - `niepewny` lub `niezgodny`, który ostateczna etykieta uznaje za poprawny odcinek → przypadek testowy i zadanie poprawy reguł (w E1, jeśli zmiana nie psuje żadnego `zgodnego`; inaczej w planie E2);
  - pokrycie automatu poniżej połowy odcinków TV → decyzja właściciela przed E2 (rozszerzenie reguł albo więcej ręcznych wyborów).
- **Regresja:** wszystkie rekordy, w których heurystyka była błędna albo agenci się nie zgadzali, oraz 1000 losowych rekordów z ostateczną etykietą (przycięte do pól testu) trafiają do `tests/fixtures/acquisition/identity-corpus.json` i stają się testem obok parytetu 231/231.

### N-03 — metadane z samego hasha

- **Procedura:** `scripts/tmp/magnet_probe.py` uruchamia osobny `qbittorrent.exe` z `--profile=<temp>`, `--webui-port`, `--torrenting-port` (wzorzec `workspace/.archive/acquisition/evidence/bundle/run01/probe-*.py.txt`), z włączonym DHT i domyślnymi ustawieniami sieci, zapis do katalogu tymczasowego poza repo. Dla 3 kandydatów `zgodnych` z N-02 (1 pojedynczy plik, 2 paczki): dodanie magnetu `magnet:?xt=urn:btih:<hash>&tr=<trackery z sources>` z parametrem `stopCondition=MetadataReceived`; odczyt co 1 s `torrents/info` i `torrents/files` do otrzymania listy plików; zapis czasu; ustawienie priorytetu 0 wszystkim plikom poza wskazanym (mapowanie według U-18) i priorytetu 1 wskazanemu; **bez startu**; odczyt `downloaded`, listy plików na dysku; usunięcie torrentu z `deleteFiles=true`; zatrzymanie procesu; usunięcie katalogu tymczasowego.
- **Wynik:** czas do metadanych, bajty pobrane przed zatrzymaniem, pliki utworzone na dysku, zgodność `fileIdx` z indeksem qB, czy mapowanie U-18 wskazało plik jednoznacznie.
- **Reguła decyzji:** jeśli wszystkie 3 dały listę plików, zatrzymały się bez zapisu plików treści i mapowanie było jednoznaczne → E2 używa tej sekwencji. Jeśli którakolwiek nie dała metadanych w 10 min albo zapisała treść → stop przed E2, decyzja właściciela.

### N-04 — filmy

- **Procedura:** `acquisition_probe.py movies` dla 3 filmów z franczyz z próbki: Torrentio `stream/movie/kitsu:<id>.json` i `stream/series/kitsu:<id>:1.json`.
- **Reguła decyzji:** jeśli którykolwiek wariant zwraca kandydatów dla wszystkich 3 filmów → E2 dodaje Pobierz dla filmów (plan E2 określi regułę tożsamości filmu). W przeciwnym razie U-21 zostaje odłożone.

## 10. Target design

### 10.1 Odpowiedzialności

| Element | Odpowiada za | Nie odpowiada za |
| --- | --- | --- |
| `services/catalog/anilist.py` | Zapytania AniList, parsowanie do typów katalogu | Grupowanie wpisów w UI, tożsamość wydań |
| `services/catalog/anizip.py` (NEW) | Zapytanie ani.zip po AniList ID, parsowanie odcinków i mapowań, czas ważności z `Cache-Control` | Łączenie z harmonogramem AniList |
| `services/torrents/torrentio.py` (NEW) | Zapytanie Torrentio po Kitsu ID i numerze, parsowanie strumieni do faktów surowych | Ocena tożsamości, ranking |
| `application/episode_selection.py` (NEW) | Cel odcinka, heurystyka tożsamości, fakty wydania z nazw, ranking | I/O, konfiguracja, UI |
| `application/acquisition.py` | Złożenie franczyzy, listy odcinków (ani.zip + harmonogram), oferty odcinka; pamięć odpowiedzi | Render, stan trwały |
| `application/automation.py` | Dispatch nowych pod-operacji pod limitem `requests("user")` | Logika wyboru |
| `cli/resident.py` | Metody klienta IPC | — |
| `cli/interactive/anime.py` | Stan ekranów i klawisze | Sieć w renderze |

### 10.2 Przepływ danych

```text
Anime.Query ──titles──▶ AniList.search ──▶ TitleCandidate[]
Titles(Enter) ──franchise(anilist_id)──▶ AniList relations (warstwami, id_in) ──▶ Franchise
Entries(Enter) ──episodes(anilist_id)──▶ ani.zip(anilist_id) + AniList.airing_schedule ──▶ EpisodeListing
Episodes(D, dla każdego zaznaczonego, po kolei) ──offer(anilist_id, numer)──▶
      Torrentio(kitsu_id, numer) ──▶ StreamCandidate[]
      episode_target(franchise, listing, numer) ──▶ EpisodeTarget
      assess_identity + release_facts + rank ──▶ EpisodeOffer
Offer(I) ──▶ Candidates (lokalnie, bez sieci)
```

Błędy: AniList → `TitleCatalogError` (`TITLE_CATALOG_FAILED`), ani.zip → `TitleCatalogError` z nowym kodem `EPISODE_CATALOG_FAILED`, Torrentio → `TorrentSourceError` (`TORRENT_SOURCE_FAILED`). Jedyny nowy kod błędu: `ErrorCode.EPISODE_CATALOG_FAILED` w `anishift/errors.py` (sekcja Catalog).

### 10.3 Docelowe drzewo (zmiany)

```text
anishift/
├── errors.py                                  # MODIFY: EPISODE_CATALOG_FAILED
├── bootstrap.py                               # MODIFY: wiring AniZipCatalog, TorrentioSource
├── application/
│   ├── episode_selection.py                   # NEW
│   ├── discovery.py                           # MODIFY: publiczna VIDEO_SOURCE_SUFFIXES
│   ├── acquisition.py                         # MODIFY: franchise/episodes/offer, pamięć
│   ├── automation.py                          # MODIFY: pod-operacje franchise/episodes/offer
│   ├── __init__.py                            # MODIFY: eksport nowych typów
│   └── AGENTS.md                              # MODIFY: opis episode_selection
├── services/
│   ├── http_requests.py                       # MODIFY: dostawcy anizip, torrentio
│   ├── catalog/
│   │   ├── anilist.py                         # MODIFY: franchise()
│   │   ├── anizip.py                          # NEW
│   │   ├── types.py                           # MODIFY: FranchiseEntry, Franchise, ListedEpisode, EpisodeListing
│   │   ├── __init__.py                        # MODIFY
│   │   └── AGENTS.md                          # MODIFY
│   └── torrents/
│       ├── torrentio.py                       # NEW
│       ├── types.py                           # MODIFY: StreamCandidate
│       ├── __init__.py                        # MODIFY
│       └── AGENTS.md                          # MODIFY
└── cli/
    ├── resident.py                            # MODIFY: franchise/episodes/offer
    ├── AGENTS.md                              # MODIFY: nowe ekrany Anime
    └── interactive/
        └── anime.py                           # MODIFY: ENTRIES/EPISODES/OFFER/CANDIDATES; RESULTS bez zmian pod klawiszem G
tests/
├── fixtures/
│   ├── search/manifest.json                   # MODIFY: wpisy anizip, torrentio, anilist franchise
│   ├── search/anizip__*.json                  # NEW (kopie z evidence)
│   ├── search/torrentio__*.json               # NEW (kopie z evidence)
│   ├── search/anilist__franchise__*.json      # NEW (nagrane w fazie 0)
│   └── acquisition/identity-231.json          # NEW (przycięty dataset.json)
├── application/test_episode_selection.py      # NEW
├── application/test_acquisition.py            # MODIFY
├── application/test_automation.py             # MODIFY: pod-operacje
├── services/catalog/test_anizip.py            # NEW
├── services/catalog/test_anilist.py           # MODIFY
├── services/torrents/test_torrentio.py        # NEW
├── services/test_http_requests.py             # MODIFY
├── integration/harness.py                     # MODIFY: odtwarzanie anizip/torrentio
├── integration/test_search_pipeline.py        # MODIFY: nowa ścieżka
├── integration/test_search_live.py            # MODIFY: network dla anizip/torrentio/franchise
├── cli/test_interactive_anime.py              # MODIFY
└── cli/test_resident.py                       # MODIFY
scripts/tmp/
├── acquisition_probe.py                       # NEW (jednorazowy)
└── magnet_probe.py                            # NEW (jednorazowy)
workspace/.archive/acquisition/evidence/e1/    # NEW: wyniki pomiarów (lokalnie, poza gitem)
docs/work/acquisition/outcomes/e1.md            # NEW: wynik etapu
```

### 10.4 Kontrakty danych

Wszystkie typy: `@dataclass(frozen=True, slots=True)`, kodowane przez istniejące `encode_view`/`decode_view`. Numery odcinków są `int`: tak numerują je klucze ani.zip (`"1".."n"`) i `EpisodeAiring.episode` (`catalog/types.py:34`).

**`services/catalog/types.py`**

```text
FranchiseEntry
  anilist_id: int
  romaji: str
  english: str | None
  native: str | None
  format: str | None            # AniList: TV, TV_SHORT, ONA, OVA, SPECIAL, MOVIE, MUSIC
  status: TitleStatus
  year: int | None              # seasonYear, inaczej startDate.year
  start: date | None
  relation: str                 # "SELF" dla wybranego; inaczej typ krawędzi, po której wpis dołączono
  group: EntryGroup             # StrEnum: SEASON="season", EXTRA="extra", OTHER="other" (reguła §10.5.1)

Franchise
  selected_id: int
  entries: tuple[FranchiseEntry, ...]   # kolejność: SEASON, EXTRA, OTHER (jawny indeks grupy); w grupie start rosnąco, brak daty na końcu, potem anilist_id
  complete: bool                        # False, gdy przerwano na limicie zapytań

ListedEpisode
  number: int                   # klucz lokalny ani.zip albo numer z harmonogramu AniList
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

EpisodeListing                  # wynik usługi: ani.zip + harmonogram AniList
  anilist_id: int
  kitsu_id: int | None
  catalog_type: str | None
  status: TitleStatus
  episode_count: int | None     # AniList episodes, inaczej episodeCount ani.zip
  episodes: tuple[ListedEpisode, ...]
  specials: tuple[ListedSpecial, ...]
  aired: int | None             # jedyna definicja: RELEASING → liczba odcinków z airs_at ≤ teraz; FINISHED → episode_count; inaczej None
```

**`services/torrents/types.py`**

```text
StreamCandidate
  info_hash: str                # małe litery
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

**`application/episode_selection.py`**

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

ReleaseFacts
  resolution: int | None        # §10.5.5
  polish: bool                  # 🇵🇱 w tags albo token "POL"/"Polish"/"PL" (reguła study.language)
  multisub: bool                # "Multi Subs", "MultiSub", "Multi-Subs", "Multiple Subtitle"
  platform: str | None          # "Netflix" dla NF/Netflix, "Crunchyroll" dla CR/Crunchyroll (całe tokeny)
  dub_only: bool                # "Dubbed" w tags i brak "Dual Audio"/"Multi Audio" (niezależnie od polish)
  container: str | None         # rozszerzenie file_name (małe litery, z kropką)
  supported: bool               # container ∈ VIDEO_SOURCE_SUFFIXES

RankedCandidate
  stream: StreamCandidate
  identity: IdentityAssessment
  facts: ReleaseFacts

EpisodeOffer
  key: EpisodeKey
  candidates: tuple[RankedCandidate, ...]   # zgodni wg klucza §10.5.5, potem niepewni (ten sam klucz), potem niezgodni (kolejność odpowiedzi)
  suggestion: int | None                    # indeks pierwszego zgodnego z supported=True
  checked_at: datetime
  counts: dict[str, int]                    # klucze: "match", "insufficient_evidence", "mismatch"
```

Funkcje publiczne `episode_selection.py`:

```text
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
3. Start: `$ids = [selected_id]`. Z odpowiedzi zbieramy węzły do głębokości `d`. Łańcuchem idziemy tylko krawędziami `PREQUEL` i `SEQUEL` między węzłami `type=ANIME`. Węzły dołączone krawędzią `SIDE_STORY`, `SPIN_OFF`, `ALTERNATIVE`, `SUMMARY`, `PARENT` są liśćmi (nie rozwijamy ich relacji). Inne relacje i węzły `MANGA`/`NOVEL` są pomijane (W-05).
4. Jeśli na najgłębszym poziomie są węzły łańcucha z nierozwiniętymi krawędziami `PREQUEL`/`SEQUEL`, następne zapytanie pyta o nie (`$ids` = te węzły). Łącznie najwyżej `_MAX_FRANCHISE_REQUESTS = 4` zapytania (stała, docstring: limit czasu wejścia w tytuł przy limicie AniList ~30/min); po limicie `complete=False`.
5. Grupy: `SEASON` — format TV, TV_SHORT, ONA **i** wpis w łańcuchu PREQUEL/SEQUEL (albo wybrany); `EXTRA` — OVA, SPECIAL; `OTHER` — MOVIE, MUSIC oraz TV/TV_SHORT/ONA dołączone jako liść.
6. Faza 0 potwierdza liczbę zapytań dla Slime; więcej niż 4 → warunek zatrzymania §7.

#### 10.5.2 Lista odcinków i pamięć

1. ani.zip `GET https://api.ani.zip/mappings?anilist_id=<id>`; 404 → `AniZipMapping` z pustymi listami i `kitsu_id=None` (UI: „Brak mapowania odcinków dla tego wpisu”); inne błędy → `TitleCatalogError(EPISODE_CATALOG_FAILED)`.
2. AniList `airing_schedule(id)` (istniejące). Błąd → lista z datami ani.zip i notką „Terminy emisji niedostępne”.
3. Łączenie po numerze: klucze ani.zip `"1".."n"` + numery z harmonogramu; odcinek tylko z harmonogramu ma `number` i `airs_at` (W-07).
4. `airs_at`: harmonogram AniList; brak → `airDateUtc` ani.zip; brak → None. Pola `airDate`/`airdate` nie są używane.
5. Klucze `S…` → `specials`.
6. **Pamięć w `AcquisitionService`** (jedna mapa, klucz `anilist_id` wpisu):
   - `EpisodeListing` i `Franchise` wpisu — ważne `max_age_s` sekund od pobrania odpowiedzi ani.zip; brak nagłówka → `_FALLBACK_CACHE_S = 900` (stała, docstring: wartość `Cache-Control` ani.zip zmierzona 2026-09-22).
   - `Franchise` zapisywana pod `anilist_id` **każdego** swojego wpisu; `selected_id` i `relation="SELF"` są ustawiane przy odczycie dla wpisu, o który pytano.
   - `aired` i stany odcinków liczone są przy każdej odpowiedzi z `airs_at` i bieżącego czasu, nie zapisywane w pamięci.
   - Wypieranie: najdawniej użyty wpis, gdy mapa przekroczy `_REMEMBERED_ENTRIES` (stała, docstring: limit pamięci procesu rezydenta).
   - Pamięć służy wyłącznie odczytom w E1. E2 przed zleceniem pobiera dane ponownie.
7. `offer(key)`: franczyza i lista z pamięci (pobrane, jeśli ich brak); Torrentio zawsze na żywo. Dla 12 odcinków jednego wpisu: 12 zapytań Torrentio i 0 dodatkowych zapytań AniList/ani.zip po pierwszym wejściu we wpis.

#### 10.5.3 Cel odcinka

Reguły odtwarzają `make_targets` z `workspace/.archive/acquisition/evidence/matching/prepare.py.txt`:

- `aliases` = `romaji`, `english`, `native` wybranego wpisu + te same pola pierwszego wpisu grupy `SEASON` franczyzy; bez powtórzeń i pustych; kolejność: wybrany, potem pierwszy sezon. Synonimy nie wchodzą (jak w badaniu).
- `other_series` = dla każdego wpisu dołączonego krawędzią `SPIN_OFF`: z każdego niepustego tytułu część po ostatnim `": "`.
- `kind` = `"OVA"` dla formatu OVA/SPECIAL, inaczej `"TV"`.
- `local_episode` = numer; `season`/`episode`/`absolute` z `ListedEpisode`.
- `episode_title` = `title` bez prefiksu `"Extra: "`, z odwróconym apostrofem zamienionym na `'`; `other_episode_titles` = tak samo dla pozostałych odcinków wpisu (tylko `OVA`).
- **Znana różnica wobec badania:** tylko dla `ova-1` badanie uzupełniło `season`/`episode` z listingu TVDB Sonarr, bo ani.zip ma tam `seasonNumber=None` (odcinki 1 i 2 wpisu OVA). W produkcji te pola zostają `None` (§10.5.4). `ova-4` ma w ani.zip `seasonNumber=0`, `episodeNumber=5` — tak jak w `targets.json`.

#### 10.5.4 Heurystyka

Przeniesienie funkcji `normalize`, `contains`, `episode_numbers`, `heuristic` z `workspace/.archive/acquisition/evidence/matching/prepare.py.txt` jako `assess_identity`. Podział tytułu na release/path/filename jest już w `StreamCandidate`.

Jedyna różnica: gdy `target.season is None`, pomijane są **obie** gałęzie oparte na sezonie — porównanie jawnych par `SxxEyy` i sprawdzenie numeru sezonu w ścieżce (`season_matches`). Bez tego każde `S00Exx` albo `S01` w ścieżce paczki dawałoby `mismatch` dla wpisu bez numeracji TVDB.

Parytet 231/231 liczony jest na zamrożonych celach z `targets.json` (tam `season` nigdy nie jest `None`), więc różnica nie wpływa na parytet.

#### 10.5.5 Fakty i ranking

- `release_facts` czyta tokeny z `release`, `path`, `file_name` i `tags` (wzorce: `workspace/.archive/acquisition/evidence/ranking/pilot.py.txt:34–55`, `workspace/.archive/acquisition/evidence/polish/study.py.txt:36–61`).
- **Rozdzielczość** (reguła badania): zebrać wszystkie wysokości z tekstów — `(\d{3,4})p`, `(\d{3,4})x(\d{3,4})` (druga liczba), `4K` → 2160 — ograniczone do {360, 480, 576, 720, 1080, 1440, 2160}; dokładnie jedna różna wartość → ta wartość; zero albo kilka różnych → `None`.
- **Obsługiwane kontenery:** `VIDEO_SOURCE_SUFFIXES` — nowa publiczna stała w `application/discovery.py` wyliczona z `_PRIMARY_SOURCE_KINDS` (rodzaje `VIDEO_*`, dziś `.mkv`, `.mp4`); bez kopiowania listy.
- **Klucz sortowania** (rosnąco; realizuje U-04, U-05, U-06, U-23):

```text
(
  not facts.supported,                  # U-06
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
- **Starszy rezydent** (sprzed E1) odpowie na te pod-operacje `refused(INTERNAL, …, "command_failed")`. Panel na odmowę `INTERNAL` dla `franchise`/`episodes`/`offer` pokazuje: „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” Bez osobnego mechanizmu wykrywania wersji.

### 10.7 Zachowanie UI

Pełne makiety, teksty i klawisze: [../ux.md](../ux.md) §3–§6, §11, §12. Najważniejsze reguły dla E1:

- Ekrany: QUERY → TITLES → ENTRIES → EPISODES → OFFER → CANDIDATES; BUSY i PROBLEM jak dziś. Z TITLES klawisz `G` otwiera dotychczasowy RESULTS (bez zmian) — pomost usuwany w E3.
- Esc wraca o jeden ekran i odtwarza kursor i zaznaczenia; nie wykonuje sieci, gdy dane są w pamięci kontrolera.
- `D` na EPISODES bez zaznaczeń używa podświetlonego odcinka.
- OFFER nie ma akcji „Pobierz” w E1; stopka: „Enter/I inne wydania · Esc odcinki”.
- `O` i `P` na EPISODES nie są obsługiwane w E1 (brak w stopce).
- Każdy wynik wątku sieciowego sprawdza generację; spóźniony wynik jest porzucany.

### 10.8 Edge cases

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| Tytuł bez wpisu ani.zip (404) | ENTRIES działa; EPISODES: „Brak mapowania odcinków dla tego wpisu”; `D` niedostępne | unit + integration |
| Przyszły wpis z pustą listą ani.zip, harmonogram z 12 numerami | 12 odcinków z datami, stan „Nie wyemitowano” | unit |
| Sprzeczne `airDate`/`airdate` | Ignorowane; użyte `airs_at` z AniList | unit |
| Torrentio 0 kandydatów | „Brak kandydatów w źródle (sprawdzono HH:MM)” | unit |
| Kandydat bez `fileIdx` | Ocena tożsamości po nazwie wydania i ścieżce; brak indeksu pokazany w szczegółach | unit |
| Ten sam hash dla kilku odcinków | Osobne oceny per odcinek | unit (EMBER idx 3/28/25) |
| `Dubbed` bez `Dual Audio` | Za wszystkimi innymi zgodnymi | unit |
| 1440×1080 | Klasa 1080 | unit |
| `.avi`, `.ts` | `supported=False`, nigdy sugestia | unit |
| Brak seedów | „?” i koniec kolejności przy remisie | unit |
| AniList 429 | Istniejące ochłodzenie `RequestControl`; komunikat z czasem następnej próby | unit (MockTransport) |
| Rezydent w starszej wersji (odmowa `INTERNAL` na `offer`) | Komunikat „Rezydent nie wykonał polecenia. Jeśli AniShift był właśnie aktualizowany, uruchom go ponownie.” | unit (kontroler z fałszywą sesją zwracającą odmowę) |
| Esc w trakcie `offer` dla 12 odcinków | Kolejne zapytania nie są wysyłane; spóźnione odpowiedzi porzucane | unit (kontroler z fałszywą usługą) |

## 11. Plan wykonania

Wykonawca kodu: subagent `astra` (brief według `.agents/skills/subagent/assets/SUBAGENT-BRIEF.template.md`). Review: świeży `opus5` po fazach 2, 4 i na końcu. Orkiestrator integruje i sprawdza dowody.

### Faza 0 — Preflight

**Cel:** czysty punkt startu i odpowiedź na pytanie o relacje AniList.

1. `git status`, `git log -3`; utworzyć gałąź `work/acquisition/01-episode-selection` (wzorzec gałęzi repo `work/<obszar>/<nn>-<slug>`) od bieżącego HEAD `work/local-automation/06-efficiency`, który sam nie jest jeszcze scalony z `main` (dokumenty w `docs/work/` pozostają nieśledzone — nie dodawać ich do commitów kodu bez zlecenia).
2. Uruchomić bramki z `AGENTS.md`; zapisać wynik (liczby passed/failed/skipped, nazwy failures) w `outcomes/e1.md` jako baseline.
3. Jedno zapytanie AniList (Slime S1, `id=101280`) z zagnieżdżeniem relacji 3, potem 2, potem 1; zapisać, która głębokość przechodzi bez błędu złożoności. Nagrać wszystkie warstwy franczyzy jako `tests/fixtures/search/anilist__franchise__101280.json` i analogicznie dla Solo Leveling (`id=151807`, istniejące fixture) oraz Haibane Renmei (`anilist_id` z `mappings` w `workspace/.archive/acquisition/evidence/sources/metadata/haibane.raw.json`).
4. Skopiować fixture z `workspace/.archive/acquisition/evidence/sources/metadata/` (slime-s1, slime-s4, slime-ova, haibane) jako `tests/fixtures/search/anizip__<anilist_id>.json` i z `workspace/.archive/acquisition/evidence/sources/releases/` oraz `workspace/.archive/acquisition/evidence/sources/ova/` jako `tests/fixtures/search/torrentio__kitsu-<id>-<n>.json`; dopisać do `manifest.json` (klucze `anizip`, `torrentio`, `anilist_franchise`).
5a. Próba oceniającego (wymaga zakończonego E00): 20 rekordów z `identity-231.json` przez `anishift.services.llm` (silnik Palantir, dwa modele różnych rodzin z katalogu po E00) z poleceniem oceny (§9 N-02, „Mechanizm”); zapisać, czy odpowiedź przechodzi walidację JSON skryptu i czy etykiety zgadzają się ze znanymi.
5. Przyciąć `workspace/.archive/acquisition/evidence/matching/dataset.json` do pól `id`, `state.target`, `state.candidate`, `heuristic.decision` → `tests/fixtures/acquisition/identity-231.json`; sprawdzić rozmiar < 500 KiB.

**Kontrola:** bramki uruchomione; 3 nowe fixture AniList; fixture ani.zip/Torrentio z sumami SHA-256 zgodnymi z `workspace/.archive/acquisition/evidence/manifest.json`.

**Gate:** znana głębokość relacji; baseline zapisany.

### Faza 1 — Czysta domena

**Cel:** `episode_selection.py` z parytetem heurystyki i rankingiem.

**Pliki:** `anishift/application/episode_selection.py` (NEW), `anishift/application/discovery.py` (`VIDEO_SOURCE_SUFFIXES`), `anishift/services/torrents/types.py` (`StreamCandidate`), `anishift/services/catalog/types.py` (typy z §10.4), `tests/application/test_episode_selection.py` (NEW), `anishift/application/__init__.py`.

**Działania:**
1. Typy z §10.4.
2. `assess_identity` jako port §10.5.4.
3. `release_facts`, `rank_candidates` według §10.5.5.
4. `episode_target` według §10.5.3.

**Inwarianty:** brak importów I/O, `httpx`, `config`, `cli` w `episode_selection.py` (test architektury w `tests/application/test_architecture.py` — dopisać moduł do listy czystych, jeśli taka lista istnieje).

**Testy (nazwy opisują zachowanie, bez prozy):**
- parytet: 231 rekordów `identity-231.json` → te same decyzje;
- dwa znane fałszywe odrzucenia (`slime-s1e4:33`, `bebop-e1:33`) nadal `insufficient_evidence`/`mismatch` jak w badaniu (parytet, nie poprawka);
- `season=None` + `S00E02` w nazwie i `S01` w ścieżce → nie `mismatch` z powodu pary ani sezonu;
- ranking: 1080p bez PL przed 720p z PL; 2160p przed 720p; 720p przed 480p; w 1080p: PL przed MultiSub, MultiSub przed NF bez MultiSub, NF przed wydaniem bez oznaczeń; 1440×1080 = 1080; `Dubbed` bez `Dual Audio` za 480p bez dubbingu; `.avi` nigdy sugestią; brak seedów (`None`) za każdą znaną liczbą, także za 0;
- ten sam hash z różnymi `file_index` oceniany osobno.

**Kontrola:** `uv run pytest tests/application/test_episode_selection.py`; ruff/mypy na całym `anishift/ tests/`.

**Gate:** parytet 231/231.

### Faza 2 — Adaptery

**Cel:** ani.zip, Torrentio, franczyza AniList, dostawcy w `RequestControl`.

**Pliki:** `anishift/services/catalog/anizip.py` (NEW), `anishift/services/catalog/anilist.py`, `anishift/services/catalog/__init__.py`, `anishift/services/torrents/torrentio.py` (NEW), `anishift/services/torrents/__init__.py`, `anishift/services/http_requests.py`, `anishift/errors.py`, testy: `tests/services/catalog/test_anizip.py` (NEW), `tests/services/torrents/test_torrentio.py` (NEW), `tests/services/catalog/test_anilist.py`, `tests/services/test_http_requests.py`, `tests/integration/test_search_live.py`.

**Działania:**
1. `AniZipCatalog(http)` z metodą `mapping(anilist_id: int) -> AniZipMapping`; parsowanie §10.5.2 pkt 1 i 5; `max_age_s` z `Cache-Control`.
2. `TorrentioSource(http)` z metodą `streams(kitsu_id: int, number: int) -> tuple[StreamCandidate, ...]`; URL `https://torrentio.strem.fun/stream/series/kitsu:{kitsu_id}:{number}.json`; parsowanie linii `title` (§6.4).
3. `AniListCatalog.franchise(anilist_id) -> Franchise` według §10.5.1.
4. `_provider()` w `http_requests.py`: host `api.ani.zip` → `anizip`, `torrentio.strem.fun` → `torrentio`.
5. `ErrorCode.EPISODE_CATALOG_FAILED`.
6. Logowanie granic: jedno `logger.info` na zakończone zapytanie (dostawca, operacja, liczba elementów, czas), `logger.warning` na błąd (dostawca, kod) — bez URL z tytułami, bez treści.
7. Testy `network` (pomijane domyślnie): ani.zip dla Slime S1, Torrentio `kitsu:41024:4`, franczyza Slime.

**Kontrola:** testy adapterów na fixture; `uv run pytest -m network tests/integration/test_search_live.py` wykonane ręcznie raz (wynik do outcome).

**Gate:** review `opus5` faz 1–2 (read-only): kontrakty z §10.4, parytet, parsowanie; findingi krytyczne/poważne poprawione.

### Faza 3 — Start pomiarów N-01, N-02, N-04

**Cel:** uruchomić 7-dniowy pomiar jak najwcześniej.

**Pliki:** `scripts/tmp/acquisition_probe.py` (NEW). Używa adapterów z fazy 2 i `episode_selection` przez import pakietu `anishift`; własny `httpx.Client` z `RequestControl`; zapis do `workspace/.archive/acquisition/evidence/e1/`.

**Działania:** podkomendy `freshness`, `corpus`, `movies` według §9. Start `freshness` na VPS właściciela (albo w jego terminalu; skrypt drukuje, jak go wznowić). `movies` wykonać od razu; `corpus` uruchomić po `movies` (od wyniku N-04 zależy, czy filmy są w korpusie odcinkowym).

**Kontrola:** pierwsze wpisy JSONL; brak wyjątków w pierwszej godzinie.

**Gate:** zgoda właściciela na uruchomienie (manifest §4).

### Faza 4 — Usługa, IPC, wiring

**Pliki:** `anishift/application/acquisition.py`, `anishift/application/automation.py`, `anishift/cli/resident.py`, `anishift/bootstrap.py`, `anishift/application/__init__.py`; testy: `tests/application/test_acquisition.py`, `tests/application/test_automation.py`, `tests/cli/test_resident.py`, `tests/integration/harness.py`, `tests/integration/test_search_pipeline.py`.

**Działania:**
1. `AcquisitionService.__init__` przyjmuje `episode_catalog: EpisodeCatalog | None` i `stream_source: StreamSource | None`; franczyzę bierze z istniejącego `title_catalog`, którego protokół rozszerza się o `FranchiseCatalog.franchise` (§10.4).
2. Metody: `franchise(anilist_id)`, `episodes(anilist_id)`, `offer(key: EpisodeKey)`; pamięć i zachowanie według §10.5.2 pkt 6–7.
3. `_acquisition_command`: gałęzie `franchise`, `episodes`, `offer` przed dekodowaniem `candidate`.
4. `ResidentSession.franchise/episodes/offer`.
5. `bootstrap._acquisition_service` tworzy oba adaptery na wspólnym `httpx.Client` z `RequestControl`.
6. Harness integracyjny odtwarza `anizip__*`, `torrentio__*`, `anilist__franchise__*`.

**Testy:**
- Slime: franczyza zawiera S1, S2 (obie części), S3, S4 w `SEASON`, OVA w `EXTRA`, Slime Diaries w `OTHER`.
- `episode_target` zbudowany z nagranych fixture'ów dla `slime-s1e4`, `slime-s4e23`, `slime-s4e10`, `haibane-e1` ma pola równe `targets.json`; dla `ova-4` równe we wszystkich polach; dla `ova-1` równe z wyjątkiem `season`/`episode` = `None` (różnica z §10.5.3).
- S1E4 → sugestia zgodna; Slime Diaries i OAD nie są zgodne.
- 12 × `offer` dla jednego wpisu → 12 zapytań Torrentio i 0 dodatkowych zapytań AniList/ani.zip po `episodes` (licznik w harnessie).
- Dispatcher: `offer` bez pola `candidate` zwraca `EpisodeOffer`, nie odmowę.

**Gate:** testy zielone.

### Faza 5 — UI

**Pliki:** `anishift/cli/interactive/anime.py`, `anishift/cli/AGENTS.md`, `tests/cli/test_interactive_anime.py`. `state.py` bez zmian (stara droga nadal produkuje szkic subskrypcji).

**Działania:**
1. Ekrany ENTRIES, EPISODES, OFFER, CANDIDATES według ux.md §4–§6.
2. Po Enter na tytule — nowa droga (ENTRIES). Klawisz `G` na TITLES otwiera dotychczasową drogę `search_title` → RESULTS bez żadnej zmiany jej zachowania (`D`, `O`, `S`, `F`, zakres). Stopka TITLES: „Enter wybierz · G wydania wg grup (stara wersja) · / szukaj · Esc wróć”.
2b. CANDIDATES (U-24): pokazuje 1080p, 2160p i nieznaną rozdzielczość; 720p i niższe tylko, gdy nie ma żadnego zgodnego 1080p/2160p.
2a. Wpis-film w ENTRIES: Enter otwiera EPISODES z jednym wierszem „Film” i notką „Pobieranie filmów zależy od pomiaru E1”; `D` na nim otwiera podgląd tylko wtedy, gdy `kitsu_id` jest znane (zapytanie `kitsu:<id>:1`), inaczej notka „Brak mapowania”.
3. `_PROBLEM_TEXTS`: `TORRENT_SOURCE_FAILED` → „Źródło wydań nie odpowiada”, `EPISODE_CATALOG_FAILED` → „Lista odcinków niedostępna”.
4. Zakres `Z`: lista `1,3,9-12` i „od N” (`5-`); tylko liczby całkowite; nieznany numer → notka „Brak odcinka 30 w tym wpisie”.

**Testy:** przejścia i Esc na każdym ekranie; `G` otwiera starą drogę — jej istniejące testy zmieniają tylko klawisz wejścia z Enter na `G`; odmowa `INTERNAL` na `offer` daje komunikat o restarcie; `D` bez zaznaczeń; zaznaczenie 1 i 3 bez 2; `Z` z listą; Esc w trakcie `offer`; spóźniony wynik po Esc; litery w TextInput nie są skrótami; wąski terminal (≤ 50 kolumn) bez nakładania; render bez wywołań usługi (fałszywa usługa licząca wywołania).

**Kontrola:** pełne bramki.

**Gate:** review `opus5` fazy 4–5.

### Faza 6 — Próba N-03

**Pliki:** `scripts/tmp/magnet_probe.py` (NEW), wynik w `evidence/e1/magnet/`.

**Działania:** §9 N-03, lokalnie na Windows właściciela (nie na VPS). Binarka qBittorrent: ta, której używa AniShift (`external/` albo ścieżka z `platform/binaries.py`); profil i dane wyłącznie w `%TEMP%`; porty losowe wolne; po próbie weryfikacja: proces nie istnieje, port nie nasłuchuje, katalog usunięty.

**Gate:** zgoda właściciela (manifest §4); wynik zapisany.

### Faza 7 — H1, wynik etapu, review końcowe

1. Po zakończeniu `freshness` (7 dni) i `corpus`: analiza N-01 według reguły; N-02: metryki, ocena całego korpusu przez agentów, lista dla właściciela, poprawki reguł i ponowne uruchomienie według §9; N-04.
2. H1 z właścicielem (ux.md §12): scenariusz, wynik, uwagi. Uwagi o wyglądzie → poprawka UI w tej fazie; uwagi o znaczeniu → spec.
3. `outcomes/e1.md` według kontraktu §16.
4. Świeży `opus5` review całości (kod + outcome) → poprawki → weryfikacja.
5. Commit(y) w formacie `typ(scope): opis` (scope z `scripts/hooks/check_commit_msg.py`), PR piętrowy na `work/local-automation/06-efficiency` — tylko na zlecenie właściciela.

## 12. Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
| --- | --- | --- |
| Heurystyka jak w badaniu | Parytet 231/231 | Pełny zbiór badania |
| Ranking według spec | Testy przypadków granicznych | Każda reguła U-04/05/06/23 ma przypadek rozróżniający |
| Parsowanie ani.zip/Torrentio | Fixture z badań + 1 test `network` | Rzeczywiste odpowiedzi |
| Franczyza | Fixture nagrane w fazie 0 | Rzeczywiste odpowiedzi 3 franczyz |
| IPC | `test_automation.py`, `test_resident.py` | Strict encode/decode |
| UI | `test_interactive_anime.py` + H1 | Mechanika + ocena człowieka |
| Brak regresji | Pełne bramki | Obowiązek `AGENTS.md` |
| N-01–N-04 | Skrypty + surowe dane w `evidence/e1/` | Odtwarzalność |

### Bramki

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

### Obowiązki regresyjne

PR-06 (cztery zakładki, marka), PR-01 (panel odłącza się bez zatrzymania pracy), istniejące testy subskrypcji i pobierania z warstwy aplikacji (nieużywane przez nowe UI, ale nadal działające).

### Odbiór człowieka — H1

Pełny scenariusz: [../ux.md](../ux.md) §12, H1. Warunek PASS: właściciel dochodzi do właściwego odcinka (w tym Slime S1E4) w ≤ 3 wyborach od wpisania nazwy dla 10 swoich tytułów i uznaje sugestie za sensowne albo wskazuje konkretny błąd.

## 13. Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Eskalacja |
| --- | --- | --- | --- |
| Limit złożoności AniList | Faza 0 | Mniejsza głębokość, więcej warstw | > 4 zapytań dla Slime |
| Zmiana formatu Torrentio | Test `network` | Aktualizacja parsera + fixture | Brak pól `infoHash` |
| Pomiar przerwany (komputer wyłączony) | Luki w JSONL | Wznowienie; brakujące odcinki dopisane jako niezmierzone | < 5 odcinków zmierzonych → przedłużenie o 7 dni |
| Za dużo `niepewnych` | N-02 (korpus 2000) | Przypadki do planu E2 | Pokrycie automatu < połowy odcinków TV → decyzja właściciela przed E2 |
| Korpus przekracza limit Torrentio | 429 w trakcie zbierania | Wstrzymanie i wznowienie następnej doby; skrypt wznawia się od miejsca przerwania | Brak postępu przez 2 doby |
| Stary rezydent po aktualizacji | Test IPC | Komunikat restartu | — |

## 14. Lokalna adaptacja

Wolno: nazwy prywatne, podział helperów, teksty zgodne znaczeniowo z ux.md, głębokość relacji, stałe limitów pamięci, dokładne nazwy plików fixture.

## 15. Materialna zmiana — zatrzymanie

Zmiana typów publicznych z §10.4, nowy magazyn danych, zapis stanu trwałego, nowa zależność, zmiana wersji protokołu, zmiana reguł rankingu lub heurystyki poza portem — wymagają powrotu do orkiestratora i aktualizacji planu.

## 16. Definition of Done i kontrakt wyniku

- [ ] warunki §3 spełnione;
- [ ] bramki zielone z liczbami w outcome;
- [ ] zakres i zakazy zachowane (diff sprawdzony przez orkiestratora);
- [ ] H1 wykonane;
- [ ] N-01–N-04 z decyzjami;
- [ ] review `opus5` rozliczone.

`outcomes/e1.md` zawiera: status; zmienione pliki; wyniki bramek (liczby); parytet; wyniki N-01–N-04 z liczbami i decyzjami według §9; wynik H1 i uwagi; odchylenia od planu; znane ograniczenia; stan Git (gałąź, commity); rekomendowany zakres planu E2.
