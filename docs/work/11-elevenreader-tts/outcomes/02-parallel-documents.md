---
kind: outcome
status: pending-human
baseline: AniShift a058c65 (main)
resulting-state: work/tts/03-parallel-documents
completed: 2026-10-31
---

# Outcome: kilka odcinków naraz w ElevenReaderze

## Status

- status: pending-human (K2 — odbiór właściciela na prawdziwych odcinkach — jeszcze nie wykonany)
- branch: `work/tts/03-parallel-documents`, worktree `.worktrees/parallel-er`, bez pusha
- human acceptance: brak

## Finalny rezultat

Jeden ukryty Chrome na profil w procesie, karta na nagranie. Odcinki z różnych runów (osobne `TtsService` na
osobnych wątkach i pętlach) nagrywają się naraz; starty idą po kolei, nagrywanie równolegle. Pomiar K1 pokazał,
że konto trzyma na urządzeniu najwyżej **2** strumienie, więc `MAX_PARALLEL_DOCUMENTS` = 2 i domyślnie 2
(zamiast zakładanych 3 i 5).

## Test na koncie (K1)

Test `tests/services/tts/test_tts_elevenreader_network.py::test_tts_services_on_own_threads_live_record_documents_together`,
headless, rezydent zamknięty, profil z `config/elevenreader`. Każdy dokument to osobny `TtsService` w osobnym
wątku, losowy tekst ok. 8 000 znaków (serwer liczy ok. 12 300–12 700 znaków z separatorami), ok. 910–930 s mowy,
`max_retries=0`. Kolejne starty co ok. 14–17 s.

| N | przebiegi | wynik | czas ściany | mowa / ściana łącznie | zamknięte strumienie |
|---|-----------|-------|-------------|-----------------------|----------------------|
| 1 | 1 | 1 × PASS | 229 s | 4,0x | 0 |
| 2 | 3 | 3 × PASS | 242 s, 235 s, 235 s | 7,6x, 7,8x, 7,8x | 0 |
| 3 | 4 | 1 × PASS, 3 × FAIL | 250 s (PASS), 338–350 s (FAIL) | 11,0x (PASS), 5,2–5,4x (FAIL) | 0 (PASS); 1 na przebieg (FAIL) |
| 5 | 1 | FAIL (4 z 5 dokumentów) | 387 s | 2,3x | 4 |

- Objaw porażki (R1 z planu): w chwili otwarcia nowego strumienia serwer zamyka jeden ze starszych (log
  `ElevenReader stream closed` z niepełną liczbą znaków, sekundę przed `stream opened`). Karta zamkniętego
  strumienia nie dostaje już audio i kończy się po `STALL_S` (300 s) błędem `TTS_TIMEOUT: ElevenReader recording
  stalled` albo `sent no audio after Play`. Pozostałe karty kończą się poprawnie.
- Przy N = 3 zamknięcie przychodzi raz przy drugim, raz przy trzecim strumieniu; przy N = 2 nie wystąpiło ani razu.
- Po każdym przebiegu, także nieudanym: głos i tempo konta jak przed testem, zero nowych importów `text/plain` na
  pierwszej stronie `GET reads`, `session.json` bez zaległych kroków. Dokumentów właściciela test nie dotykał.
- Pik pamięci procesów Chrome profilu (próbkowanie co 5 s, okna 10-minutowe): ok. 1,4 GB przy 1–2 kartach,
  do 2,7 GB przy 5. CPU Chrome najwyżej 7,6% całej maszyny (20 wątków), średnio 1–2,4%.
- Koszt: 24 dokumenty po ok. 12 400 znaków.

## Zmiany

- `anishift/services/tts/engines/elevenreader/hub.py`: nowy `ReaderHub` — rejestr per profil, wątek
  `anishift-elevenreader` z pętlą, Chrome, karty, wspólne `AccountCleanup`, jedyny autor `session.json`, bramka głosu
  (kolejka po bilecie), blokada startu zwalniana po pierwszym adresie strumienia, sprzątanie per próba, przywrócenie
  konta po ostatnim aktywnym nagraniu, restart podejrzanej przeglądarki, gdy nikt inny nie nagrywa.
- `service.py`: silnik bez własnego Chrome i `AccountCleanup`; `_KEEP_BROWSER_ERRORS` i stara ścieżka „jeden Chrome
  na silnik” usunięte; postęp wraca na pętlę silnika.
- `api_backend.py`: `clean_account(…, restore=…)`; log otwarcia i zamknięcia strumienia (bez adresu).
- `config.py`, `constants.py`: `MAX_PARALLEL_DOCUMENTS` = 2, zakres `max_concurrency` 1–2.
- Aplikacja: `tts_group_jobs` = `concurrency` profilu dla silnika dokumentowego; `_tts_config` bez wymuszenia 1.
- Ustawienia: wiersz „Syntez jednocześnie” widoczny dla ElevenReadera (1–2, domyślnie 2).
- `specification.md` (U9, U14, F28, O3) i trzy `AGENTS.md`.

## Dowody automatyczne

Testy jednostkowe gospodarza na fałszywej stronie: dwa silniki na dwóch wątkach w kartach jednej przeglądarki,
szeregowany start, koniec pierwszego bez przywrócenia konta, ostatni przywraca, zaległy dokument usuwany na
starcie bez ruszania aktywnego, inny głos czeka, anulowanie i termin jednej karty nie ruszają drugiej, zamknięcie
ostatniego silnika kończy wątek, postęp na wątku silnika. Mutacja (brak wczesnego zwolnienia blokady startu) daje
4 czerwone testy.

## Materialne odkrycia

- odkrycie: limit 2 strumieni na urządzenie konta, nie 3 ani 5;
- dowód: tabela K1;
- wpływ: domyślne 3 z decyzji właściciela nie przechodzi; ustawione 2;
- potrzebna decyzja: brak, chyba że właściciel chce ponowić pomiar 3 w innych warunkach.

## Znane ograniczenia i follow-up

- Zamknięty przez serwer strumień kończy próbę dopiero po `STALL_S` (300 s). Szybsze rozpoznanie zamknięcia
  z niepełnym tekstem nie było w zakresie.
- K2 (właściciel) do zrobienia; patrz plan `plans/02-parallel-documents.md`, z wartością 2 zamiast 3.

## Eksperyment K3: czym ElevenDownloaderPro różni się przy 3 kartach

Pytanie: EDP nagrał 3 pliki naraz (MS3_006–008, 2026-10-29), a AniShift przy N = 3 przeszedł 1 z 4 przebiegów K1.
Kod produktu bez zmian; skrypt w scratchpadzie podmieniał wybrane funkcje w procesie testu.

### Różnice w kodzie (EDP `src/auto.py`, `src/downloader.py` ↔ AniShift)

1. Konto: EDP `auto.py:146-159` (`reset_reading_speed`) wysyła POST `user_config` tylko, gdy tempo ≠ 1x, i nie
   zmienia głosu. AniShift `api_backend.py:508-522` (`prepare_account`) przy każdym starcie robi GET, POST głosu i
   tempa, potem GET.
2. Wgrywanie: EDP wgrywa z jednej stałej karty głównej (`auto.py:134-143`, `:262-264`), a nowa karta od razu otwiera
   dokument. AniShift: każda próba w nowej karcie ładuje bibliotekę (`hub.py:196`, `require_signed_in`), wgrywa i
   otwiera dokument w tej samej karcie (`service.py:233-244`).
3. Odstęp startów: EDP zaczyna następny `begin` zaraz po naciśnięciu Play (`auto.py:181-189`, `:281-284`).
   AniShift zwalnia blokadę startu po pierwszym adresie strumienia (`service.py:246-247`). Zmierzone odstępy:
   EDP 22–24 s (plan, sekcja EDP), AniShift 14–17 s.
4. Prędkość odtwarzania: bez różnicy — obie strony 64x (`auto.py:322`, `constants.py:101`), ten sam mechanizm
   `playbackRate` w skrypcie strony; `listening_speed` 1x (`downloader.py:151`, `READING_SPEED`).
5. Chrome: AniShift dodaje `--mute-audio` (`browser.py:50`); EDP nie (`downloader.py:474-486`).
6. Długość: MS3 to ok. 95–112 min audio na plik (ok. 20 min nagrywania); K1 ok. 15 min audio, K3 ok. 6 min.
7. Token: żadna strona go nie odświeża ani nie podtrzymuje; bez różnicy.

### Pomiar K3

N = 3, losowy tekst ok. 5 000 znaków (serwer liczy ok. 7 800), 3 przebiegi na wariant, 60 s przerwy między
przebiegami, `STALL_S` skrócony do 45 s. Rezydent sprawdzany przed każdym przebiegiem (wyłączony).

| wariant | co zmienia | przebiegi bez zamknięcia strumienia | nagrane dokumenty |
|---------|------------|-------------------------------------|-------------------|
| base | jak dziś | 2 z 3 | 8 z 9 |
| post | POST konta tylko, gdy głos lub tempo się różni (jak EDP, pkt 1) | 1 z 3 | 6 z 9 |
| gap | następny start dopiero 10 s po pierwszym audio poprzedniego, odstęp ok. 25 s (pkt 3) | 0 z 3 | 6 z 9 |
| post+gap | oba | 0 z 3 | 5 z 9 |
| sound | bez `--mute-audio` (pkt 5) | 2 z 3 | 8 z 9 |

Pierwszy, przerwany przebieg `base` (błąd ścieżki w skrypcie) też miał jedno zamknięcie.

- Zamknięcie zawsze przychodzi w fazie startu innej próby: między wczytaniem biblioteki lub wgraniem a otwarciem jej
  strumienia. Zdarza się także, gdy gra tylko jeden inny strumień (`gap`: zamknięcie 13–14 s po pierwszym
  strumieniu, gdy druga karta ładowała bibliotekę).
- Żaden wariant nie daje stabilnego N = 3; dłuższy odstęp i oszczędny POST nie pomagają, a raczej pogarszają.
  Czas łączny przy N = 3: 171–201 s (dłuższy w wariantach z odstępem).
- Po każdym przebiegu konto czyste: głos i tempo jak przed, zero nowych importów, `session.json` bez zaległych kroków.

### Wniosek

Limit zostaje 2. Udane 3 karty w EDP z 2026-10-29 najpewniej wynikały ze stanu serwera, nie z kodu; ten sam raport
EDP odnotował 2026-10-19 zamknięcie strumienia już przy 2 kartach. Niezbadane różnice to pkt 2 (wgrywanie z jednej
stałej karty, bez ładowania biblioteki w karcie nagrania) i pkt 6 (długie dokumenty). Sprawdzenie pkt 2 wymaga
zmiany w hubie (stała karta biblioteki do startów); bez niej nie da się tego zmierzyć skryptem.
