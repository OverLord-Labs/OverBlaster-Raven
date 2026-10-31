"""Plays OverBlaster on the REAL raven_framework widgets, offscreen, with a scripted player: title, dwell LAUNCH, the
story intro, then levels 1 to 4 (the BMS chip is level 3) with the head turning at a realistic rate.

Run by test_real_framework.py in its own process (the fake-widget tests replace
raven_framework in sys.modules, so the two can't share one). Exit code 77 means the
framework isn't installed. Any other non-zero exit is a failure.
"""

import math
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OVERBLASTER_MUTE", "1")  # tests never play sound
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication, QWidget
    import raven_framework  # noqa: F401
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)

from overblaster import config as C  # noqa: E402
from overblaster.app import OverBlasterApp  # noqa: E402
import overblaster.app as app_mod  # noqa: E402
from overblaster.core import LAUNCH, SKIPS, CHIP_CAPACITY, HIT_FORGIVENESS, azd, bot_target, rock_radius  # noqa: E402


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
app = OverBlasterApp(inputs=inp, simulated=False, mac_imu=False, seed=int(os.environ.get("OVERBLASTER_SEED", "7")))
app.show()
for _ in range(30):  # the framework fades the app in over 750 ms
    qapp.processEvents()
    time.sleep(0.03)

failures = []
app._press_box(LAUNCH)  # what a gaze dwell on the LAUNCH plate does
qapp.processEvents()


def tick():
    dt = C.TICK_MS / 1000.0
    clock["t"] += dt
    inp.head_pitch += inp.pitch * C.GYRO_PITCH_SIGN * dt  # the head really moved
    app._tick()
    qapp.processEvents()


g = app.game
tick()
if g.phase != "intro":
    failures.append(f"LAUNCH did not start the intro (phase {g.phase})")
while g.phase == "intro" and g.intro.t < 3:
    tick()
app._press_box(SKIPS)  # the story's own skip plate
tick()
for _ in range(int(60 / (C.TICK_MS / 1000.0))):  # the countdown, the jump, and into level 1
    if g.phase == "play":
        break
    tick()
if g.phase != "play":
    failures.append(f"the intro never reached play (phase {g.phase})")
baseline = len(app.app.findChildren(QWidget))
ticks = 0
worst_pixels = None
while g.phase == "play" and g.run.level <= 4 and ticks < 9000:
    r = g.run
    tgt = bot_target(g)
    in_reach = any(not w.dead and r.t >= w.spawn_at and not g.arriving(w) and g.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS for w in r.worlds)
    fire = in_reach
    if r.mode == "intermission":
        fire = ticks % 6 < 3  # SECTOR CLEARED waits for a fresh "Pew"
    dy, dp = azd(tgt["az"], app.head.yaw), tgt["el"] - app.head.pitch
    inp.yaw, inp.pitch = max(-120, min(120, dy * 5)), max(-120, min(120, dp * 5))
    inp.mic = 0.9 if fire else 0.0
    tick()
    ticks += 1
    if ticks == 600:  # a frame from the middle of the game: the scene layer really paints
        img = app.layer.grab().toImage()
        lit = sum(1 for y in range(0, img.height(), 4) for x in range(0, img.width(), 4) if img.pixelColor(x, y).value() > 40)
        worst_pixels = lit
        if lit < 150:
            failures.append(f"the scene layer painted almost nothing ({lit} lit samples)")

if g.phase != "play":
    failures.append(f"the scripted perfect player lost at level {g.run.level} (phase {g.phase}, cause {g.run.lost_cause})")
if g.run.level < 5:
    failures.append(f"only reached level {g.run.level} in {ticks} ticks")
if not g.run.chip_collected or g.run.capacity != CHIP_CAPACITY:
    failures.append(f"chip not collected / capacity {g.run.capacity}")
now = len(app.app.findChildren(QWidget))
if now != baseline:
    failures.append(f"widget count changed during play: {baseline} -> {now}")

print(f"level {g.run.level}, score {g.run.score}, chip {g.run.chip_collected}, widgets {baseline}->{now}, ticks {ticks}, lit samples {worst_pixels}")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
