import numpy as np

from overblaster import config as C
from overblaster import synth, voicefx, voicelines


def speechlike(seconds=1.0):
    t = np.arange(int(seconds * synth.SR)) / synth.SR
    return (0.4 * np.sin(2 * np.pi * 140 * t) * (1 + 0.5 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def test_every_line_is_short_enough_to_say_while_playing():
    for key, text in voicelines.LINES.items():
        assert 1 <= len(text.split()) <= 12, key


def test_every_line_has_text_and_the_bms_is_spelled_so_it_is_said_letter_by_letter():
    assert all(v.strip() for v in voicelines.LINES.values())
    assert "B M S" in voicelines.LINES["chip_found"] and "B M S" in voicelines.LINES["chip_seen"]


def test_the_chip_line_says_what_the_power_up_does():
    assert "two times" in voicelines.LINES["chip_found"].lower()


def test_a_level_announcement_is_three_clips_level_number_name():
    assert voicelines.level_intro(3) == ["level_word", "num_03", "name_2"]
    clips = voicelines.all_clips()
    for level in range(1, voicelines.MAX_LEVEL_VOICED + 1):
        for key in voicelines.level_intro(level):
            assert key in clips, (level, key)


def test_the_name_clip_repeats_the_last_name_after_the_list_ends_like_the_hud():
    assert voicelines.name_key(99) == f"name_{len(C.LEVEL_NAMES) - 1}"
    assert voicelines.name_key(1) == "name_0"


def test_beyond_the_numbers_it_just_says_next_level():
    assert voicelines.level_intro(voicelines.MAX_LEVEL_VOICED + 1) == ["next_level"]
    assert voicelines.level_intro(0) == ["next_level"]


def test_the_numbers_list_is_complete_and_unique():
    assert len(voicelines.NUMBERS) == 30 and len(set(voicelines.NUMBERS)) == 30


def test_the_effect_keeps_the_voice_in_range_and_adds_only_a_short_tail():
    x = speechlike()
    y = voicefx.cool(x)
    assert y.dtype == np.float32 and float(np.abs(y).max()) <= 0.95
    assert 0 <= len(y) - len(x) <= 0.4 * synth.SR
    assert not np.allclose(y[: len(x)], x[: len(y)], atol=0.05), "it should actually change the sound"


def test_the_effect_removes_the_rumble_below_the_band():
    t = np.arange(synth.SR) / synth.SR
    rumble = (0.5 * np.sin(2 * np.pi * 50 * t)).astype(np.float32)
    voice = speechlike()
    mix = rumble + voice
    y = voicefx.cool(mix)
    spec_in = np.abs(np.fft.rfft(mix))[40:60].max()
    spec_out = np.abs(np.fft.rfft(y[: len(mix)]))[40:60].max()
    assert spec_out < spec_in * 0.5


# ---------------- tightening the pauses between words ----------------
def burst(seconds, f=200.0, amp=0.5):
    t = np.arange(int(seconds * synth.SR)) / synth.SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)


def silence(seconds):
    return np.zeros(int(seconds * synth.SR), dtype=np.float32)


def longest_gap(x, threshold=0.02):
    quiet = np.abs(np.convolve(np.abs(x), np.ones(int(0.005 * synth.SR)) / int(0.005 * synth.SR), "same")) < threshold
    best = run = 0
    for q in quiet:
        run = run + 1 if q else 0
        best = max(best, run)
    return best / synth.SR


def test_a_long_pause_between_words_is_shortened():
    x = np.concatenate([burst(0.3), silence(0.45), burst(0.3)])
    y = voicefx.tighten(x, max_gap=0.07)
    assert longest_gap(y) <= 0.09
    assert len(y) < len(x) - 0.3 * synth.SR


def test_short_pauses_are_left_alone():
    x = np.concatenate([burst(0.3), silence(0.05), burst(0.3)])
    assert len(voicefx.tighten(x, max_gap=0.07)) == len(x)


def test_every_long_pause_is_shortened_not_just_the_first():
    x = np.concatenate([burst(0.2), silence(0.3), burst(0.2), silence(0.3), burst(0.2), silence(0.3), burst(0.2)])
    y = voicefx.tighten(x, max_gap=0.06)
    assert longest_gap(y) <= 0.08 and len(y) < len(x) - 0.6 * synth.SR


def test_the_speech_itself_is_untouched_and_the_joins_do_not_click():
    x = np.concatenate([burst(0.3), silence(0.4), burst(0.3)])
    y = voicefx.tighten(x, max_gap=0.07)
    assert np.allclose(y[: int(0.25 * synth.SR)], x[: int(0.25 * synth.SR)])
    assert float(np.abs(np.diff(y)).max()) < 0.2, "a jump at the join would click"
    assert abs(len(y) - (len(burst(0.3)) * 2 + int(0.07 * synth.SR))) < 0.02 * synth.SR


def test_silence_at_the_ends_is_not_touched():
    x = np.concatenate([silence(0.3), burst(0.2), silence(0.3)])
    assert len(voicefx.tighten(x, max_gap=0.07)) == len(x)


def test_a_clip_with_no_speech_comes_back_unchanged():
    assert len(voicefx.tighten(silence(1.0))) == synth.SR
