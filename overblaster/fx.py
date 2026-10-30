"""Shot and explosion animation, as pure geometry. No Qt: fxlayer.py draws what this returns.

Each function takes an age in seconds and returns the shapes to draw at that moment (screen pixels,
colours as (r, g, b), alpha 0..1). An age past the effect's length returns nothing, so the overlay
has nothing to repaint and costs nothing between shots.

Black is transparent on the glasses' additive display, so every effect is bright colour on nothing:
a laser from the ship's nose to the target, a muzzle flash, and a burst where it lands.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple

Color = Tuple[int, int, int]

MAGENTA: Color = (255, 60, 220)  # the old game's bullets were magenta
WHITE: Color = (255, 255, 255)
CYAN: Color = (0, 229, 255)
GOLD: Color = (255, 200, 0)
ORANGE: Color = (255, 120, 30)
RED: Color = (255, 40, 40)

BEAM_S = 0.20  # three game ticks at 15 Hz, so the beam reads as a beam and not a flicker
MUZZLE_S = 0.16
MISS_S = 0.18
HIT_S = 0.32
KILL_S = 0.50
DEATH_S = 1.10  # how long the hull-destroyed explosion plays before the game-over screen


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    color: Color
    alpha: float


@dataclass(frozen=True)
class Circle:
    x: float
    y: float
    radius: float
    color: Color
    alpha: float
    width: float = 0.0  # 0 = filled disc, otherwise the ring's stroke width


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    color: Color
    alpha: float


Shape = object  # Line | Circle | Rect


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _sparks(cx: float, cy: float, count: int, r_from: float, r_to: float, width: float, colors, alpha: float, turn: float = 0.0) -> List[Line]:
    """Short rays leaving (cx, cy) between two radii."""
    out = []
    for k in range(count):
        a = turn + k * 2 * math.pi / count
        dx, dy = math.cos(a), math.sin(a)
        out.append(Line(cx + dx * r_from, cy + dy * r_from, cx + dx * r_to, cy + dy * r_to, width, colors[k % len(colors)], alpha))
    return out


def shot_shapes(kind: str, age: float, muzzle: Tuple[float, float], target: Tuple[float, float], size_px: float = 0.0) -> List[Shape]:
    """One shot at `age` seconds after firing.

    kind: "miss", "hit" (the world survived) or "kill" (it was destroyed).
    muzzle: where the beam leaves the ship; target: where it lands; size_px: the world's radius.
    """
    shapes: List[Shape] = []
    mx, my = muzzle
    tx, ty = target

    # The laser: three layers (wide faint glow, brighter middle, white-hot core) that thin and fade.
    if age < BEAM_S:
        t = age / BEAM_S
        fade = 1.0 - t
        shapes += [
            Line(mx, my, tx, ty, _lerp(18, 6, t), MAGENTA, 0.20 * fade),
            Line(mx, my, tx, ty, _lerp(9, 3, t), MAGENTA, 0.55 * fade),
            Line(mx, my, tx, ty, _lerp(4, 1.5, t), WHITE, fade),
        ]

    # The muzzle flash at the ship's nose.
    if age < MUZZLE_S:
        t = age / MUZZLE_S
        shapes += [
            Circle(mx, my, _lerp(16, 3, t), WHITE, 1.0 - t),
            Circle(mx, my, _lerp(8, 30, t), MAGENTA, 0.9 * (1.0 - t), width=3),
        ]

    size = max(size_px, 20.0)
    if kind == "miss":
        if age < MISS_S:
            t = age / MISS_S
            shapes += [
                Circle(tx, ty, _lerp(4, 22, t), CYAN, 1.0 - t, width=2),
                Circle(tx, ty, 3, WHITE, 1.0 - t),
            ]
    elif kind == "hit":
        if age < HIT_S:
            t = age / HIT_S
            if t < 0.35:  # a white flash over the world it struck
                shapes.append(Circle(tx, ty, size * 0.55, WHITE, 0.8 * (1.0 - t / 0.35)))
            ring = _lerp(size * 0.5, size * 1.3, t)
            shapes.append(Circle(tx, ty, ring, GOLD, 1.0 - t, width=3))
            shapes += _sparks(tx, ty, 6, ring * 0.8, ring * 0.8 + size * 0.4 * (1.0 - t), 3, (WHITE, GOLD), 1.0 - t)
    elif kind == "kill":
        if age < KILL_S:
            t = age / KILL_S
            if t < 0.4:  # the world blows up: a white-then-gold flash...
                flash = t / 0.4
                shapes.append(Circle(tx, ty, size * _lerp(0.8, 1.1, flash), WHITE if flash < 0.5 else GOLD, 0.9 * (1.0 - flash)))
            shapes.append(Circle(tx, ty, _lerp(size * 0.4, size * 2.0, t), ORANGE, 1.0 - t, width=5))  # ...a shockwave...
            if t > 0.15:
                t2 = _clamp01((t - 0.15) / 0.85)
                shapes.append(Circle(tx, ty, _lerp(size * 0.3, size * 1.5, t2), GOLD, 1.0 - t2, width=3))
            shapes += _sparks(  # ...and debris
                tx, ty, 12, size * (0.5 + 1.2 * t), size * (0.8 + 1.6 * t), 4, (WHITE, GOLD, ORANGE), 1.0 - t, turn=math.pi / 12
            )
    return shapes


def death_shapes(age: float, center: Tuple[float, float], size_px: float, width: float, height: float) -> List[Shape]:
    """The explosion when a Rogue World hits the ship: a red flash around the whole view plus a
    big blast where it struck. `center` is clamped on screen, since the world may be off to one side."""
    if age >= DEATH_S:
        return []
    t = age / DEATH_S
    fade = 1.0 - t
    cx = max(60.0, min(width - 60.0, center[0]))
    cy = max(60.0, min(height - 60.0, center[1]))
    size = max(size_px, 50.0)

    edge = 40.0
    alpha = 0.8 * fade
    shapes: List[Shape] = [
        Rect(0, 0, width, edge, RED, alpha),
        Rect(0, height - edge, width, edge, RED, alpha),
        Rect(0, edge, edge, height - 2 * edge, RED, alpha),
        Rect(width - edge, edge, edge, height - 2 * edge, RED, alpha),
    ]
    if t < 0.5:
        shapes.append(Circle(cx, cy, size * _lerp(0.8, 2.4, t / 0.5), WHITE, (1.0 - t / 0.5) ** 2))
    shapes += [
        Circle(cx, cy, _lerp(size * 0.5, size * 3.2, t), RED, fade, width=8),
        Circle(cx, cy, _lerp(size * 0.4, size * 2.4, t), ORANGE, fade, width=6),
        Circle(cx, cy, _lerp(size * 0.3, size * 1.6, t), GOLD, fade, width=4),
    ]
    shapes += _sparks(cx, cy, 16, size * (0.6 + 1.6 * t), size * (1.0 + 2.4 * t), 5, (WHITE, GOLD, ORANGE), fade)
    return shapes
