"""The game's sound: what app.py calls. Music, effects, the voice, and keeping all of it out of the mic.

Sound owns a Mixer, a Bank of clips and a sink that plays the mixed output. In tests the sink is a
NullSink and `log` records what was asked for.
"""

from typing import List, Optional, Tuple

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

    def sfx(self, name: str, gain: float = 1.0) -> None:
        if not self.enabled:
            return
        x = self.bank.get(f"sfx_{name}")
        if x is None:
            return
        self._note("sfx", name)
        self.mixer.play(x, gain)

    def say(self, *keys: str) -> None:
        """Speak these clips one after another (a new line replaces one still playing)."""
        if not self.enabled:
            return
        clips = [self.bank.get(f"voice_{k}") for k in keys]
        if not clips or any(c is None for c in clips):
            return
        self._note("say", tuple(keys))
        self.mixer.play(audio.join(clips, gap=0.06), voice=True)

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
