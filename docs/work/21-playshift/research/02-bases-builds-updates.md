---
kind: research
id: playshift-r2-bases
status: proposed
date: 2026-10-31
---

# R2: Na czym zbudować PlayShift — podstawy, buildy mpv, aktualizacje, przenośność

Stan sprawdzony 2026-10-31 przez GitHub API (`gh api`), README/wiki projektów i kod źródłowy mpv. Daty przy projektach to daty z API (push, release), nie z pamięci modelu. Oznaczenia: **[F]** fakt ze źródła, **[W]** wniosek, **[?]** niewiadoma do sprawdzenia testem.

## 1. Rekomendacja

**Własna, cienka dystrybucja z niezmienionych binarek upstream + własna warstwa konfiguracji + własny aktualizator oparty na manifeście z SHA256.** Nie forkować mpv_PlayKit/mpv-lazy jako całości i nie kompilować mpv samemu.

Skład:

| Warstwa | Wybór | Dlaczego |
|---|---|---|
| mpv | `shinchiro/mpv-winbuild-cmake`, wariant `mpv-x86_64-v3` (domyślnie); zhongfly jako zapas | Na nim stoi PlayKit; buildy codzienne, 30 ostatnich wydań na GitHubie do cofnięcia; każdy asset ma w API pole `digest` (sha256). CPU właściciela (Core Ultra 7 265KF) obsługuje x86-64-v3 [W]. |
| UI | upstream **uosc 5.13.0** + miniatury (thumbfast albo `thumb_engine` z PlayKit) | Ma `pl.json`, komendę `update`, `delete-file-next` z koszem, `paste`, `stream-quality`. Obecny build ma uosc 5.0.0. |
| AI (upscale/RIFE) | **decyzja po R3**, dwie realne ścieżki: (A) VapourSynth R81 + vs-mlrt TensorRT — zachowuje obecne `.vpy`; (B) silnik AnimeJaNai (fork mpv z `vf_animejanai` + TensorRT, RIFE w tym samym filtrze, bez VapourSynth i Pythona) | Manifest traktuje źródło `mpv.exe` jako jedną pozycję, więc zamiana A↔B nie zmienia reszty dystrybucji. |
| Linki | wbudowany `ytdl_hook` + **yt-dlp nightly** + **deno** obok `yt-dlp.exe` | Od 2025-11 YouTube wymaga zewnętrznego środowiska JS; stable yt-dlp jest „często przestarzały”. |
| Aktualizacje | manifest wersji + pobranie najnowszego wydania z GitHub API + weryfikacja `digest` + instalacja obok starej wersji + przełączenie + zachowanie poprzedniej do rollbacku | Wzorce już istnieją: `anishift/setup` (SHA256, atomowe `Path.replace`) i AnimeJaNaiUpdater (`overlay_paths` / `user_preserve`). |
| Instalacja | przenośny katalog + `mpv --register` (HKCU, bez admina) + jednorazowy wybór domyślnej aplikacji w Ustawieniach Windows | Natywne w mpv od 0.41; tego samego używa PlayKit. |

### Ryzyka rekomendacji

- **Buildy shinchiro/zhongfly to git master, nie stable.** Regresja jest możliwa w dowolnym dniu. Ochrona: przypięta wersja w manifeście, aktualizacja świadoma (np. raz w tygodniu albo na żądanie), poprzednia wersja na dysku.
- **Nowy układ VapourSynth (R74+).** VSScript jest teraz w kole Pythona (`site-packages/vapoursynth/vsscript.dll`), a mpv ładuje go w runtime dopiero od commita z 2026-04-10. Połączenia „mpv z shinchiro + portable Python 3.14 + VS R81” nikt tu jeszcze nie uruchomił [?].
- **Ścieżka B to zależność od jednego autora.** Fork `the-database/mpv` jest 278 commitów przed i 65 za upstreamem; repo dystrybucji ma licencję CC BY-NC-SA 4.0, `animejanai-inference` nie ma pliku licencji.
- **Licencje PlayKit.** Pliki autora bez licencji w treści mają status `UNLICENSED`. Do prywatnego użytku bez znaczenia; przy publicznym repo PlayShift nie wolno ich kopiować.
- **Cookies Chrome na Windows nie działają w yt-dlp** (otwarte zgłoszenia od 2024). Treści z logowaniem wymagają Firefoksa albo pliku `cookies.txt`.

## 2. Stan obecny (`C:\Users\MattyMroz\Videos\mpv`) — punkt odniesienia

Odczytane z plików (bez uruchamiania):

- `mpv.exe`: `mpv v0.36.0-711-g250429da`, FFmpeg `N-112646-g28840cf49` — build z przełomu 2023/2024, około dwóch lat za upstreamem.
- uosc `5.0.0` (`portable_config/scripts/uosc/main.lua`); obecny upstream to 5.13.0.
- VapourSynth: `VapourSynth.dll` ze stringiem R65, embedded Python 3.11 (`python311._pth`) plus `VSScriptPython38.dll`; wtyczki w `vapoursynth64/plugins`: `RIFE.dll`, `mvtools`, `svpflow1/2_vs64.dll`, `MiscFilters`, `VMAF`.
- `yt-dlp.exe` z 2026-07-16 (prawdopodobnie stable z lipca).
- `mpv.conf`: `input-builtin-bindings = no`, `input-ipc-server = mpvpipe`, `hwdec = auto-copy`, `video-sync = display-resample`, brak jawnego `vo` (w 0.36 domyślnie `gpu`).
- Rozmiar: 251 MB, w tym `vapoursynth64` 73 MB i `portable_config` 65 MB.

## 3. Tabela porównawcza podstaw

Aktywność sprawdzona 2026-10-31.

| Projekt | Co to | Aktywność | Licencja | Plusy dla PlayShift | Minusy |
|---|---|---|---|---|---|
| [hooke007/mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit) | konfiguracja + paczka „mpv-lazy” (mpv, Python, VS, yt-dlp, skrypty, shadery) | push 2026-10-28; release `20260510` (2026-05-10), poprzednie 2026-02-10, 2025-12-13, 2025-10-26 | mieszana; własne pliki `UNLICENSED` | dojrzały zestaw shaderów, `.vpy` (RIFE NV/DML, ArtCNN, UAI TRT), `uosc_addones`, `thumb_engine`, `k7sfunc` | po chińsku, **brak samoaktualizacji** („不支持自更新”), paczka vsNV 2,9 GB, wycięte enkodery |
| [hooke007/MPV_lazy](https://github.com/hooke007/MPV_lazy) | stara nazwa | **zarchiwizowane**, push 2025-09-06 | — | — | martwe |
| [the-database/mpv-AnimeJaNai](https://github.com/the-database/mpv-AnimeJaNai) | gotowy odtwarzacz z upscalingiem TensorRT i RIFE | release **3.9.0 (2026-10-27)**, 3.8.1, 3.8.0 w tym samym tygodniu | CC BY-NC-SA 4.0 (repo); Manager GPL-3.0 | brak VS/Pythona, filtr bierze klatki GPU bezpośrednio; paczki TRT per architektura (`trt-sm120` = Blackwell); **wbudowany aktualizator z zachowaniem ustawień** | fork mpv jednego autora; frontend mpv.net (jest też samodzielny `mpv.exe`); licencja NC |
| [shinchiro/mpv-winbuild-cmake](https://github.com/shinchiro/mpv-winbuild-cmake) | buildy mpv/ffmpeg dla Windows (MinGW) | release **20261021** (2026-10-21), codziennie; 30 wydań wstecz | brak pliku licencji w repo (mpv: GPL/LGPL) | standard de facto, x86_64-v3, VS i Vulkan włączone; ffmpeg w tym samym wydaniu | `updater.ps1` bez weryfikacji sum |
| [zhongfly/mpv-winbuild](https://github.com/zhongfly/mpv-winbuild) | GitHub Actions na bazie shinchiro | release 2026-10-30, sprawdza mpv co godzinę; 30 dni wstecz | MIT (workflow) | `sha256.txt`, warianty `lgpl` i `debug` | trzecia strona nad shinchiro |
| [mpv-player/mpv](https://github.com/mpv-player/mpv) — oficjalne | stable v0.41.0 (2025-12-21) z zipami Windows; kroczący `git-release` z buildami Windows | `git-release` zbudowany 2026-10-30; „full” MinGW od 2026-09-25 | GPL/LGPL | źródło najbardziej zaufane; `full` ma VS i Vulkan | `git-release` nadpisuje jeden tag (brak historii do rollbacku); `full` istnieje od miesiąca; brak x86-64-v3 |
| [Andarwinux/mpv-winbuild](https://github.com/Andarwinux/mpv-winbuild) | buildy LLVM | 2026-10-29 | MIT | warianty `adl`/`v3`, dołącza mpv-menu-plugin | 23★, mała baza użytkowników |
| [mpvnet-player/mpv.net](https://github.com/mpvnet-player/mpv.net) | GUI .NET na libmpv | v7.1.2.0 (2026-01-09), ostatni commit 2026-02-09 | GPL-2.0 | ma `lang/po/pl.po`, menu kontekstowe; używa go AnimeJaNai | tempo spada; druga warstwa (.NET) nad mpv |
| [422658476/MPV-EASY-Player](https://github.com/422658476/MPV-EASY-Player) | GUI Qt na mpv | 0.41.0.6 (2026-09-06) | GPL-3.0 | aktywne | chiński pierwszy; bez polskiego; własny układ konfiguracji |
| [mpc-qt/mpc-qt](https://github.com/mpc-qt/mpc-qt) | klon MPC-HC na libmpv | v26.07 (2026-07-09) | GPL-2.0 | klasyczny GUI | inna filozofia niż konfiguracja mpv |
| [smplayer-dev/smplayer](https://github.com/smplayer-dev/smplayer) | GUI Qt na mpv/mplayer | v10461 (2026-10-06) | GPL-2.0 | aktywne | własna warstwa ustawień, trudne do skryptowania |
| [iina/iina](https://github.com/iina/iina) | odtwarzacz macOS na mpv | v1.5.0 (2026-10-03) | GPL-3.0 | wzór UX | tylko macOS |
| [celluloid-player/celluloid](https://github.com/celluloid-player/celluloid) | GTK na mpv | v0.30 (2026-03-29) | GPL-3.0 | wzór prostego UX | Linux |
| [dyphire/mpv-config](https://github.com/dyphire/mpv-config) | konfiguracja Windows | push 2026-10-26, 1921★ | NOASSERTION | źródło skryptów | tylko konfiguracja |

Warstwa UI (skrypty, nie podstawy):

| Projekt | Aktywność | Licencja | Uwagi |
|---|---|---|---|
| [tomasklaen/uosc](https://github.com/tomasklaen/uosc) | 5.13.0 (2026-08-03), push 2026-10-16 | LGPL-2.1 | `src/uosc/intl/pl.json`; komendy `update`, `paste*`, `delete-file-next/quit` (opcja `use_trash`, na Windows kosz przez `Microsoft.VisualBasic.FileIO`), `stream-quality`, `download-subtitles` |
| [Samillion/ModernZ](https://github.com/Samillion/ModernZ) | v0.3.3 (2026-05-20) | LGPL-2.1 | OSC w stylu wbudowanego |
| wbudowane mpv: `osc.lua`, `select.lua` (0.39), menu poleceń (0.40), `context_menu.lua` (0.41), OSC Preview API | osc.lua zmieniany 2026-10-05 | GPL/LGPL | API miniatur w `DOCS/man/osc.rst` |
| [po5/thumbfast](https://github.com/po5/thumbfast) | push 2026-08-12 | MPL-2.0 | miniatury; PlayKit zastąpił go własnym `thumb_engine` |

## 4. mpv_PlayKit szczegółowo

**Co zawiera** [F, drzewo repo i release `20260510`]:

- `installer/`: `mpv-register.bat` (wywołuje `mpv.com --config=no --register`), `mpv-unregister.bat`, `umpv-install.bat` (oparty na rossy/mpv-install, zapisuje do HKLM, wymaga admina), tryby `测试/纯净/跑分/输入` (test, czysty, benchmark, wejście).
- `portable_config/`: `mpv.conf` (33 KB), `input.conf`, `input_easy.conf`, `input_list.conf`, `input_scripts.conf`, `input_uosc.conf`, `menu.conf`, `profiles.conf`, `script-opts.conf`, `fonts/`, `luts/`.
- `scripts/`: `uosc` (zmodyfikowany 5.12.1 z upstreamowego commita `4104053`), `uosc_addones` (menu shaderów, skok do linii napisów, inspektor właściwości, siatka miniatur VCS), `thumb_engine` (fork thumbfast zgodny z OSC Preview API), `input_plus`, `stats`, `stats_mediainfo`, `save_global_props`, `auto_load_fonts`, `cover_art_fallback`.
- `shaders/`: 35 rodzin (m.in. ACNet, Anime4K, ArtCNN, CuNNy, ESRGAN, FSRCNNX, NV, AMD, nlmeans, deband).
- `vs/`: `MEMC_RIFE_NV/DML/STD`, `MEMC_DRBA_NV/DML`, `MEMC_SVP_PRO`, `MEMC_MVT_LQ`, `MIX_UAI_NV_TRT/DML/MIGX`, `SR_ARTCNN_NV`, `NR_BM3D_NV`, `ETC_DEINT_EX`.
- `k7sfunc` jest teraz pakietem PyPI (1.8.1, 2026-05-07, `requires_python >=3.10`). Gotowe środowisko autor trzyma w `hooke007/dotfiles` → release `mpv_addones`: `py.3_14_3+vs.R73-portable.7z`. PlayKit stoi więc na VS **R73**, sprzed zmiany układu w R74.
- Release `20260510`: mpv `git-20260509-7b057f6`, rumpv 1.0.3, yt-dlp **nightly** 2026.05.05, Python 3.14.4. Paczki: standardowy `.exe` 132 MB, `noVS` 49 MB, łatka `vsNV` 1,61 + 1,30 GB.
- Instrukcja (discussion #194, 2026-05-10): tylko Win10+ x64 i CPU x86-64-v3; buildy shinchiro z usuniętymi enkoderami; autor nie dba już o `vo=gpu` ani libmpv, tylko `gpu-next`.

**Zmiany względem mpv-lazy** [F]: od `20260510` usunięto `contextmenu_plus`, `playlist_osd` i `thumbfast`, menu GUI zastąpiło wbudowane menu mpv, doszły `thumb_engine` i `uosc_addones`. Autor pisze, że paczka „nadal nazywa się mpv-lazy, ale jest zbudowana od nowa”: mniej komponentów, użytkownik sam dokłada resztę.

**Aktywność** [F]: commity w ostatnich 12 miesiącach: 2025-11: 13, 12: 28, 2026-01: 7, 02: 16, 03: 20, 04: 13, 05: 7, potem przerwa do jednego commita 2026-10-28 (nowy shader `knl_pro`). Wydania co 2–3 miesiące.

**Co wziąć:**
- pomysły i `.vpy` dla MEMC/SR jako wzór łańcuchów; prawa autora do własnego kodu w `.vpy` trzeba sprawdzić, zanim cokolwiek trafi do publicznego repo;
- shadery: licencje są w plikach, brać pojedynczo;
- `thumb_engine` — fork thumbfast na MPL-2.0 [W], więc zmodyfikowany plik zostaje na MPL;
- model rejestracji przez `mpv --register` zamiast własnego `.bat` z HKLM;
- profile warunkowe (`vsync_auto`, `deband_bitrate`) — właściciel już je ma.

**Czego nie brać:** całej paczki (chińskie UI i komentarze, brak aktualizatora, 2,9 GB vsNV, R73), `umpv-install.bat` (HKLM, admin), własnych skryptów autora bez licencji (`input_plus`, `uosc_addones`) do publicznego repo — co najwyżej jako wzór funkcji.

## 5. Buildy mpv dla Windows

**Źródła** [F]:

| Źródło | Warianty | Weryfikacja | Retencja |
|---|---|---|---|
| shinchiro (GitHub releases, też SourceForge `mpv-player-windows`) | `mpv-x86_64`, `mpv-x86_64-v3`, `mpv-i686`, `mpv-aarch64`, `mpv-dev-*` (libmpv), `ffmpeg-*` | pole `digest` w API | 30 wydań |
| zhongfly | jak wyżej + `mpv-debug-*`, `*-lgpl-*` | `sha256.txt` + `digest` | 30 dni |
| oficjalne `git-release` | `x86_64-w64-mingw32-full` (statyczny, „każda opcjonalna funkcja”), `x86_64-pc-windows-msvc` (Clang, mniej funkcji), `libmpv` gpl/lgpl | `digest` | jeden kroczący tag |
| oficjalne stable | `mpv-v0.41.0-x86_64-w64-mingw32.zip`, `…-pc-windows-msvc.zip` | `digest` | per tag |

**gpu-next, libplacebo, d3d11, Vulkan nie są wariantami buildu.** Wszystkie wymienione buildy mają libplacebo, Vulkan i shaderc: shinchiro `mpv.cmake` ustawia `-Dvulkan=enabled -Dspirv-cross=enabled -Dvapoursynth=enabled`, oficjalny `full` ma `-D{shaderc,…,vapoursynth,vulkan}=enabled`. Wybór odbywa się w runtime: `vo=gpu-next` (domyślne od 0.41), `gpu-api=d3d11|vulkan`, `hwdec=…`.

**VapourSynth a build** [F]: od commita `75b2ccf` (2026-04-10, „update for VapourSynth R74”) `vf_vapoursynth` ładuje `VSScript.dll` przez `dlopen`, a gdy ustawiona jest zmienna `VSSCRIPT_PATH`, bierze ścieżkę z niej (`video/filter/vf_vapoursynth.c`). Build nie jest już związany z konkretną instalacją VS. [W] Każdy aktualny build z VS włączonym zadziała z dowolnym R74+, a bez VS mpv odpali się normalnie; błąd pojawi się dopiero przy włączeniu filtra.

**Wariant x86_64-v3**: wymaga AVX2. PlayKit wymaga go wprost. Core Ultra 7 265KF go obsługuje [W, rodzina Arrow Lake ma AVX2].

**Automatyczna aktualizacja mpv:**
- oficjalny `updater.bat` → `installer/updater.ps1` z `shinchiro/mpv-packaging` (push 2024-06-28): kanały `daily` (GitHub API `releases/latest`) i `weekly` (RSS SourceForge), opcjonalnie yt-dlp i ffmpeg, ustawienia w `settings.xml`; **nie sprawdza sum kontrolnych** (brak `hash`/`sha` w skrypcie);
- PlayKit: brak;
- zalecane: własny krok w aktualizatorze — `GET /repos/shinchiro/mpv-winbuild-cmake/releases/latest` → asset `mpv-x86_64-v3-*.7z` → porównanie sha256 z polem `digest` → rozpakowanie do katalogu wersji → przełączenie.

**Własna kompilacja** (fork `mpv-winbuild-cmake`): opłaca się tylko przy własnym filtrze w C, jak `vf_animejanai`. Przy obecnych celach nie ma powodu [W].

## 6. Automatyczna aktualizacja zależności

### yt-dlp [F]

- Kanały: `stable` (mniej więcej co miesiąc), `nightly` (codziennie przy zmianach), `master` (po każdym pushu). README: stable jest „often stale and prone to external breakage”, nightly to „recommended channel for regular users”.
- Ostatnie stable: 2026.10.26, 2026.10.21, 2026.08.19, 2026.07.04, 2026.06.09, 2026.03.17. Nightly: 2026.10.29.232701.
- Przełączenie: `yt-dlp --update-to nightly`, potem `yt-dlp -U` zostaje na nightly. Aktualizator yt-dlp pobiera `SHA2-256SUMS`, porównuje sha256 nowej binarki, a przy niepowodzeniu przywraca `.old` (`yt_dlp/update.py`: `SHA2-256SUMS` l. 459, porównanie l. 531, rename l. 543–551). Sumy są podpisane GPG.
- **YouTube wymaga JS** od 2025-11-12 (ogłoszenie [#15012](https://github.com/yt-dlp/yt-dlp/issues/15012)): `yt-dlp-ejs` jest wbudowany w `yt-dlp.exe`, ale potrzebny jest runtime JS; domyślnie **deno**. Na Windows `deno.exe` ma leżeć obok `yt-dlp.exe` albo w PATH (wiki EJS). Deno v2.9.8 (2026-10-21): zip 43 MB, assety `.sha256sum`.
- Dlaczego stare wersje padają [W, na podstawie README i zgłoszeń]: YouTube zmienia odtwarzacz i mechanizmy podpisów, a poprawki trafiają najpierw do nightly. Stable bywa w tyle o tygodnie (luki 03.17 → 06.09, 08.19 → 10.21).
- **Zalecenie**: nightly + `yt-dlp -U` przy starcie odtwarzacza w tle (sam weryfikuje SHA256), deno aktualizowany z manifestu.

### ffmpeg

mpv zawiera biblioteki FFmpeg, więc do odtwarzania osobny `ffmpeg.exe` nie jest potrzebny. ytdl_hook pyta yt-dlp o JSON, a strumienie otwiera samo mpv [W, z budowy `ytdl_hook.lua`]. Osobny ffmpeg przydaje się tylko do pobierania z yt-dlp (łączenie ścieżek) i AniShiftowi, który ma już przypięty `ffmpeg-9.0.2-full_build` w `external/bin_hashes.json`. Nie dublować.

### Skrypty Lua

uosc ma komendę `update` (README: „Updates uosc to the latest stable release right from the UI”, Windows ✔). Instalator `installers/windows.ps1` instaluje do `portable_config`, jeśli taki katalog istnieje. [W] W dystrybucji z własnymi zmianami albo przypiętą wersją lepiej aktualizować uosc z manifestu niż jego wbudowaną komendą, bo ta nadpisze zmiany.

### Modele i środowiska AI

- vs-mlrt: stable **v15.16** (2026-03-26: TensorRT 10.16, CUDA 13.2); seria testowa v16 do **v16.4.test1** (2026-10-30: TensorRT 11.4, TRT-RTX 1.7). Paczka `vsmlrt-windows-x64-tensorrt` ma ok. 2,7 GB (2,15 + 0,53 GB) w 7z.
- AnimeJaNai 3.9.0: `manifest.json` przypina składniki (`mpvnet v7.1.2.0`, `mpvfork 2026-10-24-b4f9f5bfed`, `inference_runtime trt-11.4.0.106`, `rife models-rife-fp16-1`). Paczki: `trt-runtime` 187 MB (444 MB po rozpakowaniu), `trt-sm120` 229 MB, `rife` 462 MB. Silniki TensorRT budują się przy pierwszym odtworzeniu per model i rozdzielczość; zmiana ustawień TRT je unieważnia (CRC ustawień w nazwie pliku).

### Wzorce bezpiecznej aktualizacji — co już istnieje

| Wzorzec | Hash | Rollback | Ochrona ustawień |
|---|---|---|---|
| `anishift/setup/installer.py` | SHA256 z przypiętego manifestu | atomowe `Path.replace` per plik, nie transakcja na cały zasób | n/d |
| yt-dlp `-U` | SHA256 z podpisanych sum | `.old` | n/d |
| AnimeJaNaiUpdater (`AnimeJaNaiUpdater/Program.cs`) | **brak**, tylko rozmiar (`installed_bytes`) | katalog `staging`, kopia `input.conf.bak-<wersja>` | `overlay_paths` vs `user_preserve`; ustawienia użytkownika w `mpv-user.conf` / `input-user.conf`, ładowanych na końcu |
| shinchiro `updater.ps1` | brak | brak | n/d |

**Zalecany wzorzec dla PlayShift** [W]:
1. Manifest z przypiętą wersją i sha256 każdego składnika (mpv, yt-dlp, deno, uosc, VS/Python albo pakiety AJN, modele).
2. „Sprawdź aktualizacje”: dla źródła GitHub release pobiera `latest`, bierze `digest` z API i zapisuje nową pozycję manifestu. Pasuje do decyzji w `anishift/setup/AGENTS.md`: „`source` to tagged union; nowe źródło = nowy literal + fetcher”.
3. Instalacja do katalogu wersji obok starej, przełączenie po weryfikacji, poprzednia wersja zostaje do rollbacku.
4. Podział konfiguracji na zarządzaną (nadpisywaną) i użytkownika (nigdy nienadpisywaną), jak w AJN.
5. Aktualizacja tylko przy zamkniętym odtwarzaczu (mpv trzyma DLL-e), z wyjątkiem `yt-dlp -U`, które samo zamienia plik.

## 7. Przenośność i instalacja

**Konfiguracja przenośna** [F, `DOCS/man/mpv.rst`]: katalog `portable_config` obok `mpv.exe` jest jedynym źródłem konfiguracji; zapisuje się tam też watch_later i cache. Na Windows to zamiennik `MPV_HOME`, bo „wrapper ustawiający zmienną nie zadziała”. Pliki konfiguracji obok `mpv.exe` mają niższy priorytet.

**Python + VapourSynth przenośnie** [F]:
- R74 (2026-04-05) zmienił wszystko: instalacja przez `pip install vapoursynth`, **Python ≥ 3.12**, nowe katalogi autoloadu, Windows 10+. R75 przywrócił vsrepo w portable i dodał pliki `.bat` „bliższe ścieżkom sprzed R74”. R76 znów przestał instalować vsrepo, „bo większość wtyczek jest na PyPI”. Najnowsze: **R81 (2026-10-04)**, R82RC1 (2026-10-28). R80: „GPU SUPPORT FOR EVERYONE”.
- `Install-Portable-VapourSynth-R81.ps1`: pobiera embedded Python (domyślnie **3.14**, najnowsza łatka), dopisuje `Lib\site-packages` do `python314._pth`, instaluje pip i koło `vapoursynth-81-cp312-abi3-win_amd64.whl`, usuwa `Scripts\*.exe` (mają zaszyte ścieżki) i zostawia `pip.bat` / `vspipe.bat`. Kolejne kroki to `register-install` (globalne `VSSCRIPT_PATH`), `register-legacy-install` (rejestr), `register-vfw`.
- Biblioteki w kole: `vapoursynth/vsscript.dll`, `libvapoursynth.dll`, `vspipe.exe`, `plugins/avscompat.dll`. Autoload: `<site-packages>/vapoursynth/plugins` plus zmienna `VAPOURSYNTH_EXTRA_PLUGIN_PATH`.
- [W] Do przenośnego PlayShift `register-install` się nie nadaje, bo to globalna zmienna użytkownika. mpv nie ustawi sobie zmiennej środowiskowej, więc są trzy drogi: (a) launcher `playshift.exe` ustawia `VSSCRIPT_PATH` i `VAPOURSYNTH_EXTRA_PLUGIN_PATH` per proces; (b) `mpv --register --register-rpath=<…\site-packages\vapoursynth>` dopisuje katalog do PATH przy uruchomieniu z Eksploratora (`App Paths\mpv.exe` → `Path`); (c) zmienna użytkownika ustawiana przy rejestracji. Która działa z R81 i bieżącym mpv: **[?] do testu**.
- [?] Zgodność vs-mlrt z R81 / Python 3.14: release notes vs-mlrt nie podają wymaganej wersji VS. Wtyczki API4 powinny się ładować, ale to trzeba sprawdzić.
- Rozmiary (pobranie): mpv x86_64-v3 35 MB, Python embed 3.14 ~12 MB, koło VS R81 24 MB, yt-dlp 18 MB, deno 43 MB. Część AI: vs-mlrt TRT ok. 2,7 GB **albo** AJN ok. 0,9 GB (runtime + sm120 + rife). Obecnie 251 MB bez TensorRT.

**Skojarzenia plików** [F, `osdep/w32_register.c`]:
- `mpv --register` (mpv 0.41: „Built-in helpers to register mpv as a media app on Windows”): bez admina pisze do **HKCU**, z adminem do HKLM. Rejestruje `App Paths\mpv.exe` (`UseUrl=1`, opcjonalnie `Path` z `--register-rpath`), `Applications\mpv.exe\shell\open`, ProgID `io.mpv.*`, `Capabilities` z `FileAssociations` i `URLAssociations`, `RegisteredApplications`, protokoły strumieni oraz autoplay dla DVD, Blu-ray i CD. Po przeniesieniu katalogu wystarczy uruchomić ponownie. `--unregister` usuwa wpisy.
- Kod mpv nie ustawia domyślnej aplikacji: „Windows will prompt the user to choose”. Domyślne skojarzenie wybiera się raz w Ustawieniach; bez instalatora i z instalatorem wygląda to tak samo.
- Nazwa w rejestrze jest zaszyta (`MPV_NAME L"mpv"`). [W] Po zmianie nazwy pliku na `playshift.exe` wpisy dalej będą „mpv”. Własna nazwa w „Otwórz za pomocą” wymaga własnego skryptu rejestracji albo zostawienia `mpv.exe`.
- PlayKit: `mpv-register.bat` → `mpv.com --config=no --register`. AnimeJaNai: osobny instalator `Setup .exe` albo przenośny 7z.
- Jedna instancja (dodawanie plików do otwartego okna): PlayKit ma `umpv`/`rumpv`. Właściciel ma już `input-ipc-server=mpvpipe`, więc własny launcher może wysyłać `loadfile … append-play` przez IPC [W].

## 8. Linki z internetu

- **ytdl_hook** jest wbudowany. Szuka kolejno `yt-dlp`, `yt-dlp_x86`, `youtube-dl` najpierw w katalogach konfiguracji (`mp.find_config_file`, czyli `portable_config`), potem w PATH (`player/lua/ytdl_hook.lua` l. 970–1000). Opcje `script-opts`: `ytdl_path`, `try_ytdl_first`, `include`, `exclude`, `all_formats`, `use_manifests`, `thumbnails`. Obecny układ z `yt-dlp.exe` obok `mpv.exe` działa, bo Windows szuka najpierw w katalogu aplikacji [W]; czytelniej trzymać yt-dlp w jednym miejscu wskazanym przez `ytdl_path`.
- **Jakość**: `--ytdl-format` (domyślnie `bestvideo*+bestaudio/bestvideo+bestaudio/best`). Szybki wybór dają profile albo uosc `stream-quality` (przełącza zdefiniowane formaty bez pobierania listy). Lista realnie dostępnych formatów: [christoph-heinrich/mpv-quality-menu](https://github.com/christoph-heinrich/mpv-quality-menu) (push 2026-01-30, GPL-2.0).
- **Wklejanie ze schowka**: od mpv 0.40 (2025-03-25) jest natywna właściwość `clipboard`. Domyślne `Ctrl+v` to `update-clipboard text; loadfile ${clipboard/text} append-play` (commity 2024-12-28 i 2026-03-19 w `etc/input.conf`). **Właściciel ma `input-builtin-bindings = no`**, więc to wiązanie trzeba wpisać jawnie albo użyć uosc `paste` / `paste-to-open` / `paste-to-playlist`, które działają też w menu `open-file` i `playlist`. Obecny `SmartCopyPaste.lua` (Eisa01, push 2025-06-21) można zastąpić wbudowanym mechanizmem [W].
- **Cookies**: `--ytdl-raw-options=cookies-from-browser=firefox` albo `cookies=<plik>`. Dla przeglądarek Chromium na Windows yt-dlp ma otwarte [#10927](https://github.com/yt-dlp/yt-dlp/issues/10927) (DPAPI, od 2024-09-05, aktualizacja 2026-01-07) i [#7271](https://github.com/yt-dlp/yt-dlp/issues/7271) („Permission denied”, gdy przeglądarka jest otwarta). FAQ: metoda „działa najlepiej z Firefoksem”. Eksport `cookies.txt` obejmuje ciasteczka wszystkich stron, więc plik jest wrażliwy.
- **JS runtime**: bez `deno.exe` YouTube działa niepełnie. Patrz §6.
- [?] Odtwarzanie strumieni DASH przy 2× i seek w długich materiałach — do sprawdzenia przy teście akceptacyjnym, bez znanych problemów w źródłach.

## 9. Otwarte pytania do właściciela

1. **Repo PlayShift publiczne czy prywatne?** Od tego zależy, czy wolno brać pliki PlayKit bez licencji i elementy AnimeJaNai (CC BY-NC-SA, inference bez licencji). Pliki SVP (`svpflow*.dll`) mają własne warunki, których tu nie badano.
2. **Silnik AI: A (VS + vs-mlrt, zachowuje obecne `.vpy`, ~2,7 GB) czy B (fork AnimeJaNai, bez Pythona, ~0,9 GB, zależność od jednego autora)?** Rozstrzygnąć benchmarkiem R3 na RTX 5090 przy 2× i 170 Hz.
3. **Rytm aktualizacji mpv**: automatycznie raz w tygodniu, czy tylko na „Sprawdź aktualizacje”? yt-dlp nightly przy starcie — tak/nie?
4. **Gdzie żyje kod**: osobne repo, czy moduł w AniShift korzystający z `anishift/setup` (manifest SHA256 już istnieje)? Gdzie katalog instalacji: zostaje `C:\Users\MattyMroz\Videos\mpv`?
5. **Nazwa pliku w Windows**: `mpv.exe` (działa `--register`) czy `playshift.exe` (wymaga własnej rejestracji)?
6. **Jedna instancja**: nowy plik ma trafiać do otwartego okna (umpv/IPC) czy otwierać nowe okno?
7. **Treści z logowaniem**: z której przeglądarki brać cookies? Przy Chrome trzeba użyć Firefoksa albo `cookies.txt`.
8. **UI**: upstream uosc 5.13 z polskim tłumaczeniem, czy wbudowane OSC + menu mpv 0.41 (mniej zależności, mniej funkcji)?

## 10. Źródła (dostęp 2026-10-31)

- PlayKit: https://github.com/hooke007/mpv_PlayKit (API repo, `/commits`, `/releases`, `LICENSE.MD`, `installer/`, `portable_config/`), release https://github.com/hooke007/mpv_PlayKit/releases/tag/20260510, discussion #194 „新整合包的快速说明” (2026-05-10), wiki `0_FAQ.md`, `3_K7sfunc.md`; https://github.com/hooke007/dotfiles/releases (`mpv_addones`); https://pypi.org/project/k7sfunc/ (1.8.1).
- mpv: https://github.com/mpv-player/mpv/releases/tag/v0.41.0, `/releases/tag/git-release`, `video/filter/vf_vapoursynth.c` + commit `75b2ccfeb1` (2026-04-10), `osdep/w32_register.c`, `player/lua/ytdl_hook.lua`, `etc/input.conf`, `DOCS/man/options.rst` (`--register`, `--register-rpath`, `--ytdl-format`, `--ytdl-raw-options`), `DOCS/man/mpv.rst` (portable_config), `DOCS/man/osc.rst` (OSC Preview API), `ci/build-mingw64-full.sh`.
- Buildy: https://github.com/shinchiro/mpv-winbuild-cmake (`packages/mpv.cmake`, `vapoursynth.cmake`, releases), https://github.com/shinchiro/mpv-packaging (`updater.bat`, `installer/updater.ps1`), https://github.com/zhongfly/mpv-winbuild, https://github.com/Andarwinux/mpv-winbuild.
- AnimeJaNai: https://github.com/the-database/mpv-AnimeJaNai (README, `CLAUDE.md`, `AnimeJaNaiUpdater/Program.cs`, release 3.9.0 z `manifest.json` i `packs.json`), https://github.com/the-database/mpv (porównanie z upstream: 278 przed / 65 za).
- VapourSynth: https://github.com/vapoursynth/vapoursynth/releases (R72–R82RC1), `Install-Portable-VapourSynth-R81.ps1`, `VapourSynth64-Portable-R81.zip` (`doc/installation.html`, zawartość koła).
- vs-mlrt: https://github.com/AmusementClub/vs-mlrt/releases (v15.16, v16.test1, v16.4.test1).
- yt-dlp: README (kanały, zależności, `--js-runtimes`, `--cookies-from-browser`), `yt_dlp/update.py`, wiki `EJS.md` i `FAQ.md`, https://github.com/yt-dlp/yt-dlp-nightly-builds/releases, zgłoszenia #15012, #10927, #7271; deno https://github.com/denoland/deno/releases (v2.9.8).
- UI: https://github.com/tomasklaen/uosc (README, `src/uosc/intl/`, `src/uosc/lib/utils.lua`, release 5.13.0), https://github.com/Samillion/ModernZ, https://github.com/po5/thumbfast, https://github.com/christoph-heinrich/mpv-quality-menu, https://github.com/Eisa01/mpv-scripts.
- Inne: https://github.com/mpvnet-player/mpv.net, https://github.com/422658476/MPV-EASY-Player, https://github.com/mpc-qt/mpc-qt, https://github.com/smplayer-dev/smplayer, https://github.com/iina/iina, https://github.com/celluloid-player/celluloid, https://github.com/dyphire/mpv-config; Scoop `ScoopInstaller/Extras/bucket/mpv.json` (persist `portable_config`, hash).
- Lokalnie: `C:\Users\MattyMroz\Videos\mpv` (odczyt plików, bez uruchamiania), `anishift/setup/AGENTS.md`, `external/bin_hashes.json`.
