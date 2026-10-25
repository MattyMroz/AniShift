---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: katalog AniList odporny na awarię

## Cel

Gdy AniList nie odpowiada, AniShift dalej sprawdza i pobiera odcinki subskrypcji, otwiera znane wpisy i listy
odcinków oraz nazywa serie w Bibliotece. Panel mówi wprost, że działa na zapisanych danych AniList i z kiedy one są.

## Użytkownik i intencja

Właściciel ogląda anime lokalnie na PC, z około 20 subskrypcjami w sezonie. Awaria AniList z 2026-10-21 zatrzymała
wszystkie subskrypcje na co najmniej 4,5 godziny, choć ani.zip, arm-server, Kitsu i źródła wydań działały
(dependency-map.md, §7). Właściciel chce, żeby awaria jednego katalogu nie zatrzymywała aplikacji.

## Stan wyjściowy

- AniList jest jedynym źródłem wyszukiwania, grafu franczyzy, harmonogramu i łańcucha prequeli
  (dependency-map.md, §2).
- Dane AniList są pamiętane tylko w pamięci procesu przez 900 s albo `max-age` ani.zip; restart je czyści
  (dependency-map.md, §1).
- Graf franczyzy to surowy JSON AniList i zasila zamrożony cel H1 (dependency-map.md, §3).
- Żaden darmowy serwis bez klucza nie daje naraz F1–F3 w jakości AniList; Jikan wyłączono 2026-10-01
  (research.md, §1, §4.2).

## Ustalenia

- Katalog pozostaje zwykłym modułem `services/catalog`, bez rejestru silników. Skutek: rozwiązanie nie wprowadza
  wyboru silnika, `engines/` ani konfiguracji dostawcy (`anishift/services/AGENTS.md`, root `AGENTS.md`).
- `anilist_id` pozostaje jedynym kluczem wpisu. Skutek: stan rezydenta, rejestr decyzji i IPC nie zmieniają kluczy.
- Kopia odpowiedzi służy wyłącznie, gdy AniList zawiedzie. Skutek: przy działającym AniList zachowanie i liczba
  żądań są takie jak dziś.
- Dane z kopii mają ten sam kształt i tę samą kolejność węzłów co odpowiedź na żywo. Skutek: widok franczyzy i
  wejście H1 z kopii są tymi samymi, które AniList dał w chwili zapisu.

## Wymagania funkcjonalne

- **W1.** Każda udana odpowiedź AniList z grafem franczyzy i z harmonogramem wpisu jest zapisywana lokalnie;
  nowsza zastępuje starszą tego samego rodzaju i wpisu.
- **W2.** Gdy żądanie AniList o graf albo harmonogram kończy się błędem `TITLE_CATALOG_FAILED` (także przy cooldownie
  dostawcy i wyczerpanym budżecie żądań), katalog zwraca zapisaną odpowiedź tego wpisu wraz z chwilą jej zapisu.
  Bez zapisu błąd jest taki jak dziś.
- **W3.** Graf w trybie awaryjnym pochodzi z zapisu tego wpisu, a gdy go brak — z zapisanego grafu innego wpisu,
  który zawiera ten wpis i nie ma nierozwiniętego łańcucha.
- **W4.** Wyszukiwanie tytułu w trybie awaryjnym zwraca kandydatów z zapisanych grafów, których tytuł zawiera hasło.
  Brak trafień daje ten sam błąd co dziś („AniList nie odpowiada”), nie „Nie znaleziono tytułu”. Zależy od D3.
- **W5.** Kontekst sezonu (łańcuch prequeli) w trybie awaryjnym jest liczony z zapisanego grafu zawierającego wpis.
- **W6.** Sprawdzenie istniejącej subskrypcji na zapisanych danych przebiega jak na danych z AniList: cele, terminy,
  wyszukiwanie wydań, wybór i przekazanie do pobrania.
- **W7.** Lista odcinków zbudowana na zapisanym harmonogramie nie ma ostrzeżenia „Brak terminów emisji” i niesie
  chwilę zapisu danych. Ostrzeżenie zostaje, gdy harmonogramu nie ma ani na żywo, ani w zapisie.
- **W8.** Panel Anime pokazuje na liście odcinków i w widoku wpisów, że dane pochodzą z zapisu, oraz chwilę zapisu.
- **W9.** Zakładka Subskrypcje pokazuje wiersz statusu, gdy ostatnie sprawdzenie którejkolwiek subskrypcji użyło
  zapisanych danych, z najstarszą chwilą zapisu wśród nich. Wiersz znika, gdy każda z tych subskrypcji została
  sprawdzona na danych z AniList.
- **W10.** Nazwa serii w Bibliotece powstaje z zapisanego grafu, gdy AniList nie odpowiada.
- **W11.** Dodanie nowej subskrypcji w trybie awaryjnym zachowuje się zgodnie z D2.
- **W12.** Każda nieudana odpowiedź AniList na poziomie żądania (brak połączenia, status inny niż 200, błędy
  GraphQL, nieczytelne ciało) jest logowana z powodem (`unreachable`, `rejected`, `malformed`) i statusem HTTP, gdy
  był. Użycie zapisu jest logowane z rodzajem danych, `anilist_id` i wiekiem zapisu.
- **W13.** Przegląd subskrypcji po migracji (`review_pending`) nie kończy się na zapisanych danych; rekord czeka na
  odczyt z AniList, tak jak dziś przy braku harmonogramu.

## Wymagania jakościowe

- Błąd zapisu lub odczytu kopii nigdy nie zmienia wyniku operacji: zapis, który się nie udał, jest logowany; plik
  nieczytelny, uszkodzony albo w nieznanej wersji traktuje się jak brak zapisu.
- Dwa procesy (rezydent i panel bez rezydenta) mogą zapisywać jednocześnie bez uszkodzenia plików.
- Liczba zapisanych wpisów każdego rodzaju jest ograniczona (D5); nadmiar usuwa się od najdawniej zapisanych.
- Pliki kopii i log nie zawierają sekretów, nagłówków, ścieżek absolutnych ani tekstu wyszukiwania.
- Wszystkie odczyty i zapisy kopii odbywają się poza wątkiem UI panelu.

## Inwarianty

- Schemat `config/watch/state.json` (wersja 5) się nie zmienia.
- Golden i przypadki regresji H1 (`tests/fixtures/acquisition/identity-regressions.json`) pozostają bez zmian.
- Pamięć `_Remembered` i jej świeżość działają jak dziś.
- Panel i rezydent z tego samego checkoutu rozumieją te same widoki IPC; nowe pola mają wartości domyślne.

## Ograniczenia

- Python 3.14, Windows, bez nowej zależności.
- Regulamin AniList zakazuje używania API jako kopii zapasowej i masowego zbierania danych (research.md, §4.1).
  Kopia obejmuje więc tylko wpisy, które aplikacja sama odczytała dla użytkownika.
- Reguły logowania z root `AGENTS.md`: bez `ErrorContext.details`, payloadów i ścieżek absolutnych.

## Zakazane

- Rejestr silników, wybór dostawcy katalogu, nowy plik konfiguracji dostawcy.
- Drugi dostawca danych (Shikimori, TVmaze, Kitsu search i inne) w tej pracy.
- Zwracanie zapisu zamiast żądania, gdy AniList działa.
- Pobieranie z wyprzedzeniem wpisów, których aplikacja nie odczytała.
- Zmiana klucza wpisu, schematu stanu rezydenta i klasyfikacji H1.

## Zakres

- Lokalna kopia grafu franczyzy i harmonogramu AniList oraz jej użycie przy awarii (W1–W5, W10).
- Przepływ subskrypcji i listy odcinków na kopii (W6, W7, W11, W13).
- Sygnalizacja w panelu i logu (W8, W9, W12).
- Aktualizacja `services/catalog/AGENTS.md`, `config/README.md` i wpisu w `docs/ideas.md`.

## Poza zakresem

- Cache z TTL, który oszczędza żądania przy działającym AniList (druga połowa pomysłu z `docs/ideas.md`, §5).
- Okładki, tytuły odcinków z TVmaze i tytuły Biblioteki z nazw plików — osobne workstreamy 18 i 19.
- Wykrywanie przesunięć emisji podczas awarii.

## Odłożone

- Kalendarz Shikimori jako drugie źródło najbliższego odcinka trwających subskrypcji (D4). Powód: zapisany
  harmonogram AniList zawiera cały sezon (research.md, §4.1), a godziny zastępców się różnią (research.md, §5).
  Warunek powrotu: zapisane daty zawiodą w rzeczywistej awarii, np. przez przesunięcie emisji.
- Cache z TTL dla oszczędności żądań. Warunek powrotu: limit 30/min zacznie przeszkadzać przy działającym AniList.

## Odrzucone

- Jikan: publiczne API wyłączone 2026-10-01 (research.md, §4.2).
- MAL API v2: klucz klienta i brak dat odcinków (research.md, §4.3).
- AnimeSchedule: token aplikacji i atrybucja; powód z `docs/work/08-acquisition/specification.md` §11 nadal obowiązuje.
- AniDB: rejestracja klienta i nieznane limity (research.md, §4.10).
- Zmiana klucza stanu z `anilist_id` na MAL ID: migracja całego stanu bez zysku, bo arm-server już mapuje ID.
- Odbudowa grafu AniList z relacji Kitsu, MAL albo Shikimori: zmienia wejście zamrożonego H1.
- manami `anime-offline-database`: repozytorium zarchiwizowane (research.md, §4.9).

## Warunki sukcesu

- Test integracyjny odtwarza awarię: po udanym odczycie i restarcie usługi AniList odpowiada błędem, a sprawdzenie
  subskrypcji kończy się ofertą i przekazaniem do pobrania jak na danych z AniList (W2, W6).
- Testy jednostkowe pokrywają W1–W5, W7, W9, W11–W13, uszkodzony plik, limit wpisów, równoległy zapis i równoważność
  grafu z pliku i z odpowiedzi na żywo.
- Przy działającym AniList liczba żądań w istniejących testach nie rośnie.
- Właściciel w panelu widzi poprawny tekst statusu na liście odcinków i w Subskrypcjach (scenariusz w plan.md, §9).
- Bramki jakości z root `AGENTS.md` przechodzą.

## Nierozstrzygnięte

Decyzje właściciela. Każda zmienia zakres albo zachowanie.

- **D1. Lokalna kopia odpowiedzi AniList a regulamin.** Regulamin zakazuje „backup or data storage service” i
  masowego zbierania. Rekomendacja: **akceptować** kopię ograniczoną do wpisów odczytanych przez aplikację, z limitem
  liczby wpisów i bez pobierania z wyprzedzeniem. Interpretacja nie jest opinią prawną.
- **D2. Nowa subskrypcja w awarii.** Punkt odcięcia (`cut`) liczony z zapisanego harmonogramu utrwala się w stanie
  na zawsze. Rekomendacja: **odmawiać** z komunikatem „AniList nie odpowiada · nową subskrypcję dodasz po powrocie
  AniList”. Istniejące subskrypcje działają na kopii.
- **D3. Wyszukiwanie w awarii.** Rekomendacja: **tak** — przeszukiwać tytuły zapisanych grafów; panel pokazuje
  „AniList nie odpowiada · wyniki tylko z zapisanych tytułów”. Nowe tytuły znajdzie się dopiero po powrocie AniList.
- **D4. Drugi harmonogram (Shikimori).** Rekomendacja: **nie teraz**; wrócić, gdy zapisane daty zawiodą w awarii.
- **D5. Limit kopii.** Rekomendacja: **256 wpisów na rodzaj, bez limitu wieku**. Dziś 20 subskrypcji i około
  30 tytułów w bibliotece (`docs/ideas.md`, §2); nagrane grafy mają 11–171 KB (`tests/fixtures/search/
  anilist__franchise__*.json`), więc górna granica to kilkadziesiąt MB. Wiek danych widać w panelu, zamiast ich
  odrzucania.
- **D6. Teksty w panelu.** Propozycje:
  - lista odcinków i widok wpisów: „AniList nie odpowiada · dane z 21.10 17:14”;
  - Subskrypcje: „AniList nie odpowiada · subskrypcje działają na danych z 21.10 17:14”;
  - wyszukiwanie: „AniList nie odpowiada · wyniki tylko z zapisanych tytułów”.
  Rekomendacja: przyjąć i ocenić na checkpoincie w panelu.
