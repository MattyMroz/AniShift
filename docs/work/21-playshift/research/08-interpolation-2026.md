---
kind: research
id: playshift-r8-interpolation-2026
date: 2026-10-31
subject: najlepsza interpolacja klatek dla anime w mpv na Windows (stan 2026-10-31), ze szczególnym uwzględnieniem tekstu na ekranie
---

# R8: interpolacja klatek dla anime w mpv w 2026 — czy jest coś lepszego niż domyślne PlayKit

Oznaczenia: **[F]** fakt ze źródłem, **[R]** relacja użytkowników, **[W]** wniosek, **[?]** niewiadoma. Źródła otwarte 2026-10-31. Nic nie pobierano ani nie uruchamiano. Raport uzupełnia `04-interpolation-color.md` i `07-nvidia.md` (nie powtarza ich); katalogu `outcomes\` nie ma, więc liczby RIFE TensorRT z AnimeJaNai (176–182 fps sam, ok. 105 fps z upscalingiem Performance) przyjęto z zlecenia, bez własnej weryfikacji.

## 1. Pytanie

Czy w 2025–2026 pojawiło się coś, co daje na anime lepszą interpolację niż to, co właściciel ocenia dziś jako najlepsze (MVTools, SVP, RIFE ncnn v4.0 ×2 z paczki PlayKit 2023), szczególnie na tekście i napisach wypalonych w obrazie, na RTX 5090, przy 2× i celu ok. 100–200 fps.

## 2. Odpowiedź w skrócie

1. **Nie pojawił się nowy model, który jednoznacznie bije RIFE w czasie rzeczywistym.** [F] Najnowszy publiczny model Practical-RIFE to 4.26 (2024-09-21); 4.25 (2024-09-19) autor nazywa domyślnym i pisze, że sceny anime są „znacznie poprawione” [F1]. Dla właściciela największym skokiem jest sam przeskok z v4.0 (2021) na 4.2x przez TensorRT, a nie nowy model.
2. **Wśród modeli 4.2x nie ma zgodnego zwycięzcy dla tekstu.** [R] Forum SVP: 4.25 najczęściej polecany, 4.26 najczęściej krytykowany (zwłaszcza `4.26_heavy`), 4.22-lite „gładszy, mniej artefaktów” w filmach, a RIFE hzwer sugeruje 4.22.lite dla anime [R][F2]. Dla napisów wypalonych starsze relacje mówią o 4.10 jako stabilnym [R][F2]. To wszystko anegdoty z lat 2024–2025, żadnego pomiaru. Decyduje test na własnych scenach (§5).
3. **Jedyna realna nowość specyficzna dla anime w mpv: DRBA (`MEMC_DRBA_NV.vpy` w PlayKit).** [F] Nakładka na RIFE/GMFSS sterująca „distance ratio” tak, by zachować tempo animacji (klatki na dwójki) [F3]; w PlayKit od wydania 2026NE (2025-12-13) „DRBA interpolation support”, a w 2026CJ (2026-02-10) poprawiono precyzję DRBA_NV (aliasing i przesunięcie przy 4K) i dodano DRBA_DML [F4]. [F] Koszt wg VSGAN-tensorrt-docker (RTX 4090, 1080p ×2): DRBA+RIFE 4.26 309 kl./s vs RIFE 4.26 410 kl./s, czyli ok. 1,3× koszt [z `04`, F2 tam]. **Brak niezależnej oceny jakości**, a użytkownicy SVFI opisują tryb DRBA jako interpolujący tylko tło, a nie poruszające się postacie [R][F5]. Kandydat do testu, nie do domyślnego użycia.
4. **GIMM-VFI (NeurIPS 2024) — do real-time w mpv się nie nadaje na dziś.** [F] Repozytorium nie podaje fps, nie wspomina o TensorRT ani VapourSynth; ostatnia aktualizacja 2024-11-18; osobny port tylko do ComfyUI [F6]. EMA-VFI, AMT: nie znalazłem integracji z mpv/VS w czasie rzeczywistym [?: brak dowodu nieistnienia]. GMFSS_Fortuna daje wg autora najmniej artefaktów na animacji (offline; ATD-12K PSNR 29,22 / SSIM 0,932 / LPIPS 0,048, wyniki własne, bez porównania z RIFE) [R][F7], repo „nie będzie aktualizowane”, w PlayKit go nie ma. Jest tylko wariantem jakościowym w DRBA (`gmfss_union`) [F3]. Czasu rzeczywistego na 5090 nie sprawdzono [?].
5. **SVP 4 (obecnie 4.7.325, 2026-09-27) nie zmienia obrazu: nic nowego dla interpolacji.** [F] Changelog 2026 zawiera tylko wsparcie macOS 27 i „poprawki dla VapourSynth R74+/R80+”; nic o RIFE, TensorRT czy RTX 50 [F8]. Cena nadal 24,99 USD (dożywotnio), strona wymienia RIFE i NVIDIA Optical Flow [F9]. **Wymóg SVP Managera w tle nadal obowiązuje dla `svpflow` w VapourSynth** (wiki: „SVPflow libs require a SVP Manager running”; bez niego czerwona ramka; dotyczy Windows i macOS) [F10]. Wiki ma datę 2019, a lokalna starsza wersja działa bez Managera (`04` §2) [F]. Czy aktualne `svpflow` 4.7 nadal rysuje ramkę: **niewiadoma** [?], trzeba przetestować.
6. **Nie istnieje narzędzie, które w mpv maskuje wypalony tekst przed interpolacją.** [W] Nie znalazłem w żadnym źródle ani skryptu, ani filtra, ani opcji PlayKit, które wykrywałyby tekst/napisy wypalone w klatkach i chroniły je (brak dowodu nieistnienia [?]). Istnieją tylko środki pośrednie opisane w §4.
7. **Dla właściciela rekomendacja zmienia się w jednym punkcie względem `04`:** ścieżkę RIFE TensorRT trzeba porównać nie tylko jako „RIFE 4.2x”, ale w trzech wariantach modelu (4.22-lite, 4.25, 4.26) i z DRBA. SVP z `algo` 2 (z dokumentacji „zalecany dla animacji 2D”) i `mask.area`/`mask.cover` jest sensownym wariantem kontrolnym na tekst.

## 3. Ustalenia per technologia

### 3.1 RIFE
- [F] Modele (Practical-RIFE README): 4.14 (2024-01), 4.15, 4.17 (+gram loss z FILM), 4.18, 4.20 (2024-07-24), 4.21, 4.22 (2024-08-08), **4.25 (2024-09-19, domyślny)**, 4.25.lite (2024-10-20), **4.26 (2024-09-21)**; żaden nowszy [F1]. Wersje lite = ten sam trening, mniejszy koszt [F1].
- [F] vs-mlrt: stabilne v15.16 (2026-03-26), test v16.4 (2026-10-30), obsługa `RIFE v4.26_heavy` od v15.7; ostrzeżenie: TensorRT 10.1 miał do 4× regresji na sieciach z GridSample (RIFE), ostatnie niedotknięte wydanie to `v14.test3`, wcześniejsze wydania v15.x to naprawiają [z wyszukiwania wiki/releases] [F11]. [?] Brak potwierdzenia, że obecne v15.16/v16 mają pełną wydajność RIFE na Blackwellu poza zmierzonymi liczbami z AnimeJaNai ze zlecenia.
- [F] PlayKit 2026CJ (2026-02-10): k7sfunc 1.3.1; `RIFE_NV` dzieli poziom `turbo`, `RIFE_STD` dostaje `turbo`; **standardowa paczka usuwa modele interpolacji spoza ustalonych parametrów skryptu presetów, łatka `vsNV` je przywraca** [F4]. Zatem „domyślne rozwiązanie PlayKit” to preset skryptowy z ograniczonym zestawem modeli, a pełny wybór wymaga paczki `vsNV` (zgodnie z `04` §5).
- [F] Praca nad wypalonymi napisami: relacje z forum SVP 2024–2025: 4.9 gorszy od 4.8 dla wypalonych napisów, 4.10 „najstabilniejszy”; 4.25 „najmniej artefaktów od 4.18”; 4.26 „doubling” w jednym teście i bardzo niestabilny w innych [R][F2]. Ocena częstości niemożliwa z takiej próby.

### 3.2 DRBA
- [F] Repozytorium routineLife1/DRBA, licencja MIT; „VS-DRBA” (VapourSynth + TensorRT) deklaruje „400% przyspieszenie” bez podania metodyki; brak wydań [F3]. Przykłady używają `rife` (szybkość) i `gmfss_union` (jakość) [F3]. Autorzy przyznają, że wariant oparty na RIFE może dawać zniekształcenia tła [F3 przez wyszukiwanie].
- [F] Integracja w mpv: `MEMC_DRBA_NV.vpy` w PlayKit [z `04`, F7 tam; 2026CJ potwierdza prace nad DRBA_NV i DRBA_DML [F4]].

### 3.3 SVP / svpflow
- [F] Parametry `SmoothFps` (wiki Manual:SVPflow, 2019): `mask.area` (domyślnie 0, polecane do 100, kosztem „dramatycznie” mniejszej płynności), `mask.cover` (100; polecane 50–100), `scene.mode` (3), `scene.blend`, `scene.limits.scene` (4000), `algo`: 2 = „przesuwa piksele z najbliższej w czasie klatki; polecany dla animacji 2D”, 13 = domyślny, najmniej artefaktów, ale widoczne halo, 21 = 11 + maska cover/uncover [F10]. Próbka dla animacji: `block:{w:8}, refine:[{thsad:1000}]` [F10].
- [R] SVP forum 2015–2016: „artifact masking” bywa gorszy dla anime, bo zmniejsza płynność; część osób zaleca shader „Complicated” bez maskowania; doradzają mniejszy interpolation mode lub mniejszą siatkę wektorów [R][F12]. Dane stare, bez testów na napisach.
- [F] Lokalny `memc_svp_*.vpy` korzysta z `k7sfunc.SVP_PRO` (`04` §5); wartości `algo`/`mask.*` w tych skryptach: [?] do odczytu przy teście.

### 3.4 MVTools
- [F] Upstream `vapoursynth-mvtools` ma wydania z 2026 (PyPI 29, 2026-06-21; Arch 28-1, 2026-06-04) [F13]. [?] Nie znalazłem forka z lepszymi artefaktami na tekście ani wzmianki o ustawieniach, które to rozwiązują. Wniosek [W]: MVTools to technologia wektorów blokowych, ta sama klasa co SVP, bez zaleceń specyficznych dla anime i wolniejszy w mpv niż SVP (lokalny pomiar `04` §5: 134 kl./s vs 244 kl./s).

### 3.5 NVIDIA
- `07-nvidia.md`: NvOFFRUC, DLSS-FG, Smooth Motion nie są dostępne w mpv. Nowość tam odnotowana: FFmpeg `fruc_vulkan` (master 2026-08), nie zbadany w mpv. [W] Nic w tym raporcie tego nie zmienia.

## 4. Artefakty na tekście: co działa, a co nie

Rozróżnienie podstawowe [W]:

| Rodzaj tekstu | Czy interpolacja go dotyka | Co robić |
|---|---|---|
| Napisy miękkie (ASS/SRT) w mpv | Nie, jeśli renderowane po filtrach `vf` [F, z `04` §2: „napisy miękkie renderuje po filtrach”] | nic; nie włączać `blend-subtitles`, jeśli nie jest potrzebne (opcja wtapia napisy w klatkę przed skalowaniem i interpolacją mpv [W: z dokumentacji `options.rst`, której tu nie otwarto do końca, status: niezweryfikowane]) |
| Napisy wypalone (hardsub) i znaki w kadrze (szyldy, tytuły, kredyty ruchome, SFX) | Tak, jako część obrazu; falują przy ruchu | tylko środki pośrednie niżej |

Środki pośrednie, wszystkie [W] wniosek z relacji i dokumentacji, żaden nie przetestowany przeze mnie:

1. **Niższy docelowy fps / mnożnik.** [F] Wiki cHiDeScaler: wyższy mnożnik ułatwia zauważenie artefaktów w trudnych scenach (napisy, UI, okluzje, szybkie cięcia) [F14]. Cel 85 fps zamiast 170 (z `04`) jest więc także środkiem na artefakty.
2. **Model RIFE.** Patrz §3.1; wybór 4.22-lite/4.25 vs 4.26 to jedyna realna dźwignia po stronie sieci. DRBA może zmieniać zachowanie na ruchomych obiektach, ale jego wpływ na tekst jest nieznany [?].
3. **Detekcja cięć.** [F] Zbyt niski próg = powtórzenia klatek (stutter), zbyt wysoki = morfing na cięciu [F15]. W vs-mlrt wymagana jest zewnętrzna detekcja (`misc.SCDetect`) [F11].
4. **SVP: `algo` 2 + `mask.area`/`mask.cover` + mała siatka bloków.** [F] Parametry istnieją i są opisane [F10]; [R] efekt na anime sporny [F12].
5. **Pełne ominięcie problemu:** GMFSS-Interp (offline, ffmpeg/mkvmerge) przenosi napisy bez interpolacji [F16]; nie jest rozwiązaniem real-time w mpv.
6. **Interpolacja częściowa (maska tylko na tekst).** [?] Nie znalazłem żadnej gotowej implementacji. Realna, ale nowa praca (VapourSynth: maska z detekcji tekstu + `core.std.MaskedMerge` z klatką źródłową), poza zakresem tego raportu.

## 5. Ranking dla przypadku właściciela

Kryteria: jakość anime, artefakty tekstu, instalacja przenośna, wydajność RTX 5090 przy 2×, licencja. Kolumny oceny to [W]. „Jakość”/„tekst” opierają się wyłącznie na relacjach lub rozumowaniu, bo nie znalazłem testu porównawczego. Oceny wydajności: z `04` (pomiary lokalne ncnn/SVP/mvtools) i ze zlecenia (RIFE TRT w AnimeJaNai).

| # | Wariant | Jakość anime | Tekst | Wydajność 5090, 2× | Instalacja | Licencja | Uwagi |
|---|---|---|---|---|---|---|---|
| 1 | **RIFE 4.25 / 4.22-lite TensorRT** (vs-mlrt / AnimeJaNai) | wysoka [F1][R] | średnia, zależna od sceny [R] | ok. 176–182 fps sam [zlecenie] | przenośna (pakiet vsNV/AnimeJaNai, ok. 2,9 GB, jednorazowy build silnika) | MIT/open (RIFE), vs-mlrt wg repozytorium | rekomendowany domyślny kandydat |
| 2 | **DRBA (RIFE-based) TensorRT** | potencjalnie najlepsza na tempie animacji, niezależnie niepotwierdzona [F3][R] | nieznany [?] | ok. 1,3× koszt RIFE [F, 4090] | jw. (`MEMC_DRBA_NV`, `vsNV`) | MIT | warto dodać do testu |
| 3 | **RIFE 4.26 / 4.26-heavy TensorRT** | wysoka, ale krytykowana przez użytkowników [R] | gorsza wg części relacji [R] | niższa dla heavy (279 vs 410 kl./s na 4090) | jw. | jw. | tylko dla porównania |
| 4 | **SVP (svpflow) `algo` 2, mask** | blokowa [W z `04`] | konfigurowalna maskami; efekt na anime sporny [R] | 244 kl./s w mpv (lokalnie) | **wymaga SVP Managera w tle wg wiki** [F10]; wersja 2026 do sprawdzenia [?] | svpflow2 zamknięty; SVP 24,99 USD | wariant kontrolny na tekst; Manager łamie preferencję „bez procesów w tle” |
| 5 | **MVTools** | niższa niż SVP/RIFE [W] | jak SVP bez masek | 134 kl./s w mpv (lokalnie), nie nadąża | przenośna | GPL | odpada przy 170 fps |
| 6 | **RIFE ncnn v4.0 (obecny)** | model z 2021 | średnia | 60–70 kl./s w mpv, CPU-bound | już jest | open | do porzucenia (`04`) |
| 7 | **GIMM-VFI, EMA-VFI, AMT, GMFSS** | niepotwierdzona | nieznany | brak dowodu real-time w mpv [?] | brak gotowych filtrów | rożne | poza zasięgiem na dziś |

## 6. Co dodać do testów K1 właściciela

Uzupełnienia do planu pomiarów z `04` §5 (wszystko na tych samych krótkich scenach, 1080p, ×1,77 do 85 i ×3,55 do 170 przy 2×):

1. **Zestaw scen tekstowych (6–8 krótkich ujęć, każde 5–10 s)**: napis wypalony na dole kadru stały i przesuwający się; tytuł/kredyty ruchome; szyld lub napis na obiekcie w ruchu kamery; pasek z tekstem przy panoramowaniu; szybkie cięcie przy napisie; rozmyty tekst. Nagrać plik testowy raz, użyć dla wszystkich wariantów.
2. **Warianty interpolacji do A/B/C…:** (a) RIFE 4.22-lite TRT, (b) RIFE 4.25 TRT, (c) RIFE 4.26 TRT, (d) DRBA (`MEMC_DRBA_NV`), (e) SVP `algo` 2 + `mask.area`≈50–100, `mask.cover`≈50–100, (f) SVP domyślny (`algo` 13), (g) bez interpolacji (kontrola). Ocena „ślepa”: kolejność losowa, właściciel nie wie, który to wariant.
3. **Cele fps:** 85 (równa kadencja) i 170 (tryb max), osobno 1× i 2×. Zapisać liczbę porzuconych klatek (`frame-drop-count`, `vo-delayed-frame-count`) i obciążenie GPU/CPU.
4. **Sprawdzić `svpflow` 4.7 bez SVP Managera:** czy w mpv/VS pojawia się czerwona ramka. Jeśli tak, SVP odpada przy zakazie procesów w tle (wymaga zgody właściciela na test: nie uruchamiać Managera na stałe).
5. **Skala szczegółów:** zapisać w jednej tabeli dla każdego wariantu i sceny: ocena tekstu (0–3: brak/lekkie/wyraźne/silne falowanie), ocena twarzy/linii, czy są „duchy” przy panoramowaniu, czy psuje się tempo animacji na dwójki.
6. **Seek:** czas startu filtra po seeku z zbudowanym silnikiem TRT (nieznane, `04` §2).

## 7. Niewiadome i ryzyka

- Brak niezależnych porównań RIFE 4.2x vs DRBA vs GMFSS na anime; ranking jakości opiera się na relacjach forum SVP.
- Czy `svpflow` 4.7 nadal wymaga działającego Managera: wiki z 2019 mówi „tak”, lokalna starsza wersja nie rysuje ramki.
- Czy ścieżka VS z TRT utrzyma 170 fps w mpv bez blokady CPU (`04` §6).
- Czy ktokolwiek rozwiązał ochronę wypalonego tekstu w czasie rzeczywistym: nie znalazłem; absence ≠ dowód.
- Statusy `GIMM-VFI`, `EMA-VFI`, `AMT`: nie przeszukałem repozytoriów EMA-VFI ani AMT osobno.
- Zachowanie `--blend-subtitles` nie zostało zweryfikowane w dokumentacji (strona zbyt długa dla odczytu w jednym wywołaniu).

## 8. Rekomendacja (jedna droga)

Domyślnie: **RIFE TensorRT 4.25 (lub 4.22-lite) z celem 85 fps**, z DRBA jako drugim kandydatem do testu; SVP z `algo` 2 i maskami tylko jako wariant kontrolny, pod warunkiem że nie wymaga Managera w tle. Wybór modelu rozstrzygnąć testem K1 z §6, bo żadne źródło nie rozstrzyga go dla tekstu.

## Źródła (dostęp 2026-10-31)

- [F1] Practical-RIFE README: https://github.com/hzwer/Practical-RIFE
- [F2] SVP forum, wątki RIFE/anime 2024–2025: https://www.svp-team.com/forum/viewtopic.php?pid=83245 , https://www.svp-team.com/forum/viewtopic.php?pid=85608 , https://www.svp-team.com/forum/viewtopic.php?pid=86334 , https://www.svp-team.com/forum/viewtopic.php?id=7474
- [F3] DRBA: https://github.com/routineLife1/DRBA (MIT, brak wydań); fork: https://github.com/hyw-dev/DRBA
- [F4] mpv_PlayKit, wydania 2025DS (2025-08-09) … 2026FM (2026-05-10): https://github.com/hooke007/mpv_PlayKit/releases
- [F5] SVFI (Steam), opis trybu DRBA: https://store.steampowered.com/app/1692080/SVFI
- [F6] GIMM-VFI: https://github.com/GSeanCDAT/GIMM-VFI (ostatni news 2024-11-18)
- [F7] GMFSS: https://github.com/routineLife1/GMFSS ; GMFSS-Interp: https://github.com/Houssemamor/GMFSS-Interp
- [F8] SVP Changelog (4.7.325, 2026-09-27): https://www.svp-team.com/wiki/Changelog
- [F9] SVP, strona pobierania i cennik (4.7.2.325, 2026-09-27; 24,99 USD): https://www.svp-team.com/get/
- [F10] SVP wiki, Manual:SVPflow (edycja 2019-09-29): https://www.svp-team.com/wiki/Manual:SVPflow
- [F11] vs-mlrt, wydania i wiki: https://github.com/AmusementClub/vs-mlrt/releases , https://github.com/AmusementClub/vs-mlrt/wiki
- [F12] SVP forum, „How Do I Get The Best Settings” (2015–2016): https://www.svp-team.com/forum/viewtopic.php?id=3515
- [F13] vapoursynth-mvtools: https://github.com/dubhater/vapoursynth-mvtools ; PyPI: https://pypi.org/project/vapoursynth-mvtools/29/
- [F14] cHiDeScaler wiki, Frame Interpolation: https://github.com/animeojisan/cHiDeScaler-Neo/wiki/Frame-Interpolation
- [F15] SVP wiki, RIFE AI interpolation (próg zmiany sceny, modele 4.4/4.6): https://www.svp-team.com/wiki/RIFE_AI_interpolation
- [F16] GMFSS-Interp: https://github.com/Houssemamor/GMFSS-Interp
- Wcześniejsze raporty w katalogu: `04-interpolation-color.md`, `07-nvidia.md`.
