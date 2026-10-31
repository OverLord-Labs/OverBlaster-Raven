"""The story intro: the bridge, the way back, the countdown, the jump (port of web src/render/story.ts).

Line-for-line translations of the web's canvas calls onto the Ctx facade in draw.py. Everything is a pure function of the intro
time `t`, so any frame can be drawn on its own (the debug scenes rely on that).
"""

import math
from typing import Callable, List, Tuple

from ..core.constants import CYAN, PINK, W
from ..core.intro import COUNT_AT, COUNT_STEP, EV, INTRO_LINES, JUMP_AT, PARTS, SH
from ..core.layout import SKIPS, in_box
from ..core.math_ import TAU, clamp, ease, js_round, lerp, ramp
from ..core.rng import Rng, srng
from .draw import Draw, css
from .sprites import wing_icon

# colours as "r,g,b" strings, the way the bridge builds its rgba() values
CYs, GDs, PKs = "0,229,255", "255,200,0", "255,60,220"

# the warp rays and the debris that rush at you as the first level arrives: (a, speed, phase, width, cyan?) and (a, d, dur, rot, size)
RAYS: List[Tuple[float, float, float, float, bool]] = []
DEBRIS: List[Tuple[float, float, float, float, float]] = []
_r = Rng(7)
for _i in range(100):
    # drawn in the web's object-literal order: a, sp, ph, w
    _a = _r.next() * 6.283
    _sp = 0.5 + _r.next() * 1.1
    _ph = _r.next()
    _w = 1.5 + _r.next() * 2
    RAYS.append((_a, _sp, _ph, _w, _i % 5 == 0))
for _i in range(30):
    _dur = 0.4 + _r.next() * 0.3
    _a = _r.next() * 6.283
    _dd = _r.next() * (1 - _dur)
    _rot = _r.next() * 6
    _sz = 60 + _r.next() * 90
    DEBRIS.append((_a, _dd, _dur, _rot, _sz))
del _r, _i, _a, _sp, _ph, _w, _dur, _dd, _rot, _sz

# the bridge: the big front window and the two side panes (where the wings are)
WIN = [
    [(140, 100), (500, 100), (538, 372), (102, 372)],
    [(0, 128), (92, 156), (86, 366), (0, 396)],
    [(640, 128), (548, 156), (554, 366), (640, 396)],
]


def plg(ctx, p) -> None:
    """Add a closed polygon to the current path."""
    for k, q in enumerate(p):
        if k:
            ctx.line_to(q[0], q[1])
        else:
            ctx.move_to(q[0], q[1])
    ctx.close_path()


def sparks(ctx, x: float, y: float, n: int, t: float, seed: float, spread: float) -> None:
    r = srng(seed + math.floor(t * 14))
    ctx.save()
    for i in range(n):
        an = r() * TAU
        dd = r() * spread
        ctx.stroke_style = "rgba(255,170,60,.95)" if i % 3 else "#fff"
        ctx.line_width = 1 + r() * 2
        ctx.begin_path()
        ctx.move_to(x + math.cos(an) * dd * 0.4, y + math.sin(an) * dd * 0.4)
        ctx.line_to(x + math.cos(an) * dd, y + math.sin(an) * dd)
        ctx.stroke()
    ctx.restore()


def wing_pane(d: Draw, side: int, tear: float, spark: float, t: float, dead: bool) -> None:
    """One side pane: the wing, sparking, tearing away (`tear` 0..1), and the dashed outline it leaves behind once gone."""
    ctx = d.ctx
    rx = 88 if side < 0 else 552
    ry = 262
    ctx.save()
    ctx.begin_path()
    plg(ctx, WIN[1 if side < 0 else 2])
    ctx.clip()
    if tear >= 1:
        if dead:
            ctx.set_line_dash([10, 8])
            ctx.stroke_style = f"rgba({PKs},{0.35 + 0.3 * math.sin(t * 5)})"
            ctx.line_width = 2.5
            ctx.begin_path()
            ctx.move_to(rx, 195)
            ctx.line_to(rx + side * 130, 215)
            ctx.line_to(rx + side * 130, 330)
            ctx.line_to(rx, 345)
            ctx.close_path()
            ctx.stroke()
            ctx.set_line_dash([])
        ctx.restore()
        return
    k = ease(tear)
    bend = spark * 0.05 * side
    ctx.save()
    ctx.translate(rx + side * k * 320, ry + k * 120)
    ctx.rotate(side * k * 1.8 + bend)
    ctx.translate(-rx, -ry)
    fl = 0.8 + 0.18 * math.sin(t * 40) * spark
    g = ctx.create_linear_gradient(rx, 0, rx + side * 170, 0)
    g.add_color_stop(0, f"rgba(255,150,30,{fl})")
    g.add_color_stop(1, f"rgba(255,215,60,{fl})")
    ctx.fill_style = g
    ctx.shadow_color = f"rgba({GDs},.9)"
    ctx.shadow_blur = 18
    ctx.begin_path()
    ctx.move_to(rx, 195)
    ctx.line_to(rx + side * 170, 165)
    ctx.line_to(rx + side * 170, 362)
    ctx.line_to(rx, 345)
    ctx.close_path()
    ctx.fill()
    ctx.shadow_blur = 0
    ctx.stroke_style = "rgba(0,0,0,.5)"
    ctx.line_width = 2
    ctx.begin_path()
    for i in range(1, 7):
        px = rx + side * i * 24
        ctx.move_to(px, 195 - i * 4.5)
        ctx.line_to(px, 345 + i * 2.4)
    for i in range(1, 4):
        ctx.move_to(rx, 195 + i * 37)
        ctx.line_to(rx + side * 170, 165 + i * 49)
    ctx.stroke()
    ctx.fill_style = "rgba(255,255,255,.22)"
    ctx.begin_path()
    ctx.move_to(rx, 198)
    ctx.line_to(rx + side * 170, 168)
    ctx.line_to(rx + side * 170, 182)
    ctx.line_to(rx, 212)
    ctx.close_path()
    ctx.fill()
    ctx.fill_style = "#39434d"
    ctx.fill_rect(min(rx, rx - side * 16), 255, 16, 30)
    if spark > 0:
        ctx.stroke_style = f"rgba(255,255,255,{0.4 + 0.5 * spark})"
        ctx.line_width = 2
        r = srng(side + 9 + math.floor(t * 18))
        ctx.begin_path()
        ctx.move_to(rx, 270)
        for j in range(1, 7):
            ctx.line_to(rx + side * j * 24, 270 + (r() - 0.5) * 90 * spark)
        ctx.stroke()
        ctx.stroke_style = f"rgba(255,40,30,{spark * 0.7})"
        ctx.line_width = 3
        ctx.begin_path()
        ctx.move_to(rx + side * 4, 205)
        ctx.line_to(rx + side * 22, 250)
        ctx.line_to(rx + side * 10, 290)
        ctx.line_to(rx + side * 30, 340)
        ctx.stroke()
    ctx.restore()
    if tear > 0:
        fr = srng(side * 13 + 5)
        for i in range(14):
            an = (math.pi if side < 0 else 0) + (fr() - 0.5) * 2.4
            sp = 80 + fr() * 260
            x = rx + math.cos(an) * sp * k * 1.6
            y = ry + math.sin(an) * sp * k * 1.6 + 260 * k * k * fr()
            ctx.save()
            ctx.translate(x, y)
            ctx.rotate(fr() * 6 + tear * 10 * (fr() - 0.5))
            ctx.global_alpha = 1 - tear * 0.6
            ctx.fill_style = "rgba(255,190,50,.95)" if i % 3 else "rgba(80,90,100,.95)"
            q = 5 + fr() * 12
            ctx.fill_rect(-q, -q * 0.5, q * 2, q)
            ctx.restore()
        fb = 1 - ramp(tear, 0, 0.35)
        if fb > 0:
            rg = ctx.create_radial_gradient(rx, ry, 0, rx, ry, 110)
            rg.add_color_stop(0, f"rgba(255,255,230,{fb})")
            rg.add_color_stop(0.35, f"rgba(255,150,40,{fb * 0.8})")
            rg.add_color_stop(1, "rgba(255,60,20,0)")
            ctx.fill_style = rg
            ctx.fill_rect(rx - 120, ry - 120, 240, 240)
    ctx.restore()
    if spark > 0 and tear <= 0:
        ctx.save()
        ctx.begin_path()
        plg(ctx, WIN[1 if side < 0 else 2])
        ctx.clip()
        sparks(ctx, rx, ry, math.floor(6 + 26 * spark), t, 3 if side < 0 else 8, 30 + 80 * spark)
        ctx.restore()


def tunnel(d: Draw, t: float, amt: float, inst: float) -> None:
    """The hyperspace tunnel seen through the front window. `amt` is how fast, `inst` how unstable (turns it pink and flickery)."""
    ctx = d.ctx
    cx, cy = 320, 235
    g = ctx.create_radial_gradient(cx, cy, 0, cx, cy, 380)
    g.add_color_stop(0, "rgba(90,10,60,.9)" if inst > 0.3 else "rgba(10,60,110,.9)")
    g.add_color_stop(0.5, "rgba(4,10,30,.9)")
    g.add_color_stop(1, "#000")
    ctx.fill_style = g
    ctx.fill_rect(0, 0, W, 480)
    col = PKs if inst > 0.3 else CYs
    for i in range(8):
        p = (t * 0.55 * (0.6 + amt) + i / 8) % 1
        rr = p * p * 460
        ctx.stroke_style = f"rgba({col},{(1 - p) * 0.55 * min(1, amt + 0.2)})"
        ctx.line_width = 1 + 5 * p
        ctx.begin_path()
        ctx.ellipse(cx, cy, rr, rr * 0.72, 0, 0, TAU)
        ctx.stroke()
    r = srng(14)
    for i in range(110):
        an = r() * TAU
        sp = 0.5 + r() * 1.2
        ph = r()
        q = (t * sp * (0.35 + 1.6 * amt) + ph) % 1
        r1 = 8 + math.pow(q, 1.7) * 430
        r2 = r1 + 6 + 170 * amt * q * sp
        ctx.global_alpha = min(1, 0.25 + 0.75 * q) * min(1, amt * 2)
        ctx.stroke_style = f"rgb({col})" if i % 5 == 0 else "#fff"
        ctx.line_width = 1 + r() * 2.2 * q
        ctx.begin_path()
        ctx.move_to(cx + math.cos(an) * r1, cy + math.sin(an) * r1 * 0.8)
        ctx.line_to(cx + math.cos(an) * r2, cy + math.sin(an) * r2 * 0.8)
        ctx.stroke()
    ctx.global_alpha = 1
    if inst > 0.5:
        rr2 = srng(40 + math.floor(t * 9))
        if rr2() < 0.6 * inst:
            ctx.save()
            ctx.stroke_style = "rgba(255,255,255,.9)"
            ctx.shadow_color = f"rgb({col})"
            ctx.shadow_blur = 14
            ctx.line_width = 2
            ctx.begin_path()
            sx = 130 if rr2() < 0.5 else 510
            sy = 90 + rr2() * 280
            ctx.move_to(sx, sy)
            for j in range(1, 8):
                ctx.line_to(lerp(sx, cx, j / 7) + (rr2() - 0.5) * 60, lerp(sy, cy, j / 7) + (rr2() - 0.5) * 50)
            ctx.stroke()
            ctx.restore()


# the crew at the console: (x, scale)
CREW = [(130, 1), (232, 0.78), (320, 0.7), (408, 0.78), (510, 1)]


def officer(d: Draw, o: Tuple[float, float], talk: bool, rim: str, t: float, flinch: float, face: float) -> None:
    """A crew silhouette at the console, rim-lit; `flinch` drops them on impact, `face` turns the head."""
    ctx = d.ctx
    ox, os_ = o
    ctx.save()
    ctx.translate(ox, 500 + flinch)
    ctx.scale(os_, os_)
    ctx.translate(0, -500)
    tn = face * 5
    ctx.fill_style = "#04070b"
    ctx.begin_path()
    ctx.move_to(-84, 520)
    ctx.bezier_curve_to(-80, 470, -52, 456, -26, 448)
    ctx.line_to(-14, 436)
    ctx.line_to(14, 436)
    ctx.line_to(26, 448)
    ctx.bezier_curve_to(52, 456, 80, 470, 84, 520)
    ctx.close_path()
    ctx.fill()
    ctx.begin_path()
    ctx.ellipse(tn, 410, 25, 29, 0, 0, TAU)
    ctx.fill()
    ctx.stroke_style = f"rgba({rim},.8)"
    ctx.line_width = 2.6 / os_
    ctx.begin_path()
    ctx.arc(tn, 410, 26, math.pi * 1.1, math.pi * 1.9)
    ctx.stroke()
    ctx.begin_path()
    ctx.move_to(-80, 500)
    ctx.bezier_curve_to(-76, 470, -52, 458, -26, 450)
    ctx.move_to(80, 500)
    ctx.bezier_curve_to(76, 470, 52, 458, 26, 450)
    ctx.stroke()
    ctx.begin_path()
    ctx.arc(tn, 412, 28, math.pi * 0.95, math.pi * 1.35)
    ctx.stroke()
    ctx.begin_path()
    ctx.move_to(tn - 26, 420)
    ctx.line_to(tn - 18, 436)
    ctx.stroke()
    if talk:
        ctx.fill_style = f"rgba({GDs},{0.6 + 0.4 * math.sin(t * 22)})"
        ctx.shadow_color = f"rgba({GDs},1)"
        ctx.shadow_blur = 12
        ctx.begin_path()
        ctx.arc(tn - 17, 437, 4.5, 0, TAU)
        ctx.fill()
    ctx.restore()


_INTERIOR_LINES = [(140, 100, 0, 0), (500, 100, 640, 0), (102, 372, 0, 500), (538, 372, 640, 500), (0, 60, 140, 100), (640, 60, 500, 100)]
_CONSOLE = [(-20, 524), (150, 492), (490, 492), (660, 524), (660, 660), (-20, 660)]
_BEACONS = [(30, 150), (610, 150), (30, 300), (610, 300)]


def bridge(d: Draw, T: float) -> None:
    """The bridge at story time T: the tunnel, the wings tearing off, the crew, the console's POWER meter, the alarms. A pure function of T."""
    ctx = d.ctx
    s1 = PARTS[1].t0
    w1, w2, drop_at = EV["w1"], EV["w2"], EV["drop"]
    inst = ramp(T, s1, w1 + 0.5)
    drop = ramp(T, drop_at, drop_at + 0.8)
    dead = T > drop_at + 0.7
    tear1 = ramp(T, w1, w1 + 1.1)
    tear2 = ramp(T, w2, w2 + 1.1)
    sp1 = ramp(T, s1 + 0.3, w1) * (0 if tear1 > 0 else 1)
    sp2 = ramp(T, w1 + 0.5, w2) * (0 if tear2 > 0 else 1)
    imp = (math.exp(-(T - w1) * 6) if T >= w1 else 0) + (math.exp(-(T - w2) * 6) if T >= w2 else 0)
    shake = 2.6 * imp
    amt = 0 if dead else (0.55 + 0.55 * inst) * (1 - drop)
    p = 1.0
    if T >= w1:
        p = lerp(1, 0.5, ease(ramp(T, w1, w1 + 0.8)))
    if T >= w2:
        p = lerp(0.5, 0, ease(ramp(T, w2, w2 + 0.9)))
    if inst > 0 and p > 0:
        p = clamp(p + math.sin(T * 31) * 0.03 * inst, 0, 1)
    alarm = ramp(T, s1, s1 + 0.4) * (1 - drop * 0.5) + (0.6 if dead else 0)
    pulse = 0.5 + 0.5 * math.sin(T * 9)
    rim = "255,70,90" if alarm > 0.1 else CYs
    d.clock_t = T
    ctx.save()
    ctx.translate(math.sin(T * 61) * 7 * shake, math.cos(T * 47) * 7 * shake)
    ctx.fill_style = "#000"
    ctx.fill_rect(-20, -20, 680, 680)
    if amt > 0.02:
        tunnel(d, T, amt, inst)
    else:
        d.draw_stars(T, 4, 0, 0.9)
    wing_pane(d, -1, tear1, sp1, T, dead)
    wing_pane(d, 1, tear2, sp2, T, dead)
    # the wings' wreckage tumbling away through the window
    for ev, sd in ((w1, -1), (w2, 1)):
        u = ramp(T, ev, ev + 1.1)
        if u <= 0 or u >= 1:
            continue
        sr = srng(sd + 31)
        ctx.save()
        ctx.begin_path()
        plg(ctx, WIN[0])
        ctx.clip()
        for sj in range(12):
            x0 = 320 + sd * 190
            ex = 320 + (sr() - 0.5) * 420
            ey = 235 + (sr() - 0.4) * 260
            e = ease(u)
            ctx.save()
            ctx.translate(lerp(x0, ex, e), lerp(260, ey, e))
            ctx.rotate(sr() * 6 + u * 9 * (sr() - 0.5))
            ctx.global_alpha = 1 - u * u
            ctx.fill_style = "rgba(255,200,60,1)" if sj % 3 else "rgba(140,150,160,1)"
            q = 2 + 16 * e * (0.5 + sr())
            ctx.fill_rect(-q, -q * 0.5, q * 2, q)
            ctx.restore()
        ctx.restore()
    if dead:
        dr = srng(21)
        for di in range(7):
            dx = 140 + dr() * 360 + math.sin(T * 0.3 + di) * 10
            dy = 120 + dr() * 230 + (T - drop_at) * 4 * (dr() - 0.5)
            q = 4 + dr() * 9
            ctx.save()
            ctx.translate(dx, dy)
            ctx.rotate(dr() * 6 + T * 0.5 * (dr() - 0.5))
            ctx.fill_style = "rgba(255,190,50,.7)" if di % 2 else "rgba(120,130,140,.7)"
            ctx.fill_rect(-q, -q * 0.5, q * 2, q)
            ctx.restore()
    # interior shell
    ctx.fill_style = "#080d14"
    ctx.begin_path()
    ctx.rect(-20, -20, 680, 680)
    for w in WIN:
        plg(ctx, w)
    ctx.fill("evenodd")
    ctx.stroke_style = f"rgba({rim},.22)"
    ctx.line_width = 1.5
    ctx.begin_path()
    for l in _INTERIOR_LINES:
        ctx.move_to(l[0], l[1])
        ctx.line_to(l[2], l[3])
    ctx.stroke()
    strip = 0.35 + 0.65 * pulse if alarm > 0.1 else 0.6
    ctx.stroke_style = f"rgba({rim},{strip * 0.8})"
    ctx.line_width = 3
    ctx.begin_path()
    ctx.move_to(20, 40)
    ctx.line_to(150, 88)
    ctx.move_to(620, 40)
    ctx.line_to(490, 88)
    ctx.stroke()
    ctx.stroke_style = f"rgba({rim},.55)"
    ctx.line_width = 3
    ctx.begin_path()
    for w in WIN:
        plg(ctx, w)
    ctx.stroke()
    fl = min(1, imp) * 7
    for j in (2, 1, 3, 0, 4):
        officer(d, CREW[j], False, rim, T, fl, 0)
    # console
    ctx.fill_style = "#0a1119"
    ctx.begin_path()
    plg(ctx, _CONSOLE)
    ctx.fill()
    ctx.stroke_style = f"rgba({rim},.55)"
    ctx.line_width = 2.5
    ctx.begin_path()
    ctx.move_to(-20, 524)
    ctx.line_to(150, 492)
    ctx.line_to(490, 492)
    ctx.line_to(660, 524)
    ctx.stroke()
    for j, o in enumerate(CREW):
        for m in range(5):
            on = math.sin(T * (6 + j * 1.7) + m * 2.1) > -0.2 if alarm > 0.1 else math.sin(T * (1.2 + j * 0.4) + m * 1.9) > 0.1
            if dead:
                ctx.fill_style = f"rgba(255,60,90,{0.15 + (0.1 * m) % 2})"
            elif on:
                ctx.fill_style = f"rgba({'255,90,80' if alarm > 0.1 else (GDs if j % 2 else CYs)},.95)"
            else:
                ctx.fill_style = "rgba(255,255,255,.12)"
            ctx.fill_rect(o[0] - 24 + m * 11, 498 + (2 if o[1] < 1 else 0), 7, 4)
    for j, l in enumerate(_BEACONS):
        ctx.fill_style = f"rgba(255,50,60,{0.3 + 0.7 * abs(math.sin(T * 7 + j))})" if alarm > 0.1 else f"rgba({CYs},.35)"
        ctx.begin_path()
        ctx.arc(l[0], l[1], 5, 0, TAU)
        ctx.fill()
    d.text("POWER", 150, 540, 13, f"rgba({CYs},.95)", 700, 6, "left")
    d.text(f"{js_round(p * 100)} %", 486, 544, 22, f"rgb({GDs if p > 0.6 else PKs})", 700, 2, "right", 0.5 + 0.5 * math.sin(T * 6) if dead else 1)
    lit = js_round(p * 20)
    bar_col = f"rgba({GDs if p > 0.6 else '255,140,40' if p > 0.25 else '255,60,90'},.95)"
    for k in range(20):
        cx = 148 + k * 17.3
        ctx.begin_path()
        ctx.move_to(cx + 3, 556)
        ctx.line_to(cx + 15, 556)
        ctx.line_to(cx + 12, 592)
        ctx.line_to(cx, 592)
        ctx.close_path()
        if k < lit:
            ctx.fill_style = bar_col
            ctx.shadow_color = f"rgba({GDs},.7)"
            ctx.shadow_blur = 8
            ctx.fill()
            ctx.shadow_blur = 0
        else:
            ctx.stroke_style = "rgba(255,255,255,.25)"
            ctx.line_width = 1
            ctx.stroke()
    gone1, gone2 = T >= w1, T >= w2
    wing_icon(d, 76, 566, 0.4, 0 if gone1 else 0.85, gone1, -0.15)
    wing_icon(d, 564, 566, 0.4, 0 if gone2 else 0.85, gone2, 0.15)
    d.text("WING 1", 76, 604, 12, f"rgb({PKs if gone1 else CYs})", 700, 4, "center")
    d.text("WING 2", 564, 604, 12, f"rgb({PKs if gone2 else CYs})", 700, 4, "center")
    ctx.restore()
    # banners and flashes
    bl = 0.45 if math.floor(T * 5) % 2 else 1
    msg = ""
    if w1 <= T < w1 + 1.3:
        msg = "WING 1  LOST"
    elif w2 <= T < w2 + 1.3:
        msg = "WING 2  LOST"
    elif w1 + 1.3 <= T < drop_at:
        msg = "POWER  FAILURE"
    if msg and not dead:
        ba = ramp(T, s1, s1 + 0.3) * (1 - drop)
        bsz = 34
        while bsz > 18 and d.text_w(msg, bsz, 800, 8) > 500:
            bsz -= 1  # the frame is as wide as its message (up to 560 px)
        fw = max(340, d.text_w(msg, bsz, 800, 8) + 48)
        ctx.save()
        ctx.global_alpha = ba
        ctx.fill_style = "rgba(20,0,6,.72)"
        ctx.fill_rect(320 - fw / 2, 182, fw, 54)
        ctx.stroke_style = f"rgba(255,70,90,{bl})"
        ctx.line_width = 3
        ctx.stroke_rect(320 - fw / 2, 182, fw, 54)
        ctx.restore()
        d.text(msg, 320, 220, bsz, "#fff", 800, 8, "center", bl * ba)
    if alarm > 0.05 and not dead:
        g = ctx.create_radial_gradient(320, 320, 150, 320, 320, 470)
        g.add_color_stop(0, "rgba(255,40,60,0)")
        g.add_color_stop(1, f"rgba(255,40,60,{0.2 * alarm + 0.5 * alarm * pulse})")
        ctx.fill_style = g
        ctx.fill_rect(0, 0, W, W)
        ctx.save()
        ctx.global_composite_operation = "lighter"
        an = T * 5
        bg = ctx.create_radial_gradient(320, 60, 0, 320 + math.cos(an) * 300, 60 + abs(math.sin(an)) * 320, 340)
        bg.add_color_stop(0, f"rgba(255,50,60,{0.35 * alarm})")
        bg.add_color_stop(1, "rgba(255,50,60,0)")
        ctx.fill_style = bg
        ctx.fill_rect(0, 0, W, 500)
        ctx.restore()
    if inst > 0.3 and not dead:
        fr = srng(math.floor(T * 20))
        if fr() < 0.22 * inst:
            ctx.fill_style = f"rgba(0,0,0,{0.35 + fr() * 0.35})"
            ctx.fill_rect(0, 0, W, W)
    for e in (w1, w2):
        if e <= T < e + 0.45:
            ctx.fill_style = f"rgba(255,190,90,{0.7 * (1 - (T - e) / 0.45)})"
            ctx.fill_rect(0, 0, W, W)
    if drop_at <= T < drop_at + 0.9:
        ctx.fill_style = f"rgba(255,255,255,{0.95 * (1 - ramp(T, drop_at, drop_at + 0.9))})"
        ctx.fill_rect(0, 0, W, W)
    if dead:
        ctx.fill_style = "rgba(0,0,0,.4)"
        ctx.fill_rect(0, 0, W, W)
        ep = 0.5 + 0.5 * math.sin(T * 3)
        g2 = ctx.create_radial_gradient(320, 320, 160, 320, 320, 460)
        g2.add_color_stop(0, "rgba(255,40,60,0)")
        g2.add_color_stop(1, f"rgba(255,40,60,{0.12 + 0.3 * ep})")
        ctx.fill_style = g2
        ctx.fill_rect(0, 0, W, W)


# scenes that carry on from the one before, with no fade between
SCN_CONT = [0, 1, 1, 1, 1, 0, 1]


def hazard_route(d: Draw, t: float, x0: float, y0: float, x1: float, y1: float, seed: float, p: float) -> None:
    """The "way back" map: the hazard route from the Meridian up through the belt. `p` is how much of the route is drawn."""
    ctx = d.ctx
    r = srng(seed or 23)
    for _ in range(16):
        u = r()
        px = lerp(x0, x1, u) + (r() - 0.5) * 360
        py = lerp(y0, y1, u) + (r() - 0.5) * 60
        if abs(px - lerp(x0, x1, u) - math.sin(u * 9) * 60) < 50:
            px += 110
        ctx.save()
        ctx.global_alpha *= 0.75
        d.draw_rock(clamp(px, 40, 600), py, 14 + r() * 22, r() * 6 + t * 0.1, PINK, False, False, False)
        ctx.restore()
    ctx.save()
    ctx.stroke_style = f"rgba({CYs},.7)"
    ctx.line_width = 3
    ctx.set_line_dash([8, 8])
    ctx.line_dash_offset = -t * 30
    ctx.begin_path()
    for k in range(int(math.floor(30 * p)) + 1):
        f = k / 30
        x = lerp(x0, x1, f) + math.sin(f * 9) * 60
        y = lerp(y0, y1, f)
        if k:
            ctx.line_to(x, y)
        else:
            ctx.move_to(x, y)
    ctx.stroke()
    ctx.restore()


def map_draw(d: Draw, t: float, rp: float, a1: float, a2: float, nh: float) -> None:
    """The route hologram: the Meridian at the bottom, the way through the belt, and the two wing blips (alpha a1, a2). `nh` fades "NO HYPERSPACE"."""
    ctx = d.ctx
    d.clock_t = t
    hazard_route(d, t, 320, 400, 320, 130, 31, rp)
    ctx.fill_style = f"rgb({CYs})"
    ctx.begin_path()
    ctx.arc(320, 440, 7, 0, TAU)
    ctx.fill()
    ctx.stroke_style = f"rgba({CYs},{1 - ((t * 0.6) % 1)})"
    ctx.line_width = 2
    ctx.begin_path()
    ctx.arc(320, 440, 8 + 36 * ((t * 0.6) % 1), 0, TAU)
    ctx.stroke()
    d.text("MERIDIAN  ·  STRANDED", 320, 478, 14, f"rgb({CYs})", 600, 5, "center")
    for k, (bx, by, ba) in enumerate(((220, 100, a1), (430, 150, a2))):
        p = (t * 0.8 + k * 0.4) % 1
        ctx.save()
        ctx.global_alpha *= ba
        ctx.stroke_style = f"rgba({GDs},{1 - p})"
        ctx.line_width = 2
        ctx.begin_path()
        ctx.arc(bx, by, 8 + 30 * p, 0, TAU)
        ctx.stroke()
        ctx.fill_style = f"rgb({GDs})"
        ctx.begin_path()
        ctx.arc(bx, by, 7, 0, TAU)
        ctx.fill()
        ctx.restore()
    d.text("NO HYPERSPACE", 320, 30, 16, f"rgb({PKs})", 700, 8, "center", nh)


def draw_story(d: Draw, t: float) -> None:
    """The story at intro time t: the bridge for the first five lines, then the route hologram for the last two."""
    ctx = d.ctx
    i = 0
    while i < len(PARTS) - 1 and t >= PARTS[i + 1].t0:
        i += 1
    s = PARTS[i]
    lt = t - s.t0
    a = (1 if SCN_CONT[i] else ramp(lt, 0, 0.45)) * (1 if i + 1 < len(SCN_CONT) and SCN_CONT[i + 1] else 1 - ramp(lt, s.D - 0.4, s.D))
    ctx.save()
    ctx.global_alpha *= a
    d.clock_t = lt
    if i <= 4:
        bridge(d, t)
        if i == 4:
            d.text("EMPTY  SPACE", 320, 230, 18, f"rgba({CYs},.6)", 600, 10, "center", ramp(lt, 0.8, 1.6))
            d.text("EARTH  ·  412,000,000 km", 320, 262, 13, f"rgba({PKs},.85)", 600, 5, "center", ramp(lt, 3, 3.6))
    elif i == 5:
        map_draw(d, lt, ease(ramp(lt, 1, 5)), ramp(lt, 3.4, 3.9), ramp(lt, 3.9, 4.4), ramp(lt, 1.4, 2))
    else:
        map_draw(d, lt + PARTS[5].D, 1, 1, 1, 1)
        d.text("WING 1", 220, 70, 14, f"rgb({GDs})", 700, 4, "center", ramp(lt, 0.3, 0.8))
        d.text("WING 2", 430, 120, 14, f"rgb({GDs})", 700, 4, "center", ramp(lt, 0.6, 1.1))
        d.text("WINGS 0 / 2", 320, 622, 18, f"rgb({PKs})", 700, 8, "center", ramp(lt, 1, 1.5))
    ctx.restore()


def draw_intro(d: Draw, game, draw_playfield: Callable) -> None:
    """The whole intro: the story, the countdown, the jump, and the arrival into level 1.
    `draw_playfield` draws the first level underneath once it has taken over."""
    ctx = d.ctx
    t = game.intro.t
    if game.intro.game:
        draw_playfield(d, game)
    else:
        ctx.fill_style = "#000"
        ctx.fill_rect(0, 0, W, W)
    warp = ramp(t, JUMP_AT, 14.4 + SH) * (1 - ramp(t, 14.4 + SH, 15.6 + SH))
    calm = 1 - warp
    fade = 1 - ramp(t, 14.2 + SH, 14.8 + SH)
    ctx.save()
    ctx.global_alpha = fade
    if t < COUNT_AT:
        draw_story(d, t)
    else:
        d.draw_stars(t, 4 + 40 * warp, 0, 0.9 * calm)
        u = t - COUNT_AT
        if u < 3:  # the rocks begin to stream at you as the count runs out
            if u > 2:
                q = ramp(u, 2, 3)
                sr = srng(55)
                for ri in range(9):
                    an = ri / 9 * 6.283 + sr()
                    dd = 60 + 300 * ease(q) * (0.5 + sr())
                    ctx.save()
                    ctx.global_alpha *= q * 0.8
                    d.draw_rock(320 + math.cos(an) * dd, 320 + math.sin(an) * dd, 6 + 30 * q * q, ri + u, PINK, True, False, False)
                    ctx.restore()
            d.text("WINGS 0 / 2", 320, 622, 18, f"rgb({PKs})", 700, 8, "center")
    cd = 3 - math.floor((t - COUNT_AT) / COUNT_STEP) if COUNT_AT <= t < JUMP_AT else 0
    ph = ((t - COUNT_AT) % COUNT_STEP) / COUNT_STEP
    if cd > 0:
        ctx.save()
        ctx.global_alpha *= 1 - ph * 0.6
        ctx.stroke_style = css(CYAN, 0.8 * (1 - ph))
        ctx.line_width = 5
        ctx.begin_path()
        ctx.arc(320, 320, 90 + 160 * ph, 0, 7)
        ctx.stroke()
        s = 1.5 - 0.5 * ease(min(1, ph * 2))
        ctx.translate(320, 320)
        ctx.scale(s, s)
        d.text(str(cd), 0, 40, 120, "#fff", 900, 0, "center")
        ctx.restore()
    ctx.restore()
    if warp > 0:  # the jump: rays streaming out of the centre, and a shake
        ctx.save()
        ctx.translate(math.sin(t * 77) * 6 * warp, math.cos(t * 63) * 6 * warp)
        for a, sp, ph0, w, cy in RAYS:
            p = (t * sp * (0.4 + 2.6 * warp) + ph0) % 1
            r1 = 20 + p * 520
            r2 = r1 + 8 + 190 * warp * p * sp
            ctx.global_alpha = warp * (0.3 + 0.7 * p)
            ctx.stroke_style = "#00e5ff" if cy else "#fff"
            ctx.line_width = w
            ctx.begin_path()
            ctx.move_to(320 + math.cos(a) * r1, 320 + math.sin(a) * r1)
            ctx.line_to(320 + math.cos(a) * r2, 320 + math.sin(a) * r2)
            ctx.stroke()
        ctx.restore()
    if t >= JUMP_AT:
        d.text("GO", 320, 360, 130, "#fff", 800, 14, "center", 1 - ramp(t, JUMP_AT + 0.2, JUMP_AT + 0.5))
    arr = ramp(t, 14.3 + SH, 16.2 + SH)
    if 0 < arr < 1:
        for a, dd, dur, rot, sz in DEBRIS:
            p = clamp((arr - dd) / dur, 0, 1)
            if p <= 0 or p >= 1:
                continue
            r = 14 + 560 * p * p
            ctx.save()
            ctx.global_alpha = min(1, p * 6)
            d.draw_rock(320 + math.cos(a) * r, 320 + math.sin(a) * r, 4 + sz * p * p, rot + t * 1.5, PINK, True, False, False)
            ctx.restore()
    # the narrator's captions: at the top over the bridge, at the bottom over the map
    for k, l in enumerate(INTRO_LINES):
        if l[0] <= t < l[1]:
            parts = l[2].split("|")
            o = ramp(t, l[0], l[0] + 0.25) * (1 - ramp(t, l[1] - 0.25, l[1]))
            y0 = 20 if k <= 4 else 512
            d.text("NARRATOR", 320, y0, 13, CYAN, 700, 5, "center", o * 0.8)
            d.text(parts[0], 320, y0 + 36, 22, "#fff", 700, 1, "center", o)
            if len(parts) > 1 and parts[1]:
                d.text(parts[1], 320, y0 + 65, 22, "#fff", 700, 1, "center", o)
    if game.story_btn_visible():  # a way out of the story, always on screen while it runs
        a = ramp(t, 0.9, 1.5) * (1 - ramp(t, COUNT_AT - 2.6, COUNT_AT - 1.6))
        b = SKIPS
        pt = game.input.pointer
        hov = in_box(b, pt.x, pt.y)
        ctx.save()
        ctx.global_alpha *= a
        d.fill_poly(d.cut_plate(b.x, b.y, b.x + b.w, b.y + b.h, 9), "rgba(0,229,255,.22)" if hov else "rgba(0,0,0,.55)", css(CYAN, 1 if hov else 0.7), 1.5)
        d.text("SKIP STORY", b.x + 66, b.y + 20, 13, "#fff" if hov else CYAN, 700, 3, "center")
        d.fill_poly([(b.x + 136, b.y + 9), (b.x + 148, b.y + 15), (b.x + 136, b.y + 21)], css(CYAN, 1 if hov else 0.8), None)
        d.fill_poly([(b.x + 148, b.y + 9), (b.x + 160, b.y + 15), (b.x + 148, b.y + 21)], css(CYAN, 1 if hov else 0.8), None)
        ctx.restore()
