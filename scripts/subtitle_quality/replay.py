"""Replay the Polish text of quality pairs through the subtitle writer and compare two replays."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from anishift.application.translation_handler import displayed_lines
from anishift.services.fonts import system_font_paths
from anishift.services.subtitles import (
    FontSources,
    is_drawing,
    layout_translated,
    load_subtitles,
    split_subtitles,
    visible_text,
    write_full,
)
from anishift.services.subtitles.layout import LayoutLimits
from anishift.utils.logger import LoggerMode, setup_mode
from anishift.utils.logger.config import FileConfig
from scripts.subtitle_quality import metrics
from scripts.subtitle_quality.episode import OUTPUT_NAME, SOURCE_NAME, episode_dirs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles import SpokenLine, SubtitleSplit, TranslatedLayout

# ── Constants ─────────────────────────────────────────────────────────────────

REPLAY_ROOTS: Final[tuple[str, ...]] = ("library", "corpus-pairs")
"""Quality-root folders replayed when no roots are given."""

MAPPING_NAME: Final[str] = "mapping.json"
"""File in a replay folder recording every pair's writer inputs, exclusions, source decisions and skips."""

FONTS_NAME: Final[str] = "fonts"
"""Folder of a pair holding the fonts attached to its episode."""

REPLAY_SUFFIX: Final[str] = ".pl.ass"
"""Suffix of a replayed pair's output file, written at the pair id inside the replay folder."""

EXCLUSION_RULE: Final[str] = (
    "A spoken group (a narrator line and every copy the writer gives its text) takes the text of its first event: "
    "Polish when that event is paired, otherwise English, and then every event of the group is excluded. "
    "A displayed event is excluded when it is unpaired."
)
"""Rule deciding which events are written from English text and left out of event comparisons."""

type Entry = dict[str, Any]
"""One pair record of a mapping file."""


@dataclass(frozen=True, slots=True)
class PairInput:
    """Text of every non-drawing source Dialogue event by index, Polish for the paired ones and English otherwise."""

    translations: dict[int, str]
    paired: frozenset[int]


@dataclass(frozen=True, slots=True)
class Comparison:
    """Outcome of comparing two replay folders byte for byte, pair by pair."""

    identical: tuple[str, ...]
    different: tuple[tuple[str, str], ...]
    skipped: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class EventCounts:
    """Event-by-event outcome of one pair."""

    pair: str
    identical: int
    different: int
    excluded: int


@dataclass(frozen=True, slots=True)
class EventComparison:
    """Outcome of comparing two replay folders event by event, leaving excluded events out."""

    pairs: tuple[EventCounts, ...]
    skipped: tuple[tuple[str, str], ...]


def pair_input(source: SSAFile, output: SSAFile) -> PairInput:
    """Take each source event's text from its paired Polish event, joining its lines with spaces."""
    source_events: list[SSAEvent] = metrics.dialogue(source)
    output_events: list[SSAEvent] = metrics.dialogue(output)
    pairs: dict[int, int] = dict(metrics.pair_events(source_events, output_events))
    translations: dict[int, str] = {}
    for index, event in enumerate(source_events):
        if not is_drawing(event.text):
            match: int | None = pairs.get(index)
            translations[index] = visible_text(event.text if match is None else output_events[match].text)
    return PairInput(translations, frozenset(index for index in translations if index in pairs))


def spoken_groups(split: SubtitleSplit) -> dict[int, int]:
    """Map every spoken event to the first event of the narrator line whose text the writer gives it."""
    firsts: set[int] = {line.order for line in split.spoken}
    lines: defaultdict[tuple[str, str], list[SpokenLine]] = defaultdict(list)
    for line in split.spoken:
        lines[line.style, line.text].append(line)
    groups: dict[int, int] = {}
    for index, (event, decision) in enumerate(zip(metrics.dialogue(split.subs), split.decisions, strict=True)):
        if decision != "spoken":
            continue
        first: int | None = index if index in firsts else _containing_line(lines, event)
        if first is not None:
            groups[index] = first
    return groups


def _containing_line(lines: dict[tuple[str, str], list[SpokenLine]], event: SSAEvent) -> int | None:
    candidates: list[SpokenLine] = lines.get((event.style, visible_text(event.text)), [])
    return next((line.order for line in candidates if line.start <= event.start and event.end <= line.end), None)


def excluded_events(split: SubtitleSplit, inputs: PairInput) -> tuple[int, ...]:
    """Return the events written from English text under ``EXCLUSION_RULE``."""
    spoken: set[int] = {index for index, first in spoken_groups(split).items() if first not in inputs.paired}
    displayed: set[int] = {line.order for line in displayed_lines(split) if line.order not in inputs.paired}
    return tuple(sorted(spoken | displayed))


def translations(split: SubtitleSplit, inputs: PairInput) -> dict[int, str]:
    """Return the unbroken text the subtitle handler would lay out: one per spoken line and displayed event."""
    keys: list[int] = [line.order for line in split.spoken] + [line.order for line in displayed_lines(split)]
    return {index: inputs.translations[index] for index in keys}


def pair_fonts(directory: Path) -> FontSources:
    """Return the pair's episode fonts, when it keeps them, and the system fonts."""
    folder: Path = directory / FONTS_NAME
    episode: tuple[Path, ...] = (
        tuple(sorted(path for path in folder.iterdir() if path.is_file())) if folder.is_dir() else ()
    )
    return FontSources(episode=episode, system=system_font_paths())


def replay_pair(directory: Path, destination: Path) -> tuple[PairInput, SubtitleSplit, Path | None]:
    """Lay out one pair's Polish text with the default limits and write it."""
    source: SSAFile = load_subtitles(directory / SOURCE_NAME)
    inputs: PairInput = pair_input(source, load_subtitles(directory / OUTPUT_NAME))
    split: SubtitleSplit = split_subtitles(source, kind="ass")
    laid_out: TranslatedLayout = layout_translated(
        split, translations(split, inputs), fonts=pair_fonts(directory), limits=LayoutLimits(), dialogue_font=None
    )
    return inputs, split, write_full(replace(split, subs=laid_out.subs), destination)


def pair_dirs(roots: Sequence[Path]) -> list[tuple[str, Path]]:
    """Return every pair folder under the roots with its id, the folder path relative to its root's parent."""
    found: dict[str, Path] = {}
    for root in roots:
        base: Path = root.absolute()
        for directory in episode_dirs([base]):
            pair_id: str = directory.relative_to(base.parent).as_posix()
            if found.setdefault(pair_id, directory) != directory:
                msg = f"Two pair folders share the id {pair_id}"
                raise ValueError(msg)
    return sorted(found.items())


def replay(roots: Sequence[Path], out: Path) -> Path:
    """Replay every pair folder under the roots into ``out`` and write its mapping file; return the mapping path."""
    out.mkdir(parents=True, exist_ok=True)
    pairs: list[Entry] = []
    skipped: list[dict[str, str]] = []
    for pair_id, directory in pair_dirs(roots):
        if not (directory / OUTPUT_NAME).is_file():
            skipped.append({"pair": pair_id, "reason": f"no {OUTPUT_NAME}"})
            continue
        destination: Path = out / f"{pair_id}{REPLAY_SUFFIX}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        inputs, split, written = replay_pair(directory, destination)
        if written is None:
            skipped.append({"pair": pair_id, "reason": "writer produced no output"})
            continue
        excluded: tuple[int, ...] = excluded_events(split, inputs)
        print(f"replayed {pair_id}  excluded {len(excluded)}", file=sys.stderr)
        rows: list[Entry] = [{"index": index, "text": text} for index, text in inputs.translations.items()]
        output: str = destination.relative_to(out).as_posix()
        pairs.append(
            {
                "pair": pair_id,
                "output": output,
                "inputs": rows,
                "excluded": list(excluded),
                "decisions": list(split.decisions),
            }
        )
    mapping: Path = out / MAPPING_NAME
    content: Entry = {"rule": EXCLUSION_RULE, "pairs": pairs, "skipped": skipped}
    mapping.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    return mapping


def compare(base: Path, other: Path) -> Comparison:
    """Compare two replay folders: equal inputs and identical output bytes count as identical."""
    matched, skipped = matched_pairs(base, other)
    identical: list[str] = []
    different: list[tuple[str, str]] = []
    for pair_id, first, second in matched:
        if (first["inputs"], first["excluded"]) != (second["inputs"], second["excluded"]):
            different.append((pair_id, "inputs differ"))
        elif (base / first["output"]).read_bytes() != (other / second["output"]).read_bytes():
            different.append((pair_id, "output bytes differ"))
        else:
            identical.append(pair_id)
    return Comparison(tuple(identical), tuple(different), tuple(skipped))


def compare_events(base: Path, other: Path) -> EventComparison:
    """Compare two replay folders event by event, leaving out every event either mapping excludes."""
    matched, skipped = matched_pairs(base, other)
    counts: list[EventCounts] = []
    for pair_id, first, second in matched:
        if first["inputs"] != second["inputs"]:
            skipped.append((pair_id, "inputs differ"))
            continue
        excluded: set[int] = set(first["excluded"]) | set(second["excluded"])
        events: zip_longest[tuple[SSAEvent | None, SSAEvent | None]] = zip_longest(
            metrics.dialogue(load_subtitles(base / first["output"])),
            metrics.dialogue(load_subtitles(other / second["output"])),
        )
        outcomes: list[bool] = [
            left is not None and right is not None and left.equals(right)
            for index, (left, right) in enumerate(events)
            if index not in excluded
        ]
        counts.append(EventCounts(pair_id, sum(outcomes), outcomes.count(False), len(excluded)))
    return EventComparison(tuple(counts), tuple(skipped))


def matched_pairs(base: Path, other: Path) -> tuple[list[tuple[str, Entry, Entry]], list[tuple[str, str]]]:
    """Return the pairs both replay folders wrote with their two records, and every other pair with its reason."""
    base_pairs, base_skipped = _read_mapping(base)
    other_pairs, other_skipped = _read_mapping(other)
    matched: list[tuple[str, Entry, Entry]] = []
    skipped: list[tuple[str, str]] = []
    for pair_id in sorted(base_pairs.keys() | other_pairs.keys() | base_skipped.keys() | other_skipped.keys()):
        reason: str | None = base_skipped.get(pair_id) or other_skipped.get(pair_id)
        if reason is None and (pair_id not in base_pairs or pair_id not in other_pairs):
            reason = f"missing in {(other if pair_id in base_pairs else base).name}"
        if reason is None:
            matched.append((pair_id, base_pairs[pair_id], other_pairs[pair_id]))
        else:
            skipped.append((pair_id, reason))
    return matched, skipped


def _read_mapping(run: Path) -> tuple[dict[str, Entry], dict[str, str]]:
    data: dict[str, Any] = json.loads((run / MAPPING_NAME).read_text(encoding="utf-8"))
    pairs: dict[str, Entry] = {pair["pair"]: pair for pair in data["pairs"]}
    skipped: dict[str, str] = {item["pair"]: item["reason"] for item in data["skipped"]}
    return pairs, skipped


def main(argv: Sequence[str], quality_root: Path) -> int:
    """Replay pairs into a folder, or compare two replay folders; return 1 when a comparison finds differences."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality replay",
        description=(
            "Write each pair's Polish text (paired by timing and style, unpaired events in English) through the "
            "translation layout and subtitle writer, or compare two replay folders byte for byte or event by event."
        ),
    )
    parser.add_argument("roots", nargs="*", type=Path, help="pair folders or roots searched recursively")
    parser.add_argument("--out", type=Path, help="replay folder to write")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASE", "OTHER"), help="replay folders to compare")
    parser.add_argument("--events", action="store_true", help="compare event by event, leaving excluded events out")
    args: argparse.Namespace = parser.parse_args(argv)
    setup_mode(LoggerMode.SILENT, file=FileConfig(enable=False))
    if args.compare is not None and args.events:
        events: EventComparison = compare_events(*args.compare)
        print(_event_summary(events))
        return 1 if any(pair.different for pair in events.pairs) else 0
    if args.compare is not None:
        result: Comparison = compare(*args.compare)
        print(_summary(result))
        return 1 if result.different else 0
    if args.out is None:
        parser.error("give --out to replay or --compare to compare")
    roots: list[Path] = list(args.roots) or [quality_root / folder for folder in REPLAY_ROOTS]
    print(f"mapping {replay(roots, args.out)}", file=sys.stderr)
    return 0


def _summary(result: Comparison) -> str:
    lines: list[str] = [f"identical {len(result.identical)}", f"different {len(result.different)}"]
    lines.extend(f"  {pair_id}: {reason}" for pair_id, reason in result.different)
    lines.extend(_skipped_lines(result.skipped))
    return "\n".join(lines)


def _event_summary(result: EventComparison) -> str:
    identical: int = sum(pair.identical for pair in result.pairs)
    different: int = sum(pair.different for pair in result.pairs)
    excluded: int = sum(pair.excluded for pair in result.pairs)
    lines: list[str] = [f"pairs {len(result.pairs)}  identical {identical} different {different} excluded {excluded}"]
    lines.extend(
        f"  {pair.pair}: identical {pair.identical} different {pair.different} excluded {pair.excluded}"
        for pair in result.pairs
    )
    lines.extend(_skipped_lines(result.skipped))
    return "\n".join(lines)


def _skipped_lines(skipped: Sequence[tuple[str, str]]) -> list[str]:
    return [f"skipped {len(skipped)}", *(f"  {pair_id}: {reason}" for pair_id, reason in skipped)]
