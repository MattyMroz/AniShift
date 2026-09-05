---
kind: plan
status: pending-human
baseline: c2e89964a4dd7d0a8efcdefacf2a7db609ec81e8
created: 2026-09-04
---

# Plan 02 — wykonanie zatwierdzonego programu napraw

## Rezultat i zgoda

Po Planie 01 realizujemy naprawy istniejącego produktu z audytu, nie przepisanie
aplikacji. Właściciel zatwierdził całość i osobno naprawy utils oraz rozszerzenie
strażnika testów. Branch integracyjny: `work/reliability/01-hardening`.
Właściciel zatwierdził lokalne commity tematyczne; bez push, issue, PR i merge.

## Granice równoległej pracy

| Właściciel | Zmiany | Dowód |
| --- | --- | --- |
| Integrator | A01–04, A15–17, UI, reflow, style, dokumenty i integracja | Niepełny wynik nie przechodzi; retry/split, klawiatura, pomiary renderera |
| Config / utils | A18–19, A21–24, Q01/Q10 | Złe dane, atomic replace, prawdziwy JSONL i filtry, audyt locka |
| Lifecycle | A09, A11–13, następnie A20 | Cichy proces i EOF, kill, niezależne grupy, przygotowanie narzędzi |
| Media | A05–08, A10, następnie A14 | Rzeczywisty FFmpeg, pełna długość audio/wideo, apostrof, callbacks |

Wykonawcy pracują w osobnych worktree. Wspólne pliki i rozszerzenia callbacków
są uzgadniane; integrator czyta diff i ponawia testy po połączeniu. Brak merge
gałęzi lub commitów nie oznacza braku integracji zmian w bieżącym drzewie.

## Kolejność

1. Odrzucanie niepełnego produktu oraz brak poprawnego końca odpowiedzi modelu.
2. Konfiguracja, instalacja, deadline, cancel i niezależność publikacji grup.
3. Integralność napisów i mediów, potem pomiar postępu przez istniejące API.
4. Jeden renderer, jedna paleta, wynik awarii i koszt animacji poza klawiszami.
5. Naprawa portable utils, skrócenie opisów i strażnik bez prose w testach.
6. Pełne gates, małe jawne próby sieciowe, rzeczywiste media, niezależne review.

Po wykryciu własnej regresji wracamy do najmniejszej dotkniętej granicy. Nie
zmieniamy providerów ani zapisanych kluczy/preferencji. Zależności aktualizujemy
narzędziem uv, nie ręczną zmianą pliku projektu. Żadne źródłowe media nie są usuwane.

## Kontrakty implementacyjne

- Brak terminalnego finish reason oznacza niekompletną odpowiedź; limit tokenów
  nadal uruchamia istniejący podział. Błąd SSE jest mapowany bez ujawniania payloadu.
- Provider resetuje postęp przed każdym requestem; liczone są zamknięte `[N]`
  należące do bieżącej próby. Naprawa kontraktu zachowuje wcześniej poprawne linie.
- Progress event może nie mieć procentu wyłącznie przy nazwanej aktywności.
  Pomiar FFmpeg/MKVToolNix trafia do jednego wiersza, 100% dopiero po walidacji.
- Długie renderowanie ma osobny skończony deadline. Brak EOF lub zamknięty stdout
  nie pozwalają ominąć anulowania/deadline. Zablokowana publikacja nie zatrzymuje
  koordynowania innych grup i nadal sprawdza generation/cancel przed replace.
- Logger zachowuje format Loguru i portable API. Wszystkie zapisane pola wraz
  z tracebackiem muszą przejść test sekretów i bezwzględnych ścieżek.
- Skracanie docstringów nie może zmienić wykonywalnego AST ani usunąć separatorów.
  Zmiany zachowania i zmiany opisów mają osobne dowody.

## Weryfikacja i warunki wyjścia

Regresje najpierw FAIL, potem PASS. Na połączonym drzewie uruchomić Ruff check,
format check, mypy Windows/Linux, pełny pytest i oba hooki. Dodatkowo: krótki
FFmpeg z ogonem narracji i apostrofem, stdout-EOF deadline, zapis→odczyt JSONL,
małe żądania Google/DeepL bez drukowania kluczy, audyt konkretnych wersji locka.
Pomiar UI rozdziela konstrukcję renderera, kodowanie obrazka i czyste klatki;
nie nazywa samego benchmarku klatki pomiarem latencji fizycznego terminala.

Odsłuch, naturalność całego odcinka i subiektywny wygląd wymagają właściciela.
Watcher, przeciąganie plików i pobieranie odcinków pozostają przyszłym zakresem.
TXT→audiobook ma oddzielny etap M09, nie jest efektem ubocznym naprawy napisów.
Wyniki i pozostałe ograniczenia zapisać w outcome oraz na tablicy.

Implementacja i automatyczne kontrole opisane są w [outcome](../outcomes/02-hardening.md).
Odsłuch, fizyczny terminal oraz brakujące dowody M08 przechodzą do
[Planu 03](03-product-acceptance.md); nie są oznaczone jako ukończone.
