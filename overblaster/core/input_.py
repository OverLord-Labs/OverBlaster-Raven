"""What the game needs from the outside world, one frame at a time (port of web src/core/input.ts).

The core never touches a device, a clock or a speaker: a host (the glasses, a test, a bot) fills in an
InputFrame and calls Game.update(dt, input).
"""

from dataclasses import dataclass, field
from typing import List, Optional

# commands: "launch" "skipStory" "skipIntro" "recenter" "flipYaw" "flipPitch"
COMMANDS = ("launch", "skipStory", "skipIntro", "recenter", "flipYaw", "flipPitch")


@dataclass
class Turn:
    x: float = 0.0
    y: float = 0.0


@dataclass
class Orientation:
    alpha: float
    beta: float


@dataclass
class Head:
    az: float
    el: float


@dataclass
class Pointer:
    x: float = 320.0
    y: float = 320.0
    mouse: bool = False
    inside: bool = False


@dataclass
class Look:
    dx: float = 0.0
    dy: float = 0.0


@dataclass
class Press:
    x: float
    y: float


@dataclass
class InputFrame:
    turn: Turn = field(default_factory=Turn)  # digital head turn, each axis -1..1. x is right, y is up
    orientation: Optional[Orientation] = None  # live device orientation in degrees
    head: Optional[Head] = None  # absolute head orientation from a head tracker: sets the view directly
    fire: bool = False
    pointer: Pointer = field(default_factory=Pointer)  # logical screen px (0..640)
    look: Look = field(default_factory=Look)  # touch-drag look delta since the last frame
    presses: List[Press] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)


def empty_input() -> InputFrame:
    return InputFrame()
