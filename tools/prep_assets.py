"""Build OverBlaster's art from the old Planet Zapper animation frames.

    .venv/bin/python tools/prep_assets.py [path/to/Android/planets]

Why GIFs: stepping animation frames from Python would cost battery, and a looping
GIF animates itself inside MediaViewer. MediaViewer is fixed-size and reloads its
image on every resize, so worlds are pre-rendered at three size bands and the game
swaps between them with load_media() instead of resizing.
Frames are flattened onto black because the glasses are additive: black is
transparent and costs no light, so no alpha channel is needed.
"""

import glob
import os
import sys

from PIL import Image, ImageDraw

SRC_DEFAULT = os.path.expanduser("~/Documents/Android/planets")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BANDS = (64, 96, 128)  # px, multiples of 4 as MediaViewer requires; keep in sync with config.WORLD_BANDS
KEEP_EVERY = 2  # 50 frames -> 25 frames
FRAME_MS = 500  # 25 frames x 500 ms = a 12.5 s spin, like the original
SETS = {  # kind -> (folder, filename pattern)
    "a": ("4", "frame_*.png"),
    "b": ("5", "planet5_frame_*.png"),
    "c": ("6", "planet6_frame_*.png"),
}
GOLD = (255, 200, 0)
CYAN = (0, 229, 255)
SS = 4  # supersampling factor for the drawn icons


def flatten(path: str, size: int) -> Image.Image:
    rgba = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
    base = Image.new("RGB", rgba.size, (0, 0, 0))
    base.paste(rgba, mask=rgba.getchannel("A"))
    return base


def tint_gold(img: Image.Image) -> Image.Image:
    """Recolor to a bright gold so the chip carrier stands out from other worlds."""
    gray = img.convert("L")
    return Image.merge(
        "RGB", [gray.point(lambda v, c=c: min(255, int(v * c / 255 * 1.4))) for c in GOLD]
    )


def save_gif(frames, path: str) -> None:
    frames[0].save(
        path, save_all=True, append_images=frames[1:], duration=FRAME_MS, loop=0, optimize=False
    )


def build_worlds(src: str) -> None:
    os.makedirs(os.path.join(OUT, "worlds"), exist_ok=True)
    for kind, (folder, pattern) in SETS.items():
        files = sorted(glob.glob(os.path.join(src, folder, pattern)))
        if not files:
            sys.exit(f"No frames found in {os.path.join(src, folder)} ({pattern})")
        for size in BANDS:
            frames = [flatten(f, size) for f in files[::KEEP_EVERY]]
            save_gif(frames, os.path.join(OUT, "worlds", f"world_{kind}_{size}.gif"))
            if kind == "a":  # the chip carrier is a gold-tinted copy of the first world
                save_gif([tint_gold(f) for f in frames], os.path.join(OUT, "worlds", f"world_chip_{size}.gif"))
        print(f"world_{kind}_*.gif: {len(frames)} frames x {len(BANDS)} sizes")


def canvas(size: int) -> Image.Image:
    return Image.new("RGB", (size * SS, size * SS), (0, 0, 0))


def finish(img: Image.Image, name: str) -> None:
    size = img.width // SS
    img.resize((size, size), Image.LANCZOS).save(os.path.join(OUT, name))
    print(f"{name}: {size} x {size}")


def poly(draw, pts, size, **kw):
    draw.polygon([(x * size * SS, y * size * SS) for x, y in pts], **kw)


def build_icons() -> None:
    # Energy crystal: a faceted cyan diamond.
    s = 40
    im = canvas(s)
    d = ImageDraw.Draw(im)
    poly(d, [(0.5, 0.02), (0.88, 0.38), (0.5, 0.98), (0.12, 0.38)], s, fill=(0, 150, 190))
    poly(d, [(0.5, 0.02), (0.12, 0.38), (0.5, 0.42)], s, fill=CYAN)
    poly(d, [(0.5, 0.02), (0.88, 0.38), (0.5, 0.42)], s, fill=(120, 245, 255))
    poly(d, [(0.12, 0.38), (0.88, 0.38), (0.5, 0.98)], s, outline=(255, 255, 255), width=SS)
    finish(im, "crystal.png")

    # Overlord Battery Gauge Chip: gold square chip with pins and a gauge bar.
    s = 64
    im = canvas(s)
    d = ImageDraw.Draw(im)
    for i in range(4):  # pins
        p = (0.22 + i * 0.18) * s * SS
        for a, b in ((p, 0.06), (p, 0.84)):
            d.rectangle([a, b * s * SS, a + 0.07 * s * SS, (b + 0.1) * s * SS], fill=GOLD)
        d.rectangle([0.06 * s * SS, p, 0.16 * s * SS, p + 0.07 * s * SS], fill=GOLD)
        d.rectangle([0.84 * s * SS, p, 0.94 * s * SS, p + 0.07 * s * SS], fill=GOLD)
    d.rectangle([0.16 * s * SS, 0.16 * s * SS, 0.84 * s * SS, 0.84 * s * SS], fill=(40, 30, 0), outline=GOLD, width=2 * SS)
    d.rectangle([0.28 * s * SS, 0.42 * s * SS, 0.72 * s * SS, 0.58 * s * SS], outline=(255, 255, 255), width=SS)
    d.rectangle([0.30 * s * SS, 0.44 * s * SS, 0.64 * s * SS, 0.56 * s * SS], fill=GOLD)
    finish(im, "chip.png")

    # Solid pixels used (stretched) for HUD bars: cyan, gold and white.
    for name, color in (
        ("bar_cyan.png", CYAN),
        ("bar_gold.png", GOLD),
        ("bar_white.png", (255, 255, 255)),
        ("bar_green.png", (120, 255, 120)),  # crosshair ticks
        ("bar_pink.png", (255, 60, 220)),  # shot tracers, like the old game's magenta bullets
    ):
        Image.new("RGB", (4, 4), color).save(os.path.join(OUT, name))
        print(f"{name}: 4 x 4")


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else SRC_DEFAULT
    os.makedirs(OUT, exist_ok=True)
    build_worlds(src)
    build_icons()
    total = sum(os.path.getsize(p) for p in glob.glob(os.path.join(OUT, "**", "*.*"), recursive=True))
    print(f"assets total: {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
