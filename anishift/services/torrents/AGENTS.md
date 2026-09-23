# torrents

Granica wydań torrent: wyszukanie w indeksie nyaa, rozpoznanie nazwy wydania i klient qBittorrent.
Domena bez rejestru silników — zwykłe moduły. Nie filtruje, nie grupuje i nie wybiera folderu;
te decyzje należą do warstwy aplikacyjnej.

## Pliki

- `types.py` — `Release`, `ReleaseName`, `TorrentInfo`, `TorrentFile` (frozen, slots)
- `errors.py` — `TorrentError`, `TorrentSourceError` (transient), `TorrentClientError`
- `categories.py` — identyfikatory kategorii nyaa i `SEARCH_CATEGORIES`; czysty moduł, który
  warstwa aplikacyjna może importować w runtime
- `names.py` — `parse_release_name`: czysty regex, zero sieci
- `query.py` — `parse_query` i `EpisodeRange`; `EpisodeRange.text` jest neutralne językowo
- `nyaa.py` — `parse_feed` (RSS) i `search_releases` (po jednym GET na kategorię)
- `qbittorrent.py` — `QBittorrentClient`: wersja, preferencje, dodanie torrenta, lista

## Inwarianty

- `httpx.Client` jest wstrzykiwany przez wywołującego; moduły go nie tworzą i nie zamykają.
- Nyaa: `search_releases` pyta dokładnie te kategorie, które dostanie w `categories` (domyślnie
  `SEARCH_CATEGORIES`, czyli `1_2` i `1_3`) — jedna kategoria to jedno żądanie GET, czyli jednostka
  budżetu liczonego w `application/acquisition.py`. Ciało ponad `MAX_BODY_BYTES` (4 MiB), status ≠ 200,
  content-type inny niż XML oraz błędny XML kończą się `TorrentSourceError` — awaria dowolnej kategorii
  przerywa całe wyszukiwanie, nie ma wyniku częściowego; wpis bez `nyaa:infoHash` lub `link` jest
  pomijany.
- `search_releases` scala kategorie po `info_hash` casefold, pierwszy wpis wygrywa, więc wydania
  angielskie stoją przed resztą. `Release.subtitle_language` bierze język z nazwy, a gdy nazwa milczy —
  `en` dla `1_2` i `None` dla `1_3`.
- `parse_release_name` czyta grupę z `[Grupa]` albo z sufiksu `-Grupa` po znaczniku technicznym
  (`H.264-VARYG`, także w zapisie ze spacją `H 264-VARYG`), a nazwę bez ani jednej spacji rozkropkowuje.
  `Sxx` bez `Eyy` jest sezonem tylko wtedy, gdy zaraz po nim stoi znacznik techniczny albo koniec nazwy —
  inaczej `Oshi no Ko S3 (01-11)` straciłby `S3` z serii. `ReleaseName.is_pack` = `batch` albo sezon bez
  odcinka.
- Część odcinkową otwiera OSTATNI separator `" - "`, po którym stoi cyfra; bez takiego separatora wygrywa
  pierwszy. Dzięki temu `Shingeki no Kyojin - The Final Season - 05` zachowuje podtytuł w serii, a
  `Kusuriya no Hitorigoto - Season 2 - 05` zostawia znacznik sezonu w serii dla `season_hint`.
- Zakres tuż po separatorze (`- 01-12`, `- 01~12`, `- 01 - 12`) to paczka: `batch=True`, `episode=None`.
  Seria kończy się przed takim zakresem, a wiodące i końcowe `-` wokół serii są ucinane, więc
  `[Doomdos] - Seria - 10` daje serię bez myślnika.
- `Release.published` jest zawsze aware UTC — nyaa stempluje `-0000`, które `email.utils` zwraca jako naive.
- qBittorrent: 403 wywołuje jednorazowy `auth/login` i jedno ponowienie; drugi 403 lub `Fails.`
  to `TORRENT_CLIENT_UNAUTHORIZED`, brak połączenia to `TORRENT_CLIENT_UNAVAILABLE`.
- Hasło klienta nie trafia do logów ani do `ErrorContext.details`.
- `TorrentInfo.amount_left` jest `None`, gdy brak poprawnej liczby bajtów; brak pola nie
  oznacza zera. `files()` waliduje typy i zakresy metadanych przed użyciem ich jako dowodu
  kompletności. Priorytet pliku `0` oznacza pominięcie. `qbittorrent.py`, `types.py`

## Testy

```bash
uv run pytest tests/services/torrents -v
```
