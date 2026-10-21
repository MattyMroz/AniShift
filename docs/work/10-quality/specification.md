# Jakość wyniku: specyfikacja

Status: zaakceptowany kierunek właściciela (2026-10-17).

## Cel

Napisy po AniShift mają wyglądać jak zrobione ręcznie: szyldy mieszczą się w swojej ramce i na ekranie, lektor czyta tylko dialogi, polskie linie są dobrze złamane i wyświetlane wystarczająco długo, a lektor jest słyszalny, ale nie za głośny.

Właściciel ogląda z lektorem, często na x2. Dialogi słyszy, więc z ekranu czyta głównie szyldy. Dlatego szyldy idą pierwsze.

## Kto ocenia

Właściciel, na zrzutach i fragmentach z bazy testowej, przed zmianą i po niej. Testy i metryki są warunkiem koniecznym, ale nie wystarczającym.

## Zakres

W kolejności z [masterplanu](masterplan.md): baza testowa, szyldy, podział dialog / szyld, granice stylów, polski podział wierszy, czasy wyświetlania (najpierw weryfikacja hipotezy), głośność lektora.

Poza zakresem: glosariusz postaci, nazwy własne w prompcie, kontekst z innych języków napisów, gotowe polskie napisy z zewnątrz, przyspieszanie lektora, ściszanie oryginału pod lektorem, własny font dialogów, piosenki OP/ED, lokalny TTS, okładki i inne zmiany TUI.

## Ustalenia

- **Baza testowa** leży w `workspace/.quality/` (katalog od kropki, pomijany przez skaner biblioteki). Nie zmienia `workspace/ready/`, `config/` ani stanu rezydenta. Tytuły wskazane przez właściciela: Grand Blue S2 i Kaguya-sama, plus komedie z bogatym typesettingiem.
- **Lektora nie generujemy** dla bazy testowej, chyba że etap dotyczy lektora (etap 6). Koszt etapu to najwyżej ponowne tłumaczenie.
- **Fakty z rozpoznania 2026-10-17:**
  - żaden z 37 MKV w bibliotece właściciela nie ma w napisach tekstów OP/ED; 24 z nich mają rozdziały z miejscem openingu i endingu;
  - nagłówki polskich ASS (rozdzielczość skryptu 16:9, `WrapStyle: 0`) są poprawne; ucieczka napisów w czarne pasy na ultrawide wynikała z `sub-ass-force-margins = yes` w mpv;
  - klasyfikator zna tylko `DIALOG`, `SIGN` i `UNCERTAIN` (`anishift/services/subtitles/classifier.py:96-101`); pole `Actor` nie jest używane w `anishift/services/subtitles/`, choć wiele źródłowych ASS podaje w nim mówcę albo znacznik `SIGN`/`Text`/`SFX`.
- **Domyślny tryb** zapisu zostaje: polskie dialogi i szyldy, wszystko wyświetlane.

## Kryteria sukcesu całości

- Na bazie testowej metryka etapu się poprawia, a żadna inna nie pogarsza.
- Właściciel potwierdza poprawę na zrzutach.
- Bramki jakości repo przechodzą.
