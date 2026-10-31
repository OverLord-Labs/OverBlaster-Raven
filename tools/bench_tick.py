"""How long does one app tick take, paint included? A bot plays levels 1, 7 and 14 offscreen on the real widgets.

    .venv/bin/python tools/bench_tick.py [--ticks 300] [--size 640]

Prints ms per tick (the core and the sensors) and per paint (the whole scene, QPainter), as mean / p95 / max. The
budget is TICK_MS (66 ms at 15 Hz); this Mac is faster than the glasses' board, so leave plenty of headroom.
"""

import argparse
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OVERBLASTER_MUTE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

qapp = QApplication(sys.argv[:1])

import overblaster.app as app_mod  # noqa: E402
from overblaster import config as C  # noqa: E402
from overblaster.core import CHIP_CAPACITY, HIT_FORGIVENESS, azd, bot_target, rock_radius  # noqa: E402


class Inputs:
    mic = yaw = pitch = 0.0

    def imu(self):
        g = [0.0, 0.0, 0.0]
        g[C.GYRO_YAW_AXIS], g[C.GYRO_PITCH_AXIS] = self.yaw, self.pitch
        return {"accelerometer": {"x": 0, "y": 0, "z": 9.8}, "gyroscope": {"x": g[0], "y": g[1], "z": g[2]}, "magnetometer": {"x": 0, "y": 0, "z": 0}}

    def gaze(self):
        return None

    def mic_level(self):
        return self.mic

    def close(self):
        pass


def stats(xs):
    xs = sorted(xs)
    return f"{sum(xs) / len(xs):5.1f} / {xs[int(len(xs) * 0.95) - 1]:5.1f} / {xs[-1]:5.1f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=300)
    ap.add_argument("--size", type=int, default=640)
    a = ap.parse_args()
    clock = {"t": 1000.0}
    app_mod.time.monotonic = lambda: clock["t"]
    inp = Inputs()
    app = app_mod.OverBlasterApp(inputs=inp, simulated=False, mac_imu=False, seed=7)
    app.layer.setFixedSize(a.size, a.size)
    app.show()
    for _ in range(10):
        qapp.processEvents()
    g = app.game
    img = QImage(a.size, a.size, QImage.Format.Format_ARGB32)
    print(f"{a.size} px, budget {C.TICK_MS} ms.  ms per frame: mean / p95 / max")
    for label, setup in (("title", None), ("level 1", 1), ("level 7", 7), ("level 14", 14), ("intro 0-45 s", "intro")):
        if setup == "intro":
            g.to_title()
            g.begin_intro()
        elif setup:
            g.begin_game()
            g.run.chip_collected, g.run.capacity, g.run.charge = True, CHIP_CAPACITY, CHIP_CAPACITY
            g.start_level(setup)
        ticks, paints = [], []
        n = int(45 / (C.TICK_MS / 1000)) if setup == "intro" else a.ticks
        for i in range(n):
            if g.phase == "play":
                r = g.run
                tgt = bot_target(g)
                fire = any(not w.dead and r.t >= w.spawn_at and not g.arriving(w) and g.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS for w in r.worlds)
                dy, dp = azd(tgt["az"], app.head.yaw), tgt["el"] - app.head.pitch
                inp.yaw, inp.pitch = max(-120, min(120, dy * 5)), max(-120, min(120, dp * 5))
                inp.mic = 0.9 if fire else 0.0
            clock["t"] += C.TICK_MS / 1000
            t0 = time.perf_counter()
            app._tick()
            t1 = time.perf_counter()
            app.layer.render(img)  # runs SceneLayer.paintEvent: the whole scene
            t2 = time.perf_counter()
            ticks.append((t1 - t0) * 1000)
            paints.append((t2 - t1) * 1000)
            if g.phase == "over":
                g.begin_game()
                g.start_level(setup)
        print(f"{label:13s} tick {stats(ticks)}   paint {stats(paints)}")


if __name__ == "__main__":
    main()
