---
kind: masterplan
status: active
updated: 2026-09-28
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# Masterplan: wspólne pobieranie i subskrypcje anime

## Cel końcowy

Użytkownik wybiera w AniShift tytuł → sezon → odcinki i klika Pobierz albo Subskrybuj. Właściwe pliki pobierają się same, przechodzą przez istniejące przetwarzanie i lądują w Bibliotece. Subskrypcje działają tydzień po tygodniu bez dotykania aplikacji i same znikają po sezonie. Kontrakt: [spec.md](spec.md). Ekrany i klawisze: [ux.md](ux.md).

## Źródła celu i ograniczeń

- [spec.md](spec.md) — co ma być prawdą (U-, W-, R-, P-, S-, M-, Q-, I-, PR-).
- [ux.md](ux.md) — makiety, przejścia, klawisze, scenariusze odbioru H1–H4.
- [plans/e1-wybor-odcinka.md](plans/e1-wybor-odcinka.md) — szczegółowy plan etapu E1; fazy 3–9 wykonuje [plans/e1-integracja.md](plans/e1-integracja.md).
- Skill OpenCode (`agents/skills/opencode/`: `assets/opencode.jsonc`, `references/models.md`, `references/foundry-proxy.md`, `references/configuration.md`) — kanoniczne źródło modeli i reguł wywołań proxy dla E00.
- `AGENTS.md` (root i scoped) — reguły repozytorium, bramki jakości, zakazy.
- Badania: `research/summary.md`, `research/anime-api-report.md`, `research/*.md`, `workspace/.archive/acquisition/evidence/`.

## Aktualny zaakceptowany stan

- **Działa i zostaje:** rezydent i jeden właściciel stanu, prywatny qBittorrent, graf przetwarzania, Biblioteka/Kosz/Ctrl+Z, Historia, Ręczny, Ustawienia, przetwarzanie plików z workspace.
- **Działa, ale zostanie zastąpione:** zakładka Anime z wyborem grupy (Nyaa), subskrypcje przypięte do grupy.
- **Nie działa:** subskrypcje (8 potwierdzonych mechanizmów zatrzymania, spec §3.2); pobieranie wybranych plików z paczki; reguła PL/MultiSub/1080p.
- **Potwierdzone badaniami, nie w kodzie:** łańcuch AniList → ani.zip → Torrentio, heurystyka tożsamości, wybór plików w qB (na pliku .torrent).
- **Silnik LLM (`anishift.services.llm`):** po E00 (PR #57) — pliki (obraz, PDF, audio, wideo) w każdym silniku; lista 22 modeli Palantira w `engines/palantir/constants.py` (katalog aplikacji to jej projekcja, bez pliku JSONC); OpenAI przez `/responses` z wariantami rozumowania; mechanizm drugiego konta w serwisie (odczyt tokena 2 z `.env` — osobny krok); próby na żywo 182/182 ([outcomes/e00.md](outcomes/e00.md)).
- **Niepewne:** metadane z samego hasha (N-03), opóźnienie Torrentio dla premier (N-01 rozstrzygnięty pilotem historycznym, U-02; potwierdzenie z rejestru po integracji), heurystyka na korpusie ≥ 2000 tytułów (N-02), filmy (N-04).
- **Blokery:** brak.
- **Znany błąd poza etapami:** dla „4th Season” (AniList `182205`) ranking panelu uznaje S04E23 za inny sezon, a S03E23 za właściwy; `ResidentSession.season_context()` zwraca przy tym `offset=48` (wykryte 2026-09-24). Jawny sezon jest porównywany z `context.index`, a offset służy numeracji absolutnej (`anishift/application/acquisition.py:read_episode`, linie 313–320); sam offset 48 nie wyjaśnia odrzucenia S04E23. Dokładnej odpowiedzi AniList powodującej błędny kontekst nie odtworzono. Decyzja właściciela 2026-09-24: E1 omija stary kalkulator w nowej drodze; starej drogi pod `G` nie naprawiamy osobno, bo jej UI znika w E3, a stare zaplecze w E5.

## Etapy

| Nr | Etap | Rezultat | Zależności | Warunek wyjścia | Status |
| --- | --- | --- | --- | --- | --- |
| E0 | Pakiet decyzyjny | Specyfikacja, masterplan, plan E1 i UX bez sprzeczności; ustalenia `inżynierska` zaakceptowane lub zawetowane | — | Właściciel akceptuje pakiet (lista weta w manifeście) i zgody na pomiary E1 | accepted |
| E00 | Katalog modeli i wywołania zgodne z OpenCode | Silnik LLM AniShift zna wszystkie modele OpenCode z limitami, modalnościami i wariantami rozumowania; katalog nadąża za kanonicznym `opencode.jsonc` jedną drogą; każdy model odpowiada przez obecne proxy; obrazy i PDF trafiają do modeli, które je deklarują, pozostałe jawnie odmawiają; decyzja o dwóch enrollmentach podjęta w planie E00 | E0; osobny plan E00 zaakceptowany przez właściciela | Bramki zielone; katalog zgodny z kanonicznym plikiem; smoke request na każdym modelu (obraz i PDF tam, gdzie deklarowane) zaliczony; review `opus5` bez otwartych findingów krytycznych i poważnych | accepted |
| E1 | Wybór odcinka na prawdziwych danych + pomiary | Najpierw oznaczony korpus ≥ 2000 tytułów / ≥ 10 000 rekordów, zamrożony podział i heurystyka zbudowana od zera na części roboczej; po egzaminie kod domeny, adaptery, usługa/IPC i nowa ścieżka Anime: tytuł → wpisy → odcinki → sugestia i inne wydania (bez pobierania). Stara lista wydań wg grup pod `G` zachowuje pobieranie i subskrypcje. Ranking właściciela bez zmian; pilot N-01 (decyzja U-02) i raport N-02–N-04 | E0, E00 (oceniający korpusu N-02 działają przez silnik LLM po E00) | Heurystyka zbudowana na korpusie ≥ 2000 tytułów / ≥ 10 000 rekordów; jednorazowy egzamin na niewidzianej odłożonej części: 0 błędnych `zgodnych` rozpoznawalnych z nazwy/metadanych (plan E1 D6); metryki `niepewnych` i błędnych `niezgodnych` per warstwa zaakceptowane przez właściciela. Testy oznaczonych fixture i bramki zielone; H1 zaliczone; raport pomiarów z decyzjami dla E2 i E3. Stan 2026-09-28: egzamin 2 (v10.3) PASS, v10.3 przyjęta; integracja według [plans/e1-integracja.md](plans/e1-integracja.md) | current |
| E2 | Jednorazowe pobieranie nową drogą | Pobierz z listy odcinków: zlecenie per odcinek, magnet → lista plików → tylko wybrane pliki → kompletność per odcinek → istniejące przetwarzanie → Biblioteka. Pobierz ponownie z podglądem wydania (spec P-05). Rejestr decyzji ścieżki ręcznej (`config/watch/decisions.jsonl`, [plan przepływu](plans/e1-przeplyw-subskrypcji.md) §5.6). Pomost `G` (stara lista wg grup) usunięty z zakładki Anime decyzją D5 ([plan panelu](plans/e2-panel-anime.md)); istniejące subskrypcje działają dalej w swojej zakładce, nowe zakłada się w E3 | E1 (N-03 pozytywne) | Test integracyjny z prawdziwym qB na syntetyku (E1/E3 bez E2, restart); migracja WatchState na kopii stanu właściciela; H2 zaliczone | pending-human ([outcome](outcomes/e2.md)) |
| E3 | Subskrypcje na wspólnym mechanizmie | Subskrybuj z listy odcinków, zakładka Subskrypcje (lista, szczegóły, dodaj, usuń, wstrzymaj, szukaj teraz), harmonogram U-13–U-15, autozamknięcie, przeniesienie starych subskrypcji; usunięty pomost `G` i stara droga grup w UI | E2; źródło świeżych odcinków rozstrzygnięte (U-02: tylko Torrentio) | Testy fake clock (emisja, brak wydania, koniec sezonu, restart, izolacja problemów); migracja na kopii; H3: tydzień bez dotykania | planned |
| E4 | Kontrola zawartości po pobraniu | PL napisy → bez tłumaczenia; obce → tłumaczenie; brak napisów → jedna zamiana wydania; lektor zawsze | E2; N-05 | Testy planera na syntetykach; H4 na prawdziwym odcinku z PL i bez PL | planned |
| E5 | Sprzątanie i przełączenie | Usunięte martwe ścieżki (grupy, kategorie, aktywne wyszukiwanie Nyaa — U-02; fallback W-08 według osobnej decyzji), aktualne `AGENTS.md`/`README.md`, PR-y scalone, nowa wersja działa u właściciela | E3, E4 | Pełne bramki, niezależne review implementacji, działający rezydent u właściciela przez 7 dni bez interwencji | planned |
| E6 | Biblioteka jako widok tytułów | Biblioteka w układzie ekranu Anime: lista tytułów → Enter → `BIBLIOTEKA › <tytuł>` z odcinkami (numer, tytuł odcinka, Emisja, Stan); zaznaczanie i usuwanie wielu; rozpoznanie plików ręcznych przez AniList z jawnym „nie rozpoznano” | E2; E3 (nadchodzące odcinki subskrypcji); osobny plan zaakceptowany przez właściciela | Szczegóły w „Stany etapów” E6; H6 właściciela na własnej Bibliotece | planned |

Gałąź i PR E00 ustala jego plan; E1 startuje od stanu po E00 (nie od samego `0e8a6bf`).

Gałęzie: `work/local-automation/06-efficiency` scalono do `main` przez PR #56 (2026-09-23, merge `c58392a`); E1 startuje od stanu po E00: `work/acquisition/00-model-catalog-v2` na `bde35d7`. Gałęzie etapów według wzorca repo `work/acquisition/<nn>-<slug>`. Scalanie: E1, E2 i E3 to osobne, piętrowe PR-y. Do `main` trafiają razem po akceptacji E3, bo dopiero wtedy nowa droga ma i pobieranie, i subskrypcje (inaczej `main` traciłby jedną z nich). E4 i E5 to osobne PR-y po nich.

## Aktualny etap

**Stan 2026-10-02:** E2 wykonane na `work/acquisition/02-download`, czeka na ludzkie H2 ([outcomes/e2.md](outcomes/e2.md)); po nim audyt i plan refaktoryzacji ([petla-wykonania.md](petla-wykonania.md) etap 5), potem plan E3. Poniższy opis E1 jest historyczny.

**Etap:** E1 — wybór odcinka na prawdziwych danych i pomiary. E0 zaakceptowane zgodnie z [README.md](README.md) §2; E00 zakończone (kod zaakceptowany, PR #57 czeka na merge).

**Następny krok:** konsensus przeglądów astra ↔ opus55 nad [planem integracji](plans/e1-integracja.md), commit zaakceptowanej dokumentacji (ten commit jest baseline wykonania), potem fazy tego planu na `work/acquisition/01-episode-selection`: F0 preflight (baseline, SHA zamrożonych skryptów, bramki) → F1 port H1 + bramka A → F2 kontrakty i czyste funkcje (`identity_target` = `project_title`, wejście H1 bez dowodów) → F3 adaptery ani.zip/Torrentio/franczyza + bramka B → F4 usługa, IPC, limit ramki, pomiar czasu → F5 UI Anime → F6 H1 z właścicielem, `outcomes/e1.md`, review końcowe. Korpus, podział i egzamin są zamknięte (egzamin 2 PASS).

**Dlaczego E00 przed E1:** E1 ocenia korpus N-02 modelami przez silnik LLM AniShift. Właściciel wymaga, by ten silnik najpierw znał aktualne modele i aktualną specyfikację wywołań; inaczej ocena korpusu biegłaby na nieaktualnym katalogu i niepotwierdzonej drodze do modeli OpenAI.

**Dlaczego E1 jako pierwszy etap pobierania:** usuwa największe niewiadome tanio i bez skutków. Pokazuje prawdziwe dane w prawdziwym panelu (zamiast makiety do wyrzucenia), więc właściciel ocenia UX na swoich tytułach przed kosztowną pracą nad pobieraniem i migracją. Jeśli N-03 wypadnie źle, cały sposób pobierania z Torrentio trzeba przemyśleć — lepiej wiedzieć to przed E2.

**Największa niewiadoma:** N-03 — czy qBittorrent pobierze listę plików z samego hasha i pozwoli wybrać pliki przed zapisem treści.

**Następny artefakt:** zaakceptowany plan integracji E1; potem wynik E1 (`outcomes/e1.md`) i plan E2 napisany na stanie po E1.

## Stany etapów

### E00 — katalog modeli i wywołania zgodne z OpenCode

- **Cel:** silnik LLM AniShift (`anishift.services.llm`, silnik Palantir) ma aktualny zestaw modeli i woła je tak, jak dziś wymaga proxy — zgodnie 1:1 ze skillem OpenCode.
- **Dlaczego teraz:** decyzja właściciela 2026-09-23: modele ciągle się dodają i katalog ma być na bieżąco; zmieniła się specyfikacja wywołań; modele są multimodalne (obrazy, PDF). E1 (N-02) potrzebuje działającego silnika z aktualnymi modelami.
- **Wejście:** zaakceptowany E0; **osobny szczegółowy plan E00 zaakceptowany przez właściciela** (powstaje przed rozpoczęciem pracy, na aktualnym baseline); kanoniczny `opencode.jsonc` na maszynie właściciela; token Palantir w `.env`.
- **Rezultat (stan po):**
  - (a) katalog AniShift zawiera wszystkie modele OpenCode z limitami, modalnościami wejścia i wariantami rozumowania; zmiana schematu katalogu ma migrację (`schema_version`);
  - (b) utrzymanie „na bieżąco” jedną drogą: katalog wynika z kanonicznego `opencode.jsonc` z zachowaniem domyślnych ról AniShift i czytelnym raportem dodanych i usuniętych modeli; plan E00 rozstrzyga, czy to polecenie synchronizacji, czy odczyt przy starcie;
  - (c) wywołania zgodne z obecnym proxy według `references/foundry-proxy.md` (droga OpenAI potwierdzona smoke requestem, reguły Gemini i xAI, brak odsyłania zaszyfrowanego reasoning);
  - (d) obrazy i PDF przekazywane w żądaniu modelom, które je deklarują; dla pozostałych jawna odmowa przed wysłaniem — wyłącznie w silniku LLM, bez nowych funkcji produktu;
  - (e) wybór wariantu rozumowania per model;
  - (f) dwa enrollmenty z failoverem jak w skillu OpenCode — zrobione albo świadomie odłożone z uzasadnieniem w planie E00.
- **Nie zawiera:** nowych funkcji produktu korzystających z obrazów lub PDF, zmian w tłumaczeniu poza tym, co wymusza zmiana silnika, zmian plików skilla OpenCode.
- **Warunek wyjścia:** bramki z `AGENTS.md` zielone; testy bez sieci; katalog zgodny z kanonicznym plikiem, a raport różnic pusty; po jednym realnym smoke requeście na każdy model (z obrazem i PDF tam, gdzie deklarowane); review `opus5` bez otwartych findingów krytycznych i poważnych.
- **Ryzyko:** proxy zachowuje się inaczej, niż opisuje skill — rozstrzyga smoke request, nie założenie; migracja schematu łamie ręcznie edytowany katalog właściciela — plan E00 pokazuje ją na kopii; zakres rośnie o funkcje produktu — zakazane w E00.

### E1 — wybór odcinka na prawdziwych danych

- **Cel:** nowa ścieżka wyboru działa na żywych danych, N-01 rozstrzyga pilot historyczny (U-02), a N-02–N-04 mają zmierzone odpowiedzi.
- **Wejście:** zaakceptowane E0 i E00, zgody na pomiary; ewentualne rozszerzenie Z-1 rozstrzygane przed przekroczeniem budżetu/czasu.
- **Kolejność:** zebranie ≥ 2000 tytułów / ≥ 10 000 rekordów → niezależne etykiety Astra/Opus 5, arbitraż Gemini Pro i rozliczenie sporów przez właściciela → stały losowy podział stratyfikowany z ziarnem i sumami → budowa reguł od zera na części roboczej → jeden egzamin → czysta domena i adaptery → usługa/IPC/UI, N-03 i H1 (N-01 rozstrzygnięty pilotem historycznym, [plan przepływu](plans/e1-przeplyw-subskrypcji.md) §5.1). N-04 poprzedza zbieranie filmów korpusu.
- **Rezultat:** heurystyka zbudowana na oznaczonym korpusie, sprawdzona na odłożonej części niedostępnej autorowi; Anime → tytuł → wpisy franczyzy → odcinki wpisu → sugestia wydania i inne wydania z oceną tożsamości; raport pomiarów. Historyczne 231 rekordów pozostaje danymi z etykietami i źródłem kontroli, bez wymogu parytetu z prototypem. Ranking U-04/U-05/U-24 pozostaje bez zmian.
- **Warunek wyjścia:** ≥ 2000 tytułów / ≥ 10 000 oznaczonych rekordów, jednorazowy egzamin na odłożonej części: **0 błędnych `zgodnych`** rozpoznawalnych z nazwy/metadanych (plan E1 D6), a udział `niepewnych` i błędnych `niezgodnych` per warstwa zmierzony i zaakceptowany przez właściciela bez wymyślonego progu. Testy na stałych oznaczonych próbkach, bramki, H1 i raport (pilot N-01 z decyzją U-02, N-02–N-04) spełniają plan E1.
- **Stan (2026-09-28):** egzamin 1 (v9.2) — FAIL; egzamin 2 na świeżej części z rezerwy (H1 v10.3) — **PASS**: 0 błędnych `zgodnych` na 3 911 rekordach, pokrycie `zgodny` 46,9% (2021+: 69,6%), `zgodny ∪ niepewny` 93–100% odcinków. Właściciel przyjął v10.3 i zamknął strojenie; egzaminu 3 nie ma. **Zasada regresji:** błąd z praktyki, który da się naprawić heurystyką, staje się stałym przypadkiem regresyjnym w `tests/fixtures/`, a poprawka nie może psuć wcześniejszych przypadków ([plan integracji](plans/e1-integracja.md) §10.6). Reszta E1 (port H1 1:1, adaptery, usługa/IPC, UI, H1, outcome): [plans/e1-integracja.md](plans/e1-integracja.md).
- **Nie zawiera:** pobierania, subskrybowania, zmian stanu trwałego ani migracji; jedyny wyjątek to istniejący zapis `WatchState.provider_locks` po 429, bez nowego modelu danych (D4, [plan E1](plans/e1-wybor-odcinka.md) §7 i §15).
- **Ryzyko:** AniList odrzuci zagnieżdżone zapytanie o relacje (faza 0); zgoda Z-1 nie wystarczy na liczność/warstwy korpusu; egzamin wykaże błędne `zgodne` albo nieakceptowalne pokrycie. Porażka → nowa iteracja na części roboczej i nowa niewykorzystana część odłożona; stara nie stanowi ponownie dowodu. Osobne pliki, uprawnienia opiekuna, sumy przed/po i skrypt zwracający wyłącznie metryki chronią egzamin (plan E1 §9).

### E2 — jednorazowe pobieranie

- **Cel:** Pobierz z listy odcinków dostarcza gotowy odcinek do Biblioteki.
- **Stan po:** trwałe zlecenie per odcinek w WatchState (nowa wersja schematu, migracja z kopią), transfer z magnetu z listą plików, wybór plików per odcinek (U-17, U-18), kompletność per odcinek (P-07), przekazanie do istniejącego przetwarzania, „Pobierz ponownie”, ekran wyboru pliku przy niepewnym mapowaniu, ograniczenie rozmiaru odpowiedzi IPC (Q-08). Pomost `G` ze starym pobieraniem i subskrybowaniem zostaje do E3; stare trwające transfery kończą się po staremu (M-06).
- **Warunek wejścia:** N-03 potwierdzone. Jeśli nie: przed E2 decyzja właściciela (np. pobieranie pliku .torrent innym źródłem), bez cichego pobierania całych paczek.
- **Ryzyko:** wspólne kawałki paczki tworzą pliki niezamówionych odcinków — chroni I-07 i test negatywny skanu folderu. W E2 stare pobieranie (pomost `G`) i nowe „Pobierz” działają jednocześnie — plan E2 musi pokazać testem, że I-06 (jedno zlecenie tego samego odcinka z dwóch wejść) obowiązuje także między starą a nową drogą.

### E3 — subskrypcje

- **Cel:** subskrypcja działa sama przez cały sezon i znika po nim.
- **Stan po:** subskrypcja = wpis AniList + Kitsu ID + punkt odcięcia; maszyna stanów celu i próby, limit 3 prób celu, H2 w przepływie, rejestr decyzji i przełącznik trybu cienia według [planu przepływu](plans/e1-przeplyw-subskrypcji.md); przy przeniesieniu H2 do `anishift/`: odczyt `ffprobe` w `services/media`, reguły w warstwie aplikacji, pętla prób i ponowienie `ffprobe` należą do maszyny stanów; `scripts/tmp/h2_synthetics.py` ma sztywną ścieżkę `DEFAULT_TEMP`, więc przy przeniesieniu do `tests/` zastąpić ją `tmp_path`; do rozstrzygnięcia w planie E3: wczesna eskalacja, gdy kolejne próby tego samego celu H2 odrzuca z tym samym powodem długości; harmonogram z AniList; szukanie co 15 min przez dobę, co godzinę do 72 h, potem raz na dobę, powiadomienie po 7 dobach (U-14, S-14); dodatki sezonu widoczne w szczegółach (S-05); usuwanie bez pytania z Ctrl+Z (S-08); odcinki bez daty (U-15); izolacja problemów (S-12); logi sprawdzeń (S-13); wynik „Szukaj teraz” widoczny (S-06); autozamknięcie (U-11); przeniesienie starych subskrypcji (M-01–M-07). Źródło świeżych odcinków: tylko Torrentio (decyzja 2026-09-28, spec U-02; pilot historyczny zamiast N-01, [plan przepływu](plans/e1-przeplyw-subskrypcji.md) §5.1).
- **Ryzyko:** opóźnienie indeksowania dłuższe niż zakładane — pokazuje rejestr decyzji i tryb cienia po integracji (plan przepływu §5.1), nie zgadywanie w E3.

### E4 — kontrola zawartości

- **Cel:** wynik nie tłumaczy polskich napisów i sam wymienia wydanie bez napisów; lektor powstaje zawsze.
- **Stan po:** inspekcja ścieżek po pobraniu, reguły U-08, licznik prób per odcinek, powody w szczegółach (I-08).
- **Ryzyko:** rozpoznanie „signs-only” (N-05) — gdy niepewne, ścieżka traktowana jako pełna tylko przy braku słów kluczowych „signs/songs” w nazwie ścieżki; rozstrzyga próba na pobranych plikach.

### E5 — sprzątanie i przełączenie

- **Cel:** jeden mechanizm w kodzie i dokumentacji, nowa wersja u właściciela.
- **Stan po:** usunięte `_group_queries`, filtry grup i kategorii, aktywne wyszukiwanie Nyaa (U-02; fallback W-08 według osobnej decyzji), nieużywane eksporty; zaktualizowane scoped `AGENTS.md` i `README.md`; PR-y scalone; 7 dni pracy u właściciela.

### E6 — Biblioteka jako widok tytułów

Pomysł właściciela z 2026-10-01, podczas E2. Wykonanie po E2 według osobnego planu; kolejność względem E4/E5 ustala właściciel.

- **Problem:** Biblioteka pokazuje surowe nazwy plików mkv, z których trudno odczytać tytuł i odcinek. Jedno anime ma różne zapisy w nazwach. Dla Slime S4 `parse_release_name` daje trzy tytuły: „That Time I Got Reincarnated as a Slime” s4, „Tensei Shitara Slime Datta Ken 4th Season” (Erai-raws) oraz „Tensei Shitara Slime Datta Ken” s4 (Judas).
- **Czym jest Biblioteka:** wszystko, co zostało przetworzone (mkv i inne pliki). Użytkownika interesują nazwa dzieła, numer odcinka i tytuł odcinka.
- **Układ:** jak ekran Anime, dla spójności. Najpierw lista tytułów, Enter otwiera sezon z odcinkami; kontekst nad tabelą w stylu D19 (`BIBLIOTEKA` / `BIBLIOTEKA › <tytuł>`). Kolumny Emisja i Stan: Gotowe albo stany subskrypcji.
- **Zaznaczanie zostaje**, m.in. do usuwania kilku odcinków naraz; Kosz i Ctrl+Z działają jak dziś (B-03).
- **Możliwe połączenie z Subskrypcjami:** w sezonie widać także odcinki, które dopiero się pobiorą, z datą emisji. Zależy od działających subskrypcji E3.
- **Obawa właściciela:** przy wielu tytułach przewijanie strzałkami będzie męczące. Plan E6 musi to rozwiązać (np. wyszukiwarka jak D17); nie zgadywać rozwiązania przed planem.
- **Dysk bez zmian:** `workspace/ready/` zostaje płaskie, bez folderów w Eksploratorze (U-19). Grupowanie istnieje tylko w widoku.
- **Pliki pobrane przez Anime:** tytuł i numer z zapisanego klucza AniList (`EpisodeChoice` ma `anilist_id` i `number`), bez zgadywania z nazwy.
- **Pliki ręczne (Judas, Erai-raws, inne):** tytuł z nazwy pliku. Pytanie właściciela: czy heurystyka może rozpoznać taki plik przez AniList i ile to trwa przy 100 plikach. Szacunek do sprawdzenia pomiarem w planie E6, nie zmierzony: jedno zapytanie AniList na serię, wynik w cache, ograniczenie limitem AniList na minutę; kilka serii to sekundy, setki serii to minuty. Ryzyko złego sezonu: przy braku pewności „nie rozpoznano” i ręczny wybór, nigdy ciche przypisanie.
- **Punkty wejścia w kodzie:** `LibrarySet` / `LibraryFile` w `anishift/application/control_views.py`; widok Biblioteki w `anishift/cli/interactive/state.py` (`_library_rows`, `_library_detail_entries`); `parse_release_name` w `anishift/services/torrents/names.py`.
- **Nie zawiera:** zmian układu plików na dysku, odtwarzacza, synchronizacji z MAL/AniList (spec §10).
- **Warunek wyjścia:** osobny plan E6 zaakceptowany i wykonany; testy widoku i rozpoznawania; pomiar czasu rozpoznania przy ~100 plikach; H6 — właściciel ocenia Bibliotekę na własnych plikach.

## Ryzyka kierunku

| Ryzyko | Jak je rozpoznać | Reakcja |
| --- | --- | --- |
| Torrentio przestaje działać lub zmienia format | Testy kontraktowe na zapisanych odpowiedziach przechodzą, a żywe zapytania dają błąd/inną strukturę | Widoczny stan „Źródło niedostępne”; decyzja właściciela o drugim źródle (U-02: dziś Torrentio jest jedynym źródłem; drugie źródło wymaga nowej decyzji) |
| ani.zip znika | 404/timeout dla znanych ID | Działające subskrypcje mają zapisane Kitsu ID (U-22); nowe tytuły czekają; decyzja o zapasowym mapowaniu Kitsu |
| Heurystyka przepuszcza błędny odcinek | Właściciel zgłasza zły odcinek w Bibliotece | Dodać przypadek do korpusu testowego, poprawić regułę, nigdy nie luzować `niezgodny` |
| Heurystyka odrzuca za dużo | N-02 lub częste „niepewne wydanie” / „Brak wydania” | Rozszerzenie reguł na korpusie E1 w ramach E2/E3; ręczny wybór zostaje |
| Magnet bez metadanych | N-03 negatywne albo długie czasy | Stop przed E2, decyzja właściciela |
| Migracja gubi subskrypcje | Test na kopii stanu właściciela | Kopia (M-07), migracja idempotentna, odmowa startu przy nieznanej wersji |
| Limit Torrentio przy gęstym szukaniu (U-14) | Odpowiedzi 429 w rejestrze decyzji lub w pracy | Rzadsze sprawdzanie w pierwszej dobie (P-10, z rejestru po integracji; plan przepływu §4) |
| E00 rozlewa się na funkcje produktu | Plan lub diff E00 dotyka tłumaczenia, TTS albo UI poza wyborem modelu | Zatrzymać; funkcje multimodalne produktu to osobna decyzja właściciela |
| Proxy zmienia wymagania wywołań po E00 | Model działający po E00 zwraca 4xx w smoke requeście albo w ocenie korpusu E1 | Aktualizacja skilla OpenCode jako źródła, ponowna synchronizacja katalogu i poprawka silnika; E1 wstrzymuje ocenę korpusu na tym modelu |
| Zakres rośnie | Pomysły spoza spec §10 | Zapis do „Odłożone” w spec, nie do bieżącego etapu |
| E1–E3 scalone bez E4 | Polskie napisy są tłumaczone ponownie; wydanie bez napisów kończy jako Problem | Świadome ryzyko przejściowe; E4 zaraz po E3 |

## Historia materialnych zmian kierunku

| Data | Zmiana | Dowód / powód | Wpływ |
| --- | --- | --- | --- |
| 2026-09-24 | Właściciel: heurystyka tożsamości od zera na ≥ 2000 tytułów / ≥ 10 000 oznaczonych rekordów, zamiast portu i parytetu 231/231 | Decyzja właściciela: około 200 przypadków nie wystarcza; błąd ma być anomalią, a jakość sprawdzona na danych niewidzianych przy budowie | Korpus i etykiety przed domeną; zamrożony podział, budowa tylko na części roboczej i jednorazowy egzamin z 0 błędnych `zgodnych`; pozostałe metryki ocenia właściciel. Porażka wymaga nowej części odłożonej. Ranking bez zmian; E0 accepted, E1 current |
| 2026-09-23 | Właściciel: nowy etap E00 przed E1 — katalog modeli i wywołania zgodne 1:1 ze skillem OpenCode, multimodalność; oceniający N-02 przez `anishift.services.llm` (silnik Palantir), nie przez silnik tłumaczenia | Decyzja właściciela | E00 dodany (planned; wejście: osobny plan zaakceptowany przez właściciela); E1 zależy od E00; plan E1 §9 N-02 i faza 0 pkt 5a zmienione |
| 2026-09-23 | Właściciel: ocena całego korpusu przez nieograniczoną liczbę agentów | Decyzja właściciela | N-02: zamiast próbki 700 — cały korpus, dwóch agentów na rekord, rekordy kontrolne, lista dla właściciela |
| 2026-09-23 | Właściciel: kodek bez znaczenia; pomiary na VPS z VpsOracleManager | Decyzja właściciela | U-25; N-06 zamknięte; miejsce pomiarów ustalone |
| 2026-09-23 | Właściciel: heurystyka na korpusie ≥ 2000 tytułów | Decyzja właściciela | N-02 rozszerzone: korpus warstwowy, audyt 700 rekordów, warunek wyjścia E1 |
| 2026-09-23 | Właściciel odpowiedział na listę weta | Decyzja właściciela | U-05 potwierdzone; U-14 zagęszczone + powiadomienie po 7 dniach; S-08 bez pytania z Ctrl+Z; U-24 ukrywanie 720p i niżej; N-01 rozszerzone o pokrycie Torrentio vs Nyaa; pomiar na VPS zamiast listy MAL; N-06 kodek do decyzji |
| 2026-09-23 | Właściciel: lektor zawsze, także przy polskim dubbingu | Decyzja właściciela | U-08, U-23, E4 zmienione |
| 2026-09-23 | Właściciel ustalił kolejność wydań: jakość obrazu wygrywa, 720p to ostateczność | Decyzja właściciela po lekturze manifestu | U-04, U-05 i klucz rankingu w planie E1 zmienione |
| 2026-09-23 | Pakiet `final/` zastąpiony pakietem `final2/` | `workspace/.archive/acquisition/final2/audit.md` | Ranking zgodny z decyzją właściciela (jakość obrazu pierwsza); etapy przebudowane: pomiary i prawdziwe dane przed kosztowną pracą; usunięte mechanizmy bez wymagań; jeden szczegółowy plan tylko dla E1 |

## Nierozstrzygnięte decyzje

Weto i decyzje właściciela są rozliczone ([README.md](README.md) §3); Z-1 i Z-3 udzielone, Z-2 wycofana (§4). Szczegóły E00 rozstrzygnięto w zaakceptowanych planach [katalogu](plans/e00-katalog-modeli.md) i [projektu kodu](plans/e00-projekt-kodu.md): katalog jest projekcją stałych, mechanizm dwóch kont istnieje w silniku. Podłączenie danych konta 2 jest krokiem D2 fazy 0 E1, nie otwartą decyzją E00 ([plan E1](plans/e1-wybor-odcinka.md) §9 i §15).

Pozostają:

- **Warunkowo w E1:** rozszerzenie Z-1, jeśli 2000 tytułów / około 4000 zapytań w 2–3 doby nie da ≥ 10 000 rekordów we wszystkich warstwach albo zabraknie świeżej części egzaminacyjnej; jedno pytanie z rachunkiem w planie E1 §15.
- N-02–N-05 — rozstrzygają etapy wskazane w spec §15 (N-01 rozstrzygnięty 2026-09-28 pilotem historycznym, U-02).
- **Przed E3:** co zastąpi fallback po braku tytułu w AniList (D5, spec W-08, UX U01), gdy zniknie stara lista wydań Nyaa? Zachowanie E1 pozostaje rozstrzygnięte; odpowiedź wymaga decyzji właściciela przed usunięciem tej drogi w E3.
