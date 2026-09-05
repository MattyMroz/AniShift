# LLM engine

Silnik tłumaczenia przez wstrzyknięty `LlmCompleter` (provider-agnostic).
Rejestrowany pod `engine_id = "llm"`.

## Pułapki

- Nie importuje `anishift.services.llm`. Konkretny completer podłącza wyłącznie
  granica w `application/runtime.py`.
- Przyjmuje tylko `LlmTranslateConfig`; zwykły `TranslationConfig` jest błędem.
- Obsługuje wyłącznie wynikowy język polski (`target_lang == "pl"`). Język
  źródłowy nie jest wysyłany do modelu.
- Nie odzyskuje fragmentów odpowiedzi i nie traktuje tekstu źródłowego jako
  udanego tłumaczenia.
- Naruszenie kontraktu uruchamia naprawę zawężoną do numerów, ale nigdy podziału
  partii. Podział na stabilne połowy dotyczy wyłącznie limitu kontekstu lub
  wyjścia.
- Porażka pojedynczej linii rzuca `TranslationEngineError`.
- `max_batch_lines=None` (default) wysyła cały plik w jednym żądaniu. Wartość
  dodatnia tnie partię; `runtime.py` podaje tu surową preferencję użytkownika, nie
  default Google.

## Kontrakt numerowanych linii

- `line_contract.py` jest JEDYNYM właścicielem formatu: wzorca, ucieczki,
  serializacji, parsowania i klasyfikacji naruszeń. Prompty opisują ten sam
  kontrakt słowami, ale niczego nie walidują.
- Wejście jest osobnym `TextPart`: jedna linia `[N] tekst` na napis, gdzie numer
  to indeks w żądaniu. Wyjście musi mieć dokładnie jedną linię `[N] tłumaczenie`
  na każdy żądany numer, w tej samej kolejności.
- Podział wiersza wewnątrz napisu jedzie jako `\n`; nieuciekniony przesunąłby
  każdy następny numer. Odwracanie ucieczki jest JEDNOPRZEBIEGOWE (regex), bo
  dwa kolejne `replace` psują napis z literalnym `\n`.
- `parse_response` nie rzuca wyjątku dla naruszenia: zwraca zaufane wpisy ORAZ
  jedno naruszenie z numerami do powtórzenia, bo pętla naprawy potrzebuje obu.
- Linia niepasująca do wzorca unieważnia numer, który poprzedza — a gdy nie ma
  otwartego numeru, całą partię. Nigdy nie jest cicho pomijana.
- Numer spoza żądania unieważnia poprzedni numer; powtórzony i z pustym
  tłumaczeniem unieważnia siebie; zła kolejność unieważnia całą partię.
- Kolejność sprawdza się po POZYCJI w żądaniu, nie po wielkości numeru — inaczej
  naprawa podzbioru (`[12]` przed `[7]` w kolejnym żądaniu) odrzucałaby poprawną
  odpowiedź.
- Puste linie i ogrodzenia bloku kodu są pomijane.
- Diagnostyka retry jest po polsku i nie zawiera treści napisów ani surowej
  odpowiedzi; powyżej 20 numerów podaje ich liczbę zamiast listy.

## Prompty

- Prompty są zasobami pakietu w `prompts/`: `system.md`, `translation.md`,
  `retry.md` oraz dokładnie jeden wybrany plik `styles/*.md`.
- `PromptLoader` używa `importlib.resources`, dlatego zasoby muszą działać także
  z zainstalowanego wheel.
- Nazwy trzech promptów bazowych są stałe. UI odkrywa style po nazwach
  bezpośrednich plików Markdown; ustawienia przechowują tylko nazwę stylu.
- Brakujący, pusty, nie-UTF-8 lub wadliwy zasób jest `TranslationConfigError`.
  Nie dodawaj zapasowej treści promptu w stałych ani `config/prompts`.
- `retry.md` musi zawierać dokładnie jeden token `{{validation_error}}`.
