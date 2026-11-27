"""Record real episode searches and compare the release verdicts two code versions give on them."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

from anishift.application.episode_identity import classify
from anishift.application.episode_selection import (
    AniZipMapping,
    EpisodeOffer,
    FranchiseGraph,
    LibraryGraph,
    franchise_traversal,
    identity_target,
    visible,
)
from anishift.application.subscription_choice import release_hash
from anishift.errors import AniShiftError
from anishift.paths import quality_dir
from anishift.services.catalog import AniListCatalog

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
"""Checkout whose test support replays the recordings."""
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests" / "application")]

import reference_support as support  # noqa: E402
from test_acquisition_reference import _actual  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────────

DATASET: Final[Path] = quality_dir() / "releases"
"""Default dataset root: recorded cases, verdict files and reports."""
REFERENCE: Final[Path] = support.REFERENCE
"""Reference cases accepted by the owner, replayed beside the dataset."""
CASE_GLOB: Final[str] = "[0-9]*-[0-9]*.json.gz"
"""File name pattern of one recorded case."""
ANILIST_HOST: Final[str] = "graphql.anilist.co"
"""Host whose limit the owner's resident shares."""
ANILIST_GAP_S: Final[float] = 4.1
"""Pause between AniList requests, at most 15 per minute."""
SOURCE_GAP_S: Final[float] = 1.0
"""Pause between two requests to one other host."""
RETRY_STATUS: Final[int] = 429
"""Status that makes the recorder wait and ask again."""
RETRY_WAIT_S: Final[float] = 60.0
"""Wait after a 429 answer without a Retry-After header."""
ATTEMPTS: Final[int] = 3
"""Requests sent for one recorded answer at most."""
YEAR: Final[re.Pattern[str]] = re.compile(r"\b(?:19|20)\d{2}\b")
"""Calendar year inside a release or file name."""


@dataclass
class Recorder:
    """Answer each request from the real network once, one request at a time, and keep the answer for replay."""

    transport: httpx.BaseTransport
    responses: list[dict[str, Any]] = field(default_factory=list)
    used: set[int] = field(default_factory=set)
    rows: dict[support.RequestKey, int] = field(default_factory=dict)
    sent: dict[str, float] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Return the recorded answer to *request*, fetching it first when it is new."""
        with self.lock:
            body: str | None = request.content.decode() if request.method == "POST" else None
            key: support.RequestKey = support.request_key(request.method, request.url, body)
            if key not in self.rows:
                self.rows[key] = len(self.responses)
                self.responses.append(self._fetch(request, body))
            self.used.add(self.rows[key])
            return support.Replay({key: self.responses[self.rows[key]]})(request)

    def _fetch(self, request: httpx.Request, body: str | None) -> dict[str, Any]:
        row: dict[str, Any] = {"method": request.method, "url": str(request.url)}
        if body is not None:
            row["request_body"] = body
        host: str = request.url.host
        gap: float = ANILIST_GAP_S if host == ANILIST_HOST else SOURCE_GAP_S
        for _ in range(ATTEMPTS):
            time.sleep(max(0.0, self.sent.get(host, 0.0) + gap - time.monotonic()))
            self.sent[host] = time.monotonic()
            try:
                response: httpx.Response = self.transport.handle_request(request)
                response.read()
            except httpx.TransportError as error:
                return {**row, "error": repr(error)}
            if response.status_code != RETRY_STATUS:
                break
            time.sleep(float(response.headers.get("retry-after", RETRY_WAIT_S)) + 1)
        return {**row, "status": response.status_code, "body": response.text}


def record(cases: list[tuple[int, int]], directory: Path) -> None:
    """Record the manual search and the subscription check of each case not recorded yet."""
    directory.mkdir(parents=True, exist_ok=True)
    transport: httpx.HTTPTransport = httpx.HTTPTransport()
    try:
        for anilist_id, number in cases:
            path: Path = directory / f"{anilist_id}-{number}.json.gz"
            if path.exists():
                continue
            document: dict[str, Any] | None = _record_case(Recorder(transport), anilist_id, number)
            if document is not None:
                path.write_bytes(gzip.compress(json.dumps(document, ensure_ascii=False).encode()))
                print(f"{path.name}: {len(document['responses'])} responses", flush=True)
    finally:
        transport.close()


def _record_case(recorder: Recorder, anilist_id: int, number: int) -> dict[str, Any] | None:
    case: str = f"{anilist_id}-{number}"
    document: dict[str, Any] = {
        "case": case,
        "anilist": {"id": anilist_id},
        "number": number,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "notes": {},
        "modes": {},
        "responses": recorder.responses,
    }
    runs: tuple[tuple[str, Any], ...] = (("manual", support.manual_search), ("subscription", support.subscription))
    for mode, run in runs:
        recorder.used.clear()
        try:
            run(document, recorder)
        except (AniShiftError, ValueError, LookupError, StopIteration) as error:
            print(f"{case} {mode}: skipped, {error!r}", flush=True)
            return None
        document["modes"][mode] = sorted(recorder.used)
    return document


def decision_cases(decisions: Path) -> list[tuple[int, int]]:
    """Return the first and last episode the owner's decisions name per entry, episode 1 when they name none."""
    numbers: dict[int, set[int]] = {}
    for line in decisions.read_text(encoding="utf-8").splitlines():
        key: Any = json.loads(line).get("key") if line.strip() else None
        if isinstance(key, dict) and isinstance(key.get("anilist_id"), int):
            known: set[int] = numbers.setdefault(key["anilist_id"], set())
            if isinstance(key.get("number"), int):
                known.add(key["number"])
    return [
        (anilist_id, number)
        for anilist_id, known in sorted(numbers.items())
        for number in sorted({min(known, default=1), max(known, default=1)})
    ]


def verdicts(directories: list[Path], out: Path) -> None:
    """Replay every recorded case with the importable code and save each row's verdict and the choices."""
    results: dict[str, Any] = {}
    for directory in directories:
        for path in sorted(directory.glob(CASE_GLOB)):
            document: dict[str, Any] = json.loads(gzip.decompress(path.read_bytes()))
            results[f"{directory.name}/{document['case']}"] = _replayed(document)
            print(document["case"], flush=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _replayed(document: dict[str, Any]) -> dict[str, Any]:
    manual: support.Replay = support.Replay.of(document, "manual")
    offer: EpisodeOffer
    target: dict[str, object]
    offer, target = support.manual_search(document, manual)
    automatic_replay: support.Replay = support.Replay.of(document, "subscription")
    automatic: support.Automatic = support.subscription(document, automatic_replay)
    return {
        "years": target.get("years"),
        "misses": [*manual.misses, *automatic_replay.misses],
        "manual": _offer(offer),
        "subscription": None if automatic.search is None else _offer(automatic.search.offer),
        "automatic": list(_actual(automatic)),
    }


def _offer(offer: EpisodeOffer) -> dict[str, Any]:
    return {
        "suggestion": offer.suggestion,
        "top3": [release_hash(row.stream.info_hash) for row in visible(offer.candidates, offer.suggestion)[:3]],
        "rows": [
            {
                "hash": release_hash(row.stream.info_hash),
                "release": row.stream.release or row.stream.name,
                "file": row.stream.path or row.stream.file_name,
                "verdict": row.identity.verdict.value,
                "reason": row.identity.reason,
            }
            for row in offer.candidates
        ],
    }


def compare(before_path: Path, after_path: Path, out: Path) -> None:
    """Write every verdict, top three and automatic choice that differs between two verdict files."""
    before: dict[str, Any] = json.loads(before_path.read_text(encoding="utf-8"))
    after: dict[str, Any] = json.loads(after_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = [
        row
        for case in after.values()
        for mode in ("manual", "subscription")
        if case[mode]
        for row in case[mode]["rows"]
    ]
    lines: list[str] = [
        "# Różnice werdyktów H1",
        "",
        f"- przypadki: {len(after)}",
        f"- wiersze ofert (ręczne i subskrypcja): {len(rows)}",
        f"- wiersze z rokiem w nazwie wydania albo pliku: {sum(_has_year(row) for row in rows)}",
        "",
        "## Zmiany werdyktu",
        "",
        "| przypadek | tryb | wydanie | plik | lata emisji celu | przed → po | powód po |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    choices: list[str] = []
    for case in sorted(after):
        old: dict[str, Any] | None = before.get(case)
        new: dict[str, Any] = after[case]
        if old is None:
            choices.append(f"- {case}: brak w pliku przed")
            continue
        lines.extend(_verdict_changes(case, old, new))
        choices.extend(_choice_changes(case, old, new))
    lines.extend(["", "## Zmiany top3, sugestii i wyboru automatu", "", *(choices or ["- brak"]), ""])
    out.write_text("\n".join(lines), encoding="utf-8")


def _has_year(row: dict[str, Any]) -> bool:
    return bool(YEAR.search(f"{row['release'] or ''} {row['file'] or ''}"))


def _verdict_changes(case: str, old: dict[str, Any], new: dict[str, Any]) -> Iterator[str]:
    for mode in ("manual", "subscription"):
        if not old[mode] or not new[mode]:
            continue
        previous: dict[tuple[str, str], dict[str, Any]] = {(row["hash"], row["file"]): row for row in old[mode]["rows"]}
        for row in new[mode]["rows"]:
            was: dict[str, Any] | None = previous.get((row["hash"], row["file"]))
            if was is not None and was["verdict"] != row["verdict"]:
                yield (
                    f"| {case} | {mode} | {_cell(row['release'])} | {_cell(row['file'])} | {new['years']} "
                    f"| {was['verdict']} → {row['verdict']} | {row['reason']} |"
                )


def _choice_changes(case: str, old: dict[str, Any], new: dict[str, Any]) -> Iterator[str]:
    for mode in ("manual", "subscription"):
        for part in ("top3", "suggestion"):
            was: Any = old[mode] and old[mode][part]
            now: Any = new[mode] and new[mode][part]
            if was != now:
                yield f"- {case} {mode} {part}: {was} → {now}"
    if old["automatic"] != new["automatic"]:
        yield f"- {case} automat: {old['automatic']} → {new['automatic']}"
    if new["misses"]:
        yield f"- {case} brak nagranej odpowiedzi po zmianie: {new['misses']}"


def _cell(text: str | None) -> str:
    return (text or "").replace("|", "/")


def history(decisions: Path, out: Path) -> None:
    """Append every saved choice whose file verdict changes once its target carries the AniList airing years."""
    entries: list[dict[str, Any]] = [
        entry
        for line in decisions.read_text(encoding="utf-8").splitlines()
        if line.strip() and "target" in (entry := json.loads(line)) and "file_name" in entry
    ]
    identifiers: set[int] = {entry["key"]["anilist_id"] for entry in entries}
    with httpx.Client(transport=httpx.MockTransport(Recorder(httpx.HTTPTransport()))) as http:
        graph: LibraryGraph = AniListCatalog(http).library_graph(identifiers)
    empty: AniZipMapping = AniZipMapping(None, None, None, (), (), None, {})
    lines: list[str] = ["", "## Historia decyzji", ""]
    changed: int = 0
    for entry in entries:
        anilist_id: int = entry["key"]["anilist_id"]
        if anilist_id not in graph.nodes:
            lines.append(f"- {entry['at']} {anilist_id}: brak wpisu w AniList")
            continue
        _, _, missing = franchise_traversal(anilist_id, graph.nodes, graph.queried)
        own: FranchiseGraph = FranchiseGraph(anilist_id, graph.nodes, graph.queried, not missing)
        moment: datetime = datetime.fromisoformat(entry["at"])
        years: object = identity_target(own, anilist_id, empty, 1, now=moment, numbering=False)["years"]
        name: str = entry["file_name"]
        candidate: dict[str, object] = {"release": None, "path": name, "filename": name}
        was: str = classify(entry["target"], candidate).verdict.value
        now: str = classify({**entry["target"], "years": years}, candidate).verdict.value
        if was != now:
            changed += 1
            lines.append(f"- {entry['at']} {anilist_id} `{name}` lata {years}: {was} → {now}")
    lines[2:2] = [f"- wpisy z celem i plikiem: {len(entries)}, zmienione werdykty: {changed}", ""]
    with out.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def _case(value: str) -> tuple[int, int]:
    anilist_id, _, number = value.partition("-")
    return int(anilist_id), int(number)


def main() -> None:
    """Run one command of the release dataset tool."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DATASET)
    commands: Any = parser.add_subparsers(dest="command", required=True)
    recording: argparse.ArgumentParser = commands.add_parser("record")
    recording.add_argument("--decisions", type=Path)
    recording.add_argument("--case", type=_case, action="append", default=[])
    replaying: argparse.ArgumentParser = commands.add_parser("verdicts")
    replaying.add_argument("out", type=Path)
    comparing: argparse.ArgumentParser = commands.add_parser("compare")
    comparing.add_argument("before", type=Path)
    comparing.add_argument("after", type=Path)
    comparing.add_argument("out", type=Path)
    past: argparse.ArgumentParser = commands.add_parser("history")
    past.add_argument("decisions", type=Path)
    past.add_argument("out", type=Path)
    arguments: argparse.Namespace = parser.parse_args()
    cases_dir: Path = arguments.root / "cases"
    if arguments.command == "record":
        found: list[tuple[int, int]] = decision_cases(arguments.decisions) if arguments.decisions else []
        record([*found, *arguments.case], cases_dir)
    elif arguments.command == "verdicts":
        verdicts([REFERENCE, cases_dir], arguments.out)
    elif arguments.command == "compare":
        compare(arguments.before, arguments.after, arguments.out)
    else:
        history(arguments.decisions, arguments.out)


if __name__ == "__main__":
    main()
