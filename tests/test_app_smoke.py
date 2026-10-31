"""Drive the real OverBlasterApp against fake Raven widgets (see fake_raven.py).

This does NOT prove the real framework behaves the same (tests/real_framework_*.py do that, offscreen); it proves our
code is internally consistent: the screens flow, the tick loop turns sensors into core input, the dwell buttons press
the right places, sound events reach Sound, and no widget is created while playing.
"""

import importlib
import sys

import pytest

import fake_raven
from overblaster import config as C
from overblaster.core import ACK_MIN, COUNT_AT, INTRO_END, SKIP_STORY_TO, Crystal
from overblaster.core.layout import LAUNCH, RETRY, SKIPS, TOTITLE

DT = C.TICK_MS / 1000.0


class FakeInputs:
    def __init__(self):
        self.gyro_yaw = 0.0
        self.mic = 0.0
        self.gaze_pos = None
        self.closed = 0
        self.mic_status = "listening"
        self.mic_reads = 0

    def imu(self):
        gyro = [0.0, 0.0, 0.0]
        gyro[C.GYRO_YAW_AXIS] = self.gyro_yaw
        return {"accelerometer": (0.0, 0.0, 9.8), "gyroscope": tuple(gyro), "magnetometer": (0, 0, 0)}

    def gaze(self):
        return self.gaze_pos

    def mic_level(self):
        self.mic_reads += 1
        return self.mic

    def close(self):
        self.closed += 1


def hold_the_voice(monkeypatch):
    """The voice mutes the mic while it speaks, and with no sound card nothing advances the mixer, so it
    would speak forever. Voice clips are logged but not played unless a test sets `sound.mixer.hear_voice`."""
    from overblaster import audio

    real_play = audio.Mixer.play

    def play(self, x, gain=1.0, voice=False, *a, **kw):
        if voice and not getattr(self, "hear_voice", False):
            return None
        return real_play(self, x, gain, voice, *a, **kw)

    monkeypatch.setattr(audio.Mixer, "play", play)


@pytest.fixture
def app(monkeypatch):
    hold_the_voice(monkeypatch)
    fake_raven.install()
    for mod in [m for m in sys.modules if m.startswith("overblaster.ui") or m.startswith("overblaster.app")]:
        del sys.modules[mod]
    app_mod = importlib.import_module("overblaster.app")
    from overblaster.sound import NullSink, Sound

    monkeypatch.setattr(app_mod, "make_sound", lambda: Sound(NullSink()))  # never open a speaker, whatever else ran before
    clock = {"t": 1000.0}
    monkeypatch.setattr(app_mod.time, "monotonic", lambda: clock["t"])
    inputs = FakeInputs()
    instance = app_mod.OverBlasterApp(inputs=inputs, simulated=False, mac_imu=False, seed=3)
    instance._clock, instance._inputs = clock, inputs
    return instance


def tick(app, n=1):
    for _ in range(n):
        app._clock["t"] += DT
        fake_raven.ROUTINES[-1].invoke()


def tick_until(app, cond, seconds=60.0):
    for _ in range(int(seconds / DT)):
        if cond():
            return True
        tick(app)
    return cond()


BOXES = {"launch": LAUNCH, "retry": RETRY, "title": TOTITLE, "skip": SKIPS}


def plates(app):
    """The plates that can be pressed on this screen."""
    return sorted(app._plates())


def dwell_on(app, name, seconds=None):
    """Rest the gaze on a plate (the eye tracker's reading, in game-area px) long enough to press it."""
    b = BOXES[name]
    app._inputs.gaze_pos = (b.x + b.w / 2, b.y + b.h / 2)
    tick(app, int((seconds if seconds is not None else C.DWELL_S) / DT) + 2)
    app._inputs.gaze_pos = None


def sounds(app, kind):
    return [e for e in app.sound.log if e[0] == kind]


def go_play(app):
    """Skip the intro straight to level 1 (core API), and settle."""
    app.game.begin_game()
    tick(app, 2)
    assert app.game.phase == "play"


def aim_at(app, az=None, el=None):
    """Return the bearing the head points at right now (the core's view), after one tick."""
    tick(app)
    return app.game.view.az if az is None else az, app.game.view.el if el is None else el


# ---------------------------------------------------------------- the screens
def test_title_has_only_the_launch_button_and_the_tick_loop_runs(app):
    assert app.game.phase == "title"
    assert plates(app) == ["launch"]
    assert fake_raven.ROUTINES[-1].interval_ms == C.TICK_MS
    tick(app, 5)
    assert app.game.phase == "title" and app.game.clock > 0


def test_the_title_has_no_music_and_no_voice_like_the_web_game(app):
    tick(app, 20)
    assert app.game.phase == "title"
    assert not sounds(app, "music") and not sounds(app, "say")


def test_dwell_needs_the_whole_time_and_the_fill_is_handed_to_the_scene(app):
    b = LAUNCH
    app._inputs.gaze_pos = (b.x + 5, b.y + 5)
    tick(app, int(C.DWELL_S / 2 / DT))
    assert 0.3 < app.layer.dwell["launch"][1] < 0.7 and app.layer.dwell["launch"][0] == LAUNCH
    app._inputs.gaze_pos = (10.0, 600.0)  # looked away
    tick(app, int(C.DWELL_S / DT))
    assert app.game.phase == "title" and not app.layer.dwell
    dwell_on(app, "launch")
    assert app.game.phase == "intro"


def test_a_mouse_click_on_a_plate_presses_it_too(app):
    app._on_click(LAUNCH.x + 10 + app.app.x(), LAUNCH.y + 10 + app.app.y())
    tick(app, 2)
    assert app.game.phase == "intro"


def test_the_dwell_boxes_follow_the_screen(app):
    assert plates(app) == ["launch"]
    app.game.begin_intro()
    app.game.intro.t = 2.0
    assert plates(app) == ["skip"]
    app.game.intro.t = COUNT_AT
    assert plates(app) == []
    app.game.begin_game()
    assert plates(app) == []


def test_launch_dwell_starts_the_intro_and_its_sounds(app):
    dwell_on(app, "launch")
    tick(app, 3)
    assert app.game.phase == "intro"
    assert not app.game.launching
    assert plates(app) == []  # no launch button, and the skip button waits until the story is under way
    assert ("drone", True) in sounds(app, "drone")
    assert app.inputs.mic_reads == 0  # the microphone is only needed while playing


def test_full_run_title_intro_play_over_retry_title(app):
    dwell_on(app, "launch")
    assert tick_until(app, lambda: app.game.story_btn_visible())
    assert plates(app) == ["skip"]
    dwell_on(app, "skip")
    tick(app)
    assert app.game.intro.t >= SKIP_STORY_TO - 0.1
    assert plates(app) == []
    assert tick_until(app, lambda: app.game.phase == "play")
    assert app.game.intro.t >= INTRO_END and app.game.run.level == 1
    assert ("music", "game") in sounds(app, "music")
    # lose to a rock
    app.game.run.worlds[0].p = 0.999
    app.game.run.worlds[0].spawn_at = 0
    app.game.run.worlds[0].speed = 1.0
    assert tick_until(app, lambda: app.game.phase == "over", 10)
    tick(app)
    assert plates(app) == ["retry", "title"]
    assert app.inputs.closed >= 1  # the microphone is released when play ends
    dwell_on(app, "retry")
    tick(app, 2)
    assert app.game.phase == "play" and app.game.run.level == 1 and app.game.run.score == 0
    app.game.run.worlds[0].p = 0.999
    app.game.run.worlds[0].spawn_at = 0
    app.game.run.worlds[0].speed = 1.0
    assert tick_until(app, lambda: app.game.phase == "over", 10)
    dwell_on(app, "title")
    tick(app, 2)
    assert app.game.phase == "title" and plates(app) == ["launch"]


def test_skip_story_by_key_and_dwell_only_while_the_story_runs(app):
    dwell_on(app, "launch")
    tick(app, int(0.5 / DT))
    assert not app.game.story_btn_visible()
    tick(app, int(1.5 / DT))
    assert app.game.story_btn_visible() and plates(app) == ["skip"]
    assert app.handle_key("escape")
    tick(app)
    assert app.game.intro.t >= SKIP_STORY_TO - 0.1
    tick(app, int(2.0 / DT))
    assert app.game.intro.t > COUNT_AT and plates(app) == []


def test_enter_launches(app):
    assert app.handle_key("return")
    tick(app, 2)
    assert app.game.phase == "intro"


# ---------------------------------------------------------------- playing
def test_no_widgets_are_created_while_playing(app):
    go_play(app)
    created = len(fake_raven.CREATED)
    app._inputs.gyro_yaw = 30.0  # sweep the view around
    app._inputs.mic = 0.5
    tick(app, 300)
    assert len(fake_raven.CREATED) == created
    assert app.layer.updates > 300  # the scene is repainted every tick


def test_levelstart_sounds_and_voice_reach_sound(app):
    go_play(app)
    assert ("music", "game") in sounds(app, "music")
    assert any(e[0] == "say" and e[1][0] == "level_word" for e in app.sound.log)
    assert ("sfx", "level_start") in app.sound.log


def test_a_loud_sound_fires_and_holding_it_keeps_firing(app):
    go_play(app)
    tick(app, int(1.5 / DT))
    c0 = app.game.run.charge
    app._inputs.mic = 0.5
    tick(app, int(1.0 / DT))
    spent = c0 - app.game.run.charge
    assert 7 <= spent <= 11  # 10 shots a second
    app._inputs.mic = 0.0
    c1 = app.game.run.charge
    tick(app, 10)
    assert app.game.run.charge == c1  # a quiet room fires nothing


def test_space_fires_while_held_and_stops_on_release(app):
    go_play(app)
    tick(app, int(1.5 / DT))
    c0 = app.game.run.charge
    app.handle_key("space")
    tick(app, int(0.5 / DT))
    assert app.game.run.charge < c0 - 3
    app.handle_key("space", down=False)
    c1 = app.game.run.charge
    tick(app, 5)
    assert app.game.run.charge == c1


def test_the_head_steers_the_view_and_c_recenters(app):
    go_play(app)
    app._inputs.gyro_yaw = 40.0
    tick(app, int(1.0 / DT))
    assert abs(app.game.view.az - 0) > 10 or abs(app.game.view.az - 360) > 10
    app._inputs.gyro_yaw = 0.0
    tick(app, 3)
    app.handle_key("c")
    app.game.view.az = 123.0
    tick(app, 3)
    assert abs(((app.game.view.az + 180) % 360) - 180) < 5  # straight ahead again


def test_a_steady_gaze_moves_the_crosshair_and_otherwise_it_sits_in_the_middle(app):
    go_play(app)
    tick(app, 5)
    assert not app.game.input.pointer.mouse
    assert (app.game.input.pointer.x, app.game.input.pointer.y) == (320, 320)
    app._inputs.gaze_pos = (400.0, 200.0)
    tick(app, 20)  # steady for long enough to be trusted
    p = app.game.input.pointer
    assert p.mouse and abs(p.x - 400) < 1 and abs(p.y - 200) < 1
    assert app.game.aim_px() == {"x": p.x, "y": p.y} or (app.game.aim_px().x, app.game.aim_px().y) == (p.x, p.y)


def test_harvesting_a_crystal_adds_battery_and_sounds(app):
    go_play(app)
    g = app.game
    az, el = aim_at(app)
    g.run.charge = 40.0
    g.run.crystals.append(Crystal(az, el, 0.0, 0.0))
    tick(app, int(0.6 / DT))
    assert g.run.charge > 40.0
    assert ("sfx", "crystal") in app.sound.log


def test_the_overlord_bms_is_collected_by_holding_aim(app):
    go_play(app)
    g = app.game
    g.run.level = 3
    az, el = aim_at(app)
    g.eject_chip(az, el)
    tick(app, int(2.8 / DT))
    assert g.run.chip_collected and g.run.capacity == 200
    assert ("sfx", "chip_collect") in app.sound.log
    assert any(e[0] == "say" and e[1] == ("chip_found",) for e in app.sound.log)


def test_a_battery_wing_on_level_14_is_collected_the_same_way(app):
    go_play(app)
    g = app.game
    g.run.chip_collected = True
    g.start_level(14)
    g.run.worlds = []
    g.run.t = 6.0
    tick(app, 3)
    assert g.run.wing is not None
    # turn to it: the head tracker owns the view in the app, so move the wing to where the head points
    az, el = aim_at(app)
    g.run.wing.az, g.run.wing.el = az, el
    tick(app, int(2.8 / DT))
    assert g.run.wings == 1 and g.run.wing is None


def test_the_plate_waits_for_a_fresh_pew_after_the_gate_opens(app):
    go_play(app)
    g = app.game
    g.run.worlds = []
    g.run.crystals = []
    tick(app, 3)
    assert g.run.mode == "intermission"
    app._inputs.mic = 0.5  # a sound already ringing when the plate comes up, and held the whole time
    tick(app, int((ACK_MIN + 1.5) / DT))
    assert g.run.level == 1 and g.run.mode == "intermission", "a held sound must not skip the plate"
    app._inputs.mic = 0.0
    tick(app, 3)
    app._inputs.mic = 0.5  # a fresh one does
    tick(app, 3)
    assert g.run.level == 2


def test_space_acknowledges_the_plate_after_its_minimum(app):
    go_play(app)
    g = app.game
    g.run.worlds = []
    g.run.crystals = []
    tick(app, 3)
    assert g.run.mode == "intermission"
    app.handle_key("space")
    app.handle_key("space", down=False)
    tick(app, 3)
    assert g.run.level == 1  # too early
    tick(app, int(ACK_MIN / DT))
    app.handle_key("space")
    app.handle_key("space", down=False)
    tick(app, 3)
    assert g.run.level == 2


def test_running_out_of_battery_ends_the_game_and_releases_the_microphone(app):
    go_play(app)
    app.game.run.charge = 0.0
    app.game.run.crystals = []
    assert tick_until(app, lambda: app.game.phase == "over", 10)
    tick(app)
    assert app.game.run.lost_cause == "battery"
    assert app.inputs.closed >= 1


# ---------------------------------------------------------------- misc
def test_debug_panel_fills_in_when_asked_for(app):
    assert app.dbg is None
    app.handle_key("d")
    assert app.dbg is not None and app.layer.debug is app.dbg
    go_play(app)
    app._inputs.mic = 0.3
    tick(app, 6)
    assert app.dbg.mic == pytest.approx(0.3) and app.dbg.hot and len(app.dbg.lines) == 2
    app.handle_key("d")
    assert app.layer.debug is None


def test_close_stops_the_loop_and_the_sound(app):
    class Ev:
        pass

    app.closeEvent(Ev())
    assert fake_raven.ROUTINES[-1].stopped
    assert app._inputs.closed >= 1
