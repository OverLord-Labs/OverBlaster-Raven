"""Checks the sound plumbing against real Qt audio output, silently (the master volume is zero).

Run by test_real_framework.py in its own process. Exit code 77 means there is no audio output
device here, so there is nothing to check.
"""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtMultimedia import QMediaDevices
    from PySide6.QtWidgets import QApplication
except ImportError:
    sys.exit(77)

qapp = QApplication(sys.argv)
if QMediaDevices.defaultAudioOutput().isNull():
    sys.exit(77)

from overblaster import audio, sound  # noqa: E402
from overblaster.audiosink import QtSink  # noqa: E402

failures = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)


mixer = audio.Mixer(master=0.0)  # silent: only the plumbing is under test
s = sound.Sound(QtSink(), mixer=mixer)
s.music("game")
s.sfx("explode")
s.say("level_clear")
check(s.speaking, "the voice is speaking as soon as it is asked")
start = mixer._clock
end = time.time() + 2.2
while time.time() < end:
    qapp.processEvents()
    time.sleep(0.005)
advanced = mixer._clock - start
check(advanced > 0.8, f"the sink pulls audio from the mixer in real time ({advanced:.2f} s of sound in 2.2 s)")
check(advanced < 3.5, f"and does not run far ahead of the clock ({advanced:.2f} s)")
end = time.time() + 2.2
while time.time() < end:
    qapp.processEvents()
    time.sleep(0.005)
check(mixer.active_effects == 0, "the explosion has finished playing")
check(not s.speaking, "the voice line is over and the mic is free again")
s.close()
sys.exit(1 if failures else 0)
