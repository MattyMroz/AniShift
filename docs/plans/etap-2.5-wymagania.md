# Etap 2.5 — pobieracz zasobów (resource resolver) — WYMAGANIA

> Ten dokument to **wymagania**, nie plan i nie kod. Plan powstanie dopiero po zaakceptowaniu wymagań.
> Status: **DRAFT — do przeglądu przez usera.** Sekcja USTALONE = potwierdzone. `???` = wymaga decyzji.
> Referencje: `docs/reference/mangashift-architecture/` (model-asset-standard, service-standard), `docs/reference/audyt-mm-avh/07-binarki-vs-python.md`.

## Cel

AniShift automatycznie pobiera i weryfikuje **zasoby zewnętrzne** potrzebne do działania. Na teraz: binarki (mkvtoolnix, ffmpeg). W przyszłości ten sam mechanizm ma obsłużyć modele AI. User nie robi nic ręcznie.

## Zasada nadrzędna

**Idioto-odporność.** User nie wie o istnieniu „binarek", „modeli", „setupu". Odpala AniShift → działa.

---

## 1. Wymagania funkcjonalne (co MA robić)

- **R1 — Auto-pobieranie przy starcie.** AniShift przy uruchomieniu wykrywa brakujące/uszkodzone zasoby i pobiera je sam. Zero ręcznego kroku.
- **R2 — Bez zbędnego re-pobierania.** Zasób obecny i zgodny z hashem → nie pobierany ponownie. Start natychmiastowy.
- **R3 — Weryfikacja obowiązkowa (integrity).** Każdy plik sprawdzany hashem SHA256 — czy pobrany CAŁY i POPRAWNY. Niezgodny/niepełny/podmieniony = odrzucony. Manifest = jedyne źródło prawdy o hashach i rozmiarach.
- **R4 — Pasek postępu.** Podczas pobierania ładny pasek (`ProgressBarManager` z `utils/rich_console` — istniejący, dobry). Pokazuje %, rozmiar, prędkość.
- **R5 — Ręczna komenda (opcja/recovery).** `anishift setup` wymusza pobranie/naprawę. Pobiera wersję z manifestu.
- **R6 — Szybkie pobieranie (równoległe).** Wiele zasobów pobieranych naraz (np. mkvtoolnix i ffmpeg jednocześnie, wątki). NIE robimy multi-connection na pojedynczy plik (dzielenie HTTP Range) — dla 2 plików to overkill i złamanie zasady prostoty. Równoległość na poziomie zasobów wystarcza.
- **R7 — Rozpakowywanie archiwów.** Zasoby w `.7z`/`.zip` → wyciągane są TYLKO potrzebne pliki (nie całe archiwum). Reszta kasowana.
- **R8 — Manifest jako SSOT.** Jeden plik-manifest opisuje wszystkie zasoby (co, skąd, hash, rozmiar, gdzie umieścić). Dodanie zasobu = wpis do manifestu.

## 2. Wymagania niefunkcjonalne (jak MA się zachowywać)

- **N1 — Nie crashuje.** Żaden błąd pobierania (sieć, serwer, dysk, archiwum) nie wywala apki.
- **N2 — Atomowość / bez śmieci.** Pobieranie → folder tymczasowy → weryfikacja → dopiero potem plik ląduje w `external/bin/`. Przerwane/uszkodzone nie zostają w docelowym miejscu. Temp kasuje się sam.
- **N3 — Generyczność (tania od razu).** Manifest opisuje „zasoby" (pliki, hashe, źródło, format, gdzie) — binarka i przyszły model AI to ten sam kształt danych, ten sam pobieracz. Uzasadnienie: to ~jedno dodatkowe pole w manifeście + kilka linii kodu TERAZ, ale przepisywanie całego pobieracza PÓŹNIEJ gdyby dorabiać. Tania ochrona, nie łamie YAGNI. NIE budujemy pełnej warstwy `catalog`+`resolver` jak MangaShift — tylko manifest na tyle ogólny, że przyjmie nowy typ zasobu bez przeróbek.
- **N4 — Zasoby poza gitem.** Setki MB NIE idą do repo. `external/bin/` (i przyszłe `external/models/`) gitignored, pobierane osobno. Git = kod. (Aktualizacja przez git repo = ODRZUCONE — repo by spuchło.)
- **N5 — Wersje pinowane.** Manifest pinuje konkretną wersję (URL + hash). Aktualizacja = świadoma zmiana manifestu, nie „ciągnij latest". Zmiany buildów rzadkie (~raz/miesiąc).
- **N6 — Bezpieczeństwo rozpakowywania.** Guard przed path-traversal (`../`, ścieżki absolutne) — złośliwe archiwum nie zapisze pliku poza `external/bin/`.
- **N7 — Windows-first, furtka wieloplatformowa.** Robimy i utrzymujemy **tylko Windows** (pobieranie win64 `.exe` do `external/bin`). Kod NIE wywala się na innym OS (istniejący `is_windows()` + PATH fallback w `binaries.py` zostają nietknięte — furtka na przyszłość), ale Linux/Mac NIE są utrzymywane: zero testowania, zero pobierania Linux buildów, zero dodatkowej pracy. Powód: user pracuje na Windows, nie obchodzą go userzy Linux/Apple; hipotetyczny serwer w przyszłości i tak zastąpi AI. YAGNI — nie budujemy pod nierealną przyszłość, ale nie palimy mostów.
- **N8 — Testowalność.** Logika pobierania/weryfikacji/rozpakowywania testowalna BEZ sieci (wstrzykiwany downloader, syntetyczne archiwa).

## 3. Zakres zasobów

**Teraz:**
- mkvtoolnix (mkvextract, mkvmerge) — etap 3
- ffmpeg (ffmpeg, ffprobe) — etapy 6-7

**Nie teraz (ale manifest gotowy):**
- balcon — etap 6 (Windows-only, inne źródło)
- modele AI — przyszłość (N3 zapewnia elastyczność)

**Nie w ogóle:**
- ffplay (nieużywany), mkvinfo/mkvpropedit (martwe wg audytu)

---

## 4. Architektura (wzorzec z MangaShift, dostosowany)

MangaShift rozdziela: **manifest** (opis zasobów) + **resolver** (pobieranie/weryfikacja/mapowanie). AniShift robi to samo:

```
external/bin_hashes.json   ← MANIFEST (opis: co, skąd, hash, gdzie)
        │
   manifest loader          ← czyta + waliduje → typy
        │
   resolver / installer      ← pobiera (multi-conn) → weryfikuje hash → rozpakowuje → przenosi
        │
   external/bin/<tool>/       ← wynik (gitignored)
        ▲
   binaries.py                ← mówi resolverowi gdzie (już istnieje)
```

Resolver jest **generyczny** — zasób opisuje manifest, nie kod. Przyszły model AI: nowy wpis w manifeście → resolver go obsłuży bez zmian.

---

## 5. Edge case'y — PEŁNA TABLICA (propozycje — POPRAW co nie tak)

> Moja ocena zachowania dla każdego przypadku (fail-loud, nie crashuje, atomowość). Wszystkie domknięte.

| # | Sytuacja | Zachowanie |
|---|----------|-----------|
| E1 | Pierwszy start, brak zasobów, net OK | Pobiera z paskiem, potem wchodzi do shella. |
| E2 | Pierwszy start, BRAK internetu | Ostrzega ("brak sieci — pobiorę przy następnym starcie"), **wpuszcza do shella** (nie blokuje — user może chcieć zrobić coś, co binarek nie wymaga). Doctor czerwony. NIE crashuje. |
| E3 | Internet padł W ŚRODKU pobierania | Plik w tempie kasowany. Ostrzeżenie. `external/bin/` nietknięte. Ponawia następnym razem. |
| E4 | Zły hash (uszkodzony/niepełny) | Odrzuca, plik nie ląduje w docelowym. Komunikat. Inne zasoby lecą dalej. |
| E5 | Drugi start (zasoby są) | Skip, zero pobierania, natychmiastowy start. |
| E6 | Częściowa instalacja (1 OK, 1 nie) | Per-zasób niezależnie: gotowy skip, brakujący ponów. Bez duplikacji. |
| E7 | Nowsza wersja dostępna | NIE aktualizuje sam (N5 — pinowane). Bierze wersję z manifestu. Aktualizacja = świadoma zmiana manifestu. |
| E8 | Serwer 404/503/timeout | `raise_for_status` → ten zasób fail, `external/bin/` nietknięte, inne lecą dalej. Ostrzeżenie. |
| E9 | Inny OS niż Windows (furtka) | Win64 nie pobiera; `resolve_binary` szuka w PATH (istniejąca furtka, nieutrzymywana). |
| E10 | Brak miejsca na dysku | `OSError` łapany → ten zasób fail, ostrzeżenie, nie crashuje. |
| E11 | Ctrl+C w trakcie pobierania | **Przerywa czysto**: temp kasowany, `external/bin/` nietknięte, wraca do promptu (nie wychodzi z apki). Traktowane jak E3 (przerwane pobranie). |
| E12 | Plik w archiwum ≠ ścieżka w manifeście | "member not found" → ten zasób fail, inne dalej. |
| E13 | Złośliwa ścieżka w archiwum (`../`) | Guard traversal odrzuca, nic poza `external/bin/` nie powstaje. |
| E14 | `external/bin/` nie istnieje | Tworzony (`mkdir parents=True`). |
| E15 | Uszkodzone archiwum (nie da się rozpakować) | Błąd rozpakowywania łapany → ten zasób fail, temp kasowany, nie crashuje, inne dalej. |
| E16 | Manifest uszkodzony/pusty | **Fail-loud**: `ManifestError` z jasnym komunikatem ("błąd konfiguracji binarek — zgłoś"). To błąd deweloperski (manifest jest w repo, nie od usera), więc ma być widoczny, nie ukryty. |

## 6. Definition of Done — KRYTERIA AKCEPTACJI

- [ ] `anishift` (sam start) auto-pobiera brakujące zasoby z paskiem postępu, potem wchodzi do shella
- [ ] Drugi start = zero pobierania, natychmiastowy
- [ ] Zły hash / brak sieci / błąd serwera / Ctrl+C NIE crashują apki (wpuszczają do shella lub wracają do promptu)
- [ ] Pobrane pliki weryfikowane hashem przed użyciem; nic nie ląduje w `external/bin/` jeśli hash się nie zgadza
- [ ] `anishift doctor` zielony po pobraniu
- [ ] Zasoby pobierane równolegle (2 naraz)
- [ ] Manifest na tyle ogólny, że przyjmie nowy typ zasobu (model AI) bez przepisywania pobieracza
- [ ] Windows w 100%; furtka wieloplatformowa (istniejący kod) nietknięta
- [ ] Testy bez sieci przechodzą (wstrzykiwany downloader, syntetyczne archiwa)
- [ ] Bramki jakości: ruff + format + mypy + pytest zielone
- [ ] `anishift setup` działa jako ręczne recovery (wymusza pobranie/naprawę)

---

## USTALONE (kluczowe decyzje z rozmowy)

- ✅ **Windows-only** utrzymywane; furtka wieloplatformowa (istniejący `is_windows`/PATH fallback) zostaje nietknięta, ale Linux/Mac NIE utrzymywane (N7)
- ✅ **Auto-pobieranie przy starcie** — idioto-odpornie, user nic nie klika (R1)
- ✅ **Generyczność tania** — manifest gotowy na modele AI (jedno pole), ale BEZ pełnej warstwy resolver MangaShift (N3)
- ✅ **Równoległe pobieranie** (2 zasoby naraz), BEZ multi-connection na plik — overkill dla 2 plików (R6)
- ✅ **Pasek postępu** — istniejący `ProgressBarManager`, ładny (R4)
- ✅ **`setup`** jako ręczne recovery (R5)
- ✅ **Poza gitem, wersje pinowane hashem** (N4, N5)
- ✅ **Weryfikacja hashem obowiązkowa**, atomowość przez temp (R3, N2)
- ✅ **Istniejący kod nietknięty** — `binaries.py`/`doctor.py` pasują, dokładamy tylko nowe pliki

## Zasady usera (na cały projekt)

- **100% albo wcale** — zero kompromisów/półśrodków w tym co robimy.
- Ja (agent) oceniam sensowność wymagań, nie user. User reaguje na moją ocenę.
