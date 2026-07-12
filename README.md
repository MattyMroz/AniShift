# AniShift

Terminal-based anime lector for Polish.

Drop MKV files into `workspace/`, press Enter — AniShift extracts subtitles, translates them, generates a TTS voice-over (lector), and merges the result.

Sister project of MangaShift. Claude Code-style terminal UI: banner, `/settings` `/help` `/auto` `/manual` commands with inline completion.

## Usage

```
uv sync
uv run anishift
```

## Requirements

- Python 3.14+
- External binaries in `external/bin/`: mkvtoolnix (mkvextract, mkvmerge), ffmpeg
- API keys in `.env` (optional per engine): DeepL, ElevenLabs, LLM providers
