"""Replay the Polish text of quality pairs through the subtitle writer and compare two replays byte for byte."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from anishift.application.translation_handler import displayed_lines, spoken_lines, translation_verses
from anishift.services.subtitles import is_drawing, load_subtitles, split_subtitles, visible_text, write_translated
from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.translation.types import FileTranslation, TranslatedLine
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.quality import metrics
from scripts.quality.episode import OUTPUT_NAME, SOURCE_NAME, episode_dirs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.application.translation_handler import TranslationVerses
    from anishift.services.subtitles import SubtitleSplit

# ── Constants ─────────────────────────────────────────────────────────────────

REPLAY_ROOTS: Final[tuple[str, ...]] = ("library", "corpus-pairs")
"""Quality-root folders replayed when no roots are given."""

MAPPING_NAME: Final[str] = "mapping.json"
"""File in a replay folder recording every pair's writer inputs, exclusions and skips."""

REPLAY_SUFFIX: Final[str] = ".pl.ass"
"""Suffix of a replayed pair's output file, named after the pair folder."""


@dataclass(frozen=True, slots=True)
class PairInput:
    """Translation of every non-drawing source Dialogue event by index, and the unpaired indexes kept in English."""

    translations: dict[int, str]
    excluded: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Comparison:
    """Outcome of comparing two replay folders pair by pair."""

    identical: tuple[str, ...]
    different: tuple[tuple[str, str], ...]
    skipped: tuple[tuple[str, str], ...]


def pair_input(source: SSAFile, output: SSAFile) -> PairInput:
    """Take each source event's translation from its paired Polish event, joining its lines with spaces."""
    source_events: list[SSAEvent] = metrics.dialogue(source)
    output_events: list[SSAEvent] = metrics.dialogue(output)
    paired: dict[int, int] = dict(metrics.pair_events(source_events, output_events))
    translations: dict[int, str] = {}
    excluded: list[int] = []
    for index, event in enumerate(source_events):
        if is_drawing(event.text):
            continue
        match: int | None = paired.get(index)
        if match is None:
            excluded.append(index)
        translations[index] = visible_text(event.text if match is None else output_events[match].text)
    return PairInput(translations, tuple(excluded))


def translation(split: SubtitleSplit, inputs: PairInput) -> FileTranslation:
    """Return the translator result the subtitle handler would receive for these inputs."""
    spoken: list[TranslatedLine] = []
    for line in spoken_lines(split):
        text: str = inputs.translations[line.order]
        spoken.append(TranslatedLine(line.start, line.end, line.text, text, (text,), line.style))
    displayed: tuple[str, ...] = tuple(inputs.translations[line.order] for line in displayed_lines(split))
    return FileTranslation(spoken=tuple(spoken), displayed=displayed)


def replay_pair(directory: Path, destination: Path) -> tuple[PairInput, Path | None]:
    """Write one pair's Polish text through today's translation layout and writer."""
    source: SSAFile = load_subtitles(directory / SOURCE_NAME)
    inputs: PairInput = pair_input(source, load_subtitles(directory / OUTPUT_NAME))
    split: SubtitleSplit = split_subtitles(source, kind="ass")
    verses: TranslationVerses = translation_verses(split, translation(split, inputs), LayoutLimits())
    return inputs, write_translated(split, verses.displayed, verses.spoken, destination)


def replay(directories: Sequence[Path], out: Path) -> Path:
    """Replay every pair folder into ``out`` and write its mapping file; return the mapping path."""
    out.mkdir(parents=True, exist_ok=True)
    pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    names: set[str] = set()
    for directory in directories:
        name: str = directory.name
        reason: str | None = _skip_reason(directory, names)
        names.add(name)
        if reason is not None:
            skipped.append({"name": name, "reason": reason})
            continue
        inputs, written = replay_pair(directory, out / f"{name}{REPLAY_SUFFIX}")
        if written is None:
            skipped.append({"name": name, "reason": "writer produced no output"})
            continue
        print(f"replayed {name}  excluded {len(inputs.excluded)}", file=sys.stderr)
        rows: list[dict[str, Any]] = [{"index": index, "text": text} for index, text in inputs.translations.items()]
        pairs.append({"name": name, "output": written.name, "inputs": rows, "excluded": list(inputs.excluded)})
    mapping: Path = out / MAPPING_NAME
    mapping.write_text(json.dumps({"pairs": pairs, "skipped": skipped}, ensure_ascii=False, indent=1), encoding="utf-8")
    return mapping


def _skip_reason(directory: Path, names: set[str]) -> str | None:
    if directory.name in names:
        return "duplicate pair name"
    if not (directory / OUTPUT_NAME).is_file():
        return f"no {OUTPUT_NAME}"
    return None


def compare(base: Path, other: Path) -> Comparison:
    """Compare two replay folders: equal inputs and identical output bytes count as identical."""
    base_pairs, base_skipped = _read_mapping(base)
    other_pairs, other_skipped = _read_mapping(other)
    identical: list[str] = []
    different: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for name in sorted(base_pairs.keys() | other_pairs.keys() | base_skipped.keys() | other_skipped.keys()):
        reason: str | None = base_skipped.get(name) or other_skipped.get(name)
        if reason is None and (name not in base_pairs or name not in other_pairs):
            reason = f"missing in {(other if name in base_pairs else base).name}"
        if reason is not None:
            skipped.append((name, reason))
            continue
        first, second = base_pairs[name], other_pairs[name]
        if (first["inputs"], first["excluded"]) != (second["inputs"], second["excluded"]):
            different.append((name, "inputs differ"))
        elif (base / first["output"]).read_bytes() != (other / second["output"]).read_bytes():
            different.append((name, "output bytes differ"))
        else:
            identical.append(name)
    return Comparison(tuple(identical), tuple(different), tuple(skipped))


def _read_mapping(run: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    data: dict[str, list[dict[str, Any]]] = json.loads((run / MAPPING_NAME).read_text(encoding="utf-8"))
    pairs: dict[str, dict[str, Any]] = {pair["name"]: pair for pair in data["pairs"]}
    skipped: dict[str, str] = {item["name"]: item["reason"] for item in data["skipped"]}
    return pairs, skipped


def main(argv: Sequence[str], quality_root: Path) -> int:
    """Replay pairs into a folder, or compare two replay folders; return 1 when a comparison finds differences."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.quality replay",
        description=(
            "Write each pair's Polish text (paired by timing and style, unpaired events in English) through the "
            "current translation layout and subtitle writer, or compare two replay folders byte for byte."
        ),
    )
    parser.add_argument("roots", nargs="*", type=Path, help="pair folders or roots searched recursively")
    parser.add_argument("--out", type=Path, help="replay folder to write")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASE", "OTHER"), help="replay folders to compare")
    args: argparse.Namespace = parser.parse_args(argv)
    if args.compare is not None:
        result: Comparison = compare(*args.compare)
        print(_summary(result))
        return 1 if result.different else 0
    if args.out is None:
        parser.error("give --out to replay or --compare to compare")
    setup_mode(LoggerMode.SILENT, file=FileConfig(enable=False))
    roots: list[Path] = list(args.roots) or [quality_root / folder for folder in REPLAY_ROOTS]
    print(f"mapping {replay(episode_dirs(roots), args.out)}", file=sys.stderr)
    return 0


def _summary(result: Comparison) -> str:
    lines: list[str] = [f"identical {len(result.identical)}", f"different {len(result.different)}"]
    lines.extend(f"  {name}: {reason}" for name, reason in result.different)
    lines.append(f"skipped {len(result.skipped)}")
    lines.extend(f"  {name}: {reason}" for name, reason in result.skipped)
    return "\n".join(lines)
