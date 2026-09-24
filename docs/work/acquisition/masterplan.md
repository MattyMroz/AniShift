---
kind: masterplan
status: active
updated: 2026-09-23
baseline: 0e8a6bf9194d2786d426d3f3a58f48272b3eb087
---

# Masterplan: wspólne pobieranie i subskrypcje anime

## Cel końcowy

Użytkownik wybiera w AniShift tytuł → sezon → odcinki i klika Pobierz albo Subskrybuj. Właściwe pliki pobierają się same, przechodzą przez istniejące przetwarzanie i lądują w Bibliotece. Subskrypcje działają tydzień po tygodniu bez dotykania aplikacji i same znikają po sezonie. Kontrakt: [spec.md](spec.md). Ekrany i klawisze: [ux.md](ux.md).

## Źródła celu i ograniczeń

- [spec.md](spec.md) — co ma być prawdą (U-, W-, R-, P-, S-, M-, Q-, I-, PR-).
- [ux.md](ux.md) — makiety, przejścia, klawisze, scenariusze odbioru H1–H4.
- [plans/e1-wybor-odcinka.md](plans/e1-wybor-odcinka.md) — szczegółowy plan etapu E1.
- Skill OpenCode (`agents/skills/opencode/`: `assets/opencode.jsonc`, `references/models.md`, `references/foundry-proxy.md`, `references/configuration.md`) — kanoniczne źródło modeli i reguł wywołań proxy dla E00.
- `AGENTS.md` (root i scoped) — reguły repozytorium, bramki jakości, zakazy.
- Badania: `research/summary.md`, `research/anime-api-report.md`, `research/*.md`, `workspace/.archive/acquisition/evidence/`.

## Aktualny zaakceptowany stan

- **Działa i zostaje:** rezydent i jeden właściciel stanu, prywatny qBittorrent, graf przetwarzania, Biblioteka/Kosz/Ctrl+Z, Historia, Ręczny, Ustawienia, przetwarzanie plików z workspace.
- **Działa, ale zostanie zastąpione:** zakładka Anime z wyborem grupy (Nyaa), subskrypcje przypięte do grupy.
- **Nie działa:** subskrypcje (8 potwierdzonych mechanizmów zatrzymania, spec §3.2); pobieranie wybranych plików z paczki; reguła PL/MultiSub/1080p.
- **Potwierdzone badaniami, nie w kodzie:** łańcuch AniList → ani.zip → Torrentio, heurystyka tożsamości, wybór plików w qB (na pliku .torrent).
- **Silnik LLM (`anishift.services.llm`):** po E00 (PR #57) — pliki (obraz, PDF, audio, wideo) w każdym silniku; lista 22 modeli Palantira w `engines/palantir/constants.py` (katalog aplikacji to jej projekcja, bez pliku JSONC); OpenAI przez `/responses` z wariantami rozumowania; mechanizm drugiego konta w serwisie (odczyt tokena 2 z `.env` — osobny krok); próby na żywo 182/182 ([outcomes/e00.md](outcomes/e00.md)).
- **Niepewne:** metadane z samego hasha (N-03), opóźnienie Torrentio dla premier (N-01), heurystyka na korpusie ≥ 2000 tytułów (N-02), filmy (N-04).
- **Blokery:** brak.
- **Znany błąd poza etapami:** `ResidentSession.season_context()` dla „4th Season” (AniList `182205`) daje `offset=48`, przez co ranking panelu uznaje S04E23 za inny sezon, a S03E23 za właściwy (wykryte 2026-09-24).

## Etapy

| Nr | Etap | Rezultat | Zależności | Warunek wyjścia | Status |
| --- | --- | --- | --- | --- | --- |
| E0 | Pakiet decyzyjny | Specyfikacja, masterplan, plan E1 i UX bez sprzeczności; ustalenia `inżynierska` zaakceptowane lub zawetowane | — | Właściciel akceptuje pakiet (lista weta w manifeście) i zgody na pomiary E1 | current |
| E00 | Katalog modeli i wywołania zgodne z OpenCode | Silnik LLM AniShift zna wszystkie modele OpenCode z limitami, modalnościami i wariantami rozumowania; katalog nadąża za kanonicznym `opencode.jsonc` jedną drogą; każdy model odpowiada przez obecne proxy; obrazy i PDF trafiają do modeli, które je deklarują, pozostałe jawnie odmawiają; decyzja o dwóch enrollmentach podjęta w planie E00 | E0; osobny plan E00 zaakceptowany przez właściciela | Bramki zielone; katalog zgodny z kanonicznym plikiem; smoke request na każdym modelu (obraz i PDF tam, gdzie deklarowane) zaliczony; review `opus5` bez otwartych findingów krytycznych i poważnych | accepted |
| E1 | Wybór odcinka na prawdziwych danych + pomiary | Nowa ścieżka Anime: tytuł → wpisy → odcinki → sugestia i inne wydania (bez pobierania). Stara lista wydań wg grup zostaje pod klawiszem `G`, więc pobieranie i dodawanie subskrypcji działa jak dziś. Adaptery ani.zip i Torrentio, heurystyka i ranking w kodzie. Raport N-01–N-04 | E0, E00 (oceniający korpusu N-02 działają przez silnik LLM po E00) | Testy i bramki zielone; parytet 231/231 z badaniem; korpus ≥ 2000 tytułów oceniony w całości przez agentów, 0 błędnych `zgodnych`; H1 zaliczone; raport pomiarów z decyzjami dla E2 i E3 | planned |
| E2 | Jednorazowe pobieranie nową drogą | Pobierz z listy odcinków: zlecenie per odcinek, magnet → lista plików → tylko wybrane pliki → kompletność per odcinek → istniejące przetwarzanie → Biblioteka. Pobierz ponownie. Pomost `G` (stara lista wg grup) zostaje, bo tylko z niego da się jeszcze dodać subskrypcję | E1 (N-03 pozytywne) | Test integracyjny z prawdziwym qB na syntetyku (E1/E3 bez E2, restart); migracja WatchState na kopii stanu właściciela; H2 zaliczone | planned |
| E3 | Subskrypcje na wspólnym mechanizmie | Subskrybuj z listy odcinków, zakładka Subskrypcje (lista, szczegóły, dodaj, usuń, wstrzymaj, szukaj teraz), harmonogram U-13–U-15, autozamknięcie, przeniesienie starych subskrypcji; usunięty pomost `G` i stara droga grup w UI | E2; decyzja o źródle świeżych odcinków z N-01 | Testy fake clock (emisja, brak wydania, koniec sezonu, restart, izolacja problemów); migracja na kopii; H3: tydzień bez dotykania | planned |
| E4 | Kontrola zawartości po pobraniu | PL napisy → bez tłumaczenia; obce → tłumaczenie; brak napisów → jedna zamiana wydania; lektor zawsze | E2; N-05 | Testy planera na syntetykach; H4 na prawdziwym odcinku z PL i bez PL | planned |
| E5 | Sprzątanie i przełączenie | Usunięte martwe ścieżki (grupy, kategorie, aktywne wyszukiwanie Nyaa jeśli N-01 nie wymaga), aktualne `AGENTS.md`/`README.md`, PR-y scalone, nowa wersja działa u właściciela | E3, E4 | Pełne bramki, niezależne review implementacji, działający rezydent u właściciela przez 7 dni bez interwencji | planned |

Gałąź i PR E00 ustala jego plan; E1 startuje od stanu po E00 (nie od samego `0e8a6bf`).

Gałęzie: cały łańcuch startuje od `work/local-automation/06-efficiency` (niescalonej jeszcze z `main`); gałęzie etapów według wzorca repo `work/acquisition/<nn>-<slug>`. Scalanie: E1, E2 i E3 to osobne, piętrowe PR-y. Do `main` trafiają razem po akceptacji E3, bo dopiero wtedy nowa droga ma i pobieranie, i subskrypcje (inaczej `main` traciłby jedną z nich). E4 i E5 to osobne PR-y po nich.

## Aktualny etap

**Etap:** E00 zakończone (kod zaakceptowany, PR #57 czeka na merge) → E1.

**Następny krok:** aktualizacja planu E1 ([plans/e1-wybor-odcinka.md](plans/e1-wybor-odcinka.md)) na stanie po E00 i jego akceptacja przez właściciela; E1 startuje od gałęzi E00.

**Dlaczego E00 przed E1:** E1 ocenia korpus N-02 modelami przez silnik LLM AniShift. Właściciel wymaga, by ten silnik najpierw znał aktualne modele i aktualną specyfikację wywołań; inaczej ocena korpusu biegłaby na nieaktualnym katalogu i niepotwierdzonej drodze do modeli OpenAI.

**Dlaczego E1 jako pierwszy etap pobierania:** usuwa największe niewiadome tanio i bez skutków. Pokazuje prawdziwe dane w prawdziwym panelu (zamiast makiety do wyrzucenia), więc właściciel ocenia UX na swoich tytułach przed kosztowną pracą nad pobieraniem i migracją. Jeśli N-03 wypadnie źle, cały sposób pobierania z Torrentio trzeba przemyśleć — lepiej wiedzieć to przed E2.

**Największa niewiadoma:** N-03 — czy qBittorrent pobierze listę plików z samego hasha i pozwoli wybrać pliki przed zapisem treści.

**Następny artefakt:** zaktualizowany plan E1; potem wynik E1 (`outcomes/e1.md`) i plan E2 napisany na stanie po E1.

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

- **Cel:** nowa ścieżka wyboru działa na żywych danych, a niewiadome N-01–N-04 mają zmierzone odpowiedzi.
- **Wejście:** zaakceptowany E0, zgody na pomiary.
- **Rezultat:** Anime → tytuł → wpisy franczyzy → odcinki wpisu → sugestia wydania i inne wydania z oceną tożsamości; raport pomiarów.
- **Nie zawiera:** pobierania, subskrybowania, zmian stanu trwałego, migracji.
- **Ryzyko:** AniList odrzuci zagnieżdżone zapytanie o relacje (sprawdzane w fazie 0 planu); heurystyka zostawi zbyt wiele `niepewnych` (N-02) — wtedy E2 dostaje zadanie rozszerzenia reguł na podstawie zebranego korpusu.

### E2 — jednorazowe pobieranie

- **Cel:** Pobierz z listy odcinków dostarcza gotowy odcinek do Biblioteki.
- **Stan po:** trwałe zlecenie per odcinek w WatchState (nowa wersja schematu, migracja z kopią), transfer z magnetu z listą plików, wybór plików per odcinek (U-17, U-18), kompletność per odcinek (P-07), przekazanie do istniejącego przetwarzania, „Pobierz ponownie”, ekran wyboru pliku przy niepewnym mapowaniu, ograniczenie rozmiaru odpowiedzi IPC (Q-08). Pomost `G` ze starym pobieraniem i subskrybowaniem zostaje do E3; stare trwające transfery kończą się po staremu (M-06).
- **Warunek wejścia:** N-03 potwierdzone. Jeśli nie: przed E2 decyzja właściciela (np. pobieranie pliku .torrent innym źródłem), bez cichego pobierania całych paczek.
- **Ryzyko:** wspólne kawałki paczki tworzą pliki niezamówionych odcinków — chroni I-07 i test negatywny skanu folderu. W E2 stare pobieranie (pomost `G`) i nowe „Pobierz” działają jednocześnie — plan E2 musi pokazać testem, że I-06 (jedno zlecenie tego samego odcinka z dwóch wejść) obowiązuje także między starą a nową drogą.

### E3 — subskrypcje

- **Cel:** subskrypcja działa sama przez cały sezon i znika po nim.
- **Stan po:** subskrypcja = wpis AniList + Kitsu ID + „od N”; harmonogram z AniList; szukanie co 15 min przez dobę, co godzinę do 72 h, potem raz na dobę, powiadomienie po 7 dobach (U-14, S-14); dodatki sezonu widoczne w szczegółach (S-05); usuwanie bez pytania z Ctrl+Z (S-08); odcinki bez daty (U-15); izolacja problemów (S-12); logi sprawdzeń (S-13); wynik „Szukaj teraz” widoczny (S-06); autozamknięcie (U-11); usuwanie z potwierdzeniem; przeniesienie starych subskrypcji (M-01–M-07). Źródło świeżych odcinków zgodnie z wynikiem N-01 (Torrentio albo Torrentio + RSS Nyaa z tą samą heurystyką).
- **Ryzyko:** opóźnienie indeksowania dłuższe niż zakładane — rozwiązuje decyzja N-01 podjęta w E1, nie zgadywanie w E3.

### E4 — kontrola zawartości

- **Cel:** wynik nie tłumaczy polskich napisów i sam wymienia wydanie bez napisów; lektor powstaje zawsze.
- **Stan po:** inspekcja ścieżek po pobraniu, reguły U-08, licznik prób per odcinek, powody w szczegółach (I-08).
- **Ryzyko:** rozpoznanie „signs-only” (N-05) — gdy niepewne, ścieżka traktowana jako pełna tylko przy braku słów kluczowych „signs/songs” w nazwie ścieżki; rozstrzyga próba na pobranych plikach.

### E5 — sprzątanie i przełączenie

- **Cel:** jeden mechanizm w kodzie i dokumentacji, nowa wersja u właściciela.
- **Stan po:** usunięte `_group_queries`, filtry grup i kategorii, aktywne wyszukiwanie Nyaa (o ile N-01 nie wymaga RSS), nieużywane eksporty; zaktualizowane scoped `AGENTS.md` i `README.md`; PR-y scalone; 7 dni pracy u właściciela.

## Ryzyka kierunku

| Ryzyko | Jak je rozpoznać | Reakcja |
| --- | --- | --- |
| Torrentio przestaje działać lub zmienia format | Testy kontraktowe na zapisanych odpowiedziach przechodzą, a żywe zapytania dają błąd/inną strukturę | Widoczny stan „Źródło niedostępne”; decyzja właściciela o drugim źródle (Nyaa RSS przez tę samą heurystykę jest gotową drogą z E1) |
| ani.zip znika | 404/timeout dla znanych ID | Działające subskrypcje mają zapisane Kitsu ID (U-22); nowe tytuły czekają; decyzja o zapasowym mapowaniu Kitsu |
| Heurystyka przepuszcza błędny odcinek | Właściciel zgłasza zły odcinek w Bibliotece | Dodać przypadek do korpusu testowego, poprawić regułę, nigdy nie luzować `niezgodny` |
| Heurystyka odrzuca za dużo | N-02 lub częste „Brak pewnego wydania” | Rozszerzenie reguł na korpusie E1 w ramach E2/E3; ręczny wybór zostaje |
| Magnet bez metadanych | N-03 negatywne albo długie czasy | Stop przed E2, decyzja właściciela |
| Migracja gubi subskrypcje | Test na kopii stanu właściciela | Kopia (M-07), migracja idempotentna, odmowa startu przy nieznanej wersji |
| Limit Torrentio przy gęstym szukaniu (U-14) | Odpowiedzi 429 w pomiarze E1 lub w pracy | Rzadsze sprawdzanie w pierwszej dobie; decyzja w planie E3 na danych N-01 |
| E00 rozlewa się na funkcje produktu | Plan lub diff E00 dotyka tłumaczenia, TTS albo UI poza wyborem modelu | Zatrzymać; funkcje multimodalne produktu to osobna decyzja właściciela |
| Proxy zmienia wymagania wywołań po E00 | Model działający po E00 zwraca 4xx w smoke requeście albo w ocenie korpusu E1 | Aktualizacja skilla OpenCode jako źródła, ponowna synchronizacja katalogu i poprawka silnika; E1 wstrzymuje ocenę korpusu na tym modelu |
| Zakres rośnie | Pomysły spoza spec §10 | Zapis do „Odłożone” w spec, nie do bieżącego etapu |
| E1–E3 scalone bez E4 | Polskie napisy są tłumaczone ponownie; wydanie bez napisów kończy jako Problem | Świadome ryzyko przejściowe; E4 zaraz po E3 |

## Historia materialnych zmian kierunku

| Data | Zmiana | Dowód / powód | Wpływ |
| --- | --- | --- | --- |
| 2026-09-23 | Właściciel: nowy etap E00 przed E1 — katalog modeli i wywołania zgodne 1:1 ze skillem OpenCode, multimodalność; oceniający N-02 przez `anishift.services.llm` (silnik Palantir), nie przez silnik tłumaczenia | Decyzja właściciela | E00 dodany (planned; wejście: osobny plan zaakceptowany przez właściciela); E1 zależy od E00; plan E1 §9 N-02 i faza 0 pkt 5a zmienione |
| 2026-09-23 | Właściciel: ocena całego korpusu przez nieograniczoną liczbę agentów | Decyzja właściciela | N-02: zamiast próbki 700 — cały korpus, dwóch agentów na rekord, rekordy kontrolne, lista dla właściciela |
| 2026-09-23 | Właściciel: kodek bez znaczenia; pomiary na VPS z VpsOracleManager | Decyzja właściciela | U-25; N-06 zamknięte; miejsce pomiarów ustalone |
| 2026-09-23 | Właściciel: heurystyka na korpusie ≥ 2000 tytułów | Decyzja właściciela | N-02 rozszerzone: korpus warstwowy, audyt 700 rekordów, warunek wyjścia E1 |
| 2026-09-23 | Właściciel odpowiedział na listę weta | Decyzja właściciela | U-05 potwierdzone; U-14 zagęszczone + powiadomienie po 7 dniach; S-08 bez pytania z Ctrl+Z; U-24 ukrywanie 720p i niżej; N-01 rozszerzone o pokrycie Torrentio vs Nyaa; pomiar na VPS zamiast listy MAL; N-06 kodek do decyzji |
| 2026-09-23 | Właściciel: lektor zawsze, także przy polskim dubbingu | Decyzja właściciela | U-08, U-23, E4 zmienione |
| 2026-09-23 | Właściciel ustalił kolejność wydań: jakość obrazu wygrywa, 720p to ostateczność | Decyzja właściciela po lekturze manifestu | U-04, U-05 i klucz rankingu w planie E1 zmienione |
| 2026-09-23 | Pakiet `final/` zastąpiony pakietem `final2/` | `workspace/.archive/acquisition/final2/audit.md` | Ranking zgodny z decyzją właściciela (jakość obrazu pierwsza); etapy przebudowane: pomiary i prawdziwe dane przed kosztowną pracą; usunięte mechanizmy bez wymagań; jeden szczegółowy plan tylko dla E1 |

## Nierozstrzygnięte decyzje

- Weto właściciela do ustaleń `inżynierska` (lista w [manifest.md](manifest.md) §3).
- Zgody na pomiary E1 (manifest §4).
- N-01–N-05 — rozstrzygają etapy wskazane w spec §15.
- Szczegóły E00 (forma synchronizacji katalogu, dwa enrollmenty) — rozstrzyga plan E00 zaakceptowany przez właściciela.
