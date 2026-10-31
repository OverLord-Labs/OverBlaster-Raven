"""The game screen: rocks, pickups, effects, the HUD (port of web src/render/playfield.ts)."""

import math

from ..core.constants import BADGE_AT, BLINK_FROM, CENTER, CHIP_HOLD, CYAN, GOLD, HARVEST, LOW, PINK, PPD, SPLASH_END, W, WING_HOLD
from ..core.game import rock_radius
from ..core.levels import level_name
from ..core.math_ import clamp, ease, lerp, ramp
from ..core.view import on_screen
from .arrows import draw_pointer, draw_rock_arrows
from .draw import Draw, css
from .hud import draw_award, draw_callout, draw_plate
from .pickups import draw_bad_chip, draw_chip, draw_gauge
from .sprites import draw_cells, wing_icon

__all__ = ["draw_playfield", "draw_chip", "draw_bad_chip"]

HALF = math.pi / 2


def _visible(game, p, m: float) -> bool:
    return on_screen(p, m, game.ox)


def _on(p, m: float, ox: float) -> bool:
    return -ox - m < p[0] < W + ox + m and -m < p[1] < W + m


def _hold_ring(d: Draw, c, cx: float, cy: float, radius: float, prog: float) -> None:
    """The ring for a hold-to-collect pickup (the chip and the wings)."""
    ctx = d.ctx
    ctx.stroke_style = css(PINK if prog > 0 and not c.on_target else GOLD, 0.25)
    ctx.line_width = 4
    ctx.begin_path()
    ctx.arc(cx, cy, radius, 0, 7)
    ctx.stroke()
    if prog > 0:
        ctx.stroke_style = css(GOLD if c.on_target else PINK)
        ctx.line_width = 6
        ctx.begin_path()
        ctx.arc(cx, cy, radius, -HALF, -HALF + math.pi * 2 * prog)
        ctx.stroke()


def _slip_arrow(d: Draw, game, cx: float, cy: float) -> None:
    """An arrow back to the pickup when your aim slips."""
    ctx = d.ctx
    ang = math.atan2(cy - CENTER, cx - CENTER)
    al = 0.65 + 0.35 * math.sin(game.clock * 10)
    ctx.save()
    ctx.translate(CENTER + math.cos(ang) * 52, CENTER + math.sin(ang) * 52)
    ctx.rotate(ang)
    ctx.fill_style = css(PINK, al)
    d.poly_path([(-12, -12), (14, 0), (-12, 12), (-5, 0)])
    ctx.fill()
    ctx.restore()


def draw_playfield(d: Draw, game) -> None:
    ctx = d.ctx
    g = game.run
    t = g.t
    clock = game.clock
    ptr = game.input.pointer
    d.clock_t = clock
    ox = game.ox
    ctx.fill_style = "#000"
    ctx.fill_rect(-ox, 0, W + 2 * ox, W)  # no stars here: on the glasses, black is see-through
    ctx.save()
    if g.shake > 0:
        ctx.translate(math.sin(clock * 90) * 8 * g.shake, math.cos(clock * 70) * 8 * g.shake)
    # the level splash hangs in the sky above where you were looking: turn away and it slides out of view
    st = clock - g.splash_t0
    sa = 0 if st < 0 else (0.55 * st) / 0.3 if st < 0.3 else 0.55 if st <= 6.0 else (0.55 * (SPLASH_END - st)) / (SPLASH_END - 6.0) if st < SPLASH_END else 0
    if sa > 0:
        sp = game.proj(g.splash_az, g.splash_el)
        ctx.save()
        ctx.global_alpha = 0.7
        ctx.translate(sp.x - 320, sp.y - 186 - 18 * (1 - ease(ramp(st, 0, 0.6))))
        d.fill_poly(d.cut_plate(40, 124, 600, 248, 22), f"rgba(0,229,255,{(0.06 * sa) / 0.55})", css(CYAN, (0.8 * sa) / 0.55), 2)
        d.glow(css(CYAN, 0.5), 8)
        d.fill_poly([(78, 140), (196, 140), (182, 232), (64, 232)], css(CYAN, min(0.9, (0.9 * sa) / 0.55)), None)
        d.no_glow()
        d.text("LVL", 124, 164, 16, "#000", 700, 3, "center", sa / 0.55)
        ctx.save()
        ctx.translate(124, 220)
        ctx.transform(1, 0, -0.176, 1, 0, 0)
        d.text(str(g.level), 0, 0, 62, "#000", 900, 0, "center", sa / 0.55)
        ctx.restore()
        nm = level_name(g.level)
        size = 54
        while size > 30 and d.text_w(nm, size, 800, 4) > 340:
            size -= 2
        d.text(nm, 224, 186 + size * 0.36, size, "#fff", 800, 4, "left", sa / 0.55)
        ctx.restore()
    # rocks, far to near
    live = sorted(game.live_rocks(), key=lambda w: w.p)
    for w in live:
        pr = game.proj(w.az, w.el)
        px, py = pr.x, pr.y
        r = rock_radius(w) * PPD
        al = 1.0
        if w.arrive:
            u = clamp((clock - w.arrive.t0 - w.arrive.delay) / w.arrive.dur, 0, 1)
            if u <= 0:
                continue
            k = u * u
            px, py = CENTER + (px - CENTER) * k, CENTER + (py - CENTER) * k
            r = r * (0.12 + 0.88 * k)
            al = min(1, u * 6)
        if not _on((px, py), r + 30, ox):
            continue
        blink = w.p >= BLINK_FROM and math.sin(clock * 6.283 * lerp(3, 10, ramp(w.p, BLINK_FROM, 1))) > 0  # faster and faster as it closes
        ctx.save()
        ctx.global_alpha = al
        d.draw_rock(px, py, r, w.rot, GOLD if w.carrier else PINK, True, w.hurt > 0, blink)
        ctx.restore()
        if w.hp < w.max:
            by = min(py + r + 6, 596)
            bw = min(r * 1.4, 220)
            ctx.fill_style = "rgba(255,255,255,.25)"
            ctx.fill_rect(px - bw / 2, by, bw, 3)
            ctx.fill_style = css(GOLD if w.carrier else PINK, 0.9)
            ctx.fill_rect(px - bw / 2, by, bw * (w.hp / w.max), 3)
    # crystals
    for c in g.crystals:
        p = game.proj(c.az, c.el)
        if not _visible(game, p, 40):
            continue
        pul = 1 + 0.12 * math.sin(clock * 6 + c.az)
        ctx.save()
        ctx.translate(p.x, p.y)
        ctx.rotate(clock * 1.5)
        ctx.scale(pul, pul)
        d.glow("rgba(255,200,0,.9)", 10)
        d.fill_poly([(0, -14), (9, 0), (0, 14), (-9, 0)], "#ffc800", "#fff3b0", 1.5)
        d.no_glow()
        ctx.restore()
        if c.dwell > 0:
            ctx.stroke_style = css(GOLD, 0.9)
            ctx.line_width = 3
            ctx.begin_path()
            ctx.arc(p.x, p.y, 22, -HALF, -HALF + (math.pi * 2 * c.dwell) / HARVEST)
            ctx.stroke()
    for q in g.gauges:
        draw_gauge(d, game, q)
    # the Overlord BMS chip: hold ring, label, and an arrow back to it when your aim slips
    if g.chip:
        c = g.chip
        p = game.proj(c.az, c.el)
        prog = clamp(c.dwell / CHIP_HOLD, 0, 1)
        if _visible(game, p, 80):
            cx = p.x + math.sin(clock * 2) * 4
            cy = p.y + math.cos(clock * 3) * 3
            _hold_ring(d, c, cx, cy, 58, prog)
            draw_chip(d, cx, cy, 90, 1 + (0.1 if prog > 0.95 else 0))
            lx = clamp(cx, 16 + 205, W - 16 - 205)
            d.text("HOLD YOUR AIM ON THE CHIP", lx, cy + 112, 18, "#fff", 700, 4, "center")
            if not c.on_target:
                _slip_arrow(d, game, cx, cy)
    # a battery wing: hold ring, label, and an arrow back to it when your aim slips
    if g.wing:
        wg = g.wing
        wp = game.proj(wg.az, wg.el)
        wprog = clamp(wg.dwell / WING_HOLD, 0, 1)
        if _visible(game, wp, 90):
            wx = wp.x + math.sin(clock * 1.6) * 5
            wy = wp.y + math.cos(clock * 2.3) * 4
            _hold_ring(d, wg, wx, wy, 70, wprog)
            d.glow("rgba(255,200,0,.8)", 16)
            wing_icon(d, wx, wy, 0.95, 0.9, False, -0.2 + math.sin(clock * 1.3) * 0.08)
            d.no_glow()
            lx = clamp(wx, 16 + 205, W - 16 - 205)
            d.text("HOLD YOUR AIM ON THE WING", lx, wy + 118, 18, "#fff", 700, 4, "center")
            if not wg.on_target:
                _slip_arrow(d, game, wx, wy)
    # pointer arrows: blue to the closest rock, gold to the closest crystal or chip, only while it is out of view
    if g.mode != "lost":
        draw_rock_arrows(d, game, [w for w in live if not game.arriving(w)])  # an arrow for every rock out of view; red when it is critically close
    tg = None
    td = 1e9
    for c in g.crystals:
        dd = game.ang_dist(c.az, c.el)
        if dd < td:
            td = dd
            tg = c
    if g.chip:
        tg = g.chip
    if g.wing:
        tg = g.wing
    if tg is not None and g.mode != "lost":
        draw_pointer(d, game, tg.az, tg.el, GOLD, 32)
    # the shot: a bolt that streaks in diagonally from off-screen, alternating lower right and lower left
    if g.flash > 0:
        cx0 = W + ox if g.flash_side > 0 else -ox
        gl = ctx.create_radial_gradient(cx0, W, 0, cx0, W, 150)
        gl.add_color_stop(0, f"rgba(255,226,122,{(0.55 * g.flash) / 0.09})")
        gl.add_color_stop(1, "rgba(255,226,122,0)")
        ctx.fill_style = gl
        ctx.fill_rect(W + ox - 160 if g.flash_side > 0 else -ox, W - 160, 160, 160)
    for b in g.bolts:
        f = b.t / 0.14
        head = clamp(f, 0, 1)
        tail = clamp(f - 0.5, 0, 1)
        sx = W + ox + 80 if b.side > 0 else -ox - 80
        sy = W + 110
        hx, hy = lerp(sx, b.tx, head), lerp(sy, b.ty, head)
        tx, ty = lerp(sx, b.tx, tail), lerp(sy, b.ty, tail)
        fade = 1 - ramp(b.t, 0.12, 0.22)
        ctx.save()
        ctx.global_alpha = fade
        ctx.line_cap = "round"
        d.glow("rgba(255,60,220,.9)", 14)
        ctx.stroke_style = "rgba(255,60,220,.65)"
        ctx.line_width = 10
        ctx.begin_path()
        ctx.move_to(tx, ty)
        ctx.line_to(hx, hy)
        ctx.stroke()
        d.no_glow()
        ctx.stroke_style = "#ffe0fb"
        ctx.line_width = 4
        ctx.begin_path()
        ctx.move_to(lerp(tx, hx, 0.3), lerp(ty, hy, 0.3))
        ctx.line_to(hx, hy)
        ctx.stroke()
        ctx.fill_style = "#fff"
        ctx.begin_path()
        ctx.arc(hx, hy, 6, 0, 7)
        ctx.fill()
        ctx.restore()
    for f in g.fx:
        if f.t < 0:
            continue
        p = game.proj(f.az, f.el)
        if f.k == "burst":
            b = f.t / 0.9
            a1 = max(0, 1 - b)
            if b < 1:
                ctx.stroke_style = css(f.col, 0.9 * a1)
                ctx.line_width = 8 - 6 * b
                ctx.begin_path()
                ctx.arc(p.x, p.y, f.r * 0.5 + 170 * ease(b), 0, 7)
                ctx.stroke()
                for i in range(10):
                    an = (i / 10) * 6.283
                    r1 = 20 + 110 * ease(b)
                    r2 = r1 + 26 * (1 - b)
                    ctx.stroke_style = css(f.col, a1)
                    ctx.line_width = 4
                    ctx.begin_path()
                    ctx.move_to(p.x + math.cos(an) * r1, p.y + math.sin(an) * r1)
                    ctx.line_to(p.x + math.cos(an) * r2, p.y + math.sin(an) * r2)
                    ctx.stroke()
        elif f.k == "spark":
            s = f.t / 0.25
            if s < 1:
                ctx.fill_style = f"rgba(255,255,255,{0.9 * (1 - s)})"
                ctx.begin_path()
                ctx.arc(p.x, p.y, 10 + 10 * s, 0, 7)
                ctx.fill()
        elif f.k == "glitch":
            gl2 = f.t / 0.55
            if gl2 < 1:
                seedn = math.floor(f.t * 24)
                for j in range(7):
                    hh = ((seedn * 37 + j * 91) % 100) / 100
                    ctx.fill_style = css(f.col, (1 - gl2) * (0.5 + 0.4 * hh))
                    ctx.fill_rect(p.x - 60 + hh * 40 - j * 3, p.y - 40 + j * 12 + hh * 6, 30 + hh * 80, 3 + (j % 3) * 2)
        elif f.k == "ping":
            p2 = f.t / 0.5
            if p2 < 1:
                ctx.stroke_style = css(GOLD, 1 - p2)
                ctx.line_width = 3
                ctx.begin_path()
                ctx.arc(p.x, p.y, 14 + 30 * p2, 0, 7)
                ctx.stroke()
    for f in g.floaters:
        p = game.proj(f.az, f.el)
        d.text(f.s, p.x, p.y - 20 - 40 * ease(f.t / 1.2), 28, GOLD, 900, 0, "center", 1 - f.t / 1.2)
    draw_award(d, game)
    frac = clamp(g.charge / g.capacity, 0, 1)
    tone = PINK if frac < LOW else g.bad.col if g.bad else GOLD if g.chip_collected else CYAN
    a_t = clock - g.award_t0 if g.award_t0 is not None else None
    draw_cells(d, clock, frac, tone, True, 1)
    ctx.stroke_style = css(tone, 0.5)
    ctx.line_width = 1
    ctx.begin_path()
    ctx.move_to(164, 8)
    ctx.line_to(164, 62)
    ctx.stroke()
    d.text(f"LVL {g.level}", 176, 44, 26, tone, 700, 2)
    for wk in range(2):
        wing_icon(d, 364 + wk * 46, 35, 0.3, 0.9 if g.wings > wk else 0.12, g.wings <= wk, -0.15, True)
    d.text(str(g.score), 535, 40, 28, "#fff", 700, 0, "right")
    badge = ramp(a_t, BADGE_AT, BADGE_AT + 0.5) if a_t is not None else (1 if g.chip_collected else 0)
    if g.bad:
        bu = ramp(clock - g.bad_t0, 0, 0.4)
        bk = 0.5 + 0.5 * ease(bu)
        bcol = g.bad.col
        ctx.save()
        ctx.translate(64, 82)
        ctx.scale(bk, bk)
        ctx.translate(-64, -82)
        ctx.global_alpha = min(1, bu * 3) * (0.8 + 0.2 * math.sin(clock * 5))
        ctx.fill_style = css(bcol)
        ctx.begin_path()
        d.round_rect(26, 68, 104, 28, 14)
        ctx.fill()
        draw_bad_chip(d, clock, 44, 82, 24, (255, 255, 255), 3, 1)
        d.text("−" + g.bad.cut, 106, 89, 16, "#000", 900, 0, "center")
        ctx.restore()
    elif badge > 0:
        u = badge
        k = 0.4 + 0.6 * ease(u) + 0.25 * math.sin(u * math.pi)
        ctx.save()
        ctx.translate(64, 82)
        ctx.scale(k, k)
        ctx.translate(-64, -82)
        ctx.global_alpha = min(1, u * 3)
        ctx.fill_style = "#ffc800"
        ctx.begin_path()
        d.round_rect(26, 68, 76, 28, 14)
        ctx.fill()
        d.logo(40, 82, 24)
        d.text("×2", 76, 89, 17, "#000", 900, 0)
        ctx.restore()
    if g.mode == "intermission":
        draw_plate(d, game)
    if g.tutorial and g.level == 1 and g.mode == "playing":
        tt = clock - g.tut_t0
        p1 = ramp(tt, 2.6, 3.0) * (1 - ramp(tt, 7.0, 7.4))
        p2 = ramp(tt, 7.4, 7.8) * (0.7 + 0.3 * math.sin(tt * 12))
        d.text("TURN YOUR HEAD", 320, 548, 22, CYAN, 700, 6, "center", p1)
        d.text("SAY “PEW”", 320, 548, 28, GOLD, 900, 6, "center", p2)
    bt = clock - g.bad_t0
    if 0 <= bt < 0.8 and g.bad:
        bc = g.bad.col
        ctx.fill_style = css(bc, 0.38 * (1 - bt / 0.8))
        ctx.fill_rect(-ox, 0, W + 2 * ox, W)
        for q2 in range(9):
            rh = ((math.floor(bt * 30) * 53 + q2 * 29) % 100) / 100
            ctx.fill_style = css(bc, 0.55 * (1 - bt / 0.8))
            ctx.fill_rect(rh * 300, rh * 640, 200 + rh * 300, 4 + (q2 % 4) * 3)
    draw_callout(d, game)
    if g.mode == "lost":
        lt = ramp(g.lost_t, 0, 0.6)
        ctx.fill_style = f"rgba(255,60,220,{0.16 * lt * (1 if g.lost_cause == 'hull' else 0)})"
        ctx.fill_rect(-ox, 0, W + 2 * ox, W)
    ctx.restore()
    apx = game.aim_px()
    d.crosshair(apx.x, apx.y, 0.3 if g.mode == "lost" else 1)  # the crosshair follows the mouse (the view follows the arrow keys)
