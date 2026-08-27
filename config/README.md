# config/

Preferences and hand-written runtime files live here — **not** in `workspace/`.

This directory holds every hand-editable runtime file AniShift keeps next to the
code:

- `settings.json` — workflow and engine preferences (processing mode,
  translation/TTS engine, voice, tempo, volume, engine options);
- `presets.json` — the stored presets a run applies, and which one is the
  default `anishift` takes without `--preset`;
- `anishift.models.jsonc` — the local model catalogue; copy it from the tracked
  `anishift.models.example.jsonc` and comment it freely, AniShift only reads it.

Each of them is created with its defaults on first run. Durable products are
always written beside their source, never here.

## Why here and not in workspace

`workspace/` is for runtime data only — the folder the user drops MKV files
into. Keeping these files next to the code leaves that folder clean while they
stay visible and hand-editable. They are per-machine and never committed:
`.gitignore` covers `settings.json`, `presets.json`, `anishift.models.jsonc` and
the custom prompts. Only this README and the model-catalogue example are tracked.

## Custom LLM prompts

Optional user prompts live in:

- `prompts/tasks/*.txt` — complete translation tasks;
- `prompts/styles/*.txt` — Polish-language style instructions;
- `prompts/modules/*.txt` — optional reusable instruction modules.

The filename without `.txt` is the prompt ID a preference stores. AniShift
rescans the directory every time it loads the preferences and forgets a selected
ID whose file is gone. Custom files use version `1`; empty files and duplicate
IDs are rejected with a clear configuration error. User-authored `.txt` prompts
are gitignored.
