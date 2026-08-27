# AniShift

Terminal-based anime lector for Polish.

Drop MKV files into `workspace/`, run `anishift` — AniShift extracts subtitles, translates them, generates a TTS voice-over (lector), and merges the result. Durable products are written beside their source; one run keeps its working files in `workspace/temp/`.

Sister project of MangaShift. There is no interactive interface: one command runs the pipeline and reports the outcome as text.

## Usage

```
uv sync
uv run anishift
```

`anishift` without a subcommand runs the preset stored as the default over every ready group in the workspace, then reports one line per group.

## Commands

```
uv run anishift                   # run the default preset over the workspace
uv run anishift run --preset ID   # run one named stored preset instead
uv run anishift doctor            # report binaries, keys, workspace, console encoding
uv run anishift setup [--force]   # download and verify external tools into external/bin/
```

Every run exits with `0` for a full success, `1` when it refuses to start, `3` for a failed or partial run and `4` when cancelled. A refusal is a sentence and a hint, never a traceback.

## Configuration

Everything is a file next to the code; edit it directly and run again.

| file | what it holds |
|---|---|
| `config/presets.json` | the automatic presets and which one is the default |
| `config/settings.json` | workflow and engine preferences |
| `config/anishift.models.jsonc` | the local catalogue of usable models |
| `.env` | API keys and tokens |

## Models

The LLM provider is Palantir Foundry. The list of usable models is a local file, `config/anishift.models.jsonc`; `config/anishift.models.example.jsonc` is the tracked example to copy.

The token is read from the environment or from `.env`, never from a JSON file:

- `ANISHIFT_PALANTIR_TOKEN` — the token AniShift asks for;
- `FOUNDRY_API_TOKEN` — unprefixed compatibility source, used when the prefixed one is absent or blank.

Secrets are never displayed: a report states `configured` or `missing`, nothing more.

## Requirements

- Python 3.14+
- External binaries in `external/bin/`: mkvtoolnix (mkvextract, mkvmerge), ffmpeg — `anishift setup` fetches them
- API keys in `.env` (optional per engine): DeepL, ElevenLabs, LLM providers
