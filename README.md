# AniShift

Terminal-based Polish voice-over pipeline for anime.

AniShift turns MKV sources into Polish subtitles or a Polish lector track through
subtitle extraction, translation, TTS, audio processing, and final media composition.
Durable products are written beside their source; temporary run data stays in
`workspace/temp/`.

## Quick start

```bash
uv sync
uv run anishift
```

If the shell still has another project's virtual environment active, start with
`uv run --no-active anishift`. This selects AniShift's `.venv` and silences the
mismatch warning. Do not use `--active` to target a different project's environment.
See [uv project environment documentation](https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path).

Running `anishift` without a subcommand opens the interactive interface:

- **Auto** processes every ready workspace group with the default preset.
- **Manual** lets you choose sources, output, and per-run overrides before execution.
- **Settings** edits supported preferences and provides a read-only model catalogue.
- **Exit** closes the interface immediately.

The interface uses one Prompt Toolkit renderer. Home and Auto display the packaged animated
pixel-art slime on terminals with SIXEL support. The animation is prepared before
the first interactive frame, so it appears without a startup placeholder. Terminals
without image support use the available text fallback; small windows can omit the mascot.

Use arrows or Tab/Shift+Tab to navigate Settings, Right/Enter to open, and Left/Esc
to go back. Text editors support cursor movement, Delete and paste; secret values
are masked and require explicit confirmation. Auto supports arrows, PageUp/PageDown
and Home to browse the queue; End resumes following the active file. Resizing keeps
the same application screen and preserves the previous console history on exit.

Before inspecting media, AniShift prepares missing MKVToolNix and FFmpeg tools from
the verified manifest. Windows downloads use SHA256 verification and run outside
the renderer. TXT-only workspaces do not trigger media-tool downloads.

## Searching and downloading

The **Anime** row in the interactive interface searches nyaa.si for a title, lists the
1080p+ releases grouped by release group, and sends the episodes you tick (Space) to
qBittorrent with Enter. Files are saved into `workspace/<Series>/`, so the watch picks
every finished download up on its own.

qBittorrent needs its Web UI once: Options → Web UI → enable the Web User Interface and
tick "Bypass authentication for clients on localhost" (or set
`ANISHIFT_QBITTORRENT_USERNAME` and `ANISHIFT_QBITTORRENT_PASSWORD` in `.env`;
`ANISHIFT_QBITTORRENT_URL` overrides the default `http://127.0.0.1:8080`). Then run:

```bash
uv run anishift qbit setup    # make qBittorrent mark unfinished files with .!qB
uv run anishift qbit status   # reachable: yes (v5.2.3) / incomplete extension: on
```

The `.!qB` suffix matters: torrent files are created at full size before they are
complete, and the watch ignores that suffix until the download finishes.

### Following a series

In the Anime results press **O** on an episode to follow that series from that
episode on, with that release group. AniShift queues the episodes already available
and the watch process checks nyaa.si every hour for new ones. Highlight the first
episode to collect the whole season, the latest one to get only what comes next.

```bash
uv run anishift subs list        # followed series, next episode, last check
uv run anishift subs check       # check every followed series now
uv run anishift subs remove ID   # stop following; downloaded files stay
```

Followed series live in `config/subscriptions.json`.

## Watching the library

`workspace/` may hold one subfolder per series, for example `workspace/Frieren/`.
Discovery reads the root and every subfolder except the managed `temp/` directory,
and products are written beside their source in the same subfolder.

```bash
uv run anishift autostart enable    # register the logon task and start watching now
uv run anishift autostart disable   # remove the task and stop watching
uv run anishift autostart status    # enabled | disabled | missing
uv run anishift watch               # watch in this terminal instead of the logon task
uv run anishift watch status        # running (pid N) | stopped
uv run anishift watch stop          # stop the watching process
```

Watching runs without a window. When a new video file (with usable text) has stayed
unchanged for ten seconds and is not held exclusively by another program, a terminal
window opens with the Auto screen for that batch only, shows the outcome for ten
seconds, and closes itself. Any key closes it earlier; closing it mid-run cancels that
batch only, and the batch is not retried until its files change. Files that appear
during a batch wait for the next scan. Groups that already hold every product of the
default preset are never reprocessed.

## Technical commands

```bash
uv run anishift run --preset ID   # run one stored preset without interaction
uv run anishift doctor            # inspect tools, credentials, workspace, encoding, watch, autostart
uv run anishift setup [--force]   # download and verify tools in external/bin/
```

Non-interactive runs and batch windows exit with `0` for full success, `1` when
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
- API credentials required by the selected translation or TTS engines
- Optional Windows SAPI voices must be installed separately with a valid license
  and be available to the Python process architecture. AniShift does not install
  or activate commercial voices; an expired voice can display its own vendor dialog.

## Documentation and plans

See the [documentation map](docs/README.md) for the current product direction,
planning handoff and historical implementation records.
