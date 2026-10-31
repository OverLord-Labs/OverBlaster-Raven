"""Gaze-dwell buttons, with no widgets: rest the gaze (the cursor, in the simulator) on a plate for DWELL_S to press it.

The glasses have no click. The scene draws each plate itself (core/layout.py has the boxes); this keeps the
time the gaze has spent on each one, and scenelayer paints the fill that grows across a plate while it dwells,
like the framework's own Button. A press goes to the core as a click in the middle of the box. Pure Python.
"""

from typing import Dict, Optional, Tuple

from .core.layout import Box, in_box

DRAIN = 2.0  # the fill drains this much faster than it fills once the gaze leaves


class Dwell:
    def __init__(self, dwell_s: float) -> None:
        self.dwell_s = dwell_s
        self.progress: Dict[str, float] = {}  # box name -> 0..1, only while above 0

    def update(self, dt: float, gaze: Optional[Tuple[float, float]], boxes: Dict[str, Box]) -> Optional[str]:
        """Advance by dt with the gaze at `gaze` (core px) or None. Returns the name of a box that was just pressed."""
        for name in [n for n in self.progress if n not in boxes]:
            del self.progress[name]
        for name, box in boxes.items():
            on = gaze is not None and in_box(box, gaze[0], gaze[1])
            p = self.progress.get(name, 0.0)
            p = p + dt / self.dwell_s if on else max(0.0, p - DRAIN * dt / self.dwell_s)
            if p >= 1.0:
                self.progress.clear()
                return name
            if p > 0:
                self.progress[name] = p
            else:
                self.progress.pop(name, None)
        return None
