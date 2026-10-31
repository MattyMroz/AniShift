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
- `ends_sentence()` patrzy tylko na ostatni znak po `rstrip()`: znak końca zdania,
  domknięcie z `CLOSING_MARKS` albo prosty `"`. Nie rozpoznaje skrótów ani zapisu
  dziesiętnego; to jedyne źródło zbioru „kwestia domknięta” dla handlera TTS i
  silnika dokumentowego.
- `hard_split_graphemes()` mierzy limit w punktach kodowych. Zachowuje grafem,
  gdy mieści się w limicie; jeśli pojedynczy grafem jest większy, rozcina go,
  żeby zachować twardy limit callera.
- `markers.py` jest jedynym właścicielem składni znaczników `<sN>…</sN>`: subtitles je tworzy i czyta, silniki translation tylko je usuwają.
- `gaps.py` daje każdej przerwie jedną klasę (najszkodliwszą wg `TIERS`) i
  flagi; nie zna wag — siłę klas ustala kalibracja rdzenia układu.
- `morphology.agrees()` to „istnieje zgodna para analiz” Morfeusza bez
  dezambiguacji: przymiotniki z odczytem rzeczownikowym („ukochana”) i
  „który” też się liczą. Słowo odpada tylko przy odczycie osobowym lub
  przeszłym (`fin`, `praet`, `bedzie`, `aglt`, `winien`); tryb rozkazujący
  i bezokolicznik („sposób”) są pomijane. `modifies()` dopuszcza także
  przymiotnik + przymiotnik i jest predykatem `gaps(words, modifies)` dla
  frazy przyimkowej; bez niego chronią ją tylko listy (zaimki dzierżawcze).
- `gaps(words, modifies, verb)`: klityka zaimkowa (`_CLITICS`) obok wyrazu, który `morphology.verb` czyta jako czasownik, daje chronioną klasę `clitic`; przymiotnik przed wyrazem zgodnym według `modifies` daje `modifier` także bez końcówki z listy. Bez predykatów (wariant bez morfologii) te przerwy zostają zwykłymi.
- `plural.py` jest jedyną regułą polskiej odmiany po liczbie (1 / 2–4 poza 12–14 / reszta); nie
  kopiuj jej w modułach.
- Apostrofy nie są separatorami fraz. Znaki otwierające z kategorii `Ps`/`Pi`
  także nie mogą zaczynać granicy.

## Testy

```powershell
uv run pytest tests/text tests/services/translation/test_translation_chunking.py tests/services/tts/test_tts_chunking.py
```
