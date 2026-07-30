# Etap 6.1 — wspólne prymitywy tekstowe

## 1. Cel

Usunąć rzeczywistą redundancję między chunkowaniem tłumaczenia i TTS bez
łączenia dwóch różnych kontraktów domenowych w jeden uniwersalny mechanizm.

Po zmianie nadal istnieją:

- `translation.chunk_text()` — dzieli pełny dokument na requesty translatora;
- `tts.chunk_speech_text()` — dzieli jedną wypowiedź według limitów silnika TTS.

Wspólne stają się wyłącznie niskopoziomowe reguły tekstowe, które nie należą
ani do tłumaczenia, ani do syntezy mowy.

## 2. Dlaczego nie jedna klasa chunkera

Oba mechanizmy mają inne niezmienne warunki.

### Translation

- wejściem jest pełny tekst;
- hierarchia cięcia to akapit → zdanie → fraza → słowo → twardy podział;
- każdy chunk musi mieścić się w limicie znaków;
- połączenie chunków musi odtworzyć wejście dokładnie 1:1;
- whitespace i separatory pozostają przy fragmencie po lewej;
- krótsze kawałki są ponownie pakowane do większych requestów.

### TTS

- wejściem jest jedna neutralna wypowiedź `SpeechRequest`;
- obowiązują jednocześnie opcjonalne limity znaków i bajtów UTF-8;
- grafem Unicode nie może zostać przecięty;
- każdy fragment musi zawierać tekst możliwy do wymówienia;
- algorytm cofa granicę, jeśli zachłanny podział zostawi niemy ogon;
- wynik jest składany w jeden klip przypisany do pierwotnego requestu.

Połączenie tych kontraktów stworzyłoby klasę z przełącznikami domenowymi,
trudniejszą do testowania niż dwa małe adaptery.

## 3. Docelowa struktura

```text
anishift/
├── text/
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── __init__.py
│   ├── boundaries.py
│   └── graphemes.py
└── services/
    ├── translation/
    │   ├── chunking.py
    │   └── linebreak.py
    └── tts/
        └── chunking.py

tests/
├── text/
│   ├── test_boundaries.py
│   └── test_graphemes.py
└── services/
    ├── translation/test_translation_chunking.py
    └── tts/test_tts_chunking.py
```

## 4. Odpowiedzialności

### `anishift/text/boundaries.py`

Jedno źródło prawdy dla:

- łacińskich i CJK znaków końca zdania;
- zero-width space spotykanego w napisach;
- separatorów fraz wyliczanych z kategorii Unicode;
- znaków domykających nawiasy i cytaty;
- apostrofów, które nie są granicą;
- list skrótów EN i PL;
- decyzji, czy kropka po tokenie jest końcem zdania.

Moduł nie zna requestów translatora, providerów TTS, napisów ani błędów
domenowych.

### `anishift/text/graphemes.py`

Jedno źródło prawdy dla:

- segmentacji `regex \X` na rozszerzone grafemy Unicode;
- awaryjnego cięcia tekstu na części o limicie znaków bez rozcinania grafemu,
  o ile pojedynczy grafem sam nie przekracza limitu.

Moduł nie ocenia, czy tekst jest możliwy do wymówienia.

### `translation/chunking.py`

Zachowuje:

- publiczne API i domyślne limity;
- split akapitów, zdań, fraz i słów;
- dokładne dołączanie separatorów;
- rekurencyjną hierarchię cięcia;
- zachłanne pakowanie kawałków.

Importuje wspólne granice i grafemy. Nadal eksportuje używane dotąd nazwy
`SENTENCE_ENDINGS`, `ZERO_WIDTH` i `phrase_cut_chars()`, żeby nie łamać
`linebreak.py` ani zewnętrznych wywołań.

### `tts/chunking.py`

Zachowuje:

- publiczne API `chunk_speech_text()`;
- walidację limitów znaków i bajtów;
- planowanie z backtrackingiem;
- gwarancję wymownego tekstu w każdym fragmencie;
- błędy `TtsUnsupportedError`.

Importuje wspólne granice, skróty i segmentację grafemów. Nie importuje
`translation`.

## 5. Przepływ danych

### Translation

```text
pełny tekst
  → domenowa hierarchia naturalnych granic
  → wspólna klasyfikacja interpunkcji i skrótów
  → grafemowo bezpieczny fallback
  → pakowanie do limitu requestu
  → list[str], concat == wejście
```

### TTS

```text
SpeechRequest.text
  → wspólne grafemy i granice językowe
  → domenowe limity znaków/bajtów
  → domenowy test wymowności i backtracking
  → tuple[str, ...], concat == wejście
  → provider generuje części
  → TTS składa je w jeden klip requestu
```

## 6. Kompatybilność

- Brak zmiany sygnatur publicznych.
- Brak nowej zależności; projekt już używa `regex`.
- Brak importu między `tts` i `translation`.
- Brak zmian w napisach ASS/SRT, timingach, providerach i audio.
- `linebreak.py` nadal korzysta z tego samego publicznego źródła znaków.
- Kolejność tekstu, whitespace i znaki Unicode pozostają bez zmian.

## 7. Testy

### Testy wspólne

- znaki fraz obejmują różne skrypty Unicode;
- znaki otwierające i apostrofy nie stają się granicą;
- skróty EN/PL, inicjały, liczby porządkowe i dziesiętne nie kończą zdania;
- emoji, flagi, ZWJ, variation selectors i combining marks są jednym grafemem;
- awaryjne cięcie zachowuje tekst dokładnie.

### Testy kontraktów domenowych

- translation nadal respektuje oba limity i odtwarza tekst 1:1;
- TTS nadal respektuje znaki i bajty oraz nie tworzy niemych fragmentów;
- oba mechanizmy preferują zgodne granice zdań i skrótów;
- istniejące testy regresyjne obu domen pozostają zielone.

### Pełne bramki

```powershell
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

## 8. Poza zakresem

- wspólny retry;
- wspólne resume i atomowy zapis JSON;
- zmiana limitów providerów;
- chunkowanie batchy napisów;
- zmiana sposobu montażu klipów audio;
- optymalizacja importowego skanu Unicode;
- nowa uniwersalna klasa chunkera.

Każdy z tych tematów wymaga osobnej motywacji i osobnego pomiaru.

## 9. Kryteria akceptacji

1. Wspólne reguły Unicode i skrótów istnieją tylko w `anishift/text/`.
2. `tts` nie importuje `translation`, a `translation` nie importuje `tts`.
3. Oba publiczne API chunkowania pozostają zgodne.
4. Konkatenacja wyników obu chunkerów zawsze odtwarza wejście.
5. Translation nie przekracza limitu znaków.
6. TTS nie przekracza limitu znaków ani bajtów i nie rozcina grafemów.
7. Wszystkie testy i cztery bramki jakości przechodzą.
8. Zmiana trafia do osobnego commita i PR etapu 6.1.
