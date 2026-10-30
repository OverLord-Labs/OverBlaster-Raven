"""Renders the sound effects and music into assets/audio/*.wav (numpy only, deterministic).

    .venv/bin/python tools/make_audio.py

Edit overblaster/synth.py and run this again to change a sound.
"""

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from overblaster import synth  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audio")


def write(name, x):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(synth.SR)
        w.writeframes(synth.to_int16(x).tobytes())
    print(f"  {name:18s} {len(x) / synth.SR:6.2f} s  {os.path.getsize(path) / 1024:7.0f} KB")


def main():
    print("sound effects")
    for name in synth.SFX:
        write("sfx_" + name, synth.render_sfx(name))
    for i in range(synth.CHARGE_TICKS):
        write(f"sfx_charge_{i}", synth.peak_normalise(synth.charge_tick(i), 0.7))
    print("music")
    write("music_game", synth.render_music("game"))
    write("music_title", synth.render_music("title"))


if __name__ == "__main__":
    main()
