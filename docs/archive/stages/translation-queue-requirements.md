# Kolejka silników tłumaczenia — wymagania

> **NIE ZREALIZOWANE.** Ustalenia zebrane 2026-09-01, realizacja odłożona decyzją właściciela.
> Dokument jest tablicą prawdy dla przyszłej pracy, nie planem wykonania.

## Cel

Gdy plik nie może zostać przetłumaczony wybranym modelem, praca ma przejść do następnej pozycji
ustalonej kolejki i jawnie to zameldować — zamiast zostać po cichu dokończona gorszym narzędziem.

## Stan wyjściowy

Fakty potrzebne do zrozumienia zakresu; nie są wymaganiami.

- Trzy silniki tłumaczenia działają, sprawdzone na żywych endpointach 2026-09-01: `google`
  (strona mobilna `/m`), `deepl` (oficjalne SDK), `llm` (przez wstrzyknięty `LlmCompleter`).
- Palantir Foundry wystawia 18 aliasów modeli w `config/anishift.models.jsonc`. Katalog jest
  widoczny tylko wtedy, gdy ustawiony jest adres enrollmentu.
- Pole `translation_fallback_chain` zostało usunięte z produktu 2026-09-01. Powód: przy
  `translation_engine = "llm"` zapisany łańcuch `["google"]` przechodził przez filtr aktywnego
  silnika i pipeline po cichu dokańczał plik gołym Google Translate, meldując sukces. Kształt
  tego pola (identyfikatory silników) nie odpowiada wymaganej kolejce, która operuje na modelach.
- `TranslationService` zachował parametr `fallback_chain` z domyślną pustą krotką. To instalacja,
  na której kolejka może stanąć bez zmiany kontraktu fasady.
- Produkt uruchamia się jednokomendowo i pracuje na żądanie. Trybu pracy w tle nie ma.

## Ustalenia

- Kolejność pozycji: modele Foundry, następnie DeepL, następnie Google.
- OpenRouter pozostaje poza kolejką, ponieważ jest płatny.
- Produkt ma pracować w tle i rozpoczynać pracę na trigger, bez obecności użytkownika.
- Gdy cała kolejka zostanie wyczerpana, decyzję podejmuje użytkownik: ponowienie, inny model albo
  inny silnik.

## Wymagania

- Kolejka jest jawnie uporządkowana i przechodzona od góry do pierwszej pozycji, która zwróci
  poprawne tłumaczenie.
- Zejście na niższą pozycję jest widoczne w wyniku pracy i w logu. Produkt nie melduje sukcesu bez
  informacji, czym plik został przetłumaczony.
- Wyczerpanie kolejki nie kończy pracy w ciszy — użytkownik otrzymuje wybór dalszego działania.
- Praca rozpoczyna się po wystąpieniu triggera bez interakcji użytkownika.

## Inwarianty

- Użytkownik zawsze wie, czym każdy plik został przetłumaczony.
- Tekst źródłowy nigdy nie jest uznawany za udane tłumaczenie.

## Zakazy

- Nie przywracać pola `translation_fallback_chain` w dawnym kształcie ani jego cichej semantyki.
- Nie umieszczać OpenRouter w kolejce, dopóki obowiązuje powód finansowy.
- Nie dokańczać pliku niższą pozycją kolejki bez zapisu tego faktu w wyniku.

## Poza zakresem

- Zmiany w samych silnikach `google`, `deepl` i `llm`. Działają i nie są przedmiotem tej pracy.
- Wybór modelu do zwykłego, ręcznego uruchomienia. To istniejące ustawienie panelu.

## Nierozstrzygnięte

Każdy punkt materialnie zmienia rezultat i wymaga decyzji przed rozpoczęciem realizacji.

- Jednostka kolejki: alias modelu czy silnik? Ustalenie mówi „modele Foundry”, a Foundry ma 18
  aliasów — nie wiadomo, które wchodzą do kolejki ani w jakiej kolejności między sobą.
- Warunek zejścia niżej: wyłącznie błąd przejściowy po wyczerpaniu retry, czy również naruszenie
  kontraktu JSON, limit kontekstu albo brak klucza dostępu?
- Zasięg kolejki: na plik, na partię czy na cały run? Czy po zejściu niżej następny plik zaczyna
  ponownie od góry?
- Trigger pracy w tle: nowy plik w workspace, harmonogram czy jawne polecenie?
- Sposób zadania pytania, gdy kolejka wyczerpie się w trybie tła i nikt nie patrzy w terminal.

## Warunki sukcesu

- Człowiek uruchamia realny plik z modelem Foundry celowo niedostępnym, obserwuje zejście kolejki
  na kolejną pozycję, a po zakończeniu widzi w podsumowaniu i logu, czym plik został
  przetłumaczony.
- Człowiek uruchamia realny plik z całą kolejką niedostępną i otrzymuje pytanie o dalsze działanie
  zamiast cichego zakończenia.
