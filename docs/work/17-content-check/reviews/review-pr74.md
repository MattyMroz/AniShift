---
kind: review
status: fail
reviewed-state: origin/work/acquisition/05-content-check @ d629837 (baza origin/main @ a286b02)
date: 2026-10-25
---

# Review: PR #74 — odrzucenie wydania bez napisów dialogowych

## Zakres

- przedmiot: `git diff origin/main origin/work/acquisition/05-content-check` (5 commitów, F1–F2 planu);
- kontrakt: subskrypcja nie przyjmuje wydania z werdyktem `none`; kontrola pominięta nie odrzuca; budżet 3 prób z wykluczeniem hashy; toast i widoczny powód; dobre wydania przechodzą;
- poza review: ścieżka ręczna i schemat 6 (F3), H4.

## Werdykt

**FAIL, wyłącznie przez P1.** Logika subskrypcji spełnia kontrakt. Wszystkie sprawdzone przypadki dobrych wydań przechodzą, odrzucenie zawsze daje toast, powód w panelu, log i wpisy w `decisions.jsonl`, a budżet nie pobiera dwa razy tego samego wydania. Blokuje tylko twarda reguła repo: PR dodaje drugą `is_polish_language` i zostawia martwą, już sprzeczną kopię reguły szyldów. Po wycięciu P1 PR można scalić.

## Findings

### Poważne

#### P1. Legacy `services/extraction/tracks.py` do wycięcia w tym PR

- miejsce: `anishift/services/extraction/tracks.py:59` (`_RE_SIGNS`), `:62-66` (`_POLISH_LANGS`, `is_polish_language`), `:114` (`score_subtitle_track`), `:172` (`select_tracks`); nowy duplikat `anishift/application/selection.py:120` (`is_polish_language`, inny zbiór tagów: `{"pl","pol","pl-pl"}` zamiast `{"pol","pl"}`).
- dowód: `git grep` na branchu pokazuje, że produkcja importuje z `tracks.py` tylko `DEFAULT_AUDIO_PRIORITY` i `DEFAULT_SUBTITLE_PRIORITY` (`anishift/config/user_settings.py:15`). Scoring, `select_tracks` i stara `is_polish_language` są używane tylko w `tests/services/extraction/test_extraction_tracks.py` i `test_regression_tracks.py`. Kopia wzorca w `tracks.py` nadal uznaje `forced` za szyldy bez względu na tempo, czyli tę regułę, którą PR właśnie zastąpił w plannerze.
- wpływ: w runtime brak, ale łamie to twarde reguły z root `AGENTS.md`: „Wycinanie raka” i „Nie twórz drugiej wersji tego samego”. Argument ze specyfikacji („kierunek zależności nie pozwala”) tu nie działa, bo żaden kod produkcyjny tej reguły nie potrzebuje. Twarda reguła wygrywa ze szkicem specyfikacji.
- minimalna reakcja: usunąć z `tracks.py` scoring, selekcję, `_RE_SIGNS`, `_POLISH_LANGS` i `is_polish_language`. Zostawić tylko stałe priorytetów albo przenieść je do `config/user_settings.py`. Usunąć `test_extraction_tracks.py` i `test_regression_tracks.py`, a potem zaktualizować wzmianki w `anishift/services/extraction/AGENTS.md` (`:20`, `:51`, akapit „legacy” w nagłówku) i `tests/AGENTS.md` (`:7`, `:9`, `:21`). Pole `TrackSelection.already_polish` jest w produkcji zawsze `False`; to osobna decyzja, poza tym PR-em.

### Mniejsze

#### M1. Niepewny werdykt `none` odrzuca, a żaden test tego nie przypina

- miejsce: `anishift/application/selection.py:127-134` (bez liczby zdarzeń o roli decyduje sama flaga `forced`), `anishift/application/automation.py:6802` (odrzucenie bez względu na `subtitles_uncertain`).
- scenariusz: plik bez `num_index_entries` z jedyną pełną ścieżką oznaczoną `forced=1` (układ SubsPlease Dark Summoner). Wynik: `none`, odrzucenie i zużyta próba.
- dowód: mutacja „nie odrzucaj przy `subtitles_uncertain`” daje zielone testy ownera i reguły (M10 niżej). W bibliotece właściciela 0 z 801 ścieżek nie ma liczby zdarzeń. Remux przez FFmpeg też zachowuje poprawne `num_index_entries` (15 cue = 15 pakietów w próbce 3 min), więc ryzyko jest niskie. Skutek pozostaje widoczny: toast i powód.
- minimalna reakcja: właściciel rozstrzyga otwarte pytanie D1 („czy flaga `forced` ma wchodzić do reguły zapasowej?”). Którąkolwiek opcję wybierze, trzeba ją przypiąć testem ownera na `none` z `uncertain=True`.

#### M2. Dokumentacja obszaru nie nadąża za kodem

- miejsce: `anishift/application/AGENTS.md` (sekcja subskrypcji opisuje kontrolę bez napisów i bez wyjątku od `record_only`); `anishift/services/media/AGENTS.md` (brak `MediaTrack.entries` i pułapki: `ffprobe` zwraca `codec_type: "subtitle"`, a nie `"subtitles"`); `docs/work/17-content-check/README.md` („kodu nie zmieniano”) oraz `specification.md` i `plan.md`, które nadal opisują F3 (ścieżka ręczna, schemat 6) jako część tego rezultatu.
- wpływ: następny wykonawca nie wie, że `none` odrzuca także w `record_only` i że ścieżka ręczna (K-10, wymagania 13–17) jest jeszcze otwarta.
- minimalna reakcja: dopisać po jednym zdaniu w obu `AGENTS.md` i zaktualizować status workstreamu 17: F1–F2 zrobione, F3–F4 otwarte.

### Sugestie

- `selection.py:74` `_TEXT_SUBTITLE_FORMATS` to piąta kopia literału `{"ass", "srt"}` (pozostałe: `planner.py:1191`, `:1471`, `:1968`, `:1975`). `MediaTrack.subtitle_format` przyjmuje tylko `ass`/`srt`/`None`, więc w `subtitle_content` wystarczy `subtitle_format is not None`, tak jak w `_has_embedded_text` (`selection.py:358`).
- Po wycięciu P1 dataset `TRACKS_DATASET` (790 ścieżek z liczbą linii) można przepiąć na `subtitle_role` jako regresję progów zamiast regresji martwego scoringu.

## Przypadki fałszywego odrzucenia

| Przypadek | Wynik | Dowód |
|---|---|---|
| Brak `num_index_entries` (inny muxer) | reguła zapasowa: dialog, chyba że `forced` albo tytuł `sign\|song\|forced`; odrzucenie tylko w M1 | `selection.py:127-134`; remux FFmpeg zachowuje cue napisów |
| Pełna ścieżka `forced`, 251 zdarzeń | dialog, bez odrzucenia, bez degradacji w plannerze | `test_role_by_event_rate[subsplease_forced_251]`, `test_a_forced_track_with_a_dialogue_rate_is_not_demoted` |
| Osobny `.ass`/`.srt` w torrencie | `foreign`, gdy ma ten sam katalog i stem co wideo (tylko takie pliki selekcja pobiera i discovery łączy, `transfers.py:446`); inny stem albo `Subs/` daje odrzucenie, a bez tego plik czekałby bez napisów | `automation.py:6752`; mutacja M9 łapana |
| PGS/VobSub (też WebVTT) | nie są tekstowe, więc `none` i odrzucenie; zgodne ze specyfikacją („Tylko napisy obrazkowe → brak”), bo planner i tak ich nie użyje | `test_content_is_none_without_text_subtitles` |
| MP4 z `mov_text` | poprawka `codec_type` działa: ścieżka `srt` z `nb_frames`; na `main` każde MP4 traciło napisy | `test_mp4_subtitle_stream_is_kept_as_a_subtitle_track`; mutacja M12 łapana |
| Krótki odcinek | o roli decyduje tempo, nie długość: 251 zdarzeń w 12 min daje dialog; odrzucenie dopiero poniżej 2,5/min (szyldy ≤ 1,52, dialog ≥ 7,98 w danych). Zwiastun z kilkoma liniami odpadnie, ale subskrypcja celuje w odcinki | `test_role_by_event_rate[short_episode_251_in_12_min]` |
| Biblioteka właściciela, 55 MKV / 801 ścieżek | reguła z brancha: 38 `polish`, 17 `foreign`, 0 `none`, 0 ścieżek w strefie 2,5–5/min; `num_index_entries == NUMBER_OF_FRAMES` na 801/801 | skrypt tylko do odczytu na `workspace/ready` |

## Zgodność z kontraktem

| Wymaganie | Stan | Dowód |
|---|---|---|
| `none` odrzuca przed nazwaniem, także w `record_only` | pass | `automation.py:6802`; `test_an_attempt_without_dialogue_subtitles_is_rejected_before_naming_also_in_record_only` |
| następne wydanie w budżecie 3 prób, bez powtórki hasha | pass | `test_three_releases_without_subtitles_exhaust_...`: hashe `[1,2,3]`, czwarty nietknięty |
| toast przy odrzuceniu i przy wyczerpaniu | pass | komunikaty „wydanie odrzucone (brak napisów dialogowych), szukam następnego” i „wyczerpano próby (3 z 3), ostatnio …” |
| panel, log, `decisions.jsonl` | pass | `status.notices`, wpisy `check`/`attempt`/`escalation`, `logger.info("Download checked", subtitles=…)` |
| kontrola pominięta nie odrzuca | pass | `test_an_unchecked_attempt_is_never_rejected_for_subtitles` |
| dobre wydania przechodzą | pass | dane biblioteki (0 `none`) i istniejące scenariusze zielone |

## Wykonane kontrole

```text
eksport brancha (git archive) do scratchpad, uv sync --frozen, binarki skopiowane do eksportu
uv run pytest                          9796 passed, 183 skipped, 4 xfailed (pierwszy przebieg bez binarek: 6 BinaryNotFound, środowisko)
ruff check / ruff format --check       czysto
mypy anishift/ tests/ (+ --platform linux)   0 błędów, 678 plików
check_test_comments.py na zmienionych testach   rc=0
mutacje (każda na kopii, potem cofnięta):
  M1 SIGNS 2.5→1.0         czerwony      M2 DIALOGUE 5→12        czerwony
  M3 DIALOGUE 5→2.5        czerwony      M4 SIGNS 2.5→4.9        czerwony
  M5 zapas bez forced      czerwony      M6 companion ignorowany czerwony
  M7 odwrócony warunek     czerwony      M8 brak odrzucenia      czerwony
  M9 companion=False       czerwony      M10 bez odrzucenia przy niepewności  ZIELONY (M1 wyżej)
  M12 codec_type MP4       czerwony      M13 MKV bez entries     czerwony
mkvmerge -J na 55 MKV z workspace/ready (tylko odczyt) + reguła brancha
remux FFmpeg 3 min do scratchpad: num_index_entries = liczba pakietów napisów
```

## Ograniczenia

- Nie uruchamiano rezydenta ani prawdziwego pobrania; H4 nadal należy do właściciela.
- Lokalny hook pre-push nie zadziałał przy ostatnim pushu (opis PR). Pełny zestaw sprawdziłem w eksporcie.
