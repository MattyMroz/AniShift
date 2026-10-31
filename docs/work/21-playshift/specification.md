---
kind: specification
status: draft
updated: 2026-10-31
---

# Specyfikacja: PlayShift — przenośny odtwarzacz na mpv

Dokument mówi, co ma być prawdą. Rekomendowaną drogę i kolejność prac opisuje `masterplan.md`, a pierwszy etap
`plans/01-engine-and-base.md`. Fakty pochodzą z raportów w `research/` (dalej R1–R6, z numerem sekcji).
Rekomendacje researchu nie są tu wymaganiami; tam, gdzie zmieniają rezultat, czekają w sekcji „Otwarte decyzje
właściciela” (D1–D18).

## Cel

PlayShift zastępuje obecny przenośny odtwarzacz `C:\Users\MattyMroz\Videos\mpv`. Ma być najlepszym odtwarzaczem
na mpv dla Windows, jakiego właściciel potrzebuje: gra każdy lokalny plik wideo i audio oraz linki z internetu,
poprawia obraz anime tylko tymi metodami, które właściciel po porównaniu uzna za lepsze (U15), sam instaluje i
aktualizuje swoje zależności, a do tego nie zostawia śladów w systemie. Jest częścią domowego „centrum rozrywki” i współpracuje z AniShift.

## Użytkownik i ocena

Właściciel jest jedynym użytkownikiem. Ogląda głównie anime z polskim lektorem AniShift, zwykle w prędkości 2×.
Jakość obrazu, płynność, wygląd interfejsu i wygodę skrótów ocenia sam, na prawdziwym odcinku.

## Stan wyjściowy (2026-10-31)

### Sprzęt (zmierzony, R4 §3 i §5)

- RTX 5090 32 GB, sterownik 610.88; Intel Core Ultra 7 265KF (20 wątków).
- Dwa monitory, oba 8 bit na kolor, HDR w Windows wyłączony, gamut blisko DCI-P3, bez profilu ICC:
  - Gigabyte G34WQC2, 3440×1440 @ 200 Hz — ekran główny;
  - Gigabyte M27Q, 2560×1440 @ 170 Hz — ekran drugi, po prawej.
- Raporty R1, R3 i R5 zakładały tylko M27Q 170 Hz; dane o dwóch monitorach pochodzą z pomiaru R4.

### Obecny odtwarzacz (R1)

- Baza to paczka mpv-lazy „2023EX” (dziś `hooke007/mpv_PlayKit`), mocno przerobiona przez właściciela: polskie
  menu, własne skrypty interpolacji, własny styl napisów (R1 §1).
- Wersje: mpv `v0.36.0-711` (build 2023-11-02), VapourSynth R65, embedded Python 3.11.6, uosc 5.0.0 w forku
  mpv-lazy, yt-dlp 2026.07.04 podmieniony ręcznie. Całość zajmuje 251 MB (R1 §2.1, §2.2).
- Nic nie aktualizuje się samo; komenda `update` uosc wskazuje nieistniejący plik (R1 §5).
- Interpolacja: MVTools (CPU), SVP i RIFE ncnn z modelem v4.0 wyłącznie ×2. Nie ma TensorRT, vs-mlrt ani
  AnimeJaNai (R1 §2.6, R4 §1).
- Upscaling to shadery GLSL; łańcuch 6 shaderów zapamiętany globalnie ładuje się przy każdym starcie (R1 §1.6).
- Profil `[vsync_auto]` na obu monitorach wyłącza `interpolation` i przestawia `video-sync=audio` (R1 §6.1, R4 §5).
- Skróty są w `portable_config/input_uosc.conf`, wbudowane skróty mpv są wyłączone (R1 §3).
- Usterki skrótów i presetów (R1 §3, §6):
  - `~` („Wyłącz interpolację”) czyści cały łańcuch `vf`, także odbicia;
  - każdy preset interpolacji nadpisuje odbicia `hflip`/`vflip`;
  - `REWIND` i `FORWARD` są odwrócone;
  - presety interpolacji liczą cel od `container_fps` i ignorują prędkość;
  - w `rife_480p_x2.vpy` i `rife_720p_x2.vpy` wykrywanie cięć scen jest martwe;
  - brak klawiszy: ścieżka napisów, widoczność napisów, ścieżka audio, rozdziały, następny i poprzedni plik,
    usuwanie pliku, zrzut ekranu bez OSD i napisów;
  - usuwanie pliku w uosc 5.0.0 istnieje bez klawisza i kasuje trwale (`cmd /C del`).
- Font napisów: w `fonts/` rodzina Officina ma tylko odmiany Bold i Bold Italic, więc napisy wychodzą
  pogrubione (R1 §6.8).
- Rejestracja w Windows pochodzi ze starego instalatora rossy/mpv-install (zapis do HKLM, wymaga administratora):
  App Paths, 86 ProgId `io.mpv.*`, UserChoice dla `.mkv` i `.mp4` (R1 §7).
- Zmierzona wydajność (R4 §5): RIFE ncnn 1080p ×2 w mpv daje 60–70 kl./s, a przy prędkości 2× potrzeba 96;
  SVP z celem 170 daje 244 kl./s; MVTools z celem 170 daje 134 kl./s. Wąskim gardłem jest CPU, nie karta.

### AniShift

- AniShift otwiera gotowy odcinek przez `os.startfile`, czyli przez skojarzenie plików (R6 §1.1).
- `anishift/services/subtitles/restyle.py` kopiuje wartości `sub-*` z `mpv.conf` właściciela (rozmiar 51,
  obwódka 2, cień 1,25, margines 44) bez żadnej kontroli zgodności (R6 §4.6).
- AniShift nie zapisuje w MKV tożsamości odcinka i nie pobiera `idMal` (R5 §5).

## Ustalenia

Decyzje właściciela, wiążące dla każdego etapu.

- **U1. Tylko Windows.** Skutek: żadnych ścieżek, testów ani CI dla Linuksa.
- **U2. Odtwarza wszystko:** lokalne pliki wideo i audio oraz linki z internetu. Wklejenie linku uruchamia
  odtwarzanie.
- **U3. Punktem wyjścia jest obecny `Videos\mpv`.** Skróty, do których właściciel przywykł (prędkość,
  interpolacja, filtry, jakość), zostają na tych samych klawiszach i działają lepiej. Znane usterki skrótów z R1
  są naprawione.
- **U4. Funkcje, których właściciel chce:** usuwanie plików z poziomu odtwarzacza, nowszy interfejs (forma: D12),
  polski interfejs, rotacja obrazu.
- **U5. Odtwarzacz odtwarza, AniShift edytuje.** Skutek: styl, położenie i treść napisów ustala AniShift przy
  produkcji pliku; odtwarzacz nie ma własnych heurystyk stylu napisów ani nie edytuje plików.
- **U6. Izolacja (twarde, 2026-10-31).** Wszystko, co odtwarzacz instaluje, jest przenośne i zamknięte w jego
  katalogu. Skutek:
  - żadnych instalacji globalnych ani globalnych zmiennych środowiskowych, jeśli da się ich uniknąć (wyjątek
    tylko za jawną zgodą, D11);
  - żadnych usług, autostartu, zadań harmonogramu;
  - żadnych procesów działających po zamknięciu odtwarzacza ani po ponownym uruchomieniu komputera.
- **U7. Zależności aktualizują się same (2026-10-31).** Właściciel nie pamięta o aktualizacjach; nowe wersje
  zależności (np. yt-dlp) instaluje sam odtwarzacz. Skutek: sprawdzanie i pobieranie uruchamia odtwarzacz w czasie
  swojej pracy i kończy razem z nim; żadnej usługi, zadania harmonogramu ani procesu po zamknięciu (U6). yt-dlp i
  `deno` aktualizują się od razu; mpv, silnik AI, uosc i skrypty po teście bez okna, z automatycznym powrotem do
  poprzedniej wersji, gdy test padnie (D18, rozstrzygnięte 2026-10-31).
- **U16. Rozgrzewka (2026-10-31).** Po otwarciu odtwarzacz ma działać od razu. Skutek: po aktualizacji, która
  wymaga przebudowy silników AI, odtwarzacz przebudowuje je sam, zanim właściciel ich użyje, a nie przy pierwszym
  włączeniu filtra w trakcie oglądania; rozgrzewka działa tylko w czasie pracy odtwarzacza (U6).
- **U8. Skojarzenia plików tylko w HKCU i tylko na jawne życzenie właściciela.**
- **U9. Implementacja startuje dopiero po zatwierdzeniu specyfikacji, masterplanu i planu etapu przez
  właściciela.**
- **U10. Katalogi po linuksowemu:** krótko, trzyliterowo, gdy istnieje konwencja (`bin`, `lib`, `etc`, `tmp`,
  `src`, `var`). Struktura folderów jest dla właściciela bardzo ważna i wymaga jego akceptacji.
- **U11. Zero legacy.** Zmiana jest ostateczna: bez aliasów, starych nazw, podwójnych ścieżek i warstw zgodności.
  Dane użytkownika przenosi jednorazowy skrypt w `scripts/tmp/`, uruchomiony raz i usunięty.
- **U12. Reuse przed nowym kodem.** Najpierw istniejąca funkcja mpv, potem utrzymywany skrypt upstream, na końcu
  własny kod. KISS i YAGNI.
- **U13. Kod, nazwy i wszystko w gicie po angielsku; dokumenty po polsku.**
- **U14. Nazwa robocza: PlayShift** (nazwa workstreamu; R6 §6 nie znalazł kolizji; ostateczną nazwę wybierze
  właściciel).
- **U15. Poprawa obrazu to hipoteza, nie wymaganie (2026-10-31).** Upscaling AI (AnimeJaNai, RTX Video Super
  Resolution i inne), interpolacja klatek (RIFE, technologie NVIDIA, algorytmy z wydań `mpv_PlayKit` i inne),
  własne filtry obrazu i „zmiana ilości barw” (D5) są kandydatami. Research szuka najlepszych dostępnych metod, pomiar sprawdza, czy w ogóle coś poprawiają, a do
  odtwarzacza wchodzi tylko to, co właściciel w porównaniu A/B z obecnym obrazem uzna za lepsze. Skutek: żaden etap
  nie zakłada z góry, że AnimeJaNai, RIFE czy dany filtr zostaną; metoda bez wyraźnej poprawy odpada.

## Wymagania funkcjonalne

### Odtwarzanie

- **F1.** Odtwarza lokalne pliki wideo i audio w formatach obsługiwanych przez FFmpeg wbudowany w mpv.
- **F2.** `Ctrl+V` z linkiem lub ścieżką w schowku uruchamia odtwarzanie; gdy coś już gra, dopisuje pozycję do
  playlisty; sam znacznik czasu w schowku przewija bieżący plik. `Ctrl+C` kopiuje ścieżkę lub URL razem z czasem
  (zachowanie z R1 §3, „Narzędzia, pliki, schowek”).
- **F3.** Dla linku można wybrać jakość strumienia z menu.
- **F4.** Ponowne otwarcie pliku wznawia pozycję i wybrane ścieżki (jak dziś `watch-later-options`).
- **F5.** Następny i poprzedni plik z tego samego katalogu są dostępne z klawiatury bez ręcznego budowania
  playlisty.

### Obraz

- **F6.** Metody upscalingu przyjęte według U15 włączają się i wyłączają z klawiatury, z rodziny `Ctrl+cyfry`,
  która zostaje przełącznikami jakości obrazu. Zawartość tej rodziny ustala etap jakości obrazu na podstawie A/B
  właściciela.
- **F7.** Interpolacja klatek przyjęta według U15 włącza się z klawiatury, z rodziny Shift + górny rząd; `~`
  wyłącza wyłącznie interpolację.
- **F8.** Cel interpolacji uwzględnia bieżącą prędkość odtwarzania: preset nie wytwarza klatek, których ekran nie
  zdąży pokazać.
- **F9.** Interpolacja, odbicia i obrót działają niezależnie: włączenie lub wyłączenie jednego nie zdejmuje
  pozostałych.
- **F10.** Korektor obrazu działa jak dziś: `1`–`0` (kontrast, jasność, gamma, nasycenie, barwa), `Ctrl+9`,
  `Ctrl+0` (presety), `Ctrl+BS` (reset).
- **F11.** Obrót `r` / `Shift+R`, odbicia `Shift+F` / `Alt+F`, zoom i przesuwanie myszą oraz strzałkami działają
  jak dziś (R1 §3, „Obraz”).
- **F12.** „Zmiana ilości barw” przyjęta według U15 ma pokrycie zgodne z D5.

### Skróty i menu

- **F13.** Wszystkie skróty z R1 §9 („Zachować jako kontrakt przyzwyczajeń”) działają na tych samych klawiszach:
  prędkość `[` `]` `\` `BS`, strzałki ±5 s / ±30 s, `,` `.` klatki, `l` pętla A-B, `z` `x` i `c` `v`
  opóźnienia, `-` `=` i kółko głośność, `m` wycisz, pełny ekran, `Ctrl+Q` wyjście, `I` i `` ` `` diagnostyka.
- **F14.** `REWIND` przewija wstecz, `FORWARD` naprzód.
- **F15.** Istnieją klawisze dla: ścieżki napisów, widoczności napisów, ścieżki audio, rozdziałów, następnego i
  poprzedniego pliku, usunięcia pliku, zrzutu ekranu bez OSD i napisów. Konkretne klawisze zatwierdza właściciel w
  etapie konfiguracji.
- **F16.** Prawy przycisk myszy otwiera menu akcji budowane z tego samego pliku co skróty (jedno źródło prawdy).

### Interfejs

- **F17.** Menu, przyciski i komunikaty OSD wywoływane skrótami właściciela są po polsku (ograniczenie O5).
- **F18.** Interfejs jest nowszy niż dzisiejszy uosc 5.0.0; forma zgodnie z D12.

### Pliki

- **F19.** Bieżący plik można usunąć z odtwarzacza jednym skrótem, a odtwarzanie przechodzi do następnego pliku;
  sposób usuwania zgodnie z D13.

### Instalacja, aktualizacja, rejestracja

- **F20.** Jedno polecenie instaluje wszystkie zależności (mpv, yt-dlp i resztę) w przypiętych wersjach do
  katalogu odtwarzacza.
- **F21.** Odtwarzacz sam sprawdza nowsze wersje zależności i je instaluje, bez udziału właściciela (U7, D18).
- **F22.** Rejestracja skojarzeń plików i jej cofnięcie to osobne, jawne polecenia (U8).
- **F23.** Odinstalowanie to cofnięcie rejestracji (jeśli była) i usunięcie katalogu odtwarzacza; nic więcej w
  systemie nie zostaje (poza śladami z D8).

### AniShift

- **F24.** Odcinek otwarty z Biblioteki AniShift odtwarza się w PlayShift, gdy właściciel zarejestrował
  skojarzenia (F22). Dalsza integracja zależy od D16.

## Wymagania jakościowe

- **N1. Płynność.** W trybie jakości wybranym jako domyślny (D3) odtwarzanie w prędkości 2× na monitorze z D2 nie
  gubi ani nie opóźnia klatek. Ocena: liczniki mpv `frame-drop-count` i `vo-delayed-frame-count` w scenariuszu
  etapu jakości obrazu oraz oko właściciela.
- **N2. Jakość obrazu** ocenia właściciel na porównaniach A/B tej samej sceny.
- **N3.** Interpolacja wykrywa cięcia scen; na cięciu nie powstaje „morfing” (R4 §2).
- **N4. Izolacja jest sprawdzalna.** Porównanie stanu systemu przed i po instalacji, odtwarzaniu, aktualizacji i
  zamknięciu nie pokazuje nowych: zmiennych środowiskowych, usług, zadań harmonogramu, wpisów autostartu, kluczy
  rejestru poza jawną rejestracją (F22), plików poza katalogiem odtwarzacza (poza śladami z D8) ani procesów z
  katalogu odtwarzacza po jego zamknięciu.
- **N5.** Każdy pobrany plik jest sprawdzony sumą SHA256 przed użyciem; niezgodna suma przerywa instalację bez
  zmian w zainstalowanych plikach.
- **N6.** Nieudana albo przerwana aktualizacja zostawia działającą poprzednią wersję. Plik używany przez działający
  odtwarzacz zostaje podmieniony dopiero przy następnym uruchomieniu.
- **N7.** Po instalacji odtwarzacz działa bez sieci (poza linkami z internetu).
- **N8.** Wszystkie biblioteki uruchomieniowe (MSVC, TensorRT i inne) leżą w katalogu odtwarzacza; nic nie wymaga
  instalacji pakietów redystrybucyjnych w systemie. Sterownik NVIDIA jest jedyną zależnością systemową.
- **N9.** Błąd w konfiguracji i błąd ładowania skryptu da się wykryć automatycznie, bez okna (R6 §5).

## Inwarianty

- **I1.** Obecny `Videos\mpv` działa bez zmian, dopóki właściciel nie zaakceptuje przełączenia na PlayShift. Do
  tego czasu agenci tylko go czytają.
- **I2.** Instalacja i aktualizacja nigdy nie nadpisują ani nie usuwają danych użytkownika: pozycji wznowień,
  historii, zapamiętanych właściwości, dziennika zdarzeń.
- **I3.** Odtwarzacz nie zmienia plików wideo ani napisów; jedynym wyjątkiem jest jawne usunięcie pliku przez
  właściciela (F19).
- **I4.** Wartości `sub-*`, które kopiuje `restyle.py` AniShift, zmieniają się tylko razem po obu stronach.

## Ograniczenia

- **O1. Budżet GPU (szacunek, do potwierdzenia pomiarem).** Przy prędkości 2× i celu 170 fps ani RIFE z
  upscalingiem ML, ani odwrotna kolejność nie mieszczą się w RTX 5090 (R3 §3, R4 §4).
- **O2.** mpv bierze przenośną konfigurację tylko z katalogu `portable_config` obok `mpv.exe` (R6 §2.1).
- **O3.** mpv nie przekazuje prędkości odtwarzania do filtrów, a domyślne `--framedrop=vo` dekoduje i filtruje
  każdą klatkę: przy 2× filtr przerabia 47,95 kl./s źródła 23,976 fps (R3 §3, R4 §2).
- **O4.** VapourSynth od R74 wymaga buildu mpv nowszego niż 2026-04-10, czyli nowszego niż wydanie stabilne
  v0.41.0, i ładuje `vsscript.dll` ze zmiennej `VSSCRIPT_PATH` albo przez wyszukiwanie DLL (R2 §5, R6 §2.1).
- **O5.** Wbudowane menu mpv (`select.lua`, konsola, statystyki) nie mają tłumaczeń; polskie są tylko teksty
  uosc, pozycje menu z `input.conf` i komunikaty wywoływane z własnych skrótów (R5 §4.8).
- **O6. Licencje** (R2 §1, R3 §6, R4 §6, R6 §1.1):
  - AnimeJaNai: repo i modele CC BY-NC-SA 4.0; silnik `animejanai-inference` bez pliku licencji;
  - mpv: GPL (redystrybucja binarek wymaga udostępnienia źródeł);
  - `svpflow2` jest zamknięty, a wiki SVP wymaga do niego SVP Managera;
  - pliki mpv-lazy/PlayKit bez osobnej licencji mają status „UNLICENSED”, a część `mpv.conf` właściciela z nich
    pochodzi;
  - fonty Officina są prywatne (repo `MattyMroz/fonts`).
- **O7.** YouTube wymaga od yt-dlp zewnętrznego środowiska JS (domyślnie `deno`); ciasteczka przeglądarek
  Chromium na Windows nie działają w yt-dlp (R2 §6, §8).
- **O8.** Zasoby wydań GitHub mają w API pole `digest` z SHA256 (R2 §5, R6 §3.2).

## Zakazane

- **Z1.** Instalacje globalne (MSI, `winget`, pakiety redystrybucyjne, `pip` do systemowego Pythona), usługi,
  autostart, zadania harmonogramu, procesy w tle po zamknięciu odtwarzacza.
- **Z2.** Globalne zmienne środowiskowe, chyba że właściciel jawnie zgodzi się na konkretny wyjątek (D11).
- **Z3.** Zapis do HKLM; zapis do HKCU poza jawną rejestracją (F22).
- **Z4.** Aktualizacje działające poza procesem odtwarzacza (usługa, harmonogram, proces po zamknięciu) oraz
  komenda `update` uosc obok aktualizatora PlayShift.
- **Z5.** Jakakolwiek zmiana w `Videos\mpv` przed zaakceptowanym przełączeniem (I1).
- **Z6.** Binarki, modele i wagi AnimeJaNai, pliki SVP i fonty Officina w gicie; rehostowanie ich.
- **Z7.** Edycja napisów, tłumaczenie i TTS w odtwarzaczu; klient API MAL/AniList i tokeny w odtwarzaczu.
- **Z8.** Pliki PlayKit/mpv-lazy bez licencji w publicznym repo.
- **Z9.** Aliasy, stare nazwy, podwójne ścieżki i warstwy zgodności (U11).

## Zakres

- Przenośna instalacja z automatyczną aktualizacją zależności oraz poleceniami instalacji i rejestracji.
- Przeniesienie konfiguracji i skrótów z `Videos\mpv` z naprawą usterek i bez martwego balastu (R1 §9).
- Upscaling, interpolacja, filtry i kolor.
- Interfejs po polsku, usuwanie plików, rotacja.
- Jednorazowa migracja danych właściciela (pozycje wznowień, zapamiętane właściwości) i przełączenie ze starego
  odtwarzacza.
- Strona odtwarzacza w integracji z AniShift, jeśli D16 ją przyjmie.

## Poza zakresem

- Linux i macOS.
- Strona AniShift integracji: dopasowanie pliku do odcinka, decyzja „obejrzane”, synchronizacja MAL/AniList
  (osobny workstream AniShift, przyszły numer 22).
- Publiczne repo i paczki binarne w wydaniach GitHub.

## Odrzucone

Drogi sprzeczne z ustaleniami; nie wracać, dopóki ustalenie obowiązuje.

- Instalator rossy/mpv-install i `umpv-install.bat` z zapisem do HKLM (R1 §7, R2 §4) — łamie U8.
- Oficjalne `register-install` VapourSynth (globalna zmienna `VSSCRIPT_PATH`) jako domyślna droga (R2 §7) — łamie
  U6; wyjątek tylko przez D11.
- SVP 4 Pro z SVP Managerem (R4 §2) — stały program w tle; łamie U6.
- Samoaktualizacja uosc komendą `update` (R5 §3) — druga ścieżka obok aktualizatora PlayShift (Z4).

## Warunki sukcesu

- **S1.** Właściciel przechodzi scenariusz kontraktu skrótów (F13–F16) na PlayShift i akceptuje go.
- **S2.** N1 spełnione w domyślnym trybie jakości przy 2× na monitorze z D2; liczniki z pomiaru zapisane.
- **S3.** Test izolacji (N4) przechodzi po instalacji, odtwarzaniu, aktualizacji i odinstalowaniu.
- **S4.** Świeży katalog plus jedno polecenie daje działający odtwarzacz; aktualizacja i powrót do poprzedniej
  wersji działają (N5, N6).
- **S5.** Wklejony link YouTube odtwarza się.
- **S6.** Właściciel akceptuje interfejs po polsku, usuwanie pliku i wygląd napisów z AniShift.
- **S7.** Właściciel przełącza się na PlayShift i akceptuje usunięcie starego `Videos\mpv`.

## Otwarte decyzje właściciela

Jedyna lista pytań workstreamu; masterplan i plany odsyłają tutaj. Przy każdym: rekomendacja, skutek odpowiedzi i
etap, który blokuje.

### Blokują wejście do etapu 01

- **D1. Zgoda na pobranie do pomiarów — rozstrzygnięte 2026-10-31: tak.** Agent pobiera do
  `C:\Users\MattyMroz\tmp\playshift\` najnowsze wydanie mpv-AnimeJaNai (w researchu 3.9.0: paczka z `mpv.exe` i
  silnikiem, `trt-runtime` 187 MB, `trt-sm120` 229 MB, `rife` 462 MB, R2 §6) oraz paczki z wydań
  `hooke007/mpv_PlayKit` z algorytmami interpolacji, i uruchamia je bez okna. Instalatorów nie uruchamia. Silniki
  TensorRT budują się raz na model i rozdzielczość, około 10 s na TRT 11 (R3 §6). Ścieżka vs-mlrt (około 2,7 GB)
  tylko po osobnej zgodzie.
- **D2. Na którym monitorze oglądasz?** G34WQC2 3440×1440 @ 200 Hz (główny) czy M27Q 2560×1440 @ 170 Hz (drugi),
  czy na obu? **Rekomendacja:** mierzyć dla obu i dać cele per monitor (połowa odświeżania: 100 albo 85 fps).
  **Skutek:** cele fps, mnożniki interpolacji i budżet GPU; przy 200 Hz pełny cel to 200 fps (R4 §4).

### Rozstrzygane w punkcie kontrolnym K2 etapu 01 (po pomiarach i A/B)

- **D3. Płynność i prędkość.** Domyślny cel: połowa odświeżania (85 albo 100 fps, równa kadencja) z upscalingiem
  AI, a pełne odświeżanie jako tryb „max” bez upscalingu AI (R4 §1)? Czy przy 2× ważniejsza jest płynność, czy
  brak artefaktów RIFE (R4 §7)? Start zawsze w 2× i automatyczne przestawianie celu przy zmianie prędkości?
  **Rekomendacja:** cel połowy odświeżania jako domyślny; start w 2×; prędkość nie zapamiętywana per plik; filtr
  przestawia się sam po zmianie prędkości, jeśli silnik na to pozwala. **Skutek:** kształt presetów, wymagania
  wobec silnika (mnożnik ułamkowy, przełączanie w locie). Alternatywa R3 (RIFE ×2, 96 fps i `display-resample`)
  daje nierówną kadencję na 170 Hz (R4 §4).
- **D4. „4×”: więcej szczegółu czy mocniejsze linie?** **Rekomendacja:** upscaling 2× (na ekranie 1440p 4× nie
  dodaje rozdzielczości, R3 §4) i A/B z wariantem `Sharp` oraz z 4× Performance+Performance. **Skutek:** model
  domyślny i koszt GPU.
- **D5. Co znaczy „zmiana ilości barw”?** Możliwości: nasycenie (anime BT.709 na panelu blisko P3 wychodzi
  przesycone, R4 §3), wyjście 10-bit, HDR albo coś innego. Czy monitor jest w trybie sRGB? **Rekomendacja:**
  najpewniej chodzi o nasycenie; A/B obecnego obrazu z `target-prim=display-p3` i trybem sRGB monitora, a 10-bit i
  HDR bez zmian (mały zysk, R4 §3). **Skutek:** profil koloru i skróty.
- **D6. Baza i VapourSynth.** (a) mpv z forka AnimeJaNai: natywny filtr TensorRT, bez VapourSynth i Pythona, około
  0,9 GB komponentów AI, jeden autor, licencja NC (R2 §1, R3 §1); czy (b) upstream mpv (shinchiro/zhongfly) +
  VapourSynth R81 + vs-mlrt: zachowuje `.vpy`, około 2,7 GB, ścieżka VS ograniczona przez CPU do około 79 kl./s
  przy upscalingu 1080p (R3 §2). Osobno: czy SVP zostaje jako tani tryb zapasowy (wymaga VapourSynth), a MVTools
  odpada (nie nadąża, R4 §5)? **Rekomendacja:** (a), jeśli przejdzie bramki etapu 01; SVP i VapourSynth tylko
  wtedy, gdy RIFE na (a) nie osiągnie celu z D3. **Skutek:** zawartość `lib/`, obecność Pythona, problem
  `VSSCRIPT_PATH` (D11) i dostępne presety.
- **D7. Układ repo i instalacji.** (a) Repo jest instalacją: klon to gotowy odtwarzacz, binarki dociąga `setup`
  (R6 §2.2), czy (b) źródła w `src/` i budowanie gotowej instalacji do osobnego katalogu? Jeden klon czy dwa
  (roboczy w `PROJECTS\PlayShift` i używany)? Gdzie ma leżeć używana instalacja? **Rekomendacja:** (a), dwa klony,
  używany w `C:\Users\MattyMroz\Videos\mpv` po odsunięciu starego katalogu (istniejące skojarzenia wskazują na
  `Videos\mpv\mpv.exe`). **Skutek:** drzewo katalogów, migracja, ryzyko, że praca agentów zmieni odtwarzacz w
  trakcie seansu (jeden klon).
- **D8. Ślady systemu, których nie da się uniknąć.** Sterownik NVIDIA i Windows zapisują własne cache i wpisy
  dla każdego programu korzystającego z GPU [W: np. cache shaderów sterownika w `%LOCALAPPDATA%\NVIDIA`, ślady
  uruchomień programów w rejestrze]. Czy uznajesz je za dopuszczalne? Etap 01 zmierzy, co faktycznie powstaje.
  **Rekomendacja:** tak, jako jedyny wyjątek, wypisany w README i odfiltrowany w teście izolacji. **Skutek:**
  definicja PASS testu N4.

### Blokują etap 02

- **D9. Gdzie żyje kod?** Osobne repo `MattyMroz/PlayShift`, prywatne na start (R6 §1), czy katalog w AniShift?
  Publiczne dopiero po audycie licencji? **Rekomendacja:** osobne prywatne repo; AniShift korzysta tylko z wąskiego
  kontraktu. **Skutek:** miejsce dokumentów i kodu, wolno-nie-wolno z licencjami (O6, Z8).
- **D10. Linki z internetu.** Kanał yt-dlp: nightly (README yt-dlp poleca go zwykłym użytkownikom, stable bywa
  tygodniami w tyle, R2 §6) czy stable? Jak często oglądasz YouTube i strumienie: czy potrzebne są dodatki
  (SponsorBlock, menu formatów, czat)? Treści z logowaniem: Firefox czy plik `cookies.txt` (Chrome nie działa)?
  **Rekomendacja:** nightly + `deno`, oba aktualizowane automatycznie (U7); dodatki dopiero po potwierdzeniu
  potrzeby; ciasteczka tylko, jeśli są potrzebne. **Skutek:** skład locka i zakres etapu 02.
- **D11. Wyjątek dla zmiennej `VSSCRIPT_PATH`** (tylko gdy D6 zostawi VapourSynth). Kolejność bez zmiennej:
  biblioteki VapourSynth obok `mpv.exe`, potem ścieżka z rejestracji (`--register-rpath`), potem launcher
  ustawiający zmienną tylko dla procesu. Czy, jeśli wszystkie zawiodą, dopuszczasz zmienną użytkownika ustawianą
  przez `setup` (rekomendacja R6 §2.1)? **Rekomendacja:** nie, dopóki warianty bez zmiennej nie zostaną
  sprawdzone. **Skutek:** wyjątek od U6 albo dodatkowy launcher i własna rejestracja.

- **D18. Które zależności aktualizują się same od razu? — rozstrzygnięte 2026-10-31.** Wszystko automatycznie:
  yt-dlp i `deno` od razu, reszta po teście bez okna z automatycznym powrotem (U7), z rozgrzewką silników (U16).

### Blokują etap 03

- **D12. Wygląd interfejsu.** uosc 5.13 jako minimalny HUD: cienka linia postępu, reszta pojawia się przy
  zbliżeniu kursora, prędkość i głośność błyskają przy zmianie (R5 §3); czy ModernZ: stały, klasyczny pasek?
  **Rekomendacja:** uosc jako HUD, A/B przy punkcie kontrolnym etapu 03. **Skutek:** komponent UI i tłumaczenia.
- **D13. Usuwanie pliku.** Do Kosza z przejściem do następnego (`use_trash=yes`), trwale, czy „zaznacz teraz,
  usuń przy wyjściu”? **Rekomendacja:** Kosz i przejście dalej. **Skutek:** ryzyko utraty danych przy pomyłce.
- **D14. Obrazy i manga.** Czy PlayShift ma też przeglądać obrazy (dziś skrypty `minimap`, `ruler`,
  `manga-reader-TEST`)? **Rekomendacja:** poza zakresem; zostaje wbudowane przesuwanie i zoom mpv. **Skutek:**
  zakres skryptów i skojarzeń.

- **D17. Wbudowane skróty mpv.** Dziś są wyłączone, a działają tylko skróty właściciela (R1 §3). Czy PlayShift
  ma włączyć domyślne skróty mpv tam, gdzie nie kolidują z własnymi, żeby odtwarzacz umiał wszystko z
  klawiatury? **Rekomendacja:** zdecydować na liście kolizji (domyślne mpv wobec kontraktu F13). **Skutek:**
  zawartość `input.conf` i menu.

### Blokują etap 05

- **D15. Nazwa pliku i rejestracja.** `mpv.exe` z wbudowanym `mpv --register` (HKCU, w „Otwórz za pomocą” widać
  „mpv”) czy `playshift.exe` z własnym kodem rejestracji (R2 §7)? Co ze starymi wpisami HKLM z instalatora rossy
  (86 ProgId, App Paths; usunięcie wymaga administratora)? **Rekomendacja:** `mpv.exe`; przy instalacji w
  `Videos\mpv` stare skojarzenia działają bez zapisu do rejestru; zamiana HKLM na HKCU tylko na Twoje życzenie,
  jednorazowo. **Skutek:** kod rejestracji i jednorazowe sprzątanie rejestru.

### Blokują etap 06

- **D16. Granica z AniShift i MAL.** Czy dopisać do zasady U5 drugą połowę: „odtwarzacz zgłasza zdarzenia,
  AniShift prowadzi stan”? Wtedy odtwarzacz dopisuje fakty o postępie do pliku zdarzeń, a AniShift dopasowuje
  odcinek i aktualizuje MAL (R5 §5, R6 §4.2). Alternatywy: skrypt w odtwarzaczu (dla MAL nie znaleziono
  utrzymywanego, R5 §4.5) albo Taiga (osobny program działający stale w tle). **Rekomendacja:** tak, dziennik
  zdarzeń; szczegóły kontraktu w workstreamie AniShift nr 22. **Skutek:** etap 06 i zakres workstreamu 22.
