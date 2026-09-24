# Polski język, preferowane 1080p i automatyczny wybór — badanie offline

Stan: 2026-09-22. **Badanie zakończone; propozycje polityki nie są zatwierdzoną implementacją.** Baseline przekazany w zleceniu: `0e8a6bf`; HEAD potwierdzony przez reviewera. Review Opus5 `ses_f35393877ffehh8MRfxtvAdNSN`: **PASS po doprecyzowaniach**. Korekty F1–F8 sprawdzono w drugim odbiorze; wskazane tam zliczenie paczek poprawiono na 5/7. Bez ponowienia pilota; historyczny hash raportu w `final-check.json` dotyczy wersji sprzed korekt.

## Odpowiedź i ustalone preferencje

**Można automatycznie wybrać kandydata do pobrania według jawnych preferencji, ale obecne metadane nie potwierdzają polskich dialogów ani rodzaju polskiej ścieżki.** Flaga jest wskazówką do kolejności prób, nie zielonym potwierdzeniem PL. Kontrola zawartości jest późniejszym etapem automatu, a nie obowiązkowym pytaniem do człowieka przy każdym odcinku.

Użytkownik ustalił: **polskie napisy dialogowe LUB polskie audio przed typesettingiem; 1080p preferowane, inne wysokości dopuszczalne**. Przy potwierdzonym PL: polskie audio 720p wygrywa z wydaniem 1080p bez PL. Nie ustalił przewagi audio nad napisami ani kolejności 720p/2160p. Intuicja „większy plik może być lepszy” nie ustanawia minimum 1,4 GB ani reguły „największy wygrywa”.

W 159 zamrożonych match znaleziono **20 polskich flag, w tym 17 przy wysokości 1080; 2 kontekstowe deklaracje napisów `[POL]` w nazwie paczki; 0 literalnych deklaracji „Polish subtitles” i 0 jawnych deklaracji polskiego audio**. Te dwa `[POL]` należą do tych samych 20 rekordów z flagą, nie są dodatkowymi trafieniami. Żaden rekord nie potwierdza pełnych polskich dialogów. Zero potwierdzeń w tej próbie nie oznacza braku polskich wersji w plikach ani poza próbką.

## Zakres i pochodzenie

Wejście: dokładnie `heuristic.decision == match` z `L/dataset.json` i `L/results.jsonl`, zgodne z `R/results-v2.json`: **159/231 rekordów**, 7 niepustych przypadków i historyczna pusta odpowiedź S4E24. Nie zmieniano etykiet, reguł identity ani 72 pominiętych rekordów. To ta sama próba in-sample trzech franczyz opisana w [heuristic-laya-validation.md](heuristic-laya-validation.md), nie nowa walidacja trafności.

Skróty lokalnych dowodów pod `C:\Users\MattyMroz\AppData\Local\Temp\opencode\`: **P** = `polish-1080-20260922-f6a82d/`; **L** = `laya-matching-trial-20260922-c7e4/`; **R** = `release-ranking-20260922-b91d/`; **B** = `anime-release-b-20260922-01/`; **A** = `anime-api-metadata-20260922-a/`; **OVA** = `anime-api-ova-20260922-followup/`.

Źródłem liczb są `P/results.json:counts,cases,records` oraz uzupełniający `P/audit.json`. Każdy rekord zachowuje ID `case:row` (wiersz od 1), ścieżkę surowego JSON, hash torrenta, indeks, nazwy i pochodzenie deklaracji. Surowe wejścia B+OVA oraz etykiety pozostały niezmienione. Archiwum repo przygotowywane przez innego writera nie było dotykane.

## Ile naprawdę wiadomo o PL i 1080

| Przypadek | Pula | Wysokość dokładnie 1080 | Flaga PL | Flaga PL + 1080 | `[POL]` przy liście napisów |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slime S1E4 | 38 | 31 | 0 | 0 | 0 |
| Slime S4E23 | 39 | 27 | 14 | 12 | 0 |
| Slime S4E10 | 45 | 39 | 4 | 4 | 0 |
| Haibane E1 | 10 | 3 | 0 | 0 | 0 |
| Bebop E1 | 22 | 18 | 2 | 1 | 2 |
| Slime OVA 4 | 4 | 4 | 0 | 0 | 0 |
| Slime OVA 1 | 1 | 1 | 0 | 0 | 0 |
| **Razem** | **159** | **123** | **20** | **17** | **2** |

Pozostałe wysokości: 720 — 20, 480 — 8, 2160 — 1, 1440 — 1, unknown — 6. Zachowano parser wysokości poprzedniego badania: sumuje deklaracje nazw/ścieżek/etykiety, wymaga jednej wartości; nie mierzy obrazu. **123 to wysokość 1080, nie dowód progressive 1080p**: literalne `1080p` w nazwach ma 114; np. `slime-s4e23:38` ma `1440x1080` w pliku `.ts`. Pozostałe 9 ID podaje `P/audit.json`; tryb skanowania pozostaje niezweryfikowany.

PL występuje w flagach: S4E23 wiersze **2,3,5,7,10,11,16,21,24,25,26,27,31,36**; S4E10 **6,8,11,17**; Bebop **14,49**. W żadnym filename nie znaleziono tokenu `PL/POL/Polish/polski/polskie/polska`. Jedynymi tekstowymi trafieniami są dwa `[POL]` w release Bebop. W 159 brak strukturalnego `subtitles` i inspekcji ścieżek; audio i kompletność dialogów pozostają unknown.

Ekstraktor bada literały w `release/path/filename`, a w prezentacyjnym `title` tylko flagę — nie jest pełnym parserem tekstu prezentacji. Według niezależnej kontroli Opus5 nie ma pominiętych literalnych deklaracji PL bez flagi; ta luka instrumentu nie zmienia liczników próby. Kod obsługuje `subtitles` (`B/torrentio-streaminfo.body.txt:55,118–131`), choć pola nie było w danych; osobnego kanału zewnętrznych napisów nie badano.

`MultiSub ≠ PL`: 33 rekordy mają rozpoznaną deklarację napisów, lecz nie mają wskazówki PL. Przykładowo `slime-s4e10:2` Erai-raws `[MultiSub]`, 1080p AVC, 917 seed hint, 1,37 GB — bez polskiej flagi. `slime-s4e23:2` tej samej grupy flagę ma. Nie wolno dziedziczyć PL po grupie, sezonie ani innym odcinku; brak flagi też nie potwierdza braku PL.

## Dlaczego flaga nie mówi „polskie audio” ani „pełne napisy”

Kod Torrentio przypięty do `39015cd654c587b041b327b6db701c423d4ebe97`: `B/torrentio-streaminfo.body.txt:12–14,71–90` parsuje osobno tytuł torrenta, tytuł pliku oraz **`record.torrent.languages + '.srt'`**, po czym scala trzy listy. Doklejenie `.srt` jest wejściem parsera, nie dowodem istnienia pliku napisów. `B/torrentio-repository.body.txt:20–52` przechowuje `languages` na modelu **Torrent**, nie File; nie ma tam osobnych języków audio i napisów.

`P/languages.js:1–47,58–66` mapuje dokładny klucz **`polish` → 🇵🇱**; `multi subs`, `dual audio`, `dubbed` to osobne etykiety. Mapowanie jest case-sensitive, nie wykonuje `lowercase`; nieznane wartości zachowuje tekstowo. `streamInfo` także nie normalizuje tu liter. Zatem polska flaga w tej ścieżce wymaga wartości `polish` po parsowaniu; nie odtworzono, z którego z trzech wejść pochodziła w danym live rekordzie.

Lock zależności wskazuje parser `TheBeastLT/parse-torrent-title` commit `ea4ab26d2394055443f3671a80b4ea8c055c9591` (`P/package-lock.json:28,1653–1655`). Nie instalowano ani nie wykonywano parsera; jego reguły rozpoznawania nazw i normalizacji liter pozostają poza tym dowodem. Nie potwierdzono też, że hosted używa dokładnie badanego commita. Kod prezentacji usuwa japoński dla anime, a przy samym angielskim ukrywa jego flagę — brak etykiety nie jest negatywnym wynikiem kontroli ścieżek.

**Konkretne przykłady, nie domniemane ścieżki:**

| ID / wskazanie | Obserwacja | Dopuszczalny wniosek |
| --- | --- | --- |
| `slime-s4e23:2`, `7dccf1737d20d3feba6aa81503d1924f4be3cc18 / 0` | Erai-raws 1080p AVC MultiSub, 🇵🇱, 927,39 MB | Wskazówka PL; nie znamy rodzaju ścieżki |
| `slime-s4e10:6`, `c7a80c518a4fa3dec48cc3eec6dcbceb200a3f32 / 0` | ToonsHub 1080p H.264, Dual Audio, Multi-Subs, 🇵🇱, 1,42 GB | Nie wiadomo, czy PL dotyczy audio, napisów, obu; „Dubbed” nie dowodzi polskiego dubbingu |
| `bebop-e1:14`, `475a64de50064dbf253c810f1aab370ecfec928a / 0` | Batch 01–26, `[Multiple Subtitle] … [POL]`; filename E1 ma tylko `[Multiple Subtitle]`; 1080p, 2,3 GB | Konkretna deklaracja języka napisów **paczki**, bez potwierdzenia jej zakresu dla E1 |
| `bebop-e1:49`, `b401f78da6d0eb37c51c21c56417cf8df97a6eb0 / 0` | Analogiczna deklaracja paczki 720p, 230,85 MB | Ta sama granica dowodu, inny torrent |

Pełne nazwy i źródła: `P/audit.json:examples`; surowe `B/{slime-s4e23,slime-s4e10,bebop-e1}.body.json`, `streams[row-1]`. Dwie paczki Bebop mają deklarację napisów PL w kontekście listy języków — to mocniejsza przesłanka niż samotna flaga, ale nie literalne „Polish subtitles” przypisane do wybranego pliku. Mieszana paczka może mieć różne języki w różnych plikach.

## Propozycja dwóch etapów i wynik eksperymentu

**Etap 1 — kwalifikacja dowodu:** zachować osobno tożsamość i klasę językową: zweryfikowane PL w odpowiednich dialogach wybranego pliku → konkretna deklaracja PL z zakresem → niejednoznaczna wskazówka PL → brak informacji o PL. W danych: **0 / 2 / 18 / 139**. Kolejność siły dowodu jest propozycją badania, a nie gwarancją, że paczka deklarująca PL jest lepsza od pliku z flagą.

**Etap 2 — kolejność prób:** wewnątrz klasy językowej preferować dokładnie 1080, potem zaakceptowany fallback. Remis można rozstrzygać deklaracją napisów → klasą źródła → seed hint → stabilnym identyfikatorem. Nie ma sumowania punktów, rozmiaru ani reputacji grupy. Znana ścieżka signs-only nie spełnia preferencji pełnych polskich dialogów; sam język `pol` również tego nie dowodzi.

Jawne **założenia analizy wrażliwości**, nie nowe wymagania: flag hint przed unknown; deklaracja paczki przed flag hint; deklaracja napisów przed jej brakiem; BD przed WEB-DL przed WEBRip, inne razem; więcej historycznych seedów późno. Pozostałe wysokości 1440/480 są tu technicznie razem po 720/2160, unknown na końcu — ich rzeczywistą kolejność trzeba ustalić. AV1/HEVC/AVC, grupa, rozmiar i provider nie są oceną jakości.

**Materialny skutek niezatwierdzonego założenia:** hint PL 720/480 wyprzedza unknown PL 1080. W obu porządkach S4E23 `:31` (720) ma pozycję **13**, `:36` (480) **14**, a pierwszy unknown PL `:8` (1080) dopiero **15**. Bebop `:49` (deklaracja PL paczki, 720) jest **2**, przed `:9` (unknown PL, 1080) na **3**. Priorytet rzeczywistego PL jest ustalony; **OPEN: czy niepotwierdzona flaga lub deklaracja paczki uzasadnia rezygnację z preferowanego 1080p**.

Porównano **P720:** 1080→720→2160 oraz **P2160:** 1080→2160→720. Każda niepusta pula zawiera 1080 w najwyższej dostępnej klasie językowej. Dlatego top-1 jest identyczny w **7/7**, ale pełna kolejność S4E23 różni się w dalszych pozycjach. Syntetyczny kontrakt bez 1080 pokazuje przeciwne wybory 720/2160; wynik nie rozstrzyga preferencji użytkownika.

| Przypadek | P720 i P2160: top-3 wiersze | Poprzednie top-1 S / Q / A | Co wyjaśnia wynik |
| --- | --- | --- | --- |
| Slime S1E4 | 3, 5, 7 | 3 / 3 / 1 | PL unknown; napisy, BD i 1080, na końcu seedy |
| Slime S4E23 | 2, 11, 3 | 2 / 1 / 2 | Hint PL + 1080; top nad runner-up przez seedy |
| Slime S4E10 | 6, 8, 11 | 2 / 2 / 1 | Hint PL wyprzedza brak informacji PL; top nad runner-up przez seedy |
| Haibane E1 | 2, 1, 3 | 2 / 2 / 6 | PL unknown; remis 1080 rozstrzyga deklarowane BD |
| Bebop E1 | 14, 49, 9 | 9 / 1 / 46 | Deklaracja PL paczki; 1080 przed 720 w tej samej klasie |
| OVA 4 | 1, 4, 6 | 1 / 1 / 1 | PL unknown; końcowe seedy |
| OVA 1 | 5 | 5 / 5 / 5 | Jedyny kandydat, nadal provisional |

Zmiana top-1 względem S: **2/7**, Q: **3/7**, A: **4/7**. Poprzednie S/Q/A: [release-ranking-validation.md](release-ranking-validation.md). Nowy wynik jest pierwszym kandydatem **do sprawdzenia**, nie werdyktem „najlepszy plik”. Pusta lista S4E24 zachowuje `suggestion=null`.

Batch kontra osobny plik nie jest kryterium rankingu; **5/7 top-1 wskazuje plik paczki** (S1E4, Haibane E1, Bebop E1, OVA4, OVA1). Seed hint dotyczy torrenta, nie osobnej dostępności wskazanego pliku; zakres deklaracji paczki także pozostaje niezweryfikowany. Użytkownik już chce wybiórczego pobierania: potrzebne jest semantyczne uzgodnienie wybranego pliku z manifestem i kontekstem, nie automatyczne dopisywanie kary za batch.

Proponowany wynik dla automatu: `candidate_ref`, `identity`, `language {tier, origins, scope, verified}`, `policy_id`, `reason`, `provisional`, `missing_checks`. Eksperyment zapisuje nazwy źródeł w `specific_origins`, `verified_pl=false`, `complete_dialogue=null` oraz pierwszy różniący się klucz `top_reason`. Bez `quality_score` i bez zamiany unknown w verified.

## Rozmiar: informacja pomocnicza, nie miara jakości

`B/torrentio-streaminfo.body.txt:27,99–107` formatuje **File.size**, dzieli przez 1024 i zaokrągla do dwóch miejsc, choć używa etykiet MB/GB. Nie są to dokładne bajty ani rozmiar całej paczki. Wszystkie 159 rekordów mają taki tekst, lecz dwa bez selektora nadal wymagają ustalenia właściwego pliku.

| Ten sam odcinek, deklarowane 1080p | Większy | Mniejszy | Co faktycznie porównujemy |
| --- | --- | --- | --- |
| Slime S4E10, Erai-raws `:2` vs `:4` | AVC, CR WEB-DL, **1,37 GB** | HEVC, CR WEBRip, **524,62 MB** | Inny kodek i deklarowana obróbka; brak pomiaru obrazu |
| Slime S4E23, VARYG `:7` vs Onalrie `:5` | H.264, CR WEB-DL, **1,4 GB** | AV1, WEBRip, **300,77 MB** | Oba z flagą PL; różne kodowanie/źródło, nie dowód równych ani różnych jakości |

Mapa A dla S4E10 i E23 daje jednocześnie `runtime=24` i `length=25` minut; podobny konflikt dotyczy S1E4 i OVA4. Haibane E1 ma 25/25, ale nadal czas katalogowy, nie pomiar wybranego wydania. OVA1 ma tylko `length=25`. **Nie wyliczono bitrate**, bo brak wiarygodnego czasu konkretnego pliku; konflikt czasu oraz zaokrąglony rozmiar nie uzasadniają precyzyjnego wyniku. Nawet poprawne bajty×8/czas byłyby średnim bitrate całego pliku, nie samego wideo ani oceną jakości.

Większy plik może zawierać więcej audio, mniej wydajny encode lub inny master. Bez obrazu nie rozstrzygamy, który przykład wygląda lepiej. Limit miejsca/transferu może być przyszłym ograniczeniem operacyjnym, nie zastępczym miernikiem jakości. **Brak whitelisty grup; nieznana grupa nie jest automatycznie gorsza.**

## Automatyzacja i bramki informacji

Przed pobraniem dostępne są nazwy, deklaracje i wskazanie pliku. Manifest torrentowy może pomóc uzgodnić ścieżkę/indeks/rozmiar, ale nie dostarcza sam w sobie inwentarza ścieżek wewnątrz MKV. **Zakończenie pobierania metadanych ≠ weryfikacja ścieżek**. Później potrzeba inspekcji mediów, a przy napisach także tekstu, zakresu czasowego i ewentualnie stylów ASS; `language=pol`, nazwa tracka ani sama liczba linii nie gwarantują kompletnych dialogów.

**Ustalonym oczekiwaniem użytkownika jest automatyczne pobieranie i przetwarzanie, analogicznie do przetwarzania folderu, bez pytań dla każdego pliku**, wspólne dla ręcznego wyboru i subskrypcji. Nie wymaga to ponownej zgody na samą automatyzację. Automat wybiera provisional, pobiera i sprawdza; otwarte pozostają konkretne retry/budżety oraz zasady alternatywy/czekania. Człowiek rozstrzyga politykę i realne konflikty, nie każdy zwykły odcinek. Checkbox oznacza wybór/intencję, nigdy potwierdzenie PL lub gotowości TTS.

12 testów kontraktu na **zasymulowanych metadanych, bez realnych tracków**: PL subtitles 1080 przed unknown PL 1080; PL audio 720 przed unknown PL 1080; flag-only bez określenia rodzaju ścieżki; MultiSub bez PL; 1080 z nieznanym rozmiarem przed dużym 2160; obie kolejności fallbacku; signs-only bez awansu do deklaracji dialogów; PL paczki bez weryfikacji innego językowo filename; checkbox bez weryfikacji; verified przed declared/hint; odrębne literały audio/subs; grupa/rozmiar bez wpływu na remis.

To test małego instrumentu badawczego, nie kompletnego parsera ani lifecycle. Testy nazwane PL audio/subtitles używają tej samej klasy `declared_specific_pl`: nie testują osobnej obsługi `audio_kind`, dubbingu/lektorstwa ani kompletności audio. Osobny test sprawdza rozpoznanie literałów; `audio_kind` pozostaje null. Syntetyczne `verified_pl` jest etykietą wejściową, nie wykonaną kontrolą audio.

**Luka prototypu i testów:** znane signs-only nadal dostaje `pl_hint`, więc wyprzedzi unknown PL. Test potwierdza tylko brak awansu do konkretnej deklaracji dialogów, nie poprawną kolejność wobec unknown. W rzeczywistym zbiorze nie było takiego przypadku (**0**), więc wyników nie zmienia. To nie docelowy wybór: proponowana reguła nadrzędna wykluczałaby pozytywny priorytet dialogów PL przy potwierdzonym braku odpowiedniego audio i napisów dialogowych; **nie została zaimplementowana ani przetestowana**.

## Ustalenia i decyzje do uzgodnienia

| Temat | Status / rekomendacja |
| --- | --- |
| PL audio lub napisy przed typesettingiem | **Ustalone**; nie sprowadzać PL do samych napisów |
| Automatyczne pobieranie/przetwarzanie, bez per-file prompts | **Ustalone oczekiwanie**, wspólne z trybem folderowym i subskrypcjami |
| Preferowane 1080p, dopuszczalne inne | **Ustalone**; nie stosować „większa wysokość zawsze lepsza” |
| 720p czy 2160p po braku 1080p | **Otwarte**; test pokazuje oba warianty, nie wybiera za użytkownika |
| Audio PL kontra dialogowe napisy PL | Obie formy spełniają preferencję; ich wzajemny priorytet **otwarty** |
| Flaga/deklaracja paczki 720/480 przed unknown PL 1080 | **OPEN**; priorytet PL nie ustanawia automatycznie priorytetu niepotwierdzonej wskazówki |
| Napisy → źródło → seedy w remisie; 1440/480/unknown | **Propozycja / otwarte**; potrzebna pełna kolejność, w tym 1080i/nieznany skan |
| Brak PL, błędna deklaracja, niedostępność | **Otwarte**: automatyczna alternatywa/czekanie i ich granice; bez pytań dla każdego odcinka |
| Rozmiar około 1,4 GB | **Spekulacja**, bez progu i bez biggest-wins |
| Pominięcie tłumaczenia/TTS po znalezieniu PL | **OPEN**, przyszła polityka pipeline zależna od rodzaju i przydatności ścieżki |
| Automatyczny typesetting | Przyszły temat; Laya i Sonarr pozostają odłożone |

## Dowody wykonania i granica stopu

- `P/freeze.json`: przed analizą zamrożono instrument, 159 ID, dwa porządki i **40 hashy wejść**; SHA-256 `618e8a72509b43b433dda0878da173fb28ca6780f9b7e930d7dc24c558de0d7a`. Sprawdzono też zgodność z historycznymi manifestami L/R. `P/audit-freeze.json` zamraża późniejszy audyt; nie zmienia pierwotnego przebiegu.
- `P/results.json`: SHA-256 `8c952aad8c84b5f03510186a31992fd0ab8cc63976fbac03c7cc486ea2ab4b5a`; wszystkie kolejności, dowody językowe, braki i czasy. `P/stdout.json`, `P/contract-tests.txt`, `P/audit.json`, `P/evidence-sha256.json` dokumentują output, **12/12 PASS**, dokładny join hash/index/filename, niezmienność kolejności przy odwróceniu wejścia oraz niezmienność hashy przed/po.
- `P/final-check.json` jest historyczną kontrolą **raportu sprzed review**; jego hash nie opisuje tej korekty. Nowy snapshot `polish-1080-20260922-review-f6a82d/` zachowuje tę iterację raportu, skrypty/dane i manifest zależności; stare freeze/wyniki pozostały bez zmian, bez rerun i nowych HTTP.
- Python **3.14.2**, Windows, wyłącznie stdlib, istniejący interpreter L uruchomiony `-I -B`, bez importu ML. Jeden przebieg: odczyt/ekstrakcja **79,546 ms**; 14 sortowań (7×2), 318 pozycji, **0,1682 ms** łącznie. Nie jest to benchmark transferu ani całego pipeline.
- Komendy i odtwarzanie: `P/commands.md`; instrumenty `study.py`, `audit.py`, `fetch_sources.py`. Wyjścia tworzone wyłącznie jako nowe pliki; ponowienie wymaga nowego katalogu, zachowania starych wyników i nowego freeze, bez ponownych HTTP.
- Nowa sieć: **0** zapytań o wydania/metadane anime; tylko **2 GET publicznego przypiętego kodu** (languages.js i package-lock.json), oba 200, **424,342 / 354,135 ms**, 2178 / 97881 bajtów; `P/source-requests.json` ma URL, UTC i SHA. Timeout 20 s/operację, limit 2 MB/ciało; brak retry i szerokiego researchu.
- Stop: wszystkie 159 ID rozliczone, 7 niepustych pul porównanych z S/Q/A, oba fallbacki sprawdzone syntetycznie, ograniczenia źródeł nazwane. Nie wykonywano pobierania metainfo/mediów, kontaktów qB/trackerów, zmian aplikacji/config/testów repo ani instalacji. Odbiór korekt wykonany; decyzje polityki pozostają otwarte.
