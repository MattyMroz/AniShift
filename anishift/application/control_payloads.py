"""Validated JSON representations of resident planning inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, fields
from typing import cast

from pydantic import TypeAdapter

from anishift.application.intents import AutoPreset, GroupIntent, ProductIntent, RebuildRequest
from anishift.application.planning import RunSettingsSnapshot


def decode_intent[T: (AutoPreset, GroupIntent, RebuildRequest, RunSettingsSnapshot)](
    model: type[T],
    payload: object,
) -> T:
    """Decode a planning contract without coercing numbers, flags or unknown fields."""
    if not isinstance(payload, Mapping) or payload.keys() - {item.name for item in fields(model)}:
        msg = "Unknown or invalid planning fields"
        raise ValueError(msg)
    products: object = payload.get("products")
    if isinstance(products, Mapping) and products.keys() - {item.name for item in fields(ProductIntent)}:
        msg = "Unknown product selection fields"
        raise ValueError(msg)
    return TypeAdapter(model).validate_json(json.dumps(dict(payload)), strict=True)


def encode_intent(intent: GroupIntent) -> dict[str, object]:
    """Represent one group selection with JSON values and no execution graph."""
    return cast("dict[str, object]", TypeAdapter(GroupIntent).dump_python(intent, mode="json"))


def decode_overrides(settings: RunSettingsSnapshot, payload: object) -> RunSettingsSnapshot:
    """Apply validated JSON overrides to an independent run settings snapshot."""
    if not isinstance(payload, Mapping):
        msg = "Run setting overrides must be an object"
        raise TypeError(msg)
    return decode_intent(RunSettingsSnapshot, {**asdict(settings), **payload})
