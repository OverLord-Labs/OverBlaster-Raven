import numpy as np
import pytest

from overblaster import dsp

SR = dsp.SR


def spectrum(x):
    return np.abs(np.fft.rfft(x * np.hanning(len(x)))), np.fft.rfftfreq(len(x), 1 / SR)


def alias_ratio(x, f0):
    """Share of the spectral energy that is not at a harmonic of f0 (that is what aliasing is)."""
    mag, freqs = spectrum(x)
    near = np.zeros(len(freqs), dtype=bool)
    for h in np.arange(1, int(SR / 2 / f0) + 1):
        near |= np.abs(freqs - h * f0) < 3 * SR / len(x) * 4
    return float((mag[~near] ** 2).sum() / (mag ** 2).sum())


def tone(f, seconds=1.0, amp=0.5):
    t = np.arange(int(seconds * SR)) / SR
    return amp * np.sin(2 * np.pi * f * t)


def test_the_sample_rate_is_cd_quality_or_better():
    assert SR >= 44100


def test_a_band_limited_saw_aliases_far_less_than_a_naive_one():
    f0, n = 3322.0, SR
    naive = 2.0 * ((np.arange(n) * f0 / SR) % 1.0) - 1.0
    good = dsp.saw(f0, n)
    assert alias_ratio(good, f0) < alias_ratio(naive, f0) * 0.25
    assert alias_ratio(good, f0) < 5e-3


def test_a_band_limited_square_aliases_far_less_than_a_naive_one():
    f0, n = 2793.0, SR
    naive = np.where((np.arange(n) * f0 / SR) % 1.0 < 0.5, 1.0, -1.0)
    assert alias_ratio(dsp.square(f0, n), f0) < alias_ratio(naive, f0) * 0.25


def test_oscillators_have_the_right_pitch_and_level():
    for osc in (dsp.saw, dsp.square, dsp.sine):
        x = osc(440.0, SR)
        mag, freqs = spectrum(x)
        assert abs(freqs[mag.argmax()] - 440) < 3
        assert 0.8 < np.abs(x).max() < 1.1


def test_a_swept_frequency_works():
    x = dsp.sine(np.linspace(200, 800, SR), SR)
    assert len(x) == SR and np.abs(x).max() <= 1.0


def test_the_lowpass_keeps_the_low_tone_and_removes_the_high_one_without_shifting_it():
    low, high = tone(300), tone(8000)
    y = dsp.lowpass(low + high, 2000)
    assert len(y) == len(low)
    mid = slice(SR // 4, 3 * SR // 4)
    assert abs(np.std(dsp.lowpass(low, 2000)[mid]) / np.std(low[mid]) - 1) < 0.02
    assert np.std(dsp.lowpass(high, 2000)[mid]) < np.std(high[mid]) * 0.01
    lag = np.argmax(np.correlate(y[mid], low[mid], "full")) - (len(low[mid]) - 1)
    assert abs(lag) <= 1, "a filter that delays the sound would smear the drums"


def test_the_highpass_removes_rumble_and_dc():
    x = tone(40) + 0.3 + tone(2000)
    y = dsp.highpass(x, 200)
    mid = slice(SR // 4, 3 * SR // 4)
    assert abs(y[mid].mean()) < 0.01 and np.std(y[mid]) < np.std(tone(2000)[mid]) * 1.05


def test_a_low_cutoff_still_works():
    y = dsp.lowpass(tone(40) + tone(3000), 150)
    mid = slice(SR // 4, 3 * SR // 4)
    assert abs(np.std(y[mid]) / np.std(tone(40)[mid]) - 1) < 0.1


def test_a_swept_lowpass_darkens_over_time():
    from overblaster import synth

    n = SR
    rng = np.random.default_rng(1)
    y = dsp.lowpass_sweep(rng.uniform(-1, 1, n), 9000, 300)
    early, late = y[: n // 5], y[-n // 5 :]

    def centroid(x):
        m, f = spectrum(x)
        return (m * f).sum() / m.sum()

    assert centroid(late) < centroid(early) * 0.5


def test_reverb_adds_a_decaying_tail_and_mix_zero_leaves_the_sound_alone():
    click = np.zeros(SR)
    click[0] = 1.0
    wet = dsp.reverb(click, seconds=0.8, mix=0.5, tail=1.0)
    assert len(wet) == SR + int(1.0 * SR)
    early = np.sqrt((wet[int(0.05 * SR) : int(0.25 * SR)] ** 2).mean())
    late = np.sqrt((wet[int(0.9 * SR) : int(1.3 * SR)] ** 2).mean())
    assert 0 < late < early * 0.2
    dry = dsp.reverb(tone(500, 0.2), seconds=0.8, mix=0.0, tail=0.0)
    assert np.allclose(dry, tone(500, 0.2), atol=1e-9)


def test_reverb_is_deterministic():
    x = tone(500, 0.2)
    assert np.array_equal(dsp.reverb(x, 0.6, 0.3, 0.5), dsp.reverb(x, 0.6, 0.3, 0.5))


def test_the_compressor_evens_out_loud_and_quiet_parts():
    quiet, loud = tone(300, 0.5, 0.05), tone(300, 0.5, 0.8)
    x = np.concatenate([quiet, loud])
    y = dsp.compress(x, threshold_db=-20, ratio=4.0)
    ratio_before = np.abs(loud).max() / np.abs(quiet).max()
    ratio_after = np.abs(y[len(quiet) :]).max() / np.abs(y[: len(quiet)]).max()
    assert ratio_after < ratio_before * 0.6
    assert np.abs(y[: len(quiet) // 2]).max() == pytest.approx(0.05, rel=0.15)  # below the threshold: untouched


def test_the_limiter_never_exceeds_its_ceiling_and_leaves_quiet_sound_alone():
    x = np.concatenate([tone(200, 0.1, 0.1), tone(200, 0.1, 3.0)])
    y = dsp.limit(x, 0.9)
    assert np.abs(y).max() <= 0.9 + 1e-6
    assert np.allclose(y[: SR // 20], x[: SR // 20], atol=0.01)


def test_resampling_keeps_pitch_level_and_changes_length_by_the_ratio():
    x = np.sin(2 * np.pi * 1000 * np.arange(24000) / 24000)
    y = dsp.resample(x, 24000, SR)
    assert abs(len(y) - round(24000 * SR / 24000)) <= 1
    mag, freqs = spectrum(y)
    assert abs(freqs[mag.argmax()] - 1000) < 5
    assert abs(np.std(y[2000:-2000]) / np.std(x) - 1) < 0.02


def test_resampling_to_the_same_rate_returns_the_same_signal():
    x = tone(500, 0.1)
    assert np.allclose(dsp.resample(x, SR, SR), x)


def test_sidechain_ducks_right_after_each_trigger_and_recovers():
    g = dsp.sidechain(SR, [0.0, 0.5], depth=0.8, release=0.15)
    assert g[0] < 0.3 and g[int(0.45 * SR)] > 0.9 and g[int(0.5 * SR) + 1] < 0.3 and g.max() <= 1.0


def test_supersaw_is_thicker_than_a_single_saw_but_the_same_pitch():
    one, many = dsp.saw(220.0, SR), dsp.supersaw(220.0, SR, voices=5, detune=0.12, seed=1)
    m1, f = spectrum(one)
    m2, _ = spectrum(many)
    assert abs(f[m2.argmax()] - 220) < 8
    assert (m2 > 0.1 * m2.max()).sum() > (m1 > 0.1 * m1.max()).sum()
