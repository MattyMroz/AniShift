# fonts

Czcionki odcinka i systemu: odczyt krojów (fontTools), wybór kroju tak jak libass (decyzja D2 planu `docs/work/10-quality/plans/01-fuzzy-layout-and-fonts.md`) i metryki glifów do pomiaru tekstu (D1). Bez zależności od pysubs2 i `services/subtitles`.

## Pliki

- `types.py` — `FontFace` (nazwy po `casefold`, waga, kursywa, metryki pionowe, `cmap`), `FontMatch`
- `index.py` — `read_faces`, `polish_missing`, `system_font_paths`, `FontIndex` (`build`, `match`, `glyph_match`)
- `metrics.py` — `GlyphMetrics`, `glyph_metrics` (Pillow, 1000 px, bez kerningu), `font_scale`

## Pułapki

- Rodzina to tylko p3 ID1 (wszystkie języki); krój bez p3 ID1 jest pomijany. ID16 i rodzina z platformy Mac nie są kluczami — „ITC Officina Sans Std” nie trafia w Officinę właściciela. Pełna nazwa (p3 ID4) i PostScript działają jak `matches_full_or_postscript_name` w libass: krój z obrysami CFF/CFF2 trafia tylko nazwą PostScript, krój TrueType tylko pełną nazwą. `FontFace` nie niesie rodzaju obrysów, więc `FontIndex` trzyma go we własnym zbiorze.
- Nazwa znaleziona w czcionkach odcinka wyklucza system, także dla zastępczego Ariala: Grand Blue (załącznik tylko Arial Bold) rysuje brakujące `ż` w Gandhi Sans kursywą syntetyczną z załącznika, Kaguya (bez Ariala) systemowym `arialbi.ttf`. Tak samo w logach libass.
- `glyph_match` dobiera krój rodziny i zastępczy Arial dla żądania (`requested_weight`, `requested_italic`), nie dla wybranego kroju: Officina Book przy wadze 400 rysuje się plikiem Bold, ale brakujący glif Arialem 400.
- Synteza pogrubienia i premia +120 w ocenie wariantu tylko dla kroju bez flagi bold (`fsSelection` bit 5, bez OS/2 `macStyle`) i przy wadze żądanej > waga kroju + 150.
- `build` czyta z plików systemowych tylko tabele `name`; pełny krój (`cmap`) dopiero dla dopasowanej nazwy. Pełny odczyt ~370 krojów systemu to ~2,3 s i ~60 MB.
- Pillow ładuje plik do pamięci, nie po ścieżce: FreeType trzymałby otwarty uchwyt i blokował usuwanie stagingu na Windows.
- Cache metryk i krojów Pillow jest procesowy, po (ścieżka, indeks kroju[, znak]): plik pod tą samą ścieżką nie może zmienić treści w trakcie procesu.
- fontTools nie ma `py.typed`: importy z `# type: ignore[import-untyped]`, obiekty fontTools jako `Any`.
- fontTools loguje przez stdlib `logging` ostrzeżenia o znacznikach czasu w `head` niektórych plików.

## Konwencje

- Plik brakujący, uszkodzony albo nie-czcionka: `read_faces` zwraca `()` i loguje debug z samą nazwą pliku. Krój bez rodziny albo z zerową wysokością jest pomijany.
- `descent` jest dodatni (pod linią bazową); metryki pionowe: Win → hhea → typo → bbox, pierwsze o niezerowej sumie (libass `set_font_metrics`).
- `exact=False` oznacza krój zastępczy (Arial za nieznaną rodzinę albo za brakujący glif); konsument mierzy nim, ale ze statusem przybliżonym.
- Arial jako krój zastępczy, bo tak robi libass z DirectWrite (FFmpeg, domyślne mpv); mpv właściciela dorysowuje węższą Officiną, więc pomiar jest ostrożny.
