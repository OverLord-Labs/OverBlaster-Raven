"""The Overlord BMS power-up, as pure geometry: the hold ring, the arrow back, the sparks and the callout.

The chip in the game is the Overlord BMS, a battery management chip. Finding it is the award, so
this module describes everything that makes finding it unmissable:

  * while you hold your aim on it, a gold ring fills; if your aim slips it turns pink and an arrow
    beside the crosshair points back at the chip;
  * when it is collected a ring bursts and ten sparks fly into the battery gauge;
  * a callout pops out of the gauge naming the Overlord BMS and what it does, then folds into an
    Overlord "OD" medallion that stays beside the gauge, with a ×2 badge under the gauge.

bmslayer.py paints it. Nothing here imports Qt.
"""

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import config as C
from . import hud
from .screens import Text, clamp01, cut_plate, ease_out, fit

Point = Tuple[float, float]

# ----- hold ring, label and arrow -----
RING_R = 58
RING_W = 6
HOLD_LABEL = "HOLD YOUR AIM ON THE CHIP"
LABEL_DY = 112  # baseline of the label below the chip's centre
ARROW_GAP = 52  # px from the crosshair to the arrow
BLINK_HZ = 1.6


@dataclass(frozen=True)
class Ring:
    cx: float
    cy: float
    progress: float
    color: hud.Color


@dataclass(frozen=True)
class Arrow:
    x: float
    y: float
    angle: float  # degrees, 0 = pointing right
    alpha: float


def hold_ring(cx: float, cy: float, progress: float, on_target: bool) -> Ring:
    color = hud.PINK if (progress > 0 and not on_target) else hud.GOLD
    return Ring(cx, cy, clamp01(progress), color)


def guide_arrow(cross: Point, chip: Point, on_target: bool, now: float = 0.0) -> Optional[Arrow]:
    """A pink arrow next to the crosshair pointing at the chip, whenever your aim is off it."""
    if on_target:
        return None
    ang = math.atan2(chip[1] - cross[1], chip[0] - cross[0])
    alpha = 0.65 + 0.35 * math.sin(now * 2 * math.pi * BLINK_HZ)
    return Arrow(cross[0] + math.cos(ang) * ARROW_GAP, cross[1] + math.sin(ang) * ARROW_GAP, math.degrees(ang), alpha)


LABEL_HALF = 205  # about half the label's width, so it is kept inside the screen


def label_pos(cx: float, cy: float, size: float = 640) -> Point:
    """Centre and baseline of the label under the chip, kept on screen when the chip is near an edge."""
    x = max(16 + LABEL_HALF, min(size - 16 - LABEL_HALF, cx))
    return x, cy + LABEL_DY


# ----- the burst and the sparks (t is seconds since the chip was collected) -----
SPARK_COUNT = 10
SPARK_DELAY = 0.1  # between one spark and the next
SPARK_FLIGHT = 1.0
SPARK_START = 0.1
SPARK_END = SPARK_START + SPARK_DELAY * (SPARK_COUNT - 1) + SPARK_FLIGHT + 0.2
BURST_S = 0.9


@dataclass(frozen=True)
class Spark:
    x: float
    y: float
    alpha: float


def spark_target(i: int) -> Point:
    """Each spark lands on a cell of the gauge's top row."""
    return hud.X0 + 4 + i * hud.PITCH, hud.Y0 + hud.H / 2


def burst(t: float) -> Tuple[float, float]:
    """(radius, alpha) of the ring that bursts out of the chip."""
    u = clamp01(t / BURST_S)
    return 20 + 180 * ease_out(u), 1.0 - u


def sparks(t: float, origin: Point) -> List[Spark]:
    out = []
    for i in range(SPARK_COUNT):
        ang = i / SPARK_COUNT * 2 * math.pi
        k = clamp01(t / 0.3)  # first they spread around the chip
        bx, by = origin[0] + math.cos(ang) * 60 * k, origin[1] + math.sin(ang) * 60 * k
        start = SPARK_START + i * SPARK_DELAY
        u = ease_out(clamp01((t - start) / SPARK_FLIGHT))
        tx, ty = spark_target(i)
        alpha = clamp01(t / 0.1) * (1.0 - clamp01((t - (start + SPARK_FLIGHT)) / 0.2))
        out.append(Spark(bx + (tx - bx) * u, by + (ty - by) * u, alpha))
    return out


# ----- the callout, the medallion and the badge -----
BUBBLE_IN = 1.8
BUBBLE_FOLD = 7.0  # five seconds on screen
BUBBLE_IN_S, BUBBLE_FOLD_S = 0.5, 0.8
MEDAL = (298.0, 36.0)  # the OD medallion beside the gauge
MEDAL_SIZE = 52
BADGE_AT = BUBBLE_IN + 1.2
SETTLE_S = BUBBLE_FOLD + BUBBLE_FOLD_S + 0.2
PLATE = (20, 108, 480, 244)
PLATE_CUT = 14
LOGO = (74.0, 164.0, 70.0)  # centre x, y and size of the OD mark in the bubble
Measure = Callable[[str, float, str, float], float]


@dataclass(frozen=True)
class CalloutModel:
    bubble_scale: float
    plate: Tuple[Point, ...]
    pointer: Tuple[Point, ...]
    texts: List[Text]
    pivot: Point  # the bubble grows from, and folds into, this point
    logo: Tuple[float, float, float]
    medal_alpha: float
    medal_scale_x: float  # 1 = face on, near 0 = edge on while it spins in
    halo_r: float
    halo_alpha: float
    badge_u: float  # 0 = not there, 1 = there; the badge pops on the way


def callout(t: float, measure: Optional[Measure] = None) -> CalloutModel:
    grow = ease_out(clamp01((t - BUBBLE_IN) / BUBBLE_IN_S))
    fold = ease_out(clamp01((t - BUBBLE_FOLD) / BUBBLE_FOLD_S))
    scale = grow * (1.0 - fold)

    spin_u = clamp01((t - BUBBLE_IN) / 1.0)
    sx = math.cos(spin_u * math.pi * 4) * (1 - spin_u) + spin_u
    medal_alpha = clamp01((t - BUBBLE_IN) / 0.2)
    halo_on = clamp01((t - BUBBLE_IN - 1.0) / 0.3)
    halo_phase = (t * 1.1) % 1.0
    tip = (MEDAL[0], 88.0)
    pointer = ((MEDAL[0] - 20, PLATE[1]), tip, (MEDAL[0] + 20, PLATE[1]))
    title = "OVERLORD BMS FOUND!"
    size = fit(title, 24, 16, PLATE[2] - 14 - 126, measure, "black", 2) if measure else 24
    texts = [
        Text(title, 126, 148, size, hud.GOLD, "black", 2),
        Text("BATTERY MANAGEMENT, BUILT", 126, 178, 16, hud.CYAN, "bold", 2),
        Text("FROM THE SILICON UP.", 126, 200, 16, hud.CYAN, "bold", 2),
        Text("NOW YOU GET 2× THE SHOTS.", 126, 232, 17, hud.WHITE, "bold", 1),
    ]
    return CalloutModel(
        bubble_scale=scale,
        plate=cut_plate(*PLATE, PLATE_CUT),
        pointer=pointer,
        texts=texts,
        pivot=(MEDAL[0], 84.0),
        logo=LOGO,
        medal_alpha=medal_alpha,
        medal_scale_x=max(0.05, abs(sx)),
        halo_r=MEDAL_SIZE / 2 + 2 + 10 * halo_phase,
        halo_alpha=0.7 * (1.0 - halo_phase) * halo_on,
        badge_u=clamp01((t - BADGE_AT) / 0.5),
    )
