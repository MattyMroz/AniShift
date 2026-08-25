# Etap 10 - wymagania TUI AniShift

**Status:** READY
**Baseline kontraktu:** `6849f32d4b197aff3507266e55f3d7fbb5c674d4`
**Audytowana gałąź:** `feature/stage-9-product-tui`
**Referencja OpenCode:** `03bba464d46f3eddf74195919b1344aa937f7b11`

> Ten dokument definiuje CO ma powstać. Szczegóły JAK i kolejność zmian są w `plan.md`.

## 1. Cel

Zastąpić odrzuconą warstwę prezentacji AniShift jednym szybkim, zwartym i klawiaturowym TUI, które wygląda i zachowuje się spójnie z gramatyką OpenCode, ale pozostaje natywną warstwą Python/Textual nad istniejącym `AppService`. Użytkownik ma móc wejść do aplikacji, nacisnąć pusty Enter i uruchomić domyślny Auto bez szukania komendy, a wszystkie ustawienia mają być edytowane pojedynczo, przewidywalnie i bez wielkiego formularza.

## 2. Aktualna prawda systemu

- Backend Etapu 9 istnieje w `anishift/application/` i udostępnia discovery, planning, execution, cancel, settings, doctor i setup przez `AppService`.
- Aktualne `anishift/tui/` jest prototypem odrzuconym wizualnie i funkcjonalnie; nie jest źródłem docelowego designu.
- Domyślny punkt wejścia po revercie uruchamia starą powłokę `prompt-toolkit`.
- `field_catalog.py`, `UserSettings`, `presets.py` i `env_file.py` zapewniają typowane pola oraz atomowe wzorce zapisu.
- Rejestr LLM obsługuje dotychczasowych providerów, ale nie ma adaptera Palantir Foundry ani katalogu modeli AniShift.
- Użytkownik wskazał osobny `opencode.corrected.jsonc` z providerami i modelami Foundry. Jego treść nie znajduje się w bieżącym zestawie plików, dlatego SPEC nie zakłada żadnego konkretnego aliasu, RID-u ani endpointu; jeśli plik zostanie dostarczony wykonawcy, wolno użyć wyłącznie jego sanityzowanej części modelowej.

## 3. Wymagania biznesowe

- **BR-001:** Podstawowa ścieżka Auto ma wymagać jednego świadomego działania: pustego Enter.
- **BR-002:** Interfejs ma zmniejszać liczbę decyzji i ekranów, a nie przenosić złożoność backendu na użytkownika.
- **BR-003:** Zmiana TUI nie może obniżyć poprawności istniejącego pipeline'u ani odwracalności produktów.
- **BR-004:** Konfiguracja modeli Foundry ma być jawna, lokalna i bezpieczna, bez zgadywania modeli dostępnych na koncie.

## 4. Zakres

### W zakresie

- kompletna wymiana TUI i wejścia no-subcommand;
- statyczne logo, motywy, composer, paleta, dokładnie 14 slash commands;
- dialogi i edycja pełnego katalogu ustawień;
- konfiguracja kluczy, Palantir Foundry, lokalny katalog modeli i dwa niezależne wybory modelu;
- workspace, Auto, Manual, Preview, Execution, Results i narzędzia diagnostyczne;
- Windows Terminal, kodowanie konsoli, responsywność, testy, parytet i usunięcie starej ścieżki po bramce akceptacji.

### Odłożone

- agent konwersacyjny obsługujący zwykły tekst;
- `/variant` i prawdziwe profile reasoning;
- automatyczne pobieranie anime, MyAnimeList i pluginy UI;
- automatyczne odkrywanie modeli z nieudokumentowanego endpointu enrollment;
- preview głosu TTS wymagające płatnej syntezy.

### Poza zakresem

- migracja AniShift do TypeScript/OpenTUI;
- przeprojektowanie domeny ekstrakcji, tłumaczenia, TTS, audio lub composition bez bezpośredniej potrzeby TUI;
- przechowywanie tokenów w plikach JSON/JSONC;
- pikselowe snapshoty terminala jako jedyny dowód wyglądu.

## 5. Zamknięte decyzje produktu

| Komenda | Znaczenie |
| --- | --- |
| /init | Inicjalizacja workspace i konfiguracji; pokazuje dalsze kroki, nie uruchamia przebiegu. |
| /connect | Konfiguracja połączenia Palantir Foundry i jawny, potwierdzony test jednego modelu. |
| /status | Bezpieczne podsumowanie konfiguracji, workspace, wybranych modeli i aktywnego przebiegu. |
| /debug | Rozszerzona, zredagowana diagnostyka bez sekretów i treści użytkownika. |
| /help | Lista komend i aktualnych skrótów z żywego rejestru. |
| /exit | Wyjście z aplikacji; przy aktywnym przebiegu wymaga potwierdzenia. |
| /auto | Konfiguracja domyślnego trybu Auto i presetów; nigdy nie uruchamia przetwarzania. |
| /manual | Ręczne przygotowanie intencji grup; zawsze prowadzi przez Preview i jawny Start. |
| /model | Wybór głównego modelu Palantir z lokalnego katalogu modeli. |
| /translation | Ustawienia tłumaczenia, w tym niezależny model LLM do tłumaczenia. |
| /prompts | Wybór promptu zadania, stylu i modułów promptu. |
| /tts | Ustawienia TTS, głosów, audio i kluczy związanych z TTS. |
| /theme | Wybór motywu z podglądem na żywo i rollbackiem po Esc. |
| /doctor | Uruchomienie diagnostyki technicznej bez automatycznej naprawy. |

Dodatkowe decyzje zamknięte:
- `/variant` nie powstaje w tym etapie.
- Refresh, Cancel, Preview, Results i Back są akcjami kontekstowymi bez slasha.
- Zwykły tekst niczego nie wykonuje.
- Pusty Enter uruchamia dokładnie jeden domyślny Auto.
- `/auto` konfiguruje, ale nie uruchamia.
- Manual zawsze przechodzi przez Preview i Start.
- Ustawienia zapisują pojedyncze pole po Enter; Esc nie zapisuje; globalnego Save nie ma.


### 5.1. Kontrakt wykonania komend

| Komenda | Widoczna zawsze | Warunek wykonania | Dozwolone skutki uboczne | Niedozwolone skutki |
| --- | --- | --- | --- | --- |
| `/init` | tak | aplikacja uruchomiona | utworzenie brakujących lokalnych plików/katalogów po potwierdzeniu; przejście do diagnostyki | start workflow, test modelu, automatyczna instalacja bez zgody |
| `/connect` | tak | wpis katalogu i dane połączenia mogą być niekompletne | edycja URL/tokena; jeden jawnie potwierdzony probe | probe przy samym otwarciu, więcej niż jedno żądanie, pokazanie tokenu |
| `/status` | tak | brak | odczyt bezpiecznej projekcji stanu sesji i konfiguracji | odczyt pełnego `Settings`, payloadów albo treści plików użytkownika |
| `/debug` | tak | brak | rozszerzona, zredagowana projekcja diagnostyczna | stack trace, nagłówki, response body, tokeny, prompty, napisy/TTS text |
| `/help` | tak | brak | odczyt żywego rejestru komend i skrótów | ręcznie utrzymywana druga lista komend |
| `/exit` | tak | brak; aktywny run wymaga potwierdzenia | bezpieczne zamknięcie aplikacji | niejawne anulowanie albo porzucenie aktywnego runu |
| `/auto` | tak | workspace może być pusty | wybór/edycja presetów Auto | `plan_auto`, `execute`, provider probe |
| `/manual` | tak | workspace może być pusty | otwarcie ręcznych draftów; przy pustym workspace czytelny empty state | automatyczny Start bez Preview |
| `/model` | tak | katalog może być pusty | wybór `primary_model_alias` | zmiana modelu tłumaczeniowego, probe przy filtrowaniu |
| `/translation` | tak | brak | edycja translation settings i `translation_model_alias` | zmiana modelu głównego, automatyczny request |
| `/prompts` | tak | brak | edycja prompt/style/modules z istniejącego `PromptRegistry` | edycja surowego promptu systemowego w tym etapie |
| `/tts` | tak | brak | edycja TTS, głosu, profilu i audio | płatny odsłuch, provider probe przy przeglądaniu |
| `/theme` | tak | brak | live preview oraz zapis wyboru po Enter | trwały zapis przy Esc |
| `/doctor` | tak | brak | uruchomienie `AppService.doctor()` w workerze | automatyczny setup/naprawa |

Komenda może być chwilowo niewykonalna, ale pozostaje widoczna z konkretnym powodem, jeżeli jej brak z listy utrudniłby użytkownikowi znalezienie ścieżki naprawy. Akcje kontekstowe są widoczne w palecie tylko wtedy, gdy ich predykat `enabled` jest prawdziwy; nie zwiększają liczby komend slash.

### 5.2. Kontrakt akcji kontekstowych

| Akcja | Typowe miejsce | Warunek | Zachowanie |
| --- | --- | --- | --- |
| Refresh | Workspace | discovery nie jest już w locie | ponowne discovery; zachowanie selekcji istniejących group ID |
| Preview | Auto/Manual | draft daje się zmaterializować | budowa `ExecutionPlan`; bez `execute` |
| Start | Preview | `can_execute`, brak aktywnego runu | ewentualny Confirm, następnie dokładnie jedno `execute` |
| Cancel | Execution | run `running`/`cancelling` | Confirm, jedno idempotentne `AppService.cancel(run_id)` |
| Results | ekrany główne | wynik istnieje w sesji | otwarcie zachowanego `RunResult` |
| Back | ekrany/dialogi | zależnie od kontekstu | powrót bez niejawnego zapisu i bez anulowania runu |
| Setup | Init/Doctor | użytkownik jawnie wybiera akcję | `AppService.setup()` w workerze |
| Save preset | Auto | draft poprawny | `AppService.save_preset()`; nie uruchamia runu |

## 6. Gramatyka wizualna

Referencją nie jest interpretacja OpenCode, lecz jego zmierzone wartości. Wszystkie liczby i reguły w tej sekcji pochodzą z zainstalowanej binarki `opencode-ai` (wbudowany motyw `opencode`, wariant `Xa` w rejestrze motywów) oraz z dokumentacji `opencode.ai/docs/themes` i `opencode.ai/docs/keybinds`. Nazwy tokenów są celowo takie same jak w OpenCode, żeby porównanie było bezpośrednie.

### Nazwy tokenów

Piętnaście tokenów, identyczne jak w schemacie `opencode.ai/theme.json`:
`primary`, `secondary`, `accent`, `error`, `warning`, `success`, `info`, `text`, `textMuted`, `background`, `backgroundPanel`, `backgroundElement`, `border`, `borderActive`, `borderSubtle`.

### Motyw ciemny
| Token | Wartość | Rola |
| --- | --- | --- |
| background | #0a0a0a | tło aplikacji |
| backgroundPanel | #141414 | tło dialogu i panelu |
| backgroundElement | #1e1e1e | tło elementu wewnątrz panelu |
| borderSubtle | #3c3c3c | podział bez znaczenia |
| border | #484848 | zwykła krawędź |
| borderActive | #606060 | krawędź elementu aktywnego |
| primary | #fab283 | **jedyny akcent** — zaznaczenie, kursor, aktywna krawędź |
| textMuted | #808080 | tekst drugorzędny |
| text | #eeeeee | tekst pierwszorzędny |
| secondary | #5c9cf5 | rzadkie wyróżnienie strukturalne |
| accent | #9d7cd8 | nagłówek grupy na liście |
| error | #e06c75 | stan terminalny nieudany |
| warning | #f5a742 | ostrzeżenie |
| success | #7fd88f | stan terminalny udany |
| info | #56b6c2 | informacja neutralna |

### Motyw jasny
| Token | Wartość |
| --- | --- |
| background | #ffffff |
| backgroundPanel | #fafafa |
| backgroundElement | #f5f5f5 |
| borderSubtle | #d4d4d4 |
| border | #b8b8b8 |
| borderActive | #a0a0a0 |
| primary | #3b7dd8 |
| textMuted | #8a8a8a |
| text | #1a1a1a |
| secondary | #7b5bb6 |
| accent | #d68c27 |
| error | #d1383d |
| warning | #d68c27 |
| success | #3d9a57 |
| info | #318795 |

Skala neutralna ma dwanaście stopni i jeden nasycony akcent na wariant. W ciemnym akcentem jest ciepły `#fab283`, w jasnym niebieski `#3b7dd8`. Kolory semantyczne istnieją, ale opisują wyłącznie stan terminalny lub ostrzeżenie — nigdy zaznaczenie, focus ani dekorację.

### 6.0. Hierarchia tekstu

Tekst nie jest jednolity. Waga, odcień i tło wynikają ze stanu, według reguł zmierzonych w komponencie listy OpenCode:

| Element | Tło | Kolor tekstu | Waga |
| --- | --- | --- | --- |
| wiersz zaznaczony, tytuł | `primary` | kontrast do `primary` | **bold** |
| wiersz zaznaczony, etykieta | `primary` | kontrast do `primary` | normalna |
| wiersz zwykły, tytuł | brak | `text` | normalna |
| wiersz zwykły, etykieta | brak | `textMuted` | normalna |
| wiersz nieaktywny | brak | `textMuted` | normalna |
| nagłówek grupy | brak | `accent` | **bold** |
| tytuł dialogu | brak | `text` | **bold** |
| afordancja `esc` | brak | `textMuted` | normalna |
| placeholder filtra | brak | `textMuted` | normalna |
| kursor | — | `primary` | — |
| pusty wynik | brak | `textMuted` | normalna |

Kontrast do `primary` liczy się luminancją `0.299r + 0.587g + 0.114b`: powyżej `0.5` tekst czarny, poniżej biały. Dla `#fab283` luminancja to `0.76`, więc zaznaczony wiersz ma **czarny bold na ciepłym tle**. Reguła jest wyliczana, nie wpisana na sztywno, więc trzyma się każdego motywu.

Zasada nadrzędna: zaznaczenie sygnalizuje **tło plus bold**, nie zmiana barwy tekstu na kolejny hue. Stan drugorzędny sygnalizuje **wyblakły odcień**, nie mniejszy rozmiar.

### Gęstość i układ

- wiersz listy ma wysokość 1; opis pojawia się w podświetlonym wierszu albo panelu szczegółów;
- standardowy padding panelu: 1 wiersz pionowo i 2 kolumny poziomo;
- dialogi nie mają ozdobnej ramki, odróżnia je tło `backgroundPanel` na zasłonie;
- zasłona dialogu to czarne tło z alfa `150/255`;
- szerokość dialogu jest skokowa: `60` domyślnie, `88` dla dużego, `116` dla bardzo dużego, zawsze przycięta do `terminal - 2`;
- dialog startuje na wysokości `terminal / 4` od góry i jest wyśrodkowany poziomo;
- nagłówek dialogu ma padding poziomy 4, lista padding poziomy 1, nagłówek grupy padding lewy 3;
- pasek przewijania listy jest ukryty;
- jedna główna powierzchnia ma pierwszeństwo przed wieloma kartami;
- logo znika przed funkcjonalnymi kontrolami przy małym terminalu;
- composer i stopka nie mogą zniknąć z powodu resize.


### 6.1. Kanoniczny układ dużego terminala

Referencją jest ekran startowy OpenCode. **Zero obramowań, zero pasków kart, zero nagłówka aplikacji.** Ekran startowy to wyśrodkowany pionowo i poziomo blok treści na tle `background`, z jednowierszowym pasem dolnym przyklejonym do dolnej krawędzi.

```text

                      █████╗ ███╗   ██╗██╗███████╗██╗  ██╗██╗███████╗████████╗
                     ██╔══██╗████╗  ██║██║██╔════╝██║  ██║██║██╔════╝╚══██╔══╝
                     ███████║██╔██╗ ██║██║███████╗███████║██║█████╗     ██║
                     ██╔══██║██║╚██╗██║██║╚════██║██╔══██║██║██╔══╝     ██║
                     ██║  ██║██║ ╚████║██║███████║██║  ██║██║██║        ██║
                     ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝

               ▌ Ask anything or press enter to dub
               ▌
               ▌ Auto · Foundry: Claude Opus 5

                 enter  auto      ctrl+p  commands

                     ● Tip  Drop an MKV into workspace to begin

 ~\Desktop\PROJECTS\AniShift:feature/stage-10-tui                    0.1.0
```

Elementy bloku, w kolejności z góry:

1. **logo** — statyczne, sześciowierszowe, wyśrodkowane, szerokość 57 kolumn; rysowane blokiem pełnym `█` z cieniem `╗╚═║╝`, nie ręcznie składanymi półblokami. `ANI` zajmuje kolumny 0–20 i jest stonowane w `textMuted`, `SHIFT` zajmuje kolumny 21–56 i jest wyróżnione w `primary`;
2. **box composera** — tło `backgroundElement`, **pionowy akcent na lewej krawędzi** w kolorze `primary`, bez obramowania; wewnątrz pole wejścia, a pod nim wyblakła **linia kontekstu** `tryb · provider: model` w `textMuted`;
3. **podpowiedzi klawiszy** — klawisz w kolorze `text`, etykieta w `textMuted`, maksymalnie dwa słowa na etykietę, czytane z żywego rejestru;
4. **linia tipu** — kropka w `warning` plus jedno krótkie zdanie; opcjonalna.

**Pas dolny** jest zawsze widoczny: po lewej skrócona ścieżka roboczej lokalizacji z gałęzią gita w formie `ścieżka:gałąź`, po prawej wersja aplikacji. Pas dolny **nie** jest panelem statusu przebiegu — stan przebiegu należy do ekranu roboczego.

Po wejściu w pracę logo i tip ustępują miejsca jednej dominującej powierzchni: liście, tabeli albo planowi. Composer zostaje na dole, pas dolny zostaje na dole. Panel szczegółów pojawia się tylko wtedy, gdy realnie pomaga aktualnej decyzji.

Podstawową nawigacją są composer, paleta i lokalne skróty ekranu.

### 6.1.1. Niezmienniki geometrii

Łamanie któregokolwiek jest błędem kontraktu, nie kwestią estetyki:

- obszar roboczy **dominuje** — dostaje całą wysokość pozostałą po logo, composerze i pasie dolnym;
- composer i pas dolny **mieszczą się w widocznym obszarze** przy każdym rozmiarze terminala; element wyrenderowany poza `y < 0` albo `y >= wysokość` jest usterką, nawet jeśli pozostaje zamontowany w DOM;
- żaden element nie ma obramowania; warstwy odróżnia wyłącznie tło i akcent krawędziowy;
- padding panelu to 1 wiersz pionowo i 2 kolumny poziomo.

### 6.2. Kanoniczny układ małego terminala

Przy szerokości lub wysokości poniżej pełnego progu:

- logo przechodzi do jednowierszowego `ANISHIFT` albo znika;
- tip znika pierwszy, przed jakimkolwiek funkcjonalnym elementem;
- panel szczegółów zostaje zwinięty;
- tabela ogranicza kolumny do identyfikatora/nazwy, zaznaczenia i stanu;
- composer oraz pas dolny pozostają **widoczne**, nie tylko zamontowane;
- pas dolny skraca ścieżkę od lewej, zachowując gałąź i wersję;
- dialog ogranicza szerokość do `terminal - 2` i przewija własną zawartość;
- użytkownik zawsze ma dostępną ścieżkę `/help` i `/exit`.

### 6.3. Teksty stanów bazowych

Napisy zwięzłe, bez kropki kończącej, bez zdań złożonych.

| Stan | Tekst bazowy | Znaczenie |
| --- | --- | --- |
| brak workspace | `No supported files in workspace` | brak źródeł, nie błąd aplikacji |
| discovery | `Scanning workspace…` | operacja lokalna w workerze |
| planning | `Building plan…` | `plan_auto` albo `plan_manual`, jeszcze bez wykonania |
| running | `Working` + bieżąca operacja | aktywny run |
| cancelling | `Cancelling…` | prośba wysłana, run jeszcze nie jest terminalny |
| partial | `Partly done` | co najmniej jeden trwały produkt lub sukces grupy oraz co najmniej jeden problem |
| failed | `Not finished` | brak wymaganego sukcesu; szczegóły bezpiecznie zredagowane |
| model unknown | `unverified` | wpis istnieje lokalnie, ale bieżąca sesja go nie sprawdziła |
| secret missing | `missing` | wartość nie jest skonfigurowana |
| secret configured | `configured` | wartość istnieje, ale nigdy nie jest wyświetlana |

### 6.4. Kontrakt skrótów klawiszowych

Skróty odwzorowują domyślne `keybinds` OpenCode. Wartości pochodzą z rejestru skrótów w binarce i z `opencode.ai/docs/keybinds`.

| Akcja | Skrót | Nazwa w OpenCode |
| --- | --- | --- |
| wyjście z aplikacji | `ctrl+c`, `ctrl+d` | `app_exit` |
| lista komend | `ctrl+p` | `command_list` |
| przerwanie przebiegu | `escape` | `session_interrupt` |
| zatwierdzenie wejścia | `enter` | `input_submit` |
| nowa linia w wejściu | `shift+enter`, `ctrl+enter`, `alt+enter`, `ctrl+j` | `input_newline` |
| czyszczenie wejścia | `ctrl+c` | `input_clear` |
| początek/koniec linii | `ctrl+a` / `ctrl+e` | `input_line_home` / `input_line_end` |
| usunięcie do końca/początku linii | `ctrl+k` / `ctrl+u` | `input_delete_to_line_end` / `input_delete_to_line_start` |
| usunięcie słowa wstecz | `ctrl+w`, `ctrl+backspace`, `alt+backspace` | `input_delete_word_backward` |
| ruch o słowo | `alt+left` / `alt+right`, `ctrl+left` / `ctrl+right` | `input_word_backward` / `input_word_forward` |
| dialog: poprzedni | `up`, `ctrl+p` | `dialog.select.prev` |
| dialog: następny | `down`, `ctrl+n` | `dialog.select.next` |
| dialog: strona | `pageup` / `pagedown` | `dialog.select.page_up` / `page_down` |
| dialog: skraj | `home` / `end` | `dialog.select.home` / `end` |
| dialog: zatwierdzenie | `enter` | `dialog.select.submit` |
| dialog: zamknięcie | `escape`, `ctrl+c` | zamknięcie dialogu |
| autocomplete: poprzedni | `up`, `ctrl+p` | `prompt.autocomplete.prev` |
| autocomplete: następny | `down`, `ctrl+n` | `prompt.autocomplete.next` |
| autocomplete: ukrycie | `escape` | `prompt.autocomplete.hide` |
| autocomplete: wybór | `enter` | `prompt.autocomplete.select` |
| autocomplete: dopełnienie | `tab` | `prompt.autocomplete.complete` |

**`input_newline` jest odłożone.** Composer stoi na jednoliniowym `Input`, w którym nowa linia nie ma znaczenia, więc te cztery skróty nie są zaimplementowane. Spełnienie ich wymaga wieloliniowego widgetu, a ten ma sens dopiero razem z treścią, która potrzebuje wielu linii. Takiej treści dziś nie ma i nie jest potwierdzone, że będzie: tryb czatu nie jest zaplanowany, a docelowy przepływ to jedno uruchomienie bez pisania, później scheduler bez udziału użytkownika. Do czasu, gdy pojawi się udowodnione zastosowanie, ten wiersz tabeli pozostaje niespełniony świadomie, a nie przez przeoczenie.

**Rozstrzyganie kolizji.** Ten sam skrót ma różne znaczenie zależnie od tego, co jest otwarte. Pierwszeństwo od najwęższego kontekstu:

1. `ctrl+p` — gdy otwarty jest dialog albo autocomplete, przechodzi do poprzedniej pozycji; w przeciwnym razie otwiera listę komend;
2. `ctrl+c` — gdy otwarty jest dialog, zamyka dialog; gdy composer ma treść, czyści treść; gdy composer jest pusty, wychodzi z aplikacji;
3. `escape` — gdy otwarty jest autocomplete, chowa autocomplete; gdy otwarty jest dialog, zamyka dialog; gdy trwa przebieg, przerywa przebieg;
4. `enter` — gdy otwarty jest autocomplete lub dialog, zatwierdza pozycję; w przeciwnym razie zatwierdza composer.

Klawisz nieobsłużony w węższym kontekście przechodzi do szerszego. Skrót, którego bieżący kontekst nie obsługuje, nie może wykonać cichej akcji w innym kontekście.

## 7. Wymagania systemowe

### R-001 - Platforma i framework

Interfejs pozostaje w Pythonie 3.14+ i Textual. Etap nie dodaje TypeScriptu, OpenTUI, procesu Node ani mostu między dwoma runtime'ami.

### R-002 - Domyślny tryb uruchomienia

Po zakończeniu migracji wywołanie `anishift` bez subkomendy otwiera nowe TUI. Subkomendy techniczne i nieinteraktywne nie uruchamiają Textual.

### R-003 - Statyczne logo

Ekran startowy pokazuje statyczne, sześciowierszowe logo blokowe `ANISHIFT` o szerokości 57 kolumn, **wyśrodkowane poziomo** w bloku startowym. Litery są rysowane pełnym blokiem `█` z cieniem `╗╚═║╝`, w jednym spójnym kroju o stałej metryce — nie ręcznie składanymi półblokami o różnej grubości. `ANI` jest stonowane w `textMuted`, `SHIFT` wyróżnione w `primary`. Nie ma maskotki, animacji ani dużego pełnoekranowego ASCII artu.

### R-004 - Układ główny

Pełny układ składa się z jednego dominującego obszaru roboczego, stale dostępnego composera i jednowierszowego pasa dolnego. **Nie ma paska nagłówka aplikacji** — kontekst nosi linia w boxie composera. Ekran startowy centruje blok logo, composera, podpowiedzi i tipu, zgodnie z 6.1.

Interfejs nie używa obramowań, siatki wielkich kart ani szerokich pustych odstępów. Composer i pas dolny pozostają widoczne w każdym rozmiarze terminala.

### R-005 - Motywy

Dostępne są co najmniej `anishift-dark` i `anishift-light`. Wszystkie kolory produkcyjnego TUI pochodzą z jednego modułu motywu i semantycznych zmiennych TCSS.

### R-006 - Stan nie tylko kolorem

Każdy stan ważny dla użytkownika ma słowo oraz glif albo pozycję strukturalną. Kolor jest wyłącznie dodatkowym sygnałem.

Tekst niesie stan także wagą i odcieniem, zgodnie z tabelą w 6.0. Jednolity tekst o jednej wadze i jednym odcieniu w całym widoku jest usterką kontraktu: pozycja zaznaczona musi różnić się tłem **i** wagą, a treść drugorzędna musi być wyblakła względem pierwszorzędnej. Zaznaczenie nigdy nie sygnalizuje się wprowadzeniem kolejnej barwy — tylko tłem `primary`, wyliczonym kontrastem i pogrubieniem.

### R-007 - Rozmiar terminala

Pełny układ obowiązuje od 100x30. Przy 80x24 aplikacja nadal pozwala wpisać komendę, otworzyć pomoc, odczytać stan i bezpiecznie wyjść; treści drugorzędne mogą zostać zwinięte.

### R-008 - Język interfejsu

Teksty interfejsu są **na razie po angielsku**, tak jak w OpenCode. Polski pozostaje językiem produktu wyjściowego — napisów, lektora i nazw generowanych plików.

Wybór języka powłoki jest **decyzją otwartą** i może zostać cofnięty na polski po ocenie działającego produktu. Dlatego:

- wszystkie napisy widoczne dla użytkownika żyją jako stałe `Final` w jednym module `anishift/tui/strings.py`, nigdy jako literały rozsiane po widgetach;
- **nie** powstaje warstwa i18n, katalog locale, przełącznik języka ani druga wersja napisów — tłumaczenie ma być zamianą jednego pliku, nie zbudowaniem mechanizmu;
- testy asertują przez te stałe, nie przez wpisane ręcznie napisy, żeby zmiana języka nie wywróciła zestawu testów.

Nazwy modeli, providerów, plików, kodów błędów i identyfikatory techniczne pozostają w oryginalnej formie niezależnie od języka powłoki.

### R-009 - Zwięzłość napisów

Etykieta akcji ma **maksymalnie dwa słowa** (`ctrl+p commands`, `tab agents`). Opis komendy w palecie to jedno zdanie bez kropki, do ośmiu słów. Komunikat stanu to fraza, nie zdanie złożone. Napis dłuższy niż to jest błędem kontraktu, a nie kwestią gustu — gęstość ekranu jest cechą produktu.

### R-010 - Jeden rejestr komend

Paleta, podpowiedzi slash, skróty i przyciski wykonują akcje przez jeden `CommandRegistry` i jeden punkt `dispatch`. Ekrany nie implementują równoległych ścieżek tej samej komendy.

### R-011 - Dokładnie 14 komend slash

Katalog slash zawiera dokładnie komendy wymienione w sekcji 5. Każda piętnasta komenda, w tym `/variant`, jest błędem kontraktu.

### R-012 - Akcje kontekstowe bez slasha

Refresh, Back, Preview, Start, Cancel, Results, Setup, Save preset i podobne akcje mogą istnieć w skrótach lub palecie, ale nie otrzymują `slash_name`.

### R-013 - Paleta i autocomplete

`Ctrl+P` otwiera paletę komend. Wpisanie `/` fokusuje composer i pokazuje maksymalnie 10 podpowiedzi. Ranking uwzględnia nazwę, opis i aliasy, wzmacnia dopasowanie prefiksowe i ma stabilne rozstrzyganie remisów.

### R-014 - Pomoc z żywego rejestru

`/help`, stopki dialogów i stopka ekranu odczytują nazwy akcji i skróty z aktualnego rejestru lub `BINDINGS`, bez ręcznie duplikowanych napisów.

### R-015 - Nieznana komenda

Nieznana komenda nie wykonuje żadnego use case'u i pokazuje najbliższą znaną nazwę, gdy istnieje wiarygodne dopasowanie.

### R-020 - Stały composer

Composer jest dostępny na każdym głównym ekranie. Placeholder brzmi: `Ask anything or press enter to dub`.

Composer renderuje się jako box na tle `backgroundElement` z pionowym akcentem `primary` na lewej krawędzi, bez obramowania. Pod polem wejścia stoi wyblakła linia kontekstu w `textMuted`, w formie `tryb · provider: model`.

### R-021 - Pusty Enter

Enter na pustym albo zawierającym wyłącznie białe znaki composerze uruchamia dokładnie jeden domyślny przebieg Auto.

### R-022 - Guard pustego Enter

Pusty Enter działa tylko wtedy, gdy composer ma fokus, nie jest otwarty modal, IME nie składa tekstu, klawisz nie jest powtórzeniem, żaden start nie jest w locie i nie trwa przebieg ani anulowanie.

### R-023 - Zachowanie domyślnego Auto

Domyślny Auto wybiera aktualnie zaznaczone grupy albo jawnie zdefiniowaną domyślną selekcję, pobiera domyślny preset, buduje plan lokalnie i na poprawnej zwykłej ścieżce przechodzi bez dodatkowego formularza do Execution. Potwierdzenie jest wymagane tylko dla nowego destrukcyjnego nadpisania lub innej jawnie oznaczonej nieodwracalnej czynności.

### R-024 - Semantyka `/auto`

`/auto` otwiera wybór lub edycję presetu. Nie wywołuje `execute`, nie wykonuje probe providera i nie udaje pustego Enter.

### R-025 - Zwykły tekst

Niepusty tekst bez prefiksu slash niczego nie wykonuje. Tekst pozostaje w composerze, a użytkownik dostaje krótki komunikat, że tryb rozmowy nie jest jeszcze dostępny.

### R-026 - Enter podczas przebiegu

Podczas stanu `running` albo `cancelling` pusty Enter nie tworzy drugiego przebiegu. Stopka pokazuje aktualny stan i dostępny Cancel.

### R-027 - Manual zawsze przez Preview

`/manual` otwiera ręczne przygotowanie. Przebieg ręczny nie może rozpocząć się bez poprawnego planu Preview i jawnego Start.

### R-030 - Wspólna rama dialogów

Dialogi używają jednej bezramkowej ramy modalnej, przyciemnionego tła, szerokości 60/88/116 ograniczonej do `terminal - 2`, przewijania wewnętrznego i przywrócenia poprzedniego fokusu.

### R-031 - SelectDialog

Jeden `SelectDialog` obsługuje pojedynczy wybór, grupowanie, wyszukiwanie, marker aktualnej wartości `●`, niezależny kursor, `Up/Down`, `PageUp/PageDown`, `Home/End`, Enter, Esc oraz opcjonalny tryb multi z przełączaniem przez Space.

### R-032 - Edytory wartości

Dostępne są `PromptDialog`, `NumberDialog`, `ConfirmDialog` i `ReorderDialog`. Liczby można wpisać oraz zmieniać krokiem; dla wartości dB domyślny krok wynosi 0.5, jeśli spec pola nie podaje innego.

### R-033 - Nawigacja drzewa

Wejście do edytora zastępuje dialog rodzica, a nie buduje nieograniczony stos. Enter zatwierdza i wraca do rodzica na edytowany wiersz; Esc wraca bez zapisu.

### R-034 - Walidacja inline

Niepoprawna wartość pozostaje w edytorze z konkretnym komunikatem. Enter nie zamyka edytora i nie powoduje częściowego zapisu.

### R-040 - Wejścia do ustawień

Nie istnieje monolityczna komenda `/settings`. Ustawienia są otwierane przez `/tts`, `/translation`, `/prompts`, `/theme`, `/model` i `/connect`, każda w swoim ograniczonym kontekście.

### R-041 - Pełne pokrycie katalogu

Każdy aktywny `SettingSpec` zwracany przez `setting_catalog()` ma edytor. Obsługa obejmuje wszystkie istniejące `SettingValueType`, zależności pól i profile głosów.

### R-042 - Mapowanie typów pól

Pole z listą wartości używa SelectDialog; tekst swobodny PromptDialog; liczba NumberDialog; boolean przełącznika inline; zbiór SelectDialog multi; lista uporządkowana ReorderDialog; lista obiektów krótkiego kreatora add/edit/remove.

### R-043 - Natychmiastowy zapis pola

Każde zatwierdzone pole tworzy odłączoną kopię ustawień, przypisuje jedną wartość, waliduje pełny kandydat i zapisuje go atomowo. Nie ma globalnego Save.

### R-044 - Esc nie zapisuje

Esc w edytorze pola nie zmienia obiektu w pamięci, pliku `settings.json`, `.env` ani aktywnego planu.

### R-045 - Sekrety

Wiersz sekretu pokazuje wyłącznie `skonfigurowany` albo `brak`. Edytor nie wyświetla dotychczasowej wartości. Niepuste zatwierdzenie ustawia sekret; usunięcie wymaga osobnej jawnej akcji.

### R-046 - Aktywacja sekretu

Sekrety są zapisywane atomowo do `.env`. Po zmianie TUI pokazuje, czy wartość została zapisana oraz czy do użycia przez pełny pipeline wymagany jest restart procesu. Jawny test `/connect` może użyć świeżo wpisanego kandydata bez ujawniania go.

### R-047 - Motyw live preview

`/theme` podgląda motyw przy ruchu kursora. Enter utrwala wybór w osobnym stanie UI; Esc przywraca motyw sprzed otwarcia.

### R-048 - Brak efektów ubocznych podczas przeglądania

Filtrowanie ustawień, modeli, głosów, promptów i komend nie wykonuje I/O sieciowego ani płatnych operacji.

### R-050 - Katalog modeli JSONC

Modele Palantir są opisane w wersjonowanym `config/anishift.models.jsonc`. Plik zawiera adres enrollment, relatywne trasy proxy dostawców, aliasy modeli, identyfikatory modelu, protokół, etykietę i opcjonalne bezpieczne metadane. Nie zawiera tokenu.

### R-051 - Początkowy katalog

Sanityzowana zawartość aktualnego `opencode.corrected.jsonc` może posłużyć do utworzenia `config/anishift.models.example.jsonc`. Kopiowane są wyłącznie providery, adresy proxy, identyfikatory, etykiety i limity; nie są kopiowane klucze, agenci, prompty ani pluginy.

### R-052 - Źródło dostępności

Obecność modelu w publicznej dokumentacji albo przykładzie nie oznacza dostępności w enrollment. TUI pokazuje tylko wpisy z lokalnego katalogu i oznacza je jako `niezweryfikowany`, `zweryfikowany` albo `błąd` w bieżącej sesji.

### R-053 - Token Palantir

Kanoniczny sekret to `ANISHIFT_PALANTIR_TOKEN`. Gdy go brakuje, odczyt może zgodnie z kompatybilnością użyć `FOUNDRY_API_TOKEN`, lecz `/connect` zapisuje wyłącznie nazwę kanoniczną.

### R-054 - Protokoły Foundry

Katalog może wskazać dokładnie jeden z czterech protokołów: OpenAI-compatible chat, Anthropic messages, Google generateContent albo xAI chat. Nieobsługiwany protokół pozostaje widoczny z błędem konfiguracji, a nie znika lub przechodzi na inny provider.

### R-055 - Picker `/model`

`/model` pokazuje wyłącznie skonfigurowane aliasy Palantir, grupuje je po providerze, pozwala filtrować i zmienia główny model bez zmiany modelu tłumaczeniowego.

### R-056 - Model tłumaczeniowy

`/translation` wybiera niezależny alias modelu używany tylko przez silnik tłumaczenia LLM. Zmiana modelu głównego nie zmienia tłumaczeniowego i odwrotnie.

### R-057 - Jawny `/connect`

`/connect` edytuje enrollment URL i token, pokazuje podsumowanie bez sekretu, ostrzega, że test połączenia może zużyć limit i wykonuje najwyżej jedno minimalne żądanie dopiero po potwierdzeniu.

### R-058 - Normalizacja odpowiedzi

Adapter Palantir mapuje odpowiedzi wszystkich wspieranych protokołów do istniejących `LlmResponse`, usage i finish reason bez przecieku providerowych struktur do tłumaczenia lub TUI.

### R-059 - Błędy Foundry

401/403, nieznany model/RID, 429, timeout, 5xx, blokada treści i nieprawidłowa odpowiedź są mapowane na istniejącą typowaną taksonomię LLM. Komunikat UI nie zawiera body, nagłówków autoryzacji ani podpisanych URL-i.

### R-060 - Zgodność istniejących providerów

Dotychczasowe silniki LLM pozostają dostępne wewnętrznie dla kompatybilności. Nowy picker modelu produktu nie miesza ich z katalogiem Palantir.

### R-070 - Workspace

Ekran startowy odkrywa grupy przez `AppService.discover()` poza wątkiem UI, pokazuje naturalnie sortowaną tabelę, stan zaznaczenia, konflikty i skrót artefaktów.

### R-071 - Stabilna selekcja

Odświeżenie zachowuje zaznaczenia istniejących grup, usuwa tylko grupy zniknięte i nie wybiera ukradkiem nowych plików, chyba że działa jawna polityka pierwszego uruchomienia.

### R-072 - Refresh bez slasha

Refresh jest akcją skrótu i palety. Nie istnieje `/refresh`.

### R-073 - Auto presets

`/auto` ładuje, wybiera i zapisuje presety przez publiczne API aplikacji. Edycja używa tych samych prymitywów pól co pozostałe ustawienia.

### R-074 - Walidacja Auto

Przed startem Auto wykrywa brak grup, brak domyślnego presetu, niezgodne produkty i wymagane zasoby. Błąd jest konkretny i nie uruchamia częściowego przebiegu.

### R-075 - Drafty Manual

Manual utrzymuje niezależny draft `GroupIntent` dla każdej grupy. Copy to selected kopiuje wartości, a nie współdzielone mutowalne obiekty.

### R-076 - Źródła zewnętrzne

Rejestracja napisów i audio odbywa się w workerze wyłącznie przez `AppService.register_external_*`, z ochroną generacji i anulowaniem.

### R-077 - Preview Manual

Manual nie może przejść do Start, dopóki każda wybrana grupa nie ma poprawnej intencji. Preview pokazuje wynik `plan_manual`, nie lokalną imitację planera.

### R-080 - Preview

Preview pokazuje grupy, wejścia, planowane operacje, produkty, problemy blokujące, skutki nadpisania i aktywne profile. Nie pokazuje sekretów ani pełnych prywatnych ścieżek.

### R-081 - Start

Start przyjmuje tylko `ExecutionPlan.can_execute == True`, ma atomowy guard przed podwójnym kliknięciem/Enter i dla destrukcyjnego nadpisania używa ConfirmDialog.

### R-082 - Execution

Execution prealokuje jeden stabilny wiersz na grupę, pokazuje stan słowem i glifem, aktualną operację, postęp oraz szczegóły retry i fallback.

### R-083 - Postęp

Częste zdarzenia postępu są koalescowane do maksymalnie 10 renderów na sekundę na zadanie. Zdarzenia terminalne są dostarczane bez oczekiwania na throttle.

### R-084 - Cancel

Cancel jest akcją klawisza i palety, nie komendą slash. Wymaga potwierdzenia, jest idempotentny i odróżnia żądanie anulowania od zamknięcia dialogu.

### R-085 - Results

Results rozdziela sukces, partial, failure i cancelled per grupa, pokazuje utworzone produkty i daje sensowną kolejną akcję.

### R-086 - Odzyskiwanie partial

Dla nieukończonej grupy Results może utworzyć draft Manual korzystający z trwałych produktów, bez ponownego wymuszania ukończonych etapów.

### R-090 - Status i debug

`/status` pokazuje bezpieczne podsumowanie. `/debug` dodaje wersje, klasy błędów, stan workerów i zredagowane detale, ale nie treści napisów, promptów, odpowiedzi providera, tokenów ani pełnych ścieżek.

### R-091 - Doctor

`/doctor` uruchamia `AppService.doctor()` poza wątkiem UI i renderuje status, komunikat oraz sugestię. Nie wykonuje automatycznej naprawy.

### R-092 - Init i setup

`/init` tworzy brakujące lokalne pliki i workspace przez publiczne granice aplikacji. Instalacja narzędzi jest osobną akcją `Setup` w palecie, nie nową komendą slash.

### R-093 - Help

`/help` pokazuje dokładnie aktualny katalog slash i skróty aktywnego kontekstu.

### R-094 - Exit

`/exit`, `Ctrl+Q` i `Ctrl+C` zamykają aplikację. Wszystkie trzy prowadzą przez tę samą komendę rejestru — nie istnieje druga ścieżka wyjścia.

`Ctrl+C` na poziomie aplikacji wychodzi, tak jak w OpenCode. Wewnątrz otwartego dialogu `Ctrl+C` anuluje dialog, bo priorytetowy binding ekranu ma pierwszeństwo; to jest zamierzone i nie tworzy drugiej ścieżki wyjścia.

Przy aktywnym przebiegu użytkownik wybiera powrót, anulowanie i wyjście albo pozostanie do końca; aplikacja nie zabija pracy bez potwierdzenia.

### R-100 - Wątek UI

Discovery, planowanie, wykonanie, doctor, setup, rejestracja plików i probe Foundry nie blokują wątku Textual. Widgety są modyfikowane tylko z wątku UI.

### R-101 - Generacje i run ID

Wynik wykonawcy lub zdarzenie z innej generacji UI albo innego `run_id` nie może zmienić bieżącego widoku.

### R-102 - Bounded event pump

EventBuffer jest drenowany okresowo tylko podczas aktywnego przebiegu. Bezczynne TUI nie przerysowuje się w nieskończonej pętli.

### R-103 - Redakcja

Błędy, powiadomienia i logi przechodzą przez istniejące reguły sanitizacji. Sekrety, prompt, napisy, tekst TTS, response body i prywatne ścieżki nie trafiają do zwykłej telemetrii.

### R-104 - Lazy startup

Start TUI nie konstruuje klientów sieciowych, nie wykonuje provider calls i nie skanuje katalogu modeli z sieci. Ładowanie katalogu jest lokalne.

### R-105 - Zgodność konfiguracji

Istniejący `settings.json` jest odczytywany bez utraty wartości. Nowe pola mają bezpieczne wartości domyślne, a migracja schematu nie usuwa ustawień providerów i głosów.

### R-106 - Kodowanie konsoli

Granica procesu ustawia UTF-8 z `errors=replace`, jeśli strumień wspiera `reconfigure`. Bezpośrednie uruchomienie w konsoli cp1250 nie kończy się `UnicodeEncodeError`.

### R-107 - Tryby CLI

Po migracji `doctor`, `setup` oraz `run --preset` pozostają nieinteraktywne. `run --preset` zwraca zero tylko dla pełnego sukcesu i kod niezerowy dla partial, failure lub cancelled.

### R-108 - Usunięcie legacy

Prompt-toolkit shell, stary panel i `anishift/pipeline/` są usuwane dopiero po dowodzie parytetu z `AppService`, akceptacji TUI i przełączeniu entrypointu. Zależność `prompt-toolkit` jest wtedy usuwana przez `uv remove`.

### R-109 - Windows CI

Repo uruchamia skupiony smoke TUI/CLI/launcher na Windows oraz dotychczasowe pełne bramki repo.

## 8. Inwarianty

- **I-001:** `anishift/application/` nie importuje Textual, TUI ani modułów CLI.
- **I-002:** TUI wykonuje workflow przez `AppService`; konkretne providery i media są konstruowane wyłącznie w composition/runtime boundary.
- **I-003:** Tokeny i klucze nie są zapisywane do JSON/JSONC, nie pojawiają się w `repr`, UI, logach ani wynikach testów.
- **I-004:** Istnieje jeden rejestr komend i jeden punkt dispatch.
- **I-005:** Katalog slash ma dokładnie 14 pozycji; `/variant`, `/refresh`, `/cancel`, `/preview`, `/results` i `/back` nie istnieją.
- **I-006:** Zwykły tekst nie uruchamia modelu, pipeline'u ani zapisu.
- **I-007:** Jeden fizyczny pusty Enter może utworzyć najwyżej jeden przebieg.
- **I-008:** `/auto` nie uruchamia przebiegu.
- **I-009:** Manual zawsze przechodzi przez Preview i jawny Start.
- **I-010:** Esc w edytorze nie powoduje trwałej zmiany.
- **I-011:** Model główny i model tłumaczeniowy są niezależne.
- **I-012:** Przeglądanie list i filtrowanie nie wykonuje requestów sieciowych.
- **I-013:** Spóźniony wykonawca lub obcy run nie zmienia aktualnego stanu.
- **I-014:** Drugi Start podczas aktywnego runu nie wywołuje `AppService.execute`.
- **I-015:** Stan ważny dla użytkownika nigdy nie jest komunikowany wyłącznie kolorem.
- **I-016:** Po F2 produkcyjne komponenty TUI nie zawierają placeholderów ani tekstów typu `arrives later`.
- **I-017:** Literalne kolory TUI są własnością jednego modułu motywu; TCSS używa zmiennych semantycznych.
- **I-018:** Model z przykładu lub publicznej listy pozostaje niezweryfikowany do czasu jawnego testu połączenia w bieżącej sesji.
- **I-019:** Legacy nie jest usuwane przed zielonym parytetem i akceptacją użytkownika.

## 9. Kryteria akceptacji

- **AC-001:** Uruchomiony prototyp pokazuje statyczne logo ANISHIFT, bez maskotki i bez animacji; ANI i SHIFT mają różne role semantyczne.
- **AC-002:** Przy 100x30 nie występuje nakładanie tekstów; przy 80x24 nadal działają composer, pomoc i wyjście.
- **AC-003:** Paleta, autocomplete i `/help` pokazują te same 14 komend slash, a `/variant` nie występuje nigdzie.
- **AC-004:** Nieznany slash wykonuje zero metod AppService i pokazuje sugestię.
- **AC-005:** Niepusty tekst bez slash pozostaje w composerze i wykonuje zero metod AppService.
- **AC-006:** Pusty Enter w stanie idle uruchamia jeden Auto; podwójny Enter i key repeat nadal wywołują dokładnie jeden start.
- **AC-007:** Pusty Enter podczas runu albo otwartego dialogu nie tworzy nowego przebiegu.
- **AC-008:** Wybranie `/auto` otwiera konfigurację i nie wywołuje planowania ani wykonania.
- **AC-009:** Manual bez poprawnych draftów nie przechodzi do Start; poprawny Manual pokazuje Preview i wymaga Start.
- **AC-010:** SelectDialog ma fokus na filtrze, osobny marker aktualnej wartości i kursor, a Esc przywraca wcześniejszy fokus.
- **AC-011:** NumberDialog odrzuca wartość poza zakresem, zachowuje tekst i stosuje właściwy krok klawiatury.
- **AC-012:** Każdy `SettingSpec` w reprezentatywnych kontekstach TTS/translation ma obsługiwany edytor.
- **AC-013:** Zatwierdzenie jednego pola wykonuje jeden atomowy zapis; Esc wykonuje zero zapisów.
- **AC-014:** Sekret jest widoczny wyłącznie jako `skonfigurowany` albo `brak`, a canary sekretu nie pojawia się w diffie, logu, powiadomieniu ani błędzie.
- **AC-015:** Filtrowanie modeli i ustawień wykonuje zero wywołań HTTP.
- **AC-016:** Katalog odrzuca rolę wskazującą nieistniejący alias oraz wpis z nieznanym protokołem.
- **AC-017:** Zmiana `/model` nie zmienia wyboru translation, a zmiana `/translation` nie zmienia modelu głównego.
- **AC-018:** `/connect` nie wykonuje testu połączenia bez potwierdzenia i po potwierdzeniu wykonuje najwyżej jedno minimalne żądanie.
- **AC-019:** Adapter mapuje reprezentatywne odpowiedzi OpenAI, Anthropic, Google i xAI do tego samego kontraktu `LlmResponse`.
- **AC-020:** 401/403/404/429/timeout/5xx dają właściwą klasę błędu i zredagowany komunikat.
- **AC-021:** Refresh zachowuje zaznaczenie grup istniejących i usuwa zaznaczenie tylko grup znikniętych.
- **AC-022:** Tabela workspace pozostaje sterowalna dla 100 grup i nie blokuje wpisywania do composera.
- **AC-023:** Prawidłowy pusty Enter buduje plan Auto i przechodzi do Execution bez otwierania formularza `/auto`.
- **AC-024:** Plan z destrukcyjnym nadpisaniem pokazuje Confirm; anulowanie nie uruchamia wykonania.
- **AC-025:** Spóźniony wynik discovery albo zdarzenie obcego runu jest ignorowane.
- **AC-026:** Execution pokazuje retry i fallback tekstowo, a terminalny stan pojawia się bez opóźnienia throttle.
- **AC-027:** Cancel jest potwierdzany, drugi Cancel nie zmienia wyniku i nie istnieje `/cancel`.
- **AC-028:** Results poprawnie rozdziela succeeded, partial, failed i cancelled oraz potrafi przejść z partial do niezależnego draftu Manual.
- **AC-029:** `/status`, `/debug` i `/doctor` nie ujawniają sekretu, promptu, napisów ani response body.
- **AC-030:** Podczas przebiegu testowego 20 grup composer i skróty pozostają responsywne.
- **AC-031:** Raport doctor zapisany przez strumień cp1250 nie rzuca `UnicodeEncodeError`.
- **AC-032:** No-subcommand uruchamia TUI; `doctor`, `setup` i `run --preset` nie importują i nie uruchamiają Textual na swojej ścieżce wykonania.
- **AC-033:** Przed usunięciem legacy hermetyczny test porównuje statusy, produkty i wywołania atrap dostawców dla starej ścieżki oraz AppService.
- **AC-034:** Po usunięciu legacy nie istnieją importy `prompt_toolkit` ani `anishift.pipeline`, a pełne bramki repo są zielone.
- **AC-035:** Użytkownik akceptuje prototyp w Windows Terminal przed rozpoczęciem F4.

## 10. Ograniczenia wykonawcze

- Python 3.14+, Textual i istniejące biblioteki repo pozostają podstawą.
- Zależności dodaje się wyłącznie przez `uv add`; usuwa przez `uv remove`.
- Testy dostawców używają atrap HTTP i sekretów testowych. Prawdziwy test połączenia występuje wyłącznie jako jawna akcja użytkownika.
- Implementacja nie kopiuje kodu SolidJS/OpenTUI z OpenCode; przenosi wyłącznie wzorce interakcji.
- User-specific enrollment URL, model RIDs i tokeny nie są commitowane.
- Wymagania aktualności modeli są rozwiązywane przez lokalny katalog użytkownika i jawny test połączenia, nie przez hardkodowaną listę w kodzie.

## 11. Pytania otwarte

Brak pytań produktowych blokujących plan. Konkretne aliasy i identyfikatory modeli są danymi środowiska użytkownika. Ich brak daje poprawny empty state i nie zmienia kontraktu TUI.

## 12. Podstawa

- `Badanie AniShift TUI.txt`: wiążące decyzje logo, pustego Enter, 14 komend, `/auto`, `/manual` i edycji pól.
- Wskazany przez użytkownika `opencode.corrected.jsonc`: opcjonalne źródło danych dopiero po faktycznym dostarczeniu wykonawcy; bez niego żaden konkretny alias/RID nie jest częścią kontraktu.
- Repo AniShift na baseline wskazanym w nagłówku: `AppService`, `field_catalog.py`, `user_settings.py`, `env_file.py`, rejestr LLM, legacy shell i odrzucone TUI.
- OpenCode na wskazanym commicie: `routes/home.tsx`, `component/logo.tsx`, `ui/dialog.tsx`, `ui/dialog-select.tsx`, `component/command-palette.tsx`, `component/dialog-model.tsx`.
- Oficjalne kontrakty Palantir dotyczące Model Catalog i provider-compatible proxy. Dostępność enrollment pozostaje danymi użytkownika.
