# Plan 01 — odbudowa prostego Interactive CLI i postępu plikowego

## Status

| Pole | Wartość |
|---|---|
| Status | AWAITING_HITL |
| Tryb | REPLAN |
| Zakres | Home, Auto i prezentacja postępu |
| Specyfikacja | `./spec.md`, uzgodniona w P-001 |
| Branch | `work/interactive-cli/01-home-auto` |
| Baseline | `1fb996f8b2738c4fa41b1ddc18e7a85dba0b8806` |
| Referencja zachowania | `55068b016997cc5d348f7d19fd1cb8869f20227f` |
| Referencyjna klasa | `anishift/cli/pipeline_ui.py::_PipelineProgressRows` |

Ten dokument zastępuje poprzedni plan wykonania Interactive CLI. Nie zatwierdza
obecnej implementacji. Opisuje jej kontrolowane usunięcie i odbudowę na aktualnym
backendzie.

## 1. Cel

Odbudować Interactive CLI tak, aby:

- Home zachował zaakceptowany slime, napis `ANISHIFT` i esencjonalną stopkę;
- Auto pokazywało jeden stabilny wiersz postępu na plik;
- pliki przechodziły przez proste, publiczne etapy podobnie do historycznego
  `_PipelineProgressRows`;
- użytkownik nie widział technicznej topologii grafu zadań;
- kolejność plików była naturalna i przewidywalna;
- Auto zachowywało kolejkę `ready_first` oraz skonfigurowaną współbieżność LLM i TTS;
- gotowy plik natychmiast przechodził do następnego etapu bez czekania na całą partię;
- zakończone wiersze pozostawały widoczne do powrotu na Home;
- szerokość i wysokość terminala natychmiast przeliczały markę, postęp i stopkę bez
  dodatkowego viewportu;
- nie pozostał osierocony kod z odrzuconego rozwiązania.

## 2. Reguły wykonania

1. Plan wykonuje główny agent. Bez orkiestratora i delegowania implementacji.
2. `anishift/utils/rich_console/**` pozostaje nietknięte.
3. Historyczny commit jest wiążącą referencją zachowania całego Auto. Implementacja
   pozostaje w `anishift.application`, ale ekstrakcja, tłumaczenie, TTS, audio,
   kolejność, retry i przejścia UI mają zachować kontrakt legacy 1:1.
4. Nie przywracamy starego `anishift.pipeline`, starego shella ani `/settings`.
5. Aktualny `RunEvent` pozostaje granicą między backendem i prezentacją.
6. UI nie może ujawniać `TaskKind`, kolejek ani technicznych etapów grafu.
7. Nie powstaje nowy toolkit, drugi manager postępu, zagnieżdżony `Live` ani
   prywatny dostęp do Rich. Resize może uruchomić jeden redraw przez publiczne API.
8. Nie dodajemy zależności.
9. Nie wykonujemy końcowego commita przed automatycznymi bramkami i ręcznym HITL.

## 3. Stan wejściowy i rozbieżności

| Obszar | Stan obecny | Stan docelowy |
|---|---|---|
| Branding | Slime i `ANISHIFT` są akceptowalne | Zachować bez przebudowy grafiki |
| Home | Zawiera eksperymentalne warstwy i geometrię | Minimalny branding, menu i hint |
| Przygotowanie Auto | Pokazuje skanowanie i stany przygotowawcze | Przygotowanie niewidoczne |
| Tożsamość wiersza | Wiersze wynikają z technicznych tasków | Jeden wiersz na plik |
| Etykiety | Pokazują techniczne etapy grafu | Tylko etapy publiczne |
| Kolejność | Wymuszona serializacja blokuje kolejkę | Stabilne wiersze i przepływ `ready_first` |
| Tłumaczenie/TTS | Nadpisane limity `1` | Zapisane limity, w tym cztery pliki LLM |
| Renderowanie | Wrapper `Live`, viewport i windowing | Bezpośredni `MultiProgressManager` |
| Nazwy plików | Ryzyko podwójnego escapowania `[` | Surowa nazwa, escape w managerze |
| Wąski terminal | Nadmiar geometrii i migotanie | Jedna czytelna linia przy 80 kolumnach |
| Koniec | Oddzielne podsumowania i listy produktów | Zielone wiersze, klawisz, Home |

## 4. Decyzje projektowe

### D-001 — zachowany zakres wizualny

Z obecnej implementacji zachowujemy:

- grafikę slime;
- główny napis `ANISHIFT`;
- stopkę z bieżącym katalogiem po lewej i wersją po prawej;
- czarne tło i istniejącą paletę brandingu tych dwóch elementów.

Nie uznajemy za zaakceptowane żadnych pozostałych warstw, ramek, statusów,
gradientów pomocniczych ani mechanizmów pozycjonowania.

### D-002 — jeden plik, jeden wiersz

Przed uruchomieniem pipeline'u renderer:

1. otrzymuje wejścia w naturalnej kolejności;
2. tworzy dokładnie jeden wiersz dla każdego pliku;
3. zapamiętuje mapowanie stabilnego identyfikatora grupy na `TaskID`;
4. aktualizuje ten sam wiersz przez cały przebieg;
5. przekazuje surową nazwę pliku do `MultiProgressManager`.

Nowy task backendu nie może automatycznie tworzyć nowego wiersza UI.

### D-003 — etapy legacy

UI odtwarza etapy `_PipelineProgressRows`:

| Etap | Znaczenie |
|---|---|
| `Extracting` | Przygotowanie materiału źródłowego |
| `Extracted` | Ekstrakcja ukończona |
| `Translating` | Tłumaczenie napisów |
| `Translated` | Tłumaczenie ukończone |
| `Synthesizing` | Generowanie lektora |
| `Retrying` | Ponowienie requestu TTS |
| `Audio normalize` | Normalizacja audio |
| `Audio timeline` | Budowanie osi czasu |
| `Audio mixing` | Miksowanie lektora |
| `Audio resume` | Wznowienie lektora |
| `Audio skipped` | Pominięcie pustego lektora |
| `Done` | Plik ukończony |
| `Failed` | Plik zakończony błędem |
| `Cancelled` | Przebieg anulowany |
| `Not processed` | Plik nie został rozpoczęty |

Normalizacja napisów, dzielenie segmentów, transkodowanie, kompozycja i
publikowanie nie otrzymują osobnych wierszy. Zdarzenia audio używają nazw legacy
na tym samym wierszu pliku.

### D-004 — etykiety zakazane

W produkcyjnym Interactive CLI nie mogą pojawiać się:

```text
Skanowanie workspace
Przygotowanie workspace
Oczekuje
Etap gotowy
Kodowanie audio
Publikowanie
Składanie MKV
Składanie MP4
```

Lista jest również kontraktem regresyjnym testów.

### D-005 — kolejka Auto zgodna z backendem

Auto nie nadpisuje snapshotu ustawień:

- `processing_order_policy=ready_first` zachowuje przepływ gotowych grup;
- `llm_max_concurrency=4` pozwala tłumaczyć cztery pliki LLM jednocześnie;
- TTS syntetyzuje jeden plik naraz, a równoległość requestów wewnątrz pliku pochodzi
  z aktywnego profilu silnika;
- ekstrakcja używa dokładnej puli legacy i jednego procesu z audio oraz napisami na
  każdy MKV;
- audio może nakładać się z syntezą następnego pliku;
- wiersze pozostają w naturalnej kolejności mimo przeplatania etapów;
- tryb ręczny korzysta z tej samej zapisanej konfiguracji.

Nie zmieniamy wspólnego schedulera ani serwisów domenowych tylko po to, aby uzyskać
wygląd UI.

### D-006 — bezpośredni manager postępu

Renderer używa publicznego `MultiProgressManager`:

- bez dodatkowego `Live`;
- bez `renderable_wrapper`;
- bez `viewport.py`;
- bez wyliczania wysokości workspace;
- bez dostępu do prywatnych pól;
- z paskiem i procentem od pierwszego stanu `Extracting`;
- bez spinnera podczas ekstrakcji, tłumaczenia i TTS;
- ze spinnerem wyłącznie dla niedeterministycznych faz audio, jak w legacy;
- z widocznym procentem;
- bez ETA i statystyk pobierania;
- z wierszami zachowanymi po ukończeniu do naciśnięcia klawisza;
- z kolumną etapu o stałej szerokości 14 znaków;
- z jednym odstępem pomiędzy paskiem i separatorem procentu oraz pomiędzy kolejnymi
  kolumnami.

Dopasowanie szerokości może sterować wyłącznie publicznymi parametrami opisu i
widocznością czasu. Musi być sprawdzone dla 80, 100 i 140 kolumn.

### D-007 — lifecycle Auto

```text
Home
  → wybór Auto
  → usunięcie menu przez Questionary przy zachowaniu marki
  → odtworzenie stopki w ostatnim bezpiecznym wierszu
  → ciche przygotowanie
  → refusal albo jeden pełny redraw widoku postępu pod marką
  → terminalne wiersze
  → dowolny klawisz
  → wyczyszczenie
  → Home
```

Nie ma osobnego ekranu „Gotowe”, listy produktów ani drukowania historii stanów.
Expected error wraca do Home po krótkim, bezpiecznym komunikacie. `Ctrl+C`
przywraca kursor i terminal bez tracebacka.

### D-008 — minimalny Home

Home zawiera wyłącznie:

- slime;
- napis `ANISHIFT`;
- `Auto`, `Ręczny`, `Ustawienia`, `Wyjście`;
- hint `↑↓ · Enter`;
- marker `❯` przy aktualnym wyborze.
- stopkę: bieżący katalog po lewej i wersję po prawej.

Zaznaczenie zmienia kolor markera i tekstu aktualnej pozycji na fioletowy. Nie
stosuje kolorowego tła.
Nie pokazujemy modelu, workspace, presetu, ramki ani command bara.

### D-009 — stany końcowe

- Sukces: zielony pasek na 100% i etykieta `Done`, bez dodatkowego prefiksu.
- Błąd: czerwony wiersz z `Failed`, bez sekretów i pełnych ścieżek.
- Anulowanie: `Cancelled` dla aktywnego pliku.
- Nieuruchomione pliki: `Not processed`.
- Wiersze nie znikają przed naciśnięciem klawisza.

## 5. Zakres plików

### Maksymalny impact set

```text
anishift/application/service.py
anishift/application/events.py
anishift/application/extraction_handler.py
anishift/application/handlers.py
anishift/application/planner.py
anishift/application/planning.py
anishift/application/runtime.py
anishift/application/tts_handler.py
anishift/application/AGENTS.md
anishift/cli/AGENTS.md
anishift/cli/interactive/app.py
anishift/cli/interactive/home.py
anishift/cli/interactive/progress.py
anishift/cli/interactive/prompts.py
anishift/config/field_catalog.py
anishift/config/presets.py
anishift/config/AGENTS.md
docs/work/plain-cli/spec.md
docs/work/plain-cli/01-plain-cli.md
tests/application/test_service.py
tests/application/test_events.py
tests/application/test_execution_handlers.py
tests/application/test_planner.py
tests/application/test_planning.py
tests/application/test_scheduler.py
tests/application/test_tts_handler.py
tests/cli/test_interactive_app.py
tests/cli/test_interactive_home.py
tests/cli/test_interactive_progress.py
tests/cli/test_main.py
tests/cli/test_run.py
tests/config/test_presets.py
```

Lista nie nakazuje dotknięcia każdego pliku. Niepotrzebne zmiany mają zostać
cofnięte do baseline'u, nie „naprawione” kolejną warstwą.

### Plik do usunięcia

```text
anishift/cli/interactive/viewport.py
```

### Obszary nietykalne

```text
anishift/services/**
anishift/utils/rich_console/**
```

Nie powstają nowe pliki produkcyjne ani `tasks.json`.

## 6. Kolejność wykonania

### P-001 — uzgodnienie dokumentów

1. Porównać `spec.md`, bieżące AGENTS i ten plan.
2. Usunąć ze specyfikacji wymagania viewportu, technicznych faz i trwałych warstw,
   które przeczą D-001–D-009.
3. Zapisać jeden kontrakt: jeden plik, jeden wiersz, publiczne fazy.
4. Sprawdzić zakaz modyfikacji `anishift/utils/rich_console/**`.

Gate: SPEC i PLAN nie mają sprzecznych wymagań.

### P-002 — reset odrzuconej implementacji

1. Zestawić każdy zmieniony plik z baseline'em
   `1fb996f8b2738c4fa41b1ddc18e7a85dba0b8806`.
2. Zachować asset slime, renderer napisu `ANISHIFT` i kontrakt stopki.
3. Usunąć `viewport.py`.
4. Usunąć adapter `Live`, viewport, windowing i `_ResponsiveText`; pozostawić tylko
   minimalną geometrię marki, paska i esencjonalnej stopki.
5. Usunąć testy istniejące wyłącznie dla tych mechanizmów.
6. Cofnąć eksperymentalne zmiany application/config, a potem wprowadzać tylko
   zmiany jawnie wymagane w P-003–P-008.

Gate: brak osieroconego importu, testu, komentarza lub wymagania dokumentacyjnego.

### P-003 — odbudowa Home

1. Złożyć minimalny Home zgodnie z D-001 i D-008.
2. Użyć standardowego selecta Questionary.
3. Zachować marker `❯`, kolor tekstu aktywnej opcji i brak tła.
4. Centrować przez publiczne API Rich/Questionary.
5. Nie implementować logiki Auto w tym kroku.

Gate HOME: ręczny PASS przy 80, 100 i 140 kolumnach oraz po kilku resize'ach.

### P-004 — odbudowa modelu postępu

1. Zbudować mapowanie `RunEvent` na publiczne fazy D-003.
2. Prealokować wiersze w naturalnej kolejności.
3. Utrzymywać jeden `TaskID` na plik.
4. Nie tworzyć wiersza dla pojedynczego `TaskKind`.
5. Przekazywać każdy realny procent ekstrakcji bez uśredniania.
6. Używać dokładnego licznika TTS legacy.
7. Dla faz bez realnego procentu użyć pulse bez wymyślania wartości.
8. Zamrozić wiersz dopiero przy stanie terminalnym pliku.

Gate: test zdarzeń dowodzi, że cały plik przechodzi przez jeden wiersz.

### P-005 — przywrócenie kolejki Auto

1. Usunąć nadpisanie `strict_natural` oraz limitów wykonania z `plan_auto()`.
2. Przekazać zapisany snapshot ustawień bez zmian do `build_auto_plan()`.
3. Zachować naturalną kolejność prealokowanych wierszy przy przeplataniu eventów.
4. Potwierdzić `ready_first`, limit czterech plików LLM i aktywne limity TTS.
5. Przywrócić pojedynczy aktywny plik TTS bez zmniejszania request concurrency.
6. Przywrócić naturalny porządek niezależnych tasków.
7. Nie zmieniać schedulera ani serwisów domenowych.

Gate: plan Auto zachowuje zapisane limity, a scheduler może utrzymać cztery aktywne
zadania `llm:*`.

### P-006 — uproszczenie pętli Auto

1. Po wyborze Auto usunąć prompt menu, ale nie wykonywać pośredniego renderu Auto ze
   sztuczną liczbą wierszy.
2. Zachować markę, odtworzyć stopkę i wykonać preflight bez `console.status` oraz bez
   stanu skanowania.
3. Przy refusal pokazać bezpieczny komunikat i wrócić na Home.
4. Przy gotowości wykonać jeden docelowy redraw i uruchomić pod marką jeden manager
   postępu.
5. Utrzymywać stopkę na ostatnim bezpiecznym wierszu przez cały run.
6. Po terminalnych wierszach zaczekać na klawisz i wrócić na Home.
7. Posprzątać terminal przy błędzie i `Ctrl+C`.

Gate: sesja nie produkuje historii poprzednich ramek ani ekranów.

### P-007 — zachowanie szerokości

1. Nie przywracać viewportu ani wrappera.
2. Skracać wyłącznie opis pliku, nigdy procent i stan.
3. Ukrywać czas tylko wtedy, gdy wymaga tego wąski terminal.
4. Reagować na zmianę szerokości i wysokości przez publiczny redraw całego widoku.
5. Scalać serię szybkich zmian do ostatniego stabilnego rozmiaru, bez kolejki pełnych
   redrawów i bez przebudowy managera przy zmianie samej wysokości.
6. Sprawdzić brak migotania i wielowierszowego progressu.
7. Poniżej szerokości pełnego brandingu przejść na kompaktową markę i dalej zachować
   procent w jednym wierszu.

Gate: pojedynczy wiersz i widoczny procent przy 80 kolumnach.

### P-008 — testy kontraktowe i regresyjne

Testy mają wykrywać:

- więcej niż jeden wiersz na plik;
- nienaturalną kolejność;
- utratę `ready_first` albo limitu czterech plików LLM;
- zakazane etykiety D-004;
- podwójne escapowanie i tekst `\\[`;
- zniknięcie wierszy przed klawiszem;
- przycięty procent przy 80 kolumnach;
- powrót `viewport.py`, dodatkowego `Live` lub prywatnego dostępu do Rich;
- nadpisanie zapisanych limitów Auto lub trybu ręcznego;
- ładowanie toolkitu przez techniczne komendy CLI;
- traceback lub pozostawiony kursor po expected error i `Ctrl+C`.

Test runtime używa prawdziwego publicznego konstruktora managera. Mock akceptujący
dowolne argumenty nie może być jedyną ochroną przed regresją typu `bar_width`.

### P-009 — weryfikacja i HITL

```powershell
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest tests/cli tests/application/test_service.py tests/application/test_scheduler.py
git diff --check
uv run pytest
```

Windows HITL:

1. Home przy 80, 100 i 140 kolumnach.
2. Kilka szybkich zmian rozmiaru.
3. Auto dla jednego pliku.
4. Auto dla wielu plików o długich nazwach.
5. Expected error.
6. `Ctrl+C` podczas Home i Auto.
7. Powrót do Home po ukończeniu.

Commit jest dozwolony dopiero po PASS.

## 7. Kryteria akceptacji

- [x] SPEC i PLAN opisują ten sam kontrakt.
- [x] Slime i `ANISHIFT` zostały zachowane.
- [x] Home zawiera branding, cztery opcje, hint i esencjonalną stopkę.
- [x] Stopka pokazuje katalog po lewej i wersję po prawej na Home oraz w Auto.
- [x] Aktywna opcja nie ma kolorowego tła.
- [x] `viewport.py` nie istnieje.
- [x] Nie istnieje dodatkowy `Live` ani wrapper; resize obsługuje wyłącznie watcher granicy promptów.
- [x] `anishift/utils/rich_console/**` jest czyste względem baseline'u.
- [x] Scheduler i serwisy domenowe są czyste względem baseline'u.
- [x] Przygotowanie Auto nie emituje widocznego stanu.
- [x] Zakazane etykiety D-004 nie występują w runtime.
- [x] Każdy plik ma jeden stabilny wiersz.
- [x] Wiersze są w naturalnej kolejności.
- [x] Fazy i przejścia odtwarzają D-003 oraz legacy `_PipelineProgressRows`.
- [x] Każdy MKV używa jednego procesu ekstrakcji dla audio i napisów oraz przekazuje
  wszystkie rzeczywiste procenty legacy.
- [x] Pula ekstrakcji i naturalny porządek tasków odpowiadają legacy.
- [x] Auto zachowuje `ready_first` oraz limit czterech równoległych plików LLM.
- [x] Auto syntetyzuje jeden plik TTS naraz bez zmniejszania współbieżności requestów.
- [x] Procent TTS jest prawdziwy i monotoniczny.
- [x] Nazwy z nawiasami nie zawierają dodatkowego backslasha.
- [x] Progress mieści się w jednej linii przy 80 kolumnach.
- [x] Procent pozostaje widoczny przy 80 kolumnach.
- [x] Seria szybkich zmian rozmiaru jest scalana i nie odkłada kolejki redrawów.
- [x] Terminalne wiersze pozostają do naciśnięcia klawisza.
- [x] Nie ma oddzielnego ekranu sukcesu ani listy produktów.
- [x] Expected error i `Ctrl+C` nie uszkadzają terminala.
- [x] Techniczne komendy CLI nadal ładują Interactive CLI leniwie.
- [x] Nie pozostał osierocony kod, test ani dokument odrzuconego rozwiązania.
- [x] Wszystkie bramki automatyczne przeszły po finalnej zmianie.
- [ ] Windows HITL otrzymał PASS.

## 8. Ryzyka i reakcje

| Ryzyko | Reakcja |
|---|---|
| Zdarzenia tasków przeplatają się | Agregować po stabilnym identyfikatorze pliku |
| Auto traci kolejkę użytkownika | Przekazywać zapisany snapshot bez nadpisywania limitów |
| Procent znika przy 80 kolumnach | Skrócić opis, potem ukryć czas |
| Nawiasy są podwójnie escapowane | Przekazywać surowy tekst i testować renderer |
| Ciche przygotowanie trwa długo | Pozostawić markę i stopkę bez fałszywego paska |
| Wiersze znikają po sukcesie | Utrzymać manager do naciśnięcia klawisza |
| Pojawia się pokusa kopiowania legacy | Portować zachowanie na `RunEvent` |

## 9. Polityka blokera

Jeżeli `RunEvent` nie dostarcza danych koniecznych do publicznej fazy lub realnego
postępu, wykonawca zatrzymuje dany krok i aktualizuje plan na podstawie dowodów.
Nie dodaje eventu wyłącznie pod UI bez osobnej decyzji.

Jeżeli publiczne API `MultiProgressManager` nie pozwala zachować jednej linii przy
80 kolumnach po skróceniu etykiet i ukryciu czasu, wykonawca zatrzymuje się przed
modyfikacją `anishift/utils/rich_console/**` i przedstawia minimalny reproducer.

## 10. Wynik planu

Po wykonaniu powstaje prosty Interactive CLI oparty na obecnym backendzie:
zaakceptowany branding na Home oraz historycznie znajomy, plikowy model postępu
w Auto. Eksperymentalna warstwa viewportu, technicznych statusów i odwzorowania
tasków na osobne wiersze zostaje usunięta razem z testami i dokumentacją, które
istniały tylko dla niej.
