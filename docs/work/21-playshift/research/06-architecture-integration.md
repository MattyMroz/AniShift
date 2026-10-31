---
kind: research
status: proposed
date: 2026-10-31
baseline: AniShift f3e6980 (work/application/04-retry-progress-qbt)
---

# R6: architektura PlayShift — repo, struktura, aktualizacje, integracja z AniShift

Oznaczenia: **[F]** fakt sprawdzony (źródło lub uruchomienie), **[W]** wniosek z kilku faktów, **[R]** rekomendacja, **[?]** niewiadoma do sprawdzenia.

## Rekomendacja

1. **[R] Osobne repo `MattyMroz/PlayShift`, na start prywatne.** Nie część AniShift, nie monorepo i nie instalacja przez `anishift setup` do `external/mpv/`. Odtwarzacz działa sam (YouTube, muzyka, pliki), a AniShift korzysta z niego tylko przez wąski kontrakt.
2. **[R] Repo jest instalacją.** Klon repo to gotowy, przenośny odtwarzacz (jak dziś `Videos\mpv`): w gicie konfiguracja, własne skrypty i manifest wersji, a binarki, Python, VapourSynth i modele pobiera `playshift setup` według locka z SHA256. Tak samo zbudowane jest repo mpv_PlayKit: w gicie tylko `portable_config/` i `installer/` [F].
3. **[R] Dwa klony:** roboczy `PROJECTS\PlayShift`, na którym pracują agenci, i używany `Videos\mpv`, aktualizowany przez `git pull` i `playshift setup`. Praca agentów nie psuje odtwarzacza, którego właściciel właśnie używa.
4. **[R] Zależności: `deps.toml` (ręcznie: co i skąd) + `deps.lock.json` (generowany: dokładny URL, SHA256, rozmiar).** Narzędzie w Pythonie przez `uv` (stdlib, bez zależności runtime), uruchamiane dwuklikiem `setup.cmd`. Pola locka nazywamy jak w AniShift `external/bin_hashes.json` (`sha256`, `size_bytes`, `archive`, `members[].archive_path/dest`), ale kod jest osobny.
5. **[R] Kontrakt z AniShift na start to dziennik postępu, nie JSON IPC.** Skrypt Lua w odtwarzaczu dopisuje fakty (plik, rozmiar, najwyższy procent, powód) do `portable_config/state/progress.jsonl`. AniShift czyta go, dopasowuje plik do odcinka, sam decyduje, czy odcinek jest obejrzany, i synchronizuje MAL/AniList. Otwieranie odcinka zostaje bez zmian (`os.startfile` i skojarzenie plików). JSON IPC odkładamy do etapu, który naprawdę wymaga sterowania na żywo.
6. **[R] Nazwa PlayShift zostaje.** Nie ma istotnej kolizji, a nazwa pasuje do rodziny AniShift/MangaShift.

Rekomendacja orkiestratora z briefu (osobne repo, `anishift setup` do `external/mpv/`, JSON IPC) jest trafna w pierwszym punkcie, a w dwóch pozostałych nie — uzasadnienie w §1.3 i §4.4.

## Zakres i stan na dzień

- Stan sprawdzony 2026-10-31. Kod AniShift na `f3e6980`. Odtwarzacz `C:\Users\MattyMroz\Videos\mpv` czytany tylko do odczytu; jedyne uruchomienia to `mpv.com --no-config` bez okna (`--vo=null --ao=null`), z plikami testowymi w scratchpadzie, nie w `Videos\mpv`.
- Poza zakresem (R1–R5): wybór buildu mpv, upscaling, interpolacja, UI, skróty. Tu tylko to, jak te wybory wpływają na strukturę.

## 1. Repo i granice

### 1.1 Fakty, od których zależy decyzja

| Fakt | Dowód |
| --- | --- |
| [F] Obecny odtwarzacz to płaski katalog 251 MB bez gita: `mpv.exe` (v0.36.0-711, build 2023-11-02), Python 3.11 embed, VapourSynth (R65), `yt-dlp.exe`, `portable_config/` (65 MB, w tym 45 MB `_cache/`), `vapoursynth64/` (73 MB, w tym 51 MB modeli RIFE). | `ls`, `du -sh`, `mpv.com --no-config --version` |
| [F] W `portable_config/fonts/` leżą prywatne fonty ITC Officina, a `mpv.conf` ma `sub-font = "ITC Officina Sans Std PL Book"`. Fonty pochodzą z prywatnego repo `MattyMroz/fonts`, a `AGENTS.md` AniShift zabrania wkładania ich do publicznego repo. | `ls portable_config/fonts`, `mpv.conf:144`, pamięć właściciela |
| [F] AniShift jest publiczne i nie ma pliku `LICENSE`. | `gh repo view`: `PUBLIC`, `licenseInfo: null`; brak `LICENSE*` |
| [F] mpv jest na GPLv2+ (LGPLv2.1+ tylko przy buildzie `-Dgpl=false`). uosc: LGPL-2.1. thumbfast: MPL-2.0. VapourSynth: LGPL-2.1. yt-dlp: Unlicense. vs-mlrt: GPL-3.0. AnimeJaNai: CC BY-NC-SA 4.0. SmartCopyPaste: BSD-2 (nagłówek pliku). | `mpv/Copyright`, `gh api repos/*` (`license.spdx_id`), `LICENSE` AnimeJaNai |
| [F] Pliki konfiguracji mpv-lazy/PlayKit bez osobnej licencji są „domyślnie UNLICENSED” (`LICENSE.MD`, po chińsku). Wiele linii `mpv.conf` właściciela pochodzi z tego szablonu (komentarz w nagłówku linkuje do mpv_PlayKit). | `Videos\mpv\LICENSE.MD`, `mpv.conf:1-3` |
| [F] Wydania GitHub: każdy plik poniżej 2 GiB, bez limitu sumy. PlayKit dzieli paczkę z TensorRT na wolumeny `.7z.001/.002` (1,6 GB + 1,3 GB). Pakiety AnimeJaNai 3.9.0 mają do 0,5 GB na komponent. | docs.github.com; `gh api .../releases` |
| [F] AniShift już otwiera gotowy odcinek przez `os.startfile` (Biblioteka, akcja „obejrzyj”). | `anishift/platform/tray.py::open_path`, `cli/interactive/actions.py:44` |
| [F] `restyle.py` w AniShift ma na sztywno „wygląd napisów z mpv właściciela” (rozmiar 51, obwódka 2, cień 1,25 przy 50% czerni, margines 44 przy 720). To te same wartości co `sub-*` w `mpv.conf`. | `anishift/services/subtitles/restyle.py:44-66`, `mpv.conf:145-166` |

### 1.2 Porównanie opcji

| Kryterium | Osobne repo | Katalog `player/` w AniShift | Instalacja przez `anishift setup` do `external/mpv/` |
| --- | --- | --- | --- |
| Kto od kogo zależy | Odtwarzacz od nikogo; AniShift opcjonalnie od kontraktu | Odtwarzacz w repo aplikacji, która go nie potrzebuje do działania | Odtwarzacz zależy od działającego AniShift (venv 3.14, manifest) |
| Cykl zmian | Konfiguracja zmienia się przy oglądaniu, niezależnie od AniShift | Zmiany konfiguracji przechodzą przez bramki Pythona, listę scope i PR AniShift | Jak obok, plus aktualizacja odtwarzacza = aktualizacja AniShift |
| Licencje i prywatność | Repo można zacząć jako prywatne; publikacja po audycie | Konfiguracja i skrypty od razu publiczne; ryzyko z „UNLICENSED” i fontami | Jak obok |
| Binarki | Pobierane z locka, nigdy w gicie | Jak obok | Instalator AniShift obsługuje tylko `kind="binary"` w `external/bin`; Python embed z wheelem VS wymaga nowej logiki w AniShift |
| Miejsce instalacji | Dowolne (`Videos\mpv`), przenośne | W checkoucie AniShift | W checkoucie AniShift, który agenci zmieniają na branchach |
| Koszt | Drugi zestaw: `AGENTS.md`, hooki, CI, README | Najmniej repo | Najmniej repo |
| Atomowa zmiana kontraktu | Dwa PR (rzadko: kontrakt to jeden format linii) | Jeden PR | Jeden PR |

**[W]** Monorepo wygrywa tylko atomowością zmian kontraktu, a kontrakt jest mały i rzadko się zmienia (§4.2). Przegrywa tam, gdzie koszt jest stały: odtwarzacz służy do wszystkiego, nie tylko do anime; jego dane (pozycje wznowienia, `saved-props.json`) mają przetrwać każdy branch i `git clean` w AniShift; publiczne repo AniShift wymusiłoby wcześniejszy audyt licencji konfiguracji.

### 1.3 Dlaczego nie `anishift setup` → `external/mpv/`

- **[F]** AniShift `external/` to narzędzia samego AniShift (`mkvtoolnix`, `ffmpeg`, `7zip`, `qbittorrent`). Instalator nie obsługuje instalacji wheela do embedded Pythona ani zapisu `._pth` (`anishift/setup/AGENTS.md`, `manifest.py`: `ResourceKind = Literal["binary"]`).
- **[F]** Pamięć projektu: AniShift właściciela działa z checkoutu, a agenci zmieniający w nim pliki już raz zepsuli mu pracę („Stop resident before changing runtime files”). Odtwarzacz w tym checkoucie dzieliłby to ryzyko.
- **[W]** Wygodę „jednej komendy” daje `anishift doctor`: gdy odtwarzacza nie ma, podaje komendę `setup.cmd` PlayShift. Nie potrzeba do tego drugiej ścieżki instalacji w AniShift.
- Kontrargument: instalator AniShift ma już SHA256, `zip/7z/raw/nsis` i atomowe `Path.replace`, a osobne repo wymaga podobnego kodu drugi raz (szacunkowo 200–300 linii). **[R]** Przyjąć tę duplikację, ale skopiować schemat pól, nie kod. Wspólna biblioteka dla dwóch repo kosztowałaby więcej niż ta duplikacja.

### 1.4 Plan Tessery v3 a PlayShift

Log `MangaShift/docs/session-logs/2026-10-30-2022-tessera-motion-failed-architecture-next.md` ocenia pomysł „Tessera v3 w osobnym repo” krytycznie: struktura folderów nie była przyczyną porażki, a osobne repo dla jednej osoby podnosi koszt utrzymania. Co z tego pasuje:

- **Pasuje: decyzja na danych, nie z frustracji.** Tu argumenty za osobnym repo są inne niż przy Tesserze: osobne środowisko uruchomieniowe, osobne miejsce instalacji, binarki i licencje, inny język (Lua, conf). Tessera była biblioteką z dwoma konsumentami w tym samym workspace, więc osobne repo nic jej nie dawało.
- **Pasuje: „konsumenci czytają `dist`, nie `src`”.** Tutaj: AniShift czyta tylko kontrakt (dziennik, ścieżka exe), nigdy wnętrza odtwarzacza (format `watch_later`, nazwy skryptów).
- **Pasuje: strażnicy jako testy** (Tessera: test wartości CSS, reguła eslint). Tutaj: test składni konfiguracji i ładowania skryptów w CI (§5).
- **Nie pasuje:** przepisywanie od zera. PlayShift migruje działający `Videos\mpv` jednorazowym skryptem, nie buduje „v3”.

### 1.5 Publiczne czy prywatne

**[R] Prywatne na start.** Zmiana z prywatnego na publiczne jest tania i odwracalna, a z publicznego na prywatne nie (raz opublikowanej treści nie da się cofnąć). Przed publikacją trzeba: (a) rozstrzygnąć status fragmentów `mpv.conf`/`input.conf` z PlayKit („UNLICENSED”), (b) dodać `THIRD-PARTY.md` z licencjami zmienionych skryptów obcych, (c) potwierdzić, że fonty i SVP nie trafiają do repo. Koszt prywatnego repo: limit minut GitHub Actions (na Windows liczonych podwójnie) — przy smoke testach rzędu minut nieistotny [W].

## 2. Drzewa katalogów

### 2.1 Zasada

Układ instalacji wymuszają **konsumenci**, nie estetyka:

- **[F]** mpv ładuje konfigurację z katalogu `portable_config` obok `mpv.exe` i tam zapisuje `watch_later` i cache (`mpv.rst`, FILES ON WINDOWS). Dlatego `mpv.exe` musi leżeć w korzeniu instalacji, obok `portable_config/`.
- **[F]** mpv ładuje VapourSynth z `VSScript.dll` przez wyszukiwanie DLL albo ze ścieżki w zmiennej `VSSCRIPT_PATH`. Obsługa `VSSCRIPT_PATH` i API VapourSynth R74+ jest w mpv dopiero od commitów z 2026-04-10 i 2026-05-31, czyli **po** wydaniu v0.41.0 z 2025-12-21 (`video/filter/vf_vapoursynth.c`, `drv_vss_init`).
- **[F]** VapourSynth R81 portable to embedded Python (domyślnie 3.14) plus wheel `vapoursynth-81-cp312-abi3-win_amd64.whl` w `Lib\site-packages`. `vsscript.dll`, `vspipe.exe` i wtyczki rdzenia leżą w `Lib\site-packages\vapoursynth\`, a nie w korzeniu. Oficjalny skrypt dopisuje `Lib\site-packages` do `python3XX._pth` i instaluje wheel przez `pip` z `get-pip.py` bez przypiętej wersji i bez sumy (`Install-Portable-VapourSynth-R81.ps1`).
- **[W]** Przy VS R81 Python z VapourSynth może leżeć w podkatalogu (`lib/python/`), jeśli mpv dostanie `VSSCRIPT_PATH`. Wymaga to buildu mpv nowszego niż 2026-04-10 (nightly albo v0.42) i zmiennej środowiskowej użytkownika ustawianej przez `playshift setup`, bo skrót, skojarzenie plików ani `mpv.conf` nie ustawią mpv zmiennej środowiskowej. **[?]** Czy `vsscript.dll` z wheela sam znajduje `python314.dll` dwa katalogi wyżej: sprawdzić smoke testem po wyborze buildu (R2/R3). Gdyby nie znajdował, wracamy do płaskiego korzenia jak dziś.
- **[F]** `ytdl_hook` szuka `yt-dlp.exe` najpierw w katalogu konfiguracji, potem przez systemowe wyszukiwanie programu, które na Windows zaczyna od katalogu `mpv.exe` (`player/lua/ytdl_hook.lua:971-985`). Dziś `yt-dlp.exe` leży w korzeniu i działa.

### 2.2 Repo = instalacja (`Videos\mpv` po migracji)

`T` = w gicie, `P` = pobierane według locka (gitignored), `S` = stan i dane użytkownika (gitignored, nigdy nie nadpisywane przez `setup`).

```text
PlayShift/                          klon repo = gotowy odtwarzacz
├── AGENTS.md                    T  reguły dla agentów (bramki, zakazy, mapa)
├── README.md                    T  instalacja, aktualizacja, skróty
├── THIRD-PARTY.md               T  licencje skryptów obcych trzymanych w repo
├── pyproject.toml, uv.lock      T  narzędzie playshift + dev (pytest, ruff, mypy) przez uv add
├── deps.toml                    T  manifest: co, skąd, polityka aktualizacji (ręcznie)
├── deps.lock.json               T  lock: wersja, URL, sha256, size_bytes, members (generuje playshift)
├── setup.cmd                    T  dwuklik: sprawdza uv, potem `uv run playshift setup`
├── update.cmd                   T  `git pull --ff-only` + `uv run playshift setup`
├── playshift/                   T  pakiet narzędzia (stdlib): cli.py, deps.py, install.py, doctor.py
├── tests/                       T  pytest: manifest/lock/instalator + smoke mpv bez okna
├── scripts/hooks/               T  check_commit_msg.py jak w AniShift
├── scripts/tmp/                 T  jednorazowa migracja z obecnego Videos\mpv (uruchomić, usunąć)
├── docs/work/<nn>-<nazwa>/      T  plany i raporty po polsku
├── .github/workflows/ci.yml     T  windows-latest (§5)
├── .luacheckrc, stylua.toml     T  lint i format Lua
│
├── mpv.exe, mpv.com             P  build mpv (wybór R2)
├── yt-dlp.exe                   P
├── lib/
│   ├── python/                  P  Python 3.14 embed + Lib/site-packages/vapoursynth (+ wtyczki VS)
│   ├── 7zip/                    P  7zr.exe, potrzebny do archiwów .7z (jak w AniShift)
│   └── models/                  P  modele RIFE/AnimeJaNai/TensorRT (opcjonalne komponenty, GB)
├── portable_config/
│   ├── mpv.conf, input.conf, profiles.conf, script-opts.conf     T
│   ├── script-opts/*.conf       T  opcje skryptów (w tym uosc.conf z languages=pl)
│   ├── scripts/
│   │   ├── progress/main.lua    T  własny: dziennik postępu (§4.2)
│   │   ├── <własne>.lua         T  własne skrypty (dziś np. ruler, minimap)
│   │   ├── <obcy-zmieniony>.lua T  kopia z nagłówkiem źródła i commita + licencja
│   │   └── uosc/, thumbfast.lua P  obce niezmienione, z wydań upstreamu
│   ├── shaders/                 P  Anime4K, FSRCNNX… z upstreamu (T tylko własne)
│   ├── vs/*.vpy                 T  skrypty VapourSynth
│   ├── fonts/                   P  publiczne fonty ikon + klon prywatnego MattyMroz/fonts
│   ├── state/                   S  watch_later/, progress.jsonl, saved-props.json
│   └── cache/                   S  cache shaderów, ICC, miniatur
├── cache/                       S  pobrane archiwa po sha256 (rollback offline)
├── tmp/                         S  staging pobierania i rozpakowywania
└── .installed.json              S  co zainstalowano: komponent → wersja → pliki z sha256
```

Uwagi:

- Wariant awaryjny (gdy `VSSCRIPT_PATH` nie zadziała): zawartość `lib/python/` trafia do korzenia, jak dziś. Zmienia się tylko `dest` w locku, nie narzędzie.
- **[R]** Obce skrypty bez zmian pobieramy (uosc 5.13.0 ma wydanie `uosc.zip` z sumą i wbudowane `intl/pl.json`, więc polski UI nie wymaga zmian w kodzie [F]). Do repo trafia tylko kopia, którą zmieniamy, z nagłówkiem `źródło + commit` (tak robi dziś mpv-lazy: `save_global_props.lua`, `thumbfast.lua`) i z licencją.
- `state/` zbiera rozproszone dziś `_cache/watch_later`, `saved-props.json` i nowy dziennik, żeby `.gitignore` i migracja miały jeden katalog danych.
- `.gitignore` korzenia jako biała lista (wzorzec z `.gitignore` AniShift: „`dir/*` + `!dir/keeper`”): `/*`, potem `!/portable_config/`, `!/playshift/`, `!/tests/`, `!/scripts/`, `!/docs/`, `!/.github/`, `!/deps.*`, `!/*.md`, `!/*.cmd`, `!/pyproject.toml`, `!/uv.lock`, `!/.gitignore`, `!/.luacheckrc`, `!/stylua.toml`; w `portable_config/`: `state/`, `cache/`, `fonts/` i katalogi obcych skryptów z locka.

### 2.3 Dlaczego nie `src/` + build do `dist/`

**[W]** Osobne drzewo źródeł i wynikowa paczka oznaczają krok kopiowania i dwie kopie konfiguracji. Właściciel stroi `mpv.conf` w trakcie oglądania (pliki zmieniane 2026-10-17), więc zmiana w zainstalowanej kopii albo ginie, albo trzeba ją ręcznie przenosić z powrotem. Gdy repo jest instalacją, każda zmiana jest od razu widoczna w `git diff`. Rolę „wydania” pełni klon `Videos\mpv` na `main` (§3.4).

## 3. Zależności, budowanie i aktualizacje

### 3.1 Co w gicie, co pobierane

| Rzecz | Gdzie | Dlaczego |
| --- | --- | --- |
| `mpv.conf`, `input.conf`, `profiles.conf`, `script-opts/`, `vs/*.vpy` | git | Edytowane przez właściciela; mały tekst; historia zmian ma wartość |
| Własne skrypty Lua, polskie teksty własnych skryptów | git | Kod produktu |
| Obcy skrypt zmieniony | git + `THIRD-PARTY.md` | Zmiana jest nasza; licencja wymaga zachowania noty |
| Obcy skrypt bez zmian (uosc, thumbfast), shadery | pobierane | Wersjonowane upstream; aktualizacja = zmiana locka |
| mpv, yt-dlp, 7zr, Python embed, wheel VapourSynth, wtyczki VS | pobierane | Binarki; licencje (GPL: obowiązek udostępnienia źródeł przy redystrybucji) |
| Modele, TensorRT, SVP | pobierane, opcjonalne | GB; CC BY-NC-SA (AnimeJaNai); SVP jest zamknięte — nie rehostować |
| Fonty Officina | klon prywatnego `MattyMroz/fonts` | Prywatne; ten sam mechanizm co `anishift/setup/fonts.py` |
| `deps.toml`, `deps.lock.json` | git | Jedno źródło prawdy o wersjach; rollback przez git |

### 3.2 Manifest i lock

Dwa pliki, bo mają różnych autorów: `deps.toml` pisze człowiek (co i skąd, polityka), `deps.lock.json` generuje narzędzie (dokładne wartości). AniShift ma jeden ręcznie utrzymywany plik `bin_hashes.json` [F], co działa, dopóki nikt nie aktualizuje zależności automatycznie. Tutaj automatyczna aktualizacja jest wymaganiem, więc generowane wartości trzymamy osobno, żeby ręczna edycja nie mieszała się z wynikiem narzędzia [W].

```toml
# deps.toml (przykład kształtu; wybór źródeł należy do R2–R5)
[yt-dlp]
github = "yt-dlp/yt-dlp"
asset = '^yt-dlp\.exe$'
track = "latest"          # playshift upgrade podnosi automatycznie
archive = "raw"
members = [{ archive_path = "yt-dlp.exe", dest = "yt-dlp.exe" }]

[mpv]
github = "zhongfly/mpv-winbuild"
asset = '^mpv-x86_64-v3-\d{8}-git-[0-9a-f]+\.7z$'
track = "manual"          # tylko `playshift upgrade mpv` po smoke teście
archive = "7z"
members = [{ archive_path = "mpv.exe", dest = "mpv.exe" }, { archive_path = "mpv.com", dest = "mpv.com" }]
```

```json
{
  "mpv": {
    "version": "2026-10-30-8e5a96fc45",
    "url": "https://github.com/zhongfly/mpv-winbuild/releases/download/2026-10-30-8e5a96fc45/mpv-x86_64-v3-20261030-git-8e5a96fc45.7z",
    "sha256": "4ddb3aea5e175654663ab5d16a30d086479594e6fcc49613e3044dd6b5ca302f",
    "size_bytes": 34944410,
    "archive": "7z",
    "members": [{ "archive_path": "mpv.exe", "dest": "mpv.exe" }]
  }
}
```

(Wartości z przykładu są prawdziwe: `digest` i `size` zasobu w API GitHub [F]. Czy ten build ma VapourSynth, rozstrzyga R2.)

- **[F]** API wydań GitHub podaje dla zasobu pole `digest` (`sha256:…`): mpv v0.41.0, zhongfly, VapourSynth R81, uosc 5.13.0. zhongfly publikuje też `sha256.txt`. `upgrade` może więc wziąć sumę z API, a przy instalacji i tak liczy ją od nowa z pobranego pliku.
- **[R]** Rodzaje operacji ograniczyć do potrzebnych: rozpakowanie `raw/zip/7z` (jak AniShift), `python-embed` (rozpakuj i dopisz `Lib\site-packages` do `._pth`), `wheel` (instalacja przez `uv pip install --python lib\python\python.exe --target …` zamiast nieprzypiętego `get-pip.py`; **[?]** sprawdzić na embedded Pythonie), `git` (klon prywatnych fontów przez `gh`).
- **[R]** Bez osobnego `requirements` dla Pythona VapourSynth, dopóki skrypty `.vpy` potrzebują tylko wheela VS i plików `.py` (dziś `k7sfunc.py`, `qtgmc.py` leżą w korzeniu [F]). Takie pliki `.py` to też zasoby locka (`raw`).

### 3.3 Narzędzie: Python + uv, nie PowerShell

| | Python + uv | PowerShell 5.1 |
| --- | --- | --- |
| Wymagania wstępne | `uv` (właściciel ma; świeża maszyna: `winget install astral-sh.uv`) | nic |
| 7z, JSON, TOML, SHA256 | stdlib (`tomllib`, `hashlib`, `zipfile`) + 7zr.exe | `ConvertFrom-Json`, `Get-FileHash`; TOML brak; 7zr.exe |
| Testy | pytest, ruff, mypy — standard właściciela | Pester 3.4 w systemie, inny standard |
| Spójność z AniShift/MangaShift | ta sama konwencja (`setup`, `doctor`, uv) | obcy język w rodzinie |

**[R]** Python 3.14 przez uv, pakiet `playshift/` z CLI na stdlib `argparse`; `setup.cmd` to trzy linie, które tylko wywołują uv. Embedded Python VapourSynth nie nadaje się na runtime narzędzia, bo powstaje dopiero po instalacji.

Komendy (nazwy jak w AniShift):

- `playshift setup` — doprowadza instalację do stanu locka: pobiera brakujące lub zmienione komponenty, sprawdza SHA256, usuwa pliki, które należały do poprzedniej wersji komponentu (według `.installed.json`), ustawia `VSSCRIPT_PATH`, jeśli wariant §2.1 się potwierdzi. Wywołanie jest idempotentne i nie dotyka `state/`.
- `playshift upgrade [komponent…]` — bez argumentów podnosi tylko `track = "latest"` (yt-dlp, uosc), z argumentem także `manual`; przepisuje lock, pokazuje różnicę, uruchamia `setup` i `doctor`.
- `playshift doctor` — testy bez okna (§5) plus kontrola, że `VSSCRIPT_PATH` wskazuje na tę instalację.

**[R]** yt-dlp aktualizujemy przez lock, nie przez `yt-dlp -U`: samoaktualizacja zmieniłaby plik, który `setup` uzna za niezgodny z lockiem i przywróci.

### 3.4 Wydania, aktualizacja paczki, rollback

- **[R] Bez paczek binarnych w GitHub Release.** Dla jednego użytkownika nie dają nic poza obowiązkami: redystrybucja GPL (mpv) wymaga udostępnienia źródeł, AnimeJaNai ma klauzulę NC-SA, SVP nie wolno rehostować, a pliki muszą mieć mniej niż 2 GiB [F]. PlayKit i AnimeJaNai rehostują i biorą te obowiązki na siebie [F].
- **Wydanie** = tag `vYYYY.MM.DD` na `main`; notatka wydania = różnica `deps.lock.json` i konfiguracji. Klon `Videos\mpv` śledzi `main`.
- **Aktualizacja paczki** = `update.cmd` (`git pull --ff-only`, potem `setup`). Aktualizacja zależności = `playshift upgrade` w klonie roboczym, commit locka, PR, a potem `update.cmd` w `Videos\mpv`.
- **Rollback** = `git revert` commitu locka (albo checkout tagu) i `setup`. Archiwa w `cache/` po sha256 pozwalają wrócić offline; trzymać bieżącą i poprzednią wersję każdego komponentu.
- **[R] Uruchomiony odtwarzacz blokuje aktualizację.** Na Windows działającego `mpv.exe` i załadowanych DLL nie da się nadpisać, a instalator AniShift podmienia pliki pojedynczo, bez transakcji na cały komponent [F: `anishift/setup/AGENTS.md`]. `setup` musi więc **przed** pierwszą zmianą sprawdzić, czy wszystkie pliki docelowe da się otworzyć do zapisu, i w razie blokady odmówić z komunikatem „zamknij odtwarzacz”. Inaczej zostaje pół starej, pół nowej wersji.
- Migracja obecnego `Videos\mpv`: jednorazowy `scripts/tmp/migrate.py` przenosi `watch_later`, `saved-props.json` i własne pliki do nowego układu, potem jest usuwany (zasada „zero legacy”). Stary katalog do czasu sprawdzenia zostaje jako kopia zapasowa poza repo.

## 4. Integracja z AniShift

### 4.1 Podział odpowiedzialności

| Sprawa | Właściciel | Uwagi |
| --- | --- | --- |
| Odtwarzanie, pozycja wznowienia, wybór ścieżek, upscaling, playlisty | PlayShift | mpv `save-position-on-quit` już to robi [F: `mpv.conf`] |
| Wybór ścieżki lektora przy odtwarzaniu | PlayShift (`alang`, `aid` lub skrypt) | AniShift dostarcza metadane MKV (język, nazwa, flaga domyślna); pomysł „Lektor od razu w odtwarzaczu” z `docs/ideas.md:100` |
| Fakt „ten plik odtworzono do X%” | PlayShift (dziennik) | Tylko fakty, bez reguł biznesowych |
| Decyzja „odcinek obejrzany” (próg), dopasowanie pliku do serii i odcinka | AniShift | AniShift zna bibliotekę, subskrypcje, AniList ID |
| Synchronizacja MAL/AniList, tokeny | AniShift | Klient AniList jest w `services/catalog/` [F] |
| Edycja napisów, tłumaczenie, lektor, merge | AniShift | „Odtwarzacz odtwarza, AniShift edytuje” |

### 4.2 Kontrakt minimalny v1

**A. Otwieranie odcinka — bez zmian.** AniShift dalej wywołuje `os.startfile`, a skojarzenie plików ustawia instalator PlayShift (dziś `mpv-install.bat` z mpv-install [F]). AniShift nie potrzebuje do tego ścieżki odtwarzacza.

**B. Dziennik postępu** `portable_config/state/progress.jsonl`, który pisze skrypt `scripts/progress/main.lua`:

```json
{"v":1,"time":1793462400,"path":"D:\\Anime\\ready\\Title - 05.mkv","size":1503238553,"duration":1420.5,"percent":91.3,"reason":"checkpoint"}
```

- `v` — wersja formatu; zmiana niezgodna wstecz podnosi `v`, a AniShift obsługuje tylko bieżącą (zero legacy).
- `time` — UNIX UTC zapisu; `path` — ścieżka absolutna jak w mpv; `size` — bajty z `utils.file_info` (pozwala dopasować plik po zmianie nazwy); `duration` — sekundy; `percent` — **najwyższy** procent osiągnięty w tej sesji pliku.
- `reason`: `checkpoint` (jednorazowo po przekroczeniu progu z `script-opts`, domyślnie 90), `eof` (właściwość `eof-reached`), `end` (zdarzenie `end-file`: zmiana pliku, stop, wyjście).
- Logowane są tylko pliki lokalne (bez `://`): YouTube i strumienie AniShiftu nie dotyczą, a przy okazji mniej prywatnych danych na dysku.
- Plik tylko do dopisywania, UTF-8, jedna linia JSON zakończona `\n`; odtwarzacz otwiera go, dopisuje i zamyka przy każdym wpisie. Czytelnik pomija ostatnią linię bez `\n`. Bez rotacji (jedna linia na kilka odcinków dziennie).
- **[F] Dlaczego trzy powody, a nie samo `end-file`:** właściciel ma `keep-open = yes`. Sprawdzone bez okna: z `--keep-open=yes` mpv po końcu pliku nie wysyła `end-file` i nie kończy działania (proces zabity po 20 s, dziennik pusty). Bez `keep-open` `end-file` przychodzi z `reason=eof`. Obserwacja `eof-reached` przy `keep-open=yes` działa (wpis `{"event":"eof","percent":100}`). Zabicie procesu nie zapisuje niczego, stąd `checkpoint` przy 90%.

**C. Po stronie AniShift** (do planu AniShift, nie PlayShift):

- Ustawienie ścieżki odtwarzacza (np. `ANISHIFT_PLAYER_DIR` albo pole panelu) i check w `anishift doctor`: brak = WARN z poleceniem `setup.cmd`.
- Rezydent obserwuje plik przez istniejący `platform/directory_watch.py` [F], pamięta własny offset w `config/watch/`, dopasowuje `path`/`size` tylko do plików swojego workspace, stosuje własny próg (np. 85% jak domyślnie w mpv-anilist-updater [F]) i synchronizuje listę. Przetwarzanie jest idempotentne: ten sam wpis przeczytany drugi raz nic nie zmienia.
- AniShift nigdy nie pisze do dziennika i nie czyta wewnętrznych plików mpv (`watch_later` to nazwa pliku z hasha ścieżki i `start=…`, format nieudokumentowany jako kontrakt).

### 4.3 Wbudowana historia mpv — dlaczego nie wystarcza

**[F]** mpv od v0.40 ma `--save-watch-history` (`~~state/watch_history.jsonl`: `time`, `path`, `title`), ale zapisuje **otwarcie** pliku, nie postęp. Do decyzji „obejrzane” to za mało; może jednak zostać włączone jako osobna funkcja odtwarzacza.

### 4.4 JSON IPC — kiedy i jak

- **[F]** Na Windows mpv tworzy named pipe `\\.\pipe\<nazwa>` (prefiks dodaje sam), dostępny tylko dla tego samego użytkownika, na tym samym lub wyższym poziomie integralności, z `PIPE_REJECT_REMOTE_CLIENTS` i `FILE_FLAG_FIRST_PIPE_INSTANCE` (`input/ipc-win.c`). Protokół nie ma uwierzytelnienia, a polecenie `run` uruchamia dowolny program (`ipc.rst`).
- **[F]** Przez `FILE_FLAG_FIRST_PIPE_INSTANCE` stała nazwa z `mpv.conf` właściciela (`input-ipc-server = mpvpipe`) działa tylko w pierwszej instancji mpv; druga zgłasza błąd i nie ma IPC.
- **[F]** Prosty synchroniczny klient w Pythonie (`open(r"\\.\pipe\…", "r+b", buffering=0)`, linia JSON, odczyt do `\n`) działa: `get_property mpv-version` zwrócił `{"data":"mpv v0.36.0-711-g250429da","request_id":7,"error":"success"}`, a `quit` zamknął mpv z kodem 0. Jednoczesne czytanie zdarzeń i wysyłanie poleceń wymaga I/O z `FILE_FLAG_OVERLAPPED` (`ipc.rst`), czyli wątku czytającego albo nieudokumentowanego `ProactorEventLoop.create_pipe_connection` z asyncio [F: `Lib/asyncio/windows_events.py:318`; brak w dokumentacji].
- **[W] Dlaczego nie na start:** obecna potrzeba (śledzenie MAL/AniList) nie wymaga sterowania na żywo. IPC działa tylko wtedy, gdy AniShift uruchomił mpv albo zna nazwę potoku, i tylko gdy rezydent działa w czasie oglądania. Pliki otwierane z Eksploratora wymagałyby stałej nazwy, a ta koliduje przy dwóch oknach. Dziennik działa bez względu na to, kto otworzył plik i czy AniShift wtedy działał. Prościej go też przetestować.
- **[F]** Tak już działa thumbfast u właściciela: uruchamia pomocnicze mpv z potokiem nazwanym od PID rodzica (`--input-ipc-server=thumbfast62052`, odczyt `Win32_Process` 2026-10-31).
- **[R] Kiedy IPC:** gdy pojawi się wymaganie typu „panel pokazuje, co teraz leci” albo „AniShift dokłada następny odcinek do otwartego okna”. Wtedy AniShift uruchamia `mpv.exe` z unikalnym `--input-ipc-server=anishift-<pid>`, a klient żyje w jednym module `platform/`.

### 4.5 Czego nie robić

- Edycji napisów, tłumaczenia ani TTS w odtwarzaczu.
- Wywołań API MAL/AniList ani tokenów w Lua (to byłby drugi klient katalogu obok `services/catalog/`).
- Wiedzy odtwarzacza o układzie workspace AniShift (`ready/`, `tmp/`).
- Czytania przez AniShift `watch_later`, `saved-props.json` i innych plików wewnętrznych mpv.
- Stałej, wspólnej nazwy potoku jako kontraktu.
- Instalacji odtwarzacza przez AniShift do jego checkoutu.

### 4.6 Ukryte sprzężenie: styl napisów

**[F]** Wartości `_MPV_*` w `anishift/services/subtitles/restyle.py` kopiują `sub-font-size`, `sub-border-size`, `sub-shadow-*` i `sub-margin-y` z `mpv.conf`. Zmiana `mpv.conf` bez zmiany AniShift rozjeżdża wygląd dialogów z napisami tekstowymi, a nic tego nie wykrywa. **[R]** Najmniejsza kontrola: gdy ścieżka odtwarzacza jest ustawiona, `anishift doctor` czyta te kilka kluczy z `portable_config/mpv.conf` i daje WARN przy różnicy. Kopia wartości zostaje świadomie (tańsza niż wspólna konfiguracja), ale przestaje być cicha.

## 5. Testowalność bez okien

Sprawdzone na obecnym `mpv.com` (v0.36): wszystkie poniższe komendy działają bez okna (`--vo=null --ao=null`).

| Kontrola | Jak | Uwaga |
| --- | --- | --- |
| Odtwarzanie bez okna | `mpv.com --vo=null --ao=null --frames=5 "av://lavfi:testsrc=duration=1"` | [F] kod wyjścia 0, bez pliku wideo w repo |
| Błąd opcji w pliku konfiguracji | uruchomić z konfiguracją repo i `--log-file`, szukać `Error parsing option` / `setting option … failed` | [F] zła opcja w pliku daje komunikat, ale **kod wyjścia 0**; sam kod wyjścia nie wystarcza |
| Błąd opcji w CLI | kod wyjścia | [F] `--foo-bar=1` → kod 1 |
| Ładowanie skryptów Lua | log z `--msg-level=all=warn`, szukać `Lua error` / błędów skryptów | błąd skryptu nie zatrzymuje mpv [W]; trzeba czytać log |
| Dziennik postępu | prawdziwy mpv + `--script=…/progress` + `--script-opts=progress-path=<tmp>` na `lavfi` z `--keep-open=yes` i bez niego | [F] oba scenariusze sprawdzone sondą w tym researchu |
| IPC (gdy dojdzie) | mpv `--idle=yes --input-ipc-server=<unikalna>`, klient testowy, `quit` | [F] sprawdzone |
| Lint Lua | `luacheck.exe` (v1.2.0, samodzielny plik exe w wydaniu, MIT) z `.luacheckrc` (`globals = {"mp"}`) | pobierany przez lock jako narzędzie dev |
| Format Lua | StyLua (v2.6.0) `--check` | opcjonalnie |
| Narzędzie playshift | pytest: parsowanie manifestu i locka, path traversal w `dest`, zła suma, blokada pliku, `._pth` | jak testy `anishift/setup` |
| VapourSynth | lokalnie `doctor`: `python -c "import vapoursynth"` i `vspipe --version`; filtr `--vf=vapoursynth=…` na `lavfi` | w CI tylko CPU; RIFE/TensorRT tylko ręczny smoke na RTX 5090 |

- **[R]** Unit testów Lua przez busted z atrapą `mp` nie robić: atrapa testowałaby własne wyobrażenie API mpv. Logikę skryptu sprawdza prawdziwy mpv bez okna, który i tak trzeba pobrać do smoke testu.
- **[R] CI** `windows-latest`: `uv sync`, ruff, mypy, pytest, `playshift setup --only mpv,yt-dlp,7zr` (około 100 MB, cache po sha256), smoke konfiguracji i skryptów, luacheck. Pre-commit i commit-msg jak w AniShift (scope z zamkniętej listy).
- Testy przy `doctor` uruchamiane na instalacji właściciela muszą wyłączać zapisy do `state/` (`--save-position-on-quit=no`, dziennik do `tmp/`).

## 6. Nazwa

- **[F]** `gh search repos PlayShift`: 4 repozytoria, wszystkie z 0 gwiazdek, żadne nie jest odtwarzaczem (synchronizacja playlist Spotify/Apple, konwerter Selenium→Playwright, Play na OpenShift z 2015, puste). Wyszukiwarka nie znalazła produktu o tej nazwie. Najbliższe nazwy to SongShift (aplikacja iOS) i SHIFT PLAYER (Shift72), inne rynki.
- **[W]** Nazwa pasuje do rodziny `*Shift` i do repo `MattyMroz/AniShift`, `MattyMroz/MangaShift`. Kolizja z PlayKit (`mpv_PlayKit`) jest tylko luźnym podobieństwem prefiksu. Lepszej alternatywy nie widzę, więc żadnej nie proponuję.

## 7. Ryzyka

| Ryzyko | Wpływ | Reakcja |
| --- | --- | --- |
| `VSSCRIPT_PATH` i VS R81 wymagają mpv nowszego niż v0.41.0; build bez VapourSynth | brak interpolacji/upscalingu przez VS | R2 wybiera build z `vapoursynth` w `--version`; smoke `doctor`; awaryjnie płaski korzeń |
| Zmienna użytkownika `VSSCRIPT_PATH` wpływa na inne programy z VapourSynth | inny program użyje tej instalacji VS | `doctor` sprawdza, czy zmienna wskazuje na tę instalację; dokumentacja w README |
| Aktualizacja przy otwartym odtwarzaczu | pół starej, pół nowej wersji | kontrola blokad przed pierwszą zmianą (§3.4) |
| Fragmenty konfiguracji z PlayKit „UNLICENSED” | problem przy publikacji repo | repo prywatne do audytu; własne przepisanie spornych fragmentów |
| Utrata wpisu przy twardym zabiciu przed progiem | brak synchronizacji odcinka | próg `checkpoint` 90%; ręczna korekta w AniShift |
| Rozjazd stylu napisów AniShift i `mpv.conf` | niespójny wygląd dialogów | WARN w `anishift doctor` (§4.6) |
| Duplikacja logiki instalatora z AniShift | dwa miejsca do poprawek bezpieczeństwa (np. path traversal) | ten sam schemat pól i te same testy graniczne w obu repo |
| Dwa klony podwajają modele (GB) | zajętość dysku | modele jako komponenty opcjonalne (`setup --with models`) tylko tam, gdzie są potrzebne |
| Nieprzypięte pobieranie w oficjalnym instalatorze VS (`get-pip.py`, „najnowsza łatka” Pythona) | niepowtarzalna instalacja | nie używać oficjalnego skryptu; wszystko z locka |

## 8. Pytania do właściciela

1. Repo prywatne na start, publiczne dopiero po audycie licencji konfiguracji — zgoda?
2. Dwa klony (`PROJECTS\PlayShift` do pracy, `Videos\mpv` do oglądania) czy jeden klon w `Videos\mpv` z ryzykiem, że praca agentów zmieni Ci odtwarzacz w trakcie seansu?
3. Zgoda na zmienną środowiskową użytkownika `VSSCRIPT_PATH`, ustawianą przez `playshift setup`? Alternatywą jest płaski katalog jak dziś (Python i DLL VapourSynth obok `mpv.exe`).
4. Czy odtwarzacz ma też logować postęp YouTube i strumieni (dziś proponuję tylko pliki lokalne)?
5. Próg „obejrzane” w AniShift: stały (np. 85% albo napisy końcowe) czy ustawienie panelu?

## Źródła

Dostęp 2026-10-31, o ile nie podano inaczej.

- mpv, `DOCS/man/ipc.rst` (bezpieczeństwo, Windows, framing, async): https://github.com/mpv-player/mpv/blob/master/DOCS/man/ipc.rst
- mpv, `DOCS/man/options.rst` (`--input-ipc-server`, `--keep-open`, `--no-config`, `--config-dir`, `--save-watch-history`, `--log-file`): https://github.com/mpv-player/mpv/blob/master/DOCS/man/options.rst
- mpv, `DOCS/man/mpv.rst` (`portable_config`, kody wyjścia, `av://`): https://github.com/mpv-player/mpv/blob/master/DOCS/man/mpv.rst
- mpv, `DOCS/man/input.rst` (zdarzenie `end-file`): https://github.com/mpv-player/mpv/blob/master/DOCS/man/input.rst
- mpv, `DOCS/interface-changes.rst` (dodanie `--save-watch-history` przed v0.40.0): https://github.com/mpv-player/mpv/blob/master/DOCS/interface-changes.rst
- mpv, `input/ipc-win.c` (SDDL, `FILE_FLAG_FIRST_PIPE_INSTANCE`): https://github.com/mpv-player/mpv/blob/master/input/ipc-win.c
- mpv, `video/filter/vf_vapoursynth.c` (`VSSCRIPT_PATH`, commity 75b2ccfeb1 2026-04-10, 44a9b03f24 2026-05-31): https://github.com/mpv-player/mpv/commits/master/video/filter/vf_vapoursynth.c
- mpv, `player/lua/ytdl_hook.lua` (szukanie `yt-dlp`): https://github.com/mpv-player/mpv/blob/master/player/lua/ytdl_hook.lua
- mpv, `Copyright` (GPLv2+/LGPLv2.1+): https://github.com/mpv-player/mpv/blob/master/Copyright
- mpv wydania (v0.41.0 2025-12-21, `digest` zasobów): https://github.com/mpv-player/mpv/releases
- hooke007/mpv_PlayKit (struktura repo, `LICENSE.MD`, wydanie 20260510 z wolumenami 7z): https://github.com/hooke007/mpv_PlayKit
- zhongfly/mpv-winbuild (wydanie 2026-10-30-8e5a96fc45, `sha256.txt`): https://github.com/zhongfly/mpv-winbuild/releases
- shinchiro/mpv-winbuild-cmake (wydanie 20261021): https://github.com/shinchiro/mpv-winbuild-cmake/releases
- VapourSynth R81 (2026-10-04): `Install-Portable-VapourSynth-R81.ps1`, `VapourSynth64-Portable-R81.zip` (sha256 `6d625bd3…63436`, sprawdzone lokalnie), wheel `vapoursynth-81-cp312-abi3`: https://github.com/vapoursynth/vapoursynth/releases/tag/R81
- the-database/mpv-upscale-2x_animejanai 3.9.0 (`manifest.json` z `overlay_paths`/`user_preserve`, komponenty, licencja CC BY-NC-SA 4.0): https://github.com/the-database/mpv-upscale-2x_animejanai/releases/tag/3.9.0
- tomasklaen/uosc 5.13.0 (`uosc.zip` z digestem, `src/uosc/intl/pl.json`, LGPL-2.1): https://github.com/tomasklaen/uosc
- po5/thumbfast (MPL-2.0): https://github.com/po5/thumbfast
- AzuredBlue/mpv-anilist-updater (próg 85%, `UPDATE_PERCENTAGE`): https://github.com/AzuredBlue/mpv-anilist-updater
- GitHub Docs, About releases (limit 2 GiB na plik): https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Python, asyncio event loop (Proactor, wymóg overlapped I/O): https://docs.python.org/3/library/asyncio-eventloop.html; `Lib/asyncio/windows_events.py`: https://github.com/python/cpython/blob/main/Lib/asyncio/windows_events.py
- lunarmodules/luacheck v1.2.0 (`luacheck.exe`): https://github.com/lunarmodules/luacheck/releases; JohnnyMorganz/StyLua v2.6.0: https://github.com/JohnnyMorganz/StyLua/releases
- Wyszukiwanie nazwy: `gh search repos PlayShift` (4 trafienia, 0 gwiazdek) oraz wyszukiwarka WWW (brak produktu PlayShift; najbliższe: https://www.shift72.com/features/player, SongShift)
- Lokalnie: `Videos\mpv` (listing, `LICENSE.MD`, `portable_config/mpv.conf`), AniShift `external/README.md`, `anishift/setup/{AGENTS.md,manifest.py}`, `anishift/paths.py`, `anishift/platform/tray.py`, `anishift/services/subtitles/restyle.py`, MangaShift `AGENTS.md`, `tessera/AGENTS.md`, log sesji Tessery 2026-10-30.
- Sondy w scratchpadzie (bez zmian w `Videos\mpv`): odtwarzanie `lavfi`, zła opcja w pliku i w CLI, `end-file` z `keep-open` i bez, `eof-reached`, klient named pipe w Pythonie.
