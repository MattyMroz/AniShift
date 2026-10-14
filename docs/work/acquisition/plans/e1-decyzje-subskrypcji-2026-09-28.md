---
kind: plan
status: zastąpione
superseded_by: plans/e1-przeplyw-subskrypcji.md
updated: 2026-09-28
parent: plans/e1-heurystyka-wyszukiwarka-weryfikator.md
---

# Decyzje: dwie heurystyki i pobieranie w subskrypcji

**Zastąpione przez [e1-przeplyw-subskrypcji.md](e1-przeplyw-subskrypcji.md)** (zaakceptowany); zmiany w dokumentach i odpowiedzi Q-1..Q-3 rozlicza jego §7. Treść poniżej jest zapisem historycznym.

Zapis rozmowy z właścicielem z 2026-09-28. Status „propozycja”: przed wpisaniem do
`spec.md` i planu przechodzi pętlę krytyki `astra` ↔ orkiestrator aż do konsensusu.

## D-1. Dwie heurystyki o rozłącznych rolach

| | Heurystyka 1 — wyszukiwarka | Heurystyka 2 — korekta po pobraniu |
| --- | --- | --- |
| Kiedy | przed pobraniem, zawsze (ręcznie i w subskrypcji) | po pobraniu, tylko przy automatycznym pobraniu z subskrypcji |
| Dane | nazwy plików, ścieżki, nazwa wydania, metadane katalogu | zawartość pliku: długość, strumienie, napisy, metadane kontenera |
| Wynik | uszeregowana lista kandydatów; każda pozycja to odcinek do pobrania | potwierdzenie albo odrzucenie pobranego pliku |
| Szybkość | natychmiast (ms) | nie może opóźniać przetwarzania: jeśli trwa ms — od razu; jeśli sekundy — w tle, bez blokowania kolejki |
| Zakres w czasie | teraźniejszość | nie działa wstecz: nie ocenia starych ani ręcznie pobranych plików |

Heurystykę 1 rozlicza się wyłącznie z tego, co da się wiedzieć przed pobraniem.
Przypadek, w którym prawda leży w zawartości pliku (rozjazd numeracji katalog vs
wydawca: NEET Kunoichi, Saiki K., Owarimonogatari; remake o identycznym tytule), jest
domeną heurystyki 2 i nie jest błędem heurystyki 1. Osobnej kategorii etykiet nie
dodajemy; w ocenie takie rekordy są oznaczone jako „domena heurystyki 2”.

## D-2. Priorytet

Lepiej pobrać coś, co może okazać się złe, niż nie pobrać nic. Heurystyka 1 nie ma
być nadmiernie ostrożna; pomyłki koryguje heurystyka 2.

## D-3. Pobieranie w subskrypcji

1. Harmonogram emisji z katalogu wyznacza okno czasowe, w którym szukamy odcinka.
2. Jest kandydat `zgodny` → pobierz najlepszy z rankingu.
3. Brak `zgodnego` w oknie → czekaj i szukaj dalej według harmonogramu szukania
   (spec: co 15 min przez dobę, co godzinę do 3. doby, potem codziennie; po 7 dniach
   powiadomienie).
4. Po wyznaczonym czasie wolno pobrać najlepszy `niepewny` („najbardziej zgodny”),
   ale tylko jeśli:
   - numer odcinka w kandydacie wskazuje odcinek docelowy (nie inny odcinek);
   - kandydat nie jest odcinkiem już pobranym dla tej subskrypcji — system zapisuje,
     co pobrał (np. szukamy odcinka 2, wyszedł tylko 1 → nie pobieramy ponownie 1);
   - kandydat nie jest `niezgodny` (dodatki, kompilacje, inne odcinki nigdy).
5. Każde automatyczne pobranie przechodzi heurystykę 2.

Czas przejścia z kroku 3 do 4 — do ustalenia w pętli konsensusu.

## D-4. Testowanie

Na tytułach, które wychodzą teraz (w emisji, praktycznie 2021+), nie na starych
seriach. Heurystyka 1: metryki per odcinek dla 2021+, błędy tylko rodzaju „informacja
była w nazwie/metadanych”. Heurystyka 2: czas działania na realnych plikach i odsetek
złapanych przypadków z domeny heurystyki 2.

## Runda 1 konsensusu — krytyka `astra` (K-01..K-13) i odpowiedzi orkiestratora

| Punkt | Odpowiedź | Skutek dla decyzji |
| --- | --- | --- |
| K-01 | Przyjęte. Heurystyka 2 wykrywa sprzeczności strukturalne, nie potwierdza tożsamości. | Trzy wyniki: **brak sprzeczności** / **odrzucenie** / **nierozstrzygnięte**. `brak sprzeczności` nie zdejmuje oznaczenia „niepewne wydanie”. |
| K-02 | Przyjęte. | Kontrola asynchroniczna, ale **przed** dopuszczeniem tego odcinka do tłumaczenia/TTS; reszta kolejki pracuje dalej. Czas mierzymy na realnym uruchomieniu `ffprobe` na plikach. |
| K-03 | Przyjęte. D-2 to polityka decyzji pobrania, nie zmiana jakości klasyfikacji. | Bramka heurystyki 1 zostaje: 0 błędnych `zgodnych` wśród przypadków rozpoznawalnych z nazwy/metadanych. D6 obowiązuje. |
| K-04 | Przyjęte. | Twarde odrzucenie tylko przy długości konkretnego odcinka (`anizip.length`); przy średniej lub sprzecznych danych rozjazd = nierozstrzygnięte. |
| K-05 | Przyjęte. | Cel = wpis katalogu + lokalny klucz zwykłego odcinka; numeracja absolutna/sezonowa tylko przez jawne mapowanie. Fallback `niepewny` wymaga zgodności numeru w tej numeracji i braku jawnej sprzeczności dzieła, sezonu i rodzaju materiału; `12.5` ≠ E12. |
| K-06 | Przyjęte. | Każdy należny, niespełniony odcinek jest osobnym celem; termin uruchamia szukanie, nie przesuwa numeru; koniec emisji nie kończy szukania braków. |
| K-07 | Przyjęte. | „Najbardziej zgodny” = najwyżej w rankingu U-04 spośród dopuszczalnych `niepewnych`. Próg czasu i jego punkt odniesienia ustala właściciel; restart go nie zeruje. |
| K-08 | Przyjęte. | Stan rozdziela **cel odcinka** (oczekuje / w realizacji / spełniony) od **prób** (hash–plik, powód odrzucenia). Odrzucona próba nie spełnia celu; v2/REPACK nie podmienia przyjętego odcinka; batch uzupełnia tylko braki. |
| K-09 | Przyjęte. | Jeden budżet prób na cel, wspólny dla tożsamości i napisów; start: 2 pobrania (U-08). Błąd `ffprobe` ≠ odrzucenie. Usuwamy tylko własny, jednoznacznie odrzucony plik; przy niepewności plik zostaje. |
| K-10 | Przyjęte. | „Nie działa wstecz” = brak masowego skanowania Biblioteki. Kontrola przypisana do próby automatycznego pobrania przetrwa restart i usunięcie subskrypcji. Kontrole języka/napisów U-07/U-08 obowiązują też ręcznie. |
| K-11 | Przyjęte. | Trzy kontrole: korpus z osobnym wynikiem 2021+; subskrypcje na tytułach faktycznie w emisji (N-01); mała regresja starszych tytułów. Rok 2021 nie jest ograniczeniem produktu. |
| K-12 | Przyjęte. | Etykiety prawdy bez zmian; „domena heurystyki 2” jako adnotacja według kryteriów zamrożonych **przed** egzaminem; pełny raport z podziałem przyczyn; metryka per odcinek: czy wybrany kandydat był właściwy. |
| K-13 | Przyjęte. | Lista miejsc do zmiany rozszerzona w D-5. |

Pytania do właściciela (Q-1..Q-3):

1. Czy niepewne wydanie po kontroli bez sprzeczności dostaje lektora automatycznie i zostaje oznaczone jako niepewne, czy czeka na Twoją decyzję?
2. Czy odcinek może krótko poczekać na kontrolę przed tłumaczeniem/TTS (reszta kolejki pracuje)? Rekomendacja: tak.
3. Po jakim czasie od emisji pobrać dopuszczalny `niepewny`, jeśli nie ma `zgodnego`? Czy utrzymujemy limit 2 automatycznych pobrań odcinka i czy ten sam czas dotyczy zaległości nowej subskrypcji?

## Runda 2 — domknięcia (orkiestrator)

Runda 1 jest nadrzędna wobec pierwotnych D-1..D-4; po odpowiedziach właściciela
decyzje zostaną przepisane w jeden kontrakt.

- **K-03 (zmiana wymagania, jawnie):** bramka heurystyki 1 zmienia się względem D6:
  0 błędnych `zgodnych` liczymy wśród przypadków rozpoznawalnych z nazwy/metadanych;
  pozostałe raportujemy osobno z adnotacją „domena heurystyki 2”. To zmiana wymagania,
  do potwierdzenia przez właściciela (Q-1).
- **K-04:** twarde odrzucenie z powodu długości tylko przy `anizip.length` konkretnego
  odcinka i gdy katalog nie sygnalizuje innych granic odcinka (np. dwa odcinki katalogu
  → ten sam numer TVDB); odcinkowy `anizip.runtime` i średnia AniList → rozjazd =
  nierozstrzygnięte. Brak strumienia wideo → odrzucenie zawsze.
- **K-06:** zmiana daty emisji → przelicz termin celu; konflikt harmonogramu z
  mapowaniem → odśwież dane, cel „nierozstrzygnięty”, bez przesuwania numeracji.
- **K-09:** usunąć wolno tylko plik odrzucony, własny i nieużywany przez inne zlecenie
  ani przetwarzanie. Wyczerpanie budżetu jest trwałe — kolejne sprawdzenia go nie zerują.
- **K-12:** pomiar heurystyki 2 na realnych plikach: błędne przyjęcia, błędne odrzucenia,
  nierozstrzygnięcia, błędy narzędzia, czas.
- **K-13 — tabela reakcji:**

| Wynik kontroli | Reakcja |
| --- | --- |
| brak sprzeczności, kandydat `zgodny` | cel spełniony, przetwarzanie |
| brak sprzeczności, kandydat `niepewny` | zależnie od Q-1 |
| odrzucenie | usuń plik (warunki K-09), następny kandydat w budżecie |
| nierozstrzygnięte | zależnie od Q-1; plik zostaje |
| błąd kontroli | plik zostaje, eskalacja, budżet nie maleje |
| wyczerpanie budżetu | plik zostaje, problem widoczny dla właściciela, bez ponawiania |

Doprecyzowane pytania do właściciela:

- **Q-1:** Kontrola po pobraniu nie dowodzi tożsamości. Dla wydania `niepewnego` z wynikiem
  „brak sprzeczności” oraz dla wyniku „nierozstrzygnięte”: lektor automatycznie (plik
  oznaczony jako niepewny, cel spełniony, szukanie kończy się), czy czekać na Twoją decyzję?
- **Q-2:** Czy konkretny odcinek czeka na wynik kontroli przed tłumaczeniem/TTS, a reszta
  kolejki pracuje dalej? (Czas kontroli zmierzymy.)
- **Q-3:** Po jakim czasie pobrać dopuszczalny `niepewny`, gdy brak `zgodnego`? Zegar liczy
  od znanej emisji, a bez daty — od chwili, gdy odcinek jest należny (U-15). Czy przy
  zaległościach nowej subskrypcji czas sprzed jej dodania już się liczy? Czy limit
  2 automatycznych pobrań odcinka zostaje?

## D-5. Do zmiany w dokumentach po konsensusie

- `spec.md`: U-03, U-08, U-11, U-14–U-16; R-04, R-06, R-07; P-07; S-02, S-14; stany §5.5;
  inwarianty; §14/N-02.
- `plans/e1-wybor-odcinka.md`: D6; `plans/e1-heurystyka-wyszukiwarka-weryfikator.md`: H-3–H-5, K-3/K-5/K-6.
- `README.md` §3 i `ux.md`: niepewne wydanie, kontrola w toku, odrzucenie, wyczerpanie prób.
- Tabela reakcji: `brak sprzeczności` / `odrzucenie` / `nierozstrzygnięte` / błąd kontroli / wyczerpanie prób.

### Pierwotna lista D-5 (przed rundą 1)

- `spec.md`: cel „0 błędnie uznanych za zgodne” zastąpić podziałem odpowiedzialności
  D-1 i priorytetem D-2; dopisać regułę D-3.
- `plans/e1-heurystyka-wyszukiwarka-weryfikator.md`: bramki K-3/K-5/K-6 zgodnie z D-1,
  D-4 i pomiarem czasu heurystyki 2.
