"""What the voice says. Pure data, shared by the game (which plays the clips) and tools/make_voice.py
(which renders them). Each line says what a popup says, in a short, cool way.

Level announcements are put together from three clips ("Level", the number, the name) so the voice
can announce any level without a clip for each one.
"""

from typing import Dict, List, Optional

from . import config as C

LINES: Dict[str, str] = {
    "title": "OverBlaster. Look at launch, pilot.",
    "level_clear": "Sector cleared.",
    "continue": "Say pew to continue.",
    "chip_seen": "Overlord B M S detected. Hold your aim on the chip.",
    "chip_found": "Overlord B M S found. Two times the shots.",
    "hull_destroyed": "Hull destroyed.",
    "battery_dead": "Battery depleted.",
    "battery_low": "Battery low.",
    "next_level": "Next level.",
    "level_word": "Level.",
}

NUMBERS: List[str] = [
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "twenty one", "twenty two", "twenty three", "twenty four", "twenty five",
    "twenty six", "twenty seven", "twenty eight", "twenty nine", "thirty",
]
MAX_LEVEL_VOICED = len(NUMBERS)


def number_key(n: int) -> str:
    return f"num_{n:02d}"


def name_key(level: int) -> str:
    names = C.LEVEL_NAMES
    return f"name_{max(0, min(level, len(names)) - 1)}"


def all_clips() -> Dict[str, str]:
    """Every clip the game may play: key -> the text to render."""
    clips = dict(LINES)
    for i, word in enumerate(NUMBERS, start=1):
        clips[number_key(i)] = word.capitalize() + "."
    for i, name in enumerate(C.LEVEL_NAMES):
        clips[f"name_{i}"] = name.title() + "."
    return clips


def level_intro(level: int) -> List[str]:
    """The clips to play, in order, to announce `level`."""
    if level < 1 or level > MAX_LEVEL_VOICED:
        return ["next_level"]
    return ["level_word", number_key(level), name_key(level)]


def spoken(key: str) -> Optional[str]:
    return all_clips().get(key)
