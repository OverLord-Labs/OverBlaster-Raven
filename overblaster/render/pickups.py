"""The Overlord BMS chip and the bad gauges (port of web src/render/pickups.ts)."""

import math
from typing import Sequence

from ..core.constants import BAD, GAUGE_LIFE
from ..core.math_ import clamp, ease, ramp
from ..core.view import on_screen
from .arrows import draw_pointer
from .draw import Draw, css, mixc


def draw_chip(d: Draw, x: float, y: float, size: float, sc: float) -> None:
    """The Overlord BMS chip."""
    c = d.ctx
    c.save()
    c.translate(x, y)
    c.scale(sc, sc)
    s = size / 2
    d.glow("rgba(0,229,255,.6)", 12)
    c.stroke_style = "#00e5ff"
    c.line_width = 3
    c.fill_style = "#001a1f"
    c.begin_path()
    d.round_rect(-s * 0.62, -s * 0.62, s * 1.24, s * 1.24, s * 0.1)
    c.fill()
    c.stroke()
    d.no_glow()
    c.begin_path()
    for i in range(4):
        o = (i - 1.5) * s * 0.34
        c.move_to(o, -s * 0.62)
        c.line_to(o, -s * 0.9)
        c.move_to(o, s * 0.62)
        c.line_to(o, s * 0.9)
        c.move_to(-s * 0.62, o)
        c.line_to(-s * 0.9, o)
        c.move_to(s * 0.62, o)
        c.line_to(s * 0.9, o)
    c.stroke()
    d.logo(0, 0, s * 1.05)
    c.restore()


def draw_bad_chip(d: Draw, clock: float, x: float, y: float, size: float, col: Sequence[int], seed: int, alpha: float) -> None:
    """A bad gauge: a chip that has seen better days. Chipped corner, a crack, bent and missing leads, burn marks; red or blue."""
    c = d.ctx
    s = size / 2
    dark = css(mixc(col, (0, 0, 0), 0.85))
    cc = css(col)
    c.save()
    c.translate(x, y)
    c.rotate(math.sin(clock * 1.7 + seed) * 0.3 + ((seed % 7) - 3) * 0.1)
    c.global_alpha *= alpha
    d.glow(css(col, 0.8), 14)
    c.line_width = 3
    c.stroke_style = cc
    c.fill_style = dark
    d.poly_path([(-0.62 * s, -0.62 * s), (0.28 * s, -0.62 * s), (0.62 * s, -0.26 * s), (0.62 * s, 0.62 * s), (-0.62 * s, 0.62 * s)])
    c.fill()
    c.stroke()
    d.no_glow()
    c.begin_path()
    for k in range(4):
        for i in range(4):
            o = (i - 1.5) * s * 0.34
            h = (seed * 31 + k * 7 + i * 13) % 10
            ln = 0.3 if h < 4 else 0.9
            kx = 0 if h < 2 else 0.12 * s  # h<2: lead is gone; h<4: a bent stub
            if k == 0 and i == 3:
                continue
            if h < 2:
                continue
            x0 = -0.62 * s if k == 2 else 0.62 * s if k == 3 else o
            y0 = -0.62 * s if k == 0 else 0.62 * s if k == 1 else o
            dx = -1 if k == 2 else 1 if k == 3 else 0
            dy = -1 if k == 0 else 1 if k == 1 else 0
            c.move_to(x0, y0)
            mx = x0 + dx * (ln - 0.62) * s * 0.5 + (0 if dx else kx * 0.5)
            my = y0 + dy * (ln - 0.62) * s * 0.5 + (0 if dy else kx * 0.5)
            c.line_to(mx, my)
            if h < 4:
                c.line_to(mx + (0 if dx else kx), my + (0 if dy else kx))
            else:
                c.line_to(x0 + dx * (ln - 0.62) * s, y0 + dy * (ln - 0.62) * s)
    c.stroke()
    c.stroke_style = "rgba(255,255,255,.9)"
    c.line_width = 2
    d.glow(css(col), 8)
    c.begin_path()
    c.move_to(0.5 * s, -0.4 * s)
    c.line_to(0.18 * s, -0.12 * s)
    c.line_to(0.3 * s, 0.05 * s)
    c.line_to(-0.1 * s, 0.22 * s)
    c.line_to(-0.05 * s, 0.4 * s)
    c.line_to(-0.4 * s, 0.62 * s)
    c.stroke()
    d.no_glow()  # the crack
    c.fill_style = "rgba(0,0,0,.65)"
    c.begin_path()
    c.ellipse(-0.25 * s, -0.2 * s, 0.22 * s, 0.15 * s, 0.4, 0, 7)
    c.fill()  # a burn mark
    c.fill_style = css(col, 0.5 + 0.5 * math.sin(clock * 20 + seed))
    c.begin_path()
    c.arc(-0.45 * s, 0.4 * s, 0.07 * s, 0, 7)
    c.fill()  # a dying LED
    c.restore()


def draw_gauge(d: Draw, game, q) -> None:
    c = d.ctx
    clock = game.clock
    p = game.proj(q.az, q.el)
    if not on_screen(p, 60, game.ox):
        draw_pointer(d, game, q.az, q.el, BAD[q.color]["col"], 40)
        return
    col = BAD[q.color]["col"]
    fade = (1 if math.sin(clock * 18) > 0 else 0.25) if (q.age > GAUGE_LIFE - 2 and not q.first) else 1
    pop = ease(ramp(q.age, 0, 0.25))
    prog = clamp(q.dwell / q.hold, 0, 1)
    c.save()
    c.global_alpha = fade
    c.translate(p.x, p.y)
    c.scale(pop, pop)
    c.translate(-p.x, -p.y)
    c.save()
    c.set_line_dash([7, 7])
    c.line_dash_offset = -clock * 30
    c.stroke_style = css(col, 0.55 + 0.3 * math.sin(clock * 8))
    c.line_width = 3
    c.begin_path()
    c.arc(p.x, p.y, 62, 0, 7)
    c.stroke()
    c.restore()  # a warning ring: stay out of it
    c.save()
    c.set_line_dash([4, 10])
    c.line_dash_offset = -clock * 40
    c.stroke_style = css(col, 0.35)
    c.line_width = 2
    c.begin_path()
    apx = game.aim_px()
    c.move_to(p.x, p.y)
    c.line_to(apx.x, apx.y)
    c.stroke()
    c.restore()  # its tether to your crosshair
    draw_bad_chip(d, clock, p.x, p.y, 92, col, q.seed, 1)
    if prog > 0:
        c.stroke_style = css(col, 1)
        c.line_width = 7
        c.begin_path()
        c.arc(p.x, p.y, 62, -math.pi / 2, -math.pi / 2 + math.pi * 2 * prog)
        c.stroke()
    c.restore()
