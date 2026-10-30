"""Plays the Mixer's output: through Qt's audio output on a Mac (the simulator), or through the
glasses' Speaker on a Raven device.

Qt: a QAudioSink in push mode, fed by a 20 ms timer on the main thread, so there is no extra thread.

Raven Speaker: it plays one WAV at a time, so the mix is handed over in half-second WAV chunks that
start slightly before the previous one ends. That path could not be tested here (no glasses): see
the README for what to check.
"""

import io
import wave

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import audio
from . import config as C
from .inputs import on_device
from .sound import NullSink, Sound
from .synth import SR, to_int16

PUSH_MS = 20
BUFFER_S = 0.2  # about this much is queued ahead: effects lag by up to this
CHUNK_S = 0.5
CHUNK_OVERLAP_S = 0.05


class QtSink:
    def __init__(self) -> None:
        self._sink = None
        self._io = None
        self._timer = None
        self._mixer = None

    def start(self, mixer: audio.Mixer) -> None:
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            print("[overblaster] sound: no audio output device; running silent")
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(SR)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._mixer = mixer
        self._sink = QAudioSink(device, fmt)
        self._sink.setBufferSize(int(SR * 2 * BUFFER_S))
        self._io = self._sink.start()
        self._timer = QTimer()
        self._timer.timeout.connect(self._pump)
        self._timer.start(PUSH_MS)

    def _pump(self) -> None:
        free = self._sink.bytesFree() // 2
        if free > 0:
            self._io.write(self._mixer.render_pcm(min(free, SR // 4)))

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        if self._sink:
            self._sink.stop()


class SpeakerSink:
    """The glasses' speaker (best effort: see the module notes)."""

    def __init__(self) -> None:
        self._speaker = None
        self._timer = None
        self._mixer = None

    def start(self, mixer: audio.Mixer) -> None:
        from raven_framework.peripherals.speaker import Speaker

        self._mixer = mixer
        self._speaker = Speaker()
        self._timer = QTimer()
        self._timer.timeout.connect(self._send)
        self._timer.start(int((CHUNK_S - CHUNK_OVERLAP_S) * 1000))
        self._send()

    def _send(self) -> None:
        pcm = to_int16(self._mixer.render(int(CHUNK_S * SR))).tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        self._speaker.play_audio(buf.getvalue())

    def stop(self) -> None:
        if self._timer:
            self._timer.stop()
        if self._speaker:
            self._speaker.stop_audio()


def make_sound() -> Sound:
    """The game's Sound, with the right output for where it runs (silent in unit tests and when muted)."""
    if QApplication.instance() is None:  # unit tests: the engine runs and logs, nothing is played
        return Sound(NullSink(), enabled=C.AUDIO_ENABLED)
    if not C.AUDIO_ENABLED:
        return Sound(NullSink(), enabled=False)
    sink = SpeakerSink() if on_device() else QtSink()
    try:
        return Sound(sink)
    except Exception as exc:  # noqa: BLE001 - no sound is better than no game
        print(f"[overblaster] sound unavailable ({exc}); running silent")
        return Sound(NullSink(), enabled=False)
