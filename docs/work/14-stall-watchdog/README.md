# 14-stall-watchdog

Ogólny strażnik utknięć: każdy materiał, który stoi w dowolnym miejscu przepływu rezydenta (pobranie, przekazanie do Auto, zlecenie, przeniesienie do `ready/`), wywołuje po ustalonym czasie widoczny sygnał dla właściciela. Powód powstania: 24.10 dwa pobrane odcinki (acquisition `6b04ba6aa3563210` i `d0b6dd57500f884f`) leżały w `workspace/` dwa dni bez zlecenia, błędu i powiadomienia. Przyczynę bada osobny workstream; ten nie zależy od jej wyniku.

Status: projekt gotowy do decyzji właściciela (progi D1-D7), kodu jeszcze nie ma.

| Plik | Zawartość |
|---|---|
| [specification.md](specification.md) | definicja utknięcia dla każdego etapu, progi z danych, kanały sygnału, nie-cele, kryteria sukcesu, decyzje do rozstrzygnięcia |
| [plan.md](plan.md) | pliki, kontrakty, algorytm skanu, testy (unit/integration), fazy, bramki, branch `work/application/01-stall-watchdog`, commity |
| [reviews/round-1.md](reviews/round-1.md) | sceptyczne review planu, sześć poważnych znalezisk naniesionych w planie |

Kolejność czytania: specyfikacja, plan, review.

Po zatwierdzeniu: wykonawca realizuje plan, świeża instancja innej rodziny recenzuje diff (`AGENTS.md`, zasada krzyżowa). Wpis w tabeli `docs/README.md` dodaje wykonawca przy PR.
