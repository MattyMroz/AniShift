---
kind: intent
status: przyjęty kierunek właściciela; D1 w specyfikacji czeka na potwierdzenie
updated: 2026-10-30
---

# Intencja: lektor AniShift przez ElevenReader

## Problem

AniShift czyta dziś polskie dialogi głosem silnika `elevenbytes` (publiczne proxy, głos Dallin). Właściciel chce
lepszego, bardziej ludzkiego lektora. Znalazł trasę przez aplikację konsumencką ElevenReader z modelem Eleven v4 i
zbudował ją w osobnym repozytorium `ElevenDownloaderPro` (EDP). EDP nagrywa audio z prawdziwej sesji Chrome i
zapisuje razem z nim czas każdego znaku.

2026-10-30 prototyp nagrał cały odcinek Tantei S2E03 obydwoma głosami, pociął nagrania na kwestie heurystyką ciszy i
zmiksował je z wyrównaną głośnością i tempem. Właściciel ocenił odsłuch jako „w miarę OK”. Wyniki:
`SCR/snap-report.md` i `SCR/loudness-report.md` (ścieżka `SCR` w `specification.md`).

Potrzeba: odcinek przetwarzany w AniShift dostaje polską ścieżkę lektora czytaną głosem z ElevenReadera, z
głośnością i tempem dobranymi do głosu, bez ręcznej pracy i bez przenoszenia plików między programami.

## Efekt, który ma znaczenie

- Właściciel wybiera w Ustawieniach → Lektor silnik ElevenReader i głos: Piotr Fronczewski albo Adam.
- Auto, Ręczny i subskrypcje działają jak dotąd. Zmienia się głos ścieżki lektora.
- Lektor brzmi tak głośno względem oryginału jak dzisiejszy Dallin, niezależnie od głosu i materiału.
- Tempo każdego głosu jest dobrane tak, żeby mowa mieściła się w oknach napisów podobnie jak dziś.
- Sesja konta trzyma się sama. Właściciel loguje się raz, a po wygaśnięciu sesji AniShift mówi to wprost i daje
  jedną akcję naprawczą.
- Gdy ElevenReader przestanie działać albo konto zostanie zablokowane, właściciel w jednym kroku wraca do
  `elevenbytes`. Każdy błąd jest widoczny; nic nie staje po cichu.

Ocenia właściciel uchem, na prawdziwym odcinku.

## Znane fakty

- Trasa łamie warunki korzystania z usługi i może skończyć się banem konta. Prohibited Use Policy ElevenLabs
  (<https://elevenlabs.io/use-policy>, §12, odczyt 2026-10-25) zakazuje automatycznej ekstrakcji i dostępu innego niż
  przez udostępnione interfejsy. ElevenReader Terms (<https://elevenreader.io/elevenreader-terms>, §5(a), odczyt
  2026-10-25) zapowiadają monitorowanie użycia. **Konsekwencja:** `elevenbytes` zostaje w kodzie jako zapas,
  działający i testowany; nowy silnik nie dostaje żadnej funkcji do obchodzenia limitów, wielu kont ani zabezpieczeń.
- Lokalny TTS jest odrzucony (`docs/ideas.md`).
- Etap 6 jakości, głośność lektora (`docs/work/10-quality/masterplan.md`), realizuje ten workstream: mierzona
  głośność względem oryginału z limiterem.
- Między głosami ElevenReadera jest 11 dB różnicy surowego poziomu, a Adam w paśmie mowy brzmi o 2,4 dB ciszej niż
  Fronczewski przy równym LUFS. Stały gain nie wystarcza.
- Przy wspólnym tempie 1,25 Fronczewski mówi o 16% wolniej niż Dallin, Adam o 9%.
- Czasy znaków serwera są zgrubne (start następnej kwestii średnio 350 ms za wcześnie), ale nie dryfują. Same nie
  wystarczą do cięcia; razem z ciszą w nagraniu dają 100% poprawnych granic na zmierzonym odcinku.

## Kierunek

Przenieść potrzebną logikę EDP i prototypu do AniShift jako nowy silnik TTS `elevenreader`, zaadaptowaną i
napisaną od nowa w konwencjach AniShift, bez kopiowania 1:1:
typowane błędy, wspólny scheduler, retry i resume klipów, testy i bramki. EDP zostaje osobnym narzędziem
właściciela do audiobooków.

Silnik czyta cały odcinek jednym dokumentem, bo wgranie i otwarcie dokumentu trwa kilkanaście sekund, a osobny
dokument na każdą z około 300 kwestii trwałby godzinami. Nagranie jest cięte na klipy kwestii w ciszy między nimi.
Kwestie urwane w pół zdania łączą się jeszcze w tekście, więc nie powstaje granica, której nie da się bezpiecznie
przeciąć. Łączenie dotyczy tylko silnika dokumentowego; silniki czytające każdą linijkę osobno działają jak dziś.
Po każdym nagraniu silnik sprząta konto: usuwa wgrany dokument i przywraca poprzedni głos i tempo, także po błędzie
i przerwaniu.

Normalizacja głośności, przycinanie ciszy na brzegach klipów i tempo na głos należą do istniejącej domeny audio i
profili głosów. Działają dla każdego silnika; zakres przycinania dla Dallina czeka na potwierdzenie (D1).

## Cele

- Silnik `elevenreader` w rejestrze TTS, wybieralny w Ustawieniach, z głosami Fronczewski i Adam.
- Jeden dokument na odcinek (i osobny na czytane szyldy), cięty na klipy kwestii bez uciętych słów.
- Lektor na stałym poziomie ponad oryginał, z limiterem szczytów.
- Tempo i korekta głośności dobrane na głos.
- Sesja w prywatnym profilu Chrome w `config/elevenreader/`, z akcją logowania w panelu i kontrolą w `doctor`.
- Wznowienie po przerwaniu: gotowe klipy są trafieniami resume; ponownie czytane są tylko brakujące kwestie.
- Jasne komunikaty dla wygasłej sesji, wyczerpanych kredytów i blokady konta.

## Nie-cele

- Audiobooki z rozdziałami, napisy karaoke i eksport słownych czasów (zostaje w EDP).
- Automatyczne przełączanie na `elevenbytes` w trakcie odcinka.
- Model inny niż Eleven v4 i znaczniki emocji w tekście.
- Logowanie e-mailem i hasłem zapisanym w AniShift.
- Wsparcie Linuksa. Zmiana EDP.

## Anty-cele

- Obchodzenie limitów, App Check, ograniczeń urządzenia lub blokad IP, podrabianie protokołu WebSocket, wiele kont.
- Ciche przełączenie silnika albo głosu w połowie odcinka.
- Sekrety, tokeny, cookies, adresy WebSocket i teksty napisów w logach, ledgerze, receipt i dokumentach.
- Nagrania głosu Fronczewskiego w repozytorium (kategoria `famous`; repozytorium jest publiczne).
- Model mowy w produkcie (CrisperWhisper służył wyłącznie jako miernik prototypu).

## Odrzucone drogi

- **Wywoływanie EDP jako zewnętrznego narzędzia:** wymaga nowego punktu wejścia w EDP, którego kluczowe pliki
  (`src/auto.py`, `src/timestamps.py`, `src/clips.py`) nie są zacommitowane; błędy trzeba by czytać z tekstu na
  stdout; EDP ma własne pętle czekania do 120 minut, stały port 9222 i własny profil. Pełne porównanie: `plan.md` §4.
- **Zależność pakietowa od EDP:** EDP nie jest pakietem (brak `build-system`, płaskie importy), ścieżka lokalna psuje
  CI i `pip-audit`.
- **Osobny dokument na każdą kwestię:** godziny na odcinek.
- **Cięcie na samych czasach znaków:** błąd do 0,5 s; ucina słowa.
- **Cięcie w najgłębszym dołku energii bez ciszy:** na dźwięcznym łączeniu słów („faktem, że”) dołek wypada w
  środku słowa.
- **Model wyrównania mowy w produkcie:** zbędny przy heurystyce ciszy i łączeniu kwestii urwanych.
- **Normalizacja głośności w `normalize_clip`:** cel jest względny wobec oryginału, którego normalizacja klipu nie
  zna; pomiar przed tempem chybiał o 0,25–0,5 LU.

## Stan uzgodnienia

Kierunek „ElevenReader przez trasę EDP, `elevenbytes` jako zapas” przyjął właściciel. Ustalenia z 2026-10-30
(nagrywanie jednym dokumentem, głosy, heurystyka cięcia, normalizacja, tempo, przycinanie, powrót do `elevenbytes`)
są wiążące, podobnie jak odpowiedzi właściciela: kod nagrywania przenosimy i refaktoryzujemy do standardu repo,
łączenie kwestii tylko dla silnika dokumentowego, sprzątanie konta zawsze. Decyzja D1 (przycinanie brzegów u
Dallina) w `specification.md` czeka na potwierdzenie.
