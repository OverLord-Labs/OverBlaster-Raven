"""A bot that plays, for tests and balance (port of web src/core/bot.ts)."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .constants import BAD, CHIP_CAPACITY, HIT_FORGIVENESS, TURN_RATE
from .game import Game, rock_radius
from .input_ import empty_input
from .math_ import azd, clamp, js_round
from .rng import Rng
from .types_ import BadState


def bot_target(game: Game) -> Dict[str, float]:
    """Where a reasonably careful player would look next: a wing or the chip first, crystals when the battery needs them, else the most urgent rock."""
    g = game.run
    if g.wing is not None:
        return {"az": g.wing.az, "el": g.wing.el}
    if g.chip is not None:
        return {"az": g.chip.az, "el": g.chip.el}
    live = [w for w in g.worlds if not w.dead and g.t >= w.spawn_at and not game.arriving(w)]
    urgent = any(w.p > 0.5 for w in live)  # a person grabs crystals when the battery needs them or when nothing presses
    if (not urgent or g.charge / g.capacity < 0.35) and g.crystals:
        return {"az": g.crystals[0].az, "el": g.crystals[0].el}
    best = None
    bp = -1.0
    for w in live:
        sc = (100 if w.p >= 0.6 else 0) + w.p * 20 - game.ang_dist(w.az, w.el) * 0.5  # the urgent ones first, then whatever is closest to where you look
        if sc > bp or best is None:
            bp = sc
            best = w
    return {"az": best.az, "el": best.el} if best is not None else {"az": game.view.az, "el": game.view.el}


@dataclass
class SimResult:
    level: int
    lost: bool
    cause: Optional[str]
    seconds: int
    wings: int
    min_charge: float
    rocks: int
    bad_taken: int
    gauges_seen: int


def simulate_level(level: int, seed: int = 1, noise: float = 0, bad: Optional[str] = None, max_seconds: float = 150,
                   loads: Optional[Tuple[float, float]] = None) -> SimResult:
    """Play one level headless with the bot, as if you already had the BMS (the late game)."""
    rng = Rng((seed * 7919 + level * 104729) & 0xFFFFFFFF)
    game = Game(seed=seed * 31 + level, loads=loads)
    game.new_game(False)
    game.phase = "play"
    g0 = game.run
    g0.chip_collected = True
    g0.capacity = CHIP_CAPACITY
    g0.charge = CHIP_CAPACITY
    if bad:
        g0.bad = BadState(bad, BAD[bad]["cap"], BAD[bad]["col"], BAD[bad]["cut"])
        g0.capacity = BAD[bad]["cap"]
        g0.charge = BAD[bad]["cap"]
    game.start_level(level)
    g = game.run
    dt = 1 / 30
    max_step = (TURN_RATE / 30) * 0.9
    off_az = off_el = 0.0
    k = 0
    minf = 1.0
    bad_taken = gauges_seen = 0
    rocks = len(g.worlds)
    inp = empty_input()
    limit = max_seconds * 30
    while game.phase == "play" and g.mode != "intermission":
        if k >= limit:
            break
        k += 1
        p = bot_target(game)
        off_az = off_az * 0.92 + rng.gauss() * noise * 0.28
        off_el = off_el * 0.92 + rng.gauss() * noise * 0.28
        da = azd(p["az"] + off_az, game.view.az)
        de = p["el"] + off_el - game.view.el
        game.view.az = (game.view.az + clamp(da, -max_step, max_step) + 360) % 360
        game.view.el = clamp(game.view.el + clamp(de, -max_step, max_step), -38, 38)  # turns no faster than a head can
        inp.fire = g.mode == "playing" and any(
            not w.dead and g.t >= w.spawn_at and not game.arriving(w) and game.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS
            for w in g.worlds
        )
        game.update(dt, inp)
        for e in game.drain():
            if e["type"] == "zap":
                if e["kind"] == "bad":
                    bad_taken += 1
                elif e["kind"] == "eject":
                    gauges_seen += 1
        minf = min(minf, g.charge / g.capacity)
    return SimResult(level, game.phase == "over", g.lost_cause, js_round(g.t), g.wings, minf, rocks, bad_taken, gauges_seen)
