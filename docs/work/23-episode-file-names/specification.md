---
kind: specification
status: draft
updated: 2026-11-26
---

# Specyfikacja: wspólne nazwy gotowych odcinków

Dowody i liczby: `research.md`. Wykonanie: `plan.md`.

## Cel

Każdy pobrany odcinek ma w `workspace/ready/` jedną, spójną nazwę niezależną od grupy wydającej, np. `The World's Strongest Witch - S01E08 - I Tried Teleporting!.mkv` zamiast `[SubsPlease] Sekai Saikyou no Majo, Hajimemashita - 08 (1080p) [7C51D32E].mkv`.

## Stan wyjściowy

- Rdzeń nazwy zestawu to stem pliku wideo z torrenta, wybierany raz przy rezerwacji nazw publikacji (`automation.py:7008`, `transfers.py:472`). Produkty, Auto, relokacja do `ready/` i regeneracja dziedziczą ten rdzeń.
- Tożsamość zestawu w Bibliotece (`ReadyGroup.set_id`) i wiązanie z odcinkiem (`EpisodeAssignment.group_id`) nie zależą od nazwy w `ready/`.
- W `ready/` właściciela leży 68 zestawów z kluczem odcinka (255 plików) i 7 zestawów bez klucza (27 plików).

## Ustalenia (decyzje właściciela, 2026-11-25)

- Rdzeń nazwy zestawu z kluczem odcinka: `<tytuł serii> - S<sezon>E<odcinek> - <tytuł odcinka>`. Wszystkie pliki zestawu (źródło, napisy towarzyszące, produkty) mają ten rdzeń i swoje dotychczasowe sufiksy (`.mkv`, `.pl.ass`, `.displayed.pl.ass`, `.eac3` …).
- Tytuł serii to angielski tytuł z AniList.
- Tytuł odcinka jest po angielsku. Kolejność źródeł: angielski z ani.zip/AniList, potem TVmaze, potem romaji, potem brak. Kolejność i dostawę tytułu realizuje workstream 19.
- Bez tytułu odcinka rdzeń kończy się na `SxxEyy`, bez ` - `.
- Grupa wydająca nie występuje w nazwie.
- Istniejące pliki w `ready/` zmienia jednorazowy skrypt w `scripts/tmp/`: uruchomiony raz przy zamkniętym rezydencie, sprawdzony i usunięty, z zapisem listy starych i nowych nazw do cofnięcia. Kod produktu nie migruje starych nazw.
- Zero legacy: stara reguła nazwy zestawu z kluczem odcinka znika w tym samym diffie. Bez aliasów, podwójnych ścieżek i zgodności wstecznej.

## Wymagania

### Reguła nazwy

1. Jedna czysta funkcja wylicza rdzeń z czterech faktów: tytuł serii, sezon, odcinek, tytuł odcinka (opcjonalny). Nikt poza nią nie składa tej nazwy.
2. Tytuł serii to `series_title(english or romaji)` wpisu AniList (`library.py:136`): bez znacznika sezonu, części i roku, czyli ta sama reguła co nazwa serii w Bibliotece.
3. Sezon i odcinek to numeracja TVDB z ani.zip dla numeru lokalnego (`ListedEpisode.season`, `.episode`), w dwóch cyfrach minimum (`S02E07`, `S01E100`).
4. Tytuł odcinka to `ListedEpisode.title` zwrócony przez `AcquisitionService.episodes(anilist_id)`; regułę kolejności źródeł posiada workstream 19.
5. Każda część przechodzi jedną regułę nazwy bezpiecznej w Windows, wspólną z nazwą katalogu serii (`series_directory_name`, `acquisition.py:589`); nie powstaje druga lista zakazanych znaków.
6. Rdzeń mieści się w limicie długości; przy przekroczeniu skraca się najpierw tytuł odcinka, na granicy słowa.
7. Rdzeń z sufiksem wideo klasyfikuje się jako źródło główne o stemie równym rdzeniowi (`classify_artifact`). Gdy tytuł odcinka to psuje, rdzeń powstaje bez tytułu odcinka.

### Moment nadania nazwy

8. Nazwę dostaje zestaw przy rezerwacji nazw publikacji ze stagingu, przed kopią do korzenia workspace. Fakty czyta wątek puli transferów przed rezerwacją; owner tylko zapisuje wynik.
9. Raz zarezerwowana nazwa jest trwała: restart, ponowienie relokacji i późniejszy tytuł odcinka z ani.zip lub TVmaze jej nie zmieniają.
10. Kolizja z nazwą zajętą lub zarezerwowaną dostaje istniejący ordinal ` [2]`, ` [3]` (`_free_core`), dla całego zestawu naraz.

### Zakres plików

11. Nową nazwę dostaje każdy zestaw pobrany jako odcinek katalogu (przypisanie z `EpisodeChoice`): z subskrypcji i z ręcznego zamówienia w zakładce Anime.
12. Pliki wrzucone ręcznie i pobrania całego wydania bez klucza odcinka zachowują nazwę źródła.

### Migracja istniejących plików

13. Skrypt zmienia nazwy wyłącznie zestawów z `ready_groups`, które mają pliki na dysku i klucz odcinka (`downloaded_episodes`), tą samą funkcją nazwy co produkt i z tymi samymi faktami z katalogu.
14. Skrypt przepisuje każde miejsce stanu, które zależy od nazwy w `ready/`: `ReadyGroup` (z zachowanym `set_id`, `source_directory`, `source_stem`, `target`, `recipe`), potwierdzenia produktów, markery, zlecenia, `notified` i dzienniki zakończonych runów. Używa `ReadyMove.apply`, `RunJournal.relocate` i `ReadyStore.execute`, nie własnej kopii tej logiki.
15. Skrypt odmawia, gdy rezydent działa, gdy są relokacje lub zlecenia w toku, gdy plik zestawu nie zgadza się z rekordem albo gdy docelowa nazwa jest zajęta.
16. Przed pierwszą zmianą skrypt zapisuje kopię `state.json` i listę starych i nowych nazw z tożsamością plików; ta sama lista pozwala cofnąć migrację.
17. Skrypt domyślnie tylko pokazuje plan zmian; zmienia pliki dopiero z jawną flagą.

## Inwarianty

- `ReadyGroup.set_id`, `EpisodeAssignment.group_id` i `PendingDeletion` nie zmieniają się przez migrację.
- Treść plików się nie zmienia; zmiana nazwy to dowiązanie i usunięcie starej nazwy na tym samym woluminie.
- Po migracji Biblioteka pokazuje te same zestawy (te same `set_id`), Enter odtwarza, F pokazuje folder, Del i Ctrl+Z działają na nowych nazwach.
- `decisions.jsonl` nadal nie zawiera nazw.

## Zakazane

- Druga kopia reguły tytułu odcinka, tytułu serii albo numeracji poza funkcjami wskazanymi w wymaganiach 1-4.
- Kod produktu, który rozpoznaje albo przemianowuje stare nazwy.
- Zmiana nazwy po publikacji (rezydent nie przemianowuje gotowych zestawów).
- Migracja przy działającym rezydencie; zmiana `history.jsonl`, `decisions.jsonl` i `pending_deletions`.

## Poza zakresem

- Dostawa tytułów odcinków z TVmaze i rozdzielenie `en` / `x-jat` (workstream 19).
- Widok Biblioteki jako lista tytułów i okładki (workstream 18).
- Nazwy plików bez klucza odcinka; rozpoznawanie ich serii.
- Podkatalog `ready/Nowy folder/` i pliki bez rekordu w `ready/`.

## Warunki sukcesu

- Test: zestaw pobrany jako odcinek publikuje się pod rdzeniem z reguły, z sidecarami i ordinalem przy kolizji.
- Test: funkcja nazwy dla przypadków z sekcji „Nierozstrzygnięte” (znaki, długość, brak tytułu, film, S00).
- Próba właściciela: nowy odcinek z subskrypcji trafia do `ready/` pod nową nazwą z kompletem produktów.
- Migracja: tryb podglądu pokazuje 68 zestawów i 255 plików (stan z 2026-11-26), po wykonaniu Biblioteka ma te same zestawy pod nowymi nazwami, a kontrola skryptu nie znajduje w stanie żadnej starej nazwy tych zestawów.
- Bramki repo zielone.

## Nierozstrzygnięte (rekomendacje do decyzji właściciela)

| ID | Pytanie | Rekomendacja | Skutek alternatywy |
| --- | --- | --- | --- |
| O-1 | Kiedy nadać nazwę | Przy publikacji ze stagingu (wymaganie 8): jedno miejsce, produkty i Auto dziedziczą rdzeń, w korzeniu workspace też widać nową nazwę | Przy przeniesieniu do `ready/`: przemianowanie gotowych produktów i odczyt sieci na ścieżce relokacji ownera |
| O-2 | Brak angielskiego tytułu serii | Romaji z AniList, tak jak Biblioteka i subskrypcje (`english or romaji`) | Tytuł natywny: znaki CJK w nazwie pliku, inna reguła niż reszta aplikacji |
| O-3 | Znaki niedozwolone w Windows | `": "` → `" - "`, pozostałe `:` `/` `\` `\|` → `-`, `"` → `'`, `` ` `` → `'`, usuń `< > ? *` i znaki sterujące, zwiń spacje, obetnij kropki i spacje na końcu, nazwa urządzenia dostaje `_`; zmiana obejmuje też `series_directory_name` | Samo usuwanie znaków (dzisiejsze): `Re:Zero` → `ReZero` |
| O-4 | Limit długości rdzenia | 150 znaków: skróć tytuł odcinka na granicy słowa; gdy sama seria z `SxxEyy` przekracza limit, skróć serię. Z `ready/` właściciela (60) i najdłuższym sufiksem (17) i ordinalem (4) ścieżka zostaje poniżej 260 | Bez limitu: dziś najdłuższy rdzeń ma 153 znaki, Windows odrzuca ścieżki od 260 |
| O-5 | Film, odcinki specjalne, brak numeracji TVDB | Film: sam tytuł serii, bez `SxxEyy`. Sezon 0 z ani.zip: `S00Eyy`. Brak pary sezon-odcinek w ani.zip: sezon z `season_hint` tytułu albo 1, odcinek = numer lokalny | `S01E01` dla filmu; dla braku numeracji czekanie na ani.zip |
| O-6 | Kolizje: ponowne pobranie usuniętego odcinka | Rekordy `ready_groups` bez plików na dysku, poza `pending_deletions` i `pending_sources`, przestają rezerwować nazwy, więc ponowne pobranie dostaje czystą nazwę; dwa wydania obecne naraz (BD i WEB, v2) dostają ` [2]` | Dzisiejsza rezerwacja: ponowne pobranie usuniętego odcinka zawsze z ` [2]` (9 z 224 kluczy było pobranych więcej niż raz) |
| O-7 | Ta sama numeracja w Bibliotece | Tak: `name_series` używa tej samej funkcji sezonu i odcinka (TVDB z zapisanego mapowania subskrypcji), żeby nazwa pliku i kolumna Odcinek się nie rozjechały | Biblioteka zostaje przy numerze lokalnym: dla split-cour plik `S01E13`, kolumna `S01E01` |
| O-8 | Zestawy bez klucza odcinka | Zostają z nazwą źródła (7 zestawów, 27 plików); właściciel może podać skryptowi mapowanie `set_id` → AniList i numer, jeśli chce je przemianować | Zgadywanie serii z nazwy pliku: ryzyko złej serii |
| O-9 | Katalog niedostępny przy publikacji | Tytuł serii z pamięci serwisu, potem z zapisanej subskrypcji; numeracja z celu H1 przypisania; tytuł odcinka pominięty. Gdy nie ma nawet tytułu serii (zamówienie ręczne, AniList niedostępny po restarcie), publikacja czeka do następnej rundy transferów z ostrzeżeniem w logu, nigdy nie wraca do nazwy wydania | Nazwa wydania jako zapas: druga reguła nazwy, sprzeczna z zero legacy |
| O-10 | Tytuł odcinka znany dopiero po publikacji | Nazwa zostaje (wymaganie 9) | Późniejsze przemianowanie: nowa operacja na stanie przy każdym tytule |
| O-11 | Historia ze starymi nazwami | `history.jsonl` zostaje bez zmian: jest nieautorytatywna, 30 dni, Enter działa po `set_id` | Przepisanie Historii: zmiana logu, który z założenia nie jest źródłem prawdy |
| O-12 | Gdzie lista cofnięcia | `config/watch/episode-names.json` obok kopii `state.json.episode-names.bak`; właściciel usuwa oba po odbiorze | Lista w repo: nazwy plików właściciela w publicznym repozytorium |
