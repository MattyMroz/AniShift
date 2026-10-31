---
kind: research
id: playshift-r5-scripts-ui
date: 2026-10-31
subject: katalog skryptów, UI i funkcji mpv dla PlayShift (stan na 2026-10-31)
---

# R5: skrypty, UI i funkcje, z których złożyć PlayShift

Oznaczenia: **[F]** fakt z dowodem (repo, kod, dokumentacja, `gh api`), **[W]** wniosek, **[?]** niewiadoma. Daty commitów i wydań sprawdzone przez `gh api` 2026-10-31. Próg porzucenia z briefu: brak commita od ponad 18 miesięcy, czyli przed 2025-04-30. Rekomendacje: **bierzemy** / **może** / **nie**.

## 1. Odpowiedź w skrócie

**Najważniejsze ustalenie [F]:** `mpv.exe` właściciela to `v0.36.0-711-g250429da`, czyli commit z 2023-11-01 (odczyt `VersionInfo` pliku, data commita z `gh api repos/mpv-player/mpv/commits/250429da`). Od tego czasu wyszły mpv 0.37, 0.38, 0.39, 0.40 i 0.41.0 (2025-12-21), a do wbudowanego mpv weszło dużo rzeczy, które dziś robią osobne skrypty. Wymiana mpv na aktualny build sama usuwa około połowy obecnych dodatków.

**Rekomendowany zestaw:**

| Warstwa | Wybór |
|---|---|
| Rdzeń | aktualne mpv ≥ 0.41.0 (stabilne) z wbudowanymi `select.lua`, `positioning.lua`, `console`, `stats`, `ytdl_hook`, właściwością `clipboard`, opcjami `--autocreate-playlist` i `--save-watch-history` |
| UI | **upstream uosc 5.13.0** (nie fork z MPV_lazy ani z PlayKit) z `languages=slang,en`, bo `slang` zaczyna się od `pl` i wtedy działa wbudowany `pl.json`; dodatkowo własny plik JSON z poprawkami tłumaczeń; konfiguracja minimalistyczna (cienka linia postępu, interfejs widoczny tylko przy zbliżeniu kursora) |
| Miniatury | thumbfast |
| Pliki | `uosc/delete-file-next` / `-prev` / `-quit` z `use_trash=yes` (Kosz Windows), `--autocreate-playlist=filter`, `save-position-on-quit` (już jest), `--save-watch-history` + `select/select-watch-history` |
| Internet | yt-dlp (aktualizowany) + `ytdl_hook`, wklejanie przez `uosc/paste-to-open` (korzysta z właściwości `clipboard`), `uosc/stream-quality`, SponsorBlock: `mpv_sponsorblock_minimal` (Codeberg) |
| Sterowanie | wbudowane: `speed`, `video-rotate`, `positioning.lua`, `screenshot`, `ab-loop`, profile; menu: uosc z komentarzy `#!` w `input.conf`; paleta: `select/menu` + `uosc/keybinds` |
| Diagnostyka | wbudowany `stats.lua` (strony 1–5) |
| Śledzenie MAL | **przez AniShift**: odtwarzacz zgłasza „plik obejrzany”, AniShift ustala tytuł i odcinek i aktualizuje MAL; zastępczo, bez kodu, Taiga do przetestowania |

Do decyzji właściciela jako dodatki „może”: `mpv-skipsilence` albo `speed-transition` (przyspieszanie ciszy i przerw bez napisów), `mpv-quality-menu`, `mpv-youtube-upnext`, `mpv-youtube-chat`, Discord RPC, `autosubsync-mpv`, `SmartSkip` (pomijanie czołówki i napisów końcowych).

## 2. Stan wyjściowy (tylko to, co wpływa na katalog)

- **[F]** UI: `portable_config/scripts/uosc/main.lua:9` → `uosc_version = '5.0.0'` (wydanie upstream z 2023-10-21), ale z `lib/lang.lua` z polskimi tekstami `_cm_*`. To fork z MPV_lazy, a nie upstream. Upstream ma `lib/intl.lua` i `intl/*.json`. Repo `hooke007/MPV_lazy` jest zarchiwizowane (ostatni push 2025-09-06).
- **[F]** Skrypty: `SmartCopyPaste.lua` (Eisa01 v3.1), `thumbfast.lua`, `save_global_props.lua` (z `zenwarr/mpv-config`), `image-positioning.lua`, `minimap.lua`, `ruler.lua`, `freeze-window.lua`, `detect-image.lua` (rodzina `occivink/mpv-image-viewer`) oraz pliki `*-TEST.lua`.
- **[F]** `input_uosc.conf`: `r` / `Shift+R` → `script-message rotate-video` (obsługuje go `image-positioning.lua:275`), `Ctrl+s` → `script-binding uosc/shot`. Komendy `shot` **nie ma w upstream uosc 5.13.0**: pełna lista `bind_command` w `src/uosc/main.lua` jej nie zawiera. Po przejściu na upstream ten skrót trzeba przepiąć na `screenshot`.
- **[F]** `mpv.conf`: `osc = no`, `input-builtin-bindings = no`, `save-position-on-quit = yes`, `watch-later-options = start,vid,aid,sid` (bez `speed`), `alang = pl,…`, `slang = pl,…`, `input-ipc-server = mpvpipe`.
- **[F, poza zakresem R5, dla R‑jakość]** `profiles.conf` `[vsync_auto]`: `profile-cond = p.display_fps>122 or …` → `interpolation = no`, `video-sync = audio`. Przy monitorze 170 Hz warunek jest zawsze spełniony, więc ten profil prawdopodobnie zawsze wyłącza `interpolation` z `mpv.conf` **[W]**. Opisy profili są po chińsku.

## 3. Decyzja UI

**Rekomendacja: upstream uosc, skonfigurowany jako minimalistyczny HUD.** Pełny, klasyczny OSC nie jest potrzebny.

Uzasadnienie:

1. **Aktywność i licencja [F]:** `tomasklaen/uosc` ma 3479 ★, LGPL‑2.1, ostatni commit 2026-10-16 i wydanie 5.13.0 z 2026-08-03. Wymaga mpv ≥ 0.33.
2. **Polski bez forka [F]:** `src/uosc/intl/pl.json` jest w repo od 2025-06-13 (commit „feat(i18n): added Polish translation (#1129)”). Moje porównanie kluczy `t('…')` w źródle z `pl.json` daje 105 z 107 przetłumaczonych; brakuje tylko `Shuffle ON` i `Shuffle OFF`. Opcja `languages` przyjmuje też ścieżkę do własnego pliku `.json` (`lib/intl.lua`, gałąź `lang:match('.json$')`), więc poprawki tłumaczeń mieszczą się w `script-opts` i nie wymagają forka. Menu kontekstowe uosc buduje z komentarzy `#!` w pliku z `input-conf` (`lib/menus.lua:579`), czyli z tego samego mechanizmu, którego właściciel już używa, i z polskimi tekstami.
3. **Pokrywa wymagania właściciela jednym komponentem [F]:** usuwanie pliku z przejściem dalej, opcjonalnie do Kosza (`delete-file-next/prev/quit`, `use_trash`); wyszukiwalne menu ścieżek, playlisty i rozdziałów; `paste-to-open` / `paste-to-playlist`; `stream-quality`; `download-subtitles` (OpenSubtitles); `keybinds` jako paleta skrótów; `update` (samoaktualizacja); `chapter_ranges` do oznaczania czołówek i napisów końcowych na osi czasu; obsługa thumbfast.
4. **„Kropka/HUD” jest konfiguracją uosc, nie osobnym projektem [F, opcje z `src/uosc.conf`]:** `progress=always` z `progress_size=2` (cienka linia postępu zawsze widoczna albo `windowed`), `timeline_persistency=paused`, `top_bar=never` albo `no-border`, `controls=` ograniczone do kilku przycisków, `pause_indicator=flash`, `volume=none` oraz `flash-elements speed,volume` przy skrótach, żeby zmiana prędkości czy głośności błysnęła tylko na chwilę. Interfejs pojawia się dopiero, gdy kursor zbliży się do krawędzi (`proximity_in` / `proximity_out`). **[W]** To jest „HUD jak w grach”, o który chodzi właścicielowi; własny HUD w Lua byłby nowym kodem do utrzymania bez przewagi.
5. **„OSC z PlayKit” to też uosc [F]:** `hooke007/mpv_PlayKit` (7761 ★, ostatni commit 2026-10-28) używa forka uosc 5.12.1 z chińskim `lib/lang` (`ulang._cm_*`) i własnego `thumb_engine`. Licencja to `NOASSERTION`, a README mówi wprost, że niewymienione pliki są „UNLICENSED”. Branie forka z PlayKit dałoby starszą wersję uosc, chińskie teksty do podmiany i niejasną licencję.

**Alternatywa:** ModernZ (klasyczny pasek, ma polski plik locale i obsługuje thumbfast), jeśli właściciel woli stale widoczny, „filmowy” pasek zamiast interfejsu na zbliżenie. Wersji pośredniej nie rekomenduję.

**Menu natywne Windows:** w mpv master od 2026-01-25 istnieje natywne menu kontekstowe Win32 z plikiem `menu.conf` (`DOCS/man/context_menu.rst`, commity `menu.conf: add this file`, `win32/menu: …`). **[F]** Nie ma go w stabilnym 0.41.0: master jest 1373 commity przed `v0.41.0`, a 0.42 jeszcze nie wyszło. **[W]** Na razie zostaje menu uosc; temat wraca po wydaniu 0.42.

## 4. Katalog według grup

Kolumny: ★ = gwiazdki; „Ost.” = data ostatniego commita na gałęzi domyślnej; „Rel.” = ostatnie wydanie.

### 4.1 UI, OSC i miniatury

| Pozycja | ★ / licencja | Ost. / Rel. | Co robi | Jakość, ryzyko | Rek. |
|---|---|---|---|---|---|
| [tomasklaen/uosc](https://github.com/tomasklaen/uosc) | 3479 / LGPL‑2.1 | 2026-10-16 / 5.13.0 (2026-08-03) | interfejs na zbliżenie, menu, Kosz, schowek, napisy z OpenSubtitles, `pl.json` | najaktywniejszy; własny helper `ziggy` (Go) tylko jako zapas dla schowka i napisów | **bierzemy** |
| [po5/thumbfast](https://github.com/po5/thumbfast) | 1752 / MPL‑2.0 | 2026-06-28 / brak | miniatury na osi czasu dla uosc, ModernZ i innych | standard; opcje `hwdec`, `network`, `direct_io` (Windows) | **bierzemy** |
| [Samillion/ModernZ](https://github.com/Samillion/ModernZ) | 1332 / LGPL‑2.1 | 2026-06-04 / v0.3.3 (2026-05-20) | nowoczesny klasyczny OSC; `extras/locale/modernz-locale.json` ma `pl` | dobry, rzadsze commity niż uosc | **może** (alternatywa) |
| wbudowany `osc.lua` | mpv | 0.40: układy `slimbottombar`/`slimtopbar`, własne przyciski, menu po prawym kliku | zerowy koszt | brak i18n; miniatury tylko z łatanym `osc.lua` z gałęzi thumbfast | **nie** (tylko awaryjnie) |
| [SCEPTICG/hikari-mpv](https://github.com/SCEPTICG/hikari-mpv) | 42 / MIT | 2026-10-30 / v0.11.1 | motyw i skrypty **na upstream uosc** (nie fork): polski, przycisk „pomiń czołówkę” (rozdziały + AniSkip), „kontynuuj oglądanie”, automatyczne Anime4K | repo założone 2026-10-06, więc ma 3 tygodnie; funkcje bardzo zbieżne z potrzebami | **może** (źródło pomysłów, nie zależność) |
| [hooke007/mpv_PlayKit](https://github.com/hooke007/mpv_PlayKit) | 7761 / NOASSERTION | 2026-10-28 / 20260510 | paczka: fork uosc 5.12.1 (chiński), `thumb_engine`, `input_plus.lua` (np. `speed_auto`, `seek_acc`, `chap_skip_toggle`), shadery, VS | aktywny; licencja niejasna; teksty po chińsku | **nie** jako baza; **może** jako źródło profili i shaderów (dla R‑jakość) |
| [zydezu/ModernX](https://github.com/zydezu/ModernX) | 305 / brak | 2026-10-25 / v0.4.8 | fork ModernX: opis i komentarze YouTube | brak licencji; `language = "en"` z dopiskiem „.json translations need implementing” | **nie** |
| [cyl0/ModernX](https://github.com/cyl0/ModernX) | 770 / brak | 2026-02-04 / 0.6.1 (2024-04) | oryginał ModernX | brak licencji, wyprzedzony przez ModernZ | **nie** |
| [brahmkshatriya/material-osc](https://github.com/brahmkshatriya/material-osc) | 177 / brak | 2026-10-30 / 0.0.13 | OSC w stylu Material | brak licencji, wersja 0.0.x | **nie** |

### 4.2 Pliki i biblioteka

| Pozycja | ★ / licencja | Ost. / Rel. | Co robi | Jakość, ryzyko | Rek. |
|---|---|---|---|---|---|
| uosc `delete-file-next/prev/quit` + `use_trash=yes` | uosc | jw. | usuwa bieżący plik i przechodzi dalej; na Windows z `use_trash` przez PowerShell `Microsoft.VisualBasic.FileIO.FileSystem::DeleteFile(…, 'SendToRecycleBin')` (`lib/utils.lua:629–660`) | **[F]** bez `use_trash` wykonuje `cmd /C del`, czyli usuwa trwale; domyślnie `use_trash=no`, więc trzeba ustawić `yes` | **bierzemy** |
| [zenyd/mpv-scripts](https://github.com/zenyd/mpv-scripts) `delete_file.lua` | 192 / GPL‑3.0 | 2025-12-06 | oznacza pliki i usuwa je przy wyjściu albo przenosi do katalogu | sensowny, gdy usuwanie ma być odroczone | **może** (tylko gdy właściciel chce „zaznacz, usuń na końcu”) |
| [stax76/mpv-scripts](https://github.com/stax76/mpv-scripts) `delete_current_file.lua` | 233 / GPL‑2.0 | 2025-11-26 | usuwa bieżący plik | dubluje uosc | **nie** |
| `--autocreate-playlist=filter` (mpv 0.39) | mpv | — | buduje playlistę z katalogu otwartego pliku, wg `--directory-filter-types` | natywny następca `autoload.lua` (release notes 0.39) | **bierzemy** |
| `save-position-on-quit` + `watch-later-options` | mpv | — | wznawianie pozycji i ścieżek | już włączone; `speed` nie jest dziś zapisywane | **bierzemy** (jest) |
| `--save-watch-history` + `select/select-watch-history` (mpv 0.40) | mpv | — | historia odtwarzania, domyślnie pod `g-h` | wbudowane; dokumentacja ostrzega przed prywatnością | **bierzemy** |
| [natural-harmonia-gropius/recent-menu](https://github.com/natural-harmonia-gropius/recent-menu) | 47 / MIT | 2025-03-20 (push 2026-07-26) / v1.3 | menu „ostatnio odtwarzane” w uosc | ostatni commit 19 mies. temu, tuż za progiem | **może** (gdy wbudowana historia nie wystarczy) |
| [Eisa01/mpv-scripts](https://github.com/Eisa01/mpv-scripts) `SimpleHistory` | 843 / BSD‑2 | 2025-06-21 | historia z wznawianiem | dubluje wbudowane | **nie** |
| uosc `next`/`prev`, `next-file`/`prev-file`, `open-file` | uosc | jw. | następny odcinek, przeglądarka plików | wystarczy z `autocreate-playlist` i `keep-open` | **bierzemy** |
| [CogentRedTester/mpv-file-browser](https://github.com/CogentRedTester/mpv-file-browser) | 331 / MIT | 2026-10-22 | pełniejsza przeglądarka plików | aktywna; dubluje `uosc/open-file` | **może** |
| [jonniek/mpv-playlistmanager](https://github.com/jonniek/mpv-playlistmanager) | 705 / Unlicense | 2026-03-16 | zarządzanie playlistą | dubluje menu playlisty uosc | **nie** |

### 4.3 Napisy i audio

| Pozycja | ★ / licencja | Ost. / Rel. | Co robi | Jakość, ryzyko | Rek. |
|---|---|---|---|---|---|
| `alang`/`slang`, `subs-with-matching-audio`, `subs-fallback`, `watch-later-options=aid,sid` | mpv | — | wybór ścieżek po języku i pamięć wyboru per plik | już ustawione; **[F]** `subs-with-matching-audio` ma domyślnie `yes`, więc przy polskim lektorze mpv włączy też polskie napisy | **bierzemy** (jest) |
| [CogentRedTester/mpv-sub-select](https://github.com/CogentRedTester/mpv-sub-select) | 135 / MIT | 2025-04-04 | warunkowy wybór napisów | poza progiem; opcje natywne wystarczają, bo AniShift sam nadaje język i nazwy ścieżek | **nie** |
| [joaquintorres/autosubsync-mpv](https://github.com/joaquintorres/autosubsync-mpv) (lustro: Ajatt-Tools) | 194 / MIT | 2026-05-17 | synchronizacja napisów przez ffsubsync lub alass | zewnętrzne zależności Pythona; dotyczy tylko plików spoza AniShift | **może** (na żądanie, nie domyślnie) |
| uosc `download-subtitles` | uosc | jw. | wyszukiwanie i pobieranie z OpenSubtitles | wbudowane w UI, uruchamiane ręcznie | **może** (pliki spoza AniShift) |
| [davidde/mpv-autosub](https://github.com/davidde/mpv-autosub) | 382 / MIT | 2021-06-29 | automatyczne pobieranie napisów (subliminal) | porzucony | **nie** |
| [Eisa01 `SmartSkip`](https://github.com/Eisa01/mpv-scripts) | 843 / BSD‑2 | 2025-06-21 | pomija czołówkę, intro, napisy końcowe i zapowiedź (po rozdziałach albo do wykrytej ciszy); `smart-next`: cisza → następny rozdział → następny plik | w progu; nawigacja częściowo dubluje uosc |  **może** |
| [ferreum/mpv-skipsilence](https://github.com/ferreum/mpv-skipsilence) | 77 / GPL‑2.0 | 2025-09-06 | przyspiesza ciszę ponad bieżącą prędkość | **[W]** w anime muzyka tła ogranicza zysk; do testu przy 2× | **może** |
| [zenyd `speed-transition.lua`](https://github.com/zenyd/mpv-scripts) | 192 / GPL‑3.0 | 2025-12-06 | przyspiesza, gdy dłużej nie ma napisów | **[W]** z lektorem AniShift przerwa bez napisów to też przerwa bez lektora, więc pasuje do 2×; do testu | **może** |

### 4.4 Internet

| Pozycja | ★ / licencja | Ost. / Rel. | Co robi | Jakość, ryzyko | Rek. |
|---|---|---|---|---|---|
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) + wbudowany `ytdl_hook` | 203 985 / Unlicense | 2026-10-29 / 2026.10.26 | odtwarzanie linków | **[F]** lokalny `yt-dlp.exe` jest z 2026-07-16, więc wymaga mechanizmu aktualizacji (temat innego researchera) | **bierzemy** |
| właściwość `clipboard` (mpv 0.40) + `uosc/paste-to-open` | mpv + uosc | — | wklej link lub ścieżkę i odtwórz; uosc czyta najpierw `clipboard/text`, a `ziggy` służy tylko jako zapas (`lib/utils.lua:929`) | natywne; zastępuje SmartCopyPaste | **bierzemy** |
| [Eisa01 `SmartCopyPaste`](https://github.com/Eisa01/mpv-scripts) | 843 / BSD‑2 | 2025-06-21 | kopiuj/wklej z historią | dubluje natywne funkcje | **nie** |
| uosc `stream-quality` | uosc | jw. | wybór wysokości (4320…144) | wystarczy do typowych przypadków | **bierzemy** |
| [christoph-heinrich/mpv-quality-menu](https://github.com/christoph-heinrich/mpv-quality-menu) | 242 / GPL‑2.0 | 2026-01-30 / v4.2.1 | menu konkretnych formatów audio i wideo | aktywny, integruje się z uosc | **może** |
| [jouni/mpv_sponsorblock_minimal](https://codeberg.org/jouni/mpv_sponsorblock_minimal) (Codeberg) | 46 / ? | 2025-12-21 | pomijanie segmentów SponsorBlock | aktywny (API Codeberg); licencji nie odczytałem | **bierzemy**, jeśli właściciel ogląda YouTube |
| [po5/mpv_sponsorblock](https://github.com/po5/mpv_sponsorblock) | 639 / GPL‑3.0 | 2023-01-30 | jw. | porzucony | **nie** |
| [cvzi/mpv-youtube-upnext](https://github.com/cvzi/mpv-youtube-upnext) | 80 / NOASSERTION | 2026-07-20 / v1.1 | „następny” i polecane z YouTube | aktywny | **może** |
| [BanchouBoo/mpv-youtube-chat](https://github.com/BanchouBoo/mpv-youtube-chat) | 59 / MIT | 2026-09-26 | nakładka czatu (yt-dlp) | aktywny, niszowy | **może** |
| komentarze YouTube | — | — | nie znalazłem utrzymywanego skryptu mpv z licencją; ma je tylko zydezu/ModernX bez licencji | luka | **nie** (brak kandydata) |
| [bitingsock/ytdl-preload](https://github.com/bitingsock/ytdl-preload) | 20 / brak | 2026-05-04 | pobiera z wyprzedzeniem następny link z playlisty | brak licencji, niszowy | **nie** |

### 4.5 Śledzenie oglądania

| Pozycja | ★ / licencja | Ost. / Rel. | Co robi | Jak rozpoznaje tytuł i odcinek | Rek. |
|---|---|---|---|---|---|
| [AzuredBlue/mpv-anilist-updater](https://github.com/AzuredBlue/mpv-anilist-updater) | 41 / MIT | 2026-10-22 | **tylko AniList**; aktualizuje postęp przy 85%, kolejkuje offline, `c` otwiera menu korekty | parsowanie nazwy pliku (`anilist_updater/parsing.py`) + wyszukiwanie w AniList; wymaga Pythona ≥ 3.11 i tokena; domyślnie aktualizuje tylko pozycje „watching/planning/rewatching” | **może** (tylko po przejściu na AniList) |
| [erengy/taiga](https://github.com/erengy/taiga) | 2339 / GPL‑3.0 | develop 2026-09-27 (przepisywanie), master/rel. v1.4.1 2024-03-21 | aplikacja Windows: MAL, AniList, Kitsu | wykrywa odtwarzacz po tytule okna (Anisthesia), parsuje nazwę pliku (Anitomy) | **może** (zastępczo, bez kodu; **[?]** działania z MAL dziś nie sprawdziłem) |
| [iamkroot/trakt-scrobbler](https://github.com/iamkroot/trakt-scrobbler) | 556 / GPL‑2.0 | 2026-10-30 | Trakt dla mpv przez IPC | Trakt, nie MAL | **nie** |
| [goodtrailer/mpv-rich-presence](https://github.com/goodtrailer/mpv-rich-presence) | 18 / AGPL‑3.0 | 2026-03-12 | Discord Rich Presence | proste; AGPL | **może** (opcjonalnie) |
| tnychn/mpv-discord, cniw/mpv-discordRPC, LiTO773/trakt-mpv | — | zarchiwizowane albo 2022 | — | — | **nie** |
| **AniShift jako księgowy** | — | — | odtwarzacz zgłasza „plik X obejrzany ≥ N%”, AniShift mapuje plik na tytuł i odcinek i aktualizuje MAL | AniShift zna tożsamość z katalogu AniList i przypisań odcinków (`anishift/application/control.py` `EpisodeAssignment`, `anishift/services/catalog/anilist.py`) | **bierzemy** (kierunek; szczegóły w §5) |

**[F]** Nie znalazłem utrzymywanego skryptu mpv dla **MAL** (wyszukiwania GitHub: „myanimelist updater mpv”, „mal-updater”, „anime tracker mpv”, wyszukiwanie kodu `myanimelist.net/v2 language:Lua`). To brak trafień w tych zapytaniach, a nie dowód, że taki skrypt nie istnieje.

### 4.6 Sterowanie

| Pozycja | Źródło | Co robi | Uwagi | Rek. |
|---|---|---|---|---|
| prędkość | mpv `speed`, `add speed`, `set speed`; uosc `flash-elements speed` | obecne skróty `[`, `]`, `BS`, `\` zostają | `speed` nie jest w `watch-later-options`; domyślne 2× to jedna linia `speed = 2` w `mpv.conf` (pytanie do właściciela) | **bierzemy** |
| rotacja | mpv `video-rotate` (0–359, `no`) | `cycle-values video-rotate 90 180 270 0` zastępuje `script-message rotate-video` z `image-positioning.lua` | **[F]** przy hwdec bez copy-back działają tylko kroki co 90° (`options.rst`) | **bierzemy** |
| zoom i przesuwanie | wbudowany `positioning.lua` (0.40): `drag-to-pan`, `cursor-centric-zoom`, `align-to-cursor`, `pan-x`, `pan-y` | zastępuje `image-positioning.lua` dla wideo | `align-border` nie ma odpowiednika; wystarczy `set video-align-x/-y` | **bierzemy** |
| [occivink/mpv-image-viewer](https://github.com/occivink/mpv-image-viewer) (minimap, ruler, freeze-window, detect-image) | 367 ★, Unlicense, 2024-11-23 | dodatki do przeglądania obrazów | poza progiem; potrzebne tylko do obrazów i mangi | **nie** dla wideo; **może** dla obrazów |
| zrzuty ekranu | mpv `screenshot`, `screenshot video` | `Ctrl+s` trzeba przepiąć z `uosc/shot` (fork) | szablon i format już są w `mpv.conf` | **bierzemy** |
| pętla A‑B | mpv `ab-loop` | jest pod `l` | — | **bierzemy** |
| menu kontekstowe | uosc `menu` z komentarzy `#!` | polskie, wyszukiwalne | natywne Win32 `menu.conf` dopiero w master | **bierzemy** (uosc) |
| [tsl0922/mpv-menu-plugin](https://github.com/tsl0922/mpv-menu-plugin) | 206 ★, GPL‑2.0, 2025-01-15 | natywne menu jako plugin C | poza progiem; zastępuje je natywne menu w master | **nie** |
| paleta komend | `select/menu`, `select/select-binding`, `commands.lua` (mpv 0.40+), `uosc/keybinds` | wyszukiwalna lista skrótów i akcji | interfejs `select.lua` jest po angielsku | **bierzemy** |
| [stax76 `command_palette.lua`](https://github.com/stax76/mpv-scripts) | 233 ★, 2025-11-26 | paleta komend | **[F]** README autora: „this script is now obsolete”, bo select.lua w 0.40 robi to samo | **nie** |
| profile jakości pod klawiszem | mpv `apply-profile`, `cycle-values profile …`, profile warunkowe | przełączanie pakietów shaderów i filtrów jednym klawiszem | zastępuje osobne `change-list glsl-shaders toggle` dla każdego shadera | **bierzemy** |
| [occivink/mpv-scripts](https://github.com/occivink/mpv-scripts) (seek-to, crop, encode) | 492 ★, Unlicense, 2025-11-01 | skok do czasu, wycinanie klipów | aktywne | **może** |
| `save_global_props.lua` (zenwarr / PlayKit) | PlayKit 2026-10-28 | pamięta globalnie głośność i shadery | mpv tego nie ma; wersja z PlayKit jest utrzymywana | **może** (zostawić, jeśli właściciel chce globalnej pamięci) |

### 4.7 Statystyki i diagnostyka

| Pozycja | Co daje | Rek. |
|---|---|---|
| wbudowany `stats.lua` | strona 1: klatki zrzucone i opóźnione, vsync i jitter (wykres po przełączeniu); strona 2: czasy renderowania shaderów; strona 5: ścieżki; `display-page-N` pod klawisz (`DOCS/man/stats.rst`) | **bierzemy** |
| właściwości `frame-drop-count`, `decoder-frame-drop-count`, `mistimed-frame-count`, `vo-delayed-frame-count`, `vsync-ratio` | **[F]** istnieją (`input.rst`); można je pokazać w krótkiej nakładce przez `show-text` przy ciężkiej interpolacji | **bierzemy** (jako skrót, bez skryptu) |
| PlayKit `stats_mediainfo.lua` | dodatkowa strona z MediaInfo; wymaga MediaInfo CLI, komentarze po chińsku | **może** |

### 4.8 Język interfejsu

| Element | Jak dać polski | Stan |
|---|---|---|
| uosc | `languages=slang,en` (`slang` zaczyna się od `pl`) albo `languages=~~/script-opts/uosc-pl.json,pl,en` z własnymi poprawkami | **[F]** 105/107 kluczy, brak „Shuffle ON/OFF” |
| menu uosc | teksty z komentarzy `#!` w `input.conf` | już po polsku |
| ModernZ (gdyby wybrany) | `language=pl` + `modernz-locale.json` | **[F]** jest `pl` |
| komunikaty OSD mpv („Speed: 2.00x” itp.), `select.lua`, `console`, `stats` | **[F]** mpv nie ma mechanizmu tłumaczeń (brak i18n w `DOCS/man`); polskie komunikaty tylko przez `no-osd …; show-text "Prędkość: ${speed}×"` w skrótach | język interfejsu wbudowanych menu zostaje angielski |
| natywne menu (mpv master) | teksty w `menu.conf` definiuje użytkownik | dopiero po 0.42 |
| chińskie teksty | upstream uosc nie ma ich na sztywno; do wymiany są opisy `profile-desc` w `profiles.conf`; z PlayKit nic chińskiego nie trzeba brać | — |

## 5. Granica odtwarzacz / AniShift: ocena zasady

**Zasada „odtwarzacz odtwarza, AniShift edytuje” jest trafna jako reguła domyślna. Uzupełniłbym ją o drugą połowę: „odtwarzacz zgłasza zdarzenia, AniShift prowadzi stan”.**

Co przemawia za zasadą:

- **Wygląd napisów [W]:** AniShift tworzy cały plik `.pl.ass` ze stylami. Jeśli dobierze w nim rozmiar i grubość, wynik wygląda tak samo w każdym odtwarzaczu i w PlayShift nie ma heurystyk do utrzymania. W odtwarzaczu zostaje to, co zależy od chwili i ekranu: globalne `sub-scale` pod klawiszem (np. oglądanie z daleka), `sub-use-margins`, oraz **`blend-subtitles`**, które według `options.rst` wpływa na interpolację i jej wydajność (ciężkie filtry VS, 170 Hz). To ostatnie należy wyłącznie do odtwarzacza.
- **Wybór ścieżek [F]:** AniShift ustawia język `pol` i nazwę każdej dodanej ścieżce, ale z flagą domyślną `no` (`anishift/services/composition/commands.py`, `_appended_track_arguments`). mpv i tak wybiera polskie audio i napisy dzięki `alang`/`slang`, więc skrypt typu sub-select jest zbędny. Pomysł z `docs/ideas.md` („lektor od razu w odtwarzaczu”) w mpv działa już z samej konfiguracji; flaga domyślna ma znaczenie tylko dla innych odtwarzaczy.
- **Synchronizacja i pobieranie napisów:** dla plików z AniShift nie są potrzebne. `autosubsync` i `download-subtitles` służą tylko plikom spoza AniShift (linki, cudze MKV) i uruchamia się je ręcznie.

**Śledzenie MAL: porównanie dróg.**

| Kryterium | skrypt mpv (np. anilist-updater) | Taiga | AniShift jako księgowy |
|---|---|---|---|
| MAL (konto właściciela) | **nie** (tylko AniList) | tak | tak, do zbudowania |
| pewność tytułu i odcinka | zgadywanie z nazwy pliku + ręczna korekta | zgadywanie z tytułu okna i nazwy pliku | **znana** dla plików z AniShift (katalog AniList + przypisanie odcinka) |
| numeracja właściciela („licznik MAL = następny odcinek”) | nie zna | nie zna | może ją uwzględnić, bo subskrypcje już z niej korzystają |
| koszt | instalacja + token | instalacja i stały proces w tle | mały skrypt Lua + moduł w AniShift |
| pliki spoza AniShift (linki, cudze MKV) | tak, z błędami | tak, z błędami | tylko po ręcznym wskazaniu tytułu |

**Rekomendowany podział [W]:**

1. Odtwarzacz emituje jedno zdarzenie: krótki skrypt Lua obserwuje `percent-pos` i `end-file` i po przekroczeniu progu dopisuje linię „ścieżka, czas, procent” do pliku zdarzeń. Działa także wtedy, gdy AniShift jest wyłączony. Jest też alternatywa: rezydent AniShift podłącza się do istniejącego `input-ipc-server = mpvpipe`. **[?]** Czy potok IPC mpv na Windows przyjmuje kilku klientów naraz (uosc i inne skrypty tego nie potrzebują), nie sprawdziłem.
2. AniShift mapuje plik na tytuł i odcinek. Mapowanie przetrwa przenoszenie plików, jeśli AniShift zapisze tożsamość w samym MKV, np. jako globalne tagi (AniList ID, numer odcinka). mpv udostępnia tagi kontenera we właściwości `metadata`, więc skrypt zgłosi ID bez zgadywania. **[F]** Dziś AniShift nie zapisuje takich tagów; w `services/composition` nie ma `global-tags` ani `--title`.
3. AniShift aktualizuje MAL. **[F]** AniShift nie pobiera dziś `idMal` (w `anishift/` brak wystąpień `idMal`/`mal_id`). Uwierzytelnienie i API MAL wykraczają poza zakres R5.

Kompromis: dla plików spoza AniShift ta droga wymaga ręcznego wskazania tytułu. Bez kodu to luka pokrywa Taiga, jeśli przejdzie test.

## 6. Odrzucone, z powodem

| Projekt | Powód |
|---|---|
| fork uosc 5.0.0 z MPV_lazy (obecny) | 13 wydań za upstream; repo źródłowe zarchiwizowane 2025-09-06; upstream ma już polski |
| fork uosc z PlayKit (5.12.1) | chińskie teksty, licencja `NOASSERTION`/„UNLICENSED”, starszy niż upstream |
| Zren/mpv-osc-tethys | ostatni commit 2024-04-30, brak licencji |
| maoiscat/mpv-osc-modern | ostatni commit 2024-01-22 |
| TheAMM/mpv_thumbnail_script, marzzzello fork | 2020-01-16 i 2024-05-18; thumbfast je zastępuje |
| tsl0922/mpv-menu-plugin | 2025-01-15; natywne menu w mpv master |
| stax76 `command_palette.lua` | autor sam uznał go za przestarzały wobec `select.lua` |
| po5/memo, hacel/recent | 2024-09-03 i 2024-10-14; zastępuje je `select-watch-history` |
| jonniek/mpv-nextfile | 2023-08-09; zastępuje go `autocreate-playlist` z uosc `next` |
| po5/mpv_sponsorblock | 2023-01-30; jest utrzymywana wersja minimal |
| po5/evafast, po5/chapterskip | 2022; mają następców (uosc, SmartSkip) |
| davidde/mpv-autosub | 2021-06-29 |
| CogentRedTester/mpv-sub-select | 2025-04-04 (19 mies.), a opcje natywne wystarczają |
| Eisa01 `SmartCopyPaste` | zastępuje go natywna właściwość `clipboard` z uosc `paste-to-open` |
| `image-positioning.lua` (dla wideo) | zastępuje go wbudowany `positioning.lua` oraz `video-rotate` |
| cyl0/zydezu ModernX, material-osc | brak licencji |
| tnychn/mpv-discord, LiTO773/trakt-mpv | zarchiwizowane |
| cniw/mpv-discordRPC, noaione/mpv-discordRPC | 2022 i 2023 |
| ytdl-preload | brak licencji, niszowy |

## 7. Pytania do właściciela

1. **Wygląd:** interfejs na zbliżenie z cienką linią postępu (uosc, rekomendacja) czy stale widoczny klasyczny pasek (ModernZ)?
2. **Usuwanie:** zawsze do Kosza (`use_trash=yes`) z przejściem do następnego odcinka? Czy „zaznacz teraz, usuń przy wyjściu”?
3. **Prędkość:** domyślnie 2× przy każdym uruchomieniu (`speed = 2`)? Czy prędkość ma być pamiętana per plik?
4. **Polski lektor i napisy razem:** mpv domyślnie włączy oba (`subs-with-matching-audio=yes`). Tak ma zostać?
5. **MAL:** zgoda na kierunek „odtwarzacz zgłasza, AniShift aktualizuje MAL” i na zapis AniList ID w tagach MKV? Czy najpierw test Taigi jako rozwiązania bez kodu?
6. **YouTube i strumienie:** jak często? Od tego zależą SponsorBlock, quality-menu, upnext i czat (dziś „może”).
7. **Przyspieszanie przerw:** test `skipsilence` albo `speed-transition` przy 2×?
8. **Przeglądanie obrazów i mangi:** ma zostać w PlayShift (`minimap`, `ruler`, `manga-reader`)? Czy to osobny temat?

## 8. Metoda i źródła

- Metadane repozytoriów: `gh api repos/<owner>/<repo>`, `…/commits?per_page=1`, `…/releases?per_page=1` (2026-10-31); wyszukiwania `gh api search/repositories` i `search/code` z zapytaniami podanymi w §4.5.
- Kod uosc: płytki klon `tomasklaen/uosc` z 2026-10-16 (`src/uosc/lib/utils.lua`, `lib/intl.lua`, `lib/menus.lua`, `main.lua`, `uosc.conf`, `intl/pl.json`).
- mpv: release notes v0.39.0, v0.40.0 i v0.41.0 (`gh api …/releases/tags/…`); rzadki klon master z 2026-10-30 (`DOCS/man/options.rst`, `input.rst`, `stats.rst`, `context_menu.rst`, `player/lua/*.lua`, `etc/input.conf`); `DOCS/interface-changes/`; historia commitów `DOCS/man/context_menu.rst`; `compare/v0.41.0...master`.
- PlayKit: `gh api …/contents` (skrypty, `script-opts`, `mpv.conf`, `LICENSE.MD`, `input_plus.lua`).
- Codeberg: API `repos/jouni/mpv_sponsorblock_minimal` i `/commits`.
- Lokalnie (tylko odczyt): `C:\Users\MattyMroz\Videos\mpv\portable_config\` (`mpv.conf`, `input_uosc.conf`, `profiles.conf`, `script-opts.conf`, `scripts/`), `VersionInfo` pliku `mpv.exe`; AniShift: `anishift/services/composition/commands.py`, `anishift/application/control.py`, `docs/ideas.md`.
- Nie sprawdzałem: działania Taigi z MAL, wielu klientów IPC mpv na Windows, licencji `mpv_sponsorblock_minimal`, jakości działania skryptów „może” (niczego nie instalowałem ani nie uruchamiałem).
