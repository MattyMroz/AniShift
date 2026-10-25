---
kind: plan
status: draft
baseline: 4365a51 (main, czyste drzewo)
created: 2026-10-25
---

# Plan: twardy limit słów linii dialogu przed rdzeniem układu

## Cel

`layout_dialogue` ma kończyć się w milisekundach dla linii o dowolnej liczbie słów, a dla każdej linii dialogu z korpusu `workspace/ready/` zwracać wynik bajt w bajt taki sam jak dziś. Linia ponad limitem idzie prostym fallbackiem (tekst nierozbity, bez `{\q2}`, więc libass zawija ją sam w marginesach stylu) i jest jawnie policzona w `LayoutReport`.

## Rezultat użytkownika

Rezydent przetwarzający odcinki nie zawiesza się na uszkodzonym albo nietypowym pliku napisów z linią o setkach słów. W logu podsumowania układu (`Subtitle layout summarized`) pojawia się licznik `dialogue_too_long`, a każda taka linia zostawia ostrzeżenie z liczbą słów (bez treści).

## Warunki końcowe

- [ ] `layout_dialogue(SSAEvent(text="x"), "a b " * 500, profile)` i to samo z `profile=None` kończą się poniżej 2 s (dziś: > 1000 s) i zwracają `too_long=True`, tekst bez `\N` i bez `{\q2}`.
- [ ] Linia o dokładnie `MAX_DIALOGUE_WORDS` słowach przechodzi przez rdzeń jak dotąd (`too_long=False`).
- [ ] `layout_translated` na korpusie `workspace/ready/` daje identyczne teksty zdarzeń i identyczny `LayoutReport` jak przed zmianą (plus nowe pole równe 0).
- [ ] Istniejące testy `tests/services/subtitles/` zielone bez zmian w asercjach; cztery bramki repo zielone.

## Nie-cel

- Przyspieszanie rdzenia układu (`layout.py`) ani zmiana przeglądu pełnego dla K ≤ 3 (spec `docs/work/10-quality/text-layout.md` §5.1).
- Leniwa tabela `_measure` i ścieżka szyldów (`fit_signs`, `tagged_measure`) — odłożone, patrz „Deferred”.
- Ładny układ linii ponad limitem (zachłanne cięcie, skalowanie) — taka linia nie jest dialogiem, który pole 3 wierszy potrafi pokazać.

## Authority i baseline

| Źródło | Rola |
|---|---|
| `diagnosis.md` (ten katalog) | pomiary, profil, przyczyna, górna granica korpusu |
| `AGENTS.md` (root), `anishift/services/subtitles/AGENTS.md`, `tests/AGENTS.md` | reguły kodu, logowania, testów i hooków |
| `docs/work/10-quality/text-layout.md` §5.1 | decyzja o pełnym przeglądzie dla dialogu — nie do zmiany tym planem |
| `anishift/services/subtitles/linebreak.py`, `service.py`, `types.py` | aktualny stan |

**Baseline:** `main` `4365a51`, czyste drzewo; `uv run pytest` zielony (PR #66 scalony).

**Znane wcześniejsze failures:** brak.

## Stan aktualny

### Obecne zachowanie

- `layout_dialogue` (`linebreak.py:58-75`) buduje słowa, pole, granice stylów, tabelę `_measure` wszystkich par (start, end) i woła `lay_out`, który przegląda wszystkie podziały na 1–3 wiersze. Bez ograniczenia na liczbę słów.
- Czas: 19 słów 0,04 s; 160 słów 1,4 s / 7,6 s (bez / z profilem); 320 słów 5,5 s / 42 s; 640 słów 38 s / 274 s; 1000 słów > 1000 s i 2,2 GB na samą tabelę `_measure`.
- Korpus: 22 439 linii dialogu, maksimum 19 słów / 143 znaki; 95% ≤ 10 słów.

### Root cause / gap

Brak granicy zaufania na wejściu: rdzeń liczy O(n²) kandydatów po O(n) każdy, a `_measure` buduje O(n²) wpisów po O(n) znaków. Dla dialogu (≤ 19 słów) to jest tanie i poprawne; dla linii o setkach słów to minuty i gigabajty. Szczegóły i linie w `diagnosis.md`.

### Istniejące rozwiązania do reuse

| Element | Ścieżka / symbol | Co wykorzystać | Ograniczenie |
|---|---|---|---|
| Pola jakości wyniku | `linebreak.DialogueLayout.approximate`, `.untagged` | wzór dla nowego pola `too_long: bool = False` | — |
| Liczniki raportu | `types.LayoutReport.dialogue_*`, `service._count_dialogue` | nowy licznik `dialogue_too_long`, jedna linia w `_count_dialogue` | `asdict(report)` idzie do logu automatycznie |
| Logger | `anishift.utils.logger.get_logger` | ostrzeżenie o fallbacku (reguła AGENTS: loguj fallbacki) | bez treści linii, tylko liczby |
| Stałe | `# ── Constants ──` w `linebreak.py` | `MAX_DIALOGUE_WORDS: Final[int]` z docstringiem pod stałą | hook `check_const_docstrings.py` |
| Fixture profilu | `tests/services/subtitles/test_subtitles_dialogue_layout.py::_profile` | test wydajności | — |

### Dowody

| Twierdzenie | Dowód | Status |
|---|---|---|
| Koszt O(n²) kandydatów × O(n) i tabela `_measure` O(n³) | `diagnosis.md`: tabele czasu, `cProfile` n = 160, `measure_build.py` | verified |
| Korpus dialogu ≤ 19 słów / 143 znaki | `corpus_lines.py` na 101 plikach, 22 439 linii | verified |
| Guard na początku `layout_dialogue` zwraca w ms dla 1000 i 5000 słów | `identity.py pathological 50`: 1000 słów 0,001–0,002 s, 5000 słów 0,009 s, oba tryby | verified |
| Wynik na korpusie identyczny z guardem (limit 50) | `identity.py workspace/ready 50`: 101 plików, 24 233 zdarzenia, 0 różnic w tekstach i raportach; 22 439 linii dialogu przez `layout_dialogue`, maks. 19 słów, guard 0 odpaleń; czcionki systemowe, 283 s na oba warianty | verified |
| Linia o 50 słowach kosztuje ≤ 0,45 s (pomiar zastępczy), 64 słowa ≤ 0,83 s | `bench.py 19 32 50 64` | verified |

## Zakres

### In scope

- Stała `MAX_DIALOGUE_WORDS` i guard w `layout_dialogue` (oba tryby: z profilem i bez).
- Pole `DialogueLayout.too_long`, licznik `LayoutReport.dialogue_too_long`, zliczanie w `_count_dialogue`, ostrzeżenie w logu.
- Testy: wydajność/fallback, granica limitu, licznik raportu.
- Jedna fraza w `anishift/services/subtitles/AGENTS.md` (punkt `linebreak.py`).

### Out of scope

- `fit_signs`, `tagged_measure`, `_measure` dla szyldów; `layout.py`; `geometry.py`; kalibracja wag.

### Forbidden

- Zmiana wyniku dla jakiejkolwiek linii o ≤ `MAX_DIALOGUE_WORDS` słowach (ani jednego bajtu).
- Dodawanie `Flag` do rdzenia układu (`Flag` zasila `HARMS` i kalibrację).
- Okno par w `_measure` według szerokości — zmienia wynik, gdy żaden układ się nie mieści (szerokości wierszy ponad `max_width` wchodzą do szkód `length_*` i porządkują kandydatów z `OUTSIDE`; przypadek realny: kotwica blisko krawędzi, test `test_layout_dialogue_fits_the_safe_area_from_the_event_anchor`).
- Edycja `pyproject.toml`, nowe zależności, zmiany poza `anishift/services/subtitles/` i `tests/services/subtitles/` (poza wierszem w `docs/README.md`, patrz decyzje lokalne).

### Deferred

- Ścieżka szyldów: `tagged_measure` → `_measure` ma tę samą tabelę O(n³) (11 s i 2,2 GB przy 1000 słów), a `fit_signs` dodaje `_programmed_widths` (O(n²) pomiarów) i DP. Korpus szyldów sięga 32 słów / 213 znaków, więc dziś nie boli; wymaga osobnej decyzji, co jest fallbackiem szyldu (skala, wiersze źródła). Osobny plan, jeśli właściciel zechce.
- Leniwa tabela `_measure` (pary liczone na żądanie) — bez limitu nie ogranicza czasu (sam przegląd kandydatów przy 1000 słów to ≈ 500 tys. × 0,16 ms ≈ 80 s), z limitem jest zbędna.

### Dozwolone decyzje lokalne

- Treść komunikatu ostrzeżenia i nazwy pól logu (bez treści linii, bez ścieżek).
- Nazwy testów, układ parametryzacji.
- Wiersz dla `15-layout-performance/` w tabeli workstreamów `docs/README.md` (jeśli orkiestrator chce mieć go w tym PR).

### Zatrzymaj się i wróć po decyzję, gdy

- Eksperyment tożsamości na korpusie pokaże różnicę w jakimkolwiek pliku.
- Istniejący test w `tests/services/subtitles/` wymaga zmiany asercji.
- Okaże się, że `tagged_line` albo `visible_text` przed guardem kosztują ponad 0,1 s dla 5000 słów (dziś 9 ms).

## Kontekst do przeczytania

| Kolejność | Źródło | Po co | Zakres odczytu |
|---|---|---|---|
| 1 | `AGENTS.md`, `anishift/services/subtitles/AGENTS.md`, `tests/AGENTS.md` | reguły | full |
| 2 | `.agents/skills/simple/SKILL.md`, `.agents/skills/coding/references/python.md`, `comments-docstrings.md`, `testing.md` | standard kodu i testów | full |
| 3 | `diagnosis.md` | przyczyna i liczby | full |
| 4 | `anishift/services/subtitles/linebreak.py` | miejsce zmiany | full (150 linii) |
| 5 | `anishift/services/subtitles/service.py` | `layout_translated`, `_count_dialogue`, `_write_laid_out` | linie 564-640, 682-685 |
| 6 | `anishift/services/subtitles/types.py` | `LayoutReport` | linie 112-131 |
| 7 | `tests/services/subtitles/test_subtitles_dialogue_layout.py` | wzór testów i `_profile` | full |

## Impact scan

| Kontrakt / subsystem | Ryzyko wpływu | Obowiązek regresyjny |
|---|---|---|
| `DialogueLayout` (frozen, slots) — nowe pole z domyślną wartością | porównania `DialogueLayout(text, flags)` w testach nadal równe | `test_layout_dialogue_breaks_a_new_translation_and_keeps_the_event_tags` |
| `LayoutReport` — nowe pole domyślne 0 | `LayoutReport(dialogue_unmeasured=4)` w testach nadal równe; log `asdict` dostaje nowe pole | `tests/services/subtitles/test_subtitles_translated_write.py` |
| `layout_translated` / `write_translated` / `normalize_subtitles` / `reflow_polish_dialogue` | brak zmiany dla ≤ limit | korpus `identity.py`, `tests/services/subtitles/` |
| `scripts/subtitle_quality/replay.py` i inne skrypty | brak: `LayoutReport` czyta tylko `service._write_laid_out` (`asdict` do logu) i testy równości w `tests/services/subtitles/` (`grep -rn LayoutReport anishift scripts tests`) | — |
| Ścieżka szyldów | nietknięta | — |

## Target design

### Odpowiedzialności i ownership

| Element | Odpowiada za | Owner danych/stanu | Nie odpowiada za |
|---|---|---|---|
| `linebreak.layout_dialogue` | odrzuca linię ponad limit przed `_measure` i `lay_out` | — | ładny układ takiej linii |
| `linebreak.MAX_DIALOGUE_WORDS` | jedyne źródło limitu | moduł `linebreak` | — |
| `service._count_dialogue` | zlicza `too_long` do raportu | `LayoutReport` | logowanie pojedynczej linii (robi `layout_dialogue`) |

### Przepływ

```text
layout_dialogue(event, text, profile)
-> tagged_line, visible_text, words (jak dziś)
-> len(words) > MAX_DIALOGUE_WORDS ?
     tak: logger.warning(words=len(words), limit=...) ; return DialogueLayout(tagged, frozenset(), too_long=True)
     nie: dalej jak dziś (dialogue_field / _measure / lay_out / reflow / without_wrap)
-> layout_translated -> _count_dialogue -> report.dialogue_too_long
-> _write_laid_out -> logger.info("Subtitle layout summarized", **asdict(report))
```

### Mapa plików

| Ścieżka | Operacja | Rola zmiany |
|---|---|---|
| `anishift/services/subtitles/linebreak.py` | MODIFY | stała, pole `too_long`, guard, logger |
| `anishift/services/subtitles/types.py` | MODIFY | `LayoutReport.dialogue_too_long: int = 0` |
| `anishift/services/subtitles/service.py` | MODIFY | jedna linia w `_count_dialogue` |
| `anishift/services/subtitles/AGENTS.md` | MODIFY | fraza o limicie w punkcie `linebreak.py` |
| `tests/services/subtitles/test_subtitles_dialogue_layout.py` | MODIFY | trzy nowe testy |
| `docs/README.md` | MODIFY (opcjonalnie) | wiersz workstreamu 15 |
| `anishift/services/subtitles/layout.py`, `geometry.py`, `fitting.py` | READ ONLY | — |

### Publiczne kontrakty

```text
MAX_DIALOGUE_WORDS: Final[int] = 50
"""Most words a dialogue line is laid out with; longer lines stay unbroken, since three lines cannot hold them."""

DialogueLayout.too_long: bool = False   # linia przekroczyła MAX_DIALOGUE_WORDS i została nierozbita
LayoutReport.dialogue_too_long: int = 0 # linie dialogu zostawione nierozbite przez limit słów

layout_dialogue(event, text, profile) -> DialogueLayout
  wejście ponad limit: text == tagged_line(event, text, profile) (bez \N, bez NO_WRAP),
                        flags == frozenset(), approximate == False, untagged == False, too_long == True
  wejście ≤ limit: bajt w bajt jak dotąd
```

Wartość 50: 2,6× maksimum korpusu (19), powyżej pojemności trzech wierszy dialogu (≈ 30–35 słów przy 0,9 szerokości ekranu i kolanie 56 znaków), a koszt najgorszej dopuszczonej linii to ≤ 0,45 s pomiarem zastępczym (64 słowa: 0,83 s). Mniejszy limit nic nie zyskuje na korpusie; większy tylko podnosi najgorszy przypadek. Docstring stałej ma mówić, co robi limit, nie historię kalibracji.

### Algorytm (guard)

Po wyliczeniu `words` w `layout_dialogue`, przed `if profile is None:` — obie gałęzie (SRT bez profilu i ASS z profilem) są objęte jednym warunkiem. Fallback nie woła `without_wrap` (libass ma zawinąć sam), nie liczy `approximate` ani `untagged` (nie ma czego raportować — linii nie mierzono). `tagged_line` zostaje przed guardem, bo fallback oddaje tekst z nałożonymi tagami; jego koszt dla 5000 słów to 9 ms.

Dlaczego guard w `layout_dialogue`, a nie w `lay_out`: tabela `_measure` (2,2 GB przy 1000 słów) powstaje w `layout_dialogue` zanim rdzeń ruszy, więc tylko tu guard chroni przed pamięcią; rdzeń nie zna tekstu z tagami, więc nie mógłby oddać fallbacku.

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
|---|---|---|
| 50 słów | układ jak dotąd, `too_long=False` | test graniczny |
| 51 słów | fallback, `too_long=True`, bez `\N` i `{\q2}` | test graniczny |
| 1000 słów (`"a b " * 500`), profil i bez | < 2 s, fallback | test wydajności |
| linia ponad limit z tagami `{\i1}` i `\h` | tekst to `tagged_line(...)` (tagi i `\h` zachowane) | asercja w teście fallbacku |
| `layout_translated` z jedną linią ponad limit | `report.dialogue_too_long == 1`, pozostałe liczniki dialogu bez zmian | test raportu |
| linia ≤ limit z korpusu | identyczny bajt w bajt | `identity.py` |

## Plan wykonania

### Faza 0 — Preflight

1. `git switch -c work/subtitles/03-dialogue-word-limit` z aktualnego `main`.
2. `uv run pytest tests/services/subtitles -q` — zielone jako baseline.

**Gate:** zielony baseline.

### Faza 1 — Testy (czerwone)

W `tests/services/subtitles/test_subtitles_dialogue_layout.py`, bez prozy, markery z `pyproject.toml`:

1. `@pytest.mark.integration` `test_layout_dialogue_leaves_a_line_over_the_word_limit_unbroken_within_the_time_budget`, parametryzacja `profile in (None, _profile())` (profil budowany w ciele testu albo przez `pytest.param` z lambda, żeby nie wołać `_profile()` przy kolekcji): `text = "a b " * 500`; `start = time.perf_counter()`; `layout = layout_dialogue(SSAEvent(text="x"), text, profile)`; asercje: `layout.too_long`, `"\\N" not in layout.text`, `not layout.text.startswith("{\\q2}")`, `time.perf_counter() - start < 2.0`. Budżet 2 s jest 500× poniżej dzisiejszego czasu, więc nie będzie flaky pod xdist.
2. `@pytest.mark.integration` parametryzowany `(words, too_long)` ∈ `{(MAX_DIALOGUE_WORDS, False), (MAX_DIALOGUE_WORDS + 1, True)}` na tekście `" ".join(["słowo"] * words)` z `_profile()`; asercja `layout.too_long is too_long`. (Linia o 50 słowach z profilem kosztuje ≈ 0,5 s, stąd `integration`.)
3. `@pytest.mark.unit` `test_layout_translated_counts_a_dialogue_line_over_the_word_limit`: `SSAFile` jak w `test_layout_translated_keeps_a_dialogue_line_equal_to_the_source_byte_for_byte`, tekst źródła `"x"`, przekład o `MAX_DIALOGUE_WORDS + 1` słowach; asercje `laid_out.report.dialogue_too_long == 1`, `"\\N" not in laid_out.subs.events[0].text`.

**Gate:** nowe testy czerwone (`AttributeError: too_long`), reszta zielona.

### Faza 2 — Implementacja

1. `linebreak.py`: import `from anishift.utils.logger import get_logger`; w `# ── Constants ──` dodać `MAX_DIALOGUE_WORDS: Final[int] = 50` z jednolinijkowym docstringiem pod stałą; `logger = get_logger(__name__)` po stałych; `DialogueLayout` dostaje `too_long: bool = False` (po `untagged`); w `layout_dialogue` po `words`:

   ```python
   if len(words) > MAX_DIALOGUE_WORDS:
       logger.warning("Dialogue line over the word limit left unbroken", words=len(words), limit=MAX_DIALOGUE_WORDS)
       return DialogueLayout(tagged, frozenset(), too_long=True)
   ```

   Docstring `layout_dialogue` uzupełnić o jedną frazę o limicie (nadal jedna linia, ≤ 120 znaków) albo zostawić, jeśli przestaje się mieścić — kontrakt niesie docstring stałej. `MAX_DIALOGUE_WORDS` do `__all__`.
2. `types.py`: `dialogue_too_long: int = 0` w `LayoutReport` (obok `dialogue_overflow`), docstring klasy bez zmian treści.
3. `service.py`: w `_count_dialogue` dodać `report.dialogue_too_long += dialogue.too_long`.
4. `anishift/services/subtitles/AGENTS.md`, punkt `linebreak.py`: dopisać „linia ponad `MAX_DIALOGUE_WORDS` (50) słów zostaje nierozbita bez `{\q2}` i liczy się w `dialogue_too_long`”.

**Inwarianty:** żadna inna linia `layout_dialogue` nie zmienia się; brak zmian w `layout.py`, `geometry.py`, `fitting.py`.

**Automatyczna kontrola:**

```text
uv run pytest tests/services/subtitles -q
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

**Gate:** wszystko zielone; nowe testy zielone.

### Faza 3 — Dowód tożsamości na korpusie

Skrypt `identity.py` ze scratchpadu diagnosty (ścieżka w `README.md`) albo jego odtworzenie w `scripts/tmp/`: dla każdego `workspace/ready/**/*.ass|*.srt` (tylko odczyt) `load_subtitles` → `split_subtitles` → `layout_translated(split, _source_texts(split), fonts=FontSources((), system_font_paths()), dialogue_font=None, own_text=True)` na `main` i na branchu; porównać listy `event.text` i `asdict(report)` (bez nowego pola). Jeśli wykonawca nie chce dwóch checkoutów, wystarczy monkeypatch oryginalnego `layout_dialogue` w jednym procesie, jak w `identity.py`.

**Gate:** 0 plików z różnicą; `max words` na korpusie < 50; guard nie odpalił ani razu.

### Faza 4 — Commit i PR

- Jeden commit: `perf(subtitles): leave a dialogue line over the word limit unbroken instead of enumerating its layouts` (scope `subtitles` z listy hooka; bez stopek AI).
- PR z `work/subtitles/03-dialogue-word-limit` do `main`; w opisie: tabela przed/po dla 1000 słów (> 1000 s → 2 ms), wynik tożsamości na korpusie (101 plików, 0 różnic), limit i jego uzasadnienie. Tytuł PR jak commit.
- Przegląd: zmiana w ścieżce danych wyjściowych (napisy) → autor + jeden świeży recenzent innego modelu (reguła krzyżowa z `AGENTS.md`), bez pętli ponad to, czego nie zamówi orkiestrator.

## Strategia dowodu

| Twierdzenie | Kontrola | Dlaczego wystarcza |
|---|---|---|
| 1000 słów w budżecie | test integracyjny z budżetem 2 s (dziś > 1000 s) | 500× margines, nie flaky |
| Granica limitu dokładna | test parametryzowany 50 / 51 | wykrywa off-by-one |
| Raport liczy fallback | test `layout_translated` | kontrakt raportu dla właściciela |
| Zero zmian dla realnych linii | istniejące testy + korpus `identity.py` | korpus maks 19 słów, guard nie odpala; testy chronią resztę ścieżki |
| Reguły repo | ruff, format, mypy, hooki pre-commit | strażnicy maszynowi |

### Regression obligations

- `tests/services/subtitles/` bez zmian asercji.
- `tests/services/subtitles/test_text_layout_catalogue.py` zielony (nie dotyka `layout_dialogue`, ale biegnie w pełnym `uv run pytest`).

### Human acceptance

Nie wymaga oceny wizualnej: linia ponad limitem nie występuje w korpusie, a dla linii z korpusu wynik jest identyczny. Właściciel zatwierdza wartość limitu (50) i kształt fallbacku (nierozbita, libass zawija) na podstawie tego planu.

## Ryzyka i reakcje

| Ryzyko | Jak rozpoznać | Reakcja | Kiedy eskalować |
|---|---|---|---|
| Prawdziwy dialog > 50 słów w przyszłym pliku | `dialogue_too_long > 0` w logu podsumowania | linia zostaje czytelna (libass zawija), lektor czyta normalnie; właściciel decyduje, czy podnieść limit | gdy pojawi się na realnym odcinku |
| Test z budżetem czasu flaky na CI (Windows runner) | sporadyczny fail > 2 s | podnieść budżet do 5 s (marker `integration` to < 5 s) | gdy fail wystąpi dwa razy |
| `replay.py` lub inny konsument porównuje raport jako pełny słownik z zapisanym plikiem | fail testu/skryptu po dodaniu pola | pole domyślne 0 — dopisać do zapisu | gdy porównanie jest z zamrożonym JSON |
| Logowanie w `linebreak.py` łamie konwencję „czyste helpery bez loggera” | review | fallback to przejście stanu, więc log jest zgodny z regułą; jeśli recenzent woli, log przenieść do `_count_dialogue` w `service.py` | — |

## Definition of Done

- [ ] guard, pole, licznik, log, AGENTS.md;
- [ ] trzy testy zielone, reszta bez zmian;
- [ ] cztery bramki zielone;
- [ ] korpus: 0 różnic, guard 0 odpaleń;
- [ ] jeden commit `perf(subtitles): …` na `work/subtitles/03-dialogue-word-limit`, PR otwarty, przegląd krzyżowy wykonany.

## Kontrakt wyniku

```text
status
czasy przed/po dla 1000 słów (oba tryby)
wynik identity na korpusie (plików, zdarzeń, różnic, max words)
wynik bramek (komendy i exit code)
commit sha, branch, link PR
odchylenia od planu
```
