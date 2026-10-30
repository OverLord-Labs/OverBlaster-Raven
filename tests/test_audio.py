import numpy as np
import pytest

from overblaster import audio, synth

SR = synth.SR


def tone(seconds=0.5, amp=0.5, freq=440.0):
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def mixer(**kw):
    kw.setdefault("master", 1.0)
    return audio.Mixer(**kw)


def rms(x):
    return float(np.sqrt((x ** 2).mean())) if len(x) else 0.0


def test_an_idle_mixer_is_silent_and_renders_the_requested_length():
    out = mixer().render(1000)
    assert out.shape == (1000,) and out.dtype == np.float32 and not out.any()


def test_an_effect_plays_once_with_its_gain_and_then_stops():
    m, x = mixer(sfx_gain=1.0), tone(0.1)
    m.play(x, gain=0.5)
    out = np.concatenate([m.render(500), m.render(5000)])
    assert np.allclose(out[: len(x)], np.tanh(x * 0.5), atol=0.01)
    assert not out[len(x) + 5 :].any()


def test_music_loops_without_a_gap():
    m, loop = mixer(music_gain=1.0), tone(0.2, 0.4)
    m.set_music(loop, fade_s=0.0)
    out = np.concatenate([m.render(1000) for _ in range(20)])  # about 0.9 s: several loops
    assert rms(out[-2000:]) > 0.2 and np.abs(out).max() <= 1.0


def test_music_can_be_switched_off_and_on():
    m = mixer(music_gain=1.0)
    m.set_music(tone(0.2), fade_s=0.0)
    m.render(2000)
    m.set_music(None, fade_s=0.0)
    assert rms(m.render(2000)) == 0.0


def test_voice_ducks_the_music_and_the_music_comes_back():
    m = mixer(music_gain=1.0, voice_gain=1.0, duck=0.3)
    m.set_music(tone(2.0, 0.4, 220), fade_s=0.0)
    before = rms(np.concatenate([m.render(2000) for _ in range(5)]))
    m.play(np.zeros(SR, dtype=np.float32), voice=True)  # a silent voice clip: only the ducking shows
    during = rms(np.concatenate([m.render(2000) for _ in range(10)])[-8000:])
    for _ in range(40):
        m.render(2000)  # the clip ends
    after = rms(np.concatenate([m.render(2000) for _ in range(5)]))
    assert during < before * 0.5 and after > before * 0.9


def test_speaking_is_true_while_a_voice_plays_and_for_a_moment_after():
    m = mixer()
    assert not m.speaking
    m.play(tone(0.3), voice=True)
    assert m.speaking
    m.render(int(0.3 * SR) + 10)
    assert m.speaking, "the room is still ringing"
    for _ in range(10):
        m.render(int(0.1 * SR))
    assert not m.speaking


def test_effects_are_not_voice():
    m = mixer()
    m.play(tone(0.3))
    assert not m.speaking


def test_a_new_voice_line_replaces_the_one_that_is_still_playing():
    m = mixer(voice_gain=1.0)
    m.play(tone(1.0, 0.5, 300), voice=True)
    m.render(1000)
    m.play(tone(0.1, 0.5, 900), voice=True)
    out = m.render(int(0.05 * SR))
    assert abs(float(np.fft.rfftfreq(len(out), 1 / SR)[np.abs(np.fft.rfft(out)).argmax()]) - 900) < 100


def test_only_a_handful_of_effects_play_at_once():
    m = mixer(sfx_gain=1.0)
    for _ in range(30):
        m.play(tone(0.5, 0.05))
    assert m.active_effects <= audio.MAX_EFFECTS


def test_the_output_never_leaves_minus_one_to_one():
    m = mixer(music_gain=1.0, sfx_gain=1.0, voice_gain=1.0)
    m.set_music(tone(1.0, 0.9), fade_s=0.0)
    for _ in range(8):
        m.play(tone(0.5, 0.9))
    m.play(tone(0.5, 0.9), voice=True)
    assert np.abs(m.render(5000)).max() <= 1.0


def test_master_volume_scales_everything():
    a, b = mixer(master=1.0, sfx_gain=1.0), mixer(master=0.5, sfx_gain=1.0)
    for m in (a, b):
        m.play(tone(0.2, 0.2))
    assert rms(b.render(3000)) == pytest.approx(rms(a.render(3000)) * 0.5, rel=0.05)


def test_level_follows_the_output_and_decays_after_it_stops():
    m = mixer(sfx_gain=1.0)
    assert m.level == 0
    m.play(tone(0.2, 0.5))
    m.render(2000)
    assert m.level > 0.1
    for _ in range(20):
        m.render(2000)
    assert m.level < 0.01


def test_a_wav_file_loads_as_floats(tmp_path):
    import wave

    p = tmp_path / "t.wav"
    x = (tone(0.1) * 32767).astype(np.int16)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(x.tobytes())
    y = audio.load_wav(str(p))
    assert y.dtype == np.float32 and len(y) == len(x) and abs(float(y.max()) - 0.5) < 0.01


def test_a_wav_at_another_rate_is_resampled(tmp_path):
    import wave

    p = tmp_path / "r.wav"
    x = (tone(0.5, 0.5, 200)[::2] * 32767).astype(np.int16)  # crude 11025 Hz
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR // 2); w.writeframes(x.tobytes())
    assert abs(len(audio.load_wav(str(p))) / SR - 0.5) < 0.02


def test_a_voice_sequence_joins_clips_with_short_gaps():
    a, b = tone(0.2), tone(0.3)
    joined = audio.join([a, b], gap=0.1)
    assert abs(len(joined) / SR - 0.6) < 0.01


# ---------------- keeping the game's own sound out of the microphone ----------------
def test_the_gate_passes_the_mic_through_when_nothing_is_playing():
    g = audio.EchoGate()
    assert g.apply(0.3, 0.0, False) == pytest.approx(0.3)


def test_the_mic_is_muted_while_the_voice_speaks():
    assert audio.EchoGate().apply(0.9, 0.2, True) == 0.0


def test_it_learns_how_much_of_the_playback_the_mic_hears_and_subtracts_it():
    g = audio.EchoGate()
    for _ in range(100):  # a quiet player, music playing at 0.2, the mic hears 40% of it
        out = g.apply(0.08, 0.2, False)
    assert out < 0.02, out
    assert g.apply(0.08 + 0.4, 0.2, False) > 0.3  # then somebody says "pew"


def test_a_shout_while_calibrating_does_not_spoil_it():
    g = audio.EchoGate()
    for i in range(100):
        g.apply(0.9 if i == 40 else 0.08, 0.2, False)
    assert g.apply(0.08, 0.2, False) < 0.02


def test_the_estimate_is_capped():
    g = audio.EchoGate()
    for _ in range(100):
        g.apply(1.0, 0.1, False)  # a mic that hears ten times what we play
    assert g.k <= audio.ECHO_K_MAX
