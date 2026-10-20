"""Text layout catalogue: quiz answers and hard cases with their acceptable layouts, measured once with real fonts."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from anishift.paths import default_workspace_dir
from anishift.services.fonts import FontIndex
from anishift.services.fonts.index import system_font_paths
from anishift.services.subtitles.geometry import RenderProfile, measure_text
from anishift.services.subtitles.layout import Field, Flag, Layout, chars_measure, dialogue_field, sign_field
from anishift.services.subtitles.service import load_subtitles
from anishift.text.gaps import TIERS, GapKind, gaps
from scripts.subtitle_quality.episode import FONTS_NAME

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.subtitles.layout import Measure

# ── Constants ─────────────────────────────────────────────────────────────────

CATALOGUE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "tests" / "services" / "subtitles" / "data" / "text_layout_catalogue.json"
)
"""Catalogue file: authored cases plus the measurements this tool writes into them."""

BASELINE: Final[Path] = Path("experiments") / "v4-hard" / "baseline-font"
"""Input-state scripts with the owner's dialogue font, relative to the quality root."""

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

_RE_FONT_SIZE: Final[re.Pattern[str]] = re.compile(r"\\fs(\d+(?:\.\d+)?)")
"""Font size override tag of an ASS event."""


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
    return sign_field(
        source_lines=measured["original_lines"],
        template=tuple(measured.get("template", ())),
        letter_height=measured["letter_height"],
        max_width=measured.get("max_width", 1.0),
        height_lines=measured.get("height_lines"),
        breaks=breaks,
        style_breaks=styles,
    )


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
    if rule == "not_ragged":
        return Flag.OUTSIDE not in layout.flags and not layout.harms.get(RAGGED_HARM, 0.0)
    if rule == "no_hourglass":
        return Flag.OUTSIDE not in layout.flags and not _hourglass(layout)
    if rule == "phrase":
        phrased: list[Layout] = [other for other in found if _phrased_or_listed(case, other)]
        fewest: int = min((len(other.lines) for other in phrased), default=0)
        return _phrased_or_listed(case, layout) and len(layout.lines) == fewest
    msg = f"Unknown catalogue rule {rule!r} in {case.id}"
    raise ValueError(msg)


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


def measure_catalogue(path: Path, quality_root: Path, fonts: Path) -> int:
    """Write word, space and field measurements into every core case taken from a script; return their count."""
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    measured: int = 0
    for entry in document["cases"]:
        if entry["scope"] != "core" or "pair" not in entry:
            continue
        entry["measure"] = _measurement(entry, quality_root, fonts)
        measured += 1
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    return measured


def _measurement(entry: dict[str, Any], quality_root: Path, fonts: Path) -> dict[str, Any]:
    pair: Path = Path(entry["pair"])
    subs: SSAFile = load_subtitles(quality_root / BASELINE / pair.parent / f"{pair.name}.pl.ass")
    folder: Path = quality_root / pair / FONTS_NAME
    episode: list[Path] = sorted(folder.iterdir()) if folder.is_dir() else []
    index: FontIndex = FontIndex.build([*episode, *sorted(fonts.iterdir())], system_font_paths())
    profile: RenderProfile = RenderProfile.from_subs(subs, index)
    event: SSAEvent = [line for line in subs if line.type == "Dialogue"][entry["event"]]
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
        result |= _sign_measurement(spec, event, profile, tags)
    return result


def _sign_measurement(spec: dict[str, Any], event: SSAEvent, profile: RenderProfile, tags: str) -> dict[str, Any]:
    originals: list[str] = [line.strip() for line in spec["original"].split(" / ") if line.strip()]
    scale: float = profile.play_res_x
    template: list[float] = [round(measure_text(event, tags + line, profile).width / scale, 6) for line in originals]
    one: float = measure_text(event, tags + "Xg", profile).height
    pitch: float = measure_text(event, tags + "Xg\\NXg", profile).height - one
    to_screen: float = SCREEN_HEIGHT / profile.play_res_y
    result: dict[str, Any] = {
        "original_lines": len(originals),
        "letter_height": round(_font_size(event, profile, tags) * to_screen, 3),
    }
    if not spec.get("song"):
        result["template"] = template
    if "max_width_px" in spec:
        result["max_width"] = round(spec["max_width_px"] / SCREEN_WIDTH, 6)
    if "height_px" in spec:
        result["height_lines"] = round(spec["height_px"] / (to_screen * pitch), 4)
    return result


def _font_size(event: SSAEvent, profile: RenderProfile, tags: str) -> float:
    override: re.Match[str] | None = _RE_FONT_SIZE.search(tags)
    if override is not None:
        return float(override.group(1))
    return float(profile.styles[event.style].fontsize)


def main(argv: Sequence[str] | None = None) -> int:
    """Measure the catalogue with the fonts of the quality pairs and the owner's dialogue font."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality.layout_catalogue"
    )
    parser.add_argument("--fonts", type=Path, required=True, help="folder with the owner's dialogue font files")
    parser.add_argument("--quality-root", type=Path, default=default_workspace_dir() / ".quality")
    parser.add_argument("--catalogue", type=Path, default=CATALOGUE)
    arguments: argparse.Namespace = parser.parse_args(argv)
    count: int = measure_catalogue(arguments.catalogue, arguments.quality_root, arguments.fonts)
    print(f"measured {count} cases into {arguments.catalogue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
