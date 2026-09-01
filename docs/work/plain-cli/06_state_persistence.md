---
kind: plan
status: done
baseline: e841c97
created: 2026-09-01
---

# Plan: manifest utrwalania stanu w Interactive CLI

## Cel

Ustalić jedną, spójną regułę zapisu stanu dla całego terminalowego panelu i doprowadzić
kod do tej reguły. Panel ma zachowywać się jak dobrze zrobione narzędzie terminalowe:
zmiana zapisuje się sama, cicho, natychmiast widoczna, a użytkownik nigdy nie musi
pamiętać, czy coś się zapisało.

## Rezultat użytkownika

- Chodzenie po liście i po opcjach nie zmienia niczego. Kulka `●` stoi tam, gdzie stoi
  zapisana wartość, nie pod kursorem.
- Wybór wartości to jawna akcja (`Enter` na opcji, `Space` na przełączniku, `←→` na
  wierszu z liczbą, wpisany znak). Każda z nich zapisuje się sama.
- Nic nie melduje zapisu. Żaden wiersz nie pojawia się i nie znika pod listą.
- Wyjście z panelu — także `Ctrl+C` i awaryjne zamknięcie procesu — jest równe zapisowi.

## Warunki końcowe

- [ ] Ruch kursora w edytorze wyboru nie tworzy transakcji i nie rusza kulki.
- [ ] `Enter` w edytorze wyboru zapisuje wybór i zamyka edytor, bez komunikatu.
- [ ] Seria zmian jednej wartości to jedna transakcja (debounce `_SAVE_DELAY_SECONDS`).
- [ ] Zamknięcie panelu z jakiegokolwiek powodu utrwala oczekującą zmianę, nie czekając
      na deadline.
- [ ] Zapis równy stanowi zapisanemu nie tworzy transakcji.
- [ ] Testy pilnują każdej reguły manifestu z sekcji 1.

## Nie-cel

- Obsługa kliknięcia myszą (wybór wiersza klikiem). Myszy w panelu poza kółkiem nie ma
  i ten plan jej nie dodaje.
- Zmiana zestawu pól, kategorii ani układu ekranów.
- Historia zmian, undo, wersjonowanie `settings.json`.

## Authority i baseline

| Źródło                                     | Rola                                                     |
| ------------------------------------------ | -------------------------------------------------------- |
| decyzje właściciela produktu z tej sesji    | wymaganie nadrzędne nad wcześniejszymi dokumentami        |
| `anishift/cli/AGENTS.md`                    | kontrakt obszaru, aktualizowany na końcu planu            |
| `docs/work/plain-cli/05_settings_and_progress.md` | wymagania etapu 05                                 |
| `anishift/cli/interactive/settings.py`      | aktualne zachowanie panelu                               |
| `anishift/cli/interactive/app.py`           | właściciel cyklu życia panelu i pętli idle               |
| `anishift/cli/interactive/prompts.py`       | renderer, `refresh_interval = 0.1 s`                     |

**Baseline:** `e841c97`, branch `work/interactive-cli/04-mascot-polish`.
`ruff` czysto, `mypy` 37 błędów w 3 plikach, `pytest` 47 failed / 2436 passed / 2 errors.

**Znane wcześniejsze failures:** `tests/cli/test_run.py` (18), `tests/cli/test_interactive_progress.py` (28),
`tests/config/test_model_catalog.py` (1) oraz 2 errors — zastane, poza zakresem planu.
Błędy `mypy` dotyczą wyłącznie nieaktualnych testów `test_interactive_app.py`,
`test_interactive_progress.py`, `test_interactive_home.py`.

## 1. Manifest — jak ma się zachowywać zapis stanu

Dziewięć reguł. Każda kolejna zmiana w panelu musi się do nich stosować.

**Z1. Nawigacja nie jest zmianą stanu.**
`↑↓`, `PageUp`/`PageDown`, `Home`/`End`, kółko myszy, wejście na ekran i zejście z niego
nie zapisują nic. Kursor wskazuje, o czym mówimy; nie wybiera.

**Z2. Stan zmienia wyłącznie jawna akcja.**
`Enter` na opcji wyboru, `Space` na przełączniku, `←→` na wierszu z wartością, wpisany
znak w edytorze tekstu, dodanie lub usunięcie głosu, potwierdzony reset. Nic poza tym.

**Z3. Zapis jest cichy.**
Sukces nie ma komunikatu. Dowodem zapisu jest sama wartość w wierszu i kulka `●`.
Komunikat należy do błędu i do jawnie potwierdzonej operacji zbiorczej (reset).

**Z4. Widok wyprzedza dysk.**
Zmiana jest widoczna w tej samej klatce, w której padł klawisz. Zapis może być
opóźniony. Ekran nigdy nie czeka na I/O, a `render()` nigdy nie zapisuje.

**Z5. Zapis jest grupowany, nie wołany na każdy klawisz.**
Seria zmian tej samej wartości zwija się w jedną transakcję po `_SAVE_DELAY_SECONDS`
bezczynności. Przytrzymana strzałka to jeden zapis, nie sto.

**Z6. Każde wyjście jest zapisem.**
Zejście z wiersza, `Esc` z edytora, wyjście z kategorii, zamknięcie panelu, `Ctrl+C`
i awaryjne zamknięcie procesu utrwalają oczekującą zmianę natychmiast, bez czekania na
deadline. Użytkownik nie może stracić zmiany przez to, że wyszedł za szybko.

**Z7. Zapis bez różnicy nie istnieje.**
Wartość równa zapisanej nie tworzy transakcji ani żadnego widocznego skutku.

**Z8. Niepełna wartość milczy.**
Wartość wpisywana, która jeszcze nie jest poprawna, nie zapisuje się i nie krzyczy.
Błąd należy do jawnego zatwierdzenia, nie do trzeciego znaku w trakcie pisania.

**Z9. Status nie rusza layoutu.**
Wiersz statusu jest wydany zawsze, pusty czy nie. Nic nie może przesunąć listy pod
kursorem między dwoma klawiszami.

## 2. Stan aktualny

### Zgodne z manifestem już teraz

| Reguła | Dowód                                                                        |
| ------ | ---------------------------------------------------------------------------- |
| Z3     | brak `_SAVED_MESSAGE`; sukces bez komunikatu — `settings.py`, commit `8d0ad52` |
| Z4     | `_adjust_selected` przebudowuje `_items`; `_effective_value` czyta `_pending` |
| Z5     | `_PendingEdit.deadline`, `_SAVE_DELAY_SECONDS = 0.4`, `flush_pending`         |
| Z7     | `_already_stored` w `_commit_pending`                                         |
| Z8     | `_schedule_editor_save` gubi niepoprawną wartość bez komunikatu               |
| Z9     | `_STATUS_ROWS`, `_append_feedback` zawsze wydaje wiersz                       |

Pętla idle działa: `TerminalRenderer` ma `refresh_interval = 0.1 s`
(`prompts.py:74`, `prompts.py:205`), a `after_render` woła `_handle_idle` →
`flush_pending` (`app.py:204`), więc debounce domyka się bez kolejnego klawisza.

### Gap 1 — ruch kursora w edytorze wyboru zapisuje (łamie Z1 i Z2)

`_handle_choice_editor` (`settings.py:648-652`) po każdej udanej nawigacji w edytorze
`SELECT` woła `_schedule_editor_save`. Skutki:

- `↑↓` po liście opcji utrwala kolejno wartości, przez które użytkownik tylko przejechał;
- kulka `●` rysowana jest z `editor.current_value` ustawionego przy otwarciu
  (`settings.py` `_option_marker`), więc po takim zapisie kulka pokazuje inną wartość niż
  ta, która trafiła do pliku;
- to jest źródło pierwotnej skargi „zapisuje się, choć nic nie zrobiłem"; łatka
  `_already_stored` uciszyła tylko powrót na wartość wyjściową, nie samą regułę.

### Gap 2 — martwy kod po Gap 1

`_schedule_editor_save` ma gałąź `_EditorAction.SELECT_MODEL` używaną wyłącznie ze
ścieżki nawigacji. Po jej usunięciu nikt nie planuje `_PendingEdit` z akcją
`SELECT_MODEL`, więc obsługa tej akcji w `_persist_pending` i `_already_stored` oraz pole
`_PendingEdit.provider_id` przestają mieć wywołanie. Model wybiera się przez `Enter` →
`_apply_editor` → `select_translation_model` i ta ścieżka zostaje bez zmian.

### Gap 3 — awaryjne wyjście może zgubić zmianę (łamie Z6)

`handle_key` utrwala `_pending` na wejściu dla każdego klawisza niebędącego kontynuacją
wartości (`settings.py:385-388`), więc `Esc` i `Ctrl+C` w panelu są bezpieczne. Nie ma
natomiast żadnego domknięcia poza ścieżką klawisza: `AniShiftApp.run()` ma tylko
`finally: self._mascot.close()` (`app.py:165-171`), a `_show_home()` zeruje
`self._settings` (`app.py:521`) bez utrwalenia. Zmiana młodsza niż `0.4 s` ginie, gdy
proces kończy się inaczej niż klawiszem panelu.

### Dowody

| Twierdzenie                                        | Dowód                                        | Status   |
| -------------------------------------------------- | -------------------------------------------- | -------- |
| nawigacja w `SELECT` planuje zapis                  | `settings.py:648-652`                        | verified |
| kulka rysuje się ze stanu z chwili otwarcia         | `_option_marker`, `editor.current_value`     | verified |
| debounce domyka się bez klawisza                    | `prompts.py:74`, `prompts.py:205`, `app.py:204` | verified |
| `Esc`/`Ctrl+C` w panelu utrwalają                   | `settings.py:385-388`                        | verified |
| brak utrwalenia przy zamknięciu poza klawiszem      | `app.py:165-171`, `app.py:506-521`           | verified |

## 3. Zakres

### In scope

- Usunięcie zapisu z nawigacji w edytorze wyboru.
- Usunięcie kodu, który po tym staje się nieosiągalny.
- Publiczne domknięcie panelu utrwalające `_pending` bez czekania na deadline, wołane z
  każdej ścieżki zamknięcia, w tym `finally` sesji.
- Hint edytora wyboru mówiący wprost, że wybiera `Enter`.
- Testy każdej reguły manifestu.
- Aktualizacja `anishift/cli/AGENTS.md` i wymagań etapu 05 o manifest.

### Out of scope

- Mysz (klik), nowe pola, nowe ekrany, zmiana `_SAVE_DELAY_SECONDS`.
- Naprawa zastanych failures i błędów `mypy` w nieaktualnych testach.

### Forbidden

- Przywracanie akcji „Zapisz" i komunikatu sukcesu.
- I/O w `render()`.
- Zapis na `↑↓`, `PageUp`/`PageDown`, `Home`/`End` i kółku myszy — w żadnym ekranie.
- Ruszanie kulki `●` za kursorem.
- Zmiana kontraktu `AppService`; panel dalej mutuje stan wyłącznie przez fasadę.

### Allowed local decisions

- Nazwy nowych metod i stałych, kolejność gałęzi, dokładna treść hintu.
- Podział testów między pliki `tests/cli/test_interactive_settings_*.py`.

### Escalation conditions

- Gdyby usunięcie zapisu z nawigacji wymagało zmiany sposobu rysowania kulki dla któregoś
  edytora — zatrzymać i zapytać, bo to zmiana wyglądu.
- Gdyby domknięcie panelu w `finally` wymagało I/O na ścieżce wyjątku, która może
  zamaskować pierwotny błąd — zatrzymać i zapytać.

## 4. Mapa plików

```text
MODIFY  anishift/cli/interactive/settings.py   Z1/Z2 w edytorze wyboru, publiczne close(), hint, sprzątanie po SELECT_MODEL
MODIFY  anishift/cli/interactive/app.py        wywołanie close() z zamknięcia panelu i z finally sesji
MODIFY  anishift/cli/AGENTS.md                 manifest jako kontrakt obszaru
MODIFY  docs/work/plain-cli/05_settings_and_progress.md  wymagania etapu wskazują manifest
MODIFY  tests/cli/test_interactive_settings_autosave.py  reguły Z1, Z2, Z6
MODIFY  tests/cli/test_interactive_settings_steps.py     regresja: nawigacja bez zapisu
READ    anishift/cli/interactive/prompts.py    pętla idle, bez zmian
CREATE  docs/work/plain-cli/06_state_persistence.md      ten plan
```

## 5. Wykonanie

### Faza 1 — nawigacja przestaje zapisywać

**Cel:** Z1 i Z2 w edytorze wyboru.

**Działania:** w `_handle_choice_editor` nawigacja tylko przesuwa kursor. `Enter`
zapisuje wybór (istniejąca ścieżka `_submit_editor` → `_apply_editor`). `Space` w
`MULTI_SELECT` zostaje jawną zmianą z zapisem opóźnionym.

**Inwarianty:** kulka dalej rysowana z `editor.current_value`; `Esc` nie może teraz nic
zgubić, bo nawigacja nie tworzy `_pending`.

**Sprawdzenie:** nowe testy — przejechanie całej listy opcji daje `service.saves == []`;
`Enter` na innej opcji daje dokładnie jedną transakcję; `Esc` po przejechaniu listy
zostawia wartość zapisaną nietkniętą.

**Warunek przejścia:** testy przechodzą, bramki na baseline.

### Faza 2 — usunięcie kodu bez wywołania

**Cel:** żaden kod nie udaje, że nawigacja może zapisać model.

**Działania:** usunąć gałąź `SELECT_MODEL` z `_schedule_editor_save`, obsługę tej akcji z
`_persist_pending` i `_already_stored` oraz pole `_PendingEdit.provider_id`, jeśli po tym
nie ma czytelnika.

**Inwarianty:** wybór modelu przez `Enter` (`_apply_editor` → `select_translation_model`)
działa bez zmian; edytor adresu dalej planuje `UPDATE_ENVIRONMENT` z wpisywania.

**Sprawdzenie:** `tests/cli/test_interactive_settings_*` w całości; `ruff`, `mypy`.

### Faza 3 — każde wyjście utrwala

**Cel:** Z6 bez wyjątków.

**Działania:** publiczne `SettingsController.close()` utrwalające `_pending` natychmiast,
niezależnie od `deadline`, idempotentne i odporne na błąd zapisu. Wołane przy zamknięciu
panelu (`app.py:_show_home`) i w `finally` sesji (`app.py:run`).

**Inwarianty:** `close()` nie może rzucić w `finally` i nie może zamaskować pierwotnego
wyjątku; po `close()` panel nie ma oczekującej zmiany.

**Sprawdzenie:** testy — zmiana młodsza niż deadline plus `close()` jest zapisana;
`close()` bez oczekującej zmiany nie tworzy transakcji; `close()` przy błędzie zapisu nie
propaguje wyjątku.

### Faza 4 — hint i kontrakt

**Cel:** ekran mówi prawdę o tym, co zmienia stan; reguła jest pod strażnikiem tekstu.

**Działania:** hint edytora wyboru wprost `Enter wybierz`. Manifest wpisany do
`anishift/cli/AGENTS.md` skrótem i do wymagań etapu 05 jako obowiązująca reguła.

**Sprawdzenie:** pełne bramki; `git log` bez śladów AI; przegląd diffu.

## 6. Sprzężenie zwrotne

```text
błąd zgodny z designem            -> popraw w tej samej fazie i sprawdź ponownie
kulka wymaga innego źródła prawdy -> zatrzymaj, zapytaj (zmiana wyglądu)
właściciel zmienia regułę         -> popraw manifest, potem kod
brak dowodu na zachowanie         -> targeted test przed zmianą
```

## 7. Weryfikacja

| Twierdzenie                              | Dowód                                                        |
| ---------------------------------------- | ------------------------------------------------------------ |
| Z1 w edytorze wyboru                     | test: przejazd całej listy, `service.saves == []`            |
| Z1 w menu i na kółku                     | test: `↑↓` i `scroll` po ekranie bez transakcji              |
| Z2 dla `Enter`, `Space`, `←→`, pisania    | testy istniejące + nowy dla `Enter` w `SELECT`               |
| Z5 grupowanie                            | test istniejący: seria `←` to jedna transakcja               |
| Z6 wyjście = zapis                       | nowe testy `close()` oraz istniejący dla `Esc`               |
| Z7, Z8, Z9                               | testy istniejące w `test_interactive_settings_autosave.py`    |
| brak regresji                            | `ruff`, `mypy` (2 platformy), `pytest` na baseline 47/2       |

**Human checkpoint** po Fazie 3: uruchomić `uv run anishift`, wejść w `Ustawienia`,
przejechać `↑↓` po liście i po opcjach edytora wyboru, zmienić coś `Enter`, zmienić
liczbę `←→`, wyjść `Esc` i wrócić. Sprawdzić: nic nie melduje zapisu, nic nie skacze,
kulka stoi na zapisanej wartości, zmiany są po powrocie. Zgłosić, co nie pasuje.
