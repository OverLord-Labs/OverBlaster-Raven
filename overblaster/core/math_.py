"""Small numeric helpers (port of web src/core/math.ts). Pure and dependency free."""

import math

TAU = math.pi * 2


def clamp(v: float, a: float, b: float) -> float:
    return max(a, min(b, v))


def ramp(t: float, a: float, b: float) -> float:
    """0 at or before `a`, 1 at or after `b`, linear between."""
    return clamp((t - a) / (b - a), 0, 1)


def ease(u: float) -> float:
    """Ease-out cubic on 0..1."""
    return 1 - math.pow(1 - u, 3)


def lerp(a: float, b: float, u: float) -> float:
    return a + (b - a) * u


def azd(a: float, b: float) -> float:
    """Signed shortest difference between two azimuths, in degrees (-180..180)."""
    return ((((a - b + 540) % 360) + 360) % 360) - 180


def wrap360(a: float) -> float:
    """Wrap an azimuth into 0..360."""
    return ((a % 360) + 360) % 360


def js_round(x: float) -> int:
    """JavaScript's Math.round: halves round up (Python's round() rounds them to even)."""
    return math.floor(x + 0.5)


def js_mod(a: float, b: float) -> float:
    """JavaScript's % on numbers: the result has the sign of the dividend (Python's % takes the divisor's)."""
    return math.fmod(a, b)
