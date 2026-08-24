"""Neutral media identification API."""

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from anishift.services.media.probe import DefaultMediaProbe, MediaProbe

from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind

__all__ = [
    "ContainerKind",
    "DefaultMediaProbe",
    "MediaCatalog",
    "MediaProbe",
    "MediaTrack",
    "MediaTrackKind",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "DefaultMediaProbe": ("anishift.services.media.probe", "DefaultMediaProbe"),
    "MediaProbe": ("anishift.services.media.probe", "MediaProbe"),
}
"""Probe exports deferred so process helpers can load without recursive imports."""


def __getattr__(name: str) -> object:
    """Resolve probe facades only when a caller requests them."""
    target: tuple[str, str] | None = _LAZY_EXPORTS.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = target
    value: object = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
