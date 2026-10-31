---
kind: research
id: playshift-r4-interpolation-color
date: 2026-10-31
subject: interpolacja klatek i obróbka koloru w mpv na RTX 5090, monitor 2560×1440 @ 170 Hz, oglądanie przy 2×
---

# R4: interpolacja klatek i kolor w mpv na RTX 5090

Oznaczenia: **[F]** fakt ze źródłem lub pomiarem, **[W]** wniosek z kilku faktów, **[E]** estymacja z jawnych założeń, **[?]** niewiadoma. Źródła sprawdzone 2026-10-31. Pomiary lokalne wykonano 2026-10-31 na tym komputerze (RTX 5090, sterownik 610.88, Intel Core Ultra 7 265KF, 20 wątków). Komendy są w §5.

## 1. Rekomendacja

1. **Silnik: RIFE na TensorRT, nie obecny RIFE ncnn.** [F] Obecny build ma wtyczkę `RIFE.dll` (ncnn/Vulkan) z modelem **v4.0 z 2021 roku**. Katalogi `rife-v4.6`/`rife-v4.8` istnieją, ale wtyczka ich nie wczyta (`layer MemoryData not exists`). [F] W mpv ta ścieżka daje **60–70 klatek/s** dla 1080p ×2, więc przy 2× (potrzeba 96) nie nadąża nawet ze zwykłym podwojeniem. GPU jest przy tym zajęte w 30–50%, czyli wąskim gardłem jest CPU i transfer, nie karta. Kierunek: RIFE 4.25/4.26 przez TensorRT. Są dwie ścieżki:
   - **Natywny filtr forka AnimeJaNai.** R3 i tak go rekomenduje do upscalingu. Ma RIFE na TensorRT, klatki zostają na GPU, a od 3.5.0 RIFE domyślnie idzie przed upscalem [F]. [?] Nie sprawdziłem, czy ten filtr pozwala ustawić **ułamkowy mnożnik albo docelowe fps** i który model RIFE wspiera. To pierwsza rzecz do ustalenia, bo od tego zależy cel 85/170 z pkt 2.
   - **vs-mlrt w VapourSynth (ścieżka mpv_PlayKit, `k7sfunc.RIFE_NV`).** Zalety: ułamkowy mnożnik (`fractions.Fraction`), modele 4.6/4.25-lite/4.26/4.26-heavy oraz anime-specyficzny DRBA [F]. Wada: ta sama ścieżka VS z kopiowaniem GPU→CPU→GPU, która wg R3 dławi się na CPU ok. 79 fps przy upscalingu 1080p [F, R3].
2. **Cel klatek: 85 fps jako domyślny, 170 fps jako tryb „max”.** [W] 85 = 170/2, więc każda klatka trwa równo dwa odświeżenia i nie ma judderu. Kosztuje przy tym ok. połowę obliczeń RIFE. Przy prędkości 2× cel 85 oznacza mnożnik ≈1,77 względem 23,976 fps, a cel 170 mnożnik ≈3,55. **Przy prędkości 1× te same cele wymagają mnożników 3,55 i 7,09.** Filtr musi więc znać prędkość: mpv nie przekazuje jej do skryptu VS. Obecne mpv w `vf vapoursynth` ma za to parametr `user-data` [F], więc skrypt Lua może przy zmianie `speed` przeładować filtr z nowym celem.
3. **Tani wariant zapasowy, działający już dziś: SVP (svpflow).** [F] W mpv `memc_svp_170.vpy` daje **244 klatki/s** (potrzeba 170), czyli działa w czasie rzeczywistym. Jakość jest blokowa (gorsza od RIFE na liniach anime [W]), ale koszt GPU jest pomijalny. mvtools do 170 fps **nie nadąża** w mpv (134/s).
4. **Interpolacja mpv (`--interpolation`, `tscale`) to nie generowanie klatek.** To czasowe mieszanie istniejących klatek pod odświeżanie ekranu. [F] Profil `[vsync_auto]` w lokalnym `profiles.conf` **wyłącza ją na monitorze 170 Hz** i przełącza `video-sync=audio`, więc ustawione `tscale=linear` dziś w ogóle nie działa. W nowym projekcie: `video-sync=display-resample`, a gdy wyjście VS równa się odświeżaniu lub jego połowie, `interpolation` niepotrzebne. Jeśli `tscale` ma zostać, to `oversample`, nie `linear` (rozmywa).
5. **Kolor: bez rewolucji.** Zostaje wyjście 8-bit z ditheringiem (domyślne). Zostaje automatyczny deband dla niskiego bitrate'u (test: 2,0 Mb/s, więc profil `deband_bitrate` się włącza). Do decyzji właściciela zostaje **nasycenie**: oba monitory mają gamut szerszy niż sRGB (~P3), w systemie nie ma profilu ICC, a Windows nie zarządza kolorem. Anime BT.709 jest więc pokazywane przesycone, chyba że monitor ma włączony tryb sRGB. HDR passthrough i wyjście 10-bit dają tu niewiele (§3).
6. **Kolejność łańcucha: interpolacja w natywnej rozdzielczości źródła, potem upscale, i tylko przy celu 85 fps.** [E] Przy 170 fps RIFE sam zjada 60–90% GPU, więc upscale ML nie mieści się w żadnej kolejności. To zgodne z rachunkiem R3 (§4).

## 2. Opcje interpolacji

| Opcja | Co robi | Jakość dla anime | Koszt / pomiar | Ułamkowy mnożnik | Utrzymanie, licencja |
|---|---|---|---|---|---|
| **RIFE ncnn (lokalny `RIFE.dll`, model v4.0)** | Sieć optical flow, Vulkan | Model z 2021; nowsze modele są „znacznie lepsze na scenach anime” (autor o 4.25) [F1] | [F] VSPipe 1080p ×2: 107–118 kl./s; w mpv 60–70 kl./s; GPU 30–50% (CPU-bound) | Tak (`factor_num/den`, tylko v4); ×3,5 zmierzone: 90 kl./s | Wtyczka przyjmuje tylko modele 0–9, v4.6/v4.8 się nie ładują [F] |
| **RIFE 4.25/4.26 przez vs-mlrt (TensorRT)** | To samo, fp16, TRT | Autor RIFE: „4.25 domyślnie dla większości scen”; 4.26 z 2024-09-21 [F1] | [F] RTX 4090, 1080p ×2: 4.26: 410 kl./s wyj. (~205 inferencji/s, ~4,9 ms); 4.26.heavy: 279 kl./s; 4.6: 427 kl./s [F2]. 5090: [?] brak publicznej liczby; R3 cytuje ~6 ms/klatkę dla RIFE v4.14 1080p w uprzęży AnimeJaNai | Tak, `multi: int \| Fraction`, tryb `video_player` [F3] | vs-mlrt aktywny: stabilne v15.16 (2026-03-26, TRT 10.16, CUDA 13.2), test v16.4 (2026-10-30, TRT 11.4) [F4]; TRT od 10.8 wspiera RTX 50 [F5] |
| **DRBA (distilDRBA przez vs-mlrt / K7sfunc)** | Steruje RIFE mapą „distance ratio”, by zachować tempo animacji (klatki na dwójki/trójki) i ograniczyć zniekształcenia [F6] | Projektowany pod anime [F6]; [?] brak niezależnej oceny | [F] 4090, 1080p ×2, DRBA+RIFE 4.26: 309 kl./s (~1,3× koszt samego RIFE) [F2] | Tak (`Fraction`) [F7] | DRBA push 2026-08; VS-DRBA 2025-03; w mpv_PlayKit jako `MEMC_DRBA_NV.vpy` [F7] |
| **GMFSS (Fortuna/union)** | Anime-specyficzny VFI na GMFlow | Wysoka jakość offline [W] | Ciężki, PyTorch; nie znalazłem integracji real-time w mpv (brak w PlayKit) [?] | — | Repo push 2026-01, vs-gmfss_fortuna porzucone (2023-04) [F8] |
| **SVP (svpflow1/2, bez SVP Managera)** | Wektory ruchu blokami, render GPU | Blokowe artefakty na krawędziach linii [W] | [F] mpv, cel 170: 244 kl./s; VSPipe: 442 (cel 170), 322 (cel 85), 227 (NVOF, cel 85) | Tak, dowolne docelowe fps | svpflow1 GPL, svpflow2 zamknięty; wiki SVP: biblioteki „wymagają działającego SVP Managera”, inaczej czerwona ramka [F9]. Lokalna starsza wersja ramki nie rysuje (2 klatki sprawdzone wizualnie) [F] |
| **SVP 4 Pro (pełny program)** | Manager + svpflow + RIFE TRT/ncnn | jw. + RIFE | Wiki: TensorRT „do 100% szybszy” niż ncnn [F10] | Tak | **24,99 USD, licencja dożywotnia**, 30 dni trialu, kolejny komputer 15 USD [F11] |
| **mvtools (BlockFPS, lokalne `mvtools_*.vpy`)** | Wektory ruchu na CPU | Słabsza niż SVP/RIFE [W] | [F] mpv, cel 170: **134 kl./s, nie nadąża**; VSPipe: 190 (cel 170), 150 (cel 85) | Tak | Wtyczka ładowana podwójnie (`mvtools.dll` + `libmvtools.dll`, ostrzeżenie) [F] |
| **`--interpolation` + `tscale` mpv** | Mieszanie sąsiednich klatek pod Hz ekranu, bez nowych faz ruchu | Usuwa judder, nie dodaje płynności ruchu; `oversample` najostrzejszy, `linear` rozmywa [F12] | Tani [W]; wymaga `video-sync=display-*` [F12] | n/d | Rdzeń mpv |
| **NVIDIA Smooth Motion / Lossless Scaling** | Generowanie klatek w sterowniku lub nakładce | [?] | [?] | — | Smooth Motion ogłoszony dla gier DX11/DX12 na RTX 50; nie znalazłem potwierdzenia działania z mpv [F13]. Nie badałem dalej |

**Ograniczenia RIFE wspólne dla wszystkich ścieżek:**

- **Sceny.** [F] Wynik silnie zależy od detekcji cięć (`misc.SCDetect`/`mv.SCDetection`). Niewykryte cięcie daje „morfing”, fałszywe wykrycie powtarza klatkę [F3][F10].
- **Napisy wtopione.** [W] Napisy miękkie mpv renderuje po filtrach, więc nie są interpolowane. Napisy wtopione i znaki na ekranie będą falować. Erai-raws ma napisy miękkie.
- **Seek.** [F] Skrypt VS jest **przeładowywany przy każdym seeku**. W mpv start filtra trwa ok. **2,5 s** dla RIFE ncnn, 1,2 s dla SVP, 1,8 s dla mvtools (§5). Silnik TensorRT trzeba raz zbudować, co trwa minuty („really slooow” wg SVP) [F10]. [?] Czas deserializacji zbudowanego silnika przy seeku trzeba zmierzyć.
- **Opóźnienie.** [W] Filtr buforuje kilka klatek, a mpv synchronizuje A/V po znacznikach czasu, więc przy oglądaniu nie przeszkadza.
- **Mnożniki ułamkowe.** [F] RIFE v4 przyjmuje dowolny moment `t` między klatkami. vs-mlrt w trybie `video_player` wylicza dla każdej klatki wyjścia parę klatek źródła i `t` [F3], a lokalna wtyczka ncnn obsłużyła ×7/2 bez błędu (§5). Koszt rośnie z liczbą klatek pośrednich, nie z „ładnością” mnożnika.
- **Prędkość 2×.** [F] Skrypt dostaje tylko `container_fps`, `display_fps`, `display_res` i `user_data`, bez prędkości [F14]. [W] Lokalne `memc_svp_170.vpy` i `mvtools_170.vpy` celują w 170 fps w czasie treści, więc przy 2× produkują 340 klatek/s, z których połowa idzie do kosza. Cel trzeba liczyć jako `odświeżanie / speed`.

## 3. Kolor

**Stan monitora** [F, odczyt bez okien: DXGI `IDXGIOutput6::GetDesc1`, EDID z rejestru, `EnumDisplaySettings`, `MonitorDataStore`]:

| | DISPLAY1 Gigabyte M27Q | DISPLAY2 Gigabyte G34WQC2 |
|---|---|---|
| Tryb | 2560×1440 @ **170 Hz** (ekran drugi, po prawej) | 3440×1440 @ **200 Hz** (**ekran główny**) |
| Bity na kolor teraz | 8 | 8 |
| HDR w Windows | wyłączony (`HDREnabled=0`) | wyłączony |
| EDID | interfejs 12 bit, blok HDR (SDR + PQ) | interfejs 10 bit, blok HDR (SDR, HDR-gamma, PQ) |
| Luminancja (DXGI) | max 418 nit, min 0,124 | max 486 nit, min 0,102 |
| Prymarne R/G/B (DXGI, z EDID) | (0,677;0,318) (0,271;0,671) (0,151;0,046) | (0,680;0,314) (0,273;0,657) (0,152;0,046) |

Profil ICC monitora: brak (w `spool\drivers\color` są tylko `sRGB Color Space Profile.icm` i `RSWOP.icm`). Auto Color Management jest „supported”, ale niewłączony.

Wnioski i rekomendacje:

- **Nasycenie.** [W] Prymarne obu monitorów leżą blisko DCI-P3 (P3: R 0,680/0,320, G 0,265/0,690, B 0,150/0,060), a materiał to BT.709. Bez zarządzania kolorem mpv wysyła wartości BT.709 wprost na panel szerokogamutowy, więc kolory są **przesycone**, chyba że monitor jest w trybie sRGB (nie da się tego odczytać z systemu). Opcje, od najprostszej:
  - tryb sRGB w OSD monitora;
  - `target-prim=display-p3` w mpv (przybliżenie, bo G monitora 0,657 ≠ 0,690);
  - profil ICC z kolorymetru i `icc-profile-auto` [F12].

  To jest realna „korekta nasycenia”. Decyzja należy do właściciela, bo część osób woli żywszy obraz.
- **Głębia wyjścia.** [F] `--dither-depth=auto` wykrywa głębię na d3d11, a `--d3d11-output-format=auto` wybiera `rgb10_a2`, gdy pulpit ma 10 bit [F12]. Dziś pulpit ma 8 bit. [W] Źródło jest 10-bit HEVC, a 8-bit z ditheringiem (domyślny `fruit`) daje obraz praktycznie bez bandingu, więc przejście na 10 bpc w panelu NVIDIA to mały zysk. [?] Czy M27Q przy 170 Hz w ogóle oferuje 10 bpc, zależy od łącza: właściciel sprawdzi w panelu NVIDIA. `--dither=error-diffusion` wymaga compute shadera i pamięci zależnej od wysokości okna [F12]; przy 8-bit wyjściu zysk jest kosmetyczny, nie polecam.
- **Deband.** [F] mpv: „w praktyce prawie zawsze poprawa”, kosztem lekkiego zmiękczenia detalu. Domyślnie iterations 1, threshold 48, range 16, grain 32 [F12]. PlayKit ma mocniejszy preset `DeBand+` (3/42/12/24) [F7]. [W] Zostaje lokalny profil `deband_bitrate` (≤3000 kb/s); plik testowy ma 2027 kb/s, więc deband się na nim włącza.
- **HDR → SDR.** [F] W `gpu-next` domyślne `tone-mapping=auto` to `spline`, w `gpu` to `bt.2390` [F12]. [W] Materiał AniShift to SDR BT.709 (plik testowy: bt709/tv). Monitory mają ok. 420–490 nit, czyli klasę HDR400, więc HDR passthrough (`target-colorspace-hint`, tylko `gpu-next`) da niewiele. Zostaje pulpit SDR i tone mapping dla rzadkich źródeł HDR (lokalny profil `HDR_generic`).
- **Wersja mpv.** [F] Lokalnie jest `mpv v0.36.0-711` z 2023-11-02 z libplacebo v6.338. Od mpv 0.41.0 (2025-12-21) domyślnym VO jest `gpu-next` [F15]. Sprawę buildu prowadzi R2, ale opcje koloru wyżej zakładają `gpu-next`.

## 4. Łańcuch i budżet

Łańcuch w mpv: dekoder → `vf` (VapourSynth albo natywny filtr: interpolacja, ewentualnie upscale ML) → VO (`gpu-next`: deband, skalowanie, shadery GLSL, kolor, dithering) dla **każdej klatki wyjściowej** → ekran.

**Ile pracy wymaga cel** [E] (źródło 23,976 fps; inferencja RIFE na każdą klatkę wyjścia, która nie pokrywa się z klatką źródła):

| Prędkość | Cel na ekranie | Mnożnik | Klatki wyjścia/s | Inferencje RIFE/s |
|---|---|---|---|---|
| 1× | 85 | 3,55 | 85 | ≈61–85 |
| 1× | 170 | 7,09 | 170 | ≈146 |
| 2× | 85 | 1,77 | 85 | ≈73 |
| 2× | 170 | 3,55 | 170 | ≈122 |

Kluczowe: **koszt RIFE zależy od celu na ekranie, nie od prędkości.** Przy 170 fps i 2× roboty jest niemal tyle samo co przy 1×.

**Czas GPU na sekundę oglądania** (budżet ok. 700 ms/s, z 30% zapasu na render, napisy i system) [E]. Założenia: RIFE 1080p ok. 5–6 ms na inferencję (4,9 ms z 4090 [F2], ok. 6 ms wg R3 dla 5090), RIFE 1440p ok. 1,78× (proporcjonalnie do pikseli, założenie), upscale ML wg R3: Balanced ok. 5 ms, Performance ok. 3,4 ms.

| Wariant | Rachunek | ms/s | Ocena |
|---|---|---|---|
| 2×, cel 85, RIFE 1080p → upscale Performance każdej klatki | 73×5,5 + 85×3,4 | ≈690 | na granicy; **rekomendowany do pomiaru** |
| 2×, cel 85, RIFE 1080p → upscale Balanced | 73×5,5 + 85×5 | ≈830 | ponad budżet |
| 2×, cel 85, upscale Balanced 48/s → RIFE 1440p | 48×5 + 73×9,8 | ≈960 | ponad budżet |
| 2×, cel 170, RIFE 1080p, bez upscalingu ML (skaler GLSL) | 122×5,5 + 170×~1 | ≈840 | ponad budżet lub na granicy; tryb „max” tylko po pomiarze |
| 2×, upscale Balanced 48/s + SVP do 170 | 48×5 + SVP | ≈240 + mało | mieści się (SVP zmierzony: 244 kl./s w mpv) |
| 2×, cel 85, RIFE 1080p ×1,77 bez upscalingu ML | 73×5,5 + 85×~1 | ≈490 | mieści się |

Wnioski:

- [W] **Interpolacja → upscale** wygrywa przy małym mnożniku, bo RIFE liczy w 1080p (1,78× mniej pikseli niż 1440p). Przy dużym mnożniku każdy upscale mnoży się przez liczbę klatek wyjścia. **Upscale → interpolacja** płaci RIFE w 1440p. Przy 170 fps żadna kolejność z upscalem ML się nie mieści. Ten sam wniosek wyciągnął R3 z innych danych.
- [W] Przy wyjściu 96 fps (RIFE ×2 przy 2×) na 170 Hz kadencja jest nierówna (1,77 odświeżenia na klatkę). `display-resample` tego nie wyrówna, bo zmiana tempa o ok. 11% przekracza `video-sync-max-video-change` [F12], więc zostaje judder albo mieszanie `tscale`. **Cel 85 (połowa Hz) jest pod tym względem czysty.** Wariant C z R3 (RIFE ×2 → 96 fps) warto więc zamienić na mnożnik ułamkowy do 85.
- [W] Shadery GLSL w VO liczą się per klatka wyjściowa. Lokalny `saved-props.json` przywraca dziś 6 shaderów naraz (KrigBilateral, FSR EASU, Anime4K Restore CNN L, Anime4K GAN x2 M, nnedi3 nns128, FSRCNNX). Z interpolacją do 170 fps ten zestaw nie ma szans. Moja próba pomiaru tego zestawu przez ffmpeg `libplacebo` dała rozrzut ±50%, więc nie podaję liczby i odsyłam do pomiarów R3.
- [E] Na ekranie głównym 3440×1440 @ 200 Hz budżet jest gorszy: 34% więcej pikseli wyjścia, a cel „połowa Hz” to 100 fps.

## 5. Pomiary lokalne

Wszystko bez okien, bez instalacji i bez zmian w `C:\Users\MattyMroz\Videos\mpv`. Skrypty i klatki leżały w katalogu tymczasowym sesji.

**Konfiguracja dziś** [F]:

- `mpv.conf`:
  - aktywne: `video-sync=display-resample`, `video-sync-max-video-change=5`, `interpolation=yes`, `tscale=linear`, `hwdec=auto-copy`, `scale=spline36`, `gamut-mapping-mode=clip`;
  - zakomentowane: `dither-depth`, `dither=error-diffusion`, `deband`, `target-prim=display-p3`, `icc-profile-auto`, `vo=gpu-next`.
- `profiles.conf`:
  - `[vsync_auto]` (`display_fps>122 or container_fps>32` → `interpolation=no`, `video-sync=audio`), czyli **na obu monitorach interpolacja mpv jest wyłączona**;
  - `[deband_bitrate]` (≤3000 kb/s → `deband=yes`);
  - `[HDR_generic]`, `[HDR_DolbyVision]` (`vo=gpu-next`, `tone-mapping=st2094-40`).
- Skróty w `input_uosc.conf`:
  - `~` czyści `vf`;
  - `! @ # $` uruchamiają `mvtools_x2/60/120/170`;
  - `% ^ & *` uruchamiają `memc_svp_x2/60/120/170`;
  - `( ) _` uruchamiają `rife_480p/720p/1080p_x2`.

  Skryptów `MEMC_*_NEW/old.vpy` nic nie podpina.
- Skrypty RIFE:
  - wszystkie używają `core.rife.RIFE(model=9)` (= v4.0), `SCDetect(0.15)`, konwersji do RGBS (float32) i `gpu_thread=8`;
  - `rife_2x.vpy` wymusza wyjście `YUV420P8`, co przy źródle 10-bit grozi bandingiem;
  - wszystkie odmawiają pracy powyżej 32 fps źródła (wyjątek: `rife_480p` do 64).
- SVP: `memc_svp_*` wołają `k7sfunc.SVP_PRO` (k7sfunc 0.1.23) ze stałym celem 60/120/170 (×1000/1001).
- Wtyczki VS (R65, Python 3.11): `RIFE.dll` (modele 0–9), `mvtools.dll` + `libmvtools.dll`, `svpflow1/2_vs64.dll`, `MiscFilters`, `VMAF`. **Brak vs-mlrt/TensorRT i brak filtra źródłowego** (lsmas/ffms2/bestsource).

**Uprząż:** 72 klatki z pliku testowego od 300 s. Klatki zrzucono przez `ffmpeg -ss 300 … -frames:v 72 -f rawvideo -pix_fmt yuv420p10le` i wczytano do RAM. Źródłem jest `std.ModifyFrame` w pętli (480 kl./s, więc nie ogranicza). Wynik szedł przez `VSPipe.exe -c y4m -a variant=… bench.vpy --`.

| VSPipe, 1080p 10-bit, 480 klatek wejścia | Klatki wyjścia/s |
|---|---|
| tylko źródło | 480 |
| SCDetect + YUV→RGBS→YUV (bez RIFE) | 218 |
| RIFE model 9 (v4.0), ×2, `gpu_thread=8` | 107,1 (przy 960 klatkach wejścia 117,7) |
| jw., `gpu_thread=2` (domyślne k7sfunc) | 87,6 |
| jw., ×7/2 (3,5) | 90,0 |
| jw., wejście zmniejszone do 720p, ×2 | 219,6 |
| `model_path=rife-v4`, ×2 | 114,2 |
| `model_path=rife-v4_ensembleFalse_fastTrue`, ×2 | 109,6 |
| `model_path=rife-v4.6_…` / `rife-v4.8_…` | błąd: `layer MemoryData not exists or registered` |
| mvtools BlockFPS (jak `mvtools_170.vpy`), cel 170 / 85 | 190,5 / 150,3 |
| SVP_PRO, cel 170 / 85 / 85 NVOF | 442 / 322 / 227 |

GPU podczas RIFE 1080p ×2 (`nvidia-smi -lms 1000`): obciążenie 4–59% (zwykle 30–50%), 170–180 W, 2,9 GHz, 7,4 GB VRAM. Karta czeka na CPU.

**mpv bez okna**, komenda: `mpv.com --no-config --vo=null --audio=no --untimed --hwdec=auto-copy --start=300 --end=340 --vf=vapoursynth=vs/<skrypt>` (40 s treści = 959 klatek źródła):

| Skrypt | Czas | Klatki wyjścia | Klatki/s | Potrzeba przy 1× / 2× |
|---|---|---|---|---|
| bez filtra | 3,7 s | 959 | ~260 (dekodowanie) | — |
| `rife_std.vpy` (1080p ×2) | 27,4 / 29,0 / 32,1 s | 1918 | **60–70** | 48 / **96** |
| `rife_720p_x2.vpy` | 20,3 s | 1918 | **95** | 48 / 96 |
| `memc_svp_170.vpy` | 27,8 s | 6793 | **244** | 170 / 340* |
| `mvtools_170.vpy` | 50,8 s | 6793 | **134** | **170** / 340* |

\* Stały cel 170 w czasie treści przy 2× oznacza 340 klatek/s.

Start filtra (komenda jw., `--end=300.5`): bez filtra 0,84 s, RIFE 3,32 s, SVP 2,03 s, mvtools 2,68 s. To przybliżony koszt każdego seeku, bo mpv przeładowuje skrypt [F14].

Odczyty monitora i koloru z §3: Python `ctypes` (DXGI `CreateDXGIFactory1` → `IDXGIOutput6::GetDesc1`, `EnumDisplaySettingsW`, EDID z `HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY\…\Device Parameters\EDID`), PowerShell `WmiMonitorID`, `Win32_VideoController`, `HKLM\…\GraphicsDrivers\MonitorDataStore`. Wszystko bez okien.

**Plan pomiaru TensorRT (wymaga pobrania, dlatego niewykonany):**

1. Do osobnego katalogu pobrać pakiet z RIFE na TRT. Dwie drogi: fork AnimeJaNai 3.9.0 (patrz R3) albo `mpv-lazy-20260510-noVS` + `vsNV` (2,9 GB) [F7].
2. Ta sama uprząż VSPipe: RIFE 4.25-lite / 4.26 / 4.26-heavy / DRBA v2-lite przy 1080p dla ×2, ×1,77 (85 przy 2×) i ×3,55 (170 przy 2×). Zapisać inferencje/s, obciążenie GPU, czas budowy silnika i czas startu ze zbudowanym silnikiem.
3. mpv `--vo=null --untimed`, komenda jw., dla tych samych celów, osobno z upscalem R3. Pytanie kontrolne: czy ścieżka VS przy 170 kl./s nie zatyka się na CPU, tak jak dziś ncnn.
4. Odtwarzanie w oknie przez właściciela przy prędkości 1× i 2×: liczba porzuconych klatek (statystyki mpv `i`, `frame-drop-count`, `vo-delayed-frame-count`), czas seeku, ocena artefaktów na scenach akcji i przy napisach na ekranie.

## 6. Ryzyka

- **Ścieżka VS a CPU.** [F] Dziś RIFE ncnn i upscaling przez VS (R3) dławią się na CPU przy 60–80 kl./s. Jeśli vs-mlrt w mpv też się zatnie, cel 170 z RIFE odpada niezależnie od GPU. Najmocniejszy kontrargument wobec 170 fps; rozstrzyga pomiar z §5.
- **Nieznane możliwości RIFE w forku AnimeJaNai** (mnożnik ułamkowy, modele). Gdy brak mnożnika ułamkowego, cel 85 przy 2× wymaga vs-mlrt albo zmiany odświeżania ekranu.
- **Artefakty RIFE na anime.** [W] Klatki rysowane na dwójki/trójki, szybkie cięcia, efekty i tekst na ekranie: część scen będzie „falować”. DRBA celuje w ten problem [F6], ale nie ma niezależnej oceny.
- **Licencja svpflow2.** [F] Zamknięta biblioteka; wiki wymaga SVP Managera. Lokalna wersja działa bez niego, ale nowsze mogą rysować czerwoną ramkę [F9]. Prawo do dystrybucji w PlayShift: [?].
- **Seek.** Przeładowanie skryptu przy każdym seeku: 1–3 s dziś, z TRT nieznane.
- **Dwa monitory.** Ekran główny ma 200 Hz i 3440×1440, a nie 170 Hz. Gdy okno trafi na niego, cele i budżet są inne. `display_fps` w skrypcie nie reaguje na zmianę monitora w trakcie (`display_res` „will not respond to monitor changes”) [F14].
- **Pomiary bez renderu.** `--vo=null` pomija koszt VO i napisów, więc realne zapasy są mniejsze.

## 7. Pytania do właściciela

1. Na którym monitorze oglądasz: M27Q 2560×1440 @ 170 Hz (dziś ekran drugi) czy G34WQC2 3440×1440 @ 200 Hz (ekran główny)?
2. Czy cel **85 fps** (równa kadencja, ok. połowa kosztu, miejsce na upscale) może być domyślny, a 170 fps trybem „max” bez upscalingu ML?
3. Kolory: czy monitor jest w trybie sRGB? Wolisz obecny żywy obraz czy wierne BT.709 (mniej nasycone)?
4. Co znaczyła „zmiana ilości barw”: wyjście 10-bit, żywsze kolory, HDR, czy coś innego?
5. Prędkość: zawsze 2×, czy też przełączasz 1×/2×? Od tego zależy, czy filtr ma się sam przestawiać przy zmianie `speed`.
6. Co ważniejsze przy 2×: maksymalna płynność czy brak artefaktów (RIFE vs SVP vs bez interpolacji)?
7. Czy akceptujesz pobranie kilku GB (TensorRT) i jednorazowe budowanie silnika przez kilka minut na każdą rozdzielczość?

## Źródła

- [F1] Practical-RIFE README (modele, „4.25 domyślnie”, daty 4.25/4.26): https://github.com/hzwer/Practical-RIFE (dostęp 2026-10-31)
- [F2] VSGAN-tensorrt-docker, tabela benchmarków (RTX 4090 / 7950X, TRT 10.9; wiersze 5090 bez RIFE): https://github.com/styler00dollar/VSGAN-tensorrt-docker (push 2026-06-22)
- [F3] vs-mlrt `scripts/vsmlrt.py`: `RIFEModel` (v4.0 … v4.26_heavy), `RIFE(multi: int | Fraction, video_player=…)`, wymóg detekcji scen: https://github.com/AmusementClub/vs-mlrt/blob/master/scripts/vsmlrt.py (master 2026-10-30); wiki RIFE (3090, v4.4, trt 2 streams 107,3 fps): https://github.com/AmusementClub/vs-mlrt/wiki/RIFE
- [F4] Wydania vs-mlrt v15.16 (2026-03-26) i v16.4.test1 (2026-10-30): https://github.com/AmusementClub/vs-mlrt/releases
- [F5] TensorRT 10.8.0 Release Notes (wsparcie Blackwell / GeForce 50): https://docs.nvidia.com/deeplearning/tensorrt/latest/getting-started/release-notes-10/10.8.0.html
- [F6] DRBA README: https://github.com/routineLife1/DRBA (push 2026-08-12); VS-DRBA: https://github.com/routineLife1/VS-DRBA (benchmark na 3070 laptop: RIFE 4.26 heavy 53 kl./s, DRBA 70 kl./s przy 1080p)
- [F7] mpv_PlayKit: `portable_config/vs/MEMC_RIFE_NV.vpy`, `MEMC_DRBA_NV.vpy`, `profiles.conf` (`DeBand+`), wydanie 20260510 (paczki noVS/vsNV): https://github.com/hooke007/mpv_PlayKit; K7sfunc `mod_memc.py` (`RIFE_NV`, `DRBA_HUB`, modele 46/4251/426/4262, `fractions.Fraction`): https://github.com/LumeCraft-Labs/K7sfunc (push 2026-05-07)
- [F8] GMFSS_Fortuna: https://github.com/98mxr/GMFSS_Fortuna; vs-gmfss_fortuna: https://github.com/HolyWu/vs-gmfss_fortuna
- [F9] SVP wiki, SVPflow (GPL svpflow1, zamknięty svpflow2, wymóg SVP Managera): https://www.svp-team.com/wiki/Manual:SVPflow (edycja 2019-09-29)
- [F10] SVP wiki, RIFE AI interpolation (TRT vs ncnn, tabela GPU, detekcja scen, budowa silnika): https://www.svp-team.com/wiki/RIFE_AI_interpolation
- [F11] SVP, cennik: https://www.svp-team.com/get/ (dostęp 2026-10-31)
- [F12] Manual mpv (master), `DOCS/man/options.rst`: `--tscale`, `--interpolation`, `--dither-depth`, `--dither`, `--d3d11-output-format`, `--deband*`, `--target-colorspace-hint`, `--icc-profile-auto`, `--video-sync-max-video-change`, `--tone-mapping`: https://github.com/mpv-player/mpv/blob/master/DOCS/man/options.rst
- [F13] Smooth Motion (RTX 50, gry DX11/DX12): https://wccftech.com/nvidia-adds-smooth-motion-a-driver-based-frame-generation-ai-model-for-rtx-50-gpus/amp/
- [F14] Manual mpv, `DOCS/man/vf.rst`, filtr `vapoursynth` (przeładowanie przy seeku, zmienne `container_fps`, `display_fps`, `display_res`, `user_data`): https://github.com/mpv-player/mpv/blob/master/DOCS/man/vf.rst
- [F15] mpv v0.41.0 release notes („gpu-next is now the default”): https://github.com/mpv-player/mpv/releases/tag/v0.41.0
- mpv issue #11122 (powód profilu `vsync_auto`): https://github.com/mpv-player/mpv/issues/11122
- AnimeJaNai, wydania 3.5.0 (RIFE przed upscalem), 3.8.0 (TRT 11.4 naprawia RIFE): https://github.com/the-database/mpv-upscale-2x_animejanai/releases
- R3 (`03-upscaling.md`) w tym katalogu: koszt upscalingu, ścieżka AnimeJaNai, liczba ~6 ms dla RIFE v4.14 (przejęta, niezweryfikowana przeze mnie).
