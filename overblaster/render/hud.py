"""The callout, the BMS award and the sector-cleared plate (port of web src/render/hud.ts)."""

import math

from ..core.constants import ACK_MIN, BAD, BUBBLE_FOLD, BUBBLE_IN, CELLS, COUNT_S, CYAN, GAUGE_LEVEL, GOLD, LOW, PINK
from ..core.levels import level_name, level_note
from ..core.math_ import clamp, ease, js_round, lerp, ramp
from .draw import Draw, css


def draw_callout(d: Draw, game) -> None:
    co = game.run.callout
    ctx = d.ctx
    if not co:
        return
    ct = game.clock - co.t0
    if ct > co.dur:
        return
    sz = 14
    a = ramp(ct, 0, 0.25) * (1 - ramp(ct, co.dur - 0.5, co.dur))
    while sz > 10 and d.text_w(co.b, sz, 700, 2) > 600:
        sz -= 1
    ctx.save()
    ctx.global_alpha = a * 0.75
    ctx.fill_style = "#000"
    ctx.fill_rect(20, 492, 600, 70)
    ctx.restore()
    ctx.save()
    ctx.global_alpha = a
    ctx.stroke_style = css(co.col, 0.9)
    ctx.line_width = 2
    ctx.stroke_rect(20, 492, 600, 70)
    ctx.restore()
    d.text(co.a, 320, 526, 28, co.col, 900, 4, "center", a)
    d.text(co.b, 320, 551, sz, "#fff", 700, 2, "center", a)


def draw_award(d: Draw, game) -> None:
    """The BMS award: a ring, cells flying to the battery, the medallion and the callout."""
    g = game.run
    ctx = d.ctx
    if g.award_t0 is None or not g.award_origin:
        return
    t = game.clock - g.award_t0
    o = g.award_origin
    br = ramp(t, 0, 0.9)
    if br < 1:
        ctx.stroke_style = css(GOLD, 0.9 * (1 - br))
        ctx.line_width = 7 * (1 - br) + 1
        ctx.begin_path()
        ctx.arc(o.x, o.y, 20 + 180 * ease(br), 0, 7)
        ctx.stroke()
    for i in range(10):
        s0 = 0.1 + i * 0.1
        u = ease(ramp(t, s0, s0 + 1.0))
        a = (i / 10) * 6.283
        k = ramp(t, 0, 0.3)
        al = ramp(t, 0, 0.1) * (1 - ramp(t, s0 + 1.0, s0 + 1.2))
        if al <= 0:
            continue
        bx = o.x + math.cos(a) * 60 * k
        by = o.y + math.sin(a) * 60 * k
        ctx.fill_style = css(CYAN, al)
        ctx.begin_path()
        ctx.arc(lerp(bx, 31 + i * 12.5, u), lerp(by, 20, u), 5, 0, 7)
        ctx.fill()
    # the medallion and the callout
    grow = ease(ramp(t, BUBBLE_IN, BUBBLE_IN + 0.5))
    fold = ease(ramp(t, BUBBLE_FOLD, BUBBLE_FOLD + 0.8))
    sc = grow * (1 - fold)
    su = ramp(t, BUBBLE_IN, BUBBLE_IN + 1.0)
    sx = math.cos(su * math.pi * 4) * (1 - su) + su
    ma = ramp(t, BUBBLE_IN, BUBBLE_IN + 0.2)
    if ma > 0:
        hp = (t * 1.1) % 1
        halo = 0.7 * (1 - hp) * ramp(t, BUBBLE_IN + 1.0, BUBBLE_IN + 1.3)
        if halo > 0:
            ctx.stroke_style = css(CYAN, halo)
            ctx.line_width = 2
            ctx.begin_path()
            ctx.arc(298, 36, 28 + 10 * hp, 0, 7)
            ctx.stroke()
        ctx.save()
        ctx.global_alpha = ma
        ctx.translate(298, 36)
        ctx.scale(max(0.05, abs(sx)), 1)
        img = d._logo()
        if img is not None:
            ctx.draw_image(img, -26, -26, 52, 52)
        ctx.restore()
    if sc > 0.01:
        ctx.save()
        ctx.translate(298, 84)
        ctx.scale(sc, sc)
        ctx.translate(-298, -84)
        d.fill_poly(d.cut_plate(20, 108, 480, 244, 14), "#1a1400", "#ffc800", 2)
        d.fill_poly([(278, 108), (298, 88), (318, 108)], "#ffc800", None)
        d.logo(74, 164, 70)
        ph = (t * 1.3) % 1
        ctx.stroke_style = css(CYAN, 0.8 * (1 - ph))
        ctx.line_width = 2
        ctx.begin_path()
        ctx.arc(74, 164, 36 + 12 * ph, 0, 7)
        ctx.stroke()
        back = g.award_kind == "restore"
        ttl = "OVERLORD BMS RESTORED!" if back else "OVERLORD BMS FOUND!"
        ts = 24
        while ts > 14 and d.text_w(ttl, ts, 900, 2) > 340:
            ts -= 1
        d.text(ttl, 126, 148, ts, GOLD, 900, 2)
        d.text("THE REAL THING IS BACK." if back else "BATTERY MANAGEMENT, BUILT", 126, 178, 16, CYAN, 700, 2)
        d.text("BAD GAUGES: STAY SHARP." if back else "FROM THE SILICON UP.", 126, 200, 16, CYAN, 700, 2)
        d.text("2× THE SHOTS, BACK ON." if back else "NOW YOU GET 2× THE SHOTS.", 126, 232, 17, "#fff", 700, 1)
        ctx.restore()


def draw_plate(d: Draw, game) -> None:
    """The sector-cleared plate."""
    g = game.run
    ctx = d.ctx
    pt = game.clock - g.plate_at
    if pt < 0:
        return
    frac = clamp(g.charge / g.capacity, 0, 1)
    tone = PINK if frac < LOW else g.bad.col if g.bad else GOLD if g.chip_collected else CYAN
    lit = min(CELLS, max(1, math.ceil(frac * CELLS)))
    d.fill_poly(d.cut_plate(90, 166, 550, 476, 22), css(tone, 0.12), css(tone, 0.9), 2)
    ctx.stroke_style = css(tone, 0.4)
    ctx.line_width = 1
    ctx.begin_path()
    ctx.move_to(124, 276)
    ctx.line_to(516, 276)
    ctx.move_to(352, 296)
    ctx.line_to(352, 380)
    ctx.stroke()
    d.text(f"LVL {g.level}", 124, 212, 22, tone, 700, 2)
    d.text("SECTOR CLEARED", 124, 258, 36, "#fff", 900, 2)
    d.text("SCORE", 124, 316, 16, CYAN, 500, 4)
    shown = g.score if pt >= COUNT_S else js_round(g.score * ease(pt / COUNT_S))
    d.text(f"{shown:,}", 124, 352, 34, "#fff", 900, 0)
    na = ramp(pt, 0.5, 1.0)
    dy = 12 * (1 - ease(ramp(pt, 0.5, 1.0)))
    d.text("NEXT", 372, 316, 16, CYAN, 500, 4, "left", na)
    d.text(f"LVL {g.level + 1}", 372, 348 + dy, 30, GOLD, 900, 2, "left", na)
    d.text(level_name(g.level + 1), 372, 372 + dy, 16, "#fff", 500, 3, "left", na)
    note = level_note(g.level + 1)
    if note:
        d.text(note, 372, 389 + dy, 12, BAD["red"]["col"] if g.level + 1 >= GAUGE_LEVEL else CYAN, 700, 3, "left", na)
    for i in range(CELLS):
        pts = d.slanted(124 + i * 15.5, 396, 11, 16, 5)
        if i < lit:
            al = 0.95 * ramp(pt, 0.3 + i * 0.05, 0.65 + i * 0.05)
            d.fill_poly(pts, css(tone, al), css(tone, al), 1)
        else:
            d.fill_poly(pts, None, "rgba(255,255,255,.22)", 1)
    pa = ramp(pt, COUNT_S + 0.2, COUNT_S + 0.5) * (0.7 + 0.3 * math.sin(pt * 6) if pt >= ACK_MIN else 0.5)
    d.text("CLICK OR SPACE TO CONTINUE", 320, 452, 18, GOLD, 700, 4, "center", pa)
