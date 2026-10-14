# etap 3 — ekstrakcja + refaktor napisów

> cel: Enter zaczyna coś robić — MKV wrzucone do `workspace/` → wyciągnięte ścieżki + napisy przerobione do SRT, pliki pośrednie obok MKV (jak dziś).
> zależności: etapy 1-2. logika przenoszona z `mm_avh/modules/mkvtoolnix.py`, `track_selector.py`, `subtitle.py` (w tym świeże poprawki live-progress ekstrakcji z ostatnich commitów mm_avh: postęp w kolejności plików, stdout mkvextract przez bufor, finalne "Postęp: 100%", wyciszenie surowego WARNING).
> DoD: parytet z dzisiejszą ekstrakcją+refaktorem na pliku testowym (te same ścieżki wybrane, ten sam SRT co stary kod), pasek postępu live jak dziś.

## pliki do stworzenia/zmiany

domeny bez wyboru silnika = zwykłe moduły, BEZ `engines/` (extraction i subtitles nie mają rejestru).

### `anishift/services/extraction/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs domeny ekstrakcji.
- **zawartość:** `__all__` + re-export fasady, typów i błędów.

### `anishift/services/extraction/types.py` (NOWY)
- **odpowiedzialność:** typy domeny ekstrakcji.
- **zawartość:** dataclassy (slots, frozen dla wyników): `TrackInfo` (id, typ, kodek, język, nazwa, flagi — z JSON mkvmerge), `MediaInfo` (plik + lista ścieżek), `ExtractionResult` (wybrane ścieżki, ścieżki wyjściowych plików obok MKV, czasy).
- **wzorzec z MangaShift:** domenowe `types.py` z service-standard.

### `anishift/services/extraction/errors.py` (NOWY)
- **odpowiedzialność:** błędy domenowe ekstrakcji.
- **zawartość:** `ExtractionError` (dziedziczy z bazowego `AnishiftError` w `anishift/errors.py`) + ewentualnie `ToolNotFoundError`/`ExtractionFailedError` (non-zero exit mkvextract). liść — importuje tylko `anishift.errors`.

### `anishift/services/extraction/service.py` (NOWY)
- **odpowiedzialność:** fasada — identyfikacja i ekstrakcja ścieżek z MKV przez binarki mkvtoolnix.
- **zawartość:**
  - `identify(mkv: Path) -> MediaInfo` — `mkvmerge --identify --identification-format json`, parsowanie do `TrackInfo` (jak dziś).
  - `extract(mkv, tracks) -> ExtractionResult` — `mkvextract` subprocessem; pliki wyjściowe OBOK źródłowego MKV (te same rozszerzenia/nazwy co dziś); live pasek postępu przez `utils/rich_console` ProgressBarManager (stdout mkvextract czytany przez bufor, log wypakowywania w kolejności plików, finalny "Postęp: 100%" — przeniesione poprawki z ostatnich commitów); walidacja kodu wyjścia PRZED uznaniem plików za gotowe.
  - ścieżki binarek z `platform/binaries.py` (nigdy zahardkodowane); sync, bez `input()`/`sys.exit()`.
- **skąd logika:** `modules/mkvtoolnix.py` (mm_avh).

### `anishift/services/extraction/tracks.py` (NOWY)
- **odpowiedzialność:** auto-wybór ścieżek (audio + napisy main/alt).
- **zawartość:** czyste funkcje scoringu/wyboru przeniesione z `track_selector` — te same wagi i heurystyki (język, flagi, kodek, nazwa), `select_*() -> TrackInfo | None`; zero interakcji z userem (pytania w trybie manual żyją w `cli/`).
- **skąd logika:** `modules/track_selector.py` (mm_avh) — parytet 1:1, bez strojenia.

### `anishift/services/subtitles/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs domeny napisów.
- **zawartość:** `__all__` + re-export fasady, typów i błędów.

### `anishift/services/subtitles/types.py` (NOWY)
- **odpowiedzialność:** typy domeny napisów.
- **zawartość:** dataclassy: wynik podziału (ścieżki main/alt SRT w `workspace/tmp/main_subs/` i `alt_subs/`), metadane stylów ASS, wynik konwersji.

### `anishift/services/subtitles/errors.py` (NOWY)
- **odpowiedzialność:** błędy domenowe napisów.
- **zawartość:** `SubtitlesError` (podklasa `AnishiftError`).

### `anishift/services/subtitles/service.py` (NOWY)
- **odpowiedzialność:** fasada refaktoru napisów — ASS→SRT, podział main/alt, przygotowanie pod tłumaczenie.
- **zawartość:** funkcje przeniesione z `modules/subtitle.py`: podział zdarzeń ASS na main/alt wg stylów (auto wg heurystyki, manual = wybór stylów przekazany z cli), konwersja ASS→SRT (zachowanie timingów), txt→srt, srt→ass (potrzebne w etapie 7 — jeśli logicznie sprzężone, przenieść już tu), zapis plików roboczych do `workspace/tmp/main_subs/` i `alt_subs/`, plików pośrednich obok MKV.
- **skąd logika:** `modules/subtitle.py` (mm_avh).

### `anishift/services/subtitles/cleanup.py` (NOWY)
- **odpowiedzialność:** czyszczenie znaczników ASS/formatowania z tekstu napisów.
- **zawartość:** czyste funkcje: usuwanie tagów ASS (`{\...}`), HTML, `\h`, pomijanie rysunków wektorowych (drawing commands) — używane przez service i (w etapie 4) przez tłumaczenie.
- **skąd logika:** fragmenty czyszczące z `modules/subtitle.py` + `modules/translator.py`.

### `anishift/services/subtitles/styles.py` (NOWY)
- **odpowiedzialność:** hak na przyszły style_classifier — TYLKO miejsce, nie implementacja.
- **zawartość:** zaślepka: jedna funkcja przepuszczająca dzisiejszą prostą heurystykę wyboru stylów (jeśli jest w `subtitle.py`) + komentarz, że pełny klasyfikator jest odłożony (user zbiera przykłady). NIE wchodzi żadne strojenie.

### `anishift/pipeline/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs pipeline.
- **zawartość:** re-export runnera i typów.

### `anishift/pipeline/types.py` (NOWY)
- **odpowiedzialność:** kontekst przebiegu pipeline.
- **zawartość:** dataclass kontekstu per plik (ścieżka MKV, wybrane ścieżki, ścieżki plików pośrednich, ustawienia usera, wyniki kroków) + typ wyniku przebiegu (sukces/błąd per plik); enum trybu (auto/manual) — proste typy, żadnego DAG-a.

### `anishift/pipeline/runner.py` (NOWY)
- **odpowiedzialność:** liniowy przebieg pipeline — w tym etapie kroki 1-2 (extract → refactor).
- **zawartość:** `run(...)` — discovery plików MKV wprost z `workspace/` (natsorted), per plik: identify → wybór ścieżek (auto przez `tracks.py`, manual przez callback pytający — implementacja pytań w `cli/`) → extract → refaktor napisów; kolejność zapisana wprost w kodzie (zero step-registry); błąd jednego pliku nie przerywa pozostałych, raport na końcu.
- **wzorzec z MangaShift:** liniowy runner zamiast generycznego DAG (świadome odchudzenie).
- **skąd logika:** orkiestracja z `start.py`/`modules/mkv_processing.py` (część discovery+extract).

### `anishift/cli/shell.py` (ZMIANA)
- **odpowiedzialność:** podpięcie Enter=auto do runnera.
- **zawartość:** Enter (pusta linia) → `runner.run()` w trybie z ustawień; tryb manual — pytania o wybór ścieżek/stylów renderowane w cli (rich), odpowiedzi przekazywane do runnera; progress rusza dopiero PO zakończeniu `session.prompt()` (rich Live nie koliduje z prompt_toolkit).

## kolejność implementacji

1. `extraction/types.py` + `errors.py` + `service.py::identify()` → weryfikacja: test na realnym MKV — JSON sparsowany, te same ścieżki co `mkvmerge --identify` dziś.
2. `extraction/tracks.py` → weryfikacja: test regresji wyboru ścieżek na zrzucie identify z mm_avh (te same ID co stary `track_selector`).
3. `extraction/service.py::extract()` z live progress → weryfikacja: pliki obok MKV identyczne rozszerzeniem/rozmiarem jak ze starego kodu; pasek postępu wygląda jak dziś.
4. `subtitles/` (cleanup → service → styles-hak) → weryfikacja: ten sam SRT bit-w-bit co stary `subtitle.py` na pliku testowym; main/alt w `workspace/tmp/`.
5. `pipeline/types.py` + `runner.py` (kroki 1-2) → weryfikacja: `run()` na folderze z 2+ MKV przechodzi oba, błąd jednego nie ubija drugiego.
6. podpięcie Enter w `shell.py` (auto + manual) → weryfikacja ręczna: Enter w shellu robi ekstrakcję+refaktor; manual pyta o ścieżki.

## jak testować

realny MKV wrzucony do `workspace/` → wyciągnięte audio i napisy pośrednie obok MKV, robocze main_subs/alt_subs w `workspace/tmp/`; tryb manual pyta o wybór ścieżek, auto wybiera sam. parytet: porównanie wybranych ID ścieżek i wynikowego SRT ze starym kodem na tym samym pliku.
