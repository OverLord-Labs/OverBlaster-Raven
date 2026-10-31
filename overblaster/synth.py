"""Sound effects and music for OverBlaster, synthesised with numpy at 44.1 kHz.

Nothing here is recorded or sampled, so there are no licences to track. tools/make_audio.py renders
these into assets/audio/*.wav; the game only plays the files. Everything is deterministic (fixed
random seeds) and mono.

Oscillators are band-limited and filters linear-phase (see dsp.py); sounds are built in layers (a
click, a body, a sub, a tail) and given a room with a convolution reverb, which is most of the
difference between a "beep" and a sound effect.
"""

import numpy as np

from . import dsp
from .dsp import SR, highpass, lowpass, lowpass_sweep, noise, peak_normalise, reverb, saw, sine, square, supersaw

BPM = 108
GAME_BARS = 16
TITLE_BARS = 8
CHARGE_TICKS = 8  # the rising ticks while you hold your aim on the Overlord BMS


# ----- small helpers -----
def env(n: int, attack: float, decay: float, curve: float = 3.0) -> np.ndarray:
    """Quick attack, then an exponential decay that has fallen by `curve` e-folds after `decay` seconds."""
    t = np.arange(n) / SR
    return np.clip(t / max(attack, 1e-4), 0.0, 1.0) * np.exp(-curve * t / max(decay, 1e-4))


def fade(x: np.ndarray, head: float = 0.004, tail: float = 0.02) -> np.ndarray:
    x = x.copy()
    h, t = max(1, int(head * SR)), max(1, int(tail * SR))
    x[:h] *= np.linspace(0.0, 1.0, h)
    x[-t:] *= np.linspace(1.0, 0.0, t)
    return x


def note(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def to_int16(x: np.ndarray) -> np.ndarray:
    return (np.clip(x, -1.0, 1.0) * 32767).astype(np.int16)


def place(track: np.ndarray, x: np.ndarray, start: float) -> None:
    s = int(start * SR)
    if s >= len(track):
        return
    seg = x[: len(track) - s]
    track[s : s + len(seg)] += seg


def bell(freq: float, seconds: float, decay: float = 0.5) -> np.ndarray:
    """A struck-metal tone: a few inharmonic partials, the higher ones dying faster."""
    n = int(seconds * SR)
    out = np.zeros(n)
    for ratio, amp, fall in ((1.0, 1.0, 1.0), (2.0, 0.45, 1.4), (2.76, 0.35, 1.8), (5.4, 0.18, 2.6), (8.93, 0.08, 3.5)):
        out += amp * sine(freq * ratio, n) * env(n, 0.001, decay / fall, 4.0)
    return out


def _trim(x: np.ndarray, seconds: float) -> np.ndarray:
    return x[: int(seconds * SR)]


# ----- sound effects -----
def hit() -> np.ndarray:
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    click = highpass(noise(n, 1), 3500) * np.exp(-t * 600)
    body = sine(np.linspace(260, 75, n), n) * env(n, 0.0005, 0.09)
    ring = bell(1250.0, 0.3, 0.12) * 0.12
    x = 0.8 * click + 0.9 * body + ring
    return fade(_trim(reverb(x, 0.3, 0.18, tail=0.1), 0.4), 0.0005, 0.06)


def explode() -> np.ndarray:
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    crack = highpass(noise(n, 2), 2500) * np.exp(-t * 45)
    boom = lowpass_sweep(noise(n, 3), 7000, 140) * env(n, 0.002, 0.75, 3.0)
    sub = np.tanh(sine(np.linspace(100, 30, n), n) * 2.2) * env(n, 0.002, 0.8)
    rng = np.random.default_rng(4)
    debris = lowpass(np.where(rng.uniform(size=n) < 0.0016 * np.exp(-t * 2.2), rng.uniform(-1, 1, n), 0.0), 6000) * 3.0
    x = 0.55 * crack + 1.0 * boom + 0.85 * sub + 0.35 * debris
    return fade(_trim(reverb(x, 1.0, 0.22, tail=0.5), 1.8), 0.001, 0.15)


def crystal() -> np.ndarray:
    n = int(0.9 * SR)
    x = np.zeros(n)
    place(x, bell(note(88), 0.9, 0.35) * 0.7, 0.0)  # E6
    place(x, bell(note(93), 0.8, 0.35) * 0.7, 0.09)  # A6
    place(x, highpass(noise(int(0.15 * SR), 5), 8000) * env(int(0.15 * SR), 0.001, 0.05) * 0.12, 0.0)
    return fade(_trim(reverb(x, 0.8, 0.3, tail=0.4), 1.2), 0.001, 0.12)


def charge_tick(i: int) -> np.ndarray:
    """One of the rising ticks while the hold on the Overlord BMS fills (i from 0 to CHARGE_TICKS - 1)."""
    n = int(0.14 * SR)
    f = note(72 + i * 2)  # a whole-tone climb from C5
    glide = f * (1.0 + 0.015 * np.linspace(0.0, 1.0, n))
    x = (sine(glide, n) * 0.7 + sine(glide * 2, n) * 0.25 + sine(glide * 3, n) * 0.08) * env(n, 0.003, 0.06, 3.5)
    return fade(x, 0.002, 0.03)


def _arp_track(notes, step: float, length: float, lead_in: float, decay: float, gain: float, seed: int = 0) -> np.ndarray:
    n = int(length * SR)
    track = np.zeros(n)
    for k, m in enumerate(notes):
        nn = int(0.8 * SR)
        tone = supersaw(note(m), nn, voices=5, detune=0.14, seed=seed + k) * env(nn, 0.004, decay, 3.0)
        place(track, tone * gain, lead_in + k * step)
    return track


def chip_collect() -> np.ndarray:
    n = int(2.4 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    rise = int(0.5 * SR)
    riser = highpass(noise(rise, 6), 1200) * np.linspace(0, 1, rise) ** 2 * 0.6  # a swell into the hit
    place(x, riser, 0.0)
    boom = (sine(np.linspace(130, 38, n), n) * env(n, 0.003, 0.7) * 0.9 + lowpass(noise(n, 7), 2500) * env(n, 0.001, 0.25) * 0.5)
    place(x, boom, 0.5)
    arp = _arp_track((60, 64, 67, 72, 76, 79, 84, 88), 0.075, 2.4, 0.5, 0.7, 0.16, seed=10)
    x += lowpass(arp, 7000)
    for k, m in enumerate((96, 100, 103)):  # sparkle on top
        place(x, bell(note(m), 0.6, 0.25) * 0.18, 0.62 + k * 0.1)
    return fade(_trim(reverb(x, 1.4, 0.3, tail=0.5), 2.9), 0.003, 0.25)


def level_start() -> np.ndarray:
    n = int(1.9 * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    wn = int(1.0 * SR)
    whoosh = lowpass_sweep(noise(wn, 8), 500, 7000) * np.sin(np.pi * np.linspace(0, 1, wn)) ** 2 * 0.7
    place(x, whoosh, 0.0)
    stab = np.zeros(n)
    for k, m in enumerate((45, 57, 60, 64, 69)):  # an A minor stab
        sn = int(1.2 * SR)
        stab_part = supersaw(note(m), sn, 5, 0.16, seed=20 + k) * env(sn, 0.004, 0.55, 3.0)
        place(stab, stab_part, 0.8)
    x += lowpass(stab, 3500) * 0.3
    place(x, sine(np.linspace(90, 40, int(0.6 * SR)), int(0.6 * SR)) * env(int(0.6 * SR), 0.002, 0.3) * 0.7, 0.8)
    return fade(_trim(reverb(x, 1.0, 0.25, tail=0.5), 2.3), 0.003, 0.2)


def level_clear() -> np.ndarray:
    n = int(1.9 * SR)
    x = np.zeros(n)
    for k, m in enumerate((67, 71, 74, 79)):  # G B D G, up, then held
        sn = int(1.5 * SR)
        tone = (square(note(m), sn, 0.3) * 0.25 + saw(note(m), sn) * 0.2 + sine(note(m), sn) * 0.3) * env(sn, 0.004, 0.7 if k == 3 else 0.35, 3.0)
        place(x, lowpass(tone, 6000), k * 0.15)
        place(x, bell(note(m + 12), 1.0, 0.5) * 0.25, k * 0.15)
    return fade(_trim(reverb(x, 1.0, 0.28, tail=0.6), 2.4), 0.003, 0.25)


def hull_death() -> np.ndarray:
    n = int(2.4 * SR)
    t = np.arange(n) / SR
    crack = highpass(noise(n, 9), 2000) * np.exp(-t * 28)
    boom = lowpass_sweep(noise(n, 10), 5000, 70) * env(n, 0.003, 1.3, 3.0)
    sub = np.tanh(sine(np.linspace(85, 22, n), n) * 2.5) * env(n, 0.003, 1.4)
    groan = lowpass_sweep(saw(np.linspace(190, 55, n), n) * (1 + 0.4 * sine(7.0, n)), 2500, 150) * env(n, 0.05, 1.0, 3.0) * 0.4
    rng = np.random.default_rng(11)
    debris = lowpass(np.where(rng.uniform(size=n) < 0.002 * np.exp(-t * 1.3), rng.uniform(-1, 1, n), 0.0), 5000) * 3.0
    x = 0.55 * crack + 1.0 * boom + 0.95 * sub + groan + 0.4 * debris
    return fade(_trim(reverb(x, 1.6, 0.3, tail=0.8), 3.0), 0.001, 0.3)


def battery_dead() -> np.ndarray:
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    f = np.geomspace(700, 55, n)
    x = (saw(f, n) * 0.5 + sine(f, n) * 0.5) * np.exp(-t * 1.6)
    x = lowpass_sweep(x, 6000, 220)
    hiss = lowpass(noise(n, 12), 4000) * np.exp(-t * 6) * 0.15
    thump = sine(np.linspace(120, 35, int(0.4 * SR)), int(0.4 * SR)) * env(int(0.4 * SR), 0.002, 0.2)
    place(x, thump * 0.7, 1.2)
    return fade(_trim(reverb(x + hiss, 0.6, 0.15, tail=0.3), 2.1), 0.003, 0.2)


def ui_confirm() -> np.ndarray:
    x = np.zeros(int(0.5 * SR))
    place(x, bell(note(84), 0.4, 0.15) * 0.8, 0.0)
    place(x, bell(note(91), 0.4, 0.18) * 0.8, 0.07)
    return fade(_trim(reverb(x, 0.4, 0.2, tail=0.15), 0.65), 0.001, 0.08)


def low_battery() -> np.ndarray:
    n = int(0.65 * SR)
    one = square(note(81), int(0.12 * SR), 0.45) * env(int(0.12 * SR), 0.002, 0.09)
    x = np.zeros(n)
    place(x, one, 0.0)
    place(x, one, 0.22)
    return fade(_trim(reverb(lowpass(x, 5000) * 0.8, 0.3, 0.15, tail=0.15), 0.8), 0.002, 0.08)


SFX = {
    "hit": hit,
    "explode": explode,
    "crystal": crystal,
    "chip_collect": chip_collect,
    "level_start": level_start,
    "level_clear": level_clear,
    "hull_death": hull_death,
    "battery_dead": battery_dead,
    "ui_confirm": ui_confirm,
    "low_battery": low_battery,
}


def render_sfx(name: str) -> np.ndarray:
    return peak_normalise(dsp.limit(SFX[name](), 0.97), 0.85)


# ----- music -----
CHORDS = {  # name: (bass note, arpeggio tones, pad tones) as MIDI numbers
    "Am": (45, (69, 72, 76), (57, 60, 64)),
    "F": (41, (65, 69, 72), (53, 57, 60)),
    "C": (48, (72, 76, 79), (60, 64, 67)),
    "G": (43, (67, 71, 74), (55, 59, 62)),
    "Dm": (38, (65, 69, 74), (50, 53, 57)),
    "E": (40, (68, 71, 76), (52, 56, 59)),
}
GAME_PROGRESSION = ("Am", "Am", "F", "F", "C", "C", "G", "G", "Dm", "Dm", "F", "F", "Am", "Am", "E", "E")
TITLE_PROGRESSION = ("Am", "Am", "F", "F", "C", "C", "G", "G")


def _kick() -> np.ndarray:
    n = int(0.4 * SR)
    t = np.arange(n) / SR
    body = sine(np.linspace(190, 46, n) * 1.0 + 0 * t, n) * env(n, 0.0005, 0.28, 4.0)
    click = highpass(noise(n, 31), 2500) * np.exp(-t * 400) * 0.5
    return np.tanh((body + click) * 1.4)


def _snare() -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    snap = dsp.bandpass(noise(n, 32), 1400, 9000) * env(n, 0.0005, 0.14, 4.0)
    body = sine(np.linspace(240, 170, n), n) * env(n, 0.0005, 0.07, 4.0) * 0.6
    return snap * 0.9 + body


def _hat(open_: bool = False) -> np.ndarray:
    n = int((0.22 if open_ else 0.07) * SR)
    return highpass(noise(n, 33 if open_ else 34), 7500) * env(n, 0.0004, 0.16 if open_ else 0.035, 4.0)


def render_music(kind: str) -> np.ndarray:
    drive = kind == "game"
    progression = GAME_PROGRESSION if drive else TITLE_PROGRESSION
    bars = len(progression)
    beat = 60.0 / BPM
    bar = 4 * beat
    total = int(round(bars * bar * SR))
    room = int(3.5 * SR)  # space after the end for tails: wrapped onto the start so the loop is seamless
    size = total + room

    pad, arp, bass, lead = (np.zeros(size) for _ in range(4))
    kick, snare, hats = (np.zeros(size) for _ in range(3))
    kick_times = []

    for b, name in enumerate(progression):
        root, arp_tones, pad_tones = CHORDS[name]
        t0 = b * bar
        # pad: a wide supersaw chord
        pn = int((bar + 0.9) * SR)
        chord = np.zeros(pn)
        for k, m in enumerate(pad_tones):
            chord += supersaw(note(m), pn, voices=5, detune=0.18, seed=40 + k + 3 * b)
        shape = np.minimum(1.0, np.arange(pn) / (0.35 * SR)) * np.minimum(1.0, (pn - np.arange(pn)) / (0.5 * SR))
        place(pad, chord * shape / 3.0, t0)

        if drive:
            # sixteenth-note arpeggio, up an octave every other bar
            step = beat / 4
            for k in range(16):
                m = arp_tones[(0, 1, 2, 1)[k % 4]] + (12 if b % 2 else 0)
                nn = int(0.35 * SR)
                tone = (square(note(m), nn, 0.38) * 0.55 + saw(note(m), nn) * 0.45) * env(nn, 0.002, 0.13, 3.0)
                place(arp, tone, t0 + k * step)
            # pumping eighth-note bass
            for k in range(8):
                m = root + (12 if k % 4 == 3 else 0)
                nn = int(0.4 * SR)
                tone = (saw(note(m), nn) * 0.6 + sine(note(m), nn) * 0.6) * env(nn, 0.004, 0.2, 3.0)
                place(bass, tone, t0 + k * beat / 2)
            # a lead line in the second half
            if b >= 8:
                motif = (arp_tones[2], arp_tones[1], arp_tones[2], arp_tones[0] + 12)
                for k, m in enumerate(motif):
                    nn = int(0.55 * SR)
                    vib = 1.0 + 0.004 * sine(5.5, nn)
                    tone = (saw(note(m + 12) * vib, nn) * 0.5 + square(note(m + 12) * vib, nn, 0.45) * 0.5) * env(nn, 0.01, 0.35, 3.0)
                    place(lead, tone, t0 + k * beat)
            # drums
            for k in range(4):
                bt = t0 + k * beat
                place(kick, _kick(), bt)
                kick_times.append(bt)
                if k % 2 == 1:
                    place(snare, _snare(), bt)
                place(hats, _hat() * 0.8, bt + beat / 2)
                place(hats, _hat() * 0.3, bt + beat / 4)
                place(hats, _hat() * 0.3, bt + 3 * beat / 4)
            if b % 8 == 7:  # a snare roll into the next section
                for k in range(8):
                    place(snare, _snare() * (0.35 + 0.08 * k), t0 + 3 * beat + k * beat / 8)
            place(hats, _hat(open_=True) * 0.6, t0 + 3.5 * beat)
        else:  # the title: a slow bell arpeggio over the pad, a held sub note
            step = beat
            for k in range(4):
                m = arp_tones[(0, 2, 1, 2)[k % 4]] + 12
                place(arp, bell(note(m), 1.6, 0.9) * 0.5, t0 + k * step)
            nn = int((bar + 0.4) * SR)
            place(bass, sine(note(root), nn) * np.minimum(1.0, np.arange(nn) / (0.2 * SR)) * np.minimum(1.0, (nn - np.arange(nn)) / (0.4 * SR)) * 0.6, t0)

    # shape each part
    pump = dsp.sidechain(size, kick_times, depth=0.55, release=0.2) if drive else np.ones(size)
    pad = lowpass(pad, 2200) * pump
    arp = dsp.delay(lowpass(arp, 6000), beat * 0.75, 0.38, taps=3)
    arp = reverb(arp, 1.4, 0.3)
    bass = lowpass(bass, 800) * pump
    lead = reverb(lowpass(lead, 4500), 1.2, 0.3) if drive else lead
    snare = reverb(snare, 0.9, 0.3)
    if drive:
        mix = 0.9 * kick + 0.45 * snare + 0.13 * hats + 0.5 * bass + 0.2 * arp + 0.3 * pad + 0.15 * lead
    else:
        mix = reverb(0.55 * pad + 0.5 * arp + 0.5 * bass, 2.2, 0.35)
    mix = dsp.compress(mix, -16.0, 2.5)
    mix = dsp.limit(mix, 0.95)

    out = mix[:total].copy()
    tail = mix[total : total + room]
    out[: len(tail)] += tail  # the tail of the last bar rings into the first
    out = dsp.limit(out, 0.95)
    seam = int(0.003 * SR)  # a few milliseconds of fade at each end so the loop point cannot click
    out[:seam] *= np.linspace(0.0, 1.0, seam)
    out[-seam:] *= np.linspace(1.0, 0.0, seam)
    return peak_normalise(out, 0.9 if drive else 0.4)  # the title is a pad with few peaks: lower, so it is calmer


# ----- the web game's synthesised effects (OverBlaster-web src/platform/audio.ts), as numpy clips -----
ALARM_S = 5.0  # 11 cycles of the 2.2 Hz pulse and 3700 of the 740 Hz tone: a whole number of both, so it loops seamlessly
DRONE_S = 10.0  # whole cycles of 55, 82.4 and 110.3 Hz (550, 824 and 1103)
DRONE_GAIN, DRONE_ATTACK_TAU, DRONE_RELEASE_TAU = 0.07, 1.2, 0.4  # the loop's level, and how fast it comes in and goes out


def _sweep(kind: str, f0: float, f1: float, dur: float, vol: float) -> np.ndarray:
    """An oscillator gliding exponentially from f0 to f1 while its gain falls exponentially from vol to 0.001; it is
    stopped 20 ms after the glide ends (a WebAudio exponentialRampToValueAtTime pair, which is what the web plays)."""
    n = int((dur + 0.02) * SR)
    t = np.arange(n) / SR
    u = np.clip(t / dur, 0.0, 1.0)
    freq = f0 * (f1 / f0) ** u
    wave = (dsp.saw if kind == "sawtooth" else dsp.square)(freq, n)
    return wave * vol * (0.001 / vol) ** u


def _burst(dur: float, vol: float, seed: int) -> np.ndarray:
    """Noise through a 1.5 kHz highpass with an exponential decay."""
    n = int((dur + 0.02) * SR)
    u = np.clip(np.arange(n) / SR / dur, 0.0, 1.0)
    return highpass(noise(n, seed), 1500.0) * vol * (0.001 / vol) ** u


def render_zap(kind: str) -> np.ndarray:
    """"eject" (a rock spits out a bad gauge), "bad" (you took one) or "pop"."""
    parts = []  # (delay s, samples)
    if kind == "eject":
        gain = 0.5
        parts = [(0.0, _sweep("square", 1000, 620, 0.07, 0.3)), (0.11, _sweep("square", 1000, 620, 0.07, 0.3)), (0.0, _burst(0.18, 0.25, 11))]
    elif kind == "bad":
        gain = 0.9
        parts = [(0.0, _sweep("sawtooth", 760, 40, 1.0, 0.5)), (0.0, _sweep("square", 190, 38, 1.0, 0.35)), (0.15, _sweep("square", 95, 30, 0.8, 0.3)), (0.0, _burst(0.6, 0.45, 12))]
    elif kind == "pop":
        gain = 0.6
        parts = [(0.0, _sweep("square", 1500, 260, 0.12, 0.3)), (0.0, _burst(0.12, 0.3, 13))]
    else:
        raise KeyError(kind)
    out = np.zeros(max(int(d * SR) + len(x) for d, x in parts))
    for d, x in parts:
        place(out, x, d)
    return (out * gain).astype(np.float32)


def render_alarm() -> np.ndarray:
    """The red-alert loop: a 740 Hz square tone whose gain a 2.2 Hz square wave switches between 0 and 0.07."""
    n = int(ALARM_S * SR)
    t = np.arange(n) / SR
    lfo = np.where((t * 2.2) % 1.0 < 0.5, 1.0, -1.0)
    return (dsp.square(740.0, n) * (0.035 + 0.035 * lfo)).astype(np.float32)


def render_drone() -> np.ndarray:
    """The engine drone loop (unit level; the player fades it in at DRONE_GAIN): 55 Hz triangle + two sines."""
    n = int(DRONE_S * SR)
    tri = 2.0 / np.pi * np.arcsin(np.clip(np.sin(2 * np.pi * np.cumsum(np.full(n, 55.0)) / SR), -1.0, 1.0))
    return (0.6 * tri + 0.35 * dsp.sine(82.4, n) + 0.35 * dsp.sine(110.3, n)).astype(np.float32)


# what Bank.get builds on demand for names that have no WAV
GENERATED = {
    "zap_eject": lambda: render_zap("eject"),
    "zap_bad": lambda: render_zap("bad"),
    "zap_pop": lambda: render_zap("pop"),
    "loop_alarm": render_alarm,
    "loop_drone": render_drone,
}
