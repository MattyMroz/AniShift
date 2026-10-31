---
kind: plan
status: draft
baseline: raporty R1–R6 z 2026-10-31; stan `Videos\mpv` według R1; AniShift f3e6980 (tylko dokumenty)
created: 2026-10-31
---

# Plan 01: porównanie metod poprawy obrazu i decyzja bazy PlayShift

Plan jest kontraktem dla świeżego wykonawcy. Ustalenia (`U*`), wymagania (`F*`, `N*`), inwarianty (`I*`), zakazy
(`Z*`) i decyzje właściciela (`D*`) są w `../specification.md`; tu są tylko odwołania. Miejsce etapu w całości:
`../masterplan.md`.

Skróty:

- **OLD** = `C:\Users\MattyMroz\Videos\mpv` — obecny odtwarzacz. Tylko odczyt (I1, Z5); agenci go nie uruchamiają.
- **EXP** = `C:\Users\MattyMroz\tmp\playshift\` — katalog eksperymentu (zgoda w D1). Poza repozytoriami, poza OLD.
- **DOC** = `C:\Users\MattyMroz\Desktop\PROJECTS\AniShift\docs\work\21-playshift\`.
- **AJN** = mpv-AnimeJaNai (`the-database/mpv-AnimeJaNai`) razem z forkiem mpv z filtrem `vf_animejanai`.
- **R1–R6** = raporty w `DOC\research\`, z numerem sekcji.

## 1. Cel

Sprawdzić, czy kandydaci na poprawę obrazu (U15) w ogóle dają obraz lepszy od obecnego: natywny filtr AJN
(upscaling i RIFE TensorRT) oraz algorytmy interpolacji z wydań `hooke007/mpv_PlayKit`. Zmierzyć na RTX 5090 i
plikach właściciela, czy działają w czasie rzeczywistym przy prędkości 2× i celu fps właściwym dla monitora,
dać właścicielowi A/B każdego kandydata z obecnym obrazem, a potem na tych liczbach i jego ocenie rozstrzygnąć,
które metody wchodzą (także „żadna”), bazę PlayShift (D6), domyślny łańcuch jakości (D3, D4, D5) i drzewo
katalogów (D7). Etap nie tworzy repo ani kodu produktu.

## 2. Rezultat użytkownika

- Tabela zmierzonych liczb: ile klatek na sekundę daje każdy wariant, ile zajmuje VRAM, ile trwa budowa silnika,
  start filtra i przełączenie trybu.
- Własne oglądanie w oknie: porównanie upscalerów na tej samej klatce, płynność RIFE przy 2× na wybranym
  monitorze, kolory, napisy z AniShift — obok obecnego odtwarzacza.
- Krótka propozycja decyzji D3–D8 z uzasadnieniem w liczbach i jedno drzewo katalogów do akceptacji.
- Po etapie w systemie nie zostaje nic poza śladami zaakceptowanymi w D8.

## 3. Warunki końcowe

- [ ] Bramka wejścia (§5) spełniona.
- [ ] Macierz pomiarów §11.4 wypełniona dla wariantów obsługiwanych przez silnik; bramki G1–G6 (§11.5) mają
      werdykt.
- [ ] Punkt kontrolny K1 przeprowadzony przez właściciela, odpowiedzi zapisane.
- [ ] `DOC\outcomes\01-engine-and-base.md` zawiera liczby, werdykty, mapę śladów i propozycję decyzji.
- [ ] K2: właściciel rozstrzygnął D3–D8 i zatwierdził drzewo §12 (z wybranym wariantem).
- [ ] Specyfikacja, masterplan i `DOC\README.md` zaktualizowane po K2.
- [ ] EXP usunięty (albo właściciel jawnie zostawił go do etapu 04); snapshot końcowy nie pokazuje śladów spoza D8.
- [ ] OLD bez zmian (porównanie z §13 Faza 0).

## 4. Nie-cel

- Repo PlayShift, narzędzie `playshift`, lock zależności, konfiguracja docelowa — etap 02 i dalej.
- Pomiar ścieżki VapourSynth + vs-mlrt — tylko po osobnej zgodzie i przeplanowaniu (§13 Faza 4b).
- Jakiekolwiek zmiany w OLD, w rejestrze, w zmiennych środowiskowych.

## 5. Bramka wejścia

Etap nie rusza, dopóki:

1. D1: „tak” (2026-10-31) — pobranie AJN i paczek `mpv_PlayKit` do EXP i uruchamianie bez okna; spełnione;
2. D2: bez odpowiedzi, więc obowiązuje domyślne „oba monitory”;
3. pliki referencyjne (tylko odczyt, nie kopiować do repozytoriów); bez wskazania właściciela wykonawca bierze
   plik z researchu dla S1, odcinek 720p z `workspace` lub bibliotek właściciela dla S2 i gotowy odcinek z
   `AniShift\workspace\ready\` dla S3:
   - **S1** — anime 1080p HEVC 10-bit, 23,976 fps; research użył `Edgerunners 2 - 01.mkv` od 300 s (R3 §5.2,
     R4 §5);
   - **S2** — anime 720p, 23,976 fps (przypadek „2× daje dokładnie 1440p”, R3 §4);
   - **S3** — gotowy odcinek AniShift z polskim lektorem i napisami `.pl` (sprawdzenie napisów, I4);
4. na dysku C: jest co najmniej 10 GB wolnego miejsca (szacunek: pobranie 1–1,5 GB, rozpakowanie i silniki
   kilka GB). 2026-10-31 było 302 GB.

## 6. Authority i baseline

- Wymagania i zakazy: `../specification.md` (U6, U7, U8, I1, Z1–Z6, N4, N8).
- Kolejność i powód etapu: `../masterplan.md`, „Aktualny etap”.
- Fakty: R1 (OLD), R2 §5–§7 (buildy, VapourSynth, rejestracja), R3 (upscaling, budżet, plan pomiaru §5.3),
  R4 (interpolacja, monitory, budżet, plan pomiaru §5), R6 §2.1 i §5 (układ, testy bez okna).

**Baseline:** OLD w stanie z R1 (2026-10-31; ostatnia zmiana `saved-props.json` 2026-10-31 00:06). AJN najnowsze
wydanie w dniu wykonania (w researchu 3.9.0 z 2026-10-27).

**Znane wcześniejsze wyniki:** RIFE ncnn w OLD daje 60–70 kl./s dla 1080p ×2 (R4 §5); SVP z celem 170 daje
244 kl./s (R4 §5); upscaling przez VapourSynth na 5090 kończy się na około 79 kl./s przez CPU (R3 §2, dane
autora AJN).

## 7. Stan aktualny

### 7.1 Dowody

| Twierdzenie | Dowód | Status |
|---|---|---|
| AJN od 3.4.0 nie używa VapourSynth ani Pythona; filtr `vf_animejanai` trzyma klatki na GPU | R3 §1 [F] | verified (źródło) |
| Od 3.6.0 paczka AJN zawiera samodzielny `mpv.exe` | R3 §1 [F] | verified (źródło) |
| Balanced 1920→3840 na 5090: około 5 ms (155,9 kl./s w uprzęży autora); Performance około 3,4 ms | R3 §3 [F2] | reported (autor AJN) |
| RIFE v4.14 przy 1080p na 5090: około 6 ms na klatkę pośrednią | R3 §3 [F2] | reported, R4 przejął bez weryfikacji |
| Filtr AJN wybiera łańcuch po nominalnym fps źródła, nie po prędkości | R3 §3 [F14] | verified (kod forka) |
| Mnożnik ułamkowy i docelowe fps RIFE w AJN | R4 §1, §6 | **unknown** |
| Zmiana łańcucha AJN w trakcie odtwarzania i jej koszt | — | **unknown** |
| Czy biblioteki AJN (aji, TensorRT) mogą leżeć w podkatalogu, a nie obok `mpv.exe` | — | **unknown** |
| Co AJN zapisuje poza swoim katalogiem (silniki TensorRT, cache sterownika) | — | **unknown** |
| Okno `gpu-api=vulkan` na RTX 50 bywa nie do otwarcia (issue #200) | R3 §6 [F16] | reported |
| Czy fork ma `--register`, VapourSynth, `--autocreate-playlist`, właściwość `clipboard` | — | **unknown** |
| Pomiary w OLD bez okna (`--vo=null --untimed`) działają | R4 §5, R6 §5 | verified |

### 7.2 Luka

Wybór bazy (D6) opiera się dziś na liczbach autora AJN z syntetycznej uprzęży i na estymacjach R3/R4, które się
różnią (masterplan, „Sprzeczności”). Brakuje pomiaru na prawdziwych plikach właściciela, wiedzy o sterowaniu
filtrem (mnożnik, przełączanie) i obrazu, który właściciel oceni sam. Bez tego drzewo katalogów (czy jest
`lib/python/`, gdzie leżą biblioteki AJN) byłoby zgadywaniem.

### 7.3 Istniejące rozwiązania do reuse

- Plan pomiaru AJN z R3 §5.3 (komendy `mpv.exe --vo=null --untimed … --vf=@aji:animejanai:…`).
- Uprząż i komendy R4 §5 (mpv bez okna, `nvidia-smi -lms`).
- Metoda odczytu monitorów R4 §5 (DXGI, EDID) — tylko gdy potrzebny `display-fps` bez okna.
- Sondy R6 §5 (smoke `lavfi`, wykrywanie błędów konfiguracji w logu).

## 8. Zakres

### In scope

- Odczyt źródeł i wydań AJN przez `gh api` (bez pobierania binarek).
- Pobranie wydania AJN do EXP z weryfikacją SHA256 i rozpakowanie.
- Pobranie z wydań `hooke007/mpv_PlayKit` paczek z algorytmami interpolacji (bez instalatorów) do EXP, z
  weryfikacją sumy, gdy wydanie ją podaje; przegląd, które algorytmy są nowe wobec OLD, i pomiar tych, które
  działają bez instalacji systemowej.
- RTX Video Super Resolution (`d3d11vpp` z `scaling-mode=nvidia`, R7): czy mpv z AJN go ma, A/B z AJN i z obrazem
  bez upscalera, zgodność z `vf_animejanai` i RIFE. Bez zmian w ustawieniach sterownika; gdy przełącznik VSR w
  panelu NVIDIA jest wyłączony, wykonawca prosi właściciela o włączenie na czas K1.
- Kontrole możliwości i pomiary bez okna (§11).
- Próba docelowego układu bibliotek w `EXP\layout\` (P8).
- Snapshoty stanu systemu i ich porównanie.
- Konfiguracja eksperymentu i pliki `.cmd` dla właściciela do K1.
- `DOC\outcomes\01-engine-and-base.md`; po K2 aktualizacja `../specification.md`, `../masterplan.md`, `../README.md`.

### Out of scope

- Ścieżka VapourSynth + vs-mlrt, SVP na nowym mpv, MVTools.
- Repo, narzędzie instalacyjne, konfiguracja docelowa, skróty docelowe.

### Forbidden

- Jakakolwiek zmiana w OLD; uruchamianie OLD przez agentów (porównania w oknie robi właściciel).
- Uruchamianie instalatora AJN (`Setup .exe`), `mpvnet.exe`/`mpvnet.com` i `benchmark.ps1` (uruchamia mpv.net).
- Instalacje systemowe (CUDA, TensorRT, VC++ redist, `winget`), zmienne środowiskowe, zapisy do rejestru,
  `mpv --register`.
- Okna uruchamiane przez agentów; wszystko z oknem robi właściciel w K1.
- Pobieranie czegokolwiek poza zakresem D1.
- Kopiowanie plików S1–S3 gdziekolwiek; commity; nowe repo; zmiany w kodzie AniShift.

### Deferred

- Ścieżka A (vs-mlrt) — Faza 4b, tylko po osobnej zgodzie.
- Docelowy instalator i lock — etap 02.

### Dozwolone decyzje lokalne

- Dokładne nazwy plików w EXP, skryptów sondujących i logów.
- Liczba powtórzeń pomiaru (minimum 3, mediana).
- Skład klawiszy K1, jeśli silnik nie obsługuje któregoś wariantu (wariant znika, zapis w outcome).
- Wybór narzędzia do rozpakowania `.7z`: 7-Zip z `AniShift\external\` albo `OLD\7z.exe` uruchomiony bez zmian w OLD.

### Zatrzymaj się i wróć po decyzję, gdy

- suma SHA256 pobranego pliku nie zgadza się z polem `digest` wydania;
- AJN wymaga czegokolwiek instalowanego w systemie albo zmiennej środowiskowej;
- snapshot pokazuje ślad spoza kategorii D8 (np. nowy katalog w `%APPDATA%` od forka);
- `mpv.exe` z AJN nie działa bez mpv.net;
- sterownik zgłasza błąd, karta się resetuje albo system traci stabilność;
- potrzebna byłaby zmiana w OLD albo zapis do rejestru.

## 9. Kontekst do przeczytania

Czytaj w tej kolejności:

1. `../specification.md` (całość): ustalenia, zakazy, D1–D8.
2. `../masterplan.md` (sekcje „Rekomendowana droga”, „Sprzeczności”, „Aktualny etap”).
3. R3 (całość), zwłaszcza §3 (budżet) i §5.3 (plan pomiaru AJN).
4. R4 §1, §2, §4, §5 (cele fps, mnożniki, uprząż, komendy).
5. R2 §5–§7 (buildy, VapourSynth, rejestracja) i R6 §2 i §5 (układ, testy bez okna).
6. R1 §2.3 (ustawienia `sub-*` do K1) i §3 (skróty, które właściciel zna).

### Warunkowo

- Jeśli Faza 1 pokaże, że AJN nie ma mnożnika ułamkowego: R4 §2 (opcje interpolacji) przed propozycją D3.
- Jeśli G1 albo G5 zawiedzie: R2 §1 i R4 §5 („Plan pomiaru TensorRT”) przed przeplanowaniem na ścieżkę A.

## 10. Impact scan

- OLD: brak wpływu, o ile nikt go nie uruchamia z innymi opcjami; kontrola mtime plików w Fazie 0 i 9.
- Rejestr i skojarzenia: brak zapisów (`mpv --register` zakazane); kontrola w snapshotach.
- Sterownik NVIDIA: budowa silników TensorRT obciąża GPU; nie uruchamiać pomiarów równolegle z innymi ciężkimi
  zadaniami GPU (np. CrisperWhisper w MangaShift), bo zafałszują liczby.
- AniShift: rezydent może działać; pomiary go nie dotykają. Pliki S3 tylko do odczytu.

## 11. Design eksperymentu

### 11.1 Układ EXP

```text
C:\Users\MattyMroz\tmp\playshift\   EXP: cały eksperyment; usuwany po K2
├── dl\        pobrane archiwa AJN z sumami (tylko odczyt po weryfikacji)
├── ajn\       rozpakowana paczka AJN w oryginalnym układzie (tylko odczyt)
├── layout\    próba docelowego układu: mpv.exe w korzeniu, biblioteki w lib\ (P8); tu też portable_config\ do K1
├── probe\     sondy: snapshot.ps1, gpu.ps1, switch.lua, seek.lua (kod eksperymentu, nie produktu)
├── logs\      logi mpv, nvidia-smi, wyniki snapshotów, listingi
├── shots\     zrzuty A/B z K1
└── k1\        pliki .cmd, które uruchamia właściciel
```

Jeśli `C:\Users\MattyMroz\tmp\` nie istnieje (2026-10-31 nie istniał), wykonawca go tworzy i usuwa razem z EXP,
gdy jest pusty.

### 11.2 Wymagane klatki na sekundę

Źródło 23,976 fps (24000/1001). Przy prędkości 2× filtr dostaje 47,95 kl./s (O3). Mnożnik = cel / (23,976 ×
prędkość); wartości wyliczone.

| Monitor | Cel | Przy 1× | Przy 2× |
|---|---|---|---|
| M27Q 170 Hz | połowa: 85 | ×3,55 | ×1,77 |
| M27Q 170 Hz | pełny: 170 | ×7,09 | ×3,55 |
| G34WQC2 200 Hz | połowa: 100 | ×4,17 | ×2,09 |
| G34WQC2 200 Hz | pełny: 200 | ×8,34 | ×4,17 |

Próg zaliczenia bez okna (szacunek: zapas 30% na render, napisy i system jak w R4 §4): przepustowość wyjścia ≥
1,3 × cel. Dla samego upscalingu przy 2×: ≥ 63 kl./s (1,3 × 47,95). Dla celów: 85 → 111, 100 → 130,
170 → 221, 200 → 260 kl./s.

### 11.3 Szablon pomiaru bez okna

Na podstawie R3 §5.3, z samodzielnym `mpv.exe` (nie mpv.net) i bez konfiguracji:

```text
<layout>\mpv.com --no-config --vo=null --audio=no --untimed --load-scripts=no --cache=no
  --hwdec=nvdec --start=300 --frames=2000
  --vf=@aji:animejanai:lib=<aji.dll>:conf=<conf>:model-dir=<onnx>:rife-model-dir=<rife>:trtexec=<trtexec>:slot=<N>
  --log-file=<EXP>\logs\<id>-<n>.log "<S1>"
```

Dokładne nazwy opcji filtra, numery slotów i sposób ustawienia mnożnika RIFE wynikają z Fazy 1 (dozwolona
adaptacja). Równolegle `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv -lms 500` do
`logs\<id>-gpu.csv`. Wynik przebiegu: liczba klatek wyjścia z logu podzielona przez czas od pierwszej klatki do
końca. Każdy wariant 3 razy, mediana. Pierwszy przebieg każdej pary model + rozdzielczość to budowa silnika:
jego czas zapisać osobno (M9) i nie liczyć do mediany.

### 11.4 Macierz pomiarów

| Id | Co | Źródło | Po co |
|---|---|---|---|
| M0 | samo dekodowanie, bez filtra | S1, S2 | sufit dekodowania |
| M1 | upscaling Balanced 2× | S1, S2 | G1 |
| M2 | upscaling Performance 2× | S1 | zapas na RIFE |
| M3 | Balanced Sharp 2× (jeśli osobny slot) | S1 | potwierdzenie, że koszt jak M1 (R3 §2) |
| M4 | 4× Performance + Performance (jeśli łańcuch istnieje) | S1 | D4 |
| M5 | zmniejszenie do 720p + 2× (jeśli opcja istnieje) | S1 | D4 (R3 §4) |
| M6 | sam RIFE: ×2 oraz mnożniki z §11.2 przy 2×, tylko obsługiwane | S1 | G2 |
| M7 | RIFE → upscaling (Balanced, Performance) dla celów połowy odświeżania przy 2× | S1 | G2, D3 |
| M8 | jak M7 przy 1× (×3,55 i ×4,17) | S1 | D3 (przypadek 1×) |
| M9 | start filtra: czas do pierwszej klatki, zimny (budowa silnika) i ciepły | S1 | seek, pierwsze odtworzenie |
| M10 | przełączenie łańcucha w trakcie (`switch.lua`: zmiana slotu lub mnożnika) i seek o 60 s (`seek.lua`) | S1 | G3 |
| M11 | szczytowy VRAM i obciążenie GPU dla M1 i M7 | S1 | zapas, równoległe użycie GPU |

### 11.5 Bramki decyzji

- **G1. Upscaling:** M1 na S1 ≥ 63 kl./s.
- **G2. Interpolacja:** dla każdego monitora z D2 istnieje wariant M7 (Balanced albo Performance) z celem połowy
  odświeżania przy 2×, który osiąga próg z §11.2.
- **G3. Sterowanie:** silnik przyjmuje mnożnik ułamkowy albo docelowe fps i da się go zmienić w trakcie
  odtwarzania (M10); czas przełączenia i seeku zapisany, a w K1 właściciel ocenia, czy przerwa przeszkadza.
- **G4. Izolacja:** AJN nie wymaga niczego zainstalowanego w systemie (N8); snapshoty pokazują tylko ślady
  kategorii D8.
- **G5. Okno:** w K1 okno otwiera się i gra na monitorach z D2 z `vo=gpu-next`.
- **G6. Obraz:** w K1 właściciel akceptuje wygląd upscalingu, RIFE i napisów AniShift.

Reguły propozycji na K2:

- G1, G4, G5, G6 i G2 PASS → propozycja D6 (a): fork AJN bez VapourSynth, SVP i MVTools usunięte.
- G2 FAIL tylko dlatego, że RIFE w AJN jest wyłącznie całkowity → trzy opcje dla właściciela: RIFE ×2 z
  nierówną kadencją (R3 wariant C), SVP przez VapourSynth jako tryb płynności (wraca VapourSynth i D11), pomiar
  ścieżki A (Faza 4b). Rekomendacja zależy od oceny z K1.
- G2 FAIL z braku wydajności → propozycja: cel połowy odświeżania tylko bez upscalingu AI albo z Performance;
  rozstrzyga D3.
- G1 albo G5 FAIL bez obejścia → AJN odpada jako baza; zatrzymanie i przeplanowanie (Faza 4b albo upstream mpv
  + shadery GLSL, R3 §1 plan B).
- G4 FAIL → zatrzymanie i decyzja właściciela (U6).

### 11.6 Snapshot izolacji

`probe\snapshot.ps1` zapisuje JSON z:

- zmiennymi środowiskowymi użytkownika i maszyny;
- usługami (`Get-Service`), zadaniami harmonogramu (`Get-ScheduledTask`), autostartem (`Win32_StartupCommand`,
  klucze `Run`/`RunOnce` w HKCU i HKLM, folder Autostart);
- podkluczami `HKCU\Software` i kluczami `HKCU\Software\Classes` pasującymi do `mpv`, `io.mpv`, `animejanai`;
- pozycjami najwyższego poziomu z datą modyfikacji w `%APPDATA%`, `%LOCALAPPDATA%`, `%ProgramData%`,
  `%USERPROFILE%`, a dla `%LOCALAPPDATA%\NVIDIA` i `%APPDATA%\NVIDIA` także drugim poziomem;
- procesami, których ścieżka leży w EXP.

Momenty: T0 przed pobraniem, T1 po pomiarach bez okna, T2 po K1, T3 po usunięciu EXP. Różnice klasyfikować:
EXP, ślady kategorii D8 (sterownik i Windows), niezwiązane (inne programy właściciela, rozpoznane po nazwie i
czasie). Pliki tymczasowe w `%TEMP%` sprawdzić osobno po nazwach powiązanych z mpv, AJN i TensorRT.

### 11.7 Konfiguracja K1

`EXP\layout\portable_config\` z minimalnym `mpv.conf` i `input.conf` (kod eksperymentu, nie wzór dla etapu 03):

- `mpv.conf`: `vo=gpu-next`, `hwdec` zgodnie z zaleceniem AJN, `video-sync=display-resample`, `keep-open=yes`,
  zrzuty do `EXP\shots`, linie `sub-*` skopiowane z `OLD\portable_config\mpv.conf` (R1 §2.3) i
  `sub-fonts-dir` wskazujące `OLD\portable_config\fonts` (odczyt);
- `input.conf` z klawiszami, które właściciel zna:

| Klawisz | Akcja w K1 |
|---|---|
| `Ctrl+1` … `Ctrl+6` | upscaling: wyłączony, Balanced, Balanced Sharp, Performance, 4× (jeśli jest), 720p + 2× (jeśli jest) |
| `~` | interpolacja wyłączona |
| `!` | RIFE ×2 |
| `@` | RIFE do połowy odświeżania bieżącego monitora przy bieżącej prędkości (`switch.lua`; tylko gdy G3) |
| `#` | RIFE do pełnego odświeżania (tylko gdy G3) |
| `\` / `BS` | prędkość 2× / 1× (jak dziś) |
| `Ctrl+7` | `target-prim=display-p3` włącz/wyłącz (D5) |
| `I` | statystyki na stałe (strona 1: klatki zgubione i opóźnione) |
| `Ctrl+s` | `screenshot window` do `EXP\shots` |

Pliki `k1\k1-s1.cmd`, `k1\k1-s2.cmd`, `k1\k1-s3.cmd` uruchamiają `EXP\layout\mpv.exe` z odpowiednim plikiem.
Przed oddaniem właścicielowi każdy konfig sprawdzić bez okna: `--vo=null --frames=50` z logiem i brak
komunikatów `Error parsing option`, `setting option … failed`, `Lua error` (R6 §5).

## 12. Docelowe drzewo PlayShift (do akceptacji w K2)

Oznaczenia: **T** = w gicie; **P** = pobierane przez `setup` według locka, ignorowane przez git; **S** = stan
maszyny albo użytkownika, ignorowany przez git; `setup` nigdy nie nadpisuje `portable_config/state/`. Nazwy
narzucone przez narzędzia zostają (`portable_config` wymaga mpv, `.github` GitHub). Drzewo zakłada rekomendacje
D7 (repo jest instalacją) i D9 (osobne repo); wariant z D6 zaznaczony przy `lib/`.

### 12.1 Repo, czyli zawartość klonu

```text
PlayShift/
├── .github/workflows/ci.yml   T  CI na windows-latest: ruff, mypy, pytest, luacheck, smoke mpv bez okna
├── .gitignore                 T  biała lista: ignoruje wszystko poza plikami T
├── .pre-commit-config.yaml    T  hooki jak w AniShift (ruff, commit-msg)
├── .luacheckrc                T  lint Lua (globalne `mp`)
├── AGENTS.md                  T  reguły dla agentów: bramki, izolacja (U6), zakazy, mapa katalogów
├── README.md                  T  instalacja, aktualizacja, rejestracja, skróty, lista dopuszczalnych śladów (D8)
├── THIRD-PARTY.md             T  licencje obcych plików trzymanych w repo
├── pyproject.toml, uv.lock    T  narzędzie `playshift` (Python przez uv; zależności tylko dev)
├── deps.toml                  T  co instalujemy i skąd, polityka aktualizacji (pisze człowiek)
├── deps.lock.json             T  wersja, URL, sha256, rozmiar i pliki każdego składnika (generuje `playshift upgrade`)
├── setup.cmd                  T  dwuklik: `uv run playshift setup`, cache i Python uv kierowane do var\ tylko dla tego procesu
├── update.cmd                 T  dwuklik w klonie używanym: `git pull --ff-only`, potem setup
├── docs/work/<nn>-<slug>/     T  plany, raporty, outcome'y po polsku (przeniesione z AniShift DOC w etapie 02)
├── playshift/                 T  pakiet narzędzia: cli.py, deps.py, install.py, doctor.py
├── tests/                     T  pytest: lock i instalator (zła suma, path traversal, blokada pliku), smoke mpv bez okna
├── scripts/
│   ├── hooks/                 T  check_commit_msg.py (scope z zamkniętej listy)
│   └── tmp/                   T  jednorazowe skrypty, np. migracja z OLD; usuwane po uruchomieniu
└── portable_config/           T  konfiguracja mpv (nazwa wymuszona przez mpv; katalog musi leżeć obok mpv.exe)
    ├── mpv.conf               T  ustawienia główne
    ├── input.conf             T  skróty i menu `#!` w jednym pliku (dziś input_uosc.conf)
    ├── profiles.conf          T  profile warunkowe: cele fps per monitor, deband, HDR
    ├── script-opts/           T  opcje skryptów: uosc.conf, thumbfast.conf, uosc-pl.json (poprawki tłumaczeń)
    ├── scripts/               T  własne skrypty Lua i zmienione kopie obcych z nagłówkiem źródła
    └── vs/                    T  skrypty .vpy — tylko gdy VapourSynth zostaje (D6 b albo SVP)
```

### 12.2 Instalacja, czyli ten sam katalog po `setup` i używaniu

```text
PlayShift/                     (wszystko z 12.1, plus:)
├── mpv.exe, mpv.com           P  build mpv z D6; muszą leżeć w korzeniu, obok portable_config/ (O2)
├── bin/                       P  programy pomocnicze: yt-dlp.exe, deno.exe (obok yt-dlp, O7), 7zr.exe (dla setup)
├── lib/                       P  biblioteki uruchomieniowe i modele
│   ├── aji/                   P  wariant D6 (a): aji.dll, runtime TensorRT dla sm120, trtexec [?] P8
│   ├── models/                P  modele ONNX: AnimeJaNai (upscaling), RIFE
│   └── python/                P  tylko gdy VapourSynth zostaje: Python 3.14 embed + VapourSynth R81 + wtyczki
├── portable_config/
│   ├── scripts/uosc/          P  upstream uosc, niezmieniony
│   ├── scripts/thumbfast.lua  P  upstream thumbfast
│   ├── shaders/               P  shadery GLSL z upstreamu, jeśli etap 04 jakieś zostawi (własne byłyby T)
│   ├── fonts/                 P  fonty z paczki uosc i Officina z prywatnego repo MattyMroz/fonts
│   ├── state/                 S  watch_later/, historia, saved-props.json, dziennik zdarzeń (etap 06)
│   └── cache/                 S  cache mpv: shadery, ICC; można usunąć bez utraty danych
└── var/                       S  stan narzędzia `playshift`; można usunąć, `setup` odtworzy
    ├── cache/                 S  archiwa po sha256 (bieżąca i poprzednia wersja, powrót bez sieci), cache uv, silniki TensorRT [?]
    ├── tmp/                   S  staging pobierania i rozpakowania; pusty po każdej operacji
    └── installed.json         S  co zainstalowano: składnik → wersja → pliki z sha256
```

Uwagi do drzewa:

- **[?] P8 (ta faza):** czy `aji.dll` i runtime TensorRT działają z `lib\aji\`. Jeśli nie, lądują w korzeniu obok
  `mpv.exe`, a `lib\aji\` znika. Wynik wpisać do drzewa przed K2.
- **[?] silniki TensorRT:** gdzie AJN je zapisuje i czy da się to ustawić (Faza 1 i 4). Docelowo `var\cache\`;
  jeśli tylko obok modeli, to `lib\models\` staje się katalogiem z danymi zmiennymi i trzeba to opisać w README.
- **[?] `bin\yt-dlp.exe`:** czy `ytdl_hook` przyjmie ścieżkę z `script-opts` (`ytdl_path`) poza katalogiem
  konfiguracji (R2 §8). Sprawdza etap 02; zapas: yt-dlp i deno w korzeniu obok `mpv.exe`.
- **`var\` zamiast `cache\` i `tmp\` w korzeniu (R6 §2.2):** jeden katalog na cały stan narzędzia, zgodnie z
  konwencją linuksową (`var/cache`, `var/tmp`); różnica wobec R6 do akceptacji w K2.
- **`setup.cmd` i uv:** zmienne `UV_CACHE_DIR` i `UV_PYTHON_INSTALL_DIR` ustawiane tylko w procesie `.cmd`
  kierują pobrania uv do `var\cache\`, więc narzędzie nie zostawia śladów poza katalogiem [W]. `uv` jest
  wymaganiem wstępnym, które właściciel już ma.
- **Dwa klony (D7):** roboczy `C:\Users\MattyMroz\Desktop\PROJECTS\PlayShift\` (agenci, CI; składniki AI
  opcjonalne) i używany `C:\Users\MattyMroz\Videos\mpv\` po odsunięciu OLD (etap 05).
- **Odrzucony wariant `src/` + budowanie do osobnego katalogu (D7 b):** dwie kopie konfiguracji i krok
  kopiowania; zmiana zrobiona w trakcie oglądania ginie albo wymaga ręcznego przeniesienia (R6 §2.3).

### 12.3 Co z OLD trafia gdzie (podgląd migracji z etapów 03 i 05)

| W OLD | W PlayShift |
|---|---|
| `portable_config/mpv.conf`, `profiles.conf`, `script-opts.conf` | `portable_config/` po oczyszczeniu (R1 §9); usunięte opcje mpv ≥0.39 (R1 §5) |
| `portable_config/input_uosc.conf` | `portable_config/input.conf` (bez `input-conf=`) |
| `portable_config/_cache/watch_later/`, `saved-props.json` | `portable_config/state/` (jednorazowy skrypt, etap 05) |
| `portable_config/_cache/shader/`, `cache/`, `ambient-blur.json` | nie przenosić (cache odtworzy się sam) |
| `portable_config/scripts/` | uosc i thumbfast z upstreamu; SmartCopyPaste, `image-positioning`, `*TEST*`, `detect-image` usunięte (masterplan) |
| `portable_config/shaders/` | decyzja w etapie 04 (A/B); 21 niepodpiętych usuniętych |
| `portable_config/vs/`, `vapoursynth64/`, Python i VapourSynth w korzeniu | `portable_config/vs/` i `lib/python/` tylko przy VapourSynth (D6); inaczej usunięte |
| `portable_config/fonts/` | Officina z prywatnego repo (odmiana Book); LXGW WenKai usunięty |
| `yt-dlp.exe` | `bin/yt-dlp.exe` (P) |
| `installer/`, `mpv-install.bat`, `mpv-uninstall.bat`, `mpv-document.ico` | usunięte; rejestracja przez `mpv --register` (D15) |
| `manual.pdf`, `LICENSE.MD`, resztki VapourSynth portable, `7z.exe` | usunięte (`7zr.exe` w `bin/`) |

## 13. Plan wykonania

Wykonawca: jeden agent dla faz bez okna (0–6, 8–9). Właściciel: K1 i K2. Orkiestrator: odbiór dowodów,
integracja, aktualizacja dokumentów po K2.

### Faza 0 — Preflight

**Cel:** spełniona bramka wejścia i zapisany punkt odniesienia.

**Działania:**

1. Potwierdzić odpowiedzi D1, D2 i ścieżki S1–S3 (§5).
2. Sprawdzić wolne miejsce na C:.
3. Zapisać do `EXP\logs\old-baseline.txt` listę plików `OLD\portable_config\*.conf`, `saved-props.json` i
   `mpv.exe` z rozmiarem, datą i SHA256.
4. Utworzyć EXP według §11.1 i zrobić snapshot T0 (§11.6).

**Kontrola:** pliki S1–S3 istnieją; T0 zapisany; `old-baseline.txt` zapisany.

**Gate:** wszystkie punkty §5 spełnione.

### Faza 1 — Odczyt źródeł AJN, bez pobierania

**Cel:** wiedzieć, co sprawdzać, zanim cokolwiek zostanie pobrane.

**Działania:** przez `gh api` przeczytać w wydaniu z dnia wykonania i w repo forka:

1. konfigurację slotów (`aji_conf.cpp`, `add_builtin_slots`): modele upscalingu, `Sharp`, łańcuch 4×,
   zmniejszanie przed upscalingiem;
2. RIFE: modele, mnożnik całkowity czy ułamkowy, docelowe fps, wykrywanie cięć scen, kolejność z upscalingiem;
3. opcje `vf_animejanai` i możliwość zmiany w locie (`vf-command`, ponowne `vf set`), wybór łańcucha po
   `nominal_fps`;
4. miejsce zapisu silników TensorRT i czy da się je ustawić; rolę `trtexec`;
5. sposób ładowania bibliotek TensorRT przez `aji.dll` (ścieżka względna, katalog DLL);
6. konfigurację buildu forka: VapourSynth, `--register`, wersja bazowa upstream;
7. zasoby wydania: nazwy, rozmiary, pole `digest`, `manifest.json` i `packs.json`;
8. pliki licencji.

**Kontrola:** tabela „pytanie → odpowiedź ze źródła (plik, linia) → co zmierzyć” w szkicu outcome.

**Gate:** wiadomo, które zasoby pobrać i które warianty macierzy §11.4 istnieją. Brak mnożnika ułamkowego nie
zatrzymuje etapu, tylko trafia do outcome jako ryzyko G2.

### Faza 2 — Pobranie i weryfikacja

**Cel:** pakiet AJN w EXP, sprawdzony i nieuruchomiony.

**Działania:**

1. Pobrać do `EXP\dl\` tylko zasoby wskazane w Fazie 1 (bazowa paczka z `mpv.exe` i `aji`, `trt-runtime`,
   `trt-sm120`, `rife`).
2. Porównać SHA256 każdego pliku (`Get-FileHash`) z polem `digest` z API.
3. Rozpakować do `EXP\ajn\`. Nie uruchamiać instalatorów ani mpv.net.
4. Zapisać listing z rozmiarami do `logs\ajn-tree.txt`.

**Kontrola:** wszystkie sumy zgodne; listing zapisany.

**Gate:** niezgodna suma → stop (§8).

### Faza 3 — Możliwości i układ bibliotek, bez okna

**Cel:** wiedzieć, co potrafi `mpv.exe` z AJN i gdzie mogą leżeć jego biblioteki.

**Działania:**

1. `mpv.com --version`, `--vo=help`, `--vf=help`, `--list-options` → zapisać: wersja bazowa, FFmpeg,
   libplacebo, obecność `animejanai`, `vapoursynth`, `gpu-next`, `register`, `autocreate-playlist`,
   `save-watch-history`.
2. Smoke: `mpv.com --no-config --vo=null --ao=null --frames=5 "av://lavfi:testsrc=duration=1"`, kod wyjścia 0.
3. **P8:** zbudować `EXP\layout\`: `mpv.exe` i `mpv.com` w korzeniu, `aji` i runtime TensorRT w `lib\aji\`,
   modele w `lib\models\`; krótki przebieg M1 (200 klatek). Jeśli biblioteki się nie załadują, przenieść runtime
   do korzenia i powtórzyć. Zapisać, który układ działa.

**Kontrola:** log z wynikami 1–3.

**Gate:** filtr `animejanai` obecny i krótki przebieg na S1 kończy się klatkami wyjścia.

### Faza 4 — Pomiary

**Cel:** macierz §11.4 wypełniona.

**Działania:** przebiegi według §11.3 dla każdego obsługiwanego wariantu; sondy `switch.lua` i `seek.lua` dla M10
(zapis czasu przed komendą i przy następnej klatce do logu); `nvidia-smi` dla M11. Nie uruchamiać innych
ciężkich zadań GPU w tym czasie.

**Kontrola:** `logs\results.csv` (id, źródło, wariant, przebieg, klatki, czas, kl./s, VRAM szczyt, GPU %), mediany
w szkicu outcome.

**Gate:** M0–M2, M6, M7 i M9–M11 zmierzone (M3–M5, M8 tylko jeśli silnik je obsługuje).

### Faza 4b — Ścieżka A (warunkowa)

Tylko gdy G1 albo G5 zawiedzie albo właściciel o to poprosi, i tylko po jego osobnej zgodzie na pobranie
(około 2,7 GB vs-mlrt oraz VapourSynth R81 i build mpv nowszy niż 2026-04-10). Wymaga rewizji tego planu na
podstawie R4 §5 („Plan pomiaru TensorRT”) i R2 §7; nie wykonywać bez niej.

### Faza 5 — Izolacja po pomiarach

**Działania:** snapshot T1, porównanie z T0 według §11.6; sprawdzenie, że żaden proces z EXP nie działa.

**Kontrola:** `logs\isolation-t1.md` z klasyfikacją różnic.

**Gate:** ślad spoza kategorii D8 → stop (§8).

### Faza 6 — Przygotowanie K1

**Działania:** konfiguracja i pliki `.cmd` według §11.7; walidacja konfiguracji bez okna; krótka instrukcja dla
właściciela w odpowiedzi orkiestratora (bez nowego pliku dokumentu).

**Kontrola:** log walidacji bez błędów konfiguracji i skryptów.

**Gate:** wszystkie `k1-*.cmd` przechodzą walidację bez okna.

### Faza 7 — K1: ocena właściciela w oknie

```text
Uruchom: EXP\k1\k1-s1.cmd (potem k1-s2.cmd i k1-s3.cmd); obok obecny odtwarzacz z Videos\mpv.
Zrób:
  1. Okno: przeciągnij na każdy monitor z D2, pełny ekran. Czy obraz gra? (G5)
  2. Upscaling: pauza na scenie z wyraźnymi liniami (S1, około 300 s), przełączaj Ctrl+1…Ctrl+6, zrób Ctrl+s
     przy każdym. Który wygląda najlepiej? Czy 4× daje coś ponad Sharp? (D4)
  3. Płynność przy 2×: \ , potem @ z Ctrl+2, potem @ z Ctrl+4; po około 2 minutach akcji odczytaj z I liczbę
     zgubionych i opóźnionych klatek. Potem # bez upscalingu. Porównaj w starym odtwarzaczu * (SVP 170) i _
     (RIFE 1080p ×2). Zwróć uwagę na cięcia scen, napisy wtopione w obraz i szybki ruch. (D3, D6)
  4. Prędkość 1×: BS i znów @. Ile trwa przerwa przy przełączeniu? (G3)
  5. Seek: strzałki w trakcie RIFE. Jak długo obraz stoi?
  6. Kolor: Ctrl+7 włącz/wyłącz; sprawdź w menu monitora, czy jest tryb sRGB. Co wolisz? (D5)
  7. Napisy: k1-s3.cmd i ten sam odcinek w starym odtwarzaczu. Czy font, rozmiar i położenie są takie same? (I4)
Oczekiwany rezultat: okno działa; jest wariant płynny przy 2× bez gubienia klatek; napisy wyglądają jak dziś.
Zwróć uwagę na: artefakty RIFE, migotanie tekstur, zmiękczenie obrazu, różnice kolorów.
Przekaż wynik jako: krótka lista w czacie, punkt po punkcie (OK / nie / uwaga) z odczytami liczników;
  zrzuty zostają w EXP\shots.
```

**Gate:** odpowiedzi do punktów 1–7 zapisane w outcome.

### Faza 8 — Izolacja po K1

**Działania:** snapshot T2 po zamknięciu wszystkich okien; porównanie z T0; kontrola procesów z EXP.

**Kontrola:** `logs\isolation-t2.md`; lista śladów do D8.

### Faza 9 — Outcome, K2, sprzątanie

**Działania:**

1. Napisać `DOC\outcomes\01-engine-and-base.md`: wersje, sumy, liczby (mediany), werdykty G1–G6, odpowiedzi K1,
   mapa śladów, wynik P8 i silników TensorRT, drzewo §12 z rozstrzygniętymi `[?]`, propozycja D3–D8 według
   reguł §11.5 z ryzykami.
2. **K2:** orkiestrator przedstawia właścicielowi propozycję (krótko, w czacie, z odsyłaczem do outcome);
   właściciel rozstrzyga D3–D8 i zatwierdza drzewo.
3. Po K2: decyzje przenieść w specyfikacji do „Ustaleń” (usunąć z otwartych), zaktualizować masterplan (01
   accepted, 02 current, wpis w historii zmian kierunku), zaktualizować `DOC\README.md`.
4. Usunąć EXP (i pusty `C:\Users\MattyMroz\tmp\`), chyba że właściciel jawnie zostawi go do etapu 04; snapshot
   T3 i porównanie z T0; porównanie OLD z `old-baseline.txt` (przed usunięciem EXP skopiować je do outcome).

**Kontrola:** T3 bez śladów spoza D8; OLD identyczny z baseline.

**Gate:** warunki końcowe §3 spełnione.

## 14. Strategia dowodu

- Wydajność: pomiar bez okna, 3 przebiegi, mediana; ostateczny werdykt płynności z liczników mpv w K1. Liczby
  autora AJN i estymacje R3/R4 służą tylko do porównania.
- Możliwości silnika: odczyt źródła (Faza 1) potwierdzony uruchomieniem (Fazy 3–4).
- Izolacja: snapshoty T0–T3 i kontrola procesów; dowód ograniczony do sprawdzanych miejsc (§11.6), nie do całego
  systemu.
- Jakość obrazu, kolor, napisy: wyłącznie ocena właściciela (K1); bez metryk zastępczych.
- OLD: SHA256 kluczowych plików przed i po.
- Review: outcome przed K2 przegląda jeden recenzent innego modelu niż wykonawca (zasada krzyżowa AniShift),
  pod kątem zgodności liczb z logami i reguł §11.5.

## 15. Ryzyka i reakcje

- **Okno nie otwiera się na RTX 50 (issue #200, R3 §6):** w K1 próbować `gpu-api=d3d11`, potem obejście z issue;
  bez okna G5 FAIL i przeplanowanie.
- **Rozrzut pomiarów** (R3 §5.2 widział ±40% w innej uprzęży): więcej powtórzeń, zamknięte ciężkie programy GPU;
  wynik „na granicy” rozstrzyga K1, nie rachunek.
- **Budowa silnika przerwana albo uszkodzona** (problem sprzed 3.8.1, R3 §6): usunąć silnik z cache EXP i
  zbudować ponownie; zapisać w outcome.
- **AJN zapisuje poza EXP:** stop według §8; sprawdzić, czy da się to ustawić opcją; bez tego decyzja
  właściciela (U6).
- **Nowe wydanie AJN w trakcie etapu:** zostać przy wersji pobranej w Fazie 2; zmiana wersji tylko z
  powtórzeniem pomiarów.
- **Napisy AniShift wyglądają inaczej w forku** (fork zmienia renderowanie napisów, R3 §6): zapisać różnicę;
  wpływa na D6 i I4.

## 16. Lokalna adaptacja i materialna zmiana

Wykonawca może sam: dopasować składnię opcji filtra i numery slotów do Fazy 1, pominąć wariant nieobsługiwany
przez silnik, zmienić nazwy plików w EXP, zwiększyć liczbę powtórzeń.

Przeplanowanie i powrót do orkiestratora: pomiar ścieżki A, zmiana bazy na inną niż AJN, każda potrzeba zapisu
poza EXP i DOC, każda zmiana progów §11.2 i reguł §11.5.

## 17. Definition of Done

- [ ] Warunki końcowe §3 spełnione.
- [ ] Liczby w outcome zgadzają się z logami w EXP (sprawdzone przez recenzenta przed usunięciem EXP).
- [ ] Zakazy §8 dotrzymane; OLD bez zmian.
- [ ] K1 i K2 wykonane; decyzje D3–D8 w specyfikacji jako ustalenia.
- [ ] Ślady w systemie tylko z kategorii zaakceptowanej w D8.

## 18. Kontrakt wyniku

```text
status
wersja AJN i sumy SHA256
wyniki Fazy 1 (tabela pytań i odpowiedzi ze źródeł)
macierz pomiarów (mediany) i werdykty G1–G6
odpowiedzi właściciela z K1
mapa śladów T0–T3 i ich klasyfikacja
wynik P8 i miejsce silników TensorRT
drzewo §12 z rozstrzygniętymi [?]
propozycja i ostateczne decyzje D3–D8
odchylenia od planu i odkrycia materialne
stan EXP i OLD
rekomendowany następny krok (plan etapu 02)
```

## 19. Pytania

Wszystkie pytania są w `../specification.md`, „Otwarte decyzje właściciela”. Ten plan wymaga D1 i D2 przed startem
i rozstrzyga D3–D8 w K2.
