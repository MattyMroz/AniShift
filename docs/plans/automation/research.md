---
kind: research
status: revised-for-review
baseline: 369efcd (main 6eef7d1)
updated: 2026-09-05
---

# Research: automatyzacja folderu, pozyskiwanie i układ napisów

## Odpowiedź

Trzy kierunki są wykonalne na obecnym kodzie bez drugiego pipeline'u, ale
każdy ma jedną niewiadomą, którą trzeba domknąć małym eksperymentem, a nie
kodem. Watcher potrzebuje własnego rejestru zleceń z tożsamością biblioteki
i prawdziwej blokady systemowej, bo obecne mechanizmy są procesowe.
Pobieranie ma sterować zewnętrznym qBittorrentem 5.x przez już używany
`httpx`, a źródła wyszukiwania to wtyczki zainstalowane przez użytkownika
w jego kliencie, więc repozytorium nie definiuje żadnego parsera indeksera.
Dialog polski ma działającą ochronę `się` z dwoma obejściami w fallbackach;
ozdobny ASS wymaga najpierw dowodu renderu z maską różnicy i próbkami czasu.

## Zakres i stan na dzień

Kod `369efcd`; PR #41 scalony do `main` jako `6eef7d1` z zielonym CI, drzewo
kodu identyczne. Nie uruchamiano testów, aplikacji ani narzędzi. Nie otwierano
indekserów, `.env`, logów, `workspace/`, `config/` runtime ani `shadow-slave.md`.
Lokalny wynik przed izolacją: 3014 passed, 2 failed, 9 skipped; oba failure
wiązały się z prywatnym stylem. Później prowadzący sprawdził dokładny commit
publikacji w izolowanym worktree: 2990 passed, 35 skipped, bez failures.
Więcej skipów wynikało z braku lokalnych narzędzi i fixture'ów w tej kopii.
Kontrole PR #41 i CI po scaleniu przeszły. Nie jest to dowód wszystkich
scenariuszy produktu ani test bieżącego procesu użytkownika.

## Ustalenia z kodu

### Tożsamość, cache, blokady

- `application/discovery.py:246` woła `create_group_id(Path(), first.stem)`,
  więc `group_id` zależy tylko od stemu. Dwie biblioteki z tym samym stemem
  dają ten sam identyfikator. Rejestr watchera musi mieć własną tożsamość
  root; `group_id` jest kluczem tylko wewnątrz jednego root.
- `application/service.py:_workspace_fingerprint` liczy (ścieżka, rozmiar,
  `st_mtime_ns`) dla wszystkich artefaktów grup, także produktów. Każda
  publikacja produktu unieważnia cache i wymusza pełną reinspekcję.
- `application/sessions.py:RunSession` chroni konkretny katalog runu, nie całą bibliotekę, w obrębie procesu
  (`_ACTIVE_ROOTS`); marker `.anishift-owner` z PID służy sprzątaniu sierot
  (`config/workspace.py:cleanup_orphaned_temp`, pomija wpisy niebędące
  katalogami). `service.py:_claim_run` blokuje drugi run w tym samym procesie.
  Dwa procesy mogą dziś równolegle wykonać ten sam plan; publikacja jest
  atomowa (`publisher.py`: `mkstemp` z sufiksem `.tmp<ext>` obok celu, potem
  `replace`), co nie dowodzi spójności wielu produktów ani zgodności ostatniego wyniku
  z właściwym wejściem; ostatni writer może wygrać.
- `planner.py:_durable_target` przy istniejącym produkcie dodaje nieblokujący
  problem `product_overwrite`; `plan_auto` nigdy nie pomija ukończonych grup.
  `cli/run.py:prepare_auto_run` bierze `ready_group_ids` ze wszystkich grup;
  `AppService.plan_auto(group_ids, preset)` przyjmuje podzbiór.
- `results.py`: `ProducedArtifact.metadata` to mapa `str -> str|int|bool`,
  `RunResult.warnings` to krotka tekstów; oba istnieją i nadają się na
  diagnozy bez nowego kontraktu.

### Ustawienia Auto (Plan 05)

- `config/field_catalog.py:_workflow_specs` w kontekście `RunMode.AUTO` daje
  osiem speców `AUTO_PRESET`; panel edytuje tylko `requested_products`
  (`cli/interactive/settings.py:_save_output`, pełny `AutoPresetDraft`).
- `config/field_access.py:setting_is_active` woła `_preference_value`, które
  rzuca `ValueError` dla identyfikatorów spoza `UserSettings`; trzy pola
  produktowe mają `depends_on` na `requested_products`.
- `_reset_scope` dla root woła `reset_settings()` i `_restore_default_products()`;
  po dodaniu siedmiu pól reset root nie przywracałby całego presetu.

### Dialog i ASS

- `services/translation/linebreak.py:_protected` blokuje cięcie przed `się`,
  po prostym przyimku i wewnątrz fraz wielowyrazowych. Obejścia: `_best_cut`
  bez niechronionych kandydatów woła `_greedy_cut`; `_proportional_boundaries`
  przy pustej liście bierze wszystkie indeksy. Przepełnienie jest przyjmowane
  cicho. `split_line` zwraca `tuple[str, ...]` i jest publiczne.
- `services/subtitles/text.py:replace_visible_text` mapuje kotwice tagów
  proporcjonalnie po grafemach; tagi z początku linii zostają na początku,
  tagi śródtekstowe i karaoke są przesuwane po proporcji, co nie zachowuje
  ich semantyki. `service.py:_translated_file` kopiuje rysunki (`is_drawing`)
  bez zmian, a każdy inny event otrzymuje przetłumaczony tekst.
- `services/subtitles/classifier.py` ma `_RE_KARA`, `_RE_POS`, `_RE_DRAW` na
  poziomie stylu; brak ochrony per event.
- Nic w kodzie nie mierzy szerokości tekstu. `pillow`, `pysubs2`, `httpx`
  są zależnościami w `pyproject.toml`; `ffmpeg` jest binarką projektu.

## Ustalenia ze źródeł

| Twierdzenie | Źródło, data odczytu | Status |
| --- | --- | --- |
| Kod rozwojowy master: akcje `torrents/stop` i `torrents/start`, brak aliasów pause/resume; stany `stoppedUP`/`stoppedDL`, `metaDL`, `forcedMetaDL`, `stalledDL`, `checkingDL`, `checkingUP`, `checkingResumeData`, `moving`, `missingFiles`, `error`, `unknown` | [torrentscontroller.cpp](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/torrentscontroller.cpp), [serialize_torrent.cpp](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/serialize/serialize_torrent.cpp), 2026-09-05 | verified (kod master) |
| `torrents/add` czyta m.in. `stopped`, `savepath`, `downloadPath`, `category`, `tags`, `rename`, `autoTMM`, `stopCondition`, `contentLayout`, `filePriorities`; nie czyta `paused` | jw. | verified |
| `torrents/files` zwraca `index`, `name`, `size`, `progress`, `priority`, `availability`, `piece_range`, `is_seed`; brak pola atrybutów/symlinku | jw.; wiki 5.0 potwierdza brak | verified |
| `torrents/info` niesie `progress`, `state`, `save_path`, `download_path`, `content_path`, `amount_left`, `completion_on`, `infohash_v1/v2`; `torrents/delete` ma `hashes`, `deleteFiles` | jw. | verified |
| Search API: `search/start(pattern, category, plugins)` z wartościami `all`/`enabled`; `search/results(id, limit, offset)` zwraca `status`, `total`, `results[]` z `fileName`, `fileUrl`, `fileSize`, `nbSeeders`, `nbLeechers`, `engineName`, `siteUrl`, `descrLink`, `pubDate`; `search/stop`, `search/delete`, `search/plugins` (`name`, `version`, `fullName`, `url`, `supportedCategories`, `enabled`) | [searchcontroller.cpp](https://raw.githubusercontent.com/qbittorrent/qBittorrent/master/src/webui/api/searchcontroller.cpp), 2026-09-05 | verified (kod master) |
| Wiki 5.0 w części tekstu nadal podaje `pausedUP`; strona ucina się przed sekcjami wyszukiwania i dodawania | [wiki WebUI-API 5.0](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29), 2026-09-05 | rozbieżność wersji; master nie dowodzi kontraktu wydania 5.x |
| watchfiles 1.2.0 ma koło `watchfiles-1.2.0-cp314-cp314-win_amd64.whl` | [PyPI JSON](https://pypi.org/pypi/watchfiles/json), prowadzący 2026-09-05 | verified |
| libtorrent najnowsze 2.1.1; koła Windows do cp313, bez cp314 | [PyPI JSON](https://pypi.org/pypi/libtorrent/json), prowadzący 2026-09-05 | verified |
| mpv: `sub-ass-override` przyjmuje no/yes/scale/force/strip; force i strip mogą niszczyć ASS; `sub-ass-force-margins` domyślnie no; `sub-use-margins` dotyczy zwykłego tekstu | [mpv manual](https://mpv.io/manual/stable/), prowadzący 2026-09-05 | verified |
| BEP 3: w trybie wielu plików każdy plik ma listę `path` z możliwymi podkatalogami; BEP 47: atrybut `p` (padding) i `l` (symlink) | [bep_0003](https://www.bittorrent.org/beps/bep_0003.html), [bep_0047](https://www.bittorrent.org/beps/bep_0047.html), 2026-09-05 | verified |
| Aegisub: `\N` łamie zawsze, `\n` tylko w `\q2`, `\h` twarda spacja; `\pos`, `\move`, `\clip`, `\org`, `\fad` raz na linię; `\t` animuje; `\k`, `\K`, `\kf`, `\ko` karaoke; `\p` rysunek | [ass_tags](https://aegisub.org/docs/latest/ass_tags/), 2026-09-05 | verified |
| Netflix Polish: 42 znaki/wers, najwyżej dwa wersy, dolny wers cięższy, jeden mówca na wers; to wytyczne konkretnego dostawcy, nie uniwersalna norma języka | [Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide), 2026-09-05 | verified |

## Sprzeczności i ograniczenia

- Blokada procesu: samo istnienie pliku z PID nie jest blokadą; potrzebna
  blokada trzymana przez otwarty uchwyt (`msvcrt.locking` na Windows,
  `fcntl.flock` gdzie indziej), zwalniana przez system przy śmierci procesu.
  Zachowanie na tej maszynie nie było uruchamiane; Plan 01 ma bramkę E01.
- Gotowość pliku: okno spokoju i stały `mtime` nie dowodzą końca kopiowania;
  plik prealokowany ma stały rozmiar od początku. Polling nie odróżnia
  rename od utworzenia. Jedyne pewne sygnały to przekazanie z pobierania
  (stan API klienta) i jawne potwierdzenie użytkownika.
- Hash statów ani próbki początku/końca nie są tożsamością całej treści.
  Propozycja Planu 01: pełny streamingowy hash po potwierdzeniu gotowości,
  z postępem i pomiarem kosztu; staty są tylko tanim sygnałem do ponownego sprawdzenia.
- API `torrents/files` nie zdradza atrybutów BEP 47. Potrzebna jest walidacja
  surowej metadanej przed przekazaniem payloadu do klienta. Sam późniejszy
  `lstat` nie spełnia D06. Plan 02 wymaga dowodu takiego kontraktu przed implementacją.
- Jedna klatka i tło czarne nie dowodzą niczego o ASS; klatka przycięta do
  kadru nie pokazuje przepełnienia poza kadr.
- Brak dostępu do runtime: żadne twierdzenie o czasie `discover()` na dużej
  bibliotece ani o zachowaniu Windows przy kopiowaniu nie jest zmierzone.

## Rekomendacje

1. Watcher jako pętla pollingu na `os.scandir` bez nowej zależności, bo folder
   jest płaski i jeden; `watchfiles` ma koło cp314, więc pozostaje opcją po
   pomiarze, nie koniecznością.
2. Rejestr per root w `config/watch/<root-key>.json`, jeden writer (proces
   trzymający blokadę watchera), kanoniczna serializacja z wersją schematu.
3. Propozycja: qBittorrent przez `httpx`, bez nowego rejestru silników.
   `requests`, `urllib3`, `packaging`, `filelock` już są w `uv.lock` pośrednio;
   argumentem przeciw wrapperowi nie jest brak tych pakietów. Decyzja dotyczy
   utrzymania nowego klienta/wrappera. Retry i metadata-only wymagają E02;
   nie utożsamiać obsługi 429 w `_retry.py` z obsługą `Retry-After`.
4. Dialog: domknięcie fallbacków z ostrożnymi karami i korpusem; ozdobny ASS:
   eksperyment renderu z maską różnicy na jednolitym tle, próbki czasowe,
   licencjonowany font OFL, dopiero potem decyzja o kodzie.

## Stan starej roadmapy

| Pozycja | Werdykt | Powód |
| --- | --- | --- |
| auto-download: sterowanie qBittorrent | planować (Plan 02) | zewnętrzny klient; wbudowany libtorrent bez cp314 |
| auto-download: rejestr silników, szablony URL indekserów | odrzucić | rejestry tylko translation/tts/llm; źródła to wtyczki klienta |
| auto-download: AniList, `anitopy`, cache | odłożyć | niezweryfikowane; v1 z wyborem ręcznym |
| auto-download: przenoszenie MKV z podfolderu | odrzucić | nie przemieszczać danych za plecami klienta |
| watch mode: polling w sesji | planować (Plan 01) | zgodne z O02 |
| style_classifier | zrobione | `services/subtitles/classifier.py` |
| PyAV, GUI, multi-voice, licznik kosztów, integracja odtwarzacza | odrzucić | poza zakresem specyfikacji |
| layout engine: hierarchia i związki składniowe | planować (Plan 03 A) | zgodne z S01–S04 |
| layout engine: pomiar szerokości, spaCy, uniseg | eksperyment / odłożyć | niewiadoma geometrii; benchmark przed zależnością |
| layout engine: waveform, OCR | odrzucić | poza produktem |
