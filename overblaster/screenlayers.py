"""Paints the title screen, the between-levels plate and the level-start splash described by screens.py.

Each is a transparent widget that takes no mouse events, so gaze and the mouse pass straight through
(the LAUNCH button sits under the title layer). They repaint only while something is animating.
Without a Qt application (unit tests) the make_* factories return stand-ins that keep the model.
"""

import time
from typing import Optional

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from . import hud, screens
from .hudlayer import _rgba, qt_font

TITLE_FPS = 15
SPLASH_W, SPLASH_H = 600, 150  # the plate is 560 x 124, with room for its glow


def _bold(weight: str) -> bool:
    return weight in ("bold", "black")


def measure(text: str, size: float, weight: str, spacing: float) -> float:
    return QFontMetricsF(qt_font(size, _bold(weight), spacing)).horizontalAdvance(text)


def estimate(text: str, size: float, weight: str, spacing: float) -> float:
    """Text width without a font, for the stand-ins."""
    return len(text) * (size * 0.66 + spacing)


def _poly(points, dx: float = 0.0, dy: float = 0.0) -> QPolygonF:
    return QPolygonF([QPointF(x + dx, y + dy) for x, y in points])


def _text(p: QPainter, t: screens.Text, mul: float = 1.0, dx: float = 0.0, dy: float = 0.0, skew: float = 0.0) -> None:
    font = qt_font(t.size, _bold(t.weight), t.spacing)
    p.setFont(font)
    w = QFontMetricsF(font).horizontalAdvance(t.text)
    x = -w / 2 if t.anchor == "middle" else 0.0
    p.save()
    p.translate(t.x + dx, t.y + dy)
    if skew:
        p.shear(-skew, 0)
    p.setPen(_rgba(t.color, t.alpha * mul))
    p.drawText(QPointF(x, 0), t.text)
    p.restore()


def _cell(p: QPainter, cell: screens.Cell, tone, mul: float = 1.0) -> None:
    poly = _poly(cell.points)
    if not cell.lit:
        p.setPen(QPen(_rgba(hud.WHITE, 0.2 * mul), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(poly)
        return
    p.setPen(QPen(_rgba(tone, 0.25 * cell.alpha * mul), 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(poly)
    p.setPen(QPen(_rgba(tone, cell.alpha * mul), 1))
    p.setBrush(_rgba(tone, cell.alpha * mul))
    p.drawPolygon(poly)


def _base(w: QWidget, width: int, height: int) -> None:
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    w.setFixedSize(width, height)


def _painter(w: QWidget) -> QPainter:
    p = QPainter(w)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    return p


class TitleLayer(QWidget):
    """The OverBlaster frame: two rows of cells pulsing in opposite directions around the wordmark."""

    def __init__(self, size: int = screens.SIZE) -> None:
        super().__init__()
        _base(self, size, size)
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(int(1000 / TITLE_FPS))

    def paintEvent(self, _event) -> None:
        m = screens.title_model(time.monotonic() - self._t0, measure)
        p = _painter(self)
        for c in m.cells:
            _cell(p, c, hud.CYAN)
        for glow in (0.10, 0.18):  # the wordmark's soft glow, then the wordmark itself
            for d in (3, -3):
                _text(p, m.wordmark, glow, d, 0, 0.176)
                _text(p, m.wordmark, glow, 0, d, 0.176)
        _text(p, m.wordmark, 1.0, 0, 0, 0.176)
        for t in m.texts[1:]:
            _text(p, t)
        x, y, w, h = m.launch  # the plate around the LAUNCH button
        plate = screens.cut_plate(x, y, x + w, y + h, screens.LAUNCH_CUT)
        p.setPen(QPen(_rgba(hud.CYAN, 0.9), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(_poly(plate))
        p.end()


class PauseLayer(QWidget):
    """Between levels: SECTOR CLEARED, the score counting up, what comes next, the battery cells filling."""

    def __init__(self, size: int = screens.SIZE) -> None:
        super().__init__()
        _base(self, size, size)
        self.model: Optional[screens.PauseModel] = None
        self._drawn = None
        self.hide()

    def set(self, level: int, score: int, lit: int, tone, t: float) -> None:
        """Show the plate `t` s after it began. Repaints only while it is animating."""
        self.show()
        key = (level, score, lit, tone, round(t * screens.TITLE_CELLS) if t < 2.0 else None)
        if key == self._drawn:
            return
        self._drawn = key
        self.model = screens.pause_model(level, score, lit, tone, t, measure)
        self.update()

    def clear(self) -> None:
        self.model, self._drawn = None, None
        self.hide()

    def paintEvent(self, _event) -> None:
        m = self.model
        if m is None:
            return
        p = _painter(self)
        poly = _poly(m.plate)
        p.setPen(QPen(_rgba(m.tone, 0.9), 2))
        p.setBrush(_rgba(m.tone, 0.12))
        p.drawPolygon(poly)
        dx = screens.NEXT_X - 20  # a thin divider between the two columns
        p.setPen(QPen(_rgba(m.tone, 0.4), 1))
        p.drawLine(QPointF(screens.LEFT_X, 276), QPointF(screens.PLATE[2] - 34, 276))
        p.drawLine(QPointF(dx, 296), QPointF(dx, 380))
        for t in m.texts:
            _text(p, t)
        for c in m.cells:
            _cell(p, c, m.tone)
        p.end()


class SplashLayer(QWidget):
    """The level number in a block and the level name beside it, a see-through backdrop that follows a point in the sky."""

    def __init__(self) -> None:
        super().__init__()
        _base(self, SPLASH_W, SPLASH_H)
        self.model: Optional[screens.SplashModel] = None
        self._alpha = 0.0
        self.hide()

    def start(self, level: int, name: str) -> None:
        self.model = screens.splash_model(level, name, measure)

    def place(self, x: float, y: float, t: float) -> None:
        """Centre the splash on (x, y) `t` s after it began, with the fade for that moment."""
        a = screens.splash_alpha(t)
        if self.model is None or a <= 0:
            self.hide()
            self._alpha = 0.0
            return
        self.move(int(x - SPLASH_W / 2), int(y - SPLASH_H / 2))
        if a != self._alpha:
            self._alpha = a
            self.update()
        self.show()

    def paintEvent(self, _event) -> None:
        m, a = self.model, self._alpha
        if m is None or a <= 0:
            return
        p = _painter(self)
        p.translate(SPLASH_W / 2, SPLASH_H / 2)
        p.setPen(QPen(_rgba(hud.CYAN, 0.8 * a), 2))
        p.setBrush(_rgba(hud.CYAN, 0.06 * a / screens.SPLASH_MAX))
        p.drawPolygon(_poly(m.plate))
        p.setPen(QPen(_rgba(hud.CYAN, 0.3 * a), 5))  # a glow under the block
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(_poly(m.block))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_rgba(hud.CYAN, 0.9 * a / screens.SPLASH_MAX))
        p.drawPolygon(_poly(m.block))
        _text(p, m.caption, 1.0)
        _text(p, m.number, 1.0, skew=0.176)
        _text(p, m.name, a / screens.SPLASH_MAX)
        p.end()


class NullTitle:
    def __init__(self) -> None:
        self.model = screens.title_model(0.0, estimate)


class NullPause:
    def __init__(self) -> None:
        self.model: Optional[screens.PauseModel] = None
        self.shown = False

    def set(self, level: int, score: int, lit: int, tone, t: float) -> None:
        self.shown = True
        self.model = screens.pause_model(level, score, lit, tone, t, estimate)

    def clear(self) -> None:
        self.shown, self.model = False, None


class NullSplash:
    def __init__(self) -> None:
        self.model: Optional[screens.SplashModel] = None
        self.pos = (0.0, 0.0)
        self.alpha = 0.0
        self.shown = False

    def start(self, level: int, name: str) -> None:
        self.model = screens.splash_model(level, name, estimate)

    def place(self, x: float, y: float, t: float) -> None:
        self.pos = (x, y)
        self.alpha = screens.splash_alpha(t) if self.model else 0.0
        self.shown = self.alpha > 0


def _real() -> bool:
    return QApplication.instance() is not None


def make_title_layer(app):
    if not _real():
        return NullTitle()
    layer = TitleLayer(app.width())
    app.add(layer, x=0, y=0)
    return layer


def make_pause_layer(app):
    if not _real():
        return NullPause()
    layer = PauseLayer(app.width())
    app.add(layer, x=0, y=0)
    return layer


def make_splash_layer(app):
    if not _real():
        return NullSplash()
    layer = SplashLayer()
    app.add(layer, x=0, y=0)
    return layer
