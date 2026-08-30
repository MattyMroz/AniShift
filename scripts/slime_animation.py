from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Final, cast

from PIL import Image

__all__ = ["MotionFrame", "build_motion_frames", "main", "prepare_gif_frame"]

# ── Constants ──

_ALPHA_THRESHOLD: Final = 128
"""Minimum alpha value treated as a visible source pixel."""

_FRAME_DURATION_MS: Final = 60
"""Duration of one exported animation frame in milliseconds."""

_ICON_SIZE: Final = 128
"""Canvas size of the compact terminal mascot export."""

_FULL_SIZE: Final = 640
"""Canvas size of the unclipped full animation export."""

_FULL_SOURCE_SCALE: Final = 3
"""Nearest-neighbour scale of the canonical bitmap in the full export."""

_FULL_BODY_BOTTOM: Final = 600
"""Target bottom edge of the resting body on the full canvas."""

_VERSION_LABEL: Final = "v1"
"""Asset label of the accepted pixel animation."""

_V2_FRAME_COUNT: Final = 46
"""Frame count of the original second motion study."""

_SHEET_COLUMNS: Final = 8
"""Number of animation frames per sprite-sheet row."""

_FULL_PROFILE_NAME: Final = "full"
"""Output profile that must preserve the complete animated silhouette."""

_ORB_DEPTH_SCALE: Final = 0.12
"""Perspective size change between the front and back halves of the orbit."""

_ORB_FRONT_VERTICAL_RADIUS_RATIO: Final = 0.10
"""Vertical drop that carries the foreground orbit below the eyes."""

_ORB_BACK_VERTICAL_RADIUS_RATIO: Final = 0.16
"""Vertical lift that carries the background orbit behind the flame."""

_SUBJECT_COMPONENT_COUNT: Final = 2
"""Expected visible source components: the body and its orbiting orb."""


type Point = tuple[int, int]
type PixelSet = set[Point]
type Bounds = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class MotionFrame:
    """Non-rigid transform applied to one canonical pose."""

    bend: float = 0.0
    wave: float = 0.0
    wave_phase: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    bulge: float = 0.0
    arch: float = 0.0
    jump: float = 0.0
    orb_angle: float = 0.0
    orb_scale: float = 1.0


@dataclass(frozen=True, slots=True)
class Profile:
    """Canvas and motion scale for one output profile."""

    name: str
    canvas_size: int
    motion_scale: float
    base: Image.Image


@dataclass(frozen=True, slots=True)
class Geometry:
    """Pixel geometry used by the inverse body warp."""

    bounds: Bounds
    center_x: float
    bottom: float
    half_width: float
    height: float


@dataclass(frozen=True, slots=True)
class ProfileResult:
    """Export measurements recorded in the build manifest."""

    canvas_size: int
    motion_scale: float
    frame_count: int
    minimum_margin: int
    removed_frame_artifact_pixels: int


@dataclass(frozen=True, slots=True)
class RenderParts:
    """Reusable source geometry shared while rendering one profile."""

    source: Image.Image
    body_pixels: PixelSet
    orb_pixels: PixelSet
    geometry: Geometry
    motion_scale: float


def _parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Build deterministic AniShift slime animation assets.",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clean-source", type=Path)
    return parser.parse_args()


def _visible_pixels(image: Image.Image) -> PixelSet:
    pixels: PixelSet = set()
    rgba: Image.Image = image.convert("RGBA")
    for y in range(rgba.height):
        for x in range(rgba.width):
            pixel: tuple[int, int, int, int] = cast(
                tuple[int, int, int, int],
                rgba.getpixel((x, y)),
            )
            if pixel[3] >= _ALPHA_THRESHOLD:
                pixels.add((x, y))
    return pixels


def _connected_components(pixels: PixelSet) -> list[PixelSet]:
    remaining: PixelSet = set(pixels)
    components: list[PixelSet] = []
    neighbours: tuple[Point, ...] = (
        (-1, -1),
        (0, -1),
        (1, -1),
        (-1, 0),
        (1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
    )
    while remaining:
        seed: Point = remaining.pop()
        component: PixelSet = {seed}
        frontier: list[Point] = [seed]
        while frontier:
            x, y = frontier.pop()
            for delta_x, delta_y in neighbours:
                candidate: Point = (x + delta_x, y + delta_y)
                if candidate not in remaining:
                    continue
                remaining.remove(candidate)
                component.add(candidate)
                frontier.append(candidate)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def _clean_source(source: Image.Image) -> tuple[Image.Image, list[Point]]:
    cleaned: Image.Image = source.convert("RGBA")
    components: list[PixelSet] = _connected_components(_visible_pixels(cleaned))
    if len(components) < _SUBJECT_COMPONENT_COUNT:
        msg: str = "The source must contain separate body and orb components."
        raise ValueError(msg)
    artifacts: PixelSet = set().union(*components[_SUBJECT_COMPONENT_COUNT:])
    for point in artifacts:
        cleaned.putpixel(point, (0, 0, 0, 0))
    return cleaned, sorted(artifacts, key=lambda point: (point[1], point[0]))


def _bounds(pixels: PixelSet) -> Bounds:
    x_values: list[int] = [point[0] for point in pixels]
    y_values: list[int] = [point[1] for point in pixels]
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _geometry(pixels: PixelSet) -> Geometry:
    left, top, right, bottom = _bounds(pixels)
    width: int = right - left
    height: int = bottom - top
    return Geometry(
        bounds=(left, top, right, bottom),
        center_x=(left + right) / 2,
        bottom=float(bottom),
        half_width=max(width / 2, 1.0),
        height=max(float(height), 1.0),
    )


def _smoothstep(progress: float) -> float:
    return progress * progress * (3.0 - 2.0 * progress)


def build_motion_frames() -> list[MotionFrame]:
    """Build the accepted v1 motion timeline."""
    frames: list[MotionFrame] = []
    frames.extend(MotionFrame() for _ in range(3))

    for index in range(8):
        progress: float = (index + 1) / 8
        phase: float = progress * math.tau
        sway: float = math.sin(phase)
        frames.append(
            MotionFrame(
                bend=8.0 * sway,
                wave=3.5 * sway,
                wave_phase=phase / 2,
                scale_x=1.0 + 0.025 * sway,
                scale_y=1.0 - 0.035 * sway,
                bulge=0.035 * sway,
            )
        )

    frames.extend(MotionFrame() for _ in range(2))

    for index in range(4):
        progress = (index + 1) / 4
        anticipation: float = math.sin(progress * math.pi / 2)
        frames.append(
            MotionFrame(
                bend=2.0 * math.sin(progress * math.pi),
                scale_x=1.0 + 0.45 * anticipation,
                scale_y=1.0 - 0.42 * anticipation,
                bulge=0.12 * anticipation,
                arch=-2.0 * anticipation,
            )
        )

    frames.append(MotionFrame())

    for index in range(12):
        progress = (index + 1) / 12
        flight: float = math.sin(progress * math.pi)
        frames.append(
            MotionFrame(
                bend=8.0 * math.sin(progress * math.tau) * flight,
                wave=4.0 * math.sin(progress * math.tau) * flight,
                wave_phase=progress * math.pi,
                scale_x=1.0 + 0.06 * flight,
                scale_y=1.0 + 0.10 * flight,
                bulge=0.03 * flight,
                arch=2.5 * flight,
                jump=-30.0 * flight,
            )
        )

    frames.append(
        MotionFrame(
            scale_x=1.45,
            scale_y=0.60,
            bulge=0.12,
            arch=-2.0,
        )
    )
    frames.extend(
        (
            MotionFrame(bend=4.0, wave=2.0, scale_x=1.08, scale_y=0.92),
            MotionFrame(bend=-8.0, wave=-3.0, scale_x=0.88, scale_y=1.22, arch=3.0),
            MotionFrame(bend=-6.0, wave=-2.5, scale_x=0.91, scale_y=1.18, arch=2.5),
            MotionFrame(bend=4.0, wave=2.0, scale_x=1.03, scale_y=0.98),
            MotionFrame(bend=5.0, wave=2.0, scale_x=1.04, scale_y=0.96),
            MotionFrame(bend=2.0, wave=1.0, scale_y=0.99),
            MotionFrame(bend=-2.0, wave=-1.0, scale_x=0.98, scale_y=1.01),
            MotionFrame(),
            MotionFrame(bend=4.0, wave=2.0, scale_y=0.98),
            MotionFrame(bend=3.0, wave=1.0, scale_y=0.99),
            MotionFrame(bend=-2.0, wave=-1.0, scale_y=1.01),
            MotionFrame(bend=-1.0, wave=-0.5, scale_y=1.01),
        )
    )
    frames.extend(MotionFrame() for _ in range(3))
    if len(frames) != _V2_FRAME_COUNT:
        msg: str = f"Restored v2 motion must contain {_V2_FRAME_COUNT} frames."
        raise ValueError(msg)
    return [replace(frame, orb_angle=360.0 * index / (_V2_FRAME_COUNT - 1)) for index, frame in enumerate(frames)]


def _make_profiles(cleaned: Image.Image) -> list[Profile]:
    visible: list[PixelSet] = _connected_components(_visible_pixels(cleaned))
    body_bounds: Bounds = _bounds(visible[0])
    scaled_size: int = cleaned.width * _FULL_SOURCE_SCALE
    scaled: Image.Image = cleaned.resize((scaled_size, scaled_size), Image.Resampling.NEAREST)
    full: Image.Image = Image.new("RGBA", (_FULL_SIZE, _FULL_SIZE), (0, 0, 0, 0))
    x_offset: int = (_FULL_SIZE - scaled_size) // 2
    y_offset: int = _FULL_BODY_BOTTOM - (body_bounds[3] + 1) * _FULL_SOURCE_SCALE
    full.alpha_composite(scaled, (x_offset, y_offset))
    return [
        Profile(name="icon", canvas_size=_ICON_SIZE, motion_scale=1.0, base=cleaned.copy()),
        Profile(
            name="full",
            canvas_size=_FULL_SIZE,
            motion_scale=float(_FULL_SOURCE_SCALE),
            base=full,
        ),
    ]


def _sample_body(
    destination: Image.Image,
    parts: RenderParts,
    motion: MotionFrame,
) -> None:
    source: Image.Image = parts.source
    body_pixels: PixelSet = parts.body_pixels
    geometry: Geometry = parts.geometry
    motion_scale: float = parts.motion_scale
    _, top, _, _ = geometry.bounds
    bend: float = motion.bend * motion_scale
    wave: float = motion.wave * motion_scale
    arch: float = motion.arch * motion_scale
    jump: float = motion.jump * motion_scale
    edge_padding: int = math.ceil(4 * motion_scale)
    maximum_width_scale: float = motion.scale_x * (1.0 + abs(motion.bulge))
    lateral_extent: float = geometry.half_width * maximum_width_scale
    lateral_extent += abs(bend) + abs(wave) + edge_padding
    x_start: int = max(0, math.floor(geometry.center_x - lateral_extent))
    x_end: int = min(
        destination.width - 1,
        math.ceil(geometry.center_x + lateral_extent),
    )
    transformed_top: float = geometry.bottom + (top - geometry.bottom) * motion.scale_y
    transformed_top += jump - abs(arch) - edge_padding
    transformed_bottom: float = geometry.bottom + jump + abs(arch) + edge_padding
    y_start: int = max(0, math.floor(transformed_top))
    y_end: int = min(destination.height - 1, math.ceil(transformed_bottom))

    for destination_y in range(y_start, y_end + 1):
        initial_y: float = geometry.bottom + (destination_y - geometry.bottom - jump) / motion.scale_y
        initial_upward: float = max(0.0, min(1.0, (geometry.bottom - initial_y) / geometry.height))
        for destination_x in range(x_start, x_end + 1):
            relative_x: float = (destination_x - geometry.center_x) / geometry.half_width
            arch_offset: float = arch * math.sin(relative_x * math.pi) * math.sin(initial_upward * math.pi)
            source_y: float = geometry.bottom + (destination_y - geometry.bottom - jump - arch_offset) / motion.scale_y
            upward: float = max(0.0, min(1.0, (geometry.bottom - source_y) / geometry.height))
            lateral_offset: float = bend * upward**1.35
            lateral_offset += wave * math.sin(upward * math.tau + motion.wave_phase) * math.sin(upward * math.pi)
            width_scale: float = motion.scale_x * (1.0 + motion.bulge * math.sin(upward * math.pi))
            source_x: float = geometry.center_x + (destination_x - geometry.center_x - lateral_offset) / width_scale
            source_point: Point = (round(source_x), round(source_y))
            if source_point in body_pixels:
                pixel: tuple[int, int, int, int] = cast(
                    tuple[int, int, int, int],
                    source.getpixel(source_point),
                )
                destination.putpixel((destination_x, destination_y), pixel)


def _orb_sprite(source: Image.Image, orb_pixels: PixelSet) -> tuple[Image.Image, tuple[float, float]]:
    left, top, right, bottom = _bounds(orb_pixels)
    sprite: Image.Image = Image.new(
        "RGBA",
        (right - left + 1, bottom - top + 1),
        (0, 0, 0, 0),
    )
    for source_point in orb_pixels:
        pixel: tuple[int, int, int, int] = cast(
            tuple[int, int, int, int],
            source.getpixel(source_point),
        )
        destination_point: Point = (source_point[0] - left, source_point[1] - top)
        sprite.putpixel(destination_point, pixel)
    center: tuple[float, float] = ((left + right) / 2, (top + bottom) / 2)
    return sprite, center


def _paste_orb(
    destination: Image.Image,
    parts: RenderParts,
    motion: MotionFrame,
) -> None:
    source: Image.Image = parts.source
    orb_pixels: PixelSet = parts.orb_pixels
    geometry: Geometry = parts.geometry
    motion_scale: float = parts.motion_scale
    sprite, source_center = _orb_sprite(source, orb_pixels)
    normalized_angle: float = motion.orb_angle % 360.0
    radians: float = math.radians(normalized_angle)
    depth: float = math.sin(radians)
    perspective_scale: float = motion.orb_scale * (1.0 + _ORB_DEPTH_SCALE * depth)
    scaled_width: int = max(1, round(sprite.width * perspective_scale))
    scaled_height: int = max(1, round(sprite.height * perspective_scale))
    scaled: Image.Image = sprite.resize((scaled_width, scaled_height), Image.Resampling.NEAREST)
    source_upward: float = (geometry.bottom - source_center[1]) / geometry.height
    bend: float = motion.bend * motion_scale
    wave: float = motion.wave * motion_scale
    lateral_offset: float = bend * source_upward**1.35
    lateral_offset += wave * math.sin(source_upward * math.tau + motion.wave_phase) * math.sin(source_upward * math.pi)
    orbit_center_x: float = geometry.center_x + lateral_offset
    orbit_center_y: float = geometry.bottom + (source_center[1] - geometry.bottom) * motion.scale_y
    orbit_center_y += motion.jump * motion_scale
    horizontal_radius: float = abs(source_center[0] - geometry.center_x)
    horizontal_radius *= motion.scale_x * (1.0 + motion.bulge)
    destination_center_x: float = orbit_center_x + horizontal_radius * math.cos(radians)
    vertical_ratio: float = _ORB_FRONT_VERTICAL_RADIUS_RATIO if depth >= 0.0 else _ORB_BACK_VERTICAL_RADIUS_RATIO
    vertical_offset: float = geometry.height * vertical_ratio * motion.scale_y * depth
    destination_center_y: float = orbit_center_y + vertical_offset
    paste_x: int = round(destination_center_x - (scaled.width - 1) / 2)
    paste_y: int = round(destination_center_y - (scaled.height - 1) / 2)
    destination.alpha_composite(scaled, (paste_x, paste_y))


def _render_frame(profile: Profile, motion: MotionFrame) -> Image.Image:
    if motion == MotionFrame():
        return profile.base.copy()

    components: list[PixelSet] = _connected_components(_visible_pixels(profile.base))
    body_pixels: PixelSet = components[0]
    orb_pixels: PixelSet = components[1]
    geometry: Geometry = _geometry(body_pixels)
    parts: RenderParts = RenderParts(
        source=profile.base,
        body_pixels=body_pixels,
        orb_pixels=orb_pixels,
        geometry=geometry,
        motion_scale=profile.motion_scale,
    )
    body_layer: Image.Image = Image.new(
        "RGBA",
        (profile.canvas_size, profile.canvas_size),
        (0, 0, 0, 0),
    )
    orb_layer: Image.Image = body_layer.copy()
    _sample_body(body_layer, parts, motion)
    _paste_orb(orb_layer, parts, motion)
    normalized_orb_angle: float = motion.orb_angle % 360.0
    orb_depth: float = math.sin(math.radians(normalized_orb_angle))
    orb_is_in_front: bool = orb_depth >= 0.0
    if orb_is_in_front:
        frame: Image.Image = body_layer.copy()
        frame.alpha_composite(orb_layer)
        return frame

    frame = orb_layer.copy()
    frame.alpha_composite(body_layer)
    return frame


def _save_frames(frames: list[Image.Image], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stale_frame in directory.glob("frame_*.png"):
        stale_frame.unlink()
    for index, frame in enumerate(frames):
        frame.save(directory / f"frame_{index:03d}.png")


def _save_sheet(frames: list[Image.Image], target: Path) -> None:
    frame_width, frame_height = frames[0].size
    rows: int = math.ceil(len(frames) / _SHEET_COLUMNS)
    sheet: Image.Image = Image.new(
        "RGBA",
        (frame_width * _SHEET_COLUMNS, frame_height * rows),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(frames):
        x_offset: int = index % _SHEET_COLUMNS * frame_width
        y_offset: int = index // _SHEET_COLUMNS * frame_height
        sheet.alpha_composite(frame, (x_offset, y_offset))
    sheet.save(target)


def prepare_gif_frame(frame: Image.Image) -> Image.Image:
    """Convert one transparent RGBA frame to a GIF-safe palette."""
    rgba: Image.Image = frame.convert("RGBA")
    background: Image.Image = Image.new("RGB", rgba.size, (0, 0, 0))
    background.paste(rgba, mask=rgba.getchannel("A"))
    paletted: Image.Image = background.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    data: list[int] = list(cast(tuple[int, ...], paletted.get_flattened_data()))
    alpha: list[int] = list(cast(tuple[int, ...], rgba.getchannel("A").get_flattened_data()))
    transparent_data: list[int] = [
        255 if value < _ALPHA_THRESHOLD else data[index] for index, value in enumerate(alpha)
    ]
    paletted.putdata(transparent_data)
    palette: list[int] = list(paletted.getpalette() or [])
    palette.extend([0] * (768 - len(palette)))
    paletted.putpalette(palette[:768])
    paletted.info["transparency"] = 255
    return paletted


def _save_animations(frames: list[Image.Image], directory: Path, profile_name: str) -> None:
    stem: str = f"anishift-slime-spin-squash-jump-{profile_name}-{_VERSION_LABEL}"
    frames[0].save(
        directory / f"{stem}.apng",
        save_all=True,
        append_images=frames[1:],
        duration=_FRAME_DURATION_MS,
        loop=0,
        disposal=1,
        blend=0,
    )
    gif_frames: list[Image.Image] = [prepare_gif_frame(frame) for frame in frames]
    gif_frames[0].save(
        directory / f"{stem}.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=_FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        transparency=255,
        optimize=False,
    )
    preview_frames: list[Image.Image]
    if frames[0].width == _ICON_SIZE:
        preview_frames = [frame.resize((_FULL_SIZE, _FULL_SIZE), Image.Resampling.NEAREST) for frame in frames]
    else:
        preview_frames = frames
    preview_gif_frames: list[Image.Image] = [prepare_gif_frame(frame) for frame in preview_frames]
    preview_gif_frames[0].save(
        directory / f"{stem}-preview-{_FULL_SIZE}.gif",
        save_all=True,
        append_images=preview_gif_frames[1:],
        duration=_FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        transparency=255,
        optimize=False,
    )


def _minimum_margin(frames: list[Image.Image]) -> int:
    margins: list[int] = []
    for frame in frames:
        bounds: Bounds | None = frame.getchannel("A").getbbox()
        if bounds is None:
            continue
        left, top, right, bottom = bounds
        margins.append(min(left, top, frame.width - right, frame.height - bottom))
    if not margins:
        msg: str = "Animation contains no visible frames."
        raise ValueError(msg)
    return min(margins)


def _remove_frame_artifacts(frame: Image.Image) -> tuple[Image.Image, int]:
    cleaned: Image.Image = frame.copy()
    hardened_alpha: Image.Image = cleaned.getchannel("A").point(lambda value: 255 if value >= _ALPHA_THRESHOLD else 0)
    cleaned.putalpha(hardened_alpha)
    transparent_mask: Image.Image = hardened_alpha.point(lambda value: 255 - value)
    cleaned.paste((0, 0, 0, 0), mask=transparent_mask)
    components: list[PixelSet] = _connected_components(_visible_pixels(cleaned))
    if len(components) <= _SUBJECT_COMPONENT_COUNT:
        return cleaned, 0
    artifacts: PixelSet = set().union(*components[_SUBJECT_COMPONENT_COUNT:])
    for point in artifacts:
        cleaned.putpixel(point, (0, 0, 0, 0))
    return cleaned, len(artifacts)


def _export_profile(profile: Profile, motions: list[MotionFrame], output: Path) -> ProfileResult:
    directory: Path = output / profile.name
    directory.mkdir(parents=True, exist_ok=True)
    generated_pattern: str = f"anishift-slime-spin-squash-jump-{profile.name}-*"
    for stale_asset in directory.glob(generated_pattern):
        if stale_asset.is_file():
            stale_asset.unlink()
    rendered_frames: list[Image.Image] = [_render_frame(profile, motion) for motion in motions]
    cleaned_frames: list[tuple[Image.Image, int]] = [_remove_frame_artifacts(frame) for frame in rendered_frames]
    frames: list[Image.Image] = [frame for frame, _ in cleaned_frames]
    removed_frame_artifacts: int = sum(count for _, count in cleaned_frames)
    minimum_margin: int = _minimum_margin(frames)
    if profile.name == _FULL_PROFILE_NAME and minimum_margin <= 0:
        msg: str = f"The {profile.name} profile clips the animation at the canvas edge."
        raise ValueError(msg)
    _save_frames(frames, directory / "frames")
    sheet_name: str = f"anishift-slime-spin-squash-jump-{profile.name}-sheet-{_VERSION_LABEL}.png"
    _save_sheet(frames, directory / sheet_name)
    _save_animations(frames, directory, profile.name)
    return ProfileResult(
        canvas_size=profile.canvas_size,
        motion_scale=profile.motion_scale,
        frame_count=len(frames),
        minimum_margin=minimum_margin,
        removed_frame_artifact_pixels=removed_frame_artifacts,
    )


def _sha256(path: Path) -> str:
    digest: hashlib._Hash = hashlib.sha256()
    with path.open("rb") as source_file:
        while chunk := source_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(
    output: Path,
    source: Path,
    removed_artifacts: list[Point],
    results: dict[str, ProfileResult],
) -> None:
    manifest: dict[str, object] = {
        "source": str(source.resolve()),
        "source_sha256": _sha256(source),
        "removed_artifact_pixels": [list(point) for point in removed_artifacts],
        "frame_duration_ms": _FRAME_DURATION_MS,
        "motion": "spin-squash-jump-v1",
        "orb_path_degrees": [0, 360],
        "orb_path": "constant-speed projected 3D ellipse",
        "profiles": {name: asdict(result) for name, result in results.items()},
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build cleaned source and deterministic dual-profile animation assets."""
    args: argparse.Namespace = _parse_args()
    source_path: Path = args.source.resolve()
    output_path: Path = args.output.resolve()
    clean_source_path: Path | None = args.clean_source.resolve() if args.clean_source else None
    source: Image.Image = Image.open(source_path).convert("RGBA")
    cleaned, removed_artifacts = _clean_source(source)
    if clean_source_path is not None:
        clean_source_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned.save(clean_source_path)
    motions: list[MotionFrame] = build_motion_frames()
    profiles: list[Profile] = _make_profiles(cleaned)
    output_path.mkdir(parents=True, exist_ok=True)
    results: dict[str, ProfileResult] = {
        profile.name: _export_profile(profile, motions, output_path) for profile in profiles
    }
    _write_manifest(output_path, source_path, removed_artifacts, results)


if __name__ == "__main__":
    main()
