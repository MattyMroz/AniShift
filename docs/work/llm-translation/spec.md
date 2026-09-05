---
kind: specification
status: accepted
updated: 2026-09-02
---

# Specyfikacja: kontrakt kodu tłumaczenia LLM

## Cel

Silnik tłumaczenia LLM ma przyjmować uporządkowaną partię napisów, przekazywać ją
modelowi w formacie numerowanych linii i zwracać kompletny, zwalidowany wynik.
Format granicy ma zużywać jak najmniej tokenów odpowiedzi przy zachowaniu pełnej
weryfikowalności przypisania tłumaczeń do wejścia, tak aby cały plik napisów
mieścił się w jednym żądaniu. Wszystkie napisy są tłumaczone na język polski. Kod
nie obsługuje wyboru innego języka docelowego.

## Użytkownik i intencja

Odbiorcą jest właściciel produktu uruchamiający AniShift na własnych plikach MKV.
Zależy mu na tym, aby tłumaczenie jednego pliku szło w jednym żądaniu, a każde
przekłamanie liczby lub kolejności linii było wykryte i naprawione, nie przemilczane.

## Granica przedsięwzięcia

Specyfikacja definiuje kontrakt kodu dla:

- danych przekazywanych do modelu;
- danych odbieranych od modelu;
- ładowania i wyboru promptów aplikacji;
- prezentowania dostępnych stylów w UI;
- walidacji odpowiedzi;
- naprawy i ponowienia po odpowiedzi niezgodnej z kontraktem;
- podziału partii na żądania;
- końcowego błędu silnika LLM.

Treść merytoryczna promptu tłumaczeniowego i stylowego nie jest wymaganiem kodu.

## Stan wyjściowy

- Granica tłumaczenia używa dziś kontraktu JSON `{"subtitles":[{"id":0,"text":"…"}]}`
  na wejściu i `{"translations":[{"id":0,"translated":"…"}]}` na wyjściu.
- Pomiar tokenizerem `o200k_base` na 2369 linijkach ośmiu realnych plików napisów
  użytkownika: obecny kontrakt wyjściowy kosztuje 20,77 tokena na linię, z czego
  7,57 to samo rusztowanie formatu. Rusztowanie stanowi 36% odpowiedzi dla
  zwykłych odcinków i 73% dla pliku z napisami ekranowymi klatka po klatce.
- Pola `id` w dzisiejszym kontrakcie nie niosą informacji: walidacja wymaga, aby
  były dokładnie ciągiem `0..N-1` w tej kolejności, a silnik nie odzyskuje
  brakujących fragmentów odpowiedzi.
- Przed kontraktem JSON silnik używał formatu `[N] tekst`, którego parser
  ignorował po cichu każdą linię niepasującą do wzorca.
- `llm_max_output_tokens` ma domyślną wartość 8192, a dopuszczalny zakres kończy
  się na 32000.
- Zwykły odcinek to 234–366 linii do tłumaczenia i 4556–7692 tokeny odpowiedzi w
  dzisiejszym formacie, czyli do 93% domyślnego limitu wyjścia.
- Plik z napisami ekranowymi klatka po klatce daje 7525 linii i 72006 tokenów
  odpowiedzi w dzisiejszym formacie, czyli przekracza nawet górny limit zakresu.
- Zwijanie klatka po klatce działa wyłącznie na strumieniu mówionym; napisy
  ekranowe trafiają do tłumaczenia bez zwijania.
- Globalne pole `translation_batch_size` z wartością 0 daje wszystkim silnikom
  `DEFAULT_BATCH_SIZE = 50`, więc silnik LLM dzieli zwykły odcinek na około
  siedem żądań, mimo że własny domyślny limit silnika to 1000 linii.
- Silnik LLM nie ma żadnego limitu znaków ani tokenów na żądanie; Google ma
  `MAX_CHARS_PER_REQUEST = 15000`, DeepL ma `MAX_PAYLOAD_BYTES`.
- W badanym korpusie 9894 napisów żaden nie zawiera prawdziwego znaku nowej
  linii, nawiasu kwadratowego, kreski pionowej ani cudzysłowu prostego.

## Ustalenia

- Granica tłumaczenia między AniShift a modelem LLM używa numerowanych linii
  `[N] tekst` dla wejścia i wyjścia. Skutek: obowiązujący dotąd kontrakt JSON
  przestaje być formatem granicy.
- Numeracja jest obowiązkowa i nie podlega usunięciu. Skutek: format bez numerów
  jest niedopuszczalny, nawet gdy jest tańszy.
- Znacznikiem numeru jest nawias kwadratowy z pojedynczą spacją po nim.
  Skutek: przyjęty koszt to jeden token na linię więcej niż najtańszy zmierzony
  wariant, w zamian za znacznik, którego nie da się pomylić z etykietą mówiącego
  ani z listą Markdown.
- Rygor walidacji przeniesiony z kontraktu JSON obowiązuje w całości. Skutek:
  zmiana formatu nie może obniżyć siły sprawdzenia odpowiedzi.
- Parser odrzuca każdą linię odpowiedzi niepasującą do wzorca. Skutek: powrót do
  wcześniejszego zachowania, w którym niepasująca linia była pomijana, jest
  niedopuszczalny.
- Naprawa niezgodnej odpowiedzi może dotyczyć wyłącznie brakujących lub błędnych
  numerów, a nie całej partii. Skutek: koszt naprawy jest proporcjonalny do
  liczby zepsutych linii, nie do rozmiaru pliku.
- Domyślny podział partii dla silnika LLM to cały plik w jednym żądaniu.
  Skutek: globalna wartość 50 linii przestaje ograniczać silnik LLM.
- Silnik LLM otrzymuje własny zapasowy limit rozmiaru żądania. Skutek: plik
  patologicznie długi jest dzielony, zamiast przekroczyć limit wyjścia modelu.
- Jedynym obsługiwanym językiem docelowym jest polski.
- Żądanie LLM nie zawiera ustawienia języka źródłowego ani docelowego.
- Żądanie LLM nie zawiera tytułu, gatunku, streszczenia, płci postaci, słownika,
  historii serii ani innych metadanych materiału.
- Każdy napis ma techniczny numer używany do sprawdzenia kompletności i mapowania
  odpowiedzi.
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

- Część wiadomości z danymi tłumaczenia zawiera wyłącznie numerowane linie.
- Jedna linia wejścia ma postać `[N] tekst`, gdzie `N` jest numerem napisu, a
  `tekst` jego treścią źródłową.
- Numery tworzą ciąg `0..N-1`, gdzie `N` jest liczbą napisów w partii.
- Linie są rozdzielone jednym znakiem nowej linii.
- Kolejność linii odpowiada kolejności napisów w partii.
- Powtórzone teksty pozostają osobnymi liniami z osobnymi numerami.
- Jeden napis zajmuje dokładnie jedną linię wejścia.
- Wewnętrzny podział wierszy napisu jest przenoszony jako dwuznakowa sekwencja
  `\n`, a znak odwrotnego ukośnika jako `\\`. Skutek: napis dwuwierszowy nie
  rozjeżdża numeracji.
- Puste oraz składające się wyłącznie z białych znaków napisy nie są przekazywane
  do modelu.
- Dane nie zawierają żadnych pól językowych, kontekstowych ani opcjonalnych.
- Danych nie otacza instrukcja ani tekst swobodny.
- Prompt tłumaczeniowy, prompt stylowy i dane są osobnymi częściami wiadomości
  użytkownika, dzięki czemu część z danymi pozostaje czystymi numerowanymi
  liniami.

Obowiązujący kształt:

```text
[0] Hello.
[1] How are you?
```

## Kontrakt wyjściowy LLM

- Odpowiedź modelu składa się wyłącznie z numerowanych linii.
- Jedna linia odpowiedzi ma postać `[N] tłumaczenie`.
- Numer odpowiedzi jest numerem odpowiadającego napisu wejściowego.
- Tłumaczenie jest niepustym tekstem w języku polskim.
- Odpowiedź zawiera dokładnie jedną linię dla każdego numeru wejściowego.
- Zbiór numerów odpowiedzi jest równy zbiorowi numerów wejścia.
- Numery nie mogą się powtarzać.
- Linie odpowiedzi zachowują kolejność linii wejściowych.
- Jedno tłumaczenie zajmuje dokładnie jedną linię odpowiedzi.
- Wewnętrzny podział wierszy tłumaczenia jest przenoszony jako dwuznakowa
  sekwencja `\n`, a znak odwrotnego ukośnika jako `\\`.
- Parser odwraca ucieczkę, więc wynik silnika zawiera prawdziwe znaki nowej linii
  tam, gdzie model użył sekwencji `\n`.
- Model nie może scalać linii, dzielić linii ani tworzyć dodatkowych linii.
- Model nie może przenumerować linii.
- Odpowiedź nie może zawierać komentarza, wyjaśnienia, Markdown ani tekstu przed
  lub po numerowanych liniach.

Obowiązujący kształt:

```text
[0] Cześć.
[1] Jak się masz?
```

## Parser odpowiedzi

- Parser jest jedynym miejscem rozpoznającym format odpowiedzi modelu.
- Parser dzieli odpowiedź na linie i wymaga, aby każda znacząca linia pasowała do
  wzorca `[N] tekst`.
- Linia pusta lub zawierająca wyłącznie białe znaki jest pomijana w dowolnym
  miejscu odpowiedzi. Nie może ukryć treści, więc nie jest naruszeniem.
- Linia będąca wyłącznie ogrodzeniem bloku kodu Markdown jest pomijana. Nie może
  ukryć treści, więc nie jest naruszeniem.
- Każda inna linia niepasująca do wzorca jest naruszeniem kontraktu i nie może
  zostać pominięta, ponieważ może być urwaną częścią poprzedniego tłumaczenia.
- Linia niepasująca do wzorca unieważnia numer bezpośrednio ją poprzedzający. Gdy
  nie poprzedza jej żaden numer, unieważnia całą partię.
- Parser zwraca albo kompletny zestaw tłumaczeń, albo opis naruszenia.
- Opis naruszenia wskazuje rodzaj błędu oraz numery, których dotyczy.
- Opis naruszenia nie zawiera treści napisów, treści tłumaczeń ani surowej
  odpowiedzi modelu.
- Parser rozpoznaje osobno: brakujące numery, nadmiarowe numery, powtórzone
  numery, numery poza zakresem, złą kolejność, puste tłumaczenie oraz linię
  niepasującą do wzorca.

## Walidacja odpowiedzi

- Odpowiedź jest poprawna wyłącznie wtedy, gdy spełnia dokładny kontrakt
  wyjściowy dla wszystkich numerów partii.
- Linia niepasująca do wzorca powoduje odrzucenie odpowiedzi.
- Brakujący albo nadmiarowy numer powoduje odrzucenie odpowiedzi.
- Powtórzony numer powoduje odrzucenie odpowiedzi.
- Numer poza zakresem partii powoduje odrzucenie odpowiedzi.
- Zmieniona kolejność numerów powoduje odrzucenie odpowiedzi.
- Puste tłumaczenie powoduje odrzucenie odpowiedzi.
- Odpowiedź opakowana w Markdown albo zawierająca dodatkowy tekst pozostaje
  niepoprawna, nawet jeżeli zawiera możliwy do wycięcia poprawny fragment.
- Odpowiedź przerwana przez limit wyjścia pozostaje niepoprawna.
- Niepełny albo niezwalidowany wynik nie może zostać zapisany jako sukces.

## Naprawa i ponowienie po błędnej odpowiedzi

- Każda odpowiedź niezgodna z kontraktem może uruchomić kolejną próbę w granicy
  skonfigurowanego limitu ponowień.
- Gdy naruszenie da się zawęzić do konkretnych numerów, kolejna próba prosi
  wyłącznie o te numery.
- Gdy naruszenia nie da się zawęzić do numerów, kolejna próba prosi o całą partię.
- Numery poprawnie przetłumaczone we wcześniejszej próbie są zachowywane i nie są
  tłumaczone ponownie.
- Kolejna próba zachowuje trzy podstawowe prompty.
- Do kolejnej próby zostaje dołączony na końcu prompt korekcyjny.
- Prompt korekcyjny wskazuje wykryty błąd oraz numery, których dotyczy.
- Gdy błąd dotyczy liczby linii lub numerów, prompt korekcyjny podaje oczekiwaną
  wartość.
- Prompt korekcyjny dotyczy bezpośrednio poprzedniej odpowiedzi i nie gromadzi
  historii wszystkich wcześniejszych błędów.
- Wynik naprawy jest akceptowany wyłącznie wtedy, gdy po scaleniu z zachowanymi
  numerami cała partia spełnia kontrakt wyjściowy.
- Po wyczerpaniu limitu bez kompletnej poprawnej partii silnik LLM kończy próbę
  jawnym błędem tłumaczenia.
- Częściowa odpowiedź nie jest zapisywana po ostatniej próbie.

## Podział partii na żądania

- Domyślnie cała partia napisów pliku idzie w jednym żądaniu.
- Silnik LLM dzieli partię wyłącznie po sygnale dostawcy o wyczerpaniu limitu
  wyjścia albo limitu kontekstu. Podział jest reakcją na zdarzenie, nie
  przewidywaniem rozmiaru odpowiedzi.
- Kod nie szacuje liczby tokenów odpowiedzi z długości tekstu.
- Podział zachowuje kolejność napisów.
- Podział nie zmienia numeracji widzianej przez walidację partii.
- Ustawienie liczby linii na żądanie pozostaje dostępne dla użytkownika jako
  ograniczenie górne.
- Wartość ustawienia widoczna w panelu jest liczbą, nie słowem opisującym
  domyślność.

## Role promptów

### Prompt systemowy

- Określa kontrakt numerowanych linii odpowiedzi.
- Określa zakaz zwracania treści poza numerowanymi liniami.
- Ma pierwszeństwo przed pozostałymi promptami w sprawach formatu odpowiedzi.

### Prompt tłumaczeniowy

- Określa, że przekazane napisy mają zostać przetłumaczone na język polski.
- Zawiera wszystkie merytoryczne reguły tłumaczenia.
- Nie może zmieniać kontraktu formatu.

### Prompt stylowy

- Określa styl polskiego tekstu.
- Nie może zmieniać kontraktu formatu ani mapowania linii.
- W jednym wywołaniu aktywny jest dokładnie jeden styl.

### Prompt korekcyjny

- Jest używany wyłącznie po odpowiedzi niezgodnej z kontraktem.
- Opisuje konkretny błąd wykryty w poprzedniej odpowiedzi.
- Nakazuje nie powtarzać tego błędu i zwrócić odpowiedź zgodną z kontraktem.
- Nie zastępuje trzech promptów podstawowych.
- Nie zmienia wymaganej liczby tłumaczeń dla zakresu, o który prosi.

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
- Stałe mogą określać wyłącznie niezmienne nazwy zasobów, wzorzec formatu linii i
  domyślną nazwę stylu.
- Brak, błąd odczytu, błędne kodowanie UTF-8 albo pusta treść `system.md`,
  `translation.md`, `retry.md` lub wybranego stylu jest jawnym błędem
  konfiguracji silnika tłumaczeniowego.
- Test zbudowanej paczki potwierdza, że wszystkie obowiązkowe pliki `.md` są
  dostarczane razem z AniShift.

## Wymagania jakościowe

- Rusztowanie formatu odpowiedzi zużywa nie więcej niż 3,5 tokena na linię
  mierzone tokenizerem `o200k_base` na korpusie napisów użytkownika.
- Zwykły odcinek mieści się w jednym żądaniu w granicy domyślnego limitu wyjścia.
- Naprawa jednej zepsutej linii nie wymaga ponownego tłumaczenia całej partii.
- Diagnostyka naruszenia kontraktu jest wystarczająca do wskazania przyczyny bez
  logowania treści napisów.

## Inwarianty

- Wynik silnika LLM jest zawsze kompletnym, zwalidowanym zestawem tłumaczeń dla
  całej partii albo jawnym błędem.
- Liczba wyników jest równa liczbie napisów przekazanych modelowi.
- Mapowanie numeru jednoznacznie łączy każde tłumaczenie z wejściem.
- Każdy model i dostawca LLM otrzymuje ten sam logiczny kontrakt formatu.
- Kod nie zakłada obsługi natywnego `response_format` ani JSON Schema przez
  wybrany model. Wspólny kontrakt opiera się na promptach, czystych danych i tej
  samej ścisłej walidacji lokalnej dla każdego dostawcy.
- Język docelowy nie jest wybieralny i pozostaje polski.
- Treść promptów oraz napisów nie trafia do logów.
- Konfiguracja użytkownika nie jest właścicielem treści promptów aplikacji.
- Publiczne typy wyniku używane przez dalszy pipeline pozostają zgodne z
  istniejącym kontraktem serwisu tłumaczenia.

## Ograniczenia

- Dopuszczalny zakres `llm_max_output_tokens` kończy się na 32000; format musi
  mieścić realne pliki użytkownika poniżej tej granicy.
- Silnik tłumaczenia LLM nie importuje `anishift.services.llm`; completer wchodzi
  wyłącznie przez wstrzyknięcie z `application/runtime.py`.
- Zmiana nie może wprowadzić nowej zależności zewnętrznej.
- Zmiana nie może naruszyć bramek jakości repozytorium.

## Zakazane

- Format odpowiedzi bez numeracji linii.
- Odpowiedź swobodnym tekstem bez numerów.
- Ciche pomijanie linii odpowiedzi niepasującej do wzorca.
- Wycinanie poprawnego fragmentu z odpowiedzi zawierającej Markdown lub dodatkowy
  tekst.
- Znacznik numeru mogący zostać zinterpretowany jako lista Markdown albo nagłówek.
- Traktowanie tekstu źródłowego jako udanego tłumaczenia po błędzie modelu.
- Zapis częściowej albo niezwalidowanej odpowiedzi.
- Konfigurowanie innego języka docelowego dla silnika LLM.
- Przekazywanie modelowi metadanych materiału.
- Umieszczanie reguł jakości tłumaczenia w kodowym kontrakcie formatu zamiast w
  prompcie tłumaczeniowym.
- Przechowywanie wersjonowanych promptów aplikacji w runtime'owym katalogu
  `config/`.
- Rejestr promptów oparty na kategoriach `task`, `style`, `module` i `contract`.
- Logowanie treści napisów, tłumaczeń albo surowej odpowiedzi modelu w
  diagnostyce naruszeń.

## Zakres

- Kontrakt numerowanych linii na wejściu i wyjściu silnika LLM.
- Parser odpowiedzi z rozpoznawaniem rodzaju naruszenia i numerów, których
  dotyczy.
- Naprawa zawężona do brakujących lub błędnych numerów.
- Zachowanie poprawnych tłumaczeń między próbami.
- Treść trzech podstawowych promptów i promptu korekcyjnego w zakresie opisu
  formatu.
- Domyślny podział partii silnika LLM na jedno żądanie na plik.
- Zapasowy limit rozmiaru żądania silnika LLM.
- Podniesienie domyślnego limitu wyjścia modelu.
- Prezentacja liczby linii na żądanie w panelu ustawień.
- Usunięcie kontraktu JSON granicy tłumaczenia.

## Poza zakresem

- Rozbudowana treść merytoryczna promptu tłumaczeniowego.
- Biblioteka dodatkowych stylów poza minimalnym stylem neutralnym.
- Obsługa języków docelowych innych niż polski.
- Automatyczne wykrywanie lub dobieranie stylu.
- Pozyskiwanie metadanych materiału.
- Zmiana działania Google Translate i DeepL.
- Zwijanie klatka po klatce dla strumienia napisów ekranowych.
- Kolejka silników awaryjnych.
- Zmiana ekstrakcji napisów, TTS, miksowania i tworzenia pliku wynikowego.

## Odrzucone

- Format XML `<t i="N">tekst</t>`. Zmierzony koszt jest wyższy niż obecnego
  kontraktu JSON.
- Format `[[N,"tekst"]]` oraz `{"N":"tekst"}`. Droższe od numerowanych linii i
  nie dają w zamian mocniejszej walidacji.
- Format `N. tekst`. Modele przerabiają go na listę Markdown i przenumerowują.
- Format `#N tekst`. Znak `#` bywa interpretowany jako nagłówek Markdown.
- Format `N: tekst`. Wygląda identycznie jak etykieta mówiącego w napisach.
- Goła tablica tekstów bez numerów. Najtańsza ze zmierzonych, ale usuwa
  weryfikowalność przypisania, która jest wymogiem.
- Regex ignorujący linie niepasujące do wzorca, jak w implementacji sprzed
  kontraktu JSON.

## Warunki sukcesu

- Każde żądanie modelu zawiera napisy w dokładnym kontrakcie wejściowym.
- Każdy zaakceptowany wynik spełnia dokładny kontrakt wyjściowy dla całej partii.
- Każda niezgodność wymieniona w sekcji walidacji jest wykrywana i odrzucana, co
  potwierdzają testy jednostkowe parsera dla każdego rodzaju naruszenia.
- Naprawa po niezgodnej odpowiedzi prosi wyłącznie o numery, których dotyczyło
  naruszenie, co potwierdza test na atrapie completera.
- Żaden częściowy albo niezwalidowany wynik nie jest zapisywany jako sukces.
- Rusztowanie odpowiedzi nie przekracza 3,5 tokena na linię, co potwierdza pomiar
  na korpusie napisów użytkownika.
- Model nie otrzymuje ustawień języka ani metadanych materiału.
- Pełne bramki jakości repozytorium przechodzą po implementacji.
- Przelot na żywo tłumaczy wszystkie odcinki z katalogu roboczego użytkownika
  modelem `gpt-5.6-terra` na Foundry bez błędu terminalnego, a właściciel produktu
  ocenia wynikowe napisy jako poprawne.

## Odłożone

- Opracowanie pełnej treści promptu tłumaczeniowego.
- Dodanie i opracowanie kolejnych stylów.
- Ocena jakości tłumaczenia i strojenie treści promptów.
- Zwijanie powtarzających się napisów ekranowych przed tłumaczeniem.

## Nierozstrzygnięte

Brak. Specyfikacja rozstrzyga kontrakt wymagany do przygotowania planu.
