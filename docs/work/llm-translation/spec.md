---
kind: specification
status: accepted
updated: 2026-08-30
---

# Specyfikacja: kontrakt kodu tłumaczenia LLM

## Cel

Silnik tłumaczenia LLM ma przyjmować uporządkowaną partię napisów, przekazywać
ją modelowi jako JSON i zwracać kompletny, zwalidowany wynik JSON. Wszystkie
napisy są tłumaczone na język polski. Kod nie obsługuje wyboru innego języka
docelowego.

## Granica przedsięwzięcia

Specyfikacja definiuje kontrakt kodu dla:

- danych przekazywanych do modelu;
- danych odbieranych od modelu;
- ładowania i wyboru promptów aplikacji;
- prezentowania dostępnych stylów w UI;
- walidacji odpowiedzi;
- ponowienia po odpowiedzi niezgodnej z kontraktem;
- końcowego błędu silnika LLM.

Treść merytoryczna promptu tłumaczeniowego i stylowego nie jest wymaganiem
kodu. Pierwsza wersja tych promptów ma być krótka, a ich rozwinięcie stanowi
osobny etap.

## Stan wyjściowy

- Obecny silnik LLM oczekuje odpowiedzi tekstowej z numerowanymi liniami.
- Obecny system dzieli prompty na zadanie, styl, moduły i kontrakty.
- Obecna konfiguracja wybiera prompty przez identyfikatory.
- Ten stan zostaje zastąpiony przez kontrakt zdefiniowany poniżej.

## Ustalenia

- Granica tłumaczenia między AniShift a modelem LLM używa JSON-u dla wejścia i
  wyjścia.
- Jedynym obsługiwanym językiem docelowym jest polski.
- Żądanie LLM nie zawiera ustawienia języka źródłowego ani docelowego.
- Żądanie LLM nie zawiera tytułu, gatunku, streszczenia, płci postaci, słownika,
  historii serii ani innych metadanych materiału.
- Każdy napis ma techniczny identyfikator używany do sprawdzenia kompletności i
  mapowania odpowiedzi.
- Każde wywołanie używa trzech podstawowych promptów: systemowego,
  tłumaczeniowego i stylowego.
- Ponowienie po błędnej odpowiedzi używa dodatkowego promptu korekcyjnego
  opisującego błąd poprzedniej odpowiedzi.
- Wszystkie prompty dostarczane przez aplikację są napisane po polsku.
- Prompty są częścią aplikacji, są wersjonowane w Git i są dostarczane razem z
  instalacją AniShift.
- Właścicielem promptów jest silnik tłumaczenia LLM, dlatego pliki znajdują się
  przy `anishift/services/translation/engines/llm/`, a nie w runtime'owym
  katalogu `config/`.
- `config/` przechowuje wyłącznie nazwę wybranego stylu, nie treść ani ścieżki
  obowiązkowych promptów aplikacji.

## Kontrakt wejściowy LLM

- Wiadomość z danymi tłumaczenia jest jednym poprawnym obiektem JSON.
- Obiekt zawiera wyłącznie pole `subtitles`.
- `subtitles` jest tablicą obiektów zawierających dokładnie:
  - `id`: nieujemny, unikalny numer całkowity;
  - `text`: niepusty tekst napisu źródłowego.
- Identyfikatory tworzą ciąg `0..N-1`, gdzie `N` jest liczbą elementów partii.
- Kolejność elementów odpowiada kolejności napisów w partii.
- Powtórzone teksty pozostają osobnymi elementami z osobnymi identyfikatorami.
- Wewnętrzny podział wierszy napisu pozostaje częścią wartości `text`.
- Puste oraz składające się wyłącznie z białych znaków napisy nie są
  przekazywane do modelu.
- JSON nie zawiera żadnych pól językowych, kontekstowych ani opcjonalnych.
- Danych JSON nie otacza instrukcja ani tekst swobodny.
- Prompt tłumaczeniowy, prompt stylowy i dane JSON są osobnymi częściami
  wiadomości użytkownika, dzięki czemu część z danymi pozostaje czystym JSON-em.

Obowiązujący kształt:

```json
{
  "subtitles": [
    {"id": 0, "text": "Hello."},
    {"id": 1, "text": "How are you?"}
  ]
}
```

## Kontrakt wyjściowy LLM

- Odpowiedź modelu jest jednym poprawnym obiektem JSON.
- Obiekt zawiera wyłącznie pole `translations`.
- `translations` jest tablicą obiektów zawierających dokładnie:
  - `id`: identyfikator odpowiadającego napisu wejściowego;
  - `translated`: niepusty tekst w języku polskim.
- Odpowiedź zawiera dokładnie jeden element dla każdego wejściowego
  identyfikatora.
- Zbiór identyfikatorów odpowiedzi jest równy zbiorowi identyfikatorów wejścia.
- Identyfikatory nie mogą się powtarzać.
- Elementy odpowiedzi zachowują kolejność elementów wejściowych.
- Model nie może scalać elementów ani tworzyć dodatkowych elementów.
- Odpowiedź nie może zawierać komentarza, wyjaśnienia, Markdown ani tekstu przed
  lub po obiekcie JSON.
- Odpowiedź nie może zawierać nieznanych pól.

Obowiązujący kształt:

```json
{
  "translations": [
    {"id": 0, "translated": "Cześć."},
    {"id": 1, "translated": "Jak się masz?"}
  ]
}
```

## Role promptów

### Prompt systemowy

- Określa kontrakt wyjściowego JSON-u.
- Określa zakaz zwracania treści poza JSON-em.
- Ma pierwszeństwo przed pozostałymi promptami w sprawach formatu odpowiedzi.

### Prompt tłumaczeniowy

- Określa, że przekazane napisy mają zostać przetłumaczone na język polski.
- Zawiera wszystkie merytoryczne reguły tłumaczenia.
- Nie może zmieniać kontraktu JSON.

### Prompt stylowy

- Określa styl polskiego tekstu.
- Nie może zmieniać kontraktu JSON ani mapowania elementów.
- W jednym wywołaniu aktywny jest dokładnie jeden styl.

### Prompt korekcyjny

- Jest używany wyłącznie po odpowiedzi niezgodnej z kontraktem.
- Opisuje konkretny błąd wykryty w poprzedniej odpowiedzi.
- Nakazuje nie powtarzać tego błędu i zwrócić odpowiedź zgodną z kontraktem.
- Nie zastępuje trzech promptów podstawowych.
- Nie zmienia danych wejściowych ani wymaganej liczby tłumaczeń.

## Pliki promptów aplikacji

- Wersjonowane pliki promptów znajdują się pod:

```text
anishift/services/translation/engines/llm/prompts/
├── system.md
├── translation.md
├── retry.md
└── styles/
    └── neutral.md
```

- `system.md` jest głównym plikiem promptu systemowego.
- `translation.md` jest głównym plikiem promptu tłumaczeniowego.
- `retry.md` jest szablonem promptu korekcyjnego.
- `styles/neutral.md` jest głównym plikiem neutralnego stylu.
- Nazwy `system.md`, `translation.md` i `retry.md` są stałe.
- Każdy plik promptu ma rozszerzenie `.md`, kodowanie UTF-8 i niepustą treść.
- Pliki są częścią paczki aplikacji i muszą być dostępne również po instalacji,
  a nie tylko przy uruchamianiu ze źródeł repozytorium.
- Początkowa treść plików jest minimalna.
- Dodanie kolejnego stylu polega na dodaniu kolejnego pliku `.md` do katalogu
  `styles/`.

## Wybór promptów i UI

- Prompt systemowy, tłumaczeniowy i korekcyjny są obowiązkowymi zasobami modułu i
  nie są wybierane przez konfigurację.
- Konfiguracja przechowuje wyłącznie nazwę wybranego stylu, bez rozszerzenia i
  bez ścieżki, w polu `llm_translation_style`.
- Domyślną wartością `llm_translation_style` jest `neutral`.
- UI skanuje katalog `styles/` i uwzględnia wyłącznie niepuste pliki `.md`.
- Nazwa pliku bez rozszerzenia jest nazwą stylu widoczną w UI.
- Jeden dostępny plik stylu daje jedną możliwą wartość.
- Więcej niż jeden dostępny plik stylu umożliwia użytkownikowi wybór stylu.
- UI nie rozpoznaje gatunku i nie dobiera stylu automatycznie.
- Wybrany styl zostaje zapisany w konfiguracji.
- Jeżeli zapisany styl przestał istnieć, wybór nie może pozostać wskazaniem na
  nieistniejący plik.
- Jeżeli istnieje `neutral`, niepoprawny zapisany wybór zostaje zastąpiony
  wartością `neutral`; w przeciwnym razie zostaje wybrany pierwszy poprawny styl
  w stabilnej kolejności nazw.
- Brak choć jednego poprawnego stylu jest błędem uszkodzonej instalacji.

## Dostępność zasobów

- Pliki promptów są jedynym źródłem ich treści; `constants.py` nie zawiera kopii
  promptów ani awaryjnych treści tekstowych.
- Kod ładuje prompty jako zasoby zainstalowanego pakietu, a nie przez ścieżkę
  zależną od bieżącego katalogu roboczego.
- Stałe mogą określać wyłącznie niezmienne nazwy zasobów i domyślną nazwę stylu.
- Brak, błąd odczytu, błędne kodowanie UTF-8 albo pusta treść `system.md`,
  `translation.md`, `retry.md` lub wybranego stylu jest jawnym błędem
  konfiguracji silnika tłumaczeniowego.
- Test zbudowanej paczki potwierdza, że wszystkie obowiązkowe pliki `.md` są
  dostarczane razem z AniShift.

## Walidacja odpowiedzi

- Odpowiedź jest poprawna wyłącznie wtedy, gdy cały obiekt spełnia dokładny
  kontrakt wyjściowy.
- Niepoprawny JSON powoduje odrzucenie całej odpowiedzi.
- Nieprawidłowy typ pola powoduje odrzucenie całej odpowiedzi.
- Nieznane pole powoduje odrzucenie całej odpowiedzi.
- Brakujący albo dodatkowy element powoduje odrzucenie całej odpowiedzi.
- Duplikat, brak albo nieznany identyfikator powoduje odrzucenie całej
  odpowiedzi.
- Zmieniona kolejność elementów powoduje odrzucenie całej odpowiedzi.
- Puste pole `translated` powoduje odrzucenie całej odpowiedzi.
- Odpowiedź opakowana w Markdown albo zawierająca dodatkowy tekst pozostaje
  niepoprawna, nawet jeżeli zawiera możliwy do wycięcia fragment JSON-u.
- Odpowiedź przerwana przez limit wyjścia pozostaje niepoprawna.
- Niepełny albo niezwalidowany wynik nie może zostać zapisany jako sukces.

## Ponowienie po błędnej odpowiedzi

- Każda odpowiedź niezgodna z kontraktem może uruchomić kolejną próbę w granicy
  skonfigurowanego limitu ponowień.
- Kolejna próba zachowuje trzy podstawowe prompty oraz ten sam wejściowy JSON.
- Do kolejnej próby zostaje dołączony na końcu prompt korekcyjny.
- Prompt korekcyjny wskazuje wykryty błąd, na przykład niepoprawny JSON,
  niezgodną liczbę elementów, brak identyfikatora, duplikat albo dodatkową treść.
- Gdy błąd dotyczy liczby elementów lub identyfikatorów, prompt korekcyjny podaje
  oczekiwaną wartość.
- Prompt korekcyjny dotyczy bezpośrednio poprzedniej odpowiedzi i nie gromadzi
  historii wszystkich wcześniejszych błędów.
- Poprawna kolejna odpowiedź zastępuje odrzuconą odpowiedź w całości.
- Po wyczerpaniu limitu bez poprawnej odpowiedzi silnik LLM kończy próbę jawnym
  błędem tłumaczenia.
- Ostateczny błąd silnika LLM może uruchomić kolejny silnik z istniejącego
  łańcucha fallback.
- Częściowa odpowiedź nie jest zapisywana po ostatniej próbie.

## Inwarianty

- Wynik silnika LLM jest zawsze kompletnym, zwalidowanym obiektem wynikającym z
  jednego poprawnego JSON-u albo jawnym błędem.
- Liczba wyników jest równa liczbie elementów przekazanych modelowi.
- Mapowanie `id` jednoznacznie łączy każde tłumaczenie z wejściem.
- Każdy model i dostawca LLM otrzymuje ten sam logiczny kontrakt JSON.
- Kod nie zakłada obsługi natywnego `response_format` ani JSON Schema przez
  wybrany model. Wspólny kontrakt opiera się na promptach, czystych danych JSON i
  tej samej ścisłej walidacji lokalnej dla każdego dostawcy.
- Język docelowy nie jest wybieralny i pozostaje polski.
- Treść promptów oraz napisów nie trafia do logów.
- Konfiguracja użytkownika nie jest właścicielem treści promptów aplikacji.
- Publiczne typy wyniku używane przez dalszy pipeline pozostają zgodne z
  istniejącym kontraktem serwisu tłumaczenia.

## Zakazane

- Numerowane linie tekstowe jako format odpowiedzi modelu.
- Odpowiedź swobodnym tekstem zamiast JSON-u.
- Konfigurowanie innego języka docelowego dla silnika LLM.
- Przekazywanie modelowi metadanych materiału.
- Umieszczanie reguł jakości tłumaczenia w kodowym kontrakcie JSON zamiast w
  prompcie tłumaczeniowym.
- Przechowywanie wersjonowanych promptów aplikacji w runtime'owym katalogu
  `config/`.
- Używanie plików `.txt` dla promptów nowego systemu.
- Rejestr promptów oparty na kategoriach `task`, `style`, `module` i `contract`.
- Akceptowanie alternatywnych kluczy albo alternatywnych kształtów JSON-u.
- Wycinanie JSON-u z odpowiedzi zawierającej Markdown lub dodatkowy tekst.
- Zapis częściowej albo niezwalidowanej odpowiedzi.
- Oznaczanie tekstu źródłowego jako udanego tłumaczenia po błędzie modelu.

## Zgodność konfiguracji

- Pola `llm_prompt_id`, `llm_style_id` i `llm_module_ids` przestają być częścią
  obowiązującej konfiguracji.
- Nowe pole `llm_translation_style` przechowuje wyłącznie nazwę stylu i domyślnie
  ma wartość `neutral`.
- Konfiguracja z poprzedniej wersji nie blokuje uruchomienia aplikacji.
- Stare pola promptów są ignorowane.
- Brak nowego pola wybiera styl `neutral`.
- Nowo zapisywana konfiguracja nie zapisuje starych pól.
- Zmiana promptów nie zmienia wyboru dostawcy LLM, modelu, temperatury, limitu
  wyjścia ani współbieżności.

## Zakres

- Kontrakt JSON wejścia i wyjścia silnika LLM.
- Trzy podstawowe role promptów.
- Warunkowy prompt korekcyjny.
- Wersjonowane pliki `.md` należące do silnika LLM.
- Wykrywanie dostępnych stylów i wybór stylu w UI.
- Walidacja odpowiedzi i ponowienie z opisem poprzedniego błędu.
- Usunięcie starego formatu numerowanych linii.
- Usunięcie starego systemu `task/style/module/contract`.
- Zgodność istniejącego pliku ustawień po zmianie pól promptów.

## Poza zakresem

- Rozbudowana treść promptu tłumaczeniowego.
- Biblioteka dodatkowych stylów poza minimalnym stylem neutralnym.
- Obsługa języków docelowych innych niż polski.
- Automatyczne wykrywanie lub dobieranie stylu.
- Pozyskiwanie metadanych materiału.
- Zmiana działania Google Translate i DeepL.
- Zmiana ekstrakcji napisów, TTS, miksowania i tworzenia pliku wynikowego.
- Zmiana konfiguracji dostawców albo modeli niezwiązana z tłumaczeniem.

## Warunki sukcesu

- Każde żądanie modelu zawiera napisy w dokładnym kontrakcie wejściowego JSON-u.
- Każdy zaakceptowany wynik spełnia dokładny kontrakt wyjściowego JSON-u.
- Każda niezgodność wymieniona w sekcji walidacji jest wykrywana i odrzucana.
- Ponowienie po niezgodnej odpowiedzi zawiera polski prompt korekcyjny opisujący
  konkretny poprzedni błąd.
- Żaden częściowy albo niezwalidowany wynik nie jest zapisywany jako sukces.
- Domyślne pliki promptów są częścią paczki aplikacji.
- UI pokazuje wszystkie poprawne style dostępne w katalogu `styles/`.
- Dodanie kolejnego pliku stylu powoduje pojawienie się nowego wyboru w UI bez
  zmiany kodu katalogu stylów.
- Brak albo niepoprawna treść obowiązkowego promptu kończy się jawnym błędem
  konfiguracji zamiast użycia ukrytej kopii tekstu.
- Model nie otrzymuje ustawień języka ani metadanych materiału.
- Pełne bramki jakości repozytorium przechodzą po implementacji.

## Odłożone

- Opracowanie pełnej treści promptu tłumaczeniowego.
- Dodanie i opracowanie kolejnych stylów.
- Ocena jakości tłumaczenia i strojenie treści promptów.

## Nierozstrzygnięte

Brak. Specyfikacja rozstrzyga kontrakt wymagany do przygotowania planu.
