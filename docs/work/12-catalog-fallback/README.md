# 12-catalog-fallback

AniShift działa dalej, gdy AniList nie odpowiada: subskrypcje, lista odcinków, znane wpisy i nazwy serii korzystają
z zapisanej ostatniej odpowiedzi AniList, a panel mówi, z kiedy są dane.

**Status:** research, specyfikacja i plan gotowe, dwie rundy samokontroli wykonane; kod niezaczęty. Czeka na decyzje
właściciela D1–D6 (`specification.md`, „Nierozstrzygnięte”) i niezależne review planu przez inny model.
Data: 2026-10-25, baseline `main` @ `4365a51`.

Wniosek w jednym zdaniu: żaden darmowy serwis bez klucza nie zastępuje AniList (Jikan wyłączono 2026-10-01), więc
najprostsza skuteczna droga to lokalna kopia ostatnich odpowiedzi AniList używana tylko w czasie awarii.

## Kolejność czytania

| Plik | Zawartość |
|---|---|
| [dependency-map.md](dependency-map.md) | każde użycie AniList w kodzie, `anilist_id` w stanie, zachowanie przy awarii, dowód z logu 2026-10-21 |
| [research.md](research.md) | AniList, Jikan, MAL, Kitsu, ani.zip, arm, TVmaze, Shikimori, AnimeSchedule, AniDB, ANN, mapowania ID; tabela i źródła |
| [specification.md](specification.md) | wymagania W1–W13, zakazy, zakres, warunki sukcesu, decyzje D1–D6 z rekomendacją |
| [plan.md](plan.md) | design, pliki, kontrakty, fazy, testy, komendy dowodu, branch i commity |
| [reviews/round-1.md](reviews/round-1.md) | FAIL: kolejność węzłów grafu, przegląd migracji na kopii — naniesione |
| [reviews/round-2.md](reviews/round-2.md) | PASS WITH FINDINGS: drobne poprawki naniesione |

## Powiązane workstreamy

- [18-library-titles-covers](../18-library-titles-covers/README.md) i
  [19-tvmaze-episode-titles](../19-tvmaze-episode-titles/README.md) zmieniają te same pliki (`acquisition.py`,
  `anilist.py`, `bootstrap.py`); kolejność scalania do ustalenia.
- [08-acquisition/research](../08-acquisition/research/anime-api-report.md): wcześniejsze badanie API z 2026-09-22.
