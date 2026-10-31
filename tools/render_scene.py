"""Render a debug scene offscreen to a PNG with the QPainter renderer.

    .venv/bin/python tools/render_scene.py title out.png
    .venv/bin/python tools/render_scene.py lvl:12:8 out.png --size 640 --seed 1

Scene names are the web demo's `#test=<scene>[:arg[:arg2]]` ones (see overblaster/debug_scenes.py).
"""

import argparse
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overblaster.core import Game  # noqa: E402
from overblaster.debug_scenes import apply_scene  # noqa: E402
from overblaster.render.draw import Draw  # noqa: E402
from overblaster.render.scene import draw_game  # noqa: E402

_app = None


def render(scene: str, size: int = 640, seed: int = 1) -> QImage:
    """The scene as an ARGB image, size x size px."""
    global _app
    _app = QApplication.instance() or QApplication(sys.argv[:1])
    game = Game(seed=seed)
    name, *args = scene.split(":")
    apply_scene(game, name, *(args + [None, None])[:2])
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0xFF000000)
    p = QPainter(img)
    draw_game(Draw(p, size), game)
    p.end()
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene")
    ap.add_argument("out")
    ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    render(a.scene, a.size, a.seed).save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
