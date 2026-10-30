"""Renders the voice clips into assets/audio/voice_*.wav with Kokoro text-to-speech, then gives them
a cool ship's-computer sound (overblaster/voicefx.py).

Kokoro and its tools are only needed here, never when the game runs:

    python3 -m venv /tmp/kokoro && /tmp/kokoro/bin/pip install kokoro-onnx "misaki[en]" soundfile
    mkdir -p /tmp/kvoices && cd /tmp/kvoices
    R=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
    curl -LO $R/kokoro-v1.0.onnx && curl -LO $R/voices-v1.0.bin
    /tmp/kokoro/bin/python tools/make_voice.py /tmp/kvoices [voice]      # voice defaults to af_heart

Misaki turns the text into phonemes (it needs no espeak, which does not start on every Mac), Kokoro
speaks them. Kokoro-82M's weights are Apache 2.0. What is said lives in overblaster/voicelines.py.
"""

import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from overblaster import dsp, synth, voicefx, voicelines  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "assets", "audio")
SPEED = 0.97  # a touch slower than the default: calmer, more in control
MAX_GAP = 0.07  # pauses inside a clip (between words, and between the letters of B M S) are cut to this many seconds


def load(folder):
    from kokoro_onnx import Kokoro
    from misaki import en

    model = "kokoro-v1.0.onnx"  # full precision (310 MB); the int8 file is smaller but noticeably rougher
    k = Kokoro(os.path.join(folder, model), os.path.join(folder, "voices-v1.0.bin"))
    return k, en.G2P(trf=False, british=False, fallback=None)


# Spelled-out letters come out as three slow, fully stressed syllables with gaps between. Run them
# together and keep the stress for the first and last letter.
PRONUNCIATIONS = {"bˈi ˈɛm ˈɛs": "bˈiˌɛmˈɛs"}  # B M S


def synthesize(engine, text, voice):
    k, g2p = engine
    phonemes, _ = g2p(text)
    for old, new in PRONUNCIATIONS.items():
        phonemes = phonemes.replace(old, new)
    x, rate = k.create(phonemes, voice=voice, speed=SPEED, lang="en-us", is_phonemes=True)
    return dsp.resample(x.astype(np.float64), rate, synth.SR)  # Kokoro speaks at 24 kHz; the game plays at 44.1 kHz


def trim(x, threshold=0.01, pad=0.03):
    idx = np.nonzero(np.abs(x) > threshold)[0]
    if not len(idx):
        return x
    a, b = max(0, idx[0] - int(pad * synth.SR)), min(len(x), idx[-1] + int(pad * synth.SR))
    return x[a:b]


def write(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(synth.SR)
        w.writeframes(synth.to_int16(x).tobytes())


def main():
    folder = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
    engine = load(folder)
    os.makedirs(OUT, exist_ok=True)
    for key, text in voicelines.all_clips().items():
        x = trim(voicefx.cool(voicefx.tighten(trim(synthesize(engine, text, voice)), max_gap=MAX_GAP)), threshold=0.03, pad=0.1)
        write(os.path.join(OUT, f"voice_{key}.wav"), x)
        print(f"  {key:16s} {len(x) / synth.SR:5.2f} s  {text}")


if __name__ == "__main__":
    main()
