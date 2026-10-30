"""The battery meter and the level number, as pure geometry. hudlayer.py paints what this returns.

Twenty slanted cells in two rows of ten at the top-left of the screen, lit in reading order, with
"LVL 3" to their right. That is all the HUD says: no percentage, no label and no level name (the
name is announced by a banner when the level starts). The cells are the reading.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

Color = Tuple[int, int, int]
CYAN: Color = (0, 229, 255)
GOLD: Color = (255, 200, 0)
PINK: Color = (255, 60, 220)
WHITE: Color = (255, 255, 255)

COLS, ROWS = 10, 2
CELLS = COLS * ROWS
X0, Y0 = 26, 8  # right at the top of the screen
PITCH, W, H, SKEW, ROW_GAP = 12.5, 9.5, 24, 4, 6
DIVIDER_X = 164
TEXT_X = 176
CAPTION_SIZE = 26  # the only text beside the meter, so it can be large
SPACING = 2.0  # letter spacing in px
PILL = (26, 68, 76, 28)  # x, y, w, h: the gold badge under the grid, with the OD mark and "x2"
PILL_LOGO = (28, 70, 24)  # x, y, size of the OD mark inside it
PILL_TEXT = (76, 89, 17)  # x, baseline, size of the "x2" beside it
LOW = 0.25  # under this the battery is low


@dataclass(frozen=True)
class Cell:
    points: Tuple[Tuple[float, float], ...]
    lit: bool
    last: bool  # the last lit cell, which pulses


@dataclass(frozen=True)
class Text:
    text: str
    x: float
    y: float  # baseline
    size: int
    color: Color
    spacing: float = SPACING


@dataclass(frozen=True)
class HudModel:
    cells: List[Cell]
    tone: Color
    low: bool
    divider: Tuple[float, float, float]  # x, y1, y2
    caption: Text  # "LVL 3"
    pill: Optional[Tuple[float, float, float, float]]

    @property
    def texts(self) -> List[Text]:
        return [self.caption]


def badge_scale(u: float) -> float:
    """Size of the badge while it pops in (u from 0 to 1): grows, overshoots a little, settles at 1."""
    u = max(0.0, min(1.0, u))
    return 0.4 + 0.6 * (1 - (1 - u) ** 3) + 0.25 * math.sin(u * math.pi)


def lit_cells(p: float) -> int:
    """How many of the twenty cells are lit. Any charge at all lights at least one."""
    if p <= 0:
        return 0
    return min(CELLS, max(1, math.ceil(p * CELLS)))


def tone(p: float, chip: bool) -> Color:
    if p < LOW:
        return PINK  # a warning is a warning, even with the chip
    return GOLD if chip else CYAN


def build(p: float, chip: bool, level: int) -> HudModel:
    lit = lit_cells(p)
    cells = []
    for i in range(CELLS):
        x = X0 + (i % COLS) * PITCH
        y = Y0 + (i // COLS) * (H + ROW_GAP)
        pts = ((x + SKEW, y), (x + SKEW + W, y), (x + W, y + H), (x, y + H))
        cells.append(Cell(pts, i < lit, lit > 0 and i == lit - 1))
    top, bottom = Y0, Y0 + 2 * H + ROW_GAP
    t = tone(p, chip)
    # baseline so that the capitals sit in the vertical middle of the two rows of cells
    baseline = (top + bottom) / 2 + CAPTION_SIZE * 0.35
    return HudModel(
        cells=cells,
        tone=t,
        low=p < LOW,
        divider=(DIVIDER_X, top, bottom),
        caption=Text(f"LVL {level}", TEXT_X, baseline, CAPTION_SIZE, t),
        pill=PILL if chip else None,
    )
