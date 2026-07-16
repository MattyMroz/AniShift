# etap 2.5 — pobieracz zasobów zewnętrznych (v2.1, FINAL — leniwe pobieranie)

> data: 2026-07-16 | zastępuje roboczy plan v1 (`docs/superpowers/plans/2026-07-16-etap-2.5-pobieracz-binarek.md`) i domyka `docs/plans/etap-2.5-wymagania.md`.
> **v2.1 — ZMIANA ARCHITEKTURY (decyzja usera):** binarki pobierają się **leniwie** — dopiero gdy funkcja, która ich potrzebuje, jest realnie wołana (`ensure_binary`/`ensure_resource`), NIE wszystkie z góry przy starcie shella. Start shella = natychmiastowy, zero sieci. `/setup` i `anishift setup` zostają jako JAWNE „pobierz wszystko teraz". Szczegóły i uzasadnienie: sekcja 1.6.
> struktura: **SEKCJA 1** wymagania (ocenione i domknięte) → **SEKCJA 2** issue do GitHuba → **SEKCJA 3** pełny plan implementacji (drzewo, API, kod, testy, commity).
> zasady: recykling MangaShift, KISS/YAGNI (skill `simple`), standard Pythona (skille `python` + `instructions`), Conventional Commits bez śladów AI.

---

# SEKCJA 1 — WYMAGANIA (przegląd krytyczny + wersja ostateczna)

## 1.1 Werdykt ogólny

Wymagania z `etap-2.5-wymagania.md` są **dobre i kompletne w 95%**. Architektura (manifest SSOT + generyczny installer), atomowość przez temp, równoległość per-zasób bez multi-connection, Windows-only z nietkniętą furtką — wszystko trzyma się kupy i zgadza z istniejącym kodem (`binaries.py`, `doctor.py`, `errors.py`). Poniżej: co przyjmuję bez zmian, co doprecyzowuję (bo w praktyce było niedomknięte), co dodaję i dwie realne decyzje usera (1.5 — pin ffmpeg; 1.6 — leniwe pobieranie zamiast auto-startu, zmiana względem v2).

## 1.2 Doprecyzowania (wymagania były niejednoznaczne — rozstrzygam)

- **R3 (weryfikacja hashem) — hash dotyczy ARCHIWUM, nie pojedynczych `.exe`.** Manifest pinuje SHA256 **pobieranego archiwum** (tylko takie hashe policzyliśmy i tylko takie mają sens — granica zaufania to pobranie z sieci). Po weryfikacji archiwum wyciągnięte pliki są zaufane. Konsekwencja: `doctor` **nie** weryfikuje hashy per-exe (musiałby istnieć drugi manifest hashy per plik — YAGNI); `doctor` zostaje przy obecności plików, dokładnie jak dziś. To zgodne z USTALONE „doctor.py nietknięty".
- **R1 („uszkodzone zasoby") — definicja „obecny i poprawny":** plik istnieje **i ma rozmiar > 0**. Zerobajtowy/urwany plik nigdy nie powstaje w `external/bin/` (atomowość N2), ale gdyby powstał (ręczna ingerencja), check `is_installed` go wychwyci i zasób zostanie pobrany ponownie. Głębsza weryfikacja obecnych plików = `/setup force` (patrz R9).
- **R4 + R6 (pasek + równoległość) — JEDEN wspólny pasek zbiorczy.** `ProgressBarManager` to pojedynczy pasek na współdzielonej konsoli rich — dwa niezależne paski z dwóch wątków to gwarantowana sieczka na ekranie. Rozwiązanie proste i lepsze UX-owo: jeden pasek „Downloading tools" z `total = suma size_bytes` brakujących zasobów (rozmiary znamy z manifestu z góry); oba wątki `advance()` ten sam pasek (metody rich `Progress` są thread-safe; dodatkowo jeden `threading.Lock` na `advance` serializuje księgowość managera). Pokazuje %, MB, prędkość łączną — spełnia R4 i R6 naraz. Dotyczy to **`run_setup`** (ścieżka zbiorcza); ścieżka leniwa (`ensure_resource`) pobiera zwykle JEDEN zasób w jednym wątku, więc dostaje własny pojedynczy pasek `Downloading <nazwa>` z `total = size_bytes` tego zasobu — te same flagi paska, zero maszynerii wątków. Tak godzimy oba światy: równoległość i zbiorczy pasek żyją wyłącznie w `run_setup`.
- **E11 (Ctrl+C) — jawny mechanizm anulowania w `run_setup`.** Wątki pobierające sprawdzają `threading.Event` między chunkami; Ctrl+C w wątku głównym ustawia event → pobierania kończą się w ułamku sekundy → tempy sprzątają się same → raport oznacza zasoby jako `cancelled` → shell wraca do promptu. Uwaga windowsowa: czekanie na futures musi być pętlą z timeoutem (`concurrent.futures.wait(timeout=0.2)`), bo blokujące `wait()` bez timeoutu na Windows nie reaguje na Ctrl+C. Ścieżka leniwa (`ensure_resource`) jest **jednowątkowa** — Ctrl+C to zwykły `KeyboardInterrupt` w wątku wołającym: temp sprząta się przez context manager, nic nie ląduje w `external/bin/`, wyjątek idzie do wołającego (pipeline etapu 3/6 decyduje, jak go pokazać).
- **N3 (generyczność) — konkretny kształt:** manifest ma klucz główny `resources` i pole `type` per zasób (dziś jedyna wartość: `"binary"`). Przyszły model AI = nowa wartość `type` (+ mapowanie na katalog docelowy) — pobieracz (download → hash → extract → move) nie zmienia się ani o linię. Nazwa pliku zostaje `bin_hashes.json` (już w repo, wpięta w etap 1 — zmiana nazwy to churn bez zysku).
- **R5 (`/setup` w shellu + `anishift setup` z terminala) — semantyka:** bez opcji = **jawne „pobierz wszystko z góry teraz"** (pobierz brakujące, pomiń obecne; no-op gdy komplet) — dla usera, który chce mieć komplet od razu (recovery / przygotowanie offline). Naprawa obecnego-ale-uszkodzonego pliku → R9 (`/setup force`). W shellu **nie ma flag uniksowych** — opcje komend to gołe tokeny podpowiadane inline przez completer, UX 1:1 jak podpowiedzi komend po `/` (patrz R12).
- **E9 (inny OS):** `run_setup` raportuje zasoby `type="binary"` jako `unavailable` (bez pobierania) — komendy `/setup` i `anishift setup` pokazują to jawnie; `ensure_resource` na innym OS jest **cichym no-opem** (PATH-fallback w `binaries.py` i tak działa, a `require_binary` da czytelny błąd, gdy binarki nie ma też w PATH).
- **E16 (zepsuty manifest):** `ManifestError` (fail-loud). W komendzie `anishift setup` = czerwony komunikat + exit 1; w `/setup` w shellu = czerwony komunikat, REPL działa dalej. W ścieżce leniwej `ManifestError` leci do funkcji domenowej jak każdy `AniShiftError` — pipeline go pokazuje, apka nie crashuje. Start shella nie dotyka manifestu w ogóle (zero pobierania na starcie).

## 1.3 Nowe wymagania (dodaję)

- **R9 — `/setup force` (shell) / `anishift setup --force` (terminal).** Wymusza ponowne pobranie i instalację wszystkiego, nawet gdy pliki są obecne. To jedyna ścieżka naprawy pliku, który istnieje, ma rozmiar > 0, ale jest uszkodzony (check obecności go nie wykryje). W shellu `force` to token opcji (nie flaga uniksowa), zadeklarowany w `Command.options`; nieznany token (`/setup blah`) = czytelny komunikat, nie crash. Jedna opcja, zero dodatkowej maszynerii.
- **R12 — completer opcji komend w shellu (UX jak w Claude Code).** `Command` dostaje pole `options: dict[str, str]` (opcja → opis, domyślnie puste) — SSOT opcji, analogicznie jak `_REGISTRY` silników jest SSOT silników. `SlashCompleter` robi się dwupoziomowy: `/` bez spacji podpowiada komendy (jak dziś); `/<znana-komenda>` + spacja podpowiada opcje tej komendy (prefix match, opis opcji jako meta). `dispatch` waliduje tokeny po komendzie względem `options` i przekazuje je handlerowi. Poza `/` completer dalej nic nie podpowiada.
- **R10 — walidacja manifestu przy wczytaniu.** Manifest jest w repo (błąd = błąd dewelopera), więc loader waliduje twardo: znany `type`, znany `archive` (`7z`/`zip`), sha256 = 64 znaki, `size_bytes` > 0, niepusta lista `members`, `dest` bez `..` i bez ścieżek absolutnych (pierwsza warstwa guarda N6; druga warstwa: re-check przy rozpakowaniu).
- **R11 — aktualizacja planów etapów.** Binarki znikają z etapu 8 (zostaje tam migracja workspace + kasacje starego kodu); `docs/plans/_index.md` dostaje wiersz 2.5 i poprawiony graf zależności. Etap 3 zależy odtąd też od 2.5 (ekstrakcja potrzebuje mkvtoolnix).

## 1.4 Usunięte / poza zakresem (potwierdzam decyzje z wymagań)

- **ffplay** — nie pobieramy (martwy). **mkvinfo/mkvpropedit** — martwe wg audytu.
- **balcon** — etap 6 (inne źródło, Windows-only silnik TTS); manifest go przyjmie bez zmian kodu (nowy wpis `type="binary"`).
- **Multi-connection na pojedynczy plik** — odrzucone (overkill dla 2 plików).
- **Hash per-exe w doctorze** — odrzucone (patrz doprecyzowanie R3; wymagałoby drugiego manifestu).
- **Zmiany w `binaries.py` i `doctor.py`** — zero; oba pasują jak są.

## 1.5 USTALONE — ffmpeg pinowany do datowanego, niezmiennego release'u BtbN (nie `latest`)

**Decyzja usera: opcja (a) — datowany tag, obowiązkowo.** BtbN buduje ffmpeg **codziennie**, a tag `latest` jest ruchomy — plik pod takim URL-em zmienia się z każdym autobuildem i weryfikacja hashem zaczęłaby trwale odrzucać pobranie na każdej świeżej maszynie. Dlatego manifest pinuje ffmpeg do **datowanego, niezmiennego release'u** (`releases/download/autobuild-YYYY-MM-DD-.../...`) — URL nie jest ruchomy, pełna zgodność z N5, zero rozjazdów hasha.

Konsekwencje (wpisane w plan):

- **Zadanie 1 ma OBOWIĄZKOWY krok re-pin:** wykonawca w dniu implementacji wchodzi na `https://github.com/BtbN/FFmpeg-Builds/releases`, wybiera aktualny **datowany** autobuild (konkretny release z tagiem `autobuild-YYYY-MM-DD-HH-MM`, nie `latest`), pobiera z niego build win64-gpl (zip), liczy SHA256 + rozmiar i wpisuje url/sha256/size_bytes do manifestu.
- URL `latest` + hash odziedziczone z v1 to w tym planie **wyłącznie tymczasowe placeholdery** do zastąpienia przed commitem zadania 1 — jawnie oznaczone w 3.3 i w zadaniu 1.
- mkvtoolnix nie ma tego problemu (URL przypięty do wersji 100.0) — jego wartości są ostateczne.

## 1.6 USTALONE — leniwe pobieranie na żądanie, nie przy starcie shella (v2.1)

**Decyzja usera:** binarki pobierają się **dopiero wtedy, gdy funkcja, która ich potrzebuje, jest realnie wołana** — nie wszystkie z góry przy starcie shella. Powód: user nie ma czekać na ~200 MB (w tym ~168 MB ffmpeg) tylko po to, żeby otworzyć shell. ffmpeg jest potrzebny dopiero w etapach 6-7 (audio), mkvtoolnix dopiero w etapie 3 (ekstrakcja). Idioto-odporność zostaje — zmienia się tylko **moment**: z „start shella" na „pierwsze użycie".

Mechanizm (dwa punkty wejścia, wspólne klocki):

- **`ensure_binary(binary: Binary) -> Path`** (installer) — leniwy punkt wejścia dla kodu domenowego. Najpierw `resolve_binary` (binarka jest → zwróć ścieżkę, **zero kosztu**: bez czytania manifestu, bez sieci); nie ma → `ensure_resource` pobiera JEDEN zasób dostarczający tę binarkę (download → hash → extract → move, pojedynczy pasek), potem `require_binary` zwraca ścieżkę. Etap 3 zawoła to dla mkvextract, etap 6 dla ffmpeg/balcon.
- **`ensure_resource(name: str) -> None`** (installer) — sprawdź, czy zasób z manifestu jest zainstalowany; nie → pobierz go **jednego**, synchronicznie, z paskiem; tak → nic. Błędy (sieć, dysk, hash) = czytelny `InstallerError` z `ErrorContext` (nie surowy traceback httpx) — funkcja domenowa nie może działać bez binarki, więc tu **raise** jest właściwy (w odróżnieniu od `run_setup`, które raportuje).
- **`run_setup()` zostaje bez zmian** jako jawne „pobierz wszystko teraz" — woła je tylko `/setup` (shell) i `anishift setup` (terminal), już **nie** start shella. Równoległość, zbiorczy pasek, raport per zasób, Ctrl+C-cancel — wszystko jak było.

Dlaczego most jest w `installer.py`, a NIE w `binaries.py` (rozstrzygnięcie z uzasadnieniem):

1. **Kierunek zależności:** `installer.py` już importuje `binaries.py` (`external_bin_root`, `is_windows`). Hook w `require_binary` odwróciłby kierunek (platform → setup) i dał cykl importów łatany lazy-importem — warstwa niskopoziomowa nie powinna znać sieci i manifestu.
2. **`binaries.py` zostaje nietknięte** — reguła „zero zmian w `binaries.py` i `doctor.py`" z 1.4 dalej obowiązuje co do litery. `resolve_binary`/`require_binary` działają jak dziś; `require_binary` już sugeruje `anishift setup` w komunikacie błędu.
3. **Warstwa setup to naturalny dom** dla wszystkiego, co dotyka manifestu i sieci; kod domenowy i tak importuje z góry na dół (`services → setup/platform`).

**Zakres etapu 2.5 vs etapy 3/6 (jasne rozgraniczenie):** w etapie 2.5 **nie ma jeszcze funkcji domenowych** (ekstrakcja = etap 3, audio = etap 6), więc etap 2.5 dostarcza **MECHANIZM** — `ensure_binary`/`ensure_resource` z testami jednostkowymi + `/setup`/`anishift setup` — a etapy 3/6 go **WOŁAJĄ** (pierwsze realne wywołanie `ensure_binary(Binary.MKVEXTRACT)` dojdzie w etapie 3 razem z ekstrakcją). Smoke na żywo w etapie 2.5: przez `/setup`/`anishift setup` (ścieżka zbiorcza) oraz jednorazowe `python -c` z `ensure_binary` (ścieżka leniwa) — patrz zadanie 6.

## 1.7 Wymagania — wersja ostateczna

### Funkcjonalne

| # | Wymaganie |
|---|-----------|
| R1 | **Leniwe pobieranie na żądanie:** funkcja domenowa woła `ensure_binary(...)` przed użyciem binarki — brakujący zasób (brak pliku lub rozmiar 0) pobiera się dopiero wtedy, JEDEN, z paskiem. Start shella = natychmiastowy, ZERO pobierania i zero sieci. `/setup` = jawne pobranie wszystkiego z góry. Zero ręcznych kroków dla usera. |
| R2 | Zasób obecny i niepusty → skip, zero sieci — `ensure_binary` z obecną binarką nie czyta nawet manifestu. |
| R3 | SHA256 **archiwum** weryfikowany przed rozpakowaniem; niezgodny = odrzucony, nic nie ląduje w `external/bin/`. Manifest = SSOT hashy/rozmiarów/URL-i. |
| R4 | Pasek postępu (`ProgressBarManager`, styl blocks, %, MB, prędkość, czas) — jeden zbiorczy w `run_setup`, pojedynczy per zasób w `ensure_resource`. |
| R5 | `/setup` (shell) i `anishift setup` (terminal) — jawne „pobierz wszystko z góry teraz" (recovery / offline-prep; pobierz brakujące, no-op gdy komplet). |
| R6 | `run_setup` pobiera zasoby równolegle (max 2 wątki), bez multi-connection na plik; `ensure_resource` pobiera jeden zasób synchronicznie. |
| R7 | Z archiwów `.7z`/`.zip` wyciągane TYLKO pliki z manifestu; reszta ginie z tempem. |
| R8 | Manifest (`external/bin_hashes.json`, klucz `resources`) opisuje wszystko: type, url, sha256, size_bytes, archive, members. Nowy zasób = nowy wpis. |
| R9 | `/setup force` (shell; token opcji, nie flaga uniksowa) / `anishift setup --force` (terminal) — wymuszone ponowne pobranie wszystkiego (naprawa uszkodzonych-ale-obecnych plików). |
| R10 | Twarda walidacja manifestu przy wczytaniu (`ManifestError`, fail-loud). |
| R11 | Aktualizacja `docs/plans/etap-8-dystrybucja-binarek.md` i `docs/plans/_index.md` (binarki → 2.5). |
| R12 | Completer opcji w shellu: po `/<znana-komenda>` + spacja podpowiadane są opcje tej komendy (prefix match, opis jako meta); SSOT = `Command.options`, z którego derywują completer i `dispatch`. |

### Niefunkcjonalne

| # | Wymaganie |
|---|-----------|
| N1 | Żaden błąd pobierania (sieć, serwer, dysk, archiwum, Ctrl+C) nie wywala apki. `run_setup`: raport per zasób zamiast wyjątku. `ensure_resource`/`ensure_binary`: czytelny błąd domenowy (`InstallerError` z `ErrorContext` — code, message, suggestion), nigdy surowy traceback httpx/OSError. |
| N2 | Atomowość: temp → hash → extract do stage → move do `external/bin/`. Temp sprząta się sam (`TemporaryDirectory`). |
| N3 | Generyczność tania: pole `type` w manifeście; installer nie zna pojęcia „binarka" poza mapowaniem type→katalog docelowy. |
| N4 | Zasoby poza gitem (`external/bin/` gitignored — już jest). |
| N5 | Wersje pinowane (URL + hash w manifeście); aktualizacja = świadoma zmiana manifestu. |
| N6 | Guard path-traversal: walidacja `dest` przy wczytaniu manifestu + re-check `resolve().is_relative_to()` przy zapisie. |
| N7 | Windows-only utrzymywane; `is_windows()`/PATH-fallback w `binaries.py` nietknięte; na innym OS zasoby `binary` = `unavailable`, zero pobierania, zero crasha. |
| N8 | Testowalność bez sieci: wstrzykiwany downloader (`DownloadFn`), syntetyczne archiwa zip w testach. |

### Edge case'y — tablica ostateczna

| # | Sytuacja | Zachowanie (mechanizm) |
|---|----------|------------------------|
| E1 | Pierwsze użycie funkcji potrzebującej binarki (net OK) | `ensure_binary` pobiera JEDEN brakujący zasób z pojedynczym paskiem, potem funkcja działa. `/setup` pobiera wszystko z góry ze zbiorczym paskiem. Start shella nigdy nie pobiera — prompt natychmiast. |
| E2 | Brak internetu | `ensure_binary`: `httpx.HTTPError` → `InstallerError` (`NETWORK_ERROR`, sugestia „sprawdź sieć / `anishift setup`") do funkcji domenowej — czytelny błąd, nie crash. `/setup` i `anishift setup`: wynik `failed` z komunikatem w raporcie, REPL/terminal działa dalej; doctor czerwony. |
| E3 | Net pada w trakcie | Częściowy plik tylko w tempie; temp skasowany; `external/bin/` nietknięte; retry = następne wywołanie `ensure_binary` albo `/setup`. |
| E4 | Zły hash | `HashMismatchError` → `failed`, nic nie ląduje w docelowym; drugi zasób leci dalej. |
| E5 | Zasoby już zainstalowane (komplet) | `ensure_binary` → `resolve_binary` trafia od razu (zero manifestu, zero sieci); `/setup` → same skipy. Każdy start shella jest natychmiastowy niezależnie od stanu `external/bin/`. |
| E6 | Częściowa instalacja | Per-zasób niezależnie: gotowy skip, brakujący pobierany. |
| E7 | Nowsza wersja upstream | Ignorowana (N5) — bierzemy wersję z manifestu; URL-e datowane/niezmienne (patrz 1.5), więc hash nie ma prawa się rozjechać. Aktualizacja = świadomy re-pin manifestu. |
| E8 | 404/503/timeout | `raise_for_status()`/`httpx.TimeoutException` → `failed`, inne lecą dalej. |
| E9 | Inny OS | `run_setup` → `unavailable` (jawnie w `/setup` i `anishift setup`); `ensure_resource` → cichy no-op; `resolve_binary` szuka w PATH. |
| E10 | Brak miejsca na dysku | `OSError` → `run_setup`: `failed`; `ensure_resource`: `InstallerError` (`IO_ERROR`). Nie crashuje. |
| E11 | Ctrl+C w trakcie | `run_setup`: cancel-event → wątki przerywają w <1 s, temp skasowany, wynik `cancelled`, shell wraca do promptu. `ensure_resource` (jeden wątek): `KeyboardInterrupt` do wołającego, temp skasowany, `external/bin/` bez śmieci. |
| E12 | Member ≠ zawartość archiwum | `InstallerError` „member not found" → `failed`, inne dalej. |
| E13 | Złośliwa ścieżka (`../`) | Odrzucona na 2 warstwach (loader + extract). |
| E14 | Brak `external/bin/` | `mkdir(parents=True, exist_ok=True)`. |
| E15 | Uszkodzone archiwum | `BadZipFile`/`ArchiveError` → `InstallerError` → `failed`; (praktycznie nieosiągalne — hash weryfikowany wcześniej). |
| E16 | Zepsuty manifest | `ManifestError` fail-loud: `anishift setup` → exit 1; `/setup` → czerwony komunikat, REPL dalej; `ensure_*` → wyjątek do funkcji domenowej (pipeline pokazuje, apka żyje). Start shella nie czyta manifestu. |

### Definition of Done

- [ ] `uv run anishift` (goły start) wchodzi do shella **natychmiast, z zerowym pobieraniem i zerem sieci** — nawet przy pustym `external/bin/`
- [ ] `ensure_binary(Binary.X)` z obecną binarką = ścieżka od ręki (zero manifestu, zero sieci); z brakującą (Windows, net OK) = pobiera JEDEN zasób z paskiem i zwraca ścieżkę
- [ ] `ensure_resource`/`ensure_binary` przy braku sieci rzucają czytelny `InstallerError` z sugestią (błąd domenowy), nie surowy traceback
- [ ] Zły hash / brak sieci / błąd serwera / brak dysku / Ctrl+C NIE crashują apki
- [ ] Nic nie ląduje w `external/bin/` bez zgodnego SHA256 archiwum
- [ ] `anishift doctor` zielony po pobraniu (bez zmian w doctorze)
- [ ] `/setup`/`anishift setup` pobiera 2 zasoby równolegle, wspólny pasek `ProgressBarManager`
- [ ] Manifest generyczny (pole `type`) — model AI = nowy wpis + literal, nie nowy pobieracz
- [ ] `/setup` (shell) oraz `anishift setup` i `anishift setup --force` (terminal) działają jak w R5/R9 (jawne „pobierz wszystko teraz")
- [ ] po wpisaniu `/setup ` (ze spacją) completer pokazuje inline opcję `force` z opisem; `/setup force` wymusza pełny re-download; `/setup blah` = czytelny komunikat o nieznanej opcji, nie crash
- [ ] ffmpeg w manifeście wskazuje **datowany, niezmienny** release BtbN (nie ruchomy tag `latest`)
- [ ] `binaries.py` i `doctor.py` nietknięte; kod nie wywala się na innym OS
- [ ] Testy bez sieci zielone; bramki: ruff check + format + mypy + pytest
- [ ] `docs/plans/etap-8` i `_index.md` zaktualizowane (R11)

---

# SEKCJA 2 — ISSUE DO GITHUBA

> Do wklejenia w template **✨ Feature** (`.github/ISSUE_TEMPLATE/feature.yml`). Tytuł: `feat: external resource downloader — lazy install of mkvtoolnix + ffmpeg (stage 2.5)`

**Goal**

AniShift depends on external binaries (mkvtoolnix's `mkvextract`/`mkvmerge` for stage 3, ffmpeg's `ffmpeg`/`ffprobe` for stages 6-7), but today `external/bin/` is empty and the manifest (`external/bin_hashes.json`) is a stub. The app must be idiot-proof without taxing startup: the shell opens instantly with zero downloads, and a missing tool is downloaded, SHA256-verified and unpacked into `external/bin/` **lazily, on first use** — domain code calls `ensure_binary(...)` right before running a tool (stage 3 for mkvtoolnix, stage 6 for ffmpeg), which fetches just that one resource with a live progress bar. `/setup` (shell) and `anishift setup` (terminal) remain as the explicit "download everything up front now" path. No manual setup step required, no binaries in git, versions pinned by the manifest. This stage ships the mechanism plus tests; stages 3/6 add the real call sites.

**Scope / how to do it**

- Fill `external/bin_hashes.json` (generic `resources` manifest: type, url, sha256, size, archive format, members to extract) with pinned mkvtoolnix 100.0 (7z) and ffmpeg win64 gpl (zip) builds; ffmpeg pinned to a **dated, immutable** BtbN autobuild release (never the moving `latest` tag).
- New `anishift/setup/manifest.py` (typed loader + validation) and `anishift/setup/installer.py` (download → verify hash → extract named members with a path-traversal guard → atomic move; `run_setup()` downloads two resources in parallel behind one shared `ProgressBarManager` bar with Ctrl+C-safe cancel; `ensure_resource(name)` / `ensure_binary(binary)` install a single missing resource on demand with its own bar and raise a typed domain error on failure — the lazy entry point stages 3/6 will call).
- No download hook at shell start — the shell must open instantly. Explicit commands instead: `/setup [force]` in the shell — no unix flags inside the shell; `Command` gains an `options` field (token → description) as the single source of truth, the `SlashCompleter` becomes two-level (commands after `/`, the command's options after `/<command> `, Claude-Code style) and `dispatch` validates option tokens — plus `anishift setup [--force]` from the terminal.
- Windows-only downloads; on other OSes resources report `unavailable` and the existing PATH fallback in `binaries.py` applies. `binaries.py` and `doctor.py` stay untouched.
- New dependency: `py7zr` (7z extraction); zip is stdlib. Tests run without network (injected downloader, synthetic archives).
- Docs: move the binary-distribution scope out of stage 8 into this stage (update `docs/plans/etap-8-*.md` and `_index.md`).

**Area:** infra

**Size:** medium (a few days)

**Definition of done**

- [ ] `anishift` (bare launch) enters the shell instantly with zero downloads and zero network, even with an empty `external/bin/`
- [ ] `ensure_binary(...)` resolves an installed tool with zero cost, downloads exactly one missing resource with a progress bar, and raises a typed domain error (clear message + suggestion) when offline — never a raw traceback
- [ ] Nothing lands in `external/bin/` unless the archive SHA256 matches the manifest
- [ ] Bad hash / no network / server error / disk full / Ctrl+C never crash the app
- [ ] `/setup` in the shell downloads everything up front (the completer suggests the `force` option after a space; `/setup force` = full reinstall) and `anishift setup [--force]` works from the terminal; `anishift doctor` goes green after install
- [ ] `run_setup` downloads two resources in parallel; manifest is generic (a `type` field) so future AI models are a manifest entry, not a rewrite
- [ ] Tests green without network; ruff + format + mypy + pytest gates pass
- [ ] Stage 8 plan and plans index updated (binaries moved to stage 2.5)

---

# SEKCJA 3 — PEŁNY PLAN IMPLEMENTACJI

## 3.1 DRZEWO KATALOGÓW — co powstaje, co się zmienia

```
<repo root>
├── pyproject.toml                        # ZMIANA (przez `uv add py7zr` — nigdy ręcznie)
├── uv.lock                               # ZMIANA (automatycznie z uv add)
├── external/
│   ├── bin_hashes.json                   # ZMIANA — manifest wypełniony (mkvtoolnix + ffmpeg,
│   │                                     #   klucz `resources`, pole `type` per zasób)
│   └── bin/                              # (gitignored — tu lądują pobrane pliki; NIE w repo)
│       ├── mkvtoolnix/                   #   mkvextract.exe, mkvmerge.exe   ← wynik działania
│       └── ffmpeg/                       #   ffmpeg.exe, ffprobe.exe        ← wynik działania
├── anishift/
│   ├── setup/
│   │   ├── __init__.py                   # ZMIANA — tylko docstring (installer już nie „later")
│   │   ├── doctor.py                     # BEZ ZMIAN (obecność binarek już sprawdza)
│   │   ├── manifest.py                   # NOWY — wczytanie + walidacja manifestu → typy
│   │   │                                 #   (Resource, Member, load_manifest, ManifestError)
│   │   └── installer.py                  # NOWY — serce etapu: download → hash → extract →
│   │                                     #   move; ensure_resource()/ensure_binary() leniwe
│   │                                     #   per zasób (pojedynczy pasek, typowane błędy);
│   │                                     #   run_setup() równoległy z paskiem i Ctrl+C
│   ├── platform/
│   │   └── binaries.py                   # BEZ ZMIAN — leniwy most (ensure_binary) mieszka w
│   │                                     #   installer.py, żeby nie odwracać zależności
│   │                                     #   platform→setup (uzasadnienie: 1.6)
│   └── cli/
│       ├── main.py                       # ZMIANA — subkomenda Typer `setup` (--force; poza shellem)
│       ├── commands.py                   # ZMIANA — Command.options (SSOT opcji) + komenda /setup +
│       │                                 #   dispatch walidujący tokeny opcji (`/setup force`)
│       ├── completer.py                  # ZMIANA — SlashCompleter dwupoziomowy: komendy po `/`,
│       │                                 #   opcje komendy po `/<komenda> ` (spacja)
│       └── shell.py                      # BEZ ZMIAN — start shella nic nie pobiera (v2.1);
│                                         #   żadnego hooka po bannerze
├── tests/
│   ├── test_manifest.py                  # NOWY — walidacja manifestu (w tym realnego pliku)
│   ├── test_installer.py                 # NOWY — hash, extract, traversal, skip, force,
│   │                                     #   run_setup: izolacja błędów, cancel, non-Windows
│   ├── test_commands.py                  # ZMIANA — /setup: dispatch opcji (force), nieznana opcja
│   ├── test_completer.py                 # ZMIANA — podpowiedzi opcji po `/setup ` (dwupoziomowość)
│   └── test_setup_cli.py                 # NOWY — komenda Typer `anishift setup` (CliRunner)
└── docs/plans/
    ├── etap-8-dystrybucja-binarek.md     # ZMIANA — binarki wyprowadzone (zostaje migracja+kasacje)
    └── _index.md                         # ZMIANA — wiersz 2.5, graf zależności, zależność etapu 3
```

**Podział odpowiedzialności (1 plik = 1 zadanie):**

| Plik | Odpowiada za | NIE odpowiada za |
|------|--------------|------------------|
| `manifest.py` | JSON → typy (`Resource`, `Member`), twarda walidacja, `ManifestError` | pobieranie, pliki na dysku |
| `installer.py` | download (httpx stream), SHA256, rozpakowanie 7z/zip, atomowy move, paski; leniwie: `ensure_resource`/`ensure_binary` (jeden zasób, typowane błędy); zbiorczo: `run_setup` (równoległość, cancel, raport) | wiedza co jest w manifeście (dostaje typy), rendering CLI, wołanie ensure z funkcji domenowych (to etapy 3/6) |
| `commands.py` (`/setup`) | deklaracja opcji w `Command.options` (SSOT), walidacja tokenów opcji w `dispatch`, handler wołający `run_setup(force=...)`, raport ikonkami (`print_setup_report`) | logika instalacji |
| `completer.py` | podpowiedzi dwupoziomowe (komendy po `/`, opcje po `/<komenda> `) — wszystko derywowane z `COMMANDS` | wiedza co opcje robią |
| `main.py` (`setup`) | subkomenda Typer z flagą `--force` (poza shellem), exit code | logika instalacji, rendering raportu (bierze `print_setup_report` z `commands.py`) |

`shell.py` celowo NIE ma wiersza — start shella nic nie pobiera (v2.1); plik zostaje nietknięty w tym etapie.

## 3.2 PUBLICZNE API — jak się to woła

Dwa punkty wejścia — **leniwy** (kod domenowy, 99% przypadków od etapu 3) i **zbiorczy** (komendy setup):

```python
# ── LENIWY — funkcja domenowa woła tuż przed użyciem binarki ────────────────
from anishift.platform.binaries import Binary
from anishift.setup.installer import ensure_binary

# Etap 3 (ekstrakcja) — dokładnie tak będzie to wołane:
mkvextract = ensure_binary(Binary.MKVEXTRACT)   # -> Path

# Etap 6 (audio) — analogicznie:
ffmpeg = ensure_binary(Binary.FFMPEG)           # -> Path

# Semantyka: binarka jest → ścieżka od ręki (zero manifestu, zero sieci).
# Nie ma (Windows) → pobiera JEDEN zasób z paskiem, potem zwraca ścieżkę.
# Błąd (sieć/dysk/hash) → InstallerError z ErrorContext (czytelny błąd domenowy).
# Nie ma i nie da się pobrać (inny OS bez PATH, brak wpisu) → BinaryNotFoundError.

# Niżej: ensure_resource("mkvtoolnix") — ten sam mechanizm per zasób z manifestu,
# dla przyszłych zasobów nie-binarkowych (type != "binary").

# ── ZBIORCZY — tylko `/setup` (shell) i `anishift setup` (terminal) ─────────
from anishift.setup.installer import run_setup

# Jawne „pobierz wszystko z góry teraz" (recovery / offline-prep).
# NIGDY nie rzuca za błędy zasobów (sieć/dysk/hash/Ctrl+C → wpis w raporcie).
# Rzuca tylko ManifestError (fail-loud, błąd dewelopera).
report = run_setup()                    # -> list[ResourceResult]

# `/setup force` (shell) i `anishift setup --force` (terminal) — wszystko od zera (naprawa).
report = run_setup(force=True)

for result in report:
    print(result.name, result.outcome, result.detail)
    # outcome: "installed" | "skipped" | "failed" | "unavailable" | "cancelled"
```

**Etap 2.5 dostarcza mechanizm, etapy 3/6 go wołają:** w tym etapie nie istnieje jeszcze żadna funkcja domenowa, więc `ensure_binary`/`ensure_resource` powstają z pełnymi testami jednostkowymi (+ smoke `python -c` w zadaniu 6), a pierwsze produkcyjne wywołanie dojdzie w etapie 3 razem z ekstrakcją.

Pełna powierzchnia modułów (sygnatury docelowe):

```python
# anishift/setup/manifest.py
ResourceType  = Literal["binary"]                 # przyszły model AI = nowy literal
ArchiveFormat = Literal["7z", "zip"]
Member(archive_path: str, dest: str)                              # frozen, slots
Resource(name, type, url, sha256, size_bytes, archive, members)   # frozen, slots
class ManifestError(FatalError): ...
def manifest_path() -> Path                        # <repo>/external/bin_hashes.json
def load_manifest(path: Path | None = None) -> tuple[Resource, ...]   # raises ManifestError

# anishift/setup/installer.py
ResourceOutcome = Literal["installed", "skipped", "failed", "unavailable", "cancelled"]
ResourceResult(name: str, outcome: ResourceOutcome, detail: str)  # frozen, slots
class InstallerError(FatalError): ...
class HashMismatchError(InstallerError): ...       # ErrorCode.BINARY_HASH_MISMATCH
class InstallCancelledError(InstallerError): ...   # ErrorCode.CANCELLED
def sha256_file(path: Path) -> str
def is_installed(resource: Resource, dest_root: Path) -> bool
def extract_members(archive: Path, resource: Resource, dest_root: Path) -> None
def install_resource(resource, *, dest_root, download=..., force=False) -> ResourceResult
def ensure_resource(name, *, resources=None, dest_root=None) -> None   # leniwie: JEDEN zasób
def ensure_binary(binary: Binary) -> Path                              # leniwie: resolve → ensure → resolve
def run_setup(*, force=False, resources=None, dest_root=None) -> list[ResourceResult]

# anishift/cli/commands.py (warstwa shella — opcje komend w stylu Claude Code)
Command(name, summary, handler, options={})     # options: dict[opcja → opis] = SSOT completera i dispatch
#   handler: Callable[[AppContext, frozenset[str]], bool] — dostaje zbiór włączonych tokenów opcji
def print_setup_report(results: list[ResourceResult]) -> None   # wspólny rendering raportu (/setup + Typer)
def dispatch(text: str, context: AppContext) -> bool   # tokeny po komendzie muszą być znanymi opcjami
```

Zasady projektowe: `ensure_binary` = punkt wejścia dla kodu domenowego (etapy 3/6); `run_setup` = punkt wejścia dla `/setup` i `anishift setup`; `download: DownloadFn = Callable[[Resource, Path], None]` wstrzykiwany w `install_resource`, a testy `ensure_*`/`run_setup` monkeypatchują `installer._download_httpx` (N8 — testy bez sieci); parametry `resources`/`dest_root` to overridy pod testy; żadnych globali, żadnego stanu między wywołaniami. Rozdział semantyk błędów jest celowy: ścieżka leniwa **rzuca** (wołający nie może kontynuować bez binarki), ścieżka zbiorcza **raportuje** (user ma zobaczyć pełny obraz wszystkich zasobów).

## 3.3 Fakty (mkvtoolnix verbatim z v1 — zweryfikowany, nie liczyć od nowa; ffmpeg = PLACEHOLDERY do obowiązkowego re-pinu w zadaniu 1)

| Zasób | Wartość |
|-------|---------|
| mkvtoolnix URL | `https://mkvtoolnix.download/windows/releases/100.0/mkvtoolnix-64-bit-100.0.7z` |
| mkvtoolnix sha256 | `061de38bd10e7e28697b897e0b890b78d6f2ec8d668a9c198600ed45c19672ab` |
| mkvtoolnix size | `29708584` B · format `7z` · members: `mkvtoolnix/mkvextract.exe`, `mkvtoolnix/mkvmerge.exe` |
| ffmpeg URL ⚠️ | `https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip` — **TYMCZASOWY placeholder z v1** (ruchomy tag); zadanie 1 OBOWIĄZKOWO zastępuje go datowanym release'em (USTALONE, patrz 1.5) |
| ffmpeg sha256 ⚠️ | `6f0c5e3e1ecf447ea52448fb9111f1c7429ae93d95ce71b80e2761053154a20e` — **placeholder**, przeliczany w re-pinie (zadanie 1) |
| ffmpeg size ⚠️ | `168699965` B — **placeholder** · format `zip` · members: `.../bin/ffmpeg.exe`, `.../bin/ffprobe.exe` (prefiks `archive_path` weryfikowany w re-pinie — nazwa folderu w datowanym zipie może się różnić; pola `dest` bez zmian) |

Nowa zależność: **`py7zr`** (7z; zip = stdlib `zipfile`). `httpx` już jest w zależnościach. ffplay nie bierzemy; balcon = etap 6.

## 3.4 Zadania

Branch: `feat/etap-2.5-pobieracz-binarek` (od `main`, po zmergowaniu etapu 2). Po każdym zadaniu bramki jakości:

```bash
uv run ruff check anishift/ tests/
uv run ruff format --check anishift/ tests/
uv run mypy anishift/ tests/
uv run pytest
```

---

### Zadanie 1 — zależność py7zr + wypełnienie manifestu

**Kroki:**

```bash
git checkout main && git pull && git checkout -b feat/etap-2.5-pobieracz-binarek
uv add py7zr
```

Nadpisz `external/bin_hashes.json` (wpis ffmpeg poniżej zawiera **placeholdery z v1** — url/sha256/size_bytes oraz prefiks `archive_path` członków zastępuje OBOWIĄZKOWY krok re-pin niżej, PRZED commitem):

```json
{
  "$schema_note": "Manifest of external resources: per resource a type (binary; AI models may come later), archive URL + SHA256 + size (bytes) + members to extract. Lazy on-demand installs (ensure_binary/ensure_resource) and `anishift setup` download and verify against this. Windows (win64) builds; non-Windows falls back to PATH.",
  "resources": {
    "mkvtoolnix": {
      "type": "binary",
      "url": "https://mkvtoolnix.download/windows/releases/100.0/mkvtoolnix-64-bit-100.0.7z",
      "sha256": "061de38bd10e7e28697b897e0b890b78d6f2ec8d668a9c198600ed45c19672ab",
      "size_bytes": 29708584,
      "archive": "7z",
      "members": [
        { "archive_path": "mkvtoolnix/mkvextract.exe", "dest": "mkvtoolnix/mkvextract.exe" },
        { "archive_path": "mkvtoolnix/mkvmerge.exe", "dest": "mkvtoolnix/mkvmerge.exe" }
      ]
    },
    "ffmpeg": {
      "type": "binary",
      "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
      "sha256": "6f0c5e3e1ecf447ea52448fb9111f1c7429ae93d95ce71b80e2761053154a20e",
      "size_bytes": 168699965,
      "archive": "zip",
      "members": [
        { "archive_path": "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe", "dest": "ffmpeg/ffmpeg.exe" },
        { "archive_path": "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe", "dest": "ffmpeg/ffprobe.exe" }
      ]
    }
  }
}
```

`dest` mapuje się 1:1 na układ `_TOOL_DIR` z `binaries.py` (mkvextract/mkvmerge → `mkvtoolnix/`, ffmpeg/ffprobe → `ffmpeg/`) — dzięki temu `resolve_binary` znajduje pliki bez żadnej zmiany.

**Krok OBOWIĄZKOWY — re-pin ffmpeg na datowany, niezmienny release BtbN (USTALONE, patrz 1.5; wykonaj PRZED weryfikacją i commitem):**

```powershell
# 1. Wejdź na https://github.com/BtbN/FFmpeg-Builds/releases i wybierz NAJNOWSZY DATOWANY release
#    (tag w stylu autobuild-YYYY-MM-DD-HH-MM) — NIGDY ruchomy tag `latest`. Skopiuj URL assetu
#    win64-gpl (zip) z tego release'u i pobierz go:
curl.exe -L -o ffmpeg.zip "<datowany-URL>"
# 2. Przelicz hash i rozmiar:
uv run python -c "import hashlib,pathlib; p=pathlib.Path('ffmpeg.zip'); print(hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_size)"
# 3. Sprawdź nazwę folderu najwyższego poziomu w zipie (w datowanym buildzie może różnić się od
#    `ffmpeg-master-latest-win64-gpl`) i w razie potrzeby popraw `archive_path` obu członków
#    (pola `dest` zostają bez zmian):
uv run python -c "import zipfile; print(sorted({n.split('/')[0] for n in zipfile.ZipFile('ffmpeg.zip').namelist()}))"
# 4. Wpisz datowany url + przeliczony sha256 + size_bytes (i ewentualnie archive_path) do
#    external/bin_hashes.json; usuń ffmpeg.zip.
```

Ta sama procedura służy później do świadomej aktualizacji wersji (N5) — zawsze na kolejny datowany release, nigdy `latest`.

**Weryfikacja:**

```bash
uv run python -c "import json,pathlib; d=json.loads(pathlib.Path('external/bin_hashes.json').read_text(encoding='utf-8')); print(sorted(d['resources'])); assert '/download/latest/' not in d['resources']['ffmpeg']['url'], 'ffmpeg still points at the moving latest tag'; import py7zr; print('py7zr OK')"
# oczekiwane: ['ffmpeg', 'mkvtoolnix'] + py7zr OK (assert pilnuje datowanego URL-a ffmpeg)
```

**Commit:**

```bash
git add external/bin_hashes.json pyproject.toml uv.lock
git commit -m "feat(setup): fill resource manifest and add py7zr"
```

---

### Zadanie 2 — loader manifestu `manifest.py` (TDD)

**Krok 1 — testy (najpierw, mają się wywalić na ImportError).** Utwórz `tests/test_manifest.py`:

```python
"""Tests for the resource-manifest loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.setup.manifest import (
    ManifestError,
    Resource,
    load_manifest,
    manifest_path,
)


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "bin_hashes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _raw_resource(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "type": "binary",
        "url": "https://example.test/a.zip",
        "sha256": "ab" * 32,
        "size_bytes": 10,
        "archive": "zip",
        "members": [{"archive_path": "a/x.exe", "dest": "tool/x.exe"}],
    }
    raw.update(overrides)
    return raw


def test_real_manifest_loads_both_resources() -> None:
    resources = load_manifest(manifest_path())
    assert {r.name for r in resources} == {"mkvtoolnix", "ffmpeg"}


def test_real_manifest_dests_match_binaries_layout() -> None:
    by_name = {r.name: r for r in load_manifest(manifest_path())}
    assert {m.dest for m in by_name["mkvtoolnix"].members} == {
        "mkvtoolnix/mkvextract.exe",
        "mkvtoolnix/mkvmerge.exe",
    }
    assert {m.dest for m in by_name["ffmpeg"].members} == {"ffmpeg/ffmpeg.exe", "ffmpeg/ffprobe.exe"}


def test_load_returns_typed_resources(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"tool": _raw_resource()}})
    resources = load_manifest(path)
    assert len(resources) == 1
    resource = resources[0]
    assert isinstance(resource, Resource)
    assert resource.name == "tool"
    assert resource.type == "binary"
    assert resource.members[0].dest == "tool/x.exe"


def test_missing_resources_key_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"binaries": {}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_unknown_type_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(type="model")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_bad_archive_format_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(archive="rar")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_bad_sha256_length_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(sha256="abc")}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_empty_members_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, {"resources": {"t": _raw_resource(members=[])}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_member_dest_traversal_raises(tmp_path: Path) -> None:
    member = {"archive_path": "a", "dest": "../evil.exe"}
    path = _write(tmp_path, {"resources": {"t": _raw_resource(members=[member])}})
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_corrupt_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bin_hashes.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "nope.json")
```

`uv run pytest tests/test_manifest.py -q` → **FAIL** (ImportError) — dobrze.

**Krok 2 — implementacja.** Utwórz `anishift/setup/manifest.py`:

```python
"""Load and validate the external-resource manifest (``bin_hashes.json``).

The manifest is the single source of truth for what the resource installer
downloads: per resource a ``type``, the archive URL, its SHA256 and size, and
the members to extract. Adding a resource — including a future AI model — is
a new manifest entry plus at most a new ``type`` literal, not a new
downloader.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from anishift.errors import ErrorCode, ErrorContext, FatalError

__all__ = [
    "ArchiveFormat",
    "ManifestError",
    "Member",
    "Resource",
    "ResourceType",
    "load_manifest",
    "manifest_path",
]

ResourceType = Literal["binary"]
"""Kinds of downloadable resources (a future AI model adds a literal here)."""

ArchiveFormat = Literal["7z", "zip"]
"""Supported archive container formats."""

# ── Constants ────────────────────────────────────────────────────────────────

_RESOURCE_TYPES: Final[frozenset[str]] = frozenset(("binary",))
"""Accepted values of the manifest ``type`` field."""

_ARCHIVE_FORMATS: Final[frozenset[str]] = frozenset(("7z", "zip"))
"""Accepted values of the manifest ``archive`` field."""

_SHA256_HEX_LENGTH: Final[int] = 64
"""Length of a SHA256 digest in hexadecimal characters."""


class ManifestError(FatalError):
    """Raised when the resource manifest is missing or malformed."""


@dataclass(frozen=True, slots=True)
class Member:
    """One file to extract from a resource archive.

    Attributes:
        archive_path: Path of the member inside the archive.
        dest: Destination relative to the resource's install root (no ``..``).
    """

    archive_path: str
    dest: str


@dataclass(frozen=True, slots=True)
class Resource:
    """One downloadable resource: an archive plus the members to install.

    Attributes:
        name: Resource name (also the manifest key), e.g. ``"ffmpeg"``.
        type: Resource kind; decides the install root (binary -> ``external/bin/``).
        url: Download URL of the archive.
        sha256: Expected SHA256 of the downloaded archive (lowercase hex).
        size_bytes: Expected archive size in bytes.
        archive: Container format of the download.
        members: Files to extract from the archive.
    """

    name: str
    type: ResourceType
    url: str
    sha256: str
    size_bytes: int
    archive: ArchiveFormat
    members: tuple[Member, ...]


def _repo_root() -> Path:
    """Return the repository root (ancestor holding ``pyproject.toml``)."""
    return Path(__file__).resolve().parents[2]


def manifest_path() -> Path:
    """Return ``<repo>/external/bin_hashes.json``."""
    return _repo_root() / "external" / "bin_hashes.json"


def _fail(message: str) -> ManifestError:
    """Build a :class:`ManifestError` with a consistent context."""
    return ManifestError(
        context=ErrorContext(
            code=ErrorCode.CONFIG_INVALID,
            message=f"resource manifest: {message}",
            suggestion="external/bin_hashes.json is broken — fix it or report a bug",
        ),
    )


def _parse_member(raw: Any) -> Member:
    """Validate and build a :class:`Member` from raw JSON."""
    if not isinstance(raw, dict):
        raise _fail("member must be an object")
    archive_path = raw.get("archive_path")
    dest = raw.get("dest")
    if not isinstance(archive_path, str) or not isinstance(dest, str):
        raise _fail("member needs string archive_path and dest")
    if not archive_path or not dest:
        raise _fail("member archive_path and dest must be non-empty")
    if Path(dest).is_absolute() or ".." in Path(dest).parts:
        raise _fail(f"member dest escapes the install root: {dest}")
    return Member(archive_path=archive_path, dest=dest)


def _parse_resource(name: str, raw: Any) -> Resource:
    """Validate and build a :class:`Resource` from raw JSON."""
    if not isinstance(raw, dict):
        raise _fail(f"resource {name} must be an object")
    kind = raw.get("type")
    url = raw.get("url")
    sha256 = raw.get("sha256")
    size_bytes = raw.get("size_bytes")
    archive = raw.get("archive")
    members = raw.get("members")
    if kind not in _RESOURCE_TYPES:
        raise _fail(f"resource {name} has unsupported type: {kind!r}")
    if not isinstance(url, str) or not url:
        raise _fail(f"resource {name} needs a non-empty url")
    if not isinstance(sha256, str) or len(sha256) != _SHA256_HEX_LENGTH:
        raise _fail(f"resource {name} needs a {_SHA256_HEX_LENGTH}-char sha256")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
        raise _fail(f"resource {name} needs a positive integer size_bytes")
    if archive not in _ARCHIVE_FORMATS:
        raise _fail(f"resource {name} has unsupported archive: {archive!r}")
    if not isinstance(members, list) or not members:
        raise _fail(f"resource {name} needs a non-empty members list")
    return Resource(
        name=name,
        type=cast(ResourceType, kind),
        url=url,
        sha256=sha256.lower(),
        size_bytes=size_bytes,
        archive=cast(ArchiveFormat, archive),
        members=tuple(_parse_member(member) for member in members),
    )


def load_manifest(path: Path | None = None) -> tuple[Resource, ...]:
    """Load and validate the resource manifest.

    Args:
        path: Manifest file (defaults to :func:`manifest_path`).

    Returns:
        Parsed resources in manifest order.

    Raises:
        ManifestError: When the file is missing, unparseable, or malformed.
    """
    target = path if path is not None else manifest_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _fail(f"cannot read {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise _fail(f"not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("resources"), dict):
        raise _fail("top-level 'resources' object is required")
    return tuple(_parse_resource(name, body) for name, body in raw["resources"].items())
```

**Krok 3 — bramki + testy zielone, commit:**

```bash
git add anishift/setup/manifest.py tests/test_manifest.py
git commit -m "feat(setup): typed resource-manifest loader with validation"
```

---

### Zadanie 3 — installer `installer.py` z leniwym `ensure_binary`/`ensure_resource` (TDD)

**Krok 1 — testy (najpierw; syntetyczne zipy, zero sieci).** Utwórz `tests/test_installer.py`:

```python
"""Tests for the resource installer (no network — synthetic archives)."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import httpx
import pytest

from anishift.platform import binaries
from anishift.platform.binaries import Binary, BinaryNotFoundError
from anishift.setup import installer
from anishift.setup.installer import (
    HashMismatchError,
    InstallCancelledError,
    InstallerError,
    ensure_binary,
    ensure_resource,
    extract_members,
    install_resource,
    is_installed,
    run_setup,
    sha256_file,
)
from anishift.setup.manifest import Member, Resource


def _zip(tmp_path: Path, entries: dict[str, bytes], name: str = "pkg.zip") -> Path:
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        for entry, data in entries.items():
            zf.writestr(entry, data)
    return archive


def _resource(archive: Path, members: list[Member], name: str = "tool") -> Resource:
    return Resource(
        name=name,
        type="binary",
        url=f"https://example.test/{name}.zip",
        sha256=sha256_file(archive),
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=tuple(members),
    )


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    file = tmp_path / "x.bin"
    file.write_bytes(b"hello world")
    assert sha256_file(file) == hashlib.sha256(b"hello world").hexdigest()


def test_extract_members_writes_dest_tree(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/bin/tool.exe": b"MZbinary", "root/README.txt": b"junk"})
    resource = _resource(archive, [Member("root/bin/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    extract_members(archive, resource, dest_root)
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZbinary"
    assert not (dest_root / "root").exists()  # only named members land


def test_extract_members_rejects_missing_member(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/other.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    with pytest.raises(InstallerError, match="member not found"):
        extract_members(archive, resource, tmp_path / "bin")


def test_extract_members_rejects_broken_archive(tmp_path: Path) -> None:
    archive = tmp_path / "pkg.zip"
    archive.write_bytes(b"this is not a zip")
    resource = Resource(
        name="tool",
        type="binary",
        url="https://example.test/tool.zip",
        sha256="00" * 32,
        size_bytes=1,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )
    with pytest.raises(InstallerError, match="broken zip"):
        extract_members(archive, resource, tmp_path / "bin")


def test_is_installed_true_when_all_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest = tmp_path / "bin" / "tool"
    dest.mkdir(parents=True)
    (dest / "tool.exe").write_bytes(b"x")
    assert is_installed(resource, tmp_path / "bin") is True


def test_is_installed_false_when_missing(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    assert is_installed(resource, tmp_path / "bin") is False


def test_is_installed_false_when_empty_file(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest = tmp_path / "bin" / "tool"
    dest.mkdir(parents=True)
    (dest / "tool.exe").write_bytes(b"")
    assert is_installed(resource, tmp_path / "bin") is False


def test_install_resource_skips_when_present(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path) -> None:
        raise AssertionError("download must not be called when already present")

    result = install_resource(resource, dest_root=dest_root, download=_never)
    assert result.outcome == "skipped"


def test_install_resource_downloads_and_extracts(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    result = install_resource(resource, dest_root=dest_root, download=_fake)
    assert result.outcome == "installed"
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZ"


def test_install_resource_force_replaces_existing(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"NEW"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"OLD")

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    result = install_resource(resource, dest_root=dest_root, download=_fake, force=True)
    assert result.outcome == "installed"
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"NEW"


def test_install_resource_rejects_bad_hash(tmp_path: Path) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = Resource(
        name="tool",
        type="binary",
        url="https://example.test/tool.zip",
        sha256="00" * 32,
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path) -> None:
        target.write_bytes(archive.read_bytes())

    with pytest.raises(HashMismatchError):
        install_resource(resource, dest_root=dest_root, download=_fake)
    assert not (dest_root / "tool" / "tool.exe").exists()


def test_run_setup_skips_all_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    results = run_setup(resources=(resource,), dest_root=dest_root)
    assert [r.outcome for r in results] == ["skipped"]


def test_run_setup_reports_unavailable_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    monkeypatch.setattr(installer, "is_windows", lambda: False)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")
    assert [r.outcome for r in results] == ["unavailable"]


def test_run_setup_installs_missing_and_isolates_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good_archive = _zip(tmp_path, {"root/good.exe": b"MZ"}, name="good.zip")
    good = _resource(good_archive, [Member("root/good.exe", "good/good.exe")], name="good")
    bad = Resource(
        name="bad",
        type="binary",
        url="https://example.test/bad.zip",
        sha256="00" * 32,
        size_bytes=good_archive.stat().st_size,
        archive="zip",
        members=(Member("root/good.exe", "bad/bad.exe"),),
    )
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(good_archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    results = {r.name: r for r in run_setup(resources=(good, bad), dest_root=dest_root)}
    assert results["good"].outcome == "installed"
    assert results["bad"].outcome == "failed"
    assert (dest_root / "good" / "good.exe").read_bytes() == b"MZ"
    assert not (dest_root / "bad" / "bad.exe").exists()


def test_run_setup_swallows_network_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _boom(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _boom)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")  # must NOT raise
    assert [r.outcome for r in results] == ["failed"]


def test_run_setup_marks_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _cancelled(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise InstallCancelledError("cancelled")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _cancelled)
    results = run_setup(resources=(resource,), dest_root=tmp_path / "bin")
    assert [r.outcome for r in results] == ["cancelled"]


def test_ensure_resource_noop_when_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"
    (dest_root / "tool").mkdir(parents=True)
    (dest_root / "tool" / "tool.exe").write_bytes(b"x")

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)  # must not raise


def test_ensure_resource_installs_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)
    assert (dest_root / "tool" / "tool.exe").read_bytes() == b"MZ"


def test_ensure_resource_maps_network_error_to_domain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])
    dest_root = tmp_path / "bin"

    def _boom(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _boom)
    with pytest.raises(InstallerError, match="download failed"):
        ensure_resource(resource.name, resources=(resource,), dest_root=dest_root)
    assert not (dest_root / "tool" / "tool.exe").exists()


def test_ensure_resource_propagates_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"MZ"})
    resource = Resource(
        name="tool",
        type="binary",
        url="https://example.test/tool.zip",
        sha256="00" * 32,
        size_bytes=archive.stat().st_size,
        archive="zip",
        members=(Member("root/tool.exe", "tool/tool.exe"),),
    )

    def _fake(_resource: Resource, target: Path, **_kwargs: object) -> None:
        target.write_bytes(archive.read_bytes())

    monkeypatch.setattr(installer, "is_windows", lambda: True)
    monkeypatch.setattr(installer, "_download_httpx", _fake)
    with pytest.raises(HashMismatchError):
        ensure_resource("tool", resources=(resource,), dest_root=tmp_path / "bin")


def test_ensure_resource_noop_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = _zip(tmp_path, {"root/tool.exe": b"x"})
    resource = _resource(archive, [Member("root/tool.exe", "tool/tool.exe")])

    def _never(_resource: Resource, _target: Path, **_kwargs: object) -> None:
        raise AssertionError("no network calls expected off Windows")

    monkeypatch.setattr(installer, "is_windows", lambda: False)
    monkeypatch.setattr(installer, "_download_httpx", _never)
    ensure_resource(resource.name, resources=(resource,), dest_root=tmp_path / "bin")  # silent no-op


def test_ensure_resource_unknown_name_raises(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="unknown resource"):
        ensure_resource("nope", resources=(), dest_root=tmp_path / "bin")


def test_ensure_binary_resolves_installed_without_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = tmp_path / "mkvextract.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: exe)

    def _never(_name: str, **_kwargs: object) -> None:
        raise AssertionError("ensure_resource must not run when the binary resolves")

    monkeypatch.setattr(installer, "ensure_resource", _never)
    assert ensure_binary(Binary.MKVEXTRACT) == exe


def test_ensure_binary_installs_then_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "ffmpeg.exe"
    ensured: list[str] = []

    def _ensure(name: str, **_kwargs: object) -> None:
        ensured.append(name)
        exe.write_bytes(b"MZ")

    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: None)
    monkeypatch.setattr(installer, "ensure_resource", _ensure)
    monkeypatch.setattr(installer, "require_binary", lambda _binary: exe)
    assert ensure_binary(Binary.FFMPEG) == exe
    assert ensured == ["ffmpeg"]


def test_ensure_binary_unmapped_raises_binary_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "resolve_binary", lambda _binary: None)
    monkeypatch.setattr(binaries, "resolve_binary", lambda _binary: None)

    def _never(_name: str, **_kwargs: object) -> None:
        raise AssertionError("ensure_resource must not run for a binary without a resource")

    monkeypatch.setattr(installer, "ensure_resource", _never)
    with pytest.raises(BinaryNotFoundError):
        ensure_binary(Binary.BALCON)
```

`uv run pytest tests/test_installer.py -q` → **FAIL** (ImportError) — dobrze.

**Krok 2 — implementacja.** Utwórz `anishift/setup/installer.py`:

```python
"""Download and install external resources per the manifest.

For every manifest resource: skip it when its members are already present,
otherwise download the archive to a temp dir, verify its SHA256, extract only
the named members (rejecting path traversal), and move them into the install
root. Nothing lands in the live tree unless the archive verified.

Two entry points share those steps:

- ``ensure_binary`` / ``ensure_resource`` — lazy, called by domain code right
  before a tool is used; installs exactly one missing resource, synchronously,
  behind its own progress bar, and raises a typed domain error on failure.
- ``run_setup`` — explicit "download everything up front" behind `/setup` and
  ``anishift setup``; missing resources download in parallel behind one shared
  progress bar and failures become report entries, never exceptions.

Usage:
    from anishift.setup.installer import ensure_binary, run_setup

    mkvextract = ensure_binary(Binary.MKVEXTRACT)   # domain code (stages 3/6)
    report = run_setup()            # `/setup`, `anishift setup`
    report = run_setup(force=True)  # `/setup force` / `anishift setup --force`
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
import zipfile
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import httpx
import py7zr
from py7zr.exceptions import ArchiveError

from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.platform.binaries import (
    Binary,
    external_bin_root,
    is_windows,
    require_binary,
    resolve_binary,
)
from anishift.setup.manifest import Resource, load_manifest
from utils.rich_console import ProgressBarManager

__all__ = [
    "HashMismatchError",
    "InstallCancelledError",
    "InstallerError",
    "ResourceOutcome",
    "ResourceResult",
    "ensure_binary",
    "ensure_resource",
    "extract_members",
    "install_resource",
    "is_installed",
    "run_setup",
    "sha256_file",
]

ResourceOutcome = Literal["installed", "skipped", "failed", "unavailable", "cancelled"]
"""What happened to one resource during a setup run."""

DownloadFn = Callable[[Resource, Path], None]
"""Downloads a resource's archive to the given target path."""

ProgressFn = Callable[[int], None]
"""Advances the shared progress bar by a number of bytes."""

# ── Constants ────────────────────────────────────────────────────────────────

_CHUNK_SIZE: Final[int] = 1 << 20
"""Stream chunk size in bytes (1 MiB)."""

_DOWNLOAD_TIMEOUT: Final[float] = 30.0
"""Per-operation (connect/read/write) HTTP timeout in seconds."""

_MAX_PARALLEL: Final[int] = 2
"""Maximum resources downloaded at the same time."""

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Future-poll interval that keeps Ctrl+C responsive on Windows."""

_BINARY_RESOURCE: Final[dict[Binary, str]] = {
    Binary.MKVEXTRACT: "mkvtoolnix",
    Binary.MKVMERGE: "mkvtoolnix",
    Binary.FFMPEG: "ffmpeg",
    Binary.FFPROBE: "ffmpeg",
}
"""Manifest resource that provides each binary (balcon joins in stage 6)."""


class InstallerError(FatalError):
    """Raised when installing a resource fails."""


class HashMismatchError(InstallerError):
    """Raised when a downloaded archive fails SHA256 verification."""


class InstallCancelledError(InstallerError):
    """Raised inside a download worker when the user cancelled the run."""


@dataclass(frozen=True, slots=True)
class ResourceResult:
    """Outcome of handling one resource during a setup run.

    Attributes:
        name: Resource name from the manifest.
        outcome: What happened.
        detail: Human-readable one-liner for the report.
    """

    name: str
    outcome: ResourceOutcome
    detail: str


# ── Verification ─────────────────────────────────────────────────────────────


def sha256_file(path: Path) -> str:
    """Return the SHA256 hex digest of *path*, streamed in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def is_installed(resource: Resource, dest_root: Path) -> bool:
    """Return ``True`` when every member of *resource* exists and is non-empty."""
    for member in resource.members:
        target = dest_root / member.dest
        if not target.is_file() or target.stat().st_size == 0:
            return False
    return True


# ── Extraction ───────────────────────────────────────────────────────────────


def _fail(message: str) -> InstallerError:
    """Build an :class:`InstallerError` with a consistent context."""
    return InstallerError(
        context=ErrorContext(
            code=ErrorCode.IO_ERROR,
            message=message,
            suggestion="Re-run `anishift setup`",
        ),
    )


def _read_zip_member(archive: Path, archive_path: str) -> bytes:
    """Read one member's bytes from a zip archive."""
    with zipfile.ZipFile(archive) as zf:
        if archive_path not in zf.namelist():
            raise _fail(f"member not found in archive: {archive_path}")
        return zf.read(archive_path)


def _read_7z_member(archive: Path, archive_path: str) -> bytes:
    """Read one member's bytes from a 7z archive."""
    with py7zr.SevenZipFile(archive, "r") as zf:
        extracted = zf.read(targets=[archive_path])
        if not extracted or archive_path not in extracted:
            raise _fail(f"member not found in archive: {archive_path}")
        return extracted[archive_path].read()


def _read_member(archive: Path, resource: Resource, archive_path: str) -> bytes:
    """Read one member's bytes, mapping archive errors to :class:`InstallerError`."""
    try:
        if resource.archive == "zip":
            return _read_zip_member(archive, archive_path)
        return _read_7z_member(archive, archive_path)
    except zipfile.BadZipFile as exc:
        raise _fail(f"{resource.name}: broken zip archive") from exc
    except ArchiveError as exc:
        raise _fail(f"{resource.name}: broken 7z archive") from exc


def extract_members(archive: Path, resource: Resource, dest_root: Path) -> None:
    """Extract *resource*'s named members from *archive* into *dest_root*.

    Destinations were validated against traversal at manifest load; this
    re-checks after resolving, then writes each member.
    """
    root = dest_root.resolve()
    for member in resource.members:
        target = (dest_root / member.dest).resolve()
        if not target.is_relative_to(root):
            raise _fail(f"member dest escapes the install root: {member.dest}")
        data = _read_member(archive, resource, member.archive_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


# ── Download & install ───────────────────────────────────────────────────────


def _download_httpx(
    resource: Resource,
    target: Path,
    *,
    progress: ProgressFn | None = None,
    cancel: threading.Event | None = None,
) -> None:
    """Stream *resource*'s archive to *target* over HTTPS."""
    with httpx.stream("GET", resource.url, follow_redirects=True, timeout=_DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(_CHUNK_SIZE):
                if cancel is not None and cancel.is_set():
                    raise InstallCancelledError(
                        context=ErrorContext(
                            code=ErrorCode.CANCELLED,
                            message=f"{resource.name}: download cancelled",
                        ),
                    )
                handle.write(chunk)
                if progress is not None:
                    progress(len(chunk))


def install_resource(
    resource: Resource,
    *,
    dest_root: Path,
    download: DownloadFn = _download_httpx,
    force: bool = False,
) -> ResourceResult:
    """Install one resource, skipping when already present.

    Args:
        resource: The resource to install.
        dest_root: Root the members are placed under (``external/bin``).
        download: Injectable downloader (real HTTPS by default; fakes in tests).
        force: Reinstall even when the members are present.

    Returns:
        A :class:`ResourceResult` (``installed`` or ``skipped``).

    Raises:
        HashMismatchError: When the downloaded archive fails verification.
        InstallCancelledError: When the user cancelled the download.
        InstallerError: On extraction failure or a broken archive.
        httpx.HTTPError: On network or server failure (callers map it).
        OSError: On disk failure (callers map it).
    """
    if not force and is_installed(resource, dest_root):
        return ResourceResult(resource.name, "skipped", "already present")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / f"{resource.name}.{resource.archive}"
        download(resource, archive)

        actual = sha256_file(archive)
        if actual != resource.sha256:
            raise HashMismatchError(
                context=ErrorContext(
                    code=ErrorCode.BINARY_HASH_MISMATCH,
                    message=f"{resource.name}: sha256 mismatch — corrupt download or stale manifest",
                    suggestion="Re-run `anishift setup`; if it persists, update external/bin_hashes.json",
                    details={"expected": resource.sha256, "actual": actual},
                ),
            )

        staged = tmp_dir / "staged"
        extract_members(archive, resource, staged)
        for member in resource.members:
            final = dest_root / member.dest
            final.parent.mkdir(parents=True, exist_ok=True)
            final.unlink(missing_ok=True)
            shutil.move(staged / member.dest, final)

    return ResourceResult(resource.name, "installed", "downloaded and verified")


# ── Lazy ensure (domain entry point) ─────────────────────────────────────────


def _install_single(resource: Resource, dest_root: Path) -> None:
    """Install one resource synchronously behind its own progress bar."""
    with ProgressBarManager(
        f"Downloading {resource.name}",
        total=resource.size_bytes,
        bar="blocks",
        show_download=True,
        show_speed=True,
        show_percentage=True,
        show_elapsed=True,
        show_eta=False,
        show_spinner=False,
    ) as bar:

        def _download(res: Resource, target: Path) -> None:
            _download_httpx(res, target, progress=bar.advance)

        install_resource(resource, dest_root=dest_root, download=_download)


def ensure_resource(
    name: str,
    *,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
) -> None:
    """Ensure one manifest resource is installed, downloading it on demand.

    The lazy counterpart of :func:`run_setup`, called by domain code right
    before a resource is used (for binaries via :func:`ensure_binary`). An
    installed resource returns immediately; a missing one downloads alone,
    synchronously, behind a single-resource progress bar. Off Windows this is
    a silent no-op for ``binary`` resources — the ``PATH`` fallback in
    ``binaries.py`` applies instead.

    Args:
        name: Resource name from the manifest (e.g. ``"mkvtoolnix"``).
        resources: Manifest override for tests (defaults to :func:`load_manifest`).
        dest_root: Install-root override for tests (defaults to ``external/bin``).

    Raises:
        InstallerError: When *name* is unknown or the install fails — network
            and disk errors are mapped so callers always get a domain error.
        HashMismatchError: When the downloaded archive fails verification.
        ManifestError: When the manifest itself is broken (fail-loud dev error).
    """
    loaded = resources if resources is not None else load_manifest()
    root = dest_root if dest_root is not None else external_bin_root()
    resource = next((entry for entry in loaded if entry.name == name), None)
    if resource is None:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.CONFIG_INVALID,
                message=f"unknown resource: {name}",
                suggestion="Fix the resource name or add it to external/bin_hashes.json",
            ),
        )
    if resource.type == "binary" and not is_windows():
        return
    if is_installed(resource, root):
        return
    try:
        _install_single(resource, root)
    except httpx.HTTPError as exc:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.NETWORK_ERROR,
                message=f"{name}: download failed: {exc}",
                suggestion="Check your internet connection, then retry or run `anishift setup`",
            ),
        ) from exc
    except OSError as exc:
        raise InstallerError(
            context=ErrorContext(
                code=ErrorCode.IO_ERROR,
                message=f"{name}: install failed: {exc}",
                suggestion="Check disk space and permissions, then run `anishift setup`",
            ),
        ) from exc


def ensure_binary(binary: Binary) -> Path:
    """Return *binary*'s path, installing its resource first when missing.

    The single lazy entry point for domain code (stage 3 extraction, stage 6
    audio): an installed binary resolves immediately — no manifest read, no
    network — and a missing one triggers the download of exactly the one
    resource that provides it.

    Args:
        binary: The executable the caller is about to run.

    Returns:
        Absolute path to the executable.

    Raises:
        InstallerError: When the on-demand install fails (network, disk, hash).
        BinaryNotFoundError: When the binary cannot be provided at all (other
            OS without a ``PATH`` fallback, or no manifest resource maps to it).
    """
    path = resolve_binary(binary)
    if path is not None:
        return path
    resource_name = _BINARY_RESOURCE.get(binary)
    if resource_name is not None:
        ensure_resource(resource_name)
    return require_binary(binary)


# ── Setup runner ─────────────────────────────────────────────────────────────


def _result_of(name: str, future: Future[ResourceResult]) -> ResourceResult:
    """Map one worker future to a :class:`ResourceResult`, never raising."""
    try:
        result = future.result()
    except InstallCancelledError:
        return ResourceResult(name, "cancelled", "download interrupted — will retry on next start")
    except InstallerError as exc:
        return ResourceResult(name, "failed", str(exc))
    except httpx.HTTPError as exc:
        return ResourceResult(name, "failed", f"download failed: {exc}")
    except OSError as exc:
        return ResourceResult(name, "failed", f"install failed: {exc}")
    return result


def _collect(futures: dict[str, Future[ResourceResult]]) -> dict[str, ResourceResult]:
    """Turn finished worker futures into a name-keyed result map."""
    return {name: _result_of(name, future) for name, future in futures.items()}


def _install_parallel(to_install: list[Resource], dest_root: Path, *, force: bool) -> dict[str, ResourceResult]:
    """Download and install *to_install* in parallel behind one shared bar."""
    cancel = threading.Event()
    bar_lock = threading.Lock()
    total = sum(resource.size_bytes for resource in to_install)
    futures: dict[str, Future[ResourceResult]] = {}
    try:
        with (
            ProgressBarManager(
                "Downloading tools",
                total=total,
                bar="blocks",
                show_download=True,
                show_speed=True,
                show_percentage=True,
                show_elapsed=True,
                show_eta=False,
                show_spinner=False,
            ) as bar,
            ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool,
        ):

            def _advance(amount: int) -> None:
                with bar_lock:
                    bar.advance(amount)

            def _download(resource: Resource, target: Path) -> None:
                _download_httpx(resource, target, progress=_advance, cancel=cancel)

            futures = {
                resource.name: pool.submit(
                    install_resource,
                    resource,
                    dest_root=dest_root,
                    download=_download,
                    force=force,
                )
                for resource in to_install
            }
            pending = set(futures.values())
            try:
                while pending:
                    _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
            except KeyboardInterrupt:
                cancel.set()
                raise
    except KeyboardInterrupt:
        return _collect(futures)
    return _collect(futures)


def run_setup(
    *,
    force: bool = False,
    resources: tuple[Resource, ...] | None = None,
    dest_root: Path | None = None,
) -> list[ResourceResult]:
    """Install every manifest resource up front; never crash the caller.

    The explicit bulk path behind `/setup` and ``anishift setup``. Per-resource
    failures (network, disk, bad hash, Ctrl+C) become ``failed`` or
    ``cancelled`` entries in the returned report instead of exceptions, so the
    caller can always render a complete report and keep running.

    Args:
        force: Reinstall everything, even resources already present.
        resources: Manifest override for tests (defaults to :func:`load_manifest`).
        dest_root: Install-root override for tests (defaults to ``external/bin``).

    Returns:
        One :class:`ResourceResult` per manifest resource, in manifest order.

    Raises:
        ManifestError: When the manifest itself is broken (fail-loud dev error).
    """
    loaded = resources if resources is not None else load_manifest()
    root = dest_root if dest_root is not None else external_bin_root()

    results: dict[str, ResourceResult] = {}
    to_install: list[Resource] = []
    for resource in loaded:
        if resource.type == "binary" and not is_windows():
            results[resource.name] = ResourceResult(resource.name, "unavailable", "install via your OS package manager")
        elif not force and is_installed(resource, root):
            results[resource.name] = ResourceResult(resource.name, "skipped", "already present")
        else:
            to_install.append(resource)

    if to_install:
        results.update(_install_parallel(to_install, root, force=force))
    return [results[resource.name] for resource in loaded]
```

Uwagi implementacyjne (dlaczego tak):

- **Dwie semantyki błędów, celowo:** `ensure_resource` **rzuca** typowany `InstallerError` (funkcja domenowa nie może działać bez binarki — dostaje błąd z code/message/suggestion, nie surowy traceback), a `run_setup` **raportuje** (user komendy setup ma zobaczyć pełny obraz wszystkich zasobów). Wspólne klocki (`install_resource`, `is_installed`, `_download_httpx`) — zero duplikacji logiki.
- **Ścieżka leniwa bez wątków:** `ensure_resource` pobiera jeden zasób synchronicznie w wątku wołającym — zero `ThreadPoolExecutor`, zero cancel-eventu; Ctrl+C to zwykły `KeyboardInterrupt`, który przerywa `iter_bytes`, temp sprząta context manager, wyjątek idzie do wołającego. Cała maszyneria równoległości żyje tylko w `run_setup`.
- **`ensure_binary` w installerze, nie w `binaries.py`:** installer już importuje `binaries.py` — hook w `require_binary` dałby cykl importów i wciągnął sieć/manifest do warstwy platform (uzasadnienie: 1.6). `binaries.py` zostaje nietknięte.
- **`_BINARY_RESOURCE` obok `_TOOL_DIR`:** mapowanie Binary→zasób mieszka w warstwie setup (ta wie o manifeście); wpis balcon dojdzie w etapie 6 razem z wpisem w manifeście.
- **Jeden pasek, dwa wątki (`run_setup`):** metody rich `Progress` są thread-safe; `bar_lock` dodatkowo serializuje księgowość `ProgressBarManager` (`last_successful_progress`, przejścia kolorów). Flagi paska 1:1 ze wzorca MangaShift; `_install_single` używa tych samych flag dla pojedynczego zasobu.
- **Ctrl+C na Windows:** pętla `wait(pending, timeout=0.2)` zamiast blokującego czekania — blokujące `Event.wait()` bez timeoutu nie reaguje na Ctrl+C na Windows. Po `cancel.set()` re-raise przechodzi przez `pool.__exit__` (workery kończą w <1 s, bo sprawdzają event co chunk) i `bar.__exit__` (ścieżka wyjątku = pasek zamiera na realnym stanie, nie kłamie 100%).
- **Timeout 30 s per operacja** (nie total): duży plik na wolnym łączu może pobierać się dowolnie długo, ale martwe łącze wykrywane jest w ≤30 s — i tyle maksymalnie czeka Ctrl+C na wiszącym readzie.
- **`ignore_cleanup_errors=True`:** windowsowa asekuracja na locki plików przy sprzątaniu tempa.
- **Rozbite `except` (osobne bloki):** obejście buga formatu ruff 0.15.21 (`except (A, B):`).
- **Osobne `_read_zip_member`/`_read_7z_member`:** max 2 poziomy zagnieżdżeń, guard clauses.

**Krok 3 — bramki + testy zielone, commit.** Gdyby mypy nie widział typów `py7zr` (`import-untyped`), dopisz w `pyproject.toml` (sekcja tool — to konfiguracja, nie zależność, wolno ręcznie):

```toml
[[tool.mypy.overrides]]
module = "py7zr.*"
ignore_missing_imports = true
```

```bash
git add anishift/setup/installer.py tests/test_installer.py
git commit -m "feat(setup): resource installer with lazy ensure, hash verify and traversal guard"
```

---

### Zadanie 4 — `/setup` w shellu (completer opcji) + komenda Typer `anishift setup` (TDD dla CLI)

Zasada UX (jak w Claude Code): **w shellu nie ma flag uniksowych.** Opcje komend to gołe tokeny — `/setup force`, nie `/setup --force`. Deklaruje je pole `Command.options` (opcja → opis) — SSOT, z którego completer bierze inline podpowiedzi (po `/<komenda>` + spacja, dokładnie tak jak podpowiada komendy po `/`), a `dispatch` walidację. `run_setup(force=...)` i cały installer **bez zmian** — zmienia się tylko warstwa CLI/shell. Poza shellem zostaje komenda Typer `anishift setup [--force]` (tam flaga uniksowa jest idiomatyczna; priorytet ma shell, CLI jest drugorzędne).

**`shell.py` w tym zadaniu NIE jest dotykany (v2.1):** start shella nic nie pobiera — żadnego `_ensure_resources_at_start()`/`run_setup()` po bannerze. Prompt pojawia się natychmiast, niezależnie od stanu `external/bin/`. Jedyna droga do pobierania z shella to jawne `/setup`; leniwe pobieranie dojdzie w etapach 3/6 przez `ensure_binary` w funkcjach domenowych.

**Krok 1 — testy (najpierw, mają się wywalić).**

Do `tests/test_completer.py` dopisz import (do istniejących) i testy; zaktualizuj też `test_prefix_filters_commands` — po dojściu `/setup` prefiks `/se` ma dwa trafienia:

```python
from prompt_toolkit.formatted_text import to_plain_text
```

```python
def test_prefix_filters_commands() -> None:
    assert _complete("/se") == ["/settings", "/setup"]


def test_space_after_setup_suggests_its_options() -> None:
    assert _complete("/setup ") == ["force"]


def test_option_prefix_filters_options() -> None:
    assert _complete("/setup f") == ["force"]
    assert _complete("/setup x") == []


def test_option_meta_is_the_option_description() -> None:
    completer = SlashCompleter()
    doc = Document("/setup ", cursor_position=len("/setup "))
    completion = next(iter(completer.get_completions(doc, CompleteEvent())))
    assert "re-download" in to_plain_text(completion.display_meta)


def test_space_after_optionless_command_suggests_nothing() -> None:
    assert _complete("/help ") == []


def test_space_after_unknown_command_suggests_nothing() -> None:
    assert _complete("/zzz ") == []
```

W `tests/test_commands.py` zaktualizuj test rejestru (komend jest teraz 7) i dopisz testy `/setup` (import `ResourceResult` dołóż na górze):

```python
from anishift.setup.installer import ResourceResult
```

```python
def test_registry_has_the_seven_commands() -> None:
    assert set(COMMANDS) == {"/help", "/settings", "/auto", "/manual", "/doctor", "/exit", "/setup"}


def test_setup_defaults_to_no_force(context: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return [ResourceResult("ffmpeg", "installed", "downloaded and verified")]

    monkeypatch.setattr("anishift.setup.installer.run_setup", _fake_run_setup)
    assert dispatch("/setup", context) is True
    assert seen["force"] is False


def test_setup_force_token_forces_reinstall(context: AppContext, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return []

    monkeypatch.setattr("anishift.setup.installer.run_setup", _fake_run_setup)
    assert dispatch("/setup force", context) is True
    assert seen["force"] is True


def test_setup_unknown_option_reports_without_running(
    context: AppContext, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _never(**_kwargs: object) -> list[ResourceResult]:
        raise AssertionError("run_setup must not run for an unknown option")

    monkeypatch.setattr("anishift.setup.installer.run_setup", _never)
    assert dispatch("/setup blah", context) is True
    assert "Unknown option" in capsys.readouterr().out


def test_option_on_optionless_command_reports(
    context: AppContext, capsys: pytest.CaptureFixture[str]
) -> None:
    assert dispatch("/help force", context) is True
    assert "Unknown option" in capsys.readouterr().out
```

Utwórz `tests/test_setup_cli.py` (komenda Typer — spoza shella):

```python
"""Tests for the `anishift setup` CLI command."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from anishift.cli import main as cli_main
from anishift.setup.installer import ResourceResult


def test_setup_command_prints_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        return [ResourceResult("ffmpeg", "installed", "downloaded and verified")]

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup"])
    assert result.exit_code == 0
    assert "ffmpeg" in result.output


def test_setup_command_exits_1_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        return [ResourceResult("ffmpeg", "failed", "download failed")]

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup"])
    assert result.exit_code == 1


def test_setup_command_passes_force(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}

    def _fake_run_setup(*, force: bool = False) -> list[ResourceResult]:
        seen["force"] = force
        return []

    monkeypatch.setattr(cli_main, "run_setup", _fake_run_setup)
    result = CliRunner().invoke(cli_main.app, ["setup", "--force"])
    assert result.exit_code == 0
    assert seen["force"] is True
```

`uv run pytest tests/test_completer.py tests/test_commands.py tests/test_setup_cli.py -q` → **FAIL** — dobrze.

**Krok 2 — `anishift/cli/commands.py`** (Command z `options`, komenda `/setup`, dispatch walidujący tokeny; handlery dostają jednolicie zbiór włączonych opcji). Nowa pełna treść pliku:

```python
"""Shell command registry — single source of truth for ``/commands``.

The completer, ``/help``, option suggestions and option validation all derive
from :data:`COMMANDS`; nothing lists the commands or their options twice.
Handlers take the :class:`AppContext` plus the set of enabled option tokens
and return ``True`` to keep the REPL running or ``False`` to exit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from anishift.bootstrap import AppContext
from anishift.config.user_settings import Mode, save_user_settings
from anishift.setup.doctor import CheckStatus, run_doctor
from utils.rich_console import StatusType, console, get_status_icon

if TYPE_CHECKING:
    from anishift.setup.installer import ResourceResult

__all__ = ["COMMANDS", "Command", "dispatch", "print_setup_report"]

# ── Constants ──────────────────────────────────────────────────────────────

_STATUS_ICON: dict[CheckStatus, StatusType] = {
    CheckStatus.OK: "success",
    CheckStatus.WARN: "warning",
    CheckStatus.FAIL: "error",
    CheckStatus.SKIP: "stopped",
}
"""Maps a doctor check outcome to a ``rich_console`` status-icon name."""

_OUTCOME_ICON: dict[str, StatusType] = {
    "installed": "success",
    "skipped": "info",
    "unavailable": "warning",
    "cancelled": "warning",
    "failed": "error",
}
"""Maps a setup outcome to a ``rich_console`` status-icon name."""

_FORCE: Final[str] = "force"
"""Option token of ``/setup`` that re-downloads everything."""


@dataclass(frozen=True, slots=True)
class Command:
    """A shell command.

    Attributes:
        name: The slash-prefixed command token (``"/help"``).
        summary: One-line description shown in completion and ``/help``.
        handler: Runs the command with the enabled option tokens; returns
            ``False`` to exit the REPL.
        options: Option token to description — the single source of truth
            both the completer (suggestions after the command name) and
            :func:`dispatch` (validation) derive from. Empty for commands
            without options.
    """

    name: str
    summary: str
    handler: Callable[[AppContext, frozenset[str]], bool]
    options: dict[str, str] = field(default_factory=dict)


def print_setup_report(results: list[ResourceResult]) -> None:
    """Render setup results as an icon + message list."""
    for result in results:
        icon = get_status_icon(_OUTCOME_ICON.get(result.outcome, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.detail}")


def _set_mode(context: AppContext, mode: Mode) -> bool:
    """Switch the processing mode and persist it."""
    context.user_settings.mode = mode
    save_user_settings(context.user_settings)
    console.print(f"[success]Mode set to[/success] [info]{mode}[/info].")
    return True


def _handle_help(context: AppContext, options: frozenset[str]) -> bool:
    """Print the command table."""
    for command in COMMANDS.values():
        console.print(f"  [info]{command.name}[/info]  [gray]{command.summary}[/gray]")
    return True


def _handle_settings(context: AppContext, options: frozenset[str]) -> bool:
    """Open the settings panel (imported lazily to defer prompt_toolkit)."""
    from anishift.cli.settings_panel import open_settings_panel  # noqa: PLC0415

    context.user_settings = open_settings_panel(context)
    return True


def _handle_auto(context: AppContext, options: frozenset[str]) -> bool:
    """Switch to auto mode."""
    return _set_mode(context, "auto")


def _handle_manual(context: AppContext, options: frozenset[str]) -> bool:
    """Switch to manual mode."""
    return _set_mode(context, "manual")


def _handle_doctor(context: AppContext, options: frozenset[str]) -> bool:
    """Run diagnostics and render the report."""
    for result in run_doctor(context.settings):
        icon = get_status_icon(_STATUS_ICON.get(result.status, "info"))
        console.print(f"{icon} [bold]{result.name}[/bold]: {result.message}")
        if result.suggestion and result.status in (CheckStatus.FAIL, CheckStatus.WARN):
            console.print(f"   [gray]-> {result.suggestion}[/gray]")
    return True


def _handle_setup(context: AppContext, options: frozenset[str]) -> bool:
    """Install missing external tools (``force`` re-downloads everything)."""
    from anishift.errors import AniShiftError  # noqa: PLC0415
    from anishift.setup.installer import run_setup  # noqa: PLC0415

    try:
        results = run_setup(force=_FORCE in options)
    except AniShiftError as exc:
        console.print(f"[error]{exc}[/error]")
        return True
    print_setup_report(results)
    return True


def _handle_exit(context: AppContext, options: frozenset[str]) -> bool:
    """Leave the REPL."""
    return False


COMMANDS: dict[str, Command] = {
    "/auto": Command("/auto", "Switch to auto mode (Enter processes everything)", _handle_auto),
    "/doctor": Command("/doctor", "Run diagnostics and report your setup", _handle_doctor),
    "/exit": Command("/exit", "Leave AniShift", _handle_exit),
    "/help": Command("/help", "Show available commands", _handle_help),
    "/manual": Command("/manual", "Switch to manual mode (prompt per track)", _handle_manual),
    "/settings": Command("/settings", "Open the settings panel", _handle_settings),
    "/setup": Command(
        "/setup",
        "Download missing external tools",
        _handle_setup,
        options={_FORCE: "re-download everything, even if already present"},
    ),
}
"""Single source of truth for every shell command, keyed by name."""


def dispatch(text: str, context: AppContext) -> bool:
    """Route a ``/``-prefixed line to its handler.

    The first token selects the command; every following token must be an
    option declared in that command's :attr:`Command.options` (Claude-Code
    style: ``/setup force``, never unix flags).

    Args:
        text: The raw command line (leading/trailing spaces tolerated).
        context: The wired application context passed to the handler.

    Returns:
        ``True`` to keep the REPL running, ``False`` to exit. A blank line,
        an unknown command or an unknown option keeps the loop running.
    """
    parts = text.strip().split()
    if not parts:
        return True
    name = parts[0]
    command = COMMANDS.get(name)
    if command is None:
        console.print(f"[warning]Unknown command[/warning] [info]{name}[/info]. Type [info]/help[/info].")
        return True
    options = frozenset(parts[1:])
    unknown = options - command.options.keys()
    if unknown:
        known = ", ".join(sorted(command.options)) if command.options else "none"
        console.print(
            f"[warning]Unknown option[/warning] [info]{', '.join(sorted(unknown))}[/info]"
            f" for [info]{name}[/info]. Available: [info]{known}[/info]."
        )
        return True
    return command.handler(context, options)
```

**Krok 3 — `anishift/cli/completer.py`** (dwupoziomowy: komendy po `/`, opcje po `/<komenda> `). Nowa pełna treść pliku:

```python
"""Inline autocomplete for ``/commands`` — active only after a leading ``/``."""

from __future__ import annotations

from collections.abc import Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from anishift.cli.commands import COMMANDS, Command

__all__ = ["SlashCompleter"]


class SlashCompleter(Completer):
    """Complete ``/commands`` and their options, Claude-Code style.

    Two levels, both derived from :data:`anishift.cli.commands.COMMANDS`:
    a leading ``/`` completes command names (summary as meta), and a known
    command followed by a space completes that command's option tokens
    (option description as meta). Outside a leading ``/`` nothing is
    suggested.
    """

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        """Yield command or option completions for the text before the cursor."""
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return
        name, separator, option_prefix = text.partition(" ")
        if not separator:
            yield from _complete_commands(name)
            return
        command = COMMANDS.get(name)
        if command is not None:
            yield from _complete_options(command, option_prefix)


def _complete_commands(prefix: str) -> Iterable[Completion]:
    """Yield alphabetical ``/command`` completions matching *prefix*."""
    for name in sorted(COMMANDS):
        if name.startswith(prefix):
            yield Completion(
                name,
                start_position=-len(prefix),
                display_meta=COMMANDS[name].summary,
            )


def _complete_options(command: Command, prefix: str) -> Iterable[Completion]:
    """Yield alphabetical option completions of *command* matching *prefix*."""
    for option in sorted(command.options):
        if option.startswith(prefix):
            yield Completion(
                option,
                start_position=-len(prefix),
                display_meta=command.options[option],
            )
```

**Krok 4 — `anishift/cli/main.py`.** Subkomenda Typer (spoza shella; raport renderuje `print_setup_report` z `commands.py` — jedno miejsce dla shella i CLI). Dodaj importy (do istniejących bloków):

```python
from typing import Annotated

from anishift.cli.commands import print_setup_report
from anishift.errors import AniShiftError
from anishift.setup.installer import run_setup
```

Dodaj po komendzie `doctor`:

```python
@app.command()
def setup(
    force: Annotated[
        bool,
        typer.Option("--force", help="Re-download everything, even resources already present."),
    ] = False,
) -> None:
    """Download and verify missing external tools into external/bin/."""
    try:
        results = run_setup(force=force)
    except AniShiftError as exc:
        console.print(f"[error]{exc}[/error]")
        raise typer.Exit(code=1) from exc
    print_setup_report(results)
    if any(result.outcome == "failed" for result in results):
        raise typer.Exit(code=1)
```

**Krok 5 — `anishift/setup/__init__.py`:** zaktualizuj tylko docstring (installer już nie jest „later"):

```python
"""Setup layer — diagnostics (doctor) and resource installation (installer)."""
```

Uwagi implementacyjne (dlaczego tak):

- **Jednolita sygnatura handlerów** (`Callable[[AppContext, frozenset[str]], bool]`): jeden typ zamiast rozgałęziania w `dispatch` na „handler z opcjami / bez"; handlery bez opcji ignorują argument, a `dispatch` gwarantuje, że dostaną pusty zbiór (nieznane tokeny odcina wcześniej).
- **`print_setup_report` w `commands.py`, nie w `main.py`:** `main.py` może importować z `commands.py`, ale nie odwrotnie (cykl przez `shell.py`); jeden rendering dla `/setup` i `anishift setup` (DRY).
- **Lazy import `run_setup` w `_handle_setup`** (wzór `_handle_settings`): rejestr komend nie płaci za import httpx/py7zr przy starcie shella.
- **`frozenset` opcji:** kolejność tokenów bez znaczenia, duplikaty nieszkodliwe (`/setup force force` = `force`).
- **Completer poza znanym kontekstem milczy:** spacja po nieznanej komendzie lub po komendzie bez opcji = zero podpowiedzi; poza wiodącym `/` bez zmian — nic.

**Krok 6 — bramki + pełne testy, commit** (`shell.py` celowo poza commitem — nie zmienia się):

```bash
git add anishift/cli/commands.py anishift/cli/completer.py anishift/cli/main.py anishift/setup/__init__.py tests/test_commands.py tests/test_completer.py tests/test_setup_cli.py
git commit -m "feat(cli): /setup with option completer and Typer setup command"
```

---

### Zadanie 5 — aktualizacja planów etapów (R11)

**Krok 1 — `docs/plans/etap-8-dystrybucja-binarek.md`:** usuń z etapu 8 wszystko o binarkach (sekcje `bin_hashes.json`, `installer.py`, `doctor.py`, `main.py` + punkty 1-3 kolejności implementacji). Nowa treść pliku:

```markdown
# etap 8 — migracja danych + wyburzenie starego

> cel: repo po przeprowadzce — dane usera zmigrowane, stary kod i bałagan usunięte.
> **binarki wyprowadzone z tego etapu:** manifest, `anishift setup` i leniwe pobieranie mkvtoolnix/ffmpeg (`ensure_binary` przy pierwszym użyciu) zrealizowane w [etap-2.5-pobieracz-binarek-v2.md](etap-2.5-pobieracz-binarek-v2.md); wpis balcon w manifeście dochodzi w etapie 6 razem z silnikiem.
> zależności: etap 7 (nic starego nie kasujemy, dopóki nowe nie ma parytetu).
> DoD: w repo nie ma śladu nazw `mm_avh` / `working_space` w nowym kodzie; README opisuje AniShift; świeży klon + `uv sync` + `anishift setup` + `anishift doctor` = zielono (albo bez `setup` — binarki dociągają się same przy pierwszym użyciu w pipeline).

## pliki do stworzenia/zmiany

### `scripts/maintenance/migrate_workspace.py` (NOWY)
- **odpowiedzialność:** jednorazowe przeniesienie danych usera ze starego `working_space/` do `workspace/`.
- **zawartość:** skrypt: PRZENOSI (nigdy nie kasuje) pliki usera płasko do `workspace/` (żadnych podfolderów poza tmp/output — struktura docelowa jest płaska); kolizje nazw = pomiń + raport; dry-run domyślnie (`--apply` wykonuje); na końcu raport co przeniesiono/pominięto. kasacja starego `working_space/` NIE jest częścią skryptu — dopiero ręczne potwierdzenie usera (704 pliki danych, w tym luźne MKV i audiobooki).

### kasacje starego kodu (ZMIANA — commit(y) porządkowe, osobno od zmian architektury)
- **odpowiedzialność:** wyburzenie mm_avh po potwierdzonym parytecie.
- **zawartość (kolejność bezpieczeństwa):**
  1. zrzut `git ls-files bin/` do notatki (dowód co było trackowane).
  2. kasacje kodu: `modules/`, `start.py`, `constants.py`, `run_mm_avh.bat`, `data/`.
  3. kasacje binarek: `bin/` (w tym stylish_tts ~567MB — zweryfikować absolutną ścieżkę przed `rm`, oraz espeak-ng); untrack z gita.
  4. `working_space/` — dopiero PO migracji skryptem i ręcznym potwierdzeniu usera.
  5. porządek w `temp/` i starych `tests/`: przejrzeć każdy skrypt, realnie używane → `scripts/maintenance/`, reszta out.
  6. `.gitignore` — finalna wersja (external/bin, workspace, config/settings.json, .env); `pyproject.toml` — usunięcie martwych zależności po `rg` importów.
  7. `README.md` — opisuje AniShift (instalacja: uv sync; binarki dociągają się same przy pierwszym użyciu, `anishift setup` pobiera je z góry; użycie: anishift → Enter).

## kolejność implementacji

1. `migrate_workspace.py` → weryfikacja: dry-run na kopii `working_space/` raportuje komplet; `--apply` przenosi płasko, nic nie kasuje.
2. smoke czystego klonu: świeży klon → `uv sync` → `anishift` (shell startuje natychmiast, zero pobierania) → smoke e2e (binarki dociągają się same przy pierwszym użyciu przez `ensure_binary`) → `anishift doctor` → weryfikacja: wszystko zielono bez ręcznych kroków.
3. kasacje (osobne commity, w kolejności wyżej) → weryfikacja: `git status` czysty, `git ls-files` bez binarek, `rg "mm_avh|working_space"` w nowym kodzie = 0 trafień, smoke e2e nadal przechodzi.

## jak testować

świeży klon repo + `uv sync` + smoke e2e = zielono (osobny `anishift setup` niepotrzebny — brakującą binarkę pobiera pierwsze użycie w pipeline; `setup` zostaje jako jawne „pobierz wszystko z góry"); `anishift doctor` zielony po pobraniu; `git status` czysty, żadnych binarek w gicie. dodatkowo: `rg` po nazwach `mm_avh`/`working_space` w nowym kodzie pusty; migracja danych potwierdzona przez usera przed kasacją starego folderu.
```

**Krok 2 — `docs/plans/_index.md`:**

- w tabeli po wierszu etapu 2 dodaj:

```markdown
| 2.5 | [etap-2.5-pobieracz-binarek-v2.md](etap-2.5-pobieracz-binarek-v2.md) | pobieracz zasobów zewnętrznych: manifest + leniwe pobieranie mkvtoolnix/ffmpeg na żądanie (`ensure_binary`) + `anishift setup`/`/setup` do pobrania z góry. | 2 |
```

- wiersz etapu 3: kolumna „zależy od" `1, 2` → `1, 2, 2.5` (ekstrakcja potrzebuje mkvtoolnix);
- wiersz etapu 8: cel na `migracja danych usera i wyburzenie starego kodu (dystrybucja binarek przeniesiona do etapu 2.5).`;
- graf zależności na:

```text
1 → 2 → 2.5 → 3 → 4 → 5 (llm)
                      └→ 6 (tts+audio) → 7 (e2e) → 8 (migracja+kasacje)
```

**Commit:**

```bash
git add docs/plans/etap-8-dystrybucja-binarek.md docs/plans/_index.md
git commit -m "docs: move binary distribution from stage 8 to stage 2.5"
```

---

### Zadanie 6 — smoke na żywo (Windows) + finalne bramki + PR

1. **Pierwsza instalacja przez komendę:** `uv run anishift setup` → jeden zbiorczy pasek (blocks, MB, prędkość), na końcu `installed` × 2; istnieją: `external/bin/mkvtoolnix/mkvextract.exe`, `mkvmerge.exe`, `external/bin/ffmpeg/ffmpeg.exe`, `ffprobe.exe`. ⚠️ Jeśli ffmpeg zgłosi `sha256 mismatch` — URL jest datowany i niezmienny, więc to uszkodzone pobranie (ponów) albo błąd w wartościach z re-pinu; zweryfikuj hash/size z zadania 1 jeszcze raz.
2. **Idempotencja:** drugi `uv run anishift setup` → `skipped` × 2, zero sieci, natychmiast.
3. **Start natychmiastowy (v2.1):** skasuj CAŁE `external/bin/` → `uv run anishift` (goły start) → prompt pojawia się natychmiast, ZERO pobierania, zero sieci, żadnych warningów o binarkach. To jest sedno zmiany architektury.
4. **Ścieżka leniwa (smoke mechanizmu — funkcja domenowa dojdzie dopiero w etapie 3):** skasuj `external/bin/ffmpeg/` → `uv run python -c "from anishift.platform.binaries import Binary; from anishift.setup.installer import ensure_binary; print(ensure_binary(Binary.FFMPEG))"` → pojedynczy pasek `Downloading ffmpeg` (tylko ten jeden zasób; mkvtoolnix nietknięty), na końcu wypisana ścieżka do `ffmpeg.exe`. Drugi run tej samej komendy → ścieżka od razu, zero sieci. Dodatkowo offline-check: wyłącz sieć, skasuj `external/bin/ffmpeg/`, ten sam one-liner → czytelny `InstallerError` (`download failed` + sugestia), nie surowy traceback httpx.
5. **Ctrl+C w `/setup`:** skasuj `external/bin/` → `uv run anishift` → `/setup` → Ctrl+C w połowie pobierania → raport `cancelled`, shell działa (prompt), `external/bin/` bez śmieci, brak plików częściowych. Kolejny `/setup` ponawia pobieranie.
6. **Completer opcji:** w shellu wpisz `/setup` i naciśnij spację → inline podpowiedź `force` z opisem (dokładnie jak podpowiedzi komend po `/`); `/setup f` zawęża do `force`.
7. **`/setup force`:** w shellu → ponowne pobranie obu zasobów mimo obecności (pasek jak przy pierwszej instalacji), raport `installed` × 2.
8. **Nieznana opcja:** `/setup blah` → komunikat `Unknown option ... Available: force`, prompt działa dalej, zero sieci.
9. **`--force` (terminal):** `uv run anishift setup --force` → ponowne pobranie obu mimo obecności.
10. **Doctor:** `uv run anishift doctor` → check `binaries` OK (zielony).
11. **Git czysty:** `git status --porcelain external/` → pusto (gitignore działa).
12. **Finalne bramki:** wszystkie 4 komendy z nagłówka 3.4 zielone.
13. **PR:**

```bash
git push -u origin feat/etap-2.5-pobieracz-binarek
gh pr create --base main --title "feat: etap 2.5 — external resource downloader (lazy install of mkvtoolnix + ffmpeg)" --body "Stage 2.5: generic resource downloader with lazy, on-demand installs. Manifest (external/bin_hashes.json, resources with a type field) pins URL + SHA256 + size + members per resource. The shell starts instantly with zero downloads; a missing tool is installed on first use via ensure_binary/ensure_resource (single resource, own progress bar, typed domain errors — stages 3/6 add the real call sites, this stage ships the mechanism plus tests). Explicit bulk path: /setup [force] in the shell (Claude-Code-style option completer — options are bare tokens suggested after a space, no unix flags inside the shell) and anishift setup [--force] from the terminal — two parallel downloads behind one shared progress bar, Ctrl+C-safe cancel. Atomic temp->verify->extract->move with a path-traversal guard everywhere. ffmpeg pinned to a dated immutable BtbN release (not the moving latest tag). binaries.py, doctor.py and shell.py untouched; non-Windows keeps the PATH fallback. Tests run without network. Binary distribution scope moved out of stage 8 (docs updated)."
```

Po review CodeRabbita (skill `/coderabbit`) → merge.

## 3.5 Checklist zgodności ze standardami (do odhaczenia przy review własnym)

- [ ] `from __future__ import annotations` linia 1 w każdym nowym module
- [ ] Docstringi Google-style: moduły, klasy publiczne, funkcje publiczne, każda stała `Final` i każdy alias typu
- [ ] Stałe `Final` w sekcji `# ── Constants ──…` (separator do 80 znaków)
- [ ] `dataclass(frozen=True, slots=True)` dla `Member`, `Resource`, `ResourceResult`; `Literal` dla zbiorów zamkniętych
- [ ] Guard clauses, early return, max 2 poziomy zagnieżdżeń; max 5 parametrów
- [ ] Zero `except Exception` / gołych `except`; każdy `raise ... from exc`; osobne bloki `except` (bug ruff 0.15.21)
- [ ] Błędy przez `ErrorContext` (code + message + suggestion); żadnego `sys.exit()` w logice domenowej
- [ ] `pathlib` wszędzie; `httpx.stream` + `raise_for_status`
- [ ] Testy bez docstringów (nazwa = opis), AAA, `pytest.raises(SpecificError, match=...)`, zero sieci
- [ ] Zależność tylko przez `uv add py7zr`; `utils/`, `binaries.py`, `doctor.py` i `shell.py` nietknięte
- [ ] Start shella bez żadnego pobierania (v2.1); ścieżka leniwa (`ensure_*`) rzuca typowane błędy domenowe, ścieżka zbiorcza (`run_setup`) raportuje — obie na wspólnych klockach
- [ ] W shellu zero flag uniksowych: opcje komend to tokeny z `Command.options` (SSOT — completer i `dispatch` derywują z jednego miejsca)
- [ ] ffmpeg w manifeście = datowany, niezmienny URL BtbN (weryfikacja z zadania 1 pilnuje braku `/download/latest/`)
- [ ] Commity Conventional Commits, zero śladów AI (dotyczy też PR body)
