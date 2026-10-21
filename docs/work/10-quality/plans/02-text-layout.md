---
kind: plan
status: w realizacji
baseline: work/quality/21-text-layout @ bffcb3c6 (z work/quality/08-fuzzy-quality)
created: 2026-10-19
---

# Plan 02: jeden rdzeń układu tekstu (wykonanie specyfikacji v4)

Kontrakt: [text-layout.md](../text-layout.md). Ten plan mówi, w jakiej kolejności go wykonać i jak sprawdzić każdy krok. Gdy plan i specyfikacja się różnią, wygrywa specyfikacja; materialną różnicę zgłasza się orkiestratorowi.

## Rezultat

Każdy polski tekst wyświetlany przez AniShift (dialog, szyld, piosenka, napis ekranowy) układa jeden rdzeń w `anishift/services/subtitles/layout.py`, z polem jako parametrem i wagami z narzędzia kalibracji, które dowodzi spójności na katalogu (§6), ankiecie (§5.4) i praktyce zawodowców. Galeria stan wejściowy → nowy z czcionką właściciela.

## Stan obecny i luka

- Dialog: `linebreak.py` `layout_dialogue` (znaki, 42 × 2, ranking krotkowy). Szyld: `split_for_layout` + `fitting.py` `fit_signs` (Arial 64 px, podłoga 0,72). Dwa rozjechane rankingi cięcia.
- Klasy przerw (`anishift/text/gaps.py`, `idioms.txt`) istnieją tylko na odrzuconej gałęzi `work/quality/20-line-breaking` (`014cdf1d`) — do przeniesienia bez wag i kosztu z v1.9.
- Pomiar prawdziwą czcionką z emulacją libass jest w `geometry.py` (`measure_text`, `available_width`, `wrap_text`), dziś nieużywany przez układ.
- Prototyp kalibracji (poza repo): `C:\Users\MATTYM~1\AppData\Local\Temp\claude\c--Users-MattyMroz-Desktop-PROJECTS-AniShift\0488f8e2-9732-43a5-9342-fab126972e85\scratchpad\v4-cal\cal2.py` — tylko jako ilustracja cech; jego braki opisuje §5.3 specyfikacji.

## Fazy

### A. Fundamenty

1. Przenieść `anishift/text/gaps.py` i `anishift/text/idioms.txt` z `014cdf1d` (klasy, mówcy, wtrącenia, utarte zwroty, `banned`/`protected`/`turn`). Bez tablicy `STRENGTH` i bez kosztu — siłę klas daje kalibracja. Testy klas z `tests/text/test_gaps.py` tej samej gałęzi, bez asercji o wagach.
2. Dodać klasy i cechy ze specyfikacji §4.2, których brak: liczba z separatorem tysięcy, cięcie wewnątrz krótkiego cytatu, wiersz zaczynający się od pauzy wtrącenia (zakaz), znaczniki punktów listy „(n)” (granica wymuszona), słowo otwierające frazę na końcu wiersza, jąkanie „N-nie” jako jedno słowo.
3. `anishift/text/morphology.py`: zgoda przymiotnik/imiesłów przymiotnikowy + rzeczownik z Morfeusza 2 (warunki §4.2: ta sama liczba, wspólny przypadek i rodzaj, bez odczytania czasownikowego, lewe słowo bez interpunkcji na końcu, nie para przymiotnik + przymiotnik), z pamięcią podręczną. Zależność: `uv add morfeusz2`. Morfeusz zostaje w kodzie tylko po bramce z fazy C.

### B. Rdzeń

1. `layout.py` (rozszerzenie istniejącego modułu `LayoutLimits`): `Field` (szerokość maksymalna, wysokość, dozwolone/ratunkowe wiersze, wymuszone cięcia, tryb skali, skala minimalna, rodzaj pola), funkcja pomiaru wstrzykiwana (`measure(line, scale) -> szerokość jako ułamek PlayResX`), kandydaci (§5.1: pełny przegląd dla K ≤ 3, programowanie dynamiczne powyżej), stopnie szkód z §4 jako wektor cech, ocena = iloczyn skalarny z wagami, poziomy (filtry nienaruszalne → związki chronione → ratunek, §5.2), wynik z wierszami, skalą, stopniami szkód, poziomem i flagami raportu.
2. Obie miary długości (§4.1): szerokość i znaki, większa decyduje; kolana z ankiety.
3. Katalog jako dane testowe w repo: `tests/services/subtitles/data/text_layout_catalogue.json` — każdy przypadek d/s/e z §6 i każde pytanie ankiety: tekst, parametry pola, **szerokości słów i spacji zmierzone raz prawdziwą czcionką** (testy nie potrzebują czcionki; szerokość wiersza = suma), zbiór dopuszczalnych, zakazy, źródło. Generator tego pliku w `scripts/subtitle_quality/` (czyta `workspace/.quality/experiments/v4-hard`, `v4-quiz`).
4. Testy zachowania: każdy przypadek katalogu → wynik w zbiorze dopuszczalnych i bez zakazów (parametryzacja po id); rdzeń nigdy nie rozcina słowa, nie gubi treści, nie przekracza pola poza ratunkiem.

### C. Kalibracja i bramka morfologii

1. `scripts/subtitle_quality/layout_calibrate.py` (zależność narzędziowa: `uv add --group dev scipy`): program liniowy z wymaganiami §5.3 (filtry przed kalibracją, monotoniczność klas, pary miękkie dla „oba dobre”, ocena w pełnej przestrzeni kandydatów, test z pominięciem jednego przypadku, wrażliwość ±10%), wejście: katalog, ankieta, zawodowcy NF+AMZN(+CR z niższą wagą) z `workspace/.quality/experiments/lb-research/opus55/dataset.json`. Wynik: wagi + raport `docs/work/10-quality/research/text-layout-calibration.md` (wykonalność, naruszenia, LOO, wrażliwość).
2. Niewykonalność → lista najmniejszego zbioru sprzecznych przypadków, stop, zgłoszenie orkiestratorowi (pytanie do właściciela z obrazami). Nie łatać.
3. Wagi jako nazwane stałe `Final` w `layout.py` z odwołaniem do raportu kalibracji.
4. Bramka morfologii: kalibracja i ocena z cechą zgody i bez niej; narzędzie przygotowuje ślepą próbę ≥ 150 kwestii dwuwierszowych zawodowców (A/B w losowej kolejności, klucz osobno) dla obu wariantów. Oceny robią sędziowie wskazani przez orkiestratora. Morfeusz zostaje, jeśli wariant z nim ma mniej złych cięć, a katalog i ankieta nie tracą.

**Stop po fazie C** — raport dla orkiestratora i przegląd recenzenta przed integracją.

### D. Integracja dialogu

`layout_dialogue` → rdzeń z polem dialogu (szerokość maksymalna: 90% `PlayResX` od kotwicy zdarzenia, także gdy marginesy stylu są węższe; wiersz bez zawijania libass), pomiar `geometry.measure_text` z tagami danego wiersza i czcionką dialogu właściciela, gdy jest ustawiona. Tagi i znaczniki `<sN>` jak dziś (`restore_markers`, `reflow_visible_text`). Usunąć stary ranking dialogu.

### E. Integracja napisów pobocznych

`split_for_layout` i wybór w `fit_signs` → rdzeń z polami szyldu, listy i piosenki (§3.2): zmniejszenie z zachowaniem proporcji przed ściśnięciem (q15), piosenka w jednym wierszu ze zmniejszeniem (r1), liczba wierszy niewiązana z oryginałem (r2), puste wiersze autorskie na swoich miejscach, karaoke i rysunki nietknięte. Warstwa sceny w `fitting.py`: obiekty, ekran, ramka `\clip`, sąsiedzi, obwiednia obróconych rogów, kierunek wzrostu wg `\an`. Usunąć pomiar Arialem, podłogę 0,72, stary ranking szyldu.

### F. Replay i galeria (orkiestrator)

Replay nowej gałęzi z czcionką dialogu właściciela → `workspace/.quality/experiments/replay/v4`; galeria `compare` stan wejściowy (`experiments/v4-hard/baseline-font`) → `v4` z `--font` oraz obrazy „po” dla 60 przypadków zestawu trudnego. Orkiestrator ogląda każdy obraz; właściciel dostaje konkretne obrazy.

## Zakazy

- Nic na `main`, bez push, bez zmian w głównym checkoucie poza `workspace/.quality/` (tylko odczyt danych, chyba że faza mówi inaczej).
- Bez płatnych API, bez zabijania procesów python, zależności tylko `uv add`.
- Bez stałych „z ręki”: każda waga pochodzi z kalibracji; każdy próg pola (90% ekranu, kolana długości) ma odwołanie do ankiety albo specyfikacji.
- Bez łatek dla pojedynczych przypadków: przypadek, którego rdzeń nie spełnia, wraca do kalibracji albo do właściciela.

## Dowody na koniec każdej fazy

Bramki repo (`ruff check`, `ruff format --check`, `mypy` dla win32 i linux na `anishift/ tests/`), testy obszaru, na końcu fazy jeden pełny `uv run pytest -n 8`; raport fazy: commity, liczby z katalogu (ile przypadków w zbiorze dopuszczalnych), wynik kalibracji, czego nie zrobiono.
