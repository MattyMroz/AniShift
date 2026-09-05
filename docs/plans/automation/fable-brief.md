---
kind: subagent-brief
mode: read-only
baseline: 369efcd
model: claude-fable-5-1
status: historical
---

# Zlecenie dla Claude Fable 5.1: kompletny pakiet planów

Historyczne zlecenie, nie instrukcja uruchomienia nowej pracy.
Aktualne przekazanie: [brief dla Pro](pro-brief.md).

## Rola i ograniczenia

Sam wykonujesz research, projekt planów i kontrolę ich spójności. Nie wywołuj
Opusa, Haiku, innych modeli ani subagentów. Narzędzie Agent nie jest potrzebne.
Prowadzący sprawdzi Twoje źródła i zapisze wynik, właściciel zatwierdzi plany.
Nie implementuj funkcji ani poprawek aplikacji.

Dozwolony odczyt kodu, testów, dokumentacji i publicznych źródeł technicznych.
Zakazane: shell, wykonanie testów lub aplikacji, instalacje, zmiany Git, pobieranie
odcinków, operacje na torrentach, modyfikacje procesów. Nie czytaj ani nie zmieniaj
`.env`, plików auth, logów, `workspace/`, ustawień runtime w `config/` ani
`shadow-slave.md`. W tle działa prywatne tłumaczenie użytkownika.

## Kontekst obowiązkowy

1. `AGENTS.md`, `docs/plans/automation/specification.md` w całości.
2. Skille `workflow`, `simple`, `research`, `specification`, `masterplan`,
   `planning`, `review`; pasujące szablony i referencje według ich routingu.
   `.agents/skills/*` to junctions. Fizyczny katalog to
   `C:/Users/MattyMroz/Desktop/PROJECTS/agents/skills/`.
   Jeśli odczyt jest zabroniony, zgłoś brak dostępu; nie twierdź, że skill nie istnieje.
3. `README.md`, `docs/work/reliability-audit/tasks.md`, `masterplan.md` i
   `plans/05-auto-preset-controls.md` w tym workstreamie.
4. Pasujące zagnieżdżone `AGENTS.md` przed badaniem kodu. Kod i aktualne wymagania
   mają pierwszeństwo przed historycznymi roadmapami.
5. Historyczne pomysły: `docs/plans/future/auto-download-anime.md`,
   `subtitle-layout-engine.md`, `other-feature-ideas.md`, `mkv-integration-plugin.md`.
   Czytaj sekcje istotne dla decyzji; nie kopiuj całych starych roadmap.

## Stan sprawdzony przez prowadzącego

- Root potwierdza Prompt Toolkit i trzy rejestry silników: translation/tts/llm.
- `application/discovery.py:discover_groups` skanuje płaski root;
  `is_primary_source`, `is_derived_product` i `classify_artifact` rozróżniają źródła
  i produkty. To są punkty reuse, nie nowy skaner sufiksów w watcherze.
- `application/service.py:discover` ma cache inspekcji na podstawie ścieżki,
  rozmiaru i mtime; to nie trwały rejestr ukończonych zleceń.
- `RunSession` ma generację i własny katalog tymczasowy; nie jest trwałym
  rejestrem subskrypcji ani blokadą między dwoma procesami AniShift.
- `plan_auto(group_ids, preset)` oraz `execute(plan, sink)` są istniejącymi
  granicami planowania i wykonania. Nie zakładaj, że uruchomienie całego Auto
  po każdym zdarzeniu folderu da deduplikację.
- `translation_handler.py:translation_verses` używa `split_line` dla dialogu
  i `split_for_layout` dla displayed. W `linebreak.py` istnieje ochrona `się`,
  ale fallbacki `_greedy_cut` i `_proportional_boundaries` trzeba zbadać.
- `subtitles/service.py:_translated_file` kopiuje style, info i eventy, zamienia
  widoczny tekst przez `replace_visible_text`. Zachowanie tagów nie dowodzi
  poprawnego dopasowania geometrycznego po tłumaczeniu.
- Wstępny pilot wykazał osiem speców AUTO_PRESET i siedem brakujących edycji
  (nie pięć). `requested_products` jest już edytowalne. Sprawdź sam aktualny kod.
  Edytory UserSettings nie obsługują automatycznie odczytu/zapisu/zależności
  AutoPreset. `save_preset` wymaga pełnego draftu. Reset produktów nie resetuje
  automatycznie wszystkich polityk presetu.
- Ostatnie pełne testy: 3014 passed, 2 failed, 9 skipped. Dwa failure wynikają
  z prywatnego dodatkowego stylu `shadow-slave` i sztywnej oczekiwanej listy.
  Nie naprawiaj ich w tym zleceniu i nie ogłaszaj zielonego suite.

## Research do wykonania

### A. Obecny produkt i ustawienia

Zweryfikuj brakujące opcje Auto, ownera zapisu i resetu, wąski zakres poprawy
UX oraz sens struktury katalogów. Raportuj tylko potwierdzone luki i zbędną
złożoność, bez obietnicy znalezienia wszystkich błędów. Przygotuj uzupełnienie
istniejącego Planu 05, nie konkurencyjny plan tego samego zakresu.

### B. Folder i pobieranie — główny nowy feature

Porównaj jedną płaską bibliotekę z oddzielnymi importami/outputem. Propozycja
prowadzącego: jeden folder, ręczny tryb i jawny przełącznik watch; produkty obok
źródła, stan poza biblioteką. Nazwij konflikt: w jednym folderze przy aktywnym
watch zwykłe wrzucenie nie komunikuje intencji ręcznej. Zaproponuj prosty pause/skip.

Przeanalizuj: kopiowanie niedokończone, pliki prealokowane, rename/delete,
samowzbudzenie na produktach, restart, identyfikację zlecenia, zależne napisy
sidecar, nowe pliki przy aktywnym runie, dwa procesy obserwujące ten sam folder,
ledger versus reuse istniejącego schedulera, brak produktu wcześniej ukończonego,
zmianę źródła i ustawień, jednoznaczne ponowienie. Nie obiecuj dokładnie-jednokrotnego
zewnętrznego wywołania modelu przy awarii w nieznanym momencie.

Zbadaj qBittorrent Web API i alternatywę wbudowanego klienta pod Windows/Python
3.14. Najpierw reuse istniejącej zależności HTTP; nowa biblioteka tylko z dowodem
korzyści. Nie zakładaj zainstalowanego klienta. Sprawdź wyszukiwanie i źródła,
sezony, aliasy tytułu, numerację, wybrane odcinki batcha, duplikaty, v2 wydania,
seedowanie, cancellation, ukończenie wybranych plików, bezpieczeństwo ścieżek
i płaski layout. Nie przyjmuj `NoSubfolder` jako gwarancji usunięcia wszystkich
wewnętrznych katalogów torrenta. Nie przemieszczaj danych za plecami klienta.

Subskrypcja: owner harmonogramu, start po zamknięciu UI, offline i sleep/resume,
backoff/429, brak wielogodzinnego nadrabiania zaległych ticków, stop/pause,
stan pozyskania oddzielony od stanu przetworzenia. Zaprojektuj grupowaną listę
terminalową, sortowanie, zaznaczenie epizodów, prawdziwy postęp, brak wyników i błędy.

### C. Dialog PL, ozdobny ASS i kadr

Nie planuj globalnego zamieniania tekstu ani prostego zakazu jednego słowa.
Ustal hierarchię: niezmienność tekstu/grafemów/tagów, interpunkcja i związki
składniowe, czytelność, geometria, estetyka. `się` nie powinno zaczynać nowego
drugiego wersu przez decyzję algorytmu. Konflikty ograniczeń mają jawną degradację.

Oddziel dialog od ozdobnych displayed; zbadaj preservation `\N`, `\n`, `\h`,
inline tagów, `\pos`, `\move`, clip, transformacji i karaoke. Nie zakładaj,
że proporcjonalne mapowanie znaków zachowa semantykę zdobień. Fonty i bounds
mierzyć względem wideo/PlayRes, nie monitorowych proporcji. Zbadaj ustawienia
mpv/libass/Aegisub; nie zmieniaj konfiguracji odtwarzacza użytkownika.
Przygotuj plan małego deterministycznego korpusu i syntetycznego render proof,
bez wymagania teraz odsłuchu albo udostępnienia jego prywatnego materiału.

### D. Przegląd dawnej roadmapy

Tabela: już zrobione / częściowe / planować teraz / odłożyć / odrzucić.
Bez nowego GUI, licznika kosztów, A/B promptów, integracji odtwarzacza,
PyAV i multi-voice. TXT audiobook później. Cache metadanych tylko gdy służy
wybranemu dopasowaniu; nie osobny feature dla samego cache.

## Punkty startowe do źródeł

Otwórz źródła, sprawdź wersję i datę. Nie traktuj linków jako dowodu bez odczytu.

- https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-5.0)
- https://qbittorrent-api.readthedocs.io/en/latest/
- https://watchfiles.helpmanual.io/api/watch/
- https://www.bittorrent.org/beps/bep_0003.html
- https://aegisub.org/docs/latest/ass_tags/
- https://mpv.io/manual/stable/
- https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide

## Wynik i warunek stopu

Zwróć treść gotowych dokumentów, po polsku, ze ścieżką przed każdym dokumentem.
Nie zapisuj plików bezpośrednio. Prowadzący zachowa ten wynik i zintegruje go
przez apply_patch po review. Łącznie celuj w 5000–7000 słów, bez kopiowania skilli.

1. `docs/plans/automation/research.md`: kod + źródła z datami, ustalenia,
   sprzeczności, ograniczenia, rekomendacje, stan starej roadmapy.
2. `docs/plans/automation/masterplan.md`: stany pośrednie, zależności,
   warunki wyjścia, decyzje O01–O06. Rozwój planowany, nie zatwierdzony.
3. `docs/plans/automation/plans/01-folder-watch.md`: jeden plan watch bez
   pobierania, z ownerem stanu i kontraktem folderu warunkowym na zatwierdzenie.
4. `docs/plans/automation/plans/02-acquisition.md`: pierwsze ręczne pionowe
   przecięcie, potem subskrypcje; dalsze etapy warunkowe, nie fałszywie szczegółowe.
5. `docs/plans/automation/plans/03-subtitle-layout.md`: osobne etapy dialogu
   i ozdobnego ASS, plan eksperymentu dla niewiadomej geometrii, przypadki graniczne.
6. Dokładne proponowane uzupełnienia Planu 05 i `specification.md`, jeśli potrzebne.
7. Krótka samoocena: luki dowodowe, nierozstrzygnięte decyzje, bez deklaracji
   niezależnego review własnej pracy.

Wskaż potwierdzone istniejące ścieżki; nowe oznacz NEW. Nie dodawaj rejestru
acquisition. Jasne in scope / forbidden / deferred / tests / owner / stop.
Gdy narzędzie, źródło lub model jest niedostępny, nazwij blokadę zamiast zgadywać.
Nie prowadź nieograniczonych retry. Zakończ na dokumentach do zatwierdzenia.
