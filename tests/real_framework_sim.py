"""The simulator experience, on the REAL framework and (where present) this Mac's real hardware.

Run by test_real_framework.py in its own process. Exit 77 = framework not installed. Parts that
need hardware (Mac IMU, microphone) only assert when that hardware is there.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OVERBLASTER_MUTE", "1")  # tests never play sound
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QLabel
    from raven_framework.components.button import Button
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)

from overblaster import config as C  # noqa: E402
from overblaster.app import OverBlasterApp  # noqa: E402
from overblaster.macimu import MacImuSensor  # noqa: E402

SHOT = os.environ.get("OVERBLASTER_SHOT")  # optional: save a screenshot here
failures = []


def check(ok, message):
    print(("ok   " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


app = OverBlasterApp()  # real RavenInputs, real MacImuSensor: exactly what main.py builds
app.show()
for _ in range(30):
    qapp.processEvents()
    time.sleep(0.03)
check(app.simulated, "off a Raven device the app runs in simulator mode")
launch = next(w for w in app.app.findChildren(Button) if w.text == "LAUNCH")
launch.clicked.emit()
qapp.processEvents()
check(not [w for w in app.app.findChildren(Button) if w.text.lower() == "pew"], "there is no PEW button")


def pump(seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        qapp.processEvents()
        time.sleep(0.01)


def dot_center():
    dot = app.cross.sprites[-1]
    return dot.widget.x() + dot.w / 2, dot.widget.y() + dot.h / 2


# Mouse: plain moves (no button held) delivered to the widget under the cursor, which is how a
# real mouse arrives. Qt throws these away at the first widget that doesn't track the mouse, so a
# handler on the app widget alone only ever heard moves made while a button was held (the bug).
ox, oy = app.app.x(), app.app.y()
check((ox, oy) != (0, 0), f"the game area is offset inside the window ({ox}, {oy}); that offset must be subtracted")
for held, label in ((Qt.MouseButton.NoButton, "no button"), (Qt.MouseButton.LeftButton, "button held")):
    for target in ((500, 200), (150, 450)):
        window = QPointF(ox + target[0], oy + target[1])
        child = app.childAt(int(window.x()), int(window.y())) or app
        event = QMouseEvent(
            QEvent.Type.MouseMove, QPointF(child.mapFrom(app, window.toPoint())), window,
            Qt.MouseButton.NoButton, held, Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(child, event)
        pump(0.25)  # a few real game ticks (the Routine fires on the Qt event loop)
        x, y = dot_center()
        check(abs(x - target[0]) < 3 and abs(y - target[1]) < 3,
              f"crosshair follows the mouse with {label} to {target}: at ({x:.0f}, {y:.0f}) over a {type(child).__name__}")

# Microphone: the real Qt microphone is delivering levels (the debug panel is off, so read it directly).
mic = app.inputs._mic
if mic is not None and getattr(mic, "audio_source", None) is not None:
    pump(1.0)
    check(app.inputs.mic_status == "listening", f"microphone status is '{app.inputs.mic_status}'")
    check(app.inputs._peak.latest > 0.0, f"the microphone is delivering levels (latest {app.inputs._peak.latest:.4f})")
else:
    print("skip microphone checks: no audio input")

# No debug text unless asked for.
check(not app.debug and not hasattr(app, "dbg_mic"), "no debug panel by default")
shown_text = " ".join(w.text() for w in app.app.findChildren(QLabel) if w.isVisible())
check(not any(word in shown_text for word in ("MIC ", "IMU ", "GAZE ", "fires >")), "no debug text on screen")

# The battery meter: a small real widget that really paints, with no words in it.
from overblaster import hud as hud_mod  # noqa: E402
from overblaster.hudlayer import HudLayer  # noqa: E402

check(isinstance(app.hud, HudLayer), "the HUD is the real painted widget")
check(app.hud.width() <= 330 and app.hud.height() <= 110, f"the HUD widget is a small corner, not the game area ({app.hud.width()} x {app.hud.height()})")
check(app.hud.y() == 0, "the HUD sits at the very top of the game area")
game0 = app.game
game0.state = type(game0.state).PLAYING
game0.charge, game0.capacity, game0.chip_collected, game0.level = 100.0, 100.0, False, 3
real_mac0, app.mac_imu = app.mac_imu, None
pump(3.5)  # past the level splash, so only the permanent HUD is on screen
img = app.grab().toImage()
ox, oy = app.app.x(), app.app.y()
lit = sum(1 for yy in range(oy + 4, oy + 70) for xx in range(ox + 20, ox + 160)
          if img.pixelColor(xx, yy).red() < 90 and img.pixelColor(xx, yy).green() > 190 and img.pixelColor(xx, yy).blue() > 200)
check(lit > 800, f"the HUD paints lit cyan cells at full battery ({lit} cyan pixels)")
caption_px = sum(1 for yy in range(oy + 14, oy + 58) for xx in range(ox + 170, ox + 300)
                 if img.pixelColor(xx, yy).red() < 90 and img.pixelColor(xx, yy).green() > 190 and img.pixelColor(xx, yy).blue() > 200)
check(caption_px > 150, f"the HUD paints 'LVL 3' to the right of the meter, in the battery's colour ({caption_px} cyan pixels there)")
white = sum(1 for yy in range(oy + 6, oy + 66) for xx in range(ox + 170, ox + 420)
            if img.pixelColor(xx, yy).red() > 200 and img.pixelColor(xx, yy).green() > 200 and img.pixelColor(xx, yy).blue() > 200)
check(white == 0, f"and no white level name beside it ({white} white pixels there)")
visible = " | ".join(w.text() for w in app.app.findChildren(QLabel) if w.isVisible() and w.text().strip())
check(not any(n in visible for n in C.LEVEL_NAMES), f"no level name anywhere on screen between levels")
check("ENERGY" not in visible.upper() and "%" not in visible, "no ENERGY label and no percentage")

# The level name is announced when a level starts, then goes away.
from overblaster.game import State  # noqa: E402

game0.worlds.clear()
game0.crystals.clear()
game0.level = 3  # the next level will be level 4
game0.state = State.INTERMISSION
game0._intermission_left = 0.0
game0.acknowledge()  # SECTOR CLEARED would otherwise wait for a "Pew"
pump(0.5)
from overblaster import screens  # noqa: E402
from overblaster.screenlayers import SplashLayer  # noqa: E402

check(isinstance(app.splash, SplashLayer) and app.splash.isVisible(), "the level-start splash is on screen")
check(app.splash.model.number.text == "4" and app.splash.model.name.text == C.level_name(4), "and it says LVL 4 and the level's name")
pump(0.7)  # fully faded in, and the head has not moved
img = app.grab().toImage()
sx, sy = app.splash.x() + app.app.x(), app.splash.y() + app.app.y()
solid = sum(1 for yy in range(sy, sy + 150, 2) for xx in range(sx, sx + 600, 2)
            if img.pixelColor(xx, yy).green() > 160 and img.pixelColor(xx, yy).blue() > 180 and img.pixelColor(xx, yy).red() < 80)
check(solid > 400, f"the splash paints its cyan number block ({solid} sampled cyan pixels)")
pump(screens.SPLASH_END + 0.2)
check(not app.splash.isVisible(), "and the splash is gone a couple of seconds later (the HUD keeps LVL 4)")

app.hud.set_state(0.1, False, 4, 1000.0)
phase_a = app.hud._phase
app.hud.set_state(0.1, False, 4, 1000.75)
check(app.hud._phase != phase_a, "the low-battery flicker alternates between two phases")
app.mac_imu = real_mac0

# The blue pointer arrow: a real widget that turns toward the closest world, any direction.
import math  # noqa: E402

from overblaster.game import World  # noqa: E402

game = app.game
game.state = type(game.state).PLAYING
# Hold the head still for these checks: with this Mac's real IMU driving the view, a nudge of the
# laptop between steps would legitimately move the arrow and make the expected angle a moving target.
real_mac, app.mac_imu = app.mac_imu, None
app.head.yaw = app.head.pitch = 0.0
pump(0.2)
game.crystals.clear()
for az, el in ((50, 18), (-60, -10), (0, -18), (300, 15)):
    game.worlds[:] = [World(az=az, el=el, az_v=0, el_v=0, progress=0.3, speed=0, hp=3, kind="a")]
    pump(0.3)
    ppd = C.DISPLAY_PX / C.FOV_DEG
    world = game.worlds[0]  # not (az, el): the game keeps worlds within +/- EL_LIMIT degrees of elevation
    dy = -(world.el - app.game.view_el) * ppd
    dx = ((world.az - app.game.view_az + 180) % 360 - 180) * math.cos(math.radians(world.el)) * ppd
    want = math.degrees(math.atan2(dy, dx))
    arrow = app.planet_arrow
    got = arrow._deg
    off = abs((got - want + 180) % 360 - 180)
    cx, cy = arrow.x() + arrow.width() / 2, arrow.y() + arrow.height() / 2
    ring = math.hypot(cx - 320, cy - 320)
    check(arrow.isVisible() and off <= 3 and abs(ring - 250) < 3,
          f"blue arrow for a world at ({az}, {el}): visible={arrow.isVisible()}, points {got:.0f} deg (want {want:.0f}), ring {ring:.0f} px")
    if (az, el) == (50, 18) and SHOT:
        qapp.processEvents(); app.grab().save(SHOT.replace(".png", "_arrow.png"))

app.mac_imu = real_mac  # back to the real sensor

# Mac IMU: the real sensor drives the head tracker (laptop assumed still, so the view stays put).
if app.mac_imu is not None and app.mac_imu.error is None:
    pump(1.5)
    check(app.imu_source == "mac", f"head tracking uses this Mac's IMU (source: {app.imu_source})")
    check(abs(app.head.pitch) < 15, f"a flat laptop reads as roughly level: pitch {app.head.pitch:.1f}")
    check(min(app.head.yaw, 360 - app.head.yaw) < 5, f"a still laptop doesn't drift the yaw: {app.head.yaw:.2f}")
else:
    print(f"skip Mac IMU checks: {getattr(app.mac_imu, 'error', 'no sensor')}")

if SHOT:
    qapp.processEvents()
    app.grab().save(SHOT)
    print("screenshot:", SHOT)
sys.exit(1 if failures else 0)
