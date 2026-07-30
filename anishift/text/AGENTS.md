# text

Wspólne, bezdomenowe prymitywy Unicode używane przez translation, TTS i
subtitle line breaking.

## Granica

- Ten moduł nie importuje `anishift.services`.
- Reguły requestów, wymowności tekstu, retry i błędy domenowe zostają w
  adapterach `services/translation/chunking.py` i `services/tts/chunking.py`.
- Nie twórz uniwersalnego chunkera z przełącznikami domenowymi.

## Pułapki

- `boundaries.py` wylicza separatory i domknięcia przez pełny skan Unicode
  podczas importu; nie duplikuj tego skanu ani nie dodawaj kolejnej kategorii
  bez pomiaru kosztu importu.
- `period_ends_sentence()` chroni zapis dziesiętny tylko wtedy, gdy caller poda
  `previous_character` i `next_character`.
- `hard_split_graphemes()` mierzy limit w punktach kodowych. Zachowuje grafem,
  gdy mieści się w limicie; jeśli pojedynczy grafem jest większy, rozcina go,
  żeby zachować twardy limit callera.
- Apostrofy nie są separatorami fraz. Znaki otwierające z kategorii `Ps`/`Pi`
  także nie mogą zaczynać granicy.

## Testy

```powershell
uv run pytest tests/text tests/services/translation/test_translation_chunking.py tests/services/tts/test_tts_chunking.py
```
