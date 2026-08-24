# config/

Panel preferences live here — **not** in `workspace/`.

`settings.json` (created on first `/settings` save) holds the choices the panel
edits: processing mode, selected translation/TTS engine, voice, tempo, volume,
and related engine options. Durable products are always written beside their source.

## Why here and not in workspace

`workspace/` is for runtime data only — the folder the user drops MKV files
into. Keeping `settings.json` next to the code leaves that folder clean while
the file stays visible and hand-editable. It is gitignored (preferences are
per-machine); this README is tracked.

## Custom LLM prompts

Optional user prompts live in:

- `prompts/tasks/*.txt` — complete translation tasks;
- `prompts/styles/*.txt` — Polish-language style instructions;
- `prompts/modules/*.txt` — optional reusable instruction modules.

The filename without `.txt` is the prompt ID shown in `/settings`. AniShift
discovers every UTF-8 `.txt` file on panel open and before a pipeline run.
Custom files use version `1`; empty files and duplicate IDs are rejected with a
clear configuration error. User-authored `.txt` prompts are gitignored.
