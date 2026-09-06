---
kind: plan
status: accepted-in-progress
baseline: 167a181 (work/local-automation/05-polish)
branch: work/local-automation/06-efficiency
created: 2026-09-06
---

# Plan 06: Szybciej i oszczędniej — czuwanie, subskrypcje, klient, cache

## Cel

To samo zachowanie co dziś, ale: nowy odcinek dopływa w kilka minut od premiery zamiast do godziny; nyaa i AniList
dostają ułamek dzisiejszych zapytań; okno partii i czuwanie startują w ułamku sekundy zamiast 11 s; qBittorrent
i procesor nie pracują, gdy nie ma czego robić. Zero nowych zależności, zero zmian w formacie produktów.

## Stan wyjściowy (pomiary 2026-09-06, biblioteka 83 grupy, 25 subskrypcji)

| Co | Dziś | Źródło |
| --- | --- | --- |
| Inspekcja biblioteki przy starcie procesu | 11,2 s (cache tylko w pamięci procesu); kolejny skan 14 ms | pomiar `discover()` |
| Start okna partii do „Automatic run planned” | ~6 s | log 21:51:30 → 21:51:36 |
| Sprawdzanie subskrypcji | co godzinę wszystkie: 52 zapytania nyaa = 104 GET-y/h, ~2 500/dobę; odcinek czeka do 60 min | log daemona |
| Czuwanie w spoczynku | skan co 5 s, 0,5 % rdzenia, 68 MB | pomiar procesu |
| qBittorrent | musi działać stale; 100 MB; po restarcie Windows zależy od jego własnego autostartu | obserwacja |
| Odcinek w oknie partii | ~110 s: bootstrap 6 s, ekstrakcja 3 s, LLM ~65 s (mediana wywołania 16 s, maks. 246 s), lektor ~20 s, odliczanie 10 s | log |
| AniList | każde Enter w Anime = zapytanie + łańcuch prequeli; przy awarii (403 dziś) brak tytułów | sondy |
| Ekran Anime | do 16 GET-ów nyaa na wybór tytułu; `F`/`S`/powrót powtarzają te same zapytania | plan 04 |
| Logi | loguru z rotacją; `errors.log.jsonl` 1 MB historycznych błędów TTS/LLM | odczyt |

## Rezultat użytkownika

- Odcinek obserwowanej serii jest w qBittorrencie do 10 min po tym, jak grupa go opublikuje; poza oknem premiery
  czuwanie nie pyta nyaa wcale. `subs list` pokazuje, kiedy spodziewa się następnego odcinka.
- Okno partii zaczyna pracę po < 1 s (inspekcja z dysku), czuwanie po restarcie też.
- qBittorrent uruchamia się sam, gdy jest coś do pobrania, i wyłącza, gdy AniShift skończył, a Ty nie masz w nim
  własnych aktywnych torrentów; ręcznie otwartego nie rusza.
- Czuwanie w spoczynku skanuje rzadziej (30 s po 5 min ciszy, 5 s po zmianie); zużycie spada do ~0,1 %.
- Ekran Anime: powtórne wejście w ten sam tytuł jest natychmiastowe (cache AniList i nyaa), AniList w awarii nie
  odbiera znanych tytułów.
- Nic nie zmienia się w plikach, presetach, kluczach ani w tym, co widzisz w oknie partii.

## Warunki końcowe

- [ ] E01 **Harmonogram premier.** `Subscription` dostaje `expected_at: str | None` i `cadence_days: int | None`
      wyliczane z dat publikacji odcinków grupy w feedzie (mediana odstępu między kolejnymi numerami, ostatnia
      publikacja + odstęp); `check` odświeża je przy każdym trafieniu. Czuwanie sprawdza subskrypcję tylko w oknie
      `[expected − 10 min, expected + 6 h]` co 10 min, poza oknem raz na 24 h (asekuracja); bez historii → co godzinę
      jak dziś. `subs list` pokazuje `next: 12 · ~pon 17:00`. Test: feed z 3 odcinkami co 7 dni → expected = ostatni + 7 d;
      poza oknem check nie woła nyaa; w oknie woła co 10 min; po trafieniu okno przesuwa się o odstęp.
- [ ] E02 **Serie zakończone.** Gdy subskrypcja ma `season_episodes` i `next_episode > season_episodes`, albo kandydat
      AniList był `FINISHED` i nyaa nie ma nowego numeru przez 30 dni, wpis dostaje `dormant: true`: sprawdzany raz na
      7 dni, `subs list` pokazuje `zakończone`; `subs check` wymuszone sprawdza mimo to. Test na obu regułach.
- [ ] E03 **Cache feedów nyaa.** `search_releases` dostaje cache w pamięci procesu z TTL 120 s kluczowany
      `(query, category)`; trafienie nie robi GET-a. `F`/`S`/`Esc→Enter` w Anime nie powtarzają zapytań; zapytanie
      doganiające subskrypcji nie odpytuje dwa razy tego samego. Test: dwa wyszukania w TTL = 2 GET-y, po TTL = 4.
- [ ] E04 **Cache AniList na dysku.** `config/cache/anilist.json`: wyniki `search` (TTL 7 dni) i łańcuchy prequeli
      (TTL 30 dni); trafienie nie woła sieci; przy błędzie sieci przeterminowany wpis jest używany z notką
      (`AniList nie odpowiada, dane z pamięci`). Bez sekretów; plik ≤ 1 MB z przycinaniem najstarszych. Test round-trip,
      TTL, fallback.
- [ ] E05 **Inspekcja z dysku.** Wynik inspekcji grupy (katalog mediów, klasyfikacja napisów, długość audio) jest
      zapisywany w `config/cache/inspection.json` z kluczem `(ścieżka względna, rozmiar, mtime)` każdego pliku grupy;
      `discover()` w nowym procesie używa wpisu bez sond, gdy klucz się zgadza. Pomiar: pierwszy `discover()` po
      restarcie ≤ 0,5 s dla dzisiejszej biblioteki (dziś 11,2 s). Zły/nieczytelny plik cache = ignorowany, nie błąd.
- [ ] E06 **qBittorrent na żądanie.** `AcquisitionService.ensure_client()` uruchamia `qbittorrent.exe` (ścieżka z
      `installed_executable()`, `CREATE_NO_WINDOW` nie dotyczy GUI: uruchamiany zminimalizowany do zasobnika przez
      własne ustawienie klienta) gdy Web UI nie odpowiada, i czeka do 20 s na odpowiedź; zapamiętuje, że to AniShift
      go uruchomił. `release_client()` wyłącza go (`/app/shutdown`) tylko gdy AniShift go uruchomił, wszystkie torrenty
      kategorii `AniShift` są ukończone i nie ma innych aktywnych torrentów. Czuwanie woła `ensure` przed pobraniem,
      `release` po zakończeniu partii bez pobrań w toku. Ustawienie `qbittorrent_manage_process: true/false` w
      `settings.json` (domyślnie true). Testy z fałszywym procesem i klientem.
- [ ] E07 **Adaptacyjny skan.** Czuwanie: 5 s przez 5 min od ostatniej zmiany biblioteki lub partii, potem 30 s;
      pojawienie się pliku wraca do 5 s. Zdarzenie `stop` nadal działa w ≤ 5 s (osobne sprawdzenie flagi).
      Test z zegarem.
- [ ] E08 **Krótsze okno partii.** Bootstrap okna korzysta z E05; odliczanie 10 s skraca się do 3 s, gdy czuwanie
      ma już kolejnych kandydatów (przekazuje `--next-waiting`), inaczej 10 s jak dziś. Test.
- [ ] E09 **Równoległość API.** Pomiar: partia 4 odcinków z `translation_concurrency` 1 vs 2 (na fałszywym LLM
      z opóźnieniem); jeśli skraca wall-time ≥ 30 %, domyślne ustawienie nowej instalacji = 2, a README i
      `doctor` mówią, jak podnieść; ustawienia właściciela bez zmian (jego decyzja).
- [ ] E10 **Dowód całości.** Bramki root; testy integracyjne z nagranych feedów zielone; smoke: restart czuwania
      i `discover` < 0,5 s; `subs list` z terminami; jedno pełne przejście: subskrypcja z oknem premiery w przeszłości
      → check w oknie → pobranie → partia; qBittorrent uruchomiony i wyłączony przez AniShift w logu.

## Nie-cel

Nowe zależności (watchdog itp.), zmiana formatu produktów i presetów, VPS, zmiana silników TTS/LLM, zmiana
ustawień właściciela bez jego decyzji (E09 tylko mierzy i zmienia domyślne nowej instalacji), panel/GUI.

## Authority i baseline

Właściciel 2026-09-06: „co godzinę to nieoptymalne, mamy dokładne daty premier”, „qBittorrent nie powinien działać
cały czas, ale nie może zamykać ręcznie otwartego”, „przyspiesz działanie, ma działać tak samo albo lepiej”, „znajdź
więcej scenariuszy”. Spec local-automation R09, R12, R17, R23, R24. Kod: `application/{subscriptions,acquisition,
service,inspection,discovery,watch}.py`, `cli/{watch,main}.py`, `services/torrents/nyaa.py`, `services/catalog/anilist.py`,
`platform/qbittorrent_config.py`, `config/user_settings.py`, `bootstrap.py`; testy odpowiednich modułów i
`tests/integration/`.

## Impact scan

- `subscriptions.json`: nowe opcjonalne pola `expected_at`, `cadence_days`, `dormant` (domyślne None/False, bez migracji).
- `settings.json`: nowe pole `qbittorrent_manage_process` (domyślnie true) w `UserSettings` z katalogiem pól
  (`field_catalog`) i testami kontraktu.
- Cache na dysku w `config/cache/` (gitignore `config/cache/`); brak sekretów; usunięcie katalogu jest bezpieczne.
- `_check_subscriptions` w czuwaniu zmienia rytm: nie „raz na CHECK_INTERVAL_S”, tylko „każdą subskrypcję według
  jej okna”; `SUBSCRIPTION_CHECK_INTERVAL_S` zostaje jako rytm awaryjny bez historii.
- Okno partii: nowa opcja `watch batch --next-waiting`; ledger bez zmian.
- Wyłączanie qBittorrenta: tylko własna instancja i tylko bez cudzych aktywnych torrentów; brak `qbittorrent.exe`
  → dzisiejsze zachowanie (komunikat, brak pobrania).

## Podział wykonania (trzy niezależne zakresy plików)

| Wykonawca | Warunki | Pliki |
| --- | --- | --- |
| A | E01, E02, E03, E07, E08 | `application/subscriptions.py`, `cli/watch.py`, `cli/main.py` (tylko `subs list` i `watch batch --next-waiting`), `cli/interactive/app.py` (odliczanie), `services/torrents/nyaa.py` (cache), `bootstrap.py` (NyaaSource), testy tych modułów, `tests/integration/` |
| B | E04, E05 | `services/catalog/anilist.py` (+ nowy `cache.py`), `application/{service,inspection,discovery}.py` (persistencja), `paths.py`/`config` dla `config/cache/`, `.gitignore`, testy |
| C | E06, E09 | `platform/qbittorrent_config.py` (start/shutdown), `application/acquisition.py` (`ensure_client`, `release_client`, `client_started_by_us`), `config/user_settings.py` + `field_catalog.py` (nowe pole), `cli/main.py` (tylko `qbit` i `doctor` wiersz), pomiar E09 w `scripts/tmp/`, README, testy |

Integracja: prowadzący (ja) wpina `ensure_client`/`release_client` w pętlę czuwania po raportach A i C, robi
bramki, smoke i przegląd diffu.

## Dowód

Unit per warunek (wyżej), integracja na nagranych feedach (E01/E03 przez `tests/integration`), pomiary E05 i E09
zapisane w sekcji „Wynik wykonania”, smoke E10 na żywo, przegląd całości przez prowadzącego przed PR.
