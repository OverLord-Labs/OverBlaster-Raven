import os

import numpy as np
import pytest

from overblaster import audio, config as C, sound, synth, voicelines

SR = synth.SR


def make(tmp_path=None, enabled=True):
    return sound.Sound(sink=sound.NullSink(), enabled=enabled)


def test_every_clip_the_game_can_ask_for_exists_in_assets():
    bank = audio.Bank()
    missing = [n for n in (
        [f"sfx_{k}" for k in synth.SFX] + [f"sfx_charge_{i}" for i in range(synth.CHARGE_TICKS)]
        + ["music_game", "music_title"] + [f"voice_{k}" for k in voicelines.all_clips()]
    ) if bank.get(n) is None]
    assert not missing, missing


def test_clips_are_the_right_loudness_and_length():
    bank = audio.Bank()
    for k in voicelines.all_clips():
        x = bank.get(f"voice_{k}")
        assert 0.4 < len(x) / SR < 5.0 and 0.5 < float(np.abs(x).max()) <= 1.0, k


def test_playing_an_effect_is_logged_and_reaches_the_mixer():
    s = make()
    s.sfx("explode")
    assert ("sfx", "explode") in s.log and s.mixer.active_effects == 1


def test_an_unknown_clip_is_ignored_not_fatal():
    s = make()
    s.sfx("no_such_thing")
    s.say("no_such_voice")
    assert s.mixer.active_effects == 0 and not s.speaking


def test_a_voice_line_speaks_and_a_new_one_replaces_it():
    s = make()
    s.say("title")
    assert s.speaking and ("say", ("title",)) in s.log
    s.say("level_clear")
    assert ("say", ("level_clear",)) in s.log


def test_a_level_announcement_joins_level_number_and_name():
    s = make()
    s.say(*voicelines.level_intro(3))
    clips = [audio.Bank().get(f"voice_{k}") for k in voicelines.level_intro(3)]
    assert s.mixer._voice is not None
    assert len(s.mixer._voice.x) >= sum(len(c) for c in clips)


def test_music_starts_switches_and_stops():
    s = make()
    s.music("title")
    assert s._music_name == "title" and s.mixer._music is not None
    s.music("game")
    assert s._music_name == "game"
    s.music(None)
    assert s._music_name is None


def test_asking_for_the_same_music_again_does_not_restart_it():
    s = make()
    s.music("game")
    s.mixer.render(5000)
    pos = s.mixer._music_pos
    s.music("game")
    assert s.mixer._music_pos == pos


def test_a_muted_game_makes_no_sound_and_loads_nothing():
    s = make(enabled=False)
    s.music("game")
    s.sfx("explode")
    s.say("title")
    assert s.log == [] and s.mixer.active_effects == 0 and not s.speaking and s.mixer._music is None


def test_the_mic_is_muted_while_the_voice_speaks_and_free_after():
    s = make()
    assert s.gate(0.5) == pytest.approx(0.5)
    s.say("level_clear")
    assert s.gate(0.9) == 0.0
    for _ in range(80):
        s.mixer.render(int(0.05 * SR))
    assert s.gate(0.5) > 0.4


def test_the_gate_subtracts_the_music_it_has_learned():
    s = make()
    s.music("game", fade=False)
    for _ in range(120):
        s.mixer.render(int(0.067 * SR))
        s.gate(s.mixer.level * 0.4)  # the mic hears 40% of the music, nobody speaks
    s.mixer.render(int(0.067 * SR))
    assert s.gate(s.mixer.level * 0.4) < 0.02
    assert s.gate(s.mixer.level * 0.4 + 0.4) > 0.25


def test_the_log_does_not_grow_forever():
    s = make()
    for _ in range(1000):
        s.sfx("hit")
    assert len(s.log) <= sound.LOG_LIMIT


def test_a_player_can_choose_to_hear_a_shot_sound_but_by_default_there_is_none():
    assert C.AUDIO_SHOT_SOUND is False


def test_no_mic_reading_stays_no_reading():
    assert make().gate(None) is None
