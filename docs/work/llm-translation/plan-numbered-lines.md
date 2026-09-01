---
kind: plan
status: ready
updated: 2026-09-02
---

# Plan: numerowane linie zamiast JSON-a na granicy tłumaczenia LLM

## Cel

Zamienić format granicy tłumaczenia LLM z kontraktu JSON na numerowane linie
`[N] tekst`, zachować pełny rygor walidacji, dodać naprawę zawężoną do zepsutych
numerów i doprowadzić do tego, że cały plik napisów idzie w jednym żądaniu.

## Rezultat użytkownika

Tłumaczenie jednego odcinka wykonuje jedno żądanie do modelu zamiast siedmiu,
odpowiedź zużywa o około 20% mniej tokenów, a każde przekłamanie liczby lub
kolejności linii jest wykryte i naprawione żądaniem dotyczącym wyłącznie zepsutych
linii.

## Warunki końcowe

- Silnik LLM wysyła i przyjmuje wyłącznie numerowane linie `[N] tekst`.
- Parser odrzuca każde naruszenie wymienione w specyfikacji i wskazuje numery,
  których dotyczy.
- Naprawa prosi wyłącznie o numery brakujące lub unieważnione.
- Domyślnie cała partia pliku idzie w jednym żądaniu.
- `llm_max_output_tokens` ma domyślną wartość 32000.
- Bramki jakości repozytorium przechodzą względem zastanego baseline'u.
- Przelot na żywo tłumaczy wszystkie odcinki z `workspace/` modelem
  `gpt-5.6-terra` na Foundry bez błędu terminalnego.

## Nie-cel

- Poprawianie jakości merytorycznej tłumaczenia.
- Zwijanie powtarzających się napisów ekranowych.
- Kolejka silników awaryjnych.
- Zmiana Google Translate i DeepL.

## Authority i baseline

Wymagania: `docs/work/llm-translation/spec.md` (status `accepted`,
zaktualizowana 2026-09-02).

Stan repozytorium: branch `work/interactive-cli/04-mascot-polish`, ostatni commit
`e5a99f6`, working tree czysty.

Baseline bramek do zachowania bez zmian:

- `pytest`: 47 failed, 2 errors, 2468 passed, 7 skipped. Wszystkie w
  `tests/cli/test_run.py` (18), `tests/cli/test_interactive_progress.py` (28) i
  `tests/config/test_model_catalog.py` (1). Nieaktualne testy CLI, nie do naprawy
  w tym planie.
- `mypy`: 38 błędów w 3 plikach (`tests/cli/test_interactive_app.py`,
  `test_interactive_progress.py`, `test_interactive_home.py`).
- `ruff check` i `ruff format`: czyste.

Każdy nowy błąd poza tą listą jest regresją tego planu.

## Stan aktualny

### Obecne zachowanie

- `json_contract.py` serializuje `{"subtitles":[{"id":0,"text":"…"}]}` i waliduje
  `{"translations":[{"id":0,"translated":"…"}]}`.
- `service.py:109` dzieli partię wyłącznie po liczbie linii z
  `config.max_batch_lines`.
- `service.py:120-129` ponawia całą partię po każdym naruszeniu kontraktu.
- `service.py:153-165` dzieli partię na połowy po sygnale limitu wyjścia lub
  kontekstu; ten mechanizm jest sprawny i zostaje.
- `runtime.py:455` przekazuje silnikowi LLM `engine_config.batch_size`, czyli
  `snapshot.translation_batch_size or DEFAULT_BATCH_SIZE` = 50.
- `config.py` ma `max_batch_lines: int = 1000` i odrzuca wartość niedodatnią.
- Trzy prompty w `prompts/` opisują kontrakt JSON.

### Root cause / gap

Rusztowanie `{"id":N,"translated":"…"}` kosztuje 7,57 tokena na każdą linię
odpowiedzi, czyli 36% odpowiedzi zwykłego odcinka i 73% odpowiedzi pliku z
napisami ekranowymi. Pola `id` są przy tym redundantne, bo walidacja wymaga
dokładnie ciągu `0..N-1`. Razem z narzuconym limitem 50 linii daje to siedem
żądań na odcinek i 93% wykorzystania domyślnego limitu wyjścia.

### Istniejące rozwiązania do reuse

- Reaktywny podział na połowy po sygnale limitu (`_split`) zostaje bez zmian i
  pełni rolę zabezpieczenia przy partii całego pliku.
- `PromptLoader` i układ zasobów `prompts/` zostają bez zmian.
- `RETRY_ERROR_PLACEHOLDER` zostaje jako punkt wstrzyknięcia diagnozy.
- Hierarchia błędów `TranslationEngineError` / `TranslationContextLengthError`
  zostaje bez zmian.

### Dowody

- Pomiar tokenizerem `o200k_base` na 8 plikach ASS z `workspace/`: obecny format
  20,77 tok/linię, `[N] tekst` 16,68 tok/linię, podłoga bez numerów 13,20.
- Pomiar per plik: zwykły odcinek 4556–7692 → 3792–6404 tokenów, plik z napisami
  ekranowymi 72006 → 48522 tokenów.
- 9894 zbadanych napisów ASS nie zawiera nawiasu kwadratowego ani prawdziwego
  znaku nowej linii.
- `tests/services/translation/test_translation_llm.py:86,98` dowodzi, że kontrakt
  przenosi prawdziwe znaki nowej linii wewnątrz napisu; format liniowy wymaga
  dlatego ucieczki.

## Zakres

### In scope

- Zamiana `json_contract.py` na moduł kontraktu numerowanych linii.
- Parser z rozpoznaniem rodzaju naruszenia i numerów, których dotyczy.
- Ucieczka znaku nowej linii i odwrotnego ukośnika.
- Pętla naprawy zawężonej do numerów w `service.py`.
- `max_batch_lines` jako limit opcjonalny; brak limitu oznacza cały plik.
- Podniesienie domyślnego `llm_max_output_tokens` do 32000.
- Treść trzech promptów i promptu korekcyjnego w zakresie opisu formatu.
- Testy parsera, ucieczki, naprawy i pętli silnika.
- `llm/AGENTS.md` i `translation/AGENTS.md` w zakresie opisu kontraktu.
- Prezentacja liczby linii na żądanie w panelu ustawień.
- Przelot na żywo na wszystkich odcinkach z `workspace/`.

### Out of scope

- Treść merytoryczna promptu tłumaczeniowego i stylowego.
- Zwijanie napisów ekranowych.
- Zmiana `translation_batch_size` z pola globalnego na pole per silnik.
- Naprawa 47 zastanych porażek testów i 38 zastanych błędów mypy.

### Forbidden

- Ciche pomijanie linii odpowiedzi niepasującej do wzorca.
- Wycinanie poprawnego fragmentu z odpowiedzi zawierającej dodatkowy tekst.
- Szacowanie liczby tokenów odpowiedzi z długości tekstu.
- Nowa zależność zewnętrzna.
- Import `anishift.services.llm` w silniku tłumaczenia.
- Logowanie treści napisów, tłumaczeń albo surowej odpowiedzi modelu.
- Traktowanie tekstu źródłowego jako udanego tłumaczenia.
- Zmiana publicznych typów `BatchedLine`, `TranslatedLine`, `FileTranslation`.
- Ruszanie plików spoza mapy plików tego planu.

### Deferred

- Zwijanie powtarzających się napisów ekranowych przed tłumaczeniem.
- Rozdzielenie `translation_batch_size` na osobne pola per silnik.

### Dozwolone decyzje lokalne

- Nazwy funkcji prywatnych i zmiennych lokalnych.
- Dokładna treść polskich komunikatów diagnostycznych, o ile nie zawierają treści
  napisów.
- Układ pomocniczych funkcji w module kontraktu.
- Sposób sparametryzowania testów naruszeń.

### Zatrzymaj się i wróć po decyzję, gdy

- Przelot na żywo pokaże, że model regularnie gubi numerację przy całym pliku.
- Okaże się, że jakiś dostawca nie raportuje `finish_reason` limitu wyjścia, więc
  reaktywny podział nie działa.
- Naprawa zawężona do numerów wymagałaby zmiany publicznego kontraktu serwisu
  tłumaczenia.

## Impact scan

| Granica | Ryzyko | Reakcja |
| --- | --- | --- |
| `TranslationEngine.translate_batch` | Zmiana sygnatury zerwałaby fasadę i Google/DeepL | Sygnatura bez zmian; zmiana wyłącznie wewnątrz silnika LLM |
| `BatchedLine` i dalszy pipeline | Zmiana typu wyniku zerwałaby writery napisów | Typ wyniku bez zmian |
| Napisy SRT dwuwierszowe | Format liniowy rozjechałby numerację | Ucieczka `\n` i `\\` plus test na napisie z podziałem wiersza |
| `llm_max_output_tokens` = 32000 | Model o mniejszym limicie odrzuci żądanie | Reaktywny podział na połowy już to obsługuje |
| Partia całego pliku | Jedno zmarnowane żądanie na patologicznym pliku | Świadomy koszt zamiast kruchego szacowania tokenów |
| `translation_batch_size` jest globalny | Wartość 0 znaczy co innego dla LLM i dla Google | Panel opisuje wartość zależnie od aktywnego silnika |
| Zastane porażki testów CLI | Pomylenie regresji z baseline'em | Porównanie do liczb z sekcji baseline |
| `config/settings.json` użytkownika | Zapisana wartość 8192 przesłoni nowy default | Sprawdzić plik w preflight i zgłosić użytkownikowi |

## Target design

### Odpowiedzialności i ownership

- `line_contract.py` jest jedynym właścicielem formatu granicy: serializacji,
  wzorca, ucieczki, parsowania i klasyfikacji naruszeń.
- `service.py` jest właścicielem pętli prób, naprawy, scalania wyników i
  reaktywnego podziału.
- `prompts/*.md` są właścicielem opisu kontraktu dla modelu.
- `config.py` jest właścicielem limitu rozmiaru partii.

### Source of truth

Wzorzec formatu i reguły naruszeń istnieją wyłącznie w `line_contract.py`.
Prompty opisują ten sam kontrakt słowami, ale nie są źródłem walidacji.

### Przepływ danych

```text
texts: list[str]                     (indeksy 0..N-1 = numery)
    ↓ pending = wszystkie numery
serialize_request([(numer, tekst)])  -> "[0] tekst\n[1] tekst"
    ↓ jako osobna część wiadomości użytkownika
completer.complete(request)
    ↓ finish_reason z limitu -> _split na połowy
parse_response(text, pending)        -> ParsedResponse(entries, violation)
    ↓ results.update(entries); pending = expected - results
pending puste i brak naruszenia      -> sukces
pending niepuste i został budżet prób -> naprawa wyłącznie pending
budżet prób wyczerpany               -> TranslationEngineError
```

### Mapa plików

```text
CREATE
  anishift/services/translation/engines/llm/line_contract.py

DELETE
  anishift/services/translation/engines/llm/json_contract.py

MODIFY
  anishift/services/translation/engines/llm/service.py      pętla prób, naprawa, scalanie
  anishift/services/translation/engines/llm/config.py       max_batch_lines opcjonalny
  anishift/services/translation/engines/llm/constants.py    wzorzec formatu, jeśli tu należy
  anishift/services/translation/engines/llm/prompts/system.md       opis formatu
  anishift/services/translation/engines/llm/prompts/translation.md  opis formatu
  anishift/services/translation/engines/llm/prompts/retry.md        opis naprawy zakresu
  anishift/services/translation/engines/llm/AGENTS.md       sekcja kontraktu
  anishift/services/translation/AGENTS.md                   wzmianka o kontrakcie LLM
  anishift/application/runtime.py                           brak wymuszenia 50 linii dla LLM
  anishift/config/user_settings.py                          default llm_max_output_tokens
  anishift/cli/interactive/settings.py                      opis wartości linii na żądanie
  tests/services/translation/test_translation_llm.py        przepisane testy kontraktu

READ ONLY
  anishift/services/translation/service.py
  anishift/services/translation/protocols.py
  anishift/services/translation/engines/llm/prompts/__init__.py
  anishift/config/field_catalog.py
  anishift/application/planning.py
```

### Publiczne kontrakty

#### `line_contract.py`

```python
LINE_PATTERN: Final[re.Pattern[str]]
"""Wzorzec jednej linii kontraktu: numer w nawiasie, spacja, treść."""

class ViolationKind(Enum):
    MALFORMED_LINE
    MISSING_NUMBER
    DUPLICATE_NUMBER
    UNKNOWN_NUMBER
    EMPTY_TRANSLATION
    WRONG_ORDER
    EMPTY_RESPONSE

@dataclass(frozen=True, slots=True)
class ContractViolation:
    kind: ViolationKind
    numbers: tuple[int, ...]   # puste = naruszenie dotyczy całej partii
    message: str               # polska diagnoza bez treści napisów

@dataclass(frozen=True, slots=True)
class ParsedResponse:
    entries: Mapping[int, str]          # wyłącznie numery zaufane
    violation: ContractViolation | None

def serialize_request(items: Sequence[tuple[int, str]]) -> str
def parse_response(text: str, expected: Sequence[int]) -> ParsedResponse
```

`parse_response` nie rzuca wyjątku dla naruszenia kontraktu; naruszenie jest
częścią wyniku, bo pętla naprawy potrzebuje zarówno tego, co się udało, jak i
opisu tego, co się nie udało.

#### `LlmTranslateConfig`

```python
max_batch_lines: int | None = None   # None = cały plik w jednym żądaniu
```

Walidacja odrzuca wartość niedodatnią, ale przyjmuje `None`.

### Algorytm parsera

1. Rozbij odpowiedź na linie.
2. Pomiń linie puste, białe oraz będące wyłącznie ogrodzeniem bloku kodu.
3. Dla każdej pozostałej linii dopasuj `LINE_PATTERN`.
4. Linia niepasująca unieważnia ostatni otwarty numer; gdy nie ma otwartego
   numeru, unieważnia całą partię.
5. Numer poza zbiorem `expected` unieważnia ostatni otwarty numer.
6. Numer powtórzony unieważnia oba wystąpienia.
7. Puste tłumaczenie unieważnia swój numer.
8. Numer mniejszy od poprzedniego zaakceptowanego oznacza `WRONG_ORDER` i
   unieważnia całą partię.
9. Odwróć ucieczkę `\\` i `\n` w zaufanych wpisach.
10. Zwróć zaufane wpisy oraz naruszenie z posortowanymi unieważnionymi numerami i
    numerami brakującymi.

### Edge cases i failures

- Pusta odpowiedź modelu: `EMPTY_RESPONSE`, cała partia do naprawy.
- Odpowiedź w ogrodzeniu Markdown bez innego tekstu: ogrodzenie pominięte,
  odpowiedź poprawna.
- Model zwraca komentarz na końcu: unieważnia ostatni numer, naprawa dotyczy
  tylko jego.
- Model dzieli tłumaczenie na dwie linie: druga linia unieważnia numer pierwszej.
- Model numeruje od 1 zamiast od 0: wszystkie numery poza zbiorem, cała partia do
  naprawy.
- Partia jednoliniowa nie do przetłumaczenia po wyczerpaniu prób: dotychczasowy
  jawny błąd bez zmian.
- Naprawa zwraca ponownie zepsuty ten sam numer: kolejna próba w granicy budżetu,
  potem błąd terminalny.

## Plan wykonania

### Faza 0 - Preflight

Cel: potwierdzić baseline i dane potrzebne do przelotu.

- Potwierdź czyste working tree i zgodność liczb baseline'u z sekcją Authority.
- Odczytaj `config/settings.json`: sprawdź, czy `llm_max_output_tokens` nie jest
  zapisany jawnie, bo przesłoniłby nowy default.
- Ustal dokładny identyfikator modelu `gpt-5.6-terra` w katalogu modeli aplikacji.
- Nie zmieniaj kodu.

Przejście: znane liczby baseline'u i znany identyfikator modelu.

### Faza 1 - Moduł kontraktu

Cel: gotowy, przetestowany format i parser bez dotykania silnika.

- Utwórz `line_contract.py` zgodnie z sekcją Publiczne kontrakty i Algorytm.
- Napisz testy jednostkowe: serializacja, ucieczka i jej odwrócenie, każdy rodzaj
  naruszenia osobno, przypisanie numeru przy linii niepasującej, pominięcie
  ogrodzenia i pustych linii.
- Nie usuwaj jeszcze `json_contract.py`.

Sprawdzenie: `uv run pytest tests/services/translation/test_translation_llm.py`
plus nowe testy parsera przechodzą; `ruff` i `mypy` bez nowych błędów.

Przejście: parser spełnia każdy punkt sekcji walidacji specyfikacji.

### Faza 2 - Pętla silnika i naprawa

Cel: silnik używa nowego kontraktu i naprawia zawężonym żądaniem.

- Przepisz `_translate_batch` na pętlę z `results` i `pending`.
- Zachowaj `_split` i wykrywanie limitu wyjścia bez zmian.
- `max_batch_lines` opcjonalny; brak limitu oznacza całą partię.
- Usuń `json_contract.py` i jego import.
- Przepisz testy silnika: partia w jednym żądaniu, naprawa wyłącznie pending,
  zachowanie poprawnych numerów między próbami, błąd terminalny po budżecie.

Sprawdzenie: testy silnika przechodzą; żaden test nie odwołuje się już do
`json_contract`.

Przejście: naprawa jednego zepsutego numeru wysyła żądanie z jedną linią, co
potwierdza test na atrapie completera.

### Faza 3 - Prompty

Cel: model dostaje opis dokładnie tego kontraktu, który waliduje kod.

- Przepisz `system.md` na opis numerowanych linii, zakaz treści poza nimi oraz
  zasadę jednej linii na tłumaczenie i sekwencji `\n` dla podziału wiersza.
- Przepisz `translation.md` na polecenie tłumaczenia numerowanych linii z
  przepisaniem numerów bez zmian.
- Przepisz `retry.md` tak, aby prosił o wyłącznie te numery, które są w żądaniu.
- Zachowaj `{{validation_error}}` jako jedyny token szablonu.

Sprawdzenie: `tests/services/translation/test_translation_prompts.py` przechodzi;
prompty nie wspominają o JSON.

Przejście: opis w promptach zgadza się z regułami parsera.

### Faza 4 - Konfiguracja i panel

Cel: cały plik w jednym żądaniu jest domyślnym zachowaniem produktu.

- `runtime.py`: silnik LLM nie dostaje wymuszonego 50; wartość 0 z ustawień
  oznacza brak limitu.
- `user_settings.py`: domyślny `llm_max_output_tokens` = 32000.
- `settings.py`: wartość linii na żądanie opisana liczbą albo słowem
  „wszystkie" zależnie od aktywnego silnika, nigdy nieinformującym „domyślnie".
- Popraw testy zależne od tych defaultów.

Sprawdzenie: pełne bramki jakości względem baseline'u.

Przejście: panel pokazuje sensowną wartość, a silnik LLM nie dzieli zwykłego
odcinka.

### Faza 5 - Dokumentacja

Cel: instrukcje repozytorium nie kłamią o kontrakcie.

- `llm/AGENTS.md`: sekcja kontraktu opisuje numerowane linie, parser, naprawę
  zawężoną i regułę unieważniania.
- `translation/AGENTS.md`: popraw wzmianki o kontrakcie JSON.
- Zaktualizuj `docs/work/llm-translation/outcome.md` albo utwórz nowy outcome dla
  tego etapu.

Sprawdzenie: `rg "json_contract|translations\"" ` nie zwraca aktywnych odwołań.

### Faza 6 - Przelot na żywo

Cel: dowód na realnym materiale, nie na atrapach.

- Ustaw silnik tłumaczenia na `llm`, dostawcę na Foundry, model na
  `gpt-5.6-terra`.
- Przetłumacz wszystkie odcinki z `workspace/`.
- Zbierz: liczbę żądań na plik, liczbę napraw, rodzaje naruszeń, czas, błędy
  terminalne.
- Porównaj liczbę linii wyjściowych z liczbą linii wejściowych dla każdego pliku.

Sprawdzenie: zero błędów terminalnych, zgodność liczby linii dla każdego pliku.

Checkpoint człowieka: przekaż właścicielowi produktu tabelę wyników oraz kilka
przetłumaczonych plików do oceny jakości.

## Strategia dowodu

### Targeted automated checks

- Testy jednostkowe parsera: jeden test na każdy rodzaj naruszenia.
- Test ucieczki: napis z prawdziwym znakiem nowej linii i z odwrotnym ukośnikiem
  przechodzi pełną drogę serializacja–parsowanie bez zmiany treści.
- Test naprawy: atrapa completera zwraca odpowiedź z jednym brakującym numerem;
  drugie żądanie zawiera dokładnie jedną linię.
- Test partii: 300 linii idzie w jednym żądaniu przy braku limitu.
- Test reaktywnego podziału: atrapa zgłasza limit wyjścia, silnik dzieli na
  połowy.

### Regression obligations

- Pełne bramki repozytorium względem liczb z sekcji Authority.
- Google i DeepL bez zmian zachowania; ich testy muszą pozostać zielone.
- Testy pakowania promptów w wheelu pozostają zielone.

### Human acceptance

Przelot na żywo na wszystkich odcinkach z `workspace/` modelem `gpt-5.6-terra` i
ocena jakości napisów przez właściciela produktu.

## Ryzyka i reakcje

| Ryzyko | Sygnał | Reakcja |
| --- | --- | --- |
| Model gubi numerację przy 350 liniach | Wysoki odsetek napraw w przelocie | Zatrzymaj się, zgłoś, rozważ górny limit linii jako default |
| Model numeruje od 1 | Wszystkie numery poza zbiorem | Wzmocnij `system.md`, dodaj test |
| Ucieczka `\n` myli model | Tłumaczenia z widocznym `\n` w treści | Sprawdź, czy napisy źródłowe faktycznie mają podziały; rozważ zakaz podziału |
| 32000 tokenów odrzucone przez dostawcę | Błąd żądania zamiast `finish_reason` | Zmniejsz default, oprzyj się na reaktywnym podziale |
| Naprawa w pętli na tym samym numerze | Budżet prób wyczerpany na jednym numerze | Błąd terminalny z diagnozą; bez cichego pomijania |

## Lokalna adaptacja

Dozwolona dla nazw prywatnych, treści komunikatów i układu funkcji
pomocniczych. Wymagane przeplanowanie, gdy zmienia się kształt
`ParsedResponse`, reguła unieważniania, właściciel formatu albo sygnatura
`translate_batch`.

## Definition of Done

- Warunki końcowe spełnione i udowodnione wskazanym instrumentem.
- Zero odwołań do kontraktu JSON w kodzie, testach i instrukcjach.
- Bramki jakości bez nowych błędów względem baseline'u.
- Przelot na żywo zakończony i przekazany do oceny człowieka.
- Commity w formacie `typ(scope): opis` na branchu roboczym, bez commitu na
  `main`.
