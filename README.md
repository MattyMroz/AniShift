# AniShift

Terminal-based anime lector for Polish.

Drop MKV files into `workspace/`, press Enter — AniShift extracts subtitles, translates them, generates a TTS voice-over (lector), and merges the result. Durable products are written beside their source; one run keeps its working files in `workspace/temp/`.

Sister project of MangaShift. The interactive interface is a Textual shell: a static logo, an always-available composer with inline slash completion, and a one-row bottom bar.

## Usage

```
uv sync
uv run anishift
```

`anishift` without a subcommand opens the shell. An **empty Enter** in the composer is the one deliberate action that starts the automatic route: it plans the default preset over every ready group, then either runs it, asks first when the plan would replace an existing product, or shows the reasons on `/auto` when the plan cannot run.

## Commands

The palette (`Ctrl+P`), the inline completion and `/help` show the same fourteen commands:

| command | what it does |
|---|---|
| `/init` | prepare the workspace and the configuration, then show the next steps |
| `/connect` | edit the Palantir Foundry connection and probe one model on request |
| `/status` | safe summary of configuration, workspace and current run |
| `/debug` | wider redacted diagnostics of the current session |
| `/help` | list the commands and the keys the registry holds |
| `/exit` | leave the application, confirming first while a run is active |
| `/auto` | configure the automatic mode and its presets |
| `/manual` | prepare the manual intents of the selected groups |
| `/model` | choose the primary model from the local catalogue |
| `/translation` | edit the translation settings and their own model |
| `/prompts` | choose the task prompt, the style and the prompt modules |
| `/tts` | edit the speech settings, the voices and the audio profile |
| `/theme` | choose the theme with a live preview and a rollback |
| `/doctor` | run the technical diagnostics without repairing anything |

`Ctrl+C` leaves the application; with a dialog open it cancels that dialog first. `Esc` closes a dialog without changing anything.

### `/auto` versus `/manual`

`/auto` only configures: it edits the preset the automatic route applies and never starts a run. The run starts from an empty Enter.

`/manual` prepares per-group intents (which subtitle or audio source to use, which products to build). A manual plan always passes through Preview and an explicit Start; leaving the preview gives the reservation back and starts nothing.

## Models

The LLM provider is Palantir Foundry. The list of usable models is a local file, `config/anishift.models.jsonc`; `config/anishift.models.example.jsonc` is the tracked example to copy. Browsing and filtering that list performs no network request — a model stays unverified until `/connect` probes it in the current session.

The token is read from the environment or from `.env`, never from a JSON file:

- `ANISHIFT_PALANTIR_TOKEN` — the token AniShift asks for;
- `FOUNDRY_API_TOKEN` — unprefixed compatibility source, used when the prefixed one is absent or blank.

Secrets are never displayed: a settings row states `configured` or `missing`, nothing more.

## Non-interactive modes

These subcommands never open Textual:

```
uv run anishift doctor            # report binaries, keys, workspace, console encoding
uv run anishift setup [--force]   # download and verify external tools into external/bin/
uv run anishift run --preset ID   # run one stored automatic preset over the workspace
```

`run --preset` reports one line per group and exits with `0` for a full success, `1` when it refuses to start, `3` for a failed or partial run and `4` when cancelled.

## Requirements

- Python 3.14+
- External binaries in `external/bin/`: mkvtoolnix (mkvextract, mkvmerge), ffmpeg — `anishift setup` fetches them
- API keys in `.env` (optional per engine): DeepL, ElevenLabs, LLM providers
