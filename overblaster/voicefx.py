"""Gives the text-to-speech voice a cool ship's-computer sound. numpy only; used by tools/make_voice.py.

The clean voice is kept clear and present: rumble out, a little lift in the presence range,
compression for punch, then a light slowly-moving double, a faint metallic edge and a small room.
Every stage has an amount in EFFECT, so it is easy to turn down if it is too much.
"""

import numpy as np

from . import dsp

EFFECT = {
    "highpass": 130.0,
    "presence_db": 2.5,  # lift above 3 kHz
    "threshold_db": -20.0,
    "ratio": 3.0,
    "drive": 1.25,  # gentle saturation
    "chorus_mix": 0.22,
    "chorus_ms": 11.0,
    "ring_hz": 70.0,
    "ring_mix": 0.05,
    "room_seconds": 0.5,
    "room_mix": 0.14,
}


def tighten(x: np.ndarray, max_gap: float = 0.07, floor: float = 0.02, fade: float = 0.01) -> np.ndarray:
    """Shorten every pause inside the clip to at most `max_gap` seconds.

    Text-to-speech leaves a long gap between words and between spelled letters ("B M S"). A pause is a
    run where the (5 ms smoothed) level is under `floor`; one longer than max_gap is cut down to
    max_gap, keeping its start and end so the speech is untouched, and the join is faded so it cannot
    click. Silence at the very start and end is left alone (the caller trims that).
    """
    sr = dsp.SR
    x = np.asarray(x, dtype=np.float64)
    win = max(1, int(0.005 * sr))
    level = np.convolve(np.abs(x), np.ones(win) / win, mode="same")
    quiet = level < floor
    loud = np.nonzero(~quiet)[0]
    if not len(loud):
        return x.copy()
    first, last = loud[0], loud[-1]
    keep_min = int(max_gap * sr)
    pieces = []
    pos = first
    i = first
    n_fade = max(1, int(fade * sr))
    while i <= last:
        if quiet[i]:
            j = i
            while j <= last and quiet[j]:
                j += 1
            if j - i > keep_min:
                half = keep_min // 2
                pieces.append(x[pos : i + half])
                pos = j - (keep_min - half)
            i = j
        else:
            i += 1
    pieces.append(x[pos : last + 1])
    out = pieces[0]
    for p in pieces[1:]:  # join with a short crossfade across the shortened pause
        f = min(n_fade, len(out), len(p))
        ramp = np.linspace(0.0, 1.0, f)
        out = np.concatenate([out[:-f], out[-f:] * (1 - ramp) + p[:f] * ramp, p[f:]])
    return np.concatenate([x[:first], out, x[last + 1 :]])


def cool(x: np.ndarray, effect=EFFECT) -> np.ndarray:
    """Process a mono float voice clip at dsp.SR. The result is a little longer (the room's tail)."""
    sr = dsp.SR
    n = len(x)
    y = dsp.highpass(x.astype(np.float64), effect["highpass"])
    y = dsp.shelf(y, 3000.0, effect["presence_db"], high=True)
    y = dsp.compress(y, effect["threshold_db"], effect["ratio"], attack=0.004, release=0.09)
    y = np.tanh(y * effect["drive"]) / np.tanh(effect["drive"])
    t = np.arange(n) / sr
    delay = (effect["chorus_ms"] + 2.5 * np.sin(2 * np.pi * 0.35 * t)) / 1000.0 * sr
    doubled = np.interp(np.clip(np.arange(n) - delay, 0, n - 1), np.arange(n), y)
    y = y * (1 - effect["chorus_mix"] * 0.5) + doubled * effect["chorus_mix"]
    y = y * (1 - effect["ring_mix"]) + y * np.sin(2 * np.pi * effect["ring_hz"] * t) * effect["ring_mix"] * 2.0
    y = dsp.reverb(y, effect["room_seconds"], effect["room_mix"], tail=0.25)
    fade = int(0.006 * sr)
    y[:fade] *= np.linspace(0.0, 1.0, fade)
    y[-int(0.06 * sr):] *= np.linspace(1.0, 0.0, int(0.06 * sr))
    return dsp.peak_normalise(dsp.limit(y, 0.97), 0.9)
