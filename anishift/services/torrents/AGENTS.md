# torrents

Granica wydań torrent: wyszukanie w indeksie nyaa, rozpoznanie nazwy wydania i klient qBittorrent.
Domena bez rejestru silników — zwykłe moduły. Nie filtruje, nie grupuje i nie wybiera folderu;
te decyzje należą do warstwy aplikacyjnej.

## Pliki

- `types.py` — `Release`, `ReleaseName`, `TorrentInfo` (frozen, slots)
- `errors.py` — `TorrentError`, `TorrentSourceError` (transient), `TorrentClientError`
- `names.py` — `parse_release_name`: czysty regex, zero sieci
- `nyaa.py` — `parse_feed` (RSS) i `search_releases` (jedno żądanie GET)
- `qbittorrent.py` — `QBittorrentClient`: wersja, preferencje, dodanie torrenta, lista

## Inwarianty

- `httpx.Client` jest wstrzykiwany przez wywołującego; moduły go nie tworzą i nie zamykają.
- Nyaa: kategoria `1_2`, ciało ponad `MAX_BODY_BYTES` (4 MiB), status ≠ 200, content-type inny niż XML
  oraz błędny XML kończą się `TorrentSourceError`; wpis bez `nyaa:infoHash` lub `link` jest pomijany.
- `Release.published` jest zawsze aware UTC — nyaa stempluje `-0000`, które `email.utils` zwraca jako naive.
- qBittorrent: 403 wywołuje jednorazowy `auth/login` i jedno ponowienie; drugi 403 lub `Fails.`
  to `TORRENT_CLIENT_UNAUTHORIZED`, brak połączenia to `TORRENT_CLIENT_UNAVAILABLE`.
- Hasło klienta nie trafia do logów ani do `ErrorContext.details`.

## Testy

```bash
uv run pytest tests/services/torrents -v
```
