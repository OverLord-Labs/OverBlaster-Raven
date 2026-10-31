"""The whole game screen, painted by one widget.

`render.scene.draw_game` (a QPainter port of the web game's renderer) draws the title, the story intro,
the playfield and the game-over screen from a core.Game. This widget is the surface it paints on:
the full game area, transparent to the mouse (so gaze and cursor pass through to the dwell buttons
above it), repainted once per tick. The picture is black where nothing is lit, which is see-through
on the glasses' additive display.

A small debug panel (mic level against the fire threshold, IMU and gaze state) can be switched on;
it paints over the scene and costs nothing while it is off.
"""

from typing import List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import config as C
from .render.draw import Draw
from .render.scene import draw_game


def paint_dwell(painter: QPainter, size: int, dwell) -> None:
    """The fill that grows left to right across a plate while the gaze rests on it (name -> (Box, progress 0..1))."""
    k = size / 640.0
    for box, progress in dwell.values():
        painter.fillRect(QRectF(box.x * k, box.y * k, box.w * k * progress, box.h * k), QColor(0, 229, 255, 70))
        painter.setPen(QPen(QColor(0, 229, 255, 230), max(1.0, 3 * k)))
        painter.drawRect(QRectF(box.x * k, box.y * k, box.w * k, box.h * k))


def paint_game(painter: QPainter, size: int, game, draw: Optional[Draw] = None, dwell=None) -> Draw:
    """Paint `game` into `painter` (a square `size` px). Reuses `draw` between frames. `dwell` is the plates' dwell fills."""
    d = draw or Draw()
    d.begin(painter, size)
    draw_game(d, game)
    if dwell:
        paint_dwell(painter, size, dwell)
    return d


def render_image(game, size: int = 640) -> QImage:
    """The game as an ARGB image (tests, screenshots)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(0xFF000000)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    paint_game(p, size, game)
    p.end()
    return img


class DebugInfo:
    """What the debug panel shows (filled in by the app each tick)."""

    def __init__(self) -> None:
        self.mic = 0.0
        self.hot = False  # the trigger fired recently
        self.lines: List[str] = []


class SceneLayer(QWidget):
    def __init__(self, width: int, height: int, game) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)  # it fills every pixel itself
        self.setFixedSize(int(width), int(height))
        self.game = game
        self.debug: Optional[DebugInfo] = None
        self.dwell: dict = {}  # plate name -> (Box, progress): painted over the scene
        self._draw = Draw()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._draw = paint_game(p, min(self.width(), self.height()), self.game, self._draw, self.dwell)
        if self.debug is not None:
            self._paint_debug(p)
        p.end()

    def _paint_debug(self, p: QPainter) -> None:
        dbg, h = self.debug, self.height()
        x, y = 28, h - 118
        scale = 220 / C.DEBUG_MIC_FULL_SCALE
        p.setPen(QColor("#FFFFFF"))
        p.drawText(x, y + 14, f"MIC {dbg.mic:0.3f}  fires > {C.VOICE_HI:0.2f}" + ("  PEW!" if dbg.hot else ""))
        p.fillRect(QRectF(x, y + 26, max(4.0, 220 * min(1.0, dbg.mic / C.DEBUG_MIC_FULL_SCALE)), 12), QColor("#FF3CDC" if dbg.hot else "#00E5FF"))
        p.fillRect(QRectF(x + C.VOICE_HI * scale, y + 22, 4, 20), QColor("#FFC800"))  # fires above this
        p.fillRect(QRectF(x + C.VOICE_LO * scale, y + 22, 4, 20), QColor("#FFFFFF"))  # re-arms below this
        p.setPen(QPen(QColor("#FFFFFF")))
        for i, line in enumerate(dbg.lines):
            p.drawText(x, y + 60 + 20 * i, line)


class NullLayer:
    """Stands in for the widget when no Qt application is running (tests with the fake framework)."""

    def __init__(self, game) -> None:
        self.game = game
        self.debug: Optional[DebugInfo] = None
        self.dwell: dict = {}
        self.updates = 0

    def update(self) -> None:
        self.updates += 1


def make_scene_layer(app, width: int, height: int, game):
    """The real widget (added to `app` at its top-left) if a Qt application is running, else a stand-in."""
    if QApplication.instance() is None:
        return NullLayer(game)
    layer = SceneLayer(width, height, game)
    app.add(layer, x=0, y=0)
    return layer
