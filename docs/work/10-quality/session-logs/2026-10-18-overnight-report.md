# Raport nocny 17/18.10.2026: jakość napisów

Dla właściciela. Co zrobione, jak, gdzie i dlaczego, plus decyzje, które czekają na Ciebie.

## W skrócie

1. **W `main` i na GitHubie:** poprawka rozjechanego lektora (Nia Liston S01E02), z dokładnością do próbki audio. W mpv włączone `sub-ass-force-margins = no` (ultrawide).
2. **Zrobione nocą, nie w `main`:** narzędzie pomiaru jakości, poprawki szyldów, podziału dialog/szyld, granic stylów, łamania wierszy i #47. Wszystko leży na gałęzi integracyjnej `work/quality/06-integration`, testy przechodzą (2143). Czeka na Twoją ocenę.
3. **Pomiar przed/po:** szyldy mniejsze, zero nowych kolizji, kursywa i kolory na właściwych słowach. Za długich wierszy jest więcej, ale winne jest dłuższe nowe tłumaczenie, nie kod. Sprawdzono to osobnym testem A/B.
4. **Twoje uwagi o sztywnych regułach były trafne.** Audyt znalazł 25 ostrych progów, a kilka z nich gubi kwestie albo psuje szyldy. Powstały dwie specyfikacje „rozmyte”: najmniejsze zło zamiast sztywnych limitów. Przeszły przegląd agentów w kilku rundach (kto co zaakceptował: punkt 5). **Kodu według nich jeszcze nie ma**, bo najpierw musisz je zaakceptować Ty.
5. **Na Ciebie czekają decyzje** z ostatniej sekcji. Każda ma rekomendację, wystarczy „tak” albo „nie”.

## 1. Lektor rozjechany z oryginałem (w `main`, wypchnięte)

- **Co:** lektor w Nia Liston S01E02 był przesunięty względem oryginalnego audio.
- **Dlaczego:** ścieżka audio w tym MKV zaczyna się później niż obraz (`minimum_timestamp`). Przy miksie gubiliśmy to przesunięcie. ffprobe podaje dla MKV niewiarygodny `start_time`, dlatego czytamy wartość z mkvmerge.
- **Jak:** przesunięcie jest liczone w próbkach audio (`adelay=<n>S`), więc dokładność wynosi 1/48000 s, a nie milisekundę. Zmienił się „odcisk” miksu, więc stare miksy przeliczą się same.
- **Gdzie:** `anishift/services/media/`, `application/planner.py`, `services/audio/`; commity `fe8b743`, `067e3c1`. Odcinek wygenerowałeś i sprawdziłeś.

## 2. Narzędzie pomiaru i baza testowa (etap 0)

- **Co:** `scripts/quality/` mierzy szyldy (szerokość względem oryginału, wyjście poza ekran, kolizje), granice stylów, łamanie wierszy i CPS. Robi też galerię najgorszych przypadków.
- **Jak:** renderuje każdy napis przez libass, czyli tak jak mpv. Klatki tła są zapisane jako JPG, więc MKV nie są potrzebne. Testowe MKV usunąłem za Twoją zgodą.
- **Gdzie:** kod na `work/quality/01-test-corpus` (commity `17827f9`…`b0feb97`). Dane (gitignored) w `workspace/.quality/`: 19 par z Twojej biblioteki i 21 par z korpusu (Grand Blue S2, Kaguya, First Kiss, Joshiraku, Uzaki, A Certain Dark Item od Shishy).
- **Dlaczego:** bez stałej bazy nie da się powiedzieć, czy zmiana poprawia, czy psuje.

## 3. Poprawki zrobione nocą (gałąź `work/quality/06-integration`)

Każdą poprawkę napisał jeden model, a przejrzał inny.

| Obszar | Co się zmieniło | Efekt na bazie | Commit |
|---|---|---|---|
| Szyldy (#22, #23) | polski szyld zmniejszany proporcjonalnie do szerokości oryginału, z dzieleniem na dwa wiersze | za szerokie szyldy 53 → 6 na tym samym tekście, nowe kolizje 4 → 0 | `c548f73` |
| Dialog / szyld (#16) | decyzja dla każdej linii, a nie tylko dla całego stylu: kwestia w stylu szyldów jest czytana, a szyld w stylu dialogu pomijany | 0 zgubionych kwestii na trzech zbiorach | `88c3a40` |
| Granice stylów (#34) | znaczniki `<s1>…</s1>` dla tłumacza, więc kursywa i kolor trafiają na to samo słowo po polsku | tag w środku słowa 60 → 0, zgubione zakresy 7 → 3 | `ecc7222` |
| Łamanie wierszy (#22) | cięcie po sensie: nie odrywa przyimka, nie rozdziela imienia i nazwiska, bez sierot | wiersze ponad 42 znaki 45 → 27, sieroty 0 | `f38e57d` |
| Pusty plik szyldów (#47) | SRT nie ma szyldów, więc program mówi to od razu, zamiast tłumaczyć na próżno | brak niepotrzebnych tłumaczeń | `ce1ae48` |

Przykład: napis stacji „Prywatny” przed/po, ×1,29 → ×0,98 szerokości oryginału, kolizja znika.

![Przed i po: szyldy w Seihantai](../../../../workspace/.quality/experiments/final/compare/06.png)

## 4. Pomiar końcowy: 13 odcinków przetłumaczonych od nowa

Raport: [final/report.md](../../../../workspace/.quality/experiments/final/report.md), 20 porównań przed/po: [compare/index.md](../../../../workspace/.quality/experiments/final/compare/index.md).

| | Przed | Po |
|---|---:|---:|
| Szyldy szersze o >10% od angielskich | 53 | 38 |
| Nowe kolizje szyldów | 4 | 0 |
| Zmieniona kolejność stylów (kursywa/kolor) | 55 | 0 |
| Tag stylu w środku słowa | 1 | 0 |
| Kwestie z wierszem ponad 42 znaki | 45 | 74 |
| Kwestie powyżej 17 znaków/s | 13,9% | 20,0% |

- **Dlaczego wierszy ponad 42 jest więcej:** 82% kwestii ma inny tekst, bo tłumaczenie powstało od nowa. Na kwestiach z identycznym tekstem jest 7 → 5. Osobny test A/B (stary i nowy kod, po dwa przebiegi na 3 odcinkach) pokazał, że nowy kod nie wydłuża tłumaczenia. Za długich wierszy daje nawet o połowę mniej: 16–17 zamiast 35–38. Stare polskie pliki w bibliotece są po prostu krótsze, niż dziś tłumaczy ten sam model. Najpewniej dostawca zmienił model.
- **Szyldy 38, a nie 6:** w pomiarze końcowym są nowe, dłuższe tłumaczenia, a obecna reguła ma podłogę 72%. Część szyldów nie może zejść niżej. Naprawia to specyfikacja z punktu 5.
- **Najgorszy przypadek:** w Iceblade S2E01 tytuł został po angielsku. Model raz zwrócił angielski tekst (w 3 z 4 przebiegów tłumaczył poprawnie). To losowość modelu, nie błąd kodu. Propozycja zabezpieczenia jest w decyzjach.

## 5. Audyt sztywnych reguł i specyfikacje rozmyte

**Dlaczego:** napisałeś, że limity to zalecenia, nie sztywne progi, i żeby wybierać najmniejsze zło. Sprawdziłem cały kod napisów: [rigidity-audit/report.md](../../../../workspace/.quality/experiments/rigidity-audit/report.md). Najgorsze klify:

- **Szyldy** mierzymy Arialem, a nie fontem odcinka. Błąd sięga 21%, a 42 szyldy trafiają przez to do złej gałęzi. Podłoga 72% wypycha szyldy poza ekran, choć mniejszy tekst byłby czytelny.
- **Dialog/szyld:** jeden znak średniej długości przestawia cały styl. W Joshiraku i Uzaki lektor gubi przez to „I'm sick of this.”, „Have a nice day.”, „Can it!”.
- **Łamanie:** reguła „43 znaki = zawsze dwa wiersze” tnie nawet tam, gdzie każde cięcie jest brzydkie.

**Jak:** obie specyfikacje stosują ten sam schemat. Najpierw ostre zakazy (nie poza ekran, nie na inny napis, nie ciąć wyrazu). Wśród dopuszczalnych wariantów wygrywa ten o najmniejszej łącznej szkodzie, a szkody są stopniowane: mało, średnio, dużo. Wzorce: Netflix PL (zalecenia), ręczne napisy Shishy (łamią po sensie, nie po kształcie, ok. 10% kwestii) i Twój wybór na zrzutach.

| Specyfikacja | Co rozwiązuje | Status |
|---|---|---|
| [fuzzy-line-breaks.md](../../../../../AniShift-wt/fuzzy-breaks/docs/work/10-quality/fuzzy-line-breaks.md) | łamanie polskich wierszy | autor astra; zaakceptowali opus55, argon, sol6 i Claude, commit `5aee750` |
| [fuzzy-signs-and-split.md](../../../../../AniShift-wt/fuzzy-breaks/docs/work/10-quality/fuzzy-signs-and-split.md) | dopasowanie szyldów, podział dialog/szyld, granice stylów | autor opus55; v3.2 zaakceptowali astra, sol6 i Claude; argon zaakceptował v2, ostatniej rundy nie oddał; commit `4851f62` |

Galerie z przypadkami granicznymi:

- łamanie: [36 przypadków](../../../../workspace/.quality/experiments/fuzzy-spec/cases/index.md);
- szyldy i podział: [a0–a10, b1](../../../../workspace/.quality/experiments/fuzzy-spec2/cases/index.md).

Przykład szyldu „Safety Hazard”, który dziś wychodzi za ekran. Specyfikacja wybiera wariant B, czyli ten, który sam wskazałeś:

![Warianty szyldu Safety Hazard](../../../../workspace/.quality/experiments/fuzzy-spec2/cases/a1-grand-blue-safety-hazard.png)

Wynik nowych reguł podziału na Twoich etykietach: wszystkie 425 kwestii czytane, 23 szyldy mniej czytane, 6 nowych szyldów czytanych.

## 6. Decyzje dla Ciebie

Rekomendacja jest pierwsza. Nic z tego nie trafi do `main` bez Twojego „tak”.

**Scalenie**

1. **Gałąź integracyjna do `main`?** Rekomenduję tak: wszystkie metryki poza długością tłumaczenia są lepsze, a długość ma osobną przyczynę. Najpierw obejrzyj 20 porównań.
2. **#47:** gdy plik to SRT, odcinek kończy się sukcesem z notką „brak szyldów”, a nie błędem. Rekomenduję tak.

**Tłumaczenie**

3. **Limit długości tłumaczenia** („nie dłużej niż angielski, chyba że jest czas”)? Ten limit naprawiłby resztę za długich wierszy i za szybkich kwestii. Zmienia sposób tłumaczenia, dlatego decyzja należy do Ciebie.
4. **Zabezpieczenie Iceblade:** jeśli model zwróci dłuższą linię bez zmian po angielsku, ponowić tylko tę linię? Rekomenduję tak, to mała zmiana.
5. **Etap 5, czasy napisów:** dane pokazały, że winne jest długie tłumaczenie, nie czasy. Wydłużenie końców naprawia tylko 21% za szybkich kwestii. Rekomenduję pominąć.

**Łamanie wierszy** (obrazy w galerii łamania)

6. Przypadki 03, 07, 33: przyjąć wybór modelu (B)?
7. Przypadek 28: przy braku miejsca wolno rozdzielić „Jan / Kowalski”, byle się zmieściło?
8. Przypadek 31: gdy za szeroki jest sam wyraz, zostawić go i zgłosić w raporcie?
9. Przypadek 18: przyjąć cięcie po przecinku (A), bez specjalnej reguły na wtrącenia?
10. Ustawienie „42 znaki” działa tylko wtedy, gdy nie da się zmierzyć fontu. Przy pomiarze decyduje szerokość ekranu. OK?

**Szyldy i czytanie** (obrazy w galerii szyldów)

11. a7 i a10: przyjąć wybór modelu (ściśnięcie / dwa wiersze)?
12. Od ilu pikseli szyld jest „za mały”? Propozycja: kara od 30 px, pełna przy 16 px.
13. Szyld szerszy od angielskiego na wolnym tle: karać zawsze czy tylko w ramce?
14. Nowa zależność `fonttools` do czytania fontów z MKV: zgoda?
15. Okrzyki wersalikami przy dialogu („EEK”) lektor czyta, a te w innym miejscu ekranu („KAGUYA”) pomija. OK?
16. Lektor zacznie czytać „Next Time”/„Preview”, tytuły odcinków i opisy produktów. OK?
17. Pliki samego openingu/endingu: nie czytać piosenki, gdy w pliku nie ma dialogu? Rekomenduję tak.

## 7. Gdzie co leży

- `main` (GitHub): poprawka lektora. Lokalnie `main` ma też plan jakości (`5bc27b8`), jeszcze niewypchnięty.
- `work/quality/01-test-corpus` (bieżący checkout): narzędzie pomiaru.
- `work/quality/06-integration` (worktree `AniShift-wt/integration`, `659afba`): wszystkie poprawki i narzędzie.
- `work/quality/07-fuzzy-line-breaks` (worktree `AniShift-wt/fuzzy-breaks`): obie specyfikacje.
- `workspace/.quality/`: baza testowa, pomiary, galerie, przeglądy agentów (`experiments/*/reviews*`).
- mpv: `C:\Users\MattyMroz\Videos\mpv\portable_config\mpv.conf`, l. 159.

## 8. Co dalej po Twoich decyzjach

1. Scalenie integracji do `main` i push.
2. Wdrożenie specyfikacji w kolejności: pomiar prawdziwym fontem → szyldy → podział → granice stylów → łamanie. Każdy krok to osobny PR z galerią przed/po.
3. Głośność lektora (etap 6) po przejściu na nowy silnik TTS.
