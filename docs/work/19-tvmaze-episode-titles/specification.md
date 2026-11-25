---
kind: specification
status: accepted
updated: 2026-11-26
issue: "#58 feat(services): fill missing episode titles from TVmaze"
---

# Specyfikacja: angielskie tytuły odcinków z TVmaze

Dowody i kształt odpowiedzi: `research.md`. Plik wykonawczy: `plan.md`.

## Cel

Panel pokazuje angielski tytuł odcinka, gdy ani.zip ma tylko romaji albo nic, a TVmaze zna angielski tytuł. Ten sam
tytuł jest jedynym źródłem tytułu odcinka dla dalszej pracy (workstream 23: nazwy plików
`<angielski tytuł serii> - SxxEyy - <tytuł odcinka>`).

## Ustalenia właściciela (2026-11-25)

- D1: wykonać.
- D2: serial TVmaze tylko po `tvdbShowId`; bez wyszukiwania po tytule i dacie premiery.
- D3: angielski tytuł TVmaze wygrywa także z romaji (`x-jat`) z ani.zip. Skutek: `ListedEpisode` i parser ani.zip
  rozróżniają język tytułu, a zapisany kształt w `state.json` się zmienia.
- D4: zapytanie do TVmaze wywołuje tylko wyemitowany odcinek bez angielskiego tytułu.
- D5: atrybucja CC BY-SA to jedna linia źródeł danych z linkiem do https://www.tvmaze.com w `README.md` i
  `README.pl.md`; panel bez zmian.
- D6: w repo tylko przycięte nagranie odpowiedzi TVmaze z adnotacją źródła i licencji w manifeście.
- D7: błąd TVmaze używa istniejącego `ErrorCode.EPISODE_CATALOG_FAILED`.

## Wymagania funkcjonalne

1. Kolejność tytułu odcinka: angielski z ani.zip, potem angielski z TVmaze, potem romaji z ani.zip, potem brak
   (UI pokazuje „Odcinek N” albo „Film”).
2. Angielski tytuł z ani.zip nigdy nie jest zastępowany. AniList nie dostarcza tytułów odcinków.
3. Serial TVmaze wyznacza jedyne niepuste `tvdbShowId` w `raw_episodes` mapowania, z którego zbudowano listę
   (`ListingRead.mapping`, także po zamianie na mapowanie AniDB). Zero albo kilka różnych `tvdbShowId` oznacza brak
   tytułów z TVmaze.
4. Odcinek łączy się po parze `(season, episode)` z ani.zip z `(season, number)` TVmaze, tylko dla wpisów
   `type == "regular"`. Nie łączy się po dacie, numerze lokalnym ani absolutnym.
5. Odcinek bez pary, z parą niepewną według `numbering_gap` (`none`, `duplicate`, `tvdb_season`) albo z parą
   występującą w TVmaze więcej niż raz nie dostaje tytułu z TVmaze.
6. Film nie dostaje tytułu z TVmaze i nie wywołuje zapytania.
7. Pusty napis i placeholder `Episode N` (cały napis, bez rozróżniania wielkości liter) nie są tytułem. Tytuł TVmaze ma
   usunięte znaki sterujące i zwinięte białe znaki; tytuł antologii `A / B / C` zostaje w całości.
8. Tytuły TVmaze trafiają do odcinków niewyemitowanych także, gdy zapytanie już padło (D4 ogranicza tylko wywołanie).
9. Brak katalogu TVmaze, błąd sieci, 404 lookupu, 429 albo zła treść zostawiają listę z tytułami ani.zip, bez błędu w
   panelu.
10. Odcinki specjalne (`S1`…) zachowują dzisiejszy tytuł: angielski, a gdy go brak, romaji z ani.zip.

## Wymagania jakościowe

- Otwarcie listy kosztuje najwyżej 3 żądania fizyczne do TVmaze na wpis na godzinę (301, serial, odcinki).
- Udany wynik, także pusty po 404, żyje w pamięci rezydenta 3600 s, tyle co cache TVmaze; awaria żyje 900 s.
- Logi TVmaze mają dostawcę `tvmaze`, kod i klasę błędu albo liczbę tytułów; nigdy treści odpowiedzi.

## Inwarianty

- Tytuły TVmaze istnieją tylko w `EpisodeListing` zwracanym przez `AcquisitionService.episodes()` i w pamięci
  rezydenta. Nie trafiają do `AniZipMapping`, `raw_episodes`, `state.json` ani do wejścia H1.
- Cykliczne kontrole subskrypcji (`read_listing`) nie wysyłają żądań do TVmaze.
- Jedyną regułą wyboru tytułu odcinka jest `ListedEpisode.title`; UI i workstream 23 jej nie powtarzają.

## Ograniczenia

- Licencja TVmaze CC BY-SA wymaga podania źródła (D5) i ogranicza treść TVmaze w publicznym repo (D6).
- Limit TVmaze: co najmniej 20 wywołań na 10 s na IP; użycie AniShift jest daleko poniżej, więc bez własnego
  ogranicznika.
- Zmiana zapisanego kształtu odcinka podbija `WATCH_STATE_SCHEMA_VERSION`; dane właściciela przenosi jednorazowy skrypt w
  `scripts/tmp/`, nie kod produktu.

## Zakazane

- Aliasów i warstw zgodności dla starego pola `ListedEpisode.title` jako pola danych, starego klucza `title` w
  zapisanym odcinku i odczytu schematu 6.
- Nowej zależności, nowego `ErrorCode`, zmian H1 (`episode_identity.py`, `_episode_title`, `identity_target`).
- Zmian wyglądu i interakcji panelu.

## Poza zakresem

- Wyszukiwanie serialu po tytule (D2).
- Tytuły TVmaze dla odcinków specjalnych, opisy i obrazy odcinków, zapis tytułów TVmaze na dysk, odświeżanie w tle.
- Rejestr decyzji automatu (`decisions.jsonl`) dla odczytów TVmaze.
- Nazwy plików z tytułem odcinka (workstream 23).

## Warunki sukcesu

- Testy jednostkowe na kształcie z `research.md` dowodzą wymagań 1-10 i inwariantów.
- Test `network` (domyślnie pomijany): lookup TVDB 478752 daje dla `(1, 1)` tytuł `Legendary Class`.
- Właściciel w panelu przy zamkniętym starym rezydencie: Overgeared E8 pokazuje `Yatan's High Priest` zamiast romaji,
  Even the Student Council Has Its Holes! E1-E8 mają tytuły zamiast „Odcinek N”, a odcinki z angielskim tytułem
  ani.zip wyglądają jak dziś.
- Stan właściciela przeniesiony skryptem do schematu 7 i wczytany przez rezydenta bez `ConfigError`.
- Bramki repo zielone.
