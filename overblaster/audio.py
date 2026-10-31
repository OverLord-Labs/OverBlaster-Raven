"""Mixing for OverBlaster's sound: looping music, short effects and one voice line, in numpy.

The glasses' Speaker plays one WAV at a time, so the game mixes everything itself and hands the
output to a sink (audiosink.py) in small chunks. Everything here is pure numpy and tested without a
sound card.

The microphone is also the trigger ("Pew"), and it hears the game's own sound. EchoGate keeps that
sound from pulling the trigger: it mutes the mic while the voice speaks, and learns how much of what
is being played reaches the mic so it can subtract it from the level.
"""

import collections
import os
import wave
from typing import Deque, Dict, List, Optional

import numpy as np

from . import config as C
from . import synth
from .synth import SR, to_int16

MAX_EFFECTS = 8
LOOP_DROP = 0.02  # a loop that is fading out is dropped once it is below this fraction of its level
VOICE_TAIL_S = 0.15  # the room keeps ringing a moment after a voice line ends
LEVEL_WINDOW_S = 0.3  # the mic hears what was played a little earlier, so level looks back this far
ECHO_K0 = 0.5  # until it has learned, assume the mic hears half of what is played
ECHO_K_MAX = 2.0
ECHO_MIN_PLAY = 0.02  # playback quieter than this teaches nothing
ECHO_WINDOW = 60  # ticks of history the estimate is the median of
ECHO_SAFETY = 1.2


def load_wav(path: str) -> np.ndarray:
    """A mono 16-bit WAV as floats in [-1, 1] at SR (resampled by linear interpolation if it isn't)."""
    with wave.open(path, "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError(f"{path}: only 16-bit WAV is supported")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if rate != SR and len(x):
        t_new = np.arange(int(len(x) * SR / rate)) / SR
        x = np.interp(t_new, np.arange(len(x)) / rate, x).astype(np.float32)
    return x


def join(clips: List[np.ndarray], gap: float = 0.08) -> np.ndarray:
    """Clips one after another with a short silence between them."""
    pause = np.zeros(int(gap * SR), dtype=np.float32)
    parts: List[np.ndarray] = []
    for i, c in enumerate(clips):
        if i:
            parts.append(pause)
        parts.append(c.astype(np.float32))
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


class _Clip:
    __slots__ = ("x", "pos", "gain")

    def __init__(self, x: np.ndarray, gain: float, pos: int = 0) -> None:
        self.x, self.pos, self.gain = x, pos, gain


class _Loop:
    """A looping effect (the alarm, the drone) that fades toward a target level: exponentially, like a
    WebAudio setTargetAtTime. tau 0 jumps. Once told to stop it is dropped when it has all but faded out."""

    __slots__ = ("x", "pos", "gain", "level", "target", "tau")

    def __init__(self, x: np.ndarray, gain: float, tau: float) -> None:
        self.x, self.pos, self.gain, self.tau = x, 0, gain, tau
        self.target = 1.0
        self.level = 0.0 if tau > 0 else 1.0


class Mixer:
    def __init__(self, master: float = C.AUDIO_MASTER, music_gain: float = C.AUDIO_MUSIC, sfx_gain: float = C.AUDIO_SFX,
                 voice_gain: float = C.AUDIO_VOICE, duck: float = C.AUDIO_DUCK) -> None:
        self.master, self.music_gain, self.sfx_gain, self.voice_gain, self.duck = master, music_gain, sfx_gain, voice_gain, duck
        self._music: Optional[np.ndarray] = None
        self._music_pos = 0
        self._music_level = 0.0  # fades toward the target
        self._music_target = 0.0
        self._music_rate = 1.0  # level change per second
        self._duck_level = 1.0
        self._effects: List[_Clip] = []
        self._loops: Dict[str, _Loop] = {}
        self._voice: Optional[_Clip] = None
        self._voice_end = -1e9  # in rendered seconds
        self._clock = 0.0
        self._recent: Deque = collections.deque()  # (seconds, rms) of recent chunks

    # ----- control -----
    def set_music(self, x: Optional[np.ndarray], fade_s: float = 0.6) -> None:
        if x is None:
            self._music_target = 0.0
            self._music_rate = 1.0 / fade_s if fade_s > 0 else 1e9
            if fade_s <= 0:
                self._music, self._music_level = None, 0.0
            return
        if self._music is not x:
            self._music, self._music_pos = x, 0
        self._music_target = 1.0
        self._music_rate = 1.0 / fade_s if fade_s > 0 else 1e9
        if fade_s <= 0:
            self._music_level = 1.0

    def play(self, x: np.ndarray, gain: float = 1.0, voice: bool = False, offset: float = 0.0) -> _Clip:
        """Play a clip once, starting `offset` seconds into it. Returns a handle for stop()."""
        pos = min(len(x), max(0, int(offset * SR)))
        if voice:
            self._voice = _Clip(x, gain * self.voice_gain, pos)
            self._voice_end = self._clock + (len(x) - pos) / SR + VOICE_TAIL_S
            return self._voice
        clip = _Clip(x, gain * self.sfx_gain, pos)
        self._effects.append(clip)
        del self._effects[:-MAX_EFFECTS]
        return clip

    def stop(self, clip: Optional[_Clip]) -> None:
        """Cut a clip that play() returned (a no-op if it has already finished)."""
        if clip is not None and clip in self._effects:
            self._effects.remove(clip)

    def stop_voice(self) -> None:
        self._voice = None
        self._voice_end = self._clock

    def start_loop(self, key: str, x: np.ndarray, gain: float = 1.0, attack_tau: float = 0.0) -> None:
        """Start (or restart) a loop. It reaches `gain` with time constant `attack_tau` seconds (0 = at once)."""
        self.stop_loop(key)
        self._loops[key] = _Loop(x, gain * self.sfx_gain, attack_tau)

    def stop_loop(self, key: str, release_tau: float = 0.0) -> None:
        """Stop a loop: at once, or fading out with time constant `release_tau` seconds."""
        lp = self._loops.get(key)
        if lp is None:
            return
        if release_tau <= 0:
            del self._loops[key]
        else:
            lp.target, lp.tau = 0.0, release_tau

    def loop_running(self, key: str) -> bool:
        lp = self._loops.get(key)
        return lp is not None and lp.target > 0

    @property
    def active_effects(self) -> int:
        return len(self._effects)

    @property
    def speaking(self) -> bool:
        return self._clock < self._voice_end

    @property
    def level(self) -> float:
        """How loud the output has been over the last moments (0 to 1): what the mic may be hearing."""
        return max((r for _, r in self._recent), default=0.0)

    # ----- rendering -----
    def render(self, n: int) -> np.ndarray:
        out = np.zeros(n, dtype=np.float64)
        dt = n / SR
        if self._music is not None and (self._music_level > 0 or self._music_target > 0):
            idx = (self._music_pos + np.arange(n)) % len(self._music)
            self._music_pos = int((self._music_pos + n) % len(self._music))
            lvl0 = self._music_level
            step = self._music_rate * dt
            lvl1 = min(self._music_target, lvl0 + step) if self._music_target > lvl0 else max(self._music_target, lvl0 - step)
            self._music_level = lvl1
            ramp = np.linspace(lvl0, lvl1, n)
            duck_target = self.duck if self._voice is not None else 1.0
            d0 = self._duck_level
            d1 = d0 + (duck_target - d0) * min(1.0, dt * 8.0)
            self._duck_level = d1
            out += self._music[idx] * ramp * np.linspace(d0, d1, n) * self.music_gain
            if self._music_target == 0.0 and lvl1 == 0.0:
                self._music = None
        for c in self._effects:
            seg = c.x[c.pos : c.pos + n]
            out[: len(seg)] += seg * c.gain
            c.pos += n
        self._effects = [c for c in self._effects if c.pos < len(c.x)]
        if self._voice is not None:
            seg = self._voice.x[self._voice.pos : self._voice.pos + n]
            out[: len(seg)] += seg * self._voice.gain
            self._voice.pos += n
            if self._voice.pos >= len(self._voice.x):
                self._voice = None
        for key, lp in list(self._loops.items()):
            idx = (lp.pos + np.arange(n)) % len(lp.x)
            lp.pos = int((lp.pos + n) % len(lp.x))
            l0 = lp.level
            l1 = lp.target + (l0 - lp.target) * float(np.exp(-dt / lp.tau)) if lp.tau > 0 else lp.target
            lp.level = l1
            out += lp.x[idx] * np.linspace(l0, l1, n) * lp.gain
            if lp.target == 0.0 and l1 < LOOP_DROP:
                del self._loops[key]
        out = np.tanh(out * self.master)
        out = np.clip(out, -1.0, 1.0).astype(np.float32)
        self._clock += dt
        self._recent.append((self._clock, float(np.sqrt((out.astype(np.float64) ** 2).mean())) if n else 0.0))
        while self._recent and self._recent[0][0] < self._clock - LEVEL_WINDOW_S:
            self._recent.popleft()
        return out

    def render_pcm(self, n: int) -> bytes:
        return to_int16(self.render(n)).tobytes()


class EchoGate:
    """Keeps the game's own sound from pulling the "Pew" trigger.

    `apply(mic, playing, speaking)` returns the mic level with the playback's share removed. While a
    voice line speaks it returns 0. The share is learned: whenever something is playing, mic / playing
    is recorded, and the median of the last second or so is used, so a shout now and then doesn't
    spoil it.
    """

    def __init__(self) -> None:
        self._ratios: Deque[float] = collections.deque(maxlen=ECHO_WINDOW)

    @property
    def k(self) -> float:
        if len(self._ratios) < 10:
            return ECHO_K0
        return min(ECHO_K_MAX, float(np.median(self._ratios)))

    def apply(self, mic: float, playing: float, speaking: bool) -> float:
        if speaking:
            return 0.0
        if playing >= ECHO_MIN_PLAY:
            self._ratios.append(mic / playing)
        return max(0.0, mic - self.k * playing * ECHO_SAFETY) if playing >= ECHO_MIN_PLAY else mic


# ----- the sound bank -----
ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audio")


class Bank:
    """Loads WAVs from assets/audio on first use and keeps them. Names in synth.GENERATED (zap_*, loop_*) are synthesised instead."""

    def __init__(self, folder: str = ASSET_DIR) -> None:
        self.folder = folder
        self._cache: Dict[str, Optional[np.ndarray]] = {}

    def get(self, name: str) -> Optional[np.ndarray]:
        if name not in self._cache:
            path = os.path.join(self.folder, name + ".wav")
            if os.path.exists(path):
                self._cache[name] = load_wav(path)
            elif name in synth.GENERATED:  # the web game's synthesised effects: built here, never stored
                self._cache[name] = synth.GENERATED[name]()
            else:
                self._cache[name] = None
        return self._cache[name]
