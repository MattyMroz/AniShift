---
kind: specification
status: direction-agreed-design-open
baseline: 83150d8
updated: 2026-09-05
---

# Specyfikacja: wybieram anime, dostaję gotowy odcinek

## Cel i bieżące zlecenie

AniShift ma usuwać codzienną obsługę: wyszukiwanie, pobieranie, uruchamianie Auto
i szukanie wyników. Właściciel wskazuje, co chce obejrzeć, a aplikacja prowadzi
dostępny materiał do gotowego polskiego odcinka i pokazuje jego stan.

Bieżące zlecenie: GitHub Issues dla długu, uporządkowane dokumenty, wizja i brief
do szczegółowego planowania w ChatGPT Pro. Zgoda obejmuje publikację lokalnego
kodu i dokumentów przez PR, nie implementację nowych funkcji ani deployment VPS.
Ogólne polerowanie jest odłożone. Bezpieczeństwo danych i testy nowej funkcji
pozostają wymagane.

## Ustalenia właściciela

- U01: pozostaje prosta aplikacja terminalowa Prompt Toolkit; nie nowy GUI/TUI.
- U02: obecny workspace pozostaje płaski, bez cichego przenoszenia źródeł.
  Przyszły katalog może grupować serie wirtualnie. Wzmianka o podfolderach nie
  rozstrzyga zmiany fizycznego układu; wymaga decyzji przed migracją.
- U03: obsługa ręczna i automatyczna mają współistnieć. Dwa importy i oddzielny
  output były rozważanym pomysłem, nie zatwierdzoną strukturą.
- U04: wyszukiwanie ma umożliwiać wybór tytułu i odcinków, sortowanie oraz
  czytelną grupowaną listę. Subskrypcja ma sprawdzać nowe wydania okresowo;
  godzina jest propozycją interwału, nie niezmiennym ograniczeniem.
- U05: samodzielnie dostarczone napisy, także polskie, nadal można przypisać
  ręcznie do materiału. Nie zakładać konieczności ponownego tłumaczenia.
- U06: właściciel potwierdził działanie programu na swoim materiale. Nie jest
  to potwierdzenie wszystkich awarii, jakości każdego ASS ani świeżej instalacji.
- U07: bieżące tłumaczenie w tle, jego pliki i eksperymentalny `shadow-slave.md`
  pozostają nietknięte. Nie odczytywać payloadów, sekretów ani logów tego procesu.
- U08: prowadzący przygotowuje syntezę; Fable 5.1 może opiniować bez dalszych
  agentów. ChatGPT Pro ma pomóc wybrać narzędzia i rozpisać jedną najbliższą
  iterację. Właściciel zatwierdza wykonanie.
- U09: obecny pakiet i lokalne commity mogą zostać wypchnięte przez PR do main.
  Nie wynika z tego automatyczna zgoda na merge ani przyszłe wdrożenia.
  Kolejne implementacje mają odrębne tematyczne gałęzie na odebranym kodzie.
- U10: po stabilizacji docelowych funkcji README ma pokazać animację prawdziwego
  interfejsu: skaczący slime, menu i postęp. GIF lub animowany WebP wymaga sprawdzenia
  odtwarzania na GitHubie; materiał demonstracyjny nie ujawnia sekretów ani
  prywatnych ścieżek/tytułów. To etap późniejszy, nie obecne wykonanie.
- U11: przeciągnięcie pliku do terminala ma zlecać AniShift kopiowanie do
  biblioteki, z zachowaniem oryginału. Zakończenie własnej kopii jest sygnałem
  gotowości; nie wymaga dodatkowego ręcznego potwierdzenia. Nie utożsamiać tego
  importu z obserwowaniem zapisu wykonywanego przez obcy program.

- U12: priorytetem jest oszczędność codziennej uwagi, nie ocena „10/10”.
  Status odłożonego długu należy do GitHub Issues.
- U13: jedna historia zleceń łączy przyjęcie, pobranie, przetwarzanie i gotowość.
  Wewnętrzny stan pobierania nadal należy do klienta; AniShift przechowuje
  odwołanie i uzgadnia status, nie tworzy drugiego klienta torrent.
- U14: pobrane, przetworzone, gotowe i obejrzane są różnymi pojęciami.
  Pokazywać „następny odcinek do zdobycia” bez liczenia +1. Nie modyfikować
  historii AniList/MyAnimeList na podstawie samego pobrania.
- U15: przyszły worker VPS korzysta z tego samego rdzenia bez terminala;
  lokalna praca nie zależy od dostępności serwera.
- U16: wysyłka gotowych produktów, np. do Google Drive, i synchronizacja
  z komputerem są opcjonalnym dalszym kierunkiem. Nie obiecywać nieograniczonego
  miejsca/pasma ani zgodności wszystkich silników TTS z Linuxem.
  Drive nie jest wymogiem. Właściciel deklaruje około 10 TB dostępnego miejsca
  i szacuje bibliotekę na około 200 GB; to wejście do porównania wariantów,
  nie zweryfikowane parametry konta, limit transferu ani zobowiązanie do użycia usługi.
- U17: późniejszy katalog „Gotowe” i „Oglądaj” mogą otwierać istniejący mpv.
  Bez nowego odtwarzacza, obietnicy źródeł 4K ani automatycznego upscalera.
- U18: rozmowa jest opcjonalną warstwą nad zatwierdzonymi działaniami aplikacji,
  nie dowolną powłoką, edycją działającego kodu lub prawem kasowania danych.

Kod bazowy: PR #41 dostarczył fundament; lokalne 4dc99dc i 83150d8 — pełne
ustawienia Auto i scroll. Właściciel potwierdził scroll i codzienne Auto,
nie pełny odbiór wszystkich opcji. 3102 testy PASS i 30 smoke to określone
dowody, nie gwarancja całkowitej poprawności.

## Wymagania przyszłej implementacji

### Folder i przetwarzanie

- F01: dodanie gotowego źródła uruchamia tylko należącą do niego pracę, jeśli
  obserwowanie zostało jawnie włączone. Usunięcie pliku nie uruchamia całej biblioteki.
- F02: plik w trakcie kopiowania lub pobierania nie jest gotowym wejściem.
- F03: ponowne zdarzenie, restart i własny produkt nie tworzą drugiego zlecenia
  tej samej wersji wejścia. Ponowienie ukończonego materiału jest jawne.
- F04: stan automatyzacji nie zaśmieca biblioteki; źródła i trwałe produkty nadal
  leżą obok siebie. Jedyny zarządzany podfolder workspace to `temp/`.
- F05: pauza przyjmowania nowych plików, anulowanie bieżącej pracy i wyłączenie
  obserwowania są osobnymi działaniami z widocznym skutkiem.
- F06: istniejąca ręczna ścieżka i wspólny planner/scheduler pozostają właścicielami
  wykonania. Watcher nie tworzy drugiego pipeline'u.

### Pobieranie

- D01: wyszukiwanie, wybór i pobieranie ręczne działają bez subskrypcji.
- D02: subskrypcja pamięta tytuł/sezon, odcinki, dopuszczone źródła i kryteria
  wydania. Niepewne dopasowanie wymaga decyzji zamiast pobrania pierwszego wyniku.
- D03: pobranie i przetworzenie są dwoma stanami, z własnym postępem i błędami.
- D04: błędny indekser albo klient torrent nie blokuje lokalnej pracy AniShift.
- D05: brak powtórnych pobrań po restarcie; nie kasować cudzych torrentów,
  nie zmieniać globalnego seedowania ani zawartości bez osobnej zgody.
- D06: nazwy i ścieżki z sieci są niezaufane: kontrola wyjścia poza katalog,
  kolizji Windows, symlinków i niepożądanych typów plików przed zapisem/importem.
- D07: źródła wybiera użytkownik; dokumentacja i testy nie rozpoczynają pobierania
  chronionych materiałów. Testy integracji korzystają z własnych legalnych fixture'ów.

### Układ napisów

- S01: zwykły dialog otrzymuje naturalny polski podział bez utraty słów,
  interpunkcji, kolejności ani grafemów. Unikać rozpoczynania drugiego wersu od
  `się`; traktować to jako kontrakt łamania wersu, nie zakaz cytowania takiego tekstu.
- S02: nie poprawiać szerokości przez zmianę znaczenia ani automatyczne skracanie
  tłumaczenia. Priorytet składni przed estetyczną równością wersów.
- S03: ozdobne napisy zachowują kontekst pozycji, stylów, transformacji,
  warstw, czasów i rysunków. Oryginalne podziały są informacją layoutową, nie
  samą proporcją liczby znaków.
- S04: niespełnialne jednocześnie ograniczenia mają jawną strategię degradacji
  i diagnozę, nie ciche wypchnięcie tekstu poza kadr lub zniszczenie ozdobnego ASS.
- S05: układ odnosi się do obrazu wideo. Oddzielić błąd pliku od nadpisywania
  ASS przez odtwarzacz; nie obiecywać kontroli nad dowolną konfiguracją odtwarzacza.

## Jakość, zakres i zakazy

KISS: reuse obecnej fasady, zdarzeń i renderera; brak reorganizacji katalogów
bez konkretnej wykazanej korzyści. Rejestry silników pozostają tylko w domenach
`translation`, `tts`, `llm`. Wydajność mierzyć, nie wywodzić z liczby testów.

Osiem pól presetu jest już dostępnych. Planowanie awarii nowych funkcji jest wymagane, lecz nie wykonujemy
teraz hard-kill, długich testów produktu, obciążeń ani live prób dostawców.

Poza bieżącym wykonaniem: A/B promptów, licznik kosztów, nowy GUI, PyAV,
multi-voice i metadane bez zastosowania. Odtwarzacz, VPS i synchronizacja są
pomysłami, nie implementacją. TXT → audiobook pozostaje oddzielnym etapem.

### Dostarczenie i oglądanie

- R01: wysyłać tylko kompletne produkty. Retry uploadu nie tłumaczy ponownie
  i nie usuwa jedynej lokalnej kopii.
- R02: „gotowe na serwerze” nie oznacza „zsynchronizowane na komputerze”.
- R03: katalog wykorzystuje istniejące produkty i historię; nie jest drugim
  ręcznie utrzymywanym trackerem watched.
- R04: niepewny tytuł, sezon, numer lub wydanie wymaga konkretnej decyzji.
- R05: przed serwerem sprawdzić OS/TTS/providerów, zasoby, autoryzację,
  backup stanu, retencję i zasady storage/źródeł. Bez publicznego API torrenta.

## Decyzje wymagające zatwierdzenia

| ID | Propozycja | Dlaczego potrzebna decyzja |
| --- | --- | --- |
| O13 | JSON czy SQLite i model pojedynczego writera | Wybrać po określeniu przejść stanu i restartu |
| O14 | Fizyczne podfoldery czy wirtualny katalog | Nie zmieniać obecnego workspace bez decyzji |
| O15 | VPS/OS, storage i synchronizacja/oglądanie | Research kosztów, ograniczeń i realny proof przed wdrożeniem |
| O16 | Kontrolowana kopia → Auto czy magnet → Auto jako pierwszy wycinek | Wybrać jeden wynik i zatwierdzić jego plan |
| O01 | Jedna płaska biblioteka z przełącznikiem obserwowania | W takim folderze zwykłe dodanie pliku przy aktywnym watcherze oznacza automatyczną pracę; wyjątek wymaga pauzy lub pominięcia |
| O02 | Obserwowanie tylko podczas działania AniShift w pierwszej wersji | Uruchomienie po zamknięciu programu wymaga osobnego procesu/autostartu; to inne zobowiązanie niż zwykły watcher |
| O03 | Najpierw qBittorrent jako zewnętrzny klient, źródła skonfigurowane przez użytkownika | Dostępność Web API i dopuszczone źródła trzeba potwierdzić przed implementacją |
| O04 | Pierwsza wersja pobiera tylko wydania zgodne z płaskim układem | Złożony torrent nie daje bezpiecznej gwarancji braku podfolderów; obsługa batchy wymaga osobnej polityki |
| O05 | Istniejące źródła przy pierwszym włączeniu wymagają wskazania, a automatyka dotyczy nowych | Nie rozpoczynamy przypadkiem pracy nad całą biblioteką |
| O06 | Osobne plany dla dialogu i ozdobnego ASS; krótki automatyczny proof przed kodowaniem pełnego rozwiązania | Ta sama heurystyka nie gwarantuje poprawnej gramatyki, dopasowania geometrii i wszystkich transformacji |
| O11 | Tylko dla późniejszego watchera zewnętrznych zapisów ustalić protokół gotowości | Import U11 zna koniec własnej kopii i nie jest blokowany tą decyzją; dla obcego writera stały rozmiar/mtime nadal nie dowodzi zakończenia |
| O12 | Politykę niewspieranych tekstowych eventów ASS ustalić po syntetycznym proof | Ostrzeżenie, niepełny produkt i odmowa mają różne skutki. Nie kopiować nietłumaczonego tekstu jako kompletnego polskiego produktu |

O03 obejmuje propozycję wyszukiwania przez włączone wtyczki qBittorrenta.
To nie jest obowiązek instalowania klienta/wtyczek ani uznanie zgodności
każdego wydania 5.x. Plan 02 najpierw wymaga izolowanego proof metadanych,
bezpiecznego zapisu i kontraktu konkretnej wersji. Bez niego nie wdrażać pobierania.

## Warunek odbioru tego pakietu

Pakiet oddziela wymagania od pomysłów, wdrożony kod od planów i dług od bramek
nowej funkcji. Propozycje O01–O06 oraz O11–O16 pozostają do zatwierdzenia.
Starsze szczegółowe plany są materiałem do przeplanowania, nie instrukcją wykonania.
Odbiór planów nie wymaga teraz od właściciela testowania filmu; implementacja
rusza dopiero po wskazaniu zaakceptowanej iteracji.
