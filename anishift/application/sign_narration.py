"""Choose the on-screen signs the narrator reads in the pauses its spoken lines leave."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from anishift.services.audio.timeline import plan_timeline
from anishift.services.audio.types import PlacementReason
from anishift.services.subtitles import SignCandidate
from anishift.services.subtitles.signs import SIGN_AFTER_MS, SIGN_MARGIN, place_weight_against

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from anishift.services.audio.types import NormalizedClip, TimelinePlan

__all__ = [
    "SignPlacement",
    "SignSelection",
    "free_intervals",
    "load_sign_candidates",
    "reachable_signs",
    "select_signs",
    "write_sign_candidates",
]

# ── Constants ─────────────────────────────────────────────────────────────────

SIGN_BREATH_MS: Final[int] = 200
"""Silence kept between a sign reading and any other reading on either side."""

_SMART: Final[str] = "smart"
"""Sign narration mode that weighs every sign against the pause it would be read in."""

type Interval = tuple[int, int | None]
"""Free narrator frames from a start up to an end, open when the reading may run on to the end of the file."""


@dataclass(frozen=True, slots=True)
class SignPlacement:
    """Where one accepted sign group is read: its start and end in whole milliseconds."""

    group: int
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class SignSelection:
    """Accepted sign readings and the decision taken on every candidate group, with its weight margin when weighed."""

    placements: tuple[SignPlacement, ...]
    decisions: tuple[tuple[int, str], ...]
    margins: tuple[tuple[int, float], ...]


def write_sign_candidates(candidates: Sequence[SignCandidate], destination: Path) -> Path:
    """Write sign candidates as private JSON for the synthesis task."""
    payload: list[dict[str, object]] = [
        {
            "group": candidate.group,
            "start_ms": candidate.start,
            "end_ms": candidate.end,
            "text": candidate.text,
            "key": candidate.key,
            "weight_for": candidate.weight_for,
            "weight_against": candidate.weight_against,
        }
        for candidate in candidates
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return destination


def load_sign_candidates(path: Path) -> tuple[SignCandidate, ...]:
    """Load sign candidates written by ``write_sign_candidates``."""
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        msg: str = "Sign candidates must be a list"
        raise TypeError(msg)
    return tuple(
        SignCandidate(
            int(item["group"]),
            int(item["start_ms"]),
            int(item["end_ms"]),
            str(item["text"]),
            str(item["key"]),
            float(item["weight_for"]),
            float(item["weight_against"]),
        )
        for item in payload
    )


def free_intervals(plan: TimelinePlan) -> tuple[Interval, ...]:
    """Return the narrator frames no spoken line needs, each kept a breath away from the lines around it."""
    breath: int = _frames(SIGN_BREATH_MS, plan.sample_rate)
    raw: list[Interval] = []
    previous_end: int = 0
    for placement in plan.placements:
        if placement.reason is PlacementReason.ON_TIME:
            raw.append((previous_end, placement.start_frame))
        previous_end = placement.end_frame
    raw.append((previous_end, None))
    narrowed: list[Interval] = [(start + breath, None if end is None else end - breath) for start, end in raw]
    return tuple((start, end) for start, end in narrowed if end is None or start < end)


def reachable_signs(
    candidates: Sequence[SignCandidate], intervals: Sequence[Interval], sample_rate: int
) -> tuple[SignCandidate, ...]:
    """Return the candidates with free frames inside the span their reading may take."""
    return tuple(
        candidate
        for candidate in candidates
        if any(_overlap(interval, _area(candidate, sample_rate)) for interval in intervals)
    )


def select_signs(
    candidates: Sequence[SignCandidate],
    clips: Mapping[int, NormalizedClip],
    lines: tuple[NormalizedClip, ...],
    mode: str,
) -> SignSelection:
    """Place sign readings greedily in sign order without moving a single spoken line."""
    baseline: TimelinePlan | None = plan_timeline(lines)
    if baseline is None:
        return SignSelection((), tuple((candidate.group, "no_pause") for candidate in candidates), ())
    selector = _Selector(baseline, lines, mode)
    for candidate in candidates:
        selector.consider(candidate, clips.get(candidate.group))
    return SignSelection(tuple(selector.placements), tuple(selector.decisions), tuple(selector.margins))


class _Selector:
    __slots__ = (
        "_accepted",
        "_baseline_starts",
        "_intervals",
        "_last_read_ms",
        "_lines",
        "_mode",
        "_sample_rate",
        "decisions",
        "margins",
        "placements",
    )

    def __init__(self, baseline: TimelinePlan, lines: tuple[NormalizedClip, ...], mode: str) -> None:
        self._lines: tuple[NormalizedClip, ...] = lines
        self._mode: str = mode
        self._sample_rate: int = baseline.sample_rate
        self._baseline_starts: dict[str, int] = {item.request_id: item.start_frame for item in baseline.placements}
        self._intervals: list[Interval] = list(free_intervals(baseline))
        self._accepted: list[NormalizedClip] = []
        self._last_read_ms: dict[str, float] = {}
        self.placements: list[SignPlacement] = []
        self.decisions: list[tuple[int, str]] = []
        self.margins: list[tuple[int, float]] = []

    def consider(self, candidate: SignCandidate, clip: NormalizedClip | None) -> None:
        area: tuple[int, int] = _area(candidate, self._sample_rate)
        if not any(_overlap(interval, area) for interval in self._intervals):
            self.decisions.append((candidate.group, "no_pause"))
            return
        if clip is None:
            self.decisions.append((candidate.group, "missing"))
            return
        choice: tuple[int, int] | None = self._place(candidate, clip.frame_count, area)
        if choice is None:
            return
        index, start_ms = choice
        placed: NormalizedClip = self._timed(clip, start_ms)
        if not self._keeps_lines(placed):
            self.decisions.append((candidate.group, "late"))
            return
        self._accept(candidate, placed, index)

    def _place(self, candidate: SignCandidate, frames: int, area: tuple[int, int]) -> tuple[int, int] | None:
        area_start, area_end = area
        fitted: bool = False
        best_margin: float | None = None
        for index, (start, end) in enumerate(self._intervals):
            start_ms: int = math.ceil(max(area_start, start) * 1000 / self._sample_rate)
            reading: int = _frames(start_ms, self._sample_rate)
            limit: int = _bounded(end, area_end)
            if reading + frames > limit:
                continue
            fitted = True
            if self._mode != _SMART:
                return index, start_ms
            margin: float = candidate.weight_for - self._against(candidate, frames, reading, end)
            best_margin = margin if best_margin is None else max(best_margin, margin)
            if margin >= SIGN_MARGIN:
                self.margins.append((candidate.group, margin))
                return index, start_ms
        if best_margin is not None:
            self.margins.append((candidate.group, best_margin))
        self.decisions.append((candidate.group, "weight" if fitted else "no_pause"))
        return None

    def _against(self, candidate: SignCandidate, frames: int, reading: int, end: int | None) -> float:
        slack: float = math.inf if end is None else (end - reading - frames) / frames
        reading_ms: float = reading * 1000 / self._sample_rate
        overrun_ms: float = (reading + frames) * 1000 / self._sample_rate - candidate.end
        previous: float | None = self._last_read_ms.get(candidate.key)
        return place_weight_against(
            candidate.weight_against,
            slack=slack,
            overrun_ms=overrun_ms,
            repeat_gap_ms=None if previous is None else reading_ms - previous,
        )

    def _timed(self, clip: NormalizedClip, start_ms: int) -> NormalizedClip:
        end_ms: int = start_ms + math.ceil(clip.frame_count * 1000 / self._sample_rate)
        return replace(clip, timed_clip=replace(clip.timed_clip, start_ms=start_ms, end_ms=end_ms))

    def _keeps_lines(self, placed: NormalizedClip) -> bool:
        plan: TimelinePlan | None = plan_timeline((*self._lines, *self._accepted, placed))
        if plan is None:
            return False
        return all(
            item.start_frame == self._baseline_starts[item.request_id]
            for item in plan.placements
            if item.request_id in self._baseline_starts
        )

    def _accept(self, candidate: SignCandidate, placed: NormalizedClip, index: int) -> None:
        breath: int = _frames(SIGN_BREATH_MS, self._sample_rate)
        start: int = _frames(placed.timed_clip.start_ms, self._sample_rate)
        interval_start, interval_end = self._intervals.pop(index)
        pieces: list[Interval] = []
        if start - breath > interval_start:
            pieces.append((interval_start, start - breath))
        after: int = start + placed.frame_count + breath
        if interval_end is None or after < interval_end:
            pieces.append((after, interval_end))
        self._intervals[index:index] = pieces
        self._accepted.append(placed)
        self._last_read_ms[candidate.key] = start * 1000 / self._sample_rate
        timed = placed.timed_clip
        self.placements.append(SignPlacement(candidate.group, timed.start_ms, timed.end_ms))
        self.decisions.append((candidate.group, "read"))


def _area(candidate: SignCandidate, sample_rate: int) -> tuple[int, int]:
    return _frames(max(candidate.start, 0), sample_rate), _frames(max(candidate.end, 0) + SIGN_AFTER_MS, sample_rate)


def _overlap(interval: Interval, area: tuple[int, int]) -> bool:
    start, end = interval
    return max(start, area[0]) < _bounded(end, area[1])


def _bounded(end: int | None, limit: int) -> int:
    return limit if end is None else min(end, limit)


def _frames(milliseconds: int, sample_rate: int) -> int:
    return (milliseconds * sample_rate + 500) // 1000
