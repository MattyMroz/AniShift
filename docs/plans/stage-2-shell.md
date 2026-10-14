# etap 2 — shell: banner, REPL, /komendy, /settings

> cel: serce wizji UX — terminalówka "między Claude Code a webem" działa jako pusta skorupa (komendy są, pipeline jeszcze nie).
> zależności: etap 1.
> DoD: wszystkie komendy (`/help /settings /auto /manual /doctor /exit`) działają, autocomplete inline działa, ustawienia przeżywają restart, w workspace nie powstaje żaden plik ustawień.

## pliki do stworzenia/zmiany

### `utils/cool_animation.py` (NOWY — kopia 1:1 z mm_avh)
- **odpowiedzialność:** animowany ASCII banner (istniejący kod usera).
- **zawartość:** kopia bez żadnych zmian — utils nietykalne.
- **skąd logika:** `mm_avh_working_space/utils/cool_animation.py`.

### `anishift/cli/shell.py` (NOWY)
- **odpowiedzialność:** REPL prompt_toolkit — pętla główna interaktywnego trybu.
- **zawartość:**
  - funkcja `run_shell(context: AppContext)` — pokazuje banner, tworzy `PromptSession` (historia `FileHistory` w pliku obok `config/settings.json` — NIE w workspace; `completer=SlashCompleter`, `complete_while_typing=True`, bottom_toolbar z podpowiedzią "Enter = auto | /help | Ctrl+C = wyjście"), pętla `while True` z prompt.
  - dispatch: pusta linia (Enter) → na razie komunikat "pipeline w budowie" (w etapie 3 podłączony runner); linia zaczynająca się od `/` → lookup w rejestrze komend z `commands.py`; nieznana komenda → czytelny komunikat; `EOFError`/`KeyboardInterrupt` → czyste wyjście.
  - zero logiki domenowej — shell tylko dispatchuje.
- **wzorzec z MangaShift:** brak bezpośredniego pierwowzoru (jedyna nowa funkcjonalność przebudowy — dlatego wcześnie i osobno); rendering przez `utils/rich_console`.

### `anishift/cli/banner.py` (NOWY)
- **odpowiedzialność:** ASCII banner na start shella.
- **zawartość:** funkcja `show_banner(console)` — ASCII art AniShift przez `utils/cool_animation` + style z `utils/rich_console`; krótka linia statusu (wersja, tryb auto/manual z ustawień).
- **skąd logika:** banner startowy z `mm_avh` `start.py` (idea), animacja z `utils/cool_animation.py`.

### `anishift/cli/commands.py` (NOWY)
- **odpowiedzialność:** jedno źródło prawdy o `/komendach` shella.
- **zawartość:**
  - stała `COMMANDS: dict[str, opis]` — `/help`, `/settings`, `/auto`, `/manual`, `/doctor`, `/exit` (completer i help derywują z tej mapy, nic nie przepisują ręcznie — ta sama zasada co `_REGISTRY` silników).
  - handlery: `/help` renderuje tabelę komend; `/settings` otwiera panel z `settings_panel.py`; `/auto` i `/manual` przełączają tryb w `UserSettings` + auto-zapis; `/doctor` woła istniejące checki z `anishift/setup/doctor.py` i renderuje wynik; `/exit` kończy pętlę.
- **wzorzec z MangaShift:** zasada SSOT rejestru (engine-factory-standard) zastosowana do komend.

### `anishift/cli/completer.py` (NOWY)
- **odpowiedzialność:** inline autocomplete po `/` (jak Claude Code).
- **zawartość:** klasa `SlashCompleter(Completer)` — `get_completions()` reaguje TYLKO gdy tekst przed kursorem zaczyna się od `/`; podpowiada komendy z `COMMANDS` (prefix match) z `display_meta` = opis; poza `/` nic nie podpowiada.

### `anishift/cli/settings_panel.py` (NOWY)
- **odpowiedzialność:** panel `/settings` (rich) z auto-zapisem do `config/settings.json`.
- **zawartość:**
  - funkcja `open_settings_panel(context) -> UserSettings` — tabela rich z bieżącymi wartościami wszystkich preferencji; edycja pojedynczego pola (wybór z listy albo wpis wartości); Enter bez zmiany zachowuje wartość; powrót do shella.
  - po każdej zmianie: walidacja + natychmiastowy zapis przez `user_settings.save()` (auto-zapis, bez przycisku "zapisz").
  - klucze API pokazywane wyłącznie jako status "ustawiony/brak" (wartości nigdy nie renderowane).
  - pola w tym etapie: tryb auto/manual, silnik tłumaczenia, silnik TTS, głos, tempo, głośność, wariant wyjścia (players/merge/burn), "przenieś wyniki do output/" TAK/NIE (default NIE). listy silników na razie statyczne zaślepki — od etapu 4/6 derywowane z `available_engine_ids()`.
- **wzorzec z MangaShift:** rendering `utils/rich_console`; odpowiednik trwałego configu `setup/config.py` MangaShift.

### `anishift/cli/main.py` (ZMIANA)
- **odpowiedzialność:** wejście Typer — default = shell.
- **zawartość:** callback bez subkomendy odpala `run_shell(bootstrap())`; subkomenda `doctor` zostaje bez zmian; `load_dotenv` na starcie (jeśli nie robi tego bootstrap).

### `anishift/config/user_settings.py` (ZMIANA)
- **odpowiedzialność:** pełny model preferencji panelu + load/save.
- **zawartość:** rozszerzenie istniejącego `UserSettings` o komplet pól panelu (tryb, silnik tłumaczenia, silnik TTS, głos, tempo, głośność, wariant wyjścia, `move_results_to_output: bool = False`); walidacja zakresów (tempo, głośność); zapis atomowy (tmp → replace); brakujące pola w istniejącym JSON = defaulty (bez wywalania się).

## kolejność implementacji

1. kopia `utils/cool_animation.py` → weryfikacja: import działa, plik identyczny ze źródłem (diff pusty).
2. rozszerzenie `user_settings.py` (pełny model + walidacja) → weryfikacja: test round-trip JSON, brakujące/nadmiarowe pola, uszkodzony JSON.
3. `commands.py` + `completer.py` (SSOT komend) → weryfikacja: test jednostkowy — completer podpowiada tylko po `/`, wszystkie komendy z mapy.
4. `banner.py` + `shell.py` (pętla + dispatch) → weryfikacja: ręcznie — `uv run anishift` pokazuje banner i prompt; Enter = "pipeline w budowie"; nieznana `/komenda` = czytelny komunikat.
5. `settings_panel.py` + podpięcie `/settings`, `/auto`, `/manual`, `/doctor`, `/help`, `/exit` → weryfikacja: zmiana pola zapisuje `config/settings.json`; restart apki pamięta tryb.
6. `main.py` default = shell → weryfikacja: `uv run anishift` bez argumentów = shell, `uv run anishift doctor` = doctor jak dotąd.

## jak testować

ręcznie — banner po starcie; wpisanie `/` pokazuje inline podpowiedzi; `/settings` renderuje panel i zapisuje `config/settings.json`; `/auto` i `/manual` przełączają tryb i jest on pamiętany po restarcie; przełącznik output/ widoczny w panelu; Enter odpowiada komunikatem "pipeline w budowie". dodatkowo: w `workspace/` nie powstaje żaden plik ustawień ani historii.
