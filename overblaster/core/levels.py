"""Level names, the voice line for each level, and the planner that lays out a level's rocks
(port of web src/core/levels.ts)."""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .constants import GAUGE_LEVEL, LEVELS, LOADS, WING_LEVELS
from .math_ import clamp, js_mod, js_round, lerp
from .rng import Rng


@dataclass
class PlanRock:
    """One rock in a level's plan. `t` is when it appears, `appr` how many seconds it takes to reach you."""

    t: float
    az: float
    el: float
    hp: float
    appr: float
    eject: Optional[str] = None


def level_name(n: int) -> str:
    return LEVELS[int(clamp(n, 1, len(LEVELS))) - 1]


LEVEL_VOICE = ["name_far", "name_1", "name_2", "name_3", "name_4", "name_5"]


def level_say(n: int) -> List[str]:
    """The voice says "Level", the number, and (for the first six) the name. Numbers above 19 are a tens word, then a units word."""
    k = ["level_word"]
    if n < 20:
        k.append("num_" + ("0" if n < 10 else "") + str(n))
    else:
        k.append("num_" + str(n // 10 * 10))
        if n % 10:
            k.append("num_0" + str(n % 10))
    if n <= 6:
        k.append(LEVEL_VOICE[n - 1])
    return k


def level_note(n: int) -> str:
    """The small note under the next level's name on the sector-cleared plate."""
    if n in WING_LEVELS:
        return "A BATTERY WING DRIFTS IN"
    if n == 4:
        return "NEW: CLUSTERS"
    if n == GAUGE_LEVEL:
        return "NEW: BAD GAUGES"
    if n > GAUGE_LEVEL:
        return ["", "WATCH FOR BAD GAUGES", "WALL OF ROCKS", "FAST AND FRAGILE", "TURN TO FIND THEM", "ARMOURED. BAD GAUGES."][(n - 8) % 6]
    return ""


def gauge_chase(n: int) -> float:
    """Degrees a second a bad gauge drifts toward your crosshair: sweep your head faster than that and it falls behind."""
    return 12 + 0.25 * (n - GAUGE_LEVEL)


def crystals_for(hp: float) -> int:
    return int(clamp(js_round(hp / 3 + 1), 3, 5))


def level_plan(n: int, rng: Rng, loads: Tuple[float, float] = LOADS) -> List[PlanRock]:
    """A level from 4 on is a list of rocks. The pace comes from how much shooting is asked of you per second
    ("load", of the 10 shots a second you can fire), how little time you have before a rock lands, and the bad gauges."""
    plan: List[PlanRock] = []
    kind = "cluster" if n <= 6 else "intro" if n == GAUGE_LEVEL else ["stream", "cluster", "gauge", "swarm", "pincer", "boss"][(n - 8) % 6]
    u = clamp((n - 4) / 38, 0, 1)
    load = lerp(loads[0], loads[1], u)
    hp = [3, 3, 4][n - 4] if n <= 6 else 3 if n == GAUGE_LEVEL else clamp(js_round(3 + (n - 8) * 0.1), 3, 6)
    appr = [24, 22, 20][n - 4] if n <= 6 else max(12, 28 * math.pow(0.98, n - 4))
    spread = 40 if n <= 7 else min(70, 45 + 1.5 * (n - 8))
    span = 20 + 0.4 * (n - 4)
    tt = 1.0
    frac = 0 if n < GAUGE_LEVEL else min(0.45, 0.06 + 0.012 * (n - GAUGE_LEVEL)) + (0.15 if kind in ("gauge", "boss") else 0)

    def side() -> float:
        return rng.signed() * spread

    def lump(t: float, size: int, az: float, h: float, ap: float) -> None:
        for _ in range(size):
            t_ = t + rng.next() * 0.2
            az_ = az + rng.signed() * 4.5
            el_ = clamp(rng.signed() * 3 + js_mod(az * 7, 11) - 5, -18, 18)
            plan.append(PlanRock(t_, az_, el_, h, ap))

    if kind == "intro":
        for i in range(6):
            t_ = tt + i * 3.2
            az_ = side()
            el_ = rng.signed() * 10
            plan.append(PlanRock(t_, az_, el_, hp, appr))
        plan[1].eject = "red"
        plan[4].eject = "blue"
        return plan
    if kind in ("cluster", "boss", "pincer"):
        size = [3, 4, 4][n - 4] if n <= 6 else int(clamp(3 + (n - 8) // 6, 3, 6))
        h = js_round(hp * 1.5) if kind == "boss" else hp
        ap = appr * 0.9 if kind == "boss" else appr
        nL = [4, 5, 6][n - 4] if n <= 6 else js_round((span * 10 * load) / (size * h))
        for i in range(nL):
            if kind == "pincer":
                az_arg = (1 if i % 2 else -1) * min(85, 45 + spread * 0.5) * (0.8 + 0.2 * rng.next())
            else:
                az_arg = side()
            lump(tt, size, az_arg, h, ap)
            tt += ((size * h) / (10 * load)) * (1.3 if n <= 6 else 1.35 if kind == "pincer" else 1)
    elif kind == "swarm":
        h2 = max(1, js_round(hp * 0.5))
        cnt = js_round(((span * 10 * load) / h2) * 0.6)
        for _ in range(cnt):
            az_ = side()
            el_ = rng.signed() * 16
            plan.append(PlanRock(tt, az_, el_, h2, appr * 0.85))
            tt += (h2 / (10 * load)) * (0.7 + 0.6 * rng.next())
    else:
        cnt = js_round((span * 10 * load) / hp)
        for _ in range(cnt):
            az_ = side()
            el_ = rng.signed() * 16
            plan.append(PlanRock(tt, az_, el_, hp, appr))
            tt += (hp / (10 * load)) * (0.75 + 0.5 * rng.next())
    ne = 0 if n < GAUGE_LEVEL else max(1, js_round(len(plan) * frac))
    pick = rng.shuffle(list(range(len(plan))))
    for i in range(ne):
        plan[pick[i]].eject = "red" if rng.next() < 0.5 else "blue"
    plan.sort(key=lambda r: r.t)  # stable, like Array.prototype.sort
    return plan
