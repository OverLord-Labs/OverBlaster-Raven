"""Render a scene in the web game (headless Chrome) and in this app (QPainter), and diff them.

    .venv/bin/python tools/compare_web.py title over lvl:12:8 --out /tmp/cmp
    .venv/bin/python tools/compare_web.py title --size 640

For each scene it writes <out>/<scene>_web.png, _py.png, _side.png (web | py | diff) and prints the share of pixels that differ
by more than 40 in any channel, and the mean absolute difference. Both use seed 1, so scenes with randomness line up.

The web page lays its stage out as width 100%, height 100dvh - 76 px with a 1 px border and 10 px side padding, so the Chrome
window is sized (size + 22) x (size + 78) to make the canvas exactly size x size at a device pixel ratio of 1 (aspect 1: no side
bars). The web game is served by `npx vite --port 5173` in ../OverBlaster-web; this starts it if nothing is listening.
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageChops  # noqa: E402

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
WEB_DIR = os.environ.get("OVERBLASTER_WEB", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "OverBlaster-web"))
URL = "http://localhost:5173/"


def _up() -> bool:
    try:
        urllib.request.urlopen(URL, timeout=1)
        return True
    except Exception:
        return False


def ensure_server():
    """Start the web dev server if it is not running. Returns the process to stop afterwards (or None)."""
    if _up():
        return None
    proc = subprocess.Popen(["npx", "vite", "--port", "5173", "--strictPort"], cwd=WEB_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if _up():
            return proc
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("could not start the web dev server in " + WEB_DIR)


def shoot_web(scene: str, out_png: str, size: int = 640, seed: int = 1) -> None:
    raw = out_png + ".raw.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={size + 22},{size + 78}",
                    "--force-device-scale-factor=1", "--virtual-time-budget=6000", f"--screenshot={raw}", f"{URL}#test={scene}&freeze&seed={seed}"],
                   capture_output=True, timeout=120)
    im = Image.open(raw).convert("RGB")
    im.crop((11, 1, 11 + size, 1 + size)).save(out_png)  # the canvas sits at (10 + 1 border, 1 border)
    os.remove(raw)


def stats(a: Image.Image, b: Image.Image):
    d = ImageChops.difference(a, b)
    px = d.convert("L").point(lambda v: 255 if v > 40 else 0)
    n = sum(1 for v in px.getdata() if v)
    mean = sum(ImageChops.difference(a.convert("L"), b.convert("L")).getdata()) / (a.size[0] * a.size[1])
    return 100.0 * n / (a.size[0] * a.size[1]), mean, d


def compare(scene: str, out_dir: str, size: int = 640, seed: int = 1):
    from render_scene import render

    os.makedirs(out_dir, exist_ok=True)
    n = scene.replace(":", "_")
    web_png, py_png = os.path.join(out_dir, f"{n}_web.png"), os.path.join(out_dir, f"{n}_py.png")
    shoot_web(scene, web_png, size, seed)
    render(scene, size, seed).save(py_png)
    a, b = Image.open(web_png).convert("RGB"), Image.open(py_png).convert("RGB")
    pct, mean, d = stats(a, b)
    side = Image.new("RGB", (size * 3, size))
    side.paste(a, (0, 0))
    side.paste(b, (size, 0))
    side.paste(d.point(lambda v: min(255, v * 3)), (size * 2, 0))
    side.save(os.path.join(out_dir, f"{n}_side.png"))
    return pct, mean


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenes", nargs="+")
    ap.add_argument("--out", default="/tmp/overblaster_compare")
    ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    server = ensure_server()
    try:
        for sc in a.scenes:
            pct, mean = compare(sc, a.out, a.size, a.seed)
            print(f"{sc:16s} pixels differing by >40: {pct:5.2f}%   mean abs diff: {mean:5.2f}   -> {a.out}/{sc.replace(':', '_')}_side.png")
    finally:
        if server:
            server.terminate()


if __name__ == "__main__":
    main()
