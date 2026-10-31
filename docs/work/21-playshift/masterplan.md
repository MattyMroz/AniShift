---
kind: masterplan
status: active
updated: 2026-10-31
---

# Masterplan: PlayShift

## Cel końcowy

Właściciel ogląda wszystko w PlayShift: przenośnym odtwarzaczu na mpv, który ma jego dotychczasowe skróty bez
usterek, polski interfejs, upscaling AI i interpolację dobraną do prędkości 2× i monitora, instaluje się jednym
poleceniem, aktualizuje sam i nie zostawia śladów w Windows. Stary `Videos\mpv` jest usunięty, a AniShift
dostaje od odtwarzacza fakt „obejrzane”, jeśli właściciel przyjmie D16.

## Źródła celu i ograniczeń

- `specification.md` — ustalenia (U), wymagania (F, N), zakazy (Z), otwarte decyzje D1–D18.
- `research/01-local-mpv.md` … `06-architecture-integration.md` (R1–R6) — fakty, pomiary, rekomendacje.
- `AGENTS.md` AniShift (konwencje), `C:\Users\MattyMroz\.claude\CLAUDE.md` (zero legacy, nazwy katalogów).

## Aktualny zaakceptowany stan

- Działa i zostało zaakceptowane: nic po stronie PlayShift. Właściciel ustalił cel, zasady i zakazy (U1–U14).
- Gotowe: sześć raportów researchu z 2026-10-31; lokalne pomiary RIFE ncnn, SVP, MVTools i shaderów GLSL (R3 §5,
  R4 §5).
- Pozostaje niepewne: czy AnimeJaNai, RIFE TensorRT albo algorytmy z `mpv_PlayKit` w ogóle poprawiają obraz w
  ocenie właściciela (U15), a jeśli tak, czy działają w czasie rzeczywistym przy 2× z celem fps dobranym do
  prędkości i monitora. Od tego zależy baza, obecność VapourSynth i drzewo katalogów.
- Blokery: brak. D1 rozstrzygnięte (tak); D2 bez odpowiedzi, więc etap 01 mierzy oba monitory.

## Rekomendowana droga

Propozycja zbudowana z raportów. Nie wiąże, dopóki właściciel nie rozstrzygnie wskazanej decyzji. Wiersze baza,
upscaling, interpolacja i kolor to kandydaci do porównania (U15): zostają tylko, jeśli właściciel uzna je za
lepsze od obecnego obrazu.

| Obszar | Rekomendacja | Źródło | Decyzja |
|---|---|---|---|
| Baza mpv i AI | `mpv.exe` z forka AnimeJaNai: natywny filtr TensorRT, RIFE przed upscalingiem, bez VapourSynth i Pythona | R3 §1, R2 §1 (ścieżka B) | D6 po etapie 01 |
| Upscaling | AnimeJaNai HD V3.1 Balanced, tylko 2×; wariant `Sharp` zamiast 4× | R3 §1, §4 | D4 |
| Interpolacja | RIFE TensorRT w natywnej rozdzielczości źródła, potem upscaling; cel połowy odświeżania, liczony z prędkości | R4 §1, §4 | D3 |
| Kolor | 8 bit z ditheringiem, deband przy niskim bitrate, decyzja o nasyceniu po A/B | R4 §3 | D5 |
| Synchronizacja | `video-sync=display-resample`; profil `[vsync_auto]` usunięty w obecnej postaci | R1 §6.1, R4 §1 | etap 04 |
| UI | upstream uosc 5.13 jako minimalny HUD, polski `pl.json` + własny plik poprawek; thumbfast | R5 §3 | D12 |
| Pliki | uosc `delete-file-next` z Koszem; `--autocreate-playlist`; wbudowana historia | R5 §4.2 | D13 |
| Linki | wbudowany `ytdl_hook` + yt-dlp nightly + `deno`; wklejanie przez właściwość `clipboard` | R2 §6, §8, R5 §4.4 | D10 |
| Repo | osobne, prywatne `MattyMroz/PlayShift`; repo jest instalacją; dwa klony | R6 §1, §2.2 | D7, D9 |
| Instalator | narzędzie `playshift` (Python przez uv, stdlib): `setup`, `upgrade`, `doctor`; `deps.toml` + `deps.lock.json` z SHA256; aktualizacja automatyczna w czasie pracy odtwarzacza (U7, D18) | R6 §3 | etap 02 |
| Rejestracja | wbudowane `mpv --register` (HKCU) na jawne życzenie; nazwa `mpv.exe` | R2 §7 | D15 |
| AniShift | odtwarzacz dopisuje fakty o postępie do `state/progress.jsonl`; AniShift dopasowuje odcinek i aktualizuje MAL | R6 §4.2, R5 §5 | D16 |

Najpierw usuwamy: MVTools (nie nadąża, R4 §5), RIFE ncnn (60–70 kl./s, R4 §1), SmartCopyPaste
(`clipboard` w mpv 0.40, R5 §4.4), `image-positioning.lua` (wbudowany `positioning.lua`, R5 §4.6), fork uosc
5.0.0, 21 niepodpiętych shaderów, martwe skrypty `*TEST*`, resztki VapourSynth portable, chiński font LXGW
(R1 §9). VapourSynth i SVP zostają tylko wtedy, gdy etap 01 pokaże, że są potrzebne (D6).

## Sprzeczności w researchu i rozstrzygnięcia

- **Budżet GPU (R3 §3 wobec R4 §4).** R3 liczy budżet jako 1000 ms GPU na sekundę, R4 jako 700 ms (30% zapasu na
  render, napisy i system). Ten sam łańcuch „RIFE → upscaling Balanced” wychodzi w R3 „na granicy, mieści się”, a
  w R4 „ponad budżet”. **Rozstrzygnięcie:** estymacje nie decydują. Etap 01 mierzy przepustowość bez okna z
  progiem 1,3× zapotrzebowania (zapas R4; szacunek), a ostateczny werdykt daje odtwarzanie w oknie bez
  gubionych klatek (N1).
- **Cel interpolacji (R3 §3 wariant C wobec R4 §4).** R3 proponuje RIFE ×2 (96 fps przy 2×) i `display-resample`
  do 170 Hz. R4 pokazuje, że 96 fps na 170 Hz daje nierówną kadencję, a zmiana tempa o około 11% przekracza
  `video-sync-max-video-change`, więc `display-resample` tego nie wyrówna. **Rozstrzygnięcie:** rekomendacja R4
  (cel połowy odświeżania, mnożnik ułamkowy). Wymaga od silnika mnożnika ułamkowego; etap 01 to sprawdza. Decyzja:
  D3.
- **Monitor (R1, R3, R5 wobec R4 §3).** Trzy raporty zakładały jeden monitor 170 Hz; R4 zmierzył dwa, z głównym
  3440×1440 @ 200 Hz. **Rozstrzygnięcie:** specyfikacja używa danych R4; wybór monitora to D2. Uwaga [W]: R4 §4
  szacuje „34% więcej pikseli” dla 3440×1440, ale obraz 16:9 na pełnym ekranie 21:9 zajmuje 2560×1440 z pasami po
  bokach, więc dla anime różnica to głównie 200 wobec 170 Hz. Etap 01 mierzy oba cele.
- **Wersja mpv (R5 §1 wobec R2 §5, R6 §2.1, R3 §1).** R5 rekomenduje stabilne mpv 0.41.0, R2 codzienny build
  shinchiro, R3 fork AnimeJaNai. VapourSynth R74+ działa dopiero z buildem nowszym niż 2026-04-10, czyli nie z
  0.41.0 (R2 §5, R6 §2.1). **Rozstrzygnięcie:** stabilne 0.41.0 odpada, jeśli VapourSynth zostaje; wybór między
  forkiem a buildem upstream to D6 po etapie 01.
- **Aktualizacja yt-dlp (R2 §6 wobec R6 §3.3).** R2: `yt-dlp -U` przy starcie w tle. R6: tylko przez lock.
  **Rozstrzygnięcie:** właściciel (U7): aktualizacje są automatyczne; yt-dlp aktualizuje się sam, a zakres
  pozostałych zależności i ochrona przed regresją to D18.
- **Model powrotu do poprzedniej wersji (R2 §6 wobec R6 §3.4).** R2: katalog na każdą wersję obok starej i
  przełączenie. R6: jeden katalog, lock w gicie, archiwa w cache po SHA256, `git revert` + `setup`.
  **Rozstrzygnięcie:** droga R6 jako rekomendacja etapu 02 (mniej pojęć, jedno źródło prawdy); warunek N6
  zapewnia staging w `var/tmp/` i odmowa przy zablokowanych plikach. Gdyby test N6 jej nie spełnił, wraca wariant
  R2.
- **`VSSCRIPT_PATH` (R6 §2.1 wobec R2 §7 i U6).** R6 rekomenduje zmienną użytkownika ustawianą przez `setup`; R2
  wymienia też launcher i `--register-rpath`. **Rozstrzygnięcie:** U6 spycha zmienną globalną na sam koniec
  (D11). Gdy D6 wybierze bazę bez VapourSynth, problem znika.
- **Skojarzenia (R6 §4.2 wobec U8).** R6 zakłada, że skojarzenia ustawia instalator. **Rozstrzygnięcie:** U8 —
  osobne, jawne polecenie (F22).
- **Miniatury (R2 §1 wobec R5 §4.1).** R2: thumbfast albo `thumb_engine` z PlayKit; R5: thumbfast.
  **Rozstrzygnięcie:** thumbfast (upstream, MPL-2.0, utrzymywany; `thumb_engine` to fork o niejasnym statusie
  licencji).
- **Samoaktualizacja uosc (R5 §3 wobec R2 §6, R6 §2.2).** R5 wymienia komendę `update` jako zaletę; R2 i R6
  aktualizują uosc z locka. **Rozstrzygnięcie:** lock; komenda `update` bez klawisza (Z4).
- **Kontrakt z AniShift (R5 §5 wobec R6 §4.2).** R5: zdarzenie „ścieżka, czas, procent” i tożsamość w tagach MKV;
  R6: `progress.jsonl` z rozmiarem pliku i powodem wpisu, bez tagów. Taiga z R5 to stały proces w tle, co kłóci
  się z duchem U6. **Rozstrzygnięcie:** szczegóły kontraktu należą do etapu 06 i workstreamu 22; kierunek to D16.
- **Pomiar AnimeJaNai (R3 §5.3).** R3 proponuje `benchmark.ps1`, który uruchamia `mpvnet.com`. **Rozstrzygnięcie
  [W]:** etap 01 używa samodzielnego `mpv.exe` z `--no-config`, żeby nie uruchamiać mpv.net i nie tworzyć jego
  ustawień poza katalogiem eksperymentu.

## Etapy

### 01. Porównanie metod poprawy obrazu i decyzja bazy

- rezultat: zmierzone na RTX 5090 i plikach właściciela liczby dla kandydatów (AnimeJaNai: przepustowość
  upscalingu i RIFE dla celów z D2/D3, VRAM, budowa silnika, czas startu i przełączenia filtra; algorytmy
  interpolacji z wydań `mpv_PlayKit`), możliwości silnika (mnożnik ułamkowy, przełączanie w locie, umiejscowienie
  bibliotek), mapa śladów w systemie; ocena właściciela w oknie: A/B każdego kandydata z obecnym obrazem,
  płynność, napisy; werdykt, które metody wchodzą (U15), także „żadna”; decyzje D3–D8; zatwierdzone drzewo
  katalogów.
- zależności: pliki referencyjne (domyślnie z researchu, właściciel może wskazać inne).
- warunek wyjścia: `outcomes/01-engine-and-base.md` z liczbami; właściciel rozstrzygnął D3–D8 i zatwierdził
  drzewo; specyfikacja i masterplan zaktualizowane; katalog eksperymentu usunięty albo jawnie zostawiony do etapu
  04.
- status: current

### 02. Repo i przenośna instalacja bazowa

- rezultat: repo według D9; narzędzie `playshift` (`setup`, `upgrade`, `doctor`) z lockiem SHA256; instalacja
  bazy z D6, `bin/` (yt-dlp, deno, 7zr), uosc i thumbfast z polskim UI; minimalna konfiguracja; odtwarza plik i
  link; CI bez okna; dokumenty workstreamu przeniesione z AniShift do nowego repo i usunięte z AniShift.
- zależności: 01, D9, D10, D11.
- warunek wyjścia: świeży klon + `setup.cmd` daje działający odtwarzacz (smoke bez okna PASS); `upgrade` i powrót
  do poprzedniej wersji zademonstrowane (N5, N6); test izolacji N4 PASS; właściciel raz otwiera plik i link.
- status: planned

### 03. Konfiguracja, skróty i interfejs

- rezultat: konfiguracja z `Videos\mpv` przeniesiona i oczyszczona (R1 §9); kontrakt skrótów F13–F16 z
  naprawionymi usterkami; polski interfejs w formie z D12; usuwanie pliku (D13); obrót, odbicia, zoom; poprawiony
  font napisów (odmiana Book); sprawdzone wyświetlanie napisów AniShift (I4); domyślne ścieżki lektor + napisy
  ocenione przez właściciela.
- zależności: 02, D12, D13, D14.
- warunek wyjścia: automatyczne kontrole konfiguracji i skryptów bez okna PASS (N9); właściciel przechodzi
  scenariusz skrótów i akceptuje wygląd (S1, S6).
- status: planned

### 04. Jakość obrazu: upscaling, interpolacja, kolor

- rezultat: metody przyjęte w etapie 01 (U15) pod rodzinami `Ctrl+cyfry` i Shift + górny rząd; cel fps liczony z
  prędkości i monitora (F8); profile per monitor; kolor według D5; deband; `[vsync_auto]` zastąpiony. Jeśli
  etap 01 nie przyjął żadnej metody AI, etap obejmuje tylko kolor, synchronizację i obecne presety bez usterek.
- zależności: 01 (decyzje), 03.
- warunek wyjścia: N1 zmierzone w oknie na domyślnym trybie przy 2× na monitorze z D2 (S2); A/B zaakceptowane
  przez właściciela; test izolacji po budowie silników TensorRT PASS.
- status: planned

### 05. Przełączenie właściciela

- rezultat: używana instalacja w miejscu z D7; jednorazowy skrypt w `scripts/tmp/` przenosi pozycje wznowień i
  zapamiętane właściwości do `portable_config/state/`, po czym jest usuwany; rejestracja według D15; stary
  katalog zachowany jako kopia do akceptacji, potem usunięty.
- zależności: 03, 04, D15.
- warunek wyjścia: właściciel ogląda w PlayShift i akceptuje usunięcie starego odtwarzacza (S7); test izolacji
  po odinstalowaniu próbnej kopii PASS (S3).
- status: planned

### 06. Zdarzenie „obejrzane” dla AniShift

- rezultat: po stronie PlayShift skrypt dopisuje fakty o postępie do pliku zdarzeń w formacie ustalonym z
  workstreamem 22 (punkt wyjścia: R6 §4.2B); sprawdzony bez okna na `lavfi` z `keep-open` i bez niego.
- zależności: D16; workstream AniShift nr 22 (dopasowanie odcinka, próg „obejrzane”, MAL); może biec po etapie 02
  równolegle z 03–05, bo zapisuje tylko własny skrypt i własny plik stanu.
- warunek wyjścia: kontrakt zaakceptowany po obu stronach; scenariusz end-to-end z workstreamu 22 PASS.
- status: blocked (D16, workstream 22)

## Aktualny etap

**Etap:** 01. Porównanie metod poprawy obrazu i decyzja bazy. Plan: `plans/01-engine-and-base.md`.

**Dlaczego teraz:** to najdroższa decyzja. Wybór bazy przesądza o tym, co leży w `lib/`, czy w ogóle jest Python
i VapourSynth, jak wygląda instalator, presety interpolacji i drzewo katalogów, którego właściciel oczekuje.
Pomiar kosztuje około 1–1,5 GB pobrania i nie dotyka obecnego odtwarzacza.

**Największa niewiadoma:** czy którakolwiek metoda daje obraz lepszy od obecnego w oczach właściciela; dalej,
czy natywny filtr AnimeJaNai pozwala ustawić ułamkowy mnożnik RIFE (albo docelowe fps) i zmienić go w trakcie
odtwarzania, i czy przy 2× zmieści RIFE do połowy odświeżania razem z upscalingiem (R4 §6).

**Następny artefakt lub decyzja:** wykonanie planu 01 i `outcomes/01-engine-and-base.md`.

## Późniejsze etapy

Kierunek bez pseudo-precyzji. Kandydaci po etapie 05, tylko na życzenie właściciela:

- JSON IPC do sterowania na żywo z AniShift (unikalna nazwa potoku na proces), gdy pojawi się wymaganie typu
  „panel pokazuje, co teraz leci” (R6 §4.4).
- Dodatki „może” z R5 §1: SponsorBlock, menu formatów, YouTube upnext i czat, Discord, `autosubsync`, SmartSkip,
  przyspieszanie ciszy (`skipsilence` albo `speed-transition`).
- Natywne menu Win32 mpv (`menu.conf`) po wydaniu mpv 0.42 (R5 §3).
- Publikacja repo po audycie licencji konfiguracji (Z8, D9).

## Ryzyka kierunku

- **Fork jednego autora** (AnimeJaNai, 278 commitów przed i 65 za upstreamem, częste wydania, R2 §1, R3 §6):
  rozpoznanie — regresja po aktualizacji albo porzucenie projektu; reakcja — wersja przypięta w locku, powrót
  przez `git revert` locka; awaryjnie upstream mpv + shadery GLSL (ArtCNN) bez TensorRT (R3 §1, plan B).
- **RTX 50 i Vulkan** (issue #200: okno się nie otwiera z `gpu-api=vulkan`, R3 §6): rozpoznanie — punkt kontrolny
  K1 etapu 01; reakcja — `gpu-api=d3d11` albo obejście z issue.
- **Silniki TensorRT** zależą od wersji TRT i sterownika; aktualizacja wymusza przebudowę, a przerwana budowa
  psuła silnik przed 3.8.1 (R3 §6): reakcja — silniki w cache, pierwsze odtworzenie po aktualizacji sterownika
  liczy się z kilkunastoma sekundami.
- **Ścieżka VapourSynth przez CPU** (RIFE ncnn i upscaling przez VS dławią się na 60–80 kl./s, R3 §2, R4 §6): jeśli
  fork AnimeJaNai odpadnie, ścieżka vs-mlrt może mieć ten sam sufit; reakcja — osobny pomiar po zgodzie (D1).
- **Licencje** (O6): repo prywatne do audytu; binarki i modele tylko pobierane, nigdy w gicie (Z6).
- **Przestój właściciela:** do etapu 05 obecny `Videos\mpv` zostaje nietknięty (I1).
- **Rozjazd stylu napisów** AniShift i `mpv.conf` (R6 §4.6): I4 i kontrola w etapie 03; trwała kontrola po
  stronie AniShift należy do workstreamu 22 albo osobnego zadania AniShift.

## Historia materialnych zmian kierunku

- 2026-10-31: utworzenie mapy na podstawie R1–R6 i ustaleń właściciela; etap 01 przed jakimkolwiek repo, bo
  wybór bazy zmienia drzewo katalogów i instalator.
- 2026-10-31: właściciel: upscaling, interpolacja i filtry to hipotezy do sprawdzenia, nie wymagania (U15); etap
  01 staje się porównaniem kandydatów z obecnym obrazem, z możliwym werdyktem „żadna”; dochodzą algorytmy z
  wydań `mpv_PlayKit`; D1 rozstrzygnięte.
- 2026-10-31: właściciel: zależności aktualizują się same (U7), nie na żądanie; aktualizacja działa tylko w czasie
  pracy odtwarzacza (U6); zakres i ochrona przed regresją: D18; dotyka etapu 02.

## Nierozstrzygnięte decyzje

Pełna lista z rekomendacjami: `specification.md`, sekcja „Otwarte decyzje właściciela” (D1–D18). Etap 01
rozstrzyga D3–D8; D2 domyślnie „oba monitory”.
