# Jakość wyniku: masterplan

Status: projekt do akceptacji właściciela (2026-10-15). Kontrakt: [specification.md](specification.md).

Szczegółowo zaplanowany jest tylko etap 0. Każdy kolejny etap dostaje własny plan w `plans/` dopiero po wyniku poprzedniego.

| Etap | Rezultat | Metryka automatyczna | Ocena właściciela | Ponawia |
| --- | --- | --- | --- | --- |
| 0 | Wzorzec: 3 odcinki, arkusz ocen, narzędzie pomiaru, pomiar bazowy | wszystkie metryki z tabeli niżej, zapisane jako baseline | arkusz bazowy dla 3 odcinków | — |
| 1 | Glosariusz postaci z AniList (pisownia, płeć, rola), mówca linii z pola `Actor` i oznaczenie szyldów w prompcie | niespójne pisownie imion z glosariusza = 0; średnia długość szyldów krótsza | imiona i rodzaj gramatyczny lepsze | tłumaczenie |
| 2 | Kategoria „piosenka”, znaczniki `SIGN`/`SFX`/`Text` z pola `Actor` jako sygnał szyldu i niepewne linie nie wypadają po cichu | linie OP/ED i karaoke w `spoken` = 0; niepewne linie poza lektorem i napisami = 0 | lektor nie czyta piosenek ani szyldów i nie gubi kwestii | podział + lektor |
| 3 | Miks: ducking oryginału pod lektorem i przyspieszanie pojedynczych długich kwestii (z limitem tempa) | p95 opóźnienia lektora (`drift_ms`) niższe o ≥ 50%; kwestii z opóźnieniem > 1,5 s mniej | lektor słyszalny, oryginał nie ginie, lektor nie zostaje w tyle | lektor |
| 4 | Szyldy mieszczą się w ramce przy dłuższym polskim tekście i w aktywnym obszarze obrazu (#23) | szyldy z `\pos` lub `\clip` wychodzące poza ramkę: ≥ 85% mniej | szyldy czytelne, nic nie wychodzi poza kadr | tłumaczenie (zapis ASS) |

## Metryki etapu 0

Liczone dla każdego odcinka narzędziem z etapu 0, bez ingerencji w kod produkcyjny:

- **Imiona:** liczba różnych pisowni każdej postaci z AniList w polskim wyniku.
- **Lektor:** liczba linii czytanych przez lektora, które mają pozycję (`\pos`, `\move`, `\an7–9`), styl szyldu albo tag karaoke, oraz linie w oknie OP/ED.
- **Gubione linie:** liczba linii `UNCERTAIN`, które nie trafiły ani do lektora, ani do napisów.
- **Opóźnienie lektora:** `drift_ms` z osi czasu: p50, p95, maksimum, liczba kwestii powyżej 1,5 s.
- **Szyldy:** stosunek długości tekstu polskiego do źródła dla szyldów z `\pos` lub `\clip`; liczba szyldów powyżej 1,15.

## Zasady przejścia

- Etap kończy się outcome'em w `outcomes/<nn>-<slug>.md`: metryki przed i po, arkusz właściciela, decyzja.
- Pogorszenie na którymkolwiek odcinku wzorca oznacza powrót do planu etapu, nie przejście dalej.
- Zmiana kolejności etapów jest dozwolona, jeśli pomiar bazowy pokaże inny największy problem. Wtedy aktualizuję ten plik i pytam właściciela.

## Powiązane issue

- [#46](https://github.com/MattyMroz/AniShift/issues/46) i [#44](https://github.com/MattyMroz/AniShift/issues/44): etap 0;
- [#16](https://github.com/MattyMroz/AniShift/issues/16) i [#34](https://github.com/MattyMroz/AniShift/issues/34): etap 2;
- [#22](https://github.com/MattyMroz/AniShift/issues/22) i [#23](https://github.com/MattyMroz/AniShift/issues/23): etap 4;
- [#47](https://github.com/MattyMroz/AniShift/issues/47): po etapie 2.
