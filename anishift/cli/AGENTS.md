# cli

REPL prompt_toolkit, komendy `/`, panel `/settings`, banner. Typer entry point `anishift` (default = shell).

## Pliki

- `main.py` — Typer entry point, subkomendy `doctor`/`setup`, default = shell
- `shell.py` — REPL prompt_toolkit routujący linie do komend/pipeline
- `commands.py` — rejestr `/komend`, opcji, dispatch i walidacja
- `completer.py` — completer prompt_toolkit dla `/komend`
- `pipeline_ui.py` — render pipeline na Enter: prompty, progres, raport
- `settings_panel.py` — pełnoekranowy panel `/settings` sterowany strzałkami, auto-save
- `banner.py` — startowy banner ASCII + linia statusu

## Pułapki

- Pusta linia w REPL (nie `/`-komenda) uruchamia pipeline — jawnego triggera brak, samo Enter przetwarza workspace. `shell.py:61-69`
- Opcje `/komend` to gołe tokeny w stylu Claude-Code (`/setup force`), NIE uniksowe flagi; ten sam efekt w CLI Typer to jednak `--force`. `commands.py:125,162-165` vs `main.py:66-69`
- `dispatch` traktuje wszystkie tokeny po nazwie jako opcje przez `frozenset` — duplikaty i kolejność tracone; nieznana opcja tylko ostrzega i utrzymuje REPL. `commands.py:178-187`
- `main()` woła `logger.remove()` PRZED `app()` — loguru nic nie pisze dopóki ktoś jawnie nie doda handlera; cichy log to zaprojektowany stan wejścia. `main.py:82-87`
- `_ensure_binaries` sprawdza MKVToolNix tylko gdy w inputach jest `.mkv`, i musi wykonać się PRZED startem Rich Live (inaczej prompt instalatora zderzy się z Live). `pipeline_ui.py:54-67`
- W panelu `/settings` `Enter` NIE zatwierdza/wychodzi — działa jak `→` (cykluje wartość); wyjście to tylko `Esc`/`q`. `settings_panel.py:193-201`
- Każda zmiana w panelu jest natychmiast zapisywana na dysk (`save_user_settings` po każdym kroku) — brak anulowania. `settings_panel.py:184-196`
- Lista silników w panelu ukrywa `llm` zawsze i `deepl` bez klucza API; pusty wynik → fallback twardo na `("google",)`. `settings_panel.py:90-96`
- Manualny prompt stylów: Enter (pusto) zwraca `None` = akceptacja klasyfikatora, nie pusty zbiór. `pipeline_ui.py:149-161`

## Konwencje

- Completer aktywuje się wyłącznie po wiodącym `/`. `completer.py:31-40`
- `COMMANDS` jest jedynym źródłem prawdy — completer, `/help`, sugestie i walidacja z niego wynikają. `commands.py:1-7,84-88`
- Ciężkie importy odraczane lokalnie (`noqa: PLC0415`) — prompt_toolkit/loguru/bootstrap poza ścieżką importu do użycia. `main.py:49-51,84`
- Shell trzyma `.shell_history` obok `config/settings.json` (poza `workspace/`). `shell.py:25-33`
- Domyślna akcja Typera (bez subkomendy) odpala shell przez `invoke_without_command=True` + `no_args_is_help=False`. `main.py:20-25`
- Panel czerpie zakresy z `config.user_settings` i listę silników z `services.translation.engines.available_engine_ids`. `settings_panel.py:22-29`

## Uwaga

- TTS engine i głosy w panelu to statyczne placeholdery „do stage 6". `settings_panel.py:38-42`
