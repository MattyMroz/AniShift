# ficzer: auto-pobieranie anime do workspace

> status: POMYSŁ (poza obecną przebudową)
> priorytet: wysoki — domyka pętlę "nazwa anime → gotowy lektor" bez ręcznego szukania plików
> cel: user wpisuje `/download <nazwa anime>`, program znajduje odcinki, pobiera MKV prosto do `workspace/`, a Enter przetwarza je jak każde inne pliki.

## ⚠️ legalność — przeczytaj zanim cokolwiek powstanie

Torrenty z anime to w praktyce **szara/nielegalna strefa** — indeksery typu Nyaa hostują niemal wyłącznie materiały bez licencji dystrybucyjnej. Konsekwencje projektowe:

- moduł jest **opcjonalny i domyślnie wyłączony** — AniShift działa w pełni bez niego; to user świadomie go włącza i **user odpowiada za źródła**, z których pobiera.
- AniShift **nie hostuje, nie linkuje w README i nie promuje** żadnego indeksera — konfiguracja źródła to decyzja usera (analogicznie do tego, jak działają Sonarr/Radarr: narzędzie automatyzuje, user dostarcza indeksery).
- w repo żadnych wbudowanych trackerów prywatnych, kluczy ani passkey.
- jedyna w pełni legalna ścieżka to metadane: AniList/Jikan (patrz niżej) są legalne i darmowe. Legalnego API do pobierania samych plików wideo nie ma (Crunchyroll itd. nie udostępniają API do downloadu) — dlatego alternatywy nie istnieją, a moduł zostaje opt-in z wyraźną notą w `/settings`.

## problem / motywacja

Dziś pętla pracy zaczyna się poza AniShift: user musi sam znaleźć odcinek, pobrać go i wrzucić do `workspace/`. To najbardziej manualny krok całego procesu. Automatyzacja: nazwa anime → metadane → wyszukanie torrenta → pobranie → plik ląduje w `workspace/` → istniejący pipeline przejmuje. Zero zmian w pipeline — moduł tylko "karmi" workspace.

## technologie i repozytoria

### sterowanie pobieraniem (klient torrent)

| technologia | po co | dojrzałość | plusy | minusy |
|---|---|---|---|---|
| `qbittorrent-api` (pip) | sterowanie qBittorrent przez Web API: dodaj magnet, ustaw ścieżkę zapisu, kategoria, poll postępu | bardzo wysoka — wydania 2026.x, pokrywa cały Web API qBittorrent v5.x, auto-odnawianie cookie sesji | pełne API; qBittorrent robi całą robotę torrentową (DHT, resume, limity); user i tak zwykle ma qBittorrent; zero własnej logiki sieciowej | wymaga zainstalowanego qBittorrent z włączonym Web UI (doctor to sprawdzi); zależność od zewnętrznej apki |
| `libtorrent` (pip, oficjalne bindingi rasterbar) | wbudowany klient torrent w procesie Pythona — bez zewnętrznej apki | wysoka (biblioteka), ale bindingi bywają kapryśne na Windows | samowystarczalne — user nie instaluje nic | cała sesja torrent (resume data, porty, limity, seedowanie) staje się NASZYM kodem — dziesiątki edge-case'ów, które qBittorrent już rozwiązał; wheel-e na Windows historycznie problematyczne |
| `transmission-rpc` (pip) | to samo co qbittorrent-api, ale dla Transmission | wysoka, dojrzała | prosty daemon, lekki RPC | Transmission to rzadkość na Windows — nasz user siedzi na Windows |
| `deluge-client` (pip) | RPC do deluged | średnia — mało aktywny | lekki | Deluge słabnie przy wielu torrentach; klient mniej rozwijany |

**wybór: `qbittorrent-api`.** Najmniej naszego kodu, najdojrzalsze API, klient który user prawdopodobnie już ma. Reszta odnotowana jako świadomie odrzucona — bez rejestru "silników pobierania", bo realnego wyboru nie ma (YAGNI).

### wyszukiwanie (indeksery)

| technologia | po co | dojrzałość | plusy | minusy |
|---|---|---|---|---|
| RSS Nyaa.si + `feedparser` (pip) | wyszukiwarka Nyaa ma wbudowany feed RSS (`?page=rss&q=...&c=1_2&f=2` — kategoria anime-eng, tylko trusted); feedparser to standard parsowania RSS | feedparser: bardzo wysoka (wieloletni standard); RSS Nyaa: stabilny od lat, w polach rozszerzonych daje seedery/leechery/infohash/rozmiar | **zero scrapera** — oficjalny mechanizm strony, nie łamie się przy zmianie HTML; jedna lekka zależność | brak paginacji głębokiej (RSS zwraca ~75 wyników — dla szukania odcinków wystarcza); Nyaa bywa niedostępna (mirrory) |
| `NyaaPy` (pip `nyaapy`, repo JuanjoSalvador/NyaaPy) | scraper HTML Nyaa z wygodnym API (search, kategorie, strony) | niska-średnia — utrzymanie sporadyczne, łamie się gdy Nyaa zmieni HTML | gotowe obiekty wyników | kruchość scrapera; RSS daje to samo taniej |
| `nyaascraper` (pip) | nowszy, asynchroniczny scraper Nyaa + sukebei, ma też klienta RSS | średnia — aktywniejszy niż NyaaPy | async, filtry, sortowanie | dalej scraper HTML; async niepotrzebny (fasady AniShift są sync) |
| Animetosho (JSON API: `feed.animetosho.org/json`) | mirror wpisów Nyaa/TokyoTosho z **prawdziwym JSON API** — ustrukturyzowane metadane, magnety, listy plików | wysoka — serwis działa stabilnie od lat, API udokumentowane | jedyne źródło z prawdziwym API zamiast RSS/scrape; dane o zawartości torrenta (które pliki to MKV) | zależność od jednego serwisu-mirrora; opóźnienie indeksowania względem Nyaa |
| AniDex | drugi indekser anime | niska — częste przestoje, brak API | teoretyczny zapas | w praktyce zbyt niestabilny — nie planować |

**wybór: dwa silniki w rejestrze — `nyaa` (RSS + feedparser) i `animetosho` (JSON API).** Tu wybór jest realny (różne źródła, różna dostępność), więc pasuje wzorzec `engines/` z sekcji E planu. NyaaPy/nyaascraper odrzucone: scraper przegrywa z oficjalnym RSS.

### metadane anime (tytuły, numeracja odcinków)

| technologia | po co | dojrzałość | plusy | minusy |
|---|---|---|---|---|
| AniList GraphQL API (`graphql.anilist.co`) | z nazwy wpisanej przez usera → kanoniczne tytuły (romaji/english/synonimy), liczba odcinków, format, sezon | bardzo wysoka — publiczne, bez klucza, limit ~90 req/min | jedno zapytanie GraphQL zwraca dokładnie potrzebne pola; synonimy tytułów kluczowe do budowy zapytania na indekser; zwykły `httpx`/`requests`, **zero dodatkowej biblioteki** | GraphQL to odrobina nauki (jeden statyczny query — trywialne) |
| Jikan v4 (REST, `api.jikan.moe`) + `jikanpy-v4` (pip) | to samo z bazy MyAnimeList | wysoka (Jikan aktywnie rozwijany) | REST prostszy koncepcyjnie; MAL ma największą bazę | ostrzejsze limity (3 req/s), scraper MAL pod spodem — bywa wolny; dodatkowa zależność jeśli brać jikanpy |
| `anitopy` (pip) | parsowanie nazw release'ów (`[Grupa] Tytuł - 05 [1080p]...` → tytuł, odcinek, grupa, rozdzielczość) | wysoka — port sprawdzonego anitomy, stabilny od lat | bez tego nie da się wiarygodnie dopasować wyniku z indeksera do odcinka; czysty Python, zero zależności | rozwój zamrożony (ale format nazw release'ów też się nie zmienia) |

**wybór: AniList (gołym httpx, bez biblioteki) + `anitopy`.** Jikan jako odnotowany zapas, bez implementacji.

## architektura modułu

Domena z realnym wyborem źródła → fasada + rejestr silników, kropka w kropkę wzorzec z sekcji E planu (jak `translation/`). Pobieranie (qBittorrent) to zwykły moduł w domenie — bez rejestru, bo klient jest jeden.

```
anishift/services/acquisition/
├── __init__.py
├── config.py            # AcquisitionConfig (engine_id źródła wymagany) + QbtConfig (host/port/login Web UI)
├── constants.py
├── errors.py            # AcquisitionError, IndexerUnavailableError, TorrentClientError, NoResultsError
├── protocols.py         # Protocol źródła: engine_id, is_available, search(query) -> list[TorrentResult]
├── types.py             # TorrentResult (tytuł, magnet, seedery, rozmiar, trusted, odcinek z anitopy),
│                        #   DownloadStatus (postęp, prędkość, ETA, stan)
├── metadata.py          # AniList GraphQL: nazwa usera -> AnimeInfo (tytuły+synonimy, liczba odcinków)
├── ranking.py           # scoring wyników: trusted > seedery > preferowana rozdzielczość > batch vs odcinek
├── downloader.py        # klient qBittorrent (qbittorrent-api): add magnet (save_path=workspace/,
│                        #   category="anishift"), poll postępu, wykrycie ukończenia
├── service.py           # fasada sync: metadane -> search (create_engine) -> ranking -> download -> poll
└── engines/
    ├── __init__.py      # _REGISTRY: nyaa, animetosho + available_engine_ids() + create_engine()
    ├── nyaa/            # __init__.py, config.py, constants.py, service.py
    │                    #   RSS nyaa.si przez feedparser; parsowanie nazw przez anitopy
    └── animetosho/      # __init__.py, config.py, constants.py, service.py
                         #   JSON API feed.animetosho.org; anitopy na nazwach

anishift/cli/
├── commands.py          # ZMIANA: nowa komenda /download w mapie COMMANDS
└── download_panel.py    # NOWY: interakcja — lista wyników (rich table), wybór, pasek postępu pobierania

anishift/setup/
└── doctor.py            # ZMIANA: check "qBittorrent Web UI osiągalny" (tylko gdy moduł włączony)
```

### opis plików

- **`config.py`** — `AcquisitionConfig` (dataclass slots): wymagany `engine_id` źródła (default trzyma panel, jak wszędzie), preferowana rozdzielczość, filtr "tylko trusted", limit wyników. `QbtConfig`: host/port Web UI, login/hasło z `.env` (`ANISHIFT_QBT_*`). Zero defaultu silnika w serwisie.
- **`protocols.py`** — Protocol źródła: `engine_id`, `is_available` (np. HEAD na endpoint — indekser leży = znika z panelu, jak balcon poza Windows), `search(query) -> list[TorrentResult]`.
- **`metadata.py`** — jedno statyczne zapytanie GraphQL do AniList: tytuł romaji/english + synonimy + `episodes` + format. Synonimy służą do budowy kilku wariantów zapytania na indekser (anime często ma inny tytuł w release'ach niż wpisał user).
- **`ranking.py`** — czysta funkcja: lista `TorrentResult` → posortowana wg trusted, seederów, dopasowania rozdzielczości; preferencja batch (cały sezon) gdy user chce wszystkie odcinki, pojedynczy odcinek gdy podał numer. Osobny plik, bo to jedyna "mądra" logika modułu — łatwa do testu jednostkowego bez sieci.
- **`downloader.py`** — cienki wrapper na `qbittorrent-api`: dodaj magnet z `save_path` wskazującym na `workspace/` i kategorią `anishift`, potem poll `torrents_info(category="anishift")` co ~2 s → `DownloadStatus`. Wykrycie ukończenia = stan `uploading`/`stalledUP`/`completed`. Nic więcej — limity, kolejki, resume to sprawa qBittorrent.
- **`service.py`** — fasada sync, jedyny publiczny punkt: `acquire(nazwa, odcinek?) `. Nie zna żadnego konkretnego indeksera — woła `create_engine`. Zwraca ścieżki pobranych MKV.
- **`engines/nyaa/service.py`** — składa URL RSS (`?page=rss&q=<tytuł>&c=1_2&f=2`), `feedparser.parse`, mapuje wpisy (pola `nyaa:seeders`, `nyaa:infoHash`, rozmiar) na `TorrentResult`, `anitopy` wyciąga numer odcinka/rozdzielczość z nazwy.
- **`engines/animetosho/service.py`** — GET na JSON API, mapowanie pól na te same `TorrentResult`. Bonus: API zwraca listę plików w torrencie — filtr "zawiera MKV" przed pokazaniem userowi.
- **`cli/download_panel.py`** — UX: `/download <nazwa>` → potwierdzenie znalezionego anime (tytuł + liczba odcinków z AniList) → tabela rich z top wynikami (nazwa, odcinek, rozmiar, seedery, trusted) → wybór (w trybie auto: pierwszy wynik z rankingu) → pasek postępu przez `utils/rich_console` ProgressBarManager → komunikat "gotowe — Enter przetworzy".
- **`doctor.py`** — nowy `CheckResult`: Web UI qBittorrent odpowiada na skonfigurowanym host:port. Check aktywny tylko przy włączonym module (wyłączony moduł nie czerwieni doktora).

## przepływ

1. user: `/download frieren` (opcjonalnie `/download frieren 5` — konkretny odcinek).
2. `metadata.py` → AniList: kanoniczny tytuł "Sousou no Frieren", synonimy, 28 odcinków. Panel pokazuje dopasowanie do potwierdzenia (w manual; auto bierze pierwsze).
3. fasada woła `create_engine(engine_id z ustawień)` → `search()` dla wariantów tytułu → lista `TorrentResult`.
4. `ranking.py` sortuje; `anitopy` już przypisał numery odcinków — wyniki bez dopasowania do żądanego odcinka odpadają.
5. manual: tabela wyboru; auto: top wyniku rankingu.
6. `downloader.py` dodaje magnet do qBittorrent (`save_path=workspace/`, kategoria `anishift`).
7. poll co 2 s → pasek postępu (%, prędkość, ETA) w shellu; Ctrl+C przerywa poll, **nie** pobieranie (qBittorrent ciągnie dalej — komunikat o tym).
8. ukończone → MKV leży w `workspace/` (torrent z podfolderem: przenieś MKV płasko do `workspace/`, zgodnie z zasadą "workspace jest płaski"). Komunikat: "pobrano N plików — Enter uruchamia pipeline".
9. Enter → istniejący runner przetwarza jak każdy ręcznie wrzucony plik. **Zero zmian w pipeline.**

## ryzyka / uwagi

- **legalność** — patrz nota na górze; moduł opt-in, user odpowiada za źródła, żadnych promowanych indekserów.
- **qBittorrent jako zależność zewnętrzna** — user musi mieć qBittorrent z włączonym Web UI; doctor prowadzi za rękę (komunikat jak włączyć Web UI). Bez qBittorrenta moduł znika z panelu (`is_available`), apka działa dalej.
- **kruchość indekserów** — Nyaa miewa przestoje i mirrory; dlatego dwa silniki w rejestrze i `is_available` per źródło. RSS zamiast scrapera minimalizuje łamliwość.
- **dopasowanie tytułów** — release'y używają romaji, user wpisze po angielsku/polsku; synonimy z AniList + anitopy łagodzą, ale trafność nie będzie 100% — tryb manual z tabelą wyboru jest pierwszorzędny, auto to skrót dla pewnych przypadków.
- **torrenty-batche** — cały sezon w jednym torrencie z podfolderem; trzeba przenieść MKV płasko do `workspace/` i ewentualnie wybrać podzbiór plików (qbittorrent-api umie ustawić priorytet 0 na niechciane pliki).
- **seedowanie** — po pobraniu torrent seeduje; zostawić decyzję qBittorrentowi (ustawienia usera), AniShift nie kasuje torrentów sam.

## rekomendacja

Warto — to najbardziej odczuwalny ficzer z całej listy (usuwa jedyny ręczny krok). Ale dopiero **po zakończeniu przebudowy (etap 8)**: moduł dotyka CLI, doctora i ustawień, więc potrzebuje stabilnego fundamentu. Zacząć od pionowego przecięcia: `metadata.py` + silnik `nyaa` + `downloader.py` + `/download` w trybie manual (tabela wyboru) — to działający produkt; ranking-auto i `animetosho` jako druga iteracja. Rejestr silników przenosi się wzorcem 1:1 z `translation/`, więc koszt architektury jest bliski zeru.
