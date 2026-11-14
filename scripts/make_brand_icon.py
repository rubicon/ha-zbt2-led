# SPDX-License-Identifier: MIT
"""Draw the brand icon (a lit RGB LED) into custom_components/zbt2_led/brand.

Run from the repository root with a Python that has Pillow installed:

    python scripts/make_brand_icon.py

The output is deterministic, so re-running it only changes the files when
this script changes.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BRAND_DIR = Path("custom_components/zbt2_led/brand")


def draw_icon(size: int) -> Image.Image:
    """Return a square RGBA icon of the given pixel size."""
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    centre = size / 2
    for index, colour in enumerate(((255, 64, 64), (64, 220, 96), (72, 128, 255))):
        angle = math.radians(90 + index * 120)
        offset = 26 * scale
        x = centre + offset * math.cos(angle)
        y = centre - offset * math.sin(angle)
        radius = 70 * scale
        glow_draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=(*colour, 170)
        )
    glow = glow.filter(ImageFilter.GaussianBlur(18 * scale))
    image.alpha_composite(glow)

    core = ImageDraw.Draw(image)
    radius = 46 * scale
    core.ellipse(
        (centre - radius, centre - radius, centre + radius, centre + radius),
        fill=(255, 255, 255, 235),
    )
    return image


def main() -> None:
    """Write icon.png (256 px) and icon@2x.png (512 px)."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    draw_icon(256).save(BRAND_DIR / "icon.png", optimize=True)
    draw_icon(512).save(BRAND_DIR / "icon@2x.png", optimize=True)


if __name__ == "__main__":
    main()
