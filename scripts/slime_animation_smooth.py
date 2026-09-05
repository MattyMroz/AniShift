from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import zlib
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Final

from PIL import Image, ImageChops, ImageDraw
from slime_animation import MotionFrame, build_motion_frames, prepare_gif_frame

__all__ = ["main"]

# ── Constants ──

_CANVAS_SIZE: Final = 4096
"""Width and height of every smooth 4K frame."""

_PREVIEW_SIZE: Final = 1024
"""Width and height of the lightweight animated preview."""

_GIF_PREVIEW_SIZE: Final = 640
"""Compatibility preview size for viewers without animated WebP support."""

_FRAME_DURATION_MS: Final = 60
"""Duration shared with the accepted pixel v1 animation."""

_COMPONENT_ALPHA_THRESHOLD: Final = 8
"""Alpha threshold used only to isolate connected source components."""

_FLOOD_FILL_MARKER: Final = 128
"""Temporary mask value assigned to the selected connected component."""

_BODY_SEED: Final = (2048, 2500)
"""Point inside the body component of the approved 4K source."""

_ORB_SEED: Final = (2670, 1430)
"""Point inside the orb component of the approved 4K source."""

_BODY_TARGET_HEIGHT: Final = 2450
"""Resting body height with enough room for the complete jump."""

_BODY_BOTTOM: Final = 3600
"""Resting body baseline on the 4K canvas."""

_MESH_COLUMNS: Final = 32
"""Horizontal density of the continuous body deformation mesh."""

_MESH_ROWS: Final = 128
"""Vertical density of the continuous body deformation mesh."""

_LOGICAL_BODY_HEIGHT: Final = 110.0
"""Body height of the accepted 128-pixel motion coordinate system."""

_LOGICAL_BODY_WIDTH: Final = 92.0
"""Body width of the accepted 128-pixel motion coordinate system."""

_ORB_DEPTH_SCALE: Final = 0.12
"""Perspective scale change between the front and back orbit halves."""

_ORB_FRONT_VERTICAL_RATIO: Final = 0.10
"""Foreground orbit drop that keeps the orb above the eyes."""

_ORB_BACK_VERTICAL_RATIO: Final = 0.16
"""Background orbit lift behind the flame."""

_WEBP_QUALITY: Final = 92
"""Quality of animated WebP exports."""

_WEBP_METHOD: Final = 4
"""WebP compression effort balanced for large animation frames."""

_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
"""Required signature at the beginning of every PNG and APNG file."""

_PNG_IHDR: Final = b"IHDR"
"""PNG image header chunk identifier."""

_PNG_IDAT: Final = b"IDAT"
"""PNG compressed image data chunk identifier."""

_PNG_IEND: Final = b"IEND"
"""PNG end chunk identifier."""

_PNG_WORD_SIZE: Final = 4
"""Byte width of PNG lengths, identifiers, checksums, and sequence numbers."""


type Bounds = tuple[int, int, int, int]
type PngChunk = tuple[bytes, bytes]
type MeshQuad = tuple[float, float, float, float, float, float, float, float]
type MeshCell = tuple[tuple[int, int, int, int], MeshQuad]


@dataclass(frozen=True, slots=True)
class SmoothSource:
    """Prepared high-resolution layers and their resting geometry."""

    body: Image.Image
    orb: Image.Image
    body_center_x: float
    body_bottom: float
    orb_center_y: float
    orb_horizontal_radius: float


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Measurements written to the smooth animation manifest."""

    canvas_size: int
    frame_count: int
    frame_duration_ms: int
    minimum_margin: int
    loop_is_exact: bool


def _parse_args() -> argparse.Namespace:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Build the smooth AniShift slime v1 animation from its 4K master.",
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _component_mask(alpha: Image.Image, seed: tuple[int, int]) -> Image.Image:
    binary: Image.Image = alpha.point(lambda value: 255 if value >= _COMPONENT_ALPHA_THRESHOLD else 0)
    if binary.getpixel(seed) == 0:
        msg: str = f"Component seed {seed} is outside the visible source."
        raise ValueError(msg)
    ImageDraw.floodfill(binary, seed, _FLOOD_FILL_MARKER, thresh=0)
    return binary.point(lambda value: 255 if value == _FLOOD_FILL_MARKER else 0)


def _extract_component(image: Image.Image, seed: tuple[int, int]) -> tuple[Image.Image, Bounds]:
    alpha: Image.Image = image.getchannel("A")
    mask: Image.Image = _component_mask(alpha, seed)
    bounds: Bounds | None = mask.getbbox()
    if bounds is None:
        msg: str = f"No connected component found at {seed}."
        raise ValueError(msg)
    component: Image.Image = image.crop(bounds)
    component_alpha: Image.Image = ImageChops.multiply(alpha.crop(bounds), mask.crop(bounds))
    component.putalpha(component_alpha)
    return component, bounds


def _center(bounds: Bounds) -> tuple[float, float]:
    left, top, right, bottom = bounds
    return (left + right - 1) / 2, (top + bottom - 1) / 2


def _resize_rgba(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    premultiplied: Image.Image = image.convert("RGBa")
    return premultiplied.resize(size, Image.Resampling.LANCZOS).convert("RGBA")


def _prepare_source(image: Image.Image) -> tuple[SmoothSource, Bounds, Bounds]:
    if image.size != (_CANVAS_SIZE, _CANVAS_SIZE):
        msg: str = f"Expected a {_CANVAS_SIZE}x{_CANVAS_SIZE} source, got {image.size}."
        raise ValueError(msg)
    body, body_bounds = _extract_component(image, _BODY_SEED)
    orb, orb_bounds = _extract_component(image, _ORB_SEED)
    scale: float = _BODY_TARGET_HEIGHT / body.height
    body_width: int = round(body.width * scale)
    orb_size: tuple[int, int] = (round(orb.width * scale), round(orb.height * scale))
    prepared_body: Image.Image = _resize_rgba(body, (body_width, _BODY_TARGET_HEIGHT))
    prepared_orb: Image.Image = _resize_rgba(orb, orb_size)
    source_body_center_x, _ = _center(body_bounds)
    source_orb_center_x, source_orb_center_y = _center(orb_bounds)
    resting_body_top: float = _BODY_BOTTOM - _BODY_TARGET_HEIGHT
    orb_center_y: float = resting_body_top + (source_orb_center_y - body_bounds[1]) * scale
    orb_horizontal_radius: float = (source_orb_center_x - source_body_center_x) * scale
    prepared: SmoothSource = SmoothSource(
        body=prepared_body,
        orb=prepared_orb,
        body_center_x=_CANVAS_SIZE / 2,
        body_bottom=float(_BODY_BOTTOM),
        orb_center_y=orb_center_y,
        orb_horizontal_radius=orb_horizontal_radius,
    )
    return prepared, body_bounds, orb_bounds


def _logical_vertical(value: float, source: SmoothSource) -> float:
    return value / _LOGICAL_BODY_HEIGHT * source.body.height


def _logical_horizontal(value: float, source: SmoothSource) -> float:
    return value / _LOGICAL_BODY_WIDTH * source.body.width


def _inverse_body_point(
    source: SmoothSource,
    motion: MotionFrame,
    destination_x: float,
    destination_y: float,
) -> tuple[float, float]:
    jump: float = _logical_vertical(motion.jump, source)
    bend: float = _logical_horizontal(motion.bend, source)
    wave: float = _logical_horizontal(motion.wave, source)
    arch: float = _logical_vertical(motion.arch, source)
    initial_source_y: float = source.body.height
    initial_source_y += (destination_y - source.body_bottom - jump) / motion.scale_y
    initial_upward: float = max(0.0, min(1.0, 1.0 - initial_source_y / source.body.height))
    relative_x: float = (destination_x - source.body_center_x) / (source.body.width / 2)
    arch_offset: float = arch * math.sin(relative_x * math.pi) * math.sin(initial_upward * math.pi)
    source_y: float = source.body.height
    source_y += (destination_y - source.body_bottom - jump - arch_offset) / motion.scale_y
    upward: float = max(0.0, min(1.0, 1.0 - source_y / source.body.height))
    lateral_offset: float = bend * upward**1.35
    lateral_offset += wave * math.sin(upward * math.tau + motion.wave_phase) * math.sin(upward * math.pi)
    width_scale: float = motion.scale_x * (1.0 + motion.bulge * math.sin(upward * math.pi))
    source_x: float = source.body.width / 2
    source_x += (destination_x - source.body_center_x - lateral_offset) / width_scale
    return source_x, source_y


def _body_mesh(source: SmoothSource, motion: MotionFrame) -> list[MeshCell]:
    x_edges: list[int] = [round(index * _CANVAS_SIZE / _MESH_COLUMNS) for index in range(_MESH_COLUMNS + 1)]
    y_edges: list[int] = [round(index * _CANVAS_SIZE / _MESH_ROWS) for index in range(_MESH_ROWS + 1)]
    mesh: list[MeshCell] = []
    for row in range(_MESH_ROWS):
        top: int = y_edges[row]
        bottom: int = y_edges[row + 1]
        for column in range(_MESH_COLUMNS):
            left: int = x_edges[column]
            right: int = x_edges[column + 1]
            upper_left: tuple[float, float] = _inverse_body_point(source, motion, left, top)
            lower_left: tuple[float, float] = _inverse_body_point(source, motion, left, bottom)
            lower_right: tuple[float, float] = _inverse_body_point(source, motion, right, bottom)
            upper_right: tuple[float, float] = _inverse_body_point(source, motion, right, top)
            quad: MeshQuad = (*upper_left, *lower_left, *lower_right, *upper_right)
            mesh.append(((left, top, right, bottom), quad))
    return mesh


def _render_body(source: SmoothSource, motion: MotionFrame) -> Image.Image:
    premultiplied: Image.Image = source.body.convert("RGBa")
    transformed: Image.Image = premultiplied.transform(
        (_CANVAS_SIZE, _CANVAS_SIZE),
        Image.Transform.MESH,
        _body_mesh(source, motion),
        Image.Resampling.BICUBIC,
        fillcolor=(0, 0, 0, 0),
    )
    return transformed.convert("RGBA")


def _render_orb(source: SmoothSource, motion: MotionFrame) -> tuple[Image.Image, bool]:
    layer: Image.Image = Image.new(
        "RGBA",
        (_CANVAS_SIZE, _CANVAS_SIZE),
        (0, 0, 0, 0),
    )
    normalized_angle: float = motion.orb_angle % 360.0
    radians: float = math.radians(normalized_angle)
    depth: float = math.sin(radians)
    perspective: float = motion.orb_scale * (1.0 + _ORB_DEPTH_SCALE * depth)
    orb_size: tuple[int, int] = (
        max(1, round(source.orb.width * perspective)),
        max(1, round(source.orb.height * perspective)),
    )
    orb: Image.Image = _resize_rgba(source.orb, orb_size)
    source_upward: float = (source.body_bottom - source.orb_center_y) / source.body.height
    bend: float = _logical_horizontal(motion.bend, source)
    wave: float = _logical_horizontal(motion.wave, source)
    lateral_offset: float = bend * source_upward**1.35
    lateral_offset += wave * math.sin(source_upward * math.tau + motion.wave_phase) * math.sin(source_upward * math.pi)
    orbit_center_y: float = source.body_bottom + (source.orb_center_y - source.body_bottom) * motion.scale_y
    orbit_center_y += _logical_vertical(motion.jump, source)
    horizontal_radius: float = source.orb_horizontal_radius
    horizontal_radius *= motion.scale_x * (1.0 + motion.bulge)
    vertical_ratio: float = _ORB_FRONT_VERTICAL_RATIO if depth >= 0.0 else _ORB_BACK_VERTICAL_RATIO
    center_x: float = source.body_center_x + lateral_offset
    center_x += horizontal_radius * math.cos(radians)
    center_y: float = orbit_center_y + source.body.height * vertical_ratio * depth
    destination: tuple[int, int] = (
        round(center_x - (orb.width - 1) / 2),
        round(center_y - (orb.height - 1) / 2),
    )
    layer.alpha_composite(orb, destination)
    return layer, depth >= 0.0


def _render_frame(source: SmoothSource, motion: MotionFrame) -> Image.Image:
    body: Image.Image = _render_body(source, motion)
    orb, orb_is_in_front = _render_orb(source, motion)
    if orb_is_in_front:
        body.alpha_composite(orb)
        return body
    orb.alpha_composite(body)
    return orb


def _clear_frames(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stale_frame in directory.glob("frame_*.png"):
        stale_frame.unlink()


def _render_frames(source: SmoothSource, motions: list[MotionFrame], directory: Path) -> list[Path]:
    _clear_frames(directory)
    paths: list[Path] = []
    for index, motion in enumerate(motions):
        frame: Image.Image = _render_frame(source, motion)
        target: Path = directory / f"frame_{index:03d}.png"
        frame.save(target, compress_level=4)
        paths.append(target)
    return paths


def _save_preview_webp(frame_paths: list[Path], target: Path) -> None:
    frames: list[Image.Image] = []
    try:
        for path in frame_paths:
            with Image.open(path) as image:
                frame: Image.Image = image.convert("RGBA").resize(
                    (_PREVIEW_SIZE, _PREVIEW_SIZE),
                    Image.Resampling.LANCZOS,
                )
            frames.append(frame)
        frames[0].save(
            target,
            save_all=True,
            append_images=frames[1:],
            duration=_FRAME_DURATION_MS,
            loop=0,
            format="WEBP",
            lossless=False,
            quality=_WEBP_QUALITY,
            method=_WEBP_METHOD,
        )
    finally:
        for frame in frames:
            frame.close()


def _save_preview_gif(frame_paths: list[Path], target: Path) -> None:
    frames: list[Image.Image] = []
    try:
        for path in frame_paths:
            with Image.open(path) as image:
                resized: Image.Image = image.convert("RGBA").resize(
                    (_GIF_PREVIEW_SIZE, _GIF_PREVIEW_SIZE),
                    Image.Resampling.LANCZOS,
                )
            frames.append(prepare_gif_frame(resized))
            resized.close()
        frames[0].save(
            target,
            save_all=True,
            append_images=frames[1:],
            duration=_FRAME_DURATION_MS,
            loop=0,
            disposal=2,
            transparency=255,
            optimize=False,
        )
    finally:
        for frame in frames:
            frame.close()


def _read_png_chunks(path: Path) -> Iterator[PngChunk]:
    with path.open("rb") as png_file:
        if png_file.read(len(_PNG_SIGNATURE)) != _PNG_SIGNATURE:
            msg: str = f"Invalid PNG signature: {path}"
            raise ValueError(msg)
        while length_data := png_file.read(_PNG_WORD_SIZE):
            if len(length_data) != _PNG_WORD_SIZE:
                msg = f"Truncated PNG chunk length: {path}"
                raise ValueError(msg)
            length: int = struct.unpack(">I", length_data)[0]
            chunk_type: bytes = png_file.read(_PNG_WORD_SIZE)
            data: bytes = png_file.read(length)
            checksum: bytes = png_file.read(_PNG_WORD_SIZE)
            if len(chunk_type) != _PNG_WORD_SIZE or len(data) != length or len(checksum) != _PNG_WORD_SIZE:
                msg = f"Truncated PNG chunk: {path}"
                raise ValueError(msg)
            yield chunk_type, data
            if chunk_type == _PNG_IEND:
                return


def _write_png_chunk(output: BinaryIO, chunk_type: bytes, data: bytes) -> None:
    checksum: int = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    output.write(struct.pack(">I", len(data)))
    output.write(chunk_type)
    output.write(data)
    output.write(struct.pack(">I", checksum))


def _frame_control(sequence: int, width: int, height: int) -> bytes:
    return struct.pack(
        ">IIIIIHHBB",
        sequence,
        width,
        height,
        0,
        0,
        _FRAME_DURATION_MS,
        1000,
        0,
        0,
    )


def _save_apng(frame_paths: list[Path], target: Path) -> None:
    first_chunks: list[PngChunk] = list(_read_png_chunks(frame_paths[0]))
    header: bytes | None = next(
        (data for chunk_type, data in first_chunks if chunk_type == _PNG_IHDR),
        None,
    )
    if header is None:
        msg: str = "First animation frame has no PNG header."
        raise ValueError(msg)
    width, height = struct.unpack(">II", header[:8])
    ancillary: list[PngChunk] = [chunk for chunk in first_chunks if chunk[0] not in {_PNG_IHDR, _PNG_IDAT, _PNG_IEND}]
    first_image_data: list[bytes] = [data for chunk_type, data in first_chunks if chunk_type == _PNG_IDAT]
    sequence: int = 0
    with target.open("wb") as output:
        output.write(_PNG_SIGNATURE)
        _write_png_chunk(output, _PNG_IHDR, header)
        for chunk_type, data in ancillary:
            _write_png_chunk(output, chunk_type, data)
        _write_png_chunk(output, b"acTL", struct.pack(">II", len(frame_paths), 0))
        _write_png_chunk(output, b"fcTL", _frame_control(sequence, width, height))
        sequence += 1
        for data in first_image_data:
            _write_png_chunk(output, _PNG_IDAT, data)
        for path in frame_paths[1:]:
            _write_png_chunk(output, b"fcTL", _frame_control(sequence, width, height))
            sequence += 1
            for chunk_type, data in _read_png_chunks(path):
                if chunk_type != _PNG_IDAT:
                    continue
                _write_png_chunk(output, b"fdAT", struct.pack(">I", sequence) + data)
                sequence += 1
        _write_png_chunk(output, _PNG_IEND, b"")


def _minimum_margin(frame_paths: list[Path]) -> int:
    margins: list[int] = []
    for path in frame_paths:
        with Image.open(path) as image:
            bounds: Bounds | None = image.getchannel("A").getbbox()
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            margins.append(min(left, top, image.width - right, image.height - bottom))
    if not margins:
        msg: str = "Smooth animation contains no visible frames."
        raise ValueError(msg)
    return min(margins)


def _frames_are_equal(first: Path, last: Path) -> bool:
    with Image.open(first) as first_image, Image.open(last) as last_image:
        return first_image.convert("RGBA").tobytes() == last_image.convert("RGBA").tobytes()


def _sha256(path: Path) -> str:
    digest: hashlib._Hash = hashlib.sha256()
    with path.open("rb") as source_file:
        while chunk := source_file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(
    output: Path,
    source_path: Path,
    body_bounds: Bounds,
    orb_bounds: Bounds,
    result: BuildResult,
) -> None:
    manifest: dict[str, object] = {
        "source": str(source_path),
        "source_sha256": _sha256(source_path),
        "body_bounds": list(body_bounds),
        "orb_bounds": list(orb_bounds),
        "motion": "spin-squash-jump-v1",
        "profile": "smooth-4k",
        "result": asdict(result),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Build transparent smooth 4K frames, APNG, and a WebP preview."""
    args: argparse.Namespace = _parse_args()
    source_path: Path = args.source.resolve()
    output: Path = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as source_image:
        source_rgba: Image.Image = source_image.convert("RGBA")
    source, body_bounds, orb_bounds = _prepare_source(source_rgba)
    motions: list[MotionFrame] = build_motion_frames()
    frame_paths: list[Path] = _render_frames(source, motions, output / "frames")
    stale_webp: Path = output / "anishift-slime-spin-squash-jump-smooth-4k-v1.webp"
    stale_webp.unlink(missing_ok=True)
    _save_apng(
        frame_paths,
        output / "anishift-slime-spin-squash-jump-smooth-4k-v1.apng",
    )
    _save_preview_webp(
        frame_paths,
        output / "anishift-slime-spin-squash-jump-smooth-preview-1024-v1.webp",
    )
    _save_preview_gif(
        frame_paths,
        output / "anishift-slime-spin-squash-jump-smooth-preview-640-v1.gif",
    )
    result: BuildResult = BuildResult(
        canvas_size=_CANVAS_SIZE,
        frame_count=len(frame_paths),
        frame_duration_ms=_FRAME_DURATION_MS,
        minimum_margin=_minimum_margin(frame_paths),
        loop_is_exact=_frames_are_equal(frame_paths[0], frame_paths[-1]),
    )
    _write_manifest(output, source_path, body_bounds, orb_bounds, result)


if __name__ == "__main__":
    main()
