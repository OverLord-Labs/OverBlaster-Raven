"""Paints the battery meter and level number described by hud.py.

A small transparent widget in the top-left of the game area. It repaints only when a cell lights or
goes dark, when the level or chip changes, or on the slow flicker while the battery is low or on the
last lit cell's pulse, so most ticks cost nothing. It paints no opaque backing, and it is
transparent to the mouse, so gaze and mouse positions pass straight through it.
"""

import os
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from . import hud

FLICKER_HZ = 1.4  # the last lit cell pulses, and every lit cell flickers when the battery is low
_fonts: Dict[Tuple[int, bool, float], QFont] = {}


def qt_font(size: float, bold: bool, spacing: float) -> QFont:
    """Inter at `size` px, via the framework's own loader, with letter spacing."""
    key = (int(size), bold, spacing)
    if key not in _fonts:
        from raven_framework.helpers.font_utils import create_font

        f = QFont(create_font("inter", int(size), "bold" if bold else "medium"))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
        _fonts[key] = f
    return _fonts[key]


_logo: Optional[QPixmap] = None


def logo_pixmap() -> QPixmap:
    """The Overlord OD mark (needs a QApplication)."""
    global _logo
    if _logo is None:
        _logo = QPixmap(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "overlord_od.png"))
    return _logo


def _rgba(color, alpha: float) -> QColor:
    return QColor(color[0], color[1], color[2], int(255 * max(0.0, min(1.0, alpha))))


class HudLayer(QWidget):
    def __init__(self, width: int = 320, height: int = 100) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(width, height)
        self.model: Optional[hud.HudModel] = None
        self._key = None
        self._drawn = None
        self._phase = 0
        self._badge = 1.0

    def set_state(self, p: float, chip: bool, level: int, now: float, badge: float = 1.0) -> None:
        """`badge` (0 to 1) is how far the OD x2 badge has popped in; it only shows once the chip is collected."""
        self._badge = badge
        key = (hud.lit_cells(p), p < hud.LOW, chip, level, round(badge * 24))
        if key != self._key:
            self.model, self._key = hud.build(p, chip, level), key
        self._phase = int(now * FLICKER_HZ) % 2
        if (key, self._phase) != self._drawn:
            self._drawn = (key, self._phase)
            self.update()

    def paintEvent(self, _event) -> None:
        m = self.model
        if m is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        for cell in m.cells:
            poly = QPolygonF([QPointF(x, y) for x, y in cell.points])
            if not cell.lit:
                painter.setPen(QPen(_rgba(hud.WHITE, 0.2), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(poly)
                continue
            alpha = 1.0
            if (m.low or cell.last) and self._phase == 1:
                alpha = 0.45
            painter.setPen(QPen(_rgba(m.tone, 0.28 * alpha), 5))  # a soft glow under the cell
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)
            painter.setPen(QPen(_rgba(m.tone, alpha), 1))
            painter.setBrush(_rgba(m.tone, 0.95 * alpha))
            painter.drawPolygon(poly)
        x, y1, y2 = m.divider
        painter.setPen(QPen(_rgba(m.tone, 0.5), 1))
        painter.drawLine(QPointF(x, y1), QPointF(x, y2))
        for t in m.texts:
            painter.setFont(qt_font(t.size, True, t.spacing))
            painter.setPen(_rgba(t.color, 1.0))
            painter.drawText(QPointF(t.x, t.y), t.text)
        if m.pill and self._badge > 0:
            px, py, pw, ph = m.pill
            k = hud.badge_scale(self._badge)
            painter.save()
            painter.translate(px + pw / 2, py + ph / 2)
            painter.scale(k, k)
            painter.translate(-(px + pw / 2), -(py + ph / 2))
            painter.setOpacity(min(1.0, self._badge * 3))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_rgba(hud.GOLD, 1.0))
            painter.drawRoundedRect(QRectF(px, py, pw, ph), ph / 2, ph / 2)
            lx, ly, ls = hud.PILL_LOGO
            painter.drawPixmap(QRectF(lx, ly, ls, ls), logo_pixmap(), QRectF(logo_pixmap().rect()))
            tx, ty, ts = hud.PILL_TEXT
            painter.setFont(qt_font(ts, True, 0))
            painter.setPen(_rgba((0, 0, 0), 1.0))
            painter.drawText(QPointF(tx, ty), "×2")
            painter.restore()
        painter.end()


class NullHud:
    """Stands in when there is no Qt application (unit tests): builds the same model and keeps it."""

    def __init__(self) -> None:
        self.model: Optional[hud.HudModel] = None
        self.calls = 0
        self.badge = 1.0

    def set_state(self, p: float, chip: bool, level: int, now: float, badge: float = 1.0) -> None:
        self.calls += 1
        self.badge = badge
        self.model = hud.build(p, chip, level)


def make_hud(app, width: int = 320, height: int = 100):
    """The real widget (added to `app` at the top-left) if a Qt application is running, else a stand-in."""
    if QApplication.instance() is None:
        return NullHud()
    layer = HudLayer(width, height)
    app.add(layer, x=0, y=0)
    return layer
