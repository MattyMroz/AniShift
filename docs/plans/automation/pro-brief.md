# Brief dla ChatGPT Pro: następna użyteczna funkcja AniShift

## Zadanie

Pomóż wybrać JEDEN najbliższy wycinek, zweryfikuj niezbędne narzędzia i opracuj
jego plan implementacyjny. Nie projektuj szczegółowo całego serwera ani wszystkich
przyszłych funkcji. Nie implementuj bez akceptacji właściciela.

## Czytaj w tej kolejności

1. [Wizja](vision.md) — motywacja i korzyści dla właściciela.
2. [Specyfikacja](specification.md) — aktualne wymagania i nierozstrzygnięte O13–O16.
3. [Masterplan](masterplan.md) — stany pośrednie, nie gotowy plan kodowania.
4. Root AGENTS.md i właściwe instrukcje obszarów zmiany.
5. Aktualny kod `application/service.py`, `cli/run.py`, `application/sessions.py`,
   `cli/interactive/app.py`, `cli/interactive/prompts.py` — tylko potrzebne przepływy.
6. [Import i klient pobierania](import-and-stremio.md) oraz research/plany tego katalogu
   jako historyczne dowody. Nie traktować starych propozycji jako decyzji.

Jeśli nie masz repozytorium, poproś o te źródła. Nie zgaduj architektury na podstawie wizji.

## Fakty i granice

Baseline kodu 83150d8: działający Auto, tryb ręczny, wspólna fasada/scheduler,
pełne pola presetu, naprawiony scroll. 3102 lokalne testy PASS, 13 skip;
30 smoke używa prawdziwych narzędzi medialnych, lecz stubuje sieć TTS/tłumaczenia.
Użytkownik akceptuje codzienne działanie, nie deklaruje pełnego fault qualification.

Ogólny audyt, benchmarki, layout i polerka są odłożone na Issues. Nie stają się
bramką wszystkich nowych funkcji. Przyjęcie plików wymaga jednak źródeł bez utraty,
kontroli częściowych zapisów, kolizji, restartu i duplikatów.

Nie czytaj ani nie zmieniaj prywatnych promptów, runtime config, sekretów, logów
i materiału działającego tłumaczenia. Nie kończ jego procesu.
Nie ma zgody na instalowanie klienta/VPS, zmianę kont ani prób na prywatnych odcinkach.

## Wybór pierwszego wyniku

Rekomendacja prowadzącego i Fable: kontrolowana ścieżka pliku → kopia → Auto,
z minimalną trwałą historią. Własna kopia nie potrzebuje dodatkowego potwierdzenia
gotowości. Wklejenie w edytorze ustawień nadal jest edycją tekstu, nie importem.

Materialna alternatywa: magnet → jeden istniejący klient → ukończony plik → Auto,
jeżeli to usuwa ważniejszy codzienny krok. Na początku bez wyszukiwarki/subskrypcji.
Najpierw uzgodnij O16 z właścicielem; nie łącz obu dla pozornej kompletności.

## Co ma zawierać plan

- Obserwowalny rezultat i najmniejszy pionowy wycinek.
- Rzeczywisty punkt wejścia i wspólny owner historii. Bez własnego torrent stacka.
- Decyzję JSON/SQLite opartą na atomowych przejściach, jednym writerze i restartach;
  nie zakładać potrzeby rozbudowanej bazy ani magicznej bezawaryjności JSON.
- Wspólne przyjęcie dla kopii, klienta i późniejszego watchera; downloader nie
  zależy od filesystem watchera. Stan klienta pozostaje u klienta.
- Obsługę podstawowych błędów oraz proporcjonalne testy/krótki smoke, bez
  wielkiego frameworka testowego. Pełne bramki repo przed commitem.
- Jedną tematyczną gałąź, pliki i kolejność zmian, kryterium stopu i human check.
- Koszt budowy/utrzymania jakościowo, a cenę usług dopiero na zweryfikowanych danych.
- Źródła techniczne przypięte do wersji i wyraźne odróżnienie dokumentacji od
  runtime proof. Nie powtarzać bez sprawdzenia twierdzeń ze starszych planów.

## Ważne dla późniejszego kierunku

Jedna lista historii/gotowości, bez drugiego ręcznego trackera.
„Następny odcinek do zdobycia” jest pokazany wprost; nie mylić z obejrzeniem.
Katalog może grupować serie wirtualnie; fizyczne podfoldery wymagają decyzji.
VPS to headless tryb tego samego produktu; lokalny tryb nie potrzebuje serwera.
Drive to kandydat, nie wybrana technologia. Upload ma własne retry/stan/retencję.
Właściciel deklaruje 10 TB miejsca w Drive i szacuje bibliotekę na około 200 GB.
Traktuj to jako niezweryfikowane założenia: porównaj synchronizację, dostęp
bezpośrednio do serwera i inne adekwatne warianty. Wynik ma spełniać cel użytkownika,
nie realizować obowiązkowo przykład z rozmowy.
MAL/AniList i rozmowa są opcjonalne. Brak obietnic 4K, natychmiastowych premier
lub nieograniczonych zasobów; brak dowolnej powłoki dla agenta.

## Format odpowiedzi

Krótka rekomendacja → otwarte materialne decyzje → plan tylko wybranej iteracji
→ minimalny proof/testy → warunek odbioru. Każdy nowy ficzer uzasadnij czynnością,
której użytkownik nie będzie już musiał wykonywać.
