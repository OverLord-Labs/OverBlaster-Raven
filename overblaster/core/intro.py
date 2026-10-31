"""The story intro, as data (port of web src/core/intro.ts): narrator lines, event times, sound cues.

Seen from the stranded mothership's bridge. Times are seconds from the start of the intro.
"""

from dataclasses import dataclass
from typing import List, Tuple

from .events import Event

# (voice clip, caption (| = line break), clip length s, gap after s, lead-in s)
NAR: List[Tuple[str, str, float, float, float]] = [
    ("m_n1", "The Meridian was carrying|the lights home.", 3.0, 0.7, 0.4),
    ("m_n2", "Then the jump|became unstable.", 2.58, 0.5, 0.4),
    ("m_n3", "It tore away|one battery wing.", 2.38, 0.5, 0.4),
    ("m_n4", "Then the other.", 1.25, 2.6, 0.4),
    ("m_e3", "The ship finished the run alone, in an empty|patch of space. No wings. No power.", 6.48, 1.7, 0.6),
    ("m_e4", "It can't jump again. Someone has to go back|for them. The long way. Through the belt.", 5.96, 1.7, 0.6),
    ("m_e5", "Find both wings.|Bring them back.", 2.65, 1.7, 0.6),
]


@dataclass
class Part:
    key: str
    text: str
    t0: float
    D: float
    v0: float
    v1: float


PARTS: List[Part] = []
STORY_END = 0.0
for _n in NAR:
    _D = _n[2] + _n[3]
    PARTS.append(Part(_n[0], _n[1], STORY_END, _D, STORY_END + _n[4], STORY_END + _n[4] + _n[2]))
    STORY_END += _D

# The story's length less 10.6 s, so the countdown starts as the last line ends.
SH = 23.1
COUNT_AT = 10.6 + SH
COUNT_STEP = 1.0
JUMP_AT = COUNT_AT + 3 * COUNT_STEP
# The first level takes over at GAME_AT, under the last of the intro.
GAME_AT = 14.5 + SH
INTRO_END = 17.6 + SH

# The wings go as the narrator says so.
EV = {"w1": PARTS[2].v0 + 0.6, "w2": PARTS[3].v0 + 0.3, "drop": PARTS[3].v1 + 1.1}

# Captions: (shown from, shown until, text).
INTRO_LINES: List[Tuple[float, float, str]] = [(p.v0, p.v1 + 0.2, p.text) for p in PARTS]


@dataclass
class Cue:
    at: float
    events: List[Event]


def _say(k: str) -> Event:
    return {"type": "say", "keys": [k]}


INTRO_CUES: List[Cue] = [
    *[Cue(p.v0, [_say(p.key)]) for p in PARTS],
    Cue(0, [{"type": "drone", "on": True}]),
    Cue(PARTS[1].t0, [{"type": "alarm", "on": True}]),
    Cue(EV["w1"], [{"type": "sfx", "name": "hit", "gain": 1}, {"type": "sfx", "name": "explode", "gain": 0.7}]),
    Cue(EV["w2"], [{"type": "sfx", "name": "explode", "gain": 1}, {"type": "sfx", "name": "battery_dead", "gain": 0.8}]),
    Cue(EV["drop"], [{"type": "alarm", "on": False}, {"type": "sfx", "name": "hull_death", "gain": 0.7}]),
    Cue(COUNT_AT - 7.4, [{"type": "sfx", "name": "warp_charge", "gain": 0.9, "tag": "riser"}]),
    Cue(COUNT_AT - 0.08, [_say("m_three")]),
    Cue(COUNT_AT + COUNT_STEP - 0.08, [_say("m_two")]),
    Cue(COUNT_AT + 2 * COUNT_STEP - 0.08, [_say("m_one")]),
    Cue(JUMP_AT - 0.08, [_say("m_go")]),
    Cue(COUNT_AT + 3, [{"type": "drone", "on": False}]),
    Cue(13.9 + SH, [{"type": "sfx", "name": "explode", "gain": 0.9}, {"type": "sfx", "name": "level_start", "gain": 0.8}]),
]
# When the drive's riser starts. A story skip that lands after this starts it part-way in.
RISER_AT = COUNT_AT - 7.4
# Where "skip story" lands: just before the countdown.
SKIP_STORY_TO = COUNT_AT - 1.2

# The widescreen side bars part as gameplay starts: from BARS_OPEN_AT, over BARS_OPEN_S seconds.
BARS_OPEN_AT = 14.2 + SH
BARS_OPEN_S = 1.4
