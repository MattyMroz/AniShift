# fonts

Czcionki odcinka i systemu: odczyt krojów (fontTools) i wybór kroju tak jak libass (decyzja D2 planu `docs/work/10-quality/plans/01-fuzzy-layout-and-fonts.md`). Bez zależności od pysubs2 i `services/subtitles`.

## Pliki

- `types.py` — `FontFace` (nazwy po `casefold`, waga, kursywa, metryki pionowe, `cmap`), `FontMatch`
- `index.py` — `read_faces`, `polish_missing`, `system_font_paths`, `FontIndex` (`build`, `match`, `glyph_match`)

## Pułapki

- Klucze to tylko p3 ID1 (wszystkie języki), p3 ID4 i nazwa PostScript (p3, a bez niej p1). ID16 i rodzina z platformy Mac nie są kluczami, gdy krój ma p3 ID1 — „ITC Officina Sans Std” nie trafia w Officinę właściciela. Rodzina z innej platformy tylko, gdy p3 ID1 brak.
- Nazwa znaleziona w czcionkach odcinka wyklucza system, także dla zastępczego Ariala: Grand Blue (załącznik tylko Arial Bold) rysuje brakujące `ż` w Gandhi Sans kursywą syntetyczną z załącznika, Kaguya (bez Ariala) systemowym `arialbi.ttf`. Tak samo w logach libass.
- `glyph_match` nie zna żądanej wagi (`FontMatch` jej nie niesie): wyprowadza ją z kroju i flag syntezy (synteza pogrubienia = 700). Różni się od libass tylko, gdy żądanie trafiło w wariant o innej wadze bez syntezy.
- Brak flagi `FT_STYLE_FLAG_BOLD` w `FontFace`: synteza pogrubienia i premia +120 w ocenie wariantu zależą tylko od warunku „waga żądana > waga kroju + 150”.
- `build` czyta z plików systemowych tylko tabele `name`; pełny krój (`cmap`) dopiero dla dopasowanej nazwy. Pełny odczyt ~370 krojów systemu to ~2,3 s i ~60 MB.
- fontTools nie ma `py.typed`: importy z `# type: ignore[import-untyped]`, obiekty fontTools jako `Any`.
- fontTools loguje przez stdlib `logging` ostrzeżenia o znacznikach czasu w `head` niektórych plików.

## Konwencje

- Plik brakujący, uszkodzony albo nie-czcionka: `read_faces` zwraca `()` i loguje debug z samą nazwą pliku. Krój bez rodziny albo z zerową wysokością jest pomijany.
- `descent` jest dodatni (pod linią bazową); metryki pionowe: Win → hhea → typo → bbox, pierwsze o niezerowej sumie (libass `set_font_metrics`).
- `exact=False` oznacza krój zastępczy (Arial za nieznaną rodzinę albo za brakujący glif); konsument mierzy nim, ale ze statusem przybliżonym.
- Arial jako krój zastępczy, bo tak robi libass z DirectWrite (FFmpeg, domyślne mpv); mpv właściciela dorysowuje węższą Officiną, więc pomiar jest ostrożny.
