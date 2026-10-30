"""The picture the simulator shows must line up with where it sends the mouse.

The simulator shrinks `_render_app_bgra()` into the composite you look at and remaps the mouse
back onto the app with its own transform. If the render is displaced, the crosshair appears away
from the cursor (this was off by the game area's offset, (40, 50), because the fade-in's graphics
effect was left on the game container, and QWidget.render() mishandles a child that has one).

Run by test_real_framework.py in its own process. Exit 77 = framework not installed.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OVERBLASTER_MUTE", "1")  # tests never play sound
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import numpy as np
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from raven_framework.components.button import Button
    from raven_framework.core.raven_simulator import SimulatorRunApp
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)
from overblaster.app import OverBlasterApp  # noqa: E402

app = OverBlasterApp(mac_imu=False)
app.bind_sleep_wake(app_id="", app_key="")
win = SimulatorRunApp(app)
win.start_hidden()
win.show()
win.move(0, 0)


def pump(seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        qapp.processEvents()
        time.sleep(0.01)


def crosshair_in(res):
    data, w, h = res
    rgb = np.frombuffer(data, dtype=np.uint8).reshape((h, w, 4))[..., [2, 1, 0]].astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    ys, xs = np.nonzero((g > 200) & (g - r > 60) & (g - b > 60))  # the crosshair's (120, 255, 120) ticks
    return (xs.mean(), ys.mean()) if len(xs) > 8 else None


pump(0.5)
win.reveal(10)
pump(2.5)  # past the 750 ms fade-in
next(w for w in app.app.findChildren(Button) if w.text == "LAUNCH").clicked.emit()
pump(1.0)

overlay = win._gaze_overlay
failures = []
# Aim at chosen spots *inside the app*, converted to window positions with the simulator's own
# transform, so the test holds at any window size (on a wide window the app sits off to one side).
for wanted in ((234, 360), (402, 468), (162, 528)):
    point = (overlay._offset.x() + overlay._scale_x * wanted[0], overlay._offset.y() + overlay._scale_y * wanted[1])
    event = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(*point), QPointF(*point),
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(overlay, event)
    pump(0.6)
    # The crosshair should be at `wanted` in the picture the simulator shrinks and shows.
    seen = crosshair_in(win._render_app_bgra())
    ok = seen is not None and abs(seen[0] - wanted[0]) < 4 and abs(seen[1] - wanted[1]) < 4
    where = "nowhere" if seen is None else f"({seen[0]:.0f}, {seen[1]:.0f})"
    print(("ok   " if ok else "FAIL ") + f"mouse at window ({point[0]:.0f}, {point[1]:.0f}): crosshair should be at app {wanted}, the simulator renders it at {where}")
    if not ok:
        failures.append(point)
effect = app.app.graphicsEffect()
print(("ok   " if effect is None else "FAIL ") + f"no graphics effect left on the game container (found {type(effect).__name__ if effect else None})")
if effect is not None:
    failures.append("effect")
win.close()  # lets the simulator stop its blend-worker thread
pump(0.5)
sys.stdout.flush()
# Exit without interpreter teardown: the simulator's QThread would otherwise abort the process
# ("Destroyed while thread is still running") and hide the real result behind signal 6.
os._exit(1 if failures else 0)
