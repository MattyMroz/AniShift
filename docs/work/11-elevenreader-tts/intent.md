---
kind: intent
status: przyjęty kierunek właściciela, szczegóły do akceptacji
updated: 2026-10-25
---

# Intencja: lektor AniShift przez ElevenReader

## Problem

AniShift czyta dziś polskie dialogi głosem silnika `elevenbytes` (publiczne proxy, głos Dallin, endpoint `run6`;
`anishift/config/user_settings.py:271-273`). Właściciel chce lepszego, bardziej ludzkiego lektora. Znalazł trasę
przez aplikację konsumencką ElevenReader z modelem Eleven v4 i zbudował ją w osobnym repozytorium
`ElevenDownloaderPro` (dalej: EDP). EDP nagrywa audio z prawdziwej sesji Chrome i zapisuje razem z nim czas każdego
znaku (`ElevenDownloaderPro/README.md:91-106`). W EDP powstały już próby polskiego lektora: `lektor_pl`, `v2`, `v3` i
montaż (`ElevenDownloaderPro/workspace/output/lektor_pl*.mp3`, 2026-10-24).

Potrzeba: odcinek przetwarzany w AniShift ma dostać polską ścieżkę lektora czytaną głosem z ElevenReadera, bez
ręcznego nagrywania i bez przenoszenia plików między dwoma programami.

## Efekt, który ma znaczenie

- Właściciel wybiera w Ustawieniach → Lektor silnik ElevenReader i jeden z dwóch głosów: Piotr Fronczewski albo
  Adam.
- Auto, Ręczny i subskrypcje działają jak dotąd. Zmienia się tylko głos ścieżki lektora.
- Sesja konta trzyma się sama. Właściciel loguje się raz, a gdy sesja wygaśnie, AniShift mówi to wprost i daje jedną
  akcję naprawczą.
- Gdy ElevenReader przestanie działać albo konto zostanie zablokowane, właściciel w jednym kroku wraca do
  `elevenbytes` i nic innego się nie psuje.

Ocenia właściciel uchem, na prawdziwym odcinku: jakość głosu, tempo względem okien napisów i głośność względem
oryginału.

## Znane fakty od właściciela

- Nowym silnikiem ma zostać ElevenReader przez trasę zbudowaną w EDP.
- Trasa łamie warunki korzystania z usługi i może skończyć się banem konta. Prohibited Use Policy ElevenLabs
  (wersja „Last Updated: 09 October 2026”, odczyt 2026-10-25, <https://elevenlabs.io/use-policy>) zakazuje w §12
  „Using bots, scraping, or automated tools to extract data from our Services” oraz „Accessing our Services other
  than through the interfaces and APIs we make available to you”. ElevenReader Terms (wersja „Last Updated: October
  13, 2025”, odczyt 2026-10-25, <https://elevenreader.io/elevenreader-terms>) pozwalają na użytek prywatny i
  niekomercyjny, a §5(a) zapowiada monitorowanie użycia i ograniczanie dostępu. **Konsekwencja:** silnik
  `elevenbytes` zostaje w kodzie jako zapas, działający i testowany. Nowy silnik nie dostaje żadnej funkcji do
  obchodzenia limitów, wielu kont ani zabezpieczeń.
- Lokalny TTS jest odrzucony (`docs/ideas.md:65`).
- Etap 6 jakości, głośność lektora, czeka na zmianę silnika (`docs/work/10-quality/masterplan.md:15`). Po
  przejściu na ElevenReader ten etap wraca na nowym głosie.

## Kierunek

Przenieść potrzebną logikę EDP do AniShift jako nowy silnik TTS `elevenreader`, w konwencjach AniShift: typowane
błędy, wspólny scheduler, retry i resume klipów, testy i bramki. EDP zostaje osobnym narzędziem właściciela do
audiobooków. AniShift nie zależy od jego kodu ani katalogów.

Silnik różni się od pozostałych jednym faktem: ElevenReader czyta **cały dokument**, a nie pojedynczą kwestię.
Wgranie i otwarcie dokumentu trwa około minuty (`ElevenDownloaderPro/docs/research/capabilities.md:123`), więc
osobny dokument na każdą z około 300 kwestii odcinka trwałby godzinami. Dlatego silnik czyta wszystkie kwestie
odcinka w jednym dokumencie, a nagranie jest cięte na klipy kwestii według czasów znaków i ciszy. Czasy znaków są
w tej trasie konieczne: bez nich nie da się przypisać fragmentu nagrania do kwestii.

## Cele

- Silnik `elevenreader` w rejestrze TTS, wybieralny w Ustawieniach, z głosami Fronczewski i Adam.
- Jeden dokument na odcinek (i osobny na czytane szyldy), cięty na klipy kwestii z dokładnością pozwalającą nie
  ucinać słów.
- Sesja w prywatnym profilu Chrome w `config/elevenreader/`, z akcją logowania w panelu i kontrolą w `doctor`.
- Wznowienie po przerwaniu: gotowe klipy kwestii są trafieniami resume; ponownie czytane są tylko brakujące.
- Jasne komunikaty dla wygasłej sesji, wyczerpanych kredytów i blokady konta.

## Nie-cele

- Audiobooki z rozdziałami, napisy karaoke i eksport słownych czasów (to zostaje w EDP).
- Automatyczne przełączanie na `elevenbytes` w trakcie odcinka.
- Wybór modelu innego niż Eleven v4 i znaczniki emocji w tekście.
- Wsparcie Linuksa.
- Zmiana EDP. Repozytorium EDP pozostaje nietknięte.

## Anty-cele

- Obchodzenie limitów, App Check, ograniczeń urządzenia lub blokad IP, podrabianie protokołu WebSocket, wiele kont.
- Ciche przełączenie silnika albo głosu w połowie odcinka.
- Sekrety, cookies, adresy WebSocket i teksty napisów w logach, ledgerze, receipt i dokumentach.
- Publikowanie nagrań głosu Fronczewskiego w repozytorium (kategoria `famous`;
  `ElevenDownloaderPro/docs/research/capabilities.md:153`). Repozytorium AniShift jest publiczne.

## Odrzucone drogi

- **Zależność pakietowa od EDP (`uv add` ze ścieżki lub gita):** EDP nie jest pakietem (`pyproject.toml` bez
  `build-system`, moduły importują się płasko `from timestamps import ...`, `src/downloader.py:31`), ma niezacommitowane
  pliki (`docs/report.md:87`), synchroniczne API Playwright, `print` zamiast loggera, `SystemExit` zamiast typowanych
  błędów i `msvcrt` (`src/downloader.py:18`). Ścieżka lokalna psuje CI i `pip-audit`. Adaptacja wymagałaby
  przebudowy EDP, czyli zmiany repozytorium, które ma zostać nietknięte.
- **Uruchamianie EDP jako procesu zewnętrznego:** `auto.py` pracuje na katalogach `workspace/input`, `done`, `failed`
  i raportuje stan tekstem na stdout (`src/auto.py:225-246`). Brak typowanego kontraktu, wyboru głosu, anulowania i
  retry; wynik trzeba by parsować z logów.
- **Osobny dokument na każdą kwestię:** godziny na odcinek i setki wpisów w bibliotece konta.
- **Model wyrównania mowy (ASR):** zbędny, bo serwer sam przysyła czas każdego znaku
  (`ElevenDownloaderPro/docs/research/capabilities.md:28-30`).

## Nierozstrzygnięte

Decyzje właściciela z rekomendacjami są w `specification.md`, sekcja „Otwarte decyzje właściciela”. Fakty,
których kod EDP nie ustala (identyfikatory głosów, sposób wyboru głosu, metody logowania), ustala faza 0 planu.

## Stan uzgodnienia

Kierunek „ElevenReader przez trasę EDP, `elevenbytes` jako zapas” przyjął właściciel. Wariant integracji (kopia z
refaktorem), rekomendacje decyzji i plan są propozycją do akceptacji.
