# AniShift

Terminal-based Polish voice-over pipeline for anime.

AniShift turns MKV sources into Polish subtitles or a Polish lector track through
subtitle extraction, translation, TTS, audio processing, and final media composition.
Completed sources and products collect in the flat `workspace/ready/` directory.
Regeneration runs there without moving files back. Temporary run data stays in `workspace/temp/`.

## Quick start

```bash
uv sync                                   # Python dependencies
uv run anishift setup                     # MKVToolNix and FFmpeg into external/bin/ (Windows)
uv run anishift doctor                    # everything green? then:
uv run anishift                           # the interactive interface
```

API keys go into `.env` (see "Configuration"); `doctor` lists which engines have one.
Opening the interface starts or connects to one background resident. A new configuration
starts with Auto off and no subscriptions. Enable Auto and select subscription ranges explicitly
in **Stan**. Optionally run `uv run anishift autostart enable` to start the resident
after every logon; this does not enable Auto or add subscriptions.

If the shell still has another project's virtual environment active, start with
`uv run --no-active anishift`. This selects AniShift's `.venv` and silences the
mismatch warning. Do not use `--active` to target a different project's environment.
See [uv project environment documentation](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).

Running `anishift` without a subcommand opens the interactive interface:

- **Auto** processes every ready workspace group with the default preset.
- **Ręczny** lets you choose sources, output, and per-run overrides before execution.
- **Anime** searches nyaa.si for a title and hands the chosen releases to qBittorrent.
- **Stan** shows progress, transfers, subscriptions and files while work continues.
- **Ustawienia** edits supported preferences and provides a read-only model catalogue.
- **Wyjście** closes the interface; accepted work continues in the resident.

The interface uses one Prompt Toolkit renderer. Home and Auto display the packaged animated
pixel-art slime on terminals with SIXEL support. The animation is prepared before
the first interactive frame, so it appears without a startup placeholder. Terminals
without image support use the available text fallback; small windows can omit the mascot.

Use arrows or Tab/Shift+Tab to navigate Settings, Right/Enter to open, and Left/Esc
to go back. Text editors support cursor movement, Delete and paste; secret values
are masked and require explicit confirmation. Auto supports arrows, PageUp/PageDown
and Home to browse the queue; End resumes following the active file. Resizing keeps
the same application screen and preserves the previous console history on exit.

All text fields share Prompt Toolkit's editing buffer: Ctrl+Left/Right moves by words,
Ctrl+Backspace/Delete removes words, Shift with arrows or Home/End selects text,
Ctrl+A selects all, and Ctrl+Z/Y undo or redo. Selected text is replaced when typing.
Ctrl+C copies a selection to the application clipboard; without a selection it retains
the screen's interrupt action. Ctrl+X/V cut and paste between fields; terminal paste
also accepts text from outside the application. Secrets remain masked.

Before inspecting media, AniShift prepares missing MKVToolNix and FFmpeg tools from
the verified manifest. Windows downloads use SHA256 verification and run outside
the renderer. TXT-only workspaces do not trigger media-tool downloads.

## Searching and downloading

The **Anime** row in the interactive interface takes a title the way you would say it:
`solo leveling`, `mushoku tensei`, `frieren 2`, `solo leveling 1` (the trailing number is
an episode, `4-10` a range). AniList turns the phrase into one series with its romaji and
English names, so you pick the season from a short list that shows year, format, episode
count and whether the series is finished or still airing. nyaa.si is then searched with
every name of that series, in both the English and the non-English subtitle categories,
and the 1080p+ releases are listed by release group with the subtitle language (`EN`,
`FR`, `MULTI`), newest release first. English dubs and releases of unknown language stay
hidden. When a release group numbers episodes across seasons (`Solo Leveling - 13` for
the first episode of season 2), the row shows both numbers: `odc. 1 (13)`.

In the results, Space ticks one episode, **A** ticks every episode of the highlighted
group, **Z** asks for a range (`4-10`, `5-`, `-3`), **S** switches between newest and
most seeded, **F** drops the episode filter from your phrase, and Enter sends the ticked
episodes to qBittorrent. Files of one series always land in one folder,
`workspace/<English title>/` (romaji when AniList has no English title), whichever
group you took. If AniList does not answer, the phrase goes to nyaa.si as typed and the
groups arrive ordered by seeders instead of by newest release; **S** switches that too.

AniShift prepares its own verified qBittorrent executable in `external/bin/qbittorrent/`
for the first download. Its profile, credentials and history live in `config/qbittorrent/`,
separate from your personal installation. It selects its own available Web UI port.
Downloads run concurrently. Completed jobs stop seeding and release their files before
relocation; AniShift retains their acquisition history. Uploading during a download is possible.

```bash
uv run anishift qbit setup    # optional: prepare the private binary ahead of the first download
uv run anishift qbit status   # inspect readiness without starting the client
```

The resident confirms selected torrent files through the client and disk before admitting Auto.
An allocated full-size file or an unchanged timestamp alone is not proof of completion.

### Following a series

In the Anime results press **O** on an episode to follow that series from that
episode on, with that release group. AniShift queues the episodes already available
and the resident checks according to episode air dates, release delays and bounded search windows. Highlight the first
episode to collect the whole season, the latest one to get only what comes next.

```bash
uv run anishift subs list        # followed series, next episode, last check
uv run anishift subs check       # check every followed series now
uv run anishift subs remove ID   # stop following; downloaded files stay
```

Followed series live in `config/subscriptions.json`. The State screen supports adding,
enabling, disabling and removing subscriptions. Disabling stops new orders; accepted
transfers have separate Stop, Resume and Cancel actions. Removing a subscription keeps media.
Unlinked series use the configured hourly fallback; ended seasons do not poll indefinitely.

## Watching the library

`workspace/` may hold one subfolder per series, for example `workspace/Frieren/`.
Discovery reads the root and every subfolder except the managed `temp/` directory,
and ignores hidden directories. Drop files directly into the workspace root. After successful
processing, sources and related products move to `ready/` without rewriting their contents
on the same volume. Name collisions preserve both episodes. Regenerate directly in `ready/`.

```bash
uv run anishift autostart enable    # register the logon task and start watching now
uv run anishift autostart disable   # remove the task and stop watching
uv run anishift autostart status    # enabled | disabled | missing
uv run anishift watch               # watch in this terminal instead of the logon task
uv run anishift watch status        # running (pid N) | stopped
uv run anishift watch stop          # stop the watching process
```

The resident runs without spawning batch windows. Its tray icon opens the existing panel
or one new panel. Progress and settings remain independently accessible. With Auto enabled,
stable available inputs enter the same scheduler used by Manual; confirmed existing products
are reused. Changing preferences does not regenerate old episodes.

After interruption, the resident verifies saved work and resumes safe unfinished operations.
An unconfirmed remote operation or exhausted retry budget remains visible for explicit manual
recovery. Pending moves remain visible under Files; **P** retries them. Existing products stay
available while a replacement is being prepared. `watch batch` only reports its replacement.

## Technical commands

```bash
uv run anishift run --preset ID   # run one stored preset without interaction
uv run anishift doctor            # inspect tools, credentials, workspace, encoding, watch, autostart
uv run anishift setup [--force]   # download and verify tools in external/bin/
```

Non-interactive runs use the resident and exit with `0` for full success, `1` when
refused before start, `3` for a failed or partial run, and `4` when cancelled.
User-facing refusals and errors remain concise; developer diagnostics are written
to the structured log.

## Configuration

Interactive Settings persists individual supported values immediately. Configuration
files remain available for advanced or initial setup:

| File | Contents |
|---|---|
| `config/presets.json` | Automatic presets and the default preset |
| `config/settings.json` | Workflow and engine preferences |
| `config/anishift.models.jsonc` | Local catalogue of selectable models |
| `.env` | API keys and tokens |

The LLM provider is Palantir Foundry. Its token is read from
`ANISHIFT_PALANTIR_TOKEN`, or from `FOUNDRY_API_TOKEN` when the prefixed value is
absent. Secrets are never displayed; diagnostics only report whether one is
configured.

## Requirements

- Python 3.14+
- MKVToolNix and FFmpeg (`external/bin/` on Windows; installed on demand or by
  `anishift setup`; non-Windows systems can use tools already on `PATH`)
- On Windows, AniShift downloads and configures its private qBittorrent on demand;
  a personal installation is not required. Managed torrent downloads require Windows.
- API credentials required by the selected translation or TTS engines
- Optional Windows SAPI voices must be installed separately with a valid license
  and be available to the Python process architecture. AniShift does not install
  or activate commercial voices; an expired voice can display its own vendor dialog.

## Documentation and plans

See the [documentation map](docs/README.md) for the current product direction,
planning handoff and historical implementation records.
