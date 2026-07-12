# config/

Panel preferences live here — **not** in `workspace/`.

`settings.json` (created on first `/settings` save) holds the choices the panel
edits: processing mode, selected translation/TTS engine, voice, tempo, volume,
output variant, and whether finished results move to `workspace/output/`.

## Why here and not in workspace

`workspace/` is for runtime data only — the folder the user drops MKV files
into. Keeping `settings.json` next to the code leaves that folder clean while
the file stays visible and hand-editable. It is gitignored (preferences are
per-machine); this README is tracked.
