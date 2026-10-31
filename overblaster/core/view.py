"""Where your head points, and how the sky maps onto the screen (port of web src/core/view.ts).

The world is a sphere around you (azimuth 0..360, elevation up and down); the screen is a 30 degree window of it.
"""

import math
from typing import Optional

from .constants import CENTER, EL_LIMIT, PPD, TURN_RATE, W
from .input_ import InputFrame
from .math_ import azd, clamp, wrap360
from .types_ import Projected

FOV_DEG = 30


class View:
    def __init__(self) -> None:
        self.az = 0.0
        self.el = 0.0
        self._r_az = 0.0  # turn rate, smoothed
        self._r_el = 0.0
        # device-orientation tracking
        self._a0: Optional[float] = None
        self._az0 = 0.0
        self._fy = 1
        self._fp = 1
        self.sensor_live = False  # True while a device sensor is steering the view

    def reset(self) -> None:
        self.az = 0.0
        self.el = 0.0
        self._r_az = 0.0
        self._r_el = 0.0
        self.recenter()

    def recenter(self) -> None:
        self._a0 = None

    def flip_yaw(self) -> None:
        self._fy = -self._fy
        self.recenter()

    def flip_pitch(self) -> None:
        self._fp = -self._fp

    def update(self, dt: float, input: InputFrame) -> None:
        h = input.head
        if h is not None:  # a head tracker reports where the head points: use it as is
            self.sensor_live = False
            self.az = wrap360(h.az)
            self.el = clamp(h.el, -EL_LIMIT, EL_LIMIT)
            self._r_az = self._r_el = 0.0
            return
        o = input.orientation
        self.sensor_live = o is not None
        if o is not None:
            if self._a0 is None:
                self._a0 = o.alpha
                self._az0 = self.az
            diff = ((o.alpha - self._a0 + 540) % 360) - 180
            t_az = (self._az0 - diff * self._fy + 720) % 360
            t_el = clamp((o.beta - 90) * self._fp, -EL_LIMIT, EL_LIMIT)
            k = min(1, dt * 14)
            self.az = (self.az + azd(t_az, self.az) * k + 360) % 360
            self.el += (t_el - self.el) * k
            self._r_az = self._r_el = 0.0
            return
        # touch-drag look
        if input.look.dx or input.look.dy:
            k = (FOV_DEG / W) * 1.3
            self.az = wrap360(self.az - input.look.dx * k)
            self.el = clamp(self.el + input.look.dy * k, -EL_LIMIT, EL_LIMIT)
        tx = input.turn.x * TURN_RATE
        ty = input.turn.y * TURN_RATE * 0.8
        k = min(1, dt * 9)
        self._r_az += (tx - self._r_az) * k
        self._r_el += (ty - self._r_el) * k
        self.az = (self.az + self._r_az * dt + 360) % 360
        self.el = clamp(self.el + self._r_el * dt, -EL_LIMIT, EL_LIMIT)

    def proj(self, az: float, el: float) -> Projected:
        """Where a point of the sky lands on the 640 px screen. dx, dy are the offsets from the centre."""
        dx = azd(az, self.az) * math.cos((el * math.pi) / 180) * PPD
        dy = -(el - self.el) * PPD
        return Projected(CENTER + dx, CENTER + dy, dx, dy)


def on_screen(p, margin: float, ox: float = 0) -> bool:
    """Is a screen point inside the visible area? `ox` is the extra width on each side when the screen is wider than the 640 px square."""
    return -ox - margin < p.x < W + ox + margin and -margin < p.y < W + margin
