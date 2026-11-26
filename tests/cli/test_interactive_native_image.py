from __future__ import annotations

import pytest
from PIL import Image

from anishift.cli.interactive.native_image import NATIVE_IMAGE_ANCHOR, encode_sixel
from anishift.cli.interactive.prompts import _native_anchor

pytestmark = pytest.mark.unit


def test_sixel_bands_skip_transparent_pixels_and_trim_empty_columns() -> None:
    image: Image.Image = Image.new("RGBA", (2, 7), (0, 0, 0, 0))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 6), (255, 0, 0, 255))
    palette: Image.Image = Image.new("P", (1, 1))
    palette.putpalette([255, 0, 0] * 256)

    assert encode_sixel(image, palette) == '\x1bP9;1;0q"1;1;2;7#0;2;100;0;0#0@-#0?@\x1b\\'


def test_sixel_runs_of_four_use_the_repeat_introducer() -> None:
    image: Image.Image = Image.new("RGBA", (5, 1), (0, 0, 255, 255))
    palette: Image.Image = Image.new("P", (1, 1))
    palette.putpalette([0, 0, 255] * 256)

    assert encode_sixel(image, palette).endswith("#0!5@\x1b\\")


def test_anchor_column_counts_wide_characters_as_two_cells() -> None:
    assert _native_anchor(f"x\n日本 {NATIVE_IMAGE_ANCHOR}") == (1, 5)
