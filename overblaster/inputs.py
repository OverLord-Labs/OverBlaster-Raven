"""Reads the glasses' peripherals. The only module that touches raven_framework.peripherals.

Each read is wrapped so a missing or misbehaving sensor degrades to "no data"
instead of crashing the game.

Facts from the framework source (v1.0.6) that this module relies on:
  * IMU.get_reading() -> {"accelerometer": {"x","y","z"}, "gyroscope": ..., "magnetometer": ...}
    Off-device it is simulated from the arrow keys (gyroscope is always zero).
  * EyeControl.get_gaze_position() -> (x, y) | None. Off-device it is the mouse
    cursor. On the glasses the framework's Sensorlib currently returns None.
  * Microphone has NO get_level(). Off-device the Qt path updates `mic.level`
    (peak, 0-1) while recording. On the glasses `mic.level` is never updated and
    the level comes from `mic.sensorlib_client.get_microphone_level()` (RMS, 0-1).
"""

import time
from typing import Callable, Dict, Optional, Tuple

from . import config as C
from .sensors import PeakHold


def on_device() -> bool:
    """True on a real Raven device (uses the same check the framework uses)."""
    try:
        from raven_framework.helpers.utils_light import uses_ravend_ipc

        return bool(uses_ravend_ipc())
    except Exception:  # noqa: BLE001 - no framework (tests) means not on a device
        return False


class RavenInputs:
    def __init__(self, imu=None, eye=None, mic=None) -> None:
        """The three peripherals are created here unless fakes are passed in (tests)."""
        self._warned: Dict[str, bool] = {}
        self._imu = imu or self._make("imu", "raven_framework.peripherals.imu", "IMU")
        self._eye = eye or self._make("eye", "raven_framework.peripherals.eye_control", "EyeControl")
        self._mic = mic or self._make("mic", "raven_framework.peripherals.microphone", "Microphone")
        self._recording = False
        self._recording_since = 0.0
        self._peak = PeakHold()
        signal = getattr(self._mic, "levelChanged", None)
        if signal is not None:  # off-device the Qt mic reports every 20 ms; keep every report
            signal.connect(self._peak.update)
        self.mic_status = "not started"

    def _make(self, name: str, module: str, cls: str):
        try:
            return getattr(__import__(module, fromlist=[cls]), cls)()
        except Exception as exc:  # noqa: BLE001 - any failure just disables this sensor
            self._warn(name, f"unavailable ({exc})")
            return None

    def _warn(self, name: str, message: str) -> None:
        if not self._warned.get(name):
            self._warned[name] = True
            print(f"[overblaster] {name}: {message}")

    def _safe(self, name: str, fn: Callable):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            self._warn(name, f"read failed ({exc})")
            return None

    def imu(self) -> Optional[dict]:
        return self._safe("imu", self._imu.get_reading) if self._imu else None

    def gaze(self) -> Optional[Tuple[float, float]]:
        return self._safe("eye", self._eye.get_gaze_position) if self._eye else None

    def mic_level(self) -> Optional[float]:
        """Loudest level (0.0 - 1.0) since the last call, or None. Starts the microphone on first use.

        The game looks every 67 ms but the microphone reports every 20 ms, so a short "Pew" could
        peak and fade between two looks; holding the peak means it can't be missed.
        """
        if not self._mic:
            self.mic_status = "no microphone"
            return None
        now = time.monotonic()
        device_client = getattr(self._mic, "sensorlib_client", None)
        if self._recording and not device_client and now - self._recording_since > C.MIC_RESTART_S:
            self._stop_mic()  # off-device the Microphone buffers all audio; restart to cap memory
        if not self._recording:
            self._safe("mic", self._mic.start_recording)
            self._recording, self._recording_since = True, now
        if device_client:  # on the glasses the level is polled (RMS), not pushed
            level = self._safe("mic", device_client.get_microphone_level)
            if level is None:
                self.mic_status = "read failed"
                return None
            self._peak.update(float(level))
        self.mic_status = "listening" if getattr(self._mic, "recording", True) else "not recording"
        return self._peak.take()

    def _stop_mic(self) -> None:
        if self._mic and self._recording:
            self._safe("mic", self._mic.stop_recording)  # returns WAV bytes we don't need
            self._recording = False

    def close(self) -> None:
        self._stop_mic()
