"""A stand-in for raven_framework, just enough to run OverBlasterApp without the glasses.

It records every widget created and every call made, so tests can check that the
app only uses calls we believe exist and doesn't allocate widgets during play.
"""

import sys
import types

CREATED = []  # every widget ever constructed, in order
ROUTINES = []


class Widget:
    def __init__(self, **kw):
        self.kw = kw
        self.shown = True
        self.pos = (0, 0)
        self.size = (kw.get("width") or 100, kw.get("height") or 40)
        self.text = kw.get("text") or kw.get("center_text") or ""
        self.callbacks = []
        self.corner_radius = kw.get("corner_radius")
        self.media_path = kw.get("media_path")
        self.paused = False
        self.loads = 0
        CREATED.append(self)

    def width(self):
        return self.size[0]

    def height(self):
        return self.size[1]

    def move(self, x, y):
        self.pos = (x, y)

    def resize(self, w, h):
        raise AssertionError("MediaViewer is fixed-size and reloads on resize: use setFixedSize/load_media")

    def setFixedSize(self, w, h):
        self.size = (w, h)

    def load_media(self, path):
        self.media_path = path
        self.loads += 1
        self.paused = False  # a freshly loaded GIF starts playing, like the real QMovie

    def pause_video(self):
        self.paused = True

    def play_video(self):
        self.paused = False

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False

    def set_text(self, text):
        self.text = text

    def on_clicked(self, fn, *args, **kw):
        self.callbacks.append((fn, args, kw))

    def click(self):
        for fn, args, kw in self.callbacks:
            fn(*args, **kw)


class MediaViewer(Widget):
    pass


class TextBox(Widget):
    pass


class Button(Widget):
    pass


class Container:
    def __init__(self):
        self.children = []
        self.origin = (0, 0)  # where the game area sits inside the app window (real: 40, 50)

    def x(self):
        return self.origin[0]

    def y(self):
        return self.origin[1]

    def add(self, widget, x=None, y=None):
        self.children.append(widget)
        if x is not None:
            widget.pos = (x, y)

    def clear(self):
        self.children = []

    def width(self):
        return 640

    def height(self):
        return 640


class RavenApp:
    def __init__(self, parent=None):
        self.app = Container()

    def setMouseTracking(self, on):
        self.mouse_tracking = on

    def keyPressEvent(self, event):
        self.unhandled_key = event.text()

    def closeEvent(self, event):
        self.closed = True


class Routine:
    def __init__(self, interval_ms, invoke, mode="repeat", parent=None):
        self.interval_ms, self.invoke, self.mode, self.stopped = interval_ms, invoke, mode, False
        ROUTINES.append(self)

    def stop(self):
        self.stopped = True


class RunApp:
    @staticmethod
    def run(*a, **kw):
        raise AssertionError("not used in tests")


def fade_in(widget, *a, **kw):
    pass


def install() -> None:
    """Register fake modules under the names the app imports."""
    pkg = types.ModuleType("raven_framework")
    pkg.RavenApp, pkg.Routine, pkg.RunApp, pkg.fade_in = RavenApp, Routine, RunApp, fade_in
    sys.modules["raven_framework"] = pkg
    for path, name, cls in (
        ("raven_framework.components", None, None),
        ("raven_framework.components.button", "Button", Button),
        ("raven_framework.components.media_viewer", "MediaViewer", MediaViewer),
        ("raven_framework.components.text_box", "TextBox", TextBox),
    ):
        mod = types.ModuleType(path)
        if name:
            setattr(mod, name, cls)
        sys.modules[path] = mod
    CREATED.clear()
    ROUTINES.clear()
