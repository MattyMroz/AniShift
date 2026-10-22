"""Text layout catalogue: quiz answers and hard cases with their acceptable layouts, measured once with real fonts."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from anishift.paths import default_workspace_dir
from anishift.services.fonts import FontIndex
from anishift.services.subtitles.fitting import sign_input
from anishift.services.subtitles.geometry import RenderProfile, measure_text
from anishift.services.subtitles.layout import Field, Flag, Layout, chars_measure, dialogue_field, sign_field
from anishift.services.subtitles.linebreak import tagged_line
from anishift.services.subtitles.restyle import DialogueFont, restyle_dialogue, restyle_signs, with_family
from anishift.services.subtitles.service import load_subtitles, split_subtitles
from anishift.services.subtitles.types import LayoutReport
from anishift.text.gaps import TIERS, GapKind, gaps
from scripts.subtitle_quality.episode import SOURCE_NAME, pair_fonts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles.layout import Measure
    from anishift.services.subtitles.types import FontSources, SubtitleSplit

# ── Constants ─────────────────────────────────────────────────────────────────

CATALOGUE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "tests" / "services" / "subtitles" / "data" / "text_layout_catalogue.json"
)
"""Catalogue file: authored cases plus the measurements this tool writes into them."""

SCALE_TOLERANCE: Final[float] = 0.03
"""Largest scale difference that still matches a quiz variant, which the owner saw at a rounded size."""

SCREEN_WIDTH: Final[float] = 1920.0
"""Screen width in pixels the quiz notes give frame sizes in."""

SCREEN_HEIGHT: Final[float] = 1080.0
"""Screen height in pixels letter heights are expressed in."""

PHRASE_TIER: Final[int] = TIERS[GapKind.PHRASE]
"""Highest gap tier that still counts as a phrase boundary for the ``phrase`` rule."""

RAGGED_HARM: Final[str] = "imbalance_30"
"""Harm past the top imbalance knot of spec §4.4, the very ragged shape the ``not_ragged`` rule forbids."""

_RE_LINES: Final[re.Pattern[str]] = re.compile(r"lines:(\d+)")
"""Rule demanding an exact line count."""


@dataclass(frozen=True, slots=True)
class Accepted:
    """One acceptable layout: lines and, for a sign, the scale the owner saw."""

    lines: tuple[str, ...]
    fx: float | None = None
    fy: float | None = None


@dataclass(frozen=True, slots=True)
class CatalogueCase:
    """One measured catalogue case ready for the layout core."""

    id: str
    group: str
    source: str
    text: str
    field: Field
    measure: Measure
    accept: tuple[Accepted, ...]
    rule: str | None
    if_fits: bool
    soft: bool
    forbid: frozenset[tuple[str, str]]
    forbid_lines: frozenset[str]


# ── Loading ───────────────────────────────────────────────────────────────────


def load(path: Path = CATALOGUE) -> list[CatalogueCase]:
    """Return the measured core cases of the catalogue."""
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return [_case(entry) for entry in raw if entry["scope"] == "core"]


def _case(entry: dict[str, Any]) -> CatalogueCase:
    measured: dict[str, Any] = entry["measure"]
    return CatalogueCase(
        id=entry["id"],
        group=f"{entry['pair']}#{entry['event']}" if "pair" in entry else entry["id"],
        source=entry["source"],
        text=entry["text"],
        field=_field(entry["field"], measured),
        measure=_measure(measured),
        accept=tuple(_accepted(item) for item in entry["accept"]),
        rule=entry.get("accept_rule"),
        if_fits=entry.get("if_fits", False),
        soft=entry.get("soft", False),
        forbid=frozenset(tuple(pair.split("|", 1)) for pair in entry.get("forbid", ())),  # type: ignore[misc]
        forbid_lines=frozenset(entry.get("forbid_lines", ())),
    )


def _accepted(item: dict[str, Any]) -> Accepted:
    return Accepted(lines=tuple(item["lines"]), fx=item.get("fx"), fy=item.get("fy"))


def _field(spec: dict[str, Any], measured: dict[str, Any]) -> Field:
    breaks: frozenset[int] = frozenset(spec.get("breaks", ()))
    styles: frozenset[int] = frozenset(spec.get("style_breaks", ()))
    if spec["kind"] == "dialogue":
        return replace(dialogue_field(), breaks=breaks, style_breaks=styles)
    if "field" in measured:
        return _stored_field(measured["field"])
    field: Field = sign_field(
        source_lines=measured["original_lines"],
        template=tuple(measured.get("template", ())),
        letter_height=measured["letter_height"],
        max_width=measured.get("max_width", 1.0),
        height_lines=measured.get("height_lines"),
        breaks=breaks,
        style_breaks=styles,
    )
    if "blocks" not in spec:
        return field
    return replace(field, blocks=tuple(spec["blocks"]), runs=tuple(spec["runs"]), anchor_row=spec["anchor_row"])


def _measure(measured: dict[str, Any]) -> Measure:
    if measured["kind"] == "chars":
        factor: float = measured.get("char_width", 0.0) / chars_measure("x", 1.0) if "char_width" in measured else 1.0
        return lambda line, fx: chars_measure(line, fx) * factor
    words: dict[str, float] = measured["words"]
    space: float = measured["space"]
    edge: float = measured["edge"]

    def width(line: str, fx: float) -> float:
        tokens: list[str] = line.split(" ")
        return fx * (sum(words[token] for token in tokens) + space * (len(tokens) - 1)) + edge

    return width


# ── Acceptance ────────────────────────────────────────────────────────────────


def faults(case: CatalogueCase, layout: Layout, found: Sequence[Layout]) -> list[str]:
    """Return why ``layout`` is not acceptable for ``case`` among the candidates ``found``; empty when it is."""
    reasons: list[str] = [
        f"forbidden cut {left}|{right}" for left, right in _cuts(layout) if (left, right) in case.forbid
    ]
    reasons += [f"forbidden line {line!r}" for line in layout.lines if line in case.forbid_lines]
    if not _acceptable(case, layout, found):
        reasons.append("not in the acceptable set")
    return reasons


def winner(case: CatalogueCase, found: Sequence[Layout]) -> Layout | None:
    """Return the candidate matching the first acceptable layout of ``case``, or None when none is listed."""
    for item in case.accept:
        for layout in found:
            if _matches(item, layout) and not faults(case, layout, found):
                return layout
    return None


def _acceptable(case: CatalogueCase, layout: Layout, found: Sequence[Layout]) -> bool:
    listed: bool = any(_matches(item, layout) for item in case.accept)
    if case.if_fits:
        fitting: list[Layout] = [other for other in found if any(_matches(i, other) for i in case.accept)]
        if any(Flag.OUTSIDE not in other.flags for other in fitting):
            return listed and Flag.OUTSIDE not in layout.flags
    if case.rule is None:
        return listed
    return _ruled(case, layout, found)


def _ruled(case: CatalogueCase, layout: Layout, found: Sequence[Layout]) -> bool:
    rule: str = case.rule or ""
    exact: re.Match[str] | None = _RE_LINES.fullmatch(rule)
    if exact is not None:
        return len(layout.lines) == int(exact.group(1)) and Flag.OUTSIDE not in layout.flags
    if rule == "any":
        return True
    if rule == "source_lines":
        return len(layout.lines) == case.field.preferred_lines
    if rule in {"not_ragged", "no_hourglass", "blocks"}:
        return _shaped_rule(rule, layout)
    if rule == "phrase":
        phrased: list[Layout] = [other for other in found if _phrased_or_listed(case, other)]
        fewest: int = min((len(other.lines) for other in phrased), default=0)
        return _phrased_or_listed(case, layout) and len(layout.lines) == fewest
    msg = f"Unknown catalogue rule {rule!r} in {case.id}"
    raise ValueError(msg)


def _shaped_rule(rule: str, layout: Layout) -> bool:
    if rule == "blocks":
        unreadable: bool = bool({Flag.OUTSIDE, Flag.SMALL, Flag.SHRUNK} & layout.flags)
        return layout.scale.fy == 1 and not unreadable and min(layout.spacing, default=0) >= 0
    if Flag.OUTSIDE in layout.flags:
        return False
    return not layout.harms.get(RAGGED_HARM, 0.0) if rule == "not_ragged" else not _hourglass(layout)


def _phrased_or_listed(case: CatalogueCase, layout: Layout) -> bool:
    if Flag.OUTSIDE in layout.flags or len(layout.lines) == 1:
        return False
    if any(_matches(item, layout) for item in case.accept):
        return True
    words: list[str] = case.text.split(" ")
    kinds: list[GapKind] = [gap.kind for gap in gaps(words)]
    cuts: list[int] = []
    position: int = -1
    for line in layout.lines[:-1]:
        position += len(line.split(" "))
        cuts.append(position)
    return all(TIERS[kinds[cut]] <= PHRASE_TIER for cut in cuts) and not any(
        pair in case.forbid for pair in _cuts(layout)
    )


def _hourglass(layout: Layout) -> bool:
    sizes: list[int] = [len(line) for line in layout.lines]
    return any(sizes[i] < sizes[i - 1] and sizes[i] < sizes[i + 1] for i in range(1, len(sizes) - 1))


def _matches(item: Accepted, layout: Layout) -> bool:
    if item.lines != layout.lines:
        return False
    if item.fx is None or item.fy is None:
        return True
    return abs(layout.scale.fx - item.fx) <= SCALE_TOLERANCE and abs(layout.scale.fy - item.fy) <= SCALE_TOLERANCE


def _cuts(layout: Layout) -> list[tuple[str, str]]:
    return [(upper.split(" ")[-1], lower.split(" ")[0]) for upper, lower in pairwise(layout.lines)]


# ── Measurement ───────────────────────────────────────────────────────────────


def measure_catalogue(path: Path, quality_root: Path, font: DialogueFont) -> int:
    """Write word, space and field measurements into every core case taken from a script; return their count."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    measured: int = 0
    for entry in document["cases"]:
        if entry["scope"] != "core" or "pair" not in entry:
            continue
        entry["measure"] = _measurement(entry, quality_root, font)
        measured += 1
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return measured


def _measurement(entry: dict[str, Any], quality_root: Path, font: DialogueFont) -> dict[str, Any]:
    split: SubtitleSplit = split_subtitles(load_subtitles(quality_root / entry["pair"] / SOURCE_NAME), kind="ass")
    restyled: SSAFile = restyle_dialogue(split.subs, split.decisions, font, LayoutReport())
    fonts: FontSources = pair_fonts(quality_root / entry["pair"])
    profile: RenderProfile = RenderProfile.from_subs(
        restyled, FontIndex.build((*fonts.episode, *font.files), fonts.system)
    )
    event: SSAEvent = [line for line in restyled if line.type == "Dialogue"][entry["event"]]
    spec: dict[str, Any] = entry["field"]
    tags: str = spec.get("tags", "")
    scale: float = profile.play_res_x

    def ink(text: str) -> float:
        return measure_text(event, tags + text, profile).width / scale

    edge: float = measure_text(event, tags + "x", profile).edge / scale
    pair_ink: float = ink("xx")
    result: dict[str, Any] = {
        "kind": "words",
        "words": {word: round(ink(f"x{word}x") - pair_ink, 6) for word in sorted(set(entry["text"].split(" ")))},
        "space": round(ink("x x") - ink("xx"), 6),
        "edge": round(edge, 6),
    }
    if spec["kind"] == "sign":
        return _production_measurement(entry, quality_root, font)
    return result


def _production_measurement(entry: dict[str, Any], quality_root: Path, font: DialogueFont) -> dict[str, Any]:
    split: SubtitleSplit = split_subtitles(load_subtitles(quality_root / entry["pair"] / SOURCE_NAME), kind="ass")
    restyled, clones = restyle_signs(split.subs, split.decisions, font)
    fonts: FontSources = pair_fonts(quality_root / entry["pair"])
    index: FontIndex = FontIndex.build((*fonts.episode, *font.files), fonts.system)
    profile: RenderProfile = RenderProfile.from_subs(restyled, index)
    source: SSAEvent = [line for line in restyled if line.type == "Dialogue"][entry["event"]]
    target: SSAEvent = source.copy()
    if entry["event"] in clones:
        target.style = clones[entry["event"]]
        target.text = with_family(target.text, font.family)
    target.text = tagged_line(target, _positioned(entry), profile)
    text, field, measure = sign_input(source, target, profile)
    tokens: list[str] = text.split(" ")
    space: float = measure(" ".join(tokens[:2]), 1.0) - measure(tokens[0], 1.0) - measure(tokens[1], 1.0)
    spec: dict[str, Any] = entry["field"]
    to_screen: float = SCREEN_HEIGHT / profile.play_res_y
    pitch: float = measure_text(target, "Xg\\NXg", profile).height - measure_text(target, "Xg", profile).height
    max_width: float = spec["max_width_px"] / SCREEN_WIDTH if "max_width_px" in spec else field.max_width
    height: float | None = spec["height_px"] / (to_screen * pitch) if "height_px" in spec else field.height_lines
    return {
        "kind": "words",
        "words": {token: round(measure(token, 1.0), 6) for token in sorted(set(tokens))},
        "space": round(space, 6) if len(tokens) > 1 else 0.0,
        "edge": 0.0,
        "field": {
            "source_lines": field.preferred_lines,
            "template": [round(width, 6) for width in field.template],
            "letter_height": round(field.letter_height, 3),
            "max_width": None if math.isinf(max_width) else round(max_width, 6),
            "height_lines": None if height is None else round(height, 4),
            "breaks": sorted(field.breaks),
            "style_breaks": sorted(field.style_breaks),
            "blocks": list(field.blocks),
            "runs": list(field.runs),
            "anchor_row": field.anchor_row,
        },
    }


def _positioned(entry: dict[str, Any]) -> str:
    breaks: frozenset[int] = frozenset(entry["field"].get("breaks", ()))
    words: list[str] = entry["text"].split(" ")
    return "".join(word + ("\\N" if index in breaks else " ") for index, word in enumerate(words)).strip()


def _stored_field(stored: dict[str, Any]) -> Field:
    field: Field = sign_field(
        source_lines=stored["source_lines"],
        template=tuple(stored["template"]),
        letter_height=stored["letter_height"],
        max_width=math.inf if stored["max_width"] is None else stored["max_width"],
        height_lines=stored["height_lines"],
        breaks=frozenset(stored["breaks"]),
        style_breaks=frozenset(stored["style_breaks"]),
    )
    if not stored["blocks"]:
        return field
    return replace(field, blocks=tuple(stored["blocks"]), runs=tuple(stored["runs"]), anchor_row=stored["anchor_row"])


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the catalogue with the fonts of the quality pairs and the owner's dialogue font."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality.layout_catalogue"
    )
    parser.add_argument("--dialogue-font", type=Path, required=True, help="font file drawing dialogue and signs")
    parser.add_argument("--quality-root", type=Path, default=default_workspace_dir() / ".quality")
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE)
    arguments: argparse.Namespace = parser.parse_args(argv)
    font: DialogueFont = DialogueFont.from_file(arguments.dialogue_font)
    count: int = measure_catalogue(arguments.catalogue, arguments.quality_root, font)
    print(f"measured {count} cases into {arguments.catalogue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
