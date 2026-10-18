"""Subtitle processing services."""

from __future__ import annotations

from anishift.services.subtitles.classifier import Category, StyleVerdict, classify_styles, dedup_animation
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.service import (
    collapse_fbf,
    layout_translated,
    load_subtitles,
    normalize_subtitles,
    reflow_polish_dialogue,
    split_subtitles,
    subtitle_kind,
    write_displayed,
    write_full,
    write_spoken,
    write_translated,
    write_translated_displayed,
    write_translated_spoken,
)
from anishift.services.subtitles.srt import spoken_to_srt
from anishift.services.subtitles.text import (
    is_drawing,
    marked_text,
    replace_visible_text,
    restore_markers,
    visible_text,
    visible_verses,
)
from anishift.services.subtitles.txt import read_txt, txt_to_spoken
from anishift.services.subtitles.types import (
    Decision,
    DisplayedLine,
    FontSources,
    LayoutReport,
    SplitStats,
    SpokenLine,
    SubtitleKind,
    SubtitleSplit,
    TranslatedLayout,
)

__all__ = [
    "Category",
    "Decision",
    "DisplayedLine",
    "FontSources",
    "LayoutReport",
    "SplitStats",
    "SpokenLine",
    "StyleVerdict",
    "SubtitleError",
    "SubtitleKind",
    "SubtitleSplit",
    "TranslatedLayout",
    "classify_styles",
    "collapse_fbf",
    "dedup_animation",
    "is_drawing",
    "layout_translated",
    "load_subtitles",
    "marked_text",
    "normalize_subtitles",
    "read_txt",
    "reflow_polish_dialogue",
    "replace_visible_text",
    "restore_markers",
    "split_subtitles",
    "spoken_to_srt",
    "subtitle_kind",
    "txt_to_spoken",
    "visible_text",
    "visible_verses",
    "write_displayed",
    "write_full",
    "write_spoken",
    "write_translated",
    "write_translated_displayed",
    "write_translated_spoken",
]
