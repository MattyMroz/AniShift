# torrents

Granica wydań torrent: wyszukanie w indeksie nyaa, rozpoznanie nazwy wydania i klient qBittorrent.
Domena bez rejestru silników — zwykłe moduły. Nie filtruje, nie grupuje i nie wybiera folderu;
te decyzje należą do warstwy aplikacyjnej.

## Pliki

- `types.py` — `Release`, `ReleaseName`, `TorrentInfo` (frozen, slots)
- `errors.py` — `TorrentError`, `TorrentSourceError` (transient), `TorrentClientError`
- `names.py` — `parse_release_name`: czysty regex, zero sieci
- `nyaa.py` — `parse_feed` (RSS) i `search_releases` (po jednym GET na kategorię)
- `qbittorrent.py` — `QBittorrentClient`: wersja, preferencje, dodanie torrenta, lista

## Inwarianty

- `httpx.Client` jest wstrzykiwany przez wywołującego; moduły go nie tworzą i nie zamykają.
- Nyaa: kategorie `1_2` i `1_3`; ciało ponad `MAX_BODY_BYTES` (4 MiB), status ≠ 200, content-type inny
  niż XML oraz błędny XML kończą się `TorrentSourceError` — awaria dowolnej kategorii przerywa całe
  wyszukiwanie, nie ma wyniku częściowego; wpis bez `nyaa:infoHash` lub `link` jest pomijany.
- `search_releases` scala kategorie po `info_hash` casefold, pierwszy wpis wygrywa, więc wydania
  angielskie stoją przed resztą. `Release.subtitle_language` bierze język z nazwy, a gdy nazwa milczy —
  `en` dla `1_2` i `None` dla `1_3`.
- `parse_release_name` czyta grupę z `[Grupa]` albo z sufiksu `-Grupa` po znaczniku technicznym
  (`H.264-VARYG`), a nazwę bez ani jednej spacji rozkropkowuje. `Sxx` bez `Eyy` jest sezonem tylko wtedy,
  gdy zaraz po nim stoi znacznik techniczny albo koniec nazwy — inaczej `Oshi no Ko S3 (01-11)` straciłby
  `S3` z serii. `ReleaseName.is_pack` = `batch` albo sezon bez odcinka.
- `Release.published` jest zawsze aware UTC — nyaa stempluje `-0000`, które `email.utils` zwraca jako naive.
- qBittorrent: 403 wywołuje jednorazowy `auth/login` i jedno ponowienie; drugi 403 lub `Fails.`
  to `TORRENT_CLIENT_UNAUTHORIZED`, brak połączenia to `TORRENT_CLIENT_UNAVAILABLE`.
- Hasło klienta nie trafia do logów ani do `ErrorContext.details`.

## Testy

```bash
uv run pytest tests/services/torrents -v
```
