# tui

Interaktywna powłoka Textual — jedyne interaktywne UI i domyślne wejście `anishift`. Jeden ekran, jeden właściciel stanu, jeden rejestr komend.

## Pliki

- `app.py` — `AniShiftApp`: jedyny właściciel `SessionState`, rama ekranu i host czternastu komend
- `state.py` — `SessionState`, `UiRoute`, `RunUiState`, drafty i feedback
- `lifecycle.py` — przejścia stanu sesji; zero I/O i zero domeny
- `workers.py` — launchery wątkowe każdego blokującego wywołania fasady + `RunEventPump`
- `auto_trigger.py` — brama pustego Entera i jeden werdykt planu (`START` / `CONFIRM` / `BLOCKED`)
- `commands/` — `catalog.py` (14 komend), `registry.py` (jeden dispatch), `palette.py`, `spec.py`
- `screens/` — widoki tras: workspace, auto, manual, preview, execution, results, tools
- `dialogs/` — `DialogScreen` plus select / value / reorder
- `widgets/` — composer, footer, group_table, plan_view, progress_table, hints, lists
- `settings/` — drzewo ustawień, edytory i sekrety
- `models/` — picker modeli i powierzchnia `/connect`
- `theme.py` + `styles/*.tcss` — jedyny właściciel kolorów i semantyczne zmienne
- `strings.py` — teksty widziane przez użytkownika
- `brand.py`, `messages.py`, `tools.py`, `ui_state.py`, `numbers.py`, `dropped_files.py`

## Pułapki

- Trasy to NIE ekrany Textuala. Widoki montują się raz w `compose()`, a `_render_frame` przełącza im `display`; `push_screen` należy wyłącznie do dialogów. `app.py:241,813`
- `anishift/tui/__init__.py` jest samym docstringiem i musi taki zostać — test chodzi po WSZYSTKICH modułach tui i faila, gdy w `sys.modules` pojawi się `anishift.services`, `anishift.application.service` albo `anishift.application.runtime`. Typy trzymaj w `TYPE_CHECKING`, ciężkie wywołania w importach lokalnych. `tests/tui/test_app_shell.py:93,258`
- Każda odpowiedź workera niesie `generation`, a `lifecycle.accepts_message` wyrzuca spóźnioną i obcą. Nazwa workera nosi `generation=<n>` — zmiana formatu nazwy zabija rozpoznanie spóźnionego wykonawcy. `lifecycle.py:55`, `workers.py:161,339`
- `state.run_state` zmieniaj tylko funkcjami `lifecycle`; `ALLOWED_RUN_TRANSITIONS` to jedyny dozwolony zbiór krawędzi, a odmowa wraca jako `False`, nie jako wyjątek. `lifecycle.py:38,161`
- Pusty Enter najpierw REZERWUJE generację. Każde wyjście bez runu musi ją oddać przez `auto_trigger.release`, inaczej sesja zostaje w `PLANNING` i następny Enter nie zrobi nic. `auto_trigger.py:45,55`, `app.py:331,400`
- Dialog otwieraj wyłącznie przez `open_dialog`: drugi dialog jest ODMAWIANY z feedbackiem, a dismiss przywraca focus wołającego. Własny `push_screen` gubi jedno i drugie. `dialogs/base.py:133,142`
- Kolory literalne żyją tylko w `theme.py`; TCSS bierze je jako zmienne semantyczne z `_theme_variables`. Test faila na każdy `#rrggbb` w źródłach i stylach tui poza modułem motywu. `theme.py:156`, `tests/tui/test_flow.py:310`
- Motyw jest trwały w `config/ui_state.json`, nie w `config/settings.json`; nieznane id cicho wraca do `DEFAULT_THEME_ID`. `ui_state.py:43`
- Katalog slash ma dokładnie 14 pozycji, a `palette` jest `hidden=True` i do nich się nie liczy. Rejestr odmawia duplikatu nazwy oraz drugiej rejestracji tego samego scope. `commands/catalog.py:84`, `commands/registry.py:87`
- `on_key` najpierw ustępuje węższemu kontekstowi (`screen.active_bindings`) i tylko potem pyta rejestr — inaczej skrót dialogu wykonałby cichą akcję globalną. `app.py:274`
- `ENABLE_COMMAND_PALETTE = False`: paleta Textuala jest wyłączona, nasza to `ctrl+p` z rejestru. Wbudowane `action_quit` jest przekierowane na komendę `exit`. `app.py:156,282`
- Sekret pokazuje wyłącznie `configured` albo `missing`, a zapis idzie przez `AppService.update_secret`. Nie renderuj i nie loguj wartości; zmienna procesu nadal przesłania plik i to jest osobny komunikat. `settings/secrets.py:34,106`

## Konwencje

- Jedyna droga do backendu to publiczna fasada `anishift.application`; wewnętrzne moduły I/O i scheduler są zamknięte dla tej warstwy, co sprawdza `tests/application/test_architecture.py`.
- Blokujące wywołanie fasady idzie przez `workers.*` w wątku, nigdy wprost z handlera UI. Eventy runu buforuje `RunEventPump` — progres jest koalescowany per task, a stan ma limit `STATE_EVENT_LIMIT`. `workers.py:94`
- Teksty widziane przez użytkownika deklaruj w `strings.py`, nie w widgecie.
- `CSS_PATH` to trzy pliki `styles/*.tcss` liczone względem pakietu; nowy arkusz dopisz tam. `app.py:155`
- Composer i pas dolny zostają widoczne w każdym rozmiarze; `is_compact` (100x30) przełącza tylko gęstość i blok startowy. `app.py:147,855`

## Testy

```bash
uv run pytest tests/tui -v
```
