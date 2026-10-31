---
kind: research
id: playshift-r3-upscaling
date: 2026-10-31
subject: upscaling anime w mpv na RTX 5090 i ekranie 2560×1440 @ 170 Hz
---

# R3: upscaling anime w mpv na RTX 5090 — co, jak szybko, 2× czy 4×

Oznaczenia: **[F]** fakt ze źródłem lub pomiarem, **[W]** wniosek z kilku faktów, **[E]** estymacja z danych i jawnych założeń, **[?]** niewiadoma. Daty źródeł podaję przy linkach; całość sprawdzona 2026-10-31.

## 1. Rekomendacja

**Upscaler: mpv-AnimeJaNai 3.9.0, model `2x_AnimeJaNai_HD_V3.1_Balanced` (SPAN), tylko 2×, na TensorRT.** Źródło 1080p dostaje 2× do 2160p, a potem mpv zmniejsza obraz do 1440p. Źródło 720p dostaje 2× i wychodzi dokładnie 1440p, bez dalszego skalowania.

**4× nie ma sensu, z trzech niezależnych powodów:**

1. **[E] Nie mieści się w budżecie.** Przy prędkości 2× dwa przebiegi Balanced na 1080p zajmują ok. 25 ms na klatkę, a budżet to 20,9 ms. Dwa przebiegi Performance (ok. 17 ms) mieszczą się, ale zostawiają ok. 18% GPU na interpolację, napisy i render.
2. **[W] Nie daje więcej szczegółu na tym ekranie.** Po zmniejszeniu do 1440p przepada wszystko powyżej częstotliwości Nyquista siatki 1440p. 2160p ma już 1,5× zapasu ponad to, więc drugi przebieg zmienia tylko „styl” linii (ostrość, grubość), a tego samego dostarcza wariant `Sharp` modelu.
3. **[F] Modele HD nie są do tego trenowane.** Autor projektuje je do podwajania materiału HD. Łańcuchy 4× przewiduje dla SD: model SD, a po nim model HD.

**Architektura: natywny filtr AnimeJaNai, nie VapourSynth.**

- **[F]** Od wersji 3.4.0 (2026-06-16) AnimeJaNai nie używa VapourSynth, Pythona ani vs-mlrt. Wnioskowanie TensorRT działa w filtrze `vf_animejanai` własnego forka libmpv, a klatki zostają na GPU od dekodowania do wyświetlenia.
- **[F]** Stara ścieżka VS na RTX 5090 utykała na ok. 79 fps przy 1080p, bo ograniczał ją CPU (ffms2 i Python).
- **[F]** Od 3.6.0 paczka zawiera też `mpv.exe`, a nie tylko mpv.net. Stąd decyzja dla masterplanu: PlayShift powinien bazować na mpv z forka the-database albo przenieść filtr. Nie powinien dokładać vs-mlrt do starego mpv 0.36 z VapourSynth R65.

**Plan B bez forka:** shadery GLSL na `vo=gpu-next`, np. `Ani4Kv2_ArtCNN_C4F32` albo port `the_database_AnimeJaNaiV3L1_HD_x2` z mpv_PlayKit. Są tańsze i działają w zwykłym mpv, ale dają niższą jakość niż SPAN V3.1 na TensorRT [W].

**Budżet dla właściciela:**

- **[E] Upscaler nie jest wąskim gardłem.** Balanced przy 2× prędkości zajmuje ok. 25% czasu GPU (48 klatek × ok. 5–6,4 ms).
- **[E] Wąskim gardłem jest interpolacja do 170 fps.** RIFE nie mieści się w żadnej kolejności przy pełnym 170 fps i prędkości 2×. Mieści się RIFE ×2 przed upscalem, potem `display-resample` do 170 Hz, albo upscale ML z tanią interpolacją (SVP/NVOF). Szczegóły w §3; decyzja należy do R4.

## 2. Tabela opcji

| Opcja | Jakość dla anime | Koszt na 5090 (1080p → 2×) | Wymagania | Utrzymanie / licencja |
|---|---|---|---|---|
| **AnimeJaNai 3.9.0, HD V3.1 Balanced (SPAN b8f64)** | Najwyższa w czasie rzeczywistym [W]. Autor podaje „szybkość UltraCompact, jakość lepsza niż Compact” [F1] | **155,9 fps** w narzędziu autora (TRT 11, sam inference) [F2]; katalog społeczności dla 5090: **122–167 fps** (dekodowanie + upscale, `--vo=null`) [F3]; ok. 5 ms na klatkę w łańcuchu [F2] | NVIDIA, TensorRT 11.4 w paczce, fork libmpv, `vo=gpu-next`, Vulkan; jednorazowe budowanie silnika dla każdej rozdzielczości (ok. 10 s na TRT 11) [F2] | Bardzo aktywny: 3.9.0 z 2026-10-27, 3 wydania w tygodniu [F4]. Repo i modele na **CC BY-NC-SA 4.0** [F5]; silnik `aji` w repo bez pliku licencji [F6] |
| AnimeJaNai HD V3.1 Performance (SPAN b5f48) | Trochę niższa; autor: „prawie szybkość SuperUltraCompact, jakość lepsza niż UltraCompact” [F1] | **286–293 fps** [F2]; katalog 5090: **152–302 fps** [F3]. To jest „200–300 fps” z pamięci właściciela | jw. | jw. |
| Wariant `Sharp` (V3.1Sharp1) obu modeli | Mocniejsze linie, przełącznik w profilu [F1] | Jak model bazowy | jw. | jw. |
| AnimeJaNai 4× (dwa modele 2× w łańcuchu) | Patrz §4; dla HD bez zysku na 1440p [W] | 1080p: archiwum v3.2 nie mierzy 4× dla 1080p (puste komórki) [F7]; [E] Balanced+Balanced ok. 25 ms na klatkę, ok. 40 fps maks.; 720p → 2880p: ok. 12 ms [E] | jw. + silnik dla wejścia 2160p | jw. |
| vs-mlrt + VapourSynth + k7sfunc `UAI_NV_TRT` (ścieżka PlayKit) | Te same modele ONNX | Ścieżka VS ograniczona przez CPU: ok. 79 fps przy 1080p dla obu modeli na 5090 [F2]; w mpv dochodzi kopiowanie klatek GPU→CPU→GPU (`hwdec=auto-copy`) | vs-mlrt (TRT 11.x w gałęzi v16, tylko pre-release), VS R66+ z nowym Pythonem; lokalnie jest R65 bez vs-mlrt [F8] | vs-mlrt aktywny, GPL-3.0; v15.16 stabilne (2026-03-26), v16.4.test1 (2026-10-30) [F9] |
| ArtCNN C4F32 / C4F16 (GLSL) i Ani4Kv2_ArtCNN_C4F32 (GLSL, PlayKit) | Najlepszy shader w metrykach rekonstrukcji wg Artoriuza (C4F32 > C4F16 > RAVU > lanczos) [F10]; Ani4Kv2 trenowany na anime | [?] Nie mierzone lokalnie (brak pliku, nie pobierałem modeli) | Tylko luma; `vo=gpu-next`; działa w zwykłym mpv bez VS | ArtCNN aktywny (v1.6.2, 2026-03-14; push 2026-10-22), MIT; wagi Ani4Kv2 na CC BY-NC 4.0 [F11] |
| `the_database_AnimeJaNaiV3L1_HD_x2.glsl` (PlayKit) | Port GLSL małego modelu V3 (11 przebiegów; jaki wariant kryje się pod „L1”, nie wiem [?]) | [?] Nie mierzone | `vo=gpu-next`, bez VS i TRT | PlayKit aktywny (push 2026-10-28), CC BY-NC-SA 4.0 [F11] |
| Anime4K v4 (GLSL) | Znany; tryby A/B/C; GAN mocno „przerysowuje” [W] | Lokalnie M/L ok. 3 ms lub mniej, GAN ok. 5–9 ms (§5) | Działa w obecnym mpv | **Nieutrzymywany**: ostatnie wydanie v4.0.1 z 2021-09-17, ostatni push 2024-08 [F12] |
| FSRCNNX, nnedi3, RAVU (GLSL) | Ogólne skalery luma, nie „remaster” anime | Lokalnie ok. 3 ms lub mniej (§5) | Działa w obecnym mpv | Stare: FSRCNNX 2021, mpv-prescalers (RAVU, nnedi3) push 2024-01 [F12] |
| CuNNy (GLSL, PlayKit) | Seria rozmiarów 2x12…8x32, warianty DS/SOFT | [?] | `vo=gpu-next` | Push 2025-08, LGPL-3.0, bez wydań [F12] |
| AMD FSR EASU (obecny domyślny shader) | Skaler ogólny, nie dla anime | Lokalnie najtańszy (§5) | Działa w obecnym mpv | — |
| NVIDIA RTX Video Super Resolution (`--vf=d3d11vpp=scaling-mode=nvidia`) | Ogólny, nie dla anime [?] | Prawie darmowy dla shaderów; liczy się w sterowniku | d3d11, włączenie w panelu NVIDIA, nowy mpv [F13] | Wbudowany w mpv |

Uwagi do tabeli:

- **[F]** Liczby katalogu AnimeJaNai z 720p i niższych (np. 400; 600; 1200) są skwantowane, więc wyglądają na ograniczone czymś innym niż GPU. Wiarygodne są głównie kolumny 1080p.
- **[F]** Profil „Quality” w 3.9.0 używa **tego samego** modelu Balanced. Różni się tylko tym, że dodatkowo upscaluje źródła do 61 fps (`aji_conf.cpp`, `add_builtin_slots`) [F6]. README z tabelą „Quality: RTX 4090” jest w tym miejscu nieaktualne.

## 3. Budżet klatek

Założenia: źródło 24000/1001 = 23,976 fps; prędkość 2× daje **47,95 klatki źródła na sekundę, czyli 20,85 ms na klatkę źródła**. Wyjście ma 170 Hz, czyli 5,88 ms na klatkę ekranu. Przy zachowaniu klatek źródła trzeba wytworzyć **122 klatki pośrednie na sekundę** (2,55 na klatkę źródła).

**[F] Pomiary autora na RTX 5090 (TRT 11, CUDA 13.3)** [F2]:

- Balanced 1920→3840: ok. 5 ms (w narzędziu 155,9 fps, czyli 6,4 ms z pre/post-processingiem).
- Performance: ok. 3,4 ms.
- RIFE v4.14 przy 1080p: ok. 6 ms na klatkę pośrednią.
- RIFE przy 4K: ok. 25 ms.
- Kolejność „RIFE → upscale” jest w AnimeJaNai domyślna od 3.5.0 i wygrywa 1,4× (21,7 wobec 31,2 ms na klatkę źródła przy RIFE 2×).

**[F] mpv nie zwalnia filtrów przy szybszym odtwarzaniu.** Domyślne `--framedrop=vo` „still decodes and filters all frames” [F13], a filtr AnimeJaNai wybiera łańcuch po nominalnym fps źródła, nie po prędkości (`vf_animejanai.c`: `p->fps = in_fmt->nominal_fps`) [F14]. **Przy 2× upscaler musi więc przerobić 48 klatek/s.**

Czas GPU na sekundę odtwarzania [E] (liniowe skalowanie RIFE z pikselami między 1080p a 4K, czyli ok. 3 ms/MPx dla 1440p ≈ 11 ms; bez kosztu renderu mpv i napisów, zwykle ok. 1–2 ms na klatkę ekranu):

| Wariant przy 2× prędkości | Rachunek | ms GPU / s | Wynik |
|---|---|---|---|
| A. upscale → RIFE w 4K, 170 fps | 48×5 + 122×25 | ≈ 3290 | 3,3× ponad budżet |
| A'. upscale → zmniejszenie do 1440p → RIFE w 1440p, 170 fps | 48×5 + 122×11 | ≈ 1580 | 1,6× ponad budżet |
| B. RIFE w 1080p → upscale każdej klatki, 170 fps (Balanced) | 122×6 + 170×5 | ≈ 1580 | ponad budżet |
| B. jw. (Performance) | 122×6 + 170×3,4 | ≈ 1310 | ponad budżet |
| C. RIFE ×2 w 1080p → upscale 96 fps (Balanced) → `display-resample` do 170 Hz | 48×6 + 96×5 | ≈ 770 | mieści się na granicy (77%) |
| C. jw. (Performance) | 48×6 + 96×3,4 | ≈ 615 | mieści się (61%) |
| D. upscale ML 48 fps + interpolacja nie-ML (SVP/NVOF, R4) | 48×5 + koszt R4 | ≈ 240 + R4 | upscaler bierze ok. 24%, zostaje ok. 75% |
| E. tylko upscale, bez interpolacji | 48×6,4 | ≈ 310 | swobodnie (31%) |
| F. 4× (Balanced+Balanced) bez interpolacji | 48×(5 + ok. 20) | ≈ 1200 | nie mieści się |
| F'. 4× (Performance+Performance) | 48×(3,4 + ok. 13,6) | ≈ 820 | mieści się bez interpolacji (82%) |

Dla porównania przy 1× (23,976 fps) [E]:

- Wariant B przy pełnym 170 fps: 146×6 + 170×5 ≈ 1730 ms/s, czyli nadal ponad budżet.
- RIFE ×3 przed upscalem (72 fps): 48×6 + 72×5 ≈ 650 ms/s, mieści się.

Wnioski [W]:

1. **Kolejność „interpolacja → upscale” jest tańsza tylko przy małym mnożniku.** Przy 170 fps na wyjściu każda klatka pośrednia przechodzi przez upscaler, więc koszt rośnie z liczbą klatek wyjścia. „Upscale → interpolacja” płaci natomiast RIFE w dużej rozdzielczości, co przy 170 fps jest jeszcze droższe. Pełne RIFE 170 fps z upscalem ML nie mieści się w 5090 w żadnej kolejności.
2. **Realne konfiguracje:**
   - C: RIFE ×2 w 1080p, potem upscale, potem `video-sync=display-resample` z `tscale` do 170 Hz.
   - D: upscale ML i interpolacja nie-ML do 170.
   - Przy prędkości 1× także RIFE ×3 w wariancie C.
3. **Upscaler nie jest wąskim gardłem.** Balanced zostaje modelem domyślnym; na Performance warto zejść tylko po to, by zrobić miejsce dla RIFE.

Ograniczenie: liczby ms pochodzą z syntetycznej, synchronicznej uprzęży autora. Odtwarzanie ma kolejkę głębokości 3 i jest o 6–34% szybsze [F2], więc wyniki „na granicy” wymagają pomiaru, a nie rachunku.

## 4. 2× czy 4× na ekranie 1440p

Źródło 1080p:

- 2× daje 2160p, czyli 1,5× liniowo ponad ekran. 4× daje 4320p, czyli 3× ponad ekran.
- **[W]** Po zmniejszeniu do 2560×1440 obraz może zawierać tylko częstotliwości poniżej Nyquista siatki 1440p. Wszystko, co model doda powyżej tej granicy, filtr zmniejszający usuwa (albo zamienia w aliasing, jeśli jest zły). Różnica między 2× a 4× po zmniejszeniu leży więc wyłącznie w tym, jak drugi przebieg zmienia pasmo poniżej 1440p: grubość i ciemność linii, wyostrzenie krawędzi, ewentualne wzmocnienie artefaktów. To zmiana charakteru obrazu, nie rozdzielczości.
- **[F]** Modele HD V3 są trenowane do usuwania rozmycia materiału HD przeskalowanego do 1080p. Autor przewiduje łączenie modeli dla SD: „stacked with the HD models to upscale SD anime to 4k” [F1]. Drugi przebieg HD na ostrym wyjściu 4K tego samego modelu wychodzi poza dane treningowe [W].
- **[F]** Projekt ma do zmiany ostrości gotowy, równie tani wariant `Sharp` [F1]. Jeśli właścicielowi chodzi o „mocniejszy” obraz, to jest właściwe pokrętło.
- **[?]** Nie znalazłem publicznego porównania „4× + zmniejszenie” wobec „2× + zmniejszenie” na ekranie 1440p (wyszukiwanie 2026-10-31). Rozstrzygnąć może tylko A/B na zrzutach (§6).

Źródło 720p: 2× daje dokładnie 2560×1440 [F]. To optymalny przypadek, bez końcowego skalowania. 4× (2880p) jest tu tym bardziej zbędne.

Wariant do sprawdzenia [W]: dla 1080p o natywnej produkcji ok. 720–900p (README twierdzi, że tak powstaje większość HD anime [F1]) można zmniejszyć wejście do 720p, a potem zrobić 2× do 1440p. Manager AnimeJaNai ma opcję zmniejszania przed upscalem [F1]. Taki upscale kosztuje ok. 2,3 ms zamiast 6,4 ms i nie wymaga końcowego zmniejszenia, ale traci detal ponad 720p. Tylko A/B rozstrzygnie, który wariant wygląda lepiej.

Zmniejszanie 2160p → 1440p w mpv: `profile=high-quality` AnimeJaNai ustawia własny `dscale`. Artoriuz zauważa, że domyślny Hermite zmiękcza obraz [F10]. Do A/B warto porównać `dscale=hermite`, `catmull_rom` i `mitchell` z `correct-downscaling=yes` [W].

## 5. Pomiary lokalne

### 5.1 Stan lokalny (tylko odczyt)

- **[F]** `VSPipe.exe --version` zwraca VapourSynth Core **R65**, API R4.0/R3.6. Wtyczki w `vapoursynth64\plugins`: `MiscFilters`, `RIFE` (ncnn/Vulkan), `VMAF`, `mvtools`/`libmvtools`, `svpflow1/2`; w `coreplugins` tylko `AvsCompat`.
  - **Brak filtra źródła** (ffms2, lsmas, bestsource), więc VSPipe nie otworzy MKV bez mpv.
  - **Brak vs-mlrt, TensorRT, akarin i plików ONNX/engine.**
  - Modele to tylko RIFE ncnn: `rife-v4`, `rife-v4.6_ensembleFalse`, `rife-v4.8_ensembleFalse`, `rife-v4_ensembleFalse_fastTrue`.
- **[F]** `k7sfunc.py` 0.1.23 ma funkcje `UAI_NV_TRT`, `CUGAN_NV`, `ESRGAN_NV` (wymagają `vsmlrt`, którego nie ma). Skrypty w `portable_config\vs\` dotyczą tylko interpolacji (MVTools, SVP, RIFE); żaden nie upscaluje.
- **[F]** Shadery w `portable_config\shaders\`: AMD FSR (4), Anime4K v4 (M/L, GAN_UL+x2_M, AutoDownscalePre), FSRCNNX x2 8/16, nnedi3 nns128 win8x4/8x6, KrigBilateral, SSimDownscaler, adaptive_sharpen, hdeband, nlmeans_dx. Brak ArtCNN, CuNNy, RAVU i portów AnimeJaNai.
- **[F]** `mpv.com --version`: **v0.36.0-711-g250429da** (build 2023-11-02), libplacebo v6.338. Ma `vf=vapoursynth`, `libplacebo` i `d3d11vpp`. `mpv.conf`: brak `vo` (w tej wersji domyślnie `gpu`), `hwdec=auto-copy`, `glsl-shaders-append=AMD_FSR_EASU_rgb.glsl`.
- **[F]** Profil `[vsync_auto]` w `profiles.conf` ma `profile-cond = p.display_fps>122 or p.container_fps>32` i ustawia `interpolation=no`, `video-sync=audio`. **Przy monitorze 170 Hz wyłącza więc interpolację mpv.** Ważne dla R4 i wariantu C.

### 5.2 Pomiar kosztu shaderów GLSL (headless, bez okna)

VSPipe nie mógł zmierzyć upscalera: brakuje filtra źródła i vs-mlrt, a ich pobranie było zakazane. Zmierzyłem więc koszt **lokalnych** shaderów przez filtr `libplacebo` w już zainstalowanym FFmpeg 9.0.2 (winget, Gyan full build; ten sam silnik hooków co `vo=gpu-next`). Nic nie instalowałem i nie otworzyłem okna. Shadery czytałem z katalogu mpv tylko do odczytu, a skopiowane i sklejone pliki leżały w katalogu tymczasowym sesji.

Wejście: 96 klatek z pliku testowego od 300 s (HEVC 1080p 10-bit), zapętlone w RAM, wysyłane na GPU i przeskalowane do 2560×1440. W ten sposób odpada sufit dekodowania, który bez pętli wynosił ok. 170–190 fps (`-hwaccel vulkan`, 720 klatek w 4,26 s).

```sh
ffmpeg -hide_banner -nostats -benchmark -init_hw_device vulkan=vk -filter_hw_device vk \
  -ss 300 -i "<Edgerunners 2 - 01.mkv>" -an -sn -dn \
  -vf "loop=loop=-1:size=96:start=0,format=yuv420p10le,hwupload,libplacebo=w=2560:h=1440:upscaler=ewa_lanczossharp:custom_shader_path=sh/<shader>.glsl" \
  -frames:v 2000 -f null -
```

Wyniki (fps, 2000 klatek, kilka powtórzeń):

| Konfiguracja (→ 2560×1440) | Pomiary fps |
|---|---|
| sam `ewa_lanczossharp` (bez shadera) | 479, 587*, 515*, 395, 313, 496 |
| AMD_FSR_EASU_rgb (obecny domyślny) | 621, 365, 357, 381 |
| KrigBilateral | 356, 450, 413, 409 |
| nnedi3_nns128_win8x4 | 178, 363, 369, 345 |
| FSRCNNX_x2_16_0_4_1 | 218, 298, 319, 323 |
| Anime4K Restore_CNN_M + Upscale_CNN_x2_M | 285, 291, 370, 479 |
| Anime4K Restore_CNN_L + Upscale_CNN_x2_L + AutoDownscalePre_x2/x4 + Upscale_CNN_x2_M | 172, 308, 356, 392, 419 |
| Anime4K Restore_GAN_UL + Upscale_GAN_x2_M | 193, 119, 114, 202 |

\* przebieg na 3000 klatkach.

Odczyt:

- **[F]** Uprząż ma sufit ok. 300–600 fps i rozrzut ±40%. W trakcie przebiegu `nvidia-smi` pokazywał 40–74% obciążenia GPU przy 2,8–2,9 GHz, więc ffmpeg jest częściowo ograniczony synchronizacją lub CPU.
- **[W]** Liczby są więc górną granicą kosztu, nie dokładnym czasem. Wszystkie lokalne shadery poza GAN kosztują **najwyżej ok. 3 ms** na klatkę 1080p → 1440p. Anime4K GAN kosztuje ok. **5–9 ms**. Każdy z nich mieści się w 48 fps z dużym zapasem.
- **[?]** Te pomiary nie mówią nic o AnimeJaNai ani o ArtCNN, bo żadnego z nich nie ma lokalnie.

### 5.3 Plan pomiaru AnimeJaNai (po zgodzie właściciela na pobranie)

Pobranie wymaga zgody, bo to ok. 0,6–1 GB (paczka plus komponenty TRT runtime i sm120), plus RIFE 441 MB [F4].

1. Rozpakować portable 3.9.0 do osobnego katalogu, np. `C:\Users\MattyMroz\tmp\ajn\`, nie do `Videos\mpv`.
2. **Sam upscale (bez okna):** `powershell -File animejanai\benchmarks\benchmark.ps1 -OnlyRes 1920x1080`. Skrypt sam uruchamia `mpvnet.com --vo=null --untimed --load-scripts=no --cache=no`. Wynik: fps Balanced i Performance [F15].
3. **Prawdziwy plik:** `mpv.exe --vo=null --untimed --load-scripts=no --cache=no --hwdec=nvdec --start=300 --frames=2000 --vf=@aji:animejanai:lib=…/aji.dll:conf=…:model-dir=…/onnx:rife-model-dir=…/rife:trtexec=…:slot=1002 "<Edgerunners.mkv>"`. Policzyć fps z logu, tak jak w BENCHMARKS.md [F2]. Potem powtórzyć dla `slot=1003` (Performance) i `1012`/`1013` (RIFE 2× w obu kolejnościach).
4. **Koszt RIFE w łańcuchu:** `aji_harness --rife-chain --slot 1013 --frames 240` (komenda w [F2]), dla różnych mnożników.
5. **VRAM i czas budowy silnika:** `nvidia-smi --query-gpu=memory.used -lms 500` w trakcie kroków 3–4; czas od „Configured slot” w logu.
6. **A/B wizualne (wymaga okna i oceny właściciela):** zrzuty tej samej klatki w 1440p:
   - off;
   - FSR (obecny);
   - Anime4K A;
   - ArtCNN/Ani4Kv2 (shader);
   - AnimeJaNai Balanced i Balanced Sharp;
   - 4× Performance+Performance;
   - wariant „zmniejszenie do 720p + 2×”.

   Do tego odtwarzanie z prędkością 2× i statystykami (Ctrl+J lub `i`): liczba porzuconych klatek przy 170 Hz.

## 6. Ryzyka

1. **[F] Licencje.**
   - Modele i repo AnimeJaNai są na CC BY-NC-SA 4.0 [F5]. Do użytku prywatnego wystarcza, ale wag nie wolno wkładać do publicznego repo AniShift ani PlayShift bez dziedziczenia NC-SA. Bezpieczniej pobierać je przy instalacji.
   - Repo silnika `aji` (`the-database/animejanai-inference`) nie ma pliku licencji [F6], więc formalnie nie daje praw do modyfikacji ani redystrybucji.
   - Fork mpv podlega licencji mpv (GPL/LGPL).
2. **[F] Zależność od jednego autora i szybkie tempo zmian.** 3.4.0 była przepisaniem silnika od zera („may be more bugs than usual”), a od 2026-10-07 do 2026-10-27 wyszły 4 wydania z poprawkami TRT. Wymaga przypięcia wersji [F4].
3. **[F] RTX 50xx + Vulkan:** otwarte issue #200 (2026-09-24). `mpvnet.exe` nie otwiera okna na RTX 5080 z `gpu-api=vulkan,auto`; obejściem jest usunięcie tej linii [F16]. Właściciel ma RTX 5090, więc trzeba to sprawdzić przy pierwszym uruchomieniu.
4. **[F] Budowanie silnika TensorRT** przy pierwszym odtworzeniu każdej rozdzielczości: ok. 10 s na TRT 11, ok. 60 s na TRT 10 [F2]. Przerwane budowanie psuło silnik, co naprawiono w 3.8.1 [F4]. Silniki są związane z wersją TRT i sterownikiem, więc aktualizacja wymusza przebudowę [W].
5. **[W] Integracja z obecnym mpv.** Lokalny mpv 0.36 (2023) nie ma filtra `aji`. Przejście na fork zmienia bazę całego PlayShift: uosc, skrypty, `input_uosc.conf` i profile trzeba przenieść. Fork AnimeJaNai ma też własne zmiany napisów i OSD (GPU subtitles, `sub-render-ahead`), co dotyczy AniShift i stylu Officina.
6. **[E] Interpolacja do 170 fps z RIFE nie zmieści się** przy prędkości 2× (§3). Oczekiwanie „upscale + RIFE 170” trzeba skorygować przed planem.
7. **[F] Profil `vsync_auto` wyłącza interpolację przy 170 Hz** (§5.1). Przy przenoszeniu konfiguracji trzeba go świadomie zmienić.
8. **[?] VRAM** dla 4× i RIFE w 4K nie jest opublikowany. 32 GB raczej wystarczy [W], ale to wymaga pomiaru (§5.3 krok 5).
9. **[W] Migotanie.** Modele jednoklatkowe mogą migotać na teksturach. W 3.9.0 doszedł „Temporal Fix”, ale autor opisuje go jako przydatny głównie dla DVD i SD [F4].

## 7. Pytania do właściciela

1. Czy możesz zaakceptować, że PlayShift przejdzie na mpv z forka the-database (z AnimeJaNai), zamiast rozwijać obecny mpv 0.36 z VapourSynth? Od tego zależy reszta planu.
2. Czy zgadzasz się na pobranie portable AnimeJaNai 3.9.0 (ok. 1 GB) do osobnego katalogu, żeby wykonać pomiary i A/B z §5.3?
3. Przy prędkości 2× co jest ważniejsze: upscale Balanced z interpolacją nie-RIFE do 170 Hz, czy RIFE ×2 (ok. 96 fps) z upscalem i resztą przez `display-resample`?
4. „Woli 4×” — chodzi o więcej szczegółu, czy o mocniejsze, ostrzejsze linie? Jeśli o linie, odpowiedzią jest wariant `Sharp`, a nie 4×. Czy zrobić A/B obu?
5. Czy PlayShift ma być publiczny? Od tego zależy, czy wagi CC BY-NC-SA wolno trzymać w repo, czy trzeba je pobierać przy instalacji.

## 8. Źródła

- **[F1]** README mpv-AnimeJaNai (main, odczyt 2026-10-31): https://github.com/the-database/mpv-AnimeJaNai. Release notes 3.3.0 (2026-06-02, modele V3.1 SPAN, przełącznik Sharp) i 3.4.0 (2026-06-16, natywny silnik): https://github.com/the-database/mpv-AnimeJaNai/releases
- **[F2]** `BENCHMARKS.md` w `the-database/animejanai-inference`, ostatni commit 2026-06-17 (RTX 5090, TRT 10.16/11.0, kolejność RIFE/upscale, ms na etap): https://github.com/the-database/animejanai-inference/blob/main/BENCHMARKS.md
- **[F3]** Katalog benchmarków społeczności, `benchmarks.json` wygenerowany 2026-10-28; wpisy RTX 5090 i 4090 z wersji 3.4.0–3.6.3: https://benchmarks.animejan.ai/ (dane: https://benchmarks.animejan.ai/benchmarks.json)
- **[F4]** Wydania 3.6.0–3.9.0 (2026-07-24 … 2026-10-27), assety i `packs.json`/`manifest.json` 3.9.0 (TRT 11.4.0.106, fork mpv 2026-10-24, mpv.net 7.1.2.0): https://github.com/the-database/mpv-AnimeJaNai/releases/tag/3.9.0
- **[F5]** `LICENSE` (CC BY-NC-SA 4.0) w https://github.com/the-database/mpv-AnimeJaNai
- **[F6]** `src/aji_conf.cpp` (`add_builtin_slots`: Quality, Balanced i Performance, max_fps 31/61, sloty 1010–1013) oraz brak pliku licencji w https://github.com/the-database/animejanai-inference (push 2026-10-30)
- **[F7]** Wiki AnimeJaNai, „Benchmarks (Archive)” i strona „Astral RTX 5090 OC + 9950X3D v3.2.2”, wersje ≤3.3.0 na VapourSynth; ostatnia zmiana wiki 2026-06-13: https://github.com/the-database/mpv-AnimeJaNai/wiki
- **[F8]** Lokalnie: `VSPipe.exe --version`, listing `vapoursynth64\`, `k7sfunc.py` (`__version__ = "0.1.23"`)
- **[F9]** Wydania vs-mlrt (v15.16 z 2026-03-26; v16.x.test1 z 2026-06…2026-10-30): https://github.com/AmusementClub/vs-mlrt/releases
- **[F10]** Artoriuz, „mpv Resampling Evaluation” (bez daty na stronie; jeden obraz anime, metryki MAE/PSNR/SSIM/MS-SSIM; bez pomiarów czasu): https://artoriuz.github.io/blog/mpv_upscaling.html. ArtCNN README i wydania: https://github.com/Artoriuz/ArtCNN
- **[F11]** mpv_PlayKit: lista shaderów (gałąź main, odczyt 2026-10-31), nagłówki `ESRGAN/the_database_AnimeJaNaiV3L1_HD_x2.glsl` i `Ani/Ani4Kv2_ArtCNN_C4F32_i2.glsl`, wiki `4_GLSL` i `3_K7sfunc` (ostatnia zmiana 2026-05-14), wydanie 20260510: https://github.com/hooke007/mpv_PlayKit
- **[F12]** Metadane GitHub API (2026-10-31): bloc97/Anime4K, funnyplanter/CuNNy, bjin/mpv-prescalers, igv/FSRCNN-TensorFlow
- **[F13]** Podręcznik mpv (master): `--framedrop` („still decodes and filters all frames”) w `DOCS/man/options.rst`; `d3d11vpp scaling-mode=nvidia` w `DOCS/man/vf.rst`: https://github.com/mpv-player/mpv/tree/master/DOCS/man
- **[F14]** `video/filter/vf_animejanai.c` w forku https://github.com/the-database/mpv (push 2026-10-26)
- **[F15]** `animejanai/benchmarks/benchmark.ps1` (tryb offscreen `--vo=null`, sloty 1010/1011) w repo mpv-AnimeJaNai
- **[F16]** Issue #200 „mpvnet.exe doesn't open” (otwarte; 2026-09-24, komentarz 2026-10-04): https://github.com/the-database/mpv-AnimeJaNai/issues/200. Issue #56 (subiektywna ocena ostrości V3): https://github.com/the-database/mpv-AnimeJaNai/issues/56
