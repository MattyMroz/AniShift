# TODO — różnice AniShift vs MangaShift (do przemyślenia / wyrównania)

> Notatka robocza: gdzie AniShift świadomie różni się od MangaShift, co jest długiem,
> co warto wyrównać w którymś kierunku. Nie jest to plan — to lista do decyzji.

## Pobieranie binarek — mechanizm

Rdzeń mechanizmu jest **ten sam** w obu projektach (httpx stream + rozpakowanie zip
przez `zipfile` + punkt wejścia `ensure_binary()`). Różnice:

| Aspekt | MangaShift (`runtime/llama/binary_resolver.py`) | AniShift (`setup/installer.py`) | Uwaga |
|---|---|---|---|
| **Weryfikacja SHA256** | ❌ BRAK — ufa pobranemu plikowi | ✅ hash sprawdzany przed instalacją | AniShift bezpieczniejszy. **MangaShift ma tu lukę — warto tam dodać hash.** |
| **Źródło wersji** | GitHub API `latest` (ruchomy tag) | datowany, niezmienny URL + pinowany hash | AniShift powtarzalny; MangaShift bierze zawsze najnowszy build |
| **Gdzie URL/hash** | stałe `Final` w Pythonie (`_RELEASE_DOWNLOAD_BASE`) | JSON (`external/bin_hashes.json`) | Różnica formatu — patrz niżej |
| **chmod +x na Unix** | ✅ `binary_path.chmod(... 0o755)` | ❌ brak (AniShift Windows-only na razie) | Jeśli AniShift dostanie Linux — trzeba dodać chmod |
| **path-traversal guard** | ✅ walidacja przy zip/tar extract | ✅ `is_relative_to` przy extract | oba mają |

## JSON vs Python dla manifestu zasobów — obraz sprostowany

Wcześniej myślałem, że MangaShift trzyma wszystko w Pythonie. NIEPRAWDA — MangaShift
robi **hybrydę**:
- `models/catalog.py` (Python) — STRUKTURA + logika (formaty pt/onnx/gguf, HF repo,
  przepisywanie ścieżek). Deklaruje też `sha256` na `_file(...)`.
- `external/model_hashes.json` (JSON, 54 KB, 123 pliki) — HASHE + rozmiary, **generowany
  skryptem** przy publikacji na HF (`schema_version`, `generated_at`, per-plik sha256).
- Binarki (llama-server) — stałe `Final` w `runtime/llama/binary_resolver.py`, bez hasha.

Czyli MangaShift ma JSON dla danych generowanych maszynowo (hashe) + Python dla struktury.
To ta sama hybryda, którą eksperci nazwali "najlepszą". AniShift `bin_hashes.json` jest
odpowiednikiem `model_hashes.json` — więc JSON dla hashy JEST spójny z MangaShift, nie
łamie standardu.

## DUŻY DŁUG MangaShift: hash w DWÓCH miejscach (catalog.py + JSON)

`runtime/checksum.py` (linie ~176-187) wprost przyznaje: hash modelu jest ORAZ w
`catalog.py` (`_file(sha256=...)`) ORAZ w `model_hashes.json`. Kod:
- ma regułę pierwszeństwa: **"catalog wins; manifest is a fallback"**, *"prefer the
  catalog whenever possible"*,
- ostrzega że mogą się **rozjechać**: *"the manifest's main_sha256 may disagree with
  the catalog's"*.

To jest **duplikacja / brak SSOT dla hasha** — objaw: reguła kto-wygrywa + ryzyko
rozjazdu. **AniShift robi to LEPIEJ:** hash w JEDNYM miejscu (`bin_hashes.json`), nie
duplikowany w kodzie. To jest "słabe (u MangaShift) rób lepiej (u nas)".
**TODO MangaShift:** zredukować hash do jednego źródła (generowany JSON = SSOT,
catalog nie deklaruje sha256 osobno). Nie ruszać teraz — zamrożone, notatka na później.

## TODO MangaShift: binarki bez weryfikacji hashem

`binary_resolver.py` pobiera binarki (llama-server) z GitHub `latest` BEZ sprawdzania
SHA256 — ufa pobranemu plikowi. AniShift weryfikuje hash. **Warto dodać hash do binarek
MangaShift** (dziś luka: uszkodzony/podmieniony plik przejdzie).

## SSOT — duplikacja mapowania binarka→folder/zasób (dług)

Ta sama wiedza (jaki plik należy do jakiego narzędzia/folderu) jest w 3 miejscach:
- `_TOOL_DIR` w `platform/binaries.py` (Binary → folder)
- `_BINARY_RESOURCE` w `setup/installer.py` (Binary → nazwa zasobu)
- `members[].dest` w `bin_hashes.json` (plik → gdzie ląduje)

`_TOOL_DIR` i `_BINARY_RESOURCE` mają identyczne wartości (folder = nazwa zasobu).
**Dług:** wyprowadzić jedno z drugiego / z manifestu, żeby dodanie binarki (balcon
w etapie 6) było zmianą w JEDNYM miejscu. Do zrobienia gdy i tak dotykamy tych map
(np. przy balcon).

---

# DOCELOWA ARCHITEKTURA ZASOBÓW (ultimate — jeden katalog dla binarek + modeli)

> Wzorzec potwierdzony na ollama / HuggingFace / pip / cargo / npm. Ma obsłużyć
> WSZYSTKIE typy zasobów jednym schematem, żeby dodanie nowego typu za rok = wpis
> w JSON + ewentualnie jeden mały fetcher, ZERO przepisywania. Obecny `manifest.py`
> jest już ~80% zgodny — jedyna realna zmiana to wydzielenie `source` jako tagged
> union (zrobić ZANIM dojdzie drugi typ źródła — potem drożej).

## Zasada nadrzędna: rozdziel `kind` od `source.type`

Dwie NIEZALEŻNE osie (nie sklejać):
- **`kind`** (binary / model) → decyduje GDZIE zainstalować (layout).
- **`source.type`** (url / hf / licensed) → decyduje JAK pobrać (który fetcher).

Jeden katalog danych (JSON) + rejestr fetcherów `dict[source_type, Fetcher]`. Jeden
cykl życia dla wszystkiego: `resolve → fetch → verify → materialize → receipt`.
NIE osobne systemy per typ (to gwarancja 3 różnych implementacji retry/weryfikacji).

## 4 typy zasobów = jeden schemat (przykłady wpisów katalogu)

```jsonc
{
  "resources": {
    // 1. Publiczna binarka (ffmpeg, mkvtoolnix)
    "ffmpeg": {
      "kind": "binary",
      "version": "7.1",
      "source": { "type": "url", "url": "https://.../ffmpeg-win64.zip", "archive": "zip" },
      "verify": { "sha256": "ab34...", "size_bytes": 31457280 },
      "install": { "members": [ { "archive_path": "bin/ffmpeg.exe", "dest": "ffmpeg.exe" } ] }
    },
    // 2. Publiczny model HF
    "whisper-large-v3": {
      "kind": "model",
      "source": { "type": "hf", "repo_id": "openai/whisper-large-v3",
                  "revision": "06f233fe...",   // COMMIT HASH, nigdy "main"
                  "allow_patterns": ["*.safetensors", "*.json"] },
      "verify": {}   // integralnosc = pinned revision + etag/LFS-sha HF
    },
    // 3. Gated model HF — roznica to JEDNO pole
    "pyannote-diarization": {
      "kind": "model",
      "source": { "type": "hf", "repo_id": "pyannote/speaker-diarization-3.1",
                  "revision": "84fd2591...",
                  "credential": "ANISHIFT_HF_TOKEN" },   // NAZWA env vara, nie wartosc
      "verify": {}
    },
    // 4. WLASNY prywatny model — katalog NIE zna finalnego URL-a
    "anishift-voice-v1": {
      "kind": "model",
      "version": "1.0.0",
      "source": { "type": "licensed",
                  "license_endpoint": "https://license.anishift.dev/v1/resolve",
                  "artifact": "anishift-voice-v1",
                  "credential": "ANISHIFT_LICENSE_KEY" },
      "verify": { "sha256": "9f1c...", "size_bytes": 734003200 },   // twoj artefakt = hash obowiazkowy
      "install": { "archive": "zip" }
    }
  }
}
```

## Weryfikacja integralności (reguła: kto jest właścicielem artefaktu)

- **url + licensed** (twoje/publiczne pliki) → SHA256 + size_bytes OBOWIĄZKOWO (masz to).
- **hf** → NIE duplikuj hashy per plik. Kotwica = `revision` przypięty do COMMIT hasha
  (HF sam weryfikuje przez etag/LFS-sha). Opcjonalnie `verify.sha256` dla pojedynczego
  krytycznego pliku (.onnx/.gguf) jako pas+szelki (był bug XET #3643 gdzie snapshot
  przepuścił zły blob). Dla wielkich multi-file snapshotów — pin revision wystarcza.

## Prywatny model — BRUTALNA PRAWDA + realne poziomy ochrony

**Fundament: jeśli apka na maszynie usera odczytuje wagi, zdeterminowany user też je
wyciągnie.** To problem DRM, NIE MA rozwiązania software'owego (Adobe/Topaz są
ekstrahowane mimo szyfrowania). Poziomy:

| Poziom | Co DAJE | Czego NIE daje |
|---|---|---|
| Goły URL w apce | nic | wycieka z pierwszym MITM proxy |
| **Token per-user + signed URL czasowy** (S3 presigned / CloudFront, wydawany przez twój serwer licencji) | kontrola dystrybucji: tylko płacący, revoke per user, audyt, wyciek URL bezwartościowy po N min, brak hotlinku | ochrony pliku PO wylądowaniu na dysku |
| + szyfrowanie at-rest (klucz z serwera → RAM) | podnosi próg "skopiuj plik" → "napisz dumper", zatrzymuje 95% przypadkowych | zatrzymania zdeterminowanego |
| TEE / confidential computing | realna ochrona w użyciu | NIEREALNE na konsumenckim Windows |
| **Model za API (wagi nigdy nie schodzą z twojego serwera)** | JEDYNA faktyczna ochrona wag (ElevenLabs, OpenAI) | offline, koszt infry, latencja |

**Decyzja:** model wolno stracić w najgorszym razie → **token + signed URL (poziom B)**,
śpij spokojnie. Model = core biznesu, kradzież = katastrofa → **API, nie wysyłaj wag**.
Nie ma opcji pośredniej która działa — kto ją sprzedaje, sprzedaje teatr.

## Jawne vs tajne

- **Katalog 100% jawny** — nazwy, URL-e, repo_id, revision, hashe, rozmiary. Hash to
  NIE sekret (to zobowiązanie integralności; jawny = audytowalny). Nawet prywatny model:
  katalog trzyma endpoint licencyjny, nie finalny URL → NIE MA czego chronić.
- **Sekrety poza katalogiem** — tokeny/klucze w `.env` + `SecretStr` (pydantic-settings,
  prefix `ANISHIFT_`). Katalog trzyma tylko NAZWĘ poświadczenia (`credential: "ANISHIFT_HF_TOKEN"`).
- **Szyfrowanie katalogu = TEATR** — klucz i tak w apce, każdy `strings`/debugger go wyjmie.
  Płacisz złożonością za zero ochrony. NIE ROBIĆ.

## Kod (raz a dobrze, ~4 małe moduły)

- `manifest.py` — parsowanie + walidacja tagged union `source` (masz, rozszerzyć o `source`).
- `fetchers/` — `Fetcher` protocol `fetch(resource, dest_tmp) -> Path`; impl `url.py`
  (masz w installer), `hf.py` (snapshot_download, lazy import), `licensed.py` (POST z
  kluczem → `{signed_url, expires}` → dalej ta sama ścieżka co url). Rejestr `_FETCHERS`.
- `installer.py` — wspólny cykl: tmp → fetch → verify → atomic move → receipt.
- Stan instalacji: receipt `external/<name>/.installed.json` (name, version/revision,
  hash, data) → odpowiada "czy mam i czy aktualne" BEZ re-hashowania GB przy starcie.
- Sekrety: `Settings` (pydantic-settings), `SecretStr`, rozwiązywane po `credential`
  w momencie fetchu.

**Efekt: nowy typ zasobu = nowy wpis JSON + max jeden plik fetchera. Zero przepisywania.**
Wzorzec ollamy (jeden store, wiele typów blobów) + pip (jeden indeks, hash-pinning),
sprawdzony na miliardach pobrań.

---

## Backport do MangaShift: multi-task progress bar

**Kontekst:** AniShift skopiował `utils/rich_console` 1:1 z MangaShift, ale dołożył
`MultiProgressManager` — wiele pasków naraz, każdy z własnym kolorem per-task.
MangaShift tego nie ma. Żeby `utils/` pozostał wspólny (1:1 w obie strony), ten dodatek
powinien wrócić do MangaShift.

**Co skopiować z AniShift → MangaShift:**

- `utils/rich_console/progress/multi.py` — cała klasa `MultiProgressManager` (nowy plik).
  Tryb tylko `blocks` (bo `BarColumn` trzyma `complete_style` na konstruktorze i nie czyta
  `task.fields`; blocks idzie przez `TextColumn("{task.fields[custom_bar]}")` — per-task).
  Karmiony bajtami (`total=size_bytes`, `advance` o bajty) → kolumny bytes/speed pokazują
  realne MB i MB/s. Thread-safe (własny `threading.Lock`).
- `utils/rich_console/progress/manager.py` — fix 5 kolumn (`ColoredPercentageColumn`,
  `Elapsed`, `ETA`, `Bytes`, `Speed`): każda `render` czyta styl z
  `task.fields.get(_STYLE_FIELD) or self.style_name`. Wstecznie zgodne — stary
  jednotaskowy manager nie ustawia pola, więc fallback zachowuje zachowanie 1:1.
  Nowa stała `_STYLE_FIELD: Final[str] = "style"`.
- `utils/rich_console/progress/__init__.py` + `rich_console/__init__.py` — eksport
  `MultiProgressManager`.
- `utils/rich_console/tests/test_progress.py` — klasa `TestMultiProgressManager` (9 testów:
  per-task style niezależny, thread-safety, clamp, truncation, fallback bez pola).
- `utils/rich_console/examples/demo_progress.py` — demo 25 „MULTI-TASK" (dwa paski,
  różne prędkości → różne kolory jednocześnie).

**Uwaga o strukturze:** w MangaShift `utils/` jest WEWNĄTRZ pakietu (`mangashift/utils/`),
importy relatywne (`..progress.multi`) — więc kopiuje się bez zmiany ścieżek. W AniShift
`utils/` też jest w pakiecie (`anishift/utils/`, przeniesione z rootu) — symetryczne.

**Dlaczego to działa (sedno fixu):** `rich.Progress` natywnie renderuje wiele tasków;
problemem był tylko wrapper trzymający jeden `self.task`. Kolor per-task wymagał
przeniesienia stylu z instancji kolumny (współdzielonej przez wszystkie wiersze) do
`task.fields` — inaczej ostatni `update` przemalowywał wszystkie paski.

**Efekt: `utils/rich_console` znów 1:1 między AniShift i MangaShift, z multi-paskiem po obu stronach.**
