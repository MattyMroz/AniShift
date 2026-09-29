# catalog

Granica katalogu tytułów: rozpoznanie anime po ludzkim haśle i numeracja sezonów z AniList.
Domena bez rejestru silników — zwykłe moduły. Nie szuka wydań, nie wybiera folderu i nie tłumaczy
statusu na polski; te decyzje należą do warstwy aplikacyjnej.

## Pliki

- `types.py` — `TitleCandidate` (frozen, slots) z `aliases()` i `folder_title()`, `TitleStatus`
- `errors.py` — `TitleCatalogError` (transient)
- `anilist.py` — `AniListCatalog`: title search, prequels, airing schedules and full franchise graphs
- `anizip.py` — `AniZipCatalog.mapping` and `parse_mapping`: episode metadata with raw identity fields

## Inwarianty

- `httpx.Client` jest wstrzykiwany przez wywołującego; moduł go nie tworzy i nie zamyka.
- Status ≠ 200 (429 też), błąd transportu i ciało bez `data.Page.media` kończą się `TitleCatalogError`
  z kodem `TITLE_CATALOG_FAILED`; węzeł bez `id` lub bez `romaji` jest pomijany.
- Pusty wynik to jedna ponowna próba ze słowami uciętymi do `max(3, int(len * 0.6))` znaków —
  tylko gdy któreś słowo faktycznie się skraca. Nigdy dwie próby.
- `aliases()` zwraca wyłącznie nazwy zapisane alfabetem łacińskim (romaji, angielska, synonimy),
  casefold-unikalne, w kolejności AniList; `native` jest tylko do wyświetlania.
- `episode_offset` jest leniwy (osobne zapytania), liczy tylko formaty `TV`/`TV_SHORT`/`ONA`,
  ignoruje cykle, traktuje nieznane `episodes` jako 0 i zatrzymuje się po `MAX_PREQUEL_HOPS` wpisach.
- `franchise` expands a depth-three graph in at most four requests, retaining nodes outside the
  displayed entries. `FranchiseGraph` and raw `AniZipMapping` stay inside the service; IPC carries
  projections. Identity input is built in `application/episode_selection.py`, without H1 evidence.
- ani.zip 404 means an absent mapping; transport, status and malformed data failures use
  `EPISODE_CATALOG_FAILED`. Preserve raw episode order and fields, including `S…`; these feed H1.
  Do not normalize them to fix identity errors: follow `application/AGENTS.md` regression rules.
- Logs contain counts, operation and timing, never search text or response bodies.

## Testy

```bash
uv run pytest tests/services/catalog -v
```
