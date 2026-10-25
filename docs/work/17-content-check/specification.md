---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: kontrola zawartości po pobraniu (E4)

## Cel

Po pobraniu odcinka AniShift wybiera drogę według tego, co faktycznie jest w pliku: polskie napisy dialogowe → bez tłumaczenia, tylko obce → tłumaczenie, brak użytecznych napisów → inne wydanie. Lektor powstaje zawsze. Zamyka pozycję „Kontrola zawartości po pobraniu” z `docs/ideas.md` §2 i etap E4 z `docs/work/08-acquisition/masterplan.md`.

## Użytkownik i intencja

Właściciel ogląda lokalnie gotowe odcinki z lektorem. Nie chce płacić za tłumaczenie istniejących polskich napisów, nie chce lektora czytającego same szyldy i nie chce ręcznie szukać innego wydania, gdy pobrane nie ma napisów.

## Stan wyjściowy

Fakty i źródła: [current-state.md](current-state.md). Najważniejsze:

- planner już omija tłumaczenie polskiej ścieżki i tłumaczy obcą (`translation_action: auto`, priorytet `pol`, `eng`);
- szyldy rozpoznaje flaga `forced` albo tytuł `sign|song|forced`; na 790 ścieżkach flaga myli się raz (pełna ścieżka SubsPlease z `forced=1`), tytuł pomija 2 z 32 szyldów;
- tempo zdarzeń rozdziela pełne ścieżki (≥ 7,98/min) od szyldów (≤ 1,52/min) bez pomyłki;
- kontrola po pobraniu (H2) bada tylko obraz i czas, tylko dla subskrypcji; `replacement()` nie ma wyzwalacza.

## Ustalenia (obowiązujące, z wcześniejszych decyzji właściciela)

- **U-07:** o języku decyduje zawartość pliku, nie nazwa. Deklaracja PL nie pomija tłumaczenia. (`docs/work/08-acquisition/specification.md` U-07)
- **U-08:** lektor zawsze, także przy polskim dubbingu; pełne PL → bez tłumaczenia; tylko obce → tłumaczenie; brak użytecznych napisów → automatycznie jedno kolejne wydanie z rankingu, po drugiej porażce problem do ręcznego wyboru. Tło lektora wybiera istniejący priorytet audio.
- **Limit ścieżki ręcznej:** nigdy więcej niż dwa pobrania jednego odcinka bez decyzji użytkownika. **Limit subskrypcji:** 3 automatyczne próby na cel, jeden budżet dla tożsamości, czasu i napisów (K-09, `plans/05-e1-subscription-decisions-2026-09-28.md`).
- **K-09:** błąd sondy (`ffprobe`/`mkvmerge`) to nie odrzucenie; przy niepewności plik zostaje.
- **K-10:** kontrole U-07/U-08 obowiązują także pobrania ręczne; brak masowego skanowania Biblioteki wstecz.
- **I-02 / przejście 18:** zlecenie ręczne nie przechodzi kontroli czasu H2.
- **R-07:** zamiana = `subscription_choice.replacement` (pierwszy dopuszczalny według `choice_key`, bez czekania na PL i progu, z wykluczeniem całych wypróbowanych hashy; nigdy `niepewny`).
- **I-08:** każda decyzja automatu (zamiana wydania, odrzucenie) ma powód widoczny w szczegółach odcinka; `decisions.jsonl` jest kopią dowodową.

## Pojęcia

- **Ścieżka tekstowa:** ścieżka napisów `ass`/`ssa`/`srt` (tak jak dziś w plannerze). Napisy obrazkowe nie są tekstowe.
- **Rola ścieżki:** `dialog` albo `szyldy` (szyldy, piosenki, forced).
- **Werdykt pliku:** `polskie` (jest tekstowa ścieżka `pol` w roli `dialog`), `obce` (brak polskiej, jest inna w roli `dialog`), `brak` (żadnej tekstowej ścieżki w roli `dialog`).
- **Niepewna rola:** rola rozstrzygnięta regułą zapasową (D1), a nie tempem.

## Wymagania funkcjonalne

### Rozpoznanie roli ścieżki

1. Rola ścieżki wynika z jednej reguły używanej przez kontrolę po pobraniu i przez planner. Planner nie ma własnej kopii.
2. Gdy znana jest liczba zdarzeń i czas pliku, rolę wyznacza tempo zdarzeń według progów D1.
3. Gdy tempo wypada między progami albo liczba zdarzeń jest nieznana (brak pola lub zero), rolę wyznacza reguła zapasowa D1 i rola jest oznaczona jako niepewna.
4. Sama flaga `forced` przy znanym tempie nie zmienia roli ścieżki z tempem dialogu.
5. Język ścieżki odczytuje się z tagu, tak jak dziś (`pl`, `pol`, `pl-pl` → `pol`).

### Werdykt i droga

6. Kontrola po pobraniu wyznacza werdykt pliku przed nazwaniem i publikacją, na tym samym odczycie sondy co H2.
7. Werdykt `polskie` i `obce` nie zatrzymuje pliku; droga tłumaczenia wynika z istniejącego plannera i ustawień (D4).
8. Werdykt `brak` odrzuca plik przed publikacją z powodem „brak napisów dialogowych”, niezależnie od trybu `record_only` kontroli czasu.
9. Napisy towarzyszące w tym samym zestawie odcinka (plik `ass`/`srt` z tym samym katalogiem i stemem co wideo) liczą się jako ścieżka w roli `dialog`; plik z takim towarzyszem nie dostaje werdyktu `brak`.
10. Kontrola niewykonana (brak binarki, nieobsługiwany kontener, druga awaria sondy) nie odrzuca pliku; zachowanie jak dziś (`skipped`).

### Subskrypcja

11. Odrzucenie `brak` zamyka próbę tak jak dzisiejsze odrzucenie kontroli: cel wraca do kolejki, następna próba wyklucza wypróbowany hash, budżet 3 prób jest wspólny.
12. Szczegóły odcinka i powiadomienie pokazują powód „brak napisów dialogowych”.

### Pobranie ręczne

13. Pobranie ręczne przechodzi tylko kontrolę zawartości (bez kontroli czasu, I-02).
14. Odrzucenie `brak` pobrania ręcznego uruchamia automatycznie jedną zamianę: `replacement()` na świeżych kandydatach `search_episode` z wykluczeniem hashy wszystkich przyjęć tego odcinka, przyjęcie przez `_admit_episode(previous=<odrzucone>)`.
15. Zamiana nie uruchamia się, gdy odrzucone przyjęcie samo zastąpiło przyjęcie odrzucone z powodu `brak` (najwyżej dwa pobrania bez decyzji użytkownika). Wtedy, albo gdy `replacement()` zwraca `None`, odcinek pokazuje problem do ręcznego wyboru: Stan „Brak napisów” i istniejąca podpowiedź „P pobierz ponownie”.
16. Zamiana przetrwa restart: odrzucone przyjęcie bez następcy, które spełnia warunek z punktu 15, dostaje zamianę po starcie ownera; ponowienie nie tworzy drugiego przyjęcia.
17. Wyszukiwanie zamiany biegnie w puli I/O ownera, nigdy na wątku ownera.

### Dowody

18. Każdy wynik kontroli zawartości (werdykt, niepewność, odrzucenie, zamiana albo jej brak) ma wpis w `decisions.jsonl` z dozwolonymi kluczami, bez nazw plików i ścieżek.
19. Odrzucenie i jego powód są trwałe w stanie ownera dla obu źródeł przyjęcia.

## Wymagania jakościowe

- Kontrola nie dodaje drugiego uruchomienia sondy: werdykt powstaje z katalogu, który H2 już czyta (dla pobrań ręcznych sonda biegnie raz).
- Reguła roli jest czystą funkcją bez I/O, testowaną na przypadkach z §5 `current-state.md`.

## Inwarianty

- Lektor powstaje z każdego opublikowanego odcinka tak jak dziś; E4 nie zmienia produktów ani TTS.
- Ranking, `usable`, `admissible`, `replacement` i `choice_key` bez zmian.
- Plik odrzucony przez kontrolę nigdy nie trafia do roota workspace ani do Auto.
- Błąd sondy nigdy nie odrzuca pliku (K-09).
- Ręczny wybór ścieżki w Ręcznym nadal omija degradację (test `test_manual_selected_signs_track_is_honoured_without_demotion`).
- Pliki wrzucone do workspace ręcznie (bez pobrania) nie przechodzą kontroli; plik z samymi szyldami nadal dostaje nieblokujące ostrzeżenie `subtitle_dialogue_missing` (zmienia się tylko to, co liczy się jako szyldy).

## Ograniczenia

- Tylko Windows; bramki z `AGENTS.md`.
- Zmiana inwariantu `EpisodeAssignment` (wynik kontroli także dla przyjęcia ręcznego) wymaga podbicia `WATCH_STATE_SCHEMA_VERSION` z migracją i kopią (D6).
- Rezydent właściciela działa z checkoutu: przed pierwszym uruchomieniem kodu ze schematem 6 właściciel zamyka rezydenta.

## Zakazane

- Nowa zależność, model językowy albo detekcja języka z treści.
- Ekstrakcja ścieżek lub parsowanie ASS w kontroli po pobraniu.
- Zmiana rankingu, progów A1, limitów prób subskrypcji albo polityki czekania na PL.
- Masowe skanowanie istniejącej Biblioteki.
- Zmiana wyglądu panelu poza nowym tekstem powodu.

## Zakres

- reguła roli ścieżki i werdykt pliku;
- liczba zdarzeń w neutralnym katalogu mediów (MKV i MP4);
- planner na wspólnej regule;
- odrzucenie `brak` w kontroli przed nazwaniem dla obu źródeł;
- automatyczna jedna zamiana w ścieżce ręcznej;
- teksty powodu w szczegółach odcinka;
- migracja schematu 5 → 6;
- aktualizacja `AGENTS.md` w zmienianych obszarach, `docs/ideas.md`, masterplanu 08 i `docs/README.md`.

## Poza zakresem

- Polskie napisy z zewnętrznych źródeł (`docs/ideas.md` §1.5) — osobne badanie; E4 nie zakłada, że zastąpią tłumaczenie.
- Wykrywanie błędnie otagowanego języka (ścieżka `pol` z angielskim tekstem).
- Usunięcie legacy `services/extraction/tracks.py` i jego kopii wzorca — porządki E5; kierunek zależności nie pozwala mu użyć reguły z `application/`.
- Wybór między PL a PL `Dubtitle` — dziś decyduje niższe ID; bez zmian.

## Odrzucone

- **Sama flaga `forced`:** odrzuciłaby pełną ścieżkę SubsPlease Dark Summoner 03.
- **Sam tytuł:** pomija szyldy Judas z tytułem `English`.
- **Wspólny próg względem najdłuższej ścieżki w pliku:** w Seihantai CR najdłuższa ścieżka ma 984 zdarzenia, a pełne EN/PL po 488 (stosunek 0,50); niestabilne.
- **Wpięcie napisów do `verify()` kontroli czasu:** pobranie ręczne nie przechodzi H2 (I-02), a `record_only` gasi odrzucenia.
- **Reakcja dopiero w plannerze (po publikacji):** plik byłby już w roocie i w Auto; zamiana wymagałaby cofania publikacji.

## Warunki sukcesu

- Testy jednostkowe reguły na przypadkach granicznych z `current-state.md` §5 (Dark Summoner, Judas, `Forced` 36 zdarzeń, tajski AMZN 188 zdarzeń, brak liczby, zero zdarzeń).
- Testy integracyjne ownera: subskrypcja z wydaniem bez napisów bierze następne; trzy wydania bez napisów kończą `EXHAUSTED`; pobranie ręczne bez napisów dostaje jedną zamianę; druga porażka daje problem; restart po odrzuceniu nie dubluje zamiany.
- Bramki repo zielone.
- **H4 (właściciel):** prawdziwy odcinek z PL → bez zadania tłumaczenia, z lektorem; prawdziwy odcinek bez PL (np. SubsPlease) → tłumaczenie i lektor. Przypadek „brak napisów” sprawdzają tylko testy, bo w próbce go nie ma.

## Nierozstrzygnięte (decyzje właściciela)

Każda pozycja ma rekomendację; plan zakłada rekomendację, dopóki właściciel nie zdecyduje inaczej.

- **D1. Progi i reguła zapasowa.** Rekomendacja: tempo `< 2,5` zdarzenia/min → szyldy; `≥ 5` → dialog; pomiędzy albo bez liczby → szyldy tylko przy słowie `sign|song|forced` w tytule **albo** fladze `forced`, inaczej dialog; rola niepewna. Uzasadnienie: zmierzona przerwa 1,52–7,98 na 790 ścieżkach; margines ok. 1,6× od strony szyldów i 0,6× od strony dialogu. Masterplan 08 przewidywał jako zapas sam tytuł; dodanie flagi łapie przypadek Judas przy braku liczby. Pytanie: czy flaga `forced` ma wchodzić do reguły zapasowej?
- **D2. Budżet po ręcznym „Pobierz ponownie”.** Gdy użytkownik po dwóch porażkach sam wybierze trzecie wydanie i ono też nie ma napisów — rekomendacja: bez automatycznej zamiany, od razu problem do ręcznego wyboru (każda dalsza próba to decyzja użytkownika). Alternatywa: każdy ręczny wybór daje nowy budżet jednej zamiany.
- **D3. Los odrzuconego pliku.** Rekomendacja: nie publikować; plik zostaje tylko w stagingu do istniejącego sprzątania anulowanej próby; odcinek pokazuje problem. Alternatywa: po wyczerpaniu zamian opublikować surowe wideo bez lektora.
- **D4. Ustawienia wygrywają.** Gdy użytkownik ustawi `eng` przed `pol` albo „Zawsze tłumacz”, AniShift tłumaczy mimo polskich napisów. Rekomendacja: zostawić ustawienia nadrzędne (domyślne spełniają U-08), bez nowego wyjątku.
- **D5. Obcy język spoza listy priorytetów** (np. tylko arabskie dialogi). Rekomendacja: werdykt `obce` i tłumaczenie z tego języka; bez zamiany wydania.
- **D6. Schemat stanu 5 → 6.** Rekomendacja: podbić wersję z migracją bez zmiany danych i kopią `state.json.e4-migration.bak`, żeby powrót do starszego kodu miał gotową kopię. Wymaga zamknięcia rezydenta przed pierwszym startem nowego kodu.
- **D7. Niepewna rola w panelu.** Rekomendacja: tylko wpis w `decisions.jsonl`, bez nowego tekstu w panelu (w próbce zero takich ścieżek). Alternatywa: notka „napisy niepewne” w szczegółach odcinka.
- **D8. Zamiana ręczna w globalnej pauzie.** Rekomendacja: działa, bo jest częścią zlecenia D użytkownika (U-08 „automatycznie jedno kolejne wydanie”), a pauza nie wstrzymuje pracy użytkownika; zamiana subskrypcji czeka na wznowienie jak dziś. Alternatywa: zamiana ręczna też czeka na wznowienie.
