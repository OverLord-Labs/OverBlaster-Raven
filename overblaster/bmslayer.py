"""Paints the Overlord BMS power-up described by bms.py.

One transparent, mouse-transparent widget over the whole game area: the hold ring and the arrow back
while you aim at the chip, then the burst, the sparks, the callout and the OD medallion once it is
collected. It repaints only while something moves (the ring, the blink, the first eight seconds
after collection) and once when it settles, so a quiet game costs nothing.
Without a Qt application (unit tests) make_bms_layer returns a stand-in that keeps the models.
"""

import math
from typing import Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from . import bms, hud, screens
from .hudlayer import _rgba, logo_pixmap
from .screenlayers import _base, _painter, _poly, _text, estimate, measure

Hold = Tuple[float, float, float, bool, Tuple[float, float]]  # chip x, y, progress, on target, crosshair x, y
BLINK_STEPS = 8  # repaints a second while the arrow blinks


class BmsLayer(QWidget):
    def __init__(self, size: int = screens.SIZE) -> None:
        super().__init__()
        _base(self, size, size)
        self._hold: Optional[Hold] = None
        self._now = 0.0
        self._award_t: Optional[float] = None
        self._origin = (size / 2, size / 2)
        self._drawn = None

    def begin_award(self, origin: Tuple[float, float]) -> None:
        self._origin = origin

    def set_state(self, hold: Optional[Hold], award_t: Optional[float], now: float) -> None:
        self._hold, self._award_t, self._now = hold, award_t, now
        settled = award_t is not None and award_t > bms.SETTLE_S
        key = (
            None if hold is None else (round(hold[0]), round(hold[1]), round(hold[2] * 120), hold[3], round(hold[4][0]), round(hold[4][1]), int(now * BLINK_STEPS) if not hold[3] else 0),
            "settled" if settled else (None if award_t is None else round(award_t * 30)),
        )
        if key != self._drawn:
            self._drawn = key
            self.update()

    def paintEvent(self, _event) -> None:
        p = _painter(self)
        if self._hold is not None:
            self._paint_hold(p, *self._hold)
        if self._award_t is not None:
            self._paint_award(p, self._award_t)
        p.end()

    def _paint_hold(self, p: QPainter, cx: float, cy: float, progress: float, on_target: bool, cross) -> None:
        ring = bms.hold_ring(cx, cy, progress, on_target)
        rect = QRectF(cx - bms.RING_R, cy - bms.RING_R, 2 * bms.RING_R, 2 * bms.RING_R)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_rgba(ring.color, 0.25), bms.RING_W - 2))
        p.drawEllipse(rect)
        if ring.progress > 0:
            p.setPen(QPen(_rgba(ring.color, 1.0), bms.RING_W, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawArc(rect, 90 * 16, int(-ring.progress * 360 * 16))
        lx, ly = bms.label_pos(cx, cy, self.width())
        _text(p, screens.Text(bms.HOLD_LABEL, lx, ly, 18, hud.WHITE, "bold", 4, "middle"))
        arrow = bms.guide_arrow(cross, (cx, cy), on_target, self._now)
        if arrow is not None:
            p.save()
            p.translate(arrow.x, arrow.y)
            p.rotate(arrow.angle)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_rgba(hud.PINK, arrow.alpha))
            p.drawPolygon(_poly(((-12, -12), (14, 0), (-12, 12), (-5, 0))))
            p.restore()

    def _paint_award(self, p: QPainter, t: float) -> None:
        ox, oy = self._origin
        r, a = bms.burst(t)
        if a > 0:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_rgba(hud.GOLD, a), 6 * a + 1))
            p.drawEllipse(QPointF(ox, oy), r, r)
        for s in bms.sparks(t, (ox, oy)):
            if s.alpha > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_rgba(hud.CYAN, s.alpha))
                p.drawEllipse(QPointF(s.x, s.y), 5, 5)
        m = bms.callout(t, measure)
        if m.medal_alpha > 0:  # the OD medallion beside the gauge
            mx, my = bms.MEDAL
            side = bms.MEDAL_SIZE
            if m.halo_alpha > 0:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(_rgba(hud.CYAN, m.halo_alpha), 2))
                p.drawEllipse(QPointF(mx, my), m.halo_r, m.halo_r)
            p.save()
            p.setOpacity(m.medal_alpha)
            p.translate(mx, my)
            p.scale(m.medal_scale_x, 1.0)
            pix = logo_pixmap()
            p.drawPixmap(QRectF(-side / 2, -side / 2, side, side), pix, QRectF(pix.rect()))
            p.restore()
        if m.bubble_scale > 0.01:
            p.save()
            px, py = m.pivot
            p.translate(px, py)
            p.scale(m.bubble_scale, m.bubble_scale)
            p.translate(-px, -py)
            p.setPen(QPen(_rgba(hud.GOLD, 1.0), 2))
            p.setBrush(_rgba((26, 20, 0), 1.0))  # opaque dark gold: the bubble must read over any world behind it
            p.drawPolygon(_poly(m.plate))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_rgba(hud.GOLD, 1.0))
            p.drawPolygon(_poly(m.pointer))
            lx, ly, ls = m.logo
            pix = logo_pixmap()
            p.drawPixmap(QRectF(lx - ls / 2, ly - ls / 2, ls, ls), pix, QRectF(pix.rect()))
            ph = (t * 1.3) % 1.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_rgba(hud.CYAN, 0.8 * (1 - ph)), 2))
            p.drawEllipse(QPointF(lx, ly), ls / 2 + 1 + 12 * ph, ls / 2 + 1 + 12 * ph)
            for tx in m.texts:
                _text(p, tx)
            p.restore()


class NullBmsLayer:
    """Stands in when there is no Qt application (unit tests): keeps the same models."""

    def __init__(self) -> None:
        self.hold: Optional[Hold] = None
        self.award_t: Optional[float] = None
        self.origin: Optional[Tuple[float, float]] = None
        self.callout: Optional[bms.CalloutModel] = None
        self.calls = 0

    def begin_award(self, origin: Tuple[float, float]) -> None:
        self.origin = origin

    def set_state(self, hold: Optional[Hold], award_t: Optional[float], now: float) -> None:
        self.calls += 1
        self.hold, self.award_t = hold, award_t
        self.callout = None if award_t is None else bms.callout(award_t, estimate)


def make_bms_layer(app, size: int = screens.SIZE):
    if QApplication.instance() is None:
        return NullBmsLayer()
    layer = BmsLayer(size)
    app.add(layer, x=0, y=0)
    return layer
