# AniShift

[Polski](README.pl.md)

Terminal-based Polish voice-over pipeline for anime.

AniShift finds and downloads anime episodes, then turns MKV sources into Polish subtitles or a
Polish lector track: subtitle extraction, translation, TTS, audio processing and final media
composition. Completed sources and products collect in the flat `workspace/ready/` directory.
Regeneration runs there without moving files back. Temporary run data stays in `workspace/tmp/`.

AniShift currently supports Windows only.

## Quick start

```bash
uv sync                                   # Python dependencies
uv run anishift setup                     # MKVToolNix and FFmpeg into external/bin/
uv run anishift doctor                    # everything green? then:
uv run anishift                           # the interactive interface
```

API keys go into `.env` (see "Configuration"); `doctor` lists which engines have one.
Opening the interface starts or connects to one background resident. Optionally run
`uv run anishift autostart enable` to start the resident after every logon.

If the shell still has another project's virtual environment active, start with
`uv run --no-active anishift`. This selects AniShift's `.venv` and silences the
mismatch warning. See the
[uv project environment documentation](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).

## The interface

Running `anishift` without a subcommand opens Home with four items:

- **Panel** — the main window with four tabs: Anime, Subskrypcje, Przetwarzanie and Biblioteka.
- **Ręczny** — choose sources, output and per-run overrides before execution.
- **Ustawienia** — edit preferences, engines, models, download sources and connections.
- **Wyjście** — close the interface; accepted work continues in the resident.

Home shows an animated pixel-art slime on terminals with SIXEL support; other terminals
use a text fallback. The interface uses one Prompt Toolkit renderer.

In Panel, switch tabs with Left/Right, Tab/Shift+Tab or a click. **O** turns the automation
on or off from any tab, **?** lists the keys of the current screen and **Esc** goes back.
Panel opens on Subskrypcje.

### Anime: search and download

Type a title the way you would say it, for example `frieren` or `solo leveling`. AniList
turns it into a series, you pick the entry (season, film, special) and get its episodes
with titles and air dates. For each episode AniShift searches Torrentio, Nyaa, Knaben,
nekoBT and TsukiHime, merges the results and ranks the releases with **Jakość** (quality)
and **Pewność** (confidence that the release is this episode).

In the episode list:

- **Space** ticks an episode, **A** ticks all, **Z** asks for a range;
- **D** downloads the ticked episodes, or the highlighted one;
- **I** (or Enter) opens the release list for the episode, where **D** downloads a chosen release;
- **P** downloads an episode again;
- **S** subscribes to the series;
- Enter on a ready episode plays it.

Release rows are ranked so that releases with Polish subtitles come first. Subscriptions
wait for Polish subtitles (2 hours by default, configurable in Ustawienia › Pobieranie)
before taking the best other release; a manual **D** downloads at once. Each source can be
switched off in the same place.

Downloads go through AniShift's own verified qBittorrent in `external/bin/qbittorrent/`.
Its profile, credentials and history live in `config/qbittorrent/`, separate from your
personal installation, and it picks its own free Web UI port. Downloads run concurrently;
completed jobs stop seeding and release their files before processing.

```bash
uv run anishift qbit setup    # optional: prepare the private client before the first download
uv run anishift qbit status   # inspect readiness without starting the client
```

### Subscriptions

**S** in the episode list opens a subscription draft; already aired episodes are ticked and
download right away, later ones download after they air. The **Subskrypcje** tab lists
subscriptions:

- **Enter** opens the season's episodes, where **T** downloads a waiting episode now;
- **D** adds a new subscription through the Anime search;
- **W** pauses or resumes, **R** checks now;
- **Del** removes, **Ctrl+Z** restores the last removed one.

A subscription closes itself when the season has finished and every episode is in place.
Subscriptions are stored in the resident state, `config/watch/state.json`.

```bash
uv run anishift subs list        # subscriptions, next episode, last check
uv run anishift subs check ID    # check one subscription now
uv run anishift subs remove ID   # remove one subscription
```

### Processing and the library

**Przetwarzanie** shows downloads and processing: **W** pauses or resumes a transfer,
**X** cancels it after confirmation and **H** opens the history. On an episode whose processing
failed, **P** retries it at once and **Del** moves its files to the Recycle Bin as in Biblioteka;
**Ctrl+Z** restores them.

`workspace/` may hold one subfolder per series. Discovery reads the root and every subfolder
except the managed `tmp/` directory and hidden directories. With the automation on,
stable inputs enter the same scheduler used by Ręczny; confirmed existing products are reused.
After successful processing, sources and products move to `ready/` without rewriting their
contents on the same volume. Name collisions keep both episodes.

In **Biblioteka**, Enter opens the result, **F** shows it in Explorer and **Del** moves the
whole set to the Recycle Bin without confirmation. **Ctrl+Z** restores the last deleted set,
also after a resident restart; it never overwrites an occupied destination and is a single
undo, not a stack.

The resident state in `config/watch/state.json` is versioned (schema 5). A build reads
older schemas and migrates them, but an older build refuses a newer state, so do not run
an older AniShift on a state a newer one has written.

After an interruption the resident verifies saved work and resumes safe unfinished operations.
An unconfirmed remote operation or an exhausted retry budget stays visible for manual recovery.
Existing products stay available while a replacement is being prepared.

## Resident and autostart

```bash
uv run anishift autostart enable    # register the logon task and start the resident now
uv run anishift autostart disable   # remove the task and stop the resident
uv run anishift autostart status    # enabled | disabled | missing
uv run anishift watch               # run the resident in this terminal instead
uv run anishift watch status        # running (pid N) | stopped
uv run anishift watch stop          # stop the resident
```

The resident runs without console windows and has a tray icon that opens AniShift.

## Technical commands

```bash
uv run anishift run --preset ID   # run one stored preset without interaction
uv run anishift doctor            # inspect tools, credentials, workspace, encoding, watch, autostart
uv run anishift setup [--force]   # download and verify tools in external/bin/
```

Before inspecting media, AniShift prepares missing MKVToolNix and FFmpeg from the verified
manifest (SHA256). TXT-only workspaces do not trigger these downloads.

Non-interactive runs use the resident and exit with `0` for full success, `1` when
refused before start, `3` for a failed or partial run, and `4` when cancelled.
User-facing errors stay concise; developer diagnostics go to the structured log.

## Configuration

Ustawienia saves each supported value immediately. Configuration files remain available
for advanced or initial setup:

| File | Contents |
|---|---|
| `config/presets.json` | Presets for `run --preset` and the default preset |
| `config/settings.json` | Workflow, engine and download preferences |
| `.env` | API keys and tokens |

Translation uses Google by default; LLM translation is chosen in Ustawienia, where the
provider and model are picked (Gemini by default). Each provider reads its own key from
`.env`. Palantir Foundry is one of the providers; its model list is built into
`anishift/services/llm/engines/palantir/constants.py` and its token is read from
`ANISHIFT_PALANTIR_TOKEN`, or from `FOUNDRY_API_TOKEN` when the prefixed value is absent.
Secrets are never displayed; diagnostics only report whether one is configured.

Ustawienia › Napisy › Plik czcionki dialogów chooses the font for the lines the narrator
reads. AniShift draws them with it, attaches that file and its variants from the same
folder to the MKV and burns MP4 subtitles with them; signs keep the release fonts.

Ustawienia > Napisy > Lektor a napisy ekranowe decides whether the narrator also reads
on-screen signs in the pauses between lines: never, when they matter and fit (default), or
whenever they fit. Spoken lines keep their exact places either way.

## Requirements

- Windows and Python 3.14+
- MKVToolNix and FFmpeg in `external/bin/`, installed on demand or by `anishift setup`
- qBittorrent is prepared privately on demand; a personal installation is not required
- API credentials required by the selected translation or TTS engines
- Google Chrome for the ElevenReader narrator, with the ElevenReader account signed in once through
  Ustawienia › Lektor › Zaloguj / sprawdź sesję
- Optional Windows SAPI voices must be installed separately with a valid license
  and be available to the Python process architecture. AniShift does not install
  or activate commercial voices; an expired voice can display its own vendor dialog.

## Documentation

See the [documentation map](docs/README.md) for the current work, the ideas file and
historical implementation records.
