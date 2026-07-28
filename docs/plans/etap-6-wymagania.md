# Etap 6 — wymagania TTS i toru audio

> Status: draft 15 do wspólnej iteracji HITL.
> Data audytu: 2026-07-28.
> Branch: `feature/tts-audio`.
> Ten dokument opisuje **co ma działać**. Nie jest jeszcze planem implementacji ani listą commitów.

## 1. Legenda decyzji

- **USTALONE** — wynika z wcześniejszych decyzji projektu albo zostało już potwierdzone przez usera.
- **REKOMENDACJA** — proponowane rozstrzygnięcie po audycie; wymaga akceptacji usera.
- **HITL** — otwarta decyzja, której nie należy zakodować przed wspólnym rozstrzygnięciem.
- **ODRZUCONE** — pomysł z wcześniejszego planu, którego audyt nie potwierdził.

## 2. Cel etapu

**USTALONE**

Etap 6 ma zamienić polski strumień napisów mówionych w gotową ścieżkę lektora:

```text
MKV
  → ekstrakcja audio i napisów
  → klasyfikacja spoken/displayed
  → tłumaczenie, jeżeli źródło nie jest polskie
  → synteza spoken przez wybrany silnik TTS
  → ułożenie klipów na osi czasu
  → regulacja tempa i głośności
  → połączenie lektora z oryginalnym audio
  → ścieżka audio dla etapu 7
```

Główny efekt użytkowy:

- jeden Enter uruchamia automatyczny pipeline;
- TTS zaczyna pracę na gotowych plikach bez ręcznego eksportowania SRT;
- przerwanie lub przejściowa awaria API nie marnuje poprawnie wygenerowanych klipów;
- jeden błąd pliku nie niszczy wyników pozostałych plików;
- etap 7 dostaje zweryfikowaną ścieżkę audio, którą może dołączyć do MKV, wystawić obok pliku albo wykorzystać przy renderze.

## 3. Źródła audytu

### 3.1. AniShift

- [główny roadmap](plan-anishift.md);
- [dotychczasowy plan etapu 6](etap-6-tts-audio.md);
- obecne kontrakty pipeline w `anishift/pipeline/`;
- typy napisów i tłumaczeń w `anishift/services/subtitles/` oraz `anishift/services/translation/`;
- obecne ustawienia i panel w `anishift/config/` oraz `anishift/cli/`;
- instalator i manifest binarek w `anishift/setup/`, `anishift/platform/` oraz `external/bin_hashes.json`.

Ten dokument zastępuje sprzeczne założenia dotychczasowego planu etapu 6, w szczególności
whole-SRT TTS, ukrywanie niedostępnych engine i klucz użytkownika ElevenBytes. Roadmap
pozostaje źródłem zakresu etapów, ale szczegółowy kontrakt etapu 6 pochodzi z tego pliku.

### 3.2. Stary AniShift / mm_avh

- `mm_avh_working_space/modules/subtitle_to_speech.py`;
- `mm_avh_working_space/modules/tts_elevenbytes.py`;
- [audyt starego TTS](../reference/audyt-mm-avh/04-modules-tts.md);
- [audyt wzorców EchoReader TTS](../reference/audyt-mm-avh/08-wzorzec-echoreader-tts.md).

### 3.3. Projekty referencyjne

- `MangaShift/mangashift/services/tts/`;
- `EchoReader/echoreader/services/tts/`;
- lokalne eksperymenty ElevenBytes w `TTS/`.

### 3.4. Aktualne źródła zewnętrzne

- [edge-tts — oficjalne repozytorium](https://github.com/rany2/edge-tts);
- [ElevenLabs Python SDK — oficjalne repozytorium](https://github.com/elevenlabs/elevenlabs-python);
- [ElevenLabs Text to Speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert);
- [pyttsx3 na PyPI](https://pypi.org/project/pyttsx3/);
- [Microsoft SAPI `SpVoice`](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms720149(v=vs.85));
- [Microsoft SAPI `SpFileStream`](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms722562(v=vs.85));
- [Supertonic — oficjalne repozytorium](https://github.com/supertone-inc/supertonic);
- [FLAC — oficjalne wprowadzenie Xiph.Org](https://www.xiph.org/flac/index.html);
- [FFmpeg — oficjalna dokumentacja kodeków](https://ffmpeg.org/ffmpeg-codecs.html).

## 4. Najważniejsze wnioski audytu

### 4.1. Wejściem TTS nie powinien być plik SRT

**REKOMENDACJA**

Obecny AniShift ma już w pamięci:

- tekst;
- początek i koniec eventu;
- kolejność;
- styl;
- informację o powodzeniu tłumaczenia.

TTS powinien przyjmować znormalizowane eventy z pamięci. Parsowanie dopiero co zapisanego
`*.spoken.pl.ass` albo pośredniego SRT byłoby zbędnym zapisem, ponownym odczytem i nowym
miejscem utraty danych.

Pliki napisów pozostają produktami i materiałem diagnostycznym, ale nie stają się
wewnętrznym API pomiędzy translation i TTS.

### 4.2. Źródło polskie i tłumaczone muszą wejść do tego samego kontraktu

**USTALONE**

- Dla napisów obcych TTS używa `FileTranslation.spoken`.
- Dla napisów już polskich TTS używa `SubtitleSplit.spoken`.
- Obie postacie są normalizowane do jednego typu wejściowego TTS.
- Brak obiektu `FileTranslation` przy źródle polskim nie oznacza pominięcia TTS.

### 4.3. MangaShift jest wzorcem, nie modułem do skopiowania 1:1

**USTALONE**

Warto ponownie wykorzystać:

- lazy registry;
- osobne configi silników;
- typowane wyniki audio;
- listowanie głosów;
- deklarowanie możliwości silnika;
- wspólną walidację opcji.

Nie wolno kopiować bez zmian:

- podwójnych semaphore na poziomie fasady i silnika;
- domyślnych concurrency `50–100` bez pomiarów;
- szerokiego `except Exception`;
- braku kontraktu anulowania;
- założenia, że każdy silnik zwraca MP3;
- patchowania pliku `edge_tts/communicate.py` wewnątrz `.venv`;
- samego sprawdzenia importu jako dowodu, że zewnętrzna usługa działa.

### 4.4. Stary plan zawiera niepotwierdzone kopie utils

**ODRZUCONE**

Nie kopiujemy automatycznie `number_in_words.py`, `text_chunker.py` ani
`execution_timer.py` „1:1”.

Audyt wykazał, że stary tor TTS nie importuje `NumberInWords` ani starego chunkera.
AniShift ma własne dzielenie requestów tłumaczenia, ale nie ma jeszcze chunkingu jednego
zbyt długiego eventu TTS. Ten drugi przypadek jest osobnym wymaganiem R9. Każdy dodatkowy
normalizer może pogorszyć wymowę dat, numerów odcinków, skrótów i nazw własnych.

Takie narzędzie może wejść później wyłącznie po:

1. wskazaniu konkretnego przypadku TTS, którego silnik nie potrafi przeczytać;
2. testach przed/po dla języka polskiego;
3. dodaniu jako jawnej, wyłączalnej transformacji, a nie ukrytej modyfikacji tekstu.

### 4.5. Agnieszka i Zosia wymagają różnych architektur procesu

**USTALONE**

Lokalny audyt na docelowej maszynie:

| Głos | Backend | Wynik |
|---|---|---|
| Vocalizer Expressive Zosia Harpo 22 kHz | `pyttsx3` / SAPI5 x64 | poprawny WAV, 2,51 s |
| IVONA 2 Agnieszka 22 kHz | `pyttsx3` / SAPI5 x64 | plik 0 B po około 8 s i modal licencyjny starego sterownika |
| IVONA 2 Agnieszka 22 kHz | bezpośredni SAPI COM x64 | `E_ABORT`, WAV zawierający tylko 46-bajtowy nagłówek |
| IVONA 2 Agnieszka 22 kHz | bezpośredni SAPI COM x86 | poprawny WAV PCM 22,05 kHz mono |
| IVONA 2 Agnieszka 22 kHz | Balcon 1.90 x86 | poprawny WAV PCM 22,05 kHz mono |

Wniosek:

- `pyttsx3` odpada: przy teście 20 eventów utworzył dwa WAV-y, po czym zawiesił proces;
- Agnieszka wymaga procesu x86; ten sam zainstalowany głos nie działa poprawnie w hoście x64;
- Zosia działa poprawnie w procesie x64;
- jeden silnik `sapi` używa wspólnego protokołu trwałego workera, uruchamianego jako x86
  albo x64 zależnie od profilu głosu;
- Balcon i bezpośredni SAPI wygenerowały dla Agnieszki i Zosi pliki identyczne bitowo,
  więc Balcon nie daje żadnej przewagi jakościowej;
- Balcon proces-per-event osiągnął średnio 207,2 ms/event, a trwały worker SAPI po starcie
  średnio 30,7 ms/event; Balcon został odrzucony;
- obecność głosu w rejestrze Windows nie jest równoznaczna z możliwością poprawnej syntezy przez dany backend.

### 4.6. Edge wymaga kontrolowanego patcha jakości

**USTALONE**

Pierwszy smoke test został wykonany na już spatchowanym lokalnym `edge-tts 7.2.8`.
Ponowna kontrola przez `ffprobe` potwierdziła rzeczywisty strumień MP3 96 kb/s:

- `pl-PL-MarekNeural` dostępny;
- `pl-PL-ZofiaNeural` dostępna;
- Marek wygenerował poprawne mono MP3 24 kHz / 96 kb/s;
- tempo, volume i pitch są wspierane przez publiczne opcje biblioteki.

Domyślna biblioteka żąda `audio-24khz-48kbitrate-mono-mp3`. AniShift ma automatycznie
i idempotentnie podnosić format do `audio-24khz-96kbitrate-mono-mp3`.

Patch musi:

- wykonać się przed pierwszym importem `edge_tts.Communicate`;
- rozpoznawać dokładną starą i nową wartość;
- odmówić modyfikacji nieznanej wersji zamiast wykonywać ślepy replace;
- zapisywać plik atomowo;
- aktualizować również stałą bitrate używaną do obliczania offsetów, jeżeli występuje
  w danej wersji biblioteki;
- być ponawiany po aktualizacji/reinstalacji zależności;
- po patchu wykonać kontrolę treści, a test network potwierdza bitrate przez `ffprobe`;
- pokazać czytelny warning i instrukcję, jeżeli środowisko jest tylko do odczytu.

Obecny lokalny patch zmienia output format na 96 kb/s, ale pozostawia
`MP3_BITRATE_BPS = 48_000`. Dla AniShift, który używa własnych timingów napisów, nie
zmienia to montażu audio, lecz psuje wewnętrzną spójność metadanych Edge. Nie kopiujemy
tego błędu.

### 4.7. Supertonic jest ciekawym silnikiem przyszłym, ale nie zastępuje zakresu etapu 6

**REKOMENDACJA**

Supertonic 3:

- oficjalnie wspiera polski;
- działa lokalnie przez ONNX;
- ma 99 mln parametrów i zwraca WAV 44,1 kHz;
- ONNX Runtime ma już wheel dla CPython 3.14 i Windows;
- został zaimplementowany w MangaShift.

Jednak oficjalne repozytorium od 23 lipca 2026 informuje o planowanym archiwum
i zakończeniu oficjalnego rozwoju open-source. Nie dokładamy więc szóstego silnika
do już dużego etapu bez odsłuchu i osobnej decyzji.

Supertonic zostaje kandydatem do późniejszego eksperymentu, a nie wymaganiem DoD etapu 6.

## 5. Zakres

### 5.1. W zakresie

**USTALONE**

- domena TTS z lazy registry;
- cztery identyfikatory silników:
  - `elevenbytes`;
  - `elevenlabs`;
  - `edge`;
  - `sapi`;
- wspólny kontrakt syntezy eventów spoken;
- listowanie i walidacja głosów;
- engine-specific settings;
- retry, backoff, timeout i anulowanie;
- współbieżność wewnątrz silników, które ją obsługują;
- trwałe wznowienie drogich requestów;
- montaż klipów na osi czasu;
- tworzenie WAV lektora;
- regulacja tempa i głośności;
- miks lektora z oryginalną ścieżką;
- wynik audio gotowy dla etapu 7;
- progress i raport podsumowujący;
- testy jednostkowe, integracyjne, network smoke oraz odsłuch realnego odcinka.

### 5.2. Poza zakresem

**USTALONE**

- ponowna klasyfikacja spoken/displayed;
- dual-role eventów `spoken + displayed`;
- nowy algorytm line breaking i typesetting;
- poprawa stylów ASS;
- korekta tłumaczenia przez drugi request LLM;
- składanie finalnego MKV, wypalanie MP4 i wariant `players` — etap 7;
- UI graficzne;
- klonowanie głosu;
- wybór głosu osobno dla postaci;
- diarization;
- lokalny Supertonic jako szósty silnik;
- TTS dla TXT bez wiarygodnej osi czasu.

## 6. Słownik

- **spoken event** — jeden event zakwalifikowany do przeczytania.
- **clip** — audio wygenerowane dla jednego spoken eventu.
- **narrator WAV** — pełna ścieżka samego lektora, ułożona na osi czasu.
- **mixed audio** — lektor połączony z oryginalną ścieżką audio.
- **engine** — implementacja syntezy, np. Edge albo ElevenBytes.
- **provider model** — model wewnątrz danego engine, np. ElevenLabs Multilingual v2.
- **voice** — konkretny głos używany przez engine.
- **resume state** — manifest i poprawne klipy zachowane po przerwaniu lub awarii.
- **provider-wide failure** — błąd wskazujący, że dalsze requesty do tego samego dostawcy
  prawdopodobnie również się nie udadzą.
- **drift** — opóźnienie lektora względem planowanego startu, powstałe, gdy wcześniejszy
  klip nie skończył się przed kolejnym.

## 7. Kontrakt wejściowy

### R1. Znormalizowany spoken event

**REKOMENDACJA**

Każdy event przekazany do TTS zawiera co najmniej:

- stabilny indeks w pliku;
- `start_ms`;
- `end_ms`;
- polski `text`;
- `source_text` dostępny diagnostycznie, jeżeli event był tłumaczony;
- `style`;
- informację, czy tekst pochodzi ze źródła polskiego, czy z tłumaczenia;
- informację o powodzeniu poprzedniego kroku.

TTS nie musi znać obiektów konkretnego silnika tłumaczenia.

### R2. Kolejność

**USTALONE**

- Pliki zachowują kolejność `natsorted`.
- Eventy do schedulera są stabilnie sortowane po `(start_ms, source_index)`.
- `source_index` zachowuje pierwotną kolejność z ASS/SRT dla raportu i resume.
- Remisy czasowe zachowują kolejność źródłową.
- Współbieżna synteza nie może zmienić kolejności składania.
- Indeks eventu jest elementem raportu i resume state.
- Event z `end_ms <= start_ms` nie jest po cichu naprawiany: walidacja zwraca typowany
  błąd z indeksem i timingiem.

### R3. Nieudane tłumaczenie

**USTALONE**

Event z `ok=False` nie powinien być czytany po angielsku jako cichy fallback.
Plik TTS zostaje zatrzymany z czytelnym błędem „translation incomplete”.

To zapobiega powstaniu ścieżki, która wygląda na poprawną, ale przełącza języki w środku.

### R4. TXT

**REKOMENDACJA**

TXT ma dziś sztuczne timingi `0`. Etap 6 nie tworzy na ich podstawie ścieżki anime.
TXT nadal może przejść tłumaczenie i zapis SRT, ale TTS zostaje pominięty z informacją
„no media timeline”.

## 8. Przygotowanie tekstu

### R5. Tekst przekazywany silnikowi

**USTALONE**

Silnik dostaje czysty, widoczny tekst:

- bez tagów ASS;
- bez tagów HTML;
- bez `\N`, `\n` i innych znaczników layoutu;
- bez rysunków ASS;
- z zachowanymi polskimi znakami Unicode;
- bez konwersji do ANSI;
- bez zmiany treści pliku napisów.

Usunięcie layoutu dotyczy tylko wejścia syntezy. Nie modyfikuje produktów ASS.
Tagi i znaczniki layoutu są zastępowane bezpieczną granicą whitespace, a nie ślepo
usuwane. Przykładowo `dobry\Nwieczór` ma dać `dobry wieczór`, nigdy `dobrywieczór`.
Po czyszczeniu whitespace jest normalizowany, a tekst ponownie przechodzi reguły R6.

### R6. Puste i jednoliterowe eventy

**REKOMENDACJA**

- Tekst pusty/whitespace oraz sama interpunkcja (`…`, `!`, `?`) nie uruchamiają requestu.
- Pominięty event dostaje jawny status `skipped_non_speech`; nie jest błędem ani ciszą
  o sztucznie wygenerowanej długości.
- Pojedyncza litera lub cyfra jest prawidłową wypowiedzią i nie może zniknąć po cichu.
- Engine z minimum dwóch znaków stosuje jawny, testowany adapter albo zwraca
  `unsupported_input`; scheduler nie udaje wtedy sukcesu.
- Jeżeli po czyszczeniu plik nie ma żadnego eventu możliwego do syntezy, kończy się jako
  `skipped_no_spoken` z warningiem i nie tworzy oryginalnego-only sidecaru audio.
- Mianownik progressu TTS obejmuje eventy wymagające syntezy; liczba pominiętych jest
  raportowana osobno.

### R7. Normalizacja liczb

**REKOMENDACJA**

Domyślnie tekst trafia do silnika bez własnego zamieniania liczb na słowa.
Nowoczesne Edge i ElevenLabs mają własny text normalization. SAPI również czyta liczby.

Ewentualny Polish text normalizer powinien być osobnym, wyłączalnym modułem z testami,
nie ukrytą częścią `TtsService`.

## 9. Wspólny kontrakt silnika

### R8. Registry

**USTALONE**

- Rejestr jest jednym źródłem prawdy o engine IDs.
- Import rejestru nie importuje SDK i backendów.
- Nie ma dispatchu `if engine_id == ...` w fasadzie ani pipeline.
- Nieznany ID daje typowany błąd z listą poprawnych ID.

### R9. Możliwości silnika

**REKOMENDACJA**

Każdy engine deklaruje capabilities zamiast wymuszać jeden format:

- lokalny albo sieciowy;
- dostępne głosy;
- rzeczywisty format źródłowy audio;
- obsługa batch/concurrency;
- obsługa rate, volume, pitch i voice settings;
- wymagany API key;
- wymagane binarki i głosy systemowe;
- minimalna długość tekstu;
- maksymalna długość tekstu w znakach i/lub bajtach;
- polityka obsługi przekroczenia limitu;
- możliwość sprawdzenia dostępności bez płatnego requestu.

Availability nie jest samym `bool`. Engine zwraca typowany status z kodem powodu
(`ready`, `missing_key`, `missing_voice`, `missing_binary`, `offline`,
`service_unavailable`, `unsupported_platform`), bezpiecznym opisem oraz informacją,
czy wynik pochodzi ze świeżego probe czy z cache.

Pojedynczy spoken event przekraczający limit engine jest deterministycznie dzielony
najpierw na granicach zdań, następnie słów. Części są osobno fingerprintowane,
syntezowane i sklejane bez sztucznej przerwy. Jeżeli nie da się bezpiecznie podzielić
wejścia, event kończy się typowanym `unsupported_input`, nie obcięciem tekstu.

### R10. Wynik syntezy

**REKOMENDACJA**

Wynik jednego eventu zawiera:

- event index;
- status;
- bytes albo atomowo zapisaną ścieżkę;
- format, sample rate i channels;
- engine, provider model i voice;
- czas requestu;
- liczbę prób;
- kod błędu bez sekretów;
- informację, czy wynik pochodzi z resume state.

### R11. Sync facade, async internals

**USTALONE**

Publiczna fasada AniShift pozostaje synchroniczna. Silniki sieciowe mogą używać async
wewnętrznie, jeżeli realnie daje to współbieżność. Event loop nie wycieka do CLI ani
pipeline.

Implementacja ma jednego właściciela event loopa i cyklu życia workerów. Blokujące SDK
nie może być traktowane jako anulowane wyłącznie dlatego, że anulowano coroutine
czekającą na `to_thread()`. Każdy przebieg ma:

- deadline zamykania;
- late-result commit gate blokujący zapis klipu, manifestu i progressu po anulowaniu;
- kontrolowane zakończenie subprocessów;
- jawne bounded abandonment dla workera, którego zewnętrzne SDK nie pozwala przerwać.

Spóźniony wynik po anulowaniu nie może zostać przyjęty do resume state.

## 10. Wymagania silników

### 10.1. ElevenBytes

### R12. Endpointy i ustawienia

**USTALONE**

- ElevenBytes jest osobnym engine od oficjalnego ElevenLabs.
- Korzysta z proxy sprawdzonego w starym AniShift.
- Wspiera co najmniej obecne ścieżki `run6` i `run7`.
- `run6` używa `eleven_multilingual_v2` i jest domyślnym, stabilnym wariantem.
- `run6` nie wystawia regulowanych parametrów głosu; proxy używa wartości domyślnych.
- `run7` używa Eleven v3 i pozostaje wariantem eksperymentalnym.
- `run7` przekazuje:
  - stability;
  - similarity boost;
  - style;
  - speaker boost.
- Wpływ parametrów `run7` nie został empirycznie potwierdzony; obecna implementacja proxy
  może je ignorować albo stosować niezgodnie z oczekiwaniem.
- `run7` potrafi generować niestabilne audio, w tym lekko ucięte końcówki wypowiedzi.
- Głos i wariant endpointu są częścią ustawień oraz fingerprintu.

Lokalny test z 2026-07-24 potwierdził, że oba endpointy zwracają audio. Nie oznacza to
jednak równej stabilności: `run6` jest baseline, a `run7` musi być wyraźnie oznaczony
`experimental` i nie może sam zastąpić wariantu domyślnego.

ElevenBytes w etapie 6 udostępnia wyłącznie:

| Alias | Etykieta | Voice ID |
|---|---|---|
| `dallin` | Dallin — Storyteller | `alFofuDn3cOwyoz1i44T` |

`dallin` jest jedynym i domyślnym głosem ElevenBytes. Nie przenosimy pozostałych aliasów
do wbudowanego katalogu. User może jednak później trwale dodać własny alias, etykietę
i voice ID; taki wpis pojawia się następnie na liście głosów ElevenBytes.

### R13. Publiczny token proxy

**USTALONE**

ElevenBytes nie ma klucza API podawanego przez użytkownika. Jest integracją ze stroną,
a stałe wymagane przez jej publiczny request są częścią implementacji engine:

- nie istnieje `ANISHIFT_ELEVENBYTES_API_KEY`;
- nie ma env override;
- panel nie pokazuje `missing key` dla ElevenBytes;
- user nie konfiguruje tokenu;
- stałe requestu nie są opisywane jako sekret użytkownika.

Jeżeli strona zmieni kontrakt albo przestanie działać, engine pokazuje `service
unavailable`. Nie przełączamy automatycznie na przypadkowy endpoint ani nie prosimy
usera o nieistniejący klucz.

### R14. Retry i jeden właściciel prób

**USTALONE**

- Requesty wykonują się współbieżnie do limitu engine.
- Retry dostają wyłącznie nieudane eventy.
- Poprawnych eventów nie wysyłamy ponownie.
- Event, który wcześniej się wywalił, ma pierwszeństwo w zwolnionym slocie.
- Retry jest planowane natychmiast po wymaganym backoffie, bez bariery czekającej na
  zakończenie całej rundy.
- Oczekiwanie na backoff nie zajmuje slotu concurrency.
- Gdy błędy wskazują provider-wide failure, nie uruchamiamy kolejnych nowych requestów.
- Po wyczerpaniu prób pipeline nie bombarduje API w nieskończoność.
- Domyślny limit to trzy ponowienia po pierwszej próbie, tak jak w obecnym tłumaczeniu.
- Limit jest konfigurowalny i oznacza retry, a nie łączną liczbę prób.
- Scheduler jest jedynym właścicielem retry i licznika płatnych prób. Engine i transport
  nie dokładają ukrytej drugiej pętli retry; reconnect bez ponownego wysłania payloadu
  nie zwiększa licznika, ale każde ponowne wysłanie payloadu już tak.
- Retry obejmuje tylko błędy przejściowe. Błąd klucza, konfiguracji, głosu lub niepoprawnego
  requestu przechodzi od razu do recovery.
- `Retry-After` ma pierwszeństwo przed lokalnym backoffem i nie może zostać skrócone.
- `403` jest klasyfikowane per engine: w oficjalnym ElevenLabs oznacza błąd
  autoryzacji/uprawnień bez retry; w ElevenBytes nie oznacza `missing key`, lecz
  provider-wide blokadę proxy, która może przejść ograniczony transient retry, a potem
  `service_unavailable`.
- Jawne ponowienie wybrane przez usera zaczyna nową serię prób; nie tworzymy
  automatycznej nieskończonej pętli.

### 10.2. Oficjalne ElevenLabs

### R15. SDK i klucz

**USTALONE**

- Używamy oficjalnego SDK `elevenlabs`.
- Zależność zostanie dodana przez `uv add`, nie ręcznie.
- Klucz pochodzi z `ANISHIFT_ELEVENLABS_API_KEY`.
- Klucz jest obecnie brakujący na maszynie testowej, więc live test nie jest teraz możliwy.
- Brak klucza nie może wywołać tracebacku ani ukryć innych silników.

Aktualny SDK wspiera Python `>=3.8,<4.0`, więc Python 3.14 nie blokuje integracji.

### R16. Modele i głosy

**REKOMENDACJA**

- Model jest jawnie wybierany, nie zaszyty w backendzie.
- Domyślny kandydat jakościowy: `eleven_multilingual_v2`.
- Kandydat szybkościowy: `eleven_flash_v2_5`.
- Głosy są pobierane z API i cache'owane z TTL.
- Dozwolony jest również ręczny voice ID.
- Cache listy głosów nie jest resume state i może żyć w config, nie w workspace.

### R17. Voice settings

**USTALONE**

Obsługujemy:

- stability;
- similarity boost;
- style;
- speaker boost;
- speed, jeśli wybrany model/API go wspiera;
- output format.

Każda opcja jest walidowana przed pierwszym płatnym requestem.
`output_format` pochodzi z allow-listy mapującej token ElevenLabs na rzeczywisty
kontener, codec, sample rate i channels. Kompatybilność modelu z formatem jest
sprawdzana przed requestem; odpowiedź nie jest nigdy z góry interpretowana jako MP3.

### R18. Błędy

**USTALONE**

- `400`, `401` i typowe błędy konfiguracji nie są retry.
- `429`, timeout, connection error i przejściowe `5xx` mogą być retry.
- Retry respektuje `Retry-After`, jeśli provider je zwróci.
- Odpowiedź pusta lub niebędąca audio jest błędem.

### 10.3. Edge

### R19. Publiczne API

**USTALONE**

- Używamy zainstalowanego `edge-tts`.
- Wspierana wersja `edge-tts` jest przypięta do jawnie zweryfikowanej wersji lub
  ograniczonego zakresu kompatybilności.
- Głosy PL są pobierane z listy usługi; minimum Marek i Zofia.
- Wspieramy rate, volume i pitch przez publiczne parametry.
- Automatycznie patchujemy bitrate 48 → 96 kb/s zgodnie z wymaganiami z §4.6.
- Patch jest version-aware, idempotentny, atomowy i walidowany rzeczywistym audio.
- Patch dotyczy wyłącznie dokładnie rozpoznanej wersji i wykonuje się przed pierwszym
  importem kodu używającego `Communicate`.
- Nieznana wersja, środowisko read-only albo nieskuteczna walidacja oznaczają jawny
  status `service_unavailable`; AniShift nie przechodzi po cichu na 48 kb/s.
- Nie polegamy na custom SSML, którego Edge TTS już nie wspiera.

### R20. Dostępność i awarie

**REKOMENDACJA**

Typowany availability probe rozróżnia:

- package missing;
- network unchecked/offline;
- voice missing;
- ready.

Sam import biblioteki nie oznacza, że usługa Microsoft aktualnie odpowiada.

### 10.4. SAPI / Zosia i Agnieszka

### R21. Obsługiwane głosy i architektura

**USTALONE**

Engine jest gotowy wyłącznie, gdy:

- system to Windows;
- SAPI działa;
- zainstalowany jest co najmniej jeden obsługiwany głos:
  - `Vocalizer Expressive Zosia Harpo 22kHz` przez worker x64;
  - `IVONA 2 Agnieszka 22kHz` przez worker x86;
- wybrany profil głosu wskazuje właściwą architekturę procesu;
- jawny smoke test albo pierwsze zadanie potwierdziło syntezę niepustego WAV w limicie.

### R22. Izolacja zawieszek

**USTALONE**

Spike na docelowej maszynie rozstrzyga backend:

- bezpośredni SAPI COM w jednym procesie utworzył 20/20 niepustych WAV-ów w 671 ms;
- czas pojedynczego `Speak` wyniósł 21–48 ms, średnio 24,4 ms;
- `pyttsx3.runAndWait()` utworzył tylko dwa pliki i nie zakończył procesu w ciągu
  49 sekund; proces musiał zostać zakończony przymusowo;
- engine `sapi` używa bezpośredniego SAPI COM, nie `pyttsx3`.

Synteza nadal musi być izolowana w kontrolowanym workerze albo subprocessie z timeoutem.
Nie wolno pozostawić głównego CLI bez możliwości przerwania.

Kontrakt to dedykowany subprocess Windows z kontrolowanym workerem SAPI/COM:

- główny proces przekazuje pojedyncze zadania przez ograniczony IPC;
- worker inicjalizuje COM we własnym wątku;
- timeout zabija i odtwarza cały worker, nie blokuje CLI;
- klip jest przyjmowany dopiero po pełnej walidacji;
- restart workera nie usuwa wcześniej ukończonych klipów.

Test implementacji musi jeszcze wymusić timeout i potwierdzić zabicie oraz odtworzenie
workera bez utraty wcześniej przyjętych klipów.

### R23. Wspólny trwały worker

**USTALONE**

- Istnieje jeden engine id `sapi` i jeden protokół workera.
- Zosia uruchamia worker przez 64-bitowy host Windows.
- Agnieszka uruchamia ten sam worker przez 32-bitowy host Windows.
- Worker inicjalizuje COM i wybrany głos raz, a następnie obsługuje wiele eventów przez
  ograniczony protokół IPC.
- Jednorazowy start prototypu x86 trwał 3,728 s; kolejne eventy trwały 26–42 ms,
  średnio 30,7 ms.
- Tekst, ścieżka wyjścia i id eventu są przekazywane jako dane protokołu, nie jako
  interpolowany command string.
- AniShift nie pobiera ani nie uruchamia `balcon.exe`.

### R24. Dostępność

**USTALONE**

Zwykłe `setup` i `doctor` nie uruchamiają syntezy głosu. Stare sterowniki SAPI mogą
wyświetlić modal licencyjny i zablokować bezobsługowy proces. Realny krótki WAV powstaje
wyłącznie po jawnie wybranym `doctor --live`; test ma timeout, kończy subprocess i zgłasza
`broken backend`, jeżeli pojawi się modal albo nie powstanie poprawny plik.

Zwykły doctor:

- potwierdza Windows i dostępność hostów x64/x86;
- listuje głosy osobno w obu architekturach bez uruchamiania syntezy;
- pokazuje dla każdego profilu `available`, `missing voice` albo `unsupported architecture`.

### R25. Adapter SAPI

**USTALONE**

SAPI nie dostaje całego SRT i nie posiada osobnej ścieżki montażu. Jest normalnym
silnikiem TTS działającym przez wspólny kontrakt per event:

1. adapter otrzymuje jeden znormalizowany spoken event;
2. przekazuje id, tekst i kontrolowaną ścieżkę do właściwego workera x86/x64;
3. worker generuje osobny WAV przez `SAPI.SpVoice` i `SAPI.SpFileStream`;
4. adapter waliduje niepusty i dekodowalny plik;
5. wspólny manifest zapisuje ukończony event;
6. wspólny scheduler ustawia klip na osi czasu.

Worker zwraca dokładnie jedną odpowiedź per request. Nieudane albo spóźnione odpowiedzi
nie mogą zatwierdzić klipu po anulowaniu. Zamknięcie wejścia kończy worker; timeout lub
zerwane IPC zabija cały proces i uruchamia świeży worker dla następnej próby.

## 11. Concurrency, kolejka i anulowanie

### R26. Engine-specific concurrency

**REKOMENDACJA**

Nie ma jednego globalnego limitu dla wszystkich TTS:

- SAPI: `1`;
- lokalny backend wymagający jednego modelu: według jego możliwości;
- Edge, ElevenBytes i ElevenLabs: osobne, konfigurowalne limity;
- wartości domyślne wynikają z testu obciążenia, nie z MangaShift.

Limit danego engine jest globalny dla całego przebiegu pipeline, nie mnożony przez liczbę
plików. Każdy engine ma jedną ograniczoną kolejkę priorytetową wspólną dla wszystkich
odcinków. Concurrency nie zastępuje limitów RPM: scheduler respektuje `Retry-After`,
cooldown circuit breakera i nie tworzy nieograniczonej liczby oczekujących tasków.

### R27. Pipeline wielu plików

**USTALONE — WARIANT B**

Wariant A:

```text
extract wszystko → translate wszystko → TTS wszystko
```

Wariant B:

```text
gdy plik ma gotowe spoken → od razu kolejkuj TTS,
podczas gdy pozostałe pliki nadal się tłumaczą
```

TTS jest kolejkowany natychmiast, gdy:

- zakończyło się tłumaczenie spoken danego pliku; albo
- źródło jest już polskie i spoken jest dostępny po ekstrakcji/klasyfikacji.

Pozostałe pliki mogą w tym czasie nadal się ekstrahować lub tłumaczyć. TTS ma osobny
limit concurrency i jednoznaczne anulowanie.

Kontrakt pipeline rozróżnia:

- `source_audio_path` — wyekstrahowane oryginalne audio;
- `narrator_path` — roboczy narrator WAV;
- `mixed_audio_path` — zweryfikowany finalny sidecar etapu 6;
- typowany wynik/statystyki TTS;
- osobne kroki błędów `tts` i `audio`.

Istniejące pole `audio_path` nie może jednocześnie znaczyć oryginału i gotowego miksu.

### R28. Ctrl+C

**USTALONE**

- Jedno `Ctrl+C` rozpoczyna anulowanie całego pipeline.
- Nie trzeba wciskać `Ctrl+C` wielokrotnie.
- Nowe requesty nie są uruchamiane.
- Awaitujące taski dostają anulowanie.
- `asyncio.CancelledError` nie jest retry.
- Workery SAPI i subprocessy FFmpeg są kończone.
- Poprawne, atomowo zapisane klipy zostają do resume.
- Terminal wraca do promptu po domknięciu workerów.
- Po rozpoczęciu anulowania obowiązuje late-result commit gate z R11.
- Worker z nieanulowalnym SDK dostaje ograniczony czas zamknięcia; po deadline zostaje
  odłączony od wyniku przebiegu i nie może już zmieniać stanu aplikacji.

### R29. Kolejność po błędzie

**USTALONE**

W ramach wolnych slotów:

1. retry eventu, który się wywalił;
2. następny event zgodnie z kolejnością;
3. następny plik zgodnie z `natsorted`.

Provider-wide failure zatrzymuje nowe requesty tego engine, ale nie usuwa wyników innych
plików ani innych engine.

## 12. Resume state i integralność

### R30. Lokalizacja

**USTALONE**

Stan żyje wyłącznie pod:

```text
workspace/tmp/<file-id>/tts/
```

Nie powstaje osobny `cache/`, `logs/` ani stan obok kodu.

`file-id` jest krótkim, deterministycznym identyfikatorem odpornym na kolizje i limity
ścieżek Windows, zbudowanym z bezpiecznego fragmentu stemu oraz hasha tożsamości źródła.
Tożsamość źródła obejmuje co najmniej kanoniczną ścieżkę, rozmiar, czas modyfikacji oraz
fingerprint wybranych strumieni; manifest przechowuje te pola jawnie. Zmiana tekstu
spoken jest niezależnie wykrywana przez synthesis fingerprint R32. Podmiana źródła lub
zmiana wybranej ścieżki audio unieważnia odpowiednią warstwę stanu. Długie nazwy,
Unicode i nawiasy mają testy.

### R31. Konflikt z obecnym cleanup

**USTALONE — WYMAGA NAPRAWY**

Obecny runner usuwa całe `workspace/tmp/<stem>` przed ekstrakcją. To skasowałoby resume
state po crashu, zanim TTS mógłby go użyć.

Etap 6 musi rozdzielić:

- jednorazowy scratch ekstrakcji;
- walidowany resume state TTS.

Cleanup nie może usuwać poprawnych klipów TTS przed sprawdzeniem manifestu.

### R32. Warstwowe fingerprinty

**REKOMENDACJA**

Resume ma trzy niezależne poziomy invalidation:

1. **Synthesis fingerprint** — źródło, event/source index, oczyszczony tekst, engine,
   provider model/endpoint, faktyczny resolved voice ID, natywne rate/pitch/volume,
   voice settings, format odpowiedzi API oraz wersja normalizacji tekstu.
2. **Narration fingerprint** — zestaw synthesis fingerprintów, timingi, rozwiązane
   tempo profilu engine/voice, scheduler, roboczy sample rate/channels i wersja montażu.
3. **Mix/output fingerprint** — narrator fingerprint, tożsamość oryginalnej ścieżki
   audio, bazowy gain miksu, offset głosu, channel policy, codec/kontener/bitrate
   i wersja miksu.

Zmiana tempa profilu, gainu, codeca albo bitrate przebudowuje wyłącznie odpowiednią
warstwę po syntezie i **nie powtarza requestów TTS**. Zmiana tekstu, engine, modelu,
resolved voice ID albo natywnych ustawień syntezy unieważnia synthesis fingerprint.
Cache „tylko po indeksie” jest niedopuszczalny.

Zmiana `voice_mix_offset_db`, bazowego `+7 dB` albo gainu oryginału przebudowuje wyłącznie
finalny miks. Nie modyfikuje narrator WAV.

### R33. Zapis atomowy

**USTALONE**

- Audio zapisuje się najpierw jako plik tymczasowy.
- Po pełnej walidacji dekodowalności następuje atomic replace.
- Manifest aktualizuje się dopiero po poprawnym pliku.
- Uszkodzony albo zerowy plik nigdy nie ma statusu success.
- Manifest ma wersjonowany schemat i jednego serializowanego writera albo równoważną
  blokadę chroniącą przed lost update współbieżnych workerów.
- Kolejność commitu to `validate clip → atomic clip replace → atomic manifest snapshot`.
- Przy restarcie poprawny, deterministycznie nazwany orphan clip powstały między replace
  a zapisem manifestu może zostać zweryfikowany i przyjęty bez kolejnego requestu.
- Uszkodzony manifest jest zachowany diagnostycznie i nie prowadzi do częściowego
  zaufania przypadkowym wpisom.

Nie da się zagwarantować dokładnie jednego płatnego requestu przy twardym zabiciu procesu
po sukcesie providera, lecz przed trwałym zapisem odpowiedzi. Implementacja minimalizuje
to okno i nigdy świadomie nie powtarza już zweryfikowanego klipu.

### R34. Sprzątanie

**USTALONE**

Resume state, czyli **stan wznowienia TTS**, to:

- manifest wykonanych eventów;
- poprawnie wygenerowane klipy audio;
- fingerprint tekstu, engine, modelu, głosu i ustawień;
- informacja, które requesty wymagają ponowienia.

Dzięki temu po crashu, `Ctrl+C` albo awarii API AniShift nie płaci i nie czeka drugi raz
za poprawnie wykonane requesty.

Stan wznowienia zostaje do chwili, gdy etap 7 utworzy i zweryfikuje finalny wynik.
Etap 6 może oznaczyć stan jako complete, ale go jeszcze nie usuwa.

### R35. Deduplikacja syntezy

**USTALONE — BRAK DEDUPLIKACJI TEKSTU**

Identyczny tekst w dwóch spoken events jest syntezowany osobno. Powtórzenia w spoken są
rzadkie, a osobny request pozwala zachować naturalną różnorodność intonacji.

Nie należy mylić tego z resume:

- deduplikacja próbowałaby użyć jednego klipu w dwóch różnych eventach — tego nie robimy;
- resume używa poprzedniego klipu wyłącznie dla tego samego eventu i identycznego
  fingerprintu po wznowieniu przerwanego zadania — to pozostaje wymagane.

## 13. Oś czasu

### R36. Podstawowa semantyka

**USTALONE — HEURYSTYKA V1**

- `start_ms` jest najwcześniejszym dozwolonym początkiem klipu.
- Klip nie jest ucinany.
- Jeżeli poprzedni klip skończył się wcześniej, wstawiana jest cisza.
- Jeżeli poprzedni klip zachodzi na kolejny, następny zaczyna się po poprzednim.
- Powstały drift jest liczony i raportowany.

Mały drift jest akceptowalny. Jeżeli później pojawi się dostatecznie długa naturalna
przerwa, harmonogram wraca do oryginalnych timingów bez zmiany szybkości głosu.
Jest to parytet zachowania starego ElevenBytes, ale bez ukrywania problemu.

### R37. Dopasowanie do okna napisu

**USTALONE DLA V1 / HITL DLA HEURYSTYKI ROZSZERZONEJ**

Możliwe polityki:

1. **serialize** — nigdy nie tnij, pozwól na drift;
2. **fit** — przyspiesz klip do długości okna w bezpiecznym zakresie;
3. **overlap** — pozwól klipom nachodzić na siebie;
4. **truncate** — utnij audio.

Etap 6 zaczyna od `serialize`. `truncate` jest odrzucone. Automatyczne `fit` nie jest
domyślne, ponieważ wcześniejsze lekkie zmiany szybkości były słyszalne i irytujące.

**Zasada nadrzędna:** każdy event zaklasyfikowany jako spoken ma zostać przeczytany.
Heurystyka v1 nie przenosi, nie pomija i nie degraduje spoken do displayed.

Duży drift wymaga później osobnego **narration scheduler**, który może rozważyć:

1. odzyskanie opóźnienia przez naturalne przerwy bez zmiany tempa;
2. bardzo małe `fit` tylko w ustalonym, opcjonalnym zakresie;
3. wybór głównego eventu z grupy nakładających się napisów;
4. pozostawienie drugiego eventu wyłącznie jako displayed;
5. przeliczenie końcowych zbiorów spoken/displayed i ponowny zapis produktów napisów.

Przykład do dalszego zaprojektowania:

- dwa jednoczesne eventy na górze i dole;
- dolny event jest czytany;
- górny pozostaje widoczny, ale nie blokuje narracji;
- decyzja zachowuje style, pozycję i tłumaczenie obu eventów.

Rezygnacja z przeczytania spoken może być wyłącznie ostatecznym fallbackiem dużego
konfliktu. W takim przypadku event:

- zostaje dodany do końcowego displayed;
- zachowuje oryginalny timing, styl, layer, pozycję i tagi;
- jest jawnie oznaczony w raporcie jako `displayed_fallback`;
- powoduje ponowny zapis finalnych produktów spoken/displayed.

Nie wyświetlamy domyślnie wszystkich spoken w ścieżce displayed, ponieważ wariant
lektorski stałby się pełnymi napisami i powodował zbędny szum na ekranie.

To nie może być heurystyka oparta wyłącznie na „góra = displayed”, ponieważ zwykły dialog
bywa przesuwany na górę, aby nie zasłaniać znaku. Potrzebne będą co najmniej: overlap
czasowy, pozycja, styl, layer, długość, wynik klasyfikacji i konflikt narracyjny.

Etap 6 musi już zbierać metryki potrzebne schedulerowi:

- drift per event;
- grupy eventów nachodzących czasowo;
- pozycję i layer;
- planowany oraz rzeczywisty początek/koniec;
- przyczynę przesunięcia.

Rozszerzony scheduler może później stać się osobnym podetapem pomiędzy tłumaczeniem
a finalnym zapisem spoken/displayed. Nie należy ukrywać go wewnątrz engine TTS.

### R38. Tempo

**USTALONE DLA PROFILI ENGINE / HITL DLA ENGINE-NATIVE RATE**

Trzeba rozdzielić dwa znaczenia:

- engine rate — TTS od razu mówi szybciej lub wolniej;
- post-process tempo — FFmpeg zmienia długość gotowego klipu/audio.

Każdy engine ma własne zapamiętane post-process tempo. Nie ma jednej wartości narzuconej
wszystkim głosom, ponieważ różne syntezatory mówią naturalnie w różnym tempie.
Niezależnie od wybranej wartości mechanizm jest wspólny:

1. engine generuje klip;
2. tempo profilu wybranego engine/voice jest stosowane do klipu przez FFmpeg `atempo`;
3. klip jest ponownie mierzony;
4. scheduler używa jego rzeczywistej długości;
5. dopiero potem klipy są układane na osi czasu.

Post-process tempa nie stosujemy do całego narrator WAV, ponieważ zmieniłoby również
długość ciszy i przesunęło wszystkie timingi.

Natywny engine rate jest osobną, zaawansowaną opcją barwy/prozodii. Domyślnie pozostaje
neutralny. AniShift nie może niejawnie zastosować jednocześnie engine rate i globalnego
post-process tempo; panel pokazuje obie wartości osobno, jeżeli dany engine obsługuje
rate.

Potwierdzony profil początkowy:

| Engine / voice | Post-process tempo | Voice mix offset |
|---|---:|---:|
| ElevenBytes `run6` / Dallin | `1.25` | `-2 dB` |
| SAPI / IVONA 2 Agnieszka | do ustalenia odsłuchem | `+2 dB` |

Pozostałe silniki startują od neutralnego `1.0 / 0 dB`, dopóki testy odsłuchowe nie
ustalą lepszego profilu.

Wartości `-2/+2 dB` są offsetem profilu głosu używanym wyłącznie podczas miksowania
z oryginalnym audio. Nie zmieniają samodzielnego narrator WAV.

### R39. Parametry narrator WAV

**REKOMENDACJA**

Wspólny format montażowy:

- PCM WAV;
- mono;
- 48 kHz domyślnie dla materiału wideo;
- 16-bit;
- `-rf64 auto` dla plików przekraczających limit RIFF.

Klipy mogą mieć format natywny engine. Normalizacja następuje przed montażem. Jeżeli
oryginalna ścieżka lub wybrany codec wymaga innego wspieranego sample rate, resamplowany
jest narrator/klip, a nie całe oryginalne audio w dół do 44,1 kHz. Rzeczywisty roboczy
i finalny sample rate są zapisywane w manifestach i raportowane przez `ffprobe`.

## 14. Tor audio

### R40. Zakres serwisu audio

**USTALONE**

Serwis audio:

- probuje format i długość przez `ffprobe`;
- normalizuje klipy;
- składa narrator WAV;
- stosuje jawne tempo i volume;
- miksuje narrator z oryginalnym audio;
- koduje format przekazywany do etapu 7;
- sprawdza return code i istnienie niepustego wyniku;
- wykonuje pełny decode-check wyniku przez FFmpeg, nie tylko odczyt nagłówka;
- sprawdza codec, sample rate, channel layout i tolerancję długości względem
  `max(original, narrator)`.

### R40a. Wydajność montażu

**REKOMENDACJA**

Typowy odcinek ma setki spoken events. Implementacja nie uruchamia bezwarunkowo osobnego
`ffprobe` i procesu FFmpeg dla każdego eventu, zwłaszcza gdy tempo profilu jest
neutralne i format klipu jest już znany z walidacji.

- concurrency subprocessów jest ograniczone;
- dekodowanie i składanie korzysta z bulk/in-process path tam, gdzie jest to bezpieczne;
- neutralne `atempo=1.0` nie powoduje zbędnego ponownego kodowania każdego klipu;
- benchmark na cache'owanych klipach typowego odcinka porównuje czas montażu ze starym
  ElevenBytes;
- montaż nie może dominować czasu przebiegu po zakończeniu requestów TTS.

### R41. Miks

**USTALONE DLA V1 / EKSPERYMENTY ODŁOŻONE**

Stary kod:

- najpierw stosował `pp_volume` do całego narrator WAV;
- następnie podbijał narrator o kolejne, zahardkodowane `+7 dB` podczas miksu;
- używa `amix=duration=longest`;
- nie duckuje oryginalnej ścieżki;
- koduje E-AC-3.

Dokładna kolejność starego `mm_avh`:

```text
synteza → voice profile pp_volume → narrator WAV
        → narrator mix gain +7 dB → amix normalize=true
```

Dlatego przy starym zachowaniu:

- Dallin `-2 dB` dawał `-2 + 7 = +5 dB` przed `amix`;
- Agnieszka `+2 dB` dawała `+2 + 7 = +9 dB` przed `amix`;
- rzeczywisty poziom wyjścia nadal był zmieniany przez `amix normalize=true`;
- gdy nie było oryginalnego audio, `_convert_to_eac3()` pomijało dodatkowe `+7 dB`
  i pozostawał tylko gain profilu głosu.

Nowy AniShift zachowuje równoważny gain finalnego miksu, ale porządkuje semantykę:
sam narrator pozostaje na `0 dB`, a oba składniki gainu są sumowane dopiero w filtrze
miksującym.

**USTALONE:** codec i profil końcowego audio są wybierane w `/settings`, a nie zaszyte
na stałe jako E-AC-3.

Profile do porównania:

| Format | Typ | Zastosowanie |
|---|---|---|
| MP3 | stratny | najbardziej rozpoznawalny plik, słabsza efektywność od Opus/AAC |
| WAV PCM | bezstratny, nieskompresowany | maksymalna prostota i zgodność, bardzo duży plik |
| E-AC-3 | stratny | dobry kompromis kompatybilności kina domowego i rozmiaru |
| Opus | stratny | lepsza efektywność przy małym bitrate, słabsza zgodność urządzeń |
| AAC-LC | stratny | szeroka zgodność, szczególnie MP4 |
| FLAC | bezstratny | brak kolejnej utraty jakości, ale znacznie większy plik |

E-AC-3 **nie jest bezstratny**. Jeżeli celem jest bezstratne zachowanie gotowego miksu,
właściwym profilem jest FLAC. FLAC nie odzyska jednak jakości utraconej wcześniej
w źródłowym audio lub MP3 z TTS; jedynie nie doda kolejnej stratnej generacji.

Pierwsza wersja zachowuje prosty, przewidywalny miks:

- oryginalne audio ma ustawienie wejściowe `0 dB`;
- samodzielny narrator WAV pozostaje na `0 dB`;
- podczas miksu narrator dostaje bazowe `narrator_mix_base_gain_db=+7 dB`;
- do bazowego gainu dochodzi `voice_mix_offset_db` profilu głosu;
- efektywny gain miksu to `+7 dB + offset`: Dallin `+5 dB`, Agnieszka `+9 dB`;
- `amix` używa `duration=longest`;
- `amix` jawnie używa `normalize=true` i `dropout_transition=2`;
- bazowy gain miksu, offset głosu i gain oryginału są rozdzielone w settings.

**Ważny wynik audytu:** stary filtr nie ustawiał `normalize`. FFmpeg `amix` ma domyślnie
`normalize=true` i `dropout_transition=2`, więc stary wynik nie zachowywał literalnie
ustawionych gainów; skala zmieniała się również po zakończeniu jednego wejścia.

V1 zachowuje wierny parytet brzmienia starego programu: jawne `normalize=true` i
`dropout_transition=2`. Literalne gainy z `normalize=false` wymagają osobnego
eksperymentu z limiterem/headroomem i nie są baseline etapu 6.

E-AC-3 pozostaje domyślnym profilem kompatybilnym, ale codec, bitrate i oba poziomy
volume są dostępne w ustawieniach. FLAC jest profilem jakościowym, Opus profilem małego
rozmiaru.

Nie próbujemy od razu rozwiązać wszystkich różnic głośności głosów ElevenLabs, Edge,
SAPI i pozostałych silników. Najpierw powstaje działający baseline, a kolejne tryby
są włączane i oceniane pojedynczo na różnorodnym materiale.

#### R41.1. Rejestr heurystyk głośności

| ID | Tryb | Zachowanie | Status |
|---|---|---|---|
| V0 | `fixed_gain` | Profil głosu + `7 dB`, `amix normalize=true` | Stage 6 v1, default |
| V1 | `narrator_normalize` | Ujednolica loudness aktywnej mowy lektora; oryginał bez zmian | eksperyment późniejszy |
| V2 | `local_narrator_gain` | Mierzy oryginał pod eventem i zmienia wyłącznie gain lektora | eksperyment późniejszy |
| V3 | `ducking` | Łagodnie ścisza oryginał tylko podczas mowy lektora | eksperyment późniejszy |
| V4 | `adaptive_mix` | Normalizuje lektora i stosuje delikatny ducking tylko tam, gdzie jest potrzebny | eksperyment późniejszy |
| V5 | `peak_guard` | Limiter/true-peak chroniący gotowy miks przed clippingiem | warstwa bezpieczeństwa do zbadania |

Tryby V1–V5 nie są częścią Definition of Done pierwszej implementacji. Mają zostać
testowane po kolei, a nie nałożone jednocześnie, ponieważ inaczej nie da się odsłuchowo
ustalić, która heurystyka poprawiła albo pogorszyła wynik.

#### R41.2. Wygładzanie przyszłych trybów

„Wygładzenie” nie oznacza osobnej heurystyki klasyfikującej napisy. Dotyczy wyłącznie
zmian gainu w czasie, aby audio nie pompowało i nie wykonywało nagłych skoków:

- lokalne pomiary z sąsiednich eventów są stabilizowane medianą kroczącą albo EMA;
- różnica gainu między sąsiednimi wypowiedziami ma limit;
- ducking ma attack, hold i release zamiast natychmiastowego przełączenia;
- wszystkie automatyczne korekty mają minimalny i maksymalny gain;
- gotowy miks pilnuje ustalonego true-peak ceiling.

Konkretnych okien, limitów i czasów przejść nie ustalamy bez testów odsłuchowych.
To są parametry eksperymentalne, nie ukryte stałe w kodzie.

#### R41.3. Długość wyniku i układ kanałów

**USTALONE**

Stary kod ustawiał jako pierwsze wejście ten plik, który był dłuższy. Intencją nie była
zmiana kanałów, lecz ochrona końcówki lektora: jeżeli narrator kończy się po audio albo
wideo anime, ma zostać przeczytany do końca.

Nowy tor zapisuje tę semantykę bez zależności od kolejności wejść:

- długość mixed audio to `max(original_audio_duration, narrator_duration)`;
- FFmpeg używa `amix=duration=longest`;
- narrator nigdy nie jest obcinany do długości oryginalnego audio;
- etap 7 nie używa `-shortest`;
- jeżeli audio jest dłuższe od wideo, strumień wideo kończy się naturalnie, a audio
  trwa do końca;
- nie przedłużamy ani nie kodujemy ponownie obrazu tylko po to, aby sztucznie dopisać
  ostatnią klatkę.

Wyświetlanie ostatniej klatki po zakończeniu strumienia wideo jest zachowaniem playera,
nie częścią pliku audio. AniShift zachowuje dłuższe audio; nie gwarantuje identycznego
obrazu końcowego we wszystkich odtwarzaczach.

Priorytetem jest zachowanie przestrzenności oraz układu kanałów oryginalnego anime.
Narrator pozostaje głosem centralnym; nie jest sztucznie rozrzucany po kanałach
surround. Kolejność wejść nie może decydować o layout:

- oryginał mono → wynik mono;
- oryginał stereo → narrator trafia do lewego i prawego kanału przez jawną macierz
  equal-power, przez co jest odbierany pośrodku bez niekontrolowanego podbicia;
- oryginał 5.1/7.1 → wynik zachowuje układ, jeżeli wybrany codec realnie go obsługuje,
  a narrator trafia do fizycznego kanału centralnego;
- brak oryginalnego audio → wynik zachowuje roboczy format mono narratora.

Nie każdy profil może zachować każdy layout:

- MP3 obsługuje wynik mono/stereo; źródło surround wymaga jawnego downmixu do stereo;
- lokalny encoder E-AC-3 obsługuje maksymalnie 5.1; źródło 7.1 wymaga jawnego downmixu
  do 5.1;
- pozostałe profile zachowują layout tylko po potwierdzeniu capabilities konkretnego
  encodera i testu dekodowania.

Downmix następuje wyłącznie wtedy, gdy wybrany codec nie obsługuje źródłowego layoutu.
Zawsze używa jawnej, standardowej macierzy, emituje warning i trafia do raportu. Nie
polegamy na automatycznym remapowaniu FFmpeg ani na kolejności wejść. Mapowanie wymaga
fixture mono, stereo, 5.1 i 7.1 oraz kontroli `channel_layout` przez `ffprobe`.

### R41a. Codec a format pliku

**USTALONE**

Panel pokazuje użytkownikowi popularną nazwę formatu, a serwis dobiera prawidłowy codec,
kontener i rozszerzenie:

| Wybór w settings | Codec | Wynik etapu 6 |
|---|---|---|
| MP3 | MP3 | `.mp3` |
| WAV | PCM S16LE | `.wav` |
| E-AC-3 | E-AC-3 | `.eac3` |
| Opus | Opus | `.opus` |
| FLAC | FLAC | `.flac` |
| AAC | AAC-LC | `.m4a` |

Nie używamy rozszerzenia `.aac` jako domyślnego produktu, ponieważ surowy AAC ma mniej
metadanych i słabszą ergonomię niż kontener M4A. Etap 7 może bez ponownego kodowania
wyciągnąć strumień AAC z M4A podczas muxowania, jeżeli kontener docelowy na to pozwala.

Bitrate jest widoczny tylko dla formatów stratnych. WAV i FLAC nie pokazują fałszywej
opcji bitrate; mają odpowiednio parametry PCM oraz poziom kompresji FLAC, który zmienia
czas i rozmiar, ale nie jakość.

### R42. Brak oryginalnego audio

**USTALONE**

Jeżeli nie wybrano oryginalnej ścieżki:

- narrator WAV nadal powstaje;
- mixed audio jest po prostu przekodowanym narratorem;
- narrator pozostaje na `0 dB`;
- nie stosujemy ani bazowego `+7 dB`, ani `voice_mix_offset_db`, ponieważ nie istnieje
  drugie źródło, względem którego trzeba wyrównywać poziom;
- pipeline pokazuje warning, nie błąd.

### R43. Błąd FFmpeg

**USTALONE**

Komunikat zawiera:

- operację;
- return code;
- bezpieczny fragment stderr;
- ścieżkę wejścia/wyjścia;
- sugestię naprawy.

Nie pokazuje sekretów ani pełnego dumpu binarnego. Nieudany wynik tymczasowy nie zastępuje
poprzedniego poprawnego pliku.

## 15. Artefakty i nazwy

### R44. Produkty etapu 6

**USTALONE**

Artefakty:

```text
workspace/tmp/<file-id>/tts/clips/       # klipy i resume
workspace/tmp/<file-id>/tts/narrator.wav # sam lektor
workspace/<stem>.<codec>                 # jedyne gotowe audio dla etapu 7
```

AniShift tworzy trzy różne produkty napisów, więc sufiksy `spoken` i `displayed` mają
znaczenie. Etap 6 tworzy natomiast tylko jeden gotowy sidecar audio. Sufiksy `lector`,
`narration`, `voiceover` i `dub` nie rozróżniałyby żadnych równoległych produktów.

Używamy najprostszej nazwy `{stem}.<codec>`, na przykład
`Episode 03.eac3`. Jest krótsza, zgodna ze starym pipeline i działa z trybem MPV
`audio-file-auto=exact`. Język i tytuł ścieżki zostaną zapisane jako metadane podczas
muxowania w etapie 7.

Zapis odbywa się atomowo. Istniejący poprawny sidecar nie jest zastępowany, dopóki nowy
plik nie przejdzie walidacji.

Nazwa sama nie dowodzi, że plik należy do AniShift. Manifest outputu zapisuje dokładną
ścieżkę, fingerprint i hash ostatniego sidecaru utworzonego przez aplikację. Nie wolno
nadpisać obcego `{stem}.<codec>` bez jawnej decyzji usera.

Zmiana codeca pozostawia poprzedni sidecar. Przykładowo po wygenerowaniu `Anime.eac3`,
a następnie `Anime.mp3`, oba pliki pozostają obok źródła. AniShift nie usuwa starych
formatów ani plików wyłącznie po pasującym stemie.

### R44a. Automatyczne ładowanie przez MPV

**USTALONE**

Automatyczne użycie sidecaru nadal zależy od konfiguracji MPV:

- domyślne `audio-file-auto=no` nie ładuje żadnego zewnętrznego audio;
- `audio-file-auto=exact` może znaleźć rekomendowane `{stem}.<codec>`;
- `audio-file-auto=fuzzy` może znaleźć również warianty z dodatkowymi sufiksami;
- załadowanie zewnętrznej ścieżki nie musi automatycznie wybrać jej zamiast wewnętrznej.

Główna ścieżka użytkowa pozostaje taka:

- etap 6 tworzy jeden sidecar audio;
- etap 7 muxuje go do MKV z językiem polskim, nazwą ścieżki i flagą default;
- wariant luźnych plików dokumentuje `audio-file-auto=exact` albo korzysta z planowanej
  integracji MPV.

Nie tworzymy drugiej kopii tego samego audio pod nazwą z sufiksem.

### R45. narrator WAV

**USTALONE**

Narrator WAV jest plikiem roboczym w `tmp`. Może zostać zachowany po błędzie albo w trybie
debug, ale nie jest drugim domyślnym produktem obok MKV. Użytkowym produktem etapu 6 jest
mixed audio.

## 16. Ustawienia i widoczność

### R46. Ustawienia wspólne

**REKOMENDACJA**

- engine;
- voice;
- tempo;
- narrator volume;
- original audio volume;
- output codec/profile;
- codec-specific bitrate, gdy format jest stratny;
- concurrency wybranego engine;
- retry limit;
- timeline policy;
- zachowanie resume/debug artifacts.

Wybór strategii miksu pojawi się dopiero wtedy, gdy któryś z trybów V1–V5 zostanie
zaimplementowany i potwierdzony odsłuchowo. W v1 jedyną strategią jest `fixed_gain`.

Ustawienia nie mogą mieszać różnych jednostek i warstw:

- post-process `tempo` — osobno zapamiętywany dla każdego engine/voice;
- engine-native rate/pitch/volume — osobne opcje per engine;
- `voice_mix_offset_db` — korekta konkretnego głosu używana tylko podczas miksu;
- `narrator_mix_base_gain_db` — bazowe `+7 dB` przy łączeniu z oryginałem;
- `original_gain_db` — gain oryginału w miksie, domyślnie `0.0 dB`;
- output codec/bitrate/channel policy — ustawienia finalnego sidecaru.

Obecne placeholdery Stage 2 `tempo=1.85` i `volume=60` nie są profilem żadnego silnika
i nie są migrowane. `volume: 0–100` nie może zostać potraktowane jako dB. Nowy schema
tworzy jawne profile z własnymi jednostkami i ma wersjonowany test configu.

Ustawienia TTS są przechowywane per głos, pod stabilnym kluczem `engine_id + voice_id`.
Po przełączeniu głosu panel ładuje jego ostatnie tempo, `voice_mix_offset_db` i wspierane
parametry natywne; powrót do poprzedniego głosu przywraca jego wartości. Nowy custom
voice dostaje neutralny profil, dopóki user go nie zmieni. Zmiana modelu/endpointu może
mieć osobny override tylko wtedy, gdy empirycznie wymaga innych parametrów.

### R47. Ustawienia per engine

**REKOMENDACJA**

Panel pokazuje tylko opcje sensowne dla wybranego engine:

- ElevenBytes: wariant `run6`/`run7`, voice i concurrency; parametry głosu są widoczne
  wyłącznie dla eksperymentalnego `run7`;
- ElevenLabs: model, voice, voice settings, API output format, concurrency;
- Edge: voice, rate, pitch, volume, concurrency;
- SAPI: voice, architektura workera, rate i volume.

### R48. Silnik niedostępny

**USTALONE**

Każdy engine pozostaje widoczny z powodem:

- `missing key`;
- `missing voice`;
- `missing binary`;
- `offline`;
- `service unavailable`.

Przy `missing key` panel pozwala wprowadzić klucz:

- pole jest maskowane;
- wartość trafia do właściwej zmiennej w `.env`, nie do `config/settings.json`;
- zapis jest atomowy;
- klucz nie jest ponownie wyświetlany;
- logi i błędy pokazują tylko `configured` / `missing`;
- po zapisie availability jest odświeżane.

Dotyczy to oficjalnego ElevenLabs. ElevenBytes nie używa klucza użytkownika.

Aktualizacja `.env` zachowuje wszystkie niezwiązane linie, komentarze, newline i
kodowanie. Po atomic replace aplikacja jawnie przebudowuje runtime Settings zgodnie
z ustaloną precedence; nie polega wyłącznie na ponownym `load_dotenv(override=False)`.
Dodanie, zmiana i usunięcie klucza oraz process-env override mają osobne testy.

### R49. Głosy dynamiczne i custom ID

**REKOMENDACJA**

- Edge i ElevenLabs odświeżają listę głosów.
- SAPI czyta głosy osobno z hosta x64 i x86.
- Panel ma rozsądne defaulty.
- Ustawienia oficjalnego ElevenLabs mogą przechować custom voice ID, którego panel
  jeszcze nie zna.
- Zmiana engine automatycznie wybiera kompatybilny default, jeżeli bieżący voice nie pasuje.

Wbudowany katalog ElevenBytes zawiera tylko `Dallin`. Panel lub odpowiadająca mu komenda
pozwala dodać własny wpis:

- alias;
- etykietę wyświetlaną;
- voice ID.

Custom lista ElevenBytes jest trwałą preferencją w `config/settings.json`, nie sekretem
i nie stanem `workspace`. Po ponownym uruchomieniu własne głosy nadal są dostępne na
liście. Można je edytować i usuwać bez zmiany katalogu wbudowanego. Alias musi być
unikalny, voice ID nie może być pusty, a usunięcie aktualnie wybranego głosu przełącza
ustawienie na `Dallin`.

Aliasy są porównywane case-insensitive. Wbudowanego aliasu `dallin` nie można nadpisać
ani usunąć. Zapis custom listy jest atomowy, a synthesis fingerprint zawiera faktyczny
resolved voice ID, nie tylko alias.

## 17. Progress i raport

### R50. Jeden wiersz na plik

**USTALONE**

Jeden plik zachowuje jeden wiersz:

```text
extracting → translating / already Polish → synthesizing → audio → done
```

Nie tworzymy nowych wierszy TTS pod wierszami ekstrakcji.

### R51. Progress TTS

**REKOMENDACJA**

TTS ma rzeczywisty procent:

```text
poprawne eventy / wszystkie eventy
```

Resume hits liczą się od razu jako ukończone. Retry nie zwiększa total. Wszystkie silniki,
w tym SAPI, raportują ukończenie przez wspólny kontrakt per event, więc procent nie
jest udawany ani wyliczany z upływu czasu.

### R52. Widoczna faza

**USTALONE**

Wiersz pokazuje co najmniej:

- skróconą nazwę pliku;
- aktualną fazę;
- engine/voice w zwartej formie;
- procent lub spinner;
- elapsed time.

### R53. Podsumowanie

**REKOMENDACJA**

Po przebiegu:

- files done / failed / not processed / cancelled;
- engine i voice;
- spoken events;
- synthesized / resume hits / skipped / failed;
- requests / retries;
- czas TTS i audio;
- maksymalny oraz łączny drift;
- ścieżka wyniku;
- koszt i znaki, jeżeli API je raportuje;
- ostrzeżenie o częściowym wyniku.

## 18. Odporność na błędy

### R54. Izolacja plików

**USTALONE**

- Ukończone pliki nie są cofane przez późniejszy błąd.
- Błąd jednego pliku nie usuwa klipów innego.
- Pipeline może ukończyć poprawne pliki nawet po błędzie pozostałych.
- Provider-wide failure nie powoduje lawiny identycznych requestów z kolejki.

### R55. Recovery command

**USTALONE**

Po błędzie provider-wide CLI powinno pozwolić:

- ponowić tym samym engine i wykorzystać poprawny resume state;
- wejść do `/settings` i zmienić engine, wariant, voice albo key;
- zakończyć na gotowych plikach;
- oznaczyć resztę jako not processed.

Dokładna składnia komend jest drugorzędna przed UI.

Ukończone pliki pozostają nietknięte. Zmiana engine, wariantu albo głosu nie może
połączyć różnych głosów w jednym nieukończonym odcinku:

- cały nieukończony odcinek jest generowany od początku nowym fingerprintem;
- klipy poprzedniego fingerprintu pozostają osobnym resume state;
- nie są używane w nowym narrator WAV;
- ponowienie bez zmiany fingerprintu wykorzystuje wszystkie poprawne klipy.

`Ctrl+C` pozostaje niezależną drogą anulowania i ma działać po jednym naciśnięciu.

### R55a. Zgodność z recovery tłumaczenia

**AUDYT STANU / USTALONE WYMAGANIE**

Obecny LLM pipeline już:

- ma współdzielony circuit breaker;
- zatrzymuje nowe requesty po provider-wide failure;
- pozwala aktywnym operacjom bezpiecznie się zakończyć;
- zachowuje ukończone pliki;
- po `settings` buduje runtime z aktualnej konfiguracji;
- daje pierwszeństwo plikom, które zwróciły błąd;
- po `finish` oznacza niewysłane pliki jako `not_processed`;
- przy zmianie providera/modelu tłumaczy cały nieukończony plik ponownie.

Aktualny prompt LLM pokazuje tylko `settings` i `finish`. Ponowienie tego samego providera
jest obecnie realizowane przez powrót z settings bez zmiany konfiguracji. Docelowa
warstwa recovery może pokazać osobne `retry`, ale musi zachować tę samą semantykę.

Pełny mechanizm kolejki i interaktywnego recovery działa obecnie tylko dla LLM.
Google i DeepL mają własne ograniczone retry, ale nie przechodzą przez ten sam
provider-wide circuit breaker i prompt. Wymaganie docelowe dla tłumaczenia:

- wszystkie silniki zatrzymują niewysłaną pracę po awarii całego dostawcy;
- ukończone pliki pozostają poprawne;
- ponowienie tym samym fingerprintem nie powtarza gotowej pracy, jeżeli dany engine
  posiada bezpieczny resume state;
- zmiana engine tłumaczy cały nieukończony odcinek ponownie, aby nie mieszać wyników
  różnych translatorów wewnątrz jednego pliku;
- recovery oferuje ponowienie, settings oraz zakończenie na gotowych plikach.

Implementacja nie powinna tworzyć dwóch rozbieżnych kontrolerów interakcji dla LLM i TTS.
Wspólna semantyka może być współdzielona, natomiast stan i fingerprint pozostają
domenowe.

**Zakres etapu 6:** obejmuje wspólny kontrakt interakcji i użycie go przez TTS oraz
utrzymanie obecnego recovery LLM. Przebudowa Google/DeepL do pełnego provider-wide
circuit breakera jest osobnym zadaniem, chyba że okaże się niezbędna do wydzielenia
wspólnego kontrolera; nie rozszerzamy etapu 6 po cichu o refaktor wszystkich translatorów.

### R56. Partial audio

**USTALONE DLA V1**

Niepełne mixed audio nie powstaje jako sidecar i nie może otrzymać finalnej nazwy
`{stem}.<codec>`.

- poprawne klipy i manifest zostają do resume;
- roboczy narrator WAV może zostać zachowany diagnostycznie w `tmp`;
- ukończone odcinki normalnie tworzą swój finalny sidecar;
- nieukończony odcinek nie tworzy finalnego audio;
- success wymaga wszystkich wymaganych spoken events.

Partial preview może kiedyś powstać jako osobna, jawnie oznaczona funkcja debug, ale nie
jest częścią etapu 6 v1.

## 19. Bezpieczeństwo i prywatność

### R57. Sekrety

**USTALONE**

- API keys są ładowane przez Settings/env.
- Pola sekretów używają typu/maskowania, które wyklucza ich zwykły `repr`.
- Nie trafiają do repr, logów, raportów, nazw plików ani wyjątków.
- Request URL z query string nie jest logowany, jeżeli zawiera token.
- Testy używają placeholderów.

### R58. Tekst wysyłany do usług

**REKOMENDACJA**

Panel/README powinien jasno oznaczać:

- Edge, ElevenBytes i ElevenLabs wysyłają tekst spoken do usługi zewnętrznej;
- SAPI pozostaje lokalne;
- resume state zawiera tekst/fingerprint i audio lokalnie.

### R59. Subprocess

**USTALONE**

- Argumenty są przekazywane jako lista, nie string shell.
- Request SAPI trafia do workera przez ograniczony protokół danych; tekst nie jest
  interpolowany do polecenia PowerShell.
- Ścieżki są walidowane wewnątrz workspace albo external.
- Timeout jest obowiązkowy.
- Return code jest sprawdzany.

## 20. Testy

### R60. Unit

**USTALONE**

Testy bez sieci obejmują:

- registry i lazy imports;
- config validation;
- capabilities;
- text cleaning z polskimi znakami;
- normalizację `SpokenLine` i `TranslatedLine`;
- zachowanie kolejności;
- retry classification;
- cancellation propagation;
- fingerprint;
- atomic write;
- resume hit/miss;
- uszkodzony cache;
- timeline silence, overlap i drift;
- format audio result;
- FFmpeg command construction;
- nazewnictwo artefaktów;
- brak sekretów w błędach;
- progress i raport.
- dokładne liczenie jednej próby + trzech retry bez mnożenia warstw;
- late-result commit gate po anulowaniu blokującego workera;
- globalny limit engine między kilkoma plikami i priorytet retry;
- deterministyczny `file-id`, Unicode i długie ścieżki Windows;
- concurrent manifest completions bez lost update oraz orphan clip recovery;
- warstwową invalidation: tempo/gain/codec bez ponownego requestu TTS;
- empty/punctuation/single-character/overlong event;
- stable sort `(start_ms, source_index)`;
- migrację ustawień oraz brak wycieku sekretu przez `repr`;
- ownership i kolizję istniejącego sidecaru.

### R61. Integration

**USTALONE**

- krótkie fixture WAV/MP3 przez prawdziwy FFmpeg;
- montaż kilku klipów na osi czasu;
- miks z oryginalnym audio;
- pełne dekodowanie wyniku przez FFmpeg;
- mono, stereo, 5.1 i 7.1 z oczekiwanym preserve/downmix;
- źródło, w którym narrator kończy się po oryginalnym audio;
- RF64 albo kontrolowany test ścieżki przekraczającej limit RIFF 4 GiB;
- przerwany subprocess;
- SAPI x64 z Zosią i SAPI x86 z Agnieszką, jeżeli głosy są dostępne;
- SAPI bez głosu, z pustym WAV-em, zerwanym IPC oraz workerem zablokowanym do timeoutu;
- zwykły `doctor`, który listuje głosy bez uruchamiania syntezy, oraz jawny `doctor --live`;
- unavailable paths poza Windows lub bez zasobu.

### R62. Network

**REKOMENDACJA**

Osobno oznaczone testy `network`:

- Edge Marek i Zofia;
- ElevenBytes `run6` jako wymagany smoke test;
- ElevenBytes `run7` jako test eksperymentalny; ucięta końcówka jest oceniana manualnie,
  ponieważ sama dekodowalność nie dowodzi obecności ostatniego słowa;
- ElevenLabs tylko przy obecnym kluczu;
- odpowiedź pusta/uszkodzona;
- kontrolowany retry na testowym mock serverze;
- niewielki test concurrency zamiast bombardowania usługi.

### R63. Real episode

**USTALONE**

Co najmniej dwa realne odcinki przechodzą:

```text
MKV → spoken PL → clips → narrator WAV → mixed audio
```

Jeden używa już polskich napisów, drugi tłumaczenia. Weryfikacja:

- odsłuch początku, środka i końca;
- polskie znaki i liczby;
- szybkie dialogi;
- nakładające się eventy;
- cisza;
- brak uciętych wypowiedzi;
- długość ścieżki;
- poprawny restart po przerwaniu;
- brak powtórnych płatnych requestów po resume.
- pełny decode-check bez błędów;
- oczekiwany codec, sample rate i channel layout;
- długość wyniku w ustalonej tolerancji względem `max(original, narrator)`;
- wznowienie po jednym `Ctrl+C` bez spóźnionego zapisu starego workera.

Fixture/odcinki referencyjne, tolerancja czasu i checklisty odsłuchu muszą zostać wpisane
przed rozpoczęciem końcowej weryfikacji, aby „brzmi poprawnie” nie było ruchomym celem.

### R64. Quality gates

**USTALONE**

Przed każdym commitem:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

Live tests nie mogą blokować standardowego offline `pytest`.

## 21. Definition of Done

Etap 6 jest ukończony dopiero, gdy:

- [ ] cztery engine IDs istnieją w lazy registry;
- [ ] każdy engine ma jawny status dostępności i powód niedostępności;
- [ ] Edge działa na realnym polskim tekście;
- [ ] automatyczny patch Edge daje rzeczywiste 24 kHz / 96 kb/s i spójne offsety;
- [ ] SAPI x64 działa na zainstalowanej Zosi, a SAPI x86 na zainstalowanej Agnieszce,
  bez blokowania jednego `Ctrl+C`;
- [ ] `unavailable` dla profilu SAPI jest poprawnym wynikiem tylko wtedy, gdy faktycznie
  brakuje platformy, właściwej architektury hosta albo głosu;
- [ ] ElevenBytes `run6` przechodzi realny odcinek bez uciętych końcówek;
- [ ] ElevenBytes `run7` jest dostępny jako `experimental`, a jego wynik i awarie nie
  zmieniają defaultu `run6`;
- [ ] ElevenLabs działa po podaniu klucza, a bez klucza pokazuje `missing key`;
- [ ] polskie i tłumaczone źródło używają tego samego wejścia TTS;
- [ ] synteza nie parsuje ponownie pliku napisów bez uzasadnienia engine-specific;
- [ ] retry nie powtarza poprawnych requestów;
- [ ] dokładna liczba prób nie jest mnożona przez engine/transport;
- [ ] resume przeżywa restart pipeline i zmianę fazy ekstrakcji;
- [ ] fingerprint odrzuca nieaktualne klipy;
- [ ] zmiana tempa, gainu lub codeca nie powtarza requestów syntezy;
- [ ] współbieżne wpisy manifestu nie gubią ukończonych eventów;
- [ ] jedno `Ctrl+C` anuluje cały przebieg;
- [ ] spóźniony worker po anulowaniu nie zapisuje wyniku ani progressu;
- [ ] kolejność plików pozostaje `natsorted`;
- [ ] narrator WAV ma poprawną oś czasu;
- [ ] drift jest raportowany;
- [ ] mixed audio przechodzi `ffprobe` i pełny decode-check FFmpeg;
- [ ] output codec jest wybierany w ustawieniach i nie jest zaszyty jako E-AC-3;
- [ ] każdy wspierany profil codec ma test integracyjny;
- [ ] mono/stereo/surround nie polega na niejawnym remapowaniu FFmpeg;
- [ ] zero spoken events kończy się bez mylącego sidecaru;
- [ ] długi event nie jest obcinany do limitu providera;
- [ ] RF64 lub równoważna ścieżka >4 GiB jest pokryta testem;
- [ ] montaż cache'owanego odcinka nie regresuje rażąco względem starego toru;
- [ ] jeden wiersz progress przechodzi przez wszystkie fazy pliku;
- [ ] błąd jednego pliku nie niszczy poprawnych wyników innych;
- [ ] nieukończony odcinek nie tworzy finalnego sidecaru audio;
- [ ] realny odcinek przechodzi odsłuch;
- [ ] pliki serwisów pozostają modułowe; około 300 linii kodu jest miękkim sygnałem do
  sprawdzenia odpowiedzialności, nie limitem ani bramką. Docstringi, komentarze i spójna
  logika nie są powodem do sztucznego dzielenia pliku;
- [ ] po anulowaniu nie pozostają taski, workery ani subprocessy należące do przebiegu;
- [ ] pełne quality gates są zielone.

## 22. Decyzje HITL — iteracja 1

Najpierw trzeba rozstrzygnąć fundamenty. Szczegóły głosów i bitrate można ustalić
w następnej iteracji.

### D1. Kiedy uruchamiać TTS?

- A: po ukończeniu tłumaczeń wszystkich plików;
- B: natychmiast po gotowym spoken danego pliku.

**DECYZJA USERA: B.**

### D2. Co robić, gdy klip jest dłuższy niż okno napisu?

- A: nie ucinać, przesuwać kolejne klipy i raportować drift;
- B: automatycznie przyspieszać do okna;
- C: pozwolić na overlap;
- D: ucinać.

**DECYZJA DLA V1: A; D odrzucone.**

Duży drift pozostaje otwartym problemem narration schedulera opisanym w R37. Scheduler
może później przenosić konfliktujące eventy ze spoken do displayed i ponownie zapisywać
końcowe produkty napisów.

### D3. Kiedy sprzątać resume state?

- A: po narrator WAV;
- B: po mixed audio;
- C: po zweryfikowanym wyniku etapu 7.

**DECYZJA USERA: C.**

Resume state to stan wznowienia TTS: poprawne klipy i manifest pozwalające kontynuować
po crashu bez ponownego wysyłania tych samych eventów.

### D4. Czy deduplikować identyczne audio?

- A: nie;
- B: tak, wyłącznie po pełnym fingerprint engine + model + voice + settings + text.

**DECYZJA USERA: A.** Resume tego samego eventu pozostaje niezależnym mechanizmem.

### D5. Co ma być produktem etapu 6?

- A: tylko narrator WAV;
- B: narrator WAV i mixed audio;
- C: tylko mixed audio, narrator WAV roboczy.

**DECYZJA USERA: C, ale format mixed audio jest wybierany w `/settings`.**

Dostępne wybory: MP3, WAV, E-AC-3, Opus, FLAC i AAC. E-AC-3 pozostaje kandydatem
domyślnym, nie jedynym formatem i nie jest bezstratny.

### D6. Nazwa mixed audio

- A: `{stem}.<codec>`;
- B: `{stem}.voiceover.pl.<codec>`;
- C: inny sufiks opisowy.

**DECYZJA USERA: A.** Powstaje tylko jeden gotowy plik audio, więc dodatkowy sufiks
niczego nie rozróżnia. Wariant A jest najkrótszy i działa z MPV `audio-file-auto=exact`.
Konfiguracja usera już łapie sidecary, więc nazewnictwo nie jest blockerem odtwarzania.

### D7. Widoczność niedostępnych engine

- A: ukryte;
- B: widoczne z `missing key`, `missing voice`, `missing binary` albo `offline`.

**DECYZJA USERA: B.** Przy `missing key` settings umożliwia bezpieczne podanie klucza.

### D8. Konfiguracja ElevenBytes

**DECYZJA USERA:** ElevenBytes nie ma konfiguracji tokenu/env. Kontrakt strony jest
częścią kodu; jeżeli przestanie działać, engine staje się unavailable.

### D9. Lokalny SAPI

**DECYZJA USERA:** jeden engine `sapi` obsługuje Zosię przez trwały worker x64 oraz
Agnieszkę przez trwały worker x86. Oba profile korzystają ze wspólnego kontraktu
per-event, resume, progressu, anulowania, tempa i timeline.

Balcon został odrzucony po spike'u: dla obu głosów wygenerował pliki bitowo identyczne
z bezpośrednim SAPI, ale proces-per-event był wyraźnie wolniejszy. AniShift nie pobiera
Balcona i nie utrzymuje osobnego adaptera ani engine id dla tej nakładki.

### D10. Miks audio

- A: parytet starego kodu — zahardkodowane `+7 dB`, `amix duration=longest`, E-AC-3;
- B: od razu nowy profil z duckingiem;
- C: sam narrator, miks dopiero w etapie 7.

**DECYZJA DLA V1:** prosty, stały miks bez heurystyki. Poziom lektora ma dwie jawne
warstwy stosowane wyłącznie podczas miksowania: bazowe `+7 dB` oraz offset konkretnego
głosu `-2/+2 dB`. Sam narrator pozostaje na `0 dB`. Normalizacja `amix` jest ustalona
w D18.

Kolejne kandydaty zapisane do testów to: normalizacja samego lektora, lokalne dopasowanie
jego gainu do oryginału, ducking oryginału podczas wypowiedzi i wariant hybrydowy.
Pełna tabela oraz zasady wygładzania znajdują się w R41.1–R41.2.

### D11. Domyślny format mixed audio

**DECYZJA USERA:** E-AC-3 jako default. MP3, WAV, Opus, FLAC i AAC pozostają dostępne
w settings.

### D12. Domyślny engine i wariant ElevenBytes

**DECYZJA USERA:** domyślnym engine jest ElevenBytes, a jego domyślnym wariantem `run6`,
czyli `eleven_multilingual_v2`.

`run6` jest stabilnym baseline i korzysta z domyślnych parametrów głosu proxy. `run7`
z Eleven v3 pozostaje opcją eksperymentalną: zdarzają mu się lekko ucięte końcówki,
a wpływ przekazywanych parametrów głosu nie jest potwierdzony. AniShift nie przełącza
automatycznie defaultu na `run7` ani inny engine.

### D13. Domyślny głos ElevenBytes

**DECYZJA USERA:** jedynym wbudowanym i domyślnym głosem jest `Dallin — Storyteller`
(`alFofuDn3cOwyoz1i44T`).

Nie dodajemy obecnie innych odziedziczonych aliasów. Mechanizm custom voices pozostaje:
user może później dopisać sprawdzony głos na stałe, a AniShift zachowa go w liście
ElevenBytes.

### D14. Długość mixed audio

**DECYZJA USERA:** nie wolno ucinać końcówki lektora. Mixed audio trwa tyle, ile dłuższe
z wejść: oryginalne audio albo narrator. Etap 7 nie używa `-shortest`; jeżeli narrator
wychodzi poza wideo, audio może grać po zakończeniu strumienia obrazu.

Stare przestawianie wejść według długości służyło właśnie temu celowi. Nowa implementacja
zachowuje zachowanie przez jawną semantykę `duration=longest`, a nie przez kolejność
wejść.

### D15. Recovery po zmianie TTS

**DECYZJA USERA:** po zmianie engine, wariantu albo głosu cały nieukończony odcinek jest
generowany ponownie. Nie wolno mieszać dwóch głosów w jednym odcinku. Ukończone odcinki
pozostają nietknięte, a ponowienie identycznego fingerprintu korzysta z resume.

Ta sama semantyka obowiązuje tłumaczenie: zmiana translatora/providera/modelu ponownie
tłumaczy cały nieukończony plik.

### D16. Liczba retry

**DECYZJA USERA:** polityka podobna do obecnego tłumaczenia. Domyślnie trzy ponowienia
po pierwszej próbie, tylko dla błędów przejściowych. Po wyczerpaniu limitu circuit
breaker zatrzymuje nowe requesty i uruchamia recovery. Limit pozostaje konfigurowalny.

### D17. Partial audio

**DECYZJA USERA:** brak automatycznego partial audio w v1. Nieukończony odcinek zachowuje
klipy i manifest do resume, ale nie tworzy finalnego `{stem}.<codec>`. Ukończone odcinki
pozostają normalnymi wynikami.

### D18. Normalizacja `amix`

Audyt wykazał, że stary program używał domyślnego `amix normalize=true`. Oznacza to, że
gainy wejściowe nie były literalnymi poziomami wyniku.

**DECYZJA USERA:** zachować stare brzmienie — jawne `normalize=true` oraz
`dropout_transition=2`. Wariant `normalize=false` z limiterem/headroomem może być
osobnym późniejszym eksperymentem.

### D19. Ustawienia per engine/voice

**DECYZJA USERA:** każdy engine ma własne tempo i ustawienia głośności. Obecne
`tempo=1.85` i `volume=60` są placeholderami Stage 2, nie ustawieniami do migracji.

- ElevenBytes `run6` / Dallin: post-process `tempo=1.25`, `voice_mix_offset_db=-2`;
- SAPI / IVONA 2 Agnieszka: `voice_mix_offset_db=+2`, tempo do odsłuchowego ustalenia;
- pozostałe profile zaczynają neutralnie i są poprawiane po testach.

Engine-native rate/volume pozostają oddzielone od wspólnego post-processingu FFmpeg,
ponieważ ich skale i wpływ na brzmienie różnią się między providerami.

Każdy głos zachowuje własny profil w `config/settings.json`. Przełączenie głosu nie
nadpisuje ustawień poprzedniego, a ponowny wybór przywraca ostatnie wartości tego głosu.

### D20. Stary sidecar po zmianie codeca

**DECYZJA USERA:** zachować wszystkie wcześniejsze sidecary. Zmiana codeca tworzy nowy
plik z innym rozszerzeniem i nie usuwa poprzedniego. Nie pokazujemy obowiązkowego promptu
cleanup; user może usunąć niepotrzebny format ręcznie.

### D21. Dodatkowe `+7 dB` podczas miksu

Audyt kodu `mm_avh` potwierdził dwie kolejne operacje:

1. `pp_volume` profilu głosu na narrator WAV;
2. dodatkowe `volume=7dB` przed `amix`.

Dlatego Dallin `-2 dB` oznaczał w starym miksie `+5 dB` przed normalizacją, a Agnieszka
`+2 dB` oznaczała `+9 dB`.

**DECYZJA USERA:** zachować obie warstwy i stare
`narrator_mix_base_gain_db=+7 dB`. Nowa implementacja sumuje offset Dallina `-2 dB`
albo Agnieszki `+2 dB` z bazą dopiero w filtrze miksu. Samodzielny narrator pozostaje
na `0 dB`; nie dziedziczy korekty potrzebnej tylko względem audio anime.

### D22. Przestrzenność i kanały

**DECYZJA USERA:** AniShift ma technicznie dobrać mapowanie tak, aby zachować
przestrzenność i możliwie wiernie utrzymać układ kanałów oryginalnego anime.

- narrator pozostaje centralny;
- mono/stereo/surround używają jawnych standardowych macierzy;
- layout źródła jest zachowany, jeżeli wybrany codec go obsługuje;
- downmix następuje tylko z powodu limitu codeca i jest raportowany;
- E-AC-3 zachowuje maksymalnie 5.1, MP3 maksymalnie stereo.

## 23. Pytania do następnej iteracji

Po fundamentalnych decyzjach doprecyzujemy:

- implementację i test jawnych macierzy `pan` dla mono/stereo/5.1/7.1;
- domyślne concurrency per engine po małym benchmarku;
- ElevenLabs default model;
- konkretne voice settings;
- domyślny bitrate/profile poszczególnych formatów;
- czy eksponować zaawansowany engine-native rate obok per-engine FFmpeg `atempo`;
- cleanup po etapie 7;
- testowy odcinek referencyjny i kryteria odsłuchu;
- timeout, zabicie i odtworzenie bezpośredniego workera SAPI COM x64/x86;
- wielokrotne wywołania SAPI/Agnieszka, w tym brak interaktywnego modala;
- finalny adapter pojedynczego znaku oraz maksymalnego eventu;
- wartości deadline/cooldown/bounded queue po benchmarku.
