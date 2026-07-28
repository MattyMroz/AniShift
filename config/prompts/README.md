# Custom AniShift prompts

Create UTF-8 text files in:

- `tasks/` for a complete translation task;
- `styles/` for Polish output style;
- `modules/` for optional reusable instructions.

The filename becomes the prompt ID. For example,
`styles/my_anime_style.txt` appears as `my_anime_style` in `/settings`.

AniShift reads all `.txt` files automatically. Other extensions are ignored.
Do not copy API keys or subtitle content into prompt filenames.
