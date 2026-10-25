---
kind: review
status: pass-with-findings
reviewed-state: PR #66, `git diff c41e241 4365a51` (commity 7584b60, 2cc4184, 69220e8), main checkout
date: 2026-10-25
---

# Review: PR #66 — crash na jednowyrazowej linii z `\N`, zniekształcone tagi ASS, hook `check_mutating_assign`

## Zakres

- przedmiot: scalony PR #66 — `anishift/services/subtitles/{linebreak,fitting,service}.py`, `anishift/utils/logger/modes.py`, nowy hook `scripts/hooks/check_mutating_assign.py` z testem `tests/scripts/test_check_mutating_assign.py` i wpisem w `.pre-commit-config.yaml`, testy w `tests/services/subtitles/test_subtitles_dialogue_layout.py` i `test_sign_fitting.py`
- baseline: `c41e241` (merge PR #65)
- authority: kontrakt z briefu (crashe znikają, zachowanie dla poprawnych wejść bez zmian, hook blokuje przypisanie mutujące kontener indeksowany przez target), `AGENTS.md` (root, `anishift/`, `services/subtitles/`, `tests/`), skill `simple`, `coding/references/python.md`, źródła libass (master) jako punkt odniesienia semantyki ASS
- ryzyka: regresja dopasowań regexów dla poprawnych liczb, zmiana grupowania `_kits`, zbyt szerokie `except`, fałszywe pozytywy/negatywy hooka, testy niezdolne wykryć regresji
- poza review: jakość wizualna układu szyldów, pozostałe moduły, klasyfikator (`classifier.py` ma własny, niezmieniony regex pozycji)

## Werdykt

**Status:** PASS WITH FINDINGS

**Najważniejszy powód:** wszystkie trzy naprawy są poprawne i udowodnione eksperymentem (identyczne grupowanie `_kits` w 400 tys. losowych przypadków, zero różnic regexów `\pos`/`\fsc` na 7,1 mln bloków tagów korpusu, nowe testy czerwone na starym kodzie i zielone na nowym, bramki zielone). Findingi dotyczą tylko hooka: nie biegnie w CI jak hooki siostrzane i flaguje cele atrybutowe, gdzie pułapka kolejności ewaluacji nie istnieje.

## Findings

### Krytyczne

Brak.

### Poważne

Brak.

### Mniejsze

#### Nowy hook nie jest uruchamiany w CI, w odróżnieniu od hooków siostrzanych

- miejsce / scenariusz: `.github/workflows/ci.yml:33-36` uruchamia jawnie `check_test_comments.py` i `check_const_docstrings.py`; `check_mutating_assign.py` nie ma tam wpisu. `.pre-commit-config.yaml:73-79` podpina go tylko lokalnie (`stages: [pre-commit]`).
- dowód: `sed -n 28,40p .github/workflows/ci.yml` — brak `check_mutating_assign`; root `AGENTS.md` deklaruje „CI: ruff i hooki na Ubuntu”.
- wpływ: commit bez zainstalowanych hooków lub z `--no-verify` wnosi wzorzec `x[i] += x.pop()` niezauważony aż do runtime; strażnik ma słabszą gwarancję niż jego rodzeństwo.
- minimalna reakcja: krok w `ci.yml` analogiczny do linii 36: `uv run python scripts/hooks/check_mutating_assign.py $(git ls-files '*.py' ':!external/**')`.

#### Hook flaguje cele atrybutowe, gdzie pułapka kolejności ewaluacji nie występuje

- miejsce / scenariusz: `scripts/hooks/check_mutating_assign.py:24-30` (`_target_bases` zbiera też `ast.Attribute`), test `tests/scripts/test_check_mutating_assign.py:44` utrwala przypadek `box.value += box.update(1)` jako odrzucany.
- dowód: eksperyment `scratchpad/review66/hook_cases.py`: `obj.last = obj.pop()` → flagowane (`'obj' is mutated…`), `class A(list): … self.x = self.pop()` → flagowane. W Pythonie `obj.attr = <expr>` i `obj.attr += <expr>` zapisują do atrybutu po ewaluacji wartości; `pop()` na obiekcie nie zmienia istnienia atrybutu, więc nie ma błędu, który hook ma łapać (indeks, który po mutacji przestaje istnieć).
- wpływ: fałszywe pozytywy poza kontraktem z briefu („kontener indeksowany przez target”); koszt niski (podział na dwie instrukcje), ale reguła uczy złej diagnozy i docstring modułu („subscript or attribute target”) rozszerza ją bez uzasadnienia.
- minimalna reakcja: ograniczyć `_target_bases` do `ast.Subscript` (bazę atrybutu zbierać tylko, gdy jest wewnątrz subskryptu, np. `a.b[0] = a.b.pop()` dalej łapane, bo `Subscript.value` to `a.b`), usunąć przypadek `box.value += box.update(1)` z testu albo przenieść go do listy przechodzących; docstring modułu dostosować.

### Sugestie

#### `_MAX_DRAWING_LEVEL = 64` jest bezpieczny, ale nie odzwierciedla libass

- miejsce: `anishift/services/subtitles/fitting.py:97-98`, `:269`, `:619`.
- dowód: libass `ass_render.c` (`get_outline_glyph`, `blend_vector_clip`): `scale_base = lshiftwrapi(1, scale - 1)`, a `ass_utils.h:244-248`: `(0u + (uint32_t)i) << (shift & 31)`. Poziom 32 daje `scale_base = INT32_MIN` → `w = 0` (kształt znika), poziom 33 zawija do przesunięcia 0 (dzielnik 1). Sensowny zakres libass to 1–31; `\clip` dodatkowo clampuje skalę `FFMAX(argtoi32(args[0]), 1)` (`ass_parse.c`, `parse_vector_clip`).
- ocena: 64 chroni przed `OverflowError` (2**63 mieści się we float) i nie dotyka żadnego realnego pliku (korpus nie ma `\p` > 8), więc nie blokuje. Poziomy 32–64 są mierzone dzielnikiem 2**(n-1), którego libass nie użyje. Jeśli celem stałej ma być wierność libass, wartość 31 i docstring „libass zawija przesunięcie na 32 bitach” byłyby ściślejsze.

#### Akceptacja `+` jest zgodna z libass, ale niespójna między regexami pliku

- miejsce: `fitting.py:82` (`_RE_NUMBER` z `[+-]?`), użyte teraz w `_RE_POS:88` i `_RE_AXIS_SCALE:91`; `_RE_SCALING:74-76` i `_RE_POINT:103` nadal tylko `-?`.
- dowód: libass parsuje `\pos`/`\fscx` przez `argtod` → `mystrtod` → `ass_strtod` (`ass_strtod.c:130`: `if (*p == '+') p += 1;`), a `\p` przez `argtoi32` → `strtoll`, który też przyjmuje `+`. Eksperyment `regex_cmp2.py`: `\fscx+50` stary `[]`, nowy `[('x', '+50')]`; `\pos(+5,+6)` stary `[]`, nowy dopasowany. Korpus: 0 wystąpień `+` w tych tagach (0 różnic na 7 116 083 blokach).
- ocena: zmiana idzie w stronę libass, więc nie jest regresją. Dla spójności `_RE_SCALING` i `_RE_POINT` mogłyby korzystać z tego samego `_RE_NUMBER` — poza zakresem tego PR.

#### `_kits`: identyczność sprawdzona, prostsza forma dostępna

- miejsce: `fitting.py:386-391`, `if item is items[0] or item.start >= end`.
- dowód: `kits_equiv.py` — 200 000 losowych zestawów (start ≥ 0, end ≥ start) i 200 000 (end dowolne, także < start): 0 różnic między starą a nową wersją; stara rzuca `IndexError` dla start < -1, nowa grupuje (`test_signs_starting_before_zero_form_their_own_set`).
- ocena: porównanie tożsamości `item is items[0]` wymaga zastanowienia; `kits.append([items[0]])` + pętla po `items[1:]` wyraża „pierwszy element otwiera komplet” wprost. Kosmetyka, nie blokuje.

#### Nowa zmienna lokalna bez typu w `modes.py`

- miejsce: `anishift/utils/logger/modes.py:120` `file_path = overrides.pop("file_path")`.
- ocena: root `AGENTS.md` wymaga typowania lokalnych; sąsiednie `defaults`, `config`, `config_dict` też są nietypowane (styl zastany w `utils/`), a wartość jest `Any`, więc adnotacja niesie mało. Zgłaszam dla kompletności, nie do poprawy w tym wątku.

## Zgodność z kontraktem

| Wymaganie / decyzja | Stan | Dowód |
| ------------------- | ---- | ----- |
| Crash `IndexError` na jednowyrazowej linii z `\N` znika | pass | stare `linebreak.py:117` z nowym testem: 6× `IndexError: list assignment index out of range`; nowy kod: zielone. Dodatkowo stary kod dla `Dwa słowa\N` zwracał `None` (błędny zapis do `found[-2]` po `pop`), czyli cicho tracił tagi pomiaru — nowy test to też łapie |
| Crash na zniekształconych tagach ASS znika | pass | stare `fitting.py` z nowym testem: `IndexError: pop from empty list` (`\clip(,m)`), `OverflowError` (`\clip(2000,…)`, `\p5000`), `ValueError` (`1.2.3`, `.`); nowy kod: 9/9 zielone |
| Poprawne wejścia bez zmian — regexy | pass | korpus `workspace/.quality` (771 plików, 7 116 083 bloków tagów): `pos` 0 różnic, `fsc` 0 różnic, `ink` 3 różnice — wszystkie to realny `\bord2..25`, na którym stary wzorzec dawał `float("2..25")` → crash; nowy czyta `2.` jak libass. Syntetyczne: `\fscx100`, `\fscx-50`, `\pos(10.5,20)`, `\bord2.5`, `\shad0`, `\bord.5`, `\pos(.5,.5)` identyczne |
| Poprawne wejścia bez zmian — `_kits` | pass | 400 000 losowych przypadków, 0 różnic (`kits_equiv.py`) |
| Poprawne wejścia bez zmian — `_clip` | pass | guard zwraca `None` tylko dla pustej listy wartości (stare: `IndexError`) i poziomu > 64 (stare: rect z dzielnikiem 2**(n-1) albo `OverflowError`); dla 1 ≤ poziom ≤ 64 ścieżka identyczna (`fitting.py:618-621`) |
| `except (Pysubs2Error, ValueError)` nie łapie za dużo | pass | w `try` jest wyłącznie `pysubs2.load` (`service.py:133-146`); `pysubs2_errors.py`: `ValueError` dla rozmiaru stylu, czasu zdarzenia i koloru; `FormatAutodetectionError` (podklasa `Pysubs2Error`) dla pustego/śmieciowego pliku; `UnicodeDecodeError` (podklasa `ValueError`) łapany wcześniej z własnym komunikatem, kolejność klauzul zachowana |
| Hook blokuje przypisanie mutujące indeksowany kontener | pass | `hook_cases.py`: `a.b[0] = a.b.pop()`, `x[i] = y.pop() + x.pop()`, `found[-2] += found.pop()`, `x[found[0]] = found.pop()`, `found[len(found)-2] += found.pop()` → flagowane; `d[k] = d.get(k)`, `self.x = self.x.copy()`, `found[-1] += alias.pop()`, walrus, `del`, `found[-1] += found[-2]` → czyste; stare `linebreak.py:117` i `modes.py:120` → flagowane |
| Hook bez fałszywych pozytywów | pass z findingiem | cele atrybutowe (`obj.last = obj.pop()`) flagowane bez realnej pułapki — finding wyżej; plain `Assign` (`cfg['x'] = cfg.pop('y')`, `d[k] = d.setdefault(k,0)+1`) flagowane świadomie (docstring modułu: „augmented or plain”, commit 2cc4184: „so the rule has no exceptions”) — akceptowalny konserwatyzm |
| Hook bez fałszywych negatywów w zakresie AST | pass | aliasowanie (`alias = found; found[-1] += alias.pop()`) i mutacja przez funkcję (`found[-1] += f(found)`) są poza możliwościami analizy tekstowej — ograniczenie znane, nie błąd |
| Wpis pre-commit `files: \.py$` + `exclude: ^external/` | pass | `uv run pre-commit run no-mutating-assign --all-files` → Passed; `external/` ma śledzone pliki (README, hashe), wykluczenie spójne z `trailing-whitespace`/`end-of-file-fixer`; hook obejmuje `tests/`, `scripts/`, `docs/**/*.py` — zgodnie z intencją „every staged Python file” |
| Hook uruchamiany jak pozostałe lokalne | pass | ten sam `entry: python scripts/hooks/…`, `language: system`, `stages: [pre-commit]`; różni się tylko brakiem kroku w CI (finding) |
| Testy wykrywają regresję | pass | wszystkie nowe testy czerwone na kodzie z `c41e241` (kopia pakietu w scratchpadzie z podmienionymi trzema modułami, `PYTHONPATH`), zielone na `4365a51` |
| Konwencje testów: markery, zero prozy, nazwy | pass | `test_sign_fitting.py` i `test_subtitles_dialogue_layout.py`: `@pytest.mark.unit` / `@pytest.mark.integration` (filesystem) zgodnie z `pyproject.toml:146-153`; `tests/scripts/test_check_mutating_assign.py` bez markerów jak siostrzane `test_check_const_docstrings.py`; brak komentarzy i docstringów; nazwy opisują scenariusz |
| Docstring stałej pod nią, typowanie lokalnych, brak komentarzy, KISS | pass z sugestiami | `_MAX_DRAWING_LEVEL` z docstringiem pod (`fitting.py:97-98`), `trailing: str` typowane; `MUTATING_METHODS` z docstringiem pod jak `SKIP_PARTS` w siostrzanym hooku; `# fmt: skip` to dyrektywa narzędzia; jedyny brak typu — `modes.py:120` (sugestia) |
| Commity `typ(scope): opis`, scope z listy, bez śladów AI | pass | `fix(subtitles)`, `test(repo)`, `fix(subtitles)`; `repo` i `subtitles` w `check_commit_msg.py:48,60`; treści bez stopek generatora |

## Regresje i integracja

- `_RE_POS` i `_RE_AXIS_SCALE` są używane też w `_resized` (`fitting.py:298`) do usuwania tagów rysunku; `_panel` zwraca `None` dla rysunków ze zniekształconym `\pos`/`\fsc`, więc `_resized` nigdy nie dostaje tagu, którego nowy wzorzec nie usunie.
- `_RE_NUMBER` nie ma grup łapiących (`(?:…)`), więc numeracja grup w `_RE_POS` (1, 2) i `_RE_AXIS_SCALE` (1, 2) jest nienaruszona; `_RE_INK` zachował trzy grupy czytane w `_hidden_words` (`fitting.py:483`).
- `classifier.py:103` (`_RE_ANCHOR_Y`) zachował luźne `-?[0-9.]+` tylko w części niełapanej; konwertowana grupa jest ścisła — brak crasha, poza zakresem PR.
- Pozostałe ścieżki `float()`/`int()` w `fitting.py` (`_RE_POINT`, `_RE_SCALING`, `_RE_DRAWING_LEVEL`) mają ścisłe wzorce; `int(level[1])` dla ponad 4300 cyfr rzuciłby `ValueError` (limit `int()` w CPython) — teoretyczne, nie w korpusie.
- Zmiana w `modes.py` jest semantycznie neutralna (plain `Assign` ewaluuje wartość przed zapisem klucza); wymuszona przez hook, nie przez błąd.

## Wykonane kontrole

```text
uv run pytest tests/services/subtitles tests/scripts -q
pasek 100% bez F/E, 1 SKIPPED (test_text_layout_production.py:62, zastany), exit 0

uv run pytest -n 0 tests/scripts/test_check_mutating_assign.py
13 passed

PYTHONPATH=<scratch kopia pakietu z fitting/linebreak/service z c41e241> uv run pytest -n 0 <5 nowych testów>
czerwone: IndexError (linebreak.py:117 ×6, fitting.py:385, fitting.py:614 ×2), OverflowError (fitting.py:270, :614),
ValueError (fitting.py:267, :274, :486; pysubs2 substation.py:212, :227), AssertionError None == ('Dwa', 'słowa')

uv run python -I scratchpad/review66/kits_equiv.py
nonneg start, end>=start: 0 of 200000 differ; end<start allowed: 0 of 200000 differ; old crashes on start<-1: IndexError

uv run python -I scratchpad/review66/regex_cmp2.py
synthetic differences: \fscx+50, \pos(+5,+6) (nowe dopasowania, zgodne z libass); \fscx., \pos(.,5), \pos(1.2.3,4), \bord1.2.3\shad.
(stare dopasowania prowadzące do float() crash, teraz odrzucone/ucięte)
corpus files: 771, tag blocks: 7116083, differences: pos 0, fsc 0, ink 3 (wszystkie \bord2..25)

uv run python scratchpad/review66/hook_cases.py  (23 przypadki, wyniki w tabeli wyżej)
git ls-files '*.py' | xargs uv run python scripts/hooks/check_mutating_assign.py → exit 0
uv run python scripts/hooks/check_mutating_assign.py old_linebreak.py old_modes.py → 2 problemy, exit 1
uv run pre-commit run no-mutating-assign --all-files → Passed

uv run python scratchpad/review66/pysubs2_errors.py
ValueError: fontsize abc, start xx, colour &Hzz; FormatAutodetectionError: pusty/śmieciowy plik;
OK z RuntimeWarning: layer abc, marginL abc, za mało pól

uv run ruff check anishift/ tests/ → All checks passed
uv run ruff format --check anishift/ tests/ → 675 files already formatted
uv run mypy anishift/ tests/ → exit 0
uv run ruff check scripts/hooks/check_mutating_assign.py → All checks passed (informacyjnie)

libass master (pobrane do scratchpad/review66/libass_dl/):
ass_utils.h:244-248 lshiftwrapi: (0u + (uint32_t)i) << (shift & 31)
ass_utils.h:257-262 mystrtoi32: strtoll + FFMINMAX(INT32_MIN, INT32_MAX)
ass_strtod.c:130 if (*p == '+') p += 1;
ass_parse.c: \p → argtoi32, clamp tylko val < 0 → 0; \clip wektorowy → scale = FFMAX(argtoi32(args[0]), 1)
```

## Niewykonane lub nierozstrzygające kontrole

- Pełny `uv run pytest` (cały `testpaths`) — nie uruchamiany; zakres PR nie wychodzi poza `services/subtitles`, `scripts/hooks` i neutralną zmianę w `utils/logger`. Autor deklaruje zielone `pytest tests/services/subtitles` (REPORTED).
- Normalizacja trzech padających odcinków właściciela (commit 7584b60) — REPORTED przez autora, nie odtwarzana (brak wskazania plików).
- `mypy --platform linux` — nie uruchamiany (zmiany nie dotykają kodu zależnego od platformy).

## Wymagana ocena człowieka

Nie jest wymagana: zmiany nie wpływają na wygląd ani interakcję, tylko usuwają crashe i zachowują wynik dla poprawnych wejść.

## Ograniczenia review

- Równoważność regexów sprawdzona na korpusie `workspace/.quality` (771 plików) i próbkach syntetycznych; pliki poza korpusem mogą zawierać inne zniekształcenia, których żadna wersja nie obsługuje.
- Analiza hooka jest statyczna i tekstowa — aliasów i mutacji przez wywołania funkcji nie wykryje żadna wersja tej reguły; to granica narzędzia, nie finding.
- Semantyka libass czytana ze źródeł `master` (2026-10), nie z wersji wbudowanej w mpv właściciela.

## Zalecany następny krok

- Przyjąć PR bez cofania. Osobnym, małym commitem (`ci(repo)` / `test(repo)`): dodać krok CI dla `check_mutating_assign.py` i zawęzić hook do celów subskryptowych wraz z poprawką testu i docstringu modułu. Sugestie dotyczące `_MAX_DRAWING_LEVEL`, spójności `+` w regexach i formy `_kits` zostawić do decyzji właściciela — nie blokują i nie zmieniają wyniku dla realnych plików.
