"""The pure game: no screen, audio, Qt or Raven imports. A faithful Python port of the web game's src/core.

Import from here to run the game headless (tests, bots) or to drive it from the glasses.
"""

from .bot import SimResult, bot_target, simulate_level
from .constants import *  # noqa: F401,F403
from .events import Event, PHASES, SOUND_TYPES, is_sound
from .game import Game, rock_radius
from .input_ import COMMANDS, Head, InputFrame, Look, Orientation, Pointer, Press, Turn, empty_input
from .intro import (
    BARS_OPEN_AT, BARS_OPEN_S, COUNT_AT, COUNT_STEP, EV, GAME_AT, INTRO_CUES, INTRO_END, INTRO_LINES, JUMP_AT, PARTS, RISER_AT, SH,
    SKIP_STORY_TO, STORY_END, Cue, Part,
)
from .layout import LAUNCH, RETRY, SKIPS, TOTITLE, Box, in_box
from .levels import PlanRock, crystals_for, gauge_chase, level_name, level_note, level_plan, level_say
from .math_ import TAU, azd, clamp, ease, lerp, ramp, wrap360
from .rng import Rng, srng
from .types_ import *  # noqa: F401,F403
from .view import View, on_screen
