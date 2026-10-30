import numpy as np
import pytest

from overblaster import synth

SR = synth.SR


def centroid(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    return float((spec * freqs).sum() / spec.sum())


def dominant(x):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.fft.rfftfreq(len(x), 1 / SR)[spec.argmax()])


@pytest.mark.parametrize("name", sorted(synth.SFX))
def test_every_effect_is_audible_clean_and_does_not_clip(name):
    x = synth.render_sfx(name)
    assert x.dtype == np.float32 and x.ndim == 1
    assert 0.05 < len(x) / SR < 3.2, "effects are short"
    peak = float(np.abs(x).max())
    assert 0.3 <= peak <= 0.98, peak
    assert abs(x[0]) < 0.05 and abs(x[-1]) < 0.02, "no click at the start or the end"


def test_effects_are_deterministic():
    assert np.array_equal(synth.render_sfx("explode"), synth.render_sfx("explode"))


def test_a_crystal_chimes_high_and_an_explosion_rumbles_low():
    assert centroid(synth.render_sfx("crystal")) > 1.5 * centroid(synth.render_sfx("explode"))
    assert centroid(synth.render_sfx("explode")) < 2200
    assert centroid(synth.render_sfx("hull_death")) < 1600


def test_the_charge_ticks_climb_in_pitch():
    notes = [dominant(synth.charge_tick(i)) for i in range(synth.CHARGE_TICKS)]
    assert notes == sorted(notes) and notes[-1] > notes[0] * 1.5


def test_the_game_track_loops_seamlessly():
    m = synth.render_music("game")
    assert abs(len(m) / SR - synth.GAME_BARS * 4 * 60 / synth.BPM) < 0.01
    assert abs(float(m[0])) < 0.02 and abs(float(m[-1])) < 0.02, "a jump here would click every loop"
    assert float(np.abs(m).max()) <= 0.95
    rms = float(np.sqrt((m ** 2).mean()))
    assert 0.05 < rms < 0.3, rms


def test_the_title_track_is_calmer_than_the_game_track():
    t, g = synth.render_music("title"), synth.render_music("game")
    assert float(np.sqrt((t ** 2).mean())) < float(np.sqrt((g ** 2).mean()))
    assert abs(float(t[0])) < 0.02 and abs(float(t[-1])) < 0.02


def test_music_is_deterministic_and_a_sensible_length():
    assert np.array_equal(synth.render_music("title"), synth.render_music("title"))
    assert 8 < len(synth.render_music("game")) / SR < 45


def test_to_int16_round_trips_and_clips_safely():
    x = np.array([0.0, 0.5, -0.5, 2.0, -2.0], dtype=np.float32)
    y = synth.to_int16(x)
    assert y.dtype == np.int16 and y[1] > 16000 and y[3] == 32767 and y[4] == -32767


def test_the_sound_is_full_bandwidth_not_the_dull_telephone_sound_of_a_low_sample_rate():
    assert SR >= 44100
    for name in ("explode", "crystal", "chip_collect"):
        x = synth.render_sfx(name)
        spec = np.abs(np.fft.rfft(x)) ** 2
        freqs = np.fft.rfftfreq(len(x), 1 / SR)
        assert spec[freqs > 11000].sum() / spec.sum() > 1e-5, name
    m = synth.render_music("game")
    spec = np.abs(np.fft.rfft(m)) ** 2
    freqs = np.fft.rfftfreq(len(m), 1 / SR)
    assert spec[freqs > 11000].sum() / spec.sum() > 1e-5, "the hats and the shimmer should reach past 11 kHz"


def test_the_game_track_has_two_sections_that_differ():
    m = synth.render_music("game")
    half = len(m) // 2
    a, b = m[:half], m[half:]
    assert float(np.abs(a - b).mean()) > 0.02, "sixteen bars of the same eight would get old"


def test_the_track_pulses_on_the_beat():
    from overblaster import dsp

    m = synth.render_music("game")
    env_ = dsp.lowpass(np.abs(m), 30)[: SR * 8]
    env_ = env_ - env_.mean()
    beat = int(round(SR * 60 / synth.BPM))
    ac = lambda lag: float((env_[:-lag] * env_[lag:]).mean())
    assert ac(beat) > ac(int(beat * 0.37)), "the energy should repeat once a beat"


def lowpass_env(x):
    from overblaster import dsp

    return dsp.lowpass(x, 120)
