---
kind: review
status: fail
reviewed-state: 4f7de67 (work/local-automation/05-polish) — złożony rezultat planów 01–04
date: 2026-09-06
---

# Review: automatyzacja lokalna (plany 01–04) — czuwanie, wyszukiwanie, pobieranie, subskrypcje

## Zakres

- **przedmiot:** złożony rezultat planów 01–04: `anishift/application/{watch,acquisition,subscriptions}.py`,
  `anishift/cli/{watch,main,exit_codes}.py`, `anishift/cli/interactive/{anime,app,home}.py`,
  `anishift/services/torrents/*`, `anishift/services/catalog/*`,
  `anishift/platform/{autostart,process_lock,qbittorrent_config}.py`, `anishift/setup/doctor.py`,
  `anishift/bootstrap.py`, sekcje README „Searching and downloading", „Following a series",
  „Watching the library", „Technical commands", „Requirements".
- **baseline:** HEAD `4f7de67` na gałęzi `work/local-automation/05-polish`; drzewo robocze zawiera
  cudze, nieśledzone pliki (`tests/integration/`, `tests/fixtures/`, `docs/plans/remote-automation/`,
  zmodyfikowany `docs/README.md`, `shadow-slave.md`) — nie należą do przedmiotu review i nie były
  zmieniane.
- **authority:** `docs/plans/local-automation/spec.md` (R01–R30), plany `01-watch-mode.md`,
  `02-search-and-download.md`, `03-subscriptions.md`, `04-smart-search.md` (warunki końcowe i wyniki
  wykonania), `AGENTS.md` roota oraz obszarów `anishift/`, `cli/`, `application/`,
  `services/torrents/`, `services/catalog/`, `platform/`, skille `review` i `simple`, wypowiedź
  właściciela zacytowana w zleceniu (lokalnie, prosto, przewidywalnie, domyślnie, łatwo).
- **ryzyka do wykrycia:** ciche no-opy w subskrypcjach, błędne czytanie nazw wydań, ślepe zaułki
  i mylące teksty w ekranie Anime, tracebacki na granicy CLI, wyścigi wątku sieciowego, kontrakt
  `subscriptions.json`, semantyka kodów wyjścia, zgodność README z kodem, zbędna złożoność.
- **poza review:** rdzeń Auto (planner, scheduler, handlery), tłumaczenie i TTS, ekran Ustawień,
  maskotka, plany 05+, cudza praca w drzewie roboczym, rzeczywisty odbiór przez człowieka
  (W08, A08, S06, M09) — pozostaje niewykonany.

## Werdykt

**Status:** FAIL (dla zakresu „gotowe do odbioru właściciela")

**Najważniejszy powód:** dwie z trzech obiecanych funkcji mają udowodnione ciche awarie na ścieżkach,
których użytkownik nie zobaczy: subskrypcja może na stałe nic nie pobierać, nie zgłaszając problemu
(P1), a licznik `next_episode` trwale przeskakuje odcinek po numerze ułamkowym lub po luce (P2).
Do tego parser nazw gubi numer odcinka dla realnego wzorca nazw (P3) i pokazuje paczkę sezonu jako
„odc. 1" (P4).

Happy path działa i jest potwierdzony na żywo (e2e Solo Leveling odc. 25 w planie 03, sondy M08
w planie 04, dziś: `doctor` zielony, `watch` running, `qbit status` reachable). To nie jest werdykt
o niedziałającym produkcie — to werdykt o czterech konkretnych, naprawialnych defektach w miejscach,
w których błąd jest niewidoczny dla właściciela. Po naprawie P1–P6 zakres nadaje się do odbioru.

## Findings

### Krytyczne

Brak. Żaden ze znalezionych defektów nie niszczy danych, nie rusza źródeł ani nie otwiera luki
bezpieczeństwa. Ochrona źródeł (R16) i granice sekretów (R26) w sprawdzonym zakresie trzymają się:
hasło Web UI nie trafia do logów, `add_torrent` nie przenosi ani nie kasuje plików, a `watch`
nie zmienia nazw plików użytkownika.

### Poważne

#### P1. Subskrypcja cicho przestaje pobierać, gdy zapis serii wybranego wydania różni się od etykiety grupy

- **miejsce / scenariusz:** `application/subscriptions.py:196` (`series = choice.name.series`) kontra
  `_matches` (`subscriptions.py:314-315`) i `catalog_releases` (`acquisition.py:280-281`).
  Klucz grupy powstaje z `_normalize(series)` (bez interpunkcji), ale etykietą grupy zostaje
  **pierwszy napotkany zapis** (`labels.setdefault`). `subscribe()` zapisuje zapis **wybranego
  wydania**, a `check()` porównuje go dosłownie (`casefold`) z etykietą grupy z **nowego** wyszukania.
- **dowód:** DIRECT, sonda na prawdziwych klasach (bez sieci):
  dwa wydania SubsPlease, „Mushoku Tensei: Jobless Reincarnation - 10" i
  „Mushoku Tensei Jobless Reincarnation - 11" → jedna grupa o etykiecie z dwukropkiem;
  `subscribe` na odc. 11 zapisuje serię bez dwukropka; `check` → `downloaded: 0`, `problem: -`,
  `next_episode` bez zmian. Wynik powtarzalny.
- **wpływ:** łamie R09. Użytkownik widzi „Obserwuję [SubsPlease] … od odc. 11 · pobrano 0 ·
  sprawdzam co godzinę" i co godzinę nic się nie dzieje — bez błędu w logu, bez problemu w
  `subs check`. Ten sam mechanizm może **zabić działającą** subskrypcję później: wystarczy, że
  w kolejnym feedzie pierwszy trafiony wpis grupy ma inny zapis serii, a etykieta się zmieni.
- **minimalna reakcja:** porównywać znormalizowaną postać serii (`_normalize`/`title_forms`),
  a nie surowy zapis — po obu stronach (`subscribe` zapisuje `_normalize`, `_matches` porównuje
  `_normalize`). Test: dwa zapisy tej samej serii w jednej grupie, subskrypcja z drugiego zapisu
  pobiera odcinek.
- **przyczyna:** DESIGN FLAW (dwa różne źródła prawdy dla „nazwy serii": etykieta grupy i nazwa
  pojedynczego wydania).

#### P2. `next_episode = max(pobrane) + 1` trwale przeskakuje odcinek po numerze ułamkowym i po każdej luce

- **miejsce / scenariusz:** `application/subscriptions.py:261-271` (`_advance`).
- **dowód:** DIRECT, sonda: subskrypcja od odc. 7; w feedzie 7 i 7.5 → pobrane 2,
  `next_episode = 8.5`; w kolejnym sprawdzeniu dostępne 8 i 9 → pobrany **tylko 9**,
  `next_episode = 10`. Odcinek 8 nie zostanie pobrany nigdy (8 < 8.5).
- **wpływ:** łamie R19 („7.5 … nie znika przez uproszczony licznik last_episode") i R09.
  Ten sam błąd zjada każdą lukę: jeśli w jednym feedzie widać 26 i 28, a 27 pojawi się później,
  27 jest stracony. Brak jakiegokolwiek komunikatu.
- **minimalna reakcja:** przesuwać `next_episode` do **pierwszego niepobranego** numeru
  (`min` z brakujących), a nie za maksimum; ułamkowe numery trzymać wyłącznie w `taken`.
  Test: 7 + 7.5 → następny 8; luka 26/28 → następny 27.
- **przyczyna:** IMPLEMENTATION BUG (uproszczony licznik zamiast zbioru pobranych).

#### P3. Nazwa z drugim separatorem `" - "` gubi numer odcinka

- **miejsce / scenariusz:** `services/torrents/names.py:230-240` (`_split_series` szuka
  **pierwszego** `" - "`), więc reszta tytułu trafia do „części odcinkowej", a `_EPISODE_RE`
  wymaga cyfry na jej początku.
- **dowód:** DIRECT, `parse_release_name`:
  `[Erai-raws] Shingeki no Kyojin - The Final Season - 05 [1080p]` → `episode=None`;
  `[Erai-raws] Mushoku Tensei III - Isekai Ittara Honki Dasu - 10 [1080p]` → `episode=None`;
  `[SubsPlease] Kusuriya no Hitorigoto - Season 2 - 05 (1080p)` → `episode=None`.
  W ekranie Anime taki wiersz renderuje się jako `wydanie  1080p  100 seedów  1.4 GiB`.
- **wpływ:** wydanie bez numeru nie da się zaznaczyć przez `A`/`Z`, nie da się obserwować (`O`
  → „Obserwuj działa tylko na numerowanym odcinku"), wypada z filtra odcinków (liczone jako
  „poza filtrem") i nie liczy się w `_group_queries`, więc grupa nie dostaje nawet doprecyzowania.
  Dotyczy grup wprost wymienionych w planie 04 (Erai-raws) i popularnego wzorca „… - The Final
  Season - NN". Łamie M11 i R19.
- **minimalna reakcja:** wybierać **ostatni** separator, po którym część odcinkowa zaczyna się
  cyfrą (fallback do pierwszego), zamiast bezwarunkowo pierwszego. Testy z trzema powyższymi nazwami.
- **przyczyna:** IMPLEMENTATION BUG.

#### P4. Paczka zapisana jako `- 01-12` / `- 01~12` jest czytana jako odcinek 1

- **miejsce / scenariusz:** `names.py:74-78` — `_BATCH_RANGE_RE` wymaga **nawiasów**
  (`\(\s*\d+-\d+\s*\)`), a `~` nie jest rozpoznawany w ogóle; `_EPISODE_RE` łapie wtedy `01`.
- **dowód:** DIRECT: `[Group] Show - 01-12 (1080p)` → `episode=1, batch=False, is_pack=False`;
  to samo dla `- 01~12`. W wynikach wiersz brzmi `odc. 1  1080p  100 seedów  1.4 GiB`.
- **wpływ:** łamie R19 („wspólny plik … ma poprawne i widoczne mapowanie") i zaskakuje: Enter na
  „odc. 1" ściąga kilkanaście GB całego sezonu; w subskrypcji paczka przejdzie filtr `is_pack`
  i zostanie potraktowana jak odcinek 1, przesuwając `next_episode`. Rozmiar w wierszu jest jedyną
  poszlaką.
- **minimalna reakcja:** rozszerzyć wykrywanie paczki o zakres bez nawiasów (`\d+\s*[-~]\s*\d+`
  bezpośrednio po separatorze) — wtedy wiersz pokaże „paczka" i wypadnie z filtra odcinków.
  Test na obu zapisach.
- **przyczyna:** IMPLEMENTATION BUG.

#### P5. Pusty ekran wyników po filtrze odcinków podaje złą przyczynę i nie daje `F`

- **miejsce / scenariusz:** `cli/interactive/anime.py:_render_empty` oraz `_handle_results`
  (gałąź `if not self._choices:` obsługuje wyłącznie `enter`).
- **dowód:** DIRECT, sonda kontrolera: hasło „frieren 99", katalog `groups=(), hidden=0,
  filtered=17` renderuje:
  `Brak wydań w 1080p+ dla tego tytułu` + `ukryte poniżej 1080p: 0 · Enter wróć`;
  klawisze `F`, `A`, `Space` nic nie robią (ekran się nie zmienia).
- **wpływ:** komunikat kłamie (nie chodzi o jakość), licznik `0` zaprzecza komunikatowi, liczba
  odrzuconych przez filtr (17) nie jest pokazana, a jedyne wyjście z sytuacji reklamowane w README
  i w stopce wyników (`F pokaż wszystkie`) jest w tym stanie nieosiągalne. To dokładnie ten
  scenariusz, który trafi pierwszego użytkownika: „solo leveling 1", gdy grupa nie ma odc. 1
  w 75 najnowszych trafieniach.
- **minimalna reakcja:** w stanie pustym rozróżnić przyczynę (`filtered > 0` → „Brak odc. X;
  F pokaż wszystkie") i obsłużyć `F` (oraz `Esc`) tak jak na liście wyników.
- **przyczyna:** IMPLEMENTATION BUG (stan pusty pominięty w tablicy klawiszy i w tekstach).

#### P6. Komendy techniczne sypią tracebackiem zamiast zdania z podpowiedzią

- **miejsce / scenariusz:** `cli/main.py` — `subs list|check|remove` wołają `SubscriptionService`
  bez łapania `AniShiftError`; `qbit setup` woła `setup_client()` bez łapania błędu klienta.
- **dowód:** DIRECT, `CliRunner` z podstawionym `production_service`:
  uszkodzony `subscriptions.json` → `subs list`, `subs check`, `subs remove ID` kończą się
  nieprzechwyconym `ConfigError: Subscriptions file is invalid`, stdout pusty;
  osiągalny Web UI, który odrzuca `setPreferences` → `qbit setup` kończy się nieprzechwyconym
  `TorrentClientError: qBittorrent rejected the request`, stdout pusty.
  W prawdziwym procesie `main()` loguje to jako „terminated unexpectedly" i wypisuje traceback.
- **wpływ:** łamie regułę `cli/AGENTS.md` („odmowa to zdanie + hint, nigdy traceback"; „cały output
  nieinteraktywny przechodzi przez `_safe()`") i S01 planu 03. Magazyn buduje gotową podpowiedź
  („Fix or delete config/subscriptions.json"), która nigdy nie dociera do użytkownika — a to jedyna
  możliwa naprawa.
- **minimalna reakcja:** owinąć te cztery wywołania w istniejące `_refuse_command(problem)`.
  Test CLI na uszkodzonym pliku i na odrzuconym `setPreferences`.
- **przyczyna:** IMPLEMENTATION BUG (pominięta wspólna ścieżka odmowy).

#### P7. `qbit setup` melduje sukces, gdy niczego nie zapisał

- **miejsce / scenariusz:** `platform/qbittorrent_config.py:enable_web_ui` dopisuje wyłącznie
  **brakujące** klucze (świadoma decyzja, opisana w `platform/AGENTS.md`), ale `cli/main.py:_prepare_web_ui`
  drukuje `_QBIT_WEB_UI_READY` niezależnie od `WebUiSetup.path_written`.
- **dowód:** DIRECT (lektura kodu): gdy w `[Preferences]` istnieje już `WebUI\Enabled=false`
  (typowe po jednorazowym włączeniu i wyłączeniu Web UI w opcjach), `missing` jest puste,
  funkcja zwraca `path_written=False`, a CLI mówi „Web UI enabled in the qBittorrent settings.
  Start qBittorrent and run `anishift qbit setup` again."
- **wpływ:** użytkownik wpada w pętlę „uruchom qBittorrent i powtórz", która nigdy się nie kończy,
  bez informacji, co zmienić ręcznie. Łamie M16 w części „wygodne wejście w wymaganie qBittorrenta".
- **minimalna reakcja:** rozróżnić w komunikacie `path_written=True/False`; przy `False` wymienić
  klucze, które już istnieją, i poprosić o ręczne włączenie Web UI w opcjach.
- **przyczyna:** INTEGRATION BUG (kontrakt `WebUiSetup.path_written` istnieje, ale nikt go nie czyta).

### Mniejsze

#### N1. `S` (zmiana kolejności) gubi zatapianie grup innego sezonu — dwa różne `_group_order`

- miejsce: `application/acquisition.py:_group_order` (`priority, foreign, missing, weight, …`)
  kontra `cli/interactive/anime.py:_group_order` (`priority, weight, …`).
- dowód: DIRECT, sonda: przy wybranym sezonie 2 grupa mająca wyłącznie wydania sezonu 1
  („sezon?", 900 seedów) stoi w katalogu fasady na końcu, a po `S` — w obu kierunkach — wskakuje
  na górę listy; powrót `S` nie przywraca stanu wyjściowego.
- wpływ: cofa świadomą poprawkę `945f9ff` w jednym naciśnięciu klawisza; wprowadza w błąd co do
  tego, które wydania należą do wybranego sezonu. Ta sama duplikacja powoduje, że po fallbacku
  AniList (`search()` sortuje po seedach, a `self._order` mówi `NEWEST`) **pierwsze** `S` nie
  zmienia niczego poza podpowiedzią.
- minimalna reakcja: jedno źródło reguły — wyeksponować porządek z fasady i wołać go z ekranu;
  po fallbacku ustawiać `_order` na faktyczny porządek katalogu.
- przyczyna: DESIGN FLAW (duplikacja wiedzy).

#### N2. Licznik „ukryte poniżej 1080p" liczy też dubbing i nieznany język

- miejsce: `acquisition.py:_is_hidden` (trzy przyczyny → jeden licznik) i `anime.py:_hidden_label`.
- dowód: DIRECT (lektura): `hidden` rośnie dla `resolution < 1080`, `dubbed` oraz
  `subtitle_language is None`; stopka nazywa całość „ukryte poniżej 1080p".
- wpływ: mylące liczby (README obiecuje ukrywanie dubbingu i nieznanego języka — użytkownik nie ma
  jak tego zobaczyć). Przy okazji: w kategorii `1_3` bez rozpoznanego znacznika ukrywane są też
  wydania z napisami PL, czyli dokładnie te, które pominęłyby tłumaczenie (M14).
- minimalna reakcja: rozbić licznik na dwa („ukryte poniżej 1080p", „ukryte: dubbing/nieznany
  język") albo przemianować etykietę na „ukryte: N".
- przyczyna: IMPLEMENTATION BUG (etykieta niezgodna z semantyką pola).

#### N3. Angielskie komunikaty błędów na polskim ekranie Anime

- miejsce: `services/torrents/nyaa.py:_SOURCE_TEXTS`, `qbittorrent.py:_UNAVAILABLE_SUGGESTION`
  i pokrewne, `catalog/anilist.py:_CATALOG_MESSAGES`, `ValueError` z `subscribe`.
- dowód: DIRECT (lektura): `anime.py:_render_problem` renderuje `str(problem)` i
  `problem.context.suggestion` — np. „Nyaa could not be reached" / „Check the connection and try
  again" — w ekranie, którego reszta jest po polsku.
- wpływ: niespójność językowa dokładnie w chwili, w której użytkownik potrzebuje zrozumieć,
  co zrobić. Nie łamie reguły „kod po angielsku" — łamie spójność UI.
- minimalna reakcja: mapa `ErrorCode → polskie zdanie + podpowiedź` w warstwie UI (kody już są
  stabilne), fallback na tekst domenowy.
- przyczyna: DESIGN FLAW (brak warstwy prezentacji błędów).

#### N4. `anishift watch` nie wypisuje nic — także gdy odmawia startu

- miejsce: `cli/main.py:_watch` + `cli/watch.py:run_daemon` (`logger.warning` przy zajętej
  blokadzie), sink konsolowy loggera wyłączony w `main()`.
- dowód: DIRECT (lektura): druga instancja kończy się kodem 1 bez żadnego wyjścia; normalna praca
  w terminalu też nie wypisuje ani jednej linii.
- wpływ: plan 01 w „Edge cases" obiecuje „komunikat, kod 1"; README reklamuje `anishift watch`
  jako podgląd w terminalu, a terminal wygląda na zawieszony.
- minimalna reakcja: `typer.echo` przy odmowie (jedno zdanie + `anishift watch status`) i jedna
  linia startowa dla trybu terminalowego.
- przyczyna: IMPLEMENTATION BUG.

#### N5. Wklejenie tytułu w polu wyszukiwania jest ignorowane

- miejsce: `anime.py:_handle_query` obsługuje `text:`, `space`, `backspace`; klawisz `paste:`
  z `prompts.py:344` nie ma tam gałęzi.
- dowód: DIRECT (lektura); `interactive/settings.py` obsługuje `paste:` — ekrany zachowują się
  różnie.
- wpływ: wklejony tytuł znika bez śladu; użytkownik przepisuje ręcznie.
- minimalna reakcja: doklejać `key.removeprefix("paste:")` po odfiltrowaniu znaków sterujących.
- przyczyna: IMPLEMENTATION BUG.

#### N6. Jedno Enter potrafi wysłać 22 żądania do nyaa; plan zakładał 7 zapytań

- miejsce: `acquisition.py:_search_queries`/`_episode_queries` (limit `MAX_QUERIES = 12` liczy
  **zapytania**) kontra `nyaa.py:search_releases` (każde zapytanie = 2 GET-y: kategorie `1_2` i `1_3`).
- dowód: DIRECT, sonda: `search_title(kandydat sezonu 2, zakres 4-6)` → 11 zapytań → 22 GET-y,
  sekwencyjnie, każdy z limitem 20 s. Impact scan planu 04 mówi „do 7 zapytań ≈ 2–3 s".
- wpływ: ryzyko limitowania/blokady po stronie nyaa (R23, R24) i długie „Szukam wydań…" bez
  informacji o postępie; przy odmowie jednej kategorii całe wyszukiwanie pada.
- minimalna reakcja: liczyć budżet w żądaniach HTTP, nie w zapytaniach (albo pytać o konkretny
  odcinek tylko w kategorii `1_2`).
- przyczyna: DESIGN FLAW (jednostka budżetu rozjechała się z jednostką kosztu po M10).

#### N7. Cicha degradacja numeracji sezonu, gdy AniList odpowie na wyszukanie, ale nie na łańcuch prequeli

- miejsce: `anime.py:_search_title` (`except … : context = None`) — bez notki w stopce.
- dowód: DIRECT (lektura): wyniki są wtedy numerowane „jak w nazwie", znikają odczyty
  `odc. 1 (13)` i znaczniki „sezon?", a `O` zapisze subskrypcję z `season_index=1, episode_offset=0`,
  czyli numer absolutny jako numer sezonu.
- wpływ: te same wyniki oznaczają dwie różne rzeczy w zależności od niewidocznego stanu sieci;
  subskrypcja utrwala tę różnicę.
- minimalna reakcja: notka w stopce („numeracja sezonu niedostępna") — pole `_fallback` już istnieje.
- przyczyna: IMPLEMENTATION BUG.

#### N8. `doctor` czyta `Settings()` bez `_env_file`, więc `ANISHIFT_QBITTORRENT_URL` z `.env` bywa pomijany

- miejsce: `setup/doctor.py:150,196` (`Settings()`), kontra `bootstrap.py:43`
  (`Settings(_env_file=env_path())`); `env_file=".env"` jest względne wobec **cwd**.
- dowód: DIRECT (lektura); wiersz `torrent_client` sonduje wtedy domyślne `127.0.0.1:8080`,
  a aplikacja gada z innym adresem.
- wpływ: „Web UI answers" może dotyczyć innego portu niż ten, którego używa pobieranie. Wzorzec
  jest starszy niż te plany (dotyczy też `api_keys`), ale nowy wiersz go powiela.
- minimalna reakcja: `Settings(_env_file=env_path())` w `run_doctor`.
- przyczyna: OUT OF SCOPE DEBT rozszerzony o nowy wiersz.

#### N9. Brama `ruff check anishift/ tests/` jest czerwona na sprawdzanym HEAD

- miejsce: `tests/workspace/test_temp_lifecycle.py:92` — `PLW0108`.
- dowód: DIRECT, `uv run --no-active ruff check anishift/ tests/ --exclude tests/integration`
  → `Found 1 error`. Plik pochodzi z `a9f55f5` (2026-08-13, 234 commity przed HEAD), ruff 0.15.21.
  Bez `--exclude` błędów jest 20, ale pozostałe 19 pochodzi z cudzych, nieśledzonych plików
  `tests/integration/` i nie należy do przedmiotu review.
- wpływ: plany 01–04 raportują „ruff czyste"; dziś każdy commit w tym repo wchodzi na czerwonej
  bramie (dryf wersji ruffa, nie regresja tych planów).
- minimalna reakcja: osobna, jednoliniowa poprawka poza tym zakresem.
- przyczyna: ENVIRONMENT ISSUE / OUT OF SCOPE DEBT.

#### N10. README rozmija się z ekranem w dwóch miejscach

- miejsce: README „Quick start" wymienia cztery pozycje Home (Auto, Manual, Settings, Exit) —
  brakuje **Anime**, choć plan 02 A07 i `cli/AGENTS.md` mówią o pięciu; README
  „Searching and downloading" obiecuje „newest release first", co nie jest prawdą dla ścieżki
  fallback (bez AniList `search()` sortuje po seedach).
- dowód: DIRECT (lektura README i `app.py:_HOME_CHOICES`, `acquisition.py:catalog_releases`
  domyślne `order=SEEDERS`).
- wpływ: pierwszy czytelnik nie wie, że Anime jest w menu; drugi opis myli przy awarii AniList.
- minimalna reakcja: dopisać pozycję Anime; zaznaczyć, że fallback sortuje po seedach.
- przyczyna: KNOWLEDGE GAP w dokumencie.

### Sugestie

- **S1. `Esc` z wyników wraca do hasła, nie do listy tytułów.** Po wybraniu sezonu i obejrzeniu
  wyników jedyny powrót to `QUERY`; ponowne wejście kosztuje kolejne zapytanie do AniList.
  Powrót do `TITLES`, gdy kandydaci są w pamięci, byłby tańszy i mniej zaskakujący.
- **S2. `WatchLedger.rows()`, `WatchRow`, `_stems`, `_OUTCOME_ORDER` są w produkcji martwe** —
  używają ich wyłącznie testy (`tests/application/test_watch.py`). Plan 01 chciał ich „do statusu
  i logów". Albo pokazać nieudane partie w `watch status` (to jedyne dziś miejsce, gdzie użytkownik
  mógłby zobaczyć, że okno partii skończyło się kodem 3), albo usunąć wraz z testami implementacji.
  Nie zostawiać w połowie.
- **S3. Polskie etykiety w warstwach nie-UI:** `services/torrents/query.py`
  (`EPISODE_LABEL_PREFIX = "odc."`, `RANGE_DASH`) i `acquisition.py`
  (`_FALLBACK_DIRECTORY = "Nieznana seria"`). `services/catalog/AGENTS.md` wprost mówi, że
  tłumaczenie na polski należy do warstwy aplikacyjnej; tu prezentacja przeciekła w dół.
- **S4. `SubscriptionService.check` używa surowego `search(query)`** (jedno zapytanie, 75 najnowszych
  trafień), a nie mechanizmu z planu 04 (zapytania po numerze). Przy nadrabianiu po dłuższej
  przerwie starszy odcinek może nigdy nie wypłynąć — w połączeniu z P2 znika bezpowrotnie.
  Po naprawie P2 warto rozważyć zapytanie po numerze dla brakującego odcinka.
- **S5. Brak testu prowadzącego prawdziwe nazwy z nagranego feedu przez `catalog_releases`.**
  Testy `test_acquisition.py` budują `Release` ręcznie i ustawiają `subtitle_language` z palca,
  a `test_names.py` sprawdza sam parser — dlatego P3 i P4 przeszły przez obie bramki.
  (Nieśledzone `tests/integration/` w drzewie roboczym wygląda na próbę zamknięcia tej luki —
  nie było przedmiotem tego review.)

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
| --- | --- | --- |
| R01/R13 czuwanie lokalne + autostart | pass | `anishift watch status` → `running (pid 14136)`, `autostart status` → `enabled`, `doctor` wiersze `watch`/`autostart` OK |
| R02 jeden pipeline (bez drugiego silnika) | pass | `interactive/app.py:_prepare_run` → `prepare_auto_run(..., group_ids=self._batch)` → `execute_plan`; zero nowych handlerów |
| R05 tylko 1080p+ | pass | `_is_hidden` (`resolution is None or < 1080`), test `test_catalog_hides_low_and_unknown_quality_and_counts_them` |
| R06 grupy wydań | pass (zakres planów) | grupowanie po (seria, grupa); wybór „najlepszej grupy" i fallback świadomie odłożone do planu 05 |
| R08 pobieranie na żądanie | pass z zastrzeżeniem | ścieżka Space/Enter działa (e2e planu 03), ale P4 potrafi podać paczkę jako „odc. 1" |
| R09 subskrypcje | **fail** | P1 (ciche zero), P2 (przeskok odcinka) |
| R11 gotowość pojedynczego odcinka | pass | `WatchLedger` + `execute_plan` per grupa; e2e planu 03 |
| R12 watch folder / stabilność | pass | `is_stable` (sufiksy częściowe, `QUIET_S`, `r+b`), testy `test_watch.py` |
| R14 jedno widoczne okno | pass | `_watch_loop` trzyma jedno dziecko; `poll()` przed kolejnym skanem |
| R15 porządek plików | pass | `series_directory_name` + `candidate.folder_title()`; discovery rekurencyjne z pominięciem `temp/` |
| R16 ochrona źródeł | pass (w sprawdzonym zakresie) | brak przenoszenia/kasowania w `acquisition`/`watch`; `enable_web_ui` robi kopię `.anishift.bak` |
| R17 idempotencja | częściowo | `taken` + `queued_hashes` chronią przed dublem; `add_torrent` na 202 ufa `failure_count == 0` i nie sprawdza późniejszego niepowodzenia pobrania `.torrent` przez klienta |
| R19 odcinki dodatkowe (7.5, paczki, absolutne) | **fail** | P2 (7.5), P4 (paczka jako odc. 1), P3 (numer gubiony) |
| R23 odporność integracji | częściowo | osobne kody i zdania dla nyaa/AniList/klienta; brak throttlingu (N6), awaria jednej kategorii kładzie całe wyszukiwanie |
| R25 proste TUI | częściowo | klawisze nie uruchamiają nic ukrytego; P5 (ślepy stan pusty), N3 (język), N5 (paste) |
| R26 granice bezpieczeństwa | pass | hasło Web UI poza logami i `details`; `_safe()` na wyjściu; argv budowane lokalnie |
| R30 lista „Wymaga uwagi" | poza zakresem planów 01–04 | brak widocznego śladu nieudanej partii (S2) |
| W01–W07 (plan 01) | pass | testy `tests/application/test_watch.py`, `tests/cli/test_watch_daemon.py`, `test_interactive_batch.py` — 350 testów zakresu zielonych |
| A01–A07 (plan 02) | pass | `tests/services/torrents`, `tests/application/test_acquisition.py`, `anishift qbit status` na żywo |
| S01 (plan 03) | częściowo | magazyn rzuca `ConfigError` zgodnie z kontraktem, ale CLI go nie obsługuje → P6 |
| S02, S03 (plan 03) | częściowo | `subscribe` zgodne; `check` → P1, P2 |
| M01–M07, M10–M16 (plan 04) | w większości pass | wyjątki: M11 (P3), M16 (P7); `parse_query` zgodny z M01 (potwierdzone 22 hasłami) |
| W08 / A08 / S06 / M09 (odbiór człowieka) | pending | nie wykonano; wymaga właściciela |

## Regresje i integracja

- **Kompatybilność `subscriptions.json`:** potwierdzona. Realny plik właściciela
  (`config/subscriptions.json`, wpis `d1574b595ea5`) nie ma pól `directory`, `season_index`,
  `episode_offset`, `season_episodes` i wczytuje się bez migracji (`_OPTIONAL_ENTRY_KEYS`),
  `SCHEMA_VERSION` pozostaje `1`. `subs list` na żywo działa.
- **`taken` vs. wielkość liter:** `_advance` zapisuje `info_hash` surowo, a `queued_hashes()`
  porównuje `casefold`. Dla nyaa (hashe małymi literami) różnicy nie ma, ale to dwie konwencje
  dla jednego identyfikatora — warto ujednolicić przy naprawie P1/P2.
- **202 z qBittorrenta:** `_torrent_accepted` akceptuje 202 z `failure_count == 0`. Klient pobiera
  `.torrent` z nyaa **asynchronicznie**; późniejsze niepowodzenie tego pobrania jest dla AniShift
  niewidoczne, a subskrypcja zdąży zapisać `taken` i przesunąć `next_episode`. Nie udowodniłem
  wystąpienia (wymaga żywej awarii nyaa w oknie dodania), ale to realna ścieżka utraty odcinka;
  po naprawie P2 („pierwszy niepobrany") ryzyko samo maleje.
- **Wątek sieciowy ekranu Anime:** licznik `_generation` odrzuca spóźnione wyniki; `Esc` w BUSY
  wraca do QUERY, a `Ctrl+C` jest przechwytywany wcześniej w `app.py:_handle_key` i idzie do Home
  (gałęzie `"interrupt"` wewnątrz `AnimeController` są w praktyce martwe). Nie znalazłem wyścigu
  prowadzącego do złego stanu.
- **Cykl życia czuwania:** blokada jest uchwytowa (OS zwalnia ją po zabiciu procesu), `stop`
  jest czyszczony przy starcie, więc pozostawiona flaga nie zabija kolejnego demona. Wyjątek
  z `spawner` (np. `OSError` z `Popen`) **nie jest łapany** w `_watch_loop` — demon wtedy umiera;
  w praktyce `batch_command` ma fallback na `python -m`, więc nie udało mi się tego wywołać.
- **Godzinne sprawdzanie subskrypcji** nie działa w trakcie otwartego okna partii (pętla robi
  wtedy tylko `poll`). Dla partii trwających minuty to bez znaczenia; przy długiej kolejce
  sprawdzenie przesuwa się o czas trwania okna.
- **Test suite:** 350 testów zakresu (application/watch, acquisition, subscriptions, services
  torrents i catalog, cli watch_daemon, interactive anime i batch, platform) — wszystkie zielone.
  Żaden z nich nie pokrywa P1 ani P2; `test_check_ignores_other_groups_and_other_series` utrwala
  właśnie ten kontrakt dosłownego porównania serii, który jest przyczyną P1 — poprawka musi go
  przepisać, nie usunąć.

## Wykonane kontrole

```text
uv run --no-active anishift --help
  komendy: doctor, setup, run, watch, autostart, qbit, subs        exit 0

uv run --no-active anishift doctor
  python/uv/binaries/api_keys/workspace/console_encoding OK
  torrent_client: Web UI answers on 127.0.0.1:8080
  watch: running (pid 14136) | autostart: enabled                  exit 0

uv run --no-active anishift qbit status      -> reachable: yes (v5.2.3) / incomplete extension: on   exit 0
uv run --no-active anishift subs list        -> d1574b595ea5 [SubsPlease] Solo Leveling · next: 26   exit 0
uv run --no-active anishift watch status     -> running (pid 14136)
uv run --no-active anishift autostart status -> enabled

uv run --no-active pytest tests/application/{test_subscriptions,test_acquisition,test_watch}.py
  tests/services/torrents tests/services/catalog tests/cli/{test_watch_daemon,
  test_interactive_anime,test_interactive_batch}.py tests/platform -q
  350 passed                                                        exit 0

uv run --no-active ruff format --check anishift/ tests/   -> 482 files already formatted
uv run --no-active ruff check anishift/ tests/            -> 20 errors (19 z cudzych, nieśledzonych
                                                             tests/integration/; 1 realny: N9)

sonda parse_query (22 hasła)          -> M01 potwierdzone; „steins;gate 0" czyta 0 jako odcinek
sonda parse_release_name (29 nazw)    -> P3 i P4 (numer gubiony / paczka jako odc. 1)
sonda catalog_releases + _catalog_rows-> wiersze „wydanie" i „odc. 1" dla powyższych
sonda SubscriptionService (fake source/client, tmp store)
                                      -> P1: downloaded 0, problem pusty, next bez zmian
                                      -> P2: 7 + 7.5 => next 8.5, odcinek 8 pominięty na zawsze
sonda AnimeController (fake AppService)
                                      -> P5: „Brak wydań w 1080p+", „ukryte…: 0", filtered=17,
                                         klawisze F/A/Space bez efektu
sonda CliRunner + podstawiony production_service
                                      -> P6: ConfigError i TorrentClientError bez obsługi
sonda search_title (fake source)      -> N6: 11 zapytań = 22 GET-y dla „zakres 4-6", sezon 2
sonda _group_order (fasada vs UI)     -> N1: grupa „sezon?" wskakuje na górę po S
```

## Niewykonane lub nierozstrzygające kontrole

- Odbiór człowieka: W08 (plan 01), A08 (plan 02), S06 (plan 03), M09 (plan 04) — nadal `pending`.
- Wylogowanie/zalogowanie Windows z autostartem (R13) — nie wykonano w tej sesji (zabronione
  ruszanie `autostart`), stan potwierdzony wyłącznie przez `status`.
- Rzeczywiste pobranie i przejęcie pliku przez czuwanie — nie wykonano (zakaz pobierania);
  jedyny dowód to e2e opisane w planie 03 (REPORTED).
- Zachowanie `add_torrent` przy 202, gdy klient później nie zdoła pobrać `.torrent` — nie
  odtworzone (wymaga żywej awarii nyaa); ryzyko opisane analitycznie.
- Częstotliwość realnych nazw z drugim separatorem u konkretnych grup (P3) — sprawdzone na
  wzorcach nazw, nie na żywym feedzie nyaa; skala zjawiska to luka dowodowa, sam defekt — nie.
- `mypy` (obie platformy) i pełny `pytest` — nie uruchamiane; sprawdzony podzbiór 350 testów
  zakresu jest zielony, a `ruff check` na plikach spoza `tests/integration/` daje jeden błąd (N9).

## Wymagana ocena człowieka

```text
Uruchom: uv run --no-active anishift  →  Anime
Zrób:
  1. wpisz „solo leveling 1", wybierz sezon 1, zobacz wyniki;
  2. wpisz „solo leveling 99" (odcinek, którego nie ma) i spróbuj wrócić do pełnej listy;
  3. w wynikach naciśnij S dwa razy i porównaj kolejność grup z pierwotną;
  4. naciśnij O na odcinku serii, której grupa zapisuje tytuł niejednolicie
     (np. z dwukropkiem i bez), a po godzinie sprawdź `anishift subs check`.
Oczekiwany wynik:
  1. lista wydań 1080p+ z SubsPlease na górze;
  2. czytelna informacja, że to filtr odcinków, i działający F;
  3. ta sama kolejność po dwóch S;
  4. „pobrano N" > 0 albo wyraźny problem.
Zwróć uwagę na: czy ekran Tytuł nie jest jednym krokiem za dużo przy jednym oczywistym kandydacie
  (decyzja odłożona w planie 04), oraz czy komunikaty błędów po angielsku nie przeszkadzają.
Przekaż wynik jako: krótki opis + zrzut ekranu w tym pliku.
```

## Ograniczenia review

- Nie zmieniałem żadnego pliku pod `anishift/` ani `tests/`; wszystkie sondy działały na kopiach
  w katalogu tymczasowym i na wstrzykniętych atrapach.
- Nie wykonywałem `watch stop`, `autostart enable|disable`, `qbit setup`, `subs check|remove`,
  nie pobierałem torrentów i nie modyfikowałem `config/`, `workspace/` ani `%APPDATA%`
  (`config/subscriptions.json` był wyłącznie odczytany).
- Drzewo robocze w trakcie review zmieniał ktoś inny (nieśledzone `tests/integration/`,
  `tests/fixtures/`, `docs/plans/remote-automation/`, zmodyfikowany `docs/README.md`).
  Ocena dotyczy stanu z commita `4f7de67`; cudza praca nie była analizowana ani liczona
  jako dowód.
- Werdykt dotyczy sprawdzonego zakresu i zebranych dowodów, nie całego repozytorium.

## Zalecany następny krok

Kolejność napraw (od najtańszej do najdroższej względem ryzyka, jakie zdejmuje):

1. **P2** — `next_episode` do pierwszego niepobranego odcinka (kilkanaście linii + 2 testy);
   zdejmuje trwałą utratę odcinków.
2. **P1** — porównanie serii po `_normalize` w `subscribe` i `_matches` (+ test dwóch zapisów);
   zdejmuje ciche zero w subskrypcjach.
3. **P6** — cztery wywołania w `_refuse_command` (+ 2 testy CLI); zdejmuje tracebacki.
4. **P5** — rozróżnienie przyczyny pustego ekranu i obsługa `F` w tym stanie.
5. **P4** — zakres bez nawiasów jako paczka (regex + 2 testy).
6. **P3** — wybór ostatniego separatora z cyfrą (regex/`_split_series` + 3 testy z realnych nazw).
7. **P7** — komunikat `qbit setup` zależny od `path_written`.
8. Mniejsze N1–N7 i N10 jednym commitem porządkowym; N8 i N9 osobno, bo są starsze niż te plany.
9. Dopiero potem odbiór właściciela (W08, A08, S06, M09) — dziś próba na scenariuszu
   „obserwuj serię" ma udowodnioną szansę na cichy no-op.
