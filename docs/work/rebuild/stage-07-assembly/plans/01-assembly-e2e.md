# etap 7 — składanie + pełne e2e

> cel: domknięcie pipeline — trzy wyjścia jak dziś (players / merge mkv / burn mp4) i pełny tryb auto od Enter do wyniku.
> zależności: etap 6. logika z `mm_avh/modules/mkv_processing.py`.
> DoD: happy-path identyczny funkcjonalnie ze starym kodem; tryb auto nie zadaje żadnego pytania; oba warianty miejsca wyniku (obok MKV / `output/`) działają.

## pliki do stworzenia/zmiany

### `anishift/services/composition/__init__.py` (NOWY)
- **odpowiedzialność:** publiczny interfejs domeny składania.
- **zawartość:** `__all__` + re-export fasady, typów, błędów.

### `anishift/services/composition/types.py` (NOWY)
- **odpowiedzialność:** typy składania.
- **zawartość:** enum wariantu wyjścia (`players` / `merge_mkv` / `burn_mp4` — zwykły Enum, zero registry rendererów), dataclass wejścia składania (źródłowy MKV, ścieżka audio lektora, napisy alt), dataclass wyniku (ścieżka gotowego pliku, wariant, co posprzątano).

### `anishift/services/composition/errors.py` (NOWY)
- **odpowiedzialność:** błędy domenowe składania.
- **zawartość:** `CompositionError` (podklasa `AnishiftError`) — non-zero exit mkvmerge/ffmpeg z kontekstem; nieudany merge NIGDY nie kasuje plików wejściowych.

### `anishift/services/composition/service.py` (NOWY)
- **odpowiedzialność:** fasada — trzy wyjścia + umieszczenie wyniku.
- **zawartość:**
  - `compose_players(...)` — pliki dla odtwarzaczy: gotowe napisy + gotowe audio obok MKV (w tym konwersja alt SRT→ASS przez `subtitles/service.py`, jak dziś).
  - `compose_merge(...)` — `mkvmerge` subprocessem: nowy MKV ze ścieżką lektora (+ napisy), walidacja kodu wyjścia i wyniku PRZED jakimkolwiek sprzątaniem.
  - `compose_burn(...)` — render mp4 przez ffmpeg (libx264 + wypalone napisy przez filtr `subtitles=` — uwaga na escaping ścieżek Windows: spacje, apostrofy, litera dysku), parametry CRF/preset z ustawień.
  - umieszczenie wyniku: domyślnie obok źródłowego MKV; gdy `move_results_to_output` w ustawieniach = TAK → do `workspace/output/`. binarki z `platform/binaries.py`; przerwany render nie zmienia nazwy/zawartości źródłowego MKV.
- **skąd logika:** `modules/mkv_processing.py` (mm_avh) — merge, render, sprzątanie po sukcesie.

### `anishift/pipeline/runner.py` (ZMIANA)
- **odpowiedzialność:** krok 5 + pełen przebieg wielu plików.
- **zawartość:**
  - krok 5: `composition.service` wg wariantu wyjścia z ustawień; honoruje "przenieś wyniki do output/".
  - pełen przebieg: wszystkie MKV z `workspace/` (natsorted), równoległość tam gdzie dziś jest (ThreadPoolExecutor dla ekstrakcji wielu plików — nie więcej); cleanup plików pośrednich i `tmp/` TYLKO per plik i TYLKO po sukcesie (błąd odcinka zostawia jego pliki i stan wznowienia); raport końcowy per plik (sukces/błąd/pominięty).
- **skąd logika:** orkiestracja pełnego przebiegu z `start.py` + `modules/mkv_processing.py`.

### `scripts/smoke/run_e2e.ps1` (NOWY)
- **odpowiedzialność:** ręczny smoke e2e na 1 pliku MKV.
- **zawartość:** skrypt PowerShell: sprawdza obecność MKV w `workspace/` (ścieżka z parametru lub env), odpala `uv run anishift` w trybie auto (lub bezpośrednio runner przez małe wejście CLI), po przebiegu wypisuje: wariant wyjścia, ścieżkę wyniku, ffprobe metadanych wyniku. na górze komentarz-notka jak odpalić (parametry, wymagane binarki i klucze).

## kolejność implementacji

1. `composition/types.py` + `errors.py` → weryfikacja: importy, enum trzech wariantów.
2. `compose_players` → weryfikacja: napisy ASS + audio obok MKV, odtwarzalne w odtwarzaczu.
3. `compose_merge` → weryfikacja: mkvmerge tworzy MKV z lektorem; nieudany merge (podstawiony zły plik) NIE kasuje wejść; metadane wyniku jak ze starego kodu.
4. `compose_burn` → weryfikacja: mp4 z wypalonymi napisami; test ścieżki ze spacją i polskimi znakami (escaping `subtitles=`).
5. krok 5 + pełen przebieg wielu plików w runnerze → weryfikacja: 2+ MKV przechodzą Enter→wynik; cleanup tylko po sukcesie; wynik obok MKV vs `output/` wg ustawienia.
6. `scripts/smoke/run_e2e.ps1` → weryfikacja: świeże odpalenie skryptu na realnym odcinku = zielono.

## jak testować

smoke e2e — 1 realny odcinek wrzucony do `workspace/` przechodzi Enter→wynik we wszystkich trzech wariantach wyjścia; wynik domyślnie obok MKV, po włączeniu opcji w `output/`; porównanie z wynikiem starego `start.py` na tym samym pliku (te same ścieżki wybrane, ten sam wariant, porównywalne metadane audio/wideo — audio nie będzie bit-identyczne, kryterium to metadane i timingi ±100 ms).
