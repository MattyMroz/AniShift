# AniShift Interactive CLI — wymagania całego workstreamu

## 0. Status dokumentu

```text
STATUS: READY
AUTHORITY: wymagania produktu dla nowej warstwy prezentacji AniShift
BASELINE REPO: MattyMroz/AniShift
BASELINE BRANCH: feature/plain-cli
BASELINE COMMIT: bc0841bdd4bc192587f5b3eff5952ed7c4ee1c32
JĘZYK INTERFEJSU: polski
```

Ten dokument jest źródłem prawdy dla tego, **co ma zostać zbudowane** w ramach
Interactive CLI AniShift.

Dokument obejmuje cały kierunek produktu, nie tylko pierwszy etap:

```text
Home
Auto
Ustawienia
Ręczny
wynik przebiegu
polityka błędów
polityka retry/fallback
persistencja ustawień
modele i połączenia
maskotka
finalne domknięcie
```

Szczegółowa kolejność implementacji pierwszego pionowego wycinka znajduje się w
`01-plain-cli.md`.

Nie tworzymy dla tego workstreamu:

- pełnoekranowego TUI;
- kolejnego frameworka UI;
- systemu slash commands;
- command palette;
- dashboardu;
- web UI;
- edytora wszystkich parametrów backendu;
- autonomicznego systemu agentowego;
- osobnego `tasks.json`;
- kilku konkurencyjnych wersji requirements;
- sztucznego rozszerzania dokumentów pod liczbę linii.

Jeżeli późniejsze odkrycie techniczne zmieni wyłącznie sposób lokalnej implementacji,
aktualizuje się odpowiedni PLAN. Jeżeli zmieni zachowanie opisane tutaj, najpierw
aktualizuje się ten dokument i wraca z decyzją do użytkownika.

---

## 1. Problem, który rozwiązujemy

### 1.1. Stan produktu

AniShift ma działający backend odpowiedzialny za:

```text
discovery
inspection
planowanie Auto
planowanie Ręczne
ekstrakcję
normalizację napisów
tłumaczenie
podział napisów
TTS
audio
składanie MKV/MP4
publikację produktów
```

Problem nie polega na braku backendu. Problemem jest warstwa obsługi.

Wcześniej sprawdzono trzy podejścia:

1. REPL oparty na `prompt-toolkit` i komendach slash;
2. pełnoekranowy TUI oparty na Textual i wzorowany na OpenCode;
3. goły CLI uruchamiający domyślny preset bez interakcji.

Każde z nich miało istotną wadę:

- REPL wymagał wpisywania komend;
- Textual TUI był zbyt kosztowny w utrzymaniu i rozrósł się do osobnego produktu;
- goły CLI nie dawał wygodnej drogi do ustawień ani trybu ręcznego.

### 1.2. Docelowe rozwiązanie

Docelowym rozwiązaniem jest:

> **interaktywny CLI sterowany listami i prostymi formularzami, bez własnego
> routera ekranów i bez frameworka pełnoekranowego TUI.**

Jedna sesja Interactive CLI działa w jednym alternate screen terminala. Przejścia
Home → Auto → wynik → Home zastępują zawartość tego samego widoku, a wyjście
przywraca poprzedni bufor powłoki.

Warstwa prezentacji korzysta z:

```text
Questionary  -> wybór, checkbox, input, password, confirm
Rich         -> tekst, kolor, status, spinner, progress, podsumowanie
Typer        -> techniczne subkomendy i entrypoint procesu
Pillow       -> kompaktowe renderowanie dostarczonej maskotki jako półbloki terminalowe
```

### 1.3. Główny cel projektowy

Nowa funkcja produktu nie może automatycznie wymagać:

- nowego routera;
- nowego ekranu;
- nowego drzewa widgetów;
- nowego store UI;
- nowych eventów tylko na potrzeby prezentacji;
- kilkuset linii kodu layoutu;
- kopiowania ustawienia przez kilka warstw.

Koszt dodania normalnej opcji ma sprowadzać się przede wszystkim do:

1. dodania lub wykorzystania kontraktu domenowego;
2. dopisania pozycji do właściwego menu;
3. wskazania istniejącej operacji `AppService`;
4. dodania testu zachowania.

---

## 2. Terminologia

| Termin | Znaczenie |
|---|---|
| Interactive CLI | interaktywna pętla terminalowa z listami wyboru w jednym alternate screen, ale bez frameworka pełnoekranowego TUI |
| Home | główne menu z czterema akcjami |
| Auto | automatyczny przebieg na gotowych ustawieniach i domyślnym presecie backendu |
| Ręczny | wizard pozwalający nadpisać decyzje dla wybranych grup/odcinków |
| Ustawienia | kuratorowany interfejs do ustawień produktowych, nie pełny katalog techniczny |
| aktywna konfiguracja | jedna zapisana konfiguracja użytkownika wykorzystywana przez Auto i jako domyślna dla trybu Ręcznego |
| model catalog | `config/anishift.models.jsonc`, źródło providerów i aliasów modeli |
| progress deterministyczny | postęp oparty na rzeczywistym liczniku backendu |
| progress niedeterministyczny | praca, dla której backend zna tylko stan `started/done`, bez procentu |
| grupa | jeden rozpoznany odcinek lub inna jednostka wejściowa planowana przez application layer |
| retry | ponowna próba tego samego silnika |
| fallback | przejście do kolejnego silnika lub dostawcy zgodnie z konfiguracją backendu |
| maskotka | wizualny slime AniShift, opcjonalny względem działania pipeline’u |

---

## 3. Zasady nadrzędne produktu

### R-001 — Interactive CLI, nie TUI

Warstwa prezentacji musi być interaktywnym CLI.

Nie może przywracać:

- `textual`;
- `anishift/tui`;
- `Screen`;
- routera ekranów;
- reaktywnego store UI;
- globalnego command bara;
- slash completion;
- command palette.

### R-002 — automatyczne znaczy automatyczne

Najkrótszy poprawny przebieg użytkownika ma wyglądać tak:

```text
uv run anishift
Enter
```

Po `Enter` AniShift sam:

1. odczytuje aktywną konfigurację;
2. odkrywa materiały;
3. wybiera gotowe grupy;
4. buduje plan Auto;
5. wykonuje plan;
6. pokazuje wynik.

Nie wymaga wpisania `/run`, `auto`, nazwy presetu ani ścieżki.

### R-003 — ustawienia raz, użycie wielokrotnie

Użytkownik może ustawić potrzebne parametry raz. AniShift zapisuje je i stosuje w
kolejnych uruchomieniach.

Nie wymaga ponownego przechodzenia formularza przed każdym Auto.

### R-004 — jedna aktywna konfiguracja użytkownika

Pierwsza wersja Interactive CLI nie ma CRUD-u presetów użytkownika.

Nie istnieją w niej akcje:

```text
Dodaj preset
Kopiuj preset
Zmień nazwę presetu
Usuń preset
Importuj preset
Eksportuj preset
```

Backend może nadal używać `presets.json` jako swojego kontraktu workflow. Użytkownik
nie musi wiedzieć, że konfiguracja jest fizycznie rozdzielona między kilka plików.

### R-005 — kuratorowane ustawienia

Interfejs pokazuje tylko ustawienia, które mają sens jako decyzje użytkownika.

Nie renderuje automatycznie całego `field_catalog.py`.

### R-006 — parametry techniczne pozostają automatyczne

Domyślnie niewidoczne są m.in.:

```text
temperature
top_p
max_output_tokens
batch_size
retry limits
concurrency
timeouts
fallback internals
provider-native tuning
codec bitrate
scheduler internals
```

Mogą pozostać w kodzie, katalogu lub konfiguracji technicznej.

### R-007 — reuse zamiast przepisywania

Istniejące:

- `AppService`;
- `MultiProgressManager`;
- `ProgressBarManager`;
- `console`;
- semantyczne style Rich;
- eventy schedulera;
- atomowy zapis ustawień;
- zapis sekretów;
- katalog modeli;
- planowanie Auto i Ręczne;

muszą zostać wykorzystane, jeśli spełniają kontrakt.

### R-008 — brak fałszywych informacji

UI nie pokazuje:

- wymyślonego procentu;
- wymyślonego ETA;
- statusu `ready`, którego backend nie potwierdził;
- fikcyjnej dostępności modelu;
- sukcesu, gdy część grupy zakończyła się błędem.

### R-009 — język polski

Normalny interfejs użytkownika jest po polsku.

Dozwolone wyjątki:

- historyczne publiczne etapy progressu z R-603;
- nazwy providerów;
- nazwy modeli;
- identyfikatory głosów;
- nazwy kodeków;
- ścisłe komunikaty narzędzi zewnętrznych, jeśli nie da się ich bezpiecznie przetłumaczyć.

### R-010 — brak obowiązku używania myszy

Cały wymagany workflow działa klawiaturą.

Obsługa myszy nie jest kryterium akceptacji.

---

## 4. Architektura informacji

### 4.1. Home

Home zawiera dokładnie cztery akcje:

```text
Auto
Ręczny
Ustawienia
Wyjście
```

Nie zawiera piątej pozycji `Presety`.

Nie zawiera placeholdera `Dodaj anime`.

Nie zawiera `Pomoc`, `Doctor`, `Debug`, `Status`, `Connect` ani `Setup`.

### 4.2. Ustawienia

Menu Ustawienia zawiera docelowo:

```text
Tłumaczenie
Lektor
Wynik
Połączenia
Wróć
```

### 4.3. Ręczny

Tryb Ręczny jest wizardem:

```text
discovery
-> wybór grup
-> wybory per grupa
-> minimalne podsumowanie
-> wykonanie
-> wynik
```

Nie jest dashboardem ani trwałym edytorem konfiguracji.

### 4.4. Przebieg

Po wyborze Auto znika menu Home, ale marka pozostaje widoczna. Pod nią działa jeden
prosty widok przebiegu Rich. Esencjonalna stopka z katalogiem i wersją pozostaje
w ostatnim bezpiecznym wierszu bez przywracania osobnego viewportu.

### 4.5. Wynik

Po sukcesie użytkownik widzi ukończone wiersze postępu do naciśnięcia klawisza.
Przy błędzie lub anulowaniu widzi bezpieczny komunikat i może wrócić do Home.

---

## 5. Home — wygląd i zachowanie

### R-100 — dokładna zawartość Home

Home ma kolejność:

1. wycentrowany blok marki: kolorowa maskotka po lewej i wordmark po prawej;
2. odstęp;
3. cztery akcje;
4. hint sterowania pod listą;
5. stopkę z katalogiem po lewej i wersją po prawej.

### R-101 — tytuł

Pełny wordmark brzmi dokładnie:

```text
ANISHIFT
```

Używa istniejącego sześciowierszowego kroju o stałej szerokości 57 kolumn. Przy
zbyt małym terminalu przechodzi do jednoliniowego `ANISHIFT`.

### R-102 — kolor tytułu

Wordmark używa biało-srebrnego wypełnienia oraz kontrolowanego obrysu
cyjan–fiolet–róż pochodzącego ze slime'a. Nie używa ramki ani dodatkowego panelu.

Jeżeli terminal nie obsługuje koloru, całość pozostaje czytelna jako zwykły tekst.

### R-103 — maskotka w PLANIE 01

Home PLANU 01 renderuje dostarczony `slime_transparent_4k.png` jako kolorowe półbloki
terminalowe o stałym rozmiarze 20×14. Przezroczystość zachowuje normalne tło terminala.
Brak assetu lub błąd dekodowania degraduje widok do samego wordmarku i nie blokuje
produktu.

### R-104 — menu pod tytułem

Menu znajduje się pod blokiem marki jako zwarty blok wycentrowany w terminalu.

### R-105 — Auto jako pozycja domyślna

Po każdym wejściu na Home pozycją aktywną jest:

```text
Auto
```

### R-106 — brak dashboardu

Home nie pokazuje:

- modelu;
- providera;
- głosu;
- tempa;
- głośności;
- typu eksportu;
- liczby plików;
- statusu kluczy API;
- nazwy presetu;
- czasu ostatniego przebiegu;
- logów.

### R-107 — hint i stopka

Hint sterowania znajduje się bezpośrednio pod listą:

```text
↑↓ · Enter
```

Ostatni bezpieczny wiersz pokazuje bieżący katalog względem katalogu domowego po
lewej i wersję aplikacji po prawej. Stopka jest elementem esencjonalnym Home i Auto.

### R-109 — wąski terminal

Rozmiar jest odczytywany przy każdym renderze. Resize otwartego promptu kończy tylko
bieżące pytanie techniczne, czyści powierzchnię i natychmiast renderuje Home ponownie
z nowym wycentrowaniem.

### R-110 — czyszczenie powierzchni

Przed wejściem na Home poprzedni widok jest czyszczony.

Nie pozostawiamy pod Home starego progresu, odpowiedzi Questionary ani tracebacka.

### R-111 — powrót z podmenu

Powrót z podmenu ponownie renderuje czysty Home.

### R-112 — brak dodatkowej ramki

Home, tytuł i maskotka nie są otoczone ramką, panelem ani boxem.

### R-113 — brak opisu każdej pozycji

Cztery główne akcje nie mają długich opisów po prawej.

### R-114 — brak migania

Home nie odświeża się w pętli i nie używa ciągłego `Live`. Ponowny render następuje
wyłącznie po rzeczywistej zmianie wymiarów terminala.

### R-115 — wynik anulowania promptu

`Ctrl+C` na Home kończy aplikację bez tracebacka.

### R-116 — wycentrowany blok Home

Maskotka z wordmarkiem i menu tworzą zwarty blok wycentrowany poziomo i pionowo nad
stopką. Wszystkie wiersze bloku marki korzystają z jednego wspólnego przesunięcia.

### R-117 — wyrównanie menu

Blok menu jest wycentrowany względem terminala, ale jego etykiety są wyrównane do
lewej względem najdłuższej pozycji.

Nie centrujemy osobno każdego napisu `Auto`, `Ręczny`, `Ustawienia`, `Wyjście`.

### R-118 — brak markera przy lewej krawędzi terminala

Wskaźnik aktywnej pozycji jest częścią wycentrowanego bloku menu. Nie może znajdować
się przy skrajnej lewej krawędzi.

### R-119 — fallback geometrii

Gdy terminal jest wąski lub niski:

1. zmniejsz boczny padding;
2. ukryj maskotkę, zachowując pełny wordmark;
3. przełącz wordmark na jednoliniowy, jeśli pełny nie mieści się bez zawijania;
4. skróć katalog od lewej, zachowując wersję;
5. nie obcinaj czterech głównych akcji.

---

## 6. Sterowanie i znaczniki wyboru

### R-200 — podstawowe sterowanie

```text
↑ / ↓     przejście po liście
Enter     wybór lub zatwierdzenie
Space     zmiana elementu w multi-select
Ctrl+C    anulowanie bieżącego promptu lub bezpieczne wyjście
```

### R-201 — brak komend tekstowych

Użytkownik nie wpisuje:

```text
/auto
/settings
/manual
/run
```

### R-202 — nawigacja Home

Home używa wskaźnika po lewej:

```text
❯ Auto
  Ręczny
  Ustawienia
  Wyjście
```

### R-203 — brak zaznaczenia po prawej

Zakazane wzorce:

```text
Polskie napisy                         [x]
Polskie napisy                          ✓
Model                                  active
```

### R-204 — single select ustawienia

W selektorze wartości bieżąca zapisana wartość jest oznaczona po lewej:

```text
● Claude Sonnet
○ GPT
○ Gemini
```

Aktywny kursor może być pokazany kolorem lub pogrubieniem. Nie dokładamy drugiej
kolumny po prawej.

### R-205 — multi-select

Multi-select używa:

```text
● wybrane
○ niewybrane
```

Znacznik znajduje się przed tekstem.

### R-206 — zapis Enterem

Po wybraniu nowej wartości `Enter` zatwierdza jedną zmianę.

### R-207 — brak globalnego Save

Ustawienia nie mają wielkiego formularza z przyciskiem `Save`.

Każda zaakceptowana zmiana jest osobną transakcją.

### R-208 — anulowanie edycji

Anulowanie promptu nie zapisuje częściowej wartości.

### R-209 — akcja Wróć

Każde podmenu ma jawną pozycję:

```text
Wróć
```

Pierwsza wersja nie wymaga własnego keybindingu `Esc`, który obchodziłby publiczne
API Questionary.

### R-210 — listy długie

Długie listy, przede wszystkim modele i duża lista odcinków, mogą używać filtrowania
Questionary.

### R-211 — krótkie listy bez wyszukiwania

Home i krótkie menu ustawień nie uruchamiają wyszukiwania po przypadkowym wpisaniu
litery.

### R-212 — brak skrótów literowych

Nie pokazujemy automatycznych skrótów `1)`, `a)`, `b)` przy każdej pozycji.

---

## 7. System wizualny

### R-300 — minimalistyczna paleta

Interfejs używa przede wszystkim:

- koloru domyślnego terminala;
- bieli;
- szarości;
- jednego koloru akcentu.

### R-301 — akcent

Kolor akcentu Home to fiolet slime'a `#a855f7` i odpowiada za:

- aktywny wiersz;
- informację neutralną;
- wybrany element tam, gdzie potrzebne jest wyróżnienie.

### R-302 — kolory semantyczne

```text
zielony   -> sukces
żółty     -> ostrzeżenie / retry
czerwony  -> błąd
fioletowy -> aktywny wybór Home
niebieski -> informacja
szary     -> tekst pomocniczy
```

### R-303 — brak tęczy

Nie kolorujemy każdego etapu innym przypadkowym kolorem.

### R-304 — współdzielenie z Rich

Rich korzysta z istniejących semantycznych styli projektu.

Plan 01 nie przebudowuje całego `anishift/utils/rich_console/theme.py`.

### R-305 — styl Questionary lokalny

Questionary otrzymuje mały styl należący do Interactive CLI.

Nie monkeypatchujemy Questionary i nie forkamy biblioteki.

### R-306 — czytelność bez koloru

Informacja o stanie nie może zależeć wyłącznie od koloru.

Używamy również słów i symboli:

```text
✓
!
✗
Ponowna próba
Fallback
Anulowano
```

### R-307 — brak ciężkich ramek

Panele i boxy są używane oszczędnie.

### R-308 — jeden interaktywny widok

Interactive CLI przejmuje jeden alternate screen na cały czas sesji przez
cross-platformowy output Prompt Toolkit należący do granicy promptów. Home, Auto,
wynik i komunikaty zastępują zawartość tego samego widoku. Wyjście zawsze przywraca
poprzedni bufor powłoki i kursor.

### R-309 — redraw kontrolowany przez komponent

Questionary odświeża aktywny prompt, a Rich Progress/Live odświeża postęp w miejscu.
Zmiana widoku zaczyna się od wyczyszczenia alternate screen. Nie istnieje globalna
pętla UI. Krótko żyjący watcher rozmiaru działa wyłącznie podczas Home lub Auto,
scala serię szybkich zmian do najnowszych stabilnych wymiarów i wykonuje jeden redraw
bez odkładania kolejki poprzednich rozmiarów.

Zatwierdzona odpowiedź Questionary jest usuwana przed renderem następnego widoku.

### R-310 — polskie znaki

Interfejs poprawnie renderuje polskie znaki w Windows Terminal.

### R-311 — fallback kodowania

Granica procesu wymusza bezpieczne UTF-8 zgodnie z istniejącym CLI.

---

## 8. Maskotka

### R-400 — rola maskotki

Slime jest towarzyszem użytkownika i elementem marki.

Nie jest kontrolką ani źródłem informacji koniecznej do obsługi produktu.

### R-401 — niezależność od pipeline’u

Awaria maskotki nie może:

- zatrzymać startupu;
- zatrzymać Auto;
- zmienić wynik planowania;
- zablokować Settings;
- zmienić exit code;
- ukryć błędu backendu.

### R-402 — etap pierwszy

PLAN 01 używa dostarczonego transparentnego assetu i renderuje go przez Pillow jako
true-color terminal half blocks. Nie uruchamia Chafa ani subprocessu.

### R-403 — jeden źródłowy asset w Planie 01

PLAN 01 zawiera wyłącznie dostarczony `slime_transparent_4k.png`. Nie kopiuje:

- `slime_4k.png`;
- ikony iOS;
- wielomegabajtowych grafik roboczych.

### R-404 — docelowy renderer

Późniejsza animacja lub większy renderer może używać Chafa/Sixel w Windows Terminal.

### R-405 — fallback maskotki

Kolejność degradacji:

```text
Chafa/Sixel
-> statyczny tekst/ASCII
-> brak maskotki
```

W każdym wariancie menu pozostaje działające.

### R-406 — przyszłe stany

Docelowe stany maskotki:

```text
idle
discover
extract
translate
tts
audio
compose
success
error
```

### R-407 — przyszła animacja

Animacja jest osobnym etapem. Nie jest warunkiem ukończenia Home, Auto, Settings ani
Manual.

### R-408 — brak animacji w scrollbacku

Docelowa animacja nie może zostawiać kolejnych klatek w historii terminala.

### R-409 — rozmiar

Maskotka ma stały rozmiar 20×14 i nie skaluje się wraz z terminalem. Nie może spychać
menu poza typowy terminal 80×24.

### R-410 — centrum

Wariant bazowy umieszcza maskotkę po lewej stronie wordmarku. Cały połączony blok,
nie każdy element osobno, pozostaje wycentrowany.

---

## 9. Auto

### R-500 — wejście

Wybór `Auto` uruchamia domyślny preset wskazany przez backend.

Domyślny preset produktu żąda polskich napisów oraz narration audio, dlatego normalny
Auto obejmuje prawdziwe tłumaczenie, split, TTS, miks audio i publikację. Wybrany silnik
TTS nadal pochodzi z aktywnych ustawień użytkownika.

Auto zachowuje zapisane limity i politykę wykonania użytkownika. Dla `ready_first`
gotowa grupa natychmiast przechodzi do następnego etapu, a niezależne grupy mogą
przepływać między kolejkami ekstrakcji, LLM, TTS i audio. Naturalny porządek dotyczy
stabilnego układu wierszy i wyboru następnego oczekującego pliku, nie sztucznej
serializacji całego backendu. Dla obecnego limitu `llm_max_concurrency=4` mogą być
aktywne cztery pliki LLM jednocześnie. Synteza TTS pozostaje wyłączna dla jednego
odcinka, jak w legacy, przy zachowaniu współbieżności requestów providera.

### R-501 — wspólny backend

Auto używa publicznego `AppService`.

Interactive CLI nie importuje:

- schedulera;
- handlerów;
- konkretnych services;
- prywatnych helperów planera.

### R-502 — sekwencja

```text
discover
-> default_preset_id
-> get_preset
-> ready_group_ids
-> plan_auto
-> execute
```

### R-503 — jedno discovery

Jeden Auto przebieg używa jednego wyniku discovery do zbudowania planu.

### R-504 — pusty workspace

Brak źródeł:

- nie uruchamia planera;
- pokazuje krótki komunikat;
- nie wyświetla tracebacka;
- pozwala wrócić do Home.

### R-505 — brak gotowych grup

Jeżeli grupy istnieją, lecz żadna nie jest gotowa:

- plan nie jest wykonywany;
- użytkownik widzi różnicę względem pustego workspace;
- Interactive CLI wraca do Home.

### R-506 — częściowo gotowy workspace

Auto planuje tylko gotowe grupy.

### R-507 — blocked plan

Blokujące `PlanProblem` zatrzymują wykonanie przed `execute`.

### R-508 — brak preview w normalnym Auto

Normalny Auto nie wymaga dodatkowego ekranu potwierdzenia planu.

### R-509 — pojedynczy aktywny run

Istniejąca ochrona `AppService` przed drugim równoległym runem pozostaje.

### R-510 — po zakończeniu

Po sukcesie ukończone zielone paski `Done` pozostają do naciśnięcia klawisza. Nie
pojawia się osobny tekst sukcesu ani lista produktów.

Wynik częściowy, błąd lub anulowanie nadal pokazują bezpieczne szczegóły. Po każdym
stanie terminalnym użytkownik może wrócić do Home bez restartu procesu.

### R-511 — brak automatycznego kolejnego runu

Powrót do Home nie uruchamia Auto samoczynnie.

---

## 10. Prezentacja przebiegu

### R-600 — istniejący Rich

Przebieg używa istniejącego `MultiProgressManager`.

Nie powstaje drugi system progress barów.

### R-601 — jedna linia na grupę

Każda aktywna grupa/odcinek ma jeden stabilny wiersz.

Etapy zmieniają opis tego wiersza.

### R-602 — naturalna kolejność

Wiersze są tworzone w naturalnej kolejności planu i nie przeskakują podczas runu.

### R-602A — brak własnego viewportu

Renderer przekazuje wszystkie stabilne wiersze jednemu `MultiProgressManager`.
Nie implementuje własnego okna, przewijania ani ukrywania wierszy.

Marka, postęp i stopka przeliczają swoje położenie po zmianie szerokości lub wysokości
terminala. Seria zmian podczas przeciągania krawędzi jest scalana do ostatniego
stabilnego rozmiaru, bez wielokrotnego przebudowywania tego samego managera. Krótko
żyjący watcher należy do granicy promptów i nie tworzy drugiego renderera ani historii
kolejnych ekranów.

### R-603 — etapy

UI odtwarza etapy pliku z legacy `_PipelineProgressRows`:

```text
Extracting
Extracted
Translating
Translated
Synthesizing
Retrying
Audio normalize
Audio timeline
Audio mixing
Audio resume
Audio skipped
Done
Failed
Cancelled
Not processed
```

Techniczne `TaskKind` nie są osobnymi wierszami prezentacji. Normalizacja napisów,
split, transkodowanie, kompozycja i publikowanie zachowują istniejący wiersz.
Fazy audio zmieniają jego etykietę zgodnie z legacy.

### R-604 — pasek dla etapów zadaniowych

`Extracting` od pierwszej klatki pokazuje zwykły pasek, procent i elapsed time.
`Translating` i `Synthesizing` resetują ten sam pasek. Spinner jest dozwolony
wyłącznie dla niedeterministycznych faz audio, dokładnie jak w legacy.

Na wąskim terminalu opis jest skracany, a elapsed time ukrywany przed dopuszczeniem do
zawinięcia jednego zadania na dwa wiersze. Procent pozostaje widoczny.

Szerokość wszystkich widocznych pasków wynika z geometrii terminala. Opis jest
ograniczony do historycznych 72 znaków, a manager dopasowuje pasek ponownie po resize.
Wyłączone kolumny nie rezerwują pustych odstępów. Między paskiem, procentem i czasem
znajduje się po jednym odstępie przed kolejnym separatorem `|`.

### R-605 — tłumaczenie całego pliku

Obecny handler tłumaczenia wysyła cały plik do silnika i zwraca wynik jako całość.

Dlatego normalny widok podczas pracy wygląda np.:

```text
Tłumaczenie · Odcinek 06 █░░░░░░░░░░░░░ | 0% | 00:00:18
```

Nie:

```text
Tłumaczenie 73%
```

jeżeli backend nie wyemitował takiego pośredniego procentu.

### R-606 — końcowe 100% tłumaczenia

Końcowy event `100` z handlera tłumaczenia domyka istniejący pasek. UI nie wymyśla
wartości pośrednich; wiersz przechodzi bezpośrednio z `0%` do `100%`, jeżeli tylko
takie zdarzenia dostarczył backend.

### R-607 — ekstrakcja 1:1 z legacy

Dla MKV ekstrakcja zachowuje cały historyczny kontrakt, a nie tylko wygląd wiersza:

1. jeden plik uruchamia jeden `mkvextract --gui-mode`;
2. wybrane audio i napisy są przekazywane do tego samego procesu;
3. każde rzeczywiste `#GUI#progress N%` trafia do istniejącego wiersza bez
   interpolacji, uśredniania ani zastępowania wartością sztuczną;
4. wszystkie pliki, które wymagają ekstrakcji, korzystają z historycznej puli
   `min(liczba_plików, round(sqrt(cpu_count)) + 2)`;
5. kolejność przyjęcia i wierszy jest naturalna (`2` przed `10`).

Końcowe `100%` domyka ten sam pasek jako `Extracted`. Neutralna ścieżka MP4 może
pozostać bez procentów pośrednich, jeżeli używane narzędzie ich nie dostarcza.

### R-608 — TTS

TTS używa rzeczywistego, monotonicznego procentu legacy opartego na liczbie
wymaganych requestów: widoczny licznik jest maksimum z odebranych i zatwierdzonych
requestów, wartości niepełne są zaokrąglane w górę i ograniczone do `99%`, a `100%`
pojawia się dopiero po zatwierdzeniu wszystkich wymaganych requestów.

Na poziomie plików syntetyzuje się jeden odcinek naraz. Współbieżność requestów
wewnątrz aktywnego odcinka nadal pochodzi z profilu silnika, a audio ukończonego TTS
może pracować równolegle z syntezą następnego pliku.

### R-609 — fazy audio legacy

Komunikaty faz audio zmieniają ten sam wiersz na `Audio normalize`, `Audio timeline`,
`Audio mixing`, `Audio resume` albo `Audio skipped`. Używają spinnera bez procentu.

### R-610 — brak treści napisów

UI nie wyświetla w przebiegu:

- pełnego promptu;
- fragmentów napisów;
- odpowiedzi modelu;
- payloadów;
- tekstu TTS.

### R-611 — wiele plików

Przy wielu plikach prawdziwym globalnym wskaźnikiem może być liczba zakończonych grup.

Nie interpolujemy procentu aktywnego requestu LLM.

### R-612 — elapsed

Spinner i pasek mogą pokazywać czas trwania.

### R-613 — ETA

ETA jest domyślnie ukryte, chyba że backend dostarcza wiarygodny kontrakt.

### R-614 — transition

Przejście etapu:

- nie tworzy nowej linii;
- resetuje właściwy tryb prezentacji;
- zachowuje pozycję grupy.

### R-615 — terminal row

Po zakończeniu grupy wiersz zostaje zamrożony jako:

```text
Done            nazwa grupy
Failed          nazwa grupy
Cancelled       nazwa grupy
Not processed   nazwa grupy
```

### R-616 — callback po zamknięciu

Spóźniony event po zamknięciu progress display jest ignorowany.

### R-617 — zdarzenia w kolejności

Renderer respektuje numer sekwencji eventów i nie cofa stanu przez starszy event.

### R-618 — brak nowego event busa

Interactive CLI nie dodaje drugiego event busa ani EventBuffer, jeżeli synchroniczny
`RunEventSink` wystarcza.

### R-619 — kolory i wiele pasków

Renderer używa istniejącego `MultiProgressManager`. Każda grupa ma własny pasek, a
prawdziwy procent steruje istniejącym przejściem kolorów czerwony → pomarańczowy →
żółty → zielony. Opisy są dopełniane do wspólnej szerokości, natomiast sam wiersz
korzysta z układu niezależnego, aby pomiędzy paskiem, `| procent` i `| czas` zawsze
pozostawała dokładnie jedna komórka odstępu.

---

## 11. Retry, fallback i błędy

### R-700 — retry automatyczny

Retry pozostaje decyzją backendu.

UI nie pyta użytkownika przed każdą automatyczną ponowną próbą.

### R-701 — retry w tym samym wierszu

`TASK_RETRY` nie tworzy nowego wiersza i nie zastępuje publicznej fazy technicznym
opisem. Autorytatywny procent pozostaje bez zmian.

### R-702 — fallback w tym samym wierszu

`TASK_FALLBACK` nie tworzy nowego wiersza i nie zastępuje publicznej fazy.

### R-703 — brak utraty realnego procentu

Retry i fallback nie resetują autorytatywnego licznika bez eventu backendu.

### R-704 — błąd jednej grupy

Błąd jednej grupy nie zatrzymuje automatycznie pozostałych niezależnych grup, jeżeli
scheduler pozwala im kontynuować.

### R-705 — błędy zależności

Taski zablokowane przez failed dependency nie są przedstawiane jako osobne awarie
użytkownika. Końcowy wynik grupy wyjaśnia podstawową przyczynę.

### R-706 — oczekiwany błąd użytkownika

Przykłady:

- pusty workspace;
- brak gotowych grup;
- blocked plan;
- brak konfiguracji;
- nieprawidłowa wartość ustawienia;
- brak klucza.

Są pokazywane jako krótki komunikat i nie kończą procesu tracebackiem.

### R-707 — błąd wykonania

Komunikat zawiera:

```text
co się nie udało
której grupy dotyczy
krótki bezpieczny powód
gdzie znajduje się log
```

### R-708 — brak sekretów

Terminal nie pokazuje:

- tokenów;
- API keys;
- nagłówków;
- payloadów;
- absolutnych ścieżek prywatnych;
- pełnego stderr;
- pełnych promptów.

### R-709 — log

Pełna diagnostyka trafia do istniejącego JSONL logu procesu.

UI podaje lokalizację względną:

```text
logs/anishift.log.jsonl
```

### R-710 — unexpected exception

Nieoczekiwany wyjątek programistyczny nie jest po cichu zmieniany w sukces.

Granica procesu loguje go jako critical zgodnie z istniejącym `main()`.

### R-711 — anulowanie Home

`Ctrl+C` na Home kończy proces kodem sukcesu lub standardowym kodem bez tracebacka.

### R-712 — anulowanie runu

`Ctrl+C` podczas runu pokazuje `Anulowano` i kończy bieżący run zgodnie z istniejącym
kontraktem anulowania.

### R-713 — ręczne „Ponów” poza v1

Pierwsza wersja nie dodaje osobnej akcji `Ponów nieudane`.

Automatyczne retry/fallback pozostają decyzją backendu. Ręczne wznowienie może zostać
dodane po realnych testach awarii.

---

## 12. Wynik przebiegu

### R-750 — wynik globalny

Po `RunResult` Interactive CLI rozróżnia:

```text
sukces
częściowy
błąd
anulowanie
```

### R-751 — grupy

Każda grupa ma jeden terminalny wiersz z nazwą i statusem. Błąd wykonania może dodać
krótki bezpieczny komunikat poniżej zakończonego progressu.

### R-752 — produkty

Sukces nie pokazuje osobnej listy produktów. Jeżeli wynik nieskuteczny wymaga wskazania
zachowanego produktu, używa nazwy pliku lub ścieżki względnej względem workspace.

### R-753 — brak absolutnych ścieżek

Nie pokazujemy pełnego `C:\Users\...`.

### R-754 — powrót

Po obejrzeniu ukończonych pasków albo komunikatu błędu użytkownik naciska klawisz
i wraca do Home. Nie powstaje osobny ekran końcowy ani lista produktów.

### R-755 — brak automatycznego wyjścia

Interactive CLI nie kończy procesu po normalnym runie.

### R-756 — noninteractive exit codes

Zachowanie interaktywne nie zmienia kodów `run --preset`.

---

## 13. Ustawienia — model produktu

### R-800 — menu kategorii

```text
Tłumaczenie
Lektor
Wynik
Połączenia
Wróć
```

### R-801 — pojedyncza transakcja pola

Zmiana jednego pola:

1. wczytuje aktualny snapshot;
2. waliduje nową wartość;
3. zapisuje atomowo;
4. aktualizuje stan w pamięci;
5. wraca do listy sekcji.

### R-802 — brak częściowego zapisu

Błąd walidacji lub I/O pozostawia poprzednią wartość.

### R-803 — natychmiastowa persistencja

Nie trzeba dodatkowo naciskać `Save`.

### R-804 — warunki pól

Pola zależne od silnika są widoczne tylko wtedy, gdy mają znaczenie.

### R-805 — katalog jako walidacja

`SettingSpec` i `field_access.py` pozostają źródłem typów, zakresów i warunków.

### R-806 — katalog nie jest automatycznym menu

O tym, które pola trafiają do produktu, decyduje jawna allowlista Interactive CLI.

---

## 14. Ustawienia — Tłumaczenie

### R-820 — pola widoczne

Docelowa sekcja może zawierać:

```text
Silnik tłumaczenia
Model tłumaczenia
Prompt
Styl
Wróć
```

### R-821 — Silnik tłumaczenia

Wartości pochodzą z istniejącego rejestru translation engines.

### R-822 — model tylko dla LLM

`Model tłumaczenia` jest widoczny, gdy wybrany silnik wymaga LLM.

### R-823 — model jako alias

Użytkownik wybiera czytelną etykietę modelu z katalogu. UI zapisuje alias/ID wymagany
przez backend.

### R-824 — provider pochodny

Provider wynika z katalogu modelu. Użytkownik nie musi osobno zestawiać providera i
modelu, jeśli prowadziłoby to do niepoprawnej pary.

### R-825 — Prompt

Prompt pochodzi z istniejącego `PromptRegistry`.

### R-826 — Styl

Styl pochodzi z istniejącego `PromptRegistry`.

### R-827 — ukryte parametry

Nie pokazujemy:

```text
translation_fallback_chain
translation_batch_size
translation_concurrency
translation_max_retries
llm_temperature
llm_top_p
llm_max_output_tokens
llm_max_concurrency
llm_module_ids
```

chyba że późniejsze realne użycie wykaże potrzebę.

---

## 15. Ustawienia — Lektor

### R-840 — pola widoczne

```text
Silnik
Głos
Tempo
Głośność lektora
Głośność oryginału
Wróć
```

### R-841 — silnik

Silniki pochodzą z istniejącego rejestru TTS.

### R-842 — głos

Lista głosów zależy od silnika.

### R-843 — tempo

Tempo edytuje `tts_profile.postprocess_tempo` i respektuje istniejący zakres.

### R-844 — głośność lektora

`Głośność lektora` mapuje na globalny `narrator_mix_base_gain_db`.

### R-845 — głośność oryginału

`Głośność oryginału` mapuje na `original_gain_db`.

### R-846 — kalibracja głosu ukryta

`voice_mix_offset_db` pozostaje kalibracją profilu i nie jest domyślnym polem
użytkownika.

### R-847 — provider-native tuning ukryty

Nie pokazujemy domyślnie:

- stability;
- similarity_boost;
- style;
- speaker_boost;
- native pitch;
- native volume;
- native rate;
- concurrency;
- output format providera;
- VPN toggle;
- retry count.

### R-848 — model TTS

Model/endpoint TTS jest dobierany przez konfigurację silnika, chyba że pojawi się
realna potrzeba produktowa jego wyboru.

---

## 16. Ustawienia — Wynik

### R-860 — widoczne produkty

```text
Polskie napisy
Polski lektor
MKV
MP4
```

### R-861 — znaczniki

```text
● Polskie napisy
○ Polski lektor
● MKV
○ MP4
```

### R-862 — minimum jeden produkt

Nie można zatwierdzić pustej listy.

### R-863 — mapowanie

| UI | ProductKind |
|---|---|
| Polskie napisy | `FULL_PL` |
| Polski lektor | `NARRATION_AUDIO` |
| MKV | `MKV` |
| MP4 | `MP4` |

### R-864 — szczegóły kontenera pochodne

W pierwszej wersji UI nie pyta osobno o:

- `mkv_tracks`;
- `burn_subtitle_product`;
- `mp4_audio_source`;
- bitrate;
- composition quality.

Są wyliczane według jawnej polityki backendu/default preset.

### R-865 — zapis

Wybór produktów aktualizuje domyślny preset workflow w `presets.json` atomowo.

### R-866 — jedna spójna konfiguracja

Użytkownik nie musi wiedzieć, że produkty zapisują się w innym pliku niż ustawienia
silników.

---

## 17. Ustawienia — Połączenia

### R-880 — zakres

Sekcja pozwala zarządzać wymaganymi przez projekt sekretami i adresami.

### R-881 — status bez wartości

Lista pokazuje tylko:

```text
skonfigurowane
brak
```

Nie pokazuje części tokenu.

### R-882 — obsługiwane połączenia

Sekcja może obejmować:

- Palantir Foundry;
- Gemini;
- OpenAI;
- Anthropic;
- DeepSeek;
- OpenRouter;
- OpenAI-compatible;
- DeepL;
- ElevenLabs.

### R-883 — ustawienie sekretu

Sekret jest wpisywany przez maskowany input.

### R-884 — pusty input

Pusty input nie usuwa istniejącego sekretu.

### R-885 — usunięcie

Usunięcie sekretu jest osobną, jawną akcją z potwierdzeniem.

### R-886 — zapis

Sekrety zapisuje istniejące `AppService.update_secret()` do `.env`.

### R-887 — reload

Po zapisie `Settings` są ponownie ładowane.

### R-888 — adres Palantir

Enrollment URL jest edytowany jako zwykłe, walidowane ustawienie.

### R-889 — OpenAI-compatible

Base URL jest widoczny tylko tam, gdzie ma znaczenie.

### R-890 — model catalog read-only

Interactive CLI nie edytuje `anishift.models.jsonc`.

### R-891 — test połączenia

Test modelu/połączenia jest jawny, wykonuje najwyżej jedno minimalne żądanie i nie
zapisuje wyniku dostępności trwale.

---

## 18. Persistencja i źródła prawdy

### R-900 — fizyczne źródła

| Dane | Źródło |
|---|---|
| ustawienia silników i audio | `config/settings.json` |
| workflow/output domyślnego Auto | `config/presets.json` |
| modele/providery | `config/anishift.models.jsonc` |
| sekrety | `.env` / środowisko |
| log | `logs/anishift.log.jsonl` |

### R-901 — atomowy zapis

`settings.json`, `presets.json` i `.env` są zapisywane atomowo przez istniejące
mechanizmy.

### R-902 — brak zapisu katalogu modeli

AniShift tylko czyta JSONC, aby nie niszczyć komentarzy i formatowania.

### R-903 — system env ma pierwszeństwo

Jeżeli sekret istnieje w system environment, może przesłonić `.env`.

UI ma móc poinformować o tym bez pokazania wartości.

### R-904 — tolerancyjny odczyt

Uszkodzenie `settings.json` nie może prowadzić do częściowego, losowego stanu.

### R-905 — brak danych w workspace

Konfiguracja pozostaje poza folderem mediów.

---

## 19. Modele

### R-920 — dane poza kodem UI

Lista modeli nie jest zaszyta w menu Interactive CLI.

### R-921 — katalog lokalny

Modele pochodzą z `ModelCatalog`.

### R-922 — alias i etykieta

UI pokazuje `label`, a backend otrzymuje właściwy alias/model ID.

### R-923 — niedostępny alias

Alias odrzucony przez parser lub nieistniejący nie jest wybieralny.

### R-924 — issues

Błędy pojedynczych wpisów katalogu są widoczne jako bezpieczna konfiguracja do
naprawy, nie jako traceback.

### R-925 — brak sieci przy listowaniu

Otwarcie listy modeli nie wykonuje requestu.

### R-926 — availability session-only

Wynik testu dostępności modelu nie jest trwałym polem konfiguracji.

---

## 20. Tryb Ręczny

### R-1000 — wspólne ustawienia

Ręczny zaczyna od tej samej aktywnej konfiguracji co Auto.

### R-1001 — discovery

Najpierw wykonywane jest discovery.

### R-1002 — wybór grup

Użytkownik wybiera jedną lub wiele grup przez left-side multi-select.

### R-1003 — brak grup

Pusty workspace kończy wizard bez planowania.

### R-1004 — ustawienia per grupa

Wizard pyta tylko o decyzje, które użytkownik nadpisuje.

### R-1005 — źródło napisów

Może pozwolić wybrać:

- auto;
- sidecar;
- embedded;
- external;
- ready Polish;
- none.

### R-1006 — audio

Może pozwolić wybrać embedded/external audio, jeśli istnieje więcej niż jedna sensowna
opcja.

### R-1007 — produkty

Ręczny może nadpisać listę produktów dla danej grupy.

### R-1008 — brak technicznego formularza

Nie pokazuje retry, batch, temperature ani concurrency.

### R-1009 — zależne pytania

Pytanie pojawia się tylko wtedy, gdy grupa ma więcej niż jedną sensowną decyzję lub
użytkownik wybrał tryb nadpisania.

### R-1010 — planowanie

Po wizardzie powstają `GroupIntent`, następnie `AppService.plan_manual()`.

### R-1011 — blocked plan

Blokery są pokazane przed wykonaniem.

### R-1012 — przebieg

Po zaakceptowaniu planu Ręczny używa tego samego Rich progress i polityki błędów co
Auto.

### R-1013 — brak trwałego nadpisania

Decyzje per grupa nie zmieniają globalnej aktywnej konfiguracji, chyba że użytkownik
jawnie edytował Settings.

---

## 21. Techniczne subkomendy

### R-1100 — zachowane subkomendy

```text
anishift doctor
anishift setup
anishift run --preset ID
```

pozostają.

### R-1101 — noninteractive

`run --preset` pozostaje maszynowo czytelny i nie uruchamia Questionary.

### R-1102 — brak importu toolkitu

`doctor`, `setup` i `run --preset` nie importują:

- Questionary;
- prompt_toolkit;
- Textual;
- interactive package.

### R-1103 — exit codes

```text
0 success
1 refused
2 Typer usage
3 incomplete
4 cancelled
```

pozostają dla nieinteraktywnego `run`.

### R-1104 — bare invocation

Tylko gołe `anishift` uruchamia Interactive CLI.

### R-1105 — jeden composition root

Każdy produkcyjny przebieg korzysta z `bootstrap.production_service()`.

---

## 22. Granice architektury

### R-1200 — warstwa prezentacji

Nowy kod Interactive CLI leży pod `anishift/cli/interactive/`.

### R-1201 — publiczna fasada

Interactive CLI używa publicznego `AppService`.

### R-1202 — brak importu services

Warstwa interactive nie importuje konkretnych silników ani usług domenowych.

### R-1203 — brak importu schedulera

Warstwa interactive nie tworzy `GraphScheduler`.

### R-1204 — brak własnego stanu backendu

Interactive CLI nie kopiuje `UserSettings`, `ExecutionPlan` ani `RunResult` do własnego
globalnego store.

### R-1205 — lokalny stan promptu

Dozwolony jest wyłącznie lokalny stan bieżącego menu/wizarda.

### R-1206 — brak drugiego loggera

Interactive CLI korzysta z istniejącego loggera procesu.

### R-1207 — brak drugiego progress toolkit

Progress korzysta z `anishift.utils.rich_console`.

### R-1208 — lazy import

`main.py` importuje Interactive CLI dopiero w ścieżce bare invocation.

---

## 23. Wymagania jakościowe

### R-1300 — Python

Python 3.14+.

### R-1301 — zależności

Nowe zależności wyłącznie przez `uv add`.

### R-1302 — Questionary

Questionary jest jedynym wysokopoziomowym właścicielem promptów interaktywnych.

Nie używamy bezpośrednio `prompt_toolkit` poza ewentualnym minimalnym adapterem
wymuszonym przez udowodniony blocker i zaakceptowany replan.

### R-1303 — testowalność

Interaktywna pętla ma wstrzykiwalną granicę promptów, aby testy nie uruchamiały realnego
terminala.

### R-1304 — brak snapshotów terminala jako jedynego dowodu

Testy sprawdzają strukturę wyborów i zachowanie. Wygląd potwierdza HITL.

### R-1305 — Windows Terminal

Home, wybory, progress i błędy przechodzą realny test w Windows Terminal.

### R-1306 — Linux CI

Techniczne subkomendy i testy pozostają zgodne z Linux CI.

### R-1307 — brak sieci w testach standardowych

Testy Interactive CLI korzystają z fake `AppService` i fake prompt adaptera.

### R-1308 — wydajność startupu

Bare invocation nie ładuje modeli ani provider SDK przed pierwszą akcją wymagającą ich
użycia.

### R-1309 — brak ciągłych wątków UI

Poza workerami backendu Interactive CLI nie tworzy stałego wątku odświeżania.

### R-1310 — bezpieczeństwo danych

Nie logujemy ani nie renderujemy treści napisów, promptów i sekretów.

---

## 24. Twarde inwarianty

### I-001

Textual nie wraca do zależności.

### I-002

Nie powstaje `anishift/tui`.

### I-003

Home ma dokładnie cztery akcje.

### I-004

`Auto` jest domyślnie aktywne.

### I-005

Home nie pokazuje konfiguracji.

### I-006

Znaczniki wyboru są po lewej.

### I-007

Nie ma globalnego Save dla ustawień.

### I-008

Model catalog pozostaje read-only.

### I-009

Sekrety nie trafiają do `settings.json`, `presets.json` ani katalogu modeli.

### I-010

Progress bar aktualizuje wartość wyłącznie z realnego licznika.

### I-011

Tłumaczenie całego pliku ma blokowy pasek `0% → 100%` bez wymyślonych wartości
pośrednich.

### I-012

TTS może pokazywać rzeczywisty procent.

### I-013

Jedna grupa zajmuje jeden stabilny wiersz progress.

### I-014

Retry/fallback nie produkują scrollback spamu.

### I-015

Noninteractive subcommands nie importują Interactive CLI.

### I-016

`AppService` pozostaje jedyną fasadą produktu dla CLI.

### I-017

Maskotka nie może zepsuć pipeline’u.

### I-018

PLAN 01 nie integruje Chafa i zawiera tylko jeden zaakceptowany asset PNG maskotki.

### I-019

Manual nie zapisuje per-group overrides do global settings.

### I-020

Nie tworzymy managera presetów użytkownika w tym workstreamie.

---

## 25. Mapa wykonania

### PLAN 01 — Interactive CLI + Home + prawdziwy Auto

Końcowy dowód:

```text
uv run anishift
-> Home
-> Enter na Auto
-> discovery
-> plan_auto
-> execute
-> Rich progress
-> ukończone paski albo wynik błędu
-> powrót do Home
```

Zawiera:

- Questionary;
- Home;
- transparentną maskotkę renderowaną przez Pillow;
- wspólny auto-run flow;
- Rich progress;
- retry/fallback display;
- wynik i błędy;
- zachowanie technicznych subkomend.

### PLAN 02 — Ustawienia

Zawiera kolejno:

1. minimalny adapter edytorów;
2. Tłumaczenie;
3. Lektor;
4. Wynik;
5. Połączenia;
6. zapis i walidację.

### PLAN 03 — Ręczny

Zawiera:

- discovery;
- wybór grup;
- pytania per grupa;
- `GroupIntent`;
- plan manualny;
- wspólny progress i wynik.

### PLAN 04 — Maskotka, polish i cleanup

Zawiera:

- Chafa/Sixel;
- finalne assety;
- stany reaktywne;
- fallback;
- dopracowanie kolorów;
- mały terminal;
- cleanup tymczasowych placeholderów;
- finalne testy i dokumentację.

Nie tworzymy szczegółowych PLAN 02–04 przed zweryfikowaniem poprzedniego etapu na
rzeczywistym repo.

---

## 26. Kryteria akceptacji całego workstreamu

### AC-001

`uv run anishift` pokazuje Home, nie uruchamia od razu pipeline’u.

### AC-002

Home ma dokładnie cztery pozycje w wymaganej kolejności.

### AC-003

`Enter` przy domyślnym wyborze uruchamia Auto.

### AC-004

Home nie pokazuje modelu, głosu, presetu ani workspace.
Stopka pokazuje bieżący katalog i wersję.

### AC-005

Znaczniki są po lewej.

### AC-006

Nie ma Textual ani `anishift/tui`.

### AC-007

Nieinteraktywny `run --preset` zachowuje output i exit codes.

### AC-008

Doctor/setup/run nie ładują Questionary ani prompt_toolkit.

### AC-009

Pusty workspace wraca do Home bez tracebacka.

### AC-010

Blocked plan nie trafia do `execute`.

### AC-011

Translation task bez pośredniego licznika zachowuje pasek `0%`, a końcowy event
domyka go do `100%`.

### AC-012

TTS pokazuje rzeczywisty procent.

### AC-012A

Każdy plik ma jeden stabilny wiersz ograniczony do publicznych faz z R-603.

### AC-012B

Auto zachowuje `ready_first` oraz zapisane limity współbieżności. Cztery gotowe pliki
LLM mogą być widoczne równocześnie, a ukończenie jednego natychmiast zwalnia miejsce
dla kolejnego.

### AC-013

Retry i fallback aktualizują istniejący wiersz.

### AC-014

Wieloplikowy przebieg nie zalewa terminala nowymi liniami.

### AC-015

Wynik częściowy jest odróżniony od pełnego sukcesu.

### AC-016

Błędy nie ujawniają sekretów ani absolutnych ścieżek.

### AC-017

Po runie można wrócić do Home.

### AC-018

Ustawienia Tłumaczenia zapisują się po zatwierdzeniu pojedynczej wartości.

### AC-019

Ustawienia Lektora zapisują się po zatwierdzeniu pojedynczej wartości.

### AC-020

Produkty zapisują się jako jedna walidowana transakcja.

### AC-021

Sekrety są maskowane i zapisywane do `.env`.

### AC-022

Pusty password input nie usuwa sekretu.

### AC-023

Usunięcie sekretu wymaga potwierdzenia.

### AC-024

Lista modeli pochodzi z JSONC.

### AC-025

Otwarcie listy modeli nie wykonuje sieci.

### AC-026

Manual korzysta z globalnych ustawień i per-group overrides.

### AC-027

Manual planuje tylko wybrane grupy.

### AC-028

Maskotka ma działający fallback.

### AC-029

Brak Chafa nie blokuje produktu.

### AC-030

Home i Auto przechodzą HITL w Windows Terminal.

### AC-031

Settings przechodzi osobny HITL.

### AC-032

Manual przechodzi osobny HITL na prawdziwym materiale.

### AC-033

Pełne bramki repo przechodzą przed każdym końcowym commitem.

---

## 27. Rzeczy świadomie poza zakresem

- pobieranie anime;
- katalog anime;
- okładki;
- integracja z serwisem streamingowym;
- web UI;
- dashboard historii;
- edytor logów;
- command palette;
- slash commands;
- plugin system;
- tworzenie presetów przez użytkownika;
- import/export presetów;
- theme editor;
- pixel-art framework;
- obsługa myszy jako wymóg;
- ręczny edytor każdego parametru providera;
- trwałe zapisywanie availability modelu;
- strumieniowanie treści tłumaczenia do terminala;
- fałszywy procent requestu LLM;
- animowana maskotka w PLANIE 01;
- kopiowanie roboczych grafik 4K do repo.

---

## 28. Nierozstrzygnięte pytania

Brak pytań blokujących rozpoczęcie PLANU 01.

Finalny wygląd, miejsce i zestaw klatek maskotki pozostają świadomie odłożone do
PLANU 04.
