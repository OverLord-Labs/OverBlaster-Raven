"""The game's sound: what app.py calls. Music, effects, the voice, and keeping all of it out of the mic.

Sound owns a Mixer, a Bank of clips and a sink that plays the mixed output. In tests the sink is a
NullSink and `log` records what was asked for.
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from . import audio
from . import config as C
from . import synth

LOG_LIMIT = 200


class NullSink:
    """Plays nothing."""

    def start(self, mixer: audio.Mixer) -> None:
        pass

    def stop(self) -> None:
        pass


class Sound:
    def __init__(self, sink=None, enabled: bool = C.AUDIO_ENABLED, bank: Optional[audio.Bank] = None, mixer: Optional[audio.Mixer] = None) -> None:
        self.enabled = enabled
        self.bank = bank or audio.Bank()
        self.mixer = mixer or audio.Mixer()
        self.sink = sink or NullSink()
        self.echo = audio.EchoGate()
        self.log: List[Tuple] = []
        self._music_name: Optional[str] = None
        self._riser = None  # the warp-charge clip that stopRiser cuts
        if enabled:
            self.sink.start(self.mixer)

    def _note(self, *entry) -> None:
        self.log.append(entry)
        del self.log[:-LOG_LIMIT]

    # ----- playing things -----
    def music(self, which: Optional[str], fade: bool = True) -> None:
        if not self.enabled or which == self._music_name:
            return
        self._music_name = which
        self._note("music", which)
        self.mixer.set_music(self.bank.get(f"music_{which}") if which else None, fade_s=0.8 if fade else 0.0)

    def sfx(self, name: str, gain: float = 1.0, offset: float = 0.0):
        """Play sfx_<name> once, starting `offset` seconds in. Returns a handle for mixer.stop(), or None."""
        if not self.enabled:
            return None
        x = self.bank.get(f"sfx_{name}")
        if x is None:
            return None
        self._note("sfx", name)
        return self.mixer.play(x, gain, offset=offset)

    def zap(self, kind: str) -> None:
        """One of the synthesised effects: "eject", "bad" or "pop"."""
        if not self.enabled:
            return
        x = self.bank.get(f"zap_{kind}")
        if x is None:
            return
        self._note("zap", kind)
        self.mixer.play(x)

    def say(self, *keys: str) -> None:
        """Speak these clips one after another. Any new line cuts off the one still playing; say() with no
        keys just cuts it off. A key with no clip is skipped, like the web game."""
        if not self.enabled:
            return
        self._note("say", tuple(keys))
        self.mixer.stop_voice()
        clips = [c for c in (self.bank.get(f"voice_{k}") for k in keys) if c is not None]
        if clips:
            self.mixer.play(audio.join(clips, gap=0.06), voice=True)

    def alarm(self, on: bool) -> None:
        """The red-alert loop (starts and stops at once)."""
        if not self.enabled:
            return
        self._note("alarm", on)
        if on:
            self.mixer.start_loop("alarm", self.bank.get("loop_alarm"))
        else:
            self.mixer.stop_loop("alarm")

    def drone(self, on: bool) -> None:
        """The engine drone: fades in slowly, fades out in about a second and a half."""
        if not self.enabled:
            return
        self._note("drone", on)
        if on:
            self.mixer.start_loop("drone", self.bank.get("loop_drone"), synth.DRONE_GAIN, synth.DRONE_ATTACK_TAU)
        else:
            self.mixer.stop_loop("drone", synth.DRONE_RELEASE_TAU)

    def handle(self, e: Dict[str, Any]) -> None:
        """Act on one sound event drained from overblaster.core.Game (see core/events.py). Others are ignored."""
        t = e.get("type")
        if t == "sfx":
            clip = self.sfx(e["name"], 1.0 if e.get("gain") is None else e["gain"], e.get("offset") or 0.0)
            if e.get("tag") == "riser":
                self._riser = clip
        elif t == "stopRiser":
            if self.enabled:
                self._note("stopRiser")
                self.mixer.stop(self._riser)
            self._riser = None
        elif t == "zap":
            self.zap(e["kind"])
        elif t == "say":
            self.say(*e["keys"])
        elif t == "music":
            self.music(e["name"])
        elif t == "alarm":
            self.alarm(bool(e["on"]))
        elif t == "drone":
            self.drone(bool(e["on"]))

    def tick(self) -> None:
        """Called once a frame by hosts that want it. The mixer ducks the music under the voice by itself."""

    # ----- the microphone -----
    @property
    def speaking(self) -> bool:
        return self.enabled and self.mixer.speaking

    def gate(self, mic: Optional[float]) -> Optional[float]:
        """The mic level with the game's own sound taken out, and 0 while the voice speaks."""
        if not self.enabled or mic is None:
            return mic
        return self.echo.apply(mic, self.mixer.level, self.mixer.speaking)

    def close(self) -> None:
        self.sink.stop()
