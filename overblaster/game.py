"""OverBlaster game rules. Pure Python: no Raven imports, no wall-clock reads.

Everything lives in a spherical "sky" described by azimuth / elevation degrees.
The renderer projects it onto the display using the player's head direction.
Ported from the old Glass game's BadGuy / Bullet / GameView / MainActivity.
"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from . import config as C


class State(Enum):
    PLAYING = "playing"
    INTERMISSION = "intermission"
    LOST = "lost"


@dataclass
class World:
    """A Rogue World drifting toward the ship. `progress` 0 = far, 1 = impact."""

    az: float
    el: float
    az_v: float
    el_v: float
    progress: float
    speed: float
    hp: int
    kind: str
    chip_carrier: bool = False
    max_hp: int = 0

    def __post_init__(self) -> None:
        self.max_hp = self.max_hp or self.hp

    @property
    def radius(self) -> float:
        return C.WORLD_MIN_RADIUS + (C.WORLD_MAX_RADIUS - C.WORLD_MIN_RADIUS) * self.progress


@dataclass
class Crystal:
    """An energy crystal (or the Overlord chip) waiting to be harvested."""

    az: float
    el: float
    age: float = 0.0
    dwell: float = 0.0
    is_chip: bool = False
    on_target: bool = False  # the aim was on it at the last update

    @property
    def needed(self) -> float:
        """Seconds of aim it takes to collect."""
        return C.CHIP_HOLD_S if self.is_chip else C.HARVEST_DWELL_S

    @property
    def progress(self) -> float:
        return min(1.0, self.dwell / self.needed)

    @property
    def lifetime(self) -> float:
        return C.CHIP_LIFETIME_S if self.is_chip else C.CRYSTAL_LIFETIME_S


@dataclass
class Shot:
    """A shot's visual record. The hit itself is resolved instantly in shoot(); this only drives
    the animation: where it landed, what happened, and how long ago."""

    az: float
    el: float
    kind: str  # "miss" | "hit" | "kill"
    radius_deg: float = 0.0  # the target world's size, for scaling the impact
    age: float = 0.0


def wrap_az(az: float) -> float:
    return az % 360.0


def az_delta(a: float, b: float) -> float:
    """Signed shortest azimuth difference a - b in (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


def angular_distance(az1: float, el1: float, az2: float, el2: float) -> float:
    """Approximate on-screen distance in degrees (azimuth scaled by cos(elevation))."""
    d_az = az_delta(az1, az2) * math.cos(math.radians((el1 + el2) / 2.0))
    return math.hypot(d_az, el1 - el2)


@dataclass
class Game:
    rng: random.Random = field(default_factory=random.Random)
    view_az: float = 0.0  # where the player is looking; worlds spawn around it
    view_el: float = 0.0

    level: int = 0
    state: State = State.INTERMISSION
    score: int = 0
    capacity: float = C.BATTERY_START
    charge: float = C.BATTERY_START
    chip_collected: bool = False
    chip_at: Optional[Tuple[float, float]] = None  # where the chip was when it was collected
    worlds: List[World] = field(default_factory=list)
    crystals: List[Crystal] = field(default_factory=list)
    shots: List[Shot] = field(default_factory=list)
    lost_cause: Optional[str] = None  # "hull" (a world hit the ship) or "battery"
    impact: Optional[Tuple[float, float, float]] = None  # az, el, radius_deg of the world that hit
    events: List[str] = field(default_factory=list)  # consumed by the UI each tick

    _intermission_left: float = 0.5
    _cooldown: float = 0.0
    _fired_this_tick: bool = False
    _chip_pending: bool = False
    hold_between_levels: bool = False  # keep the level-clear plate up until acknowledge() (the app sets this)
    _acked: bool = False

    # ----- queries ---------------------------------------------------------
    @property
    def battery_fraction(self) -> float:
        return max(0.0, min(1.0, self.charge / self.capacity))

    def can_shoot(self) -> bool:
        return (
            self.state is State.PLAYING
            and not self._fired_this_tick  # at most one shot per tick
            and self._cooldown <= 0
            and self.charge >= C.SHOT_COST
        )

    def take_events(self) -> List[str]:
        events, self.events = self.events, []
        return events

    # ----- actions ---------------------------------------------------------
    def set_view(self, az: float, el: float) -> None:
        self.view_az = wrap_az(az)
        self.view_el = el

    def shoot(self, aim_az: float, aim_el: float) -> bool:
        """Fire at a bearing. Spends battery whether or not it hits. Returns True if fired."""
        if not self.can_shoot():
            return False
        self.charge -= C.SHOT_COST
        # += (not =) keeps the fraction of a tick left over, so holding the trigger averages exactly
        # 1 / SHOT_COOLDOWN_S shots a second even when the tick is longer than the cooldown.
        self._cooldown += C.SHOT_COOLDOWN_S
        self._fired_this_tick = True
        self.events.append("pew")

        target = self._world_at(aim_az, aim_el)
        if target is None:
            self.shots.append(Shot(aim_az, aim_el, "miss"))
            return True

        self.score += C.SCORE_HIT
        target.hp -= 1
        target.progress = max(0.0, target.progress - C.KNOCKBACK)
        if target.hp > 0:
            self.shots.append(Shot(target.az, target.el, "hit", target.radius))
            self.events.append("hit")
        else:
            self.shots.append(Shot(target.az, target.el, "kill", target.radius))
            self._destroy(target)
        return True

    def _world_at(self, az: float, el: float) -> Optional[World]:
        """Nearest world whose (forgiving) disc contains the bearing; nearer worlds win."""
        best: Optional[World] = None
        for w in self.worlds:
            if angular_distance(az, el, w.az, w.el) <= w.radius * C.HIT_FORGIVENESS:
                if best is None or w.progress > best.progress:
                    best = w
        return best

    def _destroy(self, world: World) -> None:
        self.worlds.remove(world)
        self.score += C.SCORE_DESTROY
        self.events.append("destroyed")
        if world.chip_carrier:
            self._drop(world, is_chip=True)
            return
        # Tougher worlds cost more shots, so they pay out proportionally more crystals.
        drops = self.rng.randint(C.CRYSTALS_MIN, C.CRYSTALS_MAX)
        for _ in range(min(drops, C.MAX_CRYSTALS_ON_SCREEN - len(self.crystals))):
            self._drop(world)

    def _drop(self, world: World, is_chip: bool = False) -> None:
        spread = 0.0 if is_chip else world.radius
        self.crystals.append(
            Crystal(
                az=wrap_az(world.az + self.rng.uniform(-spread, spread)),
                el=_clamp(world.el + self.rng.uniform(-spread, spread), -C.EL_LIMIT, C.EL_LIMIT),
                is_chip=is_chip,
            )
        )

    # ----- simulation ------------------------------------------------------
    def update(self, dt: float, aim_az: float, aim_el: float) -> None:
        """Advance the game by dt seconds. `aim_*` is where the crosshair points."""
        self.shots = [s for s in self.shots if _age(s, dt)]  # animations play on even after losing
        if self.state is State.LOST:
            return

        # The cooldown may go up to one tick (never more than one cooldown) negative: that credit is
        # what lets a 67 ms tick fire every 100 ms on average. It never banks more than one shot, so
        # waiting doesn't store up a burst.
        self._cooldown = max(self._cooldown - dt, -min(dt, C.SHOT_COOLDOWN_S))
        self._fired_this_tick = False

        if self.state is State.INTERMISSION:
            self._intermission_left -= dt
            if self._intermission_left <= 0 and (not self._holding() or self._acked):
                self._start_level(self.level + 1)
            return

        self._move_worlds(dt)
        if self.state is State.LOST:  # a world hit the ship: nothing else can happen, least of all
            return  # "level clear" just because that world was the last one
        self._update_crystals(dt, aim_az, aim_el)
        self._check_end_conditions()

    def _holding(self) -> bool:
        return self.hold_between_levels and self.level >= 1  # the opening pause before level 1 never waits

    @property
    def awaiting_ack(self) -> bool:
        """The minimum pause is over and the next level is waiting for acknowledge()."""
        return self.state is State.INTERMISSION and self._holding() and self._intermission_left <= 0 and not self._acked

    def acknowledge(self) -> None:
        """The player has seen the level-clear plate. The next level starts once its minimum pause is over."""
        self._acked = True

    def _start_level(self, level: int) -> None:
        self._acked = False
        self.level = level
        self.state = State.PLAYING
        count = min(C.WORLDS_BASE + C.WORLDS_PER_LEVEL * (level - 1), C.MAX_WORLDS_ON_SCREEN)
        carrier = self._offer_chip(level)
        for i in range(count):
            self.worlds.append(self._spawn_world(chip_carrier=carrier and i == 0))
        self.events.append(f"level:{level}")

    def _offer_chip(self, level: int) -> bool:
        """Is there a chip carrier this level?

        From CHIP_LEVEL on it comes back every level until the chip is actually
        collected, so a carrier that reaches the ship (or a chip that expires)
        never costs the player the chip for the whole run. With CHIP_REPEAT a
        further chip is offered every CHIP_LEVEL levels after each collection.
        """
        if level < C.CHIP_LEVEL:
            return False
        if not self.chip_collected:
            return True
        return C.CHIP_REPEAT and (level - C.CHIP_LEVEL) % C.CHIP_LEVEL == 0

    def _base_hp(self) -> int:
        return C.WORLD_HP_BASE + C.WORLD_HP_PER_LEVEL * (self.level - 1)

    def _spawn_world(self, chip_carrier: bool) -> World:
        speed = (1.0 / C.APPROACH_SECONDS) * (1 + C.APPROACH_SPEEDUP * (self.level - 1))
        drift = C.DRIFT_DEG_PER_S * (1 + 0.15 * (self.level - 1))
        return World(
            az=wrap_az(self.view_az + self.rng.uniform(-C.SPAWN_SPREAD, C.SPAWN_SPREAD)),
            el=self.rng.uniform(-C.EL_LIMIT, C.EL_LIMIT),
            az_v=self.rng.uniform(-drift, drift),
            el_v=self.rng.uniform(-drift / 2, drift / 2),
            progress=C.SPAWN_APPROACH + self.rng.uniform(0.0, 0.1),
            speed=speed * self.rng.uniform(0.8, 1.2),
            hp=self._base_hp() + (C.CARRIER_EXTRA_HP if chip_carrier else 0),
            kind=self.rng.choice(C.WORLD_KINDS) if not chip_carrier else "chip",
            chip_carrier=chip_carrier,
        )

    def _move_worlds(self, dt: float) -> None:
        for w in list(self.worlds):
            w.progress += w.speed * dt
            w.az = wrap_az(w.az + w.az_v * dt)
            w.el += w.el_v * dt
            if abs(w.el) > C.EL_LIMIT:
                w.el = _clamp(w.el, -C.EL_LIMIT, C.EL_LIMIT)
                w.el_v = -w.el_v
            if w.progress >= 1.0:
                # A Rogue World reaching the ship destroys it: the game is over, at once.
                self.worlds.remove(w)
                self.state = State.LOST
                self.lost_cause = "hull"
                self.impact = (w.az, w.el, w.radius)
                self.events.append("hull_destroyed")
                return

    def _update_crystals(self, dt: float, aim_az: float, aim_el: float) -> None:
        for c in list(self.crystals):
            c.age += dt
            if c.age >= c.lifetime:
                self.crystals.remove(c)
                self.events.append("crystal_lost")
                continue
            on_target = angular_distance(aim_az, aim_el, c.az, c.el) <= C.CRYSTAL_RADIUS
            c.on_target = on_target
            if on_target:
                c.dwell += dt
            elif c.is_chip:  # a slip costs time, never the whole hold
                c.dwell = max(0.0, c.dwell - dt * C.CHIP_HOLD_DRAIN * C.CHIP_HOLD_S)
            else:
                c.dwell = max(0.0, c.dwell - dt * C.HARVEST_DECAY)
            if c.dwell >= c.needed:
                self.crystals.remove(c)
                self._harvest(c)

    def _harvest(self, crystal: Crystal) -> None:
        if crystal.is_chip:
            self.chip_at = (crystal.az, crystal.el)
            self.chip_collected = True
            self.capacity *= C.CHIP_CAPACITY_FACTOR
            self.charge = self.capacity
            self.score += C.SCORE_CHIP
            self.events.append("chip")
        else:
            self.charge = min(self.capacity, self.charge + C.CRYSTAL_VALUE)
            self.score += C.SCORE_CRYSTAL
            self.events.append("crystal")

    def _check_end_conditions(self) -> None:
        if self.state is not State.PLAYING:
            return
        if self.charge < C.SHOT_COST and not self.crystals:
            self.state = State.LOST
            self.lost_cause = "battery"
            self.events.append("lost")
        elif not self.worlds and not self.crystals:
            self.state = State.INTERMISSION
            self._intermission_left = C.INTERMISSION_S
            self.events.append("level_clear")


def _age(shot: Shot, dt: float) -> bool:
    shot.age += dt
    return shot.age < C.SHOT_FX_S


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def crosshair_bearing(
    head_az: float, head_el: float, offset_x_deg: float, offset_y_deg: float
) -> Tuple[float, float]:
    """World bearing under the crosshair: head direction plus the crosshair's offset."""
    return wrap_az(head_az + offset_x_deg), _clamp(head_el + offset_y_deg, -90.0, 90.0)
