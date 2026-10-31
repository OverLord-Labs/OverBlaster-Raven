"""Pointer arrows (port of web src/render/arrows.ts)."""

import math
from typing import List, Sequence

from ..core.constants import CENTER, CRITICAL, CYAN, GOLD, POINTER_RING, PPD, RED
from ..core.game import rock_radius
from ..core.view import on_screen
from .draw import Draw, css


def _visible(game, p, m: float) -> bool:
    return on_screen(p, m, game.ox)


def draw_arrow(d: Draw, clock: float, ang: float, radius: float, col: Sequence[int], scale: float, crit: bool) -> None:
    ctx = d.ctx
    k = scale * (1.35 + 0.15 * math.sin(clock * 12) if crit else 1)
    ctx.save()
    ctx.translate(CENTER + math.cos(ang) * radius, CENTER + math.sin(ang) * radius)
    ctx.rotate(ang)
    ctx.scale(k, k)
    ctx.global_alpha *= 0.75 + 0.25 * math.sin(clock * 12) if crit else 0.9
    d.glow(css(col, 0.8), 16 if crit else 10)
    d.fill_poly([(18, 0), (-12, -15), (-4, 0), (-12, 15)], css(col, 0.95), None)
    d.no_glow()
    ctx.restore()


def draw_pointer(d: Draw, game, az: float, el: float, col: Sequence[int], margin: float) -> None:
    """An arrow toward a point of the sky, only while it is out of view."""
    p = game.proj(az, el)
    if not _visible(game, p, margin):
        draw_arrow(d, game.clock, math.atan2(p.dy, p.dx), POINTER_RING, col, 1, False)


def draw_rock_arrows(d: Draw, game, rocks: List) -> None:
    """One arrow for every rock that is out of view. Arrows that point the same way are stacked inward, the nearest rock outermost;
    a rock that is critically close gets a red, pulsing arrow."""
    items = []
    for w in rocks:
        p = game.proj(w.az, w.el)
        if _visible(game, p, rock_radius(w) * PPD):
            continue
        items.append({"ang": math.atan2(p.dy, p.dx), "p": w.p, "crit": w.p >= CRITICAL, "col": GOLD if w.carrier else CYAN})
    items.sort(key=lambda it: it["ang"])
    group: List[dict] = []
    groups: List[List[dict]] = []
    for it in items:
        if group and it["ang"] - group[-1]["ang"] > 0.2:
            groups.append(group)
            group = []
        group.append(it)
    if group:
        groups.append(group)
    for g in groups:
        g.sort(key=lambda it: it["p"])
        for i, it in enumerate(g):
            depth = min(5, len(g) - 1 - i)
            draw_arrow(d, game.clock, it["ang"], POINTER_RING - 17 * depth, RED if it["crit"] else it["col"], 1 - 0.07 * depth, it["crit"])
