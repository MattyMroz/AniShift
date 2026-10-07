from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Final, TypedDict, cast

import httpx

REFERENCE: Final[Path] = Path(__file__).parents[2] / "fixtures" / "acquisition" / "reference"
CASES: Final[tuple[str, ...]] = tuple(
    path.name.removesuffix(".json.gz") for path in sorted(REFERENCE.glob("*-*.json.gz")) if path.name[0].isdigit()
)


class RecordedResponse(TypedDict):
    method: str
    url: str
    status: int
    body: str


def responses(case: str, host: str) -> list[RecordedResponse]:
    body: dict[str, object] = json.loads(gzip.decompress((REFERENCE / f"{case}.json.gz").read_bytes()))
    return [row for row in cast("list[RecordedResponse]", body["responses"]) if httpx.URL(row["url"]).host == host]


def recorded_response(row: RecordedResponse, request: httpx.Request) -> httpx.Response:
    url: httpx.URL = httpx.URL(row["url"])
    assert request.method == row["method"]
    assert request.url.host == url.host
    assert request.url.path == url.path
    assert dict(request.url.params) == dict(url.params)
    return httpx.Response(
        row["status"],
        text=row["body"],
        headers={
            "content-type": "application/xml" if url.host == "nekobt.to" else "application/json",
        },
    )
