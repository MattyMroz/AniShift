---
kind: specification
status: implementation-authorized
updated: 2026-09-05
---

# AniShift — manifest dopracowania produktu

AniShift ma zamieniać anime w poprawne polskie napisy i lektora przez prosty,
responsywny interfejs terminalowy. Użytkownik ma rozumieć, co program robi,
rozpoznawać awarie i zachować poprawne wyniki również wtedy, gdy część pracy
się nie powiedzie. Szybkość nie może wynikać z pomijania treści lub walidacji.

## Dokumenty tego workstreamu

| Dokument | Rola |
| --- | --- |
| [Audyt](audit.md) | Sprawdzony baseline, ocena, dowody i ograniczenia |
| Ten manifest | Oczekiwany rezultat, ograniczenia i preferencje użytkownika |
| [Masterplan](masterplan.md) | Kolejność stanów pośrednich i warunki przejścia |
| [Tablica zadań](tasks.md) | Jedyny rejestr statusu konkretnych napraw |
| [Pierwszy plan](plans/01-translation-integrity.md) | Wykonalna pierwsza iteracja bez zgadywania zakresu |

Dokumenty dotyczą pracy rozpoczętej 2026-09-04. Stare plany pozostają materiałem
historycznym. W razie sprzeczności aktualne ustalenia użytkownika mają pierwszeństwo;
opis obecnego kodu w audycie nie ustanawia nowego wymagania.

## Kontrakt produktu

- **R01 — pełny rezultat.** Żądany polski produkt nie może zawierać źródłowego tekstu
  podstawionego po nieudanym tłumaczeniu ani pustej lub urwanej wypowiedzi uznanej
  za sukces. Sama obecność wszystkich numerów nie dowodzi poprawnego zakończenia modelu.
- **R02 — tożsamość napisów.** Powtarzające się wypowiedzi, ich kolejność, czas,
  Unicode i istotny układ muszą przetrwać przetwarzanie. Animację ASS trzeba
  odróżniać od dwóch osobnych kwestii o identycznym tekście.
- **R03 — kontrolowane naprawy.** Zachować numerowany kontrakt `[N] tekst`, naprawę
  wadliwych numerów i podział po rzeczywistym limicie modelu. Retry jest ograniczone;
  trwały błąd kończy się jawną diagnozą. Nie przywracać odrzuconego cichego fallbacku.
- **R04 — uczciwy postęp.** Każda długa faza pokazuje nazwę i stan. Procent pochodzi
  z pomiaru rzeczywistej pracy. Gdy pomiar nie istnieje, pokazywana jest aktywność,
  czas i ostatni znany etap; nie wymyśla się rosnącego procentu. Koniec strumienia,
  walidacja i zapis są odrębnymi faktami. `100%` nie może ukrywać naprawy lub błędu.
- **R05 — wynik awarii.** Użytkownik widzi, który plik i etap zawiódł, co zakończyło
  się poprawnie oraz krótką przyczynę i możliwą reakcję. Postęp innych niezależnych
  grup nadal działa. Przydatny jest kopiowalny, zredagowany opis wyniku przebiegu.
- **R06 — anulowanie.** Anulowanie zatrzymuje nowe prace, przerywa obsługiwane
  operacje zewnętrzne i sprząta własne zasoby. Zamknięcie aplikacji nie pozostawia
  niekontrolowanego procesu ani nie publikuje spóźnionego wyniku.
- **R07 — dane.** Źródła pozostają nienaruszone. Trwałe produkty leżą obok źródła,
  zarządzane dane tymczasowe wyłącznie w `workspace/temp/`, preferencje w `config/`.
  Nie usuwać istniejących katalogów użytkownika podczas porządkowania repozytorium.
- **R08 — instalacja.** Na wspieranym Windows brakujące wymagane narzędzia mają być
  przygotowywane automatycznie, ze sprawdzeniem integralności i widocznym postępem.
  Głosy wymagające instalacji systemowej, np. SAPI, mają jasno udokumentowane
  wymagania i wykrywanie dostępności. Instalację głosów opisywać dla legalnie
  dostępnych instalatorów; nie uzależniać produktu od obchodzenia aktywacji.
- **R09 — interfejs.** Zachować prostą terminalową obsługę klawiaturą: Home, Auto,
  Ręczny, Ustawienia i wynik. Nie wracać do Textual, rozbudowanego routera ani
  nowego frameworka. Obecnego przewijania kółkiem nie usuwać przy okazji; rozwój
  obsługi myszy nie jest celem tej pracy.
- **R10 — responsywność.** Mierzyć start, opóźnienie reakcji, renderowanie i pracę
  w tle na określonej maszynie oraz materiale. Długa operacja nie może blokować
  klawiszy. Optymalizować najpierw zmierzone przyczyny; nie obiecywać niezmierzonej
  przepustowości usług sieciowych.
- **R11 — styl kodu.** Zachować długie separatory sekcji. Docstringi modułów, klas,
  funkcji i stałych mają być krótkie, domyślnie jednozdaniowe; pod stałymi `Final`.
  Usuwać opowiadanie historii zmian i powtarzanie oczywistych typów lub działania
  kodu. Zachować krótki komentarz wyjaśniający istotne ograniczenie, którego kod
  sam nie wyraża. Nie dokładać warstw, klas ani plików bez konkretnego odbiorcy.
- **R12 — testy.** Brak opisowych komentarzy i docstringów w kodzie testowym;
  dyrektywy narzędziowe pozostają dozwolone. Testować zachowanie i granice usług,
  awarie, odzyskiwanie, anulowanie i reprezentatywne prawdziwe media.
- **R13 — diagnostyka.** Używać wspólnego loggera i bezpiecznych danych strukturalnych.
  Nie zapisywać sekretów, napisów, promptów, pełnych żądań, bezwzględnych ścieżek
  ani surowego stderr. Narzędzia odczytu mają rozumieć format rzeczywistych logów.
- **R14 — koszt.** Preferować już używane bezpłatne możliwości i nie zmieniać
  samodzielnie dostawcy na płatnego. Deklaracja użytkownika o darmowym dostępie
  nie jest gwarancją aktualnych limitów; pomiary mają liczyć rzeczywiste żądania,
  retry i czas. Nie zmieniać kluczy ani zapisanych preferencji na potrzeby audytu.

## Zakres i granice

Aktualny zakres obejmuje audyt całego repozytorium, poprawę istniejących przepływów,
ich niezawodności, postępu, responsywności, czytelności i dowodów działania.
Pierwsza szczegółowa iteracja jest ograniczona osobnym planem. Nie jest to zgoda
na jednorazowe przepisanie aplikacji lub reorganizację całego drzewa.

2026-09-04 właściciel zatwierdził realizację poleceniem „ZRÓB WSZYSTKO”, następnie
wyraźnie rozszerzył ją o naprawy `anishift/utils/`, wymagając dowodów działania.
Zachować przenośność biblioteki oraz jej publiczne kontrakty. Osobno zatwierdził
objęcie strażnikiem braku prose również `conftest.py` i testowych `__init__.py`.

Właściciel zatwierdził również lokalne commity tematyczne. Nie tworzyć issue, PR
ani publikacji tylko dlatego, że wpis znalazł się na lokalnej tablicy; push i merge
nie są objęte tą zgodą. Zgoda na rozszerzenie istniejącego strażnika nie obejmuje
nowych niezależnych strażników, np. automatycznego limitu długości docstringów.

## Kierunek wizualny

Jedna paleta wyprowadzona z istniejącej maskotki ma obejmować wordmark, akcenty
i postęp. Gradientowe paski są preferencją,
ocenianą na działającym terminalu po naprawie semantyki postępu. Animacja nie
może pogarszać reakcji na klawisze, czytelności ani zużycia CPU w bezczynności.
Maskotka skacze na Home oraz podczas przetwarzania, gdy pozwala na to miejsce.
Mniejszy terminal zachowuje dostęp do kolejki i sterowania; pełny wordmark może
ustąpić samej maskotce. Średni wariant i animacja napisu są odrzucone.
Wersja pozostaje czytelna po prawej.
Przejścia i resize nie odsłaniają wcześniejszej konsoli ani nie kasują jej historii.
Logo oddziela od postępu pusta linia. Ukończony wiersz zaczyna się od „✓”, zachowuje
paletę marki; nazwa pliku korzysta z dostępnej szerokości zamiast stałego limitu.
Ustawienia obsługują strzałki, Enter i cofanie z podpowiedzią działania. Dostępne
opcje i modele nie mogą znikać ani nadpisywać innych ustawień przy edycji.

Etap ma osobny odstęp od nazwy pliku. Pasek ma pierwszeństwo przed rozszerzaniem
tytułu, a akcent zachowuje oryginalny azure, bez rozjaśniania.
Home zachowuje stały górny margines, o ile wystarcza wysokości. Puste odstępy
logo–menu i menu–stopka są równe z tolerancją jednego wiersza przy resize.
Sugestie poprawy promptów trafiają do osobnego raportu;
aktywne szablony nie są zmieniane bez walidacji jakości. Trzy luźne pliki
`prompt_helper.txt`, `prompt_helperSS.txt`, `prompt_main.txt` można usunąć po
sprawdzeniu braku użycia, zachowując kopię odzyskiwalną poza repozytorium.

2026-09-04 właściciel odrzucił placeholder podczas startu. Pierwsza klatka ma
pokazywać gotową docelową maskotkę, nawet kosztem oczekiwania na jej przygotowanie.
Nie pokazywać tymczasowej maskotki ani loadera zamienianego po chwili w obraz.

W wypowiedzi użytkownika pojawiła się ścieżka w lewym górnym rogu, podczas gdy
obecny kontrakt umieszcza katalog po lewej w stopce. Położenie oraz wybór
`cwd` kontra faktyczny workspace rozstrzygnąć przy pierwszym podglądzie UI;
nie blokuje to napraw poprawności.

## Następne możliwości produktu

- **TXT → audiobook:** zamówiony kierunek rozszerzenia po stabilizacji. Zwykły
  tekst może być tłumaczony i zamieniany na plik audio, również bez wideo.
  Dzisiejsze techniczne timingi SRT nie definiują rytmu audiobooka. Język wejścia,
  domyślny format audio i sposób grupowania wymagają szczegółowego planu tego etapu.
- **Obserwowanie folderu:** późniejsza automatyzacja stabilnego przebiegu;
  rozpoznawać zakończenie kopiowania i unikać powtórnego przetwarzania produktów.
- **Wrzucanie ścieżki do terminala:** przyszła wygodna droga dodania materiału;
  polityka kopiowania/przenoszenia i kolizji musi być jawna.
- **Pobieranie odcinków:** przyszły osobny zakres po wyborze źródeł i zasad dostępu;
  nie realizować pobierania ani harmonogramu w iteracjach naprawczych.

## Warunek sukcesu

Rezultat uznajemy za przyjęty po bramkach repozytorium, testach regresji znalezionych
usterek, krótkim prawdziwym przebiegu multimedialnym oraz ocenie właściciela na
reprezentatywnym odcinku. Naturalność polskiego, odsłuch, synchronizacja i wygląd
terminala wymagają oceny człowieka. Nie zastępuje jej liczba testów ani ocena 1–10.
Budżety wydajności ustalamy po pomiarze baseline, bez arbitralnych obietnic.

Skille `workflow` i `simple` wyznaczają sposób pracy: najpierw potwierdzona
przyczyna, następnie najmniejsza spójna poprawka, dowód, review i kolejna decyzja.
