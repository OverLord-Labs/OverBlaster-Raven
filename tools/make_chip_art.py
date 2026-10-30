"""Draws assets/chip.png: the Overlord BMS, a cyan die with pins and the Overlord "OD" mark in the middle.

Run it again if assets/overlord_od.png changes:  .venv/bin/python tools/make_chip_art.py
The OD mark is the favicon from overlord-labs.com (512 px, downscaled to 160 px).
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
SIZE = 64  # app.py loads it at 64 px


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 (Qt needs one to load pixmaps)
    scale = 4  # draw big, then shrink: smoother pins
    S = SIZE * scale
    img = QImage(S, S, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    cyan = QColor(0, 229, 255)
    die = QRectF(S * 0.2, S * 0.2, S * 0.6, S * 0.6)
    p.setPen(QPen(cyan, S * 0.03))
    for i in range(4):  # four pins on every side
        o = S * (0.30 + i * 0.133)
        for a, b in (((o, S * 0.2), (o, S * 0.08)), ((o, S * 0.8), (o, S * 0.92)), ((S * 0.2, o), (S * 0.08, o)), ((S * 0.8, o), (S * 0.92, o))):
            p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
    p.setBrush(QColor(0, 26, 31))
    p.drawRoundedRect(die, S * 0.04, S * 0.04)
    logo = QPixmap(os.path.join(ASSETS, "overlord_od.png"))
    side = S * 0.52
    p.drawPixmap(QRectF((S - side) / 2, (S - side) / 2, side, side), logo, QRectF(logo.rect()))
    p.end()
    out = img.scaled(SIZE, SIZE, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out.save(os.path.join(ASSETS, "chip.png"))
    print("wrote", os.path.join(ASSETS, "chip.png"))


if __name__ == "__main__":
    main()
