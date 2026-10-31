"""Sound.handle: the sound events the web-port core emits, played by Raven's mixer (silent sink)."""

import re

import numpy as np

from overblaster import audio, sound, synth
from overblaster.core import (
    COUNT_AT, GAME_AT, INTRO_CUES, INTRO_END, LEVELS, MAX_LEVEL, RISER_AT, SKIP_STORY_TO, Game, empty_input, level_say, bot_target,
)
from overblaster.core.constants import HIT_FORGIVENESS
from overblaster.core.game import rock_radius

DT = 1 / 30
SR = synth.SR


def make() -> sound.Sound:
    return sound.Sound(sink=sound.NullSink(), enabled=True)


def pump(s: sound.Sound, g: Game, secs: float, **kw) -> list:
    """Advance the game, hand every sound event to Sound.handle and render the mixer in step. Returns all events."""
    out = []
    for _ in range(round(secs / DT)):
        f = empty_input()
        for k, v in kw.items():
            setattr(f, k, v)
        g.update(DT, f)
        for e in g.drain():
            out.append(e)
            s.handle(e)
        s.mixer.render(int(DT * SR))
    return out


# ---------------------------------------------------------------- the intro, played through the mixer
def expected_intro_log() -> list:
    """What Sound should log for the intro cues, in order, as the web game would play them."""
    log = []
    for cue in sorted(INTRO_CUES, key=lambda c: c.at):
        if cue.at >= GAME_AT:
            continue
        for e in cue.events:
            if e["type"] == "say":
                log.append(("say", tuple(e["keys"])))
            elif e["type"] == "sfx":
                log.append(("sfx", e["name"]))
            elif e["type"] == "alarm":
                log.append(("alarm", e["on"]))
            elif e["type"] == "drone":
                log.append(("drone", e["on"]))
    return log


def test_the_whole_intro_plays_the_web_cues_in_order():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, GAME_AT - 0.02)
    assert s.log == expected_intro_log()
    voices = [e[1] for e in s.log if e[0] == "say"]
    assert voices == [("m_n1",), ("m_n2",), ("m_n3",), ("m_n4",), ("m_e3",), ("m_e4",), ("m_e5",), ("m_three",), ("m_two",), ("m_one",), ("m_go",)]
    assert ("sfx", "warp_charge") in s.log and s.log.index(("alarm", True)) < s.log.index(("alarm", False))
    assert s.log.index(("drone", True)) < s.log.index(("drone", False))


def test_the_intro_hands_over_to_the_game_with_music_and_the_level_voice():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, INTRO_END + 6.0)
    assert ("music", "game") in s.log and s._music_name == "game"
    assert s.log.index(("music", "game")) > s.log.index(("say", ("m_go",)))
    assert ("say", tuple(level_say(1))) in s.log  # "Level one, the far side", once the splash has settled
    assert ("sfx", "level_start") in s.log


def test_the_alarm_and_drone_are_loops_that_stop():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, 0.1)
    assert s.mixer.loop_running("drone") and not s.mixer.loop_running("alarm")
    pump(s, g, 4.0)  # the second line's scene starts the alarm
    assert s.mixer.loop_running("alarm")
    pump(s, g, 9.0)  # the ship drops out of the jump: the alarm stops at once
    assert not s.mixer.loop_running("alarm") and "alarm" not in s.mixer._loops
    assert s.mixer.loop_running("drone")
    pump(s, g, COUNT_AT + 3 - g.intro.t + 0.1)  # the drone is told to stop and fades
    assert not s.mixer.loop_running("drone")
    pump(s, g, 3.0)
    assert "drone" not in s.mixer._loops


def test_the_drone_fades_in_slowly_and_out_over_a_second_or_two():
    s = make()
    s.drone(True)
    levels = []
    for _ in range(100):
        s.mixer.render(SR // 20)
        levels.append(s.mixer._loops["drone"].level)
    assert levels[0] < 0.1 and 0.5 < levels[24] < 0.7 and levels[-1] > 0.98  # ~1 - exp(-1.2 s / 1.2 s) after 1.2 s
    s.drone(False)
    for _ in range(40):  # 2 s
        s.mixer.render(SR // 20)
    assert "drone" not in s.mixer._loops


# ---------------------------------------------------------------- skipping
def test_skip_story_cuts_the_voice_and_starts_the_riser_part_way_in():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, 3.0)
    assert s.speaking and g.intro.t < RISER_AT
    ev = pump(s, g, DT, commands=["skipStory"])
    assert any(e["type"] == "say" and e["keys"] == [] for e in ev)
    assert not s.speaking and ("say", ()) in s.log
    riser = [e for e in ev if e["type"] == "sfx" and e.get("tag") == "riser"]
    assert len(riser) == 1 and abs(riser[0]["offset"] - (SKIP_STORY_TO - RISER_AT)) < 1e-9
    clip = s._riser
    full = audio.Bank().get("sfx_warp_charge")
    assert clip is not None and clip.pos >= int((SKIP_STORY_TO - RISER_AT) * SR) - 1 and len(full) - clip.pos > 0


def test_skip_story_late_in_the_story_does_not_restart_the_riser():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, RISER_AT + 1.0)
    assert ("sfx", "warp_charge") in s.log
    n = s.log.count(("sfx", "warp_charge"))
    pump(s, g, DT, commands=["skipStory"])
    assert s.log.count(("sfx", "warp_charge")) == n  # the first run is already playing: no second riser at an offset


def test_skip_intro_stops_the_riser_the_voice_the_alarm_and_the_drone():
    s, g = make(), Game(seed=3)
    g.begin_intro()
    pump(s, g, 5.0)
    assert s.mixer.loop_running("drone")
    pump(s, g, DT, commands=["skipIntro"])
    assert not s.speaking and ("stopRiser",) in s.log and ("drone", False) in s.log and ("alarm", False) in s.log
    pump(s, g, 3.0)
    assert "alarm" not in s.mixer._loops and "drone" not in s.mixer._loops


def test_the_riser_can_be_cut_and_a_cut_riser_is_gone():
    s = make()
    s.handle({"type": "sfx", "name": "warp_charge", "gain": 0.9, "tag": "riser"})
    assert s.mixer.active_effects == 1
    s.handle({"type": "stopRiser"})
    assert s.mixer.active_effects == 0
    s.handle({"type": "stopRiser"})  # harmless twice


# ---------------------------------------------------------------- the other events
def test_handle_plays_sfx_with_gain_and_offset():
    s = make()
    s.handle({"type": "sfx", "name": "explode", "gain": 0.5})
    clip = s.mixer._effects[-1]
    assert abs(clip.gain - 0.5 * s.mixer.sfx_gain) < 1e-9 and clip.pos == 0
    s.handle({"type": "sfx", "name": "explode", "offset": 0.25})
    assert s.mixer._effects[-1].pos == int(0.25 * SR) and s.mixer._effects[-1].gain == s.mixer.sfx_gain


def test_handle_zap_say_and_music():
    s = make()
    for kind in ("eject", "bad", "pop"):
        s.handle({"type": "zap", "kind": kind})
        assert ("zap", kind) in s.log
    s.handle({"type": "say", "keys": ["level_word", "num_07"]})
    assert s.speaking and s.log[-1] == ("say", ("level_word", "num_07"))
    s.handle({"type": "music", "name": "game"})
    assert s._music_name == "game" and s.mixer._music is not None
    s.handle({"type": "music", "name": None})
    assert s._music_name is None


def test_handle_ignores_app_events_and_a_disabled_sound_does_nothing():
    s = make()
    for e in ({"type": "phase", "phase": "play"}, {"type": "levelStart", "level": 2}, {"type": "launch"}, {"type": "gameOver", "won": False}):
        s.handle(e)
    assert s.log == []
    off = sound.Sound(sink=sound.NullSink(), enabled=False)
    for e in ({"type": "sfx", "name": "hit"}, {"type": "say", "keys": ["m_go"]}, {"type": "alarm", "on": True}, {"type": "drone", "on": True}, {"type": "zap", "kind": "bad"}):
        off.handle(e)
    assert off.log == [] and off.mixer.active_effects == 0 and not off.mixer._loops and not off.speaking


def test_music_ducks_under_the_voice_by_the_web_factors():
    s = make()
    assert s.mixer.music_gain == 0.30 and s.mixer.duck == 0.35 and s.mixer.master == 0.8 and s.mixer.sfx_gain == 0.8
    s.handle({"type": "music", "name": "game"})
    for _ in range(40):
        s.mixer.render(SR // 20)
    assert abs(s.mixer._duck_level - 1.0) < 1e-6
    s.handle({"type": "say", "keys": ["m_e3"]})
    for _ in range(40):
        s.mixer.render(SR // 20)
    assert abs(s.mixer._duck_level - 0.35) < 0.02
    s.handle({"type": "say", "keys": []})
    for _ in range(40):
        s.mixer.render(SR // 20)
    assert abs(s.mixer._duck_level - 1.0) < 0.02


# ---------------------------------------------------------------- every clip the core can ask for exists
def emitted_sound_keys(events) -> set:
    out = set()
    for e in events:
        if e["type"] == "sfx":
            out.add("sfx_" + e["name"])
        elif e["type"] == "say":
            out |= {"voice_" + k for k in e["keys"]}
        elif e["type"] == "zap":
            out.add("zap_" + e["kind"])
        elif e["type"] == "music":
            if e["name"]:
                out.add("music_" + e["name"])
        elif e["type"] == "alarm":
            out.add("loop_alarm")
        elif e["type"] == "drone":
            out.add("loop_drone")
    return out


def bot_events(level: int, seed: int = 1, seconds: float = 60.0, **setup) -> list:
    g = Game(seed=seed)
    g.begin_game()
    g.drain()
    g.run.chip_collected = setup.pop("chip", True)
    g.run.capacity = g.run.charge = 200 if g.run.chip_collected else 100
    g.start_level(level)
    out = list(g.drain())
    inp = empty_input()
    r = g.run
    for _ in range(int(seconds * 30)):
        if g.phase != "play" or r.mode == "intermission":
            break
        p = bot_target(g)
        g.view.az, g.view.el = p["az"], p["el"]
        inp.fire = r.mode == "playing" and any(
            not w.dead and r.t >= w.spawn_at and not g.arriving(w) and g.ang_dist(w.az, w.el) <= rock_radius(w) * HIT_FORGIVENESS for w in r.worlds
        )
        g.update(DT, inp)
        out.extend(g.drain())
    return out


def test_every_clip_the_core_can_emit_exists_in_the_bank():
    bank = audio.Bank()
    keys = set()
    for n in range(1, MAX_LEVEL + 1):  # every level announcement
        keys |= {"voice_" + k for k in level_say(n)}
    for cue in INTRO_CUES:
        keys |= emitted_sound_keys(cue.events)
    for i in range(synth.CHARGE_TICKS):
        keys.add(f"sfx_charge_{i}")
    for level in (1, 3, 7, 14, 28, 42):  # normal play: shots, harvest, chip, bad gauges, wings
        keys |= emitted_sound_keys(bot_events(level, chip=level != 3))
    # the endings and warnings
    g = Game(seed=2)
    g.begin_game()
    g.drain()
    g.run.charge = 0
    g.run.crystals = []
    keys |= emitted_sound_keys(pump(make(), g, 3.0))
    g = Game(seed=2)
    g.begin_game()
    g.drain()
    g.run.t = 5
    g.run.worlds[0].spawn_at, g.run.worlds[0].p, g.run.worlds[0].speed = 0, 0.99, 1.0
    keys |= emitted_sound_keys(pump(make(), g, 3.0))
    g = Game(seed=2)
    g.begin_game()
    g.drain()
    g.run.level, g.run.mode = MAX_LEVEL, "intermission"
    g.run.plate_at = g.clock
    g.update(3.0, empty_input())
    g.continue_from_plate()
    keys |= emitted_sound_keys(g.drain())
    missing = sorted(k for k in keys if bank.get(k) is None)
    assert not missing, missing
    assert len(keys) > 60  # the sweep really did reach most of the sound set


def test_the_core_source_names_only_clips_that_exist():
    """Catches branches the runs above do not reach: every literal sfx / say name in core/game.py."""
    import overblaster.core.game as core_game

    src = open(core_game.__file__).read()
    bank = audio.Bank()
    names = ["sfx_" + n for n in re.findall(r'_sfx\("([a-z_]+)"', src)] + ["voice_" + n for k in re.findall(r"_say\(\[([^\]]*)\]\)", src) for n in re.findall(r'"([a-z_]+)"', k)]
    assert len(names) > 15
    names = [n for n in names if n != "sfx_charge_"]  # built as "charge_" + i; the sweep above checks charge_0..7
    assert [n for n in names if bank.get(n) is None] == []


def test_every_web_clip_is_converted_and_the_web_names_exist():
    import os

    web = "/Users/joecrop/Projects/OverBlaster-web/public/audio"
    if not os.path.isdir(web):
        return
    bank = audio.Bank()
    names = sorted(os.path.splitext(f)[0] for f in os.listdir(web) if f.endswith(".m4a"))
    assert len(names) >= 70
    assert [n for n in names if bank.get(n) is None] == []


# ---------------------------------------------------------------- the synthesised sounds
def test_the_synthesised_clips_are_deterministic_and_the_right_size():
    for name, make_clip in synth.GENERATED.items():
        a, b = make_clip(), make_clip()
        assert np.array_equal(a, b) and a.dtype == np.float32 and np.isfinite(a).all(), name
    assert 0.19 < len(synth.render_zap("eject")) / SR < 0.22
    assert 0.9 < len(synth.render_zap("bad")) / SR < 1.1
    assert 0.12 < len(synth.render_zap("pop")) / SR < 0.16
    try:
        synth.render_zap("nope")
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_zaps_have_the_web_levels():
    assert float(np.abs(synth.render_zap("bad")).max()) > 0.6  # the loud one
    assert float(np.abs(synth.render_zap("eject")).max()) < 0.5 and float(np.abs(synth.render_zap("pop")).max()) < 0.5


def test_the_alarm_loop_pulses_at_2_point_2_hz_between_silence_and_0_07():
    x = synth.render_alarm()
    assert len(x) == int(synth.ALARM_S * SR)
    assert 0.069 < float(np.abs(x).max()) <= 0.0705
    win = SR // 100
    env = np.array([np.abs(x[i : i + win]).max() for i in range(0, len(x) - win, win)])
    loud = env > 0.03
    edges = np.flatnonzero(np.diff(loud.astype(int)) == 1)  # rising edges: one per 1/2.2 s
    assert abs(len(edges) - 10) <= 1
    assert abs(float(np.median(np.diff(edges))) * 0.01 - 1 / 2.2) < 0.02
    assert float(env[~loud].max()) < 0.005  # the off half of the pulse is silent


def test_the_alarm_tone_is_740_hz():
    x = synth.render_alarm()[: SR // 4]  # the first quarter second is a loud half cycle of the pulse (0.227 s)
    x = x[: int(0.2 * SR)]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    assert abs(np.argmax(spec) * SR / len(x) - 740) < 10


def test_the_drone_has_its_three_partials():
    x = synth.render_drone()
    spec = np.abs(np.fft.rfft(x))
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    top = sorted(freqs[np.argsort(spec)[-6:]])
    for f in (55.0, 82.4, 110.3):
        assert any(abs(t - f) < 0.2 for t in top), (f, top)


def test_the_loops_are_seamless():
    """First and last sample differ by no more than neighbouring samples do, so the wrap makes no click; and the
    waveform is periodic: continuing it one more sample reproduces the first one."""
    for name, x in (("alarm", synth.render_alarm()), ("drone", synth.render_drone())):
        step = float(np.abs(np.diff(x)).max())
        assert abs(float(x[0]) - float(x[-1])) <= step + 1e-6, name
    n = int(synth.DRONE_S * SR)
    ext = np.sin(2 * np.pi * np.arange(n + 1) * 82.4 / SR)  # the 82.4 Hz partial: 824 whole cycles in 10 s
    assert abs(ext[n] - ext[0]) < 1e-6
    n = int(synth.ALARM_S * SR)
    assert abs(740.0 * synth.ALARM_S - round(740.0 * synth.ALARM_S)) < 1e-9 and abs(2.2 * synth.ALARM_S - round(2.2 * synth.ALARM_S)) < 1e-9
    assert n == len(synth.render_alarm())
