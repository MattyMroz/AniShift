# Czcionki: dopasowanie jak w mpv/libass, polskie znaki, czcionka dialogów właściciela

Data: 2026-10-18. Baseline: `work/quality/08-fuzzy-quality` @ `2301cd0`. Tryb: research, bez zmian w kodzie.
Eksperymenty i wyniki: `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\workspace\.quality\experiments\research-fonts\` (dalej `rf/`).

## Odpowiedź

1. **Officina właściciela.** Na dysku nie ma osobnego pliku Book. „ITC Officina Sans Std PL Book” to rodzina (name ID 1, platforma Windows) obu posiadanych plików: Bold i Bold Italic. mpv właściciela rysuje więc napisy SRT i każdy styl z tą nazwą plikiem **Bold** (prawdziwy krój, bez sztucznego pogrubiania). Sprawdzone w mpv właściciela (F).
2. **Dopasowanie libass** idzie po nazwie, nie po nazwie pliku. Porównuje: rodzinę (ID 1 z platformy Windows, wszystkie języki), pełną nazwę (ID 4) albo nazwę PostScript (ID 6). Wariant wybiera po wadze z OS/2 i bicie kursywy. ID 16 nie działa przy zwykłym dopasowaniu. Gdy nazwa nie pasuje, mpv bierze `sub-font`, czyli u właściciela Officinę. Pojedynczy brakujący glif też jest dobierany osobno, więc w jednym słowie mieszają się kroje (F).
3. **Polskie znaki to realny problem dialogów.** Gandhi Sans, główny font dialogów w 20 z 40 par, nie ma 14 z 18 polskich liter. Ma tylko ł, ó, Ł i Ó. Dotyczy to 31 stylów dialogowych. Z 184 unikalnych krojów w parach 106 nie ma co najmniej jednej polskiej litery (F).
4. **Podmiana czcionki dialogów jest tania i działa w mpv.** Wymaga zmiany `Fontname` w stylach czytanych przez lektora i dołączenia plików przez `mkvmerge --attach-file`. MIME (`font/ttf`) wykrywa sam mkvmerge, a mpv go akceptuje. Załącznik działa bez lokalnego folderu fontów. Koszt to +116 KiB na MKV (F, test `rf/mux-test/`).
5. **Znaleziony błąd poza zakresem:** wypalanie MP4 używa filtra `ass=` bez `fontsdir`. Fonty z MKV nie trafiają więc do libass i nawet szyldy typesettera wychodzą Arialem (F, `rf/mux-test/burn1.log`).

## 1. Jak AniShift obsługuje czcionki i załączniki dziś (F)

- `anishift/services/composition/fonts.py:23-51`: tylko diagnostyka. Regexy wyciągają nazwy z `Style:` i `\fn`. `attachment_font_names` porównuje **nazwy plików** załączników. Kontrakt sam mówi, że to nie potwierdza rodziny (`composition/AGENTS.md:55-57`). Ostrzeżenia wołają `service.py:573-603`.
- Mux MKV: `commands.py:118-136` (`merge_command`) i `commands.py:139-160` (`container_merge_command`). Źródło trafia jako zwykły plik wejściowy, bez `--no-attachments`, więc mkvmerge **kopiuje jego załączniki domyślnie** (dokumentacja mkvmerge §12, niżej). Żadnego `--attach-file` dziś nie ma.
- Wydobywanie: produkcja czyta tylko nazwy załączników z `mkvmerge -J` (`services/extraction/service.py:100`, `119-121`). Pliki fontów wyciąga wyłącznie narzędzie jakości: `scripts/quality/render.py:122-147` (`mkvextract … attachments`).
- Wypalanie MP4: `service.py:324-331` i `service.py:540-546` wołają `subtitle_filter_argument(...)` bez `fonts_dir`. Parametr istnieje w `commands.py:323-334`, ale nikt go nie przekazuje.
- Napisy: `subtitles/service.py:321-328` (`_copy_metadata`) kopiuje style i `fonts_opaque` (sekcja `[Fonts]` ASS) bez zmian. `fitting.py:58-67` mierzy Arialem. Łamanie dialogów liczy znaki (`translation/linebreak.py:14`, `DEFAULT_MAX_CHARS = 42`), nie piksele.
- Ustawienia: żadnego ustawienia fontu nie ma. Typy pól są w `config/field_catalog.py:87-99` (jest `OPTIONAL_STRING`, nie ma typu ścieżki). Pola napisów jako wzór: `field_catalog.py:609` (`subtitle_output_format`), `:639` (`burn_subtitle_product`), `config/user_settings.py:258`.

## 2. Reguły libass i mpv (źródła)

Kod: libass `master` @ `f61db56`, mpv `master` @ `fffe7a2`, FFmpeg `master` @ `eceaa54` (pobrane 2026-10-18 do `rf/sources/`). mpv właściciela: v0.36.0-711 z libass `0.17.0-59` i dostawcą DirectWrite (z logu `rf/mpv-test/mpv-*.log`). Zachowanie poniżej potwierdzono na tym buildzie.

| Reguła | Źródło i fragment |
|---|---|
| Rodzina i pełna nazwa tylko z platformy Windows, wszystkie języki | [ass_fontselect.c#L274-L276](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_fontselect.c#L274-L276): `name.platform_id == TT_PLATFORM_MICROSOFT && (name.name_id == TT_NAME_ID_FULL_NAME \|\| name.name_id == TT_NAME_ID_FONT_FAMILY)`; PS z `FT_Get_Postscript_Name` (L316) |
| Rodzina albo pełna nazwa / PS, bez rozróżniania wielkości liter | [L598-L641](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_fontselect.c#L598-L641): `matches_family_name` i `matches_full_or_postscript_name`; ID 16 (`extended_family`) tylko przy `match_extended_family` |
| Trafienie pełną nazwą = wybór natychmiastowy; trafienie rodziną = najlepszy wariant | [L733-L748](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_fontselect.c#L733-L748): `score = font_attributes_similarity(font, &req)` vs `score = 0` |
| Ocena wariantu: kursywa i waga | [L650-L672](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_fontselect.c#L650-L672): brak żądanej kursywy +1, niechciana kursywa +4, `score += (73 * ABS(a_weight - req->weight)) / 256` |
| Waga i styl z OS/2 | [ass_font.c#L605-L655](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_font.c#L605-L655): `usWeightClass`, `fsSelection & 1` kursywa, `& (1 << 5)` bold |
| `Bold=-1/1` → 700, `Italic=1` → 100 | [ass_parse.c#L99-L112](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_parse.c#L99-L112) |
| Sztuczna kursywa i pogrubienie | [ass_font.c#L806-L811](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_font.c#L806-L811): `!(style_flags & FT_STYLE_FLAG_ITALIC) && (font->desc.italic > 55)` → pochylenie; `font->desc.bold > ass_face_get_weight(face) + 150` → pogrubienie |
| Łańcuch zastępczy: rodzina → `family_default` → fallback dostawcy (z ID 16) → plik domyślny | [ass_fontselect.c#L884-L940](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_fontselect.c#L884-L940): `fontselect: Using default font family`, `select_font(priv, fallback_family, true, …)` |
| Brak glifu → osobny krój tylko dla tego znaku | [ass_font.c#L735-L740](https://github.com/libass/libass/blob/f61db567e6593df3470e91594bcd4ad2d0473aff/libass/ass_font.c#L735-L740): `Glyph 0x%X not found, selecting one more font`; najpierw inne warianty tej rodziny z glifem (`check_glyph`, ass_fontselect.c L750-L760) |
| mpv: `sub-font` = `family_default` także dla ASS | [ass_mp.c#L96](https://github.com/mpv-player/mpv/blob/fffe7a23a83bc13e0f5d2109179723405812da15/sub/ass_mp.c#L96): `ass_set_fonts(priv, default_font, opts->font, …)`, wołane dla ASS w [sd_ass.c#L243](https://github.com/mpv-player/mpv/blob/fffe7a23a83bc13e0f5d2109179723405812da15/sub/sd_ass.c#L243). Dokumentacja `--sub-font` mówi, że opcja jest ignorowana dla ASS. W praktyce działa jako zastępstwo (test niżej). |
| mpv: które załączniki MKV są fontami | [sd_ass.c#L143-L191](https://github.com/mpv-player/mpv/blob/fffe7a23a83bc13e0f5d2109179723405812da15/sub/sd_ass.c#L143-L191): MIME z listy (`font/ttf`, `font/otf`, `application/x-truetype-font`…) albo rozszerzenie `.ttf/.ttc/.otf/.otc` z ostrzeżeniem |
| mpv: opcje | [options.rst](https://github.com/mpv-player/mpv/blob/fffe7a23a83bc13e0f5d2109179723405812da15/DOCS/man/options.rst): `--embeddedfonts` „Use fonts embedded in Matroska container files and ASS scripts (default: yes)”; `--sub-fonts-dir` „If this option is not specified, ``~~/fonts`` will be used by default”; `--sub-ass-style-overrides=FontName=Arial,…`; `--sub-ass-override=force` |
| FFmpeg `ass=` nie czyta załączników; `subtitles=` czyta tylko załączniki otwieranego pliku napisów | [vf_subtitles.c#L290-L306](https://github.com/FFmpeg/FFmpeg/blob/eceaa54a3880dad139edb4e3bfe9c548246558cb/libavfilter/vf_subtitles.c#L290-L306) (`init_ass`: tylko `ass_set_fonts`) vs [L444-L468](https://github.com/FFmpeg/FFmpeg/blob/eceaa54a3880dad139edb4e3bfe9c548246558cb/libavfilter/vf_subtitles.c#L444-L468); sekcja `[Fonts]` ASS zawsze: `ass_set_extract_fonts(ass->library, 1)` (L154) |
| mkvmerge: załączniki | [mkvmerge.html](https://mkvtoolnix.download/doc/mkvmerge.html) §2.6: „If no MIME type is given a for an attachment, its type will be detected automatically.”, `--attachment-name`; §2.7 `-M, --no-attachments`; §12: „If a Matroska(tm) containing attachments file is used as an input file then mkvmerge(1) will copy the attachments into the new file.” |

## 3. Officina właściciela (F)

Rekordy `name` (`rf/mpv-fonts.json` i zrzut w logu sesji):

| Plik | p1 ID 1 / 4 / 6 (Mac) | p3 ID 1 (Windows) | p3 ID 4 / 6 | ID 16 | OS/2 |
|---|---|---|---|---|---|
| `ITC Officina Sans Std PL - Bold.ttf` | ITC Officina Sans Std / ITC Officina Sans Std Bold / OfficinaSansStd-Bold | **ITC Officina Sans Std PL Book** | OfficinaSansStdPL-Bold | ITC Officina Sans Std | waga 700, bold |
| `… - Bold Italic.ttf` | ITC Officina Sans Std / … Bold Italic / OfficinaSansStd-BoldItalic | **ITC Officina Sans Std PL Book** | OfficinaSansStdPL-BoldItalic | ITC Officina Sans Std | waga 700, bold+italic |

Oba pliki mają wszystkie 18 polskich liter. W szukanych katalogach (`portable_config\fonts`, `C:\Windows\Fonts`, `%LOCALAPPDATA%\Microsoft\Windows\Fonts` z 8 plikami) nie ma innego pliku Officina.

Test w mpv właściciela (`--no-config`, tylko jego `sub-font` i `sub-fonts-dir`; `rf/mpv-test/`):

```text
SRT                               (ITC Officina Sans Std PL Book, 400, 0)   -> OfficinaSansStdPL-Bold
ASS Bold=0 / Bold=-1 / Italic=-1  (…, 400, 0) / (…, 700, 0) / (…, 400, 100) -> Bold / Bold / BoldItalic
ASS Fontname = ID 16 „ITC Officina Sans Std”  -> Using default font family -> OfficinaSansStdPL-Bold
ASS Fontname = PS „OfficinaSansStdPL-Bold”     -> OfficinaSansStdPL-Bold
ASS Fontname = „NoSuchFontXyz”                 -> Using default font family -> OfficinaSansStdPL-Bold
```

Zrzut `rf/mpv-test/out/ass/00000001.png`: wiersze „Regular” i „Bold” mają identyczną grubość.
Wniosek: dziś każdy styl ASS z nieznanym fontem rysuje się u właściciela Officiną Bold. Brakujące polskie glify w Gandhi Sans też pochodzą z Officiny: test A w `rf/mux-test/mpv-A-owner-current.log` daje `Glyph 0x17C not found` → `Using default font family … OfficinaSansStdPL-Bold`. W mpv bez tej konfiguracji (test C) te same glify pochodzą z Ariala. Zrzut `rf/mux-test/out/C-typesetter-default/00000001.png` pokazuje mieszankę krojów w „gęślą”.

## 4. Eksperyment: korpus 40 par (F)

Komendy (z worktree `fuzzy`):

```bash
PYTHONIOENCODING=utf-8 uv run --frozen --with fonttools python -B rf/inventory.py   # pairs.json, fonts.json, mpv-fonts.json
python -B rf/summary.py                                                             # summary.txt
PYTHONIOENCODING=utf-8 uv run --frozen --with fonttools python -B rf/dialog_scope.py  # dialog-scope.txt
PYTHONIOENCODING=utf-8 uv run --frozen python -B rf/spoken_styles.py                  # spoken-styles.txt
```

`inventory.py` odtwarza dopasowanie libass z §2: rodzina p3 ID 1, pełna nazwa p3 ID 4 lub PS i ocena wariantu. Najpierw szuka w `fonts/` pary (odpowiednik załączników), potem w fontach systemu. Systemowe dopasowanie DirectWrite przybliżono tymi samymi regułami.

| Miara | Wynik |
|---|---|
| pliki fontów w `fonts/` par / unikalne (hash) / unikalne kroje | 776 / 216 / 184 |
| kroje bez ≥ 1 polskiej litery | **106 / 184** |
| style użyte w `Dialogue` | 313: 309 z fontów pary, 3 z systemu (Arial), 1 bez fontu (`FOT Manyo Gyosho Std Strp E`, szyld, 8023 zdarzeń FBF) |
| style, których rodzina nie ma polskich liter | 66 (szyldy, OP/ED i dialogi) |
| style DIALOG (`classify_styles`) | 121, wszystkie z fontów pary |
| główny font dialogu na parę | Gandhi Sans 20, Trebuchet MS 18, Roboto Medium 2 |
| style DIALOG bez polskich liter | **31, wszystkie Gandhi Sans**: brak `ąćęńśźżĄĆĘŃŚŹŻ` |
| `\fn` w zdarzeniach | 40 800 użyć, 214 par (para, nazwa): 213 z fontów pary, 1 brak (`Aria`, 1 użycie) |
| `\fn` bez polskich liter | 142 nazwy, 25 395 użyć (szyldy) |
| linie czytane przez lektora wg stylu | 15 978 w 116 stylach DIALOG, 2 w 1 stylu UNCERTAIN |
| linie szyldowe w stylach z liniami czytanymi | 19 (`spoken-styles.txt`); `\fn` w zdarzeniach stylów DIALOG: 4, wszystkie szyldowe; nazwany `\r` w stylach DIALOG: 0 |
| średnia szerokość 300 polskich linii dialogu (fs 75, skala jak w libass) | Gandhi Sans Bold 886 px; Officina Bold 826 (0,93×); Trebuchet MS 927 (1,05×); Trebuchet MS Bold 970 (1,09×) |
| polska referencja fansubu (`certain-dark-item-01/reference.pl.ass`) | dialogi w `Fontin Sans Rg-PL`, czyli w łatce PL fontu, nie w foncie typesettera |

Wykrywanie braku polskich liter: `TTFont(path).getBestCmap()` i sprawdzenie 18 kodów z `ąćęłńóśźżĄĆĘŁŃÓŚŹŻ`. Wynik zgadza się z libass: Gandhi bez `ż`/`ź` (`0x17C`, `0x179`) w logach testów A–C.

## 5. Projekt podmiany czcionki dialogów (W)

**Które style.** Podmieniamy style, w których lektor czyta większość linii (decyzja `spoken`). W korpusie to 116 stylów DIALOG z 15 978 liniami czytanymi i 19 szyldowymi. Poza nimi czytane są tylko 2 linie w jednym stylu UNCERTAIN, który ma też 2 linie szyldowe. Werdykt DIALOG daje prawie ten sam zbiór. Kryterium „większość spoken” pozostanie poprawne, gdy podział B z `fuzzy-signs-and-split.md` zmieni decyzje. Zmieniamy tylko `Fontname`; `Bold`, `Italic`, `Fontsize`, `ScaleX/Y`, obrys i cień zostają.

**Szyldy w tych stylach.** 19 linii `displayed` dostaje na początku `{\fn<oryginalny Fontname>}`, więc zostaje w kroju typesettera. Istniejące `\fn` w liniach zostają nietknięte. Dziś są tylko w 4 liniach szyldowych, a `\fn` ma pierwszeństwo przed stylem. Ryzyko szczątkowe: nienazwany `\r` w linii szyldowej przywraca font stylu, czyli nowy. Nazwanych `\r` jest 0, nienazwanych nie liczono.

**Nazwa w stylu.** Wpisujemy rodzinę p3 ID 1 odczytaną z pliku przez fonttools, tu `ITC Officina Sans Std PL Book`. Nie używamy nazwy pliku ani ID 16, bo ID 16 nie trafia (test „Typographic”).

**Warianty.** Właściciel ma Bold (700) i Bold Italic. Styl z `Bold=0` też dostanie plik Bold, bo jest jedynym wariantem rodziny. libass nie pocienia kroju, a sztucznego pogrubienia nie doda (700 > 400+150 nie zachodzi). Efekt jest identyczny jak dziś w SRT właściciela. `\i1` i `Italic=-1` dostają Bold Italic. Bez pliku Bold Italic libass pochyli Bold sztucznie (ass_font.c L806-L808). Dołączamy wszystkie pliki z folderu właściciela o tej samej rodzinie p3 ID 1.

**Miejsce w potoku.** Podmiana idzie na kopii `split.subs`, zaraz po `split_subtitles` i przed `translation_verses` (`application/translation_handler.py:304-310`). Wzorzec kopii daje `reflow_polish_dialogue` (`subtitles/service.py:139-158`), dalej `write_translated` zapisuje style bez zmian. Dziś łamanie liczy znaki, więc kolejność nie zmienia wyniku. `fuzzy-line-breaks.md` (l. 80-82) mierzy jednak prawdziwym fontem, więc podmiana musi poprzedzać pomiar, a indeks fontów z §A.3 musi zawierać plik właściciela. Officina jest o 7% węższa od Gandhi Sans Bold i o 15% od Trebuchet MS Bold, więc zawijanie libass grozi rzadziej.

**Skąd plik.** Nowe pole w panelu, np. `dialogue_font_file` typu `OPTIONAL_STRING`, ze ścieżką do pliku. Puste pole wyłącza funkcję. Zapis idzie przez `field_catalog.py` i `user_settings.py`, jak `subtitle_max_chars_per_line`. Walidacja przy starcie przetwarzania: plik czytelny dla fonttools, ma p3 ID 1 i wszystkie 18 polskich liter.

**Brak pliku lub wariantu.** Brak pliku albo nieudana walidacja: bez podmiany, z ostrzeżeniem w raporcie przebiegu (nie przerywa pracy). Brak Bold Italic: sztuczna kursywa. Plik z jednym wariantem regular przy stylu `Bold=-1`: sztuczne pogrubienie (L809-L811).

**MKV.** `--attach-file <plik>` dla każdego wariantu, dopisane w `merge_command` i `container_merge_command` po plikach wejściowych. Lista plików idzie w `CompositionPlan`/`ContainerCompositionRequest` (`composition/types.py`), a decyzję podejmuje application (`composition/AGENTS.md:11-13`). MIME zostawiamy mkvmerge: test dał `font/ttf`, który jest na liście mpv. mkvmerge **nie odrzuca duplikatów nazw**: test `rf/mux-test/dup.mkv` to dwa razy `007-font-8-GandhiSans-Bold.otf` przy kodzie 0. Dołączenie pomijamy więc, gdy źródło ma już załącznik o tej samej nazwie i rozmiarze; `mkvmerge -J` podaje `file_name` i `size`. Test B (`rf/mux-test/mpv-B-attached-default.log`, pusty folder fontów, domyślne `sub-font`) potwierdza: `(ITC Officina Sans Std PL Book, 700, 0) -> OfficinaSansStdPL-Bold` z samego załącznika.

**SRT.** SRT nie ma stylów. mpv rysuje je czcionką `sub-font`, u właściciela Officiną Bold (test SRT), więc nic nie zmieniamy. Załącznik w MKV z SRT nie zmienia kroju.

**MP4 z wypalaniem.** Dziś libass w FFmpeg nie widzi żadnego fontu z MKV ani fontu właściciela: `burn1.log` pokazuje Gandhi Sans i Officina → Arial-BoldMT. Z `fontsdir` zawierającym wyciągnięte załączniki libass trafia w prawdziwe kroje (`burn2.log`). Naprawa to osobny błąd: wyciągnąć załączniki jak `render.py:122-147`, dodać plik właściciela i przekazać `fonts_dir`. Alternatywa bez katalogu: osadzić font w sekcji `[Fonts]` ASS. libass ją czyta (`ass.c` L1079-L1130), FFmpeg zawsze, mpv przy `embeddedfonts=yes`. pysubs2 trzyma ją jako `fonts_opaque`. Kosztem jest UUencode (+~33%). Wariantu nie testowano.

**Ryzyka.**

- Licencja: ITC Officina Sans to komercyjna rodzina ITC; plik „Std PL” jest przerobiony, bo nazwy zmieniono tylko w rekordach Windows. Odnotowane, nie oceniane.
- Rozmiar: +119 035 B na MKV (233 169 → 352 204 B, dwa pliki).
- Duplikaty nazw: opisane wyżej.
- Zmiana wyglądu dialogu wobec stylu typesettera: obrys i cień dobrano do innego kroju, a x-height się różni. Do oceny na galerii.

**Sprzeczności z dokumentami do aktualizacji po decyzji właściciela.**

- `visual-quality.md` §6 („Nie robimy: … zmiany czcionki”).
- `fuzzy-line-breaks.md` l. 12 i 41 (font nienaruszalny).
- `fuzzy-signs-and-split.md` §A.3 podaje „(1/16, 4, 6)” jako klucz indeksu, a libass nie dopasowuje ID 16 przy zwykłym wyborze. ID 16 tylko w ścieżce zastępczej dostawcy.

## 6. Rekomendacja pierwszego kroku (W)

1. Podmiana `Fontname` w stylach z większością linii `spoken` na rodzinę p3 ID 1 z pliku z ustawienia oraz `{\fn<oryginał>}` na liniach `displayed` w tych stylach. To jedna czysta funkcja w domenie `subtitles` z testem na korpusie.
2. Dołączenie wariantów tej rodziny do MKV przez `--attach-file`, z pominięciem duplikatu nazwy i rozmiaru.
3. fonttools w kroku 1 tylko do odczytu rodziny i walidacji pliku właściciela. Wykrywanie braku polskich liter w fontach szyldów należy do indeksu fontów z §A.3 (status przybliżony, `u = 0,07`), nie do pierwszego kroku.
4. Poza pierwszym krokiem: naprawa fontów przy wypalaniu MP4 (osobny błąd, istnieje już dziś) i osadzanie w `[Fonts]`.

Największy zysk daje punkt 1. Usuwa mieszankę krojów w 20/40 parach (Gandhi Sans) i zgadza się z tym, co właściciel widzi w SRT.

## Niewiadome

- Wygląd Officiny Bold z obrysem i cieniem stylu typesettera: obejrzano jedną klatkę testową, nie galerię.
- Kolejność rozstrzygania remisu libass przy dwóch identycznych krojach (załącznik i folder fontów): nie sprawdzano. Przy tym samym pliku wynik jest ten sam.
- Systemowe dopasowanie DirectWrite przybliżono regułami libass. Dotyczy 3 stylów (Arial).
- Nienazwane `\r` w liniach szyldowych stylów dialogowych: nie liczono.
- Warunki licencji wersji PL.
- Czy właściciel ma gdzieś prawdziwy plik Book (waga 400). Szukano tylko w trzech wskazanych katalogach.

## Źródła i artefakty

- libass @ `f61db56`: `ass_fontselect.c`, `ass_font.c`, `ass_parse.c`, `ass.c`; mpv @ `fffe7a2`: `sub/sd_ass.c`, `sub/ass_mp.c`, `DOCS/man/options.rst`; FFmpeg @ `eceaa54`: `libavfilter/vf_subtitles.c`, `doc/filters.texi` (`fontsdir`). Kopie w `rf/sources/`.
- mkvmerge: https://mkvtoolnix.download/doc/mkvmerge.html (dostęp 2026-10-18; kopia `rf/sources/mkvmerge.txt`).
- `rf/inventory.py`, `rf/summary.py`, `rf/dialog_scope.py`, `rf/spoken_styles.py` → `pairs.json`, `fonts.json`, `mpv-fonts.json`, `summary.txt`, `dialog-scope.txt`, `spoken-styles.txt`.
- `rf/mpv-test/`: `test.srt`, `test.ass`, `mpv-srt.log`, `mpv-ass.log` (mpv zakończył się segfaultem przy wyjściu po zapisaniu klatki), `out/`.
- `rf/mux-test/`: `test.ass`, `only-typesetter.mkv`, `with-owner-font.mkv`, `dup.mkv`, `mpv-A/B/C-*.log`, `burn1.log`, `burn2.log`, `out/`.
