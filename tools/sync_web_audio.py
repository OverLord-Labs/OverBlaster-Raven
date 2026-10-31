"""Copies the web game's sound into assets/audio/ as 16-bit mono WAVs at the Bank's rate (44.1 kHz).

    .venv/bin/python tools/sync_web_audio.py [--src ../OverBlaster-web/public/audio] [--prune]

The web game (OverBlaster-web) is the source of truth for every clip: sfx_<name>, voice_<key> (the
narrator, the countdown, level numbers and names, ...) and music_game. Needs macOS's `afconvert`.
--prune also deletes WAVs the web game has no clip for.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from overblaster.dsp import SR  # noqa: E402

DEFAULT_SRC = os.path.join(os.path.dirname(ROOT), "OverBlaster-web", "public", "audio")
OUT = os.path.join(ROOT, "assets", "audio")


def convert(src: str, dst: str) -> None:
    subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{SR}", "-c", "1", src, dst], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--prune", action="store_true", help="remove WAVs the web game has no clip for")
    args = ap.parse_args()
    clips = sorted(glob.glob(os.path.join(args.src, "*.m4a")))
    if not clips:
        print(f"no .m4a clips in {args.src}")
        return 1
    os.makedirs(OUT, exist_ok=True)
    names = set()
    for path in clips:
        name = os.path.splitext(os.path.basename(path))[0]
        names.add(name)
        convert(path, os.path.join(OUT, name + ".wav"))
    print(f"converted {len(clips)} clips into {OUT}")
    if args.prune:
        for path in sorted(glob.glob(os.path.join(OUT, "*.wav"))):
            name = os.path.splitext(os.path.basename(path))[0]
            if name not in names:
                os.remove(path)
                print("  removed", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
