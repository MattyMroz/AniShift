---
kind: specification
status: draft
baseline: 4365a51 (main)
created: 2026-10-25
issue: "#58 feat(services): fill missing episode titles from TVmaze"
---

# Specyfikacja: brakujące tytuły odcinków z TVmaze

Dowody i próbki odpowiedzi: `research.md`. Plik wykonawczy: `plan.md`.

## Cel

Panel pokazuje prawdziwy tytuł odcinka tam, gdzie ani.zip go nie ma, a TVmaze go zna. Brak dopasowania, błąd sieci albo placeholder TVmaze zostawiają dzisiejsze "Odcinek N" bez błędu.

## Rezultat użytkownika

- Lista odcinków w zakładce Anime i szkic subskrypcji pokazują np. `Greetings, Tsukuyomi Magic Academy` zamiast `Odcinek 5` (Magical Explorer E5 dziś, Student Council E1-E4 dziś).
- Nic się nie zmienia dla odcinków, które mają tytuł z ani.zip.
- Otwarcie listy kosztuje najwyżej dwa dodatkowe żądania na serial na godzinę, tylko gdy jakiś wyemitowany odcinek nie ma tytułu.

## Wymagania

1. Uzupełniamy wyłącznie `ListedEpisode.title == None`. Tytuły ani.zip mają pierwszeństwo, AniList nie dostarcza tytułów odcinków.
2. Serial TVmaze wyznacza jedyne niepuste `tvdbShowId` z `mapping.raw_episodes` przez `GET /lookup/shows?thetvdb=<id>` (301 -> serial). Zero lub kilka różnych `tvdbShowId` = brak uzupełnienia.
3. Odcinek łączymy po parze `(season, episode)` z ani.zip (`ListedEpisode.season/episode`) z `(season, number)` TVmaze, tylko `type == "regular"`. Nie łączymy po dacie, numerze lokalnym ani absolutnym.
4. Odcinek bez pary, z dublem pary lub z sezonem innym niż `tvdb_season` wpisu (`numbering_gap(...) is not None`) zostaje bez tytułu. To ta sama reguła niepewności, której używa H1.
5. Filmy (`movie`) nie są uzupełniane.
6. Placeholder `Episode N` (cały napis, bez rozróżniania wielkości liter) i pusty napis nie są tytułem. Tytuł jest oczyszczony ze znaków sterujących i zwiniętych białych znaków.
7. Tytuły TVmaze żyją wyłącznie w `EpisodeListing` zwracanym przez `episodes()` i w pamięci rezydenta. Nie trafiają do `raw_episodes`, do zapisanej mapowania subskrypcji (`state.json`) ani do H1.
8. Żądania TVmaze idą tylko ze ścieżki `episodes()` (UI). Cykliczne kontrole automatu (`read_listing`) ich nie wywołują.
9. Cache w pamięci rezydenta: wynik (także pusty po 404) 3600 s, czyli tyle, ile TVmaze cache'uje odpowiedzi; błąd 900 s, żeby awaria TVmaze nie wydłużała każdego otwarcia listy.
10. Błąd TVmaze (transport, status inny niż 200/404, zła treść) kończy się `TitleCatalogError(EPISODE_CATALOG_FAILED)` w adapterze, a wywołujący łapie go, loguje (`provider="tvmaze"`, bez treści odpowiedzi) i zostawia listę bez zmian.
11. Dostawca `tvmaze` ma własny wpis w `_PROVIDERS` (statystyki i wspólny cooldown po 429). Limit TVmaze (20 wywołań na 10 s na IP) jest daleko poza naszym użyciem; dodatkowego throttlingu nie dodajemy.
12. Opcjonalne źródło: bez wstrzykniętego katalogu tytułów zachowanie jest dzisiejsze.

## Nie-cele

- Zapas na wypadek awarii AniList i jakiekolwiek inne źródła niż tytuły odcinków (równoległy workstream katalogu).
- Wyszukiwanie serialu po tytule i dacie premiery (patrz D2).
- Nadpisywanie romaji `x-jat` angielskim tytułem TVmaze (patrz D3).
- Zapis tytułów TVmaze na dysk, odświeżanie w tle, tytuły dla specjali (`S1`...), opisy i obrazy odcinków.
- Wersja zakładki Subskrypcje z tytułami odcinków (dziś ich nie pokazuje).

## Zgodność z kierunkiem "TVmaze jako jedno ze źródeł"

Adapter `TvMazeCatalog` leży w `services/catalog/` obok `anizip`, `arm`, `kitsu`, ma wąski interfejs `episode_titles(tvdb_show_id)` i wstrzykiwany protokół `EpisodeTitleCatalog` w warstwie aplikacji. Workstream zapasu katalogu może go potraktować jako źródło tytułów odcinków bez zmian; ten workstream nie dotyka wyboru źródeł serii ani logiki zapasu. Punkt styku: ewentualny wspólny interfejs źródeł zastąpi `EpisodeTitleCatalog`, nic więcej.

## Decyzje otwarte (do właściciela)

| ID | Pytanie | Rekomendacja | Skutek alternatywy |
| --- | --- | --- | --- |
| D1 | Zakres: czy wystarcza dziś skromny zysk (6 z 93 braków, głównie okno opóźnienia ani.zip)? | Tak, wykonać; koszt to jeden adapter, jedna czysta funkcja i cache | Odłożyć issue do czasu, gdy opóźnienia ani.zip boleśniej się pokażą |
| D2 | Fallback "po tytule i dacie premiery", jak sugeruje issue | Nie robić: w 20 na 20 subskrypcji jest `tvdbShowId`, wyszukiwanie po tytule jest ryzykiem złego serialu | Dodać później osobno, gdy trafi się wpis bez `tvdbShowId` |
| D3 | Czy TVmaze (angielski) ma zastępować romaji `x-jat` z ani.zip, np. `[Kyouteki]` -> `Powerful Foe`? | Nie: wymaganie 1 (issue: ani.zip ma pierwszeństwo) i `ListedEpisode` nie zna języka tytułu | Wymaga rozdzielenia `en` i `x-jat` w `ListedEpisode` i parserze (większa zmiana kontraktu) |
| D4 | Czy odcinki niewyemitowane mają wywoływać zapytanie? | Nie: w próbie żaden nie miał prawdziwego tytułu; zapytanie tylko gdy brakuje tytułu wyemitowanego odcinka | Zapytanie zawsze: więcej żądań, ten sam efekt |
| D5 | Atrybucja CC BY-SA: link do TVmaze | Jedna linia "Data sources" w `README.md` (EN i PL) z linkiem do https://www.tvmaze.com; w panelu nic | Link w panelu (zmiana UI, której nikt nie zamawiał) |
| D6 | Nagrane odpowiedzi w publicznym repo (ShareAlike) | Minimalne wycinki (kilka odcinków jednego serialu) z adnotacją źródła w manifeście, albo odpowiedzi syntetyczne | Pełne nagrania: więcej treści CC BY-SA w repo |
| D7 | Kod błędu | Użyć istniejącego `EPISODE_CATALOG_FAILED` | Nowy `ErrorCode` bez realnej różnicy zachowania |

Rekomendacja ogólna: wykonać z D1-D7 jak wyżej. D3 i D5 wymagają świadomej decyzji właściciela, bo zmieniają widoczny efekt (D3) lub treść README (D5).

## Kryteria sukcesu

- Magical Explorer E5 i Student Council E1-E4 pokazują tytuły TVmaze przy realnym stanie z 2026-10-25; reszta braków zostaje `Odcinek N`.
- Overgeared E1 pokazuje `Legendary Class` (dziś z ani.zip, test na nagranej odpowiedzi TVmaze dowodzi ścieżki, gdy ani.zip tytułu nie ma).
- Wyłączony lub padający TVmaze: lista identyczna jak dziś, bez błędu w panelu.
- Brak zmian w `raw_episodes`, `state.json` i H1 (test kontraktu).
- Wszystkie bramki repo zielone.
