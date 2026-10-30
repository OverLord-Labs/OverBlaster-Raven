"""Plays OverBlaster on the REAL raven_framework widgets, offscreen, with a scripted player.

Run by test_real_framework.py in its own process (the fake-widget tests replace
raven_framework in sys.modules, so the two can't share one). Exit code 77 means the
framework isn't installed. Any other non-zero exit is a failure.
"""

import math
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OVERBLASTER_MUTE", "1")  # tests never play sound
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication, QWidget
    from raven_framework.components.button import Button
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)

from overblaster import config as C  # noqa: E402
from overblaster.app import OverBlasterApp  # noqa: E402
import overblaster.app as app_mod  # noqa: E402
from overblaster.game import az_delta  # noqa: E402


class Inputs:
    """Fake glasses: the head turns at yaw / pitch deg/s and gravity follows the true head pitch."""

    mic = yaw = pitch = 0.0
    head_pitch = 0.0  # true pitch in degrees, integrated by tick()

    def imu(self):
        g = [0.0, 0.0, 0.0]
        g[C.GYRO_YAW_AXIS], g[C.GYRO_PITCH_AXIS] = self.yaw, self.pitch
        # Same shape as the framework's own IMU simulator (dicts, gravity on z), but tilted
        # with the head like a real accelerometer; a constant "level" reading would
        # make the tracker correctly drag every upward aim back to horizontal.
        a = [0.0, 0.0, 0.0]
        rad = math.radians(self.head_pitch * C.ACCEL_PITCH_SIGN)
        a[C.ACCEL_UP_AXIS], a[C.ACCEL_FWD_AXIS] = 9.8 * math.cos(rad), 9.8 * math.sin(rad)
        return {
            "accelerometer": {"x": a[0], "y": a[1], "z": a[2]},
            "gyroscope": {"x": g[0], "y": g[1], "z": g[2]},
            "magnetometer": {"x": 0, "y": 0, "z": 0},
        }

    def gaze(self):
        return None

    def mic_level(self):
        return self.mic

    def close(self):
        pass


clock = {"t": 1000.0}
app_mod.time.monotonic = lambda: clock["t"]
inp = Inputs()
app = OverBlasterApp(inputs=inp, simulated=False)
app.show()
for _ in range(30):  # the framework fades the app in over 750 ms
    qapp.processEvents()
    time.sleep(0.03)

launch = next(w for w in app.app.findChildren(Button) if w.text == "LAUNCH")
launch.clicked.emit()
qapp.processEvents()


def tick():
    dt = C.TICK_MS / 1000.0
    clock["t"] += dt
    inp.head_pitch += inp.pitch * C.GYRO_PITCH_SIGN * dt  # the head really moved
    app._tick()
    qapp.processEvents()


g = app.game
g.rng = random.Random(int(os.environ.get("OVERBLASTER_SEED", "7")))  # reproducible, before level 1 spawns
tick()
baseline = len(app.app.findChildren(QWidget))
hidden_running = 0
ticks = 0
while g.state.value != "lost" and g.level <= 4 and ticks < 6000:
    if g.crystals:
        tgt, fire = (g.crystals[0].az, g.crystals[0].el), False
    elif g.worlds:
        w = max(g.worlds, key=lambda w: w.progress)
        tgt, fire = (w.az, w.el), True
    else:
        tgt, fire = (app.head.yaw, app.head.pitch), g.awaiting_ack and ticks % 6 < 3  # SECTOR CLEARED waits for a fresh "Pew"
    dy, dp = az_delta(tgt[0], app.head.yaw), tgt[1] - app.head.pitch
    inp.yaw, inp.pitch = max(-120, min(120, dy * 5)), max(-120, min(120, dp * 5))
    inp.mic = 0.9 if fire and abs(dy) < 1 and abs(dp) < 1 else 0.0  # hold the sound while on target
    tick()
    ticks += 1
    idle = app._free + [s for s in app._bound.values() if not s.visible]
    hidden_running += sum(1 for s in idle if s.widget.movie and s.widget.movie.state().name == "Running")

failures = []
if g.state.value == "lost":
    failures.append(f"the scripted perfect player lost at level {g.level}")
if g.level < 5:
    failures.append(f"only reached level {g.level} in {ticks} ticks")
if not g.chip_collected or g.capacity != C.BATTERY_START * C.CHIP_CAPACITY_FACTOR:
    failures.append(f"chip not collected / capacity {g.capacity}")
now = len(app.app.findChildren(QWidget))
if now != baseline:
    failures.append(f"widget count changed during play: {baseline} -> {now}")
if hidden_running:
    failures.append(f"{hidden_running} hidden GIF-ticks were still animating")

print(f"level {g.level}, score {g.score}, chip {g.chip_collected}, widgets {baseline}->{now}, ticks {ticks}")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
