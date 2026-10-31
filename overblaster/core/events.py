"""Everything the core wants the outside world to do or know (port of web src/core/events.ts).

Events are dicts with a "type" key. The core appends them during update(); the host drains them with
Game.drain(). Sound events:  sfx {name, gain?, offset?, tag?}  stopRiser  zap {kind}  say {keys}
music {name|None}  alarm {on}  drone {on}.  App events:  launch  phase {phase}  levelStart {level}
levelClear {level, score}  chipFound  wingFound {wings}  gameOver {won, cause, score, level}.
"""

from typing import Any, Dict

Event = Dict[str, Any]

SOUND_TYPES = frozenset({"sfx", "stopRiser", "zap", "say", "music", "alarm", "drone"})
PHASES = ("title", "intro", "play", "over")


def is_sound(e: Event) -> bool:
    return e["type"] in SOUND_TYPES
