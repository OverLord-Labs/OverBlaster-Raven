"""The overlay that draws the shapes from fx.py.

One transparent widget over the whole game area, painted with QPainter. It repaints only when
there is something to draw (or something to clear), so it costs nothing between shots. Unlike a
MediaViewer it paints no opaque backing, so nothing under it is cut out, and it is transparent to
the mouse so gaze and mouse positions pass straight through it.
"""

import math
from typing import List

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from . import fx


class FxLayer(QWidget):
    def __init__(self, width: int, height: int) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(width, height)
        self._shapes: List[object] = []

    def set_shapes(self, shapes: List[object]) -> None:
        if shapes == self._shapes:  # nothing changed: don't repaint the whole game area
            return
        self._shapes = shapes
        self.update()

    def paintEvent(self, _event) -> None:
        if not self._shapes:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for shape in self._shapes:
            color = QColor(*shape.color, int(255 * max(0.0, min(1.0, shape.alpha))))
            if isinstance(shape, fx.Line):
                pen = QPen(color, shape.width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(int(shape.x1), int(shape.y1), int(shape.x2), int(shape.y2))
            elif isinstance(shape, fx.Circle):
                if shape.width > 0:
                    painter.setPen(QPen(color, shape.width))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                r = shape.radius
                painter.drawEllipse(int(shape.x - r), int(shape.y - r), int(2 * r), int(2 * r))
            elif isinstance(shape, fx.Rect):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(int(shape.x), int(shape.y), int(shape.w), int(shape.h))
        painter.end()


class ArrowWidget(QWidget):
    """An arrowhead that can point any way round. It is a small widget moved and turned each tick,
    so a pointer that is always on screen never forces the whole game area to repaint."""

    SIZE = 76
    STEP_DEG = 2  # turns smaller than this don't repaint

    def __init__(self, color) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._color = QColor(*color)
        self._deg = 0
        self.hide()

    def point(self, x: float, y: float, angle: float) -> None:
        """Centre the arrow on (x, y), pointing `angle` radians clockwise from 'right'."""
        deg = round(math.degrees(angle) / self.STEP_DEG) * self.STEP_DEG
        if deg != self._deg:
            self._deg = deg
            self.update()
        self.move(int(x - self.SIZE / 2), int(y - self.SIZE / 2))
        if not self.isVisible():
            self.show()

    def clear(self) -> None:
        if self.isVisible():
            self.hide()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.translate(self.SIZE / 2, self.SIZE / 2)
        painter.rotate(self._deg)
        head = QPolygonF([QPointF(28, 0), QPointF(-14, 18), QPointF(-4, 0), QPointF(-14, -18)])
        glow = QColor(self._color)
        glow.setAlpha(80)
        painter.setPen(QPen(glow, 9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(head)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
        painter.setBrush(self._color)
        painter.drawPolygon(head)
        painter.end()


class NullArrow:
    """Stands in when there is no Qt application (unit tests); it records where it was told to point."""

    def __init__(self) -> None:
        self.visible = False
        self.x = self.y = self.angle = 0.0

    def point(self, x: float, y: float, angle: float) -> None:
        self.visible, self.x, self.y, self.angle = True, x, y, angle

    def clear(self) -> None:
        self.visible = False


def make_arrow(app, color):
    """A pointer arrow (added to `app`, hidden) if a Qt application is running, else a stand-in."""
    if QApplication.instance() is None:
        return NullArrow()
    arrow = ArrowWidget(color)
    app.add(arrow, x=0, y=0)
    return arrow


class NullFxLayer:
    """Stands in when there is no Qt application (unit tests); it just remembers what it was given."""

    def __init__(self) -> None:
        self.shapes: List[object] = []

    def set_shapes(self, shapes: List[object]) -> None:
        self.shapes = shapes


def make_fx_layer(app, width: int, height: int):
    """The real overlay (added to `app`) if a Qt application is running, else a recording stand-in."""
    if QApplication.instance() is None:
        return NullFxLayer()
    layer = FxLayer(width, height)
    app.add(layer, x=0, y=0)
    return layer
