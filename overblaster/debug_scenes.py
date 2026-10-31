"""Jump a game to a known moment, for screenshots and manual checks (port of web src/debug/scenes.ts).

Used by tools/render_scene.py and tools/compare_web.py with the same scene names as the web demo's `#test=<scene>[:arg[:arg2]]`.
"""

from typing import Optional

from .core import (
    BAD, CHIP_CAPACITY, GAME_AT, HIT_FORGIVENESS, INTRO_CUES, MAX_LEVEL, Game, Gauge, Pickup, bot_target, empty_input, rock_radius,
)

DT = 1 / 30


def _face(g: Game) -> None:
    p = bot_target(g)
    g.view.az = p["az"]
    g.view.el = p["el"]


def _step(g: Game, inp, sec: float, fire: bool, bot: bool = True) -> None:
    for _ in range(int(sec * 30 + 0.5)):
        if g.phase != "play":
            break
        if bot:
            _face(g)
        inp.fire = fire and g.run.mode == "playing"
        g.update(DT, inp)
        g.drain()
    inp.fire = False


def _until(g: Game, inp, cond, max_steps: int = 6000) -> None:
    n = 0
    while not cond() and n < max_steps and g.phase == "play":
        n += 1
        _face(g)
        inp.fire = g.run.mode == "playing"
        g.update(DT, inp)
        g.drain()
    inp.fire = False


def _tick(g: Game, inp, n: int) -> None:
    for _ in range(n):
        g.update(DT, inp)
        g.drain()


def intro_at(g: Game, t: float) -> None:
    """Show the intro at time t (seconds)."""
    g.frozen = False
    g.begin_intro()
    g.drain()
    for i in range(len(INTRO_CUES)):
        g.intro.fired.add(i)
    inp = empty_input()
    inp.pointer.inside = True
    if t < GAME_AT:
        g.intro.t = t
        g.input = inp
        g.frozen = True
        return
    g.intro.t = GAME_AT - 0.001
    for _ in range(int((t - GAME_AT) * 30 + 0.5) + 1):
        if g.phase != "intro":
            break
        g.update(DT, inp)
        g.drain()
    g.frozen = True


def apply_scene(g: Game, name: str, arg: Optional[str] = None, arg2: Optional[str] = None) -> None:
    g.frozen = False
    inp = empty_input()
    inp.pointer.inside = True
    g.input = inp
    if name == "title":
        inp.pointer.inside = False
        g.phase = "title"
        g.frozen = True
        return
    if name == "intro":
        intro_at(g, float(arg or 0))
        return
    g.new_game(False)
    g.phase = "play"
    g.drain()
    R = lambda: g.run  # noqa: E731

    def free(lvl: int) -> None:
        R().chip_collected = True
        R().capacity = CHIP_CAPACITY
        R().charge = CHIP_CAPACITY
        g.start_level(lvl)

    def enough(w) -> bool:
        return (not w.dead) and R().t >= w.spawn_at

    def in_reach() -> bool:
        return any(enough(w) and not g.arriving(w) and g.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS for w in R().worlds)

    if name == "splash":
        _step(g, inp, 2.6, False, False)
    elif name == "arrow":
        _step(g, inp, 5.5, False, False)
    elif name == "rocks":
        _step(g, inp, 9, False, False)
        _face(g)
    elif name == "fight":
        _step(g, inp, 11, True)
    elif name == "laser":
        g.start_level(5)
        R().tutorial = False
        _step(g, inp, 6, False, False)
        _face(g)
        inp.fire = True
        _tick(g, inp, 3)
    elif name == "mouse":
        g.start_level(5)
        R().tutorial = False
        _step(g, inp, 6, False, False)
        inp.pointer.mouse = True
        rk = [w for w in R().worlds if enough(w)][0]
        g.view.az = rk.az - 6
        g.view.el = rk.el + 2
        pr = g.proj(rk.az, rk.el)
        inp.pointer.x, inp.pointer.y = pr.x, pr.y
        inp.fire = True
        _tick(g, inp, 4)
    elif name == "win":
        R().level = MAX_LEVEL
        R().score = 123456
        R().lost_cause = "win"
        g.phase = "over"
        g.over = {"t": 1}
    elif name == "over":
        R().charge = 0
        _until(g, inp, lambda: g.phase == "over")
        g.phase = "over"
        g.over = {"t": 1}
    elif name == "wing":
        free(14)
        R().worlds = []
        R().t = 6
        R().tutorial = False
        _step(g, inp, 0.1, False, False)
        w = R().wing
        if arg == "hold":
            g.view.az = w.az
            g.view.el = w.el
            _step(g, inp, 1.2, False, False)
        elif arg == "side":
            g.view.az = (w.az + 12) % 360
            _step(g, inp, 0.2, False, False)
    elif name == "lvl":
        free(int(arg or "7") or 7)
        _step(g, inp, float(arg2 or "4"), False, False)
    elif name == "fight7":
        R().chip_collected = True
        R().capacity = CHIP_CAPACITY
        R().charge = 180
        g.start_level(7)
        R().tutorial = False
        q = 0
        while q < 900 and not (R().gauges and R().gauges[0].age > 0.6):
            q += 1
            _face(g)
            inp.fire = R().mode == "playing" and in_reach()
            g.update(DT, inp)
            g.drain()
        inp.fire = False
        g.view.az = R().gauges[0].az - 9
        g.view.el = R().gauges[0].el + 3
        _step(g, inp, 0.1, False, False)
    elif name in ("gauge", "bad", "back"):
        R().chip_collected = True
        R().capacity = CHIP_CAPACITY
        R().charge = 160
        g.start_level(7)
        g.view.az = 0
        g.view.el = 0
        R().worlds = [g.make_world(0, 0, 9999, 30, 3)]
        R().tutorial = False
        R().gauges = [
            Gauge(8, 3, "red", 1, 0, 0, 0, 8, False, False, 2),
            Gauge(-10, -4, "blue", 1, 0, 0, 0, 21, False, False, 2),
        ]
        R().gauge_seen = True
        g.callout("BAD GAUGE!", "IT LOCKS ON TO YOUR AIM. IN 4 SECONDS IT IS YOURS.", BAD["red"]["col"], 30)
        if name != "gauge":
            g.take_bad(R().gauges[0])
            R().callout = None
            g.callout("OVERLORD BMS LOST", "CAPACITY CUT 70%. SHOOT ROCKS: ONE WILL EJECT A NEW BMS.", BAD["red"]["col"], 30)
            _step(g, inp, 0.9, False, False)
        if name == "back":
            R().callout = None
            R().chip = Pickup(0, 0, 0, 0, False)
            _until(g, inp, lambda: R().award_t0 is not None and g.clock - R().award_t0 >= 3.0)
        _step(g, inp, 0.2, False, False)
    else:
        g.start_level(3)
        if name == "close":
            pc = float(arg or "0.9")
            for i, w in enumerate(R().worlds):
                if i == 0:
                    w.hold = False
                    w.spawn_at = -1
                    w.p = pc
                    w.az = g.view.az
                    w.el = g.view.el
                    w.speed = 0
                    w.azv = w.elv = 0
                    w.carrier = False
                else:
                    w.dead = True
            _tick(g, inp, 2)
        elif name == "arrows":
            R().t = 3
            for i, w in enumerate(R().worlds):
                w.hold = False
                w.spawn_at = -1
                w.p = 0.08 + (i % 6) * 0.17
                w.azv = w.elv = 0
                w.az = (i * 31) % 360
                w.el = ((i * 7) % 30) - 15
            g.view.az = 0
            g.view.el = 0
            _tick(g, inp, 3)
        elif name == "wave1":
            _step(g, inp, 7, False, False)
            g.view.az = 0
            g.view.el = 0
        elif name == "wave1b":
            _until(g, inp, lambda: R().t > 9)
        elif name == "wave2":
            _until(g, inp, lambda: R().award_t0 is not None and g.clock - R().award_t0 >= 9.5)
        elif name == "chip50":
            _until(g, inp, lambda: R().chip is not None and R().chip.dwell >= 1.2)
        elif name == "chipslip":
            _until(g, inp, lambda: R().chip is not None and R().chip.dwell >= 0.8)
            g.view.az += 6
            g.view.el -= 2
            _tick(g, inp, 28)
        elif name == "chipfar":
            _until(g, inp, lambda: R().chip is not None)
            g.view.az += 20
            _tick(g, inp, 20)
        elif name == "award":
            _until(g, inp, lambda: R().award_t0 is not None and g.clock - R().award_t0 >= 2.6)
        elif name == "plate":
            _until(g, inp, lambda: R().mode == "intermission" and g.clock - R().plate_at >= 3.2, 9000)
    g.frozen = True
