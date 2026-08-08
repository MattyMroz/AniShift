# Etap 8 — domknięcie legacy

> Status: implementacja lokalna zakończona — gotowe do PR
> Szczegółowe wymagania: [`etap-8-wymagania.md`](etap-8-wymagania.md)
> Zależności: zakończony etap 7

## Cel

Zamknąć stary roadmap bez tworzenia niepotrzebnej migracji albo nowego sposobu
dystrybucji aplikacji. AniShift pozostaje pakietem Pythona zarządzanym przez `uv`.

## Decyzje

- dystrybucja MKVToolNix i FFmpeg pozostaje rozwiązaniem z etapu 2.5;
- migrator nie powstaje, ponieważ nie istnieją dane użytkownika do migracji;
- aplikacja nie jest pakowana do EXE;
- `workspace/tmp/` zachowuje obecną nazwę;
- zewnętrzny korpus `mm_avh` pozostaje opcjonalnym źródłem regresji;
- finalne README powstanie po ustaleniu funkcji i workflow w nowym roadmapie.

## Zmiany

1. Dodać `run_anishift.bat`, wzorowany na dawnym launcherze `mm_avh`:
   - UTF-8 przez `chcp 65001`;
   - przejście do katalogu repo;
   - `uv run anishift %*`.
2. Potwierdzić brak zależności runtime od starego kodu i katalogów.
3. Uruchomić wszystkie bramki jakości oraz `run_anishift.bat doctor`.
4. Uaktualnić główny roadmap, indeks planów i issue etapu 8.
5. Zachować etap 7.1 jako wejście do nowego etapu 9.

## Poza zakresem

- naprawa backlogowych issue;
- implementacja funkcji z etapu 7.1;
- projektowanie UI v2;
- nowy korpus testowy;
- przenoszenie albo usuwanie danych spoza repozytorium.

## Definition of Done

- [x] `run_anishift.bat doctor` przechodzi także przy uruchomieniu spoza repo;
- [x] ruff, format, mypy i pytest przechodzą na pełnym zakresie;
- [x] audyt nie wykazuje zależności runtime od `mm_avh`;
- [x] repo nie śledzi binarek ani dawnych katalogów runtime;
- [x] główny roadmap, indeks i issue etapu 8 opisują aktualny stan;
- [x] nowy etap 9 przejmuje dalszą analizę produktu i wpływu na UI.
