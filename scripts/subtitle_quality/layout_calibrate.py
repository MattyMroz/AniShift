"""Calibrate the layout core weights by a linear program on the catalogue, the owner quiz and professional cues."""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from scipy.optimize import linprog  # type: ignore[import-untyped]
from scipy.sparse import coo_matrix  # type: ignore[import-untyped]

from anishift.paths import default_workspace_dir
from anishift.services.subtitles.layout import HARMS, Layout, candidates, chars_measure, dialogue_field, lay_out
from anishift.text.gaps import TIERS, GapKind
from scripts.subtitle_quality.layout_catalogue import CatalogueCase, faults, load, winner

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# ── Constants ─────────────────────────────────────────────────────────────────

PROFESSIONAL: Final[Path] = Path("experiments") / "lb-research" / "opus55" / "dataset.json"
"""Professional Polish cues with their two-line layouts, relative to the quality root."""

FAMILIES: Final[frozenset[str]] = frozenset({"nf", "amzn"})
"""Professional families used: Netflix and Amazon, the reference of the blind evaluation (spec §7.3)."""

SEED: Final[int] = 20261019
"""Seed of the blind sample drawn from the professional cues, which are then left out of the calibration."""

BLIND_SIZE: Final[int] = 160
"""Professional two-line cues in the blind sample (spec §7.3 asks for at least 150)."""

SENSITIVITY: Final[float] = 0.1
"""Relative change of every single weight whose effect on the chosen layouts is reported (spec §5.3)."""

KNEE_BAND: Final[tuple[float, float]] = (0.74, 0.80)
"""One-line widths between the owner's nearest decisions, q04 won at 0.74 and q11 lost at 0.80."""

POSITIVE: Final[float] = 1e-3
"""Smallest weight of a cut class, in units of the pair margin, so every class stays positive (spec §5.3)."""

TOLERANCE: Final[float] = 1e-6
"""Relative slack allowed when a stage keeps the optimum of the previous stage."""

CUT_HARMS: Final[tuple[str, ...]] = tuple(f"cut_{kind.value}" for kind in GapKind)
"""Harm names of the cut classes, ranked by ``TIERS``."""


@dataclass(frozen=True, slots=True)
class Pairs:
    """Preference rows ``f(loser) - f(winner)`` with the case each comes from."""

    hard: list[tuple[str, np.ndarray]] = field(default_factory=list)
    soft: list[tuple[str, np.ndarray]] = field(default_factory=list)
    professional: list[np.ndarray] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Fit:
    """Weights of one solve, or the reason none exist."""

    weights: dict[str, float] | None
    soft_loss: float = 0.0
    professional_loss: float = 0.0
    violated_professional: int = 0


# ── Constraints ───────────────────────────────────────────────────────────────


def vector(layout: Layout) -> np.ndarray:
    """Return the harm degrees of a layout in ``HARMS`` order."""
    return np.array([layout.harms.get(name, 0.0) for name in HARMS])


def case_pairs(case: CatalogueCase, *, morphology: bool) -> tuple[list[np.ndarray], list[np.ndarray], list[str]]:
    """Return hard rows, soft rows and level conflicts of one case against every candidate of its full space."""
    found: list[Layout] = candidates(case.text, case.field, case.measure, morphology=morphology)
    best: Layout | None = winner(case, found)
    if best is None:
        return [], [], []
    hard: list[np.ndarray] = []
    conflicts: list[str] = []
    for layout in found:
        if not faults(case, layout, found):
            continue
        if layout.rescue < best.rescue:
            conflicts.append(" / ".join(layout.lines))
        elif layout.rescue == best.rescue:
            hard.append(vector(layout) - vector(best))
    soft: list[np.ndarray] = []
    if case.soft and len(case.accept) > 1:
        alternative: list[Layout] = [layout for layout in found if layout.lines == case.accept[1].lines]
        soft = [vector(layout) - vector(best) for layout in alternative[:1] if layout.rescue == best.rescue]
    return hard, soft, conflicts


def professional_cues(quality_root: Path) -> list[dict[str, Any]]:
    """Return the Netflix and Amazon two-line cues of the professional dataset."""
    corpus: list[dict[str, Any]] = json.loads((quality_root / PROFESSIONAL).read_text(encoding="utf-8"))["corpus"]
    return [cue for cue in corpus if cue["family"] in FAMILIES and len(cue["gold"]) == 2]  # noqa: PLR2004


def blind_ids(cues: Sequence[dict[str, Any]]) -> list[str]:
    """Return the ids of the blind sample, drawn with the fixed seed."""
    return random.Random(SEED).sample(  # noqa: S311 - a reproducible sample, not a secret
        sorted(cue["id"] for cue in cues), BLIND_SIZE
    )


def professional_pairs(cues: Iterable[dict[str, Any]], *, morphology: bool) -> tuple[list[np.ndarray], int]:
    """Return rows preferring each professional layout to the other two-line layouts of its level; count skips."""
    rows: list[np.ndarray] = []
    skipped: int = 0
    for cue in cues:
        text: str = " ".join(cue["text"].split())
        gold: tuple[str, ...] = tuple(" ".join(line.split()) for line in cue["gold"])
        found: list[Layout] = [
            layout
            for layout in candidates(text, dialogue_field(), chars_measure, morphology=morphology)
            if len(layout.lines) == 2 and layout.rescue == (0, 0, 0)  # noqa: PLR2004
        ]
        golden: list[Layout] = [layout for layout in found if layout.lines == gold]
        if not golden:
            skipped += 1
            continue
        rows.extend(vector(layout) - vector(golden[0]) for layout in found if layout.lines != gold)
    return rows, skipped


def gather(
    cases: Sequence[CatalogueCase], *, morphology: bool
) -> tuple[dict[str, tuple[Any, ...]], dict[str, list[str]]]:
    """Return the hard and soft rows of every case and the level conflicts found."""
    rows: dict[str, tuple[Any, ...]] = {}
    conflicts: dict[str, list[str]] = {}
    for case in cases:
        hard, soft, conflict = case_pairs(case, morphology=morphology)
        rows[case.id] = (hard, soft)
        if conflict:
            conflicts[case.id] = conflict
    return rows, conflicts


# ── Linear program ────────────────────────────────────────────────────────────


def monotone_rows() -> list[np.ndarray]:
    """Return rows ``w_lower - w_upper <= 0`` for every pair of cut classes in neighbouring tiers."""
    rows: list[np.ndarray] = []
    for lower in GapKind:
        for upper in GapKind:
            if TIERS[upper] != TIERS[lower] + 1:
                continue
            row: np.ndarray = np.zeros(len(HARMS))
            row[HARMS.index(f"cut_{lower.value}")] = 1.0
            row[HARMS.index(f"cut_{upper.value}")] = -1.0
            rows.append(row)
    return rows


def solve(pairs: Pairs) -> Fit:
    """Return weights meeting every hard row with a margin, then nearest the soft rows, professionals and margin."""
    size: int = len(HARMS)
    soft_count: int = len(pairs.soft)
    pro_count: int = len(pairs.professional)
    width: int = size + soft_count + pro_count
    builder: _Rows = _Rows(width)
    for _, row in pairs.hard:
        builder.add({index: -value for index, value in enumerate(row)}, -1.0)
    for offset, (_, row) in enumerate(pairs.soft):
        builder.add({**{index: -value for index, value in enumerate(row)}, size + offset: -1.0}, 0.0)
    for offset, row in enumerate(pairs.professional):
        builder.add({**{index: -value for index, value in enumerate(row)}, size + soft_count + offset: -1.0}, -1.0)
    for row in monotone_rows():
        builder.add({index: value for index, value in enumerate(row) if value}, 0.0)
    bounds: list[tuple[float, float | None]] = [(POSITIVE if name in CUT_HARMS else 0.0, None) for name in HARMS] + [
        (0.0, None)
    ] * (soft_count + pro_count)
    soft_cost: np.ndarray = np.concatenate([np.zeros(size), np.ones(soft_count), np.zeros(pro_count)])
    pro_cost: np.ndarray = np.concatenate([np.zeros(size + soft_count), np.ones(pro_count)])
    margin_cost: np.ndarray = np.concatenate([np.ones(size), np.zeros(soft_count + pro_count)])
    values: np.ndarray | None = None
    for cost in (soft_cost, pro_cost, margin_cost):
        result: Any = linprog(cost, A_ub=builder.matrix(), b_ub=builder.bounds(), bounds=bounds, method="highs")
        if result.status != 0:
            return Fit(weights=None)
        values = result.x
        builder.add({index: value for index, value in enumerate(cost) if value}, float(result.fun) * (1 + TOLERANCE)
                    + TOLERANCE)  # fmt: skip
    assert values is not None  # noqa: S101 - the loop ran at least once
    slack: np.ndarray = values[size + soft_count :]
    return Fit(
        weights={name: float(values[index]) for index, name in enumerate(HARMS)},
        soft_loss=float(values[size : size + soft_count].sum()),
        professional_loss=float(slack.sum()),
        violated_professional=int((slack > TOLERANCE).sum()),
    )


class _Rows:
    """Sparse inequality rows ``A x <= b`` grown one row at a time."""

    def __init__(self, width: int) -> None:
        self._width: int = width
        self._rows: list[int] = []
        self._columns: list[int] = []
        self._values: list[float] = []
        self._bounds: list[float] = []

    def add(self, coefficients: Mapping[int, float], bound: float) -> None:
        """Append one row."""
        row: int = len(self._bounds)
        for column, value in coefficients.items():
            if value:
                self._rows.append(row)
                self._columns.append(column)
                self._values.append(value)
        self._bounds.append(bound)

    def matrix(self) -> Any:
        """Return the rows as a sparse matrix."""
        return coo_matrix((self._values, (self._rows, self._columns)), shape=(len(self._bounds), self._width)).tocsr()

    def bounds(self) -> np.ndarray:
        """Return the right-hand sides."""
        return np.array(self._bounds)


def feasible(rows: Mapping[str, tuple[Any, ...]], ids: Iterable[str]) -> bool:
    """Return whether the hard rows of ``ids`` admit weights meeting them with a margin."""
    pairs: Pairs = Pairs(hard=[(case, row) for case in ids for row in rows[case][0]])
    return solve(pairs).weights is not None


def conflict_set(rows: Mapping[str, tuple[Any, ...]], ids: Sequence[str]) -> list[str]:
    """Return a minimal set of cases whose hard rows cannot hold together (deletion filter)."""
    kept: list[str] = list(ids)
    for case in list(ids):
        trial: list[str] = [other for other in kept if other != case]
        if not feasible(rows, trial):
            kept = trial
    return kept


def conflict_sets(rows: Mapping[str, tuple[Any, ...]], ids: Sequence[str]) -> list[list[str]]:
    """Return minimal conflicting sets found one after another, setting aside the last case of each found set."""
    found: list[list[str]] = []
    aside: set[str] = set()
    while not feasible(rows, [case for case in ids if case not in aside]):
        conflict: list[str] = conflict_set(rows, [case for case in ids if case not in aside])
        found.append(conflict)
        aside.add(conflict[-1])
    return found


# ── Evaluation ────────────────────────────────────────────────────────────────


def evaluate(
    cases: Sequence[CatalogueCase], weights: Mapping[str, float], *, morphology: bool
) -> dict[str, dict[str, Any]]:
    """Return the chosen layout of every case in the full space and why it is not acceptable, if it is not."""
    results: dict[str, dict[str, Any]] = {}
    for case in cases:
        best: Layout = lay_out(case.text, case.field, case.measure, weights, morphology=morphology)
        found: list[Layout] = [*candidates(case.text, case.field, case.measure, morphology=morphology), best]
        results[case.id] = {
            "lines": list(best.lines),
            "scale": [best.scale.fx, best.scale.fy],
            "rescue": list(best.rescue),
            "flags": sorted(best.flags),
            "faults": faults(case, best, found),
        }
    return results


def calibrate(
    cases: Sequence[CatalogueCase], pro_rows: list[np.ndarray], *, morphology: bool, leave_one_out: bool
) -> dict[str, Any]:
    """Return weights, feasibility, catalogue results, leave-one-out results and sensitivity for one variant."""
    rows, conflicts = gather(cases, morphology=morphology)
    ids: list[str] = [case.id for case in cases]
    report: dict[str, Any] = {"morphology": morphology, "level_conflicts": conflicts}
    if not feasible(rows, ids):
        report["feasible"] = False
        report["conflict_sets"] = conflict_sets(rows, ids)
        return report
    fit: Fit = solve(_pairs(rows, ids, pro_rows))
    assert fit.weights is not None  # noqa: S101 - feasible hard rows always solve with soft professional rows
    report |= {
        "feasible": True,
        "weights": fit.weights,
        "soft_loss": fit.soft_loss,
        "professional_rows": len(pro_rows),
        "professional_loss": fit.professional_loss,
        "violated_professional": fit.violated_professional,
        "catalogue": evaluate(cases, fit.weights, morphology=morphology),
        "sensitivity": sensitivity(cases, fit.weights, morphology=morphology),
    }
    report["near_knee"] = near_knee(cases, report["catalogue"])
    if leave_one_out:
        report["leave_one_out"] = loo(cases, rows, pro_rows, morphology=morphology)
    return report


def _pairs(rows: Mapping[str, tuple[Any, ...]], ids: Iterable[str], pro_rows: list[np.ndarray]) -> Pairs:
    chosen: list[str] = list(ids)
    return Pairs(
        hard=[(case, row) for case in chosen for row in rows[case][0]],
        soft=[(case, row) for case in chosen for row in rows[case][1]],
        professional=pro_rows,
    )


def loo(
    cases: Sequence[CatalogueCase],
    rows: Mapping[str, tuple[Any, ...]],
    pro_rows: list[np.ndarray],
    *,
    morphology: bool,
) -> dict[str, list[str]]:
    """Return, per case, the faults of its layout under weights calibrated without every case of its event."""
    results: dict[str, list[str]] = {}
    for group in dict.fromkeys(case.group for case in cases):
        held: list[CatalogueCase] = [case for case in cases if case.group == group]
        rest: list[str] = [case.id for case in cases if case.group != group]
        fit: Fit = solve(_pairs(rows, rest, pro_rows))
        if fit.weights is None:
            results |= {case.id: ["no weights without this event"] for case in held}
            continue
        outcome: dict[str, dict[str, Any]] = evaluate(held, fit.weights, morphology=morphology)
        results |= {case_id: value["faults"] for case_id, value in outcome.items()}
    return results


def sensitivity(
    cases: Sequence[CatalogueCase], weights: Mapping[str, float], *, morphology: bool
) -> dict[str, list[str]]:
    """Return, per weight changed by the sensitivity step either way, the cases whose chosen layout changes."""
    base: dict[str, dict[str, Any]] = evaluate(cases, weights, morphology=morphology)
    changes: dict[str, list[str]] = {}
    for name, value in weights.items():
        if not value:
            continue
        for factor in (1 - SENSITIVITY, 1 + SENSITIVITY):
            shifted: dict[str, float] = {**weights, name: value * factor}
            outcome: dict[str, dict[str, Any]] = evaluate(cases, shifted, morphology=morphology)
            moved: list[str] = [
                case_id for case_id, result in outcome.items() if result["lines"] != base[case_id]["lines"]
            ]
            if moved:
                changes[f"{name} x{factor:.1f}"] = moved
    return changes


# ── Blind sample ──────────────────────────────────────────────────────────────


def blind_sample(cues: Sequence[dict[str, Any]], weights: Mapping[str, float], out: Path) -> dict[str, int]:
    """Write the blind A/B sheet of professional and core layouts, leaving identical ones out, and its separate key."""
    chosen: set[str] = set(blind_ids(cues))
    rng: random.Random = random.Random(SEED + 1)  # noqa: S311 - a reproducible shuffle, not a secret
    sheet: list[str] = []
    key: list[dict[str, Any]] = []
    picked: list[dict[str, Any]] = [cue for cue in cues if cue["id"] in chosen]
    rng.shuffle(picked)
    position: int = 0
    for cue in picked:
        text: str = " ".join(cue["text"].split())
        layouts: dict[str, tuple[str, ...]] = {
            "professional": tuple(" ".join(line.split()) for line in cue["gold"]),
            "core": _two_lines(text, weights, morphology=True),
        }
        entry: dict[str, Any] = {"id": cue["id"], "text": text, "layouts": {k: list(v) for k, v in layouts.items()}}
        if layouts["professional"] == layouts["core"]:
            key.append({**entry, "same": True})
            continue
        position += 1
        sources: list[str] = list(layouts)
        rng.shuffle(sources)
        letters: dict[str, str] = dict(zip("AB", sources, strict=True))
        sheet.append(f"#{position:03d}")
        sheet.extend(
            f" {letter}: {'  /  '.join(layouts[source])}   [{'/'.join(str(len(line)) for line in layouts[source])}]"
            for letter, source in letters.items()
        )
        sheet.append("")
        key.append({**entry, "same": False, "pos": position, "letters": letters})
    out.mkdir(parents=True, exist_ok=True)
    (out / "blind.txt").write_text("\n".join(sheet), encoding="utf-8", newline="\n")
    (out / "key.json").write_text(json.dumps({"seed": SEED, "key": key}, ensure_ascii=False, indent=1),
                                  encoding="utf-8", newline="\n")  # fmt: skip
    return {"sampled": len(picked), "judged": position, "same": len(picked) - position}


def near_knee(cases: Sequence[CatalogueCase], outcome: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return the cases whose one-line width falls between the owner's nearest one-line decisions."""
    found: dict[str, dict[str, Any]] = {}
    for case in cases:
        width: float = case.measure(case.text, 1.0)
        if KNEE_BAND[0] <= width <= KNEE_BAND[1] and case.field.length_knots:
            found[case.id] = {"width": round(width, 3), "chosen_lines": len(outcome[case.id]["lines"])}
    return found


def _two_lines(text: str, weights: Mapping[str, float], *, morphology: bool) -> tuple[str, ...]:
    found: list[Layout] = [
        layout
        for layout in candidates(text, dialogue_field(), chars_measure, morphology=morphology)
        if len(layout.lines) == 2  # noqa: PLR2004
    ]
    if not found:
        return (text,)
    return min(found, key=lambda layout: (layout.rescue, layout.score(weights))).lines


# ── Command line ──────────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Calibrate with and without morphology, write the results and optionally the blind sample."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="python -m scripts.subtitle_quality.layout_calibrate"
    )
    parser.add_argument("--quality-root", type=Path, default=default_workspace_dir() / ".quality")
    parser.add_argument("--out", type=Path, required=True, help="JSON file with the results of both variants")
    parser.add_argument("--blind", type=Path, help="folder for the blind sample sheet and its key")
    parser.add_argument("--no-loo", action="store_true", help="skip the leave-one-out check")
    arguments: argparse.Namespace = parser.parse_args(argv)
    cases: list[CatalogueCase] = load()
    cues: list[dict[str, Any]] = professional_cues(arguments.quality_root)
    held: set[str] = set(blind_ids(cues))
    training: list[dict[str, Any]] = [cue for cue in cues if cue["id"] not in held]
    results: dict[str, Any] = {"blind_size": len(held), "professional_cues": len(training)}
    for name, morphology in (("morphology", True), ("plain", False)):
        pro_rows, skipped = professional_pairs(training, morphology=morphology)
        results[name] = calibrate(cases, pro_rows, morphology=morphology, leave_one_out=not arguments.no_loo)
        results[name]["professional_skipped"] = skipped
        print(f"{name}: feasible={results[name]['feasible']}")
    if arguments.blind is not None and results["morphology"].get("weights"):
        results["blind"] = blind_sample(cues, results["morphology"]["weights"], arguments.blind)
    arguments.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
