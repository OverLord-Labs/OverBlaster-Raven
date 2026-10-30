"""Thin wrappers over Raven widgets. Written against raven_framework v1.0.6 source.

How MediaViewer behaves (read from the source, not the docs):
  * It is fixed-size (setFixedSize in __init__) and reloads its image from disk on
    every resize, so we never resize a sprite. Worlds change size by swapping to a
    pre-rendered band with load_media(), which only happens a few times per world.
  * paintEvent fills an opaque black rounded rectangle behind the image, whatever the
    image's alpha, so overlapping sprites cut holes in each other. Solid-color bars
    (fully covered) are safe; round art gets corner_radius = size / 2 so its backing
    is a circle that matches it. The default corner_radius would eat thin bars, so
    it is always set explicitly.
  * A hidden GIF keeps animating unless paused, so hide() also calls pause_video().
  * width and height are rounded to a multiple of 4.
"""

from typing import List, Optional

from raven_framework.components.button import Button
from raven_framework.components.media_viewer import MediaViewer
from raven_framework.components.text_box import TextBox

from . import config as C


class Sprite:
    """A positioned image that starts hidden. Call place() to show it."""

    def __init__(self, app, path: str, w: int, h: int = 0, radius: int = 0) -> None:
        self.path = path
        self.w, self.h = w, h or w
        self.radius = radius
        self.widget = MediaViewer(media_path=path, width=self.w, height=self.h, corner_radius=radius)
        app.add(self.widget, x=0, y=0)
        self.widget.hide()
        self.widget.pause_video()  # no-op for still images
        self.visible = False
        self._pos = (None, None)

    def set_media(self, path: str, w: int, h: int = 0) -> None:
        """Swap the image (and size), e.g. when a world crosses into a bigger band."""
        h = h or w
        if path == self.path and (w, h) == (self.w, self.h):
            return
        if (w, h) != (self.w, self.h):
            self.widget.setFixedSize(w, h)
            self.w, self.h = w, h
            if self.radius:  # keep a round sprite's backing circle matched to its size
                self.radius = w // 2
                self.widget.corner_radius = self.radius
        if path != self.path:
            self.widget.load_media(path)  # starts a fresh QMovie that runs immediately
            self.path = path
            if not self.visible:
                self.widget.pause_video()  # don't let a hidden sprite decode frames
        self._pos = (None, None)  # force a re-place after the swap

    def place(self, cx: float, cy: float) -> None:
        """Center the sprite on (cx, cy) and make it visible."""
        pos = (int(cx - self.w / 2), int(cy - self.h / 2))
        if pos != self._pos:  # skip redundant moves to save work
            self.widget.move(*pos)
            self._pos = pos
        if not self.visible:
            self.widget.show()
            self.widget.play_video()
            self.visible = True

    def hide(self) -> None:
        if self.visible:
            self.widget.hide()
            self.widget.pause_video()  # a hidden GIF would otherwise keep decoding frames
            self.visible = False


class Bar:
    """A solid rectangle made by stretching a tiny PNG, in the left-top coordinates of the display."""

    def __init__(self, app, path: str, w: int, h: int) -> None:
        self.sprite = Sprite(app, path, w, h)

    def set_rect(self, x: float, y: float, w: int, h: int) -> None:
        w, h = max(4, int(round(w / 4.0)) * 4), max(4, int(round(h / 4.0)) * 4)
        self.sprite.set_media(self.sprite.path, w, h)
        self.sprite.place(x + w / 2.0, y + h / 2.0)

    def hide(self) -> None:
        self.sprite.hide()


class Crosshair:
    """Four ticks and a center dot, all solid bars so nothing around it is cut out.

    Gap and length are in px; the bars are 4 px thick, the smallest MediaViewer size.
    """

    GAP, LENGTH, THICK = 10, 16, 4

    def __init__(self, app, path: str, dot_path: str) -> None:
        g, n, t = self.GAP, self.LENGTH, self.THICK
        # (dx, dy of the bar's center from the crosshair center, width, height, image)
        self._parts = [
            (0, -(g + n / 2), t, n, path),
            (0, g + n / 2, t, n, path),
            (-(g + n / 2), 0, n, t, path),
            (g + n / 2, 0, n, t, path),
            (0, 0, t, t, dot_path),
        ]
        self.sprites = [Sprite(app, p, int(w), int(h)) for _, _, w, h, p in self._parts]

    def place(self, cx: float, cy: float) -> None:
        for (dx, dy, _, _, _), sprite in zip(self._parts, self.sprites):
            sprite.place(cx + dx, cy + dy)


class Label:
    """A TextBox that only repaints when its text changes."""

    def __init__(self, app, text: str, x: int, y: int, size: int = 28, color: str = "#FFFFFF", **kw) -> None:
        self.widget = TextBox(text=text, font_size=size, text_color=color, **kw)
        app.add(self.widget, x=x, y=y)
        self._text = text
        self._visible = True

    def set(self, text: str) -> None:
        if text != self._text:
            self.widget.set_text(text)
            self._text = text

    def show(self, on: bool = True) -> None:
        if on == self._visible:
            return
        if on:
            self.widget.show()
        else:
            self.widget.hide()
        self._visible = on


class SpritePool:
    """Fixed set of hidden sprites reused for the whole game (no per-frame allocation)."""

    def __init__(self, app, paths: List[str], size: int, radius: int = 0) -> None:
        self.sprites = [Sprite(app, p, size, radius=radius) for p in paths]
        self._used = 0

    def begin_frame(self) -> None:
        self._used = 0

    def next(self) -> Optional[Sprite]:
        if self._used >= len(self.sprites):
            return None
        s = self.sprites[self._used]
        self._used += 1
        return s

    def end_frame(self) -> None:
        for s in self.sprites[self._used:]:
            s.hide()


def static_text(app, text: str, size: int, color: str, y: int) -> TextBox:
    """A centered line of text for the title and game-over screens."""
    box = TextBox(text=text, font_size=size, text_color=color, alignment="center", width=app.width() - 40)
    app.add(box, x=20, y=y)
    return box


def add_centered(app, widget, y: int) -> None:
    app.add(widget, x=int(app.width() / 2 - widget.width() / 2), y=y)


def make_button(text: str, on_click, **kw) -> Button:
    b = Button(center_text=text, **kw)
    b.on_clicked(on_click)
    return b


def display_size(app) -> tuple:
    try:
        return app.width(), app.height()
    except Exception:  # noqa: BLE001
        return C.DISPLAY_PX, C.DISPLAY_PX
