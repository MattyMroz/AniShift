---
kind: plan
status: implemented-e2e-verified
baseline: 4eb90cf (work/local-automation/01-watch)
branch: work/local-automation/01-watch
created: 2026-09-06
---

# Plan 03: Obserwuj — nowe odcinki serii pobierają się same

## Cel

W wynikach Anime klawisz **O** na odcinku zapisuje subskrypcję „ta seria, ta grupa, od tego odcinka”.
AniShift od razu pobiera dostępne odcinki od tego numeru, a proces czuwania co godzinę sprawdza nyaa i
dosyła nowe. Nie trzeba pamiętać o cotygodniowym wchodzeniu na stronę: raz „chcę to oglądać” wystarcza.

## Rezultat użytkownika

- Anime → wyniki → podświetl odcinek → `O`: „Obserwuję [SubsPlease] Neko to Ryuu od odc. 9 · pobrano 3 ·
  sprawdzam co godzinę”. Podświetlenie pierwszego odcinka = cały sezon; ostatniego = tylko nowe.
- Ta sama seria i grupa drugi raz = aktualizacja punktu startu, bez duplikatu.
- `anishift subs list` (id, grupa, seria, następny odcinek, ostatnie sprawdzenie), `anishift subs remove ID`,
  `anishift subs check` (jedno sprawdzenie teraz, z liczbą pobranych na subskrypcję).
- Proces czuwania sprawdza subskrypcje co 60 min między skanami; błąd sieci lub klienta to wpis w logu
  i następna próba za godzinę, nigdy przerwanie czuwania.

## Warunki końcowe

- [x] S01: `SubscriptionStore` zapisuje i czyta `config/subscriptions.json` atomowo; brak pliku = pusta lista;
      zepsuty plik = `ConfigError`, nie traceback.
- [x] S02: `subscribe(query, choice)` tworzy lub aktualizuje wpis (id z serii i grupy), `next_episode` = odcinek
      wyboru; paczka lub brak numeru → `ValueError`.
- [x] S03: `check(subscription)`: wyszukuje `query`, bierze grupy o tej samej serii i grupie (casefold), odcinki
      `>= next_episode`, bez paczek, bez już wziętych infoHash, jedna wersja na odcinek (najwyższa), pobiera je,
      przesuwa `next_episode` za najwyższy pobrany, zapisuje `taken` i `checked_at`; błąd = `CheckOutcome.problem`.
- [x] S04: czuwanie wywołuje `check_all` co `CHECK_INTERVAL_S` gdy nie ma okna partii; wynik w logu; wyjątki
      nie zabijają pętli.
- [x] S05: klawisz `O` w wynikach; `subs list|remove|check` w CLI; bramki root zielone.
- [ ] S06: właściciel: zasubskrybował serię, odcinki pojawiły się w `workspace/<Seria>/`, po godzinie nowy
      odcinek dopłynął sam.

## Nie-cel

Kalendarz emisji (AniList/LiveChart), inteligentny interwał, edycja subskrypcji w TUI, wybór grupy fallback,
pauza subskrypcji, paczki w subskrypcji, MAL, powiadomienia.

## Target design

```text
anishift/application/subscriptions.py   # NEW: Subscription, CheckOutcome, SubscriptionStore, SubscriptionService
anishift/application/service.py         # MODIFY: property subscriptions
anishift/application/__init__.py        # MODIFY: eksport
anishift/bootstrap.py                   # MODIFY: SubscriptionService(store=config/subscriptions.json, acquisition)
anishift/cli/watch.py                   # MODIFY: godzinne check_all w pętli
anishift/cli/main.py                    # MODIFY: grupa subs
anishift/cli/interactive/anime.py       # MODIFY: klawisz O, ekran DONE dla subskrypcji
tests/application/test_subscriptions.py, tests/cli/test_watch_daemon.py, test_main.py, test_interactive_anime.py
.gitignore                              # config/subscriptions.json
```

```text
SUBSCRIPTIONS_FILE_NAME = "subscriptions.json"; CHECK_INTERVAL_S = 3600.0; SCHEMA_VERSION = 1
Subscription(subscription_id, query, series, group, next_episode: Decimal, min_resolution: int,
             taken: frozenset[str], added_at: str, checked_at: str | None)
    subscription_id = sha256(f"{series.casefold()}|{group.casefold()}")[:12]
CheckOutcome(subscription, downloaded: int, problem: str = "")
SubscriptionStore(path).load() -> tuple[Subscription, ...]; .save(subscriptions) -> None
SubscriptionService(store, acquisition, clock=lambda: datetime.now(UTC))
    subscribe(query, choice) -> Subscription; list() -> tuple; remove(id) -> bool
    check(subscription) -> CheckOutcome; check_all() -> tuple[CheckOutcome, ...]
AppService.subscriptions -> SubscriptionService | None
CLI: subs list (0), subs remove ID (0 / 1 gdy brak), subs check (0; wiersz per subskrypcja: "[grupa] seria: pobrano N" lub "…: <problem>")
```

## Dowód

Unit: store (round-trip, brak pliku, zepsuty plik), subscribe (nowy, aktualizacja, paczka), check (filtr
odcinków, wersje, taken, przesunięcie next_episode, błąd), daemon (check po interwale, nie podczas okna,
błąd nie przerywa), CLI (list/remove/check), Anime (O → subscribe+check → DONE; O na paczce → nic; błąd →
PROBLEM). Human: S06.

## Wynik wykonania (2026-09-06)

Trzy commity: serwis subskrypcji z magazynem JSON (16 testów), wpięcie w fasadę, bootstrap, godzinne
sprawdzanie w pętli czuwania i komendy `subs` (testy daemona i CLI), klawisz `O` w ekranie Anime (26 testów
ekranu). Bramki: ruff, format, mypy (win32 i linux) czyste; pytest 3312 passed, 2 failed z nieśledzonego
`shadow-slave.md` właściciela. `anishift subs list` na żywo: „No followed series.”

Nie wykonano: S06 (odbiór właściciela z włączonym WebUI qBittorrenta).

## Przebieg e2e (2026-09-06)

Na polecenie właściciela („pobierz 1 odcinek Solo Leveling”) wykonano ścieżkę klawisza `O` przez fasadę:
`subscribe("Solo Leveling", SubsPlease odc. 25)` → `check` → qBittorrent pobrał 1,3 GiB do `workspace/Solo Leveling/`
w niecałą minutę → czuwanie po 10 s ciszy otworzyło okno partii → tłumaczenie 280 linii (LLM) i lektor `.eac3`
w 2,5 min → kod wyjścia 0. Produkty: `.pl.ass`, `.eac3` obok źródła.

Przebieg odsłonił dwa błędy, naprawione i pokryte testami:

- qBittorrent 5.2 (Web API 2.15) odpowiada na `torrents/add` kodem 202 z raportem JSON zamiast `Ok.`; klient
  uznawał udane dodanie za odmowę, a subskrypcja nie zapisywała pobrania. Klient akceptuje oba formaty.
- ponowne sprawdzenie dodawało ten sam torrent drugi raz; `check` pomija teraz hashe już obecne w kliencie
  (`AcquisitionService.queued_hashes`) i zapisuje je jako wzięte. Po naprawie `subs check` przesunął
  subskrypcję na odc. 26 bez drugiego pobrania.

S06 w części „nowy odcinek dopłynął sam po godzinie” pozostaje do obserwacji właściciela (odc. 26 wychodzi
w przyszłym tygodniu); mechanizm sprawdzania co godzinę potwierdził wpis `Subscriptions checked` w logu.
