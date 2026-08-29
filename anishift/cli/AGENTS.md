# cli

Jedyna granica procesu: Typer entry point `anishift`. Bez subkomendy uruchamia Interactive CLI; techniczne subkomendy pozostają nieinteraktywne.

## Pliki

- `main.py` — Typer app, `main()` (console script), subkomendy `doctor`/`setup`/`run --preset`, bare = Interactive CLI
- `console.py` — jedyny właściciel rekonfiguracji stdout/stderr na UTF-8 + check dla doctora
- `run.py` — wspólny, UI-neutralny preflight Auto oraz wykonanie zaakceptowanego planu
- `interactive/` — lazy-loaded Home, jeden renderer Prompt Toolkit, maskotka, Settings, Manual i wspólny postęp

## Pułapki

- `main()` woła `configure_utf8_streams()` PRZED jakimkolwiek outputem, a dopiero
  potem konfiguruje logger; nie odwracaj tej kolejności. `main.py`
- `main()` konfiguruje publiczne `utils/logger` przez `setup_mode_from_env()` z
  wyłączonym sinkiem terminalowym i zawsze zamyka kolejkę przez
  `shutdown_logger()`. Nie dodawaj sinka konsolowego obok raportu; diagnostyka
  aplikacji trafia do `logs/anishift.log.jsonl`. `main.py`
- Gołe `anishift` otwiera Interactive CLI. Interactive Auto i `anishift run --preset`
  dzielą `prepare_auto_run()`, a `execute_auto_run()` deleguje do wspólnego
  `execute_plan()` używanego także przez Manual. Nie dubluj discovery, planowania
  ani wykonania. `main.py`, `run.py`, `interactive/app.py`
- `TerminalRenderer` jest jedynym ownerem aplikacji Prompt Toolkit, klawiszy i
  alternate screen przez całą sesję. Nie zastępuj go `console.screen()`:
  Rich pomija alternate screen na części konfiguracji `legacy_windows`. Home, Auto i
  wynik czyszczą ten sam output. `interactive/prompts.py`, `interactive/app.py`
- Auto usuwa menu, ale zachowuje markę oraz esencjonalną stopkę z cwd/version.
  Jeden `MultiProgressManager` renderuje postęp pod marką. Resize przebudowuje
  wyłącznie ten widok przez publiczne API; nie dodawaj viewportu, wrappera `Live`,
  ukrywania wierszy ani technicznych ekranów pośrednich.
  `interactive/app.py`, `interactive/progress.py`, `interactive/prompts.py`
- `run --preset` ma stabilny kontrakt kodów wyjścia: `0` sukces, `1` odmowa startu,
  `3` run niepełny/failed, `4` anulowany. `2` jest zarezerwowane dla błędów użycia
  Typera — nie używaj go. `main.py`
- `run --preset` odmawia PRZED wykonaniem, gdy workspace jest pusty, żadna grupa
  nie jest gotowa albo plan ma blokujący `PlanProblem`. Odmowa to zdanie + hint,
  nigdy traceback. `main.py`
- Cały output nieinteraktywny przechodzi przez `_safe()` → `sanitize_event_message`;
  nie echuj `str(exc)` ani ścieżek bezpośrednio. `main.py`
- `_QuietRunEvents` celowo gubi wszystkie eventy postępu — raport ma być
  parsowalny, bez przeplotu. Nie dodawaj tam renderowania. `main.py`
- `RichRunProgress` prealokuje jeden pasek na plik w naturalnej kolejności i odtwarza przejścia
  legacy `_PipelineProgressRows`: `Extracting` od razu ma pasek i procent,
  `Extracted`, `Translating`, `Translated` i `Synthesizing` reużywają ten sam
  wiersz, a spinner jest dozwolony wyłącznie dla faz audio. Techniczne taski nie
  otrzymują osobnych wierszy. Etykieta zachowuje konkretną nazwę źródła wraz z
  rozszerzeniem; procent ekstrakcji i TTS pochodzi wyłącznie z eventu backendu.
  `interactive/progress.py`
- Home ma dokładnie `Auto`, `Ręczny`, `Ustawienia`, `Wyjście`. Settings działa w tym
  samym rendererze, a mutacje `settings.json`, `presets.json` i `.env` przechodzą
  przez `AppService`. Manual przechowuje drafty wyłącznie lokalnie, rejestruje pliki
  zewnętrzne przez `AppService`, waliduje przez `plan_manual()` i przekazuje zaakceptowany
  plan do tej samej ścieżki wykonania oraz postępu co Auto.
  `interactive/app.py`, `interactive/settings.py`, `interactive/manual.py`, `run.py`
- `SettingsController.render()` korzysta wyłącznie z lokalnego, odświeżonego snapshotu;
  nie wykonuj w nim I/O ani wywołań sieciowych, bo renderer odświeża klatkę cyklicznie.
  Katalog modeli jest tylko do odczytu, a probe działa wyłącznie po jawnej akcji.
  `interactive/settings.py`
- Home ma slime 20×14, sześciowierszowy wordmark, cztery akcje, hint i esencjonalną
  stopkę z cwd/version. `MascotController` mapuje zaakceptowane eventy pracy na
  statyczne stany; nie ma własnego workera ani bezpośredniego zapisu do terminala.
  Asset PNG renderuje się jako półbloki, a błąd dekodowania lub zbyt mały terminal
  degraduje widok do ASCII albo braku maskotki. Resize otwartego promptu wywołuje
  czysty rerender; nie rozciągaj elementów wraz z terminalem.
  `interactive/home.py`, `interactive/mascot.py`, `interactive/prompts.py`
- `configure_utf8_streams()` musi znosić `None`, `StringIO` i strumienie bez
  `reconfigure`; jest idempotentne. `console.py`

## Konwencje

- Ciężkie importy odraczane lokalnie (`noqa: PLC0415`) — `bootstrap`,
  `anishift.application` i `anishift.cli.interactive` poza ścieżką importu Typera.
  Subkomendy techniczne (`doctor`, `setup`, `run --preset`) nie mogą ładować
  prompt_toolkit ani Interactive CLI; pilnują tego testy CLI. `main.py`
- Jest dokładnie jedna droga budowy fasady: `bootstrap.production_service()`.
  Entry point nie ma drugiej ścieżki konstrukcji. `main.py`
- Opcje CLI to uniksowe flagi (`--force`, `--preset`), nie gołe tokeny. `main.py`

## Testy

```bash
uv run pytest tests/cli -v
```
