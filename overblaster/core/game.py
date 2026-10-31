"""The whole game, with no screen, audio or timer in it (port of web src/core/game.ts).

    game = Game(seed=7)
    game.update(dt, input_frame)        # advance by dt seconds with this frame's input
    for e in game.drain(): ...           # sounds and app events to act on (dicts with a "type" key)
    # read game.phase / game.run / game.view / game.intro to draw it
"""

import math
import random
from typing import List, Optional, Tuple

from .constants import (
    ACK_MIN, BAD, CENTER, CHIP_CAPACITY, CHIP_DRAIN, CHIP_HOLD, CHIP_LEVEL, COUNT_S, CRITICAL, CRYSTAL_RADIUS, CRYSTAL_VALUE,
    FIRST_HOLD, GAUGE_HOLD, GAUGE_LIFE, GAUGE_RADIUS, GOLD, HARVEST, HIT_FORGIVENESS, LOADS, LOW, MAX_ASPECT, MAX_LEVEL, PINK,
    PPD, RESTORE_AFTER, RESTORE_ODDS, SETTLE, SHOT_COOLDOWN, SHOT_COST, SPAWN_SPREAD, START_CHARGE, W, WING_HOLD, WING_LEVELS, WING_RADIUS,
)
from .events import Event
from .input_ import InputFrame, empty_input
from .intro import COUNT_AT, GAME_AT, INTRO_CUES, INTRO_END, RISER_AT, SKIP_STORY_TO
from .layout import RETRY, SKIPS, TOTITLE, in_box
from .levels import crystals_for, gauge_chase, level_plan, level_say
from .math_ import azd, clamp, ramp, wrap360
from .rng import Rng
from .types_ import (
    Arrive, BadState, Bolt, Callout, Crystal, Floater, Fx, Gauge, HitAt, IntroState, PendingSay, Pickup, Point, Rock, Run, Wave2,
)
from .view import View, on_screen

# where the first rocks come to rest: all inside the window, none on top of another
ENTRY_SPOTS = [(-9, 3), (8, 6), (-3, -6), (11, -4)]


def rock_radius(w: Rock) -> float:
    """Angular radius in degrees: a rock grows slowly, then fast; at impact it is 8 degrees, a diameter of 53% of the screen."""
    return (1.0 + 1.8 * w.p + 5.2 * math.pow(w.p, 4)) * (1.08 if w.carrier else 1)


class Game:
    def __init__(self, seed: Optional[int] = None, loads: Optional[Tuple[float, float]] = None) -> None:
        self.phase = "title"  # "title" | "intro" | "play" | "over"
        self.clock = 0.0
        self.view = View()
        self.rng = Rng(seed if seed is not None else random.getrandbits(32))
        self.loads = loads if loads is not None else LOADS
        self.input: InputFrame = empty_input()
        self.intro = IntroState()
        self.run: Run = Run()
        self.over: Optional[dict] = None  # {"t": seconds}
        self.launching = False  # between asking to launch and the host calling begin_intro()
        self.ox = 0.0  # extra visible width on each side of the 640 px square (0 on a square screen)
        self.frozen = False  # frozen games ignore update(): used by screenshot and debug tools
        self._events: List[Event] = []

    # ---------------------------------------------------------------- events
    def emit(self, e: Event) -> None:
        self._events.append(e)

    def drain(self) -> List[Event]:
        """Take the events emitted since the last call."""
        e, self._events = self._events, []
        return e

    def _sfx(self, name: str, gain: Optional[float] = None) -> None:
        e: Event = {"type": "sfx", "name": name}
        if gain is not None:
            e["gain"] = gain
        self.emit(e)

    def _say(self, keys: List[str]) -> None:
        self.emit({"type": "say", "keys": keys})

    def set_aspect(self, aspect: float) -> None:
        """Tell the game how wide the screen is (width / height). The 30 degree vertical field stays; a wider screen sees more sky to each side."""
        self.ox = (clamp(aspect, 1, MAX_ASPECT) * W - W) / 2

    # ---------------------------------------------------------------- aim and projection
    def proj(self, az: float, el: float):
        return self.view.proj(az, el)

    def aim_px(self) -> Point:
        """Where the crosshair is on screen: it follows the pointer (gaze, mouse); with head motion alone it stays at the centre."""
        p = self.input.pointer
        if p.mouse:
            return Point(clamp(p.x, -self.ox, W + self.ox), clamp(p.y, 0, W))
        return Point(CENTER, CENTER)

    def ang_dist(self, az: float, el: float) -> float:
        """Degrees from the crosshair to a point of the sky."""
        a = self.aim_px()
        p = self.proj(az, el)
        return math.hypot(p.dx - (a.x - CENTER), p.dy - (a.y - CENTER)) / PPD

    def arriving(self, w: Rock) -> bool:
        return w.arrive is not None and self.clock < w.arrive.t0 + w.arrive.delay + w.arrive.dur

    def live_rocks(self) -> List[Rock]:
        """Rocks that are on the field right now."""
        return [w for w in self.run.worlds if not w.dead and self.run.t >= w.spawn_at]

    # ---------------------------------------------------------------- phases
    def _set_phase(self, p: str) -> None:
        if self.phase != p:
            self.phase = p
            self.emit({"type": "phase", "phase": p})

    def launch(self) -> None:
        """Ask to start. The host loads audio and then calls begin_intro()."""
        if self.phase != "title" or self.launching:
            return
        self.launching = True
        self.emit({"type": "launch"})

    def begin_intro(self) -> None:
        self.launching = False
        self.intro = IntroState()
        self._set_phase("intro")

    def begin_game(self) -> None:
        """Straight into level 1 with no intro."""
        self.launching = False
        self.new_game(False)
        self._set_phase("play")
        self.emit({"type": "music", "name": "game"})

    def to_title(self) -> None:
        self._set_phase("title")
        self.emit({"type": "music", "name": None})

    # ---------------------------------------------------------------- new game and levels
    def new_game(self, from_intro: bool) -> None:
        self.view.reset()
        self.run = Run(charge=START_CHARGE, capacity=START_CHARGE)
        self.start_level(1, from_intro)

    def make_world(self, az: float, el: float, spawn_at: float, approach: float, hp: float, p: Optional[float] = None, hold: bool = False,
                   carrier: bool = False, arrive: Optional[Arrive] = None, eject: Optional[str] = None) -> Rock:
        r = self.rng
        # the draws are made in this order, as in the web game
        azv = (r.next() - 0.5) * 0.9
        elv = (r.next() - 0.5) * 0.4
        rot = r.next() * 6
        spin = (r.next() - 0.5) * 0.6
        return Rock(az=az, el=el, azv=azv, elv=elv, p=p or 0, spawn_at=9999 if hold else spawn_at, hold=bool(hold), speed=1 / approach,
                    hp=hp, max=hp, carrier=bool(carrier), rot=rot, spin=spin, dead=False, hurt=0.0, arrive=arrive, eject=eject or None)

    def start_level(self, n: int, from_intro: bool = False) -> None:
        g, r, V = self.run, self.rng, self.view
        g.level = n
        g.mode = "playing"
        g.t = 0
        g.crystals = []
        g.chip = None
        g.wing = None
        g.wing_spawned = False
        g.plate_voiced = 0
        g.splash_az = V.az
        g.splash_el = V.el + 6.3
        g.tut_t0 = self.clock
        g.pending_say = None
        g.wave2 = None
        g.stingy = False
        g.gauges = []
        approach = 34 / (1 + 0.12 * (n - 1))
        carrier = n >= CHIP_LEVEL and not g.chip_collected
        entry = len(ENTRY_SPOTS) if from_intro else 0
        g.worlds = []
        if n == CHIP_LEVEL and not g.chip_collected:
            # wave one is a huge, tough cluster that drains the battery; the gold rock with the BMS is inside it.
            # When the BMS is taken, wave two finishes the level.
            g.stingy = True
            g.wave2 = Wave2(10, 0.9, 6, 30)
            CARRIER_AT = 7
            cl: List[Tuple[float, float]] = []
            for _ in range(5):  # five tight clusters of three, each arriving as one lump
                a = V.az + r.signed() * 11
                e = r.signed() * 8
                cl.append((a, e))
            for i in range(15):
                ce = cl[i // 3]
                az = wrap360(ce[0] + r.signed() * 5)
                el = clamp(ce[1] + r.signed() * 4, -18, 18)
                p = 0.08 + r.next() * 0.22
                g.worlds.append(self.make_world(az, el, 1.0 + (i // 3) * 2.4, 42, 7, p=p, carrier=i == CARRIER_AT, hold=i == CARRIER_AT))
        elif n >= 4:
            for pr in level_plan(n, r, self.loads):
                g.worlds.append(self.make_world(wrap360(V.az + pr.az), pr.el, pr.t, pr.appr, pr.hp, eject=pr.eject))
        else:
            count = 4 + 2 * n
            gap = max(1.4, 2.8 - 0.15 * n)
            hp = 4 + n
            for j in range(count):
                is_c = carrier and j == 0
                az = wrap360(V.az + r.signed() * SPAWN_SPREAD)
                el = r.signed() * 16
                w = self.make_world(az, el, 1.0 + j * gap, approach, hp + 4 if is_c else hp, carrier=is_c)
                if j < entry:
                    w.az = wrap360(V.az + ENTRY_SPOTS[j][0])
                    w.el = ENTRY_SPOTS[j][1]
                    w.azv = w.elv = 0
                    w.p = 0.42 + 0.04 * j
                    w.spawn_at = -9
                    w.arrive = Arrive(self.clock, j * 0.16, 1.5)
                elif entry:
                    w.spawn_at = 4.0 + (j - entry) * gap
                g.worlds.append(w)
        self.emit({"type": "levelStart", "level": n})
        if from_intro:
            g.splash_t0 = self.clock + 5.0
            g.pending_say = PendingSay(self.clock + 5.0, level_say(n))
        else:
            g.splash_t0 = self.clock
            self._sfx("level_start")
            self._say(level_say(n))

    # ---------------------------------------------------------------- things that happen
    def _lose_game(self, cause: str) -> None:
        g = self.run
        if g.mode == "lost":
            return
        g.mode = "lost"
        g.lost_cause = cause
        g.lost_t = 0
        if cause == "hull":
            self._sfx("hull_death")
            self._say(["hull_destroyed"])
            g.shake = 1
        else:
            self._sfx("battery_dead")
            self._say(["battery_dead"])

    def _destroy(self, w: Rock) -> None:
        g, r = self.run, self.rng
        w.dead = True
        g.score += 100
        self._sfx("explode", 0.8)
        g.fx.append(Fx("burst", w.az, w.el, -0.12, r=rock_radius(w) * PPD, col=GOLD if w.carrier else PINK))
        g.floaters.append(Floater(w.az, w.el, "+100", 0))
        if w.carrier:
            self.eject_chip(w.az, w.el)
        else:
            n = 2 + math.floor(r.next() * 2) if g.level < 4 else crystals_for(w.max)
            if w.eject:
                n = max(1, n - 1)
            for i in range(n):
                g.crystals.append(Crystal(w.az + (i - (n - 1) / 2) * 2.4, w.el, 0, 0))
            if w.eject:
                self.eject_gauge(w)
            elif g.bad is not None and g.chip is None:
                g.kills_bad += 1  # lost your BMS? sooner or later a rock spits a new one out
                if g.kills_bad >= 1 and (r.next() < RESTORE_ODDS or g.kills_bad >= (3 if g.bad_count <= 1 else RESTORE_AFTER)):
                    self.eject_chip(w.az, w.el + 3)

    def eject_chip(self, az: float, el: float) -> None:
        g = self.run
        g.chip = Pickup(az, el, 0, 0, False)
        g.chip_seen = False
        g.kills_bad = 0

    def callout(self, a: str, b: str, col, dur: Optional[float] = None) -> None:
        self.run.callout = Callout(a, b, col, self.clock, dur or 4.2)

    def eject_gauge(self, w: Rock) -> None:
        g, r = self.run, self.rng
        color = w.eject
        first = not g.gauge_seen
        g.gauge_seen = True
        vaz = (r.next() - 0.5) * 7
        vel = (r.next() - 0.5) * 2.5
        seed = math.floor(r.next() * 1000)
        g.gauges.append(Gauge(w.az, clamp(w.el, -20, 20), color, 0, 0, vaz, vel, seed, False, first, FIRST_HOLD if first else GAUGE_HOLD))
        g.fx.append(Fx("glitch", w.az, w.el, 0, col=BAD[color]["col"]))
        self.emit({"type": "zap", "kind": "eject"})
        if first:
            self.callout("BAD GAUGE!", "IT LOCKS ON TO YOUR AIM. IN 4 SECONDS IT IS YOURS.", BAD[color]["col"], 6)
            self._say(["gauge_seen"])

    def take_bad(self, gz: Gauge) -> None:
        g, b = self.run, BAD[gz.color]
        g.gauges = [x for x in g.gauges if x is not gz]  # by identity, like indexOf
        g.bad_t0 = self.clock
        g.shake = 0.5
        g.kills_bad = 0
        g.score = max(0, g.score - 200)
        self.emit({"type": "zap", "kind": "bad"})
        self._say(["bad_gauge"])
        if g.bad is None:
            g.bad_count += 1
            g.bad = BadState(gz.color, b["cap"], b["col"], b["cut"])
            g.capacity = b["cap"]
            g.charge = min(g.charge, g.capacity)
            self.callout("OVERLORD BMS LOST", f"CAPACITY CUT {b['cut']}. SHOOT ROCKS: ONE WILL EJECT A NEW BMS.", b["col"], 5.5)
        else:
            g.charge = max(0, g.charge - 0.3 * g.capacity)
            self.callout("ANOTHER BAD GAUGE", "YOUR BATTERY JUST TOOK A HIT", b["col"], 3.5)
        g.fx.append(Fx("glitch", gz.az, gz.el, 0, col=b["col"]))

    def _shoot(self) -> None:
        g = self.run
        g.charge -= SHOT_COST
        g.flash = 0.09
        g.tutorial = False
        best: Optional[Rock] = None
        bd = 1e9
        g.hit_at = None
        for w in g.worlds:
            if w.dead or g.t < w.spawn_at or self.arriving(w):
                continue
            d = self.ang_dist(w.az, w.el)
            if d <= rock_radius(w) * HIT_FORGIVENESS and d < bd:
                best = w
                bd = d
        tgt = self.aim_px()
        if best is not None:
            p = self.proj(best.az, best.el)  # shots pass straight through a bad gauge: you can only keep your aim off it
            tgt = Point(p.x, p.y)
        g.side = -g.side
        g.flash_side = g.side
        g.bolts.append(Bolt(0, tgt.x, tgt.y, g.side))  # the blaster fires from the right side, then the left, then the right
        if best is not None:
            best.hp -= 1
            best.p = max(0, best.p - 0.0015)
            best.hurt = 0.08
            g.hit_at = HitAt(best.az, best.el)
            if self.clock - g.last_hit > 0.1:
                self._sfx("hit", 0.45)
                g.last_hit = self.clock
            g.fx.append(Fx("spark", best.az, best.el, -0.13))
            if best.hp <= 0:
                self._destroy(best)

    def _acknowledge(self) -> None:
        g = self.run
        self._sfx("ui_confirm")
        if g.level >= MAX_LEVEL:
            g.lost_cause = "win"
            self._set_phase("over")
            self.over = {"t": 0}
            self._sfx("level_clear")
            self._say(["victory"])
            self.emit({"type": "gameOver", "won": True, "cause": "win", "score": g.score, "level": g.level})
            return
        self.start_level(g.level + 1)

    def _collect_wing(self) -> None:
        g = self.run
        w = g.wing
        g.wings += 1
        g.score += 2000
        g.fx.append(Fx("ping", w.az, w.el, 0))
        g.floaters.append(Floater(w.az, w.el + 4, f"WING {g.wings} / 2", 0))
        g.wing = None
        self._sfx("chip_collect")
        self.emit({"type": "wingFound", "wings": g.wings})

    def _collect_chip(self) -> None:
        g = self.run
        c = g.chip
        p = self.proj(c.az, c.el)
        g.award_origin = Point(clamp(p.x, 30, W - 30), clamp(p.y, 30, W - 30))
        back = g.chip_collected
        g.chip = None
        g.chip_seen = False
        g.chip_collected = True
        g.bad = None
        g.capacity = CHIP_CAPACITY
        g.charge = CHIP_CAPACITY
        g.score += 500 if back else 1000
        g.award_t0 = self.clock
        g.award_kind = "restore" if back else "found"
        g.callout = None
        self._sfx("chip_collect")
        self._say(["chip_back" if back else "chip_found"])
        g.stingy = False
        self.emit({"type": "chipFound"})
        if g.wave2 is not None:
            w2 = g.wave2
            g.wave2 = None
            for i in range(w2.count):
                az = wrap360(self.view.az + self.rng.signed() * 30)
                el = self.rng.signed() * 14
                g.worlds.append(self.make_world(az, el, g.t + 5.5 + i * w2.gap, w2.approach, w2.hp))

    # ---------------------------------------------------------------- input
    def _press(self, x: float, y: float) -> None:
        if self.phase == "intro" and not self.intro.game:
            if self.story_btn_visible() and in_box(SKIPS, x, y):
                self.skip_story()
            return
        if self.phase == "title":
            self.launch()
            return
        if self.phase == "play" and self.run.mode == "intermission":
            if self.clock - self.run.plate_at >= ACK_MIN:
                self._acknowledge()
            return
        if self.phase == "over":
            if in_box(RETRY, x, y):
                self.new_game(False)
                self._set_phase("play")
                self.emit({"type": "music", "name": "game"})
            elif in_box(TOTITLE, x, y):
                self.to_title()

    def _command(self, c: str) -> None:
        if c == "launch":
            if self.phase == "title":
                self.launch()
        elif c == "skipStory":
            self.skip_story()
        elif c == "skipIntro":
            self.skip_intro()
        elif c == "recenter":
            self.view.recenter()
        elif c == "flipYaw":
            self.view.flip_yaw()
        elif c == "flipPitch":
            self.view.flip_pitch()

    def story_btn_visible(self) -> bool:
        """Is the in-canvas "skip story" button showing?"""
        return self.phase == "intro" and not self.intro.game and 0.9 < self.intro.t < COUNT_AT - 1.6

    def can_skip_intro(self) -> bool:
        """Is a skip control worth offering right now (story or countdown still running)?"""
        return self.phase == "intro" and self.intro.t < GAME_AT

    def skip_story(self) -> None:
        """Skip the story only: the narrator stops, and the drive's last climb, the countdown and the jump still play."""
        I = self.intro
        if self.phase != "intro" or I.game or I.t >= SKIP_STORY_TO:
            return
        need_riser = I.t < RISER_AT
        for i, c in enumerate(INTRO_CUES):
            if c.at < SKIP_STORY_TO:
                I.fired.add(i)
        self._say([])
        self.emit({"type": "alarm", "on": False})
        if need_riser:
            self.emit({"type": "sfx", "name": "warp_charge", "gain": 0.9, "offset": SKIP_STORY_TO - RISER_AT, "tag": "riser"})
        I.t = SKIP_STORY_TO

    def skip_intro(self) -> None:
        """Skip the whole intro and drop into level 1."""
        I = self.intro
        if not self.can_skip_intro():
            return
        for i, c in enumerate(INTRO_CUES):
            if c.at < GAME_AT:
                I.fired.add(i)
        self.emit({"type": "stopRiser"})
        self._say([])
        self.emit({"type": "alarm", "on": False})
        self.emit({"type": "drone", "on": False})
        I.t = GAME_AT

    # ---------------------------------------------------------------- the clock
    def update(self, dt: float, input: InputFrame) -> None:
        if self.frozen:
            return
        self.input = input
        for c in input.commands:
            self._command(c)
        for p in input.presses:
            self._press(p.x, p.y)
        self.clock += dt
        if self.phase == "intro":
            self._update_intro(dt)
            if not self.intro.game:
                return
        elif self.phase == "over":
            if self.over is not None:
                self.over["t"] += dt
            return
        elif self.phase != "play":
            return
        self._update_run(dt)

    def _update_intro(self, dt: float) -> None:
        I = self.intro
        I.t += dt
        for i, c in enumerate(INTRO_CUES):
            if I.t >= c.at and i not in I.fired:
                I.fired.add(i)
                for e in c.events:
                    self.emit(dict(e))
        if I.t >= GAME_AT and not I.game:
            I.game = True
            self.new_game(True)
            self.emit({"type": "music", "name": "game"})
        if I.t >= INTRO_END:
            self._set_phase("play")

    def _update_run(self, dt: float) -> None:
        g, inp, clock = self.run, self.input, self.clock
        if g.pending_say is not None and clock >= g.pending_say.at:
            self._say(g.pending_say.keys)
            g.pending_say = None
        g.t += dt
        g.flash = max(0, g.flash - dt)
        g.shake = max(0, g.shake - dt * 1.2)
        self.view.update(dt, inp)
        for b in g.bolts:
            b.t += dt
        g.bolts = [b for b in g.bolts if b.t < 0.3]
        for f in g.fx:
            f.t += dt
        g.fx = [f for f in g.fx if f.t < 1.2]
        for f in g.floaters:
            f.t += dt
        g.floaters = [f for f in g.floaters if f.t < 1.2]
        if g.callout is not None and clock - g.callout.t0 > g.callout.dur:
            g.callout = None
        if g.mode == "lost":
            g.lost_t += dt
            if g.lost_t >= (1.4 if g.lost_cause == "hull" else 0.6):
                self._set_phase("over")
                self.over = {"t": 0}
                self.emit({"type": "gameOver", "won": False, "cause": g.lost_cause, "score": g.score, "level": g.level})
            return
        for w in g.worlds:
            if w.dead or g.t < w.spawn_at:
                continue
            w.p += w.speed * dt
            w.rot += w.spin * dt
            w.az = wrap360(w.az + w.azv * dt)
            w.el = clamp(w.el + w.elv * dt, -22, 22)
            w.hurt = max(0, w.hurt - dt)
            if w.p >= 1:
                self._lose_game("hull")
        if g.mode == "lost":
            return
        # a rock that is critically close and whose arrow is showing sounds an alarm (once per rock, not more than one alarm a second)
        for w in g.worlds:
            if w.dead or g.t < w.spawn_at or self.arriving(w) or w.warned or w.p < CRITICAL:
                continue
            if on_screen(self.proj(w.az, w.el), rock_radius(w) * PPD, self.ox):
                continue
            w.warned = True
            if clock - g.last_warn > 1.0:
                g.last_warn = clock
                g.warns += 1
                self._sfx("warning", 0.9)
        g.cool = max(g.cool - dt, -min(dt, SHOT_COOLDOWN))
        if g.mode == "playing" and inp.fire and g.charge >= SHOT_COST and g.cool <= 0:
            self._shoot()
            g.cool += SHOT_COOLDOWN
        for c in g.crystals:
            c.age += dt
            c.el = max(-24, c.el - 0.6 * dt)
            on = self.ang_dist(c.az, c.el) <= CRYSTAL_RADIUS
            c.dwell = c.dwell + dt if on else max(0, c.dwell - dt * 2)
        kept: List[Crystal] = []
        for c in g.crystals:
            if c.age > 9:
                continue
            if c.dwell >= HARVEST:
                g.charge = min(g.capacity, g.charge + CRYSTAL_VALUE)
                g.score += 10
                self._sfx("crystal", 0.8)
                g.fx.append(Fx("ping", c.az, c.el, 0))
                continue
            kept.append(c)
        g.crystals = kept
        if g.chip is not None:
            c = g.chip
            c.age += dt
            c.el = max(-20, c.el - 0.25 * dt)
            if not g.chip_seen:
                g.chip_seen = True
                g.tick_k = 0
                self._say(["chip_seen"])
            c.on_target = self.ang_dist(c.az, c.el) <= CRYSTAL_RADIUS
            if c.on_target:
                c.dwell += dt
            else:
                c.dwell = max(0, c.dwell - dt * CHIP_DRAIN * CHIP_HOLD)
            k = min(8, math.floor((c.dwell / CHIP_HOLD) * 8))
            if c.on_target:
                while g.tick_k < k:
                    self._sfx("charge_" + str(g.tick_k), 0.8)
                    g.tick_k += 1
            if c.dwell >= CHIP_HOLD:
                self._collect_chip()
            elif c.age > 18:  # you let it drift off: it comes back as a rock to shoot again
                g.chip = None
                g.chip_seen = False
                g.worlds.append(Rock(az=wrap360(self.view.az + self.rng.signed() * 30), el=0, azv=0, elv=0, p=0.3, spawn_at=g.t, speed=1 / 22,
                                     hp=4, max=4, carrier=True, rot=0, spin=0.2, dead=False, hurt=0, hold=False, eject=None))
        # the level's wing drifts in a few seconds after it starts, and the level will not end until it is yours
        wi = WING_LEVELS.index(g.level) if g.level in WING_LEVELS else -1
        if g.mode == "playing" and wi >= 0 and g.wing is None and not g.wing_spawned and g.t > 5:
            g.wing_spawned = True
            sign = -1 if self.rng.next() < 0.5 else 1
            g.wing = Pickup(wrap360(self.view.az + sign * (28 + self.rng.next() * 14)), 2, 0, 0, False)
            self._sfx("warning", 0.8)
            g.floaters.append(Floater(g.wing.az, g.wing.el + 5, "BATTERY WING", 0))
        if g.wing is not None:
            wg = g.wing
            wg.age += dt
            wg.on_target = self.ang_dist(wg.az, wg.el) <= WING_RADIUS
            if wg.on_target:
                wg.dwell += dt
            else:
                wg.dwell = max(0, wg.dwell - dt * CHIP_DRAIN * WING_HOLD)
            if wg.dwell >= WING_HOLD:
                self._collect_wing()
        for q in g.gauges:
            q.age += dt
            q.vaz *= 1 - 1.2 * dt
            q.vel *= 1 - 1.2 * dt  # thrown out of the rock, then it settles and homes in on your crosshair
            cs = math.cos((q.el * math.pi) / 180)
            ap = self.aim_px()
            pq = self.proj(q.az, q.el)
            dx = (ap.x - pq.x) / PPD
            dy = -(ap.y - pq.y) / PPD
            dist = math.hypot(dx, dy)
            step = min(dist, (60 if q.first else gauge_chase(g.level)) * ramp(q.age, 0.5, 1.3) * dt)
            q.az = wrap360(q.az + q.vaz * dt + ((step * dx) / dist / max(0.3, cs) if dist > 1e-6 else 0))
            q.el = clamp(q.el + q.vel * dt + ((step * dy) / dist if dist > 1e-6 else 0), -24, 24)
            q.on = g.mode == "playing" and self.ang_dist(q.az, q.el) <= GAUGE_RADIUS
            q.dwell = q.dwell + dt if q.on else max(0, q.dwell - dt * 1.5)
        for q in list(g.gauges):
            if q.dwell >= q.hold:
                self.take_bad(q)
            elif q.age > GAUGE_LIFE and not q.first:
                g.gauges = [x for x in g.gauges if x is not q]
        frac = g.charge / g.capacity
        if g.stingy:  # wave one: the belt feeds on your power. It bleeds you down to a last reserve, never to zero, and the BMS rock turns up once you are low.
            if frac > 0.12:
                g.charge = max(0.12 * g.capacity, g.charge - 2.0 * dt)
            if frac < 0.14:
                g.charge = min(g.capacity, g.charge + 4.0 * dt)
            for w in g.worlds:
                if w.hold and not w.dead and ((g.t > 9 and frac < 0.4) or frac < 0.22 or g.t > 22):
                    w.hold = False
                    w.spawn_at = g.t + 0.4
        if frac < LOW and not g.low_fired:
            g.low_fired = True
            self._sfx("low_battery")
            self._say(["battery_low"])
        elif frac >= LOW + 0.1:
            g.low_fired = False
        pending = any(not w.dead for w in g.worlds)
        if g.mode == "playing":
            if not pending and not g.crystals and g.chip is None and g.wing is None and not (wi >= 0 and not g.wing_spawned):
                g.mode = "intermission"
                g.inter_t = 0
                g.gauges = []
                left = max(0, SETTLE - (clock - g.award_t0)) if g.award_t0 is not None else 0
                g.plate_at = clock + left
                g.plate_voiced = 0
                self.emit({"type": "levelClear", "level": g.level, "score": g.score})
            elif g.charge < SHOT_COST and not g.crystals and g.chip is None and pending and not g.stingy:
                self._lose_game("battery")  # in wave one the last reserve keeps you alive until the BMS
        elif g.mode == "intermission":
            pt = clock - g.plate_at
            if pt >= 0 and g.plate_voiced == 0:
                g.plate_voiced = 1
                self._sfx("level_clear")
                self._say(["level_clear"])
            if pt >= COUNT_S + 0.2 and g.plate_voiced == 1:
                g.plate_voiced = 2
                self._say(["continue"])

    def continue_from_plate(self) -> None:
        """Continue from the sector-cleared plate (what a click does once the plate accepts it). Exposed for bots and tests."""
        if self.phase == "play" and self.run.mode == "intermission":
            self._acknowledge()
