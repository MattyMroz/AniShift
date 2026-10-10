---
kind: intent
created: 2026-10-10
status: kierunek wybrany na podstawie delegacji właściciela (tryb nocny); punkty „do potwierdzenia” czekają na właściciela
---

# Intencja: cztery zakładki panelu jako jedna moneta

## Problem i potrzeba

Właściciel codziennie używa panelu (`uv run anishift`): sprawdza, co czeka w subskrypcjach, dodaje sezon, zagląda,
co się przetwarza, otwiera gotowe odcinki. Cztery zakładki (Anime, Subskrypcje, Przetwarzanie, Biblioteka) powstały
w różnych etapach i zachowują się różnie. Właściciel chce (2026-10-10): intuicyjnego poruszania się, mniej słów
i podpowiedzi na dole, mniej zbędnych opcji, ujednolicenia (np. Biblioteki), możliwie startu na Subskrypcjach
i połączenia wyszukiwarki z subskrypcjami. Wygląd (kolory, niebieski akcent, styl CLI/TUI z górą i dołem ekranu)
zostaje.

## Podstawa (fakty)

Spis ekranów z renderami 50/80/120 kolumn: `%TEMP%\opencode\tui\inventory.md` i `screens\` (2026-10-10).
Najważniejsze obserwacje:

- ten sam klawisz znaczy co innego w różnych zakładkach: `D` pobierz / dodaj / szczegóły, `C` kopiuj / anuluj
  zlecenie, `F` szukaj teraz / folder, `S` subskrybuj / szukaj w Historii;
- skróty `M`, `U`, `O` działają w trzech zakładkach, a pokazuje je tylko Przetwarzanie;
- dwie rodziny układu: Anime i Subskrypcje mają tytuł, kolumny i slot powiadomień, a Przetwarzanie i Biblioteka
  same wiersze;
- stopki do 18 słów, w różnej kolejności, z dopisanym wszędzie `←→ widok · ↑↓ wybierz`; przy 50 kolumnach urwane
  `Esc wr…`;
- linia statusu automatu ma trzy różne formy, a Biblioteka i Anime jej nie mają;
- `?` działa tylko w Anime i pokazuje stałe trzy linie, także z klawiszami, które na danym ekranie nie działają;
- panel startuje na Przetwarzaniu (`state.py:289`), zadanie dyżurne, a nie codzienne;
- błędy: martwe `A wszystkie` w Ręcznym (`manual.py:588`), surowe ID `SUBTITLE_MAX_CHARS_PER_LINE` jako tytuł
  w Ustawieniach (`settings.py:1907`), `C` w Przetwarzaniu anuluje całe zlecenie bez potwierdzenia.

## Rozważone kierunki

Burza mózgów (trzy perspektywy: spójność, redukcja, przepływy; `%TEMP%\opencode\tui\brainstorm-{a,b,c}.md`):

- **B0, tylko spójność:** bezpieczne, ale nie spełnia życzenia startu na Subskrypcjach.
- **B+, cztery zakładki, start na Subskrypcjach, `/` z Subskrypcji do wyszukiwarki, wspólna gramatyka klawiszy,
  stopki, `?` i status:** wybrany.
- **A, wyszukiwarka wbudowana w listę subskrypcji:** odłożony. Pole tekstowe na ekranie codziennym zderza się
  z literami akcji (`S`, `W`, `X`, `R`), dochodzi trzecia rodzina układu i dwa konteksty U08. Wysoki koszt,
  słaba odwracalność. Wrócić, jeśli B+ po tygodniu nie wystarczy.
- **C, „Oglądam / Szukam / Pracuję”:** wizja; wymaga nowego modelu łączenia subskrypcji z zestawami `ready/`.

## Kierunek (decyzja delegowana, odwracalna)

B+ według planu `plan.md`. Zasada nadrzędna: jeden słownik klawiszy, jedna stopka budowana z tej samej listy akcji
co pomoc `?`, jeden szkielet ekranu (zakładki, okruszek, treść, stopka, status), bez zmiany kolorów i układu
góra/dół. Funkcje, o które właściciel prosił (czekanie na PL, `T`, subskrypcje, ręczny wybór wydania, kolumny
Jakość i Pewność, nota kalibracji w szczegółach), są nietykalne. Wolno zmienić tylko ich podpowiedź.

## Do potwierdzenia przez właściciela (wykonane, ale odwracalne)

- **Start panelu na Subskrypcjach.** Zmienia wcześniejszą decyzję (spec `docs/work/acquisition/spec.md` i PR-06:
  „panel startuje na Przetwarzaniu”).
- **Nowe klawisze, stare działają dalej jako ciche aliasy:**
  - Subskrypcje: `/` szukaj i dodaj (było `D`; alias `D`), `R` sprawdź teraz (było `F`), pauza tylko `W`
    (alias `Space`);
  - Przetwarzanie: `X` anuluj z pytaniem „Enter tak · Esc nie” (było `C` bez pytania; alias `C`);
  - Biblioteka: `?` szczegóły (było `D`), `X` usuń obok `Delete`;
  - Historia: `/` szukaj (było `S`).
- **„Połączenie wyszukiwarki z subskrypcjami” w tej wersji** to wyłącznie `/` z listy subskrypcji do
  wyszukiwarki i `Esc` z powrotem, czyli dzisiejsze `D` pod czytelniejszym klawiszem. Pełne wbudowanie (wariant A)
  odłożone.
- **Zmienione kontrakty panelu:**
  - linia statusu automatu widoczna także w Anime i Bibliotece (dziś Anime jej nie ma, a Biblioteka pokazuje ją
    tylko przy pauzie);
  - nowy format linii statusu: zamiast `↓ N · Przetwarzanie N · Czeka N · Praca` jest
    `Automat: praca · pobiera N · przetwarza N · czeka N`, a przy pauzie `Automat wstrzymany`. W Anime status
    znika przy wysokości poniżej 13 wierszy;
  - Biblioteka pokazuje trwały komunikat po usunięciu „Usunięto · Ctrl+Z cofnij”;
  - w szczegółach (Anime, U08, Biblioteka) klawisze działają jak dziś, z trzema wyjątkami:
    - `Backspace` zamyka szczegóły;
    - w szczegółach Biblioteki `X` działa jak `Delete`, `Tab` i `←→` zamykają je i przełączają zakładkę, a `O`,
      `M` i `U` działają;
    - zmieniają się podpowiedzi: trzy stałe linie skrótów w Anime zastępuje lista generowana, pod plikami
      w szczegółach Biblioteki jest pomoc, a ich stopka ma format `Enter otwórz plik · F folder · X usuń · Esc wróć`;
  - o połączeniu informują tylko treść „Łączenie…” i status `Automat: brak połączenia`; znikają komunikat
    „Łączenie z procesem w tle…” i osobne wiersze „Brak połączenia”;
  - tytuł `ANIME` na listach tytułów i wpisów znika (okruszek na tym poziomie jest pusty), a „Wybierz plik”
    i głębsze ekrany mają okruszek `Anime › …`. Na polu zapytania `ANIME` zostaje, a ze stopki zapytania
    znika `Tab widok`;
  - bez liczników status pokazuje `Automat: bezczynny`;
  - w Przetwarzaniu `Delete` (jak `X` i `C`) uzbraja pytanie, zamiast działać od razu.
- **Stopki bez `←→ widok · ↑↓ wybierz` i z najwyżej 3 akcjami.** Część podpowiedzi (`I` wydania, `P` ponownie,
  `Z`, `A`, `R`, `X`, `Ctrl+Z`, `M`, `U`, `O`) jest tylko pod `?`, a sama `?` działa w każdej zakładce. Zmienia to
  ustalenia cli/AGENTS („navigation hints drop first”) i `ux.md:256` (pusta lista z `D dodaj · Ctrl+Z cofnij`).
  Pusta lista Subskrypcji ma treść „Brak subskrypcji” i stopkę `/ dodaj pierwszą · ? więcej · Esc wróć`.
- **Etykiety i okruszki:**
  - `Esc` ma etykietę „wróć” wszędzie (znikają „lista”, „bieżące” i „anuluj” w szkicu);
  - okruszek ma jeden format `Zakładka › Element` (`ANIME ›` → `Anime ›`);
  - nad listą subskrypcji nie ma już tytułu „Subskrypcje”;
  - informacja „ostatnie 30 dni” Historii jest w `?`.
- **`Backspace` działa jak `Esc`** w Anime (poza polem tekstowym) i w Ręcznym.
- **Liczby w linii statusu** pochodzą zawsze z liczników automatu. W Przetwarzaniu lista pokazuje wszystkie
  wiersze, a status tylko liczniki automatu (dziś liczba wierszy listy).
- **Naprawy błędów przy okazji:**
  - litera `O` na polu wyszukiwania Anime przełączała automat zamiast wpisać się w pole;
  - `/` w szczegółach subskrypcji zostawiał stary kontekst, więc `X` mógł usunąć nie tę subskrypcję;
  - martwe `A` w Ręcznym;
  - surowe ID zamiast tytułu w Ustawieniach.
- **Kategoria „Zaawansowane” w Ustawieniach:** odłożona do osobnej decyzji. Review wykazało, że przeniesienie
  opróżni kategorie Napisy, Ogólne i Pobieranie.

## Świadomie poza kierunkiem

Wbudowanie wyszukiwarki w listę (A), widok „Oglądam” (C), przeniesienie Historii do Biblioteki, usunięcie wierszy
„Cofnij/Anuluj/Wróć” z Ustawień i Ręcznego, tłumaczenie komunikatów planera w Ręcznym, zmiana `Ctrl+C`.
