"""Every tunable number in the game, in one place (port of web src/core/constants.ts)."""

from typing import Dict, List, Tuple

RGB = Tuple[int, int, int]

# The logical screen: 640 x 640 px across a 30 degree field of view.
W = 640
FOV = 30
PPD = W / FOV
CENTER = W / 2
# The widest screen the game adapts to (width / height).
MAX_ASPECT = 2.4

CYAN: RGB = (0, 229, 255)
GOLD: RGB = (255, 200, 0)
PINK: RGB = (255, 60, 220)
WHITE: RGB = (255, 255, 255)
RED: RGB = (255, 40, 40)
GREY: RGB = (141, 162, 180)

# ---- the player's head and the screen ----
TURN_RATE = 52  # degrees a second at full key deflection
EL_LIMIT = 38  # how far up or down you can look

# ---- battery ----
LOW = 0.25  # fraction of capacity that counts as low
CELLS = 20
SHOT_COST = 1
SHOT_COOLDOWN = 0.1
CRYSTAL_VALUE = 3
START_CHARGE = 100
CHIP_CAPACITY = 200

# ---- aiming and harvesting ----
HARVEST = 0.3  # seconds of aim on a crystal
CRYSTAL_RADIUS = 3.0  # degrees
HIT_FORGIVENESS = 1.5  # a shot lands within 1.5 x a rock's radius
SPAWN_SPREAD = 45
POINTER_RING = 250  # px: how far from the centre an off-screen arrow sits
CRITICAL = 0.72  # a rock past 72% of its way to you is critically close
BLINK_FROM = 0.8  # a rock this close starts blinking red itself

# ---- the Overlord BMS chip ----
CHIP_LEVEL = 3
CHIP_HOLD = 2.4
CHIP_DRAIN = 0.2

# ---- the Meridian's battery wings ----
WING_LEVELS: List[int] = [14, 28]
WING_HOLD = 2.4
WING_RADIUS = 4.2
WING_COUNT = 2

# ---- bad gauges: slightly broken chips ----
GAUGE_LEVEL = 7
GAUGE_HOLD = 2.0
FIRST_HOLD = 4.0
GAUGE_RADIUS = 3.5
GAUGE_LIFE = 14
RESTORE_ODDS = 0.15
RESTORE_AFTER = 7
# Red ones cut capacity by 70%, blue ones by 80%; either one takes the 2x away.
BAD: Dict[str, dict] = {
    "red": {"cap": 30, "col": (255, 50, 40), "cut": "70%"},
    "blue": {"cap": 20, "col": (50, 130, 255), "cut": "80%"},
}

# ---- difficulty ----
# How much of your 10 shots a second a level asks for, at level 4 and at level 42.
LOADS: Tuple[float, float] = (0.3, 0.55)

# ---- presentation timing (shared by core and renderer) ----
BUBBLE_IN = 1.8
BUBBLE_FOLD = 7.0
BADGE_AT = 3.0
SETTLE = 8.0
ACK_MIN = 2.5  # seconds before the sector-cleared plate accepts a click
COUNT_S = 1.3
SPLASH_END = 6.8

LEVELS: List[str] = [
    "THE FAR SIDE", "ASTEROID BELT", "NEBULA GATE", "VOID STORM", "EVENT HORIZON", "DEEP SPACE",
    "SHORT CIRCUIT", "COLD SOLDER", "BROWNOUT", "GRAVEL RUN", "RIFT LINE", "THE SCRAPYARD", "DARK CURRENT", "SHATTER FIELD", "STATIC SEA", "HOLLOW MOON", "BLACK ICE", "RED SHIFT", "THE WHIRL", "ION CANYON", "BURNOUT",
    "LAST LIGHT", "CRATER STORM", "DRIFT WALL", "PULSE GATE", "IRON GRAVE", "THE SIEVE", "FALLOUT", "GHOST FLEET", "THUNDER BELT", "SINGULARITY", "BREAKER", "COLD FRONT", "WIDOWMAKER", "DEEP FREEZE", "TITAN FIELD", "REDLINE", "THE MAW", "ZERO HOUR", "NO RETURN", "OVERLORD GATE", "THE OVERLORD CORE",
]
MAX_LEVEL = len(LEVELS)
