---
kind: plan
status: implemented-awaiting-owner-acceptance
baseline: fc43ddb (work/local-automation/01-watch)
branch: work/local-automation/01-watch
created: 2026-09-06
---

# Plan 02: Anime — wyszukaj tytuł, zaznacz odcinki, pobierz do biblioteki

## Cel

W Home pojawia się pozycja **Anime**. Wpisujesz tytuł, dostajesz wydania z nyaa.si w klasie 1080p+
pogrupowane po grupie wydającej, zaznaczasz odcinki (Space) i Enter wysyła je do qBittorrenta z zapisem
do `workspace/<Seria>/`. Czuwanie z Planu 01 przejmuje każdy plik po jego ukończeniu. Znika wchodzenie
na stronę z torrentami i ręczne przenoszenie plików.

## Rezultat użytkownika

- Home: Auto, Ręczny, Anime, Ustawienia, Wyjście.
- Anime → pole tytułu → Enter → lista „[Grupa] Seria — odc. 11 · 1080p · 159 seedów”, pogrupowana po grupie,
  odcinki od najnowszego. Wydania poniżej 1080p i bez rozpoznanej klasy są ukryte, z licznikiem w stopce.
- Space zaznacza, Enter pobiera zaznaczone, Esc wraca. Po wysłaniu jedno zdanie: „Wysłano 3 do qBittorrenta
  → workspace\Seria”.
- Paczka (batch) to jeden wiersz; qBittorrent tworzy jej podfolder, discovery go widzi.
- `anishift qbit status` mówi, czy WebUI odpowiada i czy sufiks `.!qB` jest włączony; `anishift qbit setup`
  włącza ten sufiks przez API (jedyna zmiana w kliencie), a gdy WebUI nie odpowiada, drukuje trzy kroki do
  wykonania w qBittorrent.

## Warunki końcowe

- [x] A01: `parse_feed` odczytuje z RSS nyaa tytuł, link `.torrent`, infoHash, seedy, rozmiar, datę; brak
      infoHash lub linku pomija wpis; ciało ponad 4 MiB, błędny XML i status ≠ 200 dają `TorrentSourceError`.
- [x] A02: `parse_release_name` rozpoznaje wzorce SubsPlease (`- 05 (1080p)`), `S01E11`, `v2`, `07.5`,
      `(01-11) [Batch]`, tytuł z nawiasem przed ` - `; nieznany wzorzec daje serię = cały tytuł, bez odcinka.
- [x] A03: `catalog_releases` odrzuca < 1080p i nieznaną klasę, grupuje po (seria, grupa), sortuje odcinki
      malejąco; `series_directory_name` daje bezpieczną nazwę Windows.
- [x] A04: klient qBittorrent: wersja, preferencje, `set_preferences`, `add_torrent(savepath, category)`,
      `torrents(category)`; 403 → login raz; brak połączenia → `TorrentClientError` z podpowiedzią.
- [x] A05: `AppService.acquisition` udostępnia `search`, `download`, `client_status`, `setup_client`;
      download ustawia `savepath = workspace/<Seria>` i kategorię `AniShift`.
- [x] A06: ekran Anime w obecnym rendererze: wpisywanie, wyniki, zaznaczanie, wysłanie, komunikaty błędów
      (brak sieci, brak klienta) jako zdanie z podpowiedzią; sieć w wątku, renderer nie blokuje.
- [x] A07: `anishift qbit status|setup`; Home ma pięć pozycji; bramki root zielone.
- [ ] A08: właściciel: wyszukał serię, zaznaczył odcinek, plik pojawił się w `workspace/<Seria>/`, czuwanie
      otworzyło okno po ukończeniu pobierania.

## Nie-cel

Subskrypcje i harmonogram (Plan 03), AniList/katalog tytułów, drugi indeks (RSS inny niż nyaa), MAL,
mpv/Oglądaj, postęp pobierania w AniShift (qBittorrent pokazuje własny), wybór plików wewnątrz paczki,
kopiowanie z folderu klienta, `qbittorrent-api` i `anitopy` jako zależności, włączanie WebUI za użytkownika.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| Wypowiedź właściciela 2026-09-05 | mądre wyszukiwanie po tytule, tylko 1080p+, podział po grupach, Space/Enter, pobranie do folderu serii, bez wchodzenia na stronę |
| [spec.md](../spec.md) R03, R05, R06, R08, R15, R16, R25, R26 | wymagania |
| [masterplan.md](../masterplan.md) §10.2, §10.4, §11 | granice Nyaa i qBittorrent |
| Sonda 2026-09-06 | qBittorrent 5.2.3 w `C:\Program Files\qBittorrent`, działa, WebUI wyłączone, sufiks `.!qB` niewłączony; nyaa RSS odpowiada 200 z `nyaa:infoHash`, `nyaa:seeders`, `nyaa:size`, link `https://nyaa.si/download/<id>.torrent` |

**Baseline:** `fc43ddb` na `work/local-automation/01-watch` (Plan 01 wykonany). Praca w tym samym
checkoucie i na tej samej gałęzi (decyzja właściciela: bez worktree).

## Stan aktualny i gap

- `services/` ma domeny z własnym AGENTS; `media/_process.py` pokazuje kontrolowany subprocess, ale nie ma
  żadnego klienta HTTP poza silnikami LLM/TTS. `httpx` jest zależnością.
- `Settings` (pydantic, prefix `ANISHIFT_`) trzyma klucze; brak ustawień klienta torrent.
- `AppService` przyjmuje wstrzykiwane granice (`inspector`, `handler_factory`) w `bootstrap.create_app_service`.
- Interaktywny Home ma cztery pozycje; `ManualController` jest wzorcem ekranu z listą, wyborem i pracą w wątku.
- Czuwanie ignoruje `.!qb`, `.part`, `.tmp`, `.crdownload` i skanuje podfoldery.
- Architektura: `anishift/cli/**` importuje z `anishift.application` tylko fasadę; nie importuje `anishift.services`.

Gap: brak źródła wydań, parsera nazw, klienta qBittorrent, warstwy aplikacyjnej i ekranu.

## Target design

### Moduły

```text
anishift/services/torrents/            # NEW domena bez rejestru silników
├── AGENTS.md
├── __init__.py                        # re-eksport publicznych nazw
├── types.py                           # Release, ReleaseName, TorrentInfo
├── errors.py                          # TorrentError, TorrentSourceError, TorrentClientError
├── names.py                           # parse_release_name
├── nyaa.py                            # search_releases, parse_feed
└── qbittorrent.py                     # QBittorrentClient
anishift/application/acquisition.py    # NEW: AcquisitionService, catalog_releases, series_directory_name, protokoły
anishift/application/service.py        # MODIFY: property acquisition
anishift/application/__init__.py       # MODIFY: eksport AcquisitionService, SeriesGroup, ReleaseChoice, ClientStatus, DownloadReceipt
anishift/bootstrap.py                  # MODIFY: składa NyaaSource + QBittorrentClient z Settings
anishift/config/settings.py            # MODIFY: qbittorrent_url/username/password
anishift/errors.py                     # MODIFY: kody TORRENT_*
anishift/cli/main.py                   # MODIFY: grupa qbit (status, setup)
anishift/cli/interactive/anime.py      # NEW: AnimeController
anishift/cli/interactive/app.py        # MODIFY: pozycja Anime, tryb ANIME
anishift/cli/interactive/home.py       # MODIFY: HomeAction.ANIME
anishift/cli/interactive/prompts.py    # MODIFY: _HOME_MENU_ROWS
tests/services/torrents/               # NEW
tests/application/test_acquisition.py  # NEW
tests/cli/test_interactive_anime.py    # NEW
tests/cli/test_main.py, test_interactive_home.py  # MODIFY
```

### Kontrakty

```text
Release(title, torrent_url, info_hash, seeders: int, size_text, published: datetime | None)
ReleaseName(group: str | None, series: str, episode: Decimal | None, season: int | None,
            resolution: int | None, batch: bool, version: int | None)
TorrentInfo(name, info_hash, progress: float, state: str, save_path: str)

parse_release_name(title) -> ReleaseName            # czysty regex, bez sieci
parse_feed(xml_text) -> tuple[Release, ...]         # xml.etree, namespace https://nyaa.si/xmlns/nyaa
search_releases(query, *, http, timeout_s=20) -> tuple[Release, ...]
    GET https://nyaa.si/?page=rss  q=<query> c=1_2 f=0; User-Agent AniShift; limit ciała 4 MiB

QBittorrentClient(base_url, *, username="", password="", http)
    version() -> str; preferences() -> dict; set_preferences(values) -> None
    add_torrent(torrent_url, *, save_path: Path, category: str) -> None   # POST torrents/add (form)
    torrents(category) -> tuple[TorrentInfo, ...]
    403 -> POST auth/login (Referer = base_url) raz; ConnectError -> TorrentClientError(UNAVAILABLE,
    suggestion: „W qBittorrent: Opcje → Web UI → włącz, zaznacz „Pomiń uwierzytelnianie dla localhost”)

catalog_releases(releases, *, min_resolution=1080) -> tuple[SeriesGroup, ...]
    SeriesGroup(series, group, choices: tuple[ReleaseChoice, ...]); ReleaseChoice(release, name)
    hidden_count dostępny obok (ReleaseCatalog(groups, hidden))
series_directory_name(series) -> str   # usuwa <>:"/\|?*, kropki i spacje na końcu, nazwy zastrzeżone -> "_"

AcquisitionService(source, client, workspace_root, category="AniShift")
    search(query) -> ReleaseCatalog
    download(choices) -> DownloadReceipt(count, directory)    # savepath = workspace_root / series_directory_name
    client_status() -> ClientStatus(reachable, version, incomplete_extension)
    setup_client() -> ClientStatus                             # set_preferences({"incomplete_files_ext": True})

AppService.acquisition -> AcquisitionService                   # wstrzykiwany w create_app_service
Settings: qbittorrent_url = "http://127.0.0.1:8080", qbittorrent_username = "", qbittorrent_password = "" (repr=False)
CLI: anishift qbit status -> "reachable: yes (5.2.3), incomplete extension: on" | "reachable: no" + podpowiedź; 0/1
     anishift qbit setup  -> włącza sufiks; 0/1
```

### Ekran Anime

- Wejście z Home. Ekran QUERY: jedna linia edycji (wzorzec edytora Ustawień), Enter szuka, Esc wraca.
- BUSY: „Szukam…” w wątku `anishift-anime`; błąd sieci → zdanie + podpowiedź, Enter ponawia.
- RESULTS: nagłówek grupy, pod nim wiersze odcinków; ↑↓ nawigacja, Space zaznacza, Enter wysyła
  zaznaczone (brak zaznaczenia → wysyła podświetlony), Esc → QUERY. Stopka: liczba zaznaczonych i ukrytych.
- SENDING → DONE: zdanie z liczbą i folderem, dowolny klawisz → Home. Błąd klienta → zdanie + podpowiedź.
- Wszystko przez `AppService.acquisition`; kontroler nie importuje services ani httpx.

### Edge cases

| Przypadek | Oczekiwane |
| --- | --- |
| nyaa zwraca HTML/challenge zamiast XML | `TorrentSourceError`, zdanie „Nyaa nie odpowiedziało poprawnie” |
| wpis bez infoHash | pominięty |
| tytuł `[Judas] Neko to Ryuu (The Cat and the Dragon) - S01E11 [1080p]` | seria z nawiasem, odc. 11, sezon 1, 1080 |
| `[SubsPlease] Oshi no Ko S3 (01-11) (1080p) [Batch]` | batch, seria „Oshi no Ko S3”, odc. None |
| `[Group] Title - 07.5 (1080p)` | episode Decimal("7.5") |
| 720p i brak klasy | ukryte, policzone |
| WebUI wyłączone | ekran: zdanie + podpowiedź; `qbit status` kod 1 |
| 403 przy dodawaniu | login i ponowienie; drugi 403 → UNAUTHORIZED |
| seria z `:` w nazwie | folder bez `:` |
| ten sam torrent dodany drugi raz | qBittorrent odpowiada „Fails.”/duplikat → zdanie „już w kliencie”, bez wyjątku |

## Plan wykonania

Fazy 1 i 2 równolegle; 3 po nich; 4 po 3.

1. **Domena torrents** (subagent A): `services/torrents/*`, `errors.py` (kody), `tests/services/torrents/*`,
   `AGENTS.md`. Commit `feat(services): add nyaa search and a qBittorrent client`.
2. **Warstwa aplikacyjna** (integrator): `settings.py`, `application/acquisition.py`, `service.py`,
   `bootstrap.py`, fasada, `cli/main.py` (`qbit`), testy. Commit `feat(application): add release catalog and
   download through qBittorrent` + `feat(cli): add qbit status and setup`.
3. **Ekran Anime** (subagent C): `anime.py`, `app.py`, `home.py`, `prompts.py`, testy. Commit
   `feat(cli): add the Anime search and download screen`.
4. **Docs + odbiór**: README, AGENTS, plan outcome; właściciel: `anishift qbit setup`, wyszukanie, pobranie.

## Strategia dowodu

Unit: parser nazw (tabela), parser RSS na fixture z realnej struktury, klient z `httpx.MockTransport`,
katalog i nazwy folderów, AcquisitionService z fake'ami, AnimeController z fake service (wzorzec testów Manual).
CLI: CliRunner. Human: A08. Bramki root przed commitem.

## Ryzyka

| Ryzyko | Reakcja |
| --- | --- |
| nyaa blokuje/CAPTCHA | zdanie w UI; brak retry w pętli |
| plik rzadki o pełnym rozmiarze bez `.!qB` (setup nie wykonany) | `qbit status` ostrzega; README każe zrobić `qbit setup` przed pierwszym pobraniem |
| różne nazwy serii między grupami | folder z nazwy wybranego wydania; użytkownik wybiera grupę |

## Wynik wykonania (2026-09-06)

| Commit | Faza |
| --- | --- |
| `f40d21e` | 1: `services/torrents` (nyaa RSS, parser nazw, klient qBittorrent), 35 testów |
| `7dcd358` | 2: ustawienia `ANISHIFT_QBITTORRENT_*`, `application/acquisition.py`, `AppService.acquisition`, bootstrap |
| `c57f792` | 2: `anishift qbit status|setup` |
| (kolejny) | 3: ekran Anime, pięć pozycji Home, 19 testów |
| (kolejny) | 4: README, AGENTS |

Dowody: ruff, format, mypy (win32 i linux) czyste; pytest 3281 passed, 2 failed — oba failures wynikają z
nieśledzonego `shadow-slave.md` właściciela (czwarty styl promptu), nie z tego planu. Próba na żywo przez
złożoną usługę: „Neko to Ryuu” → 26 grup, 20 ukrytych < 1080p, SubsPlease na górze (odc. 11/10/9, seedy);
`anishift qbit status` przy wyłączonym WebUI → `reachable: no` z podpowiedzią, kod 1.

Odchylenia: wiersze wyników mają stałą kolumnę `[ ]`/`[x]`; stopka wyników zawijana po ` · `; wydania bez
separatora „ - ” (np. ToonsHub) mają w nazwie serii resztę tytułu.

Nie wykonano: A08 (odbiór właściciela: włączenie WebUI, `qbit setup`, wyszukanie, pobranie, przejęcie przez
czuwanie).

Domknięcie (2026-09-06): Web UI qBittorrenta 5.2.3 włączone w `qBittorrent.ini` właściciela (nasłuch tylko
`127.0.0.1:8080`, bez logowania z localhost; qBittorrent 5 wymaga też ustawionego hasła admina, więc dostało
losowe). `anishift qbit setup` na żywo: `reachable: yes (v5.2.3)`, `incomplete extension: on`. Wersja z API ma
prefiks `v`, klient go zdejmuje (wcześniej CLI pokazywało `vv5.2.3`). Próba pobrania prawdziwego wydania nie
została wykonana; A08 (wyszukanie, Space/Enter, plik w `workspace/<Seria>/`, przejęcie przez czuwanie) pozostaje
odbiorem właściciela.
