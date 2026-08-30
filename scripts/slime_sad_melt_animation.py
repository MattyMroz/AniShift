from __future__ import annotations

import argparse
import json
import math
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, cast

from PIL import Image, ImageFilter
from slime_animation import prepare_gif_frame

__all__ = ["main"]

# ── Constants ────────────────────────────────────────────────────────────────

_CANVAS_SIZE: Final = 128
"""Pixel-art canvas used for every authored animation frame."""

_FULL_CANVAS_SIZE: Final = 640
"""Large transparent canvas used for the full profile."""

_FULL_SPRITE_SIZE: Final = 512
"""Nearest-neighbour size of the pixel animation inside the full profile."""

_FRAME_DURATION_MS: Final = 60
"""Duration of every animation frame."""

_SOURCE_ALPHA_THRESHOLD: Final = 128
"""Minimum alpha retained from the clean 128-pixel source."""

_REFERENCE_BACKGROUND_CEILING: Final = 24
"""Maximum RGB channel treated as the atlas' connected black background."""

_REFERENCE_WHITE_FLOOR: Final = 180
"""Minimum RGB channel used to locate the generated orb's white ring."""

_REFERENCE_DARK_CEILING: Final = 70
"""Maximum RGB channel used to locate the generated body's dark core."""

_REFERENCE_COLUMNS: Final = 4
"""Number of generated reference poses per row."""

_REFERENCE_ROWS: Final = 4
"""Number of generated reference rows."""

_REFERENCE_POSE_COUNT: Final = 15
"""Number of eyed poses used from the unified sixteen-cell reference atlas."""

_REQUIRED_COMPONENT_COUNT: Final = 2
"""Body and orb components required in every reference pose."""

_REFERENCE_ORB_RADIUS: Final = 32.0
"""Radius removed around the generated orb before body rasterization."""

_REFERENCE_ORB_WHITE_AREA_RANGE: Final = range(80, 201)
"""Expected connected white-ring area in a generated atlas cell."""

_REFERENCE_ORB_WHITE_WIDTH_RANGE: Final = range(15, 41)
"""Expected connected white-ring width in a generated atlas cell."""

_REFERENCE_ORB_WHITE_HEIGHT_RANGE: Final = range(12, 33)
"""Expected connected white-ring height in a generated atlas cell."""

_REFERENCE_ORB_MINIMUM_X_OFFSET: Final = 40
"""Minimum horizontal distance between the body core and generated orb ring."""

_REFERENCE_EYE_AREA_RANGE: Final = range(100, 801)
"""Expected connected white-eye area in a generated atlas cell."""

_REFERENCE_EYE_WIDTH_RANGE: Final = range(10, 41)
"""Expected connected white-eye width in a generated atlas cell."""

_REFERENCE_EYE_HEIGHT_RANGE: Final = range(10, 46)
"""Expected connected white-eye height in a generated atlas cell."""

_REFERENCE_EYE_X_RANGE: Final = (0.15, 0.85)
"""Horizontal body region in which generated eye shapes may appear."""

_REFERENCE_EYE_MINIMUM_Y: Final = 0.4
"""Minimum relative body height at which generated eye shapes may appear."""

_OUTLINE_MIDPOINT: Final = 0.5
"""Normalized position at which the outline changes from blue to pink."""

_BODY_DARK_COLOR: Final = (2, 0, 9, 255)
"""Base interior color before mapping to the approved source palette."""

_BODY_PURPLE_COLOR: Final = (24, 0, 58, 255)
"""Upper-body shade before mapping to the approved source palette."""

_OUTLINE_LEFT_COLOR: Final = (0, 190, 255, 255)
"""Blue side of the shared neon outline."""

_OUTLINE_MIDDLE_COLOR: Final = (126, 0, 255, 255)
"""Purple middle of the shared neon outline."""

_OUTLINE_RIGHT_COLOR: Final = (255, 0, 92, 255)
"""Pink-red side of the shared neon outline."""

_OUTLINE_LEFT_HIGHLIGHT: Final = (214, 246, 255, 255)
"""Light inner edge on the blue half of the body."""

_OUTLINE_RIGHT_HIGHLIGHT: Final = (255, 215, 239, 255)
"""Light inner edge on the pink half of the body."""

_EYE_GLOW_COLOR: Final = (91, 0, 210, 255)
"""Shared purple shadow surrounding every eye pose."""

_EYE_COLOR: Final = (255, 255, 255, 255)
"""Shared white fill used for every eye pose."""

_TEXTURE_HIGHLIGHT_FLOOR: Final = 170
"""Brightness above which base eyes and white edge highlights are removed."""

_ORB_CENTERS: Final = (
    (94, 43),
    (98, 49),
    (102, 62),
    (106, 78),
    (110, 96),
    (111, 108),
    (108, 104),
    (105, 109),
    (107, 110),
    (110, 110),
    (112, 110),
    (110, 110),
    (107, 110),
    (104, 110),
    (101, 110),
)
"""Authored fall, bounce, and short roll path for the unchanged base orb."""

_PALETTE_COLOR_COUNT: Final = 192
"""Maximum colors retained from the approved base slime palette."""

_BODY_CENTER_X: Final = 63.0
"""Horizontal anchor shared by every independently drawn pose."""

_BODY_BOTTOM: Final = 119.0
"""Ground line shared by every independently drawn pose."""

_BODY_MAX_WIDTH: Final = 124
"""Largest body width that preserves transparent icon padding."""

_BODY_MAX_HEIGHT: Final = 112
"""Largest body height that preserves transparent icon padding."""

_NORMAL_HOLD_FRAMES: Final = 3
"""Still frames before and after the complete emotional cycle."""

_PUDDLE_HOLD_FRAMES: Final = 4
"""Still frames held at the fully melted pose."""

_SHEET_FRAME_COLUMNS: Final = 8
"""Number of animation frames per exported spritesheet row."""


type Point = tuple[int, int]
type Pixel = tuple[int, int, int, int]
type PixelSet = set[Point]
type Bounds = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class RawPose:
    """One separately authored pose before normalization to 128 pixels."""

    body_mask: Image.Image
    eyes_mask: Image.Image
    body_area: int


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Measurements written to the animation manifest."""

    keyframe_count: int
    frame_count: int
    frame_duration_ms: int
    loop_is_exact: bool
    minimum_margin: int
    icon_size: int
    full_size: int


@dataclass(frozen=True, slots=True)
class RenderAssets:
    """Shared base-derived material used to paint every normalized pose."""

    palette: Image.Image
    body_texture: Image.Image
    orb: Image.Image


def _parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Build the hand-authored AniShift sad-melt-recovery animation.",
    )
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _pixel(image: Image.Image, point: Point) -> Pixel:
    return cast(Pixel, image.getpixel(point))


def _mask_value(image: Image.Image, point: Point) -> int:
    return cast(int, image.getpixel(point))


def _connected_components(pixels: PixelSet) -> list[PixelSet]:
    remaining: PixelSet = set(pixels)
    components: list[PixelSet] = []
    while remaining:
        seed: Point = remaining.pop()
        component: PixelSet = {seed}
        frontier: list[Point] = [seed]
        while frontier:
            x, y = frontier.pop()
            for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbour not in remaining:
                    continue
                remaining.remove(neighbour)
                component.add(neighbour)
                frontier.append(neighbour)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def _bounds(pixels: PixelSet) -> Bounds:
    if not pixels:
        msg: str = "Cannot calculate bounds of an empty pixel set."
        raise ValueError(msg)
    xs: list[int] = [point[0] for point in pixels]
    ys: list[int] = [point[1] for point in pixels]
    return min(xs), min(ys), max(xs), max(ys)


def _component_sprite(image: Image.Image, pixels: PixelSet) -> Image.Image:
    left, top, right, bottom = _bounds(pixels)
    sprite: Image.Image = Image.new(
        "RGBA",
        (right - left + 1, bottom - top + 1),
        (0, 0, 0, 0),
    )
    for x, y in pixels:
        sprite.putpixel((x - left, y - top), _pixel(image, (x, y)))
    return sprite


def _mask_for_bounds(pixels: PixelSet, bounds: Bounds) -> Image.Image:
    left, top, right, bottom = bounds
    mask: Image.Image = Image.new("L", (right - left + 1, bottom - top + 1), 0)
    for x, y in pixels:
        mask.putpixel((x - left, y - top), 255)
    return mask


def _cell(sheet: Image.Image, index: int) -> Image.Image:
    column: int = index % _REFERENCE_COLUMNS
    row: int = index // _REFERENCE_COLUMNS
    left: int = round(sheet.width * column / _REFERENCE_COLUMNS)
    top: int = round(sheet.height * row / _REFERENCE_ROWS)
    right: int = round(sheet.width * (column + 1) / _REFERENCE_COLUMNS)
    bottom: int = round(sheet.height * (row + 1) / _REFERENCE_ROWS)
    return sheet.crop((left, top, right, bottom))


def _is_reference_background(pixel: Pixel) -> bool:
    red, green, blue, _ = pixel
    return max(red, green, blue) <= _REFERENCE_BACKGROUND_CEILING


def _border_points(width: int, height: int) -> list[Point]:
    points: list[Point] = []
    points.extend((x, 0) for x in range(width))
    points.extend((x, height - 1) for x in range(width))
    points.extend((0, y) for y in range(1, height - 1))
    points.extend((width - 1, y) for y in range(1, height - 1))
    return points


def _reference_foreground(cell: Image.Image) -> PixelSet:
    background: PixelSet = {
        (x, y) for y in range(cell.height) for x in range(cell.width) if _is_reference_background(_pixel(cell, (x, y)))
    }
    outside: PixelSet = set()
    frontier: deque[Point] = deque()
    for point in _border_points(cell.width, cell.height):
        if point not in background or point in outside:
            continue
        outside.add(point)
        frontier.append(point)
    while frontier:
        x, y = frontier.popleft()
        for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbour not in background or neighbour in outside:
                continue
            outside.add(neighbour)
            frontier.append(neighbour)
    return {(x, y) for y in range(cell.height) for x in range(cell.width) if (x, y) not in outside}


def _raw_pose(cell: Image.Image) -> RawPose:
    foreground: PixelSet = _reference_foreground(cell)
    dark_pixels: PixelSet = {point for point in foreground if max(_pixel(cell, point)[:3]) < _REFERENCE_DARK_CEILING}
    dark_components: list[PixelSet] = _connected_components(dark_pixels)
    if not dark_components:
        msg: str = "A generated reference pose must contain a dark body core."
        raise ValueError(msg)
    body_core_left, _, body_core_right, _ = _bounds(dark_components[0])
    body_core_center_x: float = (body_core_left + body_core_right) / 2
    white_pixels: PixelSet = {point for point in foreground if min(_pixel(cell, point)[:3]) >= _REFERENCE_WHITE_FLOOR}
    white_components: list[PixelSet] = _connected_components(white_pixels)
    orb_candidates: list[PixelSet] = []
    for component in white_components:
        left, top, right, bottom = _bounds(component)
        width: int = right - left + 1
        height: int = bottom - top + 1
        center_x: float = (left + right) / 2
        if (
            len(component) in _REFERENCE_ORB_WHITE_AREA_RANGE
            and width in _REFERENCE_ORB_WHITE_WIDTH_RANGE
            and height in _REFERENCE_ORB_WHITE_HEIGHT_RANGE
            and center_x > body_core_center_x + _REFERENCE_ORB_MINIMUM_X_OFFSET
        ):
            orb_candidates.append(component)
    if not orb_candidates:
        msg = "Could not locate the generated orb ring in a reference pose."
        raise ValueError(msg)
    orb_ring: PixelSet = max(orb_candidates, key=lambda component: _bounds(component)[2])
    orb_left, orb_top, orb_right, orb_bottom = _bounds(orb_ring)
    orb_center_x: float = (orb_left + orb_right) / 2 + 5
    orb_center_y: float = (orb_top + orb_bottom) / 2 + 7
    body_candidates: PixelSet = {
        point
        for point in foreground
        if (point[0] - orb_center_x) ** 2 + (point[1] - orb_center_y) ** 2 > _REFERENCE_ORB_RADIUS**2
    }
    body_components: list[PixelSet] = _connected_components(body_candidates)
    if not body_components:
        msg = "Could not isolate the generated body pixels."
        raise ValueError(msg)
    body_pixels: PixelSet = body_components[0]
    body_bounds: Bounds = _bounds(body_pixels)
    body_left, body_top, body_right, body_bottom = body_bounds
    body_width: int = body_right - body_left + 1
    body_height: int = body_bottom - body_top + 1
    eye_candidates: list[PixelSet] = []
    for component in _connected_components(white_pixels & body_pixels):
        left, top, right, bottom = _bounds(component)
        width = right - left + 1
        height = bottom - top + 1
        center_x = (left + right) / 2
        center_y: float = (top + bottom) / 2
        relative_x: float = (center_x - body_left) / body_width
        relative_y: float = (center_y - body_top) / body_height
        if (
            len(component) in _REFERENCE_EYE_AREA_RANGE
            and width in _REFERENCE_EYE_WIDTH_RANGE
            and height in _REFERENCE_EYE_HEIGHT_RANGE
            and _REFERENCE_EYE_X_RANGE[0] <= relative_x <= _REFERENCE_EYE_X_RANGE[1]
            and relative_y >= _REFERENCE_EYE_MINIMUM_Y
        ):
            eye_candidates.append(component)
    if len(eye_candidates) < _REQUIRED_COMPONENT_COUNT:
        msg = "Could not locate both eye shapes in a reference pose."
        raise ValueError(msg)
    eyes: PixelSet = set().union(*sorted(eye_candidates, key=len, reverse=True)[:2])
    return RawPose(
        body_mask=_mask_for_bounds(body_pixels, body_bounds),
        eyes_mask=_mask_for_bounds(eyes, body_bounds),
        body_area=len(body_pixels),
    )


def _load_reference_poses(path: Path) -> list[RawPose]:
    with Image.open(path) as sheet_image:
        sheet: Image.Image = sheet_image.convert("RGBA")
    poses: list[RawPose] = []
    for index in range(_REFERENCE_POSE_COUNT):
        cell: Image.Image = _cell(sheet, index)
        poses.append(_raw_pose(cell))
        cell.close()
    return poses


def _source_components(base: Image.Image) -> list[PixelSet]:
    visible: PixelSet = {
        (x, y)
        for y in range(base.height)
        for x in range(base.width)
        if _pixel(base, (x, y))[3] >= _SOURCE_ALPHA_THRESHOLD
    }
    components: list[PixelSet] = _connected_components(visible)
    if len(components) < _REQUIRED_COMPONENT_COUNT:
        msg: str = "The approved base must contain separate body and orb components."
        raise ValueError(msg)
    return components[:_REQUIRED_COMPONENT_COUNT]


def _base_body_texture(base: Image.Image, body_pixels: PixelSet) -> Image.Image:
    sprite: Image.Image = _component_sprite(base, body_pixels)
    texture: Image.Image = Image.new("RGBA", sprite.size, _BODY_DARK_COLOR)
    texture.alpha_composite(sprite)
    for y in range(texture.height):
        for x in range(texture.width):
            pixel: Pixel = _pixel(texture, (x, y))
            if min(pixel[:3]) >= _TEXTURE_HIGHLIGHT_FLOOR:
                texture.putpixel((x, y), _BODY_PURPLE_COLOR)
    sprite.close()
    return texture


def _clean_base(base: Image.Image) -> tuple[Image.Image, int, Image.Image, Image.Image]:
    components: list[PixelSet] = _source_components(base)
    clean: Image.Image = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for component in components:
        for point in component:
            clean.putpixel(point, _pixel(base, point))
    body_texture: Image.Image = _base_body_texture(base, components[0])
    orb: Image.Image = _component_sprite(base, components[1])
    return clean, len(components[0]), body_texture, orb


def _palette(base: Image.Image) -> Image.Image:
    background: Image.Image = Image.new("RGB", base.size, (0, 0, 0))
    background.paste(base, mask=base.getchannel("A"))
    return background.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=_PALETTE_COLOR_COUNT,
    )


def _quantize(frame: Image.Image, palette: Image.Image) -> Image.Image:
    alpha: Image.Image = frame.getchannel("A")
    background: Image.Image = Image.new("RGB", frame.size, (0, 0, 0))
    background.paste(frame, mask=alpha)
    paletted: Image.Image = background.quantize(
        palette=palette,
        dither=Image.Dither.NONE,
    )
    result: Image.Image = paletted.convert("RGBA")
    result.putalpha(alpha.point(lambda value: 255 if value >= _SOURCE_ALPHA_THRESHOLD else 0))
    return result


def _normalized_pose(
    raw: RawPose,
    body_scale: float,
    assets: RenderAssets,
    orb_center: tuple[int, int],
) -> Image.Image:
    body_size: tuple[int, int] = (
        max(1, round(raw.body_mask.width * body_scale)),
        max(1, round(raw.body_mask.height * body_scale)),
    )
    body_mask: Image.Image = raw.body_mask.resize(body_size, Image.Resampling.NEAREST)
    eyes_mask: Image.Image = raw.eyes_mask.resize(body_size, Image.Resampling.NEAREST)
    canvas_mask: Image.Image = Image.new("L", (_CANVAS_SIZE, _CANVAS_SIZE), 0)
    canvas_eyes: Image.Image = Image.new("L", (_CANVAS_SIZE, _CANVAS_SIZE), 0)
    texture_canvas: Image.Image = Image.new("RGBA", (_CANVAS_SIZE, _CANVAS_SIZE), _BODY_DARK_COLOR)
    resized_texture: Image.Image = assets.body_texture.resize(body_size, Image.Resampling.NEAREST)
    body_x: int = round(_BODY_CENTER_X - (body_mask.width - 1) / 2)
    body_y: int = round(_BODY_BOTTOM - (body_mask.height - 1))
    canvas_mask.paste(body_mask, (body_x, body_y))
    canvas_eyes.paste(eyes_mask, (body_x, body_y))
    texture_canvas.paste(resized_texture, (body_x, body_y))
    result: Image.Image = _paint_body(canvas_mask, canvas_eyes, texture_canvas, assets.palette)
    orb_x: int = round(orb_center[0] - (assets.orb.width - 1) / 2)
    orb_y: int = round(orb_center[1] - (assets.orb.height - 1) / 2)
    result.alpha_composite(assets.orb, (orb_x, orb_y))
    return result


def _blend_color(left: Pixel, right: Pixel, amount: float) -> Pixel:
    return cast(
        Pixel,
        tuple(round(start + (end - start) * amount) for start, end in zip(left, right, strict=True)),
    )


def _outline_color(x: int, center_x: float, width: int, highlight: bool) -> Pixel:
    normalized_x: float = min(1.0, max(0.0, (x - (center_x - width / 2)) / width))
    if highlight:
        return _blend_color(_OUTLINE_LEFT_HIGHLIGHT, _OUTLINE_RIGHT_HIGHLIGHT, normalized_x)
    if normalized_x <= _OUTLINE_MIDPOINT:
        return _blend_color(_OUTLINE_LEFT_COLOR, _OUTLINE_MIDDLE_COLOR, normalized_x * 2)
    return _blend_color(
        _OUTLINE_MIDDLE_COLOR,
        _OUTLINE_RIGHT_COLOR,
        (normalized_x - _OUTLINE_MIDPOINT) * 2,
    )


def _paint_body(
    mask: Image.Image,
    eyes: Image.Image,
    texture: Image.Image,
    palette: Image.Image,
) -> Image.Image:
    bounds: Bounds | None = mask.getbbox()
    if bounds is None:
        msg: str = "Cannot paint an empty body mask."
        raise ValueError(msg)
    left, top, right, bottom = bounds
    width: int = right - left
    height: int = bottom - top
    eroded_once: Image.Image = mask.filter(ImageFilter.MinFilter(5))
    eroded_twice: Image.Image = mask.filter(ImageFilter.MinFilter(9))
    eye_glow: Image.Image = eyes.filter(ImageFilter.MaxFilter(5))
    painted: Image.Image = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    center_x: float = (left + right) / 2
    for y in range(top, bottom):
        vertical: float = (y - top) / max(1, height)
        for x in range(left, right):
            if _mask_value(mask, (x, y)) == 0:
                continue
            if _mask_value(eroded_once, (x, y)) == 0:
                color: Pixel = _outline_color(x, center_x, width, False)
            elif _mask_value(eroded_twice, (x, y)) == 0:
                color = _outline_color(x, center_x, width, True)
            else:
                texture_color: Pixel = _pixel(texture, (x, y))
                shade_position: float = min(0.72, vertical * 0.72)
                color = _blend_color(texture_color, _BODY_DARK_COLOR, shade_position)
            if _mask_value(eye_glow, (x, y)) > 0:
                color = _EYE_GLOW_COLOR
            if _mask_value(eyes, (x, y)) > 0:
                color = _EYE_COLOR
            painted.putpixel((x, y), color)
    return _quantize(painted, palette)


def _body_scale(raw: RawPose, target_area: int) -> float:
    area_scale: float = math.sqrt(target_area / raw.body_area)
    width_scale: float = _BODY_MAX_WIDTH / raw.body_mask.width
    height_scale: float = _BODY_MAX_HEIGHT / raw.body_mask.height
    return min(area_scale, width_scale, height_scale)


def _keyframes(
    base: Image.Image,
    reference_path: Path,
) -> list[Image.Image]:
    clean_base, body_area, body_texture, orb = _clean_base(base)
    palette: Image.Image = _palette(clean_base)
    assets: RenderAssets = RenderAssets(palette=palette, body_texture=body_texture, orb=orb)
    reference_poses: list[RawPose] = _load_reference_poses(reference_path)
    keyframes: list[Image.Image] = [
        _normalized_pose(
            pose,
            _body_scale(pose, body_area),
            assets,
            _ORB_CENTERS[index],
        )
        for index, pose in enumerate(reference_poses)
    ]
    body_texture.close()
    orb.close()
    keyframes[0].close()
    keyframes[0] = clean_base
    return keyframes


def _animation_frames(keyframes: list[Image.Image]) -> list[Image.Image]:
    frames: list[Image.Image] = [keyframes[0].copy() for _ in range(_NORMAL_HOLD_FRAMES)]
    frames.extend(frame.copy() for frame in keyframes[1:])
    frames.extend(keyframes[-1].copy() for _ in range(_PUDDLE_HOLD_FRAMES))
    frames.extend(keyframes[index].copy() for index in range(len(keyframes) - 2, -1, -1))
    frames.extend(keyframes[0].copy() for _ in range(_NORMAL_HOLD_FRAMES - 1))
    return frames


def _full_frame(icon: Image.Image) -> Image.Image:
    sprite: Image.Image = icon.resize(
        (_FULL_SPRITE_SIZE, _FULL_SPRITE_SIZE),
        Image.Resampling.NEAREST,
    )
    full: Image.Image = Image.new("RGBA", (_FULL_CANVAS_SIZE, _FULL_CANVAS_SIZE), (0, 0, 0, 0))
    offset: int = (_FULL_CANVAS_SIZE - _FULL_SPRITE_SIZE) // 2
    full.alpha_composite(sprite, (offset, offset))
    return full


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stale_frame in directory.glob("frame_*.png"):
        stale_frame.unlink()


def _save_frames(frames: list[Image.Image], directory: Path) -> None:
    frame_directory: Path = directory / "frames"
    _clear_frames(frame_directory)
    for index, frame in enumerate(frames):
        frame.save(frame_directory / f"frame_{index:03d}.png")


def _save_keyframes(frames: list[Image.Image], directory: Path) -> None:
    keyframe_directory: Path = directory / "keyframes"
    _clear_frames(keyframe_directory)
    for index, frame in enumerate(frames):
        frame.save(keyframe_directory / f"frame_{index:03d}.png")


def _save_sheet(frames: list[Image.Image], target: Path) -> None:
    rows: int = math.ceil(len(frames) / _SHEET_FRAME_COLUMNS)
    sheet: Image.Image = Image.new(
        "RGBA",
        (frames[0].width * _SHEET_FRAME_COLUMNS, frames[0].height * rows),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(frames):
        x: int = index % _SHEET_FRAME_COLUMNS * frame.width
        y: int = index // _SHEET_FRAME_COLUMNS * frame.height
        sheet.alpha_composite(frame, (x, y))
    sheet.save(target)


def _save_animations(frames: list[Image.Image], directory: Path, profile: str) -> None:
    stem: str = f"anishift-slime-sad-melt-recover-{profile}-v1"
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
    for frame in gif_frames:
        frame.close()
    _save_sheet(frames, directory / f"{stem}-sheet.png")


def _save_icon_preview(frames: list[Image.Image], directory: Path) -> None:
    preview_frames: list[Image.Image] = [
        frame.resize((_FULL_CANVAS_SIZE, _FULL_CANVAS_SIZE), Image.Resampling.NEAREST) for frame in frames
    ]
    gif_frames: list[Image.Image] = [prepare_gif_frame(frame) for frame in preview_frames]
    gif_frames[0].save(
        directory / "anishift-slime-sad-melt-recover-icon-v1-preview-640.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=_FRAME_DURATION_MS,
        loop=0,
        disposal=2,
        transparency=255,
        optimize=False,
    )
    for frame in (*preview_frames, *gif_frames):
        frame.close()


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


def _write_manifest(
    output: Path,
    base_path: Path,
    reference_path: Path,
    result: BuildResult,
) -> None:
    manifest: dict[str, object] = {
        "base_source": str(base_path),
        "unified_reference": str(reference_path),
        "motion": "sad-melt-recover-v1",
        "method": "single-atlas-poses-rasterized-to-one-base-grid-and-palette",
        "result": asdict(result),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build the hand-authored sad-melt-recovery animation profiles."""
    args: argparse.Namespace = _parse_args()
    base_path: Path = args.base.resolve()
    reference_path: Path = args.reference.resolve()
    output: Path = args.output.resolve()
    with Image.open(base_path) as base_image:
        base: Image.Image = base_image.convert("RGBA")
    keyframes: list[Image.Image] = _keyframes(base, reference_path)
    icon_frames: list[Image.Image] = _animation_frames(keyframes)
    full_frames: list[Image.Image] = [_full_frame(frame) for frame in icon_frames]
    icon_directory: Path = output / "icon"
    full_directory: Path = output / "full"
    icon_directory.mkdir(parents=True, exist_ok=True)
    full_directory.mkdir(parents=True, exist_ok=True)
    _save_keyframes(keyframes, icon_directory)
    _save_frames(icon_frames, icon_directory)
    _save_frames(full_frames, full_directory)
    _save_animations(icon_frames, icon_directory, "icon")
    _save_animations(full_frames, full_directory, "full")
    _save_icon_preview(icon_frames, icon_directory)
    result: BuildResult = BuildResult(
        keyframe_count=len(keyframes),
        frame_count=len(icon_frames),
        frame_duration_ms=_FRAME_DURATION_MS,
        loop_is_exact=icon_frames[0].tobytes() == icon_frames[-1].tobytes(),
        minimum_margin=_minimum_margin(icon_frames),
        icon_size=_CANVAS_SIZE,
        full_size=_FULL_CANVAS_SIZE,
    )
    _write_manifest(output, base_path, reference_path, result)
    for frame in (*keyframes, *icon_frames, *full_frames):
        frame.close()


if __name__ == "__main__":
    main()
