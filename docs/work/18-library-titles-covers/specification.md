---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: Biblioteka jako widok tytułów i okładki w panelu

Stan faktyczny: [current-state.md](current-state.md). Dowody o terminalu i AniList: [research-covers.md](research-covers.md).
Wykonanie: [plan.md](plan.md). Wszystkie punkty „Rekomendacja” czekają na akceptację właściciela; do tego czasu nic z nich
nie jest wymaganiem.

## Cel

1. (b) Biblioteka pokazuje tytuły, nie surowe zestawy: lista tytułów → Enter → `BIBLIOTEKA › <tytuł>` z odcinkami.
2. (a) Przy ok. 30 tytułach w trzech językach użytkownik rozpoznaje tytuł po okładce, bez zmiany stylu panelu.

## Użytkownik i intencja

Właściciel, lokalnie na PC (Windows). Chce zobaczyć obrazek, poznać tytuł, wybrać, obejrzeć, usunąć
(`docs/ideas.md`, sekcja 2). Nie chce zmiany wyglądu panelu (niebieski akcent, styl paneli góra i dół).

## Ustalenia obowiązujące (z poleceń właściciela i repo)

- U-1. Wygląd panelu zostaje; zmieniają się zachowanie, opcje i słowa. Skutek: żadna zmiana palety, nagłówka, stopki ani
  separatorów; nowy element układu wymaga decyzji O-2.
- U-2. Dysk zostaje płaski: `workspace/ready/` bez folderów serii. Skutek: grupowanie istnieje tylko w widoku i w danych ownera.
- U-3. Pliki pobrane przez Anime biorą tytuł i numer z zapisanego klucza AniList, bez zgadywania z nazwy
  (masterplan E6). Skutek: klucz `anilist_id` jest źródłem prawdy tożsamości tytułu dla tych plików.
- U-4. Pliki ręczne biorą tytuł z nazwy; przy braku pewności widać „Nie rozpoznano”, nigdy ciche przypisanie (masterplan E6).
- U-5. Kosz Windows i Ctrl+Z działają „jak dziś” (`docs/ideas.md`, sekcja 2). Skutek: patrz O-6, bo „jak dziś” jest jednopoziomowe.
- U-6. Owner (rezydent) jest właścicielem danych; panel czyta projekcje przez `ResidentSession`. Render nie robi I/O ani sieci
  (`anishift/cli/AGENTS.md`).
- U-7. Windows only; zero zmian pod Linuksa. Brak nowej zależności bez potrzeby (`uv add` tylko przez narzędzie).

## Wymagania funkcjonalne

### Widok tytułów (b)

- F-1. Zakładka Biblioteka otwiera się na liście tytułów. Wiersz tytułu: `Tytuł`, `Odcinki` (liczba zestawów na dysku), `Stan`
  (Gotowe albo liczba zestawów z problemem).
- F-2. Enter na tytule otwiera widok `BIBLIOTEKA › <tytuł>` z odcinkami na dysku w kolumnach `Nr`, `Tytuł`, `Emisja`, `Stan`
  (układ i nagłówki jak ekran odcinków Anime). `Nr` ma postać `SxxEyy`, a dla pliku bez numeru odcinka `—`.
- F-3. Esc i Backspace w widoku odcinków wracają do listy tytułów z zachowanym kursorem; Esc na liście tytułów robi to, co dziś
  (wyjście do Home). Okruszki są klikalne jak w pozostałych zakładkach.
- F-4. Tytuł wiersza pochodzi z jednego z czterech źródeł, rozróżnialnych w danych: `klucz` (AniList z pobrania), `rozpoznany`
  (plik ręczny dopasowany z pewnością do AniList), `z nazwy` (plik ręczny, tytuł z nazwy bez pewnego dopasowania),
  `nierozpoznany` (nazwa bez tytułu i odcinka). Wiersze `z nazwy` mają widoczne oznaczenie; `nierozpoznany` tworzy jeden wiersz
  „Nie rozpoznano”.
- F-5. Plik ręczny nigdy nie jest przypisany do tytułu AniList bez spełnienia kryterium pewności (definicja w O-5).
- F-6. Tytuł odcinka i data emisji pojawiają się dla zestawów z kluczem AniList (źródło: ani.zip); brak danych to `—`, bez błędu.
- F-7. Odcinki w widoku są posortowane po sezonie i numerze (jak dziś `_order`).
- F-8. Szczegóły zestawu (lista plików, `D`), otwarcie pliku, folder (`F`) działają jak dziś, z poziomu widoku odcinków.
- F-9. Enter na odcinku odtwarza wynik zestawu, jak dziś Enter na wierszu listy. Enter na tytule otwiera tytuł.

### Zaznaczanie i usuwanie

- F-10. W widoku odcinków Space zaznacza i odznacza odcinek, `A` zaznacza i odznacza wszystkie.
- F-11. Del usuwa zaznaczone odcinki; bez zaznaczenia usuwa odcinek pod kursorem, jak dziś.
- F-12. Del na liście tytułów usuwa wszystkie zestawy tytułu (zakres: wszystkie zestawy tego wiersza).
- F-13. Usuwanie wielu zestawów nie otwiera wielu równoległych sesji; każdy zestaw przechodzi przez ten sam
  `preview_deletion` → `delete_set`, a odmowa jednego nie cofa pozostałych i wraca do widoku z komunikatem.
- F-14. Usunięte zestawy trafiają do Kosza Windows (bez zmian po stronie platformy).
- F-15. Ctrl+Z cofa usunięcie zgodnie z decyzją O-6.
- F-16. Przewijanie przy wielu tytułach rozwiązuje wyszukiwarka tytułów wywoływana `/` (decyzja O-8) oraz istniejące klawisze
  `PageUp/PageDown/Home/End`.

### Okładki (a)

- F-17. Gdy terminal ma SIXEL i jest miejsce, wybrany wiersz (tytuł, a w widoku odcinków tytuł otwarty) ma okładkę w stałym
  slocie po prawej stronie listy.
- F-18. Gdy terminal nie ma SIXEL, brakuje miejsca albo okładki nie ma w cache, ekran wygląda dokładnie jak bez funkcji
  okładek (bez placeholdera, bez komunikatu błędu).
- F-19. Okładka jest pobierana przez ownera w tle dla tytułów z kluczem AniList (obserwowane, pobrane przez AniShift,
  rozpoznane), zapisywana w cache na dysku i nigdy nie jest pobierana z wątku renderu.
- F-20. Zmiana wybranego wiersza zmienia okładkę w tym samym miejscu bez czyszczenia całego ekranu.
- F-21. Tytuł bez klucza AniList (`z nazwy`, `nierozpoznany`) nie ma okładki, slot pozostaje pusty lub wyłączony zgodnie z F-18.

## Wymagania jakościowe

- Q-1. Responsywność: przesunięcie kursora po liście 30 tytułów nie blokuje klawiatury; kodowanie obrazu nie dzieje się w
  `render`/`after_render` bez wcześniejszego przygotowania w tle. Ocena: test jednostkowy (brak I/O w ścieżce renderu) i
  checkpoint człowieka.
- Q-2. Sieć: pobranie okładek nie przekracza limitów AniList; brak 429 w zwykłej pracy. Ocena: pomiar w fazie 0 i przegląd logu
  (liczniki, bez treści).
- Q-3. Prywatność i logi: w logach i w cache stanu tylko identyfikatory i liczniki, bez ścieżek absolutnych i bez URL-i
  podpisanych (`anishift/AGENTS.md`, „Dane runtime”).
- Q-4. Wygląd: ocena człowieka na własnej Bibliotece (H6 z masterplanu). Nie ma metryki liczbowej.

## Inwarianty

- I-1. Owner jest jedynym źródłem prawdy o zestawach, tożsamości plików i usuwaniu (`LibraryFileIdentity`,
  `preview_deletion`). Widok tytułów jest projekcją i niczego nie usuwa sam.
- I-2. Widok nie zmienia układu `workspace/ready/`.
- I-3. Etykiety zestawów z `library_label` pozostają zachowane dla zestawów bez klucza (kontrakt `test_library_columns.py`).
- I-4. Odmowy ownera nie są gubione przy odświeżeniu snapshotu (kontrakt `test_library_refusal_survives_snapshot_but_not_target_navigation`).
- I-5. Panel nie importuje Loguru, nie robi sieci w renderze (`cli/AGENTS.md`).

## Zakazane

- Zmiana palety, nagłówka, stopki, separatorów, maskotki (poza uogólnieniem slotu obrazu bez zmiany jej wyglądu).
- Foldery serii w `workspace/ready/`.
- Ciche przypisanie pliku ręcznego do tytułu AniList.
- Pobieranie okładek z renderu, z wątku klawiszy albo bez wspólnej bramki sieci ownera.
- Nowa zależność, jeśli Pillow, Rich, httpx i stdlib wystarczą.
- Zmiany Linuksa.

## Zakres

- Model tytułu i projekcja zestawów w tytuły (owner + czysta funkcja panelu).
- Widok tytułów i odcinków Biblioteki, zaznaczanie, usuwanie wielu, wyszukiwarka tytułów, zgodność z Koszem i Ctrl+Z.
- Okładki: dodanie `coverImage` do zapytań katalogu, pobieranie i cache w ownerze, slot SIXEL w rendererze.

## Poza zakresem

- Zmiana innych zakładek (Anime, Subskrypcje, Przetwarzanie), poza wspólnym slotem okładki w Subskrypcjach (O-3).
- Odcinki, które dopiero się pobiorą, w widoku tytułu Biblioteki (należą do Subskrypcji).
- Synchronizacja z MAL/AniList, odtwarzacz, tytuły odcinków z TVmaze (issue #58).
- Miniatura w każdym wierszu listy (zmieniałaby wygląd).
- Okładki dla ekranów Anime (wyszukiwanie), Przetwarzania i Historii.

## Odłożone

- Półbloki ANSI jako druga ścieżka okładek: wymaga osobnej decyzji, bo dubluje mechanizm i obniża jakość.
- Trwały cache rozpoznań plików ręcznych (rozstrzyga faza 3 po pomiarze).
- Eksport lub archiwizacja okładek.

## Warunki sukcesu

| Warunek | Instrument |
|---|---|
| Lista tytułów i widok odcinków renderują się w szerokościach 50, 80, 120 i w progach wysokości | testy jednostkowe na `render_anime` (wzorzec `test_library_columns.py`) |
| Pliki z kluczem AniList grupują się po tytule; plik ręczny bez pewności ma `z nazwy`, nigdy `klucz` | testy jednostkowe projekcji |
| Del wielu zestawów, odmowa jednego, Ctrl+Z zgodnie z O-6 | testy jednostkowe stylu `test_library_actions.py` |
| Okładka znika bez śladu, gdy brak SIXEL lub miejsca | testy jednostkowe układu i renderera z atrapą wyjścia |
| Zapytanie katalogu z `coverImage` parsuje się, brak pola nie psuje parsowania | test kontraktowy na zapisanej odpowiedzi |
| Wygląd i płynność na prawdziwej Bibliotece | checkpoint człowieka H1/H2 w planie; właściciel ocenia |
| Bramki repo | `ruff check`, `ruff format --check`, `mypy`, `pytest` zgodnie z `AGENTS.md` |

## Nierozstrzygnięte (decyzje właściciela)

Każda pozycja ma rekomendację. Brak odpowiedzi blokuje tylko wskazaną fazę planu.

| ID | Pytanie | Rekomendacja | Blokuje |
|---|---|---|---|
| O-1 | Jeden wspólny widok tytułów dla Anime, Subskrypcji, Przetwarzania i Biblioteki, czy obecny podział zakładek? | **Obecny podział.** Tylko Biblioteka staje się widokiem tytułów; ekran odcinków reużywa układu `Nr, Tytuł, Emisja, Stan`. Powody: Biblioteka ma inny zakres (pliki na dysku, także ręczne) niż Subskrypcje (cel pobierania) i Anime (katalog); scalanie zmieniłoby przepływ czterech zakładek i klawiszy chronionych `test_panel_keys.py`, a wspólny klucz `anilist_id` pozwala połączyć je później bez przebudowy. | faza 1 |
| O-2 | Czy slot okładki po prawej stronie listy mieści się w regule „wygląd panelu zostaje”? | **Tak, jako element dodany bez zmiany stylu**, widoczny tylko gdy jest miejsce i SIXEL; inaczej ekran jak dziś. Jeśli nie, okładki wypadają z planu. | etap okładek |
| O-3 | Gdzie pokazać okładkę? | **Lista tytułów Biblioteki i lista Subskrypcji** (oba ok. 30 tytułów, oba z `anilist_id`). Anime (wyszukiwanie) później. | etap okładek |
| O-4 | Wiersz listy to seria (bez sezonu) czy wpis AniList (sezon)? | **Seria** (`series_title` już zdejmuje sezon, część i rok); w widoku odcinków `Nr` niesie sezon jako `SxxEyy`. Zgodne z `LibraryLabel`. | faza 1 |
| O-5 | Rozpoznawanie plików ręcznych przez AniList: teraz czy później? Kryterium pewności? | **Faza 3, warunkowa po pomiarze.** Wersja 1 grupuje po znormalizowanej nazwie z oznaczeniem `z nazwy`. Pewność: dokładnie jeden kandydat z `search`, którego `aliases()` (casefold) zawiera tytuł z nazwy, i zgodny sezon; inaczej `z nazwy`. Wynik w pamięci ownera (jak `_series_titles`), nie w `WatchState`. | faza 3 |
| O-6 | Ctrl+Z po usunięciu wielu zestawów | **Wielopoziomowe cofanie:** owner pomija już przywrócone wpisy w `_latest_deletion`, więc kolejne Ctrl+Z cofają kolejne usunięcia; komunikat „Usunięto N · Ctrl+Z cofa po jednym”. Alternatywa: paczka z `batch_id` w `PendingDeletion` (zmiana schematu trwałego stanu, droższa). Opcja zerowa: zostawić jednopoziomowe (cofa tylko ostatni zestaw) i pokazać to w komunikacie. | faza 2 |
| O-7 | Potwierdzenie przy usuwaniu | **Pytanie Enter/Esc tylko, gdy usuwa się więcej niż jeden zestaw** (wzorzec `_question` z Przetwarzania); pojedynczy odcinek bez pytania, jak dziś. | faza 2 |
| O-8 | Przewijanie przy wielu tytułach | **Wyszukiwarka `/` filtrująca listę** (wzorzec pola Historii: `_history_input`, `TextInput`) plus istniejące klawisze stron. | faza 1 |
| O-9 | Nazwa dla tytułu bez rozpoznania | **„Nie rozpoznano”** jako jeden wiersz na końcu listy. | faza 1 |
| O-10 | Zapytać AniList o zgodę na cache okładek | **Tak, e-mailem lub Discordem, niski priorytet**; wersja 1 cache’uje tylko tytuły z biblioteki i subskrypcji. | brak (ryzyko akceptowane) |
| O-11 | Klawisz Enter na liście dziś odtwarza odcinek; po zmianie otwiera tytuł | **Zmiana akceptowana** (wynika z F-9); odtwarzanie przenosi się do widoku odcinków. Właściciel potwierdza. | faza 1 |
