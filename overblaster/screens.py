"""The title screen, the between-levels plate and the level-start splash, as pure geometry.

screenlayers.py paints what these models describe. Nothing here imports Qt, so the layout, the
timings and the "keep clear of the crosshair" rules are all unit-tested. `width(text, size, weight,
spacing)` is a text-measuring callback, so wordmarks and names can be fitted to the real font.

Everything is in display pixels of the 640 x 640 game area, except the splash, which is centred on
(0, 0) because it is anchored to a bearing in the sky and moves with the head.
"""

import math
from dataclasses import dataclass
from typing import Callable, List, Tuple

from . import config as C
from . import hud

Point = Tuple[float, float]
Measure = Callable[[str, float, str, float], float]
SIZE = C.DISPLAY_PX
BLACK = (0, 0, 0)


@dataclass(frozen=True)
class Text:
    text: str
    x: float
    y: float  # baseline
    size: float
    color: hud.Color = hud.WHITE
    weight: str = "medium"
    spacing: float = 0.0
    anchor: str = "start"  # "start" or "middle"
    alpha: float = 1.0


@dataclass(frozen=True)
class Cell:
    points: Tuple[Point, ...]
    alpha: float
    lit: bool = True
    row: str = ""


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def ease_out(u: float) -> float:
    return 1.0 - (1.0 - clamp01(u)) ** 3


def slanted(x: float, y: float, w: float, h: float, skew: float) -> Tuple[Point, ...]:
    return ((x + skew, y), (x + skew + w, y), (x + w, y + h), (x, y + h))


def cut_plate(x1: float, y1: float, x2: float, y2: float, cut: float) -> Tuple[Point, ...]:
    """A rectangle with its top-left and bottom-right corners clipped (the bounding box is unchanged)."""
    return ((x1 + cut, y1), (x2, y1), (x2, y2 - cut), (x2 - cut, y2), (x1, y2), (x1, y1 + cut))


def fit(text: str, size: float, low: float, limit: float, width: Measure, weight: str, spacing: float) -> float:
    """The largest size from `size` down to `low` at which the text is no wider than `limit`."""
    while size > low and width(text, size, weight, spacing) > limit:
        size -= 2
    return max(size, low)


# ============================== title ==============================
BOOT_PERIOD = 2.6
CELL_LOW, CELL_HIGH = 0.06, 0.95
TITLE_CELLS = 20
TITLE_TOP_Y, TITLE_BOTTOM_Y = 126, 282
LAUNCH = (190, 488, 260, 68)  # x, y, w, h of the clipped-corner button plate
LAUNCH_CUT = 14
HINTS = ("TURN YOUR HEAD TO AIM", "SAY “PEW” TO FIRE", "HOLD YOUR AIM ON CRYSTALS TO HARVEST THEM")


def boot_alpha(t: float, delay: float) -> float:
    """One cell's pulse: dark, ramps up, held lit, back to dark, forever. It waits `delay` s before its first ramp."""
    if t < delay:
        return CELL_LOW
    ph = ((t - delay) % BOOT_PERIOD) / BOOT_PERIOD
    if ph < 0.28:
        return CELL_LOW + (CELL_HIGH - CELL_LOW) * ph / 0.28
    if ph < 0.62:
        return CELL_HIGH
    return CELL_HIGH - (CELL_HIGH - CELL_LOW) * (ph - 0.62) / 0.38


@dataclass(frozen=True)
class TitleModel:
    cells: List[Cell]
    wordmark: Text
    texts: List[Text]  # every word on the screen, wordmark included
    launch: Tuple[float, float, float, float]


def title_model(t: float, width: Measure) -> TitleModel:
    cells = []
    for i in range(TITLE_CELLS):
        x = 88 + i * 23
        cells.append(Cell(slanted(x, TITLE_TOP_Y, 18, 16, 8), boot_alpha(t, i * 0.07), row="top"))
        cells.append(Cell(slanted(x, TITLE_BOTTOM_Y, 18, 16, 8), boot_alpha(t, (TITLE_CELLS - 1 - i) * 0.07), row="bottom"))
    size = fit("OVERBLASTER", 66, 40, 560, width, "black", 5)
    word = Text("OVERBLASTER", 320, 238, size, hud.WHITE, "black", 5, "middle")
    texts = [word, Text("AN OVERLORD LABS GAME", 320, 334, 16, hud.GOLD, "medium", 7, "middle")]
    for i, h in enumerate(HINTS):
        texts.append(Text(h, 320, 382 + i * 32, 20, hud.WHITE, "medium", 1, "middle"))
    texts.append(Text("LOOK AT IT FOR 1.5 SECONDS", 320, 590, 16, hud.CYAN, "medium", 4, "middle"))
    return TitleModel(cells, word, texts, LAUNCH)


# ============================== between levels ==============================
COUNT_S = 1.3
PLATE = (90, 166, 550, 476)
PLATE_CUT = 22
LEFT_X, NEXT_X = 124, 372
BAR_N = hud.CELLS
ACK_GATE_S = 1.0  # after the score finishes counting, a further second in which sound is ignored
ACK_MIN_S = COUNT_S + 0.2 + ACK_GATE_S  # = 2.5 s: the plate can't be dismissed before this
PROMPT = "SAY “PEW” TO CONTINUE"


def count_up(t: float, score: int) -> int:
    """The score shown `t` s after the plate appears: it races up and settles exactly on the score."""
    if t >= COUNT_S:
        return score
    return int(round(score * ease_out(t / COUNT_S)))


@dataclass(frozen=True)
class PauseModel:
    plate: Tuple[Point, ...]
    tone: hud.Color
    cells: List[Cell]
    score: Text
    next_name_text: str
    next_alpha: float
    next_dy: float
    texts: List[Text]  # every word, score and next-level column included


def pause_model(level: int, score: int, lit: int, tone: hud.Color, t: float, width: Measure) -> PauseModel:
    nxt = level + 1
    next_alpha = clamp01((t - 0.5) / 0.5)
    dy = 12.0 * (1.0 - ease_out((t - 0.5) / 0.5))
    score_text = Text(f"{count_up(t, score):,}", LEFT_X, 352, 34, hud.WHITE, "black")
    name = C.level_name(nxt)
    texts = [
        Text(f"LVL {level}", LEFT_X, 212, 22, tone, "bold", 2),
        Text("SECTOR CLEARED", LEFT_X, 258, 36, hud.WHITE, "black", 2),
        Text("SCORE", LEFT_X, 316, 16, hud.CYAN, "medium", 4),
        score_text,
        Text("NEXT", NEXT_X, 316, 16, hud.CYAN, "medium", 4, alpha=next_alpha),
        Text(f"LVL {nxt}", NEXT_X, 348 + dy, 30, hud.GOLD, "black", 2, alpha=next_alpha),
        Text(name, NEXT_X, 372 + dy, 16, hud.WHITE, "medium", 3, alpha=next_alpha),
        Text(PROMPT, 320, 452, 18, hud.GOLD, "bold", 4, "middle", clamp01((t - COUNT_S - 0.2) / 0.3)),
    ]
    cells = []
    for i in range(BAR_N):
        on = i < lit
        a = CELL_HIGH * clamp01((t - (0.3 + i * 0.05)) / 0.35) if on else 0.10
        cells.append(Cell(slanted(LEFT_X + i * 15.5, 396, 11, 16, 5), a, on, "bar"))
    return PauseModel(cut_plate(*PLATE, PLATE_CUT), tone, cells, score_text, name, next_alpha, dy, texts)


# ============================== level start ==============================
SPLASH_FADE_IN = 0.3
SPLASH_HOLD_TO = 6.0
SPLASH_END = 6.8
SPLASH_MAX = 0.55
SPLASH_EL_OFFSET = 6.3  # degrees above the line of sight, so the crosshair never strikes through it
SPLASH_ANCHOR = (SIZE / 2.0, SIZE / 2.0 - SPLASH_EL_OFFSET * C.DISPLAY_PX / C.FOV_DEG)


def splash_alpha(t: float) -> float:
    """Fade in, hold, fade out: a see-through backdrop for a couple of seconds, then gone."""
    if t <= 0 or t >= SPLASH_END:
        return 0.0
    if t < SPLASH_FADE_IN:
        return SPLASH_MAX * t / SPLASH_FADE_IN
    if t <= SPLASH_HOLD_TO:
        return SPLASH_MAX
    return SPLASH_MAX * (SPLASH_END - t) / (SPLASH_END - SPLASH_HOLD_TO)


@dataclass(frozen=True)
class SplashModel:
    plate: Tuple[Point, ...]
    block: Tuple[Point, ...]
    caption: Text
    number: Text
    name: Text


def splash_model(level: int, name: str, width: Measure) -> SplashModel:
    block = ((-242, -46), (-124, -46), (-138, 46), (-256, 46))
    size = fit(name, 54, 30, 340, width, "bold", 4)
    return SplashModel(
        plate=cut_plate(-280, -62, 280, 62, 22),
        block=block,
        caption=Text("LVL", -190, -27, 16, BLACK, "bold", 3, "middle"),
        number=Text(str(level), -190, 34, 62, BLACK, "black", 0, "middle"),
        name=Text(name, -96, size * 0.36, size, hud.WHITE, "bold", 4),
    )
