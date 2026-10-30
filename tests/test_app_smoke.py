"""Drive the real OverBlasterApp against fake Raven widgets (see fake_raven.py).

This does NOT prove the real framework behaves the same; it proves our code is
internally consistent: screens flow, the tick loop runs, and the widget pool is
fixed during play.
"""

import importlib
import sys

import pytest

import fake_raven
from overblaster import config as C

DT = C.TICK_MS / 1000.0


class FakeInputs:
    def __init__(self):
        self.gyro_yaw = 0.0
        self.mic = 0.0
        self.gaze_pos = None
        self.closed = 0
        self.mic_status = "listening"

    def imu(self):
        gyro = [0.0, 0.0, 0.0]
        gyro[C.GYRO_YAW_AXIS] = self.gyro_yaw
        return {"accelerometer": (0.0, 0.0, 9.8), "gyroscope": tuple(gyro), "magnetometer": (0, 0, 0)}

    def gaze(self):
        return self.gaze_pos

    def mic_level(self):
        return self.mic

    def close(self):
        self.closed += 1


def hold_the_voice(monkeypatch):
    """The voice mutes the mic while it speaks, which would get in the way of the older tests that
    fire right after a level starts (and with no sound card nothing advances the mixer, so it would
    speak forever). Voice clips are logged but not played unless a test sets `sound.mixer.hear_voice`."""
    from overblaster import audio

    real_play = audio.Mixer.play

    def play(self, x, gain=1.0, voice=False):
        if voice and not getattr(self, "hear_voice", False):
            return
        real_play(self, x, gain, voice)

    monkeypatch.setattr(audio.Mixer, "play", play)


@pytest.fixture
def app(monkeypatch):
    hold_the_voice(monkeypatch)
    fake_raven.install()
    for mod in [m for m in sys.modules if m.startswith("overblaster.ui") or m.startswith("overblaster.app")]:
        del sys.modules[mod]
    app_mod = importlib.import_module("overblaster.app")
    clock = {"t": 1000.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    inputs = FakeInputs()
    instance = app_mod.OverBlasterApp(inputs=inputs, simulated=False)
    instance._clock, instance._inputs = clock, inputs
    return instance


def tick(app, n=1):
    for _ in range(n):
        app._clock["t"] += DT
        fake_raven.ROUTINES[-1].invoke()


def button(app, text):
    return next(w for w in app.app.children if isinstance(w, fake_raven.Button) and w.text == text)


def crosshair_center(app):
    dot = app.cross.sprites[-1]  # the center dot
    return dot.widget.pos[0] + dot.w / 2, dot.widget.pos[1] + dot.h / 2


def test_title_screen_has_launch_button_and_no_routine(app):
    assert button(app, "LAUNCH")
    assert not fake_raven.ROUTINES


def test_launch_builds_scene_and_starts_the_tick_loop(app):
    button(app, "LAUNCH").click()
    assert fake_raven.ROUTINES[-1].interval_ms == C.TICK_MS
    assert app.game is not None
    tick(app, 40)  # leaves the intermission, spawns level 1
    assert app.game.level == 1 and app.game.worlds


def test_no_widgets_are_created_while_playing(app):
    button(app, "LAUNCH").click()
    tick(app, 5)
    created = len(fake_raven.CREATED)
    app._inputs.gyro_yaw = 30.0  # sweep the view around
    tick(app, 300)
    assert len(fake_raven.CREATED) == created


def test_worlds_get_sprites_and_unused_sprites_are_hidden_and_paused(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    assert len(app._bound) == len(app.game.worlds) > 0
    bound = list(app._bound.values())
    for sprite in app._free:
        assert not sprite.visible
    for sprite in app._free + [s for s in bound if not s.visible]:
        assert sprite.widget.paused, "a hidden GIF keeps decoding frames and burns battery"


def test_world_sprites_show_the_right_gif_and_are_never_resized(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    for wid, sprite in app._bound.items():
        world = next(w for w in app.game.worlds if id(w) == wid)
        kind = "chip" if world.chip_carrier else world.kind
        assert sprite.widget.media_path.endswith(f"world_{kind}_{sprite.w}.gif")
        assert sprite.w in C.WORLD_BANDS and sprite.widget.corner_radius == sprite.w // 2


def test_bound_sprites_stay_inside_the_display_when_visible(app):
    button(app, "LAUNCH").click()
    tick(app, 100)
    for sprite in app._bound.values():
        if sprite.visible:
            x, y = sprite.widget.pos
            assert -sprite.w <= x <= app.screen_w and -sprite.h <= y <= app.screen_h


def test_loud_sound_fires_and_costs_battery(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    app.game.worlds[:] = [fake_world(app, hp=1000)]  # a target that survives
    app.game.crystals.clear()
    before = app.game.charge
    app._inputs.mic = 0.9
    tick(app, 1)
    assert app.game.charge == pytest.approx(before - C.SHOT_COST)


def test_a_sustained_sound_is_sustained_fire_at_ten_shots_a_second_and_stops_with_the_sound(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    app.game.worlds[:] = [fake_world(app, hp=100000)]
    app.game.charge = app.game.capacity = 1e9
    start = app.game.charge
    app._inputs.mic = 0.5
    tick(app, 30)  # two seconds of "pewwwww"
    shots = (start - app.game.charge) / C.SHOT_COST
    assert shots == pytest.approx(20, abs=3), shots
    app._inputs.mic = 0.0
    tick(app, 1)
    used = app.game.charge
    tick(app, 15)
    assert app.game.charge == used  # silence: no more shots


def test_the_hud_is_the_cell_meter_and_lvl_n_with_no_other_words(app):
    button(app, "LAUNCH").click()
    tick(app, 3)
    m = app.hud.model
    assert len(m.cells) == 20
    assert min(y for c in m.cells for _, y in c.points) <= 10  # right at the top of the screen
    assert [t.text for t in m.texts] == ["LVL 1"]
    right_of_meter = max(x for c in m.cells for x, _ in c.points)
    assert m.caption.x > right_of_meter
    words = " ".join(texts(app))
    assert "ENERGY" not in words.upper() and "%" not in words
    assert not any(t.startswith("LEVEL ") and t[6:].isdigit() for t in texts(app))  # the old "LEVEL 1" label is gone


def test_the_cells_follow_the_battery(app):
    from overblaster import hud

    button(app, "LAUNCH").click()
    tick(app, 3)
    for charge in (100.0, 78.0, 50.0, 12.0):
        app.game.charge = charge
        tick(app, 1)
        lit = [c.lit for c in app.hud.model.cells].count(True)
        assert lit == hud.lit_cells(app.game.battery_fraction), charge
    assert [c.lit for c in app.hud.model.cells].count(True) == 3  # 12 of 100 units is 2.4 cells, rounded up


def test_the_meter_is_magenta_when_low_and_gold_once_the_chip_has_doubled_the_battery(app):
    from overblaster import hud

    button(app, "LAUNCH").click()
    tick(app, 3)
    assert app.hud.model.tone == hud.CYAN and app.hud.model.pill is None
    app.game.charge = 10.0
    tick(app, 1)
    assert app.hud.model.tone == hud.PINK
    app.game.chip_collected = True
    app.game.capacity = app.game.charge = 200.0
    tick(app, 1)
    assert app.hud.model.tone == hud.GOLD and app.hud.model.pill is not None


def all_visible_text(app):
    """Every piece of text actually on screen: shown text boxes, and banners that are currently shown."""
    plain = [w.text for w in app.app.children if isinstance(w, fake_raven.TextBox) and w.shown]
    return plain + [b.widget.text for b in app.banners.values() if b.widget.shown]


def test_the_hud_already_says_lvl_1_during_the_opening_pause(app):
    button(app, "LAUNCH").click()
    tick(app, 1)  # the game is still in its half-second opening intermission (level 0 inside)
    assert app.game.level == 0
    assert app.hud.model.caption.text == "LVL 1"


def test_the_hud_always_shows_the_current_level_number(app):
    button(app, "LAUNCH").click()
    tick(app, 12)  # past the opening pause: the game is playing
    assert app.game.state.value == "playing"
    for level in (1, 2, 7, 12, 30):
        app.game.level = level
        tick(app, 1)
        assert app.hud.model.caption.text == f"LVL {level}"


def test_the_level_start_splash_appears_for_a_couple_of_seconds_and_goes_away(app):
    from overblaster import screens

    button(app, "LAUNCH").click()
    assert not app.splash.shown and app.splash.model is None  # not before the level starts
    tick(app, 12)  # the first level starts after half a second
    assert app.splash.shown and app.splash.model.name.text == C.level_name(1) and app.splash.model.number.text == "1"
    tick(app, 20)  # well inside the hold
    assert app.splash.shown
    tick(app, int(screens.SPLASH_END * 15) + 5)
    assert not app.splash.shown
    assert app.hud.model.caption.text == "LVL 1"  # while the HUD's number stays
    assert not any(C.level_name(1) in t for t in all_visible_text(app))  # and no text banner carries the name


def test_each_new_level_gets_its_own_splash(app):
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    for level in (2, 3, 5, 9):
        app.game.worlds.clear()
        app.game.crystals.clear()
        app.game.level = level - 1
        app.game.state = State.INTERMISSION
        app.game._intermission_left = 0.0  # the pause is over...
        app.game.acknowledge()  # ...and acknowledged: the next level starts on the next tick
        tick(app, 2)
        assert app.game.level == level
        assert app.splash.shown and app.splash.model.number.text == str(level) and app.splash.model.name.text == C.level_name(level)
        assert app.hud.model.caption.text == f"LVL {level}"
        tick(app, 110)  # past the splash's 6.8 s
        assert not app.splash.shown


def test_the_splash_stays_put_in_the_sky_while_the_head_turns(app):
    button(app, "LAUNCH").click()
    tick(app, 12)
    x0, y0 = app.splash.pos
    assert 300 < x0 < 340 and y0 < 220  # centred, above the crosshair
    app._inputs.gyro_yaw = 40.0  # turn the head
    tick(app, 6)
    x1, y1 = app.splash.pos
    assert app.splash.shown and abs(x1 - x0) > 40 and y1 == pytest.approx(y0, abs=2)  # it slid across the view and stayed at its height


def test_the_between_levels_plate_shows_while_the_next_level_waits_and_then_goes(app):
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    assert not app.pause.shown
    app.game.worlds.clear()
    app.game.crystals.clear()
    app.game.score = 12480
    tick(app, 2)  # nothing left to destroy or harvest: the level is clear
    assert app.game.state is State.INTERMISSION and app.pause.shown
    tick(app, 20)  # past the count-up
    m = app.pause.model
    assert m.score.text == "12,480"
    assert {"SECTOR CLEARED", f"LVL {app.game.level + 1}", C.level_name(app.game.level + 1)} <= {t.text for t in m.texts}
    tick(app, 900)  # a minute of the player reading it
    assert app.game.state is State.INTERMISSION and app.pause.shown and app.game.awaiting_ack
    app._inputs.mic = 0.9  # "Pew"
    tick(app, 2)
    app._inputs.mic = 0.0
    tick(app, 3)
    assert app.game.state is State.PLAYING and not app.pause.shown
    assert app.splash.shown  # and its splash has taken over


def test_a_pew_during_the_count_up_does_not_skip_the_plate(app):
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    app.game.worlds.clear()
    app.game.crystals.clear()
    tick(app, 2)
    assert app.game.state is State.INTERMISSION
    app._inputs.mic = 0.9  # the player was still shooting when the last world died
    tick(app, 8)  # about half a second in, and the minimum pause is not over
    assert app.pause.shown and app.game.state is State.INTERMISSION
    app._inputs.mic = 0.0


def test_a_pew_held_through_the_gate_never_acknowledges_but_a_fresh_one_does(app):
    from overblaster import screens
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    app.game.worlds.clear()
    app.game.crystals.clear()
    tick(app, 2)
    app._inputs.mic = 0.9  # still saying it from the level, and never stops
    tick(app, int((screens.ACK_MIN_S + 3) * 15))
    assert app.game.state is State.INTERMISSION and app.pause.shown
    app._inputs.mic = 0.0
    tick(app, 3)  # quiet: now the next sound counts
    app._inputs.mic = 0.9
    tick(app, 3)
    app._inputs.mic = 0.0
    tick(app, 3)
    assert app.game.state is State.PLAYING


def test_the_gate_is_a_full_second_after_the_score_settles():
    from overblaster import screens

    assert screens.ACK_MIN_S >= screens.COUNT_S + 1.0


def test_the_space_key_also_acknowledges_the_plate(app):
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    app.game.worlds.clear()
    app.game.crystals.clear()
    tick(app, 2)
    assert app.handle_key("space") is False  # too early: the plate has only just appeared
    tick(app, 50)
    assert app.game.awaiting_ack and app.handle_key("space")
    tick(app, 3)
    assert app.game.state is State.PLAYING


def test_the_score_ends_clear_of_the_home_button(app):
    button(app, "LAUNCH").click()
    tick(app, 3)
    label = app.score_label.widget
    assert label.pos[0] + label.kw["width"] == 535  # the home button starts at x=547


def test_confident_gaze_moves_the_crosshair_and_noise_does_not(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    app._inputs.gaze_pos = (500, 200)
    tick(app, 12)
    assert app.gaze.confident
    x, y = crosshair_center(app)
    assert abs(x - 500) < 25 and abs(y - 200) < 25

    for i in range(12):
        app._inputs.gaze_pos = (100 + (i % 2) * 300, 200)
        tick(app, 1)
    assert not app.gaze.confident
    x, y = crosshair_center(app)
    assert abs(x - 320) < 2 and abs(y - 320) < 2


def test_wasting_battery_reaches_game_over_and_retry_restarts(app):
    button(app, "LAUNCH").click()
    for i in range(600):
        app._inputs.mic = 0.9 if i % 2 == 0 else 0.0  # "pew" every other tick, never harvesting
        tick(app, 1)
        if fake_raven.ROUTINES[-1].stopped:
            break
    assert app.game.state.value == "lost"
    assert fake_raven.ROUTINES[-1].stopped
    assert app._inputs.closed >= 1
    button(app, "Retry").click()
    assert not fake_raven.ROUTINES[-1].stopped and app.game.score == 0 and app.game.level == 0


def test_title_button_returns_to_the_title(app):
    button(app, "LAUNCH").click()
    tick(app, 3)
    app.show_title()
    assert fake_raven.ROUTINES[-1].stopped
    assert button(app, "LAUNCH")


# --- simulator behavior (what you see when you run main.py on the Mac) -------------------
class FakeMac:
    """Stands in for MacImuSensor: a laptop lying flat that is being turned at `yaw` deg/s."""

    error = None

    def __init__(self):
        self.yaw, self.fresh_now = 0.0, True

    def start(self):
        return True

    def reading(self):
        if not self.fresh_now:
            return None
        return {
            "accelerometer": {"x": 0.0, "y": 0.0, "z": -9.8},
            "gyroscope": {"x": 0.0, "y": 0.0, "z": self.yaw},
            "magnetometer": {"x": 0, "y": 0, "z": 0},
        }


@pytest.fixture
def sim_app(monkeypatch):
    hold_the_voice(monkeypatch)
    fake_raven.install()
    for mod in [m for m in sys.modules if m.startswith("overblaster.ui") or m.startswith("overblaster.app")]:
        del sys.modules[mod]
    app_mod = importlib.import_module("overblaster.app")
    clock = {"t": 1000.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    inputs, mac = FakeInputs(), FakeMac()
    instance = app_mod.OverBlasterApp(inputs=inputs, simulated=True, mac_imu=mac, debug=True)
    instance.app.origin = (40, 50)  # the real game area sits inside a 720 px window
    instance._clock, instance._inputs, instance._mac = clock, inputs, mac
    return instance


def test_there_is_no_pew_button_only_the_microphone_fires(sim_app):
    button(sim_app, "LAUNCH").click()
    tick(sim_app, 5)
    texts = [w.text for w in sim_app.app.children if isinstance(w, fake_raven.Button)]
    assert "PEW" not in texts and "Pew" not in texts
    tick(sim_app, 40)
    before = sim_app.game.charge
    sim_app._inputs.mic = 0.5
    tick(sim_app, 1)
    assert sim_app.game.charge == before - C.SHOT_COST


def test_the_mouse_moves_the_crosshair_in_game_area_pixels(sim_app):
    button(sim_app, "LAUNCH").click()
    tick(sim_app, 5)
    sim_app._on_mouse(40 + 500, 50 + 200)  # window coords: 40, 50 is the area's corner
    tick(sim_app, 1)
    x, y = crosshair_center(sim_app)
    assert (x, y) == pytest.approx((500, 200), abs=2), "the crosshair should sit under the mouse"
    assert sim_app.gaze.confident


def test_a_fast_mouse_sweep_still_moves_the_crosshair(sim_app):
    button(sim_app, "LAUNCH").click()
    tick(sim_app, 5)
    for i, x in enumerate(range(100, 560, 80)):  # 80 px per tick: "jitter" to the eye filter
        sim_app._on_mouse(40 + x, 50 + 300)
        tick(sim_app, 1)
    assert crosshair_center(sim_app)[0] > 400


def test_a_mouse_outside_the_game_area_falls_back_to_center(sim_app):
    button(sim_app, "LAUNCH").click()
    tick(sim_app, 5)
    sim_app._on_mouse(10, 10)  # in the margin, left of the game area
    tick(sim_app, 1)
    assert crosshair_center(sim_app) == pytest.approx((320, 320), abs=2)


def test_the_mac_imu_steers_and_falls_back_to_the_arrow_keys_when_it_stops(sim_app):
    button(sim_app, "LAUNCH").click()
    sim_app._mac.yaw = 90.0
    tick(sim_app, 15)  # one second
    assert sim_app.imu_source == "mac"
    assert sim_app.head.yaw == pytest.approx((90 * C.MAC_YAW_SIGN) % 360, abs=3)
    sim_app._mac.fresh_now = False
    tick(sim_app, 2)
    assert sim_app.imu_source == "keys" and sim_app.head.sim


def test_keys_flip_the_mac_axes_and_recenter(sim_app):
    button(sim_app, "LAUNCH").click()
    sim_app._mac.yaw = 90.0
    tick(sim_app, 15)
    first = sim_app.head.yaw
    assert sim_app.handle_key("c") and sim_app.head.yaw == 0.0  # C recenters
    assert sim_app.handle_key("y")  # Y flips yaw
    tick(sim_app, 15)
    flipped = sim_app.head.yaw
    assert flipped == pytest.approx((360 - first) % 360, abs=3)
    assert not sim_app.handle_key("x")  # unknown keys fall through to the framework


def test_debug_panel_shows_the_live_mic_level_against_the_threshold(sim_app):
    button(sim_app, "LAUNCH").click()
    tick(sim_app, 3)
    sim_app._inputs.mic = 0.2
    tick(sim_app, 1)
    text = sim_app.dbg_mic.widget.text
    assert "0.200" in text and f"{C.VOICE_HI:0.2f}" in text
    sim_app._inputs.mic = 0.0
    tick(sim_app, 1)
    assert "0.000" in sim_app.dbg_mic.widget.text


def test_debug_panel_is_off_on_the_glasses(app):
    button(app, "LAUNCH").click()
    tick(app, 3)
    assert not hasattr(app, "dbg_mic")


# --- gaze on the glasses: eye tracker first, the cursor as a fallback ---------------------
def test_on_the_glasses_the_eye_tracker_wins_over_the_cursor(app):
    app.app.origin = (40, 50)  # the real game area's offset inside the window
    button(app, "LAUNCH").click()
    app._on_mouse(40 + 100, 50 + 100)
    app._inputs.gaze_pos = (400, 300)
    assert app._read_gaze() == (400, 300)


def test_on_the_glasses_a_moving_cursor_stands_in_when_the_eye_tracker_reports_nothing(app):
    app.app.origin = (40, 50)  # the real game area's offset inside the window
    button(app, "LAUNCH").click()
    app._inputs.gaze_pos = None
    app._on_mouse(40 + 250, 50 + 180)
    assert app._read_gaze() == (250, 180)


def test_on_the_glasses_a_parked_cursor_is_not_a_gaze(app):
    app.app.origin = (40, 50)  # the real game area's offset inside the window
    button(app, "LAUNCH").click()
    app._inputs.gaze_pos = None
    app._on_mouse(40 + 250, 50 + 180)
    app._clock["t"] += 1.0  # the cursor hasn't moved for a second
    assert app._read_gaze() is None


def test_in_the_simulator_a_resting_mouse_still_aims(sim_app):
    button(sim_app, "LAUNCH").click()
    sim_app._on_mouse(40 + 250, 50 + 180)
    sim_app._clock["t"] += 30.0  # hasn't moved for 30 s: a resting mouse is still where you aim
    assert sim_app._read_gaze() == (250, 180)


def test_flipping_an_axis_reports_the_sign_to_put_in_config(sim_app, capsys):
    button(sim_app, "LAUNCH").click()
    sim_app._mac.yaw = 90.0
    tick(sim_app, 2)  # the Mac IMU becomes the source
    assert sim_app.handle_key("y")
    out = capsys.readouterr().out
    assert f"MAC_YAW_SIGN = {-C.MAC_YAW_SIGN:+.1f}" in out, out  # the sign now in effect, not just "flipped"
    assert sim_app.handle_key("p")
    assert f"MAC_PITCH_SIGN = {-C.MAC_PITCH_SIGN:+.1f}" in capsys.readouterr().out
    tick(sim_app, 3)
    assert f"yaw {-C.MAC_YAW_SIGN:+.0f}" in sim_app.dbg_imu.widget.text  # and the panel shows it too


# --- shot animation and the end of the game ---------------------------------------------------
def texts(app):
    return [w.text for w in app.app.children if isinstance(w, fake_raven.TextBox)]


def start_playing(app):
    button(app, "LAUNCH").click()
    tick(app, 40)
    app.game.crystals.clear()


def test_firing_draws_a_laser_from_the_ships_nose_and_it_goes_away(app):
    from overblaster import fx

    start_playing(app)
    app._inputs.mic = 0.9
    tick(app, 1)
    drawn = app.fx.shapes
    beams = [s for s in drawn if isinstance(s, fx.Line) and (s.x1, s.y1) == app.muzzle]
    assert beams, "no laser was drawn after firing"
    assert app.muzzle[0] == app.screen_w / 2 and app.muzzle[1] > app.screen_h * 0.85  # the ship's nose
    app._inputs.mic = 0.0
    tick(app, 12)  # about 0.8 s
    assert app.fx.shapes == []  # nothing left to repaint


def test_a_kill_draws_an_explosion_where_the_world_was(app):
    from overblaster import fx

    start_playing(app)
    app.game.worlds[:] = [fake_world(app, hp=1)]
    app._inputs.mic = 0.9
    tick(app, 1)
    rings = [s for s in app.fx.shapes if isinstance(s, fx.Circle) and s.width >= 5]
    assert rings, "no shockwave after destroying a world"


def fake_world(app, hp):
    from overblaster.game import World

    return World(az=app.game.view_az, el=app.game.view_el, az_v=0, el_v=0, progress=0.5, speed=0, hp=hp, kind="a")


def test_a_world_hitting_the_ship_plays_a_death_sequence_then_the_game_over_screen(app):
    from overblaster import fx
    from overblaster.game import World

    start_playing(app)
    app.game.worlds[:] = [World(az=10, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a")]
    tick(app, 1)
    assert app.game.state.value == "lost" and app.game.lost_cause == "hull"
    assert not fake_raven.ROUTINES[-1].stopped, "the game over screen came before the explosion"
    assert any(isinstance(s, fx.Rect) and s.color == fx.RED for s in app.fx.shapes)  # the red flash
    banner_texts = [b.widget.text for b in app.banners.values() if b.widget.shown]
    assert "HULL DESTROYED" in banner_texts and "LEVEL CLEAR" not in banner_texts

    ticks_needed = int(fx.DEATH_S / (C.TICK_MS / 1000.0)) + 2
    tick(app, ticks_needed - 4)
    assert not fake_raven.ROUTINES[-1].stopped  # still exploding
    tick(app, 6)
    assert fake_raven.ROUTINES[-1].stopped
    shown = texts(app)
    assert "HULL DESTROYED" in shown and "A Rogue World hit your ship." in shown
    assert "BATTERY DEAD" not in shown


def test_running_out_of_battery_says_so_and_does_not_blame_the_hull(app):
    start_playing(app)
    app.game.charge = 0.0
    app.game.worlds[:] = [fake_world(app, hp=1)]  # nothing is about to hit the ship
    app.game.worlds[0].az = 200
    tick(app, 12)
    assert app.game.state.value == "lost" and app.game.lost_cause == "battery"
    shown = texts(app)
    assert "BATTERY DEAD" in shown and "You ran out of energy." in shown
    assert "HULL DESTROYED" not in shown


# --- the debug panel is opt-in --------------------------------------------------------------
def test_there_is_no_debug_text_unless_asked_for(monkeypatch):
    fake_raven.install()
    for mod in [m for m in sys.modules if m.startswith("overblaster.ui") or m.startswith("overblaster.app")]:
        del sys.modules[mod]
    app_mod = importlib.import_module("overblaster.app")
    clock = {"t": 1000.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    plain = app_mod.OverBlasterApp(inputs=FakeInputs(), simulated=True, mac_imu=FakeMac())  # a simulator run
    plain._clock = clock
    button(plain, "LAUNCH").click()
    for _ in range(5):
        clock["t"] += DT
        fake_raven.ROUTINES[-1].invoke()
    assert not plain.debug and not hasattr(plain, "dbg_mic") and not hasattr(plain, "dbg_imu")
    on_screen = " ".join(texts(plain))
    for word in ("MIC", "IMU", "GAZE", "fires >", "listening"):
        assert word not in on_screen


# --- the pointer arrows ---------------------------------------------------------------------
import math  # noqa: E402


def place_worlds(app, *specs):
    """Stationary worlds at (az, el); the game is already playing."""
    from overblaster.game import World

    app.game.crystals.clear()
    app.game.worlds[:] = [
        World(az=az, el=el, az_v=0, el_v=0, progress=0.3, speed=0, hp=3, kind="a") for az, el in specs
    ]


def arrow_deg(arrow):
    return math.degrees(arrow.angle)


def test_the_blue_arrow_points_right_at_a_world_off_to_the_right(app):
    start_playing(app)
    place_worlds(app, (60, 0))
    tick(app, 1)
    assert app.planet_arrow.visible
    assert arrow_deg(app.planet_arrow) == pytest.approx(0, abs=1)


def test_the_blue_arrow_points_any_way_round_up_down_and_diagonally(app):
    start_playing(app)
    for spec, expected in (((0, 40), -90), (((0, -40)), 90), ((40, 40), None), ((-40, -40), None)):
        place_worlds(app, spec)
        tick(app, 1)
        assert app.planet_arrow.visible, spec
        if expected is not None:
            assert arrow_deg(app.planet_arrow) == pytest.approx(expected, abs=3), spec
    place_worlds(app, (40, 40))  # up and to the right
    tick(app, 1)
    assert -90 < arrow_deg(app.planet_arrow) < 0
    place_worlds(app, (320, -40))  # down and to the left (320 is 40 degrees left of north)
    tick(app, 1)
    assert 90 < abs(arrow_deg(app.planet_arrow)) < 180 and arrow_deg(app.planet_arrow) > 0


def test_the_blue_arrow_sits_on_a_ring_clear_of_the_corners(app):
    start_playing(app)
    place_worlds(app, (60, 20))
    tick(app, 1)
    a = app.planet_arrow
    assert math.hypot(a.x - app.screen_w / 2, a.y - app.screen_h / 2) == pytest.approx(app.POINTER_RING if hasattr(app, "POINTER_RING") else 250, abs=0.5)


def test_the_arrow_follows_the_closest_world_not_just_any_world(app):
    start_playing(app)
    place_worlds(app, (150, 0), (-50, 0))  # one far to the right, a nearer one to the left
    tick(app, 1)
    assert abs(arrow_deg(app.planet_arrow)) == pytest.approx(180, abs=1)  # points left, at the closer
    place_worlds(app, (150, 0), (50, 0))  # now the nearer one is on the right
    tick(app, 1)
    assert arrow_deg(app.planet_arrow) == pytest.approx(0, abs=1)


def test_the_arrow_turns_as_the_head_turns(app):
    start_playing(app)
    place_worlds(app, (60, 0))
    tick(app, 1)
    assert arrow_deg(app.planet_arrow) == pytest.approx(0, abs=1)  # straight right
    app._inputs.gyro_yaw = 40.0  # turn the head toward it...
    tick(app, 20)
    app._inputs.gyro_yaw = 0.0
    tick(app, 1)
    assert not app.planet_arrow.visible or abs(arrow_deg(app.planet_arrow)) < 30  # ...and it faces it


def test_no_arrow_while_the_closest_world_is_already_in_view(app):
    start_playing(app)
    place_worlds(app, (3, 2), (150, 0))  # a world right in front, another far away
    tick(app, 1)
    assert not app.planet_arrow.visible


def test_no_arrow_when_there_are_no_worlds_or_after_losing(app):
    start_playing(app)
    place_worlds(app, (60, 0))
    tick(app, 1)
    assert app.planet_arrow.visible
    app.game.worlds.clear()
    tick(app, 1)
    assert not app.planet_arrow.visible
    from overblaster.game import State

    app.game.state = State.PLAYING  # clearing the field started a level-clear intermission
    place_worlds(app, (60, 0))
    app.game.worlds[0].progress, app.game.worlds[0].speed = 0.99, 1.0  # it hits the ship
    tick(app, 2)
    assert app.game.state.value == "lost" and not app.planet_arrow.visible


def test_the_gold_arrow_points_at_the_closest_crystal_independently(app):
    from overblaster.game import Crystal

    start_playing(app)
    place_worlds(app, (60, 0))
    app.game.crystals[:] = [Crystal(az=-70, el=0), Crystal(az=140, el=0)]
    tick(app, 1)
    assert app.planet_arrow.visible and arrow_deg(app.planet_arrow) == pytest.approx(0, abs=1)
    assert app.crystal_arrow.visible and abs(arrow_deg(app.crystal_arrow)) == pytest.approx(180, abs=1)
    app.game.crystals.clear()
    tick(app, 1)
    assert not app.crystal_arrow.visible and app.planet_arrow.visible


def test_the_old_edge_labels_are_gone(app):
    start_playing(app)
    assert not hasattr(app, "arrow_left") and not hasattr(app, "arrow_right")
    assert "<" not in texts(app) and ">" not in texts(app)


# --- the Overlord BMS: hold ring, arrow back, award --------------------------------------------
def chip_in_view(app, az=0.0):
    from overblaster.game import Crystal

    g = app.game
    g.worlds.clear()
    g.crystals[:] = [Crystal(az=az, el=g.view_el, is_chip=True)]
    return g.crystals[0]


def test_aiming_at_the_chip_fills_a_ring_around_it(app):
    start_playing(app)
    chip = chip_in_view(app)
    tick(app, 12)
    hold = app.bms.hold
    assert hold is not None and hold[3] is True  # on target
    assert 0.2 < hold[2] < 1.0 and hold[2] == pytest.approx(chip.progress, abs=0.01)
    assert abs(hold[0] - app.screen_w / 2) < 3  # the ring is on the chip, which is under the crosshair


def test_when_your_aim_is_off_the_chip_the_ring_is_not_on_target_and_knows_where_the_chip_is(app):
    start_playing(app)
    chip_in_view(app, az=8.0)  # 8 degrees to the right: on screen but well off the crosshair
    tick(app, 3)
    hold = app.bms.hold
    assert hold is not None and hold[3] is False
    assert hold[0] > app.screen_w / 2 + 100  # to the right of the centre, where the arrow must point


def test_no_ring_when_the_chip_is_off_screen_or_absent(app):
    start_playing(app)
    tick(app, 3)
    assert app.bms.hold is None
    chip_in_view(app, az=100.0)
    tick(app, 3)
    assert app.bms.hold is None


def test_holding_the_chip_collects_it_and_starts_the_award(app):
    from overblaster import bms

    start_playing(app)
    chip_in_view(app)
    assert app.bms.award_t is None
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    assert app.game.chip_collected
    assert app.bms.award_t is not None and app.bms.origin is not None
    assert abs(app.bms.origin[0] - app.screen_w / 2) < 10  # the sparks start where the chip was
    assert app.bms.hold is None  # the ring is gone


def test_the_callout_names_the_overlord_bms_for_a_few_seconds_and_the_medallion_stays(app):
    from overblaster import bms

    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    tick(app, int((bms.BUBBLE_IN + 1.0) * 15))
    m = app.bms.callout
    assert m.bubble_scale == pytest.approx(1.0) and "OVERLORD BMS FOUND!" in [t.text for t in m.texts]
    tick(app, int((bms.BUBBLE_FOLD - bms.BUBBLE_IN) * 15))  # a bit past the fold
    tick(app, 30)
    m = app.bms.callout
    assert m.bubble_scale == 0 and m.medal_alpha == 1.0  # the bubble is gone and the medallion stays
    assert app.hud.badge == 1.0 and app.hud.model.pill is not None


def test_the_hud_badge_pops_in_after_the_sparks_not_at_the_instant_of_collection(app):
    from overblaster import bms

    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    assert app.hud.badge < 0.5
    tick(app, int((bms.BADGE_AT + 1.0) * 15))
    assert app.hud.badge == 1.0


def test_there_is_no_text_banner_for_the_chip_any_more(app):
    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    assert not any("CHIP" in t.upper() for t in all_visible_text(app))


def test_a_new_game_starts_without_the_award(app):
    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    app.show_title()
    button(app, "LAUNCH").click()
    assert app.bms.award_t is None and not app.game.chip_collected


def test_the_level_clear_plate_waits_for_the_bms_callout_to_finish(app):
    from overblaster import bms
    from overblaster.game import State

    start_playing(app)
    chip_in_view(app)  # the chip is the last thing left, so collecting it clears the level
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    assert app.game.state is State.INTERMISSION
    tick(app, int((bms.BUBBLE_IN + 2.0) * 15))
    assert not app.pause.shown and app.bms.callout.bubble_scale > 0.9  # the callout has the screen to itself
    tick(app, int(bms.SETTLE_S * 15))
    assert app.pause.shown  # then SECTOR CLEARED
    assert app.bms.callout.bubble_scale == 0


def test_pew_cannot_skip_a_plate_that_has_not_appeared_yet(app):
    from overblaster.game import State

    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    app._inputs.mic = 0.0
    tick(app, 40)
    app._inputs.mic = 0.9
    tick(app, 4)
    assert app.game.state is State.INTERMISSION  # still waiting: nothing to acknowledge yet


# --- sound: music, effects and the voice -----------------------------------------------------
def said(app):
    return [e[1] for e in app.sound.log if e[0] == "say"]


def sfx_played(app):
    return [e[1] for e in app.sound.log if e[0] == "sfx"]


def test_the_title_has_its_own_music_and_the_voice_welcomes_you(app):
    assert ("music", "title") in app.sound.log
    assert ("title",) in said(app)


def test_launching_plays_a_confirm_and_switches_to_the_game_music(app):
    button(app, "LAUNCH").click()
    assert "ui_confirm" in sfx_played(app)
    assert app.sound.log[-1] == ("music", "game") or ("music", "game") in app.sound.log


def test_each_level_start_is_announced_by_the_voice_with_a_whoosh(app):
    button(app, "LAUNCH").click()
    tick(app, 12)
    assert ("level_word", "num_01", "name_0") in said(app)
    assert "level_start" in sfx_played(app)


def test_the_level_number_and_name_are_spoken_for_later_levels_too(app):
    from overblaster.game import State

    button(app, "LAUNCH").click()
    tick(app, 12)
    app.game.worlds.clear()
    app.game.crystals.clear()
    app.game.level = 2
    app.game.state = State.INTERMISSION
    app.game._intermission_left = 0.0
    app.game.acknowledge()
    tick(app, 2)
    assert ("level_word", "num_03", "name_2") in said(app)


def test_shots_that_hit_and_worlds_that_die_make_noise(app):
    start_playing(app)
    app.game.worlds[:] = [fake_world(app, hp=2)]
    app._inputs.mic = 0.9
    tick(app, 1)
    assert "hit" in sfx_played(app)
    app._inputs.mic = 0.0
    tick(app, 8)
    app._inputs.mic = 0.9
    tick(app, 3)
    assert "explode" in sfx_played(app)


def test_there_is_no_laser_sound_because_you_are_the_laser(app):
    start_playing(app)
    app._inputs.mic = 0.9
    tick(app, 5)
    assert not [e for e in app.sound.log if e[0] == "sfx" and e[1] in ("pew", "laser", "shot")]


def test_harvesting_a_crystal_chimes(app):
    from overblaster.game import Crystal

    start_playing(app)
    app.game.worlds.clear()
    app.game.crystals[:] = [Crystal(az=app.game.view_az, el=app.game.view_el)]
    tick(app, 10)
    assert "crystal" in sfx_played(app)


def test_the_voice_announces_the_chip_once_when_it_appears_and_ticks_rise_as_you_hold(app):
    from overblaster import synth

    start_playing(app)
    chip_in_view(app)
    tick(app, 2)
    assert said(app).count(("chip_seen",)) == 1
    tick(app, int(C.CHIP_HOLD_S * 15 * 0.8))
    ticks = [n for n in sfx_played(app) if n.startswith("charge_")]
    assert ticks == [f"charge_{i}" for i in range(len(ticks))] and 4 <= len(ticks) <= synth.CHARGE_TICKS
    tick(app, 10)
    assert said(app).count(("chip_seen",)) == 1


def test_collecting_the_chip_plays_the_fanfare_and_the_voice_names_it(app):
    start_playing(app)
    chip_in_view(app)
    tick(app, int(C.CHIP_HOLD_S * 15) + 4)
    assert "chip_collect" in sfx_played(app) and ("chip_found",) in said(app)


def test_the_sector_cleared_plate_is_voiced_and_asks_for_a_pew(app):
    start_playing(app)
    app.game.worlds.clear()
    app.game.crystals.clear()
    tick(app, 2)
    tick(app, 8)
    assert ("level_clear",) in said(app) and "level_clear" in sfx_played(app)
    assert ("continue",) not in said(app)
    tick(app, 20)
    assert ("continue",) in said(app) and said(app).count(("continue",)) == 1


def test_a_world_hitting_the_ship_is_voiced(app):
    from overblaster.game import World

    start_playing(app)
    app.game.worlds[:] = [World(az=10, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a")]
    tick(app, 3)
    assert "hull_death" in sfx_played(app) and ("hull_destroyed",) in said(app)


def test_running_out_of_battery_is_voiced(app):
    start_playing(app)
    app.game.charge = 0.0
    app.game.worlds[:] = [fake_world(app, hp=5)]
    tick(app, 3)
    assert "battery_dead" in sfx_played(app) and ("battery_dead",) in said(app)


def test_low_battery_warns_once_per_drop(app):
    start_playing(app)
    app.game.charge = 20.0
    tick(app, 3)
    assert said(app).count(("battery_low",)) == 1
    tick(app, 20)
    assert said(app).count(("battery_low",)) == 1
    app.game.charge = 90.0
    tick(app, 2)
    app.game.charge = 20.0
    tick(app, 3)
    assert said(app).count(("battery_low",)) == 2


def test_you_cannot_fire_over_the_voice(app):
    start_playing(app)
    app.game.worlds[:] = [fake_world(app, hp=9)]
    app.sound.mixer.hear_voice = True
    app.sound.say("chip_seen")  # a long line
    charge = app.game.charge
    app._inputs.mic = 0.9
    tick(app, 6)
    assert app.game.charge == charge, "a shot was fired while the voice was speaking"
    app.sound.mixer.stop_voice()
    app.sound.mixer._voice_end = -1
    tick(app, 3)
    assert app.game.charge < charge


def test_a_pew_still_fires_with_the_music_playing_when_the_mic_hears_only_the_music(app):
    start_playing(app)
    app.game.worlds[:] = [fake_world(app, hp=9)]
    charge = app.game.charge
    app._inputs.mic = 0.0
    tick(app, 3)
    assert app.game.charge == charge
    app._inputs.mic = 0.9
    tick(app, 2)
    assert app.game.charge < charge


def test_the_music_stops_on_the_game_over_screen_and_the_title_music_returns(app):
    from overblaster.game import World

    start_playing(app)
    app.game.worlds[:] = [World(az=10, el=0, az_v=0, el_v=0, progress=0.99, speed=1.0, hp=1, kind="a")]
    tick(app, 40)
    assert app.sound.log[-1][0] in ("sfx", "say", "music")
    assert ("music", None) in app.sound.log
    app.show_title()
    assert app.sound.log[-1] == ("music", "title") or ("music", "title") in app.sound.log[-3:]
