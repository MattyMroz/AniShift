---
kind: package-index
status: implemented-e2e-verified
updated: 2026-09-06
baseline: bc74425b487fb9110da76911c26dca4194b2aad9
implementation: plans/01-watch-mode.md, plans/02-search-and-download.md, plans/03-subscriptions.md (branch work/local-automation/01-watch)
language: pl
---

# AniShift | pełny pakiet lokalnej automatyzacji

## Pliki do przekazania wykonawcy

**[Masterplan implementacji](masterplan.md): kontrakt projektowy (sekcje 1–14), 16 faz i 128 uporządkowanych kart zadań ze scenariuszami weryfikacji.**

| Dokument | Zawartość |
| --- | --- |
| [spec.md](spec.md) | Cel, sześć przepływów, 30 wymagań, granice i odbiór. |
| [research.md](research.md) | Aktualny kod, integracje, biblioteki, alternatywy, 43 źródła i ograniczenia dowodu. |
| [brief.md](brief.md) | Wybrany stos, kompromisy, konfiguracja i rzeczywiste decyzje właściciela. |
| [masterplan.md](masterplan.md) | Architektura, schemat danych, kontrakty, foldery, stany, fazy i zadania plik po pliku. |
| [handoff.md](handoff.md) | Instrukcja dla agenta kodującego, granice lokalnej adaptacji i bramki. |

## Co ma powstać

Wpisujesz tytuł, wybierasz sezon/grupę albo zapisujesz subskrypcję. Worker pobiera wskazane pliki przez qBittorrent, kopiuje je bez naruszania oryginałów, uruchamia obecny rdzeń i układa wyniki w bibliotece. Każdy gotowy fizyczny plik jest dostępny niezależnie od reszty paczki.

Wrzucenie własnego MKV/MP4 do inbox działa bez otwierania Auto. Po świadomym włączeniu autostartu worker czuwa po zalogowaniu. Jedno opcjonalne okno pokazuje postęp i może zostać zamknięte bez przerwania obróbki.

## Rozstrzygnięcia

Lokalny worker, SQLite, obecne AppService/GraphScheduler i Prompt Toolkit, qBittorrent WebUI loopback, AniList, Nyaa RSS + historia, dodatkowy publiczny RSS, własny inbox i katalogi rewizji. Bez VPS, chmury, nowego UI, Redis/Celery/Docker i przepisywania TTS.

Wybór qBittorrent jest rekomendacją techniczną, nie stwierdzeniem, że jest to obecny klient właściciela. Dwie ulubione grupy nie zostały nazwane, więc pakiet ich nie zgaduje.

**MAL:** opcjonalny import XML i lokalne obejrzane; bez automatycznego zapisu na konto lub pełnej synchronizacji w tej edycji.

## Relacja do wcześniejszego pakietu

[docs/plans/automation/](../automation/README.md) z tego samego dnia zakładał najbliższy mały wycinek (A01) i zostawiał otwarte SQLite/JSON oraz VPS. Ten pakiet jest odpowiedzią na tamten brief i zastępuje tamten masterplan kierunkowo: pełny zakres lokalny, SQLite, bez VPS. Tamte dokumenty pozostają historią i źródłem ustaleń właściciela U01–U14; nie są równoległą kolejką wykonania.

## Stan pakietu

Plan przygotowano na bazie `MattyMroz/AniShift` z commitu `bc74425b487fb9110da76911c26dca4194b2aad9`. Starszy brief „tylko jeden wycinek” nie ogranicza obecnego pełnego zlecenia.

Po przeglądzie właściciela z 2026-09-05 usunięto pliki pomocnicze generatora (eksport zadań, mapę pokrycia, sumy kontrolne, raport walidacji dokumentów, rejestr źródeł zdublowany z research.md) i zmieniono limity równoległości na ustawienia użytkownika. Pokrycie wymagań jest w polu **Realizacja** każdego R w spec.md.

To komplet dokumentów planistycznych. Nie jest implementacją. Nie instalowano klienta, nie włączano autostartu, nie zmieniano kont, nie pobierano odcinków użytkownika i nie uruchamiano suite aplikacji. T003/T004 oraz końcowe próby Windows/live/human mają dopiero dostarczyć właściwy dowód runtime.

Dokument zawiera rozstrzygnięte decyzje i konkretne testy dla niepewnych integracji. Nie daje nieuzasadnionej gwarancji, że wszystkie zewnętrzne API pozostaną niezmienne albo że nie ma błędów.

## Implementacja

Wykonane na gałęzi `work/local-automation/01-watch` (2026-09-05/06), każdy plan z sekcją „Wynik wykonania”:

| Plan | Rezultat | Zastępuje fazy |
| --- | --- | --- |
| [plans/01-watch-mode.md](plans/01-watch-mode.md) | czuwanie na istniejącym Auto, podfoldery serii, okno partii, autostart | P02–P04, P12 |
| [plans/02-search-and-download.md](plans/02-search-and-download.md) | ekran Anime: nyaa, 1080p+, grupy, Space/Enter, qBittorrent, `qbit` | P06, P07, P11 |
| [plans/03-subscriptions.md](plans/03-subscriptions.md) | klawisz `O`, sprawdzanie co godzinę w czuwaniu, `subs` | P09 |

Przebieg e2e z 2026-09-06 (plan 03, sekcja „Przebieg e2e”): Web UI qBittorrenta włączone na localhost, `qbit setup`,
subskrypcja Solo Leveling od odc. 25 → pobranie → okno partii → `.pl.ass` i `.eac3` w 2,5 min. Po drodze naprawiono
raport 202 Web API 2.15, podwójne dodawanie torrenta przy kolejnym sprawdzeniu, tolerancję długości lektora
w inspekcji i ponowne otwieranie okna dla grupy zakończonej kodem 0. `anishift doctor` raportuje czuwanie i autostart.

Właścicielowi zostaje obserwacja: nowy odcinek obserwowanej serii ma dopłynąć sam (sprawdzanie co godzinę) oraz
przejście przez ekran Anime klawiaturą (Space/Enter/O), które w e2e wykonano przez fasadę, nie przez TUI.

Fazy masterplanu bez planu wykonania i powód: P05 (katalog AniList) i P13 MAL to nie-cele właściciela (KISS);
P08 (paczki) pokrywa wiersz paczki w ekranie Anime plus rekurencyjne discovery podfolderu qBittorrenta;
P10 (odtwarzanie) nie ma na tej maszynie odtwarzacza obsługującego zewnętrzną ścieżkę audio, produkty leżą obok
źródła; P14 scenariusze awarii są testami jednostkowymi planów 01–03; P15 to ten katalog.

Wykonawca zaczyna od [handoff.md](handoff.md), potem od aktualnego planu w `plans/`. Cały katalog można umieścić w `docs/work/local-automation/`. Zachowanie nazw plików utrzymuje linki względne.
