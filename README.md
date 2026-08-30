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

The interface uses one responsive terminal renderer. Its packaged pixel-art slime
uses the approved transparent still while dedicated animation frames are prepared. If
the image cannot be decoded or the terminal is too small, it falls back to compact
ASCII or no mascot without blocking the run.

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
- MKVToolNix and FFmpeg in `external/bin/` (`anishift setup` installs them)
- API credentials required by the selected translation or TTS engines
