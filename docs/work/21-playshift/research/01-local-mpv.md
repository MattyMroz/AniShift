---
kind: research
id: playshift-r1-local
date: 2026-10-31
subject: C:\Users\MattyMroz\Videos\mpv (stan na 2026-10-31)
---

# R1: inwentaryzacja lokalnego odtwarzacza mpv właściciela

Wszystkie odczyty były tylko do odczytu. Ścieżki względne liczone od `C:\Users\MattyMroz\Videos\mpv`. Numery linii dotyczą plików w stanie z 2026-10-31. Oznaczenia: **[F]** fakt z dowodem, **[W]** wniosek, **[?]** niewiadoma.

## 1. Podsumowanie dla decyzji

1. **[F] Baza to mpv-lazy „2023EX” (tag `20231101`, opublikowany 2023-10-31)** z repozytorium hooke007, dziś `hooke007/mpv_PlayKit` (stare `hooke007/MPV_lazy` jest zarchiwizowane). Zgadzają się: k7sfunc `0.1.23`, embed Python `3.11.6`, VapourSynth `R65`, identyczny `profiles.conf` i ten sam układ `input_uosc.conf`. Właściciel mocno go przerobił: polskie komentarze i menu, własne skrypty `.vpy` do interpolacji, skrypty do obrazów, SmartCopyPaste i własny styl napisów.
2. **[F] Wszystko jest sprzed 3 lat.** mpv `v0.36.0-711-g250429da` (build 2023-11-02), libplacebo v6.338, FFmpeg N-112646. Aktualne wydanie stabilne to v0.41.0 (2025-12-21), w którym domyślnym `vo` jest już `gpu-next`. Ten build działa na `vo=gpu`, bo nie ustawia `vo`, a w tej wersji domyślne jest `gpu`. Sam PlayKit wypuścił od tamtej pory 11 paczek, ostatnią `20260510`.
3. **[F] Nic nie aktualizuje się samo.** yt-dlp `2026.07.04` właściciel podmienił ręcznie 2026-07-16 (aktualne: `2026.10.26`). Polecenie uosc `update` odwołuje się do nieistniejącego `elements/Updater.lua`.
4. **[F/W] Interpolacja jest dziś w trzech rodzinach:** MVTools (CPU) x2/60/120/170, SVP (svpflow) x2/60/120/170, RIFE (ncnn-Vulkan, model `rife-v4`) wyłącznie x2 przy 480p/720p/1080p. **Nie ma RIFE do ~170 fps, TensorRT, vs-mlrt ani AnimeJaNai.** Wtyczka RIFE to stara `com.holywu.rife`. Jej lista modeli kończy się na `rife-v4`, więc foldery modeli v4.6 i v4.8 najpewniej leżą martwe [W].
5. **[F→W] Profil `[vsync_auto]` (`profiles.conf:21-26`) działa zawsze na monitorze 170 Hz** (warunek `display_fps>122`). Wyłącza `interpolation` i przestawia `video-sync=audio`, więc `display-resample` i `interpolation=yes` z `mpv.conf:102-105` w praktyce nie działają u właściciela.
6. **[F] Upscaling to shadery GLSL, nie VapourSynth.** Pod `Ctrl+1..7` jest 7 przełączników. Zapamiętany globalnie łańcuch (`saved-props.json`) to 6 shaderów naraz, w tym trzy podwajające rozdzielczość (Anime4K GAN x2, NNEDI3, FSRCNNX x2) oraz FSR EASU i KrigBilateral. Ten łańcuch ładuje się przy każdym starcie.
7. **[F] Skróty są w jednym pliku `portable_config/input_uosc.conf`**, a `input-builtin-bindings=no` (`mpv.conf:35`) wyłącza wbudowane skróty mpv. Właściciel ma pod palcami: prędkość `[` `]` `\` `BS`, interpolację w górnym rzędzie z Shiftem `~ ! @ # $ % ^ & * ( ) _`, shadery `Ctrl+`` `` i `Ctrl+1..7`, korektor obrazu `1..0` z `Ctrl+9/0/BS`, obrót `r`/`Shift+R`, odbicia `Shift+f`/`Alt+f`, pan i zoom myszą oraz strzałkami z `Ctrl`/`Alt`, a do tego schowek `Ctrl+C/V` (wklej link → gra).
8. **[F] Luki w skrótach:** z klawiatury nie da się przełączyć ścieżki napisów ani audio, ukryć napisów, przejść do rozdziału ani do następnego pliku na liście, usunąć pliku ani zrobić zrzutu bez OSD i napisów.
9. **[F] Usuwanie plików już istnieje w uosc 5.0.0** (`delete-file-next/prev/quit`), ale nie ma przypisanego klawisza, a domyślne `use_trash=false` oznacza trwałe `cmd /C del`.
10. **[F] Chiński w interfejsie właściwie zniknął:** menu uosc (`lib/lang.lua`) i opisy menu są po polsku. Chiński został w `profile-desc` w `profiles.conf`, w 359 liniach `k7sfunc.py` (komentarze i komunikaty błędów), w komentarzach `MEMC_*.vpy`, w dwóch komunikatach OSD (uosc i thumbfast) oraz w plikach `installer/*-mode.bat` zapisanych w GB18030.
11. **[F] Instalator jest zarejestrowany w systemie:** App Paths wskazuje `C:\Users\MattyMroz\Videos\mpv\mpv.exe`, istnieje 86 ProgId `io.mpv.*`, a `.mkv` i `.mp4` mają UserChoice = mpv. Zmiana ścieżki odtwarzacza wymaga ponownej rejestracji.
12. **[F] Aktualizacja mpv do ≥0.39 wywróci obecną konfigurację:** `sub-ass-vsfilter-blur-compat` (`mpv.conf:156`) i script-opt `console-scale` (`script-opts.conf:10`) zostały usunięte. Komentarz `mpv.conf:118` pokazuje, że właściciel trafił już raz na błąd startu przy `tone-mapping-mode`.

## 2. Inwentarz

### 2.1 Wersje komponentów

| Komponent | Wersja w paczce | Dowód | Aktualny upstream (sprawdzony 2026-10-31) |
|---|---|---|---|
| mpv | `v0.36.0-711-g250429da`, build 2023-11-02 | `mpv.com --no-config --version`; FileVersion `mpv.exe` | v0.41.0 (2025-12-21), `gh api repos/mpv-player/mpv/tags` |
| libplacebo | `v6.338.0-47-g39b87ed-dirty` | jw. | — |
| FFmpeg | `N-112646-g28840cf49` (libavcodec 60.32.102) | jw. | — |
| VapourSynth | Core R65, API R4.0/R3.6, portable | `VSPipe.exe --version`; pusty plik `portable.vs` | R81 (2026-10-04) |
| Python (embed) | 3.11.6 | FileVersion `python311.dll`; `python311._pth` | — |
| yt-dlp | 2026.07.04 (plik z 2026-07-16) | FileVersion `yt-dlp.exe` | 2026.10.26 |
| k7sfunc | 0.1.23 | `k7sfunc.py:5` | PlayKit miał 0.4.7 już w 2024-01 |
| qtgmc.py | 0.0.3 | `qtgmc.py:2` | — |
| uosc | 5.0.0, wersja zmodyfikowana przez mpv-lazy i przetłumaczona na PL | `scripts/uosc/main.lua:9` | 5.13.0 (2026-08-03) |
| thumbfast | commit `4241c7da` | `scripts/thumbfast.lua:3` | HEAD `0f711de3` (2026-03-08) |
| save_global_props | z zenwarr `remember-props.lua`, commit 20220811 | `scripts/save_global_props.lua:3-4` | — |
| SmartCopyPaste | 3.1 (2022, Eisa AlAwadhi) | `scripts/SmartCopyPaste.lua:5` | — |
| RIFE (VS) | `com.holywu.rife`, ncnn-Vulkan; modele wbudowane do `rife-v4`; ma `model_path`, `fps_num/fps_den` | `strings vapoursynth64/plugins/RIFE.dll` | następca: `styler00dollar/VapourSynth-RIFE-ncnn-Vulkan` r9_mod_v33 (2025-09) |
| MVTools | „MVTools v23” `com.nodame.mvtools`, **dwie kopie**: `mvtools.dll` i `libmvtools.dll` | `strings` obu DLL | — |
| SVP | `svpflow1_vs64.dll`, `svpflow2_vs64.dll` | listing `vapoursynth64/plugins` | — |
| inne VS | `MiscFilters.dll` (`com.vapoursynth.misc`, SCDetect), `VMAF.dll`, `libfftw3f-3.dll`, `vcomp140.dll` (dodany 2026-02-09), `coreplugins/AvsCompat.dll` | listing | — |
| 7-Zip | 23.01 | FileVersion `7z.exe` | — |
| Pismo File Mount | 1.0.0.192 (2018) | FileVersion `pfm-192-vapoursynth-win.exe` | — |

Ustalenie pochodzenia: notatki wydania PlayKit `20231101` („2023EX”) wymieniają `mpv : git-20231031-908e75e`, `python : embed-3.11.6`, `vapoursynth : portable-r65` i k7sfunc 0.1.23, a także nowy profil `[speed_limit]` i opis „ostatnia wersja z presetem `vo_gpu`”. Hash mpv różni się od lokalnego (`250429da` zamiast `908e75e`), a build pochodzi z 2023-11-02 [F]. Najpewniej to ten sam pakiet z nieco nowszym `mpv.exe` [W]. `profiles.conf` jest bajt w bajt identyczny z upstreamem z commita `054faa95` (`diff`) [F].

Daty plików [F]: prawie wszystko ma mtime `2025-12-10 18:49`, więc to data skopiowania paczki, a nie powstania [W]. Późniejsze zmiany właściciela: `vs/rife_480p_x2.vpy` (2026-01-25), `vcomp140.dll` (2026-02-09), `installer/` (2026-03-31), `yt-dlp.exe` (2026-07-16), `input_uosc.conf` i `script-opts.conf` (2026-08-06 23:59), `shaders/` i `_cache/` (2026-08-07 00:00), `mpv.conf` (2026-10-17), `saved-props.json` (2026-10-31 00:06, czyli ostatnie użycie). `mpv-install.bat` w roocie ma datę 2016-11-03 i różni się od `installer/mpv-install.bat` wyłącznie końcami linii (`diff` po usunięciu `\r` jest pusty).

### 2.2 Struktura i rozmiary (`du -sh`)

Całość zajmuje 251 MB: `mpv.exe` 60 MB, `yt-dlp.exe` 18 MB, `vapoursynth64/` 73 MB (z tego modele RIFE 51 MB), `portable_config/fonts` 17 MB (z tego LXGW WenKai 15.9 MB) i `portable_config/_cache` 45 MB.

Root:
- **Odtwarzacz:** `mpv.exe`, `mpv.com`, `manual.pdf` (podręcznik mpv z 2023-11-02), `mpv-document.ico`, `mpv-install.bat`, `mpv-uninstall.bat`, `LICENSE.MD` (chiński, licencje mpv-lazy).
- **Python embed:** `python.exe`, `pythonw.exe`, `python311.dll`, `python311.zip`, `python311._pth`, `*.pyd`, `libcrypto/libssl 1.1 i 3`, `sqlite3.dll`.
- **VapourSynth portable:** `VapourSynth.dll`, `VSScript.dll`, `VSPipe.exe`, `vapoursynth.cp311-win_amd64.pyd`, `portable.vs`, `vapoursynth64/`. Do tego resztki niepotrzebne do odtwarzania [W]: `VSScriptPython38.dll`, `vapoursynth.cp38-win_amd64.pyd`, `vs-detect-python.bat`, `VSVFW.dll`, `AVFS.exe`, `pfm-192-vapoursynth-win.exe`, `vsrepo.py`, `vsgenstubs.py`, `vsgenstubs4/`, `setup.py`, `MANIFEST.in`, `7z.exe/7z.dll` (dla vsrepo).
- **Biblioteki VS w Pythonie:** `k7sfunc.py`, `qtgmc.py`.
- **Pobieranie z sieci:** `yt-dlp.exe`.
- **Runtime MSVC:** `msvcp140*.dll`, `vcruntime140*.dll`, `concrt140.dll`, `vccorlib140.dll`.

`portable_config/`:
- `mpv.conf` (187 l.), `profiles.conf` (62 l.), `script-opts.conf` (87 l.) i `input_uosc.conf` (161 l.). Pliku `input.conf` nie ma: `mpv.conf:6` ustawia `input-conf = "~~/input_uosc.conf"`.
- `saved-props.json`: `{"volume":102,"speed":1,"mute":false,"glsl-shaders":[KrigBilateral, AMD_FSR_EASU_rgb, Anime4K_Restore_CNN_L, Anime4K_UPscale_GAN_x2_M, nnedi3_nns128_win8x4, FSRCNNX_x2_16_0_4_1]}`.
- `scripts/` (13 pozycji, sekcja 2.4), `script-opts/` (6 plików), `shaders/` (28 plików), `vs/` (21 skryptów `.vpy`), `fonts/` (12 plików).
- `_cache/`: `shader/` (552 pliki, 44 MB, cache shaderów), `watch_later/` (817 plików, 1.2 MB, zapamiętane pozycje), `ambient-blur.json` (`{"preset":"glow"}`, osierocony: skryptu ambient nie ma).
- `cache/`: 48 plików o nazwach-hashach po 2–23 KB, 388 KB, z 2026-08-06. Pochodzenie nieznane [?]; możliwe, że to ślad próby z nowszym mpv, którego domyślne katalogi cache to `~~cache/` [W].

### 2.3 `mpv.conf` – stan efektywny

Sekcje opisane po polsku. Komentarz w `mpv.conf:2` nadal wskazuje dokumentację mpv-lazy. Najważniejsze ustawienia [F]:

| Obszar | Ustawienie (linia) | Uwagi |
|---|---|---|
| wejście | `input-conf=~~/input_uosc.conf` (6), `input-builtin-bindings=no` (35), `input-ipc-server=mpvpipe` (34) | Pipe o stałej nazwie `\\.\pipe\mpvpipe`; repo AniShift się do niego nie odwołuje (grep: 0 trafień). |
| dekodowanie | `hwdec=auto-copy` (22), `hwdec-codecs=h264,hevc,vp8,vp9,av1,prores` (23) | `vo`/`gpu-context` nieustawione (17–18 zakomentowane), więc `vo=gpu` jako domyślne tej wersji [W]. |
| okno | `border=no` (44), `autofit-smaller=40%x40%` (45), `keepaspect-window=no`, `hidpi-window-scale=no`, `keep-open=yes`, `idle=yes` | Bez ramki: belka uosc pełni rolę paska tytułu (`top_bar='no-border'`). |
| wznowienia | `save-position-on-quit=yes` (39), `watch-later-options=start,vid,aid,sid` (40), `watch-later-dir=~~/_cache/watch_later` | Profil `[save_props_auto]` wyłącza zapis pod koniec pliku i dla krótkich plików. |
| bufor | `demuxer-max-bytes=1024MiB` (50) | |
| OSD | czcionka 40, `osd-bar-*`, `osd-playing-msg=${filename}` (62–74) | |
| audio | `ao=wasapi`, `volume-max=150`, `audio-channels=stereo`, `ad-lavc-downmix=yes`, `alang=pl,…,eng,…,jpn` (81–90) | `volume` pamiętane globalnie przez `save_global_props`. |
| wideo | `video-sync=display-resample` (102), `video-sync-max-video-change=5`, `interpolation=yes` (104), `tscale=linear`, `scale=spline36`, `cscale=bilinear`, `dscale=bicubic`, `gamut-mapping-mode=clip` | Na 170 Hz unieważnione przez `[vsync_auto]` (sekcja 5). `dither-depth`, `deband` i `icc-profile-auto` zakomentowane. |
| shadery | `glsl-shaders-append=~~/shaders/AMD_FSR_EASU_rgb.glsl` (131) | Nadpisywane przez `saved-props.json` (komentarz `mpv.conf:3`). |
| OSC | `osc=no` (126) | UI robi uosc. |
| napisy | `sub-auto=fuzzy`, `slang=pl,pol,und,eng,en,jp,jap`, `sub-font="ITC Officina Sans Std PL Book"` rozmiar 51, obwódka 2, cień 1.25, `sub-margin-x=100`, `sub-margin-y=44`, `sub-ass-force-margins=no`, `sub-ass-vsfilter-blur-compat=no` (138–166) | Zob. problem 8 (sama odmiana Bold). |
| zrzuty | `png`, szablon `~~desktop/MPV Screens/MPV-%F-…-F%{estimated-frame-number}` (173–183) | |

`mpv.com --no-config --list-options` potwierdza, że każda opcja z `mpv.conf`, `profiles.conf` i `installer/mpv-BenchMark.conf` istnieje w tym buildzie. Jedyny wyjątek to zakomentowane `tone-mapping-mode` („removed [deprecated]”) [F].

Względem upstreamu 2023EX właściciel zmienił [F] (`diff` z `054faa95:portable_config/mpv.conf`): dodał `prores` do `hwdec-codecs`, `input-ipc-server`, `border=no`, `osd-blur`, `ad-lavc-downmix`, `tscale=linear`, polskie `alang/slang`, cały styl napisów (font, rozmiar, kolory, cień, marginesy), `volume-max=150`, `autofit-smaller=40%` i szablon zrzutów. Usunął chińskie języki i `screenshot-png-compression`.

### 2.4 Skrypty (`portable_config/scripts/`)

| Skrypt | Pochodzenie | Stan | Rola |
|---|---|---|---|
| `uosc/` (main.lua i 15 elementów, 7 bibliotek) | uosc 5.0.0 w wersji mpv-lazy | aktywny, menu i przyciski po polsku (`lib/lang.lua`) | UI: belka, oś czasu, przyciski, menu pod PPM budowane z komentarzy `#!` w `input_uosc.conf` |
| `thumbfast.lua` | po5/thumbfast `4241c7da` | aktywny, `min_duration=30`, `network=false` | miniatury na osi czasu; dla linków ich nie ma |
| `save_global_props.lua` | zenwarr, wersja mpv-lazy | aktywny, `props=volume,glsl-shaders` | globalnie zapamiętuje głośność i łańcuch shaderów |
| `SmartCopyPaste.lua` | Eisa AlAwadhi 3.1 | aktywny (wymuszone skróty) | `Ctrl+C` kopiuje ścieżkę/URL z czasem, `Ctrl+V` wkleja: link/plik → odtwarza, czas → przewija |
| `image-positioning.lua` | occivink/mpv-image-viewer | aktywny | `rotate-video`, `pan-image`, `align-border`, `cursor-centric-zoom`, `drag-to-pan`, `pan-follows-cursor` |
| `minimap.lua` | occivink | aktywny, `enabled=yes` | minimapa przy zoomie |
| `ruler.lua` | occivink | ładowany, bez skrótu | linijka; nieosiągalna z klawiatury |
| `detect-image.lua` | occivink | ładowany, wszystkie komendy puste (`script-opts/detect_image.conf`) | nic nie robi |
| `freeze-window.lua` | TheAMM | aktywny | po zmianie rozmiaru OSD ustawia `geometry` na bieżący rozmiar (stabilizacja okna) |
| `equalizer_TEST.lua`, `manga-reader-TEST.lua`, `status-line-TEST.lua`, `tts-subs-test.lua` | eksperymenty właściciela | **w 100% zakomentowane** (0 linii kodu) | martwe; `script-opts/status_line.conf` też martwy |

Wbudowane skrypty mpv: `console`, `stats`, `ytdl_hook`. `osc` jest wyłączone. `input-builtin-bindings=no` pomija tylko wbudowany `input.conf` (`input/input.c:1367` w v0.37.0), więc domyślne skróty skryptów działają dalej, np. `i` dla jednorazowych statystyk [F].

`script-opts.conf` [F]: `console-scale=1.5` (10), `stats-*` (19–22), `ytdl_hook-all_formats=yes`, `ytdl_hook-force_all_formats=yes` (29–30), `save_global_props-props=volume,glsl-shaders` (45), `thumbfast-min_duration=30` (61) oraz `uosc-video_types/audio_types/image_types/subtitle_types` (78–81).

### 2.5 Shadery (`portable_config/shaders/`, 28 plików)

Pod skrótami jest 7 [F]: `KrigBilateral` (chroma), `AMD_FSR_EASU_rgb` (FSR 1.0 EASU), `Anime4K_Restore_CNN_L` (v4.0), `Anime4K_Upscale_GAN_x2_M` (v4.1), `adaptive_sharpen`, `nnedi3_nns128_win8x4`, `FSRCNNX_x2_16_0_4_1`. Kolejnych 21 żaden skrót nie używa: pozostałe Anime4K v3.2/v4.0/v4.1 (Restore M/Soft, GAN_UL, Upscale CNN M/L, Darken, Thin, Denoise, AutoDownscalePre), `AMD_FSR.glsl`, `AMD_FSR_rgb`, `AMD_FSR_EASU_luma`, `FSRCNNX_x2_8`, `SSimDownscaler`, `adaptive_sharpen_luma`, `hdeband`, `nlmeans_dx`, `nnedi3_nns128_win8x6` i `test.glsl` (kopia Anime4K Darken HQ).

### 2.6 VapourSynth (`portable_config/vs/`, 21 skryptów)

| Skrypt | Skrót | Mechanizm | Kluczowe parametry |
|---|---|---|---|
| `mvtools_x2.vpy` | `!` | MVTools BlockFPS, ×2, CPU | `blksize 32→16 Recalculate`; wyjątek, gdy `container_fps>32` |
| `mvtools_60/120/170.vpy` | `@` `#` `$` | MVTools BlockFPS (wariant KCCat), cel 60/120/170 | `blksize=64`, `mode=2`; wyjątek, gdy `container_fps>32` |
| `memc_svp_x2.vpy` | `%` | k7sfunc `SVP_LQ` | `H_Pre=1440` (zmniejsza źródło do 1440p) |
| `memc_svp_60/120/170.vpy` | `^` `&` `*` | k7sfunc `SVP_PRO`, cel `Fps_Num/1001` | `Abs=True`, `Nvof=False` (NVIDIA Optical Flow wyłączony) |
| `rife_480p_x2.vpy` | `(` | `core.rife.RIFE(model=9)` ×2 po zmniejszeniu do 854×480 | `gpu_thread=8`, `skip_threshold=60`; limit `container_fps>64` |
| `rife_720p_x2.vpy` | `)` | jw., 1280×720 | limit 32 fps |
| `rife_1080p_x2.vpy` | `_` | jw., 1920×1080 | limit 32 fps |
| `rife_2x.vpy`, `rife_std.vpy`, `mvtools_30.vpy` | — | starsze warianty | niepodpięte |
| `MEMC_MVT_LQ/MVT_STD/RIFE_STD` w parach `_NEW` i `_old` | — | oryginały mpv-lazy na k7sfunc | niepodpięte, komentarze po chińsku |

**AnimeJaNai: brak [F]** (`find` nie znalazł żadnego `*janai*`, `*.onnx`, `*.engine` ani `vsmlrt*`). k7sfunc zawiera funkcje dla vs-mlrt/TensorRT (`RIFE_NV`, `CUGAN_NV`, `ESRGAN_NV` i inne), ale moduł `vsmlrt` nie jest zainstalowany, więc te funkcje nie działają [F].

## 3. Pełna tabela skrótów

Źródło: `portable_config/input_uosc.conf` (podany numer linii), chyba że zaznaczono inaczej. Opisy po polsku pochodzą z komentarzy `#!` widocznych w menu uosc. **W `input_uosc.conf` nie ma już chińskich opisów**, bo wszystkie przetłumaczono. Chińskie oryginały znajdują się w upstreamie (`054faa95:input_uosc.conf`).

### Prędkość

| Klawisz | Akcja | Linia |
|---|---|---|
| `[` | `add speed -0.1` | 19 |
| `]` | `add speed +0.1` | 20 |
| `BS` (Backspace) | `set speed 1` | 21 |
| `\` | `set speed 2` | 22 |
| — | dolna granica prędkości 0.1 (profil `[speed_limit]`) | `profiles.conf:7-10` |
| mysz | element prędkości uosc, krok 0.1 | `uosc/main.lua:48` |

Właściciel zmienił upstream, który miał `[`/`]` jako cykl prędkości 1/1.2/1.5/2 i `{`/`}` jako ±0.1 (`054faa95:input_uosc.conf:19-22`) [F].

### Interpolacja (filtr VapourSynth, górny rząd z Shiftem)

| Klawisz | Akcja | Linia |
|---|---|---|
| `~` | `vf clr ""`, opisane jako „Wyłącz Interpolację”, ale czyści **cały** łańcuch vf, także odbicia | 36 |
| `!` | MVTools ×2 (CPU) | 37 |
| `@` | MVTools 60 | 38 |
| `#` (`SHARP`) | MVTools 120 | 39 |
| `$` | MVTools 170 | 40 |
| `%` | SVP ×2 (GPU) | 41 |
| `^` | SVP 60 | 42 |
| `&` | SVP 120 | 43 |
| `*` | SVP 170 | 44 |
| `(` | RIFE ×2 przy 480p | 45 |
| `)` | RIFE ×2 przy 720p | 46 |
| `_` | RIFE ×2 przy 1080p | 47 |

### Upscaling i shadery

| Klawisz | Akcja | Linia |
|---|---|---|
| ``Ctrl+` `` | wyczyść wszystkie shadery | 49 |
| `Ctrl+1` | przełącz KrigBilateral | 50 |
| `Ctrl+2` | przełącz AMD_FSR_EASU_rgb | 51 |
| `Ctrl+3` | przełącz Anime4K_Restore_CNN_L | 52 |
| `Ctrl+4` | przełącz Anime4K_UPscale_GAN_x2_M | 53 |
| `Ctrl+5` | przełącz adaptive_sharpen | 54 |
| `Ctrl+6` | przełącz nnedi3_nns128_win8x4 | 55 |
| `Ctrl+7` | przełącz FSRCNNX_x2_16 | 56 |
| (`Ctrl+8`) | test.glsl, zakomentowane | 57 |
| `Ctrl+r` | wyczyść zapamiętane właściwości (`save_global_props clean_data`) | 81 |

### Filtry obrazu (korektor)

| Klawisz | Akcja | Linia |
|---|---|---|
| `1` / `2` | kontrast −1 / +1 | 65–66 |
| `3` / `4` | jasność −1 / +1 | 67–68 |
| `5` / `6` | gamma −1 / +1 | 69–70 |
| `7` / `8` | nasycenie −1 / +1 | 71–72 |
| `9` / `0` | barwa −1 / +1 | 73–74 |
| `Ctrl+9` | „Combat mode”: kontrast 10, jasność −5, nasycenie 30 | 75 |
| `Ctrl+0` | „Sport mode”: kontrast 20, jasność −10, nasycenie 50 | 76 |
| `Ctrl+BS` | reset korektora | 77 |

### Obraz: obrót, odbicia, pan i zoom

| Klawisz | Akcja | Linia |
|---|---|---|
| `r` | obrót +90° (`video-rotate` przez `image-positioning`) | 32 |
| `Shift+R` | obrót −90° | 33 |
| `Shift+f` | odbicie poziome (`vf toggle hflip`) | 30 |
| `Alt+f` | odbicie pionowe (`vf toggle vflip`) | 31 |
| `Alt+BS`, `MBTN_MID` | reset pan i zoom | 34, 139 |
| `Ctrl+WHEEL_UP/DOWN`, `Alt+WHEEL_UP/DOWN` | zoom ±0.1 względem kursora | 130–131, 136–137 |
| `Ctrl+MBTN_RIGHT`, `Alt+MBTN_RIGHT` | przeciągnij, by przesunąć | 127, 133 |
| `Ctrl+MBTN_LEFT`, `Alt+MBTN_LEFT` | obraz podąża za kursorem | 128, 134 |
| `Ctrl+strzałki` | przesuń obraz o 0.1 | 148–151 |
| `Alt+strzałki` | przesuń obraz o 0.01 | 153–156 |
| `Ctrl+Shift+strzałki` | dosuń do krawędzi | 158–161 |

### Napisy

| Klawisz | Akcja | Linia |
|---|---|---|
| `z` / `x` | opóźnienie napisów −/+100 ms | 27–28 |
| `Shift+BS` | reset opóźnień audio i napisów | 29 |
| — | **brak** klawisza do zmiany ścieżki napisów i ich ukrycia (tylko menu uosc) | — |

### Audio

| Klawisz | Akcja | Linia |
|---|---|---|
| `-` / `=` | głośność −2 / +2 i mignięcie paska uosc | 23–24 |
| `WHEEL_DOWN/UP` | głośność −2 / +2 | 111–112 |
| `m` | wycisz | 123 |
| `c` / `v` | opóźnienie audio −/+100 ms | 25–26 |
| — | **brak** klawisza do zmiany ścieżki audio | — |

### Nawigacja i odtwarzanie

| Klawisz | Akcja | Linia |
|---|---|---|
| `SPACE` | pauza | 117 |
| `LEFT` / `RIGHT` | −5 s / +5 s (exact) | 120–121 |
| `DOWN` / `UP` | −30 s / +30 s (exact) | 118–119 |
| `,` / `.` | klatka wstecz / naprzód | 16–17 |
| `Shift+LEFT` / `Shift+RIGHT` | klatka wstecz / naprzód (duplikat) | 124–125 |
| `l` | pętla A-B | 18 |
| `MBTN_BACK` / `MBTN_FORWARD` | poprzedni / następny na liście | 105–106 |
| `PREV` / `NEXT` (klawisze multimedialne) | poprzedni / następny na liście | 102–103 |
| `PLAY`, `PAUSE`, `PLAYPAUSE`, `STOP` | sterowanie multimedialne | 96–99 |
| `REWIND` / `FORWARD` | **odwrócone:** REWIND = +30 s, FORWARD = −30 s (w upstreamie −30/+30) | 100–101 |
| — | **brak** klawiatury dla następnego/poprzedniego pliku i rozdziałów | — |

### Okno i wyjście

| Klawisz | Akcja | Linia |
|---|---|---|
| `f`, `Alt+ENTER`, `MBTN_LEFT_DBL` | przełącz pełny ekran | 122, 116, 108 |
| `ENTER` / `ESC` | pełny ekran włącz / wyłącz | 115 / 114 |
| `MBTN_LEFT` | ignorowane (klik nie pauzuje) | 107 |
| `MBTN_RIGHT` | menu uosc (zbudowane z `#!`) | 109 |
| `Ctrl+q`, `POWER` | wyjście | 90, 95 |

### Narzędzia, pliki, schowek

| Klawisz | Akcja | Źródło |
|---|---|---|
| `Ctrl+s` | zrzut ekranu `screenshot window` (z OSD i napisami w rozmiarze okna) | `input_uosc.conf:59`, `uosc/main.lua:1042-1060` |
| `I` | statystyki na stałe | `input_uosc.conf:79` |
| `i` | statystyki jednorazowo (domyślny skrót skryptu `stats`) | wbudowany stats.lua [W] |
| `` ` `` | konsola | `input_uosc.conf:80` |
| `Ctrl+C` | kopiuj ścieżkę/URL z czasem | `script-opts/SmartCopyPaste.conf` (`copy_keybind`) |
| `Ctrl+V` | wklej: link lub plik → odtwarza (gdy coś gra, dodaje do listy), sam czas → przewija | jw. (`paste_keybind`, `running_paste_behavior=playlist`) |
| `Ctrl+Alt+C` | kopiuj samą ścieżkę | jw. |
| `Ctrl+Alt+V` | wklej do listy odtwarzania | jw. |
| — | usuwanie pliku: istnieje `script-binding uosc/delete-file-next/prev/quit`, ale **bez klawisza** | `uosc/main.lua:981-985` |

Pozycje menu bez klawisza (zakomentowane linie z `#!`, widoczne pod PPM): otwórz plik, wczytaj napisy, lista odtwarzania, wersje, rozdziały, listy ścieżek wideo/audio/napisów, losowa kolejność, tryb dekodowania, deband, deinterlace, auto ICC, `correct-pts`, ramka okna, zawsze na wierzchu, urządzenie audio, jakość strumienia, folder pliku, folder ustawień, stop (5–14, 60–64, 82–89).

Konflikty [F]: brak zdublowanych klawiszy w `input_uosc.conf` (`grep -v` komentarzy, `awk '{print $1}' | sort | uniq -d` zwraca pusty wynik). Kolizje semantyczne:
- `~` jest opisane jako „Wyłącz Interpolację”, a usuwa też odbicia `Shift+f`/`Alt+f`;
- każde `vf set vapoursynth=…` (36–47) nadpisuje `hflip`/`vflip`;
- `REWIND`/`FORWARD` są odwrócone.

## 4. Pipeline wideo dziś

```text
plik / link (ytdl_hook → yt-dlp.exe 2026.07.04, all_formats)
→ dekodowanie hwdec=auto-copy (h264/hevc/vp8/vp9/av1/prores)
→ [opcjonalnie] vf vapoursynth: MVTools | SVP | RIFE ncnn-Vulkan (rife-v4) — ręcznie, Shift+cyfry
→ vo=gpu (domyślne tej wersji; DoVi: profil przełącza na gpu-next)
→ shadery GLSL z saved-props.json (dziś: Krig → FSR EASU → A4K Restore CNN L → A4K GAN x2 → NNEDI3 → FSRCNNX x2)
→ skalowanie spline36/bicubic, brak ditheringu i debandu (deband tylko z profilu bitrate ≤3000 kb/s)
→ synchronizacja: [vsync_auto] na 170 Hz → video-sync=audio, interpolation=no
```

- **[F] RIFE:** wyłącznie ×2 i wyłącznie model 9 (`rife-v4`). DLL ma parametr `fps_num/fps_den`, czyli docelowy fps, ale żaden skrypt go nie używa. Na dysku są katalogi `rife-v4`, `rife-v4_ensembleFalse_fastTrue`, `rife-v4.6_ensembleFalse` i `rife-v4.8_ensembleFalse`. W ciągach DLL nie ma nazw v4.6/v4.8, więc najpewniej da się ich użyć wyłącznie przez `model_path` [W].
- **[F] TensorRT/vs-mlrt:** brak. **AnimeJaNai:** brak. **NVOF w SVP:** wyłączony.
- **[F] Głębia i liczba barw:** nic nie jest skonfigurowane (`dither-depth` i `dither` zakomentowane w `mpv.conf:113-114`), nie ma też skrótów.
- **[W] Prędkość 2× a interpolacja:** wszystkie presety liczą cel od `container_fps` i nie uwzględniają `speed`. Przy 2× preset „170” musiałby wytwarzać ~340 klatek na sekundę rzeczywistą, a monitor wyświetli 170, więc reszta przepada. RIFE ×2 przy 2× daje ~96 kl./s w czasie rzeczywistym.

## 5. Aktualizacje

- **[F] Mechanizmów automatycznych nie ma.** Brak zadania aktualizującego yt-dlp (`-U` nigdzie nie występuje), mpv, VS i skrypty. Binding uosc `update` (`uosc/main.lua:1037-1039`) wymaga `elements/Updater.lua`, którego nie ma w `scripts/uosc/elements/`, więc po wywołaniu skończy się błędem [W].
- **[F] Jawnie przestarzałe:** mpv (3 lata, 5 wydań), FFmpeg/libplacebo (2023), VapourSynth R65 (aktualny R81), k7sfunc 0.1.23, uosc 5.0.0 (aktualny 5.13.0), wtyczka RIFE `com.holywu.rife` (aktualny fork r9_mod_v33), SmartCopyPaste 3.1 (2022), Pismo File Mount (2018), yt-dlp (o 4 miesiące za upstreamem).
- **[F] Ryzyka przy podmianie samego `mpv.exe` na ≥0.39:**
  - `sub-ass-vsfilter-blur-compat` jest usunięte; zamiennik to `sub-ass-use-video-data=aspect-ratio` (`DOCS/interface-changes.rst`, sekcja 0.39.0);
  - `console-scale` jest usunięte;
  - od 0.39 mpv wymaga VapourSynth ≥R56 (R65 spełnia);
  - od 0.37 zmieniły się domyślne `tscale` (oversample) i `dscale` (hermite), co nie dotyczy właściciela, bo ustawia je jawnie;
  - od 0.38 domyślne `sub-ass-override` to `scale`;
  - od 0.41 domyślne `vo` to `gpu-next`, a shader `nlmeans_dx` jest wariantem specjalnie pod `vo=gpu` z d3d11.

## 6. Problemy i zgrzyty

1. **[F→W] `[vsync_auto]` unieważnia ustawienia płynności.** Warunek `p.display_fps>122 or p.container_fps>32` (`profiles.conf:23`) jest prawdziwy na monitorze 170 Hz, więc `interpolation=no` i `video-sync=audio` obowiązują zawsze. W efekcie 23.976/47.95 fps na 170 Hz daje nierówną kadencję bez wygładzania [W]. Upstream zmienił ten warunek już w 2024V0 (notatki `20240102`: „dostosowano warunki `[vsync_auto]`”).
2. **[F] Wykrywanie cięć scen w `rife_480p_x2.vpy` i `rife_720p_x2.vpy` jest martwe.** Wynik `SCDetect` trafia do `sc_clip`, a następna linia go nadpisuje: `sc_clip = input.resize…` (`rife_480p_x2.vpy:28,32,34`; `rife_720p_x2.vpy:31,35,37`). Parametr `sc=True` nie dostaje więc właściwości `_SceneChange*`, co grozi artefaktami interpolacji na cięciach [W]. `rife_1080p_x2.vpy:31-37` robi to poprawnie.
3. **[F] `REWIND`/`FORWARD` są odwrócone** (`input_uosc.conf:100-101`).
4. **[F] Dwie kopie MVTools** (`mvtools.dll` i `libmvtools.dll`, ten sam `com.nodame.mvtools`, „MVTools v23”). Skutek przy autoloadzie VS nie jest zmierzony [?].
5. **[F] Martwe lub nieosiągalne modele RIFE** v4.6/v4.8/fast (sekcja 4). k7sfunc `RIFE_STD` przyjmuje `model ∈ {9, 21, 24}` (`k7sfunc.py:1056`), ale 21 i 24 wymagają nowszej wtyczki [W].
6. **[F] Ciężki łańcuch shaderów zapamiętany globalnie** (`saved-props.json`, `script-opts.conf:45`). Każdy nowy plik startuje z 6 shaderami, a `glsl-shaders-append` z `mpv.conf:131` nie ma znaczenia. Czy kolejne podwajacze faktycznie się uruchamiają (warunki `//!WHEN`) i ile to kosztuje, trzeba zmierzyć [?].
7. **[F] Preset interpolacji ignoruje prędkość** (sekcja 4). MVTools i RIFE 720p/1080p rzucają wyjątek dla źródeł powyżej 32 fps, więc nie zadziałają na materiałach 60 fps.
8. **[F] Font napisów:** `sub-font="ITC Officina Sans Std PL Book"`, a w `fonts/` rodzina „ITC Officina Sans Std PL Book” ma tylko style Bold i Bold Italic (tablica nazw w TTF). W systemie Officiny nie ma (rejestr i `C:\Windows\Fonts`), więc napisy renderują się pogrubione [W].
9. **[F] Opcje do usunięcia przy aktualizacji** (sekcja 5).
10. **[F/W] `input-ipc-server=mpvpipe` ma stałą nazwę.** Druga instancja nie utworzy pipe'a [W]. AniShift go nie używa.
11. **[F] Brakujące skróty:** ścieżki napisów i audio, widoczność napisów, rozdziały, następny/poprzedni plik z klawiatury, usuwanie, deband, hwdec, zrzut bez OSD i napisów (`Ctrl+s` zapisuje okno razem z OSD).
12. **[F] Usuwanie trwałe:** gdy podepnie się `delete-file-*`, uosc przy `use_trash=false` (`uosc/main.lua`, defaults) wykona `cmd /C del` (`uosc/lib/utils.lua:517-531`).
13. **[F] Martwy balast:**
    - 4 zakomentowane skrypty `*TEST*`/`tts-subs-test`, `status_line.conf`, `detect-image` bez komend, `ruler` bez skrótu;
    - 9 niepodpiętych `.vpy` i 21 niepodpiętych shaderów;
    - LXGW WenKai (15.9 MB, chiński font, nieużywany po zmianie `sub-font`);
    - `_cache/ambient-blur.json` bez skryptu i katalog `cache/` nieznanego pochodzenia;
    - resztki VS portable (sekcja 2.2) i duplikat `mpv-install.bat` w roocie.
14. **[F] `installer/*-mode.bat` są zapisane w GB18030 i wywołują `chcp 936`,** więc w polskiej konsoli ich opisy to krzaki. `mpv-test.conf` zawiera tylko komentarz.
15. **[W] `ytdl_hook-all_formats=yes` i `force_all_formats=yes`** ładują wszystkie formaty jako ścieżki. To spowalnia start linków, ale umożliwia wybór jakości (jest też menu uosc „jakość strumienia”).
16. Kosmetyka [F]: komentarze w nagłówkach `rife_1080p_x2.vpy:4` i `rife_720p_x2.vpy:4` podają złe `show-text` („Preset MVTools_2x”). `mpv.conf:1-3` odsyła do dokumentacji mpv-lazy. `Shift+LEFT/RIGHT` dublują `,`/`.`.

## 7. Tryby, profile, instalator

**Profile (`profiles.conf`, opisy przetłumaczone z chińskiego):**

| Profil | Oryginalny `profile-desc` | Tłumaczenie | Działanie |
|---|---|---|---|
| `[speed_limit]` | 速度变化下限的控制 | kontrola dolnej granicy prędkości | `speed<0.1` → 0.1 |
| `[ontop_playback]` | 基于播放状态的自动置顶 | automatyczne „zawsze na wierzchu” wg stanu odtwarzania | warunek zakomentowany, więc nie włącza się sam |
| `[vsync_auto]` | 基于刷新率或帧率的同步模式 | tryb synchronizacji wg odświeżania lub fps | display_fps>122 lub fps>32 → `interpolation=no`, `video-sync=audio` |
| `[deband_bitrate]` | 基于码率的自动去色带 | automatyczny debanding wg bitrate | ≤3000 kb/s → `deband=yes` |
| `[save_props_auto]` | 基于进度或时长或视频轨类型的自动保存属性 | automatyczny zapis właściwości wg postępu, długości lub typu ścieżki wideo | koniec pliku, ostatnie 5 min, plik ≤5 min, audio lub obraz → bez zapisu pozycji |
| `[HDR_generic]` | hdr通用 | HDR ogólny | `blend-subtitles=no` |
| `[HDR_DolbyVision]` | hdr杜比视界 | HDR Dolby Vision | nazwa zawiera `.DoVi` → `vo=gpu-next`, `tone-mapping=st2094-40` |

Nagłówki: 文档 = dokumentacja, 配置预设组 = grupy profili.

**Tryby `installer/*.bat`** (tłumaczenie z GB18030). Każdy robi `cd` do katalogu nadrzędnego i uruchamia `mpv.com --config=no …`:
- `mpv-benchmark-mode.bat`: „tryb benchmarku, a właściwie podgląd wydajności dekodowania i renderowania, raczej zabawka”. Uruchamia z `installer/mpv-BenchMark.conf`: log na pulpit, OSD z fps, wyłączony vsync, `display-desync`, profile `API_1` (gpu/d3d11/d3d11va) lub `API_2` (gpu-next/winvk/bez hwdec) oraz `Rendering_1` (sinc) lub `Rendering_2` (lanczos). Plik conf jest już po polsku.
- `mpv-input-mode.bat`: „tryb wejścia: test klawiszy i myszy, pokazuje nazwy klawiszy i komendy czystego mpv; nie ładuj wideo; skróty zablokowane”. Uruchamia `--input-test=yes`.
- `mpv-pure-mode.bat`: „tryb czysty do testów zgodności; mpv z prawie domyślnymi opcjami; zamknięcie CMD zamyka mpv”.
- `mpv-test-mode.bat`: „tryb testowy: własne parametry z `mpv-test.conf`”, który jest pusty.

**Instalator `installer/mpv-install.bat`** (rossy/mpv-install, 304 l., wymaga administratora). Wyłącznie odczytany:
- `HKLM\…\App Paths\mpv.exe` (z `UseUrl=1`);
- `HKLM\SOFTWARE\Classes\Applications\mpv.exe` z czasownikami `play`/`open`;
- mpv dopisane do „Otwórz za pomocą” dla typów percepcyjnych video i audio;
- handlery AutoPlay dla DVD i Blu-ray (`io.mpv.dvd`, `io.mpv.bluray`);
- `HKLM\SOFTWARE\Clients\Media\mpv\Capabilities` i `RegisteredApplications`;
- 84 wywołania `add_type`, czyli ProgId `io.mpv.<ext>` z ikoną `mpv-document.ico` i `OpenWithProgIds` dla rozszerzeń audio i wideo;
- na końcu otwiera Programy domyślne.

`mpv-uninstall.bat` (tylko w roocie) usuwa te klucze.

Stan rejestru odczytany 2026-10-31 [F]: App Paths = `C:\Users\MattyMroz\Videos\mpv\mpv.exe`, `RegisteredApplications\mpv` istnieje, `io.mpv.mkv\shell\open\command` = `"C:\Users\MattyMroz\Videos\mpv\mpv.exe"  -- "%L`, 86 kluczy `io.mpv.*`, UserChoice `.mkv`=`io.mpv.mkv`, `.mp4`=`io.mpv.mpeg4`. Upstream PlayKit ma dziś także `mpv-register.bat`, `mpv-unregister.bat` i `umpv-*` (listing `installer/` na `main`).

## 8. Co jest po chińsku (do tłumaczenia lub wyrzucenia)

Liczba linii z CJK (skrypt Pythona po plikach tekstowych, bez `vapoursynth64/` i cache):

| Plik | Linie | Rodzaj |
|---|---|---|
| `k7sfunc.py` | 359 | komentarze i komunikaty `vs.Error` (np. 模块 … 的子参数 … 的值无效 = „nieprawidłowa wartość parametru … modułu …”) |
| `scripts/uosc/lib/lang.lua` | 93 | tylko zakomentowany oryginał; aktywne teksty są po polsku |
| `vs/MEMC_*_NEW/_old.vpy` | 5–12 każdy | komentarze opcji |
| `qtgmc.py` | 9 | komentarze |
| `profiles.conf` | 9 | `profile-desc` i nagłówki (tłumaczenie w sekcji 7) |
| `LICENSE.MD` | 5 | opis licencji paczki |
| `scripts/uosc/main.lua:1128` | 1 | **OSD:** `LOGO的可见性：` = „Widoczność logo:” |
| `scripts/thumbfast.lua:411` | 1 | **OSD:** `thumbfast 子进程创建失败！` = „Nie udało się uruchomić podprocesu thumbfast!” |
| `scripts/thumbfast.lua:182`, `uosc/elements/Logo.lua:1`, `uosc/elements/Controls.lua:53` | po 1 | komentarze (默认为WIN = „domyślnie Windows”; 存在问题…无法实时自适应缩放 = „znany problem: brak skalowania na żywo”; 自定义的捷径 = „własne skróty”) |
| `installer/*-mode.bat`, `mpv-BenchMark.conf` | całe opisy | GB18030 (sekcja 7) |

## 9. Co warto zachować, a co wyrzucić (wnioski)

**Zachować jako kontrakt przyzwyczajeń [W]:**
- prędkość `[` `]` `\` `BS` (2× pod jednym klawiszem) i profil `speed_limit`;
- interpolacja w górnym rzędzie z Shiftem, z `~` jako „wyłącz” (z poprawką, żeby nie zdejmować odbić);
- `Ctrl+cyfry` jako przełączniki jakości, korektor `1..0` z `Ctrl+9/0/BS`;
- obrót `r`/`Shift+R`, odbicia, pan i zoom myszą i strzałkami;
- `Ctrl+V` jako „wklej link → gra”;
- strzałki ±5/±30 s, `,`/`.` dla klatek, `l` dla A-B, `z/x` i `c/v` dla opóźnień, `-`/`=` i kółko dla głośności;
- PPM jako menu oraz menu budowane z `#!`, co daje jedno źródło prawdy dla skrótów i menu;
- wznowienia (`watch-later-options`, `save_props_auto`), szablon zrzutów, polskie priorytety `alang/slang`, `sub-auto=fuzzy`, `audio-file-auto=fuzzy`;
- polskie teksty z `uosc/lib/lang.lua` jako materiał do tłumaczenia nowego UI;
- rejestracja skojarzeń plików (mechanizm rossy/PlayKit).

**Wyrzucić lub nie przenosić [W]:**
- skrypty `*TEST*`/`tts-subs-test`, `status_line.conf`, `detect-image` (puste), duplikaty `MEMC_*_NEW/_old`, `rife_2x`, `rife_std`, `mvtools_30`;
- 21 nieużywanych shaderów i `test.glsl`;
- `libmvtools.dll` albo `mvtools.dll` (jedna kopia), martwe modele RIFE;
- resztki VS portable (`AVFS.exe`, `pfm-*.exe`, `VSVFW.dll`, py38, `vsrepo/vsgenstubs/setup.py/MANIFEST.in`);
- LXGW WenKai, `ambient-blur.json`, `cache/`, drugi `mpv-install.bat`;
- `[vsync_auto]` w obecnej postaci, odwrócone `REWIND/FORWARD`, `sub-ass-vsfilter-blur-compat`, `console-scale`;
- `[HDR_generic]`/`[HDR_DolbyVision]` do ponownej oceny po przejściu na `gpu-next`.

## 10. Niewiadome

1. Co faktycznie wybiera mpv na RTX 5090 i sterowniku 610.88 (`vo`, `gpu-context`, dekoder hwdec) i jaki jest raportowany `display-fps`. Rozstrzygnie log z jednego odtworzenia (`--log-file`), którego nie uruchamiano z powodu zakazu otwierania okna.
2. Czy stara wtyczka RIFE (ncnn-Vulkan, 2022) i VS R65 działają poprawnie i wydajnie na Blackwell. Właściciel mówi „działa”, ale nie ma pomiaru per preset.
3. Czy duplikat MVTools powoduje błąd lub ostrzeżenie przy autoloadzie VS.
4. Koszt i realne działanie 6-shaderowego łańcucha z `saved-props.json` (warunki `//!WHEN` kolejnych podwajaczy).
5. Pochodzenie katalogu `portable_config/cache/` (48 plików z 2026-08-06).
6. Których presetów właściciel faktycznie używa: zapis zostawia tylko shadery, a nie `vf`.
7. Układ klawiatury (polski programisty = US?). Od niego zależy, czy `~ ! @ # …` to Shift+górny rząd.

## Wykonane odczyty i odchylenia

- Konsolowo: `mpv.com --no-config --version`, `mpv.com --no-config --list-options`, `VSPipe.exe --version`. **Odchylenie:** uruchomiono też `yt-dlp.exe --version`, którego nie było na liście dozwolonych komend. Komenda tylko wypisała wersję i niczego nie zmieniła; tę samą wersję potwierdza FileVersion z PowerShell.
- `gh api` dla `hooke007/mpv_PlayKit` (releases, notatki `20231101` i `20240102`, pliki z commita `054faa95` do `diff`), `hooke007/MPV_lazy` (archived), `mpv-player/mpv` (tagi, `DOCS/interface-changes.rst@v0.41.0`, `input/input.c@v0.37.0`), `tomasklaen/uosc`, `po5/thumbfast`, `yt-dlp/yt-dlp`, `vapoursynth/vapoursynth`, `styler00dollar/VapourSynth-RIFE-ncnn-Vulkan`.
- Rejestr Windows i fonty systemowe: tylko odczyt (`Get-ItemProperty`).
- W `C:\Users\MattyMroz\Videos\mpv` niczego nie zmieniono. Pliki pomocnicze (pobrane configi upstream, lista opcji) leżą w scratchpadzie sesji.
