"""Validated JSON representations of resident planning inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields

from anishift.application.control_views import decode_view
from anishift.application.intents import AutoPreset, GroupIntent, ProductIntent, RebuildRequest


def decode_intent[T: (AutoPreset, GroupIntent, RebuildRequest)](
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
    return decode_view(model, dict(payload))
