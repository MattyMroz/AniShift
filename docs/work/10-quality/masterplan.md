# Jakość wyniku: masterplan

Status: zaakceptowany kierunek właściciela (2026-10-17). Kontrakt: [specification.md](specification.md).

Szczegółowo planowany jest tylko bieżący etap. Każdy kolejny dostaje własny plan w `plans/` dopiero po wyniku poprzedniego.

| Etap | Rezultat | Dowód poprawy | Issue |
| --- | --- | --- | --- |
| 0 | Baza testowa: napisy (i część pełnych odcinków) z bogatym typesettingiem, narzędzie pomiaru i galeria zrzutów najgorszych przypadków | metryki stanu obecnego dla etapów 1–5, zrzuty pokazane właścicielowi | #46 |
| 1 | Szyldy: polski szyld mieści się w ramce oryginału i na ekranie, nie nachodzi na inne | mniej szyldów poza ramką i ekranem; zrzuty przed i po | #22, #23 |
| 2 | Podział dialog / szyld: lektor nie czyta szyldów i nie gubi kwestii | mniej błędnie zaklasyfikowanych linii na oznaczonych przypadkach z bazy | #16, #47 |
| 3 | Granice stylów po tłumaczeniu: kursywa, kolory i zmiany mówcy w jednej linii przetrwają tłumaczenie | linie, które straciły granice stylu = 0 na bazie | #34 |
| 4 | Polski podział wierszy: naturalne miejsca łamania, właściwy kształt i długość linii | mniej linii za długich i źle złamanych wg reguł z researchu | #22 |
| 5 | Czasy wyświetlania polskich napisów (hipoteza właściciela): dłuższy polski tekst nie znika za szybko | najpierw sprawdzenie hipotezy na danych; zmiana tylko, jeśli dane ją potwierdzą | — |
| 6 | Głośność lektora dopasowana do głośności materiału: ani za głośno, ani niesłyszalnie | rozrzut głośności lektora względem oryginału mniejszy na bazie | — |
| 1–4 v2 (bieżący) | Rozmyte heurystyki szyldów, lektora, stylów i łamania na pomiarze prawdziwą czcionką; czcionka dialogów właściciela w MKV; czcionki przy wypalaniu MP4. Cel: [visual-quality.md](visual-quality.md), plan: [plans/01-fuzzy-layout-and-fonts.md](plans/01-fuzzy-layout-and-fonts.md) | galeria przed/po na tym samym tekście, ocena orkiestratora i właściciela; test regresji pomiaru wobec libass | #16, #22, #23, #34 |

## Zasady przejścia

- Etap kończy się outcome'em w `outcomes/<nn>-<slug>.md`: metryki przed i po, zrzuty, decyzja właściciela.
- Pogorszenie na bazie testowej oznacza powrót do planu etapu, nie przejście dalej.
- Heurystykę każdego etapu proponują niezależnie co najmniej dwa modele (astra, opus55, argon); przegląda ją model inny niż autor. Każdy błąd znaleziony po drodze trafia do testów.
- Zmiana kolejności jest dozwolona, jeśli pomiar pokaże inny największy problem. Wtedy aktualizuję ten plik i pytam właściciela.

## Poza tym planem

Odrzucone albo odłożone 2026-10-17: glosariusz postaci, przyspieszanie lektora, ściszanie oryginału pod lektorem, formalny arkusz ocen z trzech odcinków, piosenki OP/ED (wpis w `docs/ideas.md`). Napisy wychodzące w czarne pasy na ultrawide okazały się ustawieniem mpv (`sub-ass-force-margins = no`), nie błędem AniShift. 2026-10-18 właściciel przywrócił własny font dialogów do zakresu: styl ASS ma pierwszeństwo przed `sub-font` mpv, więc podmiana musi nastąpić w AniShift (etap 1–4 v2).
