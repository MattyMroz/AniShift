# config/

Preferences and hand-written runtime files live here — **not** in `workspace/`.

This directory holds every hand-editable runtime file AniShift keeps next to the
code:

- `settings.json` — workflow and engine preferences the settings screens save
  (processing mode, translation/TTS engine, voice, tempo, volume, engine options);
- `presets.json` — the stored automatic presets `/auto` edits and
  `anishift run --preset` applies;
- `ui_state.json` — presentation preferences, currently the selected theme;
- `anishift.models.jsonc` — the local model catalogue; copy it from the tracked
  `anishift.models.example.jsonc` and comment it freely, AniShift only reads it.

Each of them is created on first save. Durable products are always written beside
their source, never here.

## Why here and not in workspace

`workspace/` is for runtime data only — the folder the user drops MKV files
into. Keeping these files next to the code leaves that folder clean while they
stay visible and hand-editable. They are per-machine and are not meant to be
committed: `.gitignore` covers `settings.json`, `ui_state.json`,
`anishift.models.jsonc` and the custom prompts, but not `presets.json` yet. This
README and the model-catalogue example are tracked.

## Custom LLM prompts

Optional user prompts live in:

- `prompts/tasks/*.txt` — complete translation tasks;
- `prompts/styles/*.txt` — Polish-language style instructions;
- `prompts/modules/*.txt` — optional reusable instruction modules.

The filename without `.txt` is the prompt ID shown in `/prompts`. AniShift
rescans the directory every time it loads the preferences and forgets a selected
ID whose file is gone. Custom files use version `1`; empty files and duplicate
IDs are rejected with a clear configuration error. User-authored `.txt` prompts
are gitignored.
