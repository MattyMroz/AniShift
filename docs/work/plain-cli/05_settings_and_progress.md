# 05 — Ustawienia i widok postępu

Wymagania etapu 05. Dwa powiązane rezultaty: panel ustawień, który udostępnia
realne pokrętła jakości, oraz widok postępu, który przy wielu plikach nie gubi
ani marki, ani wierszy.

Dokument jest tablicą prawdy tego etapu. Tam, gdzie unieważnia wcześniejsze
ustalenia, mówi to wprost w sekcji „Unieważnienia".

---

## 1. Cel

Panel ustawień ma pozwolić wyregulować jakość lektora bez edycji plików i bez
znajomości kodu. Widok postępu ma pokazywać całą kolejkę, nie tylko tyle, ile
zmieści się na ekranie.

Warunek sukcesu, obserwowalny:

- każde pokrętło realnie wpływające na jakość jest albo edytowalne z panelu,
  albo świadomie i pisemnie zostawione na sztywno;
- run 46 plików pokazuje markę, maskotkę, dowolny fragment kolejki i stopkę
  jednocześnie, bez utraty wiersza;
- nawigacja klawiaturą wystarcza do wszystkiego, mysz jest wygodą.

## 2. Stan faktyczny

Zweryfikowany w kodzie na `4b03ce2`, nie z pamięci dokumentów.

### 2.1 Co już istnieje i działa

- `anishift/config/field_catalog.py` — pełny kontrakt `SettingSpec`: `value_type`,
  `default`, `allowed_values`, `minimum`, `maximum`, `validation_pattern`,
  `depends_on`, `invalidates`, `object_fields`, `is_secret`, `scope`. Katalog
  buduje 60 pól i zna zależności między nimi.
- `USER_SETTING_DISPOSITIONS` — jawna decyzja `VISIBLE`/`CONDITIONAL`/`INTERNAL`/`REMOVED`
  dla każdego pola `UserSettings`.
- Cztery magazyny konfiguracji: `.env` (sekrety), `config/settings.json`
  (`UserSettings`), `config/presets.json` (presety Auto),
  `config/anishift.models.jsonc` (katalog modeli, tylko do czytania).
- `TerminalRenderer` z jedną aplikacją Prompt Toolkit, `mouse_support=True`,
  `full_screen=True`, przyklejoną stopką przez `_fit_frame`.

### 2.2 Co jest zepsute albo niewykorzystane

| fakt | dowód | skutek |
|---|---|---|
| układ panelu nie jest w żaden sposób wiązany z katalogiem | `settings.py:28` importuje z katalogu tylko trzy nazwy; układ to trzy krotki `_*_FIELDS` | rozjazd nie daje sygnału; zmierzone: 55 pól w katalogu, 35 w układzie, 6 edytowalnych nigdy niepokazanych, z czego 1 to realna luka |
| `minimum`/`maximum` służą wyłącznie do treści błędu | `settings.py:769-771` | użytkownik poznaje zakres dopiero po pomyłce |
| liczby edytuje się wyłącznie wpisywaniem | `settings.py:620-626` | brak inkrementacji, brak kursora, brak kasowania w środku |
| `OBJECT_LIST` nie ma edytora | `settings_editors.py:33-35` rzuca `TypeError` | `elevenbytes_custom_voices` jest nieosiągalne z UI |
| okno listy to brute force `O(n³)` na klatkę | `_sectioned_window`, `settings.py:1154-1173` | ~2,7 tys. operacji na klatkę przy 10 klatkach/s |
| brak stanu przewijania | okno jest funkcją kursora | nie da się przewinąć bez zmiany zaznaczenia |
| ←→, PageUp/PageDown, Home/End nie działają | brak bindingów, `prompts.py:248-294`; na Windowsie wpadają w `"any"` z `data=""` | martwe klawisze |
| maskotka nigdy nie jest widoczna w Auto | `show_mascot: bool = False` na sztywno w `resolve_auto_geometry`, `prompts.py` | kod łamie R-407 starej specyfikacji |
| nadmiar wierszy postępu jest ucinany | `_fit_frame` obcina body do `rows-1`, `app.py:534-544` | przy 19 grupach na ekranie 24 wiersze część kolejki jest niewidoczna bez ostrzeżenia |
| kółko myszy jest no-opem | `Window._scroll_down` wymaga `content_height > window_height`, treść ma dokładnie `rows` | zdarzenie dochodzi i jest gubione |
| `narrator_sample_rate` jest martwym polem | `AudioConfig` budowany w `runtime.py:654` nie przekazuje go | wartość z configu nie ma wpływu |

## 3. Drzewo ustawień

Klasyfikacja każdego pokrętła wpływającego na wynik. Cztery decyzje:

- **WYSTAW** — pole trafia do panelu jako osobna pozycja
- **INTENCJA** — nie wystawiamy surowych liczb, wystawiamy cel użytkownika,
  a liczby są ich pochodną
- **NAPRAW** — to nie jest ustawienie, to defekt
- **ZOSTAW** — zostaje na sztywno, z podanym powodem

### 3.1 Napisy — co lektor czyta

Największa dziura. Decyduje o treści produktu, a nie ma ani jednego pola.

| pokrętło | miejsce | dziś | decyzja |
|---|---|---|---|
| progi i wagi klasyfikatora dialog/napis ekranowy | `subtitles/classifier.py:74,77,161-173` | sztywne | **INTENCJA** |
| regexy nazw stylów dające twarde verdicty | `subtitles/classifier.py:37,42,45,50` | sztywne | **INTENCJA** |
| dedup animacji klatka-po-klatce | `subtitles/classifier.py:57,60`, `service.py:43` | sztywne | ZOSTAW |
| maks. znaków w linii napisu | `translation/linebreak.py:27` = `42` | sztywne | **WYSTAW** |
| maks. linii na event | `translation/linebreak.py:30` = `2` | sztywne | **WYSTAW** |
| timing generowanego SRT | `subtitles/srt.py:27,30,33,36` | sztywne | ZOSTAW |

Uzasadnienie INTENCJI: użytkownik nie chce ustawiać `_SCORE_DIALOG = 0.55`. Chce
powiedzieć, **co ma być przeczytane**. Wystawiamy jedno pole wyboru zakresu
czytania; progi pozostają szczegółem implementacji za tym wyborem. Surowe wagi w
panelu byłyby pokrętłem, którego nikt nie umie ustawić i którego zła wartość
psuje produkt bez komunikatu.

Uzasadnienie WYSTAW dla layoutu linii: `42` znaki i `2` linie są widoczne wprost
w produkcie, użytkownik ocenia je wzrokiem, a `translation_handler.py:267,270`
woła splitter bez możliwości override.

### 3.2 Tłumaczenie — ile kontekstu widzi model

| pokrętło | miejsce | dziś | decyzja |
|---|---|---|---|
| znaków na request | `translation/chunking.py:32` = `750` | sztywne | **INTENCJA** |
| linii na chunk | `translation/chunking.py:35` = `250` | sztywne | **INTENCJA** |
| linii w batchu LLM | `translation/engines/llm/config.py:26` = `1000` | sztywne | **INTENCJA** |
| rozmiar batcha | `translation_batch_size` | wystawione | zostaje |
| równoległość, retry | `translation_concurrency`, `translation_max_retries` | wystawione | zostaje |
| temperatura, top_p, limit tokenów, styl | `llm_*` | wystawione | zostaje |
| retry kontraktu JSON | `llm/config.py:28` = `3` | sztywne | ZOSTAW |
| cap backoffu | `llm/_retry.py:23` = `4.0` s | sztywne | **NAPRAW** |
| timeout LLM | `llm/config.py:30` = `300` s | sztywne | ZOSTAW |

Uzasadnienie INTENCJI: te trzy liczby razem odpowiadają na jedno pytanie — jak
duży kawałek odcinka model widzi naraz. Większy kawałek to spójniejsze zaimki i
terminologia, ale wyższe ryzyko złamania kontraktu odpowiedzi. Wystawiamy jedno
pole rozmiaru kontekstu; trzy liczby są jego pochodną.

Uzasadnienie NAPRAW dla backoffu: cap 4 s przy odpowiedzi 429 od dostawcy pali
dwie próby w osiem sekund i gubi batch. To defekt niezawodności, nie preferencja.

### 3.3 Lektor i dźwięk

| pokrętło | miejsce | dziś | decyzja |
|---|---|---|---|
| silnik, model, głos, retry | `tts_engine`, `tts_provider_model_id`, `tts_voice_id`, `tts_max_retries` | wystawione | zostaje |
| tempo, offset głośności, równoległość, native rate/volume/pitch | `tts_profile.*` | wystawione | zostaje |
| opcje providera | `tts_profile.engine_options.*` | wystawione | zostaje |
| profil i bitrate wyjścia | `tts_output_profile`, `tts_output_bitrate` | wystawione | zostaje |
| gain narratora i oryginału | `narrator_mix_base_gain_db`, `original_gain_db` | wystawione | zostaje |
| własne głosy ElevenBytes | `elevenbytes_custom_voices` | w katalogu, **bez edytora** | **WYSTAW** |
| sufit jakości Edge 24 kHz/96 kbps | `tts/engines/edge/constants.py:29` | sztywne | ZOSTAW |
| sample rate narratora | `audio/config.py:44` = `48000`, nieprzekazywany | martwe pole | **NAPRAW** |
| współczynniki downmiksu 5.1→stereo | `audio/channels.py:42` | sztywne | ZOSTAW |
| tolerancja długości EAC3 vs tolerancja inspekcji | `audio/output.py:43` = 64 ms, `inspection.py:42` = 1 s | dwa niespójne progi | **NAPRAW** |
| cięcie tekstu na fragmenty TTS | `tts/chunking.py:22,25`, `text/boundaries.py` | sztywne | ZOSTAW |

Uzasadnienie ZOSTAW dla Edge: format jest własnością silnika, a nie preferencją;
zmiana wymaga sprawdzenia, co Edge realnie wspiera, i należy do osobnego etapu.

Uzasadnienie ZOSTAW dla listy skrótów: 260 pozycji nie jest polem w panelu.
Brakujący skrót to zgłoszenie, nie ustawienie.

### 3.4 Wybór ścieżek

| pokrętło | miejsce | dziś | decyzja |
|---|---|---|---|
| priorytety języków audio i napisów | `audio_language_priority`, `subtitle_language_priority` | wystawione | zostaje |
| kara za signs/song/forced | `extraction/tracks.py:50,60` | sztywne | ZOSTAW |

Uzasadnienie: ścieżka błędnie odrzucona jako signs-only jest naprawialna w trybie
Ręcznym, który już pozwala wskazać konkretną ścieżkę. Dublowanie tego pokrętłem
liczbowym w panelu nie dodaje wartości.

### 3.5 Podsumowanie decyzji

**Nowe pola w panelu:** zakres czytania napisów, maks. znaków w linii, maks.
linii na event, rozmiar kontekstu tłumaczenia, własne głosy ElevenBytes.

**Naprawy bez nowego pola:** cap backoffu LLM, martwy `narrator_sample_rate`,
niespójne progi tolerancji długości.

Pięć nowych pól, nie pięćdziesiąt. Reszta zostaje na sztywno z powodem zapisanym
wyżej.

## 4. Wymagania panelu ustawień

### 4.1 Podział własności

Katalog i widok mają rozdzielne, nienachodzące odpowiedzialności. To nie jest
kompromis — to warunek, żeby polskie teksty nie trafiły do warstwy konfiguracji,
a walidacja nie trafiła do widoku.

| decyzja | właściciel | dowód, że tam należy |
|---|---|---|
| czy pole jest edytowalne | katalog: `USER_SETTING_DISPOSITIONS` | już tam jest, jawna decyzja per pole |
| czy pole jest teraz aktywne | katalog: `depends_on` | zależy od wartości innych pól, nie od widoku |
| typ, zakres, wzorzec, dozwolone wartości | katalog: `SettingSpec` | walidacja musi działać też bez UI |
| która kategoria i sekcja | widok | decyzja prezentacyjna, zmienna bez zmiany kontraktu |
| kolejność w sekcji | widok | jak wyżej |
| polska etykieta i opis | widok | `label`/`description` w katalogu są UI-neutralne po angielsku |

- R-05-001 Widok nie decyduje, **czy** pole istnieje. Decyduje wyłącznie, **gdzie**
  je pokazać.
- R-05-002 Każde pole oznaczone w katalogu jako edytowalne występuje w dokładnie
  jednym miejscu układu panelu. Pole pominięte albo zdublowane jest błędem
  wykrywanym testem, nie cichą luką.
- R-05-003 Pole nieaktywne przez `depends_on` nie jest rysowane. Nie ma wersji
  wyszarzonej.
- R-05-004 `SettingSpec` nie zyskuje pól prezentacyjnych. Grupa, kolejność ani
  polski tekst nie wchodzą do `anishift/config/`.

Uzasadnienie R-05-002, oparte na pomiarze a nie na przypuszczeniu. Katalog dla
konfiguracji `elevenbytes`/`run6` daje 55 pól, układ panelu wymienia 35. Różnica
rozkłada się tak:

- 9 pól z układu jest w tej konfiguracji nieaktywnych — `native_rate`,
  `native_volume`, `native_pitch` należą do Edge i SAPI, a `engine_options.*` do
  `run7` i ElevenLabs. To poprawne działanie `depends_on`, nie defekt.
- 6 pól edytowalnych w katalogu nie pojawia się w układzie. Pięć z nich jest
  osiągalnych inną drogą i tak ma zostać: `llm_provider` i `llm_provider_model_id`
  obsługuje atomowy wybór modelu, żeby nie dało się zestawić niepoprawnej pary;
  `palantir_enrollment_base_url` i `openai_compatible_base_url` żyją w kategorii
  Połączenia budowanej osobno; `primary_model_alias` jest świadomie ukryty.
- Zostaje **jedna** realna luka: `elevenbytes_custom_voices` ma w katalogu pełny
  kontrakt z trzema polami obiektu i nie istnieje w panelu, bo `OBJECT_LIST` nie
  ma edytora.

Wniosek: układ nie jest zepsuty, jest niesprawdzony. Dlatego nie usuwamy żadnej z
list — wiążemy je testem kompletności z jawną, opisaną listą pól świadomie
obsługiwanych inną drogą. Bez tego testu każde pole dodane do katalogu w
przyszłości może zniknąć po cichu, dokładnie jak własne głosy.

### 4.2 Grupowanie i kolejność

- R-05-010 Kategorie: `Ogólne`, `Napisy`, `Tłumaczenie`, `Lektor`, `Wynik`,
  `Połączenia`, `Przywróć domyślne`, `Cofnij`. Kategoria `Napisy` jest nowa i
  mieści zakres czytania oraz layout linii.
- R-05-011 W kategorii pola są pogrupowane nazwanymi sekcjami, od najczęściej
  zmienianych do najrzadszych. Kolejność jest jawna, nie alfabetyczna.
- R-05-012 Układ panelu — kategoria, sekcja, kolejność, polski tekst — jest jedną
  strukturą danych w warstwie CLI, czytaną zarówno przez widok, jak i przez test
  kompletności z R-05-002.

### 4.3 Klawiatura

- R-05-020 Kontrakt klawiszy rozszerza się o `←`, `→`, `PageUp`, `PageDown`,
  `Home`, `End`. Rozszerzenie następuje w `TerminalRenderer._key_bindings()`,
  bo to jedyny właściciel interakcji.
- R-05-021 Na polu liczbowym `←` i `→` zmieniają wartość o krok, z klampowaniem
  do `minimum`/`maximum` ze spec. Krok jest pochodną typu i zakresu, nie nowym
  polem konfiguracji.
- R-05-022 Na polu wyboru `←` i `→` przechodzą po `allowed_values` bez otwierania
  modala.
- R-05-023 `PageUp`/`PageDown` przewijają o stronę, `Home`/`End` skaczą na
  początek i koniec listy.
- R-05-024 Wpisywanie ręczne pozostaje dostępne dla każdego pola liczbowego i
  tekstowego. Strzałki są skrótem, nie zamiennikiem.
- R-05-025 Zakres i krok są widoczne przy polu, zanim użytkownik popełni błąd.

### 4.4 Cofnij

- R-05-030 Ostatnim wierszem każdego poziomu jest `Cofnij`. Wiersz jest zawsze
  widoczny — nie może zostać wypchnięty poza okno przez przewijanie listy.
- R-05-031 `Enter` na wierszu `Cofnij` zwija jeden poziom. `Esc` robi to samo.
- R-05-032 `Enter` nie zmienia znaczenia na innych wierszach. Wciąż zatwierdza
  albo wchodzi w pozycję.

### 4.5 Opisy

- R-05-040 Opis pola nie kończy się kropką.
- R-05-041 Opis mówi, co pole zmienia w wyniku, nie jak jest zaimplementowane.
- R-05-042 Komunikat błędu zawiera zakres, gdy spec ma `minimum` i `maximum`.

### 4.6 Przewijanie listy

- R-05-050 Lista ma własny stan przewijania. Przewinięcie myszą nie zmienia
  zaznaczenia.
- R-05-051 Nawigacja klawiaturą zawsze trzyma kursor w widoku: ruch poza widoczny
  zakres przewija okno minimalnie. Przewinięcie myszą może odsunąć widok od
  kursora, a pierwsze naciśnięcie strzałki wraca do niego. To rozstrzyga konflikt
  między R-05-050 i widocznością kursora — zaznaczenie nie ucieka za myszą, ale
  klawiatura nigdy nie działa na niewidocznym wierszu.
- R-05-052 Wyznaczanie okna jest liniowe względem liczby wierszy. Obecne
  `O(n³)` znika.
- R-05-053 Kółko myszy przewija listę. Klawiatura pozostaje wystarczająca —
  mysz nie jest kryterium akceptacji.

## 5. Kolorystyka

- R-05-060 Paleta wywodzi się z maskotki: błękit `#0062fa`, fiolet `#4c03d9`,
  czerwień `#f9011a`, biel i szarości, tło terminala.
- R-05-061 Tekst normalny jest biały lub jasnoszary, tekst pomocniczy szary.
  Kolor jest akcentem, nie tłem treści.
- R-05-062 Aktywny wiersz jest wyróżniony kolorem i markerem po lewej, nigdy
  kolorowym tłem.
- R-05-063 Kolory semantyczne zostają rozdzielone od palety marki: zielony
  sukces, żółty ostrzeżenie, czerwony błąd. Czerwień marki nie jest używana do
  stanu błędu w tym samym widoku.
- R-05-064 Stan nie może zależeć wyłącznie od koloru. Słowo albo symbol zawsze
  towarzyszy.
- R-05-065 Nie powstaje theme engine ani konfiguracja kolorów przez użytkownika.

## 6. Widok postępu

### 6.1 Maskotka

- R-05-070 Marka w Auto zawiera maskotkę, tak jak Home. `show_mascot=False`
  w `resolve_auto_geometry` przestaje być stałą.
- R-05-071 Gdy terminal jest zbyt niski albo wąski, maskotka degraduje się tą
  samą drabiną co na Home. Postęp ma pierwszeństwo przed maskotką.

### 6.2 Przewijanie kolejki

- R-05-080 Widok Auto składa się z trzech regionów: przyklejony nagłówek z marką
  i maskotką, przewijana kolejka, przyklejona stopka.
- R-05-081 Żaden wiersz kolejki nie jest ucinany bez wskazania. Gdy część
  kolejki jest poza widokiem, widok pokazuje to jawnie.
- R-05-082 Kolejka przewija się kółkiem myszy oraz `↑↓`, `PageUp`/`PageDown`,
  `Home`/`End`.
- R-05-083 Przewijanie nie zmienia kolejności wierszy ani ich zawartości. Wiersz
  pliku pozostaje jednym stabilnym wierszem przez cały run.
- R-05-084 Domyślnie widok trzyma się aktywnej pracy. Ręczne przewinięcie
  zatrzymuje autopodążanie do powrotu na koniec listy.
- R-05-085 Maskotka pozostaje w nagłówku, poza przewijanym regionem. Jej wiersz
  ekranowy nie zmienia się przy przewijaniu.

### 6.3 Wykonalność — analiza, nie założenie

Pytanie: da się zrobić przyklejony nagłówek z obrazem SIXEL, przewijany środek i
przyklejoną stopkę?

Odpowiedź: tak, bez viewportu i bez drugiego renderera. Dowód z kodu:

1. Ramka jest **płaskim tekstem o dokładnie tyle wierszy, ile ma terminal** —
   `_fit_frame` obcina do `rows-1` i dokłada stopkę. Regiony są więc kwestią
   składania tekstu, nie osobnych kontenerów.
2. Przyklejona stopka **już istnieje** i działa tym mechanizmem. Nagłówek też —
   Home i Auto składają markę przed treścią.
3. Pozycja maskotki liczy się ze znacznika `\ue000` **w treści ramki**
   (`_native_anchor`). Dopóki nagłówek jest nad przewijanym regionem, wiersz
   znacznika się nie zmienia, więc obraz nie wędruje.
4. `full_screen=True` gwarantuje `Window.vertical_scroll == 0`, więc wiersz
   ramki równa się wierszowi ekranu. Warunek zostaje spełniony, bo przewijamy
   **treść**, nie okno Prompt Toolkit.
5. `mouse_support=True` jest już włączone, a zdarzenie kółka dochodzi do
   `FormattedTextControl.mouse_handler`. Dziś ginie, bo domyślny scroller okna
   wymaga treści wyższej od okna. Przechwycenie zdarzenia w kontrolce zamienia
   je w zmianę naszego offsetu.

Realne przeszkody i sposób ich obejścia:

- **Rastra SIXEL nie da się przyciąć do prostokąta.** Dlatego maskotka nie może
  nigdy wejść w przewijany region — R-05-085 jest wymaganiem, nie preferencją.
- **Nadpisanie komórek spacjami nie usuwa rastra.** Zostaje istniejący podział na
  dwa kasowania: tanie prostokątne między klatkami i pełne `\x1b[2J` przy
  zniknięciu. Przewijanie treści pod maskotką nie wymaga nowego kasowania, bo
  animacja przemalowuje prostokąt co ~100 ms.
- **Przewijanie nie może generować pełnego zapisu SIXEL na każdy klik.** Payloady
  są już cache'owane w `NativeMascotImage.payloads`, a pozycja się nie zmienia,
  więc `_draw_native_mascot` robi early return.

## 7. Zakres

**W zakresie:** panel ustawień oparty na katalogu, pięć nowych pól z sekcji 3.5,
trzy naprawy, rozszerzony kontrakt klawiszy, przewijanie w Ustawieniach i w Auto,
maskotka w Auto, paleta z maskotki.

**Poza zakresem:** theme engine, konfiguracja kolorów przez użytkownika, CRUD
presetów, edytor wszystkich parametrów backendu, format wyjścia Edge, wagi
klasyfikatora jako surowe pola, obsługa myszy jako kryterium akceptacji.

**Zabronione:** powrót `viewport.py`, drugi renderer, druga aplikacja Prompt
Toolkit, własny `Live`, `textual`, `anishift/tui`, bezpośredni import
`prompt_toolkit` poza `interactive/prompts.py`, `RIS` i `\x1b[3J` kasujące
historię terminala.

## 8. Unieważnienia

Ten dokument unieważnia poniższe wcześniejsze ustalenia. Powód: decyzja
właściciela produktu po ocenie działającego programu.

| unieważniane | gdzie | czym zastąpione |
|---|---|---|
| zakaz własnego okna i przewijania w widoku postępu | `spec.md` R-602A i powtórzenia | R-05-080..085, bez viewportu i bez drugiego renderera |
| kontrakt klawiszy ograniczony do `↑↓`/`Enter`/`Space`/`Ctrl+C` | `spec.md` R-200, `02_settings.md` §24 | R-05-020..023 |
| paleta 90–95% grayscale z jednym akcentem `#a855f7` | `spec.md` R-300/R-301 | R-05-060..062, paleta z maskotki |
| allowlista pól w `settings.py` jako niezależna decyzja o widoczności | `spec.md` R-806, `02_settings.md` §12 | R-05-001..002, układ zostaje w CLI, ale jest wiązany z katalogiem testem kompletności |
| `elevenbytes_custom_voices` i `primary_model_alias` jako ukryte | `02_settings.md` §12.2, §12.4 | własne głosy dostają edytor; `primary_model_alias` zostaje ukryty |

Ustalenia niewymienione powyżej **pozostają w mocy**, w szczególności: jeden
wiersz na plik, brak globalnego `Save`, znaczniki wyboru po lewej, brak
kolorowego tła, brak tęczy, brak wymyślonych procentów, marka bez ramki.

## 9. Ryzyka

| ryzyko | dlaczego realne | reakcja |
|---|---|---|
| testy regresyjne pilnują zakazu przewijania | `01-plain-cli.md` P-008 wymaga wykrywania powrotu viewportu | testy przepisać razem z unieważnieniem, nie usuwać bez zapisu |
| baseline 47 nieprzechodzących testów | stan zastany, potwierdzony wielokrotnie | naprawić przed etapem albo jawnie odciąć jako niezwiązane |
| katalog jako źródło etykiet wymaga polskich tekstów | dziś `label`/`description` są angielskie | tłumaczenie etykiet jest częścią etapu, nie osobną pracą |
| krok strzałek dla pól bez `maximum` | np. `narrator_mix_base_gain_db` nie ma zakresu | krok stały dla typu, klamp tylko gdy zakres istnieje |
| przewijanie w Auto przy aktywnej animacji | dwa niezależne zapisy do terminala | maskotka poza regionem przewijanym, R-05-085 |
