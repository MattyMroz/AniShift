# etap 8 — migracja danych + wyburzenie starego

> cel: repo po przeprowadzce — dane usera zmigrowane, stary kod i bałagan usunięte.
> **binarki wyprowadzone z tego etapu:** manifest, `anishift setup` i leniwe pobieranie mkvtoolnix/ffmpeg (`ensure_binary` przy pierwszym użyciu) zrealizowane w [etap-2.5-pobieracz-binarek-v2.md](etap-2.5-pobieracz-binarek-v2.md); wpis balcon w manifeście dochodzi w etapie 6 razem z silnikiem.
> zależności: etap 7 (nic starego nie kasujemy, dopóki nowe nie ma parytetu).
> DoD: w repo nie ma śladu nazw `mm_avh` / `working_space` w nowym kodzie; README opisuje AniShift; świeży klon + `uv sync` + `anishift setup` + `anishift doctor` = zielono (albo bez `setup` — binarki dociągają się same przy pierwszym użyciu w pipeline).

## pliki do stworzenia/zmiany

### `scripts/maintenance/migrate_workspace.py` (NOWY)
- **odpowiedzialność:** jednorazowe przeniesienie danych usera ze starego `working_space/` do `workspace/`.
- **zawartość:** skrypt: PRZENOSI (nigdy nie kasuje) pliki usera płasko do `workspace/` (żadnych podfolderów poza tmp/output — struktura docelowa jest płaska); kolizje nazw = pomiń + raport; dry-run domyślnie (`--apply` wykonuje); na końcu raport co przeniesiono/pominięto. kasacja starego `working_space/` NIE jest częścią skryptu — dopiero ręczne potwierdzenie usera (704 pliki danych, w tym luźne MKV i audiobooki).

### kasacje starego kodu (ZMIANA — commit(y) porządkowe, osobno od zmian architektury)
- **odpowiedzialność:** wyburzenie mm_avh po potwierdzonym parytecie.
- **zawartość (kolejność bezpieczeństwa):**
  1. zrzut `git ls-files bin/` do notatki (dowód co było trackowane).
  2. kasacje kodu: `modules/`, `start.py`, `constants.py`, `run_mm_avh.bat`, `data/`.
  3. kasacje binarek: `bin/` (w tym stylish_tts ~567MB — zweryfikować absolutną ścieżkę przed `rm`, oraz espeak-ng); untrack z gita.
  4. `working_space/` — dopiero PO migracji skryptem i ręcznym potwierdzeniu usera.
  5. porządek w `temp/` i starych `tests/`: przejrzeć każdy skrypt, realnie używane → `scripts/maintenance/`, reszta out.
  6. `.gitignore` — finalna wersja (external/bin, workspace, config/settings.json, .env); `pyproject.toml` — usunięcie martwych zależności po `rg` importów.
  7. `README.md` — opisuje AniShift (instalacja: uv sync; binarki dociągają się same przy pierwszym użyciu, `anishift setup` pobiera je z góry; użycie: anishift → Enter).

## kolejność implementacji

1. `migrate_workspace.py` → weryfikacja: dry-run na kopii `working_space/` raportuje komplet; `--apply` przenosi płasko, nic nie kasuje.
2. smoke czystego klonu: świeży klon → `uv sync` → `anishift` (shell startuje natychmiast, zero pobierania) → smoke e2e (binarki dociągają się same przy pierwszym użyciu przez `ensure_binary`) → `anishift doctor` → weryfikacja: wszystko zielono bez ręcznych kroków.
3. kasacje (osobne commity, w kolejności wyżej) → weryfikacja: `git status` czysty, `git ls-files` bez binarek, `rg "mm_avh|working_space"` w nowym kodzie = 0 trafień, smoke e2e nadal przechodzi.

## jak testować

świeży klon repo + `uv sync` + smoke e2e = zielono (osobny `anishift setup` niepotrzebny — brakującą binarkę pobiera pierwsze użycie w pipeline; `setup` zostaje jako jawne „pobierz wszystko z góry"); `anishift doctor` zielony po pobraniu; `git status` czysty, żadnych binarek w gicie. dodatkowo: `rg` po nazwach `mm_avh`/`working_space` w nowym kodzie pusty; migracja danych potwierdzona przez usera przed kasacją starego folderu.
