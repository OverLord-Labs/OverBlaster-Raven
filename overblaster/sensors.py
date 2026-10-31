"""Input filters: head tracking, gaze confidence and the "Pew" voice trigger.

Pure Python so they can be unit-tested without the Raven framework. The code that
actually reads the glasses' peripherals lives in inputs.py.
"""

import math
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Sequence, Tuple

from . import config as C
from .core.math_ import clamp as _clamp, wrap360 as wrap_az


def as_vec3(value) -> Optional[Tuple[float, float, float]]:
    """Normalize an IMU value to (x, y, z). Accepts a dict with x/y/z or any 3-sequence.

    The Raven docs don't say which one get_reading() returns, so accept both.
    """
    if value is None:
        return None
    try:
        if isinstance(value, dict):
            return float(value["x"]), float(value["y"]), float(value["z"])
        x, y, z = value[:3]
        return float(x), float(y), float(z)
    except (KeyError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class ImuProfile:
    """Which IMU axes mean what. The glasses and a Mac laptop disagree, so it is a value."""

    gyro_in_degrees: bool
    gyro_yaw_axis: int
    gyro_yaw_sign: float
    gyro_pitch_axis: int
    gyro_pitch_sign: float
    accel_up_axis: int
    accel_fwd_axis: int
    accel_pitch_sign: float
    accel_up_sign: float = 1.0  # -1 when the sensor's up axis points down (gravity reads negative)
    gyro_pitch: bool = True  # False: take pitch from gravity alone (slow, steady laptop motion)

    @classmethod
    def device(cls) -> "ImuProfile":
        """The glasses (assumptions, see config.py). Read at call time so tests can retune it."""
        return cls(
            C.GYRO_IN_DEGREES, C.GYRO_YAW_AXIS, C.GYRO_YAW_SIGN, C.GYRO_PITCH_AXIS,
            C.GYRO_PITCH_SIGN, C.ACCEL_UP_AXIS, C.ACCEL_FWD_AXIS, C.ACCEL_PITCH_SIGN,
        )

    @classmethod
    def mac(cls, yaw_flip: float = 1.0, pitch_flip: float = 1.0) -> "ImuProfile":
        """A Mac laptop lying flat: z is vertical and reads about -1 g, so up is -z. Rotation
        about that axis is the yaw, and the forward tilt comes from gravity only."""
        return cls(
            True, 2, C.MAC_YAW_SIGN * yaw_flip, 0, 1.0,
            2, C.MAC_ACCEL_FWD_AXIS, C.MAC_PITCH_SIGN * pitch_flip,
            accel_up_sign=-1.0, gyro_pitch=False,
        )


class PeakHold:
    """Remembers the loudest level seen since the last take().

    The microphone reports every 20 ms but the game looks every 67 ms, so a short "Pew"
    can peak and fade between two looks. Feed every report in; take() once per tick.
    """

    def __init__(self) -> None:
        self._peak = 0.0
        self.latest = 0.0

    def update(self, level: float) -> None:
        self.latest = level
        self._peak = max(self._peak, level)

    def take(self) -> float:
        peak, self._peak = max(self._peak, self.latest), 0.0
        return peak


def _deadband(rate: float) -> float:
    """Turn rates inside the dead band read as still; real turns pass through unchanged."""
    return rate if abs(rate) > C.GYRO_DEADBAND_DPS else 0.0


class _OneEuro:
    """Adaptive low-pass: heavy smoothing while the value is nearly still, light while it moves fast.

    That is what a view wants: a motionless head shouldn't shimmer, and a quick turn shouldn't lag.
    """

    def __init__(self, wrap: bool = False) -> None:
        self.wrap = wrap
        self.reset()

    def reset(self) -> None:
        self._out: Optional[float] = None
        self._speed = 0.0

    def _delta(self, a: float, b: float) -> float:
        d = a - b
        return (d + 180.0) % 360.0 - 180.0 if self.wrap else d

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        return 1.0 / (1.0 + 1.0 / (2.0 * math.pi * cutoff) / dt)

    def __call__(self, value: float, dt: float) -> float:
        if self._out is None:
            self._out = value
            return value
        speed = abs(self._delta(value, self._out)) / dt
        self._speed += self._alpha(1.0, dt) * (speed - self._speed)
        cutoff = C.VIEW_MIN_CUTOFF_HZ + C.VIEW_BETA * self._speed
        self._out += self._alpha(cutoff, dt) * self._delta(value, self._out)
        if self.wrap:
            self._out %= 360.0
        return self._out


class HeadTracker:
    """Turns raw IMU readings into head yaw / pitch in degrees.

    Pitch is a complementary filter (integrated gyro, corrected by the gravity
    direction). Yaw is the integrated gyro only, so it drifts slowly; recenter()
    zeroes it. A magnetometer correction is intentionally not implemented yet.
    """

    def __init__(self, sim: Optional[bool] = None, profile: Optional[ImuProfile] = None) -> None:
        self.sim = C.SIM_FORCE if sim is None else sim
        self.profile = profile  # None means ImuProfile.device(), read fresh each update
        self.yaw = 0.0
        self.pitch = 0.0
        self._has_pitch_ref = False
        self._accel_avg: Optional[Tuple[float, float, float]] = None
        self._view_yaw = _OneEuro(wrap=True)
        self._view_pitch = _OneEuro()

    def recenter(self) -> None:
        self.yaw = 0.0
        self._view_yaw.reset()

    def update(self, reading: Optional[dict], dt: float) -> Tuple[float, float]:
        """Feed one IMU reading taken dt seconds after the previous one."""
        if not reading or dt <= 0:
            return self.yaw, self.pitch

        accel = as_vec3(reading.get("accelerometer"))
        gyro = as_vec3(reading.get("gyroscope"))
        if not self.sim:
            accel = self._smooth_accel(accel)
            self._raw_update(accel, gyro, dt)
            return self._view_yaw(self.yaw, dt), self._view_pitch(self.pitch, dt)
        return self._raw_update(accel, gyro, dt)

    def _smooth_accel(self, accel):
        """A running average of the accelerometer, so its noise doesn't tilt the view."""
        if not accel:
            return accel
        if self._accel_avg is None:
            self._accel_avg = accel
        else:
            k = C.ACCEL_SMOOTH
            self._accel_avg = tuple(a + k * (n - a) for a, n in zip(self._accel_avg, accel))
        return self._accel_avg

    def _raw_update(self, accel, gyro, dt: float) -> Tuple[float, float]:
        """The unfiltered head angles: integrated gyro and the gravity direction."""
        if self.sim:
            # Arrow keys only fake accelerometer x / y (left = +x, up = +y), so
            # use them as a joystick: left turns the view left, up looks up.
            if accel:
                self.yaw = wrap_az(self.yaw - accel[0] * C.SIM_STEER_DEG_PER_S * dt)
                self.pitch = _clamp(
                    self.pitch + accel[1] * C.SIM_STEER_DEG_PER_S * dt, -C.PITCH_LIMIT, C.PITCH_LIMIT
                )
            return self.yaw, self.pitch

        p = self.profile or ImuProfile.device()
        gyro_yaw = gyro_pitch = 0.0
        if gyro:
            scale = 1.0 if p.gyro_in_degrees else math.degrees(1.0)
            gyro_yaw = _deadband(gyro[p.gyro_yaw_axis] * p.gyro_yaw_sign * scale)
            gyro_pitch = _deadband(gyro[p.gyro_pitch_axis] * p.gyro_pitch_sign * scale) if p.gyro_pitch else 0.0

        self.yaw = wrap_az(self.yaw + gyro_yaw * dt)

        predicted = self.pitch + gyro_pitch * dt
        accel_pitch = self._accel_pitch(accel, p)
        if accel_pitch is None:
            self.pitch = predicted
        elif not p.gyro_pitch:
            self.pitch = accel_pitch  # gravity alone, no gyro blend
        elif not self._has_pitch_ref:
            self.pitch, self._has_pitch_ref = accel_pitch, True  # snap on the first sample
        else:
            self.pitch = C.COMPLEMENTARY_ALPHA * predicted + (1 - C.COMPLEMENTARY_ALPHA) * accel_pitch
        self.pitch = _clamp(self.pitch, -C.PITCH_LIMIT, C.PITCH_LIMIT)
        return self.yaw, self.pitch

    @staticmethod
    def _accel_pitch(accel: Optional[Sequence[float]], p: "ImuProfile") -> Optional[float]:
        if not accel:
            return None
        up, fwd = accel[p.accel_up_axis] * p.accel_up_sign, accel[p.accel_fwd_axis]
        if abs(up) < 1e-6 and abs(fwd) < 1e-6:
            return None  # free fall or a bad sample
        return math.degrees(math.atan2(fwd, up)) * p.accel_pitch_sign


class GazeAim:
    """Decides whether eye gaze is trustworthy enough to move the crosshair.

    The eye tracker reports no confidence, so use a proxy: the last few samples
    must all exist, sit inside the display, and be tightly clustered. Anything
    else falls back to the screen center (head-only aiming).
    """

    def __init__(self, width: float = C.DISPLAY_PX, height: float = C.DISPLAY_PX, trust_all: bool = False) -> None:
        # trust_all is for the simulator's mouse: a mouse has no noise to filter out, and
        # moving it would otherwise count as "jitter" and snap the crosshair back to center.
        self.trust_all = trust_all
        self.width, self.height = width, height
        self._samples: Deque[Tuple[float, float]] = deque(maxlen=C.GAZE_WINDOW)
        self._smoothed: Optional[Tuple[float, float]] = None
        self.confident = False

    @property
    def center(self) -> Tuple[float, float]:
        return self.width / 2.0, self.height / 2.0

    def update(self, gaze: Optional[Tuple[float, float]]) -> Tuple[float, float]:
        """Return the crosshair position in display pixels."""
        if gaze is None or not self._inside(gaze):
            self._samples.clear()
            self._smoothed = None
            self.confident = False
            return self.center

        self._samples.append((float(gaze[0]), float(gaze[1])))
        xs = [s[0] for s in self._samples]
        ys = [s[1] for s in self._samples]
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        self.confident = self.trust_all or (
            len(self._samples) >= C.GAZE_MIN_SAMPLES and spread <= C.GAZE_MAX_SPREAD_PX
        )

        if not self.confident:
            self._smoothed = None
            return self.center

        if self.trust_all:  # a mouse is exact: no averaging, no smoothing lag
            self._smoothed = (xs[-1], ys[-1])
            return self._smoothed
        target = (sum(xs) / len(xs), sum(ys) / len(ys))
        if self._smoothed is None:
            self._smoothed = target
        else:
            a = C.GAZE_SMOOTHING
            self._smoothed = (
                self._smoothed[0] + a * (target[0] - self._smoothed[0]),
                self._smoothed[1] + a * (target[1] - self._smoothed[1]),
            )
        return self._smoothed

    def _inside(self, gaze: Tuple[float, float]) -> bool:
        return 0 <= gaze[0] <= self.width and 0 <= gaze[1] <= self.height


def pixels_to_degrees(
    x: float, y: float, width: float, height: float, fov_deg: float = C.FOV_DEG
) -> Tuple[float, float]:
    """Crosshair offset from display center in degrees (right and up are positive)."""
    ppd = width / fov_deg
    return (x - width / 2.0) / ppd, (height / 2.0 - y) / ppd


class VoiceTrigger:
    """Turns sound into a held trigger. What was said doesn't matter, only how loud it is.

    A sound louder than `hi` pulls the trigger, and it stays pulled (the game then fires at its own
    fire rate) for as long as the level stays above `lo`: "pew" is a short burst, "pewwwww" is
    continuous fire. Once the sound drops below `lo` the trigger is released, and a fresh sound
    above `hi` is needed to pull it again.
    """

    def __init__(self, hi: float = C.VOICE_HI, lo: float = C.VOICE_LO) -> None:
        self.hi, self.lo = hi, lo
        self._held = False

    def update(self, level: Optional[float]) -> bool:
        """True if the trigger is held on this look."""
        if level is None:  # no microphone: never fire, and let go
            self._held = False
            return False
        if self._held:
            self._held = level >= self.lo
        else:
            self._held = level >= self.hi
        return self._held
