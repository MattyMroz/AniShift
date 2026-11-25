---
kind: specification
status: accepted
updated: 2026-11-26
---

# Specyfikacja: Biblioteka jako widok tytułów i okładki w panelu

Stan faktyczny: [current-state.md](current-state.md). Dowody o terminalu i AniList: [research-covers.md](research-covers.md).
Wykonanie: [plan.md](plan.md). Decyzje O-1…O-11 przyjął właściciel 2026-11-25 (rekomendacje z poprzedniej wersji tego
dokumentu); poniżej są zapisane jako ustalenia, bez otwartych pytań.

## Cel

1. Biblioteka pokazuje tytuły, nie surowe zestawy: lista tytułów → Enter → `BIBLIOTEKA › <tytuł>` z odcinkami.
2. Przy około 30 tytułach w trzech językach właściciel rozpoznaje tytuł po okładce, bez zmiany stylu panelu.

## Użytkownik i intencja

Właściciel, lokalnie na PC z Windows, w Windows Terminal. Chce zobaczyć obrazek, poznać tytuł, wybrać, obejrzeć, usunąć
(`docs/ideas.md`, sekcja 2). Biblioteka właściciela 2026-11-26: 299 zestawów, z czego 228 pobrał AniShift (33 wpisy
AniList), a 71 to pliki ręczne (28 różnych tytułów z nazw plików); 23 subskrypcje.

## Ustalenia

- U-1. Wygląd panelu zostaje: niebieski akcent, górny i dolny panel, paleta, nagłówek, stopka i separatory bez zmian.
  Dochodzą nowe elementy (widok odcinków, pole wyszukiwania, slot okładki), ale nie nowy styl.
- U-2. Dysk zostaje płaski: `workspace/ready/` bez folderów serii. Grupowanie istnieje tylko w danych ownera i w widoku.
- U-3. Tożsamość tytułu zestawu pobranego przez AniShift pochodzi z klucza AniList zapisanego w stanie rezydenta
  (`downloaded_episodes`), nigdy z nazwy pliku. Skutek: grupowanie Biblioteki nie zależy od formatu nazwy grupy ani od
  przyszłych nazw z workstreamu 23.
- U-4. Wiersz listy to seria (O-4): wszystkie wpisy AniList połączone łańcuchem `PREQUEL`/`SEQUEL` są jednym tytułem.
  Sezon pokazuje kolumna `Nr` jako `SxxEyy`.
- U-5. Plik ręczny bierze tytuł z nazwy pliku. Przypisanie do AniList wymaga kryterium pewności z F-6; inaczej zostaje
  `z nazwy` albo „Nie rozpoznano”, nigdy ciche przypisanie.
- U-6. Kosz Windows i wielopoziomowe Ctrl+Z działają jak dziś (O-6 wdrożone: `latest_deletion` pomija przywrócone usunięcia,
  historia obejmuje jedno uruchomienie rezydenta).
- U-7. Owner (rezydent) jest jedynym źródłem prawdy o zestawach, tożsamości tytułów, okładkach i usuwaniu. Panel czyta
  projekcje przez `ResidentSession`; render nie robi I/O ani sieci.
- U-8. Obecny podział zakładek zostaje (O-1). Biblioteka staje się widokiem tytułów; Anime, Subskrypcje i Przetwarzanie
  zachowują przepływ.
- U-9. Okładka pojawia się w Bibliotece (lista tytułów i widok odcinków otwartego tytułu) i na liście Subskrypcji (O-3).
- U-10. Okładka jest obrazem SIXEL rysowanym tym samym mechanizmem co natywna maskotka (jedna kotwica, jeden slot obrazu w
  rendererze), nie drugim mechanizmem.
- U-11. Pytanie Enter/Esc przed usunięciem pada tylko, gdy usuwa się więcej niż jeden zestaw (O-7); pojedynczy odcinek
  usuwa się od razu, jak dziś.
- U-12. Przewijanie przy wielu tytułach rozwiązuje filtr `/` listy tytułów plus istniejące klawisze stron (O-8).
- U-13. Zestawy z nazwą, z której nie da się odczytać tytułu ani odcinka, tworzą jeden wiersz „Nie rozpoznano” na końcu
  listy (O-9).
- U-14. Enter na liście tytułów otwiera tytuł; odtwarzanie przenosi się do widoku odcinków (O-11).
- U-15. Wersja 1 trzyma w cache wyłącznie okładki tytułów z Biblioteki i Subskrypcji; pytanie do AniList o zgodę na cache
  zadaje właściciel osobno, poza tym workstreamem (O-10).
- U-16. AniShift działa tylko na Windows, w Windows Terminal (u właściciela 1.25, SIXEL od 1.22). Bez SIXEL panel wygląda
  jak bez okładek.
- U-17. Pliki okładek leżą w `config/covers/` (katalog konfiguracji AniShift, gitignorowany, poza `workspace/` i poza
  systemem); nazwa pliku wynika wyłącznie z ID AniList.

## Wymagania funkcjonalne

### Tożsamość tytułu

- F-1. Owner nadaje każdemu zestawowi pobranemu przez AniShift ID wpisu (`anilist_id`), ID serii (`series_id`, najwcześniejszy
  sezonowy wpis łańcucha) i tytuł serii; źródło tytułu to `key`.
- F-2. Zanim owner pozna serię (pierwsze sekundy po starcie, awaria AniList), zestaw z kluczem grupuje się po swoim
  `anilist_id`, a tytuł bierze z nazwy pliku. Po poznaniu serii przechodzi pod tytuł serii bez ingerencji użytkownika.
- F-3. Zestaw ręczny grupuje się po znormalizowanym tytule z nazwy pliku (`library_label` + `normalize_series`); źródło
  tytułu to `name`. Wiersz tytułu złożonego wyłącznie z takich zestawów ma oznaczenie `z nazwy` w kolumnie `Stan`.
- F-4. Zestaw, którego nazwy `library_label` nie rozpoznaje (brak tytułu, sezonu i odcinka), trafia do wiersza
  „Nie rozpoznano”.
- F-5. Owner próbuje rozpoznać tytuły ręczne w AniList, najwyżej jedno wyszukiwanie na unikalny tytuł z nazwy w jednym
  uruchomieniu rezydenta, sekwencyjnie przez wspólną bramkę sieci. Wynik trzyma w pamięci.
- F-6. Kryterium pewności rozpoznania: wśród kandydatów wyszukiwania dokładnie jeden ma alias, którego
  `normalize_series(strip_season(alias))` równa się `normalize_series` tytułu z nazwy i którego sezon (`season_hint(alias)`,
  brak = 1) równa się sezonowi z nazwy (brak = 1). Zero albo więcej niż jeden taki kandydat, błąd albo 429 = `z nazwy`.
  Rozpoznany zestaw ma źródło `recognized` i dalej zachowuje się jak zestaw z kluczem (seria, okładka, tytuły odcinków).

### Widok tytułów

- F-7. Zakładka Biblioteka otwiera się na liście tytułów z kolumnami `Tytuł`, `Odcinki` (liczba zestawów na dysku) i `Stan`
  (`Gotowe`, liczba zestawów z problemem albo `z nazwy`). Kolejność naturalna po tytule, „Nie rozpoznano” na końcu.
- F-8. Enter na tytule otwiera `BIBLIOTEKA › <tytuł>` z odcinkami w kolumnach `Nr`, `Tytuł`, `Emisja`, `Stan` (układ ekranu
  odcinków Anime). `Nr` to `SxxEyy`, a bez numeru `—`. Odcinki są posortowane po sezonie i numerze.
- F-9. `Tytuł` i `Emisja` odcinka z kluczem lub rozpoznanego pochodzą z listy odcinków AniList/ani.zip; brak danych to `—`,
  bez błędu. Odcinek `z nazwy` i „Nie rozpoznano” pokazuje w kolumnie `Tytuł` nazwę zestawu.
- F-10. Esc i Backspace w widoku odcinków wracają do listy tytułów z kursorem na tym samym tytule; Esc na liście tytułów
  wraca do Home jak dziś. Okruszek `Biblioteka` jest klikalny.
- F-11. Enter na odcinku odtwarza jego główny wynik; `F` pokazuje folder; `D` otwiera szczegóły zestawu (lista plików), z
  których Esc wraca do widoku odcinków.
- F-12. `/` na liście tytułów otwiera pole filtra; lista pokazuje tylko tytuły, których znormalizowany tytuł zawiera
  znormalizowany tekst. Esc w polu czyści filtr.
- F-13. Kliknięcie wyniku w zasobniku otwiera tytuł zawierający wskazany zestaw i stawia kursor na jego odcinku.

### Zaznaczanie i usuwanie

- F-14. W widoku odcinków Space zaznacza i odznacza odcinek, `A` zaznacza i odznacza wszystkie.
- F-15. Del w widoku odcinków usuwa zaznaczone odcinki, a bez zaznaczenia odcinek pod kursorem.
- F-16. Del na liście tytułów usuwa wszystkie zestawy tytułu (także wiersza „Nie rozpoznano”).
- F-17. Usunięcie więcej niż jednego zestawu najpierw pyta „Usunąć <liczba> odcinków? Enter tak · Esc nie”.
- F-18. Usuwanie wielu zestawów biegnie w jednym wątku roboczym i jednej sesji, zestaw po zestawie przez
  `preview_deletion` → `delete_set`. Odmowa jednego zestawu przywraca jego wiersz z komunikatem i nie zatrzymuje pozostałych.
- F-19. Po usunięciu wielu zestawów komunikat brzmi „Usunięto <liczba> · Ctrl+Z cofa po jednym”. Ctrl+Z cofa usunięcia po
  jednym, jak dziś.

### Okładki

- F-20. Owner pobiera w tle okładkę każdego wpisu AniList z subskrypcji, zestawów z kluczem i rozpoznanych, którego okładki
  nie ma w cache, i zapisuje ją jako `config/covers/<anilist_id>.jpg`. Nigdy nie pobiera z wątku renderu ani klawiszy.
- F-21. Okładka tytułu Biblioteki to okładka wpisu jego najnowszego zestawu na dysku (najwyższy sezon, potem numer). Okładka
  wiersza Subskrypcji to okładka jej wpisu.
- F-22. Gdy terminal ma SIXEL, jest miejsce, a na liście jest choć jeden wiersz z okładką w cache, ekran listy ma slot
  okładki po prawej stronie tabeli, pokazujący okładkę wybranego wiersza (w widoku odcinków: okładkę otwartego tytułu).
- F-23. Bez SIXEL, bez miejsca albo bez żadnej okładki na liście ekran jest identyczny jak bez funkcji okładek: bez slotu,
  placeholdera i komunikatu.
- F-24. Wiersz bez okładki przy widocznym slocie zostawia slot pusty. Zmiana wybranego wiersza zmienia obraz w tym samym
  miejscu bez czyszczenia całego ekranu.

## Wymagania jakościowe

- Q-1. Responsywność: kodowanie SIXEL okładki (około 250–350 ms, pomiar w researchu) biegnie w tle; ruch kursora nigdy na nie
  nie czeka. Ocena: test „render nie koduje i nie czyta plików” i checkpoint właściciela.
- Q-2. Sieć: tożsamość serii i adresy okładek to najwyżej kilka zapytań GraphQL na uruchomienie rezydenta; pliki okładek idą
  z CDN `s4.anilist.co` sekwencyjnie. Brak 429 w zwykłej pracy. Ocena: licznik zapytań w testach i log liczników.
- Q-3. Prywatność i logi: logi i cache zawierają tylko ID i liczniki, bez ścieżek absolutnych, URL-i i tytułów.
- Q-4. Wygląd: ocenia właściciel na własnej Bibliotece; nie ma metryki liczbowej.

## Inwarianty

- I-1. Owner jest jedynym źródłem prawdy o zestawach, tożsamości plików i usuwaniu (`LibraryFileIdentity`,
  `preview_deletion`). Widok tytułów jest projekcją i niczego nie usuwa sam.
- I-2. Widok nie zmienia układu `workspace/ready/` ani nazw plików.
- I-3. `library_label` zostaje źródłem etykiety zestawów bez klucza (kontrakt `test_library_label.py`,
  `test_library_columns.py`).
- I-4. Odmowy ownera przeżywają obce snapshoty, nie zmianę wyboru; spóźniony wynik nie nadpisuje nowszego kontekstu.
- I-5. Panel nie importuje Loguru i nie robi sieci; `WatchState` nie zmienia schematu.
- I-6. Klasyfikacja tożsamości odcinka (H1) i jej dane wejściowe (`FranchiseGraph` pojedynczego wpisu) zostają bez zmian.
- I-7. Maskotka Home i Auto wygląda i animuje się jak dziś.

## Ograniczenia

- Prompt Toolkit przy skróceniu linii wysyła `erase_end_of_line` (odczyt `prompt_toolkit/renderer.py`), co może skasować
  część rastra po prawej stronie tekstu. Slot musi to przeżyć (plan: ponowne rysowanie, gdy zmieni się linia w wierszach
  slotu).
- Raster SIXEL nie da się przyciąć, więc slot stoi w stałym miejscu poza przewijanym tekstem i w całości mieści się nad
  stopką.
- Limit AniList GraphQL w dniu pomiaru: 30 zapytań na minutę (`X-RateLimit-Limit: 30`).

## Zakazane

- Zmiana palety, nagłówka, stopki, separatorów, maskotki i stylu wierszy.
- Foldery serii w `workspace/ready/` i zmiana nazw plików (należy do workstreamu 23).
- Ciche przypisanie pliku ręcznego do AniList.
- Pobieranie okładek z renderu, z wątku klawiszy albo obok wspólnej bramki sieci ownera.
- Druga ścieżka renderu obrazów (półbloki), drugi slot obrazu w jednej klatce, miniatury w wierszach listy.
- Nowa zależność; Pillow, Rich, Prompt Toolkit, httpx i stdlib wystarczą.
- Zmiana `WatchState` (schemat, nowe trwałe pola).
- Zmiany pod Linuksa.

## Zakres

- Tożsamość serii w ownerze, rozpoznawanie plików ręcznych, pola zestawu w snapshotcie.
- Widok tytułów i odcinków Biblioteki, filtr, nawigacja z zasobnika, zaznaczanie i usuwanie wielu.
- Okładki: zapytania AniList, cache w `config/covers/`, slot SIXEL w Bibliotece i na liście Subskrypcji.

## Poza zakresem

- Inne ekrany: Anime (wyszukiwanie), widok odcinków subskrypcji, Przetwarzanie, Historia.
- Odcinki, które dopiero się pobiorą, w widoku tytułu Biblioteki (należą do Subskrypcji).
- Synchronizacja z MAL/AniList, odtwarzacz (21-playshift), tytuły odcinków z TVmaze (19, issue #58).
- Wspólne nazwy plików i jednorazowe przemianowanie `ready/` (workstream 23).

## Styk z workstreamem 23

- Biblioteka grupuje zestawy z kluczem po `series_id` z ownera, więc przemianowanie plików przez 23 nie zmienia grup.
- Tytuł serii, który 23 wpisze w nazwę pliku („angielski tytuł serii z AniList”), i tytuł wiersza Biblioteki mają jedno
  źródło: tożsamość serii ownera z F-1. Workstream 23 używa jej, zamiast liczyć tytuł drugi raz.
- Rozpoznanie pliku ręcznego (F-5, F-6) ma jedno miejsce w ownerze; jeśli 23 potrzebuje klucza AniList dla plików ręcznych,
  bierze go stąd.
- Format nazw 23 (`<tytuł> - SxxEyy - <tytuł odcinka>`) czyta `library_label` poprawnie (pomiar w researchu); test
  kontraktowy tego formatu wchodzi z tym workstreamem.
- Kolejność scalania jest dowolna: 18 nie czyta nazw z 23, a 23 nie zmienia kontraktu `LibrarySet`.

## Odłożone

- Półbloki ANSI jako okładka bez SIXEL: druga ścieżka renderu za gorszą jakość.
- Trwały zapis tożsamości serii i rozpoznań w `WatchState`: dziś jedno zapytanie zbiorcze i 28 wyszukiwań na start
  rezydenta, więc pamięć procesu wystarcza.
- Usuwanie nieużywanych okładek z cache (dziesiątki plików po około 80 KB).
- Okładki w Anime, w widoku odcinków subskrypcji i w Przetwarzaniu.

## Odrzucone

- Jeden wspólny widok tytułów dla czterech zakładek (O-1): zmienia przepływ czterech zakładek bez zysku dla Biblioteki.
- Grupowanie zestawów z kluczem po tytule z nazwy pliku: zależy od formatu nazw grup i od workstreamu 23.
- Grupowanie po `series_title` tytułu angielskiego wpisu: nowy sezon często nie ma jeszcze angielskiego tytułu w AniList, więc
  sezony jednej serii trafiłyby do różnych wierszy.

## Warunki sukcesu

| Warunek | Instrument |
|---|---|
| Sezony jednej serii z kluczem tworzą jeden tytuł, niezależnie od nazw plików | testy jednostkowe tożsamości serii na zapisanych grafach AniList |
| Plik ręczny bez pewności ma `z nazwy`, nigdy `key` ani `recognized` | testy jednostkowe kryterium F-6 |
| Lista tytułów i widok odcinków mieszczą się w szerokościach 50, 80 i 120 i w progach wysokości | testy wzorca `test_library_columns.py` |
| Del wielu zestawów, pytanie, odmowa jednego, Ctrl+Z po jednym | testy wzorca `test_library_actions.py` |
| Slot znika bez śladu bez SIXEL, bez miejsca i bez okładek | testy układu i renderera z atrapą wyjścia |
| Zapytania okładek i zapis cache odrzucają obcy host, `http`, za duży i uszkodzony plik | testy jednostkowe katalogu |
| Wygląd, płynność i brak śladów rastra na prawdziwej Bibliotece | checkpointy właściciela w planie |
| Bramki repo | `ruff check`, `ruff format --check`, `mypy`, `pytest -n 6` według `AGENTS.md` |
