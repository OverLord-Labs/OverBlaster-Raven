"""Small shared pictures (port of web src/render/sprites.ts)."""

import math
from typing import Optional, Sequence

from ..core.constants import CELLS
from .draw import Draw, css

CYs, GDs, PKs = "0,229,255", "255,200,0", "255,60,220"


def wing_icon(d: Draw, x: float, y: float, s: float, fill: float, ghost: bool, rot: Optional[float] = None, steady: bool = False) -> None:
    """A battery wing: a slanted panel with cell lines. `fill` is the gold fill alpha (0 for none); `ghost` draws a dashed pink
    outline instead of the cyan one (a wing that is missing). The ghost pulses with d.clock_t unless `steady`."""
    c = d.ctx
    c.save()
    c.translate(x, y)
    c.rotate(rot or 0)
    c.scale(s, s)
    P = [(-70, -14), (70, -40), (70, -8), (-70, 32)]
    c.begin_path()
    for i, p in enumerate(P):
        if i:
            c.line_to(p[0], p[1])
        else:
            c.move_to(p[0], p[1])
    c.close_path()
    if fill > 0:
        c.fill_style = f"rgba({GDs},{fill})"
        c.fill()
    c.line_width = 2.5 / s
    c.stroke_style = f"rgba({PKs if ghost else CYs},{(0.7 if steady else 0.5 + 0.4 * math.sin(d.clock_t * 5)) if ghost else 1})"
    if ghost:
        c.set_line_dash([8 / s, 6 / s])
    c.stroke()
    c.set_line_dash([])
    c.begin_path()
    for i in range(1, 6):
        f = i / 6
        px = -70 + f * 140
        c.move_to(px, -14 - f * 26)
        c.line_to(px, 32 - f * 40)
    c.line_width = 1.5 / s
    c.stroke_style = f"rgba({CYs},{0.25 if ghost else 0.7})"
    c.stroke()
    c.restore()


def draw_cells(d: Draw, clock: float, frac: float, tone: Sequence[int], last_pulse: bool, alpha: float, lit_override: Optional[int] = None) -> None:
    """The battery cells in the top-left of the HUD (two rows of ten)."""
    c = d.ctx
    lit = lit_override if lit_override is not None else (0 if frac <= 0 else min(CELLS, max(1, math.ceil(frac * CELLS))))
    for i in range(CELLS):
        x = 26 + (i % 10) * 12.5
        y = 8 + (i // 10) * 30
        pts = d.slanted(x, y, 9.5, 24, 4)
        if i >= lit:
            d.fill_poly(pts, None, "rgba(255,255,255,.22)", 1)
            continue
        a = alpha * (0.55 + 0.45 * abs(math.sin(clock * 4)) if last_pulse and i == lit - 1 else 1)
        d.poly_path(pts)
        c.stroke_style = css(tone, 0.28 * a)
        c.line_width = 5
        c.stroke()
        d.fill_poly(pts, css(tone, 0.95 * a), css(tone, a), 1)
