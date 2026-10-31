"""Canvas-2D-style drawing on a QPainter (port of web src/render/draw.ts).

The web renderer draws with the HTML canvas API; the scenes ported from it (title, story, playfield, HUD ...) are
line-for-line translations that call the same methods in snake_case. Two layers make that possible:

  * `Ctx`   a thin Canvas facade over a QPainter: begin_path / move_to / line_to / arc / ellipse / bezier_curve_to /
            close_path / rect / fill / stroke / clip / fill_rect / stroke_rect / save / restore / translate / rotate /
            scale / transform / set_transform / draw_image / create_linear_gradient / create_radial_gradient /
            set_line_dash, and the state properties fill_style, stroke_style, line_width, global_alpha, line_cap,
            line_join, line_dash_offset, shadow_color, shadow_blur, global_composite_operation.
  * `Draw`  the game's helpers on top of it: text (letter spacing, align, alpha), poly_path / fill_poly, cut_plate,
            slanted, glow / no_glow, round_rect, logo, crosshair, draw_stars, draw_rock, plus `clock_t`.

All coordinates are logical px in a 640 x 640 space; `Draw.begin(painter, size)` scales that to `size` device px.

Differences from a real canvas (all worked around, none visible in the game):
  * shadowBlur has no QPainter equivalent. A "glow" is emulated by stroking the shape's outline five times, from wide and
    faint to narrow and strong, with the alphas chosen so the stacked result falls off like the gaussian (sigma = blur / 2)
    the canvas applies. That is five extra draws, and only for glowing shapes. The blur radius is in logical px (a canvas's is
    in device px), so a glow looks the same at any size.
  * A path is stored in the coordinates in force when it is drawn (not when it was built). The ported scenes never
    change the transform between building a path and filling it, so this is the same thing.
  * Gradients interpolate in Qt's way (unpremultiplied RGBA), which is what the canvas does for these stops.
"""

import math
import os
import re
from typing import Dict, List, Optional, Sequence, Tuple, Union

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
    QTransform,
)

from ..core.constants import GOLD, GREY, W
from ..core.math_ import js_round
from ..core.rng import Rng

RGB = Tuple[int, int, int]
Pt = Tuple[float, float]
Color = Union[str, Sequence[int], QColor]

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets")
_FRAMEWORK_FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "raven-framework", "fonts", "Inter", "static")


# ------------------------------------------------------------------ colours
def css(c: Sequence[int], a: Optional[float] = None) -> str:
    return f"rgba({c[0]},{c[1]},{c[2]},{1 if a is None else a})"


def mixc(a: Sequence[int], b: Sequence[int], u: float) -> RGB:
    return (js_round(a[0] + (b[0] - a[0]) * u), js_round(a[1] + (b[1] - a[1]) * u), js_round(a[2] + (b[2] - a[2]) * u))


_RGBA = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)")
_color_cache: Dict[str, QColor] = {}


def parse_color(c: Color) -> QColor:
    """A CSS colour string ('rgba(0,229,255,.5)', '#fff', 'transparent'), an (r, g, b) tuple, or a QColor."""
    if isinstance(c, QColor):
        return c
    if not isinstance(c, str):
        return QColor(int(c[0]), int(c[1]), int(c[2]), 255 if len(c) < 4 else int(c[3]))
    q = _color_cache.get(c)
    if q is not None:
        return q
    m = _RGBA.fullmatch(c.strip())
    if m:
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        q = QColor(int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))), max(0, min(255, int(round(a * 255)))))
    elif c == "transparent":
        q = QColor(0, 0, 0, 0)
    else:
        q = QColor(c)
    if len(_color_cache) < 4096:
        _color_cache[c] = q
    return q


class Gradient:
    """What create_linear_gradient / create_radial_gradient return."""

    def __init__(self, q) -> None:
        self.q = q

    def add_color_stop(self, pos: float, color: Color) -> None:
        self.q.setColorAt(max(0.0, min(1.0, pos)), parse_color(color))


# ------------------------------------------------------------------ fonts
_font_family: Optional[str] = None
_fonts: Dict[Tuple[int, int], QFont] = {}
_WEIGHTS = {100: QFont.Weight.Thin, 200: QFont.Weight.ExtraLight, 300: QFont.Weight.Light, 400: QFont.Weight.Normal, 500: QFont.Weight.Medium,
            600: QFont.Weight.DemiBold, 700: QFont.Weight.Bold, 800: QFont.Weight.ExtraBold, 900: QFont.Weight.Black}


def advance_scale(size: float) -> float:
    """The web's Inter (Google Fonts) sets 0.5% to 2.5% wider than the framework's build, more so at larger sizes (measured at
    16, 20, 28 and 36 px): match its line lengths."""
    return 1.0 + min(0.025, 0.0016 * max(0.0, size - 13))


def _load_family() -> str:
    """Inter from the framework's fonts (the glasses and this repo have them): the variable font, read from memory (Qt cannot open
    a path with a comma in it), else the static files, else the system sans."""
    global _font_family
    if _font_family is not None:
        return _font_family
    fam = ""
    var = os.path.join(os.path.dirname(_FRAMEWORK_FONTS), "Inter-VariableFont_opsz,wght.ttf")
    if os.path.isfile(var):
        with open(var, "rb") as f:
            fid = QFontDatabase.addApplicationFontFromData(QByteArray(f.read()))
        names = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        fam = names[0] if names else ""
    if not fam and os.path.isdir(_FRAMEWORK_FONTS):
        for f in sorted(os.listdir(_FRAMEWORK_FONTS)):
            if f.startswith("Inter_24pt-") and f.endswith(".ttf") and "Italic" not in f:
                fid = QFontDatabase.addApplicationFont(os.path.join(_FRAMEWORK_FONTS, f))
                names = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                if names and not fam:
                    fam = names[0]
    _font_family = fam or "Sans Serif"
    return _font_family


def get_font(size: float, weight: int = 700) -> QFont:
    key = (int(round(size * 4)), int(weight))
    f = _fonts.get(key)
    if f is None:
        f = QFont(_load_family())
        f.setPixelSize(max(1, int(round(size))))
        f.setWeight(_WEIGHTS[min(900, max(100, int(round(weight / 100.0)) * 100))])
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        _fonts[key] = f
    return f


# ------------------------------------------------------------------ the canvas facade
class _State:
    __slots__ = ("fill_style", "stroke_style", "line_width", "global_alpha", "line_cap", "line_join", "line_dash", "line_dash_offset",
                 "shadow_color", "shadow_blur", "global_composite_operation")

    def __init__(self) -> None:
        self.fill_style: Color = "#000000"
        self.stroke_style: Color = "#000000"
        self.line_width = 1.0
        self.global_alpha = 1.0
        self.line_cap = "butt"
        self.line_join = "miter"
        self.line_dash: List[float] = []
        self.line_dash_offset = 0.0
        self.shadow_color: Color = "rgba(0,0,0,0)"
        self.shadow_blur = 0.0
        self.global_composite_operation = "source-over"

    def copy(self) -> "_State":
        s = _State()
        for k in _State.__slots__:
            setattr(s, k, getattr(self, k))
        s.line_dash = list(self.line_dash)
        return s


_CAPS = {"butt": Qt.PenCapStyle.FlatCap, "round": Qt.PenCapStyle.RoundCap, "square": Qt.PenCapStyle.SquareCap}
_JOINS = {"miter": Qt.PenJoinStyle.MiterJoin, "round": Qt.PenJoinStyle.RoundJoin, "bevel": Qt.PenJoinStyle.BevelJoin}
_GLOW_RADII = (0.35, 0.8, 1.35, 2.0, 2.7)  # how far each glow ring reaches, in sigmas


class Ctx:
    """The canvas API the web scenes use, over a QPainter. Create one per Draw; call begin() each frame."""

    def __init__(self) -> None:
        self.p: Optional[QPainter] = None
        self.base = QTransform()
        self.base_scale = 1.0
        self.s = _State()
        self._stack: List[_State] = []
        self.path = QPainterPath()
        self.on_glow_call = None  # test hook

    # ---- lifecycle
    def begin(self, painter: QPainter, size: float) -> None:
        self.p = painter
        self.base_scale = size / W
        self.base = QTransform.fromScale(self.base_scale, self.base_scale)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setTransform(self.base)
        painter.setOpacity(1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self.s = _State()
        self._stack = []
        self.path = QPainterPath()

    # ---- state properties (canvas names, snake_case)
    def _prop(name):  # noqa: N805
        def get(self):
            return getattr(self.s, name)

        def set_(self, v):
            setattr(self.s, name, v)

        return property(get, set_)

    fill_style = _prop("fill_style")
    stroke_style = _prop("stroke_style")
    line_width = _prop("line_width")
    global_alpha = _prop("global_alpha")
    line_cap = _prop("line_cap")
    line_join = _prop("line_join")
    line_dash_offset = _prop("line_dash_offset")
    shadow_color = _prop("shadow_color")
    shadow_blur = _prop("shadow_blur")
    global_composite_operation = _prop("global_composite_operation")
    del _prop

    def set_line_dash(self, segs: Sequence[float]) -> None:
        segs = [float(x) for x in segs]
        self.s.line_dash = segs * 2 if len(segs) % 2 else segs

    def save(self) -> None:
        self._stack.append(self.s.copy())
        self.p.save()

    def restore(self) -> None:
        if self._stack:
            self.s = self._stack.pop()
            self.p.restore()

    # ---- transforms
    def translate(self, x: float, y: float) -> None:
        self.p.translate(x, y)

    def rotate(self, rad: float) -> None:
        self.p.rotate(math.degrees(rad))

    def scale(self, x: float, y: float) -> None:
        self.p.scale(x, y)

    def transform(self, a: float, b: float, c: float, d: float, e: float, f: float) -> None:
        self.p.setTransform(QTransform(a, b, c, d, e, f), True)

    def set_transform(self, a: float, b: float, c: float, d: float, e: float, f: float) -> None:
        """Absolute, in device px (like the canvas). reset_transform() goes back to the logical 640 space."""
        self.p.setTransform(QTransform(a, b, c, d, e, f))

    def reset_transform(self) -> None:
        self.p.setTransform(self.base)

    def _rel_scale(self) -> float:
        """The current scale relative to the logical space, to turn logical px into user units."""
        t = self.p.transform()
        det = abs(t.determinant())
        return math.sqrt(det) / self.base_scale if det > 1e-12 else 1.0

    # ---- paths
    def begin_path(self) -> None:
        self.path = QPainterPath()

    def move_to(self, x: float, y: float) -> None:
        self.path.moveTo(x, y)

    def line_to(self, x: float, y: float) -> None:
        if self.path.elementCount() == 0:
            self.path.moveTo(x, y)
        else:
            self.path.lineTo(x, y)

    def close_path(self) -> None:
        if self.path.elementCount():
            self.path.closeSubpath()

    def rect(self, x: float, y: float, w: float, h: float) -> None:
        self.path.addRect(QRectF(x, y, w, h))

    def round_rect(self, x: float, y: float, w: float, h: float, r: float) -> None:
        self.path.addRoundedRect(QRectF(x, y, w, h), r, r)

    def bezier_curve_to(self, c1x: float, c1y: float, c2x: float, c2y: float, x: float, y: float) -> None:
        if self.path.elementCount() == 0:
            self.path.moveTo(c1x, c1y)
        self.path.cubicTo(c1x, c1y, c2x, c2y, x, y)

    @staticmethod
    def _sweep(a0: float, a1: float, ccw: bool) -> float:
        two = 2 * math.pi
        if not ccw:
            if a1 - a0 >= two:
                return two
            s = (a1 - a0) % two
            return s
        if a0 - a1 >= two:
            return -two
        s = -((a0 - a1) % two)
        return s

    def arc(self, x: float, y: float, r: float, a0: float, a1: float, ccw: bool = False) -> None:
        sweep = self._sweep(a0, a1, ccw)
        sx, sy = x + r * math.cos(a0), y + r * math.sin(a0)
        if self.path.elementCount() == 0:
            self.path.moveTo(sx, sy)
        else:
            self.path.lineTo(sx, sy)
        if r <= 0 or sweep == 0:
            return
        # canvas angles run clockwise on screen, Qt's counter-clockwise
        self.path.arcTo(QRectF(x - r, y - r, 2 * r, 2 * r), -math.degrees(a0), -math.degrees(sweep))

    def ellipse(self, x: float, y: float, rx: float, ry: float, rot: float, a0: float, a1: float, ccw: bool = False) -> None:
        sweep = self._sweep(a0, a1, ccw)
        n = max(24, min(240, int(max(rx, ry, 1.0) * 0.9 + 24)))
        n = max(8, int(n * abs(sweep) / (2 * math.pi)))
        cr, sr = math.cos(rot), math.sin(rot)
        for i in range(n + 1):
            t = a0 + sweep * i / n
            ex, ey = math.cos(t) * rx, math.sin(t) * ry
            px, py = x + ex * cr - ey * sr, y + ex * sr + ey * cr
            if i == 0 and self.path.elementCount() == 0:
                self.path.moveTo(px, py)
            else:
                self.path.lineTo(px, py)

    # ---- painting
    def create_linear_gradient(self, x0: float, y0: float, x1: float, y1: float) -> Gradient:
        return Gradient(QLinearGradient(x0, y0, x1, y1))

    def create_radial_gradient(self, x0: float, y0: float, r0: float, x1: float, y1: float, r1: float) -> Gradient:
        # canvas: from circle 0 (stop 0) to circle 1 (stop 1). Qt: the focal circle is stop 0, the outer circle stop 1.
        return Gradient(QRadialGradient(QPointF(x1, y1), max(r1, 1e-3), QPointF(x0, y0), r0))

    def _brush(self, style: Color) -> QBrush:
        if isinstance(style, Gradient):
            return QBrush(style.q)
        return QBrush(parse_color(style))

    def _mode(self) -> None:
        self.p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus if self.s.global_composite_operation == "lighter"
                                  else QPainter.CompositionMode.CompositionMode_SourceOver)
        self.p.setOpacity(self.s.global_alpha)

    def _pen(self, width: Optional[float] = None, brush: Optional[QBrush] = None, dash: bool = True) -> QPen:
        w = self.s.line_width if width is None else width
        pen = QPen(brush if brush is not None else self._brush(self.s.stroke_style), w)
        pen.setCapStyle(_CAPS.get(self.s.line_cap, Qt.PenCapStyle.FlatCap))
        pen.setJoinStyle(_JOINS.get(self.s.line_join, Qt.PenJoinStyle.MiterJoin))
        pen.setMiterLimit(10)
        if dash and self.s.line_dash and w > 0:
            pen.setDashPattern([max(1e-3, d / w) for d in self.s.line_dash])
            pen.setDashOffset(self.s.line_dash_offset / w)
        return pen

    def glow_active(self) -> bool:
        return self.s.shadow_blur > 0 and parse_color(self.s.shadow_color).alphaF() > 0

    def _shadow(self, path: QPainterPath, stroke_width: float = 0.0, fill: bool = True, src_alpha: float = 1.0) -> None:
        """The glow under a shape: its outline stroked several times, wide and faint to narrow and strong, so that the stacked alpha
        falls off like a gaussian blur of sigma = blur / 2 (see the module docstring)."""
        if not self.glow_active():
            return
        col = parse_color(self.s.shadow_color)
        sigma = self.s.shadow_blur / 2 / self._rel_scale()
        p = self.p
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setOpacity(self.s.global_alpha)
        A = col.alphaF() * src_alpha  # like the canvas, a see-through shape casts a see-through shadow
        if fill:
            c = QColor(col)
            c.setAlphaF(A)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(c))
            p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        radii = [r * sigma for r in _GLOW_RADII]
        # the stacked alpha wanted at the middle of each ring, outermost first
        want = [A * 0.5 * math.erfc(((radii[i - 1] if i else 0.0) + radii[i]) / 2 / (sigma * math.sqrt(2))) for i in range(len(radii))]
        under = 0.0  # alpha already stacked by the wider passes
        for i in range(len(radii) - 1, -1, -1):
            a = 0.0 if want[i] <= under else min(0.95, 1 - (1 - want[i]) / (1 - under))
            under = 1 - (1 - under) * (1 - a)
            if a <= 0.004:
                continue
            c = QColor(col)
            c.setAlphaF(a)
            pen = QPen(QBrush(c), stroke_width + 2 * radii[i])
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(path)

    @staticmethod
    def _style_alpha(style: Color) -> float:
        return 1.0 if isinstance(style, Gradient) else parse_color(style).alphaF()

    def fill(self, rule: str = "nonzero") -> None:
        path = QPainterPath(self.path)
        path.setFillRule(Qt.FillRule.OddEvenFill if rule == "evenodd" else Qt.FillRule.WindingFill)
        self._fill_path(path)

    def _fill_path(self, path: QPainterPath) -> None:
        p = self.p
        self._shadow(path, 0.0, True, self._style_alpha(self.s.fill_style))
        self._mode()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._brush(self.s.fill_style))
        p.drawPath(path)

    def stroke(self) -> None:
        self._stroke_path(self.path)

    def _stroke_path(self, path: QPainterPath) -> None:
        if self.s.line_width <= 0:
            return
        p = self.p
        self._shadow(path, self.s.line_width, False, self._style_alpha(self.s.stroke_style))
        self._mode()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen())
        p.drawPath(path)

    def fill_rect(self, x: float, y: float, w: float, h: float) -> None:
        path = QPainterPath()
        path.addRect(QRectF(x, y, w, h))
        self._fill_path(path)

    def stroke_rect(self, x: float, y: float, w: float, h: float) -> None:
        path = QPainterPath()
        path.addRect(QRectF(x, y, w, h))
        self._stroke_path(path)

    def clip(self) -> None:
        self.p.setClipPath(self.path, Qt.ClipOperation.IntersectClip)

    def draw_image(self, img: QImage, x: float, y: float, w: float, h: float) -> None:
        if img is None or img.isNull():
            return
        self._mode()
        self.p.drawImage(QRectF(x, y, w, h), img)

    def clear(self, color: Color = "#000000") -> None:
        """Paint the whole device black (or `color`), ignoring the current transform and clip."""
        p = self.p
        p.save()
        p.resetTransform()
        p.setClipping(False)
        p.setOpacity(1.0)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(p.viewport(), parse_color(color))
        p.restore()


# ------------------------------------------------------------------ the game's drawing helpers
_STARS: List[dict] = []
_ROCK: List[float] = []


def _init_tables() -> None:
    if _STARS:
        return
    r = Rng(1)
    for _ in range(70):
        # draws in the web order: x, y, z, ph, r
        x = r.next() * W
        y = r.next() * W
        z = 0.3 + r.next() * 0.7
        ph = r.next() * 6.28
        rr = 0.6 + r.next() * 1.4
        _STARS.append({"x": x, "y": y, "z": z, "ph": ph, "r": rr})
    # JavaScript does this in doubles: the product passes 2**53 and loses low bits, so the web's rock outline is made from those rounded
    # values. Python floats are the same doubles; integers would give a different (but equally jagged) rock.
    seed = 3.0
    for _ in range(15):
        seed = math.fmod(seed * 1103515245.0 + 12345.0, 2147483648.0)
        _ROCK.append(0.76 + (math.fmod(seed, 17.0) / 17) * 0.24)


ROCK_STEP = 1.06  # rock stamps exist at sizes this far apart
_ROCK_LOG_STEP = math.log(ROCK_STEP)
_ROCK_GLOW_PAD = 34.0  # logical px beyond the outline kept for the glow (the widest blur is 22)
_ROCK_CACHE_MAX = 96  # stamps kept; a few hundred KB each at the largest size
_ROCK_SPRITES: Dict[tuple, tuple] = {}


class Draw:
    """The web's Draw class on a QPainter. `d.ctx` is the canvas facade; `d.clock_t` is the clock the dashed ghost outlines read."""

    def __init__(self, painter: Optional[QPainter] = None, size: float = W, logo: Optional[QImage] = None) -> None:
        _init_tables()
        self.ctx = Ctx()
        self.clock_t = 0.0
        self.size = size
        self.logo_img: Optional[QImage] = logo
        self._logo_loaded = logo is not None
        if painter is not None:
            self.begin(painter, size)

    def begin(self, painter: QPainter, size: float = W) -> None:
        """Start a frame on this painter: `size` device px for the 640 logical px."""
        self.size = size
        self.ctx.begin(painter, size)

    @property
    def painter(self) -> QPainter:
        return self.ctx.p

    def _logo(self) -> Optional[QImage]:
        if not self._logo_loaded:
            self._logo_loaded = True
            path = os.path.join(_ASSETS, "overlord_od.png")
            img = QImage(path)
            self.logo_img = None if img.isNull() else img
        return self.logo_img

    # ---- text
    def _font(self, size: float, weight: Optional[int]) -> QFont:
        return get_font(size, weight or 700)

    def text_w(self, s: str, size: float, weight: Optional[int] = None, sp: Optional[float] = None) -> float:
        fm = QFontMetricsF(self._font(size, weight))
        if not sp:
            return fm.horizontalAdvance(s) * advance_scale(size)
        k = advance_scale(size)
        w = 0.0
        for ch in s:
            w += fm.horizontalAdvance(ch) * k + sp
        return w - sp

    def text(self, s: str, x: float, y: float, size: float, col: Color, weight: Optional[int] = None, sp: Optional[float] = None,
             align: Optional[str] = None, alpha: Optional[float] = None) -> None:
        """Text with optional letter spacing (`sp`), alignment ('left'/'center'/'right') and alpha. `col` is an RGB tuple or CSS colour."""
        c = self.ctx
        c.save()
        if alpha is not None:
            c.global_alpha *= alpha
        font = self._font(size, weight)
        fm = QFontMetricsF(font)
        brush = QBrush(parse_color(col))
        glow = c.glow_active()
        p = c.p
        if not sp:
            k = advance_scale(size)
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, k * 100)
            w = fm.horizontalAdvance(s) * k
            sx = x - w / 2 if align == "center" else x - w if align == "right" else x
            self._glyphs(s, sx, y, font, brush, glow)
        else:
            total = self.text_w(s, size, weight, sp)
            sx = x - total / 2 if align == "center" else x - total if align == "right" else x
            k = advance_scale(size)
            for ch in s:
                self._glyphs(ch, sx, y, font, brush, glow)
                sx += fm.horizontalAdvance(ch) * k + sp
        c.restore()

    def _glyphs(self, s: str, x: float, y: float, font: QFont, brush: QBrush, glow: bool) -> None:
        c, p = self.ctx, self.ctx.p
        if s == " ":
            return
        if glow:
            path = QPainterPath()
            path.addText(QPointF(x, y), font, s)
            c._shadow(path, 0.0, True, brush.color().alphaF())
        c._mode()
        p.setPen(QPen(brush, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setFont(font)
        p.drawText(QPointF(x, y), s)

    # ---- shapes
    def poly_path(self, pts: Sequence[Pt]) -> None:
        c = self.ctx
        c.begin_path()
        c.move_to(pts[0][0], pts[0][1])
        for pt in pts[1:]:
            c.line_to(pt[0], pt[1])
        c.close_path()

    def fill_poly(self, pts: Sequence[Pt], fill: Optional[Color], stroke: Optional[Color], lw: Optional[float] = None) -> None:
        c = self.ctx
        self.poly_path(pts)
        if fill:
            c.fill_style = fill
            c.fill()
        if stroke:
            c.stroke_style = stroke
            c.line_width = lw or 2
            c.stroke()

    @staticmethod
    def cut_plate(x1: float, y1: float, x2: float, y2: float, c: float) -> List[Pt]:
        """A rectangle with its top-left and bottom-right corners cut."""
        return [(x1 + c, y1), (x2, y1), (x2, y2 - c), (x2 - c, y2), (x1, y2), (x1, y1 + c)]

    @staticmethod
    def slanted(x: float, y: float, w: float, h: float, s: float) -> List[Pt]:
        return [(x + s, y), (x + s + w, y), (x + w, y + h), (x, y + h)]

    def glow(self, col: Color, blur: float) -> None:
        self.ctx.shadow_color = col if isinstance(col, str) else css(col)
        self.ctx.shadow_blur = blur

    def no_glow(self) -> None:
        self.ctx.shadow_blur = 0
        self.ctx.shadow_color = "transparent"

    def round_rect(self, x: float, y: float, w: float, h: float, r: float) -> None:
        self.ctx.round_rect(x, y, w, h, r)

    def logo(self, cx: float, cy: float, size: float, alpha: Optional[float] = None) -> None:
        img = self._logo()
        if img is None:
            return
        c = self.ctx
        c.save()
        c.global_alpha *= 1 if alpha is None else alpha
        c.draw_image(img, cx - size / 2, cy - size / 2, size, size)
        c.restore()

    def crosshair(self, x: float, y: float, a: Optional[float] = None) -> None:
        c = self.ctx
        c.save()
        c.global_alpha *= 1 if a is None else a
        c.stroke_style = "#7dff7d"
        c.line_width = 3
        c.begin_path()
        for l in ((-26, 0, -10, 0), (10, 0, 26, 0), (0, -26, 0, -10), (0, 10, 0, 26)):
            c.move_to(x + l[0], y + l[1])
            c.line_to(x + l[2], y + l[3])
        c.stroke()
        c.fill_style = "#fff"
        c.begin_path()
        c.arc(x, y, 2, 0, 7)
        c.fill()
        c.restore()

    def draw_stars(self, t: float, drift_x: float, drift_y: float, alpha: float) -> None:
        c = self.ctx
        base = c.global_alpha
        c.fill_style = "#fff"
        for s in _STARS:
            x = ((s["x"] - t * drift_x * s["z"]) % W + W) % W
            y = ((s["y"] + t * drift_y * s["z"]) % W + W) % W
            c.global_alpha = base * alpha * (0.35 + 0.65 * abs(math.sin(t * 0.8 + s["ph"]))) * s["z"]
            c.begin_path()
            c.arc(x, y, s["r"], 0, 7)
            c.fill()
        c.global_alpha = base

    def draw_rock(self, x: float, y: float, r: float, rot: float, rim: Sequence[int], eyes: bool, hurt: bool, red_on: bool) -> None:
        """A rock with craters, ice and (optionally) angry eyes. `rim` picks the colour scheme: GOLD, GREY, or anything else for pink.

        A rock is the costliest thing on screen (its glow is five stacked strokes of a 15-point outline), and every rock is the same
        picture turned and scaled, so each variant (colour scheme, eyes, hurt, red) is drawn once per size step and then stamped.
        Sizes are quantised to steps of ROCK_STEP (the stamp is scaled by the small remainder, under 3%), so a rock drawn this way
        differs from the vector drawing by well under a pixel in outline position and by the same tiny amount in glow width."""
        scale = self.ctx.base_scale
        if r * scale < 6.0:  # too small for the glow to matter: the vector drawing is as cheap
            self._draw_rock_vector(x, y, r, rot, rim, eyes, hurt, red_on)
            return
        k = round(math.log(max(r, 1e-3)) / _ROCK_LOG_STEP)
        rq = math.exp(k * _ROCK_LOG_STEP)
        key = (tuple(rim) == tuple(GOLD), tuple(rim) == tuple(GREY), bool(eyes), bool(hurt), bool(red_on), k, round(scale, 4))
        sprite = _ROCK_SPRITES.get(key)
        if sprite is None:
            if len(_ROCK_SPRITES) >= _ROCK_CACHE_MAX:
                _ROCK_SPRITES.clear()
            sprite = _ROCK_SPRITES[key] = self._build_rock_sprite(rq, rim, eyes, hurt, red_on, scale)
        img, half_logical = sprite
        c = self.ctx
        c.save()
        c.translate(x, y)
        c.rotate(rot)
        h = half_logical * (r / rq)
        c.draw_image(img, -h, -h, 2 * h, 2 * h)
        c.restore()

    def _build_rock_sprite(self, rq: float, rim: Sequence[int], eyes: bool, hurt: bool, red_on: bool, scale: float):
        """One rock (unrotated, radius rq logical px, with its glow) as a premultiplied image at `scale` device px per logical px."""
        half = rq * 1.12 + _ROCK_GLOW_PAD  # the jagged outline reaches 1.0 x rq; the stroke and the glow go beyond it
        px = max(2, int(math.ceil(2 * half * scale)))
        half = px / (2 * scale)  # whole device pixels, so the stamp lines up
        img = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        try:
            sub = Draw(p, scale * W)
            sub._draw_rock_vector(half, half, rq, 0.0, rim, eyes, hurt, red_on)
        finally:
            p.end()
        return img, half

    def _draw_rock_vector(self, x: float, y: float, r: float, rot: float, rim: Sequence[int], eyes: bool, hurt: bool, red_on: bool) -> None:
        c = self.ctx
        is_gold, is_grey = tuple(rim) == tuple(GOLD), tuple(rim) == tuple(GREY)
        c.save()
        c.translate(x, y)
        c.rotate(rot)
        c.scale(r, r)
        if red_on:
            self.glow("rgba(255,40,40,.95)", 22)
        elif is_grey:
            self.no_glow()
        else:
            self.glow("rgba(255,200,0,.8)" if is_gold else "rgba(255,60,220,.55)", 14)
        c.line_join = "round"
        c.begin_path()
        for k in range(15):
            a = (k / 15) * math.pi * 2
            rr = _ROCK[k]
            px, py = math.cos(a) * rr, math.sin(a) * rr
            if not k:
                c.move_to(px, py)
            else:
                c.line_to(px, py)
        c.close_path()
        c.fill_style = "#5a0a10" if red_on else "#3a2030" if hurt else "#15131b"
        c.fill()
        c.stroke_style = "#ff2a2a" if red_on else "#ffc800" if is_gold else "#8da2b4"
        c.line_width = 0.12 if red_on else 0.09
        c.stroke()
        self.no_glow()
        c.fill_style = "#0b0a10"
        for k in ((-0.3, -0.18, 0.2), (0.34, 0.2, 0.15), (0.06, -0.5, 0.11), (-0.4, 0.4, 0.13)):
            c.begin_path()
            c.ellipse(k[0], k[1], k[2], k[2] * 0.6, 0, 0, 7)
            c.fill()
        c.fill_style = "rgba(0,229,255,.85)"
        for p in ((-0.7, -0.36), (0.55, -0.55), (0.62, 0.45)):
            self.poly_path([(p[0], p[1] - 0.25), (p[0] + 0.11, p[1]), (p[0], p[1] + 0.25), (p[0] - 0.11, p[1])])
            c.fill()
        if eyes:
            c.fill_style = "#ffe27a" if is_gold else "#ff3cdc"
            self.poly_path([(-0.3, -0.1), (-0.07, -0.23), (-0.07, -0.1)])
            c.fill()
            self.poly_path([(0.3, -0.1), (0.07, -0.23), (0.07, -0.1)])
            c.fill()
        c.restore()
