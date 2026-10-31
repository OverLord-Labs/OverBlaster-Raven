"""OverBlaster: the RavenApp. Wires sensors -> core.Game -> one painted scene.

The rules, levels, intro and every number live in overblaster.core (a port of the web game's core, tested
against it). overblaster.render paints the game (a QPainter port of the web renderer) on one full-screen
widget, scenelayer.SceneLayer. This module only connects the glasses to those two:

  head (IMU)            -> InputFrame.head       where you look
  gaze, when steady     -> InputFrame.pointer    where the crosshair is (else it sits in the centre)
  voice level over hi   -> InputFrame.fire       "Pew" (held while the sound goes on)
  gaze dwelling on a plate -> InputFrame.presses LAUNCH, RETRY, TITLE and SKIP STORY (the glasses have no click)

and plays the SoundEvents the core emits.
"""

import time
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from raven_framework import RavenApp, Routine, fade_in

from . import config as C
from .audiosink import make_sound
from .core import ACK_MIN, LAUNCH, RETRY, SKIPS, TOTITLE, Game, Head, InputFrame, Pointer, Press, is_sound
from .core.layout import Box
from .dwell import Dwell
from .inputs import RavenInputs, on_device
from .macimu import MacImuSensor
from .mousetap import MouseTap
from .scenelayer import DebugInfo, make_scene_layer
from .sensors import GazeAim, HeadTracker, ImuProfile, VoiceTrigger
from .ui import display_size

GAZE_CURSOR_STALE_S = 0.5
FADE_SETTLE_MS = 900  # the framework's fade-in is 750 ms
LOGICAL = 640.0  # the core's screen: 640 x 640 logical px, whatever the container's real size


class OverBlasterApp(RavenApp):
    def __init__(
        self,
        parent=None,
        inputs: Optional[RavenInputs] = None,
        simulated: Optional[bool] = None,
        mac_imu=None,
        debug: Optional[bool] = None,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self.inputs = inputs or RavenInputs()
        # Off a Raven device the gyroscope is fake and the arrow keys only move the
        # accelerometer, so steer with those unless this Mac's own IMU is available.
        self.simulated = C.SIM_FORCE or not on_device() if simulated is None else simulated
        self.debug = C.DEBUG_FORCE if debug is None else debug  # the panel is off unless asked for
        self.screen_w, self.screen_h = display_size(self.app)
        self.routine: Optional[Routine] = None
        self.imu_source = "device"
        self.mac_imu: Optional[MacImuSensor] = None
        if self.simulated and mac_imu is not False:
            self.mac_imu = mac_imu or MacImuSensor()
            if not self.mac_imu.start() and self.mac_imu.error:
                print(f"[overblaster] mac imu unavailable ({self.mac_imu.error}); using the arrow keys")
        self._flip = {"yaw": 1.0, "pitch": 1.0}  # live sign flips for the Mac IMU (keys Y, P)
        self._mouse: Optional[tuple] = None  # the cursor in game-area pixels (the simulator's "gaze")
        self._mouse_at = float("-inf")
        self._mouse_tap = None
        qapp = QApplication.instance()
        if qapp is not None:  # sees every mouse move, even over widgets that don't track the mouse
            self._mouse_tap = MouseTap(self, self._on_mouse, self._on_click)
            qapp.installEventFilter(self._mouse_tap)

        self.game = Game(seed=seed)
        self.head = HeadTracker(sim=self.simulated)
        # A mouse has no noise to filter, and moving it would read as "jitter", so trust it.
        self.gaze = GazeAim(self.screen_w, self.screen_h, trust_all=self.simulated)
        self.voice = VoiceTrigger()
        self.sound = make_sound()
        self._presses: List[Press] = []  # dwell buttons and keys, handed to the core on the next tick
        self._commands: List[str] = []
        self._space_held = False
        self._ack_armed = False  # the plate's gate is open and the mic has been quiet since
        self._mic_open = False
        self._dbg_last_fire = 0.0
        self._tick_count = 0
        self.dwell = Dwell(C.DWELL_S)
        self._last_cross = self.gaze.center  # the crosshair in game-area px at the last tick

        self.layer = make_scene_layer(self.app, self.screen_w, self.screen_h, self.game)  # the bottom layer
        self.dbg = DebugInfo() if self.debug else None
        self.layer.debug = self.dbg
        self._last = time.monotonic()
        self.routine = Routine(interval_ms=C.TICK_MS, invoke=self._tick, mode="repeat")
        fade_in(self.app)
        # fade_in leaves a graphics effect on the game container for good. The simulator draws its
        # picture with QWidget.render(), which displaces a child that has an effect by that child's
        # own offset (40, 50 here), so the whole game shows away from where the simulator sends the
        # mouse. Drop the effect once the fade has finished.
        if QApplication.instance() is not None:
            QTimer.singleShot(FADE_SETTLE_MS, self._drop_fade_effect)

    def closeEvent(self, event) -> None:
        if self.routine:
            self.routine.stop()
            self.routine = None
        self.inputs.close()
        self.sound.close()
        super().closeEvent(event)

    def _drop_fade_effect(self) -> None:
        if getattr(self.app, "graphicsEffect", None) and self.app.graphicsEffect() is not None:
            self.app.setGraphicsEffect(None)

    # ----- dwell buttons -----------------------------------------------------
    def _plates(self) -> dict:
        """The plates the current screen draws that can be pressed (boxes in core/layout.py)."""
        g = self.game
        if g.phase == "title":
            return {} if g.launching else {"launch": LAUNCH}
        if g.phase == "over":
            return {"retry": RETRY, "title": TOTITLE}
        if g.story_btn_visible():
            return {"skip": SKIPS}
        return {}

    def _press_box(self, box: Box) -> None:
        """A plate was pressed (dwell or click): the core hears a press in the middle of its box."""
        self._presses.append(Press(box.x + box.w / 2, box.y + box.h / 2))

    # ----- simulator input ---------------------------------------------------
    def _on_mouse(self, x: float, y: float) -> None:
        """The cursor moved to (x, y) in this widget's coordinates; keep it in game-area pixels."""
        self._mouse = (x - self.app.x(), y - self.app.y())
        self._mouse_at = time.monotonic()

    def _on_click(self, x: float, y: float) -> None:
        """A mouse click (the simulator): a press where the cursor is, in the core's 640 px screen."""
        self._presses.append(Press((x - self.app.x()) * LOGICAL / self.screen_w, (y - self.app.y()) * LOGICAL / self.screen_h))

    def keyPressEvent(self, event) -> None:
        if hasattr(event, "isAutoRepeat") and event.isAutoRepeat():
            return
        key = event.text().lower()
        code = event.key() if hasattr(event, "key") else None
        if code == Qt.Key.Key_Escape:
            key = "escape"
        elif code == Qt.Key.Key_Space:
            key = "space"
        elif code in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            key = "return"
        if not self.handle_key(key):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if hasattr(event, "isAutoRepeat") and event.isAutoRepeat():
            return
        if (hasattr(event, "key") and event.key() == Qt.Key.Key_Space) or event.text() == " ":
            self.handle_key("space", down=False)

    def handle_key(self, key: str, down: bool = True) -> bool:
        """Space is "Pew" (held to keep firing) and presses whatever is under the crosshair; Enter launches;
        Escape skips the story; C or R recenters the view; Y / P flip the Mac IMU's yaw / pitch while you find the
        right signs; D shows the debug panel."""
        if key in ("space", " "):
            if down and not self._space_held:
                self._presses.append(self._pointer_press())
            self._space_held = down
        elif not down:
            return False
        elif key in ("return", "enter"):
            self._commands.append("launch")
        elif key in ("escape", "\x1b"):
            self._commands.append("skipStory")
        elif key in ("c", "r"):
            self.head.recenter()
        elif key in ("y", "p") and self.imu_source == "mac":
            axis = "yaw" if key == "y" else "pitch"
            self._flip[axis] = -self._flip[axis]
            print(
                f"[overblaster] mac imu {axis} flipped. To keep it, set "
                f"MAC_{axis.upper()}_SIGN = {self._effective_sign(axis):+.1f} in config.py"
            )
        elif key == "d":
            self.debug = not self.debug
            self.dbg = DebugInfo() if self.debug else None
            self.layer.debug = self.dbg
        else:
            return False
        return True

    def _effective_sign(self, axis: str) -> float:
        """The sign actually in use: the config value times any live flip."""
        base = C.MAC_YAW_SIGN if axis == "yaw" else C.MAC_PITCH_SIGN
        return base * self._flip[axis]

    def _read_imu(self) -> Optional[dict]:
        """This Mac's IMU when it is streaming, else the arrow keys (simulator), else the glasses."""
        reading = self.mac_imu.reading() if self.mac_imu else None
        if reading:
            self.imu_source = "mac"
            self.head.sim = False
            self.head.profile = ImuProfile.mac(self._flip["yaw"], self._flip["pitch"])
            return reading
        self.head.profile = None
        self.head.sim = self.simulated
        self.imu_source = "keys" if self.simulated else "device"
        return self.inputs.imu()

    def _read_gaze(self):
        """Simulator: the mouse. Glasses: the eye tracker, else (if it reports nothing) the cursor.

        The framework treats gaze as the cursor on the glasses (its Buttons dwell on hover), so if
        EyeControl returns None the cursor may still be following the eyes. A cursor that has
        stopped moving for half a second is ignored there: a parked cursor isn't a gaze.
        """
        if self.simulated:
            return self._mouse
        gaze = self.inputs.gaze()
        if gaze is not None:
            return gaze
        fresh = time.monotonic() - self._mouse_at < GAZE_CURSOR_STALE_S
        return self._mouse if fresh else None

    # ----- tick ------------------------------------------------------------
    def _pointer(self, cx: float, cy: float) -> Pointer:
        """The crosshair in the core's 640 px screen. Only a steady gaze (or the simulator's mouse) moves it."""
        on = bool(self.gaze.confident)
        return Pointer(cx * LOGICAL / self.screen_w, cy * LOGICAL / self.screen_h, mouse=on, inside=on)

    def _pointer_press(self) -> Press:
        """A press where the crosshair is now (the space bar)."""
        p = self._pointer(*self._last_cross)
        return Press(p.x, p.y)

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(max(now - self._last, 0.001), 0.25)  # clamp after a stall
        self._last = now
        g = self.game
        self._tick_count += 1

        head_az, head_el = self.head.update(self._read_imu(), dt)
        cx, cy = self.gaze.update(self._read_gaze())
        self._last_cross = (cx, cy)

        # The microphone is only needed while playing: "Pew" fires, and a fresh one acknowledges the plate.
        playing = g.phase == "play"
        level, fired = None, False
        if playing:
            self._mic_open = True
            level = self.sound.gate(self.inputs.mic_level())
            fired = self.voice.update(level)
        else:
            self.voice.update(None)
            if self._mic_open:
                self._mic_open = False
                self.inputs.close()
        raw = self._read_gaze() if self._plates() else None  # the cursor or the eyes, steady or not: what a Button would hover on
        plates = self._plates()
        pressed = self.dwell.update(dt, None if raw is None else (raw[0] * LOGICAL / self.screen_w, raw[1] * LOGICAL / self.screen_h), plates)
        if pressed:
            self._press_box(plates[pressed])
        self.layer.dwell = {n: (plates[n], p) for n, p in self.dwell.progress.items() if n in plates}
        presses = self._presses
        self._presses = []
        if playing and g.run.mode == "intermission":
            # Sound is ignored until the gate opens, and then only a fresh sound counts: a "Pew"
            # still ringing from the level (or held the whole time) must not skip the plate.
            gate_open = g.clock - g.run.plate_at >= ACK_MIN
            if not gate_open or not fired:
                self._ack_armed = gate_open
            elif self._ack_armed:
                self._ack_armed = False
                presses.append(Press(LOGICAL / 2, LOGICAL / 2))

        commands = self._commands
        self._commands = []
        frame = InputFrame(
            head=Head(head_az, head_el),
            fire=fired or self._space_held,
            pointer=self._pointer(cx, cy),
            presses=presses,
            commands=commands,
        )
        g.update(dt, frame)
        self._handle_events(g.drain())
        self.sound.tick()
        self._update_debug(level, fired, now)
        self.layer.update()

    def _handle_events(self, events: List[dict]) -> None:
        for e in events:
            t = e["type"]
            if is_sound(e):
                self.sound.handle(e)
            elif t == "launch":
                self.game.begin_intro()  # the clips are loaded already: nothing to wait for
            elif t == "levelStart" and e["level"] == 1:
                self.head.recenter()  # straight ahead is wherever you are looking as the run begins
                self._ack_armed = False

    def _update_debug(self, level: Optional[float], fired: bool, now: float) -> None:
        if self.dbg is None:
            return
        if fired:
            self._dbg_last_fire = now
        self.dbg.mic = level or 0.0
        self.dbg.hot = now - self._dbg_last_fire < 0.4
        if self._tick_count % 3 == 0:  # the text changes constantly; rebuild it a few times a second
            mode = "mouse" if self.simulated else "eye"
            where = "following" if self.gaze.confident else "centered"
            self.dbg.lines = [
                f"IMU {self.imu_source}   yaw {self.head.yaw:5.1f}   pitch {self.head.pitch:5.1f}   mic [{self.inputs.mic_status}]"
                + (f"   signs yaw {self._effective_sign('yaw'):+.0f} pitch {self._effective_sign('pitch'):+.0f}   keys: C center  Y/P flip" if self.imu_source == "mac" else ""),
                f"GAZE {mode}  {where}  head-only aim: {'no' if self.gaze.confident else 'yes'}",
            ]
