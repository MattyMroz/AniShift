---
kind: specification
status: draft
updated: 2026-10-31
---

# Specyfikacja: silnik lektora ElevenReader

## Cel

AniShift czyta polskie kwestie odcinka głosem z ElevenReadera (model Eleven v4) przez automatyzację prawdziwej
przeglądarki Chrome. Lektor ma właściwą głośność względem oryginału i tempo dobrane do głosu. Silnik `elevenbytes`
zostaje zapasem. Intencja: `intent.md`. Plan wykonania: `plan.md`.

## Użytkownik i ocena

Właściciel, jedyny użytkownik, na Windowsie, z rezydentem działającym w tle z checkoutu. Ogląda z lektorem, często
na x2. Ocenia uchem na prawdziwym odcinku: jakość głosu, tempo względem okien napisów, głośność względem oryginału,
brak uciętych słów.

## Stan wyjściowy (2026-10-30)

### Prototyp poza repozytorium

Katalog `SCR` to `er/` w tymczasowym katalogu roboczym sesji, poza repozytorium; faza 0 planu kopiuje dane poza
niego.

- `SCR/record.py` nagrywa cały odcinek jednym dokumentem przez trasę ElevenDownloaderPro (EDP): Chrome bez okna,
  Playwright przez CDP, upload przyciskiem „Import”, głos i prędkość 1x ustawione w `user_config` konta tokenem
  strony, odtwarzanie przyspieszone 64x, zapis ramek WebSocket, na koniec usunięcie dokumentu z biblioteki i
  przywrócenie poprzedniego głosu konta. Wynik Tantei S2E03: 19 038 znaków, upload 10–12 s, nagrywanie 245 s na
  głos, komplet znaków, głos potwierdzony w adresie strumienia (`SCR/tantei/record.json`).
- `SCR/snap-report.md`: cięcie nagrania na kwestie bez modelu. Na 324 kwestiach i dwóch głosach 100% poprawnych
  granic (640 cięć, 6 granic bez pewnej ciszy). CrisperWhisper służył tylko jako miernik.
- `SCR/edge02/`, `SCR/edge03/`: nagrania Edgerunners 02 i 03 do walidacji cięcia na innym materiale; walidacja
  trwa (punkt kontrolny K1 planu).
- `SCR/loudness-report.md`: głośność i tempo trzech głosów, projekt normalizacji w `AudioService`, prototyp
  odsłuchowy, który właściciel ocenił jako „w miarę OK”.

### AniShift

- Rejestr TTS: `edge`, `elevenbytes`, `elevenlabs`, `sapi` (`anishift/services/tts/engines/__init__.py`).
- Kontrakt silnika: jedno żądanie tekstu na jeden klip (`TtsEngine.synthesize` w
  `anishift/services/tts/protocols.py`). Wspólny `TtsScheduler` posiada retry, circuit i limity.
- `TtsTaskHandler` (`anishift/application/tts_handler.py`) buduje jeden `SpeechBatch` na odcinek z kwestii w
  kolejności czytania i drugi dla szyldów.
- Miks: gain narratora to `narrator_mix_base_gain_db + voice_mix_offset_db` (stałe dB, bez pomiaru;
  `anishift/services/audio/output.py`, `render_command`). Brak limitera.
- Klipy nie mają przycinania ciszy na brzegach. Tempo końcowe i korekta głośności są już na głos
  (`TtsVoiceProfileSettings.postprocess_tempo`, `.voice_mix_offset_db` w `anishift/config/user_settings.py`).
- Prywatne profile z danymi uwierzytelnienia leżą w `config/` i są zawężane ACL do bieżącego konta
  (`_protect_profile` w `anishift/platform/qbittorrent_process.py`).

## Ustalenia

- **U1. Kod nagrywania przenosimy do AniShift.** Nowy pakiet `anishift/services/tts/engines/elevenreader/`,
  zależność `playwright` przez `uv add`, profil przeglądarki w `config/elevenreader/`. AniShift nie importuje EDP,
  nie uruchamia jego skryptów i nie czyta jego katalogów. Logika EDP i prototypu jest adaptowana i
  refaktoryzowana do standardu repo (typowane błędy, logger, async, jedno źródło prawdy, zero legacy), nie
  kopiowana 1:1. Uzasadnienie: `plan.md` §4.
- **U2. Jednostką syntezy silnika jest dokument odcinka.** Domena TTS dostaje kontrakt syntezy dokumentu, a
  scheduler wykonuje dowolną próbę providera, nie tylko pojedyncze żądanie.
- **U3. Kwestie dokumentu są osobnymi akapitami rozdzielonymi akapitem „…”.** Serwer stawia `<break time="0.6s"/>`
  wokół każdego akapitu, co daje znacznik podziału w czasach znaków. `<break>` wpisany w tekst dokumentu serwer
  ignoruje, a `[pause]` lektor czyta na głos; ciszę do cięcia wydłuża dopiero osobny akapit „…”, którego lektor nie
  czyta (wynik K1, `snap-report.md` §11–§13).
- **U4. Klip kwestii wycina heurystyka ciszy, bez modelu mowy.** Czasy znaków serwera wyznaczają okno każdej
  granicy; cięcie wypada w środku ciszy (`plan.md` §7.4). CrisperWhisper ani żaden inny model nie wchodzi do
  AniShift.
- **U5. Kwestie urwane w pół zdania łączymy w tekście tylko dla silnika dokumentowego.** Granica bez pauzy w mowie
  wtedy nie powstaje. Silniki „kwestia po kwestii” (`elevenbytes`, `elevenlabs`, `edge`, `sapi`) syntetyzują każdą
  linijkę osobnym żądaniem, więc u nich takiej granicy nie ma i nic się nie zmienia. Reguła w `plan.md` §7.6.
- **U6. Głośność lektora jest mierzona, nie stała.** Lektor ma zintegrowaną głośność równą głośności oryginału
  plus `narrator_over_source_lu` (domyślnie 7,5 LU) plus korekta głosu; na wyjściu miksu limiter −1 dBFS.
  `narrator_over_source_lu` zastępuje `narrator_mix_base_gain_db` bez aliasu.
- **U7. Brzegi każdego klipu są przycinane z ciszy** przed ułożeniem na osi czasu. To obróbka audio, wspólna dla
  wszystkich silników, także `elevenbytes` (D1).
- **U8. Tempo i korekta głośności są na głos** w istniejących profilach `tts_voice_profiles`.
- **U9. Jedna przeglądarka i jeden dokument naraz.** `max_concurrency` silnika wynosi dokładnie 1.
- **U10. Brak automatycznego przełączania silników.** Powrót do `elevenbytes` to jeden wybór w Ustawieniach,
  podpowiadany w każdym trwałym błędzie silnika.
- **U11. Logowanie tylko zapisaną sesją.** Właściciel loguje się raz w oknie Chrome otwartym akcją panelu; AniShift
  nie przechowuje e-maila ani hasła.
- **U12. Głos i prędkość ustawia konto, nie odtwarzacz.** Silnik zapisuje `default_voice_id` i
  `playback_speed_rate = 1` w `user_config` konta tokenem strony.
- **U14. Sprzątanie zawsze.** Po każdej próbie — udanej, nieudanej i przerwanej — silnik w `finally` usuwa wgrany
  dokument z biblioteki ElevenReadera i przywraca poprzedni głos i tempo konta. Na koncie nie zostają śmieci.
- **U13. Nagrywanie bez okna** (`--headless=new`); okno tylko przy akcji logowania.

## Wymagania funkcjonalne

### Silnik i rejestr

- **F1.** Rejestr TTS zawiera `elevenreader` w kolejności `edge`, `elevenbytes`, `elevenlabs`, `elevenreader`,
  `sapi`; import rejestru i pakietu silnika nie ładuje Playwright.
- **F2.** Silnik czyta wszystkie brakujące kwestie jednego `SpeechBatch` w najmniejszej liczbie dokumentów
  mieszczących się w limicie znaków i daje jeden zwalidowany klip na kwestię.
- **F3.** Odcinki tekstu serwera między ciągami tagów `<break>` (sąsiednie tagi to jedna granica), bez odcinków
  pustych i równych „…”, muszą liczbą i treścią zgadzać się z kwestiami dokumentu; inaczej próba kończy się błędem i
  jest ponawiana.
- **F4.** Ponowne uruchomienie odcinka wykorzystuje zatwierdzone klipy i czyta wyłącznie brakujące kwestie.
- **F5.** Tekst kwestii trafia do dokumentu bez zmiany słów; nawiasy kwadratowe zamieniane są na okrągłe, a białe
  znaki wewnątrz kwestii na pojedyncze spacje. Dokument ma postać `"\n\n…\n\n".join(kwestie) + "\n"`, bez `<break>`
  i bez `[pause]`; wielokropek na końcu kwestii zostaje w jej tekście. Limit znaków dokumentu dotyczy całego tego
  tekstu razem z separatorami.
- **F6.** Przy silniku dokumentowym wszystkie kandydaty szyldów (tryb `sign_narration` inny niż `off`) idą w tym
  samym batchu co kwestie, więc w tym samym dokumencie i nagraniu; wybór i rozmieszczenie szyldów po syntezie są takie
  same jak przy silnikach „kwestia po kwestii”. Drugiego dokumentu nie ma.
- **F7.** Silnik nagrywa przy prędkości czytania 1x i przerywa próbę, gdy strumień zgłosi inną prędkość (model v2).
- **F8.** Silnik odmawia zatwierdzenia nagrania, gdy adres strumienia nie zawiera identyfikatora wybranego głosu.

### Cięcie i klipy

- **F9.** Granica między kwestią i a i+1 wypada w środku najlepszej ciszy w oknie wyznaczonym czasami serwera,
  według reguły z `plan.md` §7.4, na osi czasu MP3 z przeliczeniem uszkodzonych ramek.
- **F10.** Granica bez wymaganej ciszy dostaje cięcie w punkcie zakotwiczenia; liczba takich granic trafia do logu
  jako ostrzeżenie z liczbą.
- **F11.** Przy silniku dokumentowym dwie kolejne kwestie łączą się w jedno żądanie syntezy, gdy pierwsza nie kończy
  zdania, a druga zaczyna się najpóźniej w chwili końca pierwszej (§7.6 planu). Okno połączonej kwestii obejmuje oba
  napisy. Przy pozostałych silnikach kwestie nie są łączone.
- **F12.** Każdy klip przed tempem i ułożeniem traci ciszę na brzegach (§7.7 planu); klip bez mowy powyżej progu
  zostaje bez zmian.

### Głośność i tempo

- **F13.** Przy miksie z oryginałem AudioService mierzy zintegrowaną głośność narratora i oryginału (`ebur128`) i
  ustawia wzmocnienie narratora tak, by był `narrator_over_source_lu + voice_mix_offset_db` LU ponad oryginałem.
  Oryginał jest mierzony po standardowym downmiksie FFmpeg do stereo, więc cel znaczy to samo przy źródle stereo i
  5.1.
- **F14.** Miks kończy limiter szczytów −1 dBFS bez normalizacji (`alimiter … level=0`). Ścieżka tylko z
  narratorem zostaje bez wzmocnienia i bez limitera.
- **F15.** Profile głosów mają domyślnie: Fronczewski tempo 1,45 i korekta +0,5 dB; Adam 1,35 i +2,5 dB; Dallin
  (`elevenbytes`) 1,25 i 0 dB.
- **F16.** Panel pokazuje „Głośność lektora” w LU ponad oryginał.

### Głosy

- **F17.** Ustawienia oferują dla `elevenreader` dwa głosy: `fronczewski` („Piotr Fronczewski”,
  `T5l58N8RNz5DKoClpKIJ`) i `adam` („Adam”, `hIssydxXZ1WuDorjx6Ic`). Lista żyje tylko w silniku.
- **F18.** Głos domyślny silnika: `fronczewski`.
- **F19.** Przełączenie z `elevenreader` na inny silnik nie przenosi aliasu ani ID głosu: `elevenbytes` dostaje
  Dallin, pozostałe silniki swoje głosy domyślne (`elevenlabs`, bez wbudowanej listy głosów, dostaje domyślne
  `dallin` z `UserSettings`). Profile głosów zostają zapisane.

### Sesja

- **F20.** Sesja konta żyje w profilu Chrome w `config/elevenreader/chrome-profile/`, zawężonym ACL do bieżącego
  konta Windows. `config/elevenreader/` jest w `.gitignore`, zanim powstanie w nim pierwszy plik.
- **F21.** Ustawienia → Lektor przy `elevenreader` mają akcję „Zaloguj / sprawdź sesję”: otwiera okno Chrome na
  bibliotece ElevenReadera i kończy się wynikiem „zalogowano”, „nie zalogowano”, „przeglądarka zajęta” albo „brak
  Chrome”.
- **F22.** Przy ważnej sesji silnik pracuje bez działań człowieka.
- **F23.** Wygasła sesja kończy syntezę błędem uwierzytelnienia z sugestią akcji z F21; wynik ostatniego sprawdzenia
  (bez sekretów, z czasem) leży w `config/elevenreader/session.json` i jest widoczny w panelu.
- **F24.** `anishift doctor` przy wybranym `elevenreader`: brak Chrome to FAIL, brak profilu albo ostatnie
  „nie zalogowano” to WARN z sugestią F21; przy innym silniku SKIP, chyba że w `session.json` czeka zaległe
  sprzątanie konta (F28) — wtedy WARN przy każdym silniku. Doctor nie uruchamia przeglądarki.

### Błędy

- **F25.** Odmowa uwierzytelnienia, blokada konta, wyczerpane kredyty i zły głos kończą próbę błędem trwałym, który
  otwiera circuit schedulera; AniShift ich nie ponawia.
- **F26.** Niedostępność serwisu, zerwane połączenie, brak audio po starcie, przestój, niekompletne nagranie i
  niezgodna liczba kwestii są błędami przejściowymi ponawianymi przez wspólny scheduler.
- **F27.** Komunikat trwałego błędu w panelu mówi, co zrobić: zalogować się, poczekać na kredyty albo przełączyć
  silnik na `elevenbytes`. Żaden błąd nie kończy się cichym zatrzymaniem.
- **F28.** Sprzątanie (U14) biegnie także po błędzie i anulowaniu. Nieudane sprzątanie silnik ponawia przy
  następnej próbie i przy zamknięciu; jeśli i to zawiedzie, zostaje ostrzeżenie w logu i komunikat w panelu, że
  dokument lub ustawienia konta trzeba poprawić ręcznie. Błąd sprzątania nie unieważnia gotowego nagrania.

## Wymagania jakościowe

- **N1.** Żaden log, wyjątek, receipt, ledger (`config/watch/`), `decisions.jsonl` ani dokument nie zawiera:
  cookies, tokenu, adresu e-mail, adresu WebSocketu, `read_id`, odpowiedzi HTTP, tekstu kwestii, ścieżek
  absolutnych.
- **N2.** Na danych Tantei S2E03 cięcie daje te same granice co prototyp `SCR/snapcut.py` (±10 ms) dla obu głosów.
- **N3.** Odcinek około 20 000 znaków kończy nagrywanie w czasie rzędu kilku minut (prototyp: 245 s).
- **N4.** Anulowanie przebiegu zatrzymuje nagrywanie w ciągu kilku sekund i zamyka Chrome.
- **N5.** Zamknięcie rezydenta kończy proces Chrome uruchomiony przez silnik.
- **N6.** Bramki jakości przechodzą na `anishift/ tests/`, bez testów sieciowych w domyślnym `uv run pytest`.
- **N7.** Postęp w Przetwarzaniu pochodzi z pomiaru: odebrane znaki wobec `char_count` dokumentu.

## Inwarianty

- **I1.** `elevenbytes`, `edge`, `elevenlabs` i `sapi` syntetyzują jak przed zmianą, także bez łączenia kwestii.
  Zmiany wspólne dla wszystkich głosów są dwie i jawne: przycinanie brzegów (F12, D1) i mierzona głośność
  (F13–F14).
- **I2.** Domena TTS nie importuje `pysubs2`, `anishift.services.audio`, `anishift.services.subtitles` ani
  `anishift.services.translation`.
- **I3.** Retry, circuit i limity należą wyłącznie do wspólnego schedulera; transport silnika wykonuje jedną próbę.
- **I4.** Tożsamość resume klipu obejmuje tekst kwestii i profil silnika z głosem; zmiana głosu unieważnia resume.
- **I5.** Domyślny silnik w `UserSettings` pozostaje `elevenbytes`; właściciel przełącza go sam po checkpoincie.

## Ograniczenia

- **O1.** Tylko Windows i zainstalowany Google Chrome w standardowej lokalizacji albo na `PATH`.
- **O2.** Chrome 136+ ignoruje `--remote-debugging-port` dla domyślnego katalogu danych; profil musi być osobnym
  katalogiem.
- **O3.** Jedno konto, jeden dokument naraz, jedna przeglądarka na profil.
- **O4.** Wewnętrzne API ElevenReadera jest nieudokumentowane i może zmienić się bez ostrzeżenia.
- **O5.** Nowa zależność tylko `playwright` (przez `uv add`), bez pobierania przeglądarek Playwright.
- **O6.** Głos Fronczewskiego ma kategorię `famous`; nagrania służą prywatnemu odsłuchowi i nie trafiają do
  repozytorium.
- **O7.** Próg ciszy −35 dBFS jest wąskim optimum zmierzonym na jednym odcinku (`SCR/snap-report.md` §6).

## Zakazane

- **Z1.** Obchodzenie App Check, limitów urządzenia, sprawdzania IP i limitów kredytów; podrabianie ramek
  WebSocket; wiele kont. Żądania poza kliknięciami w interfejs wolno wysyłać tylko do tych endpointów, których
  strona sama używa (`user_config`, `reads/{id}`), z kontekstu zalogowanej strony i jej własnym tokenem.
- **Z2.** Automatyczne przełączanie silnika lub głosu w trakcie odcinka.
- **Z3.** Edycja repozytorium EDP, import jego modułów, odczyt jego profili `.chrome-profile/` i `.browser-profile/`.
- **Z4.** Commitowanie nagrań głosów ElevenReadera, ramek z prawdziwym audio, cookies i plików profilu.
- **Z5.** Ręczna edycja `pyproject.toml`.
- **Z6.** Retry wewnątrz transportu silnika.
- **Z7.** Automatyczne ponawianie po odmowie dostępu, blokadzie konta i wyczerpaniu kredytów.
- **Z8.** Model mowy (CrisperWhisper, Whisper i podobne) w kodzie produktu.
- **Z9.** Aliasy, stare nazwy pól i warstwy zgodności: `narrator_mix_base_gain_db` znika w całym repo w tym samym
  diffie, a dane właściciela przenosi jednorazowy skrypt w `scripts/tmp/`.

## Zakres

- Kontrakt syntezy dokumentu w domenie TTS i uogólnienie schedulera.
- Wspólne parsowanie ramek MPEG w `anishift/utils/`, cięcie nagrania na klipy, przycinanie brzegów i mierzona
  głośność w domenie audio.
- Łączenie kwestii urwanych w `TtsTaskHandler`, włączane tylko dla silnika dokumentowego.
- Silnik `elevenreader`: przeglądarka, sesja, konto, upload, nagrywanie, czasy kwestii.
- Ustawienia, profile głosów, panel, `doctor`, `paths.py`, `.gitignore`, kompozycja w `application/runtime.py`.
- Testy jednostkowe i integracyjne bez sieci; test zgodności cięcia na danych spoza repo; test sieciowy pomijany
  domyślnie.
- Aktualizacja AGENTS.md dotkniętych obszarów, `config/README.md`, `docs/reference/settings.md`, README EN i PL.

## Poza zakresem

- Audiobooki z rozdziałami, karaoke, eksport słownych czasów.
- Monitor kredytów i estymacja kosztu przed nagraniem.
- Logowanie e-mailem i hasłem z `.env`.
- Próg ciszy liczony względem głośności głosu (wraca, jeśli walidacja Edgerunners go wymusi).
- Linux.

## Warunki sukcesu

- **S1.** Bramki: `uv run ruff check anishift/ tests/`, `uv run ruff format --check anishift/ tests/`,
  `uv run mypy anishift/ tests/`, `uv run mypy --platform linux anishift/ tests/`, `uv run pytest` — zielone na
  końcowym commicie.
- **S2.** Test zgodności cięcia (N2) przechodzi na danych Tantei; walidacja Edgerunners 02 i 03 nie pokazuje
  uciętych słów ani wycieków.
- **S3.** Test sieciowy silnika uruchomiony przez właściciela nagrywa krótki dokument trzech kwestii i daje trzy
  zwalidowane klipy.
- **S4.** Checkpoint ucha: właściciel akceptuje głos, tempo i głośność na jednym prawdziwym odcinku każdym z dwóch
  głosów.
- **S5.** Powrót na `elevenbytes` w Ustawieniach daje działający przebieg tego samego odcinka.
- **S6.** Przegląd kodu krzyżowy (inny model niż autor) bez findingów krytycznych i poważnych.
- **S7.** Skan sekretów: `git grep` w `anishift/` i `tests/` nie znajduje adresu e-mail, tokenów, `read_id` ani
  plików profilu; `config/elevenreader/` jest ignorowany przez git.

## Decyzje właściciela

- **D1. Przycinanie ciszy na brzegach klipów — także dla Dallina (`elevenbytes`) i pozostałych silników?**
  Rozstrzygnięta: tak, jedna obróbka audio dla wszystkich silników (`normalize_clip`, stałe `EDGE_TRIM_*`). Pomiar:
  u Dallina kwestii dłuższych niż okno napisu ubywa z 30 do 10.
