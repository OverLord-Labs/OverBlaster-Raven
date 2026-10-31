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
    from PySide6.QtWidgets import QApplication
    from raven_framework.components.button import Button
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)

from overblaster import config as C  # noqa: E402
from overblaster.app import OverBlasterApp  # noqa: E402

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
check(list(app._plates()) == ["launch"] and not app.app.findChildren(Button), "LAUNCH is a plate the scene draws, pressed by dwelling: no widgets over it")
from overblaster.core import LAUNCH  # noqa: E402
app._press_box(LAUNCH)
qapp.processEvents()
check(not [w for w in app.app.findChildren(Button) if w.text.lower() == "pew"], "there is no PEW button")


def pump(seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        qapp.processEvents()
        time.sleep(0.01)


pump(0.3)
app.game.begin_game()  # straight into level 1 (the story intro has its own checks in the render tests)
pump(0.3)

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
        p = app.game.input.pointer
        check(p.mouse and abs(p.x - target[0]) < 3 and abs(p.y - target[1]) < 3,
              f"crosshair follows the mouse with {label} to {target}: at ({p.x:.0f}, {p.y:.0f}) over a {type(child).__name__}")

# Microphone: the real Qt microphone is delivering levels (the debug panel is off, so read it directly).
mic = app.inputs._mic
if mic is not None and getattr(mic, "audio_source", None) is not None:
    pump(1.0)
    check(app.inputs.mic_status == "listening", f"microphone status is '{app.inputs.mic_status}'")
    check(app.inputs._peak.latest > 0.0, f"the microphone is delivering levels (latest {app.inputs._peak.latest:.4f})")
else:
    print("skip microphone checks: no audio input")

# No debug text unless asked for.
check(not app.debug and app.dbg is None and app.layer.debug is None, "no debug panel by default")

# The whole screen is one painted widget; look at what it really paints.
from overblaster.scenelayer import SceneLayer  # noqa: E402

check(isinstance(app.layer, SceneLayer), "the scene is the real painted widget")
check((app.layer.width(), app.layer.height()) == (app.screen_w, app.screen_h), "and it covers the whole game area")
game = app.game
real_mac0, app.mac_imu = app.mac_imu, None  # hold the head still: a laptop nudge would move the view between steps
app.head.yaw = app.head.pitch = 0.0
game.run.worlds[:] = [w for w in game.run.worlds if False]  # clear the field (no worlds, no distractions)
game.run.crystals.clear()
for w in game.run.worlds:
    w.spawn_at = 9999


def cyan_near(img, cx, cy, r, g_min=190, b_min=200):
    n = 0
    for yy in range(int(cy - r), int(cy + r)):
        for xx in range(int(cx - r), int(cx + r)):
            if 0 <= xx < img.width() and 0 <= yy < img.height():
                c = img.pixelColor(xx, yy)
                n += c.red() < 90 and c.green() > g_min and c.blue() > b_min
    return n


def keep_alive():
    """Empty field but no level clear: park one far-away rock so the level goes on."""
    game.run.worlds[:] = [game.make_world(az=180.0, el=0.0, spawn_at=9999.0, approach=30.0, hp=3)]
    game.run.crystals.clear()


keep_alive()
game.run.t = 8.0  # past the level-start splash (its fade ends at SPLASH_END after the level began)
game.run.splash_t0 = game.clock - 99
game.run.charge, game.run.capacity, game.run.chip_collected, game.run.level = 100.0, 100.0, False, 3
pump(0.5)
img = app.grab().toImage()
ox, oy = app.app.x(), app.app.y()
lit = cyan_near(img, ox + 90, oy + 35, 70)
check(lit > 800, f"the HUD paints lit cyan cells at full battery ({lit} cyan pixels)")
caption = cyan_near(img, ox + 230, oy + 36, 55)
check(caption > 150, f"the HUD paints 'LVL 3' to the right of the meter, in the battery's colour ({caption} cyan pixels there)")

# The level name hangs in the sky when a level starts (above where you were looking), then goes away.
game.run.worlds.clear()
game.start_level(4)
keep_alive()
pump(1.0)
img = app.grab().toImage()
splash = cyan_near(img, ox + 137, oy + 186, 45, 110, 120)  # the number block (the plate is drawn at 70% opacity), hung just above the view
check(splash > 800, f"the level-start splash paints its cyan number block ({splash} cyan pixels)")
pump(7.5)
img = app.grab().toImage()
splash = cyan_near(img, ox + 137, oy + 186, 45, 110, 120)  # the number block (the plate is drawn at 70% opacity), hung just above the view
check(splash < 100, f"and the splash is gone a few seconds later ({splash} cyan pixels left; the HUD keeps LVL 4)")

# The arrows: one cyan arrow on the ring for each rock out of view, pointing at it, any direction.
import math  # noqa: E402

game.run.worlds.clear()
for az, el in ((50, 18), (-60, -10), (0, -18), (300, 15)):
    game.run.worlds[:] = [game.make_world(az=az % 360.0, el=el, spawn_at=-1.0, approach=1e9, hp=3, p=0.3)]
    game.run.crystals.clear()
    game.run.t = 8.0
    pump(0.3)
    rock = game.run.worlds[0]
    p = game.proj(rock.az, rock.el)
    ang = math.atan2(p.dy, p.dx)
    img = app.grab().toImage()
    ax, ay = ox + 320 + math.cos(ang) * 250, oy + 320 + math.sin(ang) * 250
    near = cyan_near(img, ax, ay, 22)
    check(near > 60, f"a cyan arrow sits on the ring toward a rock at ({az}, {el}): {near} cyan pixels near ({ax - ox:.0f}, {ay - oy:.0f})")
    if (az, el) == (50, 18) and SHOT:
        qapp.processEvents()
        app.grab().save(SHOT.replace(".png", "_arrow.png"))

app.mac_imu = real_mac0  # back to the real sensor

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
