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
- Błędny JSON uruchamia ponowienie kontraktu, ale nigdy podział partii. Podział
  na stabilne połowy dotyczy wyłącznie limitu kontekstu lub wyjścia.
- Porażka pojedynczej linii rzuca `TranslationEngineError`.

## Kontrakt JSON

- Wejście jest osobnym `TextPart` i ma dokładny kształt
  `{"subtitles":[{"id":0,"text":"..."}]}`.
- Wyjście musi być jednym dokumentem
  `{"translations":[{"id":0,"translated":"..."}]}`.
- `json_contract.py` wymaga dokładnych kluczy, typów, liczby elementów,
  unikalnych i kolejnych identyfikatorów oraz niepustych tłumaczeń. Odrzuca
  dodatkowy tekst, Markdown, duplikaty kluczy i liczby niefinitywne.
- Diagnostyka retry opisuje tylko ostatnie naruszenie. Nie zawiera surowej
  odpowiedzi ani historii modelu.

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
