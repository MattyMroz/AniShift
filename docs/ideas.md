# Pomysły AniShift

Jedyne miejsce na pomysły, które nie są bieżącym zleceniem. Nowy pomysł dopisz tutaj, zamiast zakładać osobny plik. Szczegóły dłuższe niż ekran zostają w dokumencie źródłowym, a tu trafia wpis z odnośnikiem.

Status wpisu: `teraz` (najbliższa praca), `potem` (po bieżącym etapie), `kiedyś` (bez terminu), `do zbadania` (najpierw sprawdzić wykonalność), `odrzucone` (z powodem), `zrobione`.

Bieżący stan prac: [docs/README.md](README.md).

## 1. Teraz: jakość wyniku

Najbliższy priorytet właściciela to jakość tego, co program generuje. Kolejność:

| Nr | Krok | Dlaczego / dowód w kodzie |
| --- | --- | --- |
| 0 | Wzorzec z 3 odcinków ocenianych przez właściciela | Bez stałego zestawu nie da się porównać zmian tłumaczenia, napisów i miksu. |
| 1 | Glosariusz postaci z AniList (imię, płeć, rola) i oznaczanie szyldów w prompcie | Prompt przewiduje glosariusz (`anishift/services/translation/engines/llm/prompts/translation.md:22`), ale silnik wysyła tylko prompt, styl i linie (`anishift/services/translation/engines/llm/service.py:247-251`). |
| 2 | Kategoria „piosenka” i naprawa wypadających niepewnych linii | Klasyfikator zna tylko `DIALOG`/`SIGN`/`UNCERTAIN`, a styl piosenki trafia do `SIGN` (`anishift/services/subtitles/classifier.py:96-101`, `:153-156`); lektor czyta wyłącznie `DIALOG`, więc `UNCERTAIN` wypada z lektora (`anishift/services/subtitles/service.py:226`). |
| 3 | Miks lektora z duckingiem (`sidechaincompress`) i przyspieszanie pojedynczych długich kwestii | Miks to stała głośność i `amix` (`anishift/services/audio/output.py:113-119`); tempo jest jedno dla całego lektora (`anishift/services/audio/fingerprint.py:39`). |
| 4 | Dopasowanie szyldów do ramki obrazu | Issue [#23](https://github.com/MattyMroz/AniShift/issues/23): layout liczony dla całej klatki, także przy ultrawide. |

### 1.1 Tłumaczenie

- **Nazwy własne i prompty** — `teraz`. Poprawne tłumaczenie nazw własnych, dopracowane prompty. Dziś najlepiej wypada Gemini 3.8 Flash: oddaje żarty i nie jest sztywny; do porównania warto wziąć Groka. Glosariusz z AniList to krok 1 tabeli wyżej.
- **Kontekst z kilku języków napisów** — `do zbadania`. Ścieżki w innych językach jako kontekst dla płci mówiącego i niejednoznacznych sformułowań, nie jako głosowanie nad tłumaczeniami. Mała próbka (20 plików ASS, Frieren i Shoushimin, Erai-raws i SubsPlease) pokazała, że inne języki niosą wskazówki płci nieobecne w angielskim, ale ścieżki różnią się czasem i podziałem, więc dopasowanie po numerze linii jest błędne. Zysku jakości nie zmierzono.
- **Pomiary silników maszynowych** — `kiedyś`. Skrypty obciążeniowe dla domyślnych wartości batch, współbieżności i retry; równoległość plików tylko wtedy, gdy jeden plik nie wysyca API. Źródło: [stage-4-requirements.md](archive/stages/stage-4-requirements.md), sekcja „Tropy / odłożone”.

### 1.2 Heurystyki napisów

- **Dokładność podziału dialog / szyld** — `teraz`. Bank tropów do 100% (pozycja `\pos` jako sygnał, kategoria piosenki, przypadki nierozstrzygalne na poziomie stylu): [stage-3-requirements.md](archive/stages/stage-3-requirements.md) §9 i issue [#16](https://github.com/MattyMroz/AniShift/issues/16).
- **Granice stylów po tłumaczeniu** — `teraz`. Issue [#34](https://github.com/MattyMroz/AniShift/issues/34).
- **Polski podział wierszy i layout ASS** — `teraz`. Issue [#22](https://github.com/MattyMroz/AniShift/issues/22).
- **Pusty `displayed` wykryty przed kosztowną pracą** — `potem`. Issue [#47](https://github.com/MattyMroz/AniShift/issues/47).

### 1.3 Typesetting, koloryzowanie, presety stylów

- **Automatyczny typesetting szyldów i piosenek** — `potem`. Szyldy i OP/ED mają wyglądać jak ręczny typesetting. Pozycjonowanie we współrzędnych względnych i bezwzględnych, ustandaryzowanych dla każdego typu ekranu (także szerokokątnego i zakrzywionego); wspólny rdzeń do ponownego użycia w MangaShift.
- **Silnik layoutu napisów** — `potem`. Deterministyczny layout i kontrola jakości: [reference/subtitle-layout-engine.md](reference/subtitle-layout-engine.md), wcześniejszy plan [03-subtitle-layout.md](archive/automation/plans/03-subtitle-layout.md).
- **Jak pracują profesjonalni tłumacze napisów** — `do zbadania`. Czas wyświetlania, tempo czytania, podział napisów i długość wypowiedzi TTS to osobne zagadnienia. Style i pozycje ASS świadczą o obecności typesettingu, nie o jego jakości. Punkty wyjścia: [Netflix Polish Timed Text Style Guide](https://partnerhelp.netflixstudios.com/hc/en-us/articles/216787928-Polish-Timed-Text-Style-Guide), [Subtitle Timing Guidelines](https://partnerhelp.netflixstudios.com/hc/en-us/articles/360051554394-Timed-Text-Style-Guide-Subtitle-Timing-Guidelines), [Subtitle Templates](https://partnerhelp.netflixstudios.com/hc/en-us/articles/219375728-Timed-Text-Style-Guide-Subtitle-Templates). Pary EN/PL z Netflixa nie zostały zweryfikowane.

### 1.4 Piosenki OP/ED

- **Tłumaczenie i styl piosenek** — `teraz` (kategoria w kroku 2), reszta `potem`. Dopracowane polskie tłumaczenia piosenek, kolorowe lub stylizowane napisy. Karaoke to możliwa interpretacja do ustalenia, nie wymaganie. Wideo, audio i zrzuty jako kontekst to hipotezy: widoczna postać nie musi być mówiącym.

### 1.5 Gotowe polskie napisy z zewnątrz

- **Polskie napisy zamiast tłumaczenia** — `do zbadania`. Gdy wydanie nie ma polskich napisów, szukać ich w zewnętrznych źródłach (ogłoszenia grup, w tym kanały Discord, dodatki napisów Stremio), a przy późniejszej lepszej wersji opcjonalnie przygotować poprawiony wynik. Otwarte: źródło i uprawnienia, wykrywanie wydań i poprawek, dopasowanie do odcinka i wersji wideo, czy czekać na PL, czy podmieniać później. Zmiana samych napisów nie zmienia nagranego lektora. Wiąże się z kontrolą zawartości (2).

## 2. Potem: wygoda na PC

Oglądanie tylko lokalnie na PC. Cel: zobaczyć obrazek, poznać tytuł, wybrać, pobrać, obejrzeć, usunąć.

- **Okładki w panelu** — `potem`. Przy około 30 tytułach w trzech językach trudno pamiętać, który jest który. Panel pokazuje dziś tylko tekst; okładki z AniList nie są pobierane.
- **Biblioteka jako widok tytułów** — `potem`. Lista tytułów → Enter → `BIBLIOTEKA › <tytuł>` z odcinkami (numer, tytuł odcinka, Emisja, Stan); zaznaczanie i usuwanie wielu; Kosz i Ctrl+Z jak dziś. Pliki z Anime biorą tytuł z klucza AniList, pliki ręczne z nazwy, a przy braku pewności „nie rozpoznano” zamiast cichego przypisania. Dysk zostaje płaski (`workspace/ready/`). Otwarte: jeden widok tytułów czy obecny podział zakładek; przewijanie przy wielu tytułach. Pełny opis: [masterplan acquisition](archive/acquisition/masterplan.md), sekcja E6.
- **Kontrola zawartości po pobraniu** — `potem`. Polskie napisy → bez tłumaczenia; obce → tłumaczenie; brak napisów → jedna zamiana wydania; lektor zawsze. Ryzyko: rozpoznanie ścieżek „signs-only”. Sekcja E4 w [masterplanie](archive/acquisition/masterplan.md).
- **Próg pewności dla automatu** — `kiedyś`. Rozszerzenie reguły `zgodny` progiem pewności dopiero po teście na świeżym zbiorze: [algorithm-spec.md](archive/acquisition/algorithm-spec.md) §7.
- **Filmy, dodatki i osobne audio PL w subskrypcji** — `kiedyś`. Warunki powrotu: [spec.md](archive/acquisition/spec.md) §11.
- **Brakujące tytuły odcinków z TVmaze** — `potem`. Issue [#58](https://github.com/MattyMroz/AniShift/issues/58).
- **Zbiorczy cel produktu** — epic [#49](https://github.com/MattyMroz/AniShift/issues/49).

## 3. Razem z API i grafiką

- **Synchronizacja z listą anime (MAL lub AniList)** — `kiedyś`. AniShift ma wiedzieć, co obejrzane i co dalej. MAL, AniList czy obie: do ustalenia.
- **Lista obejrzanych i statystyki** — `kiedyś`. Własna lista w stylu MAL ze źródłem prawdy we własnej bazie.
- **Agregator** — `kiedyś`. Harmonogram emisji, banery i newsy z wielu stron, z którego od razu zakłada się subskrypcję. AnimeSchedule odłożone, bo wymaga tokenu i atrybucji ([spec.md](archive/acquisition/spec.md) §11).
- **API, agent, MCP** — `kiedyś`. Najpierw API, agent dopiero na nim; każda warstwa dokłada złożoności. Teraz bez REST API i strony WWW.

## 4. Lektor

- **Lokalny TTS (Chatterbox, OmniVoice, Fish, Supertonic, własny model)** — `odrzucone na teraz`. Modele są ogromne (np. 40 GB) i wolne: generowanie odcinka trwa około godziny. Dopóki działa obecny dostawca (elevenbytes), nie szukamy lokalnego TTS. Wcześniejsza ocena Supertonic: [stage-6-requirements.md](archive/stages/stage-6-requirements.md) §4.7.
- **Lektor przez ElevenReader** — `do zbadania` (bada właściciel).
  - Opis: automat w przeglądarce loguje się na konto ElevenReader, tworzy wpis z tekstem odcinka, odtwarza go przyspieszony (16×, 32× albo 64×, jeśli się da) i przechwytuje gotowe audio (MP3 trafia do pamięci jako plik).
  - Lokalny model wyrównania tekstu do audio (ASR / forced alignment) z dokładnością co do milisekundy tnie nagranie na kwestie, a z nich składa się ścieżkę lektora. W tym zastosowaniu model musi obsługiwać polski.
  - Motywacja: darmowy plan ma 10 h audio miesięcznie; płatny daje praktycznie nieograniczone użycie modeli ElevenLabs (Multilingual v2, v3, Eleven v4, Flow 4).
  - Wątpliwości: wydajność, bo każdy odcinek to osobny projekt w aplikacji.
  - **Ryzyko do sprawdzenia przed jakąkolwiek implementacją:** zgodność z regulaminem ElevenReader i ElevenLabs. Automatyzacja aplikacji konsumenckiej i użycie jej audio poza nią mogą naruszać warunki i grozić utratą konta.
- **Wiele głosów (głos per postać)** — `kiedyś`. Pole `Actor` lub styl ASS mapowany na głos TTS. Zależy od jakości klasyfikacji i pól `Actor` w fansubach; mnoży koszt płatnych silników.

## 5. Utrzymanie i technika

- **Podział `automation.py`** — `kiedyś`. Decyzja właściciela: na razie nie ciąć, wszystko w jednym pliku jest akceptowalne. Stan z commita `287cb20`: plik ma 9372 linie, klasa `AutomationOwner` około 7600 z nich (linie 772–8394). Obszary: biblioteka i usuwanie, preview i start, subskrypcje, transfery, zapis stanu i zdarzenia. Są przeplecione i dzielą pola konstruktora; na przykład `_save` jednocześnie rozlicza subskrypcje, zapisuje stan, dopisuje historię, emituje zdarzenia i planuje transfery. Rozbicie na mixiny tylko rozrzuciłoby te zależności. Jeśli kiedyś, to w tej kolejności:
  1. Tani pierwszy krok: `_selection_confirmed`, `_restorable`, `_selection_basis` i `_selection_mismatch` przyjmują jawne dane, a nie ownera, więc można je przenieść do `anishift/application/transfers.py` bez zmiany zachowania.
  2. Przy pracy nad API: uporządkować projekcje z użyciem `anishift/application/control_views.py`, zachowując oba formaty odpowiedzi.
  3. Większe wydzielenie dopiero przy udowodnionej granicy, np. rozliczenie subskrypcji jako funkcja „snapshot, czas i fakty transferów → nowy stan”, z zapisem dalej u jednego ownera.

  Podfoldery w `application/` poprawiają tylko nawigację, nie spójność. Sygnał, że już trzeba: kolejna funkcja wymaga zmian w kilku niezwiązanych obszarach ownera, regresje wracają na ich styku albo API zmusza do powielania reguł.
- **Uproszczenie kodu** — `kiedyś`. Audyt złożoności: usunięcie mechanizmów i funkcji bez wymagań przy zachowaniu kontraktów chronionych testami; usunięcie martwych ścieżek grup i kategorii. Dawny etap E5 w [masterplanie](archive/acquisition/masterplan.md).
- **Przegląd testów** — `kiedyś`. Mniej powtarzalnych testów przy tych samych dowodach: issue [#43](https://github.com/MattyMroz/AniShift/issues/43).
- **Pomiary przed optymalizacją** — `kiedyś`. Czas zjadają pobieranie, LLM, TTS i ffmpeg, nie Python, więc przepisanie na Rust nie ma uzasadnienia. Najpierw zmierzyć start, responsywność i etapy: issue [#44](https://github.com/MattyMroz/AniShift/issues/44). Odłożona wydajność TTS i audio: [stage-6-tts-performance-optimization.md](archive/stages/stage-6-tts-performance-optimization.md) §12.
- **Tor audio na PyAV** — `kiedyś`. Nie pokrywa renderu mp4 ani wypalania napisów, więc binarka ffmpeg i tak zostaje; ryzyko regresji na długim lektorze. Tylko tor audio i tylko z testem porównawczym starego i nowego toru.
- **Licznik kosztów API** — `kiedyś`. Szacunek zużycia znaków TTS i tokenów LLM w podsumowaniu przebiegu, wyraźnie opisany jako szacunek.
- **Cache metadanych AniList** — `kiedyś`. Plik z TTL zamiast ponownych zapytań o te same tytuły; dopiero gdy limity lub przestoje AniList zaczną przeszkadzać.
- **Kwalifikacja recovery i realne media** — `potem`. Issues [#45](https://github.com/MattyMroz/AniShift/issues/45) i [#46](https://github.com/MattyMroz/AniShift/issues/46).
- **Opisy ustawień i nazwy limitów** — `potem`. Issue [#42](https://github.com/MattyMroz/AniShift/issues/42).
- **Drobne długi z etapu 10** — `do zbadania`. Pozycje „Odłożone świadomie” niezwiązane z Textualem (reset wyboru głosu po zmianie nazwy, zmienna środowiska wygrywająca z `.env`, walidacja międzypolowa `LlmConfig`, nieużywany `EventBuffer`, ciężki import `anishift/config/settings.py`) w [decisions.md](archive/textual-tui/decisions.md); każdą sprawdzić w obecnym kodzie przed pracą.
- **Uwagi dla MangaShift** — `kiedyś`. W MangaShift binarki nie są weryfikowane hashem, a hash modelu jest w dwóch miejscach. Szkic jednego katalogu zasobów (binarki i modele, `kind` oddzielony od `source.type`) przyda się, gdy AniShift dostanie lokalny model. Pełny tekst: `git show bede512:docs/reference/todo-mangashift.md`.

## 6. Dalekie

- **Centrum rozrywki w przeglądarce** — `kiedyś`. Strona zamiast TUI, AniShift na własnym VPS przetwarza w tle, odtwarzanie jakości mpv w przeglądarce. Otwarte: gdzie trzymać media (około 1,5 GB na odcinek), czy wystarczy SQLite, czy MKV z ASS da się odtwarzać bez transkodowania.
- **Zdalny worker** — `kiedyś`. Wcześniejsza próba (PR #54, #55) zamknięta bez scalenia.
- **Stremio** — `kiedyś`. Wykorzystanie Stremio i import pliku: [import-and-stremio.md](archive/automation/import-and-stremio.md).
- **Lektor od razu w odtwarzaczu** — `kiedyś`. Skrypt Lua dla mpv, który sam podpina lektora leżącego obok MKV, albo flaga domyślnej ścieżki dla lektora. Dziś dołożone ścieżki mają polski język i nazwę, ale flagę domyślną `no` (`anishift/services/composition/commands.py:171-176`).
- **Manga i inne treści** — `kiedyś`. Manga ze wspólnymi heurystykami MangaShift, może filmy i inne treści.
- **Demo terminala w README** — `kiedyś`. Issue [#48](https://github.com/MattyMroz/AniShift/issues/48).

## 7. Zrealizowane albo odrzucone

Krótka lista, żeby te pomysły nie wracały.

**Zrealizowane:**

- Czuwanie nad folderem i rezydent w tle.
- Auto-pobieranie anime: zakładka Anime, subskrypcje, prywatny qBittorrent.
- Klasyfikator stylów ASS (`anishift/services/subtitles/classifier.py`); dalsza praca w 1.2.

**Odrzucone:**

- **Textual i GUI** — terminal Prompt Toolkit został frontendem; Textual porzucony (gałąź `archive/textual-tui`, issue [#38](https://github.com/MattyMroz/AniShift/issues/38) do zamknięcia).
- **Sonarr jako silnik** — dublowałby właściciela stanu.
- **Wybór grupy wydającej przez użytkownika** — właściciel nie chce wybierać grupy.
- **Model do tożsamości wydania (Laya)** — brak przewagi nad heurystyką.
- **DeepLX** — 429 z IP użytkownika od pierwszego żądania.
- **Generowanie lektora w locie podczas oglądania** — tłumaczenie i TTS nie wyprzedzą odtwarzania.
- **EmbeddingGemma do audio** — model przyjmuje tylko tekst.
- **Jellyfin i zdalne oglądanie** — decyzja właściciela z 2026-10-12: oglądanie tylko lokalnie na PC, bez zdalnego dostępu, telefonu i tabletu.
