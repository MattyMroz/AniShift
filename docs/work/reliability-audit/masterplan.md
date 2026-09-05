---
kind: masterplan
status: active
updated: 2026-09-05
---

# AniShift — masterplan dopracowania

## Cel i źródła

Cel: poprawny, responsywny, przewidywalny przebieg od źródła do polskich produktów,
a następnie przygotowanie pod audiobook i automatyzację. Obowiązują
[manifest](manifesto.md), [audyt baseline](audit.md) i instrukcje repozytorium.
[Tablica](tasks.md) jest jedynym właścicielem statusu zadań. Ten dokument opisuje
stany produktu, nie każdą czynność wykonawcy.

Właściciel zatwierdził realizację 2026-09-04, również naprawy współdzielonych utils.
Aktualny zakres wykonania i podział odpowiedzialności opisuje
[Plan 04 — terminal](plans/04-terminal-polish.md). Akceptacja wyglądu i odsłuch pozostają osobnymi
checkpointami człowieka, niezależnie od zgody na implementację.

## Etapy

| Etap | Stan osiągany | Wejście / zależności | Warunek wyjścia | Status |
| --- | --- | --- | --- | --- |
| M00 | Znany baseline, wymagania i adresowalny backlog | `c2e8996`, polecenie właściciela | Dokumenty sprawdzone, zakres pierwszej iteracji ustalony | verified |
| M01 | Tłumaczenie nie udaje kompletnego sukcesu | M00 | F01–F04 zamknięte; sukces/failure/retry sprawdzone przez granice produktu i providera | verified |
| M02 | Konfiguracja i przygotowanie środowiska nie zaskakują | M00; po pierwszym wyniku M01 | Błędne typy i wpisy izolowane, bezpieczny setup, czysty Windows start zweryfikowany | partial: świeży Windows otwarty |
| M03 | Przerwanie i oczekiwanie nie blokują całej pracy | M01, rozpoznane narzędzia | Deadline, cancel, worker cleanup, blokada produktu i aktywna sieć mają sprawdzone zachowanie | verified: z limitami sieci |
| M04 | Napisy i media zachowują całą wymaganą treść | Baseline M00; zmiany runnerów uzgadniane z M03 | Powtórzenia, świadomy wybór spoken, ogon narracji, ostrzeżenia i trudne ścieżki przechodzą regresje | verified: krótkie media |
| M05 | Każdy etap ma uczciwy postęp i użyteczny wynik | M01, M03, aktywne ścieżki M04 | Pomiary przechodzą backend→event→UI; brak procentu ma jawną aktywność; widoczne przyczyny awarii | pending-human |
| M06 | Terminal jest spójny i ma zmierzony koszt | M05 | Baseline/pomiar po zmianie, wizualna akceptacja, brak regresji klawiatury/resize/fallbacku | partial: render/klawisze zmierzone; TTY i pełny startup otwarte |
| M07 | Kod i jego instrukcje są prostsze w utrzymaniu | Stabilne kontrakty wcześniejszych etapów | Skrócone opisy poza utils, zachowane separatory, aktualne źródła prawdy, usunięta uzasadniona redundancja | verified: bez zbędnych przenosin |
| M08 | Istniejący produkt ma powtarzalny dowód działania | M01–M05 i działający setup z M02 | Krótkie prawdziwe E2E, awarie, pomiary oraz zaakceptowany odcinek i odsłuch | partial: dowody i ocena człowieka otwarte |
| M09 | TXT może zostać audiobookiem | M08, szczegółowy kontrakt tekstu/audio | Samodzielny TXT, z tłumaczeniem lub bez, daje poprawne audio; odsłuch i brak zależności od wideo | deferred |

Numer etapu oznacza zalecaną kolejność, nie automatycznie twardą zależność.
Naprawy A05 i A07 w M04 mogą być wykonane wcześnie, niezależnie od całości M03.
M06/M07 mają własne akceptacje i nie blokują dowodów technicznych M08 ani TXT.
Etapy M02 i testowe przygotowania do M04 mogą być realizowane niezależnie po
ustaleniu ich własnych zakresów. Domyślnie prowadzić jedną iterację implementacji
naraz; nie uruchamiać kilku writerów modyfikujących kontrakt postępu/cancellation.

## Aktualny punkt decyzji

Naprawy niezawodności opisuje [outcome](outcomes/02-hardening.md). Feedback właściciela
z 2026-09-05 skierował bieżącą iterację na terminal i ustawienia —
[Plan 04](plans/04-terminal-polish.md). Po jego odbiorze wracamy do
[akceptacji produktu](plans/03-product-acceptance.md), nie automatycznej rozbudowy.
Pomiary nie wykazały tańszego kodowania maskotki. Pierwsza klatka nadal czeka
na docelowy obraz zgodnie z decyzją właściciela; nie wraca placeholder.

Następne rezultaty po odbiorze terminala:

1. Dostęp do siedmiu zaawansowanych opcji domyślnego AutoPreset w panelu, bez zmiany
   schema i utraty pozostałych pól — [Plan 05](plans/05-auto-preset-controls.md).
2. Spójne instrukcje tłumaczenia i porównanie krótszego promptu:
   [rekomendacje i ewaluacja](prompt-recommendations.md). Najpierw wierność znaczeniu,
   dopiero później koszt i naturalność. Nie wdrażać propozycji bez A/B.
3. Pełny odcinek, odsłuch/synchronizacja, świeży Windows i scenariusze graniczne
   pozostałe w Planie 03; potem kontrakt TXT → audiobook.

## Pierwszy rezultat

[Plan 01](plans/01-translation-integrity.md) zamyka konkretną część M01:
odrzucenie jawnie nieudanego lub pustego tłumaczenia przed utworzeniem polskiego
produktu. Ma własną wartość i mały zakres. Nie ogłasza naprawienia zakończenia SSE.
F02/F03 są realizowane w następnej spójnej części [Planu 02](plans/02-hardening.md).

Dlaczego ta kolejność: fałszywy sukces propaguje zły tekst do napisów, TTS i filmu.
Jego odcięcie chroni kilka dalszych etapów. Gradient, animacja i skracanie opisów
nie rozwiązują tej klasy problemów.

## Kierunek dalszych etapów

M02 zachowuje dotychczasowe recovery preferencji i read-only JSONC. Przygotowanie
narzędzi staje się jedną świadomą granicą poprzedzającą inspekcję. Audyt zależności
w CI ma wskazane wejście projektu, a nie przypadkowe środowisko narzędzia.

M03 najpierw opisuje lifecycle uruchomionego zadania, następnie naprawia istniejące
runnery. Nie wymaga nowej uniwersalnej platformy workerów. Bounded shutdown,
cancel przed join oraz nieblokujące oczekiwanie publikacji są warunkami postępu.

M04 używa krótkich syntetycznych mediów tam, gdzie odtwarzają problem. Zmiana
heurystyki ASS lub polskiego reflow wymaga przykładów pozytywnych i negatywnych;
nie sprowadzać jej do globalnego przesuwania jednego słowa.

M05 rozróżnia procent, aktywność, walidację, retry i stan terminalny. Liczenie
numerowanych linii musi znać granice prób i podziałów. Zachować jeden wiersz
na źródło i jeden renderer. Końcowy widok ma pokazać przyczynę failure oraz
produkty zachowane po częściowej porażce.

M06 mierzy pełny start, stan bezczynności, reakcję na klawisze i kolejkę przed
optymalizacją. Jedna paleta już istnieje w `palette.py`; jej użycie rozszerzyć
po akceptacji przykładu. Kodowanie klatek, polling i renderowanie mają osobne
koszty. Nie zakładać, że każdy Windows obsługuje SIXEL.

M07 skraca opisy zgodnie z manifestem. Każde przeniesienie modułu musi usuwać
konkretny problem odpowiedzialności. Instrukcje AGENTS/CLAUDE aktualizować
zgodnie z ich skillem, gdy dojdzie do tej iteracji. Rozszerzenie strażnika testów zostało zatwierdzone i wykonane.
Nowe niezależne strażniki nadal wymagają osobnej zgody.

## Weryfikacja końcowa M08

| Wymiar | Wymagany dowód |
| --- | --- |
| Deterministyczna poprawność | Wszystkie bramki root, regresje każdego zamkniętego findingu |
| Rzeczywiste narzędzia | Krótki MKV i MP4, ASS/SRT, dłuższa narracja, spacje/apostrof/Unicode |
| Awaria i recovery | Błąd modelu po częściowym streamie, timeout, cancel, zablokowany cel, zachowany poprzedni produkt |
| Dostawcy | Małe jawne próby skonfigurowanych bezpłatnych integracji, limit requestów i zapis wyników bez sekretów |
| Jakość | Odsłuch i przegląd reprezentatywnego odcinka przez właściciela |
| Wydajność | Ta sama maszyna i materiał przed/po; czas startu, CPU/RSS, opóźnienia UI, czasy etapów |
| Powtarzalność | Udokumentowany scenariusz do wykonania bez historii tej rozmowy |

Nie wprowadzać wymyślonych progów liczbowych. Po pierwszym miarodajnym pomiarze
właściciel akceptuje budżet UX i wydajności. Nie powtarzać pełnego suite po każdej
kosmetycznej edycji dokumentu; wykonywać wymagane gates przed commitami.

## Współdzielona biblioteka i przyszła automatyzacja

Naprawy utils (F23–F24, portability i niestandardowy poziom loggera) zostały
zatwierdzone. Ich dowodem musi być roundtrip rzeczywistych logów, także wyjątków
i filtrów czasu, bez kopiowania loggera do aplikacji. Ograniczenia oraz różnica
między testem automatycznym a akceptacją człowieka pozostają widoczne w outcome.

Watcher, import przez terminal i pobieranie odcinków pozostają poza M01–M09.
Następny masterplan lub jego rozszerzenie powstaje po M08/M09 i decyzji właściciela.
Warunki wejścia: idempotencja, zakończone kopiowanie plików, odporność na restart,
brak samowzbudzania na produktach i jawna polityka kolizji. Źródła pobierania
muszą być wybrane przed planowaniem integracji.

## Aktualizacja kierunku

Po każdej iteracji zapisać wynik w `outcomes/NN-<slug>.md` tylko gdy rzeczywiście
powstał, zaktualizować taski i dopiero wybrać następny szczegółowy plan.
Testy PASS bez wymaganego odsłuchu/podglądu oznaczają `pending-human`, nie `done`.
Nowy finding trafia na tablicę z dowodem i priorytetem; nie dopisywać od razu
kodu do bieżącego diffu. Błędna lokalna implementacja wraca do iteracji,
błędny kontrakt do manifestu, błędna kolejność do tego masterplanu.
