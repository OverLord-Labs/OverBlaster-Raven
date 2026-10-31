"""Hit boxes of the on-screen buttons, in logical px (port of web src/core/layout.ts)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float


LAUNCH = Box(190, 488, 260, 68)
RETRY = Box(190, 330, 260, 64)
TOTITLE = Box(190, 420, 260, 64)
SKIPS = Box(452, 6, 176, 30)


def in_box(b: Box, x: float, y: float) -> bool:
    return b.x <= x <= b.x + b.w and b.y <= y <= b.y + b.h
