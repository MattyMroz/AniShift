# config/

Preferences and hand-written runtime files live here, not in `workspace/`.

This directory holds every hand-editable runtime file AniShift keeps next to
the code:

- `settings.json` stores workflow and engine preferences;
- `presets.json` stores reusable run presets and the default preset;
- `anishift.models.jsonc` is the local model catalog copied from
  `anishift.models.example.jsonc`.

Durable products are always written beside their source, never here.
Per-machine files are gitignored; only this README and the model-catalog
example are tracked.

## LLM translation prompts

Translation prompts are versioned application resources under
`anishift/services/translation/engines/llm/prompts/`, not runtime config.
The fixed files are `system.md`, `translation.md` and `retry.md`; selectable
styles are immediate `styles/*.md` files.

`settings.json` stores only the selected style name in
`llm_translation_style`. To add a style, add and ship another UTF-8 Markdown
file in the module's `styles/` directory. Missing, empty or invalid packaged
resources are configuration errors.
