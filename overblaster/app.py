"""OverBlaster: the RavenApp. Wires sensors -> game rules -> sprites."""

import os
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from raven_framework import RavenApp, Routine, fade_in

from . import config as C
from . import bms
from . import hud as hudgeo
from . import synth, voicelines
from . import screens
from .game import Game, State, crosshair_bearing
from .inputs import RavenInputs, on_device
from .fx import DEATH_S, death_shapes, shot_shapes
from .audiosink import make_sound
from .bmslayer import make_bms_layer
from .fxlayer import make_arrow, make_fx_layer
from .hudlayer import make_hud
from .screenlayers import make_pause_layer, make_splash_layer, make_title_layer
from .macimu import MacImuSensor
from .mousetap import MouseTap
from .sensors import GazeAim, HeadTracker, ImuProfile, VoiceTrigger, pixels_to_degrees
from .ui import Bar, Crosshair, Label, Sprite, SpritePool, add_centered, display_size, make_button, static_text
from .view import closest, pixels_per_degree, pointer, project, size_class

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
WORLD_POOL = C.MAX_WORLDS_ON_SCREEN + 1  # widgets for worlds; the +1 is the chip carrier
WHITE, CYAN, GOLD, PINK = "#FFFFFF", "#00E5FF", "#FFC800", "#FF3CDC"
FIXED_BANNERS = {  # event -> (text, color)
    "hull_destroyed": ("HULL DESTROYED", PINK),
}
BANNER_SECONDS = 1.6
GAZE_CURSOR_STALE_S = 0.5
FADE_SETTLE_MS = 900  # the framework's fade-in is 750 ms
POINTER_RING = 250  # px from the centre of the view: clear of the HUD in the corners
CYAN_RGB, GOLD_RGB = (0, 229, 255), (255, 200, 0)
BATTERY_DEATH_S = 0.4  # a beat to see the last shot before the game-over screen
MUZZLE_Y_FROM_BOTTOM = 40  # where the laser leaves the ship's nose


def asset(*parts: str) -> str:
    return os.path.join(ASSETS, *parts)


def world_gif(kind: str, size: int) -> str:
    return asset("worlds", f"world_{kind}_{size}.gif")


class OverBlasterApp(RavenApp):
    def __init__(
        self,
        parent=None,
        inputs: Optional[RavenInputs] = None,
        simulated: Optional[bool] = None,
        mac_imu=None,
        debug: Optional[bool] = None,
    ) -> None:
        super().__init__(parent)
        self.inputs = inputs or RavenInputs()
        # Off a Raven device the gyroscope is fake and the arrow keys only move the
        # accelerometer, so steer with those unless this Mac's own IMU is available.
        self.simulated = C.SIM_FORCE or not on_device() if simulated is None else simulated
        self.debug = C.DEBUG_FORCE if debug is None else debug  # the panel is off unless asked for
        self.screen_w, self.screen_h = display_size(self.app)
        self.routine: Optional[Routine] = None
        self.game: Optional[Game] = None
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
            self._mouse_tap = MouseTap(self, self._on_mouse)
            qapp.installEventFilter(self._mouse_tap)
        self.sound = make_sound()
        self._title_said = False
        self.show_title()
        fade_in(self.app)
        # fade_in leaves a graphics effect on the game container for good. The simulator draws its
        # picture with QWidget.render(), which displaces a child that has an effect by that child's
        # own offset (40, 50 here), so the whole game shows away from where the simulator sends the
        # mouse. Drop the effect once the fade has finished.
        if QApplication.instance() is not None:
            QTimer.singleShot(FADE_SETTLE_MS, self._drop_fade_effect)

    def closeEvent(self, event) -> None:
        self.sound.close()
        super().closeEvent(event)

    def _drop_fade_effect(self) -> None:
        if getattr(self.app, "graphicsEffect", None) and self.app.graphicsEffect() is not None:
            self.app.setGraphicsEffect(None)

    # ----- screens ---------------------------------------------------------
    def show_title(self) -> None:
        self._stop_game()
        self.app.clear()
        x, y, w, h = screens.LAUNCH
        inset = 6  # the button sits inside the plate the title layer draws, so its dwell ring doesn't cover the plate
        launch = make_button(
            "LAUNCH", self.start_game, width=w - 2 * inset, height=h - 2 * inset,
            background_color="#000000", text_color=CYAN, text_size=28, font_weight="bold",
            corner_radius=0, outline_width=2, outline_color=CYAN, use_fill_dwell=False,
        )
        self.app.add(launch, x=x + inset, y=y + inset)
        self.title = make_title_layer(self.app)  # on top of the button: it takes no mouse events
        self.sound.music("title")
        if not self._title_said:
            self._title_said = True
            self.sound.say("title")

    def start_game(self) -> None:
        self._stop_game()
        self.app.clear()
        self.sound.sfx("ui_confirm")
        self.sound.music("game")
        self._chip_seen_id = None
        self._chip_tick = 0
        self._was_low = False
        self._plate_voiced = 0
        self.game = Game(hold_between_levels=True)  # SECTOR CLEARED waits for a "Pew"
        self.head = HeadTracker(sim=self.simulated)
        # A mouse has no noise to filter, and moving it would read as "jitter", so trust it.
        self.gaze = GazeAim(self.screen_w, self.screen_h, trust_all=self.simulated)
        self.voice = VoiceTrigger()
        self._build_scene()
        self._ack_armed = False  # the plate's gate is open and the mic has been quiet since
        self._award_t0: Optional[float] = None  # when the Overlord BMS was collected
        self._pause_t0: Optional[float] = None  # when the between-levels plate appeared
        self._splash_t0: Optional[float] = None  # when the level-start splash appeared
        self._splash_at = (0.0, 0.0)  # its place in the sky (az, el)
        self._banner_left = 0.0
        self._tick_count = 0
        self._death_t = 0.0
        self._last = time.monotonic()
        self.routine = Routine(interval_ms=C.TICK_MS, invoke=self._tick, mode="repeat")

    def show_game_over(self) -> None:
        self._stop_game()
        self.sound.music(None)
        self.app.clear()
        hull = self.game.lost_cause == "hull"
        static_text(self.app, "HULL DESTROYED" if hull else "BATTERY DEAD", 44, PINK, 130)
        static_text(
            self.app,
            "A Rogue World hit your ship." if hull else "You ran out of energy.",
            24, WHITE, 195,
        )
        static_text(self.app, f"Score {self.game.score}    Level {self.game.level}", 30, CYAN, 245)
        add_centered(self.app, make_button("Retry", self.start_game), 320)
        add_centered(self.app, make_button("Title", self.show_title), 400)

    def _stop_game(self) -> None:
        if self.routine:
            self.routine.stop()
            self.routine = None
        self.inputs.close()

    # ----- scene -----------------------------------------------------------
    def _build_scene(self) -> None:
        a, w, h = self.app, self.screen_w, self.screen_h

        # The between-levels plate and the level-start splash are backdrops: made first, so they sit
        # behind the worlds and the crosshair.
        self.pause = make_pause_layer(a)
        self.splash = make_splash_layer(a)

        # World sprites are a generic pool; each is bound to a live world and swapped
        # to that world's GIF (kind x size band) with load_media().
        self._free: List[Sprite] = [Sprite(a, world_gif("a", C.WORLD_BANDS[0]), C.WORLD_BANDS[0], radius=C.WORLD_BANDS[0] // 2) for _ in range(WORLD_POOL)]
        self._bound: Dict[int, Sprite] = {}  # id(World) -> sprite

        self.crystals = SpritePool(a, [asset("crystal.png")] * C.MAX_CRYSTALS_ON_SCREEN, 40, radius=20)
        self.chip = SpritePool(a, [asset("chip.png")], 64, radius=8)
        # Shot and explosion animation: one transparent overlay, above the worlds and below the HUD.
        self.fx = make_fx_layer(a, w, h)
        # The Overlord BMS power-up: hold ring, arrow back, sparks, callout and medallion. Under the crosshair.
        self.bms = make_bms_layer(a, w)
        self.muzzle = (w / 2, h - MUZZLE_Y_FROM_BOTTOM)
        self.cross = Crosshair(a, asset("bar_green.png"), asset("bar_white.png"))

        # Battery meter (twenty slanted cells) with LVL n beside it. The level's NAME is not shown here, only announced when it starts.
        self.hud = make_hud(a)  # a small widget at the top-left, not the whole game area

        self.score_label = Label(a, "0", w - 305, 14, 28, WHITE, width=200, alignment="right")  # ends at x=535, clear of the home button
        # TextBox color is only documented as a constructor argument, so keep one banner per color.
        self.banners = {
            color: Label(a, " ", int(w / 2 - 200), 96, 28, color, width=400, alignment="center")
            for color in (WHITE, CYAN, GOLD, PINK)
        }
        for banner in self.banners.values():
            banner.show(False)
        # Pointers toward the closest off-screen Rogue World (blue) and crystal or chip (gold).
        self.planet_arrow = make_arrow(a, CYAN_RGB)
        self.crystal_arrow = make_arrow(a, GOLD_RGB)

        if self.debug:
            self._build_debug()

    # ----- debug display -----------------------------------------------------
    def _build_debug(self) -> None:
        """A small panel at the bottom-left: mic level against the fire threshold, IMU, gaze."""
        a, h = self.app, self.screen_h
        x, y = 28, h - 118
        self.dbg_mic = Label(a, "MIC", x, y, 16, WHITE, width=420)
        self.dbg_bar_y, self.dbg_bar_w = y + 26, 220
        self.dbg_fill = Bar(a, asset("bar_cyan.png"), 4, 12)
        self.dbg_hot = Bar(a, asset("bar_pink.png"), 4, 12)
        scale = self.dbg_bar_w / C.DEBUG_MIC_FULL_SCALE
        # Markers: gold = fires above this, white = re-arms below this.
        Bar(a, asset("bar_gold.png"), 4, 20).set_rect(x + C.VOICE_HI * scale, self.dbg_bar_y - 4, 4, 20)
        Bar(a, asset("bar_white.png"), 4, 20).set_rect(x + C.VOICE_LO * scale, self.dbg_bar_y - 4, 4, 20)
        self.dbg_imu = Label(a, "IMU", x, y + 46, 16, WHITE, width=560)
        self.dbg_gaze = Label(a, "GAZE", x, y + 68, 16, WHITE, width=560)
        self._dbg_last_fire = 0.0

    def _update_debug(self, level: Optional[float], fired: bool, now: float) -> None:
        if not self.debug:
            return
        x = 28
        if fired:
            self._dbg_last_fire = now
        shown = level or 0.0
        width = max(4, int(self.dbg_bar_w * min(1.0, shown / C.DEBUG_MIC_FULL_SCALE)))
        hot = now - self._dbg_last_fire < 0.4
        (self.dbg_hot if hot else self.dbg_fill).set_rect(x, self.dbg_bar_y, width, 12)
        (self.dbg_fill if hot else self.dbg_hot).hide()
        self.dbg_mic.set(
            f"MIC {shown:0.3f}  fires > {C.VOICE_HI:0.2f}  [{self.inputs.mic_status}]" + ("  PEW!" if hot else "")
        )
        if self._tick_count % 3 == 0:  # the text changes constantly; repaint it a few times a second
            self.dbg_imu.set(
                f"IMU {self.imu_source}   yaw {self.head.yaw:5.1f}   pitch {self.head.pitch:5.1f}"
                + (f"   signs yaw {self._effective_sign('yaw'):+.0f} pitch {self._effective_sign('pitch'):+.0f}   keys: C center  Y/P flip" if self.imu_source == "mac" else "")
            )
            mode = "mouse" if self.simulated else "eye"
            where = "centered" if not self.gaze.confident else "following"
            self.dbg_gaze.set(f"GAZE {mode}  {where}  head-only aim: {'no' if self.gaze.confident else 'yes'}")

    # ----- simulator input ---------------------------------------------------
    def _on_mouse(self, x: float, y: float) -> None:
        """The cursor moved to (x, y) in this widget's coordinates; keep it in game-area pixels."""
        self._mouse = (x - self.app.x(), y - self.app.y())
        self._mouse_at = time.monotonic()

    def keyPressEvent(self, event) -> None:
        if not self.handle_key(event.text().lower()):
            super().keyPressEvent(event)

    def handle_key(self, key: str) -> bool:
        """C recenters the view; Y / P flip the Mac IMU's yaw / pitch while you find the right signs."""
        if key in ("space", " ", "return", "enter") and self._acknowledge_from_key():
            pass
        elif key == "c" and getattr(self, "head", None):
            self.head.recenter()
        elif key in ("y", "p") and self.imu_source == "mac":
            axis = "yaw" if key == "y" else "pitch"
            self._flip[axis] = -self._flip[axis]
            print(
                f"[overblaster] mac imu {axis} flipped. To keep it, set "
                f"MAC_{axis.upper()}_SIGN = {self._effective_sign(axis):+.1f} in config.py"
            )
        else:
            return False
        return True

    def _acknowledge_from_key(self) -> bool:
        g = getattr(self, "game", None)
        if g is None or not g.awaiting_ack or self._pause_t0 is None:
            return False
        if time.monotonic() - self._pause_t0 < screens.ACK_MIN_S:
            return False
        g.acknowledge()
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
    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(max(now - self._last, 0.001), 0.25)  # clamp after a stall
        self._last = now
        g = self.game

        self._tick_count += 1
        head_az, head_el = self.head.update(self._read_imu(), dt)
        cx, cy = self.gaze.update(self._read_gaze())
        off_x, off_y = pixels_to_degrees(cx, cy, self.screen_w, self.screen_h)
        aim_az, aim_el = crosshair_bearing(head_az, head_el, off_x, off_y)

        g.set_view(head_az, head_el)
        level = self.sound.gate(self.inputs.mic_level())  # the game's own sound is taken out of what the mic heard
        fired = self.voice.update(level)
        if g.awaiting_ack or self._pause_t0 is not None:
            # Sound is ignored until the gate opens, and then only a fresh sound counts: a "Pew"
            # still ringing from the level (or held the whole time) must not skip the plate.
            gate_open = self._pause_t0 is not None and now - self._pause_t0 >= screens.ACK_MIN_S
            if not gate_open or not fired:
                self._ack_armed = gate_open
            elif self._ack_armed and g.awaiting_ack:
                g.acknowledge()
        elif fired:
            g.shoot(aim_az, aim_el)
        g.update(dt, aim_az, aim_el)

        self._show_events(g.take_events(), dt)
        if g.state is State.LOST:
            self._death_t += dt
        self._render(head_az, head_el, cx, cy)
        self._update_debug(level, fired, now)
        if g.state is State.LOST and self._death_t >= (DEATH_S if g.lost_cause == "hull" else BATTERY_DEATH_S):
            self.show_game_over()

    def _show_events(self, events: List[str], dt: float) -> None:
        self._banner_left = max(0.0, self._banner_left - dt)
        g, now = self.game, time.monotonic()
        for e in events:
            if e == "level_clear":
                # Collecting the BMS usually clears the level too: let its callout have the screen first.
                award = self._award_t()
                self._pause_t0 = now + (max(0.0, bms.SETTLE_S - award) if award is not None else 0.0)
                self._pause_level = g.level
                self._splash_t0 = None  # a level cleared in seconds: its splash gives way to the plate
                self.splash.place(0, 0, screens.SPLASH_END)
            elif e.startswith("level:"):
                n = int(e.split(":")[1])
                self.sound.sfx("level_start")
                self.sound.say(*voicelines.level_intro(n))
                self._plate_voiced = 0
                self._pause_t0 = None
                self.pause.clear()
                # The splash is pinned to a spot in the sky just above where the player looks now, so they can turn away from it.
                self.splash.start(n, C.level_name(n))
                self._splash_at = (g.view_az, g.view_el + screens.SPLASH_EL_OFFSET)
                self._splash_t0 = now
            elif e == "chip":
                self.sound.sfx("chip_collect")
                self.sound.say("chip_found")
                self._award_t0 = now
                at = project(g.chip_at[0], g.chip_at[1], g.view_az, g.view_el, self.screen_w, self.screen_h, margin=400)
                self.bms.begin_award((at.x, at.y))
            elif e == "hit":
                self.sound.sfx("hit")
            elif e == "destroyed":
                self.sound.sfx("explode")
            elif e == "crystal":
                self.sound.sfx("crystal")
            elif e == "hull_destroyed":
                self.sound.sfx("hull_death")
                self.sound.say("hull_destroyed")
                self._flash(*FIXED_BANNERS[e])
            elif e == "lost":
                self.sound.sfx("battery_dead")
                self.sound.say("battery_dead")
            elif e in FIXED_BANNERS:
                self._flash(*FIXED_BANNERS[e])
        if self._banner_left <= 0:
            for banner in self.banners.values():
                banner.show(False)

    def _flash(self, text: str, color: str) -> None:
        for c, banner in self.banners.items():
            banner.show(c == color)
        self.banners[color].set(text)
        self._banner_left = BANNER_SECONDS

    # ----- rendering -------------------------------------------------------
    def _render(self, head_az: float, head_el: float, cx: float, cy: float) -> None:
        g, w, h = self.game, self.screen_w, self.screen_h

        # Rogue Worlds: bind a pooled sprite to each live world, release the dead ones.
        live = {id(world): world for world in g.worlds}
        for wid in [i for i in self._bound if i not in live]:
            sprite = self._bound.pop(wid)
            sprite.hide()
            self._free.append(sprite)
        for wid, world in live.items():
            if wid not in self._bound:
                if not self._free:
                    continue
                self._bound[wid] = self._free.pop()
            sprite = self._bound[wid]
            size = size_class(world.radius, w)
            sprite.set_media(world_gif("chip" if world.chip_carrier else world.kind, size), size)
            p = project(world.az, world.el, head_az, head_el, w, h, margin=size / 2)
            if p.on_screen:
                sprite.place(p.x, p.y)
            else:
                sprite.hide()

        # Crystals and the chip.
        self.crystals.begin_frame()
        self.chip.begin_frame()
        hold = None  # the Overlord BMS on screen: where it is and how far the hold has got
        for c in g.crystals:
            p = project(c.az, c.el, head_az, head_el, w, h, margin=32)
            if not p.on_screen:
                continue
            sprite = (self.chip if c.is_chip else self.crystals).next()
            if sprite:
                sprite.place(p.x, p.y)
            if c.is_chip:
                hold = (p.x, p.y, c.progress, c.on_target, (cx, cy))
                self._chip_sounds(c)
        self.crystals.end_frame()
        self.chip.end_frame()

        # Shot and explosion animation.
        ppd = pixels_per_degree(w)
        shapes = []
        for shot in g.shots:
            at = project(shot.az, shot.el, head_az, head_el, w, h, margin=400)
            shapes += shot_shapes(shot.kind, shot.age, self.muzzle, (at.x, at.y), shot.radius_deg * ppd)
        if g.state is State.LOST and g.lost_cause == "hull" and g.impact:
            az, el, radius = g.impact
            at = project(az, el, head_az, head_el, w, h, margin=400)
            shapes += death_shapes(self._death_t, (at.x, at.y), radius * ppd, w, h)
        self.fx.set_shapes(shapes)

        self._update_screens(head_az, head_el)
        self._battery_sounds()
        self.bms.set_state(hold, self._award_t(), time.monotonic())
        self.cross.place(cx, cy)
        self._point_arrows(head_az, head_el)
        self._update_hud()

    def _chip_sounds(self, c) -> None:
        """The voice announces the chip when it first appears, and rising ticks mark the hold filling."""
        if id(c) != self._chip_seen_id:
            self._chip_seen_id, self._chip_tick = id(c), 0
            self.sound.say("chip_seen")
        k = min(synth.CHARGE_TICKS, int(c.progress * synth.CHARGE_TICKS))
        if c.on_target:
            while self._chip_tick < k:
                self.sound.sfx(f"charge_{self._chip_tick}")
                self._chip_tick += 1

    def _battery_sounds(self) -> None:
        g = self.game
        p = g.battery_fraction
        if g.state is State.LOST:
            return
        if p < hudgeo.LOW and not self._was_low:
            self._was_low = True
            self.sound.sfx("low_battery")
            self.sound.say("battery_low")
        elif p >= hudgeo.LOW + 0.1:
            self._was_low = False

    def _award_t(self) -> Optional[float]:
        return None if self._award_t0 is None else time.monotonic() - self._award_t0

    def _update_screens(self, head_az: float, head_el: float) -> None:
        g, w, h, now = self.game, self.screen_w, self.screen_h, time.monotonic()
        if self._pause_t0 is not None and now >= self._pause_t0 and g.state is not State.LOST:
            if self._plate_voiced == 0:  # the plate has just appeared
                self._plate_voiced = 1
                self.sound.sfx("level_clear")
                self.sound.say("level_clear")
            elif self._plate_voiced == 1 and now - self._pause_t0 >= screens.COUNT_S + 0.2:
                self._plate_voiced = 2
                self.sound.say("continue")
            p = g.battery_fraction
            self.pause.set(self._pause_level, g.score, hudgeo.lit_cells(p), hudgeo.tone(p, g.chip_collected), now - self._pause_t0)
        if self._splash_t0 is not None:
            t = now - self._splash_t0
            at = project(self._splash_at[0], self._splash_at[1], head_az, head_el, w, h, margin=400)
            self.splash.place(at.x, at.y, t)
            if t >= screens.SPLASH_END:
                self._splash_t0 = None

    def _point_arrows(self, head_az: float, head_el: float) -> None:
        """Aim the blue arrow at the closest Rogue World and the gold one at the closest crystal.

        Each is a full 360 degree pointer that turns with your head and sits on a ring around the
        view. It appears only while its target is out of view: once you can see it, it needs no arrow.
        """
        g, w, h = self.game, self.screen_w, self.screen_h
        for arrow, targets, overhang in (
            (self.planet_arrow, g.worlds, lambda world: size_class(world.radius, w) / 2),  # drawn size
            (self.crystal_arrow, g.crystals, lambda crystal: 32),
        ):
            target = closest(targets, head_az, head_el) if g.state is not State.LOST else None
            if target is None:
                arrow.clear()
                continue
            p = pointer(target.az, target.el, head_az, head_el, w, h, POINTER_RING, overhang(target))
            if p.on_screen:
                arrow.clear()
            else:
                arrow.point(p.x, p.y, p.angle)

    def _update_hud(self) -> None:
        g = self.game
        level = max(g.level, 1)  # the opening pause is level 0 inside; the HUD should already say LVL 1
        t = self._award_t()
        badge = bms.callout(t).badge_u if t is not None else (1.0 if g.chip_collected else 0.0)
        self.hud.set_state(g.battery_fraction, g.chip_collected, level, time.monotonic(), badge)
        self.score_label.set(str(g.score))
