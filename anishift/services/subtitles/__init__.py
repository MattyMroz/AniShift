"""Subtitle processing services."""

from __future__ import annotations

from anishift.services.subtitles.classifier import Category, StyleVerdict, classify_styles, dedup_animation
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.service import (
    collapse_fbf,
    load_subtitles,
    preview_styles,
    split_subtitles,
    subtitle_kind,
    write_displayed,
    write_translated,
)
from anishift.services.subtitles.srt import spoken_to_srt
from anishift.services.subtitles.text import is_drawing, replace_visible_text, visible_text
from anishift.services.subtitles.txt import read_txt, txt_to_spoken
from anishift.services.subtitles.types import Decision, SplitStats, SpokenLine, SubtitleKind, SubtitleSplit

__all__ = [
    "Category",
    "Decision",
    "SplitStats",
    "SpokenLine",
    "StyleVerdict",
    "SubtitleError",
    "SubtitleKind",
    "SubtitleSplit",
    "classify_styles",
    "collapse_fbf",
    "dedup_animation",
    "is_drawing",
    "load_subtitles",
    "preview_styles",
    "read_txt",
    "replace_visible_text",
    "split_subtitles",
    "spoken_to_srt",
    "subtitle_kind",
    "txt_to_spoken",
    "visible_text",
    "write_displayed",
    "write_translated",
]
