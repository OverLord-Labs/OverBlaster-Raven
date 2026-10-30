"""Signal-processing building blocks for the synthesiser, in plain numpy (no scipy).

Oscillators are band-limited (PolyBLEP), so high notes do not alias into the harsh, metallic fizz
that naive saw and square waves make. Filters are linear-phase FIRs applied with an FFT, so they
do not smear transients and they can be as steep as needed. The reverb is a convolution with a
synthetic, darkening noise tail. Everything is deterministic.
"""

from typing import Iterable, Optional

import numpy as np

SR = 44100


# ----- helpers -----
def _pow2(n: int) -> int:
    return 1 << (int(n) - 1).bit_length()


def fft_convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    size = _pow2(n)
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[:n]


def _freq_array(freq, n: int) -> np.ndarray:
    return np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,))


# ----- oscillators -----
def _polyblep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """The correction that removes the aliasing from a discontinuity at phase 0."""
    out = np.zeros_like(t)
    lo = t < dt
    x = t[lo] / dt[lo]
    out[lo] = x + x - x * x - 1.0
    hi = t > 1.0 - dt
    x = (t[hi] - 1.0) / dt[hi]
    out[hi] = x * x + x + x + 1.0
    return out


def sine(freq, n: int, phase: float = 0.0) -> np.ndarray:
    f = _freq_array(freq, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR + phase)


def saw(freq, n: int, phase: float = 0.0) -> np.ndarray:
    f = _freq_array(freq, n)
    dt = f / SR
    t = (np.cumsum(dt) + phase) % 1.0
    return 2.0 * t - 1.0 - _polyblep(t, dt)


def square(freq, n: int, duty: float = 0.5, phase: float = 0.0) -> np.ndarray:
    f = _freq_array(freq, n)
    dt = f / SR
    t = (np.cumsum(dt) + phase) % 1.0
    y = np.where(t < duty, 1.0, -1.0)
    return y + _polyblep(t, dt) - _polyblep((t + 1.0 - duty) % 1.0, dt)


def supersaw(freq, n: int, voices: int = 5, detune: float = 0.15, seed: int = 0) -> np.ndarray:
    """Several slightly detuned saws with different start phases: the big, wide synth sound."""
    rng = np.random.default_rng(seed)
    f = _freq_array(freq, n)
    out = np.zeros(n)
    for v in range(voices):
        cents = (v - (voices - 1) / 2) / max(1, (voices - 1) / 2) * detune
        out += saw(f * 2 ** (cents / 12.0), n, phase=float(rng.uniform(0, 1)))
    return out / voices * 1.4


def noise(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(-1.0, 1.0, n)


# ----- filters -----
def _taps(cutoff: float) -> int:
    return int(min(4097, max(257, 8 * SR / max(cutoff, 20.0)))) | 1


def _kernel(cutoff: float, taps: int) -> np.ndarray:
    m = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff / SR * m) * np.kaiser(taps, 8.6)
    return h / h.sum()


def _apply(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    d = (len(h) - 1) // 2
    return fft_convolve(x, h)[d : d + len(x)]


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    return _apply(x, _kernel(cutoff, _taps(cutoff)))


def highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    taps = _taps(cutoff)
    h = -_kernel(cutoff, taps)
    h[(taps - 1) // 2] += 1.0
    return _apply(x, h)


def bandpass(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return lowpass(highpass(x, lo), hi)


def lowpass_sweep(x: np.ndarray, start: float, end: float, steps: int = 12) -> np.ndarray:
    """A lowpass whose cutoff moves (exponentially) from `start` to `end` over the clip."""
    n = len(x)
    cuts = np.geomspace(start, end, steps)
    bank = [lowpass(x, c) for c in cuts]
    pos = np.linspace(0, steps - 1, n)
    lo = np.clip(pos.astype(int), 0, steps - 2)
    frac = pos - lo
    out = np.zeros(n)
    for i in range(steps - 1):
        sel = lo == i
        out[sel] = bank[i][sel] * (1 - frac[sel]) + bank[i + 1][sel] * frac[sel]
    return out


def shelf(x: np.ndarray, cutoff: float, gain_db: float, high: bool = True) -> np.ndarray:
    """Boost or cut everything above (high=True) or below `cutoff` by `gain_db`."""
    g = 10 ** (gain_db / 20.0) - 1.0
    part = highpass(x, cutoff) if high else lowpass(x, cutoff)
    return x + g * part


# ----- space -----
def reverb(x: np.ndarray, seconds: float, mix: float, tail: float = 0.0, damping: float = 5500.0, seed: int = 21, predelay: float = 0.012) -> np.ndarray:
    """Convolve with a synthetic room: noise that decays and darkens. `tail` seconds are added to the end."""
    out_len = len(x) + int(tail * SR)
    if mix <= 0:
        return np.concatenate([x, np.zeros(out_len - len(x))])
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.random.default_rng(seed).normal(0.0, 1.0, n) * np.exp(-6.9 * t / seconds)
    ir = 0.5 * ir + 0.5 * lowpass(ir, damping) * 1.4  # the later it is, the darker: blend with a darker copy
    ir = lowpass(ir, damping * 2.0)
    pd = int(predelay * SR)
    ir = np.concatenate([np.zeros(pd), ir])
    ir /= np.sqrt((ir ** 2).sum()) + 1e-12
    wet = fft_convolve(np.concatenate([x, np.zeros(out_len - len(x))]), ir)[:out_len]
    dry = np.concatenate([x, np.zeros(out_len - len(x))])
    return dry * (1.0 - mix * 0.5) + wet * mix * 1.0


def delay(x: np.ndarray, seconds: float, feedback: float, taps: int = 3, mix: float = 1.0) -> np.ndarray:
    """Add decaying repeats (an echo). The output is the same length: repeats past the end are dropped."""
    d = int(seconds * SR)
    out = x.copy()
    for k in range(1, taps + 1):
        if d * k >= len(x):
            break
        out[d * k :] += x[: len(x) - d * k] * feedback ** k * mix
    return out


def sidechain(n: int, triggers: Iterable[float], depth: float = 0.7, release: float = 0.15) -> np.ndarray:
    """A gain curve that drops to (1 - depth) at each trigger time (seconds) and recovers: the pumping sound."""
    g = np.ones(n)
    t = np.arange(n) / SR
    for tr in triggers:
        s = int(tr * SR)
        if s >= n:
            continue
        dip = 1.0 - depth * np.exp(-(t[s:] - tr) / release * 3.0)
        g[s:] = np.minimum(g[s:], dip)
    return g


# ----- dynamics -----
def compress(x: np.ndarray, threshold_db: float = -18.0, ratio: float = 3.0, attack: float = 0.005, release: float = 0.12, block: int = 128) -> np.ndarray:
    """A feed-forward compressor working on short blocks (fast, and easy to reason about)."""
    n = len(x)
    pad = (-n) % block
    xp = np.concatenate([x, np.zeros(pad)])
    peaks = np.abs(xp).reshape(-1, block).max(axis=1) + 1e-9
    level_db = 20 * np.log10(peaks)
    over = np.maximum(0.0, level_db - threshold_db)
    target = -over * (1 - 1 / ratio)  # dB of gain reduction wanted
    a, r = np.exp(-block / (attack * SR)), np.exp(-block / (release * SR))
    gr = np.zeros(len(target))
    cur = 0.0
    for i, t in enumerate(target):
        coef = a if t < cur else r  # reduction grows fast (attack) and relaxes slowly (release)
        cur = coef * cur + (1 - coef) * t
        gr[i] = cur
    gain = np.repeat(10 ** (gr / 20.0), block)[:n]
    return x * gain


def limit(x: np.ndarray, ceiling: float = 0.95) -> np.ndarray:
    """Transparent below the ceiling, soft above it: never exceeds `ceiling`."""
    knee = ceiling * 0.8
    mag = np.abs(x)
    over = mag > knee
    out = x.copy()
    out[over] = np.sign(x[over]) * (knee + (ceiling - knee) * np.tanh((mag[over] - knee) / (ceiling - knee)))
    return out


def resample(x: np.ndarray, rate_in: int, rate_out: int) -> np.ndarray:
    """Change the sample rate by padding or cutting the spectrum (exact for band-limited sound)."""
    if rate_in == rate_out or len(x) == 0:
        return x.copy()
    n_out = int(round(len(x) * rate_out / rate_in))
    spec = np.fft.rfft(x)
    out_spec = np.zeros(n_out // 2 + 1, dtype=complex)
    k = min(len(spec), len(out_spec))
    out_spec[:k] = spec[:k]
    return np.fft.irfft(out_spec, n_out) * (n_out / len(x))


def peak_normalise(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.abs(x).max())
    return (x * (peak / m)).astype(np.float32) if m > 0 else x.astype(np.float32)
