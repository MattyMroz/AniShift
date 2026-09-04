---
kind: plan
status: verified
baseline: c2e89964a4dd7d0a8efcdefacf2a7db609ec81e8
created: 2026-09-04
---

# Plan 01 — odrzucanie nieudanego i pustego tłumaczenia

## Jeden rezultat

Żadne tłumaczenie z jawną porażką linii ani pustym wynikiem nie zostaje zapisane
przez `TranslationTaskHandler` jako kompletny polski produkt. Jego TTS i publikacja
nie uruchamiają się, ale inne niezależne grupy mogą się poprawnie zakończyć.

Zakres obejmuje A01 i A04. To pierwsza część M01, nie naprawa całego tłumaczenia:
urwany SSE oraz xAI incomplete pozostają A02/A03 i wymagają kolejnego planu.
Nie należy po tym planie deklarować pełnej niezawodności zdalnych modeli.

## Authority i kontekst do odczytu

| Kolejność | Źródło | Zakres i rola |
| --- | --- | --- |
| 1 | Root AGENTS, `tests/AGENTS.md` i AGENTS dotkniętych domen | Reguły repo; gates zawsze `anishift/ tests/` |
| 2 | `../manifesto.md`, `../audit.md` F01/F04 | Wymagania R01–R03, R07, R11–R14 i reprodukcje |
| 3 | `.agents/skills/coding/SKILL.md`, `simple/SKILL.md` oraz referencje Python/testing/comments | Styl i wykonanie minimalnej poprawki |
| 4 | `anishift/application/translation_handler.py` | Obie ścieżki zapisu: napisy i TXT |
| 5 | `anishift/services/translation/{types,service,protocols}.py` | Partial wynik domenowy i jego konsumenci |
| 6 | `anishift/services/translation/engines/google/_batching.py` | Mapowanie odpowiedzi i per-line fallback |
| 7 | `anishift/services/translation/engines/llm/{line_contract,service}.py` | Dekodowanie i istniejąca naprawa numeru |
| 8 | Testy wymienione w mapie plików oraz `application/scheduler_runtime.py` | Regresje i blokowanie zależnych zadań |

Przed pracą sprawdzić `git status`, HEAD i zakres diffu od baseline. Trzy
nieśledzone pliki promptów należą do użytkownika i pozostają nietknięte.
Legacy skille `python`/`instructions` nie były dostępne; obowiązuje znaleziony
standard `coding/references/python.md` oraz bardziej szczegółowe reguły repo.

Baseline: Ruff i oba targety mypy PASS. Pytest 2594 passed / 7 skipped po usunięciu
`NO_COLOR` tylko z procesu testowego; zwykłe środowisko ma znany failure testu koloru.
Nie naprawiać tego testu w tym diffie, nie osłabiać asercji, wynik podać oddzielnie.

## Stan aktualny i przyczyna

Google zwraca `BatchedLine(ok=False)` ze źródłem po porażce. Rekord
`FileTranslation` może opisywać częściowy wynik, ale `is_success` oznacza tylko
brak błędu całego pliku. Handler używa tego jako zgody na zapis `FULL_PL`.
Puste per-line Google ma dodatkowo `ok=True`. Parser LLM sprawdza niepustość
przed dekodowaniem, przez co literalne `\n` może zostać zaakceptowane jako tekst.

Naprawa musi znaleźć się na granicy uznawania produktu i w dwóch miejscach
tworzących błędną informację o niepustości. Nie jest potrzebny nowy framework
walidacji ani przebudowa rekordów domenowych.

## Materialne decyzje

1. Zachować historyczną semantykę `FileTranslation.is_success` i dane częściowego
   wyniku. Pełność produktu weryfikuje adapter application przed jakimkolwiek writerem.
2. Dla niepustych wejść nie akceptować `failed_lines > 0`, `ok=False` spoken
   ani pustego/whitespace wyniku. Sprawdzenie długości i pozycji używa faktycznego
   wejścia danej ścieżki; świadomie pomijane puste wejścia i rysunki nie są brakującymi
   tłumaczeniami. Nie zmieniać ich dotychczasowego zachowania.
3. Niepełny produkt daje `ExecutionError` z bezpieczną przyczyną; istniejący
   `error_context` zachowuje swoje mapowanie. Nie logować treści źródła lub wyniku.
4. Google zachowuje istniejącą, ograniczoną drabinę separator→newline→per-line.
   Reguła niepustości w per-line ma być zgodna z `_map_parts`; nieudana linia nadal
   może nieść źródło jako dane diagnostyczne, ale nie trafia do polskiego produktu.
5. Parser LLM dekoduje raz, następnie sprawdza obecność treści. Escaped newline
   z rzeczywistymi słowami jest dozwolony. Literalny backslash pozostaje poprawny.
   Pusty wynik zwraca istniejące `EMPTY_TRANSLATION` z numerem do naprawy.
6. Bez automatycznej zmiany dostawcy, nowych retry, wykrywania języka lub porównania
   `source == target` jako testu poprawności. Nie zmieniać promptów.

## Mapa plików

| Operacja | Plik / obszar | Rola |
| --- | --- | --- |
| MODIFY | `anishift/application/translation_handler.py` | Jedna lokalna reguła pełności używana przez TXT i napisy przed zapisem |
| MODIFY | `anishift/services/translation/engines/google/_batching.py` | Spójna walidacja per-line i batch |
| MODIFY | `anishift/services/translation/engines/llm/line_contract.py` | Niepustość po dekodowaniu |
| MODIFY | `tests/application/test_execution_handlers.py` | Oba wejścia, niepełny wynik i brak zapisu |
| MODIFY, jeśli potrzebne | `tests/application/test_scheduler.py` | Zależne zadanie blokowane, niezależna grupa kończy pracę |
| MODIFY | `tests/services/translation/test_translation_google.py` | Regression pustej odpowiedzi per-line |
| MODIFY | `tests/services/translation/test_translation_line_contract.py` | Regression decoded whitespace i prawidłowych escape |
| MODIFY, jeśli potrzebne | `tests/services/translation/test_translation_llm.py` | Naprawa tylko pustego numeru i wyczerpanie istniejącego limitu |
| READ ONLY | `translation/types.py`, `service.py`, `application/planner.py`, `publisher.py` | Chronione znaczenie partial record i kontrakty publikacji |
| READ ONLY | `anishift/utils/`, konfiguracja użytkownika, prompty, pozostałe domeny | Poza zakresem |
| CREATE po wykonaniu | `../outcomes/01-translation-integrity.md` | Rzeczywisty wynik, checks, pozostałe ograniczenia |

Nie tworzyć nowych katalogów testów ani przenosić modułów. Jeśli odpowiedni test
handlera istnieje pod inną nazwą po niesemantycznym drift, dopuszczalne jest
lokalne dopasowanie z zapisaniem go w outcome.

## Wykonanie

### 1. Odtworzenie błędu na granicy produktu

Rozszerzyć istniejące testy handlerów o kontrolowaną odpowiedź serwisu:

- ASS/SRT: jeden wynik `ok=False`, `failed_lines=1`, `error=None`;
- TXT: ten sam częściowy wynik;
- wynik pusty dla niepustego wejścia;
- istniejący poprawny wynik jako kontrola pozytywna.

Przed poprawką potwierdzić, że test wykrywa zapis/akceptację złego wyniku.
Mockować granicę dostawcy, a writer i regułę application sprawdzać rzeczywiście
w `tmp_path`. W asercji uwzględnić brak utworzenia nowego FULL_PL i zachowanie
istniejącego produktu. Nie wystarczy sprawdzenie nazwy nowego prywatnego helpera.

### 2. Zamknięcie bramki produktu

Wstawić wspólną, małą walidację po otrzymaniu `FileTranslation` i przed
`spoken_to_srt`/`write_translated`. Zachować błędy i cancellation. Dwie ścieżki
nie mają osobnych definicji sukcesu. Metadane z licznikiem failed nie zastępują
odrzucenia wyniku.

Jeśli wyniki prawidłowo pustych source entries trzeba doprecyzować, użyć
obecnej mapy wejścia/wyjścia; nie wprowadzać heurystyki rozpoznawania języka.
Zmiana publicznego schematu `FileTranslation` wymaga zatrzymania tego zakresu
i przeplanowania, nie cichego rozszerzenia diffu.

### 3. Naprawienie źródeł fałszywej niepustości

Google: wykorzystać istniejącą regułę `_map_parts` także dla per-line albo
równoważny mały wspólny helper. LLM: `_unescape` przed oceną pustki.

Regresje parsera: `\n`, `\r`, ich kombinacje i whitespace są odrzucane;
`tekst\nciąg dalszy`, literalne `\\n`, Unicode i backslash są zachowane.
Sprawdzić, że naprawa prosi tylko o wadliwy numer i kończy się błędem po swoim
obecnym limicie. Nie łączyć tego z reformą postępu.

### 4. Integracja i review

Potwierdzić, że odrzucone tłumaczenie blokuje tylko zależne TTS/publish, a drugą
grupę scheduler kończy poprawnie. Użyć istniejącego fake handlera i krótkiego
scenariusza. Ocenić finalny diff względem trzech produkcyjnych plików i wymagań.

Wykonać testy dotkniętych kontraktów, potem root gates:

```powershell
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run mypy --platform linux anishift/ tests/
uv run pytest
```

Znany failure `NO_COLOR` raportować wprost. Dodatkową kontrolę w izolowanym
procesie bez tej zmiennej wolno wykonać, aby oddzielić regresję od baseline.
Nie ustawiać nowych globalnych zmiennych ani zmieniać rzeczywistych sekretów.

## Test matrix

| Przypadek | Oczekiwany wynik |
| --- | --- |
| Częściowy Google dla spoken lub displayed | Jawna porażka produktu, brak nowego FULL_PL |
| Wszystkie requesty Google nieudane | Brak sukcesu produktu, brak zależnego TTS |
| Pusty per-line Google | Porażka linii i produktu |
| LLM escaped whitespace | EMPTY_TRANSLATION, ograniczona naprawa właściwego numeru |
| Poprawny multiline, literalne escape, Unicode | Zachowana treść i kolejność |
| Poprawne nazwy identyczne ze źródłem | Nie odrzucać na podstawie równości tekstu |
| Świadomie puste source entries / rysunki | Zachowana dotychczasowa poprawna obsługa |
| Cancellation | Brak publikacji, dotychczasowy typ cancel |
| Jedna z dwóch grup nieudana | Niezależna grupa nadal kończy się poprawnie |
| Istniejący polski produkt | Pozostaje niezmieniony po nieudanym tłumaczeniu |

## Granice i feedback

Dozwolone: nazwa prywatnego helpera, reuse test fixtures, niezbędne krótkie
docstringi i adnotacje. Zabronione: zmiana providerów, protokołu wire, retry
budżetów, UI, layoutu repo, utils, loggera, konfiguracji użytkownika i strażników.
Wynik review naprawiać w tej samej iteracji, jeśli mieści się w kontrakcie.

Ocena człowieka dla tej iteracji: krótkie kontrolowane niepowodzenie nie może
zostawić źródłowego tekstu opisanego jako polski produkt. Obecny ubogi opis błędu
w interaktywnym UI jest osobnym F16; nie wymagać jego redesignu do zamknięcia A01.
Ocena naturalności tłumaczenia ani wyglądu nie jest dowodem wymaganym dla tej
deterministycznej bramki; pełny odsłuch pozostaje M08.

## Definition of Done i przekazanie

- Regresje odtwarzają wcześniejszy błąd i przechodzą po poprawce.
- Obie ścieżki application sprawdzają pełność przed writerem.
- Google i parser nie produkują fałszywego `ok=True` dla pustki.
- Istniejąca semantyka partial record, źródła i produkty pozostają chronione.
- Wymagane gates wykonano; baseline środowiska odróżniono od nowych failures.
- Diff poddano review; brak rozszerzenia zakresu.
- Outcome podaje zmiany, polecenia i wyniki, feedback, odchylenia i stan Git.
- A01/A04 zaktualizowane na tablicy; A02/A03 nadal jawnie otwarte.

Nie commitować na main. Commit, PR i merge wymagają zakresu wynikającego z polecenia
użytkownika; sam gotowy plan nie oznacza wykonania ani publikacji.

## Review planu

2026-09-04: niezależny od autora odczyt planu, handlerów, mapowania domeny i writerów
dał PASS dla zakresu A01/A04. Sprawdzono zachowanie pustych pozycji displayed,
pomijanych spoken i rysunków oraz brak zmiany semantyki partial result. Jest to
review planu, nie wynik testów przyszłej implementacji.

Właściciel następnie zatwierdził wykonanie. A01/A04 zrealizowano i sprawdzono;
A02/A03 wykonano w Planie 02. Baseline failure koloru usunięto w osobnym Q01.
Wspólny [outcome](../outcomes/02-hardening.md) zawiera rzeczywiste wyniki,
niezależne review i ograniczenia. Historyczna kolejność powyżej pozostaje opisem planu.
