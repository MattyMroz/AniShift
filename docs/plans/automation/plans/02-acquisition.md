---
kind: plan
status: replan-required
baseline: main 6eef7d1
created: 2026-09-05
branch: work/automation/02-acquisition
---

# Plan 02: pozyskiwanie odcinków

Aktualizacja kierunku: stan pobrania uzgadnia się z klientem, a ukończony plik
przekazuje do wspólnego intake, nie obowiązkowo do watchera. Poniższy wcześniejszy
projekt wymaga przeplanowania pod jedną historię zleceń i wybrany mały wycinek.
Wybór klienta i proof jego wersji nie zostały zatwierdzone przez samą wizję.

## Rezultat i granica gotowości

Docelowo użytkownik wyszukuje tytuł, wybiera odcinki i otrzymuje gotowe
pliki w płaskiej bibliotece. Pobranie ma osobny postęp; przekazanie do
watchera uruchamia istniejący pipeline. Subskrypcje dochodzą później.

Ten dokument ustala kontrakty i **pierwszy eksperyment**, nie jest jeszcze
instrukcją wdrożenia całego downloadera. E02 musi potwierdzić bezpieczne
uzyskanie metadanych przed zapisem payloadu. W drugim drafcie pozostała luka:
zatrzymany magnet może nie pobrać metadanych, a sprawdzenie symlinka dopiero
po pobraniu nie spełnia D06. Poniższy plan zastępuje tę sekwencję.

## Propozycje do zatwierdzenia

- O03: jeden zewnętrzny qBittorrent; wyszukiwanie przez jego włączone wtyczki,
  nie nowy parser każdego indeksera. Repo nie instaluje wtyczek ani nie
  wybiera ich za użytkownika. Brak wtyczki/Pythona klienta daje instrukcję.
- O04: pierwsza wersja tylko dla zweryfikowanych płaskich wydań. Batch jest
  wyborem plików dopiero po walidacji; nie zakładać, że usunięcie nadrzędnego
  katalogu usuwa wszystkie zagnieżdżenia.
- HTTP: preferować istniejący `httpx`, zwykły moduł, bez rejestru silników.
  Nie instalować nic w tej fazie.
- Finalny zapis obok źródeł; brak samodzielnego przenoszenia danych klienta.
  E02 ma sprawdzić także jego ustawienia katalogu nieukończonych pobrań.

## Zweryfikowane punkty integracji

`AppService.plan_auto(group_ids, preset)` przyjmuje podzbiór, wspólny scheduler
pozostaje wykonawcą. Writer rejestru z Planu 01 przyjmuje gotowość, acquisition
nie edytuje jego JSON równolegle. `AppService.update_secret` i katalog pól
stanowią wzorzec ustawień połączenia; `setup/doctor.py` wzorzec checku.

Nowa domena używa `AcquisitionError(AniShiftError)` z precyzyjnymi wariantami
transient/fatal według istniejącej hierarchii. Nie logować haseł, SID,
pełnych URL-i, metadanych torrenta ani prywatnych nazw.

## E02 — dowód przed implementacją

Nowy fakt: lokalnie zarejestrowany qBittorrent 5.2.3. W odpowiadającym tagu
źródłowym znaleziono osobne operacje pobierania/parsowania/eksportu metadanych.
Pierwszy kandydat E02 to ta ścieżka, nie zatrzymany magnet.
[Dowody i Stremio](../import-and-stremio.md). Nie wykonano jeszcze próby runtime.

### Pytania

1. Jaka **konkretna wersja wydania klienta i Web API** jest wspierana?
   Kod rozwojowy master nie dowodzi kontraktu wszystkich wydań 5.x.
2. Czy można uzyskać pełną surową metadaną przed zapisaniem zawartości plików,
   sprawdzić hash i atrybuty oraz ustawić selekcję przed startem payloadu?
3. Czy wybrany layout i ustawienia klienta rzeczywiście zapisują do
   docelowej biblioteki bez kolizji, przenoszenia i podfolderów?
4. Jak zachowują się pojedynczy plik, płaski batch, magnet, v1/v2/hybrid
   i timeout dodania?

### Izolacja i procedura

Przy przyszłej realizacji użyć własnych krótkich fixture'ów i **osobnego
profilu klienta** z izolowanymi katalogami. Nie podłączać eksperymentu do
sesji torrentów użytkownika. Nie wymagać filmu, odsłuchu ani hard-kill.
Jeśli izolacji nie można zapewnić, zatrzymać eksperyment.

Przypiąć wersję klienta, API i źródła odpowiadającego tagu. Kandydat dla
magnetu: kontrolowany etap metadata-only z warunkiem zatrzymania po
metadanych, nie bierne oczekiwanie na zatrzymany magnet. Ustalić, czy
metadane dają się pobrać/wyeksportować bez uruchomienia payloadu oraz czy
klient nie tworzy plików przed zakończeniem tej walidacji. Samo istnienie
parametru API nie jest dowodem.

Dla pliku torrent pobrać ograniczoną rozmiarem metadaną do izolowanego
stagingu, sprawdzić hash na właściwych bajtach info i zwalidować strukturę
przed przekazaniem klientowi. **Nie pisać własnego parsera bencode w ciemno**:
wybór istniejącej biblioteki lub udokumentowanego narzędzia jest wynikiem
E02, z oceną Python 3.14, limitów parsowania i ewentualnej zależności.
Torrent tylko v2/hybrid nie może być potraktowany jak btih v1.

Fixture'y obejmują traversal, symlink/reparse, padding, nazwy Windows,
kolizje case-insensitive, podfoldery, istniejący plik, zatrzymane ukończenie,
wybrane pliki oraz usunięcie torrenta przez użytkownika. Złośliwych metadanych
nie przekazywać klientowi przed walidacją. Porównać stan dysku przed/po.

### Wynik i stop

Outcome podaje przypięty kontrakt, zanonimizowane odpowiedzi, potwierdzoną
kolejność operacji i niewspierane warianty. Jeżeli brak bezpiecznego
metadata-only, magnety pozostają niewspierane; jeżeli także torrent nie
spełnia D06, integracja pobierania pozostaje zablokowana. **Nie osłabiać
D06 do kontroli po zapisie.** Wtedy można osobno zaproponować tylko
wyszukiwanie/ręczne przekazanie gotowych źródeł, po akceptacji właściciela.

## Kontrakt docelowy po pozytywnym E02

### Wyszukiwanie

Wybrać jeden kontrakt Search API i jego wersję. Start zwraca identyfikator;
wyniki odbierać stronami z limitem i offsetem, deduplikować i doczytać
końcowy snapshot przed usunięciem własnego zadania wyszukiwania.
Limit czasu zwraca oznaczony niepełny wynik, nie udaje kompletnego sukcesu.
Brak opcjonalnej daty oznacza „brak danych”, nie wymyśloną datę.

Lista: tytuł, sezon, odcinek, grupa, jakość, źródło, rozmiar, seedy.
Sortowanie i grupowanie nie może ukrywać alternatywnych wydań. Niepewny
numer/tytuł ma status wymagający wyboru. Nazwa wyniku nie dowodzi nazw
plików wewnątrz torrenta. Źródła do pierwszej wersji muszą dawać odwołania,
które E02 umie bezpiecznie rozwiązać; nie uruchamiać dowolnego download
pluginu lub przekierowania jako obejścia walidacji.

### Dodawanie i bezpieczeństwo

Stan: `wanted → metadata → validated → added → downloading → completed
→ handed_over`, z odrębnymi `failed/cancelled/ambiguous`.
Zapis intencji następuje **przed** dodaniem do klienta. Trwała tożsamość
obejmuje klienta, root, hash(e), wybrane indeksy i unikalny identyfikator
zlecenia. Jeden koordynator pozyskiwania na root — ten sam właściciel sesji
co watcher — serializuje wpisy i operacje.

Kontrola surowej metadanej poprzedza zapis payloadu. Odrzuca traversal,
absolutne ścieżki, ADS, kontrolne znaki, zarezerwowane nazwy, końcowe
kropki/spacje, symlinki, nieobsługiwane typy i kolizje po normalizacji Windows.
Sposób traktowania paddingu i granic pieces potwierdza E02; nie obiecywać,
że priorytet zero oznacza brak każdego fizycznego bajtu niechcianego pliku.
Niepewne mapowanie ścieżek blokuje start.

Kolizje sprawdzać według zweryfikowanych nazw **przed add/start**, nie nazwy
wyszukania. Pliki docelowe rezerwuje koordynator; ponowna kontrola tuż przed
startem chroni przed innym zleceniem AniShift. Zewnętrznego writera i klienta
nie traktować jako objętych naszą blokadą. Użytkownik nie może równolegle
podmieniać zarezerwowanych plików; wykryta zmiana zatrzymuje przekazanie.

Pliki zarządzanego pobrania są wyłączone z ręcznej akceptacji A i heurystyk
watchera aż do `handed_over`. Brak gotowości nie jest błędem postępu UI.

### Ownership, retry i ukończenie

Tag `anishift` nie dowodzi własności. Potrzebny zgodny trwały wpis zlecenia,
hash, root i identyfikator klienta. Istniejący cudzy hash oznacza konflikt,
bez przejęcia, retagowania, stop czy delete. Po timeout `add` rekoncyliować
intencję i stan klienta; nie powtarzać POST w ciemno. Brak jednoznacznego
dowodu daje `ambiguous`, wymaga decyzji.

Monitor jest częścią use case'u działającego niezależnie od otwartego
widoku, a nie renderera. Po restarcie odtwarza własne nieterminalne wpisy;
nie ponawia automatycznie niepewnej operacji. GET może mieć ograniczony
backoff. Stop/start i zmiana priorytetów wymagają ponownej kontroli ownership
i aktualnego stanu przed retry. Przy 429/503 honorować poprawny
`Retry-After` z limitem i cancellation, inaczej backoff z limitem prób.
To nowe wymaganie adaptera: istniejący `_retry.py` go nie realizuje.

Ukończenie dotyczy **wybranych indeksów**, a nie samego globalnego procentu.
Zweryfikować je w API, brak checking/moving/error, końcowe ścieżki,
obecność, rozmiary i brak symlinków/reparse. Stan stopped nie wyklucza
ukończenia. Dopiero walidacja i przekazanie do jednego writera watchera
oznacza `handed_over`. Awaria pomiędzy tymi zapisami jest rozwiązywana
idempotentnie przez identyfikator przekazania.

Anulowanie zatrzymuje tylko własne zlecenie po ponownej weryfikacji.
Nie usuwa danych/torrenta, nie zmienia globalnego seedowania. Komunikaty
o błędach są klasyfikowane i sanitizowane, nie surowym tekstem klienta.

## Podział modułów i kolejność

Po E02 doprecyzować mały moduł `services/acquisition/` (klient, typy,
walidacja, błędy), `application/acquisition.py` (koordynator),
`config/acquisitions.py` (stan) i `cli/interactive/acquire.py` (widok).
Nie zmieniać struktury pozostałych domen.

Kolejność: E02 → aktualizacja tego planu → akceptacja → klient na fixture'ach
→ trwała intencja/reconciliation → handoff do watchera → lista i postęp
→ pełne bramki repo, review, tematyczne commity. Wejście w istniejącym
Auto/ustawieniach; nie dodawać piątej akcji Home bez nowej decyzji.

## Subskrypcje — następny, warunkowy etap

Po odbiorze ręcznego wyszukiwania i pobierania powstaje szczegółowy plan A03.
Interwał godziny jest propozycją; pętla żyje w działającym AniShift.
Przechowuje tytuł, sezon, odcinki, dopuszczone źródła, kryteria wydań,
politykę v2 i wynik dopasowania. Bez nadrabiania wszystkich ticków po sleep,
bez kilku równoległych wyszukiwań tej samej subskrypcji. Pauza subskrypcji
i pauza przetwarzania są oddzielne. Reconciliation nie dodaje kolejnego
pobrania po restarcie. Niepewne wydanie czeka na użytkownika.

## Dowody i zakazy

Testy kontraktowe na `httpx.MockTransport`, własne fixture'y i syntetyczny
restart. Sprawdzić paginację, brak daty, 401/403/429, timeout POST, cudzy
hash, oba rodzaje gotowości, kolizję i dokładnie jednokrotny handoff na poziomie
wpisu (nie obiecywać exactly-once zewnętrznych wywołań).
Realny klient tylko w osobnym profilu po uzgodnieniu E02. Zero prawdziwych
indekserów, prywatnej biblioteki, instalacji wtyczek, globalnego seedowania,
uruchamiania funkcji w tej fazie planowania.

## Źródła kontraktu

[Web API wiki](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29),
[kontroler wyszukiwania](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/searchcontroller.cpp),
[kontroler torrentów](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/torrentscontroller.cpp)
— odczyt 2026-09-05. Master potwierdza istnienie operacji, nie zgodność konkretnego
wydania ani gwarancje I/O. Źródła przypięte do wydania i runtime proof są
obowiązkowym wynikiem E02.
