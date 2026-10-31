"""The shapes of the game's state (port of web src/core/types.ts). Renderers read these; only the core writes them."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

RGB = Tuple[int, int, int]


@dataclass
class Arrive:
    """A rock that flies in from the centre (the first level's opening rocks)."""

    t0: float
    delay: float
    dur: float


@dataclass
class Rock:
    az: float
    el: float
    azv: float
    elv: float
    p: float  # 0 when it appears, 1 when it reaches you
    spawn_at: float
    hold: bool  # waiting to be released (the BMS carrier in wave one)
    speed: float
    hp: float
    max: float
    carrier: bool  # the gold rock that drops the BMS chip
    rot: float
    spin: float
    dead: bool = False
    hurt: float = 0.0
    arrive: Optional[Arrive] = None
    eject: Optional[str] = None  # "red" | "blue": spits out a bad gauge when destroyed
    warned: bool = False


@dataclass
class Crystal:
    az: float
    el: float
    age: float = 0.0
    dwell: float = 0.0


@dataclass
class Pickup:
    """The BMS chip and the battery wings: collected by holding your aim on them."""

    az: float
    el: float
    age: float = 0.0
    dwell: float = 0.0
    on_target: bool = False


@dataclass
class Gauge:
    az: float
    el: float
    color: str
    age: float
    dwell: float
    vaz: float
    vel: float
    seed: int
    on: bool
    first: bool
    hold: float


@dataclass
class Fx:
    """A visual effect: k is "burst" | "spark" | "glitch" | "ping". r and col apply to burst / glitch."""

    k: str
    az: float
    el: float
    t: float
    r: float = 0.0
    col: Optional[RGB] = None


@dataclass
class Bolt:
    t: float
    tx: float
    ty: float
    side: int


@dataclass
class Floater:
    az: float
    el: float
    s: str
    t: float


@dataclass
class Callout:
    a: str
    b: str
    col: RGB
    t0: float
    dur: float


@dataclass
class BadState:
    color: str
    cap: float
    col: RGB
    cut: str


@dataclass
class HitAt:
    az: float
    el: float


@dataclass
class Point:
    x: float
    y: float


@dataclass
class Wave2:
    count: int
    gap: float
    hp: float
    approach: float


@dataclass
class PendingSay:
    at: float
    keys: List[str]


@dataclass
class Run:
    """One game, from level 1 to the end. mode is "playing" | "intermission" | "lost"."""

    level: int = 0
    score: int = 0
    charge: float = 100.0
    capacity: float = 100.0
    chip_collected: bool = False
    worlds: List[Rock] = field(default_factory=list)
    crystals: List[Crystal] = field(default_factory=list)
    chip: Optional[Pickup] = None
    wing: Optional[Pickup] = None
    gauges: List[Gauge] = field(default_factory=list)
    fx: List[Fx] = field(default_factory=list)
    floaters: List[Floater] = field(default_factory=list)
    bolts: List[Bolt] = field(default_factory=list)
    t: float = 0.0  # seconds into the level
    mode: str = "playing"
    cool: float = 0.0
    flash: float = 0.0
    last_hit: float = -9.0
    hit_at: Optional[HitAt] = None
    side: int = -1
    flash_side: int = -1
    splash_t0: float = 0.0
    splash_az: float = 0.0
    splash_el: float = 0.0
    plate_at: float = 0.0
    plate_voiced: int = 0
    inter_t: float = 0.0
    award_t0: Optional[float] = None
    award_origin: Optional[Point] = None
    award_kind: Optional[str] = None  # "found" | "restore"
    low_fired: bool = False
    tutorial: bool = True
    tut_t0: float = 0.0
    shake: float = 0.0
    lost_t: float = 0.0
    lost_cause: Optional[str] = None  # "hull" | "battery" | "win"
    chip_seen: bool = False
    tick_k: int = 0
    bad: Optional[BadState] = None
    bad_count: int = 0
    kills_bad: int = 0
    gauge_seen: bool = False
    bad_t0: float = -9.0
    callout: Optional[Callout] = None
    wings: int = 0
    wing_spawned: bool = False
    stingy: bool = False
    wave2: Optional[Wave2] = None
    pending_say: Optional[PendingSay] = None
    last_warn: float = -9.0
    warns: int = 0


@dataclass
class IntroState:
    t: float = 0.0
    fired: Set[int] = field(default_factory=set)
    game: bool = False  # True once the first level is running underneath the end of the intro


@dataclass
class Projected:
    x: float
    y: float
    dx: float
    dy: float
