"""The title and game-over screens (port of web src/render/screens.ts)."""

import math

from ..core.constants import CYAN, GOLD, PINK, W
from ..core.layout import LAUNCH, RETRY, TOTITLE, in_box
from ..core.math_ import ramp
from .draw import Draw, css


def _boot_alpha(t: float, delay: float) -> float:
    if t < delay:
        return 0.06
    ph = (((t - delay) % 2.6) + 2.6) % 2.6 / 2.6
    if ph < 0.28:
        return 0.06 + 0.89 * ph / 0.28
    if ph < 0.62:
        return 0.95
    return 0.95 - 0.89 * (ph - 0.62) / 0.38


def draw_title(d: Draw, game) -> None:
    c, clock, ptr = d.ctx, game.clock, game.input.pointer
    c.fill_style = "#000"
    c.fill_rect(0, 0, W, W)
    d.draw_stars(clock, 3, 0, 0.7)
    for i in range(20):
        x = 88 + i * 23
        d.fill_poly(d.slanted(x, 126, 18, 16, 8), css(CYAN, _boot_alpha(clock, i * 0.07)), None)
        d.fill_poly(d.slanted(x, 282, 18, 16, 8), css(CYAN, _boot_alpha(clock, (19 - i) * 0.07)), None)
    s = "OVERBLASTER"
    size = 66
    while size > 40 and d.text_w(s, size, 900, 5) > 560:
        size -= 2
    c.save()
    c.translate(320, 238)
    c.transform(1, 0, -0.176, 1, 0, 0)
    d.glow("rgba(255,255,255,.5)", 14)
    d.text(s, 0, 0, size, "#fff", 900, 5, "center")
    d.no_glow()
    c.restore()
    d.text("AN OVERLORD LABS GAME", 320, 334, 16, GOLD, 700, 7, "center")
    d.text("TURN YOUR HEAD TO AIM", 320, 382, 20, "#fff", 500, 1, "center")
    d.text("SAY “PEW” TO FIRE", 320, 414, 20, "#fff", 500, 1, "center")
    d.text("HOLD YOUR AIM ON CRYSTALS TO HARVEST THEM", 320, 446, 20, "#fff", 500, 1, "center")
    b = LAUNCH
    hov = in_box(b, ptr.x, ptr.y)
    d.fill_poly(d.cut_plate(b.x, b.y, b.x + b.w, b.y + b.h, 14), "rgba(0,229,255,.18)" if hov else "rgba(0,229,255,.06)", css(CYAN, 0.9), 2)
    d.text("LAUNCH", 320, 532, 28, CYAN, 700, 3, "center")
    if ptr.inside:
        d.crosshair(ptr.x, ptr.y)


def draw_over(d: Draw, game) -> None:
    c, ptr, g, over = d.ctx, game.input.pointer, game.run, game.over
    c.fill_style = "#000"
    c.fill_rect(0, 0, W, W)
    d.draw_stars(game.clock, 2, 0, 0.5)
    hull, won = g.lost_cause == "hull", g.lost_cause == "win"
    a = ramp(over["t"] if over else 0, 0, 0.5)
    c.save()
    c.global_alpha = a
    d.text("BELT CLEARED" if won else "HULL DESTROYED" if hull else "BATTERY DEAD", 320, 140, 48, GOLD if won else PINK, 900, 4, "center")
    d.text("Both wings are home. The Meridian can jump again." if won else "A rock reached your ship." if hull else "You ran out of energy.",
           320, 190, 22, "#fff", 500, 1, "center")
    d.text(f"SCORE {g.score:,}    LEVEL {g.level}", 320, 252, 28, CYAN, 700, 2, "center")
    if won:
        d.logo(320, 296, 56)
    for r, label in ((RETRY, "RETRY"), (TOTITLE, "TITLE")):
        hov = in_box(r, ptr.x, ptr.y)
        d.fill_poly(d.cut_plate(r.x, r.y, r.x + r.w, r.y + r.h, 12), "rgba(0,229,255,.18)" if hov else "rgba(0,229,255,.06)", css(CYAN, 0.9), 2)
        d.text(label, 320, r.y + 42, 26, CYAN, 700, 4, "center")
    c.restore()
    if ptr.inside:
        d.crosshair(ptr.x, ptr.y)
