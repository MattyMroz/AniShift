# ficzery: pozostałe pomysły (skrót)

> status: POMYSŁ (poza obecną przebudową)
> cel: zebrane mniejsze pomysły — każdy z opisem, technologiami i szkicem modułu, żeby przy podjęciu decyzji nie zaczynać od zera.

---

## 1. migracja toru audio na PyAV

> priorytet: niski — optymalizacja czegoś, co działa

**problem:** tor audio (atempo, volume, amix, eac3/mp3, rf64) woła `ffmpeg.exe` subprocesem — działa, ale każde wywołanie to spawn procesu i parsowanie stderr do progressu.

**technologie:** `av` (pip, PyAV — bindingi FFmpeg). Dojrzałość: wysoka, aktywnie rozwijany. Plusy: natywny dostęp do grafu filtrów i kodeków audio bez subprocessa, progress z dokładnością do ramki. Minusy (z badania 07, nadal aktualne): **nie pokrywa** renderu mp4 (libx264 GPL — brak w wheelach) ani wypalania napisów (libass) → binarka ffmpeg **zostaje tak czy siak**, więc migracja daje dwa stacki audio/wideo naraz; przepisanie sprawdzonych łańcuchów filtrów (atempo-chain, `-rf64 auto` dla WAV>4GB) to realne ryzyko regresji na wielogodzinnym lektorze.

**szkic:** zero zmian w drzewie — wymiana wnętrza `anishift/services/audio/service.py`; typy i błędy domeny bez zmian, pipeline nie widzi różnicy. Warunek wejścia: test porównawczy bit-w-bit (albo z tolerancją) starego i nowego toru na próbce + na pliku >4GB.

**rekomendacja:** nie ruszać, dopóki subprocess realnie nie boli (krok 3 algorytmu Muska — nie optymalizować działającego). Jeśli kiedyś — tylko tor audio, nigdy wideo.

---

## 2. style_classifier napisów (ASS)

> priorytet: średni — realnie poprawia jakość lektora na "przegadanych" wydaniach

**problem:** pliki ASS z fansubów mieszają dialogi z szyldami (tłumaczenia napisów na ekranie), karaoke openingów i notkami tłumacza. Lektor czytający szyldy i karaoke brzmi źle. Trzeba klasyfikować linie: czytać / pominąć / (opcjonalnie) czytać innym trybem.

**technologie:** `pysubs2` (pip — dojrzały parser ASS/SSA, dostęp do stylów, warstw, tagów pozycjonowania) + heurystyki: nazwa stylu (Default/Main = dialog; OP/ED/sign/title = pomiń), obecność tagów `\pos`/`\move`/`\an8`, warstwa, procent linii danym stylem. Bez ML — klasyfikator regułowy pokrywa ~95% wydań; `scikit-learn` odnotowany jako ewentualny etap 2, jeśli user zbierze korpus (zbiera przykłady — patrz plan §G).

**szkic:** hak już istnieje — `anishift/services/subtitles/styles.py` (zaślepka z planu). Wypełnienie: funkcja klasyfikująca linie ASS → decyzja per linia przed konwersją do SRT; do tego przełącznik w `/settings` (czytaj szyldy TAK/NIE) i tryb manual pokazujący wykryte style z licznikami linii do ręcznego potwierdzenia.

**rekomendacja:** wejść po etapie 8, zaczynając od heurystyk na przykładach zebranych przez usera; ML tylko jeśli reguły przegrają z rzeczywistością.

---

## 3. GUI / web panel

> priorytet: niski — terminal jest sercem wizji; GUI to inna liga utrzymania

**problem:** shell terminalowy bywa barierą, gdyby z AniShift miał korzystać ktoś poza autorem.

**technologie:** (a) `textual` (pip) — TUI/pseudo-GUI, umie też serwować się w przeglądarce (`textual serve`); najbliżej obecnego kodu, bo panel ustawień i progress przenoszą się koncepcyjnie 1:1. (b) `fastapi` + prosty frontend (HTMX/statyczny) — pełny web panel, ale wciąga cały świat serwera (procesy w tle, stan, WebSocket do progressu), który plan świadomie wyciął z MangaShift. (c) Tauri/React — pełny desktop; najwyższy koszt, najdalej od "prostoty".

**szkic:** dowolny wariant siedziałby w `anishift/gui/` (osobny pakiet obok `cli/`), wołając te same fasady serwisów — architektura services/ już to umożliwia, bo CLI niczego nie trzyma na własność. To jedyny powód, by pomysł notować: **nie wymaga żadnych przygotowań teraz**.

**rekomendacja:** nie robić. Jeśli kiedykolwiek — Textual (wariant a), bo dzieli filozofię terminala i nie dodaje serwera.

---

## 4. batch / watch mode (folder-watcher)

> priorytet: średni-wysoki — tani w budowie, mocny w parze z auto-download

**problem:** user musi siedzieć w shellu i wcisnąć Enter. Watch mode: AniShift obserwuje `workspace/` i sam przetwarza nowe MKV — wrzucasz plik (albo `/download` go pobiera) i wracasz do gotowego lektora.

**technologie:** `watchdog` (pip) — standard obserwacji systemu plików, dojrzały, cross-platform. Alternatywa jeszcze prostsza: pętla pollingu co N sekund (zero zależności) — dla jednego folderu w zupełności wystarczy i nie ma znanych czkawek watchdoga na Windows przy dużych plikach. Kluczowy detal obu podejść: **wykrycie, że plik skończył się kopiować/pobierać** (rozmiar stabilny przez X sekund), zanim pipeline go tknie.

**szkic:**
```
anishift/cli/commands.py          # ZMIANA: /watch start|stop w mapie COMMANDS
anishift/pipeline/watcher.py      # NOWY: pętla obserwacji workspace/ (polling lub watchdog),
                                  #   filtr *.mkv, test stabilności rozmiaru, kolejka -> runner,
                                  #   pamięć przetworzonych plików w ramach sesji
```
Bez osobnej domeny serwisowej — to tryb pracy pipeline'u, nie domena. Działa w bieżącej sesji shella (`/watch` blokuje prompt, Ctrl+C wraca) — bez demonów i autostartu.

**rekomendacja:** robić zaraz po etapie 8, zaczynając od pollingu (watchdog tylko jeśli polling okaże się za wolny — pewnie nie będzie). Razem z auto-download daje pełny automat: `/download` → watch → gotowy lektor.

---

## 5. cache metadanych anime

> priorytet: niski — dodatek do auto-download, nie samodzielny ficzer

**problem:** moduł auto-download odpytuje AniList o te same tytuły przy każdym `/download`; limit 90 req/min jest łaskawy, ale offline/przestój API blokuje wyszukiwanie, a odpowiedzi są w praktyce niezmienne (liczba odcinków zakończonego anime się nie zmienia).

**technologie:** zero nowych zależności — plik JSON w `workspace/tmp/anilist_cache.json` z TTL (np. 7 dni; anime emitowane krócej, bo liczba odcinków rośnie). Świadomie NIE `diskcache`/sqlite — plan mówi wprost: cache nie istnieje jako mechanizm, stan wielokrotnego użytku żyje w `tmp/` i sprząta się razem z nim.

**szkic:** bez nowych plików — mapa tytuł→odpowiedź wewnątrz `acquisition/metadata.py` (odczyt przed requestem, dopis po). ~30 linii.

**rekomendacja:** dopisać przy drugiej iteracji auto-download, nie wcześniej (YAGNI bez tamtego modułu).

---

## 6. wybór głosów per-postać (multi-voice lektor)

> priorytet: niski-średni — efektowny, ale drogi w dopracowaniu

**problem:** jeden głos lektora czyta wszystkich. ASS często niesie pole `Actor` (nazwa postaci) albo styl per postać — można mapować postać → głos TTS i dostać "obsadę" zamiast lektora.

**technologie:** `pysubs2` (odczyt pola `Actor`/stylu per linia — te same zależności co style_classifier); po stronie TTS zero nowych bibliotek — silniki wielogłosowe już są (edge: Zofia/Marek; elevenlabs/elevenbytes: dowolne voice_id). Zmiana architektoniczna: `TtsConfig` musiałby przyjmować mapę głosów zamiast jednego głosu, a fasada TTS grupować linie per głos.

**szkic:**
```
anishift/services/subtitles/     # odczyt Actor/stylu per linia (rozszerzenie types o pole speaker)
anishift/services/tts/config.py  # ZMIANA: opcjonalna mapa speaker -> głos (default: jeden głos jak dziś)
anishift/cli/settings_panel.py   # ZMIANA: edytor mapy postać -> głos (tylko gdy plik niesie Actor)
```

**rekomendacja:** odłożyć głęboko — zależy od style_classifiera (jakość pól Actor w fansubach bywa fatalna), mnoży koszt płatnych silników i przypadki brzegowe (linia bez Actor, dwóch mówców w linii). Notowane, żeby projektując style_classifier zachować pole speaker w typach napisów — to jedyne "przygotowanie" warte zrobienia wcześniej.

---

## 7. licznik kosztów API

> priorytet: niski — higiena przy płatnych silnikach

**problem:** elevenlabs/deepl/LLM kosztują per znak/token; user nie widzi, ile odcinek "zjadł", dopóki nie zajrzy w panel dostawcy.

**technologie:** zero zależności — silniki już znają liczbę wysłanych znaków (TTS) i tokenów (`LlmUsage` w `services/llm/types.py` już istnieje, recykling z MangaShift); cenniki jako stałe w `constants.py` silników (tam gdzie już żyją katalogi modeli).

**szkic:** bez nowych plików — pole "zużycie" w wynikach kroków pipeline (`pipeline/types.py`), sumowane w podsumowaniu przebiegu ("TTS: 48 210 znaków ≈ $X"). Wyłącznie szacunek, wyraźnie opisany jako szacunek.

**rekomendacja:** tani dodatek przy okazji dowolnej pracy w pipeline po etapie 7; nie zasługuje na osobny etap.
