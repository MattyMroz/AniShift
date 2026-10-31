---
kind: outcome
status: draft
updated: 2026-10-31
plan: ../plans/01-engine-and-base.md
---

# Wynik etapu 01 (roboczy, przed K1)

Stan: fazy 0–6 planu wykonane, K1 przygotowany, ocena właściciela jeszcze nie zapisana. Werdykty G5 i G6 oraz
propozycja D3–D8 czekają na odpowiedzi z K1. Wszystkie pliki eksperymentu leżą w
`C:\Users\MattyMroz\tmp\playshift\` (dalej EXP); logi w `EXP\logs\`.

## 1. Co sprawdzono i na czym

- Sprzęt jak w specyfikacji: RTX 5090, sterownik 610.88. Przed pomiarami GPU było zajęte w 2% (3,4 GB VRAM);
  działały NVIDIA Broadcast i Wallpaper Engine.
- **S1:** `workspace\ready\[Erai-raws] Cyberpunk - Edgerunners 2 - 01 [1080p NF WEB-DL HEVC EAC3]...mkv`
  (HEVC 10-bit, 23,976 fps), od 300 s. Tylko odczyt.
- **S3:** `workspace\ready\The.Apothecary.Diaries.S03E01...mkv` (H.264 1080p) z napisami `.pl.ass` i lektorem `.eac3`.
- **S2 nie istnieje.** W `workspace` i `D:\Media\Anime` sprawdziłem ffprobe wszystkie 209 plików: nie ma żadnego
  anime poniżej 1080p, jest tylko klip testowy 160×120. Przypadek 720p zastępuje wariant M5 (zmniejszenie do 720p +
  2×).
- **Zakłócenia pomiarów.** W czasie pomiarów inne programy obciążały komputer: `pytest -n auto` AniShift i
  MangaShift, ffmpeg tessera-probe, ElevenDownloaderPro. CPU dochodził do 100%, GPU do 90% bez moich procesów.
  Pomiary RIFE (synchroniczne z CPU) mają przez to duży rozrzut. Do median biorę pierwszą, spokojniejszą serię;
  powtórka jest w tabeli tylko dla porównania.

### Pobrane pliki i sumy (wszystkie zgodne z polem `digest` wydań)

| Plik | SHA256 |
|---|---|
| mpv-AnimeJaNai 3.9.0 `mpv-upscale-2x_animejanai-full-package-3.9.0.7z.001` | `6080472d…bc001` |
| `component-trt-runtime.7z` (TensorRT 11.4.0.106) | `ef0249ce…dfe` |
| `component-trt-sm120.7z` | `38793df1…220` |
| `component-rife.7z` | `2f0262bc…d81` |
| PlayKit 20260510 `mpv-lazy-20260510-noVS.7z` | `cd837331…2c855` |
| `mpv-lazy-20260510-vsNV.7z.001` / `.002` (zgoda właściciela 2026-10-31) | `f877973f…ddda` / `1c7303d7…2007` |
| `mpv-lazy-20260510.exe` (paczka 7z SFX; nieuruchamiana, niepotrzebna, usunięta) | `f03e288d…fef4` |

Pełne sumy: `EXP\logs\sha256.txt`. Archiwa po rozpakowaniu usunąłem. Instalatorów nie uruchamiałem.

## 2. Silnik AnimeJaNai: odpowiedzi z kodu i z uruchomienia

| Pytanie | Odpowiedź | Dowód |
|---|---|---|
| Wersja forka | mpv v0.41.0-dev-gb4f9f5bfe (build 2026-10-24), libplacebo v7.387, FFmpeg N-128018 | `logs\cap-version.txt` |
| Filtry i opcje | jest `animejanai`, `vapoursynth`, `d3d11vpp` (z `scaling-mode=nvidia`), `gpu`; są `--register`, `--autocreate-playlist`, `--save-watch-history`, `--clipboard-backends` | `logs\cap-*.txt` |
| Samodzielny `mpv.exe` bez mpv.net | działa (`mpv.com --version`, smoke `lavfi` z kodem 0) | log z fazy 3 |
| Mnożnik ułamkowy RIFE | **jest**: `chain_N_rife_factor_numerator/denominator`, ułamek skracany, najwyżej 8× | `src/aji_conf.cpp`, `vf_animejanai.c` (~l. 592); w logu „RIFE active: 39/22” |
| Docelowe fps zamiast mnożnika | brak; cel liczy się jako mnożnik i ustawia slotem | jw. |
| Zmiana w trakcie odtwarzania | **jest**: `vf-command aji slot <N>`, slot 0 = obejście bez przebudowy łańcucha | `vf_animejanai.c` (~l. 1869) |
| Wybór łańcucha | po rozdzielczości i nominalnym fps źródła, nie po prędkości; prędkość musi ustawić skrypt | `vf_animejanai.c` (~l. 1426) |
| Biblioteki w podkatalogu (P8) | **działa**: `aji.dll` ładuje zależności TensorRT z własnego katalogu (`LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR`); układ `layout\lib\aji\` sprawdzony | `logs\runs\P8-*.log` |
| Gdzie są silniki TensorRT | obok modeli ONNX (`model-dir`, `rife-model-dir`) plus `.build.log` i `.timing.cache.lock`; ustawić osobno się nie da | listing `layout\lib\models`, `lib\rife` |
| Budowa silnika | zawsze w tle (`trtexec`), a do końca budowy obraz idzie bez filtra. Zamknięcie mpv kończy też `trtexec` (żaden proces nie zostaje) i usuwa niedokończony silnik | `logs\runs\P8-slot1-cold.log`, kontrola procesów |
| Licencje | repo i modele AJN: CC BY-NC-SA 4.0; `animejanai-inference` bez pliku licencji; TensorRT/CUDA z własnymi licencjami w paczce | R3, `ajn\animejanai\inference\*LICENSE*` |

Odczytane źródła: `logs\src\` (`vf_animejanai.c` z `the-database/mpv` master; `aji_conf.cpp`, `aji_trt.cpp`, `aji.h`
z `animejanai-inference` main, odczyt 2026-10-31).

## 3. Pomiary bez okna

**Metoda.** `mpv.com --no-config --vo=null --audio=no --untimed --hwdec=nvdec --start=300 --frames=2000`, filtr
AJN z `layout\` i na końcu łańcucha `scale_cuda=2560:1440:nv12`. Wynik to klatki wyjścia na sekundę od pierwszej
klatki do końca. Bez `scale_cuda` `vo=null` kopiuje każdą klatkę 4K w formacie 4:4:4 16-bit do pamięci RAM i
wszystko kończy się na ok. 57 kl./s; to wada samej metody, nie silnika (`logs\runs\M1-s1-w1.log`: „HW-downloading
from cuda”). Skalowanie na GPU zastępuje skalowanie, które w oknie i tak robi VO. Próg z planu §11.2: 1,3 × cel.

| Id | Wariant (S1) | kl./s, mediana (3 przebiegi) | Przebiegi | Powtórka przy obciążonym CPU |
|---|---|---|---|---|
| M0 | samo dekodowanie | 780 | 876 / 780 / 698 | — |
| M1 | Balanced 2× | **150** | 150 / 150 / 147 | — |
| M2 | Performance 2× | **268** | 274 / 268 / 244 | — |
| M3 | Balanced Sharp 2× | 134 | 134 / 135 / 134 | — |
| M4 | 4× Performance+Performance | 47 | 47 / 49 / 46 | — |
| M5 | zmniejszenie do 720p + Balanced 2× | 338 | 336 / 338 / 341 | — |
| M6 | RIFE (v4.14) ×2, bez upscalingu | 267 | 267 / 252 / 289 | 262–302 |
| M6 | RIFE 39/22 (85 kl./s przy 2×) | 182 | 187 / 182 / 171 | 160–183 |
| M6 | RIFE 48/23 (100 kl./s przy 2×) | 176 | 184 / 170 / 176 | 71–158 |
| M6 | RIFE 39/11 (170 przy 2× albo 85 przy 1×) | 174 | 180 / 174 / 173 | 150–160 |
| M6 | RIFE 25/6 (200 przy 2× albo 100 przy 1×) | 172 | 172 / 176 / 147 | 124–158 |
| M7 | RIFE 39/22 → Balanced (85 przy 2×) | 58 | 58 / 56 / 69 | 33–69 |
| M7 | RIFE 39/22 → Performance (85 przy 2×) | **107** | 94 / 108 / 107 | 84–102 |
| M7 | RIFE 48/23 → Balanced (100 przy 2×) | 80 | 79 / 81 / 80 | 36–68 |
| M7 | RIFE 48/23 → Performance (100 przy 2×) | **105** | 105 / 105 / 106 | 29–93 |
| M8 | RIFE 39/11 → Balanced (85 przy 1×) | 77 | 78 / 77 / 72 | — |
| M8 | RIFE 39/11 → Performance (85 przy 1×) | 76 | 96 / 76 / 69 | — |
| M8 | RIFE 25/6 → Balanced (100 przy 1×) | 76 | 63 / 76 / 77 | — |
| M8 | RIFE 25/6 → Performance (100 przy 1×) | 104 | 105 / 103 / 104 | — |

Surowe wiersze: `EXP\logs\results.csv`, logi: `EXP\logs\runs\`.

**M9, start filtra.**

- Budowa silnika przy pierwszym odtworzeniu (zimny start): Balanced 1080p 20,6 s; Performance 25,7 s; 4× (drugi stopień, wejście 2160p) 31 s;
  wejście 720p 29,5 s; RIFE 4.14 przy 1920×1088 57,4 s.
- Ze zbudowanym silnikiem (ciepły start) pierwsza klatka pojawia się po 0,3–0,4 s (RIFE do 1,0 s).

**M10, przełączanie i przewijanie** (odtwarzanie w czasie rzeczywistym przy 2×, `logs\runs\M10-*.log`):

- zmiana slotu w trakcie trwa 30–130 ms (z RIFE i bez);
- od komendy przewinięcia o 60 s do pierwszej klatki mija 70–90 ms.

**M11, obciążenie karty.**

- VRAM: Balanced 5,9 GB, 4× 9,0 GB, RIFE + upscaling 6,2–6,7 GB (cała karta, razem z innymi programami).
- GPU: upscaling 98–100%, łańcuchy z RIFE 84–89% (CPU synchronizuje każdą parę klatek, `depth 1` w logu).

### PlayKit (mpv-lazy 20260510 + vsNV), jedno uruchomienie na wariant (prośba właściciela)

Uruchamiany przez własny `mpv.exe` PlayKit z `--no-config` i `hwdec=auto-copy` (VapourSynth potrzebuje klatek w RAM),
cel 100 kl./s przy 2× (mnożnik 48/23), ok. 20 s treści, bez upscalingu. Skrypty to kopie `MEMC_RIFE_NV.vpy` i
`MEMC_DRBA_NV.vpy` ze zmienionym tylko mnożnikiem (`EXP\probe\pkvs\`).

| Wariant | Budowa silnika (pierwsze uruchomienie) | kl./s (ciepły) | Dla porównania AJN |
|---|---|---|---|
| RIFE 4.6 TensorRT (vs-mlrt, `RIFE_NV`) | 95 s | **110** | RIFE 4.14 48/23 sam: 176 |
| DRBA v2 lite TensorRT (`DRBA_NV`) | 48 s | **78** (nie nadąża do 100) | — |

**Inne modele RIFE w AJN** (bez nowego pobierania, modele z `component-rife.7z`). Po jednym przebiegu,
mnożnik 48/23, przy CPU obciążonym w 100% przez inne programy, więc liczby porównują modele tylko między sobą:

| Model | Budowa silnika | kl./s | Bieg odniesienia w tych samych warunkach |
|---|---|---|---|
| RIFE 4.22-lite | 56 s | 88 | RIFE 4.14 (domyślny AJN): 99 |
| RIFE 4.25 | 70 s | 96 | jw. |

W `vsNV` z PlayKit są tylko RIFE 4.6, 4.25-lite, 4.26 i 4.26-heavy; 4.22-lite i pełnego 4.25 tam nie ma.

- VapourSynth R73 jest w paczce przenośny (`VSScript.dll` i `portable.vs` obok `mpv.exe`). `VSSCRIPT_PATH` nie
  był potrzebny.
- Silniki vs-mlrt zapisują się obok modeli w `pk\lazy\...\vs-plugins\models\`.

**Co PlayKit wnosi wobec OLD.** OLD ma RIFE ncnn z modelem v4.0 (60–70 kl./s, R4), SVP i MVTools. PlayKit dokłada:

- RIFE na TensorRT z modelami 4.6, 4.25-lite, 4.26 i 4.26-heavy;
- DRBA, interpolację zaprojektowaną pod anime;
- warianty DirectML (`RIFE_DML`, `DRBA_DML`);
- nowe k7sfunc 1.8.1 i VapourSynth R73 z Pythonem 3.14;
- upscaling przez vs-mlrt (`MIX_UAI_NV_TRT`, `SR_ARTCNN_NV`) i odszumianie (`NR_BM3D_NV`).

Upscalingu PlayKit nie mierzyłem: to ta sama ścieżka VapourSynth, którą R3 ocenił na ok. 79 kl./s przy 1080p.
Nie mierzyłem też SVP z PlayKit, bo w `vsNV` nie ma `svpflow`.

## 4. Bramki

| Bramka | Werdykt | Uzasadnienie |
|---|---|---|
| G1 upscaling | **PASS** | Balanced 150 kl./s ≥ 63 |
| G2 RIFE do połowy odświeżania przy 2× | **FAIL na progu 1,3×, na granicy bez zapasu** | Najlepszy RIFE → Performance: 107 kl./s przy celu 85 (próg 111) i 105 przy celu 100 (próg 130). RIFE z Balanced nie osiąga celu (58 i 80). Sam RIFE bez upscalingu AI spełnia oba cele z zapasem (182 i 176). Pomiar bez okna pomija koszt renderowania, więc rozstrzyga licznik klatek w K1 (warianty 6 i 7). |
| G3 sterowanie | **PASS** | mnożnik ułamkowy, zmiana slotu w trakcie (30–130 ms), seek 70–90 ms |
| G4 izolacja | **PASS z zastrzeżeniem D8** | nic nie wymaga instalacji systemowej; ślady tylko w kategorii D8 (§6) |
| G5 okno | czeka na K1 | |
| G6 obraz | czeka na K1 | |

Reguła §11.5 przy G2 FAIL z powodu wydajności daje propozycję do D3: cel połowy odświeżania tylko z Performance
albo bez upscalingu AI. Ostateczną propozycję D3–D8 napiszę po K1.

## 5. Zrzuty do porównania (bez okna)

Strona: `EXP\shots\index.html` (lokalna, bez sieci). Ma 6 klatek (4 z S1 i 2 z S3 z napisami AniShift), na każdej 7
wariantów w 2560×1440, porównanie obok siebie albo przełączanie A/B w tym samym miejscu.

**Metoda.**

- Kopia klatki z filtra: `vo=image`, potem `vf=gpu=w=2560:h=1440` z profilem `high-quality`. AJN przed `vf=gpu`
  wymaga jawnego `hwdownload`; bez niego wychodziły czarne klatki, które wyrzuciłem.
- „Obecny wygląd” jest emulacją: mpv z OLD (0.36) nie ma `vf=gpu`, więc ten sam renderer `vo_gpu` w forku dostaje
  6 shaderów OLD (tylko odczyt) i jego skalery. Sprawdziłem, że `vf=gpu` stosuje `--glsl-shaders`: sam
  Restore CNN L zmienia 2,8% pikseli.
- RTX VSR nie da się zrzucić bez okna (`d3d11vpp` nie startuje bez urządzenia D3D11 z VO), więc jest tylko w K1.

**Dlaczego warianty wyglądają prawie tak samo.** Filtr działał; logi mają „Configured slot 1: 1920x1080 ->
3840x2160”, silnik i graf CUDA. Na czystym źródle 1080p WEB AnimeJaNai poprawia tylko krawędzie linii (cieńsze,
ostrzejsze). Na wyjściu 4K, przed zmniejszeniem, różnica wobec Lanczosa wynosi średnio 0,5–1,1 na 255, a 0,3–2,6%
pikseli zmienia się o więcej niż 8. Po zmniejszeniu do 1440p różnica w większości ginie. Wycinki 4K z wzmocnioną
różnicą: `EXP\tmp\check-crop2.png` (S3) i `EXP\tmp\check-crop.png` (S1 9:00 ma w kadrze efekt linii CRT, więc się
do tego nie nadaje).

Różnica każdego wariantu wobec „bez upscalera” w 1440p, w formacie średnia/255 / % pikseli z różnicą > 8:

| Klatka | OLD | Balanced | Sharp | Performance | 4× | 720p + 2× |
|---|---|---|---|---|---|---|
| s1 3:00 ciemna scena | 0,45 / 0,79% | 0,64 / 0,83% | 0,75 / 1,11% | 0,57 / 0,76% | 0,71 / 1,01% | 0,75 / 0,93% |
| s1 6:45 postać, jasne tło | 0,33 / 0,15% | 0,57 / 0,28% | 0,61 / 0,51% | 0,49 / 0,20% | 0,66 / 0,28% | 0,85 / 0,97% |
| s1 9:00 twarz | 0,69 / 0,10% | 0,82 / 0,00% | 0,98 / 0,06% | 0,67 / 0,00% | 1,01 / 0,00% | 1,29 / 0,08% |
| s1 16:30 linie, niebo | 0,46 / 0,32% | 0,66 / 0,28% | 0,75 / 0,72% | 0,60 / 0,20% | 0,82 / 0,30% | 1,25 / 3,18% |
| s3 4:54 napisy | 0,48 / 1,14% | 0,76 / 1,38% | 0,91 / 2,03% | 0,78 / 1,30% | 1,14 / 1,97% | 0,75 / 1,22% |
| s3 5:14 napisy | 0,55 / 0,90% | 0,83 / 0,73% | 0,94 / 1,33% | 0,80 / 0,69% | 1,18 / 1,17% | 0,90 / 0,71% |

Wniosek (wymaga potwierdzenia przez właściciela w K1): na odcinkach 1080p dobrej jakości, oglądanych na ekranie
1440p, żaden upscaler nie daje dużej, widocznej zmiany. Największa różnica dotyczy krawędzi linii (Sharp) i
zmiękczenia przy 720p + 2×. Materiału SD lub 720p, na którym upscaler mógłby pokazać więcej, w bibliotekach
właściciela nie ma.

## 6. Mapa śladów w systemie

Snapshoty `EXP\logs\snap-t0.json` (przed pobraniem), `snap-t1.json` (po pomiarach AJN), `snap-t1b`/`snap-t1c`
(przed i po PlayKit).

| Ślad | Skąd | Kategoria |
|---|---|---|
| `%APPDATA%\NVIDIA\ComputeCache`: +301 plików, +67 MB | cache JIT CUDA (`scale_cuda`, TensorRT, CUDA w aji) | D8, sterownik |
| `%LOCALAPPDATA%\NVIDIA\DXCache`, `GLCache` | cache shaderów sterownika; zmieniają je też inne programy | D8, sterownik |
| `HKCU\...\Shell\MuiCache`: 2 wartości dla `pk\lazy\mpv-lazy\mpv.exe` | Windows zapisuje je przy uruchomieniu programu przez powłokę (`cmd`). Dwuklik `.cmd` w K1 doda takie wpisy dla każdego `mpv.exe` | D8, ślad uruchomienia |
| `%LOCALAPPDATA%\CrashDumps\ffmpeg.exe.61724.dmp` (11:30) | awaria ffmpeg, nieprzypisana: ffmpeg uruchamiałem ja (wycinki klatek) i równolegle inny agent (tessera-probe) | do wyjaśnienia |
| `%TEMP%\aji\paths.txt` | istniał przed T0 (wcześniejszy research) | niezwiązany |

- Bez zmian: zmienne środowiskowe użytkownika i maszyny, usługi, zadania harmonogramu, autostart (`Run`, `RunOnce`,
  folder Autostart), klucze `HKCU\Software` i `HKCU\Software\Classes` z `mpv`/`animejanai`, `%APPDATA%\mpv`.
- Żaden mój proces nie działa po pomiarach (sprawdzane po każdej fazie).
- **OLD bez zmian:** SHA256 kluczowych plików jak w `logs\old-baseline.txt`; cały katalog (1637 plików, rozmiary i
  daty) identyczny przed i po (`logs\old-tree-before-shots.txt`).

## 7. K1: zestaw dla właściciela

Katalog `EXP\k1\`. Instrukcja po polsku jest w `CZYTAJ.txt`. Każdy plik otwiera ten sam fragment S1 (od 5:00, 2×) z
nazwą wariantu na ekranie.

| Plik | Wariant | Sprawdzony bez okna |
|---|---|---|
| `1-obecny.cmd` | `mpv.exe` z OLD, `--no-config` + 6 shaderów i skalery OLD; nic nie zapisuje w OLD | tak |
| `2-bez-upscalera.cmd` | fork AJN, filtr w trybie obejścia | tak |
| `3-ajn-balanced.cmd` | AJN Balanced | tak |
| `4-ajn-performance.cmd` | AJN Performance | tak |
| `5-rtx-vsr.cmd` | `d3d11vpp` `scaling-mode=nvidia`; wymaga włączenia VSR w NVIDIA App | nie (bez okna niemożliwe) |
| `6-rife-85fps-monitor-170Hz.cmd` | AJN RIFE 39/22 → Performance | tak |
| `7-rife-100fps-monitor-200Hz.cmd` | AJN RIFE 48/23 → Performance | tak |
| `8-playkit-rife-100fps.cmd` | PlayKit RIFE 4.6 TensorRT 48/23 | tak |
| `9-smooth-motion.cmd` | fork, `d3d11`, bez filtrów i bez interpolacji mpv, `video-sync=audio`, pełny ekran; Smooth Motion włącza właściciel w profilu programu NVIDIA App | tylko parsowanie opcji |
| `10-playkit-drba-100fps.cmd` | PlayKit DRBA 48/23 | tak |
| `11-…`, `12-…` | AJN RIFE 4.22-lite bez upscalingu: 48/23 (200 Hz), 39/22 (170 Hz) | tak |
| `13-…`, `14-…` | AJN RIFE 4.25 bez upscalingu: 48/23 (200 Hz), 39/22 (170 Hz) | tak |
| `15-tekst-w-ruchu-rife425-100fps.cmd` | czołówka od 1:20 z wtopionymi napisami; ocena smug na tekście | tak |

- W wariantach 2–4, 6 i 7 działają też klawisze eksperymentu (`layout\portable_config\input.conf`): `Ctrl+1`…`Ctrl+6`
  wybierają upscaler, `~` `!` `@` `#` interpolację (`@`/`#` liczą cel z `display-fps` i prędkości),
  `\`/`BS` ustawiają prędkość, `Ctrl+7` włącza `target-prim=display-p3`, `Ctrl+8` VSR, a `Ctrl+s` robi zrzut.
- Logi walidacji: `EXP\logs\k1-validate\`.
- Ustawień sterownika ani panelu NVIDIA nie zmieniałem. VSR i Smooth Motion włącza właściciel według
  `CZYTAJ.txt` i po teście je wyłącza.

## 8. Odkrycia i odchylenia od planu

- `--sub-ass-vsfilter-blur-compat` z `mpv.conf` OLD **nie istnieje w nowym mpv**; to błąd startu, który etap 03
  musi uwzględnić. W nowym mpv `sub-border-size` i `sub-shadow-color` są już tylko aliasami.
- Napisy AniShift `.pl.ass` mają własny styl z fontem Trebuchet MS. `sub-font` (Officina) działa więc tylko dla
  napisów innych niż ASS, w OLD i w forku tak samo. To dotyczy I4 i restyle po stronie AniShift.
- Z oknem (K1) ustawiłem `gpu-api=vulkan` jak AJN. Jeśli okno się nie otworzy (issue #200), zapasem jest
  `--gpu-api=d3d11`.
- Pomiary bez okna wymagały ujścia na GPU (`scale_cuda`); bez niego wychodzi fałszywy sufit ok. 57 kl./s (§3).
- Właściciel chciał minimum pomiarów, dlatego PlayKit ma po jednym przebiegu, tylko cel 100 kl./s, a druga seria
  RIFE została przerwana.
- Slot dla 200 Hz przy 1× wymaga mnożnika 8,34, a AJN przyjmuje najwyżej 8×; `switch.lua` wybiera wtedy najbliższy
  obsługiwany mnożnik i wyświetla ostrzeżenie.

## 9. Czego nie sprawdzono

- Wszystko z oknem: G5, G6, liczniki gubionych klatek, wygląd VSR, Smooth Motion i napisów w ruchu (K1).
- Materiał 720p, SD i DVD (nie ma go w bibliotekach).
- Upscaling i SVP z PlayKit, RIFE 4.26 w AJN. Główne pomiary robiłem na domyślnym RIFE 4.14; 4.22-lite i 4.25
  mają tylko po jednym przebiegu przy obciążonym CPU.
- Pełne 3 powtórzenia dla PlayKit i nowych modeli RIFE (pominięte na prośbę właściciela).
- Silnik RIFE dla wariantu „720p + 2× z RIFE” (sloty 161–166 w K1) nie jest zbudowany; przy pierwszym użyciu
  zbuduje się w ok. 60 s, a do tego czasu obraz idzie bez interpolacji.
- Ślady po K1 (snapshot T2) i po usunięciu EXP (T3).

## 10. Propozycje zmian w dokumentach (do decyzji orkiestratora)

- Plan §11.3: dopisać `scale_cuda` na końcu łańcucha w pomiarach bez okna i nawiasy `[...]` wokół ścieżek z dwukropkiem.
- Plan §12.2: `[?] P8` rozstrzygnięte, `lib\aji\` działa. Silniki TensorRT zapisują się obok modeli
  (`lib\models\`, `lib\rife\`), więc te katalogi są danymi zmiennymi; inaczej niż `var\cache` w drzewie.
- Specyfikacja D8: dopisać `MuiCache` i `ComputeCache` jako znane ślady.
- Specyfikacja, sekcja „Obecny odtwarzacz”: usunięta opcja `sub-ass-vsfilter-blur-compat`.

## 11. Stan

- EXP: ok. 8 GB (`ajn`, `layout` z twardymi dowiązaniami, `pk\lazy`, `shots`, `logs`); archiwa usunięte.
  Usuwamy po K2 albo zostawiamy do etapu 04.
- OLD: bez zmian.
- Następny krok: K1 według `EXP\k1\CZYTAJ.txt`, potem werdykty G5 i G6, propozycja D3–D8 i snapshot T2.
