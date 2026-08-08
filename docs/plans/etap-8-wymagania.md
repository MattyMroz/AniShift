# Etap 8 — domknięcie legacy

> Status: zakończony — PR #36 zmergowany 2026-08-08
> Cel: zamknąć stary roadmap na sprawnej bazie przed projektowaniem nowych funkcji i UI

## 1. Stan wyjściowy

- Dystrybucję MKVToolNix i FFmpeg zrealizowano w etapie 2.5.
- AniShift jest pakietem Pythona uruchamianym przez `uv run anishift`.
- Stare katalogi i entry pointy `mm_avh` nie istnieją już w repozytorium.
- Nie ma danych użytkownika wymagających migracji.
- `../mm_avh_working_space` jest wyłącznie opcjonalnym korpusem regresyjnym testów.
- Etapy 1–7 są wdrożone, ale stary roadmap i jego indeks nie opisują aktualnego stanu.

## 2. Ustalone decyzje

### 2.1. Bez migratora

Nie powstaje `migrate_workspace.py`. Nie ma źródła danych do migracji, więc taki
skrypt byłby martwym kodem i niepotrzebnym ryzykiem.

### 2.2. Bez pliku EXE

Nie dodajemy PyInstaller, Nuitka ani osobnego procesu wydawniczego. Projekt pozostaje
aplikacją Python zarządzaną przez `uv`. Powstanie EXE można rozważyć dopiero wtedy,
gdy pojawi się realna potrzeba dystrybucji aplikacji innym użytkownikom.

### 2.3. Prosty launcher Windows

W katalogu głównym repo powstaje `run_anishift.bat`, wzorowany na launcherze starego
`mm_avh`, który:

- ustawia stronę kodową UTF-8;
- przechodzi do katalogu repo niezależnie od miejsca uruchomienia;
- wykonuje `uv run anishift`;
- przekazuje wszystkie argumenty, np. `run_anishift.bat doctor`;
- nie instaluje zależności i nie ukrywa błędów `uv` ani AniShift.

### 2.4. Bez zmiany `tmp` na `temp`

Pozostaje `workspace/tmp/`. Nazwa jest już częścią kontraktu kodu, testów i
dokumentacji. Zmiana byłaby przekrojowa i nie dawałaby korzyści funkcjonalnej.

### 2.5. Bez nowego korpusu testowego

Etap 8 nie usuwa ani nie zastępuje `../mm_avh_working_space`. Testy korzystające z
niego pozostają opcjonalne i wykonują skip, gdy katalog nie istnieje. Własny korpus
regresyjny może później otrzymać osobne wymagania.

### 2.6. Dokumentacja produktu później

Finalne README powstanie po ustaleniu docelowych funkcji i workflow. Etap 8 poprawia
wyłącznie statusy oraz opisy starego roadmapu potrzebne do jego zamknięcia.

## 3. Zakres implementacji

### 3.1. Launcher

- dodać `run_anishift.bat`;
- potwierdzić uruchomienie co najmniej jednej nieinteraktywnej komendy;
- potwierdzić przekazywanie argumentów i kodu wyjścia.

### 3.2. Audyt legacy

- potwierdzić brak zależności runtime od starego kodu `mm_avh`;
- potwierdzić brak śledzonych binarek i dawnych katalogów runtime;
- nie traktować nazw pochodzenia w testach i dokumentacji jako zależności runtime;
- nie usuwać ani nie przenosić danych znajdujących się poza repozytorium.

### 3.3. Zamknięcie starego roadmapu

- oznaczyć etapy 1–8 zgodnie z faktycznym stanem;
- poprawić nieaktualny opis etapu 8;
- poprawić indeks planów i jego link do źródła prawdy;
- pozostawić zakończone plany w obecnych ścieżkach, aby nie psuć linków;
- zachować `etap-9-wymagania.md` jako wymagania produktu, workflow i wpływu na UI;
- przenieść numer etapu 9 z issue #22, ponieważ nowy etap 9 przejmuje tę analizę.

## 4. Poza zakresem

- migracja danych użytkownika;
- budowa EXE lub instalatora AniShift;
- zmiana `workspace/tmp/` na `workspace/temp/`;
- finalne README produktu;
- nowy korpus lub baza danych do testów;
- projektowanie albo implementacja UI v2;
- implementacja trybów pracy opisanych w etapie 9;
- naprawa backlogowych issue #16, #22, #23 i #34;
- zmiana instalatora binarek dostarczonego w etapie 2.5.

## 5. Przekazanie do nowego roadmapu

Następnym krokiem jest `etap-9-wymagania.md`:

1. ustalenie docelowych produktów i trybów pracy;
2. ustalenie stanów, konfiguracji, reuse i regeneracji wyników;
3. określenie wpływu tych decyzji na CLI i automatyzację;
4. wyprowadzenie wymagań UI v2 z gotowego modelu produktu.

UI nie jest projektowane przed ustaleniem tego modelu.

## 6. Walidacja

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
run_anishift.bat doctor
```

Dodatkowo należy sprawdzić status CI po wypchnięciu zmian.

## 7. Definition of Done

- [x] `run_anishift.bat` uruchamia AniShift i przekazuje argumenty.
- [x] wszystkie lokalne bramki jakości przechodzą;
- [x] aplikacja nie ma zależności runtime od starego `mm_avh`;
- [x] nie ma śledzonych binarek ani dawnych katalogów runtime;
- [x] brak migratora i EXE jest zapisany jako świadoma decyzja;
- [x] etap 8, główny roadmap, indeks planów i issue etapu 8 opisują ten sam stan;
- [x] etapy 1–8 są oznaczone jako zakończone po merge;
- [x] analiza została przeniesiona do wymagań etapu 9;
- [x] backlogowe issue pozostają otwarte i nie blokują zamknięcia etapu 8.
