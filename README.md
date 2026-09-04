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

Running `anishift` without a subcommand opens the interactive interface:

- **Auto** processes every ready workspace group with the default preset.
- **Manual** lets you choose sources, output, and per-run overrides before execution.
- **Settings** edits supported preferences and provides a read-only model catalogue.
- **Exit** closes the interface immediately.

The interface uses one Prompt Toolkit renderer. Home displays the packaged animated
pixel-art slime on terminals with SIXEL support. The animation is prepared before
the first interactive frame, so it appears without a startup placeholder. Terminals
without image support use the available text fallback; small windows can omit the mascot.

Before inspecting media, AniShift prepares missing MKVToolNix and FFmpeg tools from
the verified manifest. Windows downloads use SHA256 verification and run outside
the renderer. TXT-only workspaces do not trigger media-tool downloads.

## Technical commands

```bash
uv run anishift run --preset ID   # run one stored preset without interaction
uv run anishift doctor            # inspect tools, credentials, workspace, and encoding
uv run anishift setup [--force]   # download and verify tools in external/bin/
```

Non-interactive runs exit with `0` for full success, `1` when refused before start,
`3` for a failed or partial run, and `4` when cancelled. User-facing refusals and
errors remain concise; developer diagnostics are written to the structured log.

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
