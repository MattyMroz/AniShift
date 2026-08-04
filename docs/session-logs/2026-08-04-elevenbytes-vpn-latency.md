---
kind: session
date: 2026-08-04
topic: elevenbytes-vpn-latency
status: done
---

# Integracja ElevenBytes z 1VPN działa, ale pierwszy wynik pełnego anime dociera za późno

## Podsumowanie

ElevenBytes został połączony z natywnym transportem 1VPN, domyślnie włączonym i bez fallbacku na lokalne IP. Limit VPN ustawiono na 100, a postęp panelu rozszerzono o odpowiedź providera przed walidacją i commitem klipu. Prawdziwy smoke test całego odcinka potwierdził jednak, że panel nie jest źródłem około 48-sekundowej ciszy: pierwszy callback z providera rzeczywiście dociera dopiero po tym czasie.

## Kluczowe wnioski / decyzje

- Transport VPN jest częścią silnika w `anishift/services/tts/engines/elevenbytes/vpn.py`, a nie monkey patchem. Używa 17 publicznych serwerów 1VPN, trwałych pul `httpx`, failoveru między trasami i nie wraca do lokalnego połączenia.
- VPN jest domyślnie włączony. Profil ElevenBytes oraz panel ograniczają liczbę workerów do 100 i pokazują `100 (VPN limit)`.
- Pasek postępu nie czeka już na zapis i pełną walidację klipu. Scheduler wywołuje `on_result` po otrzymaniu pełnej odpowiedzi providera, a `SpeechBatchProgress.received_required_requests` trafia do panelu. Panel liczy pierwszy wynik `1/336` jako `1%` i utrzymuje maksimum, żeby pasek nie cofał się.
- Test jednostkowy potwierdził, że callback providera występuje przed blokującą walidacją, ale sam test jednostkowy nie wyjaśniał zachowania produkcyjnego. Dlatego wykonano realny test całego `[shisha] Youjo Senki II - 01.mkv` przez `run_pipeline(...)`, bez UI i z pustym cache.
- Realny pomiar pełnego pipeline, VPN `True`, workers `100`, cache `0`, 336 requestów:
  - start batcha TTS: `23:09:05.564`;
  - pierwsza odpowiedź providera i odpowiadające jej widoczne `1%`: `23:09:54.081`, czyli **48,517 s od startu TTS**;
  - pierwszy commit klipu: `23:09:54.136`, tylko **55 ms po odpowiedzi providera**;
  - 100/336 odpowiedzi: `tts+57,873 s`;
  - 336/336 odpowiedzi: `tts+75,273 s`;
  - koniec audio i pipeline TTS: `tts+78,240 s`;
  - pipeline faktycznie zakończył się stanem `done`. Harness zwrócił kod 1 dopiero po sukcesie przez błąd w jednorazowym wydruku podsumowania (`FileOutcome` nie ma pola `path`); nie był to błąd pipeline.
- Wniosek z realnego pomiaru: **Rich/panel nie laguje i walidacja audio nie powoduje początkowej ciszy**. Około 48,5 s powstaje przed pierwszą odpowiedzią HTTP w backendzie/VPN albo niżej w runtime sieciowym.
- Kontrola na oryginalnym `C:/Users/MattyMroz/Desktop/PROJECTS/TTS/elevenbytes/one_vpn.py` wykonała 100 requestów z `--parallel 6`: pierwszy wynik po **4,2 s**, 100/100 po **13,7 s**, bez błędów. Uruchomienie używało jego własnego Pythona 3.13.11.
- Bezpośrednie wywołanie obecnego `ElevenBytesApiBackend` z AniShift na 100 tych samych krótkich tekstach odtworzyło problem: pierwszy wynik po **46,029 s**, 25/100 po **73,055 s**, następnie `httpx.RemoteProtocolError` (`incomplete chunked read`) oraz ostrzeżenie `coroutine ... try_connect was never awaited`.
- Środowiska różnią się interpreterem, ale nie wersjami HTTP:
  - AniShift: Python 3.14.2, `httpx 0.28.1`, `httpcore 1.0.9`;
  - działający projekt TTS: Python 3.13.11, `httpx 0.28.1`, `httpcore 1.0.9`.
- To jest mocny trop, nie potwierdzony root cause. Bezpośredni test backendu nastąpił po setkach wcześniejszych requestów, więc możliwe jest również chwilowe przeciążenie tras/provider throttling. Rozstrzygający test niezmienionego `one_vpn.py` interpreterem AniShift 3.14 został rozpoczęty, ale świadomie zatrzymany na prośbę użytkownika przed wynikiem.
- `VpnTransport` w AniShift jest funkcjonalnie niemal identyczny z prostym transportem z `one_vpn.py`. Istotna zamierzona różnica to `parallel=6` i globalny cap 100 zamiast domyślnego `parallel=5`/85.
- Nie wracać do prób sterowania interaktywnym panelem przez wysyłanie Enter ani do screenshotów. Najlepszy pomiar to bezpośrednie `run_pipeline(...)` z własnym `PipelineTtsProgressSink` i monotonicznymi timestampami.

## Stan

- ✅ zrobione:
  - natywny transport 1VPN dla ElevenBytes;
  - domyślne routowanie VPN bez ujawniania lokalnego IP;
  - limit 100 w kodzie, panelu i lokalnym `config/settings.json`;
  - callback postępu po odpowiedzi providera, przed walidacją klipu;
  - testy jednostkowe i integracyjne nowych zachowań;
  - realny smoke całego anime z 336 syntezami;
  - porównanie z oryginalnym `one_vpn.py` dla 100 requestów.
- 🔄 w toku:
  - ustalenie, dlaczego ten sam wzorzec HTTP jest szybki w projekcie TTS, a wolny w AniShift.
- ⛔ zablokowane / czeka na:
  - dokończenie kontrolowanego A/B na tym samym interpreterze i przy porównywalnym obciążeniu tras.

## Artefakty

- Branch: `bugfix/elevenbytes-vpn-latency`.
- Główne pliki implementacji:
  - `anishift/services/tts/engines/elevenbytes/vpn.py`;
  - `anishift/services/tts/engines/elevenbytes/api_backend.py`;
  - `anishift/services/tts/scheduler.py`;
  - `anishift/services/tts/service.py`;
  - `anishift/services/tts/types.py`;
  - `anishift/pipeline/tts_runtime.py`;
  - `anishift/cli/pipeline_ui.py`;
  - ustawienia w `anishift/config/user_settings.py`, `anishift/cli/settings_panel.py` i `anishift/cli/tts_settings.py`.
- Testy dotyczące zmiany znajdują się w `tests/services/tts/`, `tests/pipeline/test_tts_runtime.py`, `tests/cli/` i `tests/config/test_user_settings.py`.
- Ostatnie pełne bramki jakości po zmianach kodu: Ruff check OK, Ruff format check OK, mypy OK, pytest **1668 passed, 8 skipped, 15 warnings**.
- Pierwsze równoległe uruchomienie bramek miało jeden przejściowy fail `test_service_stops_timer_after_batch_completion` z komunikatem `TTS service is closed`. Test uruchomiony osobno przeszedł, a następujący po nim pełny pytest również przeszedł 1668/1668. To potencjalny flake lifecycle, nie odtworzony ponownie.
- Runtime smoke utworzył ignorowane artefakty resume w `workspace/tmp`; nie są częścią commita.
- `scripts/one_vpn_production.py` pozostaje lokalnym, untracked plikiem i zgodnie z decyzją użytkownika nie jest częścią commita.
- Niepowiązane, istniejące wcześniej pliki dokumentacyjne oraz `docs/plans/_index.md` celowo nie należą do tego zadania i nie powinny wejść do jego commita.

## Root cause i poprawka

Kontrolowane A/B tym samym skryptem (100 requestów, `parallel=6`) rozstrzygnęło sprawę.
Przebieg na 3.14 wykonano PRZED przebiegiem na 3.13, żeby wykluczyć throttling.

| pomiar | py3.14.2 (AniShift) | py3.13.11 (TTS) | py3.14.2 po poprawce |
| --- | --- | --- | --- |
| pierwszy wynik | 58,49 s | 2,25 s | 0,85 s |
| 100/100 | 65,93 s | 18,23 s | 9,77 s |
| max lag pętli zdarzeń | 22 885 ms | 755 ms | 50 ms |
| `ConnectTimeout` | 152 | 7 | 6 |

Sampling stosu wątku głównego w trakcie zastoju wskazał jedno miejsce:
`httpcore/_async/connection.py:_connect` → `httpcore/_ssl.py:default_ssl_context`.

`httpx.AsyncHTTPTransport(proxy="https://...")` zostawia `proxy_ssl_context=None`, więc
httpcore dla KAŻDEGO połączenia do proxy buduje nowy `ssl.SSLContext` i parsuje cały
CA bundle certifi — synchronicznie, na event loopie. Koszt jednego wywołania:
**243,7 ms** przy OpenSSL 3.0.18 (Python 3.14) wobec **15,1 ms** przy OpenSSL 3.5.4
(Python 3.13). 17 pul × do 6 połączeń plus failovery dało 316 prób ≈ 77 s blokady.
Zagłodzona pętla powodowała, że 8-sekundowy connect timeout zgłaszał się po 25-52 s,
co wywoływało kolejne failovery i kolejne konteksty — pętla dodatniego sprzężenia.

Root cause to więc powtarzane budowanie kontekstu TLS, a nie Python 3.14; wersja
interpretera zmieniała tylko koszt jednostkowy przez inny build OpenSSL.

Poprawka w `vpn.py`: jeden `ssl.SSLContext` budowany raz (`@cache`) i przekazywany do
wszystkich pul jako `proxy=httpx.Proxy(ssl_context=...)` oraz `verify=`.

## Wynik po poprawce

- Bezpośredni `ElevenBytesApiBackend`, 100 requestów, VPN: pierwszy wynik **0,71 s**
  (przedtem 46,03 s), 100/100 w 10,84 s, max lag pętli 29 ms, zero błędów.
- Realny zimny smoke całego `[shisha] Youjo Senki II - 01.mkv` przez `run_pipeline(...)`
  w izolowanym workspace (`ANISHIFT_WORKSPACE_ROOT`, twardy link do MKV, resume
  użytkownika nietknięty), 336 requestów, `provider_calls=336`, `resume_hits=0`:
  - pierwsza odpowiedź providera: **tts+1,16 s** (przedtem 48,52 s);
  - pierwszy commit klipu: tts+1,22 s, czyli 60 ms po odpowiedzi;
  - 336/336 odpowiedzi: **tts+12,16 s** (przedtem 75,27 s);
  - koniec audio: tts+15,16 s (przedtem 78,24 s);
  - 0 retry, 0 błędów, status `done`.
- Ten MKV ma jedyną ścieżkę napisów w `pol`, więc pipeline pomija tłumaczenie — tak
  samo jak w pomiarze bazowym.
- Bramki jakości: ruff check OK, ruff format OK, mypy OK, pytest **1669 passed, 8 skipped**.
- Regresję pilnuje `test_vpn_transport_shares_one_prebuilt_tls_context`; pułapka
  opisana w `anishift/services/tts/engines/elevenbytes/AGENTS.md`.

## Czego NIE robić

- Nie poprawiać dalej renderowania paska: callback panelu jest szybki, problem był przed nim.
- Nie uznawać samego testu jednostkowego ani smoke 10 requestów za dowód poprawy pełnego anime.
- Nie uruchamiać dwóch instancji AniShift jednocześnie i nie wysyłać automatycznie Enter do terminala użytkownika.
- Nie usuwać ani nie nadpisywać artefaktów użytkownika; do świeżego smoke użyć osobnego
  workspace przez `ANISHIFT_WORKSPACE_ROOT` i zachować możliwość resume.
- Nie zostawiać żadnej puli proxy bez jawnego `ssl_context` — to wraca dokładnie tym samym błędem.
