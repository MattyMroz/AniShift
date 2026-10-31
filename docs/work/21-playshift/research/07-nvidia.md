---
kind: research
id: playshift-r7-nvidia
date: 2026-10-31
subject: technologie NVIDIA (RTX VSR, RTX Video HDR, Optical Flow/FRUC, DLSS FG, Smooth Motion, Maxine) w mpv na Windows, RTX 5090
---

# R7: technologie NVIDIA do obrazu i interpolacji w mpv — co działa dziś, a co nie

Oznaczenia: **[F]** fakt ze źródłem, **[R]** relacja użytkowników, **[W]** wniosek z kilku faktów, **[?]** niepotwierdzone. Źródła sprawdzone 2026-10-31 (adresy w sekcji 7). Nic nie pobierano ani nie uruchamiano; jedyny odczyt lokalny to ciągi znaków w `C:\Users\MattyMroz\Videos\mpv\mpv.exe`.

## 1. Pytanie

Czy to, co NVIDIA znana jest z gier lub z przeglądarek (DLSS, DLSS Frame Generation / Multi Frame Generation, optical flow, RTX Video), da się użyć w mpv na Windows, żeby dostać lepsze klatki pośrednie i/lub lepszy upscaling niż obecni kandydaci (AnimeJaNai TensorRT, RIFE TensorRT, SVP, MVTools). Sprzęt: RTX 5090, sterownik 610.88, Windows 11, 3440×1440 @ 200 Hz i 2560×1440 @ 170 Hz, anime 1080p/720p 23,976 fps, prędkość zwykle 2×.

## 2. Odpowiedź w skrócie

1. **RTX Video Super Resolution działa w mpv dziś**, ale tylko w mpv nowszym niż lokalny. Filtr `--vf=d3d11vpp=scale=2:scaling-mode=nvidia` jest w mpv od v0.39.0 (2024-09-23) [F1][F2]. **Lokalny `mpv.exe` to `v0.36.0-711-g250429da` (commit z 2023-11-01) i nie zawiera ciągów `scaling-mode` ani `nvidia-true-hdr`** [F3][W: nie ma tej funkcji]. To tylko upscaler (nie interpoluje), więc jest alternatywą dla AnimeJaNai, nie dodatkiem. Jakość dla anime niezmierzona [?].
2. **RTX Video HDR (`nvidia-true-hdr`) istnieje**, ale tylko w mpv od v0.40.0 (2025-03-25) i konwertuje SDR→HDR [F4][F5]. Na monitorach SDR przy wyłączonym HDR w Windows nie ma sensu i nie działa poprawnie [F6]. Pomijamy.
3. **NVIDIA Optical Flow / NvOFFRUC nie ma gotowego wejścia do mpv.** Nie znalazłem żadnego działającego pluginu mpv ani VapourSynth opartego na FRUC. Biblioteka jest zamknięta (licencja „NVIDIA DesignWorks SDK License”), jej nieredystrybuowalność zablokowała filtr FFmpeg w 2023, a oficjalnie wspiera Turing, Ampere i Ada, o Blackwellu strony milczą [F7][F8][F9]. **Nowość:** FFmpeg ma w gałęzi master (2026-08-29) filtr `fruc_vulkan` na sprzęcie NVOFA przez Vulkan (RTX 30/40/50), ale to FFmpeg, nie mpv [F10][F11]. SVP wspiera „NVIDIA Optical Flow”, lecz to inny mechanizm (patrz 4.3).
4. **DLSS Frame Generation / MFG i DLSS Super Resolution są poza zasięgiem dla wideo.** Wymagają wektorów ruchu i bufora głębi z silnika renderującego oraz podpięcia pod `Present` swapchaina DX12 przez Streamline [F12]. Wideo ich nie ma. Nie znalazłem żadnego odtwarzacza, który by to robił [?: brak dowodu nieistnienia].
5. **Smooth Motion** to funkcja sterownika dla gier DX11/DX12 [F13]. Zgłoszeń ani testów z mpv nie znalazłem [?]. Odradzam testować: mpv i tak ma własne okno, a funkcja nie jest przeznaczona do wideo.
6. **Maxine VFX SDK** (Super Resolution, Artifact Reduction) to biblioteka dla programistów z instalatorem pobierającym modele z NGC; nie ma integracji z mpv [F14]. Nic z niej nie da się użyć w mpv bez pisania własnego filtru.

## 3. Ustalenia per technologia

### 3.1 RTX Video Super Resolution (VSR)

- **[F]** Opcja `scaling-mode` filtra `d3d11vpp` przyjmuje `standard` (domyślnie), `intel` i `nvidia`; „te tryby tylko włączają rozszerzenia, a działanie zależy od sprzętu i ustawień panelu sterownika” [F2].
- **[F]** Wprowadzone commitem `2848af5` („vf_d3d11vpp: add support for scaling”), zmergowane 2024-08-20 z PR #14698 (następca #14155) [F1]. Commit jest w tagu v0.39.0 (sprawdzone `gh api compare`: v0.39.0 zawiera `2848af5`; v0.38.0 nie) [F15].
- **Składnia (potwierdzona w wątku PR):** `--vf=d3d11vpp=scale=2:scaling-mode=nvidia`, „musi to być jeden filtr” [F1]. SVP forum, 2024-08-26: działa w oficjalnym buildzie jako `vf=d3d11vpp=scale=2:scaling-mode=nvidia` albo klawisz `ctrl+g vf toggle d3d11vpp=scale=2:scaling-mode=nvidia` [R][F16].
- **Wymagania [F1]:**
  - d3d11 i dekodowanie sprzętowe (`hwdec=d3d11va`, kasper93 radzi też `gpu-api=d3d11`).
  - Dla dekodowania programowego trzeba jawnie `format=nv12` przed filtrem i po nim.
  - Przełącznik w panelu NVIDIA (RTX Video Super Resolution). Zgłoszenia „Inactive” w panelu mimo zarejestrowanego filtra bywały rozwiązywane konfiguracją.
  - VSR jest nieaktywne przy włączonym NVIDIA Image Scaling, DSR lub DLDSR (relacja jednego użytkownika, Andarwinux) [R].
  - Skala 1.0 z `nvidia` początkowo nie włączała funkcji (tylko redukcja artefaktów); poprawiono w #15071 [F1].
- **Poziomy jakości:** `d3d11vpp` nie ma opcji poziomu. Poziom wybiera się w panelu/aplikacji NVIDIA. NVIDIA App od 2025-01-30: tryb „Auto” z opcją GPU Utilization (High = wyższa jakość) albo ręczny poziom; nowszy model zużywa „do 30% mniej zasobów GPU” na najwyższym poziomie [F17]. Oficjalne FAQ z 2023: poziom 4 dla wszystkich scenariuszy tylko od serii XX70 wzwyż [?: źródło wtórne, przed RTX 50]. Czy poziomy w ogóle mają znaczenie w ścieżce mpv/VPBlt, niepotwierdzone [?].
- **Ograniczenia:**
  - **Tylko upscaling** (`scale` > 1) i artefakty kompresji; nie interpoluje.
  - **Kolejność z VapourSynth/RIFE:** gdy `d3d11vpp` trafiał przed VapourSynth, SVP zgłaszał błąd „tile size must be divisible by 32 (3840, 2168)”; obejście: nie ustawiać `vf` w `mpv.conf`, włączać skrótem po starcie (lub skryptem Lua z opóźnieniem 3 s) [R][F16]. [W] Ścieżka VS wymaga ramek CPU, a `d3d11vpp` produkuje ramki d3d11, więc w łańcuchu z VS/SVP VSR musiałby stać za interpolacją albo być niemożliwy.
  - **Skala/okno:** rozmiar okna nie jest znany przy zakładaniu filtra; skala ma być ustawiana skryptem po utworzeniu okna (kasper93 w #14698) [F1].
  - **Shadery GLSL / `gpu-next`:** nie znalazłem źródła mówiącego, że VSR nie współpracuje z shaderami; konfiguracja z `gpu-next` jest używana w wątkach [F1][F6]. Zachowanie przy łańcuchu VSR + shadery/AnimeJaNai niezmierzone [?].
  - **HDR VSR:** w 2024 maintainer pisał, że nie wspiera, bo nie miał sprzętu do testu [F1]; od NVIDIA App 2025-01-30 sterownik sam wspiera VSR dla HDR [F17], ale dla mpv niepotwierdzone [?].
  - Crashe (0xc0000005) i artefakty zgłaszano w wczesnych wersjach PR (2024) [R][F18]; stan obecny [?].
- **RTX 50:** RTX Video SDK 1.1 dodaje „RTX 50 series (Blackwell)”, natywne CUDA, VSR dla 10-bit i szybsze modele [F19]. Zgłoszeń problemów z RTX 50 w mpv nie znalazłem [?]. Działa na dowolnym GeForce RTX [F17].
- **Jakość dla anime:** brak testów porównawczych VSR w mpv z AnimeJaNai ani shaderami [?]. Relacje użytkowników: anime korzysta, najwięcej przy ≤720p; ktoś pisał, że wygląda gorzej niż FSRCNNX w mpv (jeden głos, 3080 Ti) [R][F20]. [W] Model VSR nie jest trenowany pod anime; AnimeJaNai jest, więc oczekuję przewagi AJ w liniach i jednolitych polach; to hipoteza do pomiaru.
- **Instalacja systemowa:** nie. Funkcja jest w sterowniku (już zainstalowanym) i w przełączniku panelu NVIDIA/NVIDIA App; potrzebny jest tylko nowszy mpv. Ustawienie w panelu jest globalne dla sterownika, nie „instalacją” [W].
- **Licencja:** mpv GPL/LGPL; VSR część sterownika, bez osobnej licencji na użycie [W].

**Względem istniejącego researchu:** `03-upscaling.md` (tabela, wiersz VSR) zawiera tylko „Ogólny, nie dla anime [?]”; ten raport go uzupełnia o wersję (v0.39.0), wymagania i błąd łańcucha z VS, i pokazuje, że lokalny mpv nie ma opcji.

### 3.2 RTX Video HDR (`nvidia-true-hdr`)

- **[F]** Opcja `nvidia-true-hdr` filtra `d3d11vpp` włącza RTX Video HDR; „tylko konwertuje SDR do HDR i jest ignorowana dla źródeł już HDR” [F2]. Dodana commitem `6ca3752f` (Fixes #13352), po v0.39.0, przed v0.40.0 (sprawdzone `gh api compare`) [F4][F15].
- **[F]** Dwie istotne poprawki w 2026: `5abce15f` (2026-06-28) „enable NVIDIA RTX Video only for SDR input”, bo filtr przy HDR w źródle i przy SDR-owym wyświetlaczu dawał zniekształcony obraz (issue #17800, otwarte 2026-04-22) [F6]. Maintainer zaleca profil warunkowy włączający filtr tylko dla bt.1886 i `gpu-next` [F6].
- **[W]** Ten sam wniosek co użytkownik: przy monitorach SDR i HDR wyłączonym w Windows funkcja nie ma zastosowania. Autor zgłoszenia #17800 pisze, że sama funkcja RTX Video HDR jest nieaktywna przy SDR-owym wyświetlaczu, a zniekształcenia robi obsługa formatu wyjścia w mpv [F6]. **Pomijamy.**

### 3.3 NVIDIA Optical Flow SDK, NvOFFRUC, SVP „NVIDIA Optical Flow”

- **[F] Co to jest.** NvOFFRUC „interpoluje nowe klatki z wektorów optical flow, zwiększając efektywną liczbę klatek około dwukrotnie”, liczone na dedykowanym sprzęcie NVOFA, „niezależnie od rdzeni CUDA” [F7]. Interpolowana klatka nie musi leżeć w środku między klatkami [F21].
- **[F] Status SDK.** Strona dokumentacji: Optical Flow SDK 5.0, stan strony z 2023-02-02; interfejsy DX11/DX12/CUDA/Vulkan; licencja „NVIDIA DesignWorks SDK License” [F9]. Strona produktu wymienia Turing, Ampere, Ada; **o Blackwellu (RTX 5090) nie ma wzmianki** [F7][F8]. Czy FRUC działa na RTX 5090: niepotwierdzone [?]. Forumowy głos, że SDK „nie było aktualizowane od 2023”, to opinia [R].
- **[F] FRUC w praktyce:** sample ma jedną klatkę pośrednią na parę; dla >2× trzeba wielokrotnie wołać bibliotekę [F22]. API przyjmuje NV12 i RGB (bez natywnego 10/12 bit) [R: SVP forum 2022].
- **[F] Licencja i FFmpeg.** Filtr FFmpeg oparty na NvOFFRUC (Philip Langdale, 2023-01) został uznany za niepraktyczny przez licencję i nie zmergowany [F23]. Wniosek: FRUC nie może być dołączony do wolnego oprogramowania; własny build mpv z FRUC byłby tylko do użytku prywatnego i wymagałby pobrania SDK po stronie właściciela [W].
- **[F] Brak integracji z mpv/VapourSynth:** wyszukiwanie nie znalazło działającego pluginu [?: brak dowodu nieistnienia]. SVP-team: w wątku z 2022-12-29 deweloper pisał, że wsparcie jest „w toku, niski priorytet”, bo FRUC „pozwala tylko na x2” [F24].
- **[F] FFmpeg `fruc_vulkan`.** W repozytorium FFmpeg są commity `avfilter/fruc_vulkan` z 2026-06-28…2026-08-29 (m.in. wersja `d20bae84` „version bump for vf_fruc_vulkan”), a plik `libavfilter/vf_fruc_vulkan.c` istnieje w master [F11]. Doniesienia prasowe: sprzęt NVOFA przez Vulkan (VK_NV_optical_flow), RTX 30/40/50, brak w stabilnych buildach [F10]. [W] To zbliża się do tego, czego szukamy, ale: (a) to filtr FFmpeg, nie mpv; (b) mpv używa libavfilter, więc w zasadzie `--vf=lavfi=[fruc_vulkan=...]` mogłoby działać po zbudowaniu ffmpeg z tym filtrem i dostarczeniu ramek Vulkan, lecz tego nie znalazłem w żadnym źródle [?]; (c) jakość i wydajność nieznane (artykuł nie podaje liczb) [F10].
- **SVP „NVIDIA Optical Flow”.** SVP 4 oferuje NVOF jako źródło wektorów ruchu zamiast własnych (wątki forum: „NVOF kontra RIFE”, 2022–2024) [R]. Nie znalazłem oficjalnego opisu mechanizmu w dokumentacji SVP; z relacji: NVOF jest szybszy niż wektory SVP, ale daje „fale” na krawędziach, a RIFE ogólnie wygrywa jakością [R][F25]. W RIFE TensorRT NVOF służy tylko do wykrywania cięć [R]. W lokalnych skryptach `memc_svp_*.vpy` jest `Nvof=False` (`01-local-mpv.md` §wiersz 128), więc właściciel już ten tryb ma wyłączony.
- **Porównanie z kandydatami:** [W] SVP+NVOF/NVOFA to klasyczna interpolacja z wektorów; RIFE TensorRT daje ruch uczony na anime i jest dla nas pewniejszym wyborem. NVOFA wygrywa tylko obciążeniem (poza CUDA), a to nie jest wąskie gardło na 5090. Nie rekomenduję budowy czegokolwiek wokół FRUC.

### 3.4 DLSS Frame Generation / Multi Frame Generation / DLSS Super Resolution

- **[F] Wejścia FG:** Streamline wymaga bufora głębi, wektorów ruchu, koloru bez HUD i koloru UI; „DLSS FG nie wspiera wielu viewportów”; macierz kamery bez jittera; bufory muszą żyć do `Present` [F12][F26].
- **[F] Integracja:** hook na `IDXGIFactory::CreateSwapChain` i `Present`, wymagany DX12, Windows 10 20H1+, HAGS włączone; FG liczone przy `Present`, a NVIDIA mówi wprost, że Streamline to jedyna wspierana droga (brak użycia samodzielnego) [F12][F27].
- **[F] DLSS Super Resolution** wymaga w grze wektorów ruchu i jittera kamery (część integracji Streamline/NGX) [F26].
- **[W] Dlaczego nie dla wideo:** film jest sekwencją zdekodowanych klatek, bez głębi, bez wektorów ruchu z silnika i bez jitteru; można by wyliczyć wektory (optical flow), ale to inny algorytm niż DLSS-FG i nie jest wspierane. Dlatego NVIDIA ma osobne RTX Video (VSR, HDR) dla wideo [F19].
- **[?]** Nie znalazłem żadnego odtwarzacza ani projektu stosującego DLSS FG do wideo; to jest brak znalezionego dowodu, nie dowód nieistnienia.

### 3.5 Smooth Motion i „RTX Video” w sterowniku

- **[F] Smooth Motion:** sterownikowy model AI, który „wnioskuje dodatkową klatkę między dwiema wyrenderowanymi”, dla gier DX11/DX12 bez DLSS FG; debiut RTX 50, później RTX 40 [F17]. Włączanie: NVIDIA App → Graphics → Program settings → Driver Settings [F17]. Doniesienia późniejsze: Vulkan i RTX 40 w sterownikach 581.x/590.x [R: DSOGaming, Notebookcheck].
- **[?]** Nie znalazłem żadnego testu ani zgłoszenia, że Smooth Motion działa na mpv ani na odtwarzaczu wideo. Wynik wyszukiwania dla „Smooth Motion + mpv” zwracał jedynie nieistotny, własny tryb „smooth motion” z mpv (wątki #731, #1505 dotyczą go, nie NVIDIA).
- **[W]** Funkcja jest zdefiniowana dla gier DX11/DX12 i ustawiana per program [F17]; efekt na `mpv.exe` nieznany [?]. To hipoteza do ewentualnego jednorazowego testu przez właściciela.
- **„RTX Video” w NVIDIA App:** kontroluje VSR i Video HDR dla przeglądarek i obsługiwanych aplikacji; mpv wymaga jawnego filtra `d3d11vpp` [F2][F17].

### 3.6 Maxine VFX SDK i pozostałe

- **[F]** Maxine VFX SDK: Super Resolution 90p–2160p wejścia, skale 4/3×, 1,5×, 2×, 3×, 4×; Artifact Reduction 90p–1080p; instalacja funkcji skryptem PowerShell `install_feature.ps1`, który pobiera modele TensorRT z NGC [F14]. Windows: sterownik ≥ 511.65, CMake ≥ 3.12 [F14]. Modele Video Super Resolution na licencji NVIDIA Open Model License [F14].
- **[?]** Wsparcie RTX 50, rozmiar pobierania i szczegóły licencji SDK niepotwierdzone.
- **[W]** To biblioteka C++/API, której nikt nie owinął w filtr mpv; pracochłonne i bez przewagi nad AnimeJaNai (który zna anime). Pomijamy.
- **RTX Video SDK** (VSR, artifact reduction, SDR→HDR): dla programistów, 1.1.0, Windows 10+, DX11/DX12/Vulkan/CUDA, GeForce RTX 20+ [F19][F28]. Licencja/redystrybucja niepotwierdzone [?]. Sensowne tylko jako baza własnego filtra; nie istnieje gotowy filtr mpv inny niż `d3d11vpp`.

## 4. Tabela werdyktów

| Pozycja | Werdykt | Użycie | Instalacja | Licencja | Wobec AnimeJaNai / RIFE TRT |
|---|---|---|---|---|---|
| RTX VSR | **Działa w mpv ≥ 0.39.0**; lokalny mpv 0.36.0-711 nie ma opcji | `--vf=d3d11vpp=scale=2:scaling-mode=nvidia`, `hwdec=d3d11va`, przełącznik w panelu NVIDIA | Brak systemowej; potrzebny nowszy mpv i globalny przełącznik w sterowniku | Sterownik/mpv | Alternatywa dla AJ jako upscaler, mniej dopasowana do anime [W]; nie łączy się z VS/SVP w jednym łańcuchu |
| RTX Video HDR | Działa w mpv ≥ 0.40.0, ale bez sensu na SDR | `d3d11vpp=nvidia-true-hdr` | — | — | Nie dotyczy |
| NvOFFRUC | **Nie da się** w mpv dziś (brak pluginu; Blackwell niepotwierdzony) | — | SDK z konta developera | NVIDIA DesignWorks SDK License (nieredystrybuowalna) | Gorsza ścieżka niż RIFE TRT |
| FFmpeg `fruc_vulkan` | **Z obejściem, niepotwierdzone** (tylko master FFmpeg, nie mpv) | `lavfi` w mpv [?] | Własny build FFmpeg/mpv | FFmpeg LGPL/GPL [W] | Kandydat na eksperyment, nie na produkt |
| SVP „NVIDIA Optical Flow” | Działa (SVP) | Opcja SVP | SVP (już używany) | SVP | Gorsze artefakty niż RIFE wg użytkowników [R] |
| DLSS FG / MFG / SR | **Nie da się** | — | — | — | Wymaga danych z silnika gry |
| Smooth Motion | **Niepotwierdzone, odradzam** | Profil w NVIDIA App | — | — | Nie dla wideo |
| Maxine VFX SDK | Nie da się bez własnego filtra | — | Instalator + modele z NGC | Open Model License / NVIDIA SDK | Brak przewagi nad AJ |

## 5. Co dodać do pomiarów etapu 01

1. **Sprawdzenie wersji:** zapisać, czy docelowy mpv (fork z AnimeJaNai 3.9.0 i/lub mpv v0.41.0+) zawiera `scaling-mode` (`mpv --vf=d3d11vpp=help` lub dokumentacja builda; uwaga, pomiar wymaga uruchomienia mpv, czego ten research nie robił).
2. **A/B upscalingu na 3 materiałach (720p, 1080p, 1080p z bandingiem):** AnimeJaNai V3.1 Balanced vs `d3d11vpp scaling-mode=nvidia` (poziomy auto i najwyższy) vs bez upscalera, na 2560×1440. Ocena wizualna na ujęciach z cienkimi liniami, tłem z gradientem i napisami wtopionymi w obraz; zapis zużycia GPU (`nvidia-smi -lms 500`).
3. **Zgodność łańcuchów:** czy `d3d11vpp` (ramki d3d11) uruchamia się razem z `vf_animejanai` i z `vo=gpu-next` w tym samym łańcuchu; czy z VapourSynth/RIFE (wcześniej błąd „tile size must be divisible by 32”). Zapisać dokładną kolejność i wynik.
4. **Sterownik 610.88:** czy panel pokazuje VSR jako „Active”, gdy `d3d11vpp` jest w łańcuchu (relacje o „Inactive”), oraz czy DSR/DLDSR/Image Scaling są wyłączone.
5. **Opcjonalnie, jednorazowo i tylko po zgodzie właściciela:** test Smooth Motion na `mpv.exe` jako dowód negatywny (zapis: działa/nie działa/psuje obraz).
6. **Nie mierzyć:** nvidia-true-hdr (SDR), DLSS FG/MFG, Maxine, NvOFFRUC.

## 6. Niewiadome

- Czy VSR przez `d3d11vpp` daje na anime obraz lepszy niż AnimeJaNai V3.1 Balanced po zmniejszeniu do 1440p (brak testów porównawczych).
- Czy NvOFFRUC i NVOFA FRUC działają na Blackwell i jak jakościowo wypadają obok RIFE (brak liczb).
- Czy `fruc_vulkan` da się użyć z mpv oraz jaka jest jego jakość i stabilność (świeże, 2026-08-29).
- Jaki poziom jakości VSR faktycznie stosuje sterownik 610.88 w ścieżce mpv.

## 7. Źródła (dostęp 2026-10-31)

- [F1] mpv PR #14155 i #14698 (merge 2024-08-20, commit `2848af5`): https://github.com/mpv-player/mpv/pull/14155 , https://github.com/mpv-player/mpv/pull/14698
- [F2] mpv `DOCS/man/vf.rst` (master), sekcja d3d11vpp: https://raw.githubusercontent.com/mpv-player/mpv/master/DOCS/man/vf.rst
- [F3] Lokalny `C:\Users\MattyMroz\Videos\mpv\mpv.exe` (data pliku 2025-12-10): ciąg `mpv v0.36.0-711-g250429da`; commit `250429da` z 2023-11-01 (`gh api repos/mpv-player/mpv/commits/250429da`); wystąpienia: `d3d11vpp` 3, `scaling-mode` 0, `nvidia-true-hdr` 0 (grep binarny; to wskazówka, nie dowód wyczerpujący).
- [F4] Commit `6ca3752f` „vf_d3d11vpp: add NVIDIA RTX Video HDR support”, 2024-09-23: https://github.com/mpv-player/mpv/commit/6ca3752f
- [F5] Wydania mpv: v0.39.0 2024-09-23, v0.40.0 2025-03-25, v0.41.0 2025-12-21 (`gh api repos/mpv-player/mpv/releases`).
- [F6] mpv issue #17800 (otw. 2026-04-22, zamk. 2026-06-28), commit `5abce15f`: https://github.com/mpv-player/mpv/issues/17800
- [F7] NVIDIA Optical Flow SDK, strona produktu: https://developer.nvidia.com/optical-flow-sdk
- [F8] Wyszukiwanie „NvOFFRUC … Blackwell”: brak wzmianki o Blackwell w zwróconych źródłach.
- [F9] Dokumentacja Optical Flow SDK 5.0: https://docs.nvidia.com/video-technologies/optical-flow-sdk/index.html
- [F10] Guru3D o `fruc_vulkan` (źródło wtórne, wg Phoronix): https://www.guru3d.com/story/ffmpeg-adds-nvidia-gpu-frame-interpolation-through-vulkan-for-rtx-30-rtx-40-and-rtx-50/
- [F11] Repozytorium FFmpeg: commity `avfilter/fruc_vulkan` (`c6d56731`, `91a51a79`, `f6d7c089`, `d20bae84`), plik `libavfilter/vf_fruc_vulkan.c` (`gh api`).
- [F12] Streamline, wymagania DLSS-G: https://developer.nvidia.com/rtx/streamline/get-started
- [F13] Smooth Motion (wccftech, 2025): https://wccftech.com/nvidia-adds-smooth-motion-a-driver-based-frame-generation-ai-model-for-rtx-50-gpus/amp/
- [F14] Maxine VFX SDK: https://github.com/nvidia/MAXINE-VFX-SDK , https://docs.nvidia.com/deeplearning/maxine/vfx-sdk-programming-guide/index.html , https://catalog.ngc.nvidia.com/orgs/nvidia/maxine/collections/nvvfxsuperres/-
- [F15] `gh api repos/mpv-player/mpv/compare/<tag>...<sha>` dla v0.38.0, v0.39.0, v0.40.0 i commitów `2848af5`, `6ca3752f`.
- [F16] SVP forum, „mpv + super res” (2024-08…09): https://www.svp-team.com/forum/viewtopic.php?id=7381
- [F17] NVIDIA App update, 2025-01-30 (VSR, Smooth Motion): https://www.nvidia.com/en-gb/geforce/news/nvidia-app-update-dlss-overrides-and-more
- [F18] mpv PR #14155 (komentarze o crashach/artefaktach).
- [F19] RTX Video SDK Getting Started (1.1.0, Blackwell, Windows 10+): https://developer.nvidia.com/rtx-video-sdk/getting-started
- [F20] TechPowerUp, wątki o RTX VSR: https://www.techpowerup.com/forums/posts/4961968
- [F21] NVIDIA blog o FRUC na Ada: https://developer.nvidia.com/blog/harnessing-the-nvidia-ada-architecture-for-frame-rate-up-conversion-in-the-nvidia-optical-flow-sdk
- [F22] NVIDIA forum, FRUC >2×: https://forums.developer.nvidia.com/t/use-fruc-to-do-framerate-up-conversion-more-than-2x/234623
- [F23] FFmpeg-devel, filtr NvOFFRUC (2023-01): https://lists.ffmpeg.org/pipermail/ffmpeg-devel/2023-January/305234.html
- [F24] SVP forum, „NVIDIA Optical Flow SDK 4.0” (2022-12-29): https://www.svp-team.com/forum/viewtopic.php?id=6783
- [F25] SVP forum, NVOF vs RIFE: https://svp-team.com/forum/viewtopic.php?id=6280
- [F26] NVIDIA, integracja DLSS 4 przez Streamline: https://developer.nvidia.com/blog/how-to-integrate-nvidia-dlss-4-into-your-game-with-nvidia-streamline
- [F27] NVIDIA forum, DLSS-G bez `Present()`: https://forums.developer.nvidia.com/t/using-dlssg-without-idxgiswapchain-present/247260
- [F28] RTX Video SDK: https://developer.nvidia.com/rtx-video-sdk
