---
kind: plan
status: draft v2 (po przeglądzie astra, sol6, claude)
baseline: work/quality/08-fuzzy-quality @ e1cefac (+ commit dokumentów v2)
created: 2026-10-18
---

# Plan: rozmyte układanie napisów, pomiar prawdziwą czcionką i czcionka dialogów

## Cel

Zastąpić sztywne heurystyki napisów heurystykami ze specyfikacji (szyldy, łamanie) i najtańszymi skutecznymi poprawkami (lektor, kursywa i kolory), oprzeć układ na pomiarze tekstu prawdziwą czcionką odcinka, dodać czcionkę dialogów właściciela dołączaną do MKV, naprawić czcionki przy wypalaniu MP4 i uporządkować kod tak, żeby każda heurystyka miała jedno miejsce i jedno źródło prawdy.

## Rezultat użytkownika

W mpv: szyldy w czcionkach typesettera, które nie wychodzą poza ekran, nie zlewają się z sąsiednimi napisami i nie są niepotrzebnie zmniejszane; dialogi w czcionce właściciela, bez mieszania krojów w polskich literach, łamane po sensie i najwyżej w dwóch wierszach (trzy tylko w ratunku); lektor czytający kwestie w stylach `Alt`, a nie szyldy i piosenki; kursywa i kolory na właściwych słowach; MP4 w tych samych czcionkach co MKV.

## Warunek wejścia

Właściciel 18.10: implementacja rusza, gdy plan zaakceptują trzej recenzenci (astra, sol6, claude); otwarte pytania dostają wartości domyślne (rekomendacje przyjęte 18.10), a ostateczną akceptację właściciel daje na galerii przed/po. Właściciel 18.10 polecił też uruchomić „armię subagentów Opus 5.5 w harnessie Claude Code”, co dla tego planu znosi limit dwóch równoległych instancji jednego modelu z `AGENTS.md`. Zasada krzyżowa zostaje: autor = Claude Opus 5.5, przegląd = świeża instancja z innej rodziny (astra albo sol6, naprzemiennie).

## Warunki końcowe

- [ ] Wymagania [visual-quality.md](../visual-quality.md) v2.1 spełnione na galerii przed/po na tym samym tekście, ocenionej przez orkiestratora (zapis w `reviews/`) i właściciela; punkty jawnie odłożone (§7.4, zmiana liczby wierszy szyldu) nie są warunkiem końcowym.
- [ ] Pomiar przechodzi test regresji wobec libass na 36 parach: szerokość p90 ≤ 1,5% i p99 ≤ 4% (zdarzenia statyczne ≥ 100 px), wysokość p90 ≤ 5%, liczba wierszy po zawinięciu zgodna w 12/12 znanych przypadkach auto-wrap; `\q2` i marginesy w osobnych przypadkach kontrolnych.
- [ ] Szyldy statyczne zmierzone prawdziwym fontem: 0 przyrostów wyjścia poza ekran i kolizji w renderze libass wyników, gdy istniał dopuszczalny kandydat (kryterium §D specyfikacji szyldów).
- [ ] Bramki: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`, `uv run mypy anishift/ tests/`, `uv run mypy --platform linux anishift/ tests/`, `uv run pytest` (wyjątek: testy prywatnego qBittorrent w worktree, przechodzą w głównym checkoucie).
- [ ] Legacy z D10 usunięte, nie zostawione obok nowego kodu.
- [ ] Nic nie trafiło do `main` bez akceptacji właściciela.

## Nie-cel

Przesuwanie napisów; analiza obrazu; limit długości tłumaczenia; pełna reguła B (dialogowość 0–1) i pełne C (StyleState, T1/T2) — odłożone z dowodem w aneksie v4 specyfikacji; zmiana liczby wierszy szyldu wielowierszowego; osadzone `[Fonts]` ASS; głośność lektora i timing; Linux; `scripts/slime_*.py`.

## Authority i baseline

| Źródło | Rola |
| --- | --- |
| [visual-quality.md](../visual-quality.md) v2.1 | wymaganie nadrzędne |
| [fuzzy-signs-and-split.md](../fuzzy-signs-and-split.md) z **aneksem v4** | mechanika A (szyldy), wariant minimalny B i C |
| [fuzzy-line-breaks.md](../fuzzy-line-breaks.md) z **aneksem v4** | mechanika łamania |
| research: [code-map](../research/code-map.md), [measurement](../research/measurement.md), [fonts](../research/fonts.md), [typesetting-principles](../research/typesetting-principles.md), [split-and-styles](../research/split-and-styles.md) | stan kodu i dowody |
| przeglądy `reviews/01-plan-{astra,sol6,claude}.md` | uwagi zamknięte w v2 (tabela na końcu) |
| `AGENTS.md`, skille `simple`, `coding` (+ `references/python.md`, `comments-docstrings.md`, `testing.md`), `workflow`, `subagent`, `review` | reguły pracy i kodu |

**Baseline:** `work/quality/08-fuzzy-quality`, worktree `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift-wt\fuzzy`. Kod = `2301cd0` (nocne poprawki + specyfikacje); późniejsze commity to wyłącznie dokumenty.

**Znane failures:** nocne poprawki miały sztywne progi i trzy widoczne pogorszenia (szyldy 03, 04; łamanie 05, 06); agenci opisywali obrazy zbyt optymistycznie; równoległe pełne pytest przeciążały CPU; testy qBittorrent nie startują w worktree.

## Stan aktualny (skrót; szczegóły i plik:linia w code-map.md)

- Szyld: Arial 64 px, tolerancja 3%, podłoga 72%, wspólna skala osi, bez filtrów ekranu i kolizji (sąsiednie szyldy się zlewają: „piętnastyPojawił”).
- Lektor: punktowy klasyfikator stylów + korekty per linia; 9 zgubionych kwestii `Alt`; fallback czyta piosenki NC/ED; klasyfikacja trzy razy na różnych plikach; chóry w różnych stylach czytane dwa razy (26 par).
- Style: 869 fałszywych zakresów z bloków komentarzy; T3 gubi 447 akcentów.
- Łamanie: `translation/linebreak.py`, rankingi krotkami po znakach; układ w `translation_verses` przed writerem.
- Czcionki: aplikacja nie zna czcionek odcinka; mkvmerge kopiuje załączniki źródła; Gandhi Sans (20/40 par) bez polskich liter; wypalanie MP4 bez `fontsdir` rysuje Arialem.

### Reuse

| Element | Źródło | Wykorzystanie |
| --- | --- | --- |
| Estymator pomiaru | `workspace/.quality/experiments/research-measurement/measure_lib.py` | algorytm i stałe D1 → przepisać do `services/fonts` i `subtitles/geometry.py` wg `coding`, z testami |
| Dopasowanie czcionek | `.../research-fonts/inventory.py` | reguły D2 |
| Skalowanie tagów | `fitting.py` `_RE_SCALING`, `_scale_text` | z osobnymi `fx`, `fy` |
| Szerokość ekranu | `fitting.py` `_play_width` | do `geometry.py` |
| Listy językowe | `linebreak.py` l.30–270 + helpery | do `lexicon.py` |
| Grafemy, granice | `anishift/text/graphemes.py`, `boundaries.py` | jedyne źródła |
| Parowanie zdarzeń | `scripts/subtitle_quality/metrics.py::pair_events` (l.236) | replay |
| Ekstrakcja załączników | `scripts/subtitle_quality/render.py::extract_attachments` (l.122) | przenieść do `services/extraction`, skrypt woła produkcję |
| Galerie przed/po | `workspace/.quality/experiments/visual-fixes/*/*.py` | `compare.py` |
| Wariant minimalny B | `.../research-split/minimal.py` | reguły aneksu v4 B |
| Ustawienia | `config/user_settings.py`, `field_catalog.py`, wzorzec `subtitle_max_chars_per_line` | pole `dialogue_font_file` |

## Decyzje

- **D1. Pomiar:** metoda z aneksu v4 A.3 specyfikacji szyldów (Pillow + fontTools, 1000 px, atrament, widoczny obrys/cień, blur 1,83σ, BS3, synteza kursywy, bez kerningu).
- **D2. Dopasowanie czcionek:** aneks v4 A.3 (p3 ID1, ID4, PS; wariant jak libass; czcionki odcinka przed systemowymi; brakujący glif: rodzina, potem Arial).
- **D3. Czcionki odcinka w produkcji (zasób bez nowego rodzaju artefaktu):** planer dodaje do `TRANSLATE_SUBTITLES` i `NORMALIZE_SUBTITLES` **opcjonalne** drugie wejście: kontener źródłowy grupy (MKV), gdy grupa go ma. Handler wyciąga jego załączniki przez `extraction.extract_attachments(container, staging/fonts)` (idempotentnie, katalog stagingu zadania; przy wznowieniu zadanie odtwarza go samo) i buduje `FontSources`. Bez kontenera (sidecar bez MKV, samodzielny ASS): tylko czcionka dialogów i systemowe, statusy przybliżone tam, gdzie rodziny brak. Wypalanie MP4: composition wyciąga załączniki z kontenera, który i tak dostaje, i przekazuje `fonts_dir` (z czcionką dialogów).
- **D4. Układ tylko w writerze, jedna publiczna funkcja:** `layout_translated(...)` (kontrakt niżej) przyjmuje nierozbity przekład (z odtworzonymi znacznikami) i robi kolejno: podmiana stylu dialogów → tekst i tagi → łamanie dialogu → dopasowanie szyldów (raz na plik) → raport. `write_translated*` i normalizacja polskiego źródła wołają ją; `translation_verses` przestaje układać. F0 przenosi dzisiejszy algorytm układu do tej funkcji **bez zmiany wyniku**, U5 i U4 wymieniają tylko jego wnętrze.
- **D5. Decyzje lektora raz, na źródle:** aneks v4 B pkt 6.
- **D6. Lektor i style w wariantach minimalnych:** aneks v4 B pkt 1–5 i C pkt 1–2.
- **D7. Czcionka dialogów przez klon stylu:** dla każdego stylu z większością linii spoken tworzymy klon `"<styl> (dialog)"` (przy kolizji nazwy kolejny sufiks) z `Fontname` = p3 ID1 czcionki właściciela, resztą pól bez zmian; linie spoken przechodzą do klonu, a `\r<styl>` w nich wskazuje klon. Linie displayed zostają w stylu oryginalnym, bajtowo identyczne. Pole ustawień `dialogue_font_file` (ścieżka, puste = wyłączone), walidacja przy zapisie w panelu (czytelny plik, p3 ID1, 18 polskich liter w każdym dołączanym wariancie) i przy planowaniu (nieblokujące ostrzeżenie planu `dialogue_font_unusable`, wzorzec `displayed_cues_absent`). Warianty: pliki z katalogu wskazanego pliku o tej samej rodzinie p3 ID1, każdy z polskimi literami. Do MKV `--attach-file` dla każdego wariantu, z pominięciem pliku o tej samej zawartości (sha256) co załącznik źródła; przy tej samej nazwie i innej zawartości `--attachment-name` z sufiksem. SRT bez zmian.
- **D8. Łamanie:** specyfikacja + aneks v4 LB: ratunek ≤ 2 wiersze z ochronami → ≤ 2 z rozluźnionymi → 3 wiersze → `overflow_unavoidable`; cięcie po słowie jednoliterowym chronione (SYN = 1); SHAPE pomija parę wierszy rozdzieloną mocną granicą. Przeliczenie 01–39 (`model-v32.md`): zmieniają się tylko 07 (na 2 wiersze) i 18 (na rekomendację B); 37 i 38 wygrywają cięciem po przecinku. SRT pisane z ASS dostaje układ mierzony profilem stylu źródła (te same podziały co ASS); SRT ze źródła SRT: tryb `unmeasured` (bez stylów nie ma czego mierzyć).
- **D9. Struktura** (drzewo niżej): nowa domena `services/fonts/`; w `services/subtitles/` moduły `fuzzy`, `geometry`, `lexicon`, `layout`, `restyle`; `linebreak.py` z `translation/` do `subtitles/`; `layout_config.py` dzielony (limity układu → `subtitles/layout.py`, rozmiar kawałka tłumaczenia zostaje w `translation/`); `scripts/quality` → `scripts/subtitle_quality`, testy → `tests/scripts/subtitle_quality/`.
- **D10. Legacy do usunięcia:** w `fitting.py` pomiar Arialem i stałe `_MIN_SCALE`, `_WIDTH_TOLERANCE`, `_FONT_SIZE`, wspólny czynnik osi, `_pixel_scale`, `_wraps_only_translation`, `_reflow`, `_BALANCED_LINES`, `fit_sign_text`; w `linebreak.py` `_dialogue_cut`, `_dialogue_candidates`, `_TOP_HEAVY_PENALTY`, `_OVERFLOW_TOLERANCE`, rekurencyjny `_split`, `_best_cut`, `_weight`, `_greedy_cut`, `_proportional_boundaries`, `split_for_layout` po przejściu na `split_lines`; `service.py` `reflow_polish_dialogue`, `preview_styles`, `write_translated_spoken` i `write_translated_displayed`, jeśli po usunięciu adaptera nie mają konsumentów; układ w `translation_handler.translation_verses`; `subtitle_handler.LegacySubtitleProducts/Adapter`; w `text.py` własne grafemy, martwe `insertions`, `_RE_DRAW_TAG`; `classifier.py` `_RE_DRAW` (duplikat `is_drawing`); import `SENTENCE_ENDINGS` przez `translation.chunking`; `composition/fonts.py` diagnostyka po nazwach plików → rodziny z `services/fonts`; w narzędziu `render.py` `_RE_INLINE_FONT`, `prepare_fonts`, `extract_attachments`, `event_fonts` i domyślne `PlayRes` w `metrics.py` → moduły aplikacji. `Category` zostaje (ma konsumentów, wariant minimalny B go używa).
- **D11. Raport:** jeden typ `LayoutReport` (kontrakt niżej) zwracany przez `layout_translated`; writer loguje jedno strukturalne podsumowanie na plik (`get_logger`, bez tekstów i ścieżek absolutnych); narzędzie jakości czyta ten sam obiekt z `layout_translated`, nie liczy drugi raz.
- **D12. Wartości domyślne pytań otwartych** (do czasu galerii): LB §5: 1–5 i 8 — wybory modelu po przeliczeniu `model-v32.md` (07 pod regułą ratunku, pytanie 3 w visual-quality §12), 6 — pomiar D1 i τ = 0,98, 7 — filtr `unmeasured` jako jawny wyjątek tylko bez profilu, 9 — `max_chars_per_line` tylko w `unmeasured`; E1–E9 wg aneksu v4; visual-quality §12: 1–2 do kalibracji na galerii, 4 bez limitu, 5 właściciel wskazuje plik, 6 bez zmiany czcionki szyldu.

## Zakres

### In scope
D1–D12, testy, replay, galerie, aktualizacja `AGENTS.md` obszarów (`subtitles`, nowe `fonts`, `composition`, `extraction`, `scripts`), README/ustawienia panelu dla nowego pola, wartość domyślna nowego pola dla zapisanych planów.

### Forbidden
- Ręczna edycja `pyproject.toml`/`uv.lock` (tylko `uv add fonttools`).
- Commity na `main`, merge do `main`, push.
- Zmiany w głównym checkoucie `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift` poza `workspace/.quality/` (może z niego działać rezydent właściciela).
- Płatne API (tłumaczenie, TTS) bez zgody orkiestratora.
- Zabijanie procesów python; więcej niż jeden pełny `pytest` naraz na maszynie (`-n 8`, uzgodnione z orkiestratorem).
- Zmiana kontraktu publicznego z tego planu bez zgody orkiestratora; komentarze opisowe w kodzie; wielolinijkowe docstringi bez potrzeby; `except Exception`; druga wersja istniejącego helpera.

### Deferred
Pełne B i C; usuwanie wyróżnienia pominiętego przez tłumacza; osadzone `[Fonts]`; zmiana liczby wierszy szyldu; korekta wielkości czcionki dialogów; zastępcza czcionka szyldów bez polskich liter; przenoszenie dialogu do góry; limit długości tłumaczenia.

### Dozwolone decyzje lokalne
Prywatne funkcje, cache, kolejność testów, nazwy prywatnych helperów — przy zachowaniu kontraktów.

### Zatrzymaj się i wróć po decyzję, gdy
kontrakt jest niewykonalny; test regresji pomiaru nie spełnia progów; potrzebna zmiana planera poza D3/D5/D7; galeria pokazuje pogorszenie bez uzasadnienia ważeniem cech; replay F0 nie jest bajtowo identyczny.

## Kontekst do przeczytania (każdy wykonawca)

| Kolejność | Źródło | Zakres |
| --- | --- | --- |
| 1 | `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\.agents\skills\simple\SKILL.md`, `coding\SKILL.md`, `coding\references\python.md`, `comments-docstrings.md`, `testing.md` (`.agents/` nie jest widoczne w worktree) | full |
| 2 | `AGENTS.md` root, `anishift/AGENTS.md`, `tests/AGENTS.md`, AGENTS.md obszaru | full |
| 3 | ten plan | full |
| 4 | `visual-quality.md` | full |
| 5 | aneks v4 i sekcja specyfikacji jednostki | section |
| 6 | research jednostki | full |

## Impact scan

| Kontrakt / subsystem | Ryzyko | Obowiązek regresyjny |
| --- | --- | --- |
| Writer (`layout_translated`, `write_translated*`) | wysokie | replay 36 par: liczba zdarzeń wejście = wyjście; napisy identyczne z EN bajtowo identyczne (poza klonem stylu dialogów) |
| Planer (opcjonalne wejścia D3/D5, ostrzeżenie D7, snapshot pola) | średnie | `test_planner.py`, `test_auto_preset_smoke.py`: grupa z MKV, sidecar bez MKV, gotowy PL, regeneracja w `ready/`, wznowienie |
| Tłumaczenie | średnie | `test_translate_only.py`, `test_translation_layout_wiring.py` |
| TTS | niskie | `test_execution_handlers.py` (SPOKEN_PL vs FULL_PL vs SOURCE) |
| Composition | niskie | `test_composition_commands.py`: `--attach-file`, `--attachment-name`, `fontsdir`; `mkvmerge -J` na wyniku |
| Ustawienia/panel | niskie | testy `config/`, `cli/interactive` |
| Wydajność | niskie | czas replay 36 par w raporcie U1 |

## Target design

### Przepływ danych

```text
kontener MKV (opcjonalnie) ──extract_attachments──> staging/fonts
źródło ASS/SRT ─split_subtitles─> decyzje (wariant minimalny B)                     [D5, D6]
  └─marked_text (wariant minimalny C) -> tłumaczenie -> restore_markers             [tekst nierozbity, D4]
layout_translated(split, przekład, FontSources, limits, dialogue_font):
  1 restyle_dialogue (klon stylu)                                                   [D7]
  2 profile = RenderProfile.from_subs(restyled, FontIndex(FontSources + plik dialogów))
  3 per zdarzenie: replace_visible_text (C)
  4 dialog: layout_dialogue(event, tekst, profile, limits)                           [LB]
  5 szyldy: fit_signs(source, target, indeksy szyldów, profile)                      [A]
  -> TranslatedLayout(subs, report)
FULL_PL -> SPLIT_SUBTITLES(FULL_PL, opcjonalnie źródło) -> SPOKEN_PL / DISPLAYED_PL  [D5]
TTS(SPOKEN_PL bez reklasyfikacji) ; composition: mkvmerge (+ czcionka dialogów) / ffmpeg (fontsdir)
```

### Docelowe drzewo

```text
anishift/
├── text/                                 # KEEP
├── services/
│   ├── fonts/                            # NEW: __init__, index, metrics, types, AGENTS.md
│   ├── extraction/service.py             # MODIFY: extract_attachments
│   ├── subtitles/
│   │   ├── __init__.py                   # MODIFY
│   │   ├── service.py                    # MODIFY: load, split, layout_translated, writery; − reflow_polish_dialogue, − preview_styles
│   │   ├── types.py                      # MODIFY: LayoutReport, TranslatedLayout, FontSources
│   │   ├── fuzzy.py                      # NEW
│   │   ├── geometry.py                   # NEW
│   │   ├── classifier.py                 # MODIFY (wariant minimalny B)
│   │   ├── text.py                       # MODIFY (wariant minimalny C; − grafemy, − martwy kod)
│   │   ├── lexicon.py                    # NEW
│   │   ├── linebreak.py                  # NEW tu (przeniesiony, przepisany wg LB)
│   │   ├── layout.py                     # NEW
│   │   ├── fitting.py                    # MODIFY (przepisany wg A)
│   │   ├── restyle.py                    # NEW
│   │   └── AGENTS.md                     # MODIFY
│   ├── translation/linebreak.py          # DELETE
│   ├── translation/layout_config.py      # MODIFY (tylko rozmiar kawałka)
│   └── composition/{types,commands,fonts,service}.py   # MODIFY
├── application/{planner,translation_handler,subtitle_handler,tts_handler,composition_handler,runtime}.py  # MODIFY
└── config/{user_settings,field_catalog}.py              # MODIFY
scripts/quality/ → scripts/subtitle_quality/ (+ calibrate.py, replay.py, compare.py)
tests/services/fonts/ (NEW), tests/services/subtitles/ (MODIFY/NEW), tests/scripts/subtitle_quality/ (NEW, przeniesione)
```

### Publiczne kontrakty

Wiążące. F0 tworzy je z implementacją zachowującą dzisiejszy wynik (pomiar Arialem przeniesiony z `fitting.py`, układ przeniesiony z `translation_verses`, `split_lines` delegujące do dzisiejszego cięcia). Jednostki wymieniają wnętrza.

```python
# anishift/services/fonts/types.py  (właściciel: U1; F0 tworzy plik z typami)
@dataclass(frozen=True, slots=True)
class FontFace:
    path: Path; face_index: int
    family_names: frozenset[str]   # p3 ID1, casefold
    full_names: frozenset[str]     # p3 ID4, casefold
    postscript_name: str | None    # casefold; dopasowanie ID4 vs PS wg rodzaju obrysów jak libass
    weight: int; bold: bool; italic: bool; units_per_em: int; ascent: int; descent: int
    postscript_outlines: bool      # CFF/CFF2: dopasowanie po PS i pochylenie sztucznej kursywy tan 10° jak libass
    codepoints: frozenset[int]
@dataclass(frozen=True, slots=True)
class FontMatch:
    face: FontFace; exact: bool; synthetic_bold: bool; synthetic_italic: bool
    requested_weight: int; requested_italic: bool   # żądanie, z którego glyph_match dobiera krój zastępczy

# anishift/services/fonts/index.py  (U1)
def read_faces(path: Path) -> tuple[FontFace, ...]
def polish_missing(face: FontFace) -> str                      # brakujące z „ąćęłńóśźżĄĆĘŁŃÓŚŹŻ”
def family_name(path: Path) -> str                            # p3 ID1 w oryginalnej pisowni (Fontname klonu stylu, U6)
class FontIndex:
    @classmethod
    def build(cls, episode: Iterable[Path], system: Iterable[Path]) -> FontIndex   # dwa poziomy, D2
    def match(self, name: str, *, weight: int, italic: bool) -> FontMatch | None
    def glyph_match(self, request: FontMatch, codepoint: int) -> FontMatch

# anishift/services/extraction/service.py  (F0 przenosi z narzędzia)
def extract_attachments(container: Path, dest: Path) -> tuple[Path, ...]

# anishift/services/subtitles/types.py  (F0)
@dataclass(frozen=True, slots=True)
class FontSources:
    episode: tuple[Path, ...]        # załączniki + pliki czcionki dialogów
    system: tuple[Path, ...]
@dataclass(slots=True)
class LayoutReport:                  # liczniki D11; jednostki tylko inkrementują swoje pola
    signs_fitted: int = 0; signs_fallback_screen: int = 0; signs_fallback_collision: int = 0
    signs_approximate: int = 0; sign_dialogue_collisions: int = 0
    dialogue_unmeasured: int = 0; dialogue_relaxed_phrases: int = 0; dialogue_three_lines: int = 0
    dialogue_overflow: int = 0; fallback_glyph_events: int = 0; restyled_styles: int = 0
@dataclass(frozen=True, slots=True)
class TranslatedLayout:
    subs: SSAFile; report: LayoutReport

# anishift/services/subtitles/service.py  (F0)
def layout_translated(
    split: SubtitleSplit,
    translations: Mapping[int, str],            # indeks zdarzenia Dialogue -> przekład nierozbity; klucze: pierwsze zdarzenie
                                                # każdej SpokenLine i każde zdarzenie displayed; kopie serii (FBF, kopie
                                                # w innych stylach) uzupełnia layout_translated
    *, fonts: FontSources | None, limits: LayoutLimits, dialogue_font: DialogueFont | None,
) -> TranslatedLayout
# write_translated / write_translated_spoken / write_translated_displayed: ten sam zestaw argumentów + dest

# anishift/services/subtitles/geometry.py  (F0 typy + pomiar Arialem; U1 wnętrze wg D1)
@dataclass(frozen=True, slots=True)
class Rect: left: float; top: float; right: float; bottom: float
@dataclass(frozen=True, slots=True)
class RenderProfile:
    play_res_x: int; play_res_y: int; wrap_style: int; scaled_border: bool
    styles: Mapping[str, SSAStyle]; fonts: FontIndex | None
    kerning: bool = False                         # nagłówek `Kerning: yes` → pomiar przybliżony (U1b)
    @classmethod
    def from_subs(cls, subs: SSAFile, fonts: FontIndex | None) -> RenderProfile
@dataclass(frozen=True, slots=True)
class TextBox:
    line_widths: tuple[float, ...]; width: float; height: float
    edge: float                                   # nieskalujący się obrys/cień/blur w poziomie
    status: Literal["exact", "approximate"]; fallback_glyphs: int
def measure_text(event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0) -> TextBox
def available_width(event: SSAEvent, profile: RenderProfile) -> float
def wrap_text(event: SSAEvent, text: str, profile: RenderProfile) -> str          # emulacja zawijania libass
def screen_rects(event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0) -> tuple[Rect, ...]
    # prostokąt(y) atramentu na ekranie: kotwica \pos/\an/marginesy; dla \move i \t stan początkowy i końcowy

# anishift/services/subtitles/fuzzy.py  (F0)
def rise(x: float, a: float, b: float) -> float
def fall(x: float, a: float, b: float) -> float
def nor(*degrees: float) -> float

# anishift/services/subtitles/layout.py  (F0)
@dataclass(frozen=True, slots=True)
class LayoutLimits: max_chars: int; max_lines: int          # z dzisiejszego LayoutConfig

# anishift/services/subtitles/linebreak.py  (F0 deleguje do dzisiejszego kodu; U5 przepisuje)
@dataclass(frozen=True, slots=True)
class DialogueLayout: text: str; flags: frozenset[str]   # "unmeasured", "relaxed_phrases", "three_lines", "overflow_unavoidable"
def layout_dialogue(event: SSAEvent, text: str, profile: RenderProfile | None, limits: LayoutLimits) -> DialogueLayout
def split_lines(event: SSAEvent, text: str, count: int, profile: RenderProfile | None) -> tuple[str, ...] | None
    # najlepszy podział na dokładnie `count` wierszy wg ocen LB (dla szyldów: D i źródło wielowierszowe)

# anishift/services/subtitles/fitting.py  (F0 deleguje do dzisiejszego kodu; U4 przepisuje)
def fit_signs(source: SSAFile, target: SSAFile, signs: Sequence[int], profile: RenderProfile, report: LayoutReport) -> dict[int, str]
    # source = źródło (wzorzec geometrii), target = plik z ostatecznymi tekstami dialogów i szyldów (sąsiedzi kolizji),
    # signs = indeksy zdarzeń do dopasowania; zwraca nowe teksty szyldów

# anishift/services/subtitles/restyle.py  (F0: DialogueFont + tożsamość; U6 implementacja)
@dataclass(frozen=True, slots=True)
class DialogueFont:
    family: str; files: tuple[Path, ...]
    @classmethod
    def from_file(cls, path: Path) -> DialogueFont         # SubtitleError: brak pliku, nazwy p3 ID1 lub polskich liter
def restyle_dialogue(subs: SSAFile, decisions: Sequence[Decision], font: DialogueFont, report: LayoutReport) -> SSAFile
```

`Decision`, `SubtitleSplit`, `split_subtitles`, `restore_markers` zachowują dzisiejsze sygnatury publiczne. F0b dodaje styl bazowy do dwóch operacji C i przekazuje go we wszystkich wywołaniach (handler tłumaczenia, writer, normalizacja):

```python
# anishift/services/subtitles/text.py  (F0b: parametr i przekazanie; U3: użycie)
def marked_text(text: str, style: SSAStyle | None = None) -> str
def replace_visible_text(text: str, new_text: str, style: SSAStyle | None = None) -> str
```

### Edge cases i failures

| Przypadek | Oczekiwane zachowanie | Dowód |
| --- | --- | --- |
| Rodzina nieobecna w czcionkach odcinka i systemie | Arial jak libass, status przybliżony, licznik | automated |
| Glif spoza `cmap` (Gandhi Sans) | krój tej rodziny z glifem, potem Arial; licznik | automated |
| `Kerning: yes`, zdarzenie animowane, niezmierzone | status przybliżony, osobne liczniki | automated |
| Brak kontenera (sidecar, samodzielny ASS) | czcionka dialogów + systemowe, statusy przybliżone | automated |
| Plik czcionki dialogów zniknął lub bez polskich liter | brak klonu, ostrzeżenie planu, praca trwa | automated |
| Załącznik źródła o tej samej zawartości / nazwie | pominięcie / `--attachment-name` z sufiksem | automated |
| Linia szyldu z `\r` w stylu z liniami dialogu | styl oryginalny, bajtowo identyczna | automated |
| FULL_PL bez źródła, różna tożsamość zdarzeń | klasyfikacja FULL_PL + ostrzeżenie | automated |
| Dwa wiersze nie mieszczą się | ratunek wg D8, flaga w raporcie | automated |
| Przypadki 05/06 (przecinek kontra krótsze cięcie) | wg `model-v32.md` i aneksu LB | automated + human |
| Sąsiednie szyldy („piętnastyPojawił”) | wariant bez kolizji | automated + human |
| Chór w dwóch stylach | czytany raz | automated |

## Plan wykonania

Każda jednostka: osobny worktree i gałąź od aktualnego `work/quality/08-fuzzy-quality` (z junctionami `workspace\.quality` i `external\bin\*` oraz kopią `.env`, jak `AniShift-wt/fuzzy`); autor Claude Opus 5.5; przegląd astra albo sol6; poprawki autora; weryfikacja recenzenta; orkiestrator scala do 08 i rozwiązuje konflikty. Commity po temacie, `typ(scope): opis` ze scope z `scripts/hooks/check_commit_msg.py`, bez stopek AI, bez `--no-verify`.

### Fala 0 (równolegle)

**F0a — przebudowa mechaniczna** (`work/quality/09-restructure`): **pierwszy commit** to `scripts/quality/replay.py` z adapterem do dzisiejszej ścieżki (`split_subtitles` → `translation_verses` → `write_translated`) i parowaniem `pair_events`; uruchomiony na niezmienionym kodzie zapisuje katalog „baseline” w `workspace/.quality/experiments/replay/baseline/`. Dalej: `uv add fonttools`; przeniesienie `linebreak.py` i podział `layout_config.py` (D9) z testami; `scripts/quality` → `scripts/subtitle_quality` z testami i odwołaniami w aktywnych dokumentach; usunięcie martwego i zdublowanego kodu z D10, które nie zależy od nowych modułów (grafemy, `insertions`, `_RE_DRAW*`, import granic, `LegacySubtitleAdapter`, `preview_styles`); `fuzzy.py` z testami. Grafemy: definicja `\X` różni się od własnej dla rzadkich klastrów; dopuszczalne, jeśli replay korpusu jest identyczny — odchylenie zapisać. **Gate:** bramki zielone; replay po F0a bajtowo identyczny z „baseline” dla wszystkich sparowanych par.

**U1a — domena czcionek** (`work/quality/10-fonts`, tylko nowe pliki): `services/fonts/{types,index,metrics,__init__,AGENTS.md}` wg D1/D2, `tests/services/fonts/` na plikach z `workspace/.quality/library/*/fonts`, `corpus-pairs/*/fonts` i folderu mpv właściciela (testy pomijane, gdy danych brak — wzorzec z `tests/AGENTS.md`). **Gate:** bramki zielone, testy odtwarzają przypadki z logów libass (Gandhi Sans → Arial dla `ż`, Comic Sans warianty, Officina „PL Book” → Bold).

### Fala 0b (po scaleniu F0a i U1a)

**F0b — zamknięty pion** (`work/quality/11-contracts`): kontrakty z sekcji wyżej z implementacją zachowującą wynik; `layout_translated` z dzisiejszym układem przeniesionym z `translation_verses`; `translation_handler` oddaje nierozbity przekład; `extract_attachments` w `extraction` (narzędzie woła produkcję); opcjonalne wejście kontenera w planerze dla TRANSLATE i NORMALIZE (D3) z budową `FontSources` w handlerze (na razie nieużywany przez pomiar Arialem); parametr stylu bazowego w `marked_text` i `replace_visible_text` z przekazaniem we wszystkich wywołaniach (bez zmiany wyniku); budowa `FontIndex.build(FontSources...)` w `layout_translated` (indeks z U1a; pomiar nadal Arialem do U1b); przeprowadzenie `dialogue_font: DialogueFont | None` przez `runtime.py` i konstruktory handlerów TRANSLATE i NORMALIZE (wartość zawsze `None` do U6); przełączenie replay na stały punkt wejścia `layout_translated`. Replay (od F0a): `pair_events` (reuse) paruje zdarzenia EN↔PL; przekład = widoczny tekst sparowanego PL bez starych `\N` (wiersze złączone spacją); niesparowane zdarzenia zostają po angielsku i są wyłączone z porównań; wejścia zamrożone w pliku mapowania obok „baseline”. **Gate:** bramki zielone; replay po F0b bajtowo identyczny z „baseline”; lista par pominiętych z powodem.

**U3 — style, wariant minimalny** (`work/quality/12-style-ranges`, **po scaleniu F0b**, w fali A; tylko wnętrze `text.py`, testy): aneks v4 C pkt 1–2. Dowód C: testy jednostkowe z przypadków split-and-styles H4 (T3, komentarze) oraz zapisane odpowiedzi LLM ze znacznikami z `workspace/.quality/experiments/styles/` (bez nowych wywołań). Replay nie jest dowodem C. **Gate:** bramki; liczby H4 odtworzone skryptem na korpusie (akcenty T3 odzyskane regułą bazy linii — zmierzone 325, zob. aneks v4 C; 0 zakresów z samych komentarzy).

### Fala A (po scaleniu F0b; U3 równolegle z U1b, U2, U7)

| Jednostka | Cel | Write scope | Gate |
| --- | --- | --- | --- |
| **U1b Pomiar w geometrii** `13-measurement` | wnętrze `geometry.py` wg D1 na `FontIndex` (indeks buduje już F0b); `scripts/subtitle_quality/calibrate.py` (test regresji wobec `measure_boxes`: szerokość, wysokość, liczba wierszy po zawinięciu, `\q2`, marginesy); przejście narzędzia na moduły aplikacji (D10, render/metrics) | `geometry.py`, `services/fonts/*` (poprawki), `scripts/subtitle_quality/*`, testy | progi z „Warunków końcowych”; czas replay 36 par |
| **U2 Lektor** `14-lector` | aneks v4 B pkt 1–6: klasyfikator, fallback, deduplikacja między stylami (z mapowaniem przekładów w writerze), opcjonalne wejście źródła w SPLIT (planer, `subtitle_handler`), TTS bez reklasyfikacji SPOKEN_PL | `classifier.py`, `service.py` (split i mapowanie), `planner.py` (SPLIT), `subtitle_handler.py`, `tts_handler.py`, testy | trzy reguły klasyfikatora: lista zmian = `research-split/minimal_veto2.json`; etykiety 425/425; 9 kwestii `Alt` odzyskanych; 0 zdań utraconych; regresja ≥ 0,9586; usunięty fallback: pliki NC/ED, TS i z samymi szyldami mają 0 linii spoken (lista plików z H3); deduplikacja: 26 par z H5 czytanych raz, bez innych zmian |
| **U7 Galerie** `15-gallery` | `scripts/subtitle_quality/compare.py`: obraz przed/po z dwóch katalogów replay, wybór przypadków (zmiany szerokości, kolizji, cięć, decyzji lektora + lista przypadków trudnych z visual-quality §10.4), powiększenie, podpisy po polsku; reuse `visual-fixes` | `scripts/subtitle_quality/compare.py`, testy | galeria baseline vs baseline = brak różnic; vs F0b = brak różnic |

### Fala B (po scaleniu U1b, U2 i U3)

| Jednostka | Cel | Write scope | Gate |
| --- | --- | --- | --- |
| **U5 Łamanie** `16-line-breaks` | `lexicon.py`, `linebreak.py` wg LB + aneks v4 (ratunek, jednoliterowe słowa), `layout_dialogue` i `split_lines` z pomiarem, normalizacja polskiego źródła przez `layout_translated`, usunięcie legacy łamania (D10) | `linebreak.py`, `lexicon.py`, `layout.py`, szew w `service.py`, `subtitle_handler.py` (normalizacja), testy (przeniesione + przypadki 01–39) | testy galerii 01–39 zgodne z `model-v32.md`; replay bez wyjątków |
| **U6 Czcionka dialogów i mux** `17-dialogue-font` | `restyle.py` (D7), ustawienie i panel z walidacją, snapshot planu z wartością domyślną, ostrzeżenie planu, wartość `DialogueFont` z ustawienia w miejscu przygotowanym przez F0b w `runtime.py`, composition (`--attach-file`, `--attachment-name`, sha256 vs załączniki źródła, `fonts_dir` przy wypalaniu z załącznikami kontenera), `composition/fonts.py` na rodzinach | `restyle.py`, `config/*`, `cli/interactive/*` (pole), `planner.py` (pole, ostrzeżenie), `runtime.py`, `composition/*`, `composition_handler.py`, testy | MKV testowy: `mkvmerge -J` pokazuje warianty; log libass (FFmpeg) wybiera Officinę dla dialogu bez lokalnych czcionek; MP4 z prawdziwymi krojami szyldów |

### Fala C (po scaleniu U5 i U6)

**U4 Szyldy** `18-signs`: `fitting.py` wg A + aneks v4 (obiekty, K0/A/B/C/D, filtry ekranu i kolizji z tolerancją, szkody, poziomy ostateczne, licznik kolizji z dialogiem), `split_lines` z U5 dla D i źródeł wielowierszowych. **Gate:** testy a0–a10 i b1; render libass wyników dla statycznych zmierzonych szyldów: 0 przyrostów wyjścia poza ekran i kolizji, gdy istniał dopuszczalny kandydat; replay bez wyjątków.

### Fala D (po scaleniu U4) — lektor czyta napisy ekranowe, gdy jest miejsce

**U8** `work/quality/19-sign-narration`: visual-quality §6.1. Trzeci stan decyzji linii „ekran + lektor, gdy pasuje”, liczony raz na źródle razem z decyzjami B. Twarde: brak nakładania na czytane kwestie, bez piosenek, karaoke i `*...*`. Miejsce: pauzy między czytanymi kwestiami w oknie napisu (z dopuszczalnym wyjściem poza okno dla ważnych napisów). Ważenie rozmyte (`fuzzy.py`): „za” — rozmiar i czytelność, położenie centralne/tytuł, czas na ekranie, zwięzłość, jedyny napis w kadrze; „przeciw” — ciasna pauza względem szacowanego czasu czytania (liczba znaków i tempo lektora z ustawień), wyjście poza okno napisu, długość, powtórka (ten sam znormalizowany tekst czytany niedawno albo równy przyległej kwestii), drobny napis tła. Ustawienie `sign_narration`: `off` / `when_fits` (domyślnie) / `always`. `SPOKEN_PL` zawiera wybrane napisy z czasem rozpoczęcia czytania w wybranej pauzie; kontrakt TTS i miksu bez zmian. Najpierw dopisek do aneksu B i przegląd innego modelu, potem kod. **Gate:** testy (pauza przed/po kwestii, brak pauzy, ważny tytuł w krótkiej pauzie, drobny napis, powtórka, piosenka, odgłos), replay z listą napisów wybranych do czytania na korpusie (liczba i przykłady), 3–5 fragmentów audio do odsłuchu przez właściciela.

### Faza I — integracja i dowód wizualny (orkiestrator)

1. Pełne bramki na 08 po scaleniu wszystkich jednostek.
2. Replay 36 par: baseline (F0b „baseline”) vs 08; galerie U7 dla każdego obszaru i przypadków trudnych.
3. Ocena orkiestratora obraz po obrazie (lepiej / bez zmian / gorzej) → `docs/work/10-quality/reviews/02-gallery.md`.
4. Zrzut z mpv właściciela (`--no-config` z jego `sub-font` i folderem czcionek, jak w fonts.md §3) dla 3–5 przypadków i krótki fragment szyldu ruchomego przy x2.
5. Odcinek testowy end-to-end (decyzja o koszcie tłumaczenia: właściciel) i galeria dla właściciela; jego decyzje → kalibracja stałych → outcome w `docs/work/10-quality/outcomes/`.

## Strategia dowodu

| Twierdzenie | Kontrola |
| --- | --- |
| Pomiar zgodny z libass (szerokość, wysokość, zawijanie) | `calibrate.py`, progi z „Warunków końcowych” |
| Dopasowanie czcionek jak libass | testy U1a na plikach korpusu i folderu mpv |
| Przebudowa bez zmiany wyniku | replay F0b bajtowo identyczny |
| Szyldy wg A | testy a0–a10, render libass wyników, galeria |
| Łamanie wg LB | testy 01–39, galeria |
| Lektor | etykiety, lista zmian = `minimal_veto2.json`, regresja, pliki NC/ED |
| Style | testy H4, zapisane odpowiedzi LLM ze znacznikami |
| Czcionka dialogów | testy restyle i mux, `mkvmerge -J`, log libass, zrzut mpv |
| Wygląd dla człowieka | galeria, zrzuty mpv, ocena orkiestratora i właściciela |

## Ryzyka

| Ryzyko | Reakcja |
| --- | --- |
| Konflikty scalania | szwy i kontrakty z F0b; orkiestrator scala po każdej fali |
| Pomiar gorszy na nowych danych | analiza wg measurement.md H3; eskalacja przy zmianie D1 |
| Officina źle wygląda z obrysem typesettera | galeria → decyzja właściciela |
| Agent opisuje pogorszenie jako poprawę | orkiestrator ogląda każdy obraz sam |
| Rezydent właściciela | zero zmian w głównym checkoucie |

## Uwagi przeglądu v1 i ich zamknięcie

| Uwaga | Zamknięcie |
| --- | --- |
| Brak bramki akceptacji przed F0 (sol6, astra, claude) | „Warunek wejścia”; poprawki specyfikacji wniesione przed akceptacją (aneksy v4) |
| Replay po indeksie, baseline, znaczniki C (wszyscy) | F0b: `pair_events`, adapter baseline jako pierwszy commit, C poza replay |
| Czcionki odcinka nie docierają do writera (wszyscy) | D3 + `FontSources` + `layout_translated` |
| D3 bez źródła / TTS (wszyscy) | aneks v4 B pkt 6, edge cases |
| `\r` w szyldach, bajtowa identyczność (wszyscy) | D7 klon stylu |
| Niezdefiniowane `Rect`, `FitReport`, `StyleState`, decyzje w `fit_signs`, style w profilu (wszyscy) | kontrakty v2; `StyleState` niepotrzebne (C minimalne) |
| Raport bez kontraktu (sol6) | `LayoutReport` + `TranslatedLayout` |
| Sprzężenia semantyczne fal, U4↔U5 (wszyscy) | fale 0/0b/A/B/C wg zależności; `split_lines` |
| Limit 2 instancji (astra, claude) | „Warunek wejścia”: polecenie właściciela 18.10 |
| Trzy wiersze vs COUNT, przypadek 07 (astra, claude) | ratunek w visual-quality §4 i aneksie LB; pytanie do właściciela |
| Fallback czyta piosenki i szyldy, kopie między stylami (astra, sol6, claude) | aneks v4 B pkt 4 (fallback usunięty) i pkt 5 |
| Krój zastępczy mpv vs FFmpeg (astra, claude) | Arial w pomiarze, uzasadnienie w visual-quality §9 |
| Deduplikacja załączników po nazwie (sol6, astra) | sha256 + `--attachment-name` |
| Ostrzeżenie w panelu (sol6, claude) | walidacja w Ustawieniach + ostrzeżenie planu |
| Jednoliterowe słowo bez szkody w LB (sol6) | przeliczenie `model-v32.md`, aneks LB |
| Środek ruchu, kolizja dialog–szyld (sol6) | visual-quality §9 zawężone do końców; licznik kolizji w `LayoutReport` |
| Bramka tylko szerokości (sol6, astra) | wysokość, zawijanie, `\q2`, render filtrów U4, zrzut mpv |
| D8 niepełne (claude) | D10 rozszerzone o `composition/fonts.py` i narzędzie |
| Ramka z rysunku (astra, claude) | znana ramka = `\clip` |
| 05/06 bez przeliczenia (claude) | `model-v32.md` przed akceptacją |
| Grafemy nie bajtowo (claude) | dopuszczalne przy identycznym replay, odchylenie zapisane |
| SRT z ASS (claude) | D8 |
| Tolerancja kolizji (claude) | aneks v4 A.5 |
| `split-and-styles.md` brak (wszyscy) | dodany |
