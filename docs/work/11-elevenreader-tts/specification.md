---
kind: specification
status: draft
updated: 2026-10-25
---

# Specyfikacja: silnik lektora ElevenReader

## Cel

AniShift czyta polskie kwestie odcinka głosem z ElevenReadera (model Eleven v4) przez automatyzację prawdziwej
przeglądarki Chrome, na wzór repozytorium `ElevenDownloaderPro` (EDP). Silnik `elevenbytes` zostaje zapasem.
Intencja i odrzucone drogi: `intent.md`.

## Użytkownik i ocena

Właściciel, jedyny użytkownik, na Windowsie, z rezydentem działającym w tle z checkoutu. Ogląda z lektorem, często
na x2 (`docs/work/10-quality/specification.md:9`). Ocenia uchem na prawdziwym odcinku: jakość głosu, tempo
względem okien napisów, głośność względem oryginału, brak uciętych słów.

## Stan wyjściowy

### Trasa EDP (źródło logiki, tylko do odczytu)

- EDP uruchamia zainstalowany Google Chrome z własnym profilem i portem zdalnego debugowania, a Playwright
  podłącza się przez CDP (`src/downloader.py:454-475`). Profil trzyma zalogowaną sesję
  (`src/downloader.py:38-39`, `README.md:57`).
- Upload dokumentu i odtwarzanie idą przez interfejs strony: przycisk Import, pole pliku, przycisk Upload,
  odpowiedź `POST /v1/reader/reads/add/v2` z `read_id` i `char_count` (`src/auto.py:53-57`, `src/auto.py:137-145`).
- Audio i czasy znaków przychodzą ramkami JSON przez WebSocket
  `wss://api.elevenlabs.io/v1/reader/reads/stream/v2/{read_id}`: `audio` (MP3 w base64), `alignment.chars`,
  `charStartTimesMs`, `charDurationsMs`, `isFinal` (`docs/research/capabilities.md:18-31`,
  `src/downloader.py:181-255`).
- MP3 128 kb/s, 44,1 kHz (`docs/report.md:17`). Czasy znaków są względne wobec paczki; czas bezwzględny to offset
  paczki liczony z długości ramek MP3 plus czas znaku (`src/downloader.py:230`, `src/timestamps.py:99-117`).
- Czasy znaków wyprzedzają mowę o około 0,3 s (`docs/report.md:39`); cięcie na kwestie wymaga dopasowania do ciszy
  w audio (`src/clips.py:397-514`).
- Model v4 daje prędkość czytania 1x w ustawieniach ElevenReadera; przy około 3x serwer przechodzi na v2
  (`docs/report.md:36`, `src/auto.py:86-87`, `src/auto.py:148-157`).
- Jeden dokument naraz: od 2026-10-19 nowy strumień zamyka starszy (`docs/report.md:33`, `README.md:143`).
- Kredyt to 10 000 znaków, łącznie ze wstawianymi przez serwer tagami `<break .../>` (`docs/report.md:35`,
  `docs/research/capabilities.md:28`, `docs/research/capabilities.md:35`).
- Kod EDP nie wybiera głosu. Głos wynika z ustawień konta (`default_voice_id` w `user_config`, trafia do adresu
  WebSocketu; `docs/research/capabilities.md:63`). Nazwa „Piotr Fronczewski” i kategoria `famous` są w
  `docs/research/capabilities.md:10` i `:65`. Głos „Adam” nie występuje w kodzie ani dokumentach EDP.

### AniShift dziś

- Rejestr TTS: `edge`, `elevenbytes`, `elevenlabs`, `sapi` (`anishift/services/tts/engines/__init__.py:18-38`).
- Kontrakt silnika: jedno żądanie tekstu na jeden klip (`anishift/services/tts/protocols.py:86-123`); wspólny
  scheduler posiada retry, circuit i limity (`anishift/services/tts/scheduler.py:224-344`).
- `TtsTaskHandler` składa jeden `SpeechBatch` na odcinek z kwestii w kolejności czytania i drugi dla szyldów
  (`anishift/application/tts_handler.py:541-562`, `:336-366`). Miks umieszcza klipy w oknach napisów, mierząc długość
  dekodowanego klipu (`anishift/services/audio/timeline.py:31-89`).
- Resume klipów jest per kwestia: tożsamość to tekst kwestii i profil silnika
  (`anishift/services/tts/fingerprint.py`, `anishift/services/tts/resume.py:155-170`).
- Prywatne profile z danymi uwierzytelnienia leżą w `config/` i są zawężane ACL do bieżącego konta
  (`anishift/platform/qbittorrent_process.py:633-653`, `.gitignore:292-296`).

## Ustalenia

- **U1. Wariant integracji: kopia logiki EDP z refaktorem do konwencji AniShift.** Skutek: nowy pakiet
  `anishift/services/tts/engines/elevenreader/`; AniShift nie importuje EDP, nie czyta jego katalogów i nie
  uruchamia jego skryptów.
- **U2. Jednostką syntezy silnika jest dokument.** Skutek: domena TTS dostaje kontrakt syntezy dokumentu, a wspólny
  scheduler wykonuje dowolną próbę providera, nie tylko pojedyncze żądanie.
- **U3. Kwestie dokumentu są osobnymi akapitami.** Skutek: serwer wstawia między nimi pauzę (tag `<break>`), co daje
  ciszę do cięcia, a koszt rośnie o około 21 znaków na kwestię (`docs/research/capabilities.md:105-119`). Założenie
  zależne od decyzji D4.
- **U4. Czasy znaków służą do cięcia nagrania na kwestie i do kontroli kompletności.** Skutek: dopasowanie tempa,
  przycinanie ciszy i raport rozjazdu nadal pochodzą z dekodowanej długości klipu i planu osi czasu, jak dziś.
- **U5. Cięcie i wykrywanie ciszy należą do domeny audio**, wstrzykiwane do TTS protokołem, tak jak walidacja i
  sklejanie klipów (`anishift/application/tts_clips.py:17-100`). Skutek: TTS nadal nie importuje domeny audio.
- **U6. Parsowanie nagłówków ramek MPEG ma jedno źródło** w `anishift/utils/mp3_frames.py`. Skutek: domena audio i
  silnik używają tej samej funkcji; `anishift/services/audio/mp3.py` przestaje mieć własną kopię.
- **U7. Brak automatycznego przełączania silników.** Skutek zgodny z regułą domeny „Caller jawnie wybiera silnik;
  nie ma cichego fallbacku” (`anishift/services/tts/AGENTS.md:33`). Założenie zależne od decyzji D1.
- **U8. Jedna przeglądarka i jeden dokument naraz.** Skutek: `max_concurrency` silnika wynosi dokładnie 1.

## Wymagania funkcjonalne

### Silnik i rejestr

- **F1.** Rejestr TTS zawiera `elevenreader` w stabilnej kolejności `edge`, `elevenbytes`, `elevenlabs`,
  `elevenreader`, `sapi`; import rejestru nie ładuje Playwright.
- **F2.** Silnik czyta wszystkie brakujące kwestie jednego `SpeechBatch` w najmniejszej liczbie dokumentów
  mieszczących się w limicie znaków dokumentu i zwraca jeden zwalidowany klip MP3 na kwestię.
- **F3.** Kwestia, której nie znaleziono w nagraniu, kończy się błędem tej kwestii; pozostałe kwestie są
  zatwierdzane.
- **F4.** Ponowne uruchomienie odcinka wykorzystuje zatwierdzone klipy jako trafienia resume i czyta wyłącznie
  brakujące kwestie.
- **F5.** Tekst kwestii trafia do dokumentu bez zmiany słów; nawiasy kwadratowe są zamieniane na okrągłe, a
  białe znaki wewnątrz kwestii na pojedyncze spacje, aby ElevenReader nie interpretował znaczników i nie tworzył
  dodatkowych akapitów.
- **F6.** Czytane szyldy (`sign_narration`) idą tą samą drogą, jako osobny dokument tej samej grupy.
- **F7.** Silnik ustawia w odtwarzaczu prędkość czytania 1x (model v4) przed każdym odtworzeniem.
- **F8.** Silnik używa głosu wybranego w ustawieniach i odmawia nagrania, gdy nie może potwierdzić, że odtwarzacz
  czyta tym głosem.

### Głosy

- **F9.** Ustawienia oferują dla `elevenreader` dokładnie dwa aliasy: `fronczewski` (etykieta „Piotr Fronczewski”)
  i `adam` (etykieta „Adam”); identyfikatory głosów pochodzą ze stałych silnika ustalonych w fazie 0.
- **F10.** Domyślnym głosem silnika jest `fronczewski` (decyzja D3).
- **F11.** Przełączenie z `elevenreader` na inny silnik nie przenosi aliasu, ID głosu ani modelu `eleven_v4`:
  `elevenbytes` dostaje Dallin, `edge` i `sapi` swoje głosy domyślne, `elevenlabs` model domyślny i pusty głos do
  wyboru; przełączenie na `elevenreader` ustawia głos domyślny `fronczewski`. Własne głosy ElevenBytes i profile
  głosów (tempo, korekta głośności) pozostają zapisane.
- **F12.** Każdy głos ElevenReadera ma własny profil `tts_voice_profiles` z tempem końcowym i korektą głośności;
  współbieżność nie jest edytowalna.

### Sesja i logowanie

- **F13.** Sesja konta (cookies) żyje w prywatnym profilu Chrome w `config/elevenreader/chrome-profile/`,
  zawężonym ACL do bieżącego konta Windows. Katalog `config/elevenreader/` jest w `.gitignore`, zanim powstanie w
  nim pierwszy plik (repozytorium jest publiczne).
- **F14.** Ustawienia → Lektor przy silniku `elevenreader` mają akcję „Zaloguj / sprawdź sesję”, która otwiera
  widoczne okno Chrome na stronie ElevenReadera i kończy się wynikiem: zalogowano, nie zalogowano, przeglądarka
  zajęta albo brak Chrome.
- **F15.** Przy ważnej sesji silnik pracuje bez działań człowieka (logowanie automatyczne przez zapisaną sesję).
- **F16.** Gdy sesja wygasła, silnik zgłasza błąd uwierzytelnienia z sugestią akcji z F14; jeśli w `.env` są dane
  logowania i faza 0 potwierdzi logowanie e-mailem i hasłem bez captchy, silnik najpierw próbuje jednego
  automatycznego logowania (decyzja D2).
- **F17.** Wynik ostatniego sprawdzenia sesji (zalogowano lub nie, czas) jest zapisany bez sekretów w
  `config/elevenreader/session.json` i pokazywany w panelu.

### Diagnostyka

- **F18.** `anishift doctor` zgłasza dla wybranego silnika `elevenreader`: brak Chrome jako FAIL, brak profilu
  albo ostatnie sprawdzenie „nie zalogowano” jako WARN z sugestią akcji z F14; dla innego silnika — SKIP.
- **F19.** `doctor` nie uruchamia przeglądarki i nie łączy się z ElevenReaderem.

### Błędy

- **F20.** Odmowa uwierzytelnienia, blokada konta i wyczerpane kredyty kończą próbę błędem trwałym, który otwiera
  circuit schedulera; AniShift ich nie ponawia.
- **F21.** Niedostępność serwisu, zerwane połączenie, brak audio po starcie i przestój nagrywania są błędami
  przejściowymi ponawianymi przez wspólny scheduler.
- **F22.** Komunikat błędu w panelu mówi, co zrobić: zalogować się, poczekać na doładowanie kredytów albo przełączyć
  silnik na `elevenbytes`.

## Wymagania jakościowe

- **N1.** Żadna ścieżka logu, wyjątku, receipt, ledgera (`config/watch/`), `decisions.jsonl` ani dokumentu nie
  zawiera: cookies, haseł, adresu e-mail, adresu WebSocketu, odpowiedzi HTTP, tekstu kwestii, ścieżek absolutnych.
- **N2.** Słowo nie jest ucinane na granicy klipu w ocenie ucha właściciela; automatycznie: liczba granic bez ciszy
  jest logowana jako liczba, a każda kwestia ma długość mowy większą od zera.
- **N3.** Odcinek o około 300 kwestiach (około 12 000 znaków) kończy syntezę w czasie rzędu kilku minut
  (EDP: około 4,6x czasu rzeczywistego, `docs/research/capabilities.md:116`); pomiar w fazie 6, bez progu
  narzuconego z góry.
- **N4.** Anulowanie przebiegu zatrzymuje nagrywanie w ciągu kilku sekund, zamyka kartę i przeglądarkę.
- **N5.** Zamknięcie rezydenta kończy proces Chrome uruchomiony przez silnik.
- **N6.** Bramki jakości przechodzą na `anishift/ tests/`, bez testów sieciowych w domyślnym `uv run pytest`.
- **N7.** Postęp w Przetwarzaniu pochodzi z pomiaru: liczby odebranych znaków wobec `char_count` dokumentu.

## Inwarianty

- **I1.** `elevenbytes`, `edge`, `elevenlabs` i `sapi` działają jak przed zmianą; ich testy przechodzą bez zmian
  zachowania.
- **I2.** Domena TTS nie importuje `pysubs2`, `anishift.services.audio`, `anishift.services.subtitles` ani
  `anishift.services.translation` (`tests/services/tts/test_tts_contract.py:190`).
- **I3.** Retry, circuit i limity należą wyłącznie do wspólnego schedulera; transport silnika wykonuje jedną próbę.
- **I4.** Tożsamość resume klipu kwestii obejmuje tekst kwestii i profil silnika z głosem; zmiana głosu unieważnia
  resume.
- **I5.** Domyślny silnik w `UserSettings` pozostaje `elevenbytes` (decyzja D8).

## Ograniczenia

- **O1.** Tylko Windows i zainstalowany Google Chrome w standardowej lokalizacji albo na `PATH`.
- **O2.** Chrome 136+ ignoruje `--remote-debugging-port` dla domyślnego katalogu danych; profil musi być osobnym
  katalogiem (<https://developer.chrome.com/blog/remote-debugging-port>, odczyt 2026-10-25).
- **O3.** Jedno konto, jeden dokument naraz, jedna przeglądarka na profil.
- **O4.** Wewnętrzne API ElevenReadera jest nieudokumentowane i może zmienić się bez ostrzeżenia
  (`docs/research/capabilities.md:154`).
- **O5.** Nowa zależność tylko `playwright` (przez `uv add`); bez pobierania przeglądarek Playwright.
- **O6.** Głos Fronczewskiego ma kategorię `famous`; nagrania służą prywatnemu odsłuchowi
  (`docs/research/capabilities.md:153`).

## Zakazane

- **Z1.** Obchodzenie App Check, limitów urządzenia, sprawdzania IP, limitów kredytów; podrabianie ramek WebSocket;
  bezpośrednie wywołania API poza tym, co robi strona w prawdziwym Chrome; wiele kont.
- **Z2.** Automatyczne przełączanie silnika lub głosu w trakcie odcinka.
- **Z3.** Edycja repozytorium EDP, import jego modułów, odczyt jego profili `.chrome-profile/` i `.browser-profile/`.
- **Z4.** Commitowanie nagrań głosów ElevenReadera, prawdziwych ramek z audio głosu, cookies i plików profilu.
- **Z5.** Ręczna edycja `pyproject.toml`; zależności tylko `uv add` / `uv remove`.
- **Z6.** Retry wewnątrz transportu silnika.
- **Z7.** Automatyczne ponawianie po 401, 403 i wyczerpaniu kredytów.

## Zakres

- Kontrakt syntezy dokumentu w domenie TTS i uogólnienie schedulera.
- Wspólne parsowanie ramek MPEG, cięcie nagrania na klipy w ciszy w domenie audio.
- Silnik `elevenreader`: przeglądarka, sesja, upload, odtwarzanie, nagrywanie, wyrównanie kwestii.
- Ustawienia, panel, `doctor`, `paths.py`, `.gitignore`, kompozycja w `application/runtime.py`.
- Testy jednostkowe i integracyjne bez sieci, test sieciowy pomijany domyślnie.
- Aktualizacja `AGENTS.md` dotkniętych obszarów, `config/README.md`, `docs/reference/settings.md`, README.

## Poza zakresem

- Audiobooki z rozdziałami, karaoke, eksport słownych czasów.
- Monitor kredytów i estymacja kosztu przed nagraniem.
- Usuwanie dokumentów z biblioteki ElevenReadera (decyzja D5).
- Etap 6 jakości (głośność lektora) — wraca po akceptacji silnika.
- Linux.

## Odłożone

- Ponowne użycie wgranego dokumentu między przebiegami (mapa skrót → `read_id` na dysku): w MVP ponowne użycie
  dotyczy tylko prób w jednym przebiegu.
- Słowne czasy do raportu jakości lektora.

## Odrzucone

- Zależność pakietowa od EDP i uruchamianie EDP jako procesu (powody w `intent.md`).
- Osobny dokument na kwestię.
- Model ASR do wyrównania.
- Playwright `launch_persistent_context` zamiast prawdziwego Chrome z CDP: EDP celowo używa CDP, by logowanie
  Google działało (`src/downloader.py:3`).

## Warunki sukcesu

- **S1.** Bramki: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`,
  `uv run mypy anishift/ tests/`, `uv run pytest` — zielone na końcowym commicie.
- **S2.** Test sieciowy silnika uruchomiony ręcznie przez właściciela (`-m network`, zmienna zgody) nagrywa krótki
  dokument trzech kwestii i daje trzy zwalidowane klipy.
- **S3.** Checkpoint ucha (plan, faza 6): właściciel akceptuje głos, tempo i głośność na jednym prawdziwym
  odcinku, bez uciętych słów.
- **S4.** Powrót na `elevenbytes` w Ustawieniach daje działający przebieg tego samego odcinka.
- **S5.** Przegląd kodu krzyżowy (inny model niż autor) bez findingów krytycznych i poważnych.
- **S6.** Skan sekretów: `git grep` na gałęzi nie znajduje adresu e-mail właściciela, nazw cookies ani plików
  profilu.

## Otwarte decyzje właściciela

Plan realizuje rekomendację każdej decyzji jako założenie.

- **D1. Zapas `elevenbytes`: ręczny czy automatyczny?** Rekomendacja: ręczny. Automat łamie regułę domeny, mieszałby
  głosy w jednym odcinku i maskował ban.
- **D2. Logowanie: tylko zapisana sesja czy też automatyczne wpisywanie e-maila i hasła?** Rekomendacja: zapisana
  sesja plus akcja „Zaloguj” w panelu; wpisywanie danych tylko wtedy, gdy faza 0 pokaże konto e-mail bez captchy.
  Konto Google wymaga ręcznego logowania (EDP: `src/downloader.py:3`).
- **D3. Głos domyślny.** Rekomendacja: Piotr Fronczewski — polski, na nim zrobiono wszystkie pomiary EDP.
- **D4. Kwestie jako osobne akapity czy jeden akapit?** Rekomendacja: osobne akapity — wyraźna cisza do cięcia,
  koszt około +50% znaków (`docs/research/capabilities.md:105-108`).
- **D5. Dokumenty w bibliotece ElevenReadera po nagraniu: zostawić czy usuwać?** Rekomendacja: zostawić — mniej
  automatyzacji strony i mniej ryzyka; właściciel czyści bibliotekę ręcznie.
- **D6. Skopiować zalogowany profil EDP czy zalogować się od nowa?** Rekomendacja: od nowa — EDP zostaje
  nietknięty, a jednorazowe logowanie jest tańsze niż ryzyko z kopią profilu.
- **D7. Kod automatyzacji w publicznym repozytorium AniShift.** Rekomendacja: zaakceptować świadomie — repozytorium
  jest publiczne z wyboru właściciela, kod nie zawiera sekretów; alternatywą jest prywatny pakiet, kosztowny w
  utrzymaniu.
- **D8. Kiedy `elevenreader` staje się domyślny?** Rekomendacja: domyślny w kodzie zostaje `elevenbytes`;
  właściciel przełącza silnik sam po checkpoincie.
- **D9. Przeglądarka przy nagrywaniu: bez okna czy z oknem?** Rekomendacja: bez okna (`--headless=new`, wspierane w
  EDP, `README.md:84`), jeśli faza 0 to potwierdzi; inaczej zminimalizowane okno.
- **D10. Szyldy czytane tym samym silnikiem?** Rekomendacja: tak, jednym głosem w całym odcinku.
- **D11. Pamiętać ostatni głos osobno dla każdego silnika?** Rekomendacja: nie; F11 wystarcza.
