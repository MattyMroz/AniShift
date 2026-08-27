# cli

Jedyna granica procesu: Typer entry point `anishift`. Bez subkomendy uruchamia preset zapisany jako domyślny. Aplikacja nie ma interaktywnego UI.

## Pliki

- `main.py` — Typer app, `main()` (console script), subkomendy `doctor`/`setup`/`run --preset`, default = domyślny preset
- `console.py` — jedyny właściciel rekonfiguracji stdout/stderr na UTF-8 + check dla doctora

## Pułapki

- `main()` woła `configure_utf8_streams()` PRZED jakimkolwiek outputem, a dopiero
  potem konfiguruje logger; nie odwracaj tej kolejności. `main.py`
- `main()` konfiguruje publiczne `utils/logger` przez `setup_mode_from_env()` z
  wyłączonym sinkiem terminalowym i zawsze zamyka kolejkę przez
  `shutdown_logger()`. Nie dodawaj sinka konsolowego obok raportu; diagnostyka
  aplikacji trafia do `logs/anishift.log.jsonl`. `main.py`
- Gołe `anishift` i `anishift run --preset` dzielą jedno ciało `_run_preset()`;
  goła komenda tylko bierze ID z `service.default_preset_id()`. Nie dubluj tam
  planowania ani raportowania. `main.py`
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
- `configure_utf8_streams()` musi znosić `None`, `StringIO` i strumienie bez
  `reconfigure`; jest idempotentne. `console.py`

## Konwencje

- Ciężkie importy odraczane lokalnie (`noqa: PLC0415`) — `bootstrap` i
  `anishift.application` poza ścieżką importu Typera. Subkomendy techniczne
  (`doctor`, `setup`) nie mogą ładować żadnego toolkitu terminalowego; pilnuje
  tego `tests/cli/test_main.py`. `main.py`
- Jest dokładnie jedna droga budowy fasady: `bootstrap.production_service()`.
  Entry point nie ma drugiej ścieżki konstrukcji. `main.py`
- Opcje CLI to uniksowe flagi (`--force`, `--preset`), nie gołe tokeny. `main.py`

## Testy

```bash
uv run pytest tests/cli -v
```
